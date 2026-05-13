"""文件级历史回溯：选项目里某个文件 → 看它在每个备份点中的版本 + 单文件恢复.

灵感：JetBrains Local History.

用法：
    dlg = FileHistoryDialog(parent, entry, all_points, initial_relpath="src/foo.py")
    dlg.exec()
"""
from __future__ import annotations
import difflib
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QTextCharFormat, QTextCursor, QColor
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QPlainTextEdit, QSplitter, QVBoxLayout, QWidget,
)

from . import dialogs
from .widgets import PrimaryButton, SecondaryButton, make_label
from .. import core


_KIND_EMOJI = {
    "commit": "🔵", "bundle": "🟢",
    "dir_snapshot": "📁", "release": "⭐",
}
_KIND_LABEL_ZH = {
    "commit": "提交", "bundle": "时间快照",
    "dir_snapshot": "目录快照", "release": "发布版本",
}


def _fmt_size(n: int | None) -> str:
    if n is None:
        return "—"
    for unit, t in (("MB", 1 << 20), ("KB", 1 << 10)):
        if n >= t:
            return f"{n / t:.1f} {unit}"
    return f"{n} B"


def _fmt_when(when: datetime | None) -> str:
    return when.strftime("%Y-%m-%d %H:%M") if when else "—"


