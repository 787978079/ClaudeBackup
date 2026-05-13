"""健康检查对话框 — 扫所有项目 + 备份位置后列出待修复问题."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget,
)

from . import i18n
from .widgets import Card, PrimaryButton, SecondaryButton, make_label
from .workers import run_async
from .. import health


_SEVERITY_COLOR = {
    "error": "#F87171",
    "warn":  "#FBBF24",
    "info":  "#A78BFA",
}
# Qt stylesheet 不支持 8-位 hex (#RRGGBBAA)，徽章背景/边框用 rgba() 显式写
_SEVERITY_BG = {
    "error": "rgba(248, 113, 113, 60)",
    "warn":  "rgba(251, 191, 36, 60)",
    "info":  "rgba(167, 139, 250, 60)",
}
_SEVERITY_BORDER = {
    "error": "rgba(248, 113, 113, 140)",
    "warn":  "rgba(251, 191, 36, 140)",
    "info":  "rgba(167, 139, 250, 140)",
}
_SEVERITY_LABEL = {
    "error": "严重",
    "warn":  "警告",
    "info":  "提示",
}


class _IssueRow(QFrame):
    """单条健康问题 — 左侧严重度色条 + 标题 + 详情 + 修复建议."""

    def __init__(self, issue: health.HealthIssue, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Card")
        color = _SEVERITY_COLOR.get(issue.severity, _SEVERITY_COLOR["warn"])

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 12, 0)
        outer.setSpacing(10)

        bar = QFrame()
        bar.setFixedWidth(4)
        bar.setStyleSheet(f"background-color: {color}; border-radius: 2px;")
        outer.addWidget(bar)

        col = QVBoxLayout()
        col.setContentsMargins(0, 10, 0, 10)
        col.setSpacing(4)

        top = QHBoxLayout()
        top.setSpacing(8)
        badge = QLabel(_SEVERITY_LABEL.get(issue.severity, issue.severity))
        badge.setStyleSheet(
            f"background-color: {_SEVERITY_BG.get(issue.severity, _SEVERITY_BG['warn'])};"
            f"color: {color};"
            f"border: 1px solid {_SEVERITY_BORDER.get(issue.severity, _SEVERITY_BORDER['warn'])};"
            "border-radius: 6px;"
            "padding: 2px 8px;"
            "font-size: 11px;"
            "font-weight: 600;"
        )
        badge.setFixedHeight(20)
        top.addWidget(badge)

        title = QLabel(issue.title)
        title.setObjectName("H3")
        title.setWordWrap(True)
        top.addWidget(title, 1)

        if issue.project:
            proj_lb = QLabel(issue.project)
            proj_lb.setObjectName("Mini")
            top.addWidget(proj_lb)

        col.addLayout(top)

        if issue.detail:
            detail = QLabel(issue.detail)
            detail.setObjectName("Dim")
            detail.setWordWrap(True)
            col.addWidget(detail)

        if issue.fix_hint:
            fix = QLabel(f"💡 {issue.fix_hint}")
            fix.setObjectName("Mini")
            fix.setStyleSheet(f"color: {color}; padding-top: 4px;")
            fix.setWordWrap(True)
            col.addWidget(fix)

        outer.addLayout(col, 1)


class HealthCheckDialog(QDialog):
    """健康检查面板 — 异步扫描后展示所有问题."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("健康检查")
        self.setMinimumSize(720, 560)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(14)

        title = QLabel("健康检查")
        title.setObjectName("H1")
        outer.addWidget(title)

        self._summary = QLabel("正在扫描…")
        self._summary.setObjectName("Dim")
        outer.addWidget(self._summary)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._container = QWidget()
        self._list_lay = QVBoxLayout(self._container)
        self._list_lay.setContentsMargins(0, 0, 0, 0)
        self._list_lay.setSpacing(10)
        self._list_lay.addStretch()
        self._scroll.setWidget(self._container)
        outer.addWidget(self._scroll, 1)

        btns = QHBoxLayout()
        btns.addStretch()
        self._refresh_btn = SecondaryButton("重新扫描")
        self._refresh_btn.clicked.connect(self._start_scan)
        close_btn = PrimaryButton("关闭")
        close_btn.clicked.connect(self.accept)
        btns.addWidget(self._refresh_btn)
        btns.addWidget(close_btn)
        outer.addLayout(btns)

        self._thread = None
        self._start_scan()

    def _start_scan(self):
        self._refresh_btn.setEnabled(False)
        self._refresh_btn.setText("扫描中…")
        self._clear_list()
        self._summary.setText("正在扫描…")

        def on_ok(report: health.HealthReport):
            self._render(report)
            self._refresh_btn.setEnabled(True)
            self._refresh_btn.setText("重新扫描")

        def on_err(msg: str):
            self._summary.setText(f"❌ 扫描失败：{msg}")
            self._refresh_btn.setEnabled(True)
            self._refresh_btn.setText("重新扫描")

        self._thread = run_async(self, health.run_health_check, on_ok, on_err)

    def _clear_list(self):
        while self._list_lay.count() > 0:
            item = self._list_lay.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _render(self, report: health.HealthReport):
        if not report.issues:
            self._summary.setText(
                f"✅ 一切正常 — 检查了 {report.projects_checked} 个项目，未发现问题。"
            )
            done = QLabel("🎉 没有需要处理的隐患")
            done.setObjectName("Body")
            done.setAlignment(Qt.AlignCenter)
            done.setStyleSheet("padding: 60px;")
            self._list_lay.insertWidget(0, done)
            return

        parts = [f"检查了 {report.projects_checked} 个项目，发现："]
        if report.error_count:
            parts.append(f"🔴 {report.error_count} 严重")
        if report.warn_count:
            parts.append(f"🟡 {report.warn_count} 警告")
        if report.info_count:
            parts.append(f"🟣 {report.info_count} 提示")
        if report.nas_free_gb is not None:
            parts.append(f"💾 备份位置剩余 {report.nas_free_gb:.1f} GB")
        self._summary.setText("  ·  ".join(parts))

        # 按严重度排序：error → warn → info
        order = {"error": 0, "warn": 1, "info": 2}
        sorted_issues = sorted(report.issues, key=lambda i: order.get(i.severity, 9))
        for issue in sorted_issues:
            row = _IssueRow(issue)
            self._list_lay.insertWidget(self._list_lay.count() - 1, row)
