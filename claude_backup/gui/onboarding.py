"""新手引导向导.

进入条件：
  - 首次启动 / 未配置备份位置 → 自动启动（app.py 检测）
  - 主面板"❓ 帮助" → 手动启动
"""
from __future__ import annotations
import shutil
import subprocess
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QProgressBar,
    QScrollArea, QStackedWidget, QVBoxLayout, QWidget,
)

from . import dialogs, i18n
from .assets import app_icon
from .widgets import (
    Card, PrimaryButton, SecondaryButton, make_label, make_separator,
)
from .workers import run_async
from .. import config, core, paths, registry, system_integration as si


_NO_WINDOW = 0x08000000


def detect_git() -> tuple[bool, str]:
    """检测 git 是否可用。返回 (ok, version_or_error)."""
    if shutil.which("git") is None:
        return False, "PATH 里找不到 git.exe"
    try:
        proc = subprocess.run(
            ["git", "--version"],
            capture_output=True, text=True, timeout=10,
            creationflags=_NO_WINDOW,
        )
        if proc.returncode == 0:
            return True, proc.stdout.strip()
        return False, proc.stderr.strip() or f"exit={proc.returncode}"
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, str(e)


class _Step(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)


class _WelcomeStep(_Step):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(40, 60, 40, 40)
        lay.setSpacing(20)
        lay.setAlignment(Qt.AlignTop)

        # 用真实应用图标（128px）代替原 📦 emoji
        icon = QLabel()
        icon.setPixmap(app_icon().pixmap(128, 128))
        icon.setAlignment(Qt.AlignCenter)
        lay.addWidget(icon)

        title = QLabel(i18n.ONBOARD_WELCOME_TITLE)
        title.setObjectName("H1")
        title.setAlignment(Qt.AlignCenter)
        lay.addWidget(title)

        body = QLabel(i18n.ONBOARD_WELCOME_BODY)
        body.setObjectName("Body")
        body.setAlignment(Qt.AlignCenter)
        body.setWordWrap(True)
        lay.addWidget(body)

        lay.addStretch()


class _ConceptStep(_Step):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(40, 40, 40, 40)
        lay.setSpacing(20)

        title = QLabel(i18n.ONBOARD_CONCEPT_TITLE)
        title.setObjectName("H1")
        title.setAlignment(Qt.AlignCenter)
        lay.addWidget(title)

        cards = QHBoxLayout()
        cards.setSpacing(16)

        for emoji, text in (
            ("🤖", i18n.ONBOARD_CONCEPT_AUTO),
            ("⏰", i18n.ONBOARD_CONCEPT_DAILY),
            ("🚀", i18n.ONBOARD_CONCEPT_RELEASE),
        ):
            card = Card()
            big = QLabel(emoji)
            big.setAlignment(Qt.AlignCenter)
            big.setStyleSheet("font-size: 56px;")
            card.addWidget(big)
            txt = QLabel(text)
            txt.setObjectName("Body")
            txt.setAlignment(Qt.AlignCenter)
            txt.setWordWrap(True)
            card.addWidget(txt)
            cards.addWidget(card, 1)

        lay.addLayout(cards)
        lay.addStretch()


