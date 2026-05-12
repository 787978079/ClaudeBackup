"""复用的 widget：卡片 / 项目卡 / 动作大按钮 / 时间线 等."""
from __future__ import annotations
from datetime import datetime
from typing import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout,
    QWidget,
)

from . import i18n
from .. import registry


class Card(QFrame):
    """通用卡片容器."""
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Card")
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(20, 20, 20, 20)
        self._lay.setSpacing(12)

    def addWidget(self, w: QWidget) -> None:  # noqa: N802 (Qt 风格)
        self._lay.addWidget(w)

    def addLayout(self, lay) -> None:  # noqa: N802
        self._lay.addLayout(lay)


def make_label(text: str, kind: str = "Body") -> QLabel:
    lb = QLabel(text)
    lb.setObjectName(kind)
    lb.setWordWrap(True)
    return lb


def make_separator() -> QFrame:
    f = QFrame()
    f.setObjectName("Separator")
    f.setFrameShape(QFrame.NoFrame)
    return f


class PrimaryButton(QPushButton):
    def __init__(self, text: str, parent: QWidget | None = None):
        super().__init__(text, parent)
        self.setObjectName("PrimaryBtn")
        self.setCursor(Qt.PointingHandCursor)


class SecondaryButton(QPushButton):
    def __init__(self, text: str, parent: QWidget | None = None):
        super().__init__(text, parent)
        self.setObjectName("SecondaryBtn")
        self.setCursor(Qt.PointingHandCursor)


class IconButton(QPushButton):
    """方形图标按钮 — 顶栏紧凑场景用，给一个 unicode 符号 + tooltip."""

    def __init__(self, glyph: str, tooltip: str = "",
                 parent: QWidget | None = None):
        super().__init__(glyph, parent)
        self.setObjectName("IconBtn")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(40, 40)
        if tooltip:
            self.setToolTip(tooltip)


class _ElidedLabel(QLabel):
    """长文本自动截断 + 末尾省略号；hover 显示完整文本."""

    def __init__(self, text: str, parent: QWidget | None = None):
        super().__init__(text, parent)
        self._full = text
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setMinimumWidth(0)
        self.setToolTip(text)

    def setText(self, text: str) -> None:  # noqa: N802 (Qt 风格)
        self._full = text
        self.setToolTip(text)
        super().setText(text)
        self._apply_elide()

    def resizeEvent(self, ev):  # noqa: N802
        super().resizeEvent(ev)
        self._apply_elide()

    def _apply_elide(self) -> None:
        fm = self.fontMetrics()
        w = max(0, self.width() - 4)
        elided = fm.elidedText(self._full, Qt.ElideRight, w)
        super().setText(elided)


_STATUS_DOT_TOOLTIP = {
    "healthy": "已是最新备份",
    "changes": "有未备份的修改",
    "missing": "项目目录已不存在",
    "never": "尚未备份过",
}


_STATUS_BAR_COLOR = {
    "healthy": "#34D399",
    "changes": "#FBBF24",
    "missing": "#F87171",
    "never":   "#71717A",
}


class _StatusBar(QFrame):
    """左侧 4px 状态色条，替代之前的 ● 圆点."""

    def __init__(self, status_kind: str, parent: QWidget | None = None):
        super().__init__(parent)
        color = _STATUS_BAR_COLOR.get(status_kind, _STATUS_BAR_COLOR["never"])
        self.setFixedWidth(4)
        self.setStyleSheet(
            f"background-color: {color}; border-radius: 2px;"
        )
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self.setToolTip(_STATUS_DOT_TOOLTIP.get(status_kind, ""))


