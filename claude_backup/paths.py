"""路径常量 — 单点定义，其它模块统一从这里 import.

NAS 备份根目录支持运行时配置（用户在 GUI onboarding 选择路径，写入
~/.claude-backup/config.json）。所有 NAS_* 模块级名字（NAS_ROOT /
NAS_BACKUPS_DIR / NAS_BUNDLES_DIR / NAS_SNAPSHOTS_DIR / NAS_REGISTRY_FILE）
通过 PEP 562 module __getattr__ 动态求值，调用方代码不用改。

优先级：env CLAUDE_BACKUP_NAS_ROOT > config.nas_root > 未配置。
未配置时访问 NAS_* 会抛 NasNotConfiguredError —— 调用方应先用
`is_nas_configured()` 检查，由 GUI 引导用户走 onboarding。
"""
from __future__ import annotations
import os
from pathlib import Path


def _user_home() -> Path:
    return Path(os.environ.get("USERPROFILE") or os.path.expanduser("~"))


USER_DATA_DIR = _user_home() / ".claude-backup"
LOG_DIR = USER_DATA_DIR / "logs"
CACHE_DIR = USER_DATA_DIR / "cache"
CONFIG_FILE = USER_DATA_DIR / "config.json"
HOOK_LOG_FILE = LOG_DIR / "hook.log"

NAS_REMOTE_NAME = "nas"

# 拷贝目录树时排除（与 git 无关的大目录、缓存、IDE 元数据）
DEFAULT_MIRROR_EXCLUDES = (
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env",
    "dist", "build", "target", "out", ".next", ".nuxt",
    ".idea", ".vscode", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "*.pyc", "*.pyo", "*.log", "*.tmp",
)


class NasNotConfiguredError(RuntimeError):
    """用户首次启动还没选备份位置；GUI 应引导 onboarding."""


# 模块内 NAS root 缓存（避免每次属性访问都读 config.json）。
# 通过 reload_cache() 失效，比如用户在 settings 改了路径之后。
_NAS_ROOT_CACHE: Path | None = None


def _resolve_nas_root() -> Path | None:
    """返回当前生效的 NAS 根路径；未配置时返回 None.

    解析顺序：env CLAUDE_BACKUP_NAS_ROOT > config.json:nas_root > None
    """
    global _NAS_ROOT_CACHE
    # env 不缓存——测试用 monkeypatch.setenv 能立刻生效
    env = os.environ.get("CLAUDE_BACKUP_NAS_ROOT")
    if env:
        return Path(env)
    if _NAS_ROOT_CACHE is not None:
        return _NAS_ROOT_CACHE
    # 延迟 import 避免与 config 循环
    try:
        from . import config as _config
        cfg = _config.load()
    except Exception:
        return None
    if cfg.nas_root:
        _NAS_ROOT_CACHE = Path(cfg.nas_root)
        return _NAS_ROOT_CACHE
    return None


def _resolve_or_raise() -> Path:
    r = _resolve_nas_root()
    if r is None:
        raise NasNotConfiguredError(
            "备份位置还没配置；请先在 GUI 走一次 onboarding 选择备份目录"
        )
    return r


def is_nas_configured() -> bool:
    """用户是否已经选过备份位置."""
    return _resolve_nas_root() is not None


def reload_cache() -> None:
    """让 NAS root 缓存失效（settings 修改路径后调用）."""
    global _NAS_ROOT_CACHE
    _NAS_ROOT_CACHE = None


def set_nas_root(path: Path | str) -> None:
    """持久化新的 NAS 根路径到 config.json，并刷新缓存."""
    from . import config as _config
    cfg = _config.load()
    cfg.nas_root = str(path)
    _config.save(cfg)
    reload_cache()


def __getattr__(name: str):
    """PEP 562: 让 paths.NAS_BACKUPS_DIR 等保持模块级访问语义，
    但每次访问动态读 config（带缓存）.
    """
    if name == "NAS_ROOT":
        return _resolve_or_raise()
    if name == "NAS_BACKUPS_DIR":
        return _resolve_or_raise() / "git-backups"
    if name == "NAS_BUNDLES_DIR":
        return _resolve_or_raise() / "git-bundles"
    if name == "NAS_SNAPSHOTS_DIR":
        return _resolve_or_raise() / "snapshots"
    if name == "NAS_REGISTRY_FILE":
        return _resolve_or_raise() / "git-backups" / ".registry.json"
    raise AttributeError(f"module 'claude_backup.paths' has no attribute {name!r}")


def ensure_user_dirs() -> None:
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def ensure_nas_dirs() -> None:
    """创建 NAS 三个根目录；NAS 离线（盘符不可达）或未配置时静默忽略，
    具体备份操作执行时再抛错给用户."""
    if not is_nas_configured():
        return
    try:
        root = _resolve_or_raise()
    except NasNotConfiguredError:
        return
    for sub in ("git-backups", "git-bundles", "snapshots"):
        try:
            (root / sub).mkdir(parents=True, exist_ok=True)
        except (OSError, FileNotFoundError):
            pass


def nas_available() -> bool:
    """NAS 根盘符是否可访问（且已配置）."""
    if not is_nas_configured():
        return False
    try:
        return _resolve_or_raise().exists()
    except (OSError, NasNotConfiguredError):
        return False