class _BackupLocationStep(_Step):
    """让用户选备份数据存放的根目录（NAS / 外置硬盘 / 本机大盘均可）.

    选完会调 paths.set_nas_root() 写入 config，并 emit location_chosen.
    """

    location_chosen = Signal(str)

    def __init__(self):
        super().__init__()
        self._chosen: str | None = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(40, 32, 40, 32)
        lay.setSpacing(14)

        title = QLabel("📂 选一个备份位置")
        title.setObjectName("H1")
        title.setAlignment(Qt.AlignCenter)
        lay.addWidget(title)

        body = QLabel(
            "你的代码备份会保存到这里——可以选 NAS 网络盘上的目录、外置硬盘、"
            "或者本机 D 盘的某个文件夹。建议**不要**放在 C:\\，避免占系统盘。\n\n"
            "选完之后还能在 ⚙️ 设置里随时改。"
        )
        body.setObjectName("Body")
        body.setAlignment(Qt.AlignCenter)
        body.setWordWrap(True)
        body.setTextFormat(Qt.MarkdownText)
        lay.addWidget(body)

        self._pick_btn = PrimaryButton("📂 选择备份位置")
        self._pick_btn.setMinimumHeight(48)
        self._pick_btn.setStyleSheet("font-size: 16px; padding: 12px 24px;")
        self._pick_btn.clicked.connect(self._do_pick)
        lay.addWidget(self._pick_btn, alignment=Qt.AlignCenter)

        # 推荐路径提示
        default_hint = self._suggest_default()
        hint = QLabel(f"推荐：{default_hint}")
        hint.setObjectName("Dim")
        hint.setAlignment(Qt.AlignCenter)
        lay.addWidget(hint)

        # 校验/状态显示
        self._status = QLabel("")
        self._status.setObjectName("Body")
        self._status.setAlignment(Qt.AlignCenter)
        self._status.setWordWrap(True)
        lay.addWidget(self._status)

        lay.addStretch()

    @staticmethod
    def _suggest_default() -> str:
        # 1. 已经配置过 → 显示当前值
        cur = paths._resolve_nas_root()
        if cur:
            return str(cur)
        # 2. 老用户升级场景：扫几个候选位置看是否已有 .registry.json
        #    （早期硬编码 Y:\，或之前用户自己选过的常见位置）
        for cand in (
            Path(r"Y:\\"),
            Path("D:\\ClaudeBackup-Data"),
            paths._user_home() / "ClaudeBackup-Data",
        ):
            try:
                if (cand / "git-backups" / ".registry.json").exists():
                    return str(cand)
            except OSError:
                continue
        # 3. 全新用户：D 盘存在就 D:\ClaudeBackup-Data，否则家目录下
        if Path("D:\\").exists():
            return "D:\\ClaudeBackup-Data"
        return str(paths._user_home() / "ClaudeBackup-Data")

    def _do_pick(self):
        suggested = self._suggest_default()
        # 让 QFileDialog 起点指向建议路径的父目录（如果已存在）
        start = suggested
        parent = Path(suggested).parent
        if not Path(suggested).exists() and parent.exists():
            start = str(parent)
        chosen = QFileDialog.getExistingDirectory(self, "选个文件夹存放备份数据", start)
        if not chosen:
            return
        # 校验可写
        ok, msg = self._validate(Path(chosen))
        if not ok:
            self._status.setText(f"❌ {msg}")
            return
        # 持久化
        try:
            paths.set_nas_root(chosen)
        except OSError as e:
            self._status.setText(f"❌ 保存配置失败：{e}")
            return
        self._chosen = chosen
        self._status.setText(f"✅ 已选好：{chosen}")
        self._pick_btn.setText("✅ 已设置（可点击修改）")
        self.location_chosen.emit(chosen)

    @staticmethod
    def _validate(p: Path) -> tuple[bool, str]:
        """检查目标路径是否可作为备份根使用."""
        if not p.exists():
            try:
                p.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                return False, f"该路径无法创建：{e}"
        if not p.is_dir():
            return False, "选中的不是文件夹"
        # 写入测试
        probe = p / ".claude-backup-write-test"
        try:
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
        except OSError as e:
            return False, f"该位置不可写：{e}"
        return True, ""


