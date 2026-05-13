"""矢量图标统一封装 — Font Awesome 6 Solid，替代原 emoji 图标。

设计：调用方用语义 key（"backup-now" / "release" 等），不直接接触 qtawesome 名字。
这样未来换图标库（如 Lucide / Tabler）只改这一个文件。

色彩跟随 theme：dark 主题默认 #E5E5E5，light 主题默认 #0A0A0A。
"""
from __future__ import annotations
from typing import Optional

import qtawesome as qta
from PySide6.QtGui import QIcon


# semantic-key → fa6s-name
ICON_MAP: dict[str, str] = {
    # 顶栏
    "health":      "fa6s.heart-pulse",
    "about":       "fa6s.circle-info",
    "help":        "fa6s.circle-question",
    "settings":    "fa6s.gear",
    # 主面板动作卡
    "backup-now":  "fa6s.camera",
    "release":     "fa6s.rocket",
    "compare":     "fa6s.code-compare",
    "timeline":    "fa6s.clock-rotate-left",
    # 项目卡按钮
    "add":         "fa6s.plus",
    "delete":      "fa6s.trash",
    "file-history": "fa6s.file-lines",
    "config-gh":   "fa6s.gear",
    "github":      "fa6b.github",  # FA6 brands
    "folder":      "fa6s.folder",
    "folder-open": "fa6s.folder-open",
    # 状态/通知
    "ok":          "fa6s.check",
    "fail":        "fa6s.xmark",
    "warn":        "fa6s.triangle-exclamation",
    "info":        "fa6s.circle-info",
    "tip":         "fa6s.lightbulb",
    "pending":     "fa6s.hourglass-half",
    # timeline / 备份类型
    "kind-commit":       "fa6s.code-commit",
    "kind-bundle":       "fa6s.box-archive",
    "kind-dir-snapshot": "fa6s.folder-tree",
    "kind-release":      "fa6s.star",
    # 项目状态点
    "dot-healthy":  "fa6s.circle-check",
    "dot-changes":  "fa6s.circle-dot",
    "dot-missing":  "fa6s.circle-exclamation",
    "dot-never":    "fa6s.circle",
    # tray
    "open-folder": "fa6s.folder-open",
    "pause":       "fa6s.pause",
    "play":        "fa6s.play",
    "logs":        "fa6s.file-lines",
    "quit":        "fa6s.right-from-bracket",
    # 杂项
    "search":      "fa6s.magnifying-glass",
    "refresh":     "fa6s.arrows-rotate",
    "browse":      "fa6s.folder-open",
    "test":        "fa6s.flask",
}


def icon(key: str, color: Optional[str] = None,
         color_disabled: Optional[str] = None) -> QIcon:
    """按语义 key 取矢量图标。color 默认 dark 主题对应的浅灰。

    用法:
        btn.setIcon(icons.icon("backup-now"))
        btn.setIconSize(QSize(20, 20))
    """
    fa_name = ICON_MAP.get(key)
    if fa_name is None:
        # 兜底：直接 passthrough，便于临时用未注册名
        fa_name = key
    color = color or "#E5E5E5"  # 默认与 dark text 接近
    color_disabled = color_disabled or "#52525B"
    return qta.icon(fa_name, color=color, color_disabled=color_disabled)


def icon_themed(key: str, theme: str = "dark") -> QIcon:
    """根据主题自动取色。dark = 浅文字色，light = 深文字色."""
    if theme == "light":
        return icon(key, color="#0A0A0A", color_disabled="#A3A3A3")
    return icon(key, color="#E5E5E5", color_disabled="#52525B")