class FileHistoryDialog(QDialog):
    """单文件历史 — 左侧版本列表，右侧预览或 diff，底部 [恢复这个版本到项目]."""

    def __init__(self, parent: QWidget | None,
                 project_entry,
                 points: list,
                 initial_relpath: str | None = None):
        super().__init__(parent)
        self._entry = project_entry
        # 只保留目录快照（与时间机器一致：聚焦完整目录快照之间的文件级对比/恢复）
        self._all_points = [p for p in (points or []) if p.kind == "dir_snapshot"]
        self.setWindowTitle(f"📄 文件历史 — {project_entry.name}")
        self.setMinimumSize(1080, 700)
        self._versions: list[core.FileVersion] = []
        self._build()
        if initial_relpath:
            self._path_edit.setText(initial_relpath)
            self._reload_versions()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(12)

        outer.addWidget(make_label(
            "选项目里的一个文件，下面会列出它在每个备份点中的版本 — 点一行预览，按住 Ctrl 选两行看差异。",
            "Body",
        ))

        # 文件路径输入行
        path_row = QHBoxLayout()
        path_row.setSpacing(8)
        path_row.addWidget(make_label("文件（项目内相对路径）：", "Dim"))
        self._path_edit = QLineEdit()
        self._path_edit.setPlaceholderText("src/foo.py 或 README.md")
        self._path_edit.returnPressed.connect(self._reload_versions)
        path_row.addWidget(self._path_edit, 1)
        browse_btn = SecondaryButton("📂 浏览…")
        browse_btn.clicked.connect(self._browse_file)
        path_row.addWidget(browse_btn)
        reload_btn = SecondaryButton("🔄 加载历史")
        reload_btn.clicked.connect(self._reload_versions)
        path_row.addWidget(reload_btn)
        outer.addLayout(path_row)

        # 主体：左侧版本列表 / 右侧预览区
        splitter = QSplitter(Qt.Horizontal)

        # 左侧
        left = QFrame()
        l_lay = QVBoxLayout(left)
        l_lay.setContentsMargins(0, 0, 0, 0)
        l_lay.setSpacing(6)
        l_lay.addWidget(make_label("找到的版本（按时间倒序，新→旧）：", "Dim"))
        self._versions_list = QListWidget()
        self._versions_list.setSelectionMode(QListWidget.ExtendedSelection)
        self._versions_list.itemSelectionChanged.connect(self._on_select)
        l_lay.addWidget(self._versions_list, 1)

        # 右侧
        right = QFrame()
        r_lay = QVBoxLayout(right)
        r_lay.setContentsMargins(0, 0, 0, 0)
        r_lay.setSpacing(6)
        self._right_title = QLabel("（先选一个版本预览）")
        self._right_title.setObjectName("Dim")
        r_lay.addWidget(self._right_title)
        self._preview = QPlainTextEdit()
        self._preview.setReadOnly(True)
        font = QFont("Consolas, Cascadia Code, Menlo, monospace", 10)
        self._preview.setFont(font)
        r_lay.addWidget(self._preview, 1)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([380, 700])
        outer.addWidget(splitter, 1)

        # 底部按钮
        btn_row = QHBoxLayout()
        self._hint = QLabel("")
        self._hint.setObjectName("Dim")
        btn_row.addWidget(self._hint, 1)
        self._restore_btn = PrimaryButton("⏮ 恢复这个版本到项目")
        self._restore_btn.clicked.connect(self._on_restore)
        self._restore_btn.setEnabled(False)
        btn_row.addWidget(self._restore_btn)
        close_btn = SecondaryButton("关闭")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        outer.addLayout(btn_row)

    # ---------- 加载版本 ----------

    def _browse_file(self):
        proj = Path(self._entry.path)
        fname, _ = QFileDialog.getOpenFileName(
            self, "选项目里的文件", str(proj),
        )
        if fname:
            try:
                rel = str(Path(fname).relative_to(proj)).replace("\\", "/")
                self._path_edit.setText(rel)
                self._reload_versions()
            except ValueError:
                dialogs.error(self, "选错文件",
                              "选的文件不在这个项目目录里。")

    def _reload_versions(self):
        rel = self._path_edit.text().strip()
        self._versions_list.clear()
        self._preview.clear()
        self._right_title.setText("（先选一个版本预览）")
        self._restore_btn.setEnabled(False)
        if not rel:
            self._hint.setText("先填一个文件路径")
            return
        try:
            self._versions = core.list_file_history(
                self._entry.path, rel, self._all_points,
            )
        except Exception as e:  # noqa: BLE001
            dialogs.error(self, "读取失败", str(e))
            return

        if not self._versions:
            self._hint.setText("⚠️ 这个文件在所有备份点中都不存在")
            return

        for v in self._versions:
            p = v.point
            emoji = _KIND_EMOJI.get(p.kind, "•")
            kind_zh = _KIND_LABEL_ZH.get(p.kind, p.kind)
            text = (
                f"{emoji}  {_fmt_when(p.when)}  [{kind_zh}]  "
                f"{p.label}   ·   {_fmt_size(v.size)}"
            )
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, v)
            self._versions_list.addItem(item)
        self._hint.setText(f"找到 {len(self._versions)} 个版本")
        # 默认选最新（首行）
        self._versions_list.setCurrentRow(0)

    # ---------- 选中/预览/diff ----------

    def _on_select(self):
        items = self._versions_list.selectedItems()
        if not items:
            self._right_title.setText("（先选一个版本预览）")
            self._preview.clear()
            self._restore_btn.setEnabled(False)
            return

        if len(items) == 1:
            v: core.FileVersion = items[0].data(Qt.UserRole)
            self._show_preview(v)
            self._restore_btn.setEnabled(True)
            self._restore_btn.setToolTip(
                "把这个版本的文件覆写到项目里（覆写前先把当前文件备份到备份位置）"
            )
            return

        if len(items) >= 2:
            # 取选中的前两个，按时间老→新作 diff
            vs = [it.data(Qt.UserRole) for it in items[:2]]
            vs.sort(key=lambda v: v.point.when or datetime.min)
            self._show_diff(vs[0], vs[1])
            self._restore_btn.setEnabled(False)
            self._restore_btn.setToolTip("两个版本时不能恢复 — 先单选一行")

    def _show_preview(self, v: core.FileVersion):
        rel = self._path_edit.text().strip()
        try:
            data = core.read_file_at_point(v.point, rel, self._entry.path)
        except Exception as e:  # noqa: BLE001
            self._preview.setPlainText(f"读取失败：{e}")
            return
        text, is_binary = _decode_text(data)
        self._right_title.setText(
            f"{_KIND_EMOJI.get(v.point.kind,'•')}  "
            f"{_KIND_LABEL_ZH.get(v.point.kind, v.point.kind)}  "
            f"{v.point.label}  ·  {_fmt_when(v.point.when)}  ·  {_fmt_size(v.size)}"
        )
        if is_binary:
            self._preview.setPlainText(
                f"（这是二进制文件，无法直接预览。{len(data)} 字节）\n"
                "可以选'恢复这个版本到项目'直接覆写回去。"
            )
        else:
            self._preview.setPlainText(text)

    def _show_diff(self, v_old: core.FileVersion, v_new: core.FileVersion):
        rel = self._path_edit.text().strip()
        try:
            d_old = core.read_file_at_point(v_old.point, rel, self._entry.path)
            d_new = core.read_file_at_point(v_new.point, rel, self._entry.path)
        except Exception as e:  # noqa: BLE001
            self._preview.setPlainText(f"读取失败：{e}")
            return
        t_old, b_old = _decode_text(d_old)
        t_new, b_new = _decode_text(d_new)
        if b_old or b_new:
            self._preview.setPlainText("（含二进制，无法 diff）")
            return
        title = (
            f"对比  [{_KIND_LABEL_ZH.get(v_old.point.kind)}] {v_old.point.label} "
            f"  →  [{_KIND_LABEL_ZH.get(v_new.point.kind)}] {v_new.point.label}"
        )
        self._right_title.setText(title)

        diff = list(difflib.unified_diff(
            t_old.splitlines(keepends=False),
            t_new.splitlines(keepends=False),
            fromfile=f"{v_old.point.label}",
            tofile=f"{v_new.point.label}",
            lineterm="",
        ))
        # 着色
        self._preview.clear()
        if not diff:
            self._preview.setPlainText("✅ 两个版本的文件内容完全相同。")
            return
        cur = self._preview.textCursor()
        for line in diff:
            fmt = QTextCharFormat()
            if line.startswith("+++") or line.startswith("---"):
                fmt.setForeground(QColor("#A1A1AA"))
            elif line.startswith("+"):
                fmt.setForeground(QColor("#34D399"))
            elif line.startswith("-"):
                fmt.setForeground(QColor("#F87171"))
            elif line.startswith("@@"):
                fmt.setForeground(QColor("#8B7FFF"))
            cur.insertText(line + "\n", fmt)

    # ---------- 恢复 ----------

    def _on_restore(self):
        items = self._versions_list.selectedItems()
        if len(items) != 1:
            return
        v: core.FileVersion = items[0].data(Qt.UserRole)
        rel = self._path_edit.text().strip()
        if not rel:
            return
        ok = dialogs.confirm(
            self, "恢复这个版本？",
            f"将把项目里的 {rel} 文件覆写为：\n\n"
            f"  {_KIND_EMOJI.get(v.point.kind,'•')} "
            f"[{_KIND_LABEL_ZH.get(v.point.kind, v.point.kind)}] "
            f"{v.point.label}（{_fmt_when(v.point.when)}）\n\n"
            "覆写前会自动把当前文件备份到 备份位置\\snapshots\\_restore_safety\\<项目>\\files\\，"
            "如果恢复出错可以从那里手动取回。",
            ok_text="是的，恢复",
            cancel_text="再想想",
        )
        if not ok:
            return
        try:
            res = core.restore_single_file(self._entry.path, rel, v.point)
        except Exception as e:  # noqa: BLE001
            dialogs.error(self, "恢复失败", str(e))
            return
        msg = (
            f"已恢复 {rel}（{res.bytes_written} 字节）\n"
            f"安全备份：{res.safety_path or '（原文件不存在，无需备份）'}"
        )
        dialogs.info(self, "✅ 已恢复", msg)


def _decode_text(data: bytes) -> tuple[str, bool]:
    """尝试 UTF-8 解码；含大量不可打印字节则视为二进制."""
    if b"\x00" in data[:8192]:
        return "", True
    try:
        text = data.decode("utf-8")
        return text, False
    except UnicodeDecodeError:
        try:
            text = data.decode("gbk")
            return text, False
        except UnicodeDecodeError:
            return data.decode("latin-1", errors="replace"), False