class _PickStep(_Step):
    project_picked = Signal(object)  # InitResult
    pick_failed = Signal(str)
    _stage_arrived = Signal(str)
    _result_ok = Signal(object)
    _result_err = Signal(str)

    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(40, 32, 40, 32)
        lay.setSpacing(14)

        title = QLabel(i18n.ONBOARD_PICK_TITLE)
        title.setObjectName("H1")
        title.setAlignment(Qt.AlignCenter)
        lay.addWidget(title)

        body = QLabel(i18n.ONBOARD_PICK_BODY)
        body.setObjectName("Body")
        body.setAlignment(Qt.AlignCenter)
        body.setWordWrap(True)
        lay.addWidget(body)

        self._pick_btn = PrimaryButton(i18n.ONBOARD_PICK_BTN)
        self._pick_btn.setMinimumHeight(48)
        self._pick_btn.setStyleSheet("font-size: 16px; padding: 12px 24px;")
        self._pick_btn.clicked.connect(self._do_pick)
        lay.addWidget(self._pick_btn, alignment=Qt.AlignCenter)

        # GitHub URL（可选）
        gh_row = QHBoxLayout()
        gh_row.setSpacing(8)
        gh_label = QLabel("（可选）GitHub 仓库地址：")
        gh_label.setObjectName("Dim")
        self._github_edit = QLineEdit()
        self._github_edit.setPlaceholderText("https://github.com/你的用户名/项目.git  ——  留空就只用 NAS")
        gh_row.addWidget(gh_label)
        gh_row.addWidget(self._github_edit, 1)
        lay.addLayout(gh_row)

        # 进度条 — 不定模式
        self._bar = QProgressBar()
        self._bar.setRange(0, 0)  # 不定模式
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(6)
        self._bar.setVisible(False)
        lay.addWidget(self._bar)

        # 阶段清单（可滚动）
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
        scroll.setVisible(False)
        self._stages_scroll = scroll
        lay.addWidget(scroll, 1)

        # 状态摘要（一行）
        self._summary = QLabel("")
        self._summary.setObjectName("Dim")
        self._summary.setAlignment(Qt.AlignCenter)
        lay.addWidget(self._summary)

        self._busy = False
        self._thread = None
        self._stage_labels: list[QLabel] = []

        # 关键：worker 线程通过这些 Signal 跨线程传消息到 GUI 线程
        # （Signal→Signal 间的 connect 能正确处理线程亲和度，比 Signal→闭包靠谱）
        self._stage_arrived.connect(self._add_stage)
        self._result_ok.connect(self._on_pick_ok)
        self._result_err.connect(self._on_pick_err)

    def _add_stage(self, msg: str):
        """新阶段开始：把上一条标记为 ✅，加新一条 ⏳."""
        if self._stage_labels:
            last = self._stage_labels[-1]
            last.setText(last.text().replace("⏳", "✅", 1))
        new = QLabel(f"⏳  {msg}")
        new.setObjectName("Body")
        new.setStyleSheet("padding: 4px 0;")
        self._stages_layout.addWidget(new)
        self._stage_labels.append(new)
        # 滚到底
        bar = self._stages_scroll.verticalScrollBar()
        if bar:
            bar.setValue(bar.maximum())

    def _finalize_last(self, mark_ok: bool = True):
        if self._stage_labels:
            last = self._stage_labels[-1]
            mark = "✅" if mark_ok else "❌"
            last.setText(last.text().replace("⏳", mark, 1))

    def _reset_stages(self):
        for lb in self._stage_labels:
            lb.deleteLater()
        self._stage_labels = []

    def _on_pick_ok(self, res):
        self._busy = False
        self._finalize_last(mark_ok=True)
        self._bar.setVisible(False)
        self._pick_btn.setText("✅ 已配好")
        self._summary.setText(f"已配好 — 共 {len(self._stage_labels)} 步完成")
        self.project_picked.emit(res)

    def _on_pick_err(self, msg):
        self._busy = False
        self._finalize_last(mark_ok=False)
        self._bar.setVisible(False)
        self._pick_btn.setEnabled(True)
        self._pick_btn.setText(i18n.ONBOARD_PICK_BTN)
        self._summary.setText(f"❌ 失败：{msg}")
        self.pick_failed.emit(msg)

    def _do_pick(self):
        if self._busy:
            return
        d = QFileDialog.getExistingDirectory(self, "选一个项目文件夹")
        if not d:
            return

        self._busy = True
        self._reset_stages()
        self._pick_btn.setEnabled(False)
        self._pick_btn.setText("正在配置…")
        self._bar.setVisible(True)
        self._stages_scroll.setVisible(True)
        self._summary.setText(f"项目：{d}")

        github = self._github_edit.text().strip() or None
        # worker 直接 emit 我们自己的 Signal — Qt 会自动 queued 到 GUI 线程
        self._thread = run_async(
            self, core.init_project,
            self._result_ok.emit, self._result_err.emit,
            d, github_url=github,
            on_progress=self._stage_arrived.emit,
        )


