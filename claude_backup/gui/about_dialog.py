"""关于对话框 — 应用图标 / 版本 / 描述 / 第三方组件致谢."""
from __future__ import annotations

import platform
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget,
)

from . import i18n
from .assets import app_icon
from .widgets import PrimaryButton, SecondaryButton, make_label, make_separator
from .. import __version__


_TAGLINE = "把代码自动备份到本地备份盘和 GitHub，再也不用担心丢失"
_DESCRIPTION = (
    "ClaudeBackup 是 Windows 桌面 Git 三层备份工具：\n"
    "  • 完整目录拷贝（直接看 / 直接拷回，零门槛恢复）\n"
    "  • Git bundle 时间快照（轻量增量历史）\n"
    "  • 重大版本发布到 GitHub（异地灾备 + 分享）\n\n"
    "支持 Claude Code Stop hook 自动备份、Windows 任务计划定时备份、"
    "资源管理器右键菜单一键操作。"
)
_THIRD_PARTY = [
    ("PySide6 / Qt 6", "LGPL v3 — Qt for Python"),
    ("Pillow", "MIT-CMU — 图标多尺寸生成"),
    ("PyInstaller", "GPL with PyInstaller Bootloader Exception — 打包"),
    ("Inno Setup", "Inno Setup License — Windows 安装包"),
    ("Git for Windows", "GPLv2 — 备份依赖的 git CLI（用户自装）"),
]


class AboutDialog(QDialog):
    """专业版关于对话框."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(f"关于 {i18n.APP_NAME}")
        self.setWindowIcon(app_icon())
        self.setMinimumSize(560, 520)
        self.setModal(True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 20)
        outer.setSpacing(14)

        # 头部 — 大图标 + 名称 + 版本
        header = QHBoxLayout()
        header.setSpacing(16)

        icon_lb = QLabel()
        icon_lb.setPixmap(app_icon().pixmap(72, 72))
        icon_lb.setFixedSize(72, 72)
        header.addWidget(icon_lb)

        meta = QVBoxLayout()
        meta.setContentsMargins(0, 4, 0, 4)
        meta.setSpacing(4)
        name = QLabel(i18n.APP_NAME)
        name.setObjectName("H1")
        meta.addWidget(name)
        ver = QLabel(f"版本 {__version__}")
        ver.setObjectName("Dim")
        meta.addWidget(ver)
        tagline = QLabel(_TAGLINE)
        tagline.setObjectName("Body")
        tagline.setWordWrap(True)
        meta.addWidget(tagline)
        header.addLayout(meta, 1)
        outer.addLayout(header)

        outer.addWidget(make_separator())

        # 描述
        desc = QLabel(_DESCRIPTION)
        desc.setObjectName("Body")
        desc.setWordWrap(True)
        outer.addWidget(desc)

        outer.addWidget(make_separator())

        # 运行环境
        env_text = (
            f"Python：{sys.version.split()[0]}    "
            f"平台：{platform.system()} {platform.release()}    "
            f"架构：{platform.machine()}"
        )
        env_lb = QLabel(env_text)
        env_lb.setObjectName("Mini")
        env_lb.setWordWrap(True)
        outer.addWidget(env_lb)

        # 第三方组件致谢
        outer.addWidget(make_label("开源组件", "H3"))
        for name_s, license_s in _THIRD_PARTY:
            row = QLabel(f"  • {name_s}  —  {license_s}")
            row.setObjectName("Mini")
            row.setTextInteractionFlags(Qt.TextSelectableByMouse)
            outer.addWidget(row)

        # 版权
        copyright_lb = QLabel(
            "© 2026 lin. Released under MIT License.\n"
            "ClaudeBackup is not affiliated with Anthropic."
        )
        copyright_lb.setObjectName("Mini")
        copyright_lb.setAlignment(Qt.AlignCenter)
        copyright_lb.setWordWrap(True)
        outer.addWidget(copyright_lb)

        # 按钮
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        copy_btn = SecondaryButton("复制版本信息")
        copy_btn.clicked.connect(self._copy_version_info)
        close_btn = PrimaryButton("关闭")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(copy_btn)
        btn_row.addWidget(close_btn)
        outer.addLayout(btn_row)

    def _copy_version_info(self) -> None:
        text = (
            f"{i18n.APP_NAME} {__version__}\n"
            f"Python {sys.version.split()[0]}\n"
            f"{platform.system()} {platform.release()} {platform.machine()}"
        )
        cb = QGuiApplication.clipboard()
        if cb is not None:
            cb.setText(text)
