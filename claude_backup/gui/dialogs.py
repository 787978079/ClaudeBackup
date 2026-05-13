"""对话框：注册项目 / 发布版本 / 对比版本 / 友好确认."""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMessageBox, QSplitter, QTextEdit,
    QVBoxLayout, QWidget,
)

from . import i18n
from .widgets import PrimaryButton, SecondaryButton, make_label

if TYPE_CHECKING:
    from .. import core


_KIND_EMOJI = {
    "commit": "🔵",
    "bundle": "🟢",
    "dir_snapshot": "📁",
    "release": "⭐",
}
_KIND_LABEL = {
    "commit": "提交",
    "bundle": "时间快照",
    "dir_snapshot": "目录快照",
    "release": "发布版本",
}


def _fmt_when(when: datetime | None) -> str:
    if when is None:
        return "—"
    return when.strftime("%Y-%m-%d %H:%M")


def _make_point_item(point: "core.BackupPoint") -> QListWidgetItem:
    """渲染一个 BackupPoint 为 ListWidget 行."""
    emoji = _KIND_EMOJI.get(point.kind, "•")
    kind_text = _KIND_LABEL.get(point.kind, point.kind)
    when = _fmt_when(point.when)
    detail = point.detail
    # 截断很长的 detail
    if len(detail) > 60:
        detail = detail[:57] + "…"
    text = f"{emoji}  {when}    [{kind_text}]   {point.label}   —  {detail}"
    item = QListWidgetItem(text)
    item.setData(Qt.UserRole, point)
    item.setToolTip(f"[{kind_text}] {point.label}\n{when}\n{point.detail}")
    return item


class RegisterProjectDialog(QDialog):
    def __init__(self, parent: QWidget | None = None,
                 default_path: str | None = None):
        super().__init__(parent)
        self.setWindowTitle(i18n.DIALOG_REGISTER_TITLE)
        self.setMinimumWidth(480)
        self._build(default_path)

    def _build(self, default_path: str | None):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(16)

        lay.addWidget(make_label(i18n.DIALOG_REGISTER_PROMPT, "Body"))

        form = QFormLayout()
        form.setSpacing(10)

        path_row = QHBoxLayout()
        self.path_edit = QLineEdit(default_path or "")
        self.path_edit.setPlaceholderText("D:\\code\\my-project")
        if default_path:
            self.path_edit.setCursorPosition(0)  # 长路径时让开头可见
        browse = SecondaryButton("浏览…")
        browse.clicked.connect(self._browse)
        path_row.addWidget(self.path_edit, 1)
        path_row.addWidget(browse)
        form.addRow("项目文件夹", path_row)

        self.github_edit = QLineEdit()
        self.github_edit.setPlaceholderText("https://github.com/你的用户名/项目.git")
        form.addRow(i18n.DIALOG_REGISTER_GITHUB, self.github_edit)

        # GitHub 字段说明
        gh_hint = make_label(
            "💡 留空 = 只备份到本地备份位置，不上传 GitHub。第一次推送时系统会弹浏览器登录 GitHub（一次就好）。",
            "Dim",
        )
        gh_hint.setWordWrap(True)
        lay.addWidget(gh_hint)

        lay.addLayout(form)

        btns = QHBoxLayout()
        btns.addStretch()
        cancel = SecondaryButton(i18n.BTN_CANCEL)
        ok = PrimaryButton(i18n.BTN_CONFIRM)
        cancel.clicked.connect(self.reject)
        ok.clicked.connect(self.accept)
        btns.addWidget(cancel)
        btns.addWidget(ok)
        lay.addLayout(btns)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "选一个项目文件夹")
        if d:
            self.path_edit.setText(d)
            self.path_edit.setCursorPosition(0)

    def values(self) -> tuple[str, str | None]:
        path = self.path_edit.text().strip()
        gh = self.github_edit.text().strip() or None
        return path, gh