class _TryStep(_Step):
    backup_done = Signal(object)
    backup_failed = Signal(str)
    _stage_arrived = Signal(str)
    _result_ok = Signal(object)
    _result_err = Signal(str)

    def __init__(self):
        super().__init__()
        self._project_path: str | None = None
        self._busy = False
        self._thread = None
        self._stage_labels: list[QLabel] = []

        self._stage_arrived.connect(self._add_stage)
        self._result_ok.connect(self._on_backup_ok)
        self._result_err.connect(self._on_backup_err)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(40, 32, 40, 32)
        lay.setSpacing(14)

        title = QLabel(i18n.ONBOARD_TRY_TITLE)
        title.setObjectName("H1")
        title.setAlignment(Qt.AlignCenter)
        lay.addWidget(title)

        body = QLabel(i18n.ONBOARD_TRY_BODY)
        body.setObjectName("Body")
        body.setAlignment(Qt.AlignCenter)
        body.setWordWrap(True)
        lay.addWidget(body)

        self._try_btn = PrimaryButton(i18n.ONBOARD_TRY_BTN)
        self._try_btn.setMinimumHeight(48)
        self._try_btn.setStyleSheet("font-size: 16px; padding: 12px 24px;")
        self._try_btn.clicked.connect(self._do_backup)
        lay.addWidget(self._try_btn, alignment=Qt.AlignCenter)

        self._bar = QProgressBar()
        self._bar.setRange(0, 0)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(6)
        self._bar.setVisible(False)
        lay.addWidget(self._bar)

        self._stages_container = QWidget()
        self._stages_layout = QVBoxLayout(self._stages_container)
        self._stages_layout.setContentsMargins(0, 0, 0, 0)
        self._stages_layout.setSpacing(4)
        self._stages_layout.setAlignment(Qt.AlignTop)

        scroll = QScrollArea()
        scroll.setWidget(self._stages_container)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setMinimumHeight(140)
        scroll.setVisible(False)
        self._stages_scroll = scroll
        lay.addWidget(scroll, 1)

        self._result_box = QLabel("")
        self._result_box.setObjectName("Body")
        self._result_box.setAlignment(Qt.AlignCenter)
        self._result_box.setWordWrap(True)
        lay.addWidget(self._result_box)

    def set_project(self, path: str):
        self._project_path = path

    def _add_stage(self, msg: str):
        if self._stage_labels:
            last = self._stage_labels[-1]
            last.setText(last.text().replace("⏳", "✅", 1))
        new = QLabel(f"⏳  {msg}")
        new.setObjectName("Body")
        new.setStyleSheet("padding: 4px 0;")
        self._stages_layout.addWidget(new)
        self._stage_labels.append(new)
        bar = self._stages_scroll.verticalScrollBar()
        if bar:
            bar.setValue(bar.maximum())

    def _finalize_last(self, ok: bool = True):
        if self._stage_labels:
            last = self._stage_labels[-1]
            last.setText(last.text().replace("⏳", "✅" if ok else "❌", 1))

    def _on_backup_ok(self, res):
        self._busy = False
        self._finalize_last(True)
        self._bar.setVisible(False)
        self._try_btn.setText("✅ 备份完成")
        self._result_box.setText(
            f"✅ 时间快照保存在：\n{res.bundle_path}"
        )
        self.backup_done.emit(res)

    def _on_backup_err(self, msg):
        self._busy = False
        self._finalize_last(False)
        self._bar.setVisible(False)
        self._try_btn.setEnabled(True)
        self._try_btn.setText(i18n.ONBOARD_TRY_BTN)
        self._result_box.setText(f"❌ 失败：{msg}")
        self.backup_failed.emit(msg)

    def _do_backup(self):
        if self._busy or not self._project_path:
            return
        self._busy = True
        for lb in self._stage_labels:
            lb.deleteLater()
        self._stage_labels = []
        self._try_btn.setEnabled(False)
        self._try_btn.setText("正在备份…")
        self._bar.setVisible(True)
        self._stages_scroll.setVisible(True)
        self._result_box.setText("")

        self._thread = run_async(
            self, core.backup_project,
            self._result_ok.emit, self._result_err.emit,
            self._project_path,
            on_progress=self._stage_arrived.emit,
        )


