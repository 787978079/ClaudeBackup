"""统一日志：按月分文件，带等级，hook 日志走单独文件."""
from __future__ import annotations
import logging
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from . import paths


_initialized = False


def _make_handler(file: Path, level: int) -> logging.Handler:
    file.parent.mkdir(parents=True, exist_ok=True)
    h = TimedRotatingFileHandler(
        file, when="midnight", backupCount=90, encoding="utf-8", utc=False
    )
    h.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s | %(message)s"
    ))
    h.setLevel(level)
    return h


def init(verbose: bool = False) -> None:
    """初始化全局 logger。可重复调用，幂等。"""
    global _initialized
    if _initialized:
        return
    paths.ensure_user_dirs()
    month = datetime.now().strftime("%Y-%m")
    main_log = paths.LOG_DIR / f"{month}.log"

    root = logging.getLogger("claude_backup")
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    root.addHandler(_make_handler(main_log, logging.INFO))

    if verbose:
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter("%(levelname)-7s | %(message)s"))
        console.setLevel(logging.DEBUG)
        root.addHandler(console)

    _initialized = True


def get(name: str = "claude_backup") -> logging.Logger:
    if not _initialized:
        init()
    return logging.getLogger(name)


def hook_log(msg: str, level: str = "INFO") -> None:
    """Stop hook 专用：直接追加到 hook.log，不依赖 logging 框架（更轻量）."""
    paths.LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts} {level:<7} | {msg}\n"
    with open(paths.HOOK_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line)


def crash_log_path() -> Path:
    """崩溃日志文件路径 — 单独一个 crash.log，方便快速分发给开发者排查."""
    return paths.LOG_DIR / "crash.log"


def write_crash(traceback_text: str, context: str = "") -> Path:
    """把 traceback 写到 crash.log，返回文件路径供 UI 展示."""
    paths.LOG_DIR.mkdir(parents=True, exist_ok=True)
    target = crash_log_path()
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sep = "=" * 78
    block = f"\n{sep}\n[{ts}] {context}\n{sep}\n{traceback_text}\n"
    with open(target, "a", encoding="utf-8") as f:
        f.write(block)
    return target