class ReleaseDialog(QDialog):
    def __init__(self, parent: QWidget | None = None,
                 last_tag: str | None = None,
                 commit_log_text: str = ""):
        super().__init__(parent)
        self.setWindowTitle(i18n.DIALOG_RELEASE_TITLE)
        self.setMinimumWidth(560)
        self._build(last_tag, commit_log_text)

    def _build(self, last_tag: str | None, log_text: str):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(14)

        if last_tag:
            lay.addWidget(make_label(f"上一个发布版本：{last_tag}", "Dim"))

        form = QFormLayout()
        form.setSpacing(10)
        self.version_edit = QLineEdit()
        self.version_edit.setPlaceholderText("v1.0.0")
        form.addRow(i18n.DIALOG_RELEASE_VERSION, self.version_edit)

        self.desc_edit = QTextEdit()
        self.desc_edit.setPlaceholderText("（可选）这次发布做了什么？")
        self.desc_edit.setMaximumHeight(100)
        form.addRow(i18n.DIALOG_RELEASE_DESC, self.desc_edit)
        lay.addLayout(form)

        if log_text:
            lay.addWidget(make_label("将包含的修改：", "Dim"))
            log_box = QTextEdit()
            log_box.setReadOnly(True)
            log_box.setPlainText(log_text)
            log_box.setMaximumHeight(160)
            lay.addWidget(log_box)

        btns = QHBoxLayout()
        btns.addStretch()
        cancel = SecondaryButton(i18n.DIALOG_RELEASE_CANCEL)
        ok = PrimaryButton(i18n.DIALOG_RELEASE_CONFIRM)
        cancel.clicked.connect(self.reject)
        ok.clicked.connect(self.accept)
        btns.addWidget(cancel)
        btns.addWidget(ok)
        lay.addLayout(btns)

    def values(self) -> tuple[str, str]:
        return (
            self.version_edit.text().strip(),
            self.desc_edit.toPlainText().strip(),
        )


class CompareDialog(QDialog):
    """新版：用 List 选两个备份点（按时间倒序），自动过滤可对比的（commit/release）."""

    def __init__(self, parent: QWidget | None = None,
                 points: list | None = None,
                 preselect_end: object = None):
        super().__init__(parent)
        self.setWindowTitle(i18n.DIALOG_COMPARE_TITLE)
        self.setMinimumSize(820, 520)
        self._all_points = points or []
        # 只展示目录快照（按用户决策：对比只针对完整文件夹快照，不混入 git 提交/发布）
        self._comparable = [p for p in self._all_points if p.kind == "dir_snapshot"]
        self._build(preselect_end)

    def _build(self, preselect_end):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(12)

        lay.addWidget(make_label(
            "选两个目录快照对比文件改动：左边是起点（更早）→ 右边是终点（更新）",
            "Body",
        ))

        if len(self._comparable) < 2:
            tip = (
                "这个项目还没有目录快照 —— 先做几次「立即备份」再来"
                if not self._comparable else
                "这个项目只有 1 个目录快照 —— 多备份几次再来"
            )
            warn = make_label(f"⚠️ {tip}", "Dim")
            lay.addWidget(warn)

        # 双 List
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        self.list1 = QListWidget()
        self.list2 = QListWidget()
        for p in self._comparable:
            self.list1.addItem(_make_point_item(p))
            self.list2.addItem(_make_point_item(p))

        # 默认左选第二新作起点、右选最新作终点（comparable 是按时间倒序）
        if len(self._comparable) >= 2:
            self.list1.setCurrentRow(1)
            self.list2.setCurrentRow(0)
        elif self._comparable:
            self.list1.setCurrentRow(0)
            self.list2.setCurrentRow(0)

        # 如果传了 preselect_end，定位到那一行
        if preselect_end is not None:
            for i in range(self.list2.count()):
                p = self.list2.item(i).data(Qt.UserRole)
                if getattr(p, "git_ref", None) == getattr(preselect_end, "git_ref", None):
                    self.list2.setCurrentRow(i)
                    break

        left = QFrame()
        l_lay = QVBoxLayout(left)
        l_lay.setContentsMargins(0, 0, 0, 0)
        l_lay.addWidget(make_label("起点（更早）", "Dim"))
        l_lay.addWidget(self.list1, 1)

        right = QFrame()
        r_lay = QVBoxLayout(right)
        r_lay.setContentsMargins(0, 0, 0, 0)
        r_lay.addWidget(make_label("终点（更新）", "Dim"))
        r_lay.addWidget(self.list2, 1)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([400, 400])
        lay.addWidget(splitter, 1)

        btns = QHBoxLayout()
        self._hint = QLabel("")
        self._hint.setObjectName("Dim")
        btns.addWidget(self._hint)
        btns.addStretch()
        cancel = SecondaryButton(i18n.BTN_CANCEL)
        self._ok_btn = PrimaryButton("开始对比")
        cancel.clicked.connect(self.reject)
        self._ok_btn.clicked.connect(self.accept)
        btns.addWidget(cancel)
        btns.addWidget(self._ok_btn)
        lay.addLayout(btns)

        # 监听选择变化，动态校验
        self.list1.currentItemChanged.connect(lambda *_: self._validate())
        self.list2.currentItemChanged.connect(lambda *_: self._validate())
        self._validate()

    def _validate(self):
        p1, p2 = self.selected_points()
        if not self._comparable:
            self._ok_btn.setEnabled(False)
            self._hint.setText("")
            return
        if not p1 or not p2:
            self._ok_btn.setEnabled(False)
            self._hint.setText("请在两边各选一个目录快照")
            return
        if p1.fs_path == p2.fs_path:
            self._ok_btn.setEnabled(False)
            self._hint.setText("⚠️ 起点和终点是同一个快照")
            return
        self._ok_btn.setEnabled(True)
        self._hint.setText("")

    def values(self) -> tuple[str, str]:
        """返回 (ref1, ref2) — 都是 git_ref 形式（commit hash 或 tag name）."""
        i1 = self.list1.currentItem()
        i2 = self.list2.currentItem()
        if not i1 or not i2:
            return "", ""
        p1 = i1.data(Qt.UserRole)
        p2 = i2.data(Qt.UserRole)
        return getattr(p1, "git_ref", "") or "", getattr(p2, "git_ref", "") or ""

    def selected_points(self):
        """返回 (BackupPoint, BackupPoint) — 给 caller 拿到可读 label."""
        i1 = self.list1.currentItem()
        i2 = self.list2.currentItem()
        return (i1.data(Qt.UserRole) if i1 else None,
                i2.data(Qt.UserRole) if i2 else None)


