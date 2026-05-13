"""时间机器对话框：滑块拖到任意备份点 → 实时预览那一刻的项目内容 + 一键恢复.

灵感：VS Code Timeline / JetBrains Local History / Win11 PiT Restore.
"""
from __future__ import annotations
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QSlider, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

from . import dialogs
from .widgets import PrimaryButton, SecondaryButton, make_label


_KIND_EMOJI = {
    "commit": "🔵", "bundle": "🟢",
    "dir_snapshot": "📁", "release": "⭐",
}
_KIND_LABEL_ZH = {
    "commit": "提交", "bundle": "时间快照",
    "dir_snapshot": "目录快照", "release": "发布版本",
}


def _fmt_size(n: int) -> str:
    for unit, t in (("GB", 1 << 30), ("MB", 1 << 20), ("KB", 1 << 10)):
        if n >= t:
            return f"{n / t:.1f} {unit}"
    return f"{n} B"


class TimelineDialog(QDialog):
    """滑块式时间机器 — 滑动到任意备份点查看 / 恢复."""

    request_open = Signal(object)     # BackupPoint
    request_restore = Signal(object)  # BackupPoint（仅 dir_snapshot）

    def __init__(self, parent: QWidget | None,
                 project_name: str,
                 points: list,
                 project_path: str | Path | None = None):
        super().__init__(parent)
        self.setWindowTitle(f"⏱ 时间机器 — {project_name}")
        self.setMinimumSize(960, 640)
        # 只保留目录快照（产品决策：时间机器聚焦目录快照对比/恢复，
        # commit/release/bundle 不参与）
        only_dirs = [p for p in points if p.kind == "dir_snapshot"]
        self._points = sorted(only_dirs, key=lambda p: p.when or datetime.min)
        self._project_path = Path(project_path) if project_path else None
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(12)

        if not self._points:
            empty = QLabel(
                "📦 这个项目还没有目录快照\n\n"
                "回到主面板，点右侧「📸 立即备份」就会生成第一个目录快照。"
            )
            empty.setObjectName("Dim")
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet("padding: 80px; font-size: 15px;")
            lay.addWidget(empty)
            close = SecondaryButton("关闭")
            close.clicked.connect(self.accept)
            row = QHBoxLayout()
            row.addStretch()
            row.addWidget(close)
            lay.addLayout(row)
            return

        # 顶部说明
        lay.addWidget(make_label(
            "拖动下方滑块到任意时刻 — 上方显示那时的状态，下方列出当时的文件清单。",
            "Body",
        ))

        # 当前选中的信息卡
        info = QFrame()
        info.setObjectName("Card")
        info_lay = QVBoxLayout(info)
        info_lay.setContentsMargins(20, 16, 20, 16)
        info_lay.setSpacing(6)
        self._info_title = QLabel("")
        self._info_title.setObjectName("H2")
        info_lay.addWidget(self._info_title)
        self._info_when = QLabel("")
        self._info_when.setObjectName("Dim")
        info_lay.addWidget(self._info_when)
        self._info_detail = QLabel("")
        self._info_detail.setObjectName("Mini")
        self._info_detail.setWordWrap(True)
        info_lay.addWidget(self._info_detail)
        lay.addWidget(info)

        # 滑块
        slider_row = QHBoxLayout()
        slider_row.setSpacing(8)
        oldest = QLabel("更早")
        oldest.setObjectName("Dim")
        slider_row.addWidget(oldest)
        self._slider = QSlider(Qt.Horizontal)
        self._slider.setMinimum(0)
        self._slider.setMaximum(max(0, len(self._points) - 1))
        self._slider.setValue(self._slider.maximum())  # 默认选最新
        self._slider.setTickPosition(QSlider.TicksBelow)
        self._slider.setTickInterval(max(1, len(self._points) // 20))
        self._slider.setSingleStep(1)
        self._slider.setPageStep(1)
        self._slider.valueChanged.connect(self._on_slider)
        slider_row.addWidget(self._slider, 1)
        newest = QLabel("更新")
        newest.setObjectName("Dim")
        slider_row.addWidget(newest)
        lay.addLayout(slider_row)

        # 进度位置：x / N
        self._pos_label = QLabel("")
        self._pos_label.setObjectName("Dim")
        self._pos_label.setAlignment(Qt.AlignCenter)
        lay.addWidget(self._pos_label)

        # 文件清单
        lay.addWidget(make_label("当时的项目内容：", "Dim"))
        self._files = QTreeWidget()
        self._files.setHeaderLabels(["路径", "大小"])
        self._files.setRootIsDecorated(False)
        self._files.header().resizeSection(0, 580)
        lay.addWidget(self._files, 1)

        # 底部按钮
        btns = QHBoxLayout()
        self._open_btn = SecondaryButton("📂 在备份位置打开这个版本")
        self._open_btn.clicked.connect(self._on_open)
        btns.addWidget(self._open_btn)
        btns.addStretch()
        self._restore_btn = PrimaryButton("⏮ 恢复整个项目到这一刻")
        self._restore_btn.clicked.connect(self._on_restore)
        btns.addWidget(self._restore_btn)
        close = SecondaryButton("关闭")
        close.clicked.connect(self.accept)
        btns.addWidget(close)
        lay.addLayout(btns)

        # 初始化
        self._on_slider(self._slider.value())

    # ---------- 内部 ----------

    def _current(self):
        idx = self._slider.value()
        if 0 <= idx < len(self._points):
            return self._points[idx]
        return None

    def _on_slider(self, val: int):
        p = self._current()
        if p is None:
            return
        # 只剩目录快照，所有按钮恒启用
        self._info_title.setText(f"📁  [目录快照]   {p.label}")
        when = p.when.strftime("%Y-%m-%d %H:%M:%S") if p.when else "—"
        self._info_when.setText(f"时间：{when}")
        self._info_detail.setText(p.detail)
        self._pos_label.setText(f"第 {val + 1} / {len(self._points)} 个目录快照")

        self._restore_btn.setEnabled(True)
        self._restore_btn.setToolTip(
            "把整个项目内容替换为这个版本（先自动备份当前状态）"
        )
        self._open_btn.setEnabled(True)

        self._populate_files(p)

    def _populate_files(self, p):
        """只读目录快照下的文件树（唯一支持的类型）."""
        self._files.clear()
        if not getattr(p, "fs_path", None):
            return
        root = Path(p.fs_path)
        if not root.is_dir():
            return
        items: list[tuple[str, int]] = []
        for f in sorted(root.rglob("*")):
            if f.is_file():
                try:
                    rel = str(f.relative_to(root)).replace("\\", "/")
                    items.append((rel, f.stat().st_size))
                except OSError:
                    continue
        limit = 800
        for rel, sz in items[:limit]:
            QTreeWidgetItem(self._files, [rel, _fmt_size(sz)])
        if len(items) > limit:
            more = QTreeWidgetItem(
                self._files,
                [f"... 还有 {len(items) - limit} 个文件未显示", ""],
            )
            more.setDisabled(True)

    def _on_open(self):
        p = self._current()
        if p is not None:
            self.request_open.emit(p)

    def _on_restore(self):
        p = self._current()
        if p is None:
            return
        ok = dialogs.confirm(
            self, "恢复到这个版本？",
            f"将把整个项目内容替换为「{p.label}」的快照。\n\n"
            "恢复前会自动把当前项目状态备份一份到 备份位置\\snapshots\\_restore_safety\\，"
            "如果恢复出错可以从那里回滚。\n\n"
            "项目里的 .git 目录（git 历史）不会被动。",
            ok_text="是的，恢复到这一刻",
            cancel_text="再想想",
        )
        if ok:
            self.request_restore.emit(p)
