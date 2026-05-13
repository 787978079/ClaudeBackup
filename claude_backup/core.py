"""核心业务：init / backup / release / compare / list / scheduled-daily.

所有 GUI / 托盘 / 右键菜单 / CLI 都最终调到这里，保证行为一致.

设计：
- 每个高层操作返回一个 dataclass 结果，便于 GUI 展示/日志
- 长任务接受 progress 回调（callable[[str], None]），分阶段汇报进度
- 异常要么吞（hook 场景）要么向上抛（GUI 场景），由调用层决定
"""
from __future__ import annotations
import filecmp
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable

from . import change_detect, git_ops, logger, paths, registry

log = logger.get(__name__)


ProgressFn = Callable[[str], None]


def _noop(_msg: str) -> None: pass


# ---------- 结果类型 ----------

@dataclass
class InitResult:
    project: registry.ProjectEntry
    created_mirror: bool
    created_bundle_dir: bool
    added_remote: bool
    added_github_remote: bool
    wrote_gitignore: bool = False
    detected_heavy_dirs: list[str] = field(default_factory=list)


@dataclass
class BackupResult:
    project_name: str
    pushed_to_nas: bool
    bundle_path: Path | None
    new_head: str | None
    skipped: bool
    skip_reason: str | None
    note: str | None = None
    dir_snapshot_path: Path | None = None  # 完整目录拷贝（手动/定时备份会生成）
    auto_committed: bool = False           # 是否后台自动 commit 了脏改动
    git_baseline_warning: str | None = None  # git baseline 失败但 dir_snapshot 已成时的警告文案


@dataclass
class ReleaseResult:
    project_name: str
    version: str
    tag_created: bool
    pushed_to_nas: bool
    pushed_to_github: bool
    bundle_path: Path | None


@dataclass
class CompareResult:
    project_name: str
    ref1: str
    ref2: str
    summary: str
    files: list[tuple[str, str]]   # (status, filename)


@dataclass
class BackupPoint:
    """List 视图里的一行（混合 commit / bundle / dir_snapshot / release）."""
    kind: str                       # commit / bundle / dir_snapshot / release
    label: str                      # 显示文案
    when: datetime | None
    detail: str                     # commit msg / bundle path / 目录路径 / tag desc
    git_ref: str | None = None      # 能用作 git 对比的引用（commit hash / tag name），无则 None
    fs_path: Path | None = None     # 文件系统路径（dir_snapshot 是目录、bundle/release 是 .bundle 文件）


@dataclass
class ListResult:
    project_name: str
    points: list[BackupPoint]


@dataclass
class RestoreResult:
    project_name: str
    snapshot_used: Path
    safety_backup: Path        # 恢复前的项目状态被存到这里（防止恢复操作误删工作）
    restored_count: int


@dataclass
class FileVersion:
    """某文件在某个备份点中的存在性 + 大小（不读内容，只索引）."""
    point: "BackupPoint"
    size: int | None


@dataclass
class RestoreFileResult:
    project_name: str
    rel_path: str
    safety_path: Path | None    # 覆写前对当前文件做的安全备份位置
    bytes_written: int


@dataclass
class MigrationResult:
    old_root: Path
    new_root: Path
    files_copied: int
    bytes_copied: int
    projects_updated: int       # registry 里改了路径前缀的项目数
    git_remotes_updated: int    # 项目本地 .git/config 改了 nas URL 的数量
    errors: list[str] = field(default_factory=list)


@dataclass
class ScheduledRunResult:
    started_at: datetime
    finished_at: datetime
    backed_up: list[str]            # 项目名
    skipped: list[tuple[str, str]]  # (项目名, 原因)
    failed: list[tuple[str, str]]   # (项目名, 错误)


# ---------- 工具 ----------

def _project_name(path: str | Path) -> str:
    return Path(path).resolve().name


