"""健康检查 — 扫所有项目 + 备份位置，列出可操作的隐患."""
from __future__ import annotations
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from . import config, git_ops, paths, registry


@dataclass
class HealthIssue:
    severity: str       # "error" / "warn" / "info"
    project: str | None  # None = 全局问题（非项目相关）
    title: str          # 一行总结
    detail: str         # 多行细节
    fix_hint: str = ""  # 建议修复方式


@dataclass
class HealthReport:
    issues: list[HealthIssue] = field(default_factory=list)
    projects_checked: int = 0
    nas_root: Path | None = None
    nas_writable: bool = False
    nas_free_gb: float | None = None

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "error")

    @property
    def warn_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "warn")

    @property
    def info_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "info")


# 项目里出现这些目录之一 + 没有 .gitignore = 健康警告
_HEAVY_DIRS = (
    "node_modules", ".next", ".nuxt", "dist", "build", "out", "target",
    "__pycache__", ".venv", "venv", ".playwright-mcp", "coverage",
)

# 备份过久 = 超过这个天数没新增任何快照
STALE_DAYS = 7


def _check_nas(report: HealthReport) -> None:
    """检查备份位置可达性 + 可写性 + 空间."""
    root = paths._resolve_nas_root()
    report.nas_root = root
    if root is None:
        report.issues.append(HealthIssue(
            severity="error", project=None,
            title="备份位置未配置",
            detail="还没在引导或设置里选过备份位置。所有备份操作都会失败。",
            fix_hint="打开 ⚙️ 设置 → 📂 备份位置，选一个文件夹。",
        ))
        return
    if not root.exists():
        report.issues.append(HealthIssue(
            severity="error", project=None,
            title=f"备份位置不可访问：{root}",
            detail="路径不存在 — 可能盘符变了、NAS 未挂载、或外置硬盘没接。",
            fix_hint="检查盘符 / 重新挂载 NAS，或在设置里改备份位置。",
        ))
        return

    # 可写性测试
    probe = root / ".claude-backup-write-test"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        report.nas_writable = True
    except OSError as e:
        report.issues.append(HealthIssue(
            severity="error", project=None,
            title=f"备份位置不可写：{root}",
            detail=f"写入测试失败：{e}",
            fix_hint="检查权限 / 磁盘是否只读。",
        ))
        return

    # 空间检查
    try:
        usage = shutil.disk_usage(root)
        report.nas_free_gb = usage.free / (1 << 30)
        if report.nas_free_gb < 1:
            report.issues.append(HealthIssue(
                severity="error", project=None,
                title="备份位置可用空间不足 1 GB",
                detail=f"剩余 {report.nas_free_gb:.2f} GB。备份可能失败。",
                fix_hint="清理旧快照或扩容磁盘。",
            ))
        elif report.nas_free_gb < 5:
            report.issues.append(HealthIssue(
                severity="warn", project=None,
                title=f"备份位置可用空间偏低（{report.nas_free_gb:.1f} GB）",
                detail="可用空间低于 5 GB，长期定时备份会越来越快用完。",
                fix_hint="降低设置里的保留策略，或换更大的备份位置。",
            ))
    except OSError as e:
        report.issues.append(HealthIssue(
            severity="warn", project=None,
            title="无法读取备份位置磁盘空间",
            detail=str(e),
        ))


def _check_project(entry: registry.ProjectEntry,
                   report: HealthReport) -> None:
    """对一个项目跑健康检查."""
    proj = Path(entry.path)
    name = entry.name

    if not proj.exists():
        report.issues.append(HealthIssue(
            severity="error", project=name,
            title=f"项目目录不存在：{proj}",
            detail="项目被移动或删除了，但还在备份列表里。",
            fix_hint=f"在主面板选中「{name}」点「🗑 删除此项目」清掉登记。",
        ))
        return

    if not git_ops.is_git_repo(proj):
        report.issues.append(HealthIssue(
            severity="error", project=name,
            title=f"项目不再是 git 仓库",
            detail=f"{proj} 下没有 .git/ 目录了。",
            fix_hint="项目里跑 git init，或者从备份列表移除重新添加。",
        ))
        return

    # .gitignore 检查
    has_gitignore = (proj / ".gitignore").exists()
    heavy_found = [d for d in _HEAVY_DIRS if (proj / d).is_dir()]
    if heavy_found and not has_gitignore:
        report.issues.append(HealthIssue(
            severity="warn", project=name,
            title=f"项目有大目录但无 .gitignore：{', '.join(heavy_found[:3])}",
            detail=(
                f"检测到 {', '.join(heavy_found)} 等可能拖慢 git 备份的目录，"
                "但项目根没 .gitignore。下次备份可能很慢或超时。"
            ),
            fix_hint="项目根添加 .gitignore 排除这些目录后重试备份。",
        ))

    # 备份过久检查
    last_at = entry.last_backup_at
    if last_at:
        try:
            last_dt = datetime.fromisoformat(last_at.replace("Z", "+00:00").rstrip("Z"))
        except ValueError:
            last_dt = None
        if last_dt is not None:
            age = datetime.now() - last_dt.replace(tzinfo=None)
            if age > timedelta(days=STALE_DAYS):
                report.issues.append(HealthIssue(
                    severity="warn", project=name,
                    title=f"超过 {age.days} 天没备份",
                    detail=f"最近一次备份：{last_at[:16].replace('T', ' ')}",
                    fix_hint=(
                        f"主面板选「{name}」点「📸 立即备份」，"
                        "或检查定时备份是否启用。"
                    ),
                ))
    else:
        # 从未备份
        report.issues.append(HealthIssue(
            severity="warn", project=name,
            title="从未备份过",
            detail="项目登记了但还没跑过任何一次备份。",
            fix_hint=f"主面板选「{name}」点「📸 立即备份」。",
        ))

    # nas remote 检查
    try:
        remotes = git_ops.list_remotes(proj)
        nas_url = remotes.get(paths.NAS_REMOTE_NAME)
        if not nas_url:
            report.issues.append(HealthIssue(
                severity="error", project=name,
                title="缺少 nas remote",
                detail="项目本地 git config 里没有名为 'nas' 的 remote — 备份会失败。",
                fix_hint=f"从备份列表移除「{name}」后重新添加。",
            ))
    except (git_ops.GitError, OSError) as e:
        report.issues.append(HealthIssue(
            severity="warn", project=name,
            title="无法读取 git remotes",
            detail=str(e),
        ))


def run_health_check() -> HealthReport:
    """跑完整健康检查 — 不写盘、不修任何东西，纯只读扫描."""
    report = HealthReport()
    _check_nas(report)
    reg = registry.load()
    for entry in reg.projects:
        report.projects_checked += 1
        _check_project(entry, report)
    return report
