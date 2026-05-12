"""通用进度对话框 — 阶段清单 + 不定进度条 + 完成/失败摘要."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton,
    QScrollArea, QTextEdit, QVBoxLayout, QWidget,
)

from . import i18n
from .widgets import PrimaryButton, make_label, make_separator


class ProgressDialog(QDialog):
    """跑长任务时弹出。show()/finish() 由调用方控制，add_stage 用作 progress 回调."""

    def __init__(self, parent: QWidget | None = None,
                 title: str = "处理中",
                 subtitle: str = ""):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(520, 340)
        self.setModal(True)

        self._stage_labels: list[QLabel] = []
        self._done = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 20)
        outer.setSpacing(14)

        self._title = make_label(title, "H2")
        self._title.setAlignment(Qt.AlignCenter)
        outer.addWidget(self._title)

        if subtitle:
            self._subtitle = make_label(subtitle, "Dim")
            self._subtitle.setAlignment(Qt.AlignCenter)
            outer.addWidget(self._subtitle)
        else:
            self._subtitle = None

        self._bar = QProgressBar()
        self._bar.setRange(0, 0)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(6)
        outer.addWidget(self._bar)

        self._stages_container = QWidget()
        self._stages_layout = QVBoxLayout(self._stages_container)
        self._stages_layout.setContentsMargins(0, 0, 0, 0)
        self._stages_layout.setSpacing(4)
        self._stages_layout.setAlignment(Qt.AlignTop)

        scroll = QScrollArea()
        scroll.setWidget(self._stages_container)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setMinimumHeight(160)
        self._scroll = scroll
        outer.addWidget(scroll, 1)

        self._summary = make_label("", "Body")
        self._summary.setAlignment(Qt.AlignCenter)
        self._summary.setWordWrap(True)
        outer.addWidget(self._summary)

        # 失败详情：stderr/异常太长时用可滚动文本框展示，并提供"复制"按钮
        self._detail = QTextEdit()
        self._detail.setReadOnly(True)
        self._detail.setObjectName("ErrorDetail")
        self._detail.setMinimumHeight(120)
        self._detail.hide()
        outer.addWidget(self._detail, 1)

        btns = QHBoxLayout()
        self._copy_btn = QPushButton("复制错误信息")
        self._copy_btn.clicked.connect(self._copy_detail)
        self._copy_btn.hide()
        btns.addWidget(self._copy_btn)
        btns.addStretch()
        self._close_btn = PrimaryButton("关闭")
        self._close_btn.clicked.connect(self.accept)
        self._close_btn.setEnabled(False)
        btns.addWidget(self._close_btn)
        outer.addLayout(btns)

    def _copy_detail(self) -> None:
        cb = QGuiApplication.clipboard()
        if cb is not None:
            cb.setText(self._detail.toPlainText())
            self._copy_btn.setText("✅ 已复制")

    # ---------- 回调 ----------

    def add_stage(self, msg: str) -> None:
        """progress 回调：把上一条标 ✅，新加 ⏳ 一条."""
        if self._stage_labels:
            last = self._stage_labels[-1]
            last.setText(last.text().replace("⏳", "✅", 1))
        new = QLabel(f"⏳  {msg}")
        new.setObjectName("Body")
        new.setStyleSheet("padding: 4px 0;")
        self._stages_layout.addWidget(new)
        self._stage_labels.append(new)
        bar = self._scroll.verticalScrollBar()
        if bar:
            bar.setValue(bar.maximum())

    def finish(self, success: bool, summary: str = "") -> None:
        if self._done:
            return
        self._done = True
        if self._stage_labels:
            last = self._stage_labels[-1]
            last.setText(last.text().replace("⏳", "✅" if success else "❌", 1))
        self._bar.setRange(0, 1)
        self._bar.setValue(1 if success else 0)
        prefix = "🎉 " if success else "❌ "
        body = summary or ("完成" if success else "失败")

        # 失败 / 长文本：把第一行作为简短标题，余下放进可滚动文本框
        # （避免 git stderr 多行信息把 Label 撑破或被裁剪——之前 CRLF 警告挤掉了 fatal: 行）
        body_lines = [s.strip() for s in body.split("；") if s.strip()]
        if len(body_lines) <= 1:
            body_lines = [s for s in body.splitlines() if s.strip()]

        is_long = (not success) or len(body_lines) > 1 or len(body) > 120
        if is_long:
            head = body_lines[0] if body_lines else body
            self._summary.setText(prefix + head[:200])
            self._detail.setPlainText(body)
            self._detail.show()
            self._copy_btn.setVisible(not success)
            # 给详情留出空间——失败时把窗口拉高一点
            self.resize(max(self.width(), 620), max(self.height(), 480))
        else:
            self._summary.setText(prefix + body)
        self._close_btn.setEnabled(True)

        # 成功 + 摘要简短 → 2 秒后自动关，减少用户手动点击负担。
        # 失败 / 长摘要保留窗口，给用户读错误细节的时间。
        if success and not is_long:
            self._close_btn.setText("关闭 (2s)")
            QTimer.singleShot(2000, self._auto_close)

    def _auto_close(self) -> None:
        # 用户可能已经手动点了关闭 — 不再 accept 一次
        if self.isVisible():
            self.accept()