class _IntegrationStep(_Step):
    """系统集成开关：右键菜单 / 自启托盘 / 每日定时备份。

    朋友拿到 setup.exe 装完，到这一步默认全勾，点"立即应用"批量启用。
    不想要的取消勾即可，结果失败的不阻塞 next。
    """

    apply_done = Signal()
    _row_done = Signal(str, bool, str)   # (key, ok, msg)

    def __init__(self):
        super().__init__()
        self._busy = False
        self._completed = False
        self._row_done.connect(self._on_row_done)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(40, 32, 40, 32)
        lay.setSpacing(14)

        title = QLabel("⚙️ 系统集成（推荐全开）")
        title.setObjectName("H1")
        title.setAlignment(Qt.AlignCenter)
        lay.addWidget(title)

        body = QLabel(
            "下面三项是 ClaudeBackup 推荐启用的桌面集成。**朋友拿到这个工具的话，"
            "保持默认全勾点「立即应用」就能开箱即用**——不勾的随时可以在 ⚙️ 设置里再开。"
        )
        body.setObjectName("Body")
        body.setAlignment(Qt.AlignCenter)
        body.setWordWrap(True)
        body.setTextFormat(Qt.MarkdownText)
        lay.addWidget(body)

        # 三行：[checkbox 标题] [说明] [状态]
        self._rows = []
        for key, title_text, hint, install_fn, check_fn in self._items():
            row_widget = self._build_row(key, title_text, hint, install_fn, check_fn)
            lay.addWidget(row_widget)

        self._apply_btn = PrimaryButton("立即应用")
        self._apply_btn.setMinimumHeight(40)
        self._apply_btn.clicked.connect(self._do_apply)
        lay.addWidget(self._apply_btn, alignment=Qt.AlignCenter)

        self._summary = QLabel("")
        self._summary.setObjectName("Dim")
        self._summary.setAlignment(Qt.AlignCenter)
        self._summary.setWordWrap(True)
        lay.addWidget(self._summary)

        lay.addStretch()

    @staticmethod
    def _items():
        # (key, 标题, 说明, install_fn, check_fn)
        return [
            ("ctx",
             "📂 资源管理器右键菜单",
             "在文件夹上右键能直接看到 ClaudeBackup 子菜单",
             si.install_context_menu, si.context_menu_installed),
            ("auto",
             "🚀 登录时自启托盘",
             "下次登录 Windows 自动启动托盘图标，备份完弹通知",
             si.install_autostart, si.autostart_installed),
            ("task",
             "⏰ 每日定时备份 (23:30)",
             "每晚扫描所有项目，仅在有变化时备份",
             lambda: si.install_task_scheduler("23:30"), si.task_scheduler_installed),
        ]

    def _build_row(self, key: str, title_text: str, hint: str,
                   install_fn, check_fn) -> QWidget:
        from PySide6.QtWidgets import QCheckBox
        wrap = QWidget()
        v = QVBoxLayout(wrap)
        v.setContentsMargins(0, 4, 0, 4)
        v.setSpacing(2)

        h = QHBoxLayout()
        cb = QCheckBox(title_text)
        cb.setChecked(True)
        h.addWidget(cb, 1)

        # ⚠️ 不要在 __init__ 里同步调 check_fn——schtasks/PowerShell 子进程
        # 在主线程会阻塞十几秒，整个 onboarding 显示成黑屏。点"立即应用"时
        # install_fn 自身是幂等的（已安装会返回成功），所以不预检也没问题。
        status = QLabel("")
        status.setObjectName("Dim")
        h.addWidget(status)
        v.addLayout(h)

        hint_lb = QLabel(hint)
        hint_lb.setObjectName("Mini")
        hint_lb.setWordWrap(True)
        v.addWidget(hint_lb)

        self._rows.append({
            "key": key, "checkbox": cb, "status": status,
            "install_fn": install_fn, "check_fn": check_fn,
            "already": False,
        })
        return wrap

    def _do_apply(self):
        if self._busy or self._completed:
            return
        # 收集要安装的行（勾选 + 还没装过的）
        pending = [r for r in self._rows if r["checkbox"].isChecked() and not r["already"]]
        if not pending:
            self._summary.setText("✅ 没有待应用的项")
            self._completed = True
            self.apply_done.emit()
            self._apply_btn.setText("✅ 已完成")
            self._apply_btn.setEnabled(False)
            return

        self._busy = True
        self._apply_btn.setEnabled(False)
        self._apply_btn.setText("正在应用…")
        self._summary.setText(f"正在启用 {len(pending)} 项…")
        self._pending_count = len(pending)

        for row in pending:
            row["status"].setText("⏳ 正在启用…")
            self._launch_install(row)

    def _launch_install(self, row: dict):
        key = row["key"]
        install_fn = row["install_fn"]
        signal = self._row_done

        def _on_ok(result):
            try:
                ok, output = result
            except (TypeError, ValueError):
                ok, output = bool(result), ""
            signal.emit(key, ok, output or "")

        def _on_err(msg: str):
            signal.emit(key, False, msg)

        # 防 GC：保留 thread
        t = run_async(self, install_fn, _on_ok, _on_err)
        row["_thread"] = t

    def _on_row_done(self, key: str, ok: bool, msg: str):
        for r in self._rows:
            if r["key"] == key:
                r["status"].setText("✅ 已启用" if ok else f"❌ {msg[:40] or '失败'}")
                r["already"] = ok
                break
        self._pending_count -= 1
        if self._pending_count <= 0:
            self._busy = False
            self._completed = True
            failed = [r for r in self._rows
                      if r["checkbox"].isChecked() and not r["already"]]
            if failed:
                self._summary.setText(
                    f"⚠️ 完成 — 但有 {len(failed)} 项未成功（可在 ⚙️ 设置里重试）"
                )
            else:
                self._summary.setText("✅ 全部启用成功")
            self._apply_btn.setText("✅ 完成")
            self._apply_btn.setEnabled(False)
            self.apply_done.emit()


