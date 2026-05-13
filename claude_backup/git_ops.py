"""Git 命令薄封装 — subprocess 直调 git，不引入 GitPython.

设计原则：
- 所有函数接受 cwd 参数（项目路径），不依赖 chdir
- 失败抛 GitError，由调用方决定是否吞掉
- 不打印用户友好文案；那是 i18n / GUI 的责任
- Windows 下子进程用 CREATE_NO_WINDOW 不弹黑窗口（windowed 父进程时尤其重要）
"""
from __future__ import annotations
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


class GitError(RuntimeError):
    def __init__(self, cmd: Sequence[str], code: int, stderr: str):
        self.cmd = list(cmd)
        self.code = code
        self.stderr = stderr.strip()
        # cmd 已经以 "git" 开头（见 run()/run_bytes() 的 full = ["git", *args]），
        # 不要再前置一个 "git"，否则会出现 "git git add -A failed"
        super().__init__(f"{' '.join(cmd)} failed ({code}): {self.stderr}")


@dataclass
class CommandResult:
    stdout: str
    stderr: str
    returncode: int


def run(args: Sequence[str], cwd: Path | str | None = None,
        check: bool = True, timeout: int = 120) -> CommandResult:
    """运行任意 git 子命令。"""
    full = ["git", *args]
    proc = subprocess.run(
        full,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        creationflags=_NO_WINDOW,
    )
    if check and proc.returncode != 0:
        raise GitError(full, proc.returncode, proc.stderr)
    return CommandResult(proc.stdout, proc.stderr, proc.returncode)


def run_bytes(args: Sequence[str], cwd: Path | str | None = None,
              check: bool = False, timeout: int = 120) -> tuple[int, bytes, bytes]:
    """运行 git 子命令，返回原始字节流（用于读 git show 文件内容，避免文本编码失真）.

    Returns: (returncode, stdout_bytes, stderr_bytes)
    """
    full = ["git", *args]
    proc = subprocess.run(
        full,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        timeout=timeout,
        creationflags=_NO_WINDOW,
    )
    if check and proc.returncode != 0:
        raise GitError(full, proc.returncode,
                       proc.stderr.decode("utf-8", errors="replace"))
    return proc.returncode, proc.stdout, proc.stderr


# ---------- 仓库探测 ----------

def is_git_repo(path: Path | str) -> bool:
    try:
        r = run(["rev-parse", "--is-inside-work-tree"], cwd=path, check=False)
        return r.returncode == 0 and r.stdout.strip() == "true"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def repo_root(path: Path | str) -> Path | None:
    r = run(["rev-parse", "--show-toplevel"], cwd=path, check=False)
    if r.returncode != 0:
        return None
    return Path(r.stdout.strip())


