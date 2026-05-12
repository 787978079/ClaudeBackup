"""GUI 静态资源加载入口 — 统一处理开发模式 vs PyInstaller 打包模式的路径差异."""
from __future__ import annotations
import sys
from functools import lru_cache
from pathlib import Path

from PySide6.QtGui import QIcon, QPixmap


def _assets_dir() -> Path:
    """返回 assets 目录路径。

    PyInstaller --add-data 把 assets 放到 _MEIPASS/claude_backup/gui/assets，
    开发模式则是源码下的同名路径。Path(__file__).parent 在两种模式下都对。
    """
    return Path(__file__).resolve().parent


def icon_path(name: str) -> Path:
    """assets/icons/<name> 的绝对路径."""
    return _assets_dir() / "icons" / name


@lru_cache(maxsize=8)
def app_icon() -> QIcon:
    """主图标（多尺寸 .ico），用于窗口标题栏 / 任务栏 / 托盘备选."""
    p = icon_path("claudebackup.ico")
    if p.exists():
        return QIcon(str(p))
    # 回退：用 256 PNG（开发模式 ico 没生成时也能跑）
    p256 = icon_path("claudebackup-256.png")
    if p256.exists():
        return QIcon(str(p256))
    return QIcon()  # 空图标 — 不至于崩


@lru_cache(maxsize=8)
def tray_icon() -> QIcon:
    """托盘专用图标（64px PNG，避免 Qt 从 .ico 挑错尺寸）."""
    p = icon_path("tray.png")
    if p.exists():
        return QIcon(str(p))
    return app_icon()


def tray_pixmap(size: int = 64) -> QPixmap:
    """返回托盘图标对应大小的 QPixmap — set_status 染色时用得上."""
    pm = tray_icon().pixmap(size, size)
    if pm.isNull():
        # 回退：透明像素图
        pm = QPixmap(size, size)
        pm.fill()
    return pm