class _DoneStep(_Step):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(40, 40, 40, 40)
        lay.setSpacing(16)

        icon = QLabel("🎉")
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet("font-size: 96px;")
        lay.addWidget(icon)

        title = QLabel(i18n.ONBOARD_DONE_TITLE)
        title.setObjectName("H1")
        title.setAlignment(Qt.AlignCenter)
        lay.addWidget(title)

        body = QLabel(i18n.ONBOARD_DONE_BODY)
        body.setObjectName("Body")
        body.setAlignment(Qt.AlignCenter)
        body.setWordWrap(True)
        lay.addWidget(body)

        lay.addStretch()


class OnboardingWizard(QDialog):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(i18n.APP_NAME)
        self.setWindowIcon(app_icon())
        self.setMinimumSize(720, 540)
        self.setModal(True)

        self._registered_path: str | None = None
        self._location_chosen: str | None = None
        self._integration_done: bool = False

        self._stack = QStackedWidget()
        self._steps: list[_Step] = []

        # Build steps
        self._welcome = _WelcomeStep()
        self._concept = _ConceptStep()
        self._location = _BackupLocationStep()
        self._integration = _IntegrationStep()
        self._pick = _PickStep()
        self._try = _TryStep()
        self._done = _DoneStep()

        self._location.location_chosen.connect(self._on_location_chosen)
        self._integration.apply_done.connect(self._on_integration_done)
        self._pick.project_picked.connect(self._on_picked)
        self._try.backup_done.connect(self._on_backup_done)

        if paths.is_nas_configured():
            cur = paths._resolve_nas_root()
            self._location_chosen = str(cur) if cur else None

        for s in (self._welcome, self._concept, self._location,
                  self._integration, self._pick, self._try, self._done):
            self._stack.addWidget(s)
            self._steps.append(s)

        # Layout — 必须在所有 step widget addWidget 进 stack 之后构建
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._stack, 1)
        outer.addWidget(self._build_nav())

        self._update_nav()

        # 启动时检测 git——是硬依赖，没装备份会失败。延到 layout 构建之后再弹，
        # 保证即便用户没装 git 关掉错误框后仍能看到引导内容。
        self._maybe_warn_git_missing()

    def _maybe_warn_git_missing(self):
        ok, info_msg = detect_git()
        if ok:
            return
        dialogs.error(
            self, "未检测到 Git for Windows",
            "ClaudeBackup 需要 git 命令才能备份代码（git --version 跑不通）。\n\n"
            "请先去下面这个地址下载安装 Git for Windows，装完之后**重启 ClaudeBackup**：\n\n"
            "    https://gitforwindows.org/\n\n"
            f"系统报错：{info_msg}\n\n"
            "（你可以先把这个引导走完选好备份位置，但实际跑备份前必须装好 git。）",
        )

    def _build_nav(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("StatusBar")
        bar.setFixedHeight(64)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(20, 0, 20, 0)
        lay.setSpacing(10)

        self._skip_btn = SecondaryButton(i18n.ONBOARD_SKIP)
        self._skip_btn.clicked.connect(self._on_skip)
        lay.addWidget(self._skip_btn)

        # 步骤指示器
        self._indicator = QLabel("")
        self._indicator.setObjectName("Dim")
        lay.addStretch()
        lay.addWidget(self._indicator)
        lay.addStretch()

        self._prev_btn = SecondaryButton(i18n.ONBOARD_PREV)
        self._next_btn = PrimaryButton(i18n.ONBOARD_NEXT)
        self._prev_btn.clicked.connect(self._go_prev)
        self._next_btn.clicked.connect(self._go_next)
        lay.addWidget(self._prev_btn)
        lay.addWidget(self._next_btn)
        return bar

    def _update_nav(self):
        idx = self._stack.currentIndex()
        total = self._stack.count()
        self._indicator.setText(f"{idx + 1} / {total}")
        self._prev_btn.setEnabled(idx > 0)
        if idx == total - 1:
            self._next_btn.setText(i18n.ONBOARD_FINISH)
        else:
            self._next_btn.setText(i18n.ONBOARD_NEXT)

        # 步骤： welcome(0) concept(1) location(2) integration(3) pick(4) try(5) done(6)
        # location 必填；integration 不强制；pick 必填
        if idx == 2 and not self._location_chosen:
            self._next_btn.setEnabled(False)
        elif idx == 4 and not self._registered_path:
            self._next_btn.setEnabled(False)
        else:
            self._next_btn.setEnabled(True)

    def _go_prev(self):
        i = self._stack.currentIndex()
        if i > 0:
            self._stack.setCurrentIndex(i - 1)
            self._update_nav()

    def _go_next(self):
        i = self._stack.currentIndex()
        if i == self._stack.count() - 1:
            self._finish()
            return
        self._stack.setCurrentIndex(i + 1)
        self._update_nav()

    def _on_skip(self):
        # 备份位置是必选项，不允许跳过——没有它整个软件没法用
        if not paths.is_nas_configured():
            dialogs.error(
                self, "还没选备份位置",
                "备份数据要存到哪里是必须先决定的——没设这个 ClaudeBackup 没法工作。\n\n"
                "请先在第 3 步选一个文件夹（D 盘、外置硬盘、NAS 都行）。",
            )
            return
        if dialogs.confirm(self, "跳过引导",
                           "跳过引导吗？以后随时可以从主面板的 ❓ 帮助 重新看。",
                           ok_text="跳过", cancel_text="继续看"):
            cfg = config.load()
            cfg.onboarding_completed = True
            config.save(cfg)
            self.accept()

    def _on_location_chosen(self, path: str):
        self._location_chosen = path
        self._update_nav()

    def _on_integration_done(self):
        self._integration_done = True
        self._update_nav()

    def _on_picked(self, res):
        self._registered_path = res.project.path
        self._try.set_project(res.project.path)
        self._update_nav()

    def _on_backup_done(self, res):
        # 自动切到完成页
        from PySide6.QtCore import QTimer
        QTimer.singleShot(1500, lambda: (
            self._stack.setCurrentIndex(self._stack.count() - 1),
            self._update_nav(),
        ))

    def _finish(self):
        cfg = config.load()
        cfg.onboarding_completed = True
        config.save(cfg)
        self.accept()