class CompareResultDialog(QDialog):
    def __init__(self, parent: QWidget | None,
                 summary: str, files: list[tuple[str, str]],
                 ref1: str, ref2: str):
        super().__init__(parent)
        self.setWindowTitle(f"{ref1} → {ref2}")
        self.setMinimumSize(720, 480)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(12)

        lay.addWidget(make_label(f"对比 {ref1} → {ref2}", "H2"))

        if summary.strip():
            lay.addWidget(make_label("整体变更：", "Dim"))
            sum_box = QTextEdit()
            sum_box.setReadOnly(True)
            sum_box.setPlainText(summary)
            sum_box.setMaximumHeight(160)
            lay.addWidget(sum_box)

        lay.addWidget(make_label(f"变更文件 {len(files)} 个：", "Dim"))
        files_box = QTextEdit()
        files_box.setReadOnly(True)
        STATUS = {"A": "新增", "M": "修改", "D": "删除", "R": "重命名"}
        lines = [f"{STATUS.get(s, s):<6}  {f}" for s, f in files]
        files_box.setPlainText("\n".join(lines) or "（没有变更）")
        lay.addWidget(files_box, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        ok = PrimaryButton("关闭")
        ok.clicked.connect(self.accept)
        btn_row.addWidget(ok)
        lay.addLayout(btn_row)


class ConfigGitHubDialog(QDialog):
    """配置 / 修改项目的 GitHub 远程地址."""

    def __init__(self, parent: QWidget | None,
                 current_url: str | None = None,
                 project_name: str = ""):
        super().__init__(parent)
        self.setWindowTitle("配置 GitHub 远程")
        self.setMinimumWidth(520)
        self._build(current_url, project_name)

    def _build(self, current_url: str | None, project_name: str):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(14)

        if project_name:
            lay.addWidget(make_label(f"项目：{project_name}", "Dim"))

        lay.addWidget(make_label(
            "填写 GitHub 仓库地址，「发布版本」时会自动 push 到这里。",
            "Body",
        ))

        self._url_edit = QLineEdit(current_url or "")
        self._url_edit.setPlaceholderText("https://github.com/你的用户名/项目.git")
        if current_url:
            self._url_edit.setCursorPosition(0)
        lay.addWidget(self._url_edit)

        hint = make_label(
            "💡 留空 = 移除 GitHub 关联（保留本地备份位置数据）。"
            "第一次推送时系统的 Git Credential Manager 会弹浏览器登录 GitHub（一次就好）。",
            "Mini",
        )
        hint.setWordWrap(True)
        lay.addWidget(hint)

        btns = QHBoxLayout()
        btns.addStretch()
        cancel = SecondaryButton(i18n.BTN_CANCEL)
        ok = PrimaryButton("保存")
        cancel.clicked.connect(self.reject)
        ok.clicked.connect(self.accept)
        btns.addWidget(cancel)
        btns.addWidget(ok)
        lay.addLayout(btns)

    def value(self) -> str | None:
        s = self._url_edit.text().strip()
        return s or None


def confirm_delete_project(parent: QWidget | None, project_name: str) -> tuple[bool, bool]:
    """删除项目二次确认 — 复选框可选'同时清空 NAS 备份'.

    勾选清空 NAS 时弹第二轮确认，避免误删历史备份。
    Returns: (confirmed, also_clean_nas)
    """
    from PySide6.QtWidgets import QCheckBox
    box = QMessageBox(parent)
    box.setWindowTitle("删除项目")
    box.setIcon(QMessageBox.Warning)
    box.setText(
        f"确定要把「{project_name}」从备份列表里移除吗？\n\n"
        f"项目本地文件夹不会被删，只是 ClaudeBackup 不再管它。"
    )
    cb = QCheckBox("同时清空备份位置里的所有备份（⚠️ 此操作不可恢复）")
    cb.setChecked(False)
    box.setCheckBox(cb)
    ok_btn = box.addButton("是的，移除", QMessageBox.AcceptRole)
    box.addButton("取消", QMessageBox.RejectRole)
    box.exec()
    confirmed = box.clickedButton() is ok_btn
    also_clean = cb.isChecked()
    # 勾了 NAS 清理 → 二次红色警告，再确认一次
    if confirmed and also_clean:
        warn = QMessageBox(parent)
        warn.setWindowTitle("⚠️ 真的要清空备份位置数据吗？")
        warn.setIcon(QMessageBox.Critical)
        warn.setText(
            f"你勾选了「同时清空备份位置里的所有备份」。\n\n"
            f"这会**永久删除**「{project_name}」在备份位置下的：\n"
            f"  • git-backups\\{project_name}.git\\\n"
            f"  • git-bundles\\{project_name}\\（含 releases）\n"
            f"  • snapshots\\{project_name}\\\n\n"
            f"删除后无法从此处恢复 — 只能去 GitHub（如配置过）拉回。"
        )
        del_btn = warn.addButton("永久删除", QMessageBox.DestructiveRole)
        keep_btn = warn.addButton("只移除登记，保留备份位置数据", QMessageBox.AcceptRole)
        warn.setDefaultButton(keep_btn)  # 默认 = 保留数据，避免 Enter 误删
        warn.exec()
        if warn.clickedButton() is not del_btn:
            also_clean = False
    return confirmed, also_clean


def confirm(parent: QWidget | None, title: str, message: str,
            ok_text: str = i18n.BTN_OK,
            cancel_text: str = i18n.BTN_CANCEL) -> bool:
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(message)
    box.setIcon(QMessageBox.Question)
    ok_btn = box.addButton(ok_text, QMessageBox.AcceptRole)
    box.addButton(cancel_text, QMessageBox.RejectRole)
    box.exec()
    return box.clickedButton() is ok_btn


def info(parent: QWidget | None, title: str, message: str) -> None:
    QMessageBox.information(parent, title, message)


def _show_message(parent: QWidget | None, title: str, message: str,
                  level: str = "error") -> None:
    """统一弹窗实现 — 按 level 分配 icon，长信息附带"复制"按钮.

    level: "error" / "warn" / "info"
    """
    from PySide6.QtGui import QGuiApplication
    icon = {
        "error": QMessageBox.Critical,
        "warn":  QMessageBox.Warning,
        "info":  QMessageBox.Information,
    }.get(level, QMessageBox.Critical)
    box = QMessageBox(parent)
    box.setIcon(icon)
    box.setWindowTitle(title)
    lines = [ln for ln in message.splitlines() if ln.strip()]
    head = lines[0] if lines else message
    if len(message) > 200 or len(lines) > 4:
        box.setText(head[:200] + ("…" if len(head) > 200 else ""))
        box.setDetailedText(message)
        copy_btn = box.addButton("复制错误信息", QMessageBox.ActionRole)
        box.addButton(QMessageBox.Ok)
        box.exec()
        if box.clickedButton() is copy_btn:
            cb = QGuiApplication.clipboard()
            if cb is not None:
                cb.setText(message)
    else:
        box.setText(message)
        box.addButton(QMessageBox.Ok)
        box.exec()


def error(parent: QWidget | None, title: str, message: str) -> None:
    """红色错误弹窗 — 长信息会折叠成可展开 + 可复制."""
    _show_message(parent, title, message, level="error")


def warn(parent: QWidget | None, title: str, message: str) -> None:
    """黄色警告弹窗（介于 info 和 error 之间）."""
    _show_message(parent, title, message, level="warn")