def _resolve(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def _next_unique_dir(parent: Path, base: str) -> Path:
    """返回 parent/<base> 不存在的路径；若存在加 _2 _3 直到不重复."""
    candidate = parent / base
    n = 2
    while candidate.exists():
        candidate = parent / f"{base}_{n}"
        n += 1
    return candidate


def _mirror_project_tree(src: Path, dst: Path,
                         exclude_patterns: tuple[str, ...]) -> None:
    """把 src 整个目录拷贝到 dst（dst 不存在）.

    优先策略：
      - 项目是 git 仓库 + 配置 mirror_use_gitignore=True → 用 git ls-files 列出
        git 认可的文件（自动遵循 .gitignore + .git/info/exclude），
        再叠加 exclude_patterns 防 .gitignore 没排 node_modules 等
      - 否则回退到 shutil.copytree + ignore_patterns 模式
    """
    from . import config as _cfg
    cfg = _cfg.load()

    # 合并默认排除 + 用户自定义额外排除
    excludes = set(exclude_patterns)
    if cfg.mirror_extra_excludes:
        excludes.update(cfg.mirror_extra_excludes)

    use_git = (cfg.mirror_use_gitignore and git_ops.is_git_repo(src))

    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.mkdir(parents=True, exist_ok=False)

    import fnmatch

    def _is_excluded_by_patterns(rel_path: str) -> bool:
        # 匹配任一段 basename 命中 patterns 即排除（与 shutil.ignore_patterns 行为一致）
        parts = Path(rel_path).parts
        for part in parts:
            for pat in excludes:
                if fnmatch.fnmatch(part, pat):
                    return True
        # 整路径的 *.ext 匹配
        for pat in excludes:
            if fnmatch.fnmatch(rel_path, pat):
                return True
        return False

    if use_git:
        # git ls-files 列出 cached + others（含 untracked）但排除 ignored
        r = git_ops.run(
            ["ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=src, check=False,
        )
        rels = [s for s in r.stdout.split("\0") if s]
        for rel in rels:
            if _is_excluded_by_patterns(rel):
                continue
            srcf = src / rel
            if not srcf.is_file():
                continue
            dstf = dst / rel
            dstf.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(srcf, dstf)
            except OSError as e:
                log.warning("拷贝 %s 失败: %s", rel, e)
    else:
        # 回退：shutil.copytree + ignore_patterns
        # 注意 dst 已 mkdir，要用 dirs_exist_ok=True
        shutil.copytree(
            src, dst,
            ignore=shutil.ignore_patterns(*excludes),
            dirs_exist_ok=True,
        )


def _enforce_retention(snapshots_root: Path, bundle_dir: Path,
                       *, keep_dir_snapshots: int,
                       keep_bundles: int) -> None:
    """按 keep_last_n 删除超出策略的旧目录快照和 bundle. 0 = 不限."""
    if keep_dir_snapshots > 0 and snapshots_root.exists():
        dirs = sorted(
            [d for d in snapshots_root.iterdir() if d.is_dir()],
            key=lambda d: d.stat().st_mtime,
            reverse=True,
        )
        for old in dirs[keep_dir_snapshots:]:
            try:
                shutil.rmtree(old)
                log.info("已清理旧目录快照: %s", old)
            except OSError as e:
                log.warning("清理 %s 失败: %s", old, e)

    if keep_bundles > 0 and bundle_dir.exists():
        # 只清根目录的 *.bundle，不动 releases/ 子目录
        bundles = sorted(
            [f for f in bundle_dir.glob("*.bundle") if f.is_file()],
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )
        for old in bundles[keep_bundles:]:
            try:
                old.unlink()
                log.info("已清理旧 bundle: %s", old)
            except OSError as e:
                log.warning("清理 %s 失败: %s", old, e)


# 注册项目时若工作树根含这些目录之一，且没有 .gitignore，就主动写一份保守的
# .gitignore——避免下次 git add -A 因数十万 node_modules 文件超时，或被
# 临时缓存撑爆 index。检测列表故意小而精，只覆盖会显著拖慢/阻塞 git 的目录。
_HEAVY_DIRS = (
    "node_modules",     # Node — 数十万小文件
    ".next",            # Next.js build
    ".nuxt",            # Nuxt build
    "dist",             # 通用构建产物
    "build",            # 通用构建产物
    "out",              # Next.js export / 其它
    "target",           # Rust / Java
    "__pycache__",      # Python 字节码（递归会有很多）
    ".venv",            # Python venv
    "venv",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".playwright-mcp",  # Playwright MCP 产生的测试日志
    "playwright-report",
    "coverage",
    ".nyc_output",
    "htmlcov",
)

# 保守的 .gitignore 模板：覆盖最常见的 OS / IDE / Python / Node 噪音。
# 不要太激进——用户可能希望保留某些目录入仓。
_GITIGNORE_TEMPLATE = """# 由 ClaudeBackup 注册项目时自动生成。
# 目的：让 git 备份基线（git add -A）不被海量缓存/构建产物拖死。
# 你可以随时编辑此文件，ClaudeBackup 后续不会覆盖。

# OS
.DS_Store
Thumbs.db

# IDE
.vscode/
.idea/
*.swp

# Python
__pycache__/
*.pyc
*.pyo
.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage
htmlcov/
.venv/
venv/
env/

# Node
node_modules/
.next/
.nuxt/
out/

# Build artifacts
dist/
build/
target/

# Test artifacts
.playwright-mcp/
playwright-report/
coverage/
.nyc_output/
"""


def _detect_heavy_dirs(proj: Path) -> list[str]:
    """扫工作树根（不递归），返回存在的"大目录" 名称."""
    found: list[str] = []
    for name in _HEAVY_DIRS:
        if (proj / name).is_dir():
            found.append(name)
    return found


def _ensure_gitignore(proj: Path) -> tuple[bool, list[str]]:
    """若项目根没有 .gitignore 且检测到大目录，写一份保守模板。

    Returns: (wrote, heavy_dirs_detected)
    """
    heavy = _detect_heavy_dirs(proj)
    gi = proj / ".gitignore"
    if gi.exists():
        return False, heavy
    if not heavy:
        # 没有大目录就不主动侵入项目；让用户自己决定要不要 .gitignore
        return False, heavy
    try:
        gi.write_text(_GITIGNORE_TEMPLATE, encoding="utf-8")
        log.info("已为 %s 写入推荐 .gitignore（检测到大目录: %s）", proj, ", ".join(heavy))
        return True, heavy
    except OSError as e:
        log.warning("写入 .gitignore 失败: %s", e)
        return False, heavy


_WINDOWS_RESERVED_RE = re.compile(
    r"unable to index file ['\"]?([^'\"\n]*?(?:NUL|CON|PRN|AUX|COM[1-9]|LPT[1-9])(?:\.[^'\"\n/\\]*)?)['\"]?",
    re.IGNORECASE,
)


def _diagnose_git_add_error(stderr: str) -> str | None:
    """从 git add 的 stderr 里识别已知的可操作错误，给出更明确的修复指引。

    返回 None 表示未匹配已知模式（调用方应回落到通用提示）。
    """
    if not stderr:
        return None
    m = _WINDOWS_RESERVED_RE.search(stderr)
    if m:
        offending = m.group(1).strip()
        return (
            f"项目里有 Windows 保留名文件 '{offending}'，git 无法索引。"
            f"完整目录已备份到备份位置。修复方法：在 PowerShell 跑 "
            f"`Remove-Item -LiteralPath '\\\\?\\<完整路径>' -Force` 删除该文件后重试"
        )
    if "short read while indexing" in stderr or "failed to insert into database" in stderr:
        return (
            "git 索引文件失败（可能存在 Windows 保留名文件 NUL/CON/PRN 等，"
            "或文件被其它进程占用）。完整目录已备份到备份位置"
        )
    return None


def _auto_commit_if_needed(proj: Path, *, step: "ProgressFn") -> tuple[bool, bool, str | None]:
    """如果工作树有改动 / 仓库还没 commit，自动 commit 一次.

    策略：
      - 完全空仓库（无任何 commit）：直接在当前分支上 commit 首个版本，作为后续基线
      - 已有 commit + dirty：切到临时分支 auto/snapshot-<ts> commit，再切回原分支
        （保持用户主分支历史干净）

    Returns: (auto_committed, used_temp_branch, warning)
        warning 仅在 git 操作失败时非 None；调用方可以决定是否吞掉。dir_snapshot
        作为更可靠的备份机制此时已经先做过，所以这里失败不应该让整个备份失败。
    """
    is_repo = git_ops.is_git_repo(proj)
    if not is_repo:
        step("初始化 git 仓库（项目还不是 git 项目）")
        try:
            git_ops.init_repo(proj)
        except (git_ops.GitError, subprocess.TimeoutExpired) as e:
            return False, False, f"git init 失败：{e}"

    has_commit = git_ops.has_any_commit(proj)
    dirty = git_ops.is_working_tree_dirty(proj) if has_commit else False
    has_files = any(proj.iterdir())  # 至少有一个文件，避免 empty commit

    if not has_commit:
        if not has_files:
            return False, False, None
        ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        step("把当前所有文件保存为第一个版本")
        try:
            git_ops.commit_all_or_empty(proj, f"manual-snapshot {ts}")
        except subprocess.TimeoutExpired:
            return False, False, (
                "git add -A 超时（项目工作树过大）。"
                "完整目录已备份到备份位置；建议在项目根加 .gitignore "
                "排除 node_modules / .playwright-mcp / dist 等目录后再试一次"
            )
        except git_ops.GitError as e:
            diag = _diagnose_git_add_error(e.stderr)
            return False, False, diag or f"git baseline 创建失败：{e.stderr or e}"
        return True, False, None

    if dirty:
        ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        original = git_ops.safe_current_branch(proj)
        tmp_branch = f"auto/snapshot-{ts}"
        n = 2
        while git_ops.branch_exists(proj, tmp_branch):
            tmp_branch = f"auto/snapshot-{ts}_{n}"
            n += 1
        step("把当前修改保存到临时分支（不污染主分支）")
        try:
            git_ops.checkout(proj, tmp_branch, create=True)
        except (git_ops.GitError, subprocess.TimeoutExpired) as e:
            return False, False, f"切临时分支失败：{e}"
        try:
            try:
                git_ops.commit_all_or_empty(proj, f"manual-snapshot {ts}")
            except subprocess.TimeoutExpired:
                return False, True, (
                    "git add -A 超时（项目工作树过大）。完整目录已备份到备份位置；"
                    "建议加 .gitignore 排除大目录后再试"
                )
            except git_ops.GitError as e:
                diag = _diagnose_git_add_error(e.stderr)
                return False, True, diag or f"自动 commit 失败：{e.stderr or e}"
        finally:
            if original:
                try:
                    git_ops.checkout(proj, original)
                except (git_ops.GitError, subprocess.TimeoutExpired) as e:
                    log.warning("切回原分支失败 (%s)：%s", original, e)
        return True, True, None

    return False, False, None


# ---------- init ----------

def init_project(project_path: str | Path,
                 github_url: str | None = None,
                 display_name: str | None = None,
                 progress: ProgressFn | None = None) -> InitResult:
    """注册一个项目：建 NAS 镜像、加 nas remote、（可选）GitHub remote、写 registry.

    progress: 可选的进度回调，每个主要阶段开始时被调用，参数是阶段描述."""
    step = progress or _noop

    step("检查项目文件夹")
    proj = _resolve(project_path)
    if not proj.exists():
        raise FileNotFoundError(f"项目目录不存在: {proj}")

    if not git_ops.is_git_repo(proj):
        step("初始化 git 仓库（项目还不是 git 项目）")
        log.info("项目尚未 git init，自动初始化: %s", proj)
        git_ops.init_repo(proj)

    # 在 git 化之后、第一次 add 之前主动写 .gitignore，避免巨型项目的
    # node_modules 等把首次 baseline 拖死或弄出 NUL 之类的索引错误。
    wrote_gitignore, heavy_dirs = _ensure_gitignore(proj)
    if wrote_gitignore:
        step(f"已写入推荐 .gitignore（检测到 {', '.join(heavy_dirs)}）")

    name = display_name or proj.name
    nas_mirror = paths.NAS_BACKUPS_DIR / f"{name}.git"
    bundle_dir = paths.NAS_BUNDLES_DIR / name

    step("准备备份目录")
    paths.ensure_nas_dirs()

    created_mirror = False
    if not nas_mirror.exists():
        step(f"创建镜像 {nas_mirror.name}")
        git_ops.init_bare(nas_mirror)
        created_mirror = True
        log.info("创建 NAS 镜像: %s", nas_mirror)

    created_bundle = False
    if not bundle_dir.exists():
        step("创建时间快照目录")
        bundle_dir.mkdir(parents=True, exist_ok=True)
        (bundle_dir / "releases").mkdir(parents=True, exist_ok=True)
        created_bundle = True

    step("配置 nas remote")
    added_nas_remote = False
    if not git_ops.has_remote(proj, paths.NAS_REMOTE_NAME):
        git_ops.add_remote(proj, paths.NAS_REMOTE_NAME, str(nas_mirror))
        added_nas_remote = True
    else:
        existing = git_ops.list_remotes(proj).get(paths.NAS_REMOTE_NAME)
        if existing and existing != str(nas_mirror):
            git_ops.set_remote_url(proj, paths.NAS_REMOTE_NAME, str(nas_mirror))

    added_github = False
    if github_url:
        step("配置 GitHub remote")
        if not git_ops.has_remote(proj, "origin"):
            git_ops.add_remote(proj, "origin", github_url)
            added_github = True
        else:
            existing = git_ops.list_remotes(proj).get("origin")
            if existing != github_url:
                git_ops.set_remote_url(proj, "origin", github_url)
                added_github = True

    step("登记到项目列表")
    entry = registry.ProjectEntry(
        name=name,
        path=str(proj),
        nas_mirror=str(nas_mirror),
        bundle_dir=str(bundle_dir),
        github_url=github_url,
    )
    registry.upsert(entry)

    if git_ops.has_any_commit(proj):
        step("首次同步到备份位置（项目越大越慢）")
        try:
            git_ops.push_all(proj, paths.NAS_REMOTE_NAME)
            registry.update_last_backup(proj, git_ops.head_hash(proj))
        except git_ops.GitError as e:
            log.warning("初次推送 NAS 失败（不阻塞）: %s", e.stderr)

    step("完成")

    return InitResult(
        project=entry,
        created_mirror=created_mirror,
        created_bundle_dir=created_bundle,
        added_remote=added_nas_remote,
        added_github_remote=added_github,
        wrote_gitignore=wrote_gitignore,
        detected_heavy_dirs=heavy_dirs,
    )


# ---------- backup（手动/定时/自动 共用） ----------

def backup_project(project_path: str | Path,
                   *,
                   make_bundle: bool = True,
                   skip_if_no_change: bool = False,
                   commit_dirty: bool = True,
                   mirror_files: bool = True,
                   note: str | None = None,
                   progress: ProgressFn | None = None) -> BackupResult:
    """对单个项目做一次备份.

    流程（手动 / 定时备份默认值）：
      1. 不是 git 仓库 → 自动 git init
      2. 工作树有未提交改动 → 自动 commit 到临时分支（不污染主分支）；空仓库则
         直接在当前分支建立第一个 baseline commit
      3. push --all 到 NAS bare 镜像
      4. 把整个项目目录拷贝到 Y:/snapshots/<项目>/<时间戳>/（用户能直接看 / 拷回）
      5. 生成 git bundle（含所有分支）

    参数：
      skip_if_no_change=True  → 定时任务用，没变就跳过
      commit_dirty=True       → 自动 commit 工作树脏改动到临时分支（默认开）
      mirror_files=True       → 把项目目录树整份拷贝到 NAS（默认开）
      make_bundle=True        → 生成 git bundle 时间快照（默认开）
    """
    step = progress or _noop
    proj = _resolve(project_path)
    name = _project_name(proj)

    reg = registry.load()
    entry = reg.find_by_path(proj)
    if entry is None:
        raise ValueError(f"项目尚未注册（请先 init）: {proj}")

    # 1. 保证是 git 仓库（若不是自动 init）
    if not git_ops.is_git_repo(proj):
        step("初始化 git 仓库（项目还不是 git 项目）")
        git_ops.init_repo(proj)

    # 2. 先做目录拷贝（**无条件**，不依赖 git 变化检测）
    #    定时备份每天总要产出一份目录快照，即使代码没变 —— 这是"时光机"价值所在.
    dir_snapshot_path: Path | None = None
    if mirror_files:
        step("拷贝完整目录到备份位置（排除 .git / node_modules 等）")
        ts_full = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        snapshots_root = paths.NAS_SNAPSHOTS_DIR / name
        snapshots_root.mkdir(parents=True, exist_ok=True)
        dir_snapshot_path = _next_unique_dir(snapshots_root, ts_full)
        try:
            _mirror_project_tree(proj, dir_snapshot_path,
                                 paths.DEFAULT_MIRROR_EXCLUDES)
        except OSError as e:
            log.error("目录拷贝失败：%s", e)
            dir_snapshot_path = None

    # 3. 检查变化（仅决定 git push/bundle 是否要跑）
    step("检查变化")
    status = change_detect.detect(proj, reg)
    git_skip = (
        skip_if_no_change and
        not status.has_changes and
        git_ops.has_any_commit(proj)
    )
    if git_skip:
        # 目录快照已经拷了，这里只跳过 git 的 push/bundle 部分
        log.info("跳过 git 部分备份（无新提交 + 无脏改动），dir_snapshot 已生成: %s",
                 dir_snapshot_path)
        # 触发保留策略清理（即使 git 跳过，目录快照数也变了）
        try:
            from . import config as _cfg
            cfg = _cfg.load()
            _enforce_retention(
                paths.NAS_SNAPSHOTS_DIR / name,
                Path(entry.bundle_dir),
                keep_dir_snapshots=cfg.retention_keep_last_dir_snapshots,
                keep_bundles=cfg.retention_keep_last_bundles,
            )
        except OSError as e:
            log.warning("保留策略清理失败: %s", e)
        return BackupResult(
            project_name=name,
            pushed_to_nas=False,
            bundle_path=None,
            new_head=status.head_hash,
            skipped=True,
            skip_reason=status.reason,
            note=note,
            dir_snapshot_path=dir_snapshot_path,
            auto_committed=False,
        )

    # 4. 自动 commit 工作树（dirty / 空仓库都覆盖）
    auto_committed = False
    git_baseline_warning: str | None = None
    if commit_dirty:
        auto_committed, _, git_baseline_warning = _auto_commit_if_needed(proj, step=step)
        if git_baseline_warning:
            # 不抛出。dir_snapshot 已经在 step 2 拷好了——那才是真正的备份；
            # git baseline 只是辅助。把警告带回 BackupResult，由 GUI 决定怎么呈现。
            log.warning("git baseline 跳过：%s", git_baseline_warning)
            step(f"⚠️ {git_baseline_warning}")

    # 5. push 到 NAS（只有在已有 commit 的情况下才推；前面 baseline 失败时无 commit 就跳过）
    if not git_ops.has_remote(proj, paths.NAS_REMOTE_NAME):
        raise RuntimeError(f"项目缺少 nas remote，请先重新添加项目: {proj}")
    pushed_to_nas = False
    if git_ops.has_any_commit(proj):
        step("上传到备份位置")
        try:
            git_ops.push_all(proj, paths.NAS_REMOTE_NAME)
            pushed_to_nas = True
        except (git_ops.GitError, subprocess.TimeoutExpired) as e:
            # 推送失败也不打断 dir_snapshot 备份
            log.warning("push 到 NAS 失败：%s", e)
            git_baseline_warning = (git_baseline_warning + "；" if git_baseline_warning else "") + \
                f"备份位置推送失败：{getattr(e, 'stderr', None) or e}"

    new_head = git_ops.head_hash(proj) if git_ops.has_any_commit(proj) else None

    # 6. 生成 git bundle（增量历史用）
    bundle_path: Path | None = None
    if make_bundle and git_ops.has_any_commit(proj):
        step("生成时间快照 bundle")
        bundle_dir = Path(entry.bundle_dir)
        bundle_dir.mkdir(parents=True, exist_ok=True)
        date = datetime.now().strftime("%Y-%m-%d")
        ts_full = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        candidate = bundle_dir / f"{date}.bundle"
        if candidate.exists():
            candidate = bundle_dir / f"{ts_full}.bundle"
        bundle_path = candidate
        git_ops.bundle_create(proj, bundle_path)

    if new_head:
        registry.update_last_backup(proj, new_head)

    # 7. 应用保留策略：清掉超出限额的旧 snapshot/bundle
    try:
        from . import config as _cfg
        cfg = _cfg.load()
        _enforce_retention(
            paths.NAS_SNAPSHOTS_DIR / name,
            Path(entry.bundle_dir),
            keep_dir_snapshots=cfg.retention_keep_last_dir_snapshots,
            keep_bundles=cfg.retention_keep_last_bundles,
        )
    except OSError as e:
        log.warning("保留策略清理失败: %s", e)

    step("完成")
    return BackupResult(
        project_name=name,
        pushed_to_nas=pushed_to_nas,
        bundle_path=bundle_path,
        new_head=new_head,
        skipped=False,
        skip_reason=None,
        note=note,
        dir_snapshot_path=dir_snapshot_path,
        auto_committed=auto_committed,
        git_baseline_warning=git_baseline_warning,
    )


# ---------- release ----------

def release_project(project_path: str | Path,
                    version: str,
                    description: str = "",
                    *,
                    push_github: bool = True) -> ReleaseResult:
    """打 tag → push nas（含 tag）→ push github（含 tag）→ 归档 bundle 到 releases/."""
    proj = _resolve(project_path)
    name = _project_name(proj)
    reg = registry.load()
    entry = reg.find_by_path(proj)
    if entry is None:
        raise ValueError(f"项目尚未注册: {proj}")
    if not git_ops.has_any_commit(proj):
        raise RuntimeError("项目里还没有任何提交，无法发布")

    # 打 tag（如果不存在）
    existing_tags = set(git_ops.list_tags(proj))
    tag_created = False
    if version not in existing_tags:
        msg = description or f"Release {version}"
        git_ops.tag(proj, version, message=msg)
        tag_created = True

    # 推 NAS
    pushed_nas = False
    try:
        git_ops.push_all(proj, paths.NAS_REMOTE_NAME)
        git_ops.push_tags(proj, paths.NAS_REMOTE_NAME)
        pushed_nas = True
    except git_ops.GitError as e:
        log.error("推 NAS 失败: %s", e.stderr)

    # 推 GitHub
    pushed_github = False
    if push_github and entry.github_url:
        try:
            if git_ops.has_remote(proj, "origin"):
                git_ops.push_all(proj, "origin")
                git_ops.push_tags(proj, "origin")
                pushed_github = True
        except git_ops.GitError as e:
            log.error("推 GitHub 失败: %s", e.stderr)

    # 归档 bundle
    releases_dir = Path(entry.bundle_dir) / "releases"
    releases_dir.mkdir(parents=True, exist_ok=True)
    bundle_path = releases_dir / f"{version}.bundle"
    git_ops.bundle_create(proj, bundle_path)

    registry.update_last_backup(proj, git_ops.head_hash(proj))

    return ReleaseResult(
        project_name=name,
        version=version,
        tag_created=tag_created,
        pushed_to_nas=pushed_nas,
        pushed_to_github=pushed_github,
        bundle_path=bundle_path,
    )


# ---------- compare ----------

def compare_refs(project_path: str | Path, ref1: str, ref2: str) -> CompareResult:
    proj = _resolve(project_path)
    name = _project_name(proj)
    summary = git_ops.diff_summary(proj, ref1, ref2)
    files = git_ops.diff_name_status(proj, ref1, ref2)
    return CompareResult(
        project_name=name,
        ref1=ref1,
        ref2=ref2,
        summary=summary,
        files=files,
    )


def compare_dir_snapshots(snap1: str | Path,
                          snap2: str | Path,
                          *,
                          progress: ProgressFn | None = None) -> CompareResult:
    """对比两个目录快照（按文件树）— 列出新增 / 删除 / 修改的文件.

    用 filecmp 进行内容比较（shallow=False，按字节比对）.
    返回的 files 列表与 git diff 形式一致：[(status, path), ...]
      status: 'A' 新增, 'D' 删除, 'M' 修改
    """
    step = progress or _noop
    s1 = Path(snap1).expanduser().resolve()
    s2 = Path(snap2).expanduser().resolve()
    if not s1.is_dir():
        raise FileNotFoundError(f"快照不存在: {s1}")
    if not s2.is_dir():
        raise FileNotFoundError(f"快照不存在: {s2}")

    step("扫描两边的文件清单")
    files1 = {str(p.relative_to(s1)).replace("\\", "/")
              for p in s1.rglob("*") if p.is_file()}
    files2 = {str(p.relative_to(s2)).replace("\\", "/")
              for p in s2.rglob("*") if p.is_file()}

    only_2 = sorted(files2 - files1)   # 起点没有，终点有 → 新增
    only_1 = sorted(files1 - files2)   # 起点有，终点没有 → 删除
    common = sorted(files1 & files2)

    step(f"对比 {len(common)} 个共同文件的内容")
    modified: list[str] = []
    for rel in common:
        try:
            same = filecmp.cmp(str(s1 / rel), str(s2 / rel), shallow=False)
        except OSError:
            same = False
        if not same:
            modified.append(rel)

    files: list[tuple[str, str]] = []
    for rel in only_2:
        files.append(("A", rel))
    for rel in only_1:
        files.append(("D", rel))
    for rel in modified:
        files.append(("M", rel))

    summary = (
        f"新增 {len(only_2)} 个文件\n"
        f"删除 {len(only_1)} 个文件\n"
        f"修改 {len(modified)} 个文件\n"
        f"未变化 {len(common) - len(modified)} 个文件"
    )
    step("完成")
    return CompareResult(
        project_name=s1.parent.name,
        ref1=s1.name,
        ref2=s2.name,
        summary=summary,
        files=files,
    )


# ---------- list ----------

def list_backup_points(project_path: str | Path,
                       limit_commits: int = 50) -> ListResult:
    proj = _resolve(project_path)
    name = _project_name(proj)
    reg = registry.load()
    entry = reg.find_by_path(proj)

    points: list[BackupPoint] = []

    # commits（带提交时间）
    if git_ops.has_any_commit(proj):
        commits_with_time = git_ops.log_oneline_with_time(proj, limit=limit_commits)
        for h, ts, s in commits_with_time:
            points.append(BackupPoint(
                kind="commit",
                label=h[:7],
                when=ts,
                detail=s,
                git_ref=h,
            ))

    # bundles
    if entry:
        bundle_dir = Path(entry.bundle_dir)
        if bundle_dir.exists():
            for f in sorted(bundle_dir.glob("*.bundle"), reverse=True):
                points.append(BackupPoint(
                    kind="bundle",
                    label=f.stem,
                    when=datetime.fromtimestamp(f.stat().st_mtime),
                    detail=str(f),
                    fs_path=f,
                ))
            releases = bundle_dir / "releases"
            if releases.exists():
                for f in sorted(releases.glob("*.bundle"), reverse=True):
                    # release tag name 通常等于 stem（如 v0.0.1）
                    tag_name = f.stem
                    git_ref = tag_name if tag_name in git_ops.list_tags(proj) else None
                    points.append(BackupPoint(
                        kind="release",
                        label=f.stem,
                        when=datetime.fromtimestamp(f.stat().st_mtime),
                        detail=str(f),
                        git_ref=git_ref,
                        fs_path=f,
                    ))

    # 目录快照（手动 / 定时备份的整目录拷贝）
    snap_root = paths.NAS_SNAPSHOTS_DIR / name
    if snap_root.exists():
        for d in sorted(snap_root.iterdir(), reverse=True):
            if not d.is_dir():
                continue
            points.append(BackupPoint(
                kind="dir_snapshot",
                label=d.name,
                when=datetime.fromtimestamp(d.stat().st_mtime),
                detail=str(d),
                fs_path=d,
            ))

    # 按时间倒序统一排
    points.sort(key=lambda p: p.when or datetime.min, reverse=True)

    return ListResult(project_name=name, points=points)


# ---------- 文件级历史 ----------

def list_file_history(project_path: str | Path,
                      rel_path: str,
                      points: list[BackupPoint] | None = None) -> list[FileVersion]:
    """列出某文件在所有备份点中的存在情况（不读内容，只看 size）.

    支持的备份点：dir_snapshot（直接看文件）/ commit / release（git cat-file）.
    bundle 暂不支持.
    """
    rel_path = rel_path.replace("\\", "/")
    proj = _resolve(project_path)
    if points is None:
        points = list_backup_points(proj).points

    versions: list[FileVersion] = []
    for p in points:
        size: int | None = None
        if p.kind == "dir_snapshot" and p.fs_path:
            f = Path(p.fs_path) / rel_path
            if f.is_file():
                try:
                    size = f.stat().st_size
                except OSError:
                    continue
            else:
                continue
        elif p.kind in ("commit", "release"):
            ref = p.git_ref or p.label
            r = git_ops.run(["cat-file", "-e", f"{ref}:{rel_path}"],
                            cwd=proj, check=False)
            if r.returncode != 0:
                continue
            r2 = git_ops.run(["cat-file", "-s", f"{ref}:{rel_path}"],
                             cwd=proj, check=False)
            if r2.returncode == 0:
                try:
                    size = int(r2.stdout.strip())
                except ValueError:
                    pass
        else:
            continue
        versions.append(FileVersion(point=p, size=size))
    return versions


def read_file_at_point(point: BackupPoint, rel_path: str,
                       project_path: str | Path) -> bytes:
    """从一个备份点读出某文件的字节内容."""
    rel_path = rel_path.replace("\\", "/")
    proj = _resolve(project_path)
    if point.kind == "dir_snapshot" and point.fs_path:
        f = Path(point.fs_path) / rel_path
        return f.read_bytes()
    if point.kind in ("commit", "release"):
        ref = point.git_ref or point.label
        rc, out, err = git_ops.run_bytes(
            ["show", f"{ref}:{rel_path}"], cwd=proj, check=False,
        )
        if rc != 0:
            raise FileNotFoundError(
                f"git show 失败：{err.decode('utf-8', errors='replace').strip()}"
            )
        return out
    raise ValueError(f"暂不支持从 [{point.kind}] 读取文件内容")


def restore_single_file(project_path: str | Path,
                        rel_path: str,
                        point: BackupPoint) -> RestoreFileResult:
    """把某备份点的单个文件恢复（覆写）到项目工作目录.

    安全：恢复前先把当前文件备份到 NAS\\snapshots\\_restore_safety\\<项目>\\files\\.
    """
    rel_path = rel_path.replace("\\", "/")
    proj = _resolve(project_path)
    name = proj.name
    target = proj / rel_path

    content = read_file_at_point(point, rel_path, proj)

    safety_path: Path | None = None
    if target.exists() and target.is_file():
        safety_root = paths.NAS_SNAPSHOTS_DIR / "_restore_safety" / name / "files"
        safety_root.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        safe_name = f"{ts}__{rel_path.replace('/', '__')}"
        safety_path = safety_root / safe_name
        try:
            shutil.copy2(target, safety_path)
        except OSError as e:
            log.warning("文件级安全备份失败：%s", e)
            safety_path = None

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)

    log.info("已把 %s 从 [%s]%s 恢复到 %s（%d 字节）",
             rel_path, point.kind, point.label, target, len(content))
    return RestoreFileResult(
        project_name=name,
        rel_path=rel_path,
        safety_path=safety_path,
        bytes_written=len(content),
    )


# ---------- restore ----------

def restore_from_dir_snapshot(snapshot_path: str | Path,
                              project_path: str | Path,
                              *,
                              progress: ProgressFn | None = None) -> RestoreResult:
    """从一个目录快照恢复整个项目内容到 project_path.

    安全策略：
      1. 先把项目当前所有非-.git 文件拷到 NAS\\snapshots\\_restore_safety\\<项目>\\<时间戳>\\
         （保险，恢复操作可逆）
      2. 删项目内除 .git/ 外所有文件
      3. 把快照内容（也不含 .git，因为快照本来就排除了 .git）拷回项目
    """
    step = progress or _noop
    snap = Path(snapshot_path).expanduser().resolve()
    proj = _resolve(project_path)
    if not snap.exists() or not snap.is_dir():
        raise FileNotFoundError(f"快照目录不存在: {snap}")
    name = proj.name

    step("先把当前项目状态备份一份（防止恢复出错可回滚）")
    safety_root = paths.NAS_SNAPSHOTS_DIR / "_restore_safety" / name
    safety_root.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    safety = _next_unique_dir(safety_root, ts)
    if proj.exists():
        try:
            _mirror_project_tree(proj, safety, paths.DEFAULT_MIRROR_EXCLUDES)
        except OSError as e:
            log.warning("安全备份失败（继续，但风险更高）: %s", e)
            safety = safety_root  # 占位

    step("清理当前项目内容（保留 .git）")
    if proj.exists():
        for item in proj.iterdir():
            if item.name == ".git":
                continue
            try:
                if item.is_dir() and not item.is_symlink():
                    shutil.rmtree(item)
                else:
                    item.unlink()
            except OSError as e:
                log.warning("删除 %s 失败: %s", item, e)
    else:
        proj.mkdir(parents=True, exist_ok=True)

    step("从快照恢复文件")
    count = 0
    for src in snap.rglob("*"):
        if src.is_file():
            rel = src.relative_to(snap)
            dst = proj / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            count += 1

    # 刷新 registry 的 last_backup_at — 不然主面板会把刚 restore 的项目
    # 标记成"有未备份的修改"（change_detect 比对工作树和 last_backup_hash
    # 会发现一堆 diff），用户看不懂。Restore 不动 .git，所以 head 是不变的。
    try:
        if git_ops.is_git_repo(proj) and git_ops.has_any_commit(proj):
            registry.update_last_backup(proj, git_ops.head_hash(proj))
    except (git_ops.GitError, OSError) as e:
        log.warning("restore 后刷新 registry last_backup 失败: %s", e)

    step("完成")
    log.info("从快照 %s 恢复 %d 个文件到 %s", snap, count, proj)
    return RestoreResult(
        project_name=name,
        snapshot_used=snap,
        safety_backup=safety,
        restored_count=count,
    )


# ---------- scheduled daily ----------

def scheduled_daily() -> ScheduledRunResult:
    """Task Scheduler 每天调用：遍历 registry，仅对有变化的项目备份."""
    started = datetime.now()
    backed: list[str] = []
    skipped: list[tuple[str, str]] = []
    failed: list[tuple[str, str]] = []

    reg = registry.load()
    for entry in reg.projects:
        try:
            if not Path(entry.path).exists():
                skipped.append((entry.name, "项目目录已不存在"))
                continue
            if not git_ops.is_git_repo(entry.path):
                skipped.append((entry.name, "已不是 git 仓库"))
                continue
            res = backup_project(
                entry.path,
                make_bundle=True,
                skip_if_no_change=True,
                commit_dirty=True,
                mirror_files=True,
                note="scheduled-daily",
            )
            # 即使 git 部分被跳过，只要目录快照生成了也算成功备份
            if res.dir_snapshot_path is not None or not res.skipped:
                backed.append(entry.name)
                if res.skipped:
                    log.info("项目 %s git 部分跳过（无变化），但生成了目录快照",
                             entry.name)
            else:
                skipped.append((entry.name, res.skip_reason or "no change"))
        except Exception as e:  # noqa: BLE001
            log.exception("定时备份失败: %s", entry.name)
            failed.append((entry.name, str(e)))

    finished = datetime.now()
    log.info("定时备份完成 — 成功:%d 跳过:%d 失败:%d 用时:%ss",
             len(backed), len(skipped), len(failed),
             round((finished - started).total_seconds(), 1))
    return ScheduledRunResult(
        started_at=started,
        finished_at=finished,
        backed_up=backed,
        skipped=skipped,
        failed=failed,
    )


# ---------- NAS root 迁移 ----------

def _shift_path_prefix(p: str, old_prefix: Path, new_prefix: Path) -> str | None:
    """如果 p 以 old_prefix 开头，返回替换前缀后的新路径；否则 None."""
    try:
        old_resolved = str(old_prefix.resolve()).lower()
    except OSError:
        old_resolved = str(old_prefix).lower()
    p_lower = p.lower().replace("/", "\\")
    old_lower = old_resolved.lower().replace("/", "\\")
    if not p_lower.startswith(old_lower):
        return None
    rel = p[len(str(old_prefix)):].lstrip("\\/")
    return str(new_prefix / rel)


def migrate_nas_root(new_root: str | Path,
                     *,
                     remove_old: bool = False,
                     progress: ProgressFn | None = None) -> MigrationResult:
    """把当前 NAS_ROOT 下的全部备份数据搬到 new_root.

    步骤：
      1. robocopy 旧根整树 mirror 到新根
      2. paths.set_nas_root(new_root) 切 config
      3. 改 registry 里每个项目的 nas_mirror / bundle_dir 路径前缀（.git → 新根下的同名）
      4. 改每个项目本地 .git/config 里 remote.nas.url 指向新的 bare 镜像
      5. remove_old=True 时再删旧数据（默认不删，让用户人工确认）

    迁移期间禁止其它备份并发。robocopy 失败时 config 不会切——旧数据安全。
    """
    step = progress or _noop
    new_root_path = Path(new_root)

    if not paths.is_nas_configured():
        raise RuntimeError("当前还没配置过备份位置，无可迁移；请直接用 settings 设置位置")
    old_root = paths._resolve_or_raise()
    if old_root.resolve() == new_root_path.resolve():
        raise ValueError("新位置和旧位置相同，无需迁移")

    new_root_path.mkdir(parents=True, exist_ok=True)

    # 1. robocopy 整树 mirror（旧根所有内容 → 新根）
    step(f"复制 {old_root} → {new_root_path}（可能耗时）")
    rc, files_copied, bytes_copied = _robocopy_mirror(old_root, new_root_path)
    if rc >= 8:
        raise RuntimeError(
            f"robocopy 失败 (exit={rc})。旧数据未动、配置未切；"
            f"请检查目标位置可写性后再试"
        )

    # 2. 在切 config 前先读旧 registry，避免切后 paths.NAS_REGISTRY_FILE 变成新根的
    step("读取旧 registry")
    reg_old = registry.load()
    projects_to_update = list(reg_old.projects)

    # 3. 切 config
    step("切换配置到新位置")
    paths.set_nas_root(new_root_path)

    # 4. 改 registry 路径前缀（registry 文件本身已被 robocopy 拷到新根）
    step("更新 registry 里项目路径")
    reg_new = registry.load()  # 现在从新根读
    projects_updated = 0
    for entry in reg_new.projects:
        new_mirror = _shift_path_prefix(entry.nas_mirror, old_root, new_root_path)
        new_bundle = _shift_path_prefix(entry.bundle_dir, old_root, new_root_path)
        changed = False
        if new_mirror and new_mirror != entry.nas_mirror:
            entry.nas_mirror = new_mirror
            changed = True
        if new_bundle and new_bundle != entry.bundle_dir:
            entry.bundle_dir = new_bundle
            changed = True
        if changed:
            projects_updated += 1
    registry.save(reg_new)

    # 5. 改每个项目本地 .git/config 的 nas remote URL
    step("更新各项目本地 git remote 指向新位置")
    git_updated = 0
    errors: list[str] = []
    for entry in projects_to_update:
        try:
            proj = Path(entry.path)
            if not proj.exists():
                errors.append(f"{entry.name}: 项目本地目录不存在 ({proj})，跳过 remote 更新")
                continue
            if not git_ops.is_git_repo(proj):
                continue
            cur_remotes = git_ops.list_remotes(proj)
            old_url = cur_remotes.get(paths.NAS_REMOTE_NAME)
            if not old_url:
                continue
            new_url = _shift_path_prefix(old_url, old_root, new_root_path)
            if new_url and new_url != old_url:
                git_ops.set_remote_url(proj, paths.NAS_REMOTE_NAME, new_url)
                git_updated += 1
        except (git_ops.GitError, OSError) as e:
            errors.append(f"{entry.name}: 更新 git remote 失败 — {e}")

    # 6. 可选：删除旧数据
    if remove_old:
        step("清除旧位置数据")
        try:
            shutil.rmtree(old_root, ignore_errors=False)
        except OSError as e:
            errors.append(f"删除旧位置 {old_root} 失败 (但迁移本体已成功): {e}")

    step("迁移完成")
    return MigrationResult(
        old_root=old_root,
        new_root=new_root_path,
        files_copied=files_copied,
        bytes_copied=bytes_copied,
        projects_updated=projects_updated,
        git_remotes_updated=git_updated,
        errors=errors,
    )


def _robocopy_mirror(src: Path, dst: Path) -> tuple[int, int, int]:
    """robocopy /MIR 整树同步；返回 (exit_code, files_copied, bytes_copied)."""
    if not src.exists():
        return 0, 0, 0
    proc = subprocess.run(
        [
            "robocopy", str(src), str(dst), "/E", "/COPY:DAT",
            "/R:1", "/W:1", "/NP", "/NDL", "/NJH",
        ],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        creationflags=0x08000000 if sys.platform == "win32" else 0,
        timeout=24 * 3600,
    )
    files = bytes_ = 0
    for line in proc.stdout.splitlines():
        s = line.strip()
        if s.startswith("Files :") or s.startswith("文件 :"):
            try:
                files = int(s.split()[2])
            except (IndexError, ValueError):
                pass
        elif s.startswith("Bytes :") or s.startswith("字节 :"):
            try:
                bytes_ = int(s.split()[2])
            except (IndexError, ValueError):
                pass
    return proc.returncode, files, bytes_