class ProjectCardButton(QPushButton):
    """左侧项目列表里的一个项."""
    def __init__(self, entry: registry.ProjectEntry, status_text: str,
                 status_kind: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("ProjectCard")
        self.setCheckable(True)
        self.entry = entry
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(64)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setToolTip(f"{entry.name}\n{entry.path}\n{status_text}")

        # 整体水平分两栏：左侧色条 + 右侧文字
        outer = QHBoxLayout(self)
        outer.setContentsMargins(8, 8, 12, 8)
        outer.setSpacing(10)

        outer.addWidget(_StatusBar(status_kind))

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(2)
        name = _ElidedLabel(entry.name)
        name.setObjectName("H3")
        text_col.addWidget(name)
        sub = QLabel(status_text)
        sub.setObjectName("Mini")
        text_col.addWidget(sub)
        outer.addLayout(text_col, 1)


class ActionCardButton(QPushButton):
    """右侧 4 个大动作按钮：图标 + 标题 + 一行说明."""
    def __init__(self, title: str, desc: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("ActionCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(80)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(4)

        t = QLabel(title)
        t.setObjectName("H3")
        lay.addWidget(t)

        d = QLabel(desc)
        d.setObjectName("Dim")
        d.setWordWrap(True)
        lay.addWidget(d)


class StatRow(QFrame):
    """详情卡片顶部"NAS 备份 / 时间快照 / 已发布"三个数字."""
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(20)

    def set_stats(self, items: list[tuple[str, str]]):
        # 清空
        while self._lay.count():
            item = self._lay.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        # 各项配色（按业务区分）
        colors = ["StatNumPrimary", "StatNumSuccess",
                  "StatNumAccent", "StatNumWarn"]
        for idx, (label, value) in enumerate(items):
            box = QFrame()
            v = QVBoxLayout(box)
            v.setContentsMargins(0, 0, 0, 0)
            v.setSpacing(0)
            num = QLabel(value)
            num.setObjectName(colors[idx % len(colors)])
            v.addWidget(num)
            cap = QLabel(label)
            cap.setObjectName("Mini")
            v.addWidget(cap)
            self._lay.addWidget(box)
        self._lay.addStretch()


class EmptyProjectsHint(QWidget):
    """没有项目时的友好空态."""
    add_clicked = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(16)

        # 用应用图标替代 📦 emoji，与品牌一致
        from .assets import app_icon
        icon = QLabel()
        icon.setPixmap(app_icon().pixmap(72, 72))
        icon.setAlignment(Qt.AlignCenter)
        lay.addWidget(icon)

        title = QLabel(i18n.LEFT_NO_PROJECTS)
        title.setObjectName("H2")
        title.setAlignment(Qt.AlignCenter)
        lay.addWidget(title)

        hint = QLabel(i18n.LEFT_NO_PROJECTS_HINT)
        hint.setObjectName("Dim")
        hint.setAlignment(Qt.AlignCenter)
        lay.addWidget(hint)

        btn = PrimaryButton(i18n.LEFT_ADD_PROJECT)
        btn.clicked.connect(self.add_clicked.emit)
        lay.addWidget(btn, alignment=Qt.AlignCenter)


_TIMELINE_KIND_COLOR = {
    "commit":       "#71717A",   # 灰 — 中性
    "bundle":       "#34D399",   # 绿 — 时间快照
    "dir_snapshot": "#A78BFA",   # 紫 — 目录快照
    "release":      "#FBBF24",   # 橙 — 发布
}
# Qt stylesheet 不识别 8 位 hex (#RRGGBBAA)，徽章背景/边框用 rgba() 显式
_TIMELINE_KIND_BG = {
    "commit":       "rgba(113, 113, 122, 60)",
    "bundle":       "rgba(52, 211, 153, 60)",
    "dir_snapshot": "rgba(167, 139, 250, 60)",
    "release":      "rgba(251, 191, 36, 60)",
}
_TIMELINE_KIND_BORDER = {
    "commit":       "rgba(113, 113, 122, 140)",
    "bundle":       "rgba(52, 211, 153, 140)",
    "dir_snapshot": "rgba(167, 139, 250, 140)",
    "release":      "rgba(251, 191, 36, 140)",
}
_TIMELINE_KIND_ZH = {
    "commit":       "提交",
    "bundle":       "时间快照",
    "dir_snapshot": "目录快照",
    "release":      "发布版本",
}


class TimelineRow(QWidget):
    """时间线一行 — 左侧 3px 类型色条 + 时间 + 标签徽章 + 详情副文字."""

    def __init__(self, kind: str, when_text: str, label: str, detail: str,
                 parent: QWidget | None = None):
        super().__init__(parent)
        color = _TIMELINE_KIND_COLOR.get(kind, _TIMELINE_KIND_COLOR["commit"])
        kind_zh = _TIMELINE_KIND_ZH.get(kind, kind)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(10)

        bar = QFrame()
        bar.setFixedWidth(3)
        bar.setStyleSheet(f"background-color: {color}; border-radius: 1.5px;")
        bar.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        lay.addWidget(bar)

        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(2)

        top = QHBoxLayout()
        top.setSpacing(8)
        when_lb = QLabel(when_text)
        when_lb.setObjectName("Body")
        when_lb.setStyleSheet("font-weight: 500;")
        top.addWidget(when_lb)

        badge = QLabel(kind_zh)
        bg = _TIMELINE_KIND_BG.get(kind, _TIMELINE_KIND_BG["commit"])
        bd = _TIMELINE_KIND_BORDER.get(kind, _TIMELINE_KIND_BORDER["commit"])
        badge.setStyleSheet(
            f"background-color: {bg};"
            f"color: {color};"
            f"border: 1px solid {bd};"
            "border-radius: 6px;"
            "padding: 2px 8px;"
            "font-size: 11px;"
            "font-weight: 600;"
        )
        badge.setFixedHeight(20)
        top.addWidget(badge)

        label_lb = _ElidedLabel(label)
        label_lb.setObjectName("Dim")
        top.addWidget(label_lb, 1)
        col.addLayout(top)

        if detail:
            detail_short = detail if len(detail) <= 80 else detail[:77] + "…"
            detail_lb = QLabel(detail_short)
            detail_lb.setObjectName("Mini")
            detail_lb.setToolTip(detail)
            col.addWidget(detail_lb)

        lay.addLayout(col, 1)


def fmt_time(t: datetime | None) -> str:
    if t is None:
        return "—"
    delta = datetime.now() - t
    secs = int(delta.total_seconds())
    if secs < 60:
        return "刚刚"
    if secs < 3600:
        return f"{secs // 60} 分钟前"
    if secs < 86400:
        return f"{secs // 3600} 小时前"
    if secs < 86400 * 30:
        return f"{secs // 86400} 天前"
    return t.strftime("%Y-%m-%d")