def current_branch(cwd: Path | str) -> str:
    return run(["rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd).stdout.strip()


def head_hash(cwd: Path | str) -> str:
    return run(["rev-parse", "HEAD"], cwd=cwd).stdout.strip()


def has_any_commit(cwd: Path | str) -> bool:
    r = run(["rev-parse", "--verify", "HEAD"], cwd=cwd, check=False)
    return r.returncode == 0


def is_working_tree_dirty(cwd: Path | str) -> bool:
    r = run(["status", "--porcelain"], cwd=cwd)
    return bool(r.stdout.strip())


# ---------- Remote ----------

def list_remotes(cwd: Path | str) -> dict[str, str]:
    r = run(["remote", "-v"], cwd=cwd, check=False)
    remotes: dict[str, str] = {}
    for line in r.stdout.splitlines():
        # URL 部分可能含空格（如 Windows 路径 `D:\My Project\foo.git`），
        # 必须用非贪婪 (.+?) 而非 (\S+)，否则路径有空格的项目永远解析不出 remote。
        m = re.match(r"^(\S+)\s+(.+?)\s+\((fetch|push)\)$", line)
        if m and m.group(3) == "fetch":
            remotes[m.group(1)] = m.group(2)
    return remotes


def has_remote(cwd: Path | str, name: str) -> bool:
    return name in list_remotes(cwd)


def add_remote(cwd: Path | str, name: str, url: str) -> None:
    run(["remote", "add", name, url], cwd=cwd)


def set_remote_url(cwd: Path | str, name: str, url: str) -> None:
    run(["remote", "set-url", name, url], cwd=cwd)


# ---------- Push / Tag ----------

def push_all(cwd: Path | str, remote: str, with_tags: bool = True,
             timeout: int = 600) -> CommandResult:
    args = ["push", remote, "--all"]
    if with_tags:
        args.append("--follow-tags")
    return run(args, cwd=cwd, timeout=timeout)


def push_tags(cwd: Path | str, remote: str, timeout: int = 600) -> CommandResult:
    return run(["push", remote, "--tags"], cwd=cwd, timeout=timeout)


def push_single_ref(cwd: Path | str, remote: str, ref: str,
                    timeout: int = 600) -> CommandResult:
    return run(["push", remote, ref], cwd=cwd, timeout=timeout)


def tag(cwd: Path | str, name: str, message: str | None = None,
        ref: str = "HEAD") -> None:
    if message:
        run(["tag", "-a", name, "-m", message, ref], cwd=cwd)
    else:
        run(["tag", name, ref], cwd=cwd)


def list_tags(cwd: Path | str) -> list[str]:
    r = run(["tag", "--sort=-creatordate"], cwd=cwd, check=False)
    return [t for t in r.stdout.splitlines() if t.strip()]


# ---------- Bundle ----------

def bundle_create(cwd: Path | str, dest: Path, refs: list[str] | None = None) -> None:
    """生成 bundle。refs=None → --all。"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    args = ["bundle", "create", str(dest)]
    args.extend(refs or ["--all"])
    run(args, cwd=cwd, timeout=900)


def bundle_list_heads(bundle_path: Path) -> list[tuple[str, str]]:
    r = run(["bundle", "list-heads", str(bundle_path)], check=False)
    out: list[tuple[str, str]] = []
    for line in r.stdout.splitlines():
        parts = line.strip().split(maxsplit=1)
        if len(parts) == 2:
            out.append((parts[0], parts[1]))
    return out


# ---------- Bare 镜像 ----------

def init_bare(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    run(["init", "--bare", str(path)])


def is_bare_repo(path: Path | str) -> bool:
    r = run(["-C", str(path), "rev-parse", "--is-bare-repository"], check=False)
    return r.returncode == 0 and r.stdout.strip() == "true"


# ---------- Diff / Log ----------

def diff_summary(cwd: Path | str, ref1: str, ref2: str) -> str:
    return run(["diff", "--stat", f"{ref1}..{ref2}"], cwd=cwd).stdout


def diff_name_status(cwd: Path | str, ref1: str, ref2: str) -> list[tuple[str, str]]:
    r = run(["diff", "--name-status", f"{ref1}..{ref2}"], cwd=cwd)
    out: list[tuple[str, str]] = []
    for line in r.stdout.splitlines():
        parts = line.strip().split(maxsplit=1)
        if len(parts) == 2:
            out.append((parts[0], parts[1]))
    return out


def log_oneline(cwd: Path | str, rng: str | None = None,
                limit: int | None = None) -> list[tuple[str, str]]:
    args = ["log", "--pretty=format:%H%x09%s"]
    if limit:
        args.append(f"-n{limit}")
    if rng:
        args.append(rng)
    r = run(args, cwd=cwd, check=False)
    out: list[tuple[str, str]] = []
    for line in r.stdout.splitlines():
        if "\t" in line:
            h, s = line.split("\t", 1)
            out.append((h, s))
    return out


def log_oneline_with_time(cwd: Path | str, rng: str | None = None,
                          limit: int | None = None):
    """同 log_oneline 但额外返回 commit 时间。返回 List[(hash, datetime, subject)]."""
    from datetime import datetime as _dt
    args = ["log", "--pretty=format:%H%x09%cI%x09%s"]
    if limit:
        args.append(f"-n{limit}")
    if rng:
        args.append(rng)
    r = run(args, cwd=cwd, check=False)
    out: list[tuple[str, "_dt", str]] = []
    for line in r.stdout.splitlines():
        parts = line.split("\t", 2)
        if len(parts) != 3:
            continue
        h, iso, s = parts
        try:
            ts = _dt.fromisoformat(iso)
            # 去掉时区让 GUI 比较简单
            if ts.tzinfo is not None:
                ts = ts.replace(tzinfo=None)
        except ValueError:
            ts = None  # type: ignore[assignment]
        out.append((h, ts, s))
    return out


# ---------- Stash / Branch ----------

def create_branch_at(cwd: Path | str, name: str, ref: str = "HEAD") -> None:
    run(["branch", name, ref], cwd=cwd)


# Windows 下 git 的 autocrlf/safecrlf 经常导致 "fatal: LF would be replaced by CRLF"
# 让首次备份直接挂掉。这里强制关掉两者，按文件原样存入 index——避免 ClaudeBackup
# 在用户的 Windows 项目上打不到第一个 commit。
_ADD_CFG = ["-c", "core.autocrlf=false", "-c", "core.safecrlf=false"]


# 巨型项目（含 node_modules / .playwright-mcp / dist 等）首次 add -A 会扫描海量文件，
# 默认 120s 不够；提到 10 分钟与 push_all 的超时一致。
_ADD_TIMEOUT = 600


def commit_all(cwd: Path | str, message: str) -> str:
    """add . && commit -m。返回新 commit hash。working tree 干净则抛 GitError。"""
    run([*_ADD_CFG, "add", "-A"], cwd=cwd, timeout=_ADD_TIMEOUT)
    run(["commit", "-m", message], cwd=cwd, timeout=_ADD_TIMEOUT)
    return head_hash(cwd)


def commit_all_or_empty(cwd: Path | str, message: str,
                        author_email: str = "claude-backup@local",
                        author_name: str = "ClaudeBackup") -> str:
    """add -A + commit。空仓库无任何文件也能产出 empty commit。
    自动用 -c 注入临时 author，避免 git config 缺失时 commit 失败。
    """
    run([*_ADD_CFG, "add", "-A"], cwd=cwd, timeout=_ADD_TIMEOUT)
    args = [
        "-c", f"user.email={author_email}",
        "-c", f"user.name={author_name}",
        "commit", "--allow-empty", "-m", message,
    ]
    run(args, cwd=cwd, timeout=_ADD_TIMEOUT)
    return head_hash(cwd)


def branch_exists(cwd: Path | str, name: str) -> bool:
    r = run(["rev-parse", "--verify", f"refs/heads/{name}"], cwd=cwd, check=False)
    return r.returncode == 0


def checkout(cwd: Path | str, ref: str, create: bool = False) -> None:
    args = ["checkout"]
    if create:
        args.append("-b")
    args.append(ref)
    run(args, cwd=cwd)


def safe_current_branch(cwd: Path | str) -> str | None:
    """获取当前分支名；空仓库（无 commit）返回 symbolic-ref 解析失败时的 None."""
    r = run(["symbolic-ref", "--short", "HEAD"], cwd=cwd, check=False)
    if r.returncode == 0:
        return r.stdout.strip()
    return None


def init_repo(path: Path | str) -> None:
    """git init（普通工作仓库）"""
    Path(path).mkdir(parents=True, exist_ok=True)
    run(["init", "-q"], cwd=path)
