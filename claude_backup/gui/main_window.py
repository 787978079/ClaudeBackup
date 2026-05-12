"""主窗口 — 三栏布局：左侧项目列表 + 中间详情 + 右侧动作面板."""
from __future__ import annotations
import os
import shutil
import stat
from datetime import datetime
from pathlib import Path
from typing import Callable


def _force_rmtree(target: Path) -> None:
    """rmtree 强制版：遇到 git bare 仓库里的 read-only 文件先 chmod 再删."""
    def _on_exc(func, path, exc_info):
        try:
            os.chmod(path, stat.S_IWRITE)
            func(path)
        except OSError:
            raise
    # Python 3.12+ 用 onexc；3.11 及以下用 onerror — 这里两个都尝试
    try:
        shutil.rmtree(target, onexc=_on_exc)  # type: ignore[call-arg]
    except TypeError:
        shutil.rmtree(target, onerror=_on_exc)  # type: ignore[call-arg]

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QButtonGroup, QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMainWindow, QMessageBox, QPushButton, QScrollArea,
    QSizePolicy, QSplitter, QStatusBar, QStyle, QTextEdit, QVBoxLayout, QWidget,
)

from . import dialogs, i18n, theme
from .assets import app_icon
from .widgets import (
    ActionCardButton, Card, EmptyProjectsHint, IconButton, PrimaryButton,
    ProjectCardButton, SecondaryButton, StatRow, TimelineRow, fmt_time,
    make_label, make_separator,
)
from .workers import run_async
from .. import change_detect, config, core, git_ops, registry


class MainWindow(QMainWindow):
    """ClaudeBackup 主面板."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(i18n.APP_NAME)
        self.setWindowIcon(app_icon())
        self.resize(1180, 760)
        self.setMinimumSize(900, 600)

        self._cfg = config.load()
        self._current_project: registry.ProjectEntry | None = None
        self._project_buttons: list[ProjectCardButton] = []
        self._project_btn_group = QButtonGroup(self)
        self._project_btn_group.setExclusive(True)
        self._active_threads: list = []  # 防 GC
        self._notifier: Callable | None = None  # 通知回调（由 app.py 注入 tray.notify）

        # NAS 总占用缓存 — 全盘 walk 在大备份库上很贵，分开维护避免每次廉价
        # 刷新都重算。值由 _refresh_nas_total() 异步更新。
        self._nas_total_cache: str = "计算中…"

        self._build_ui()
        self.refresh_projects()

        # 廉价定期刷新（15s）— 仅刷新项目详情 + 时间/调度等便宜的状态文字。
        # 不在这里跑 NAS 全盘 size 计算。
        self._auto_refresh_timer = QTimer(self)
        self._auto_refresh_timer.setInterval(15000)
        self._auto_refresh_timer.timeout.connect(self._auto_refresh_tick)
        self._auto_refresh_timer.start()

        # NAS 占用单独 5min 间隔。备份/恢复/迁移完成后会主动调一次刷新。
        self._nas_size_timer = QTimer(self)
        self._nas_size_timer.setInterval(5 * 60 * 1000)
        self._nas_size_timer.timeout.connect(self._refresh_nas_total)
        self._nas_size_timer.start()
        QTimer.singleShot(100, self._refresh_nas_total)  # 启动后稍后算一次

    def _auto_refresh_tick(self):
        """定期自动刷新当前项目详情 + 状态栏，发现后台新生成的备份."""
        try:
            if self._current_project is not None:
                self._refresh_detail()
            self._update_status_bar()
        except Exception:  # noqa: BLE001
            pass

    def set_notifier(self, notifier: Callable) -> None:
        """app.py 创建主窗口后注入 tray.notify，让失败/成功能弹 Win11 toast."""
        self._notifier = notifier

    def _notify(self, title: str, message: str, level: str = "info") -> None:
        if self._notifier:
            try:
                self._notifier(title, message, level)
            except Exception:  # noqa: BLE001
                pass

    # ---------- UI 构建 ----------

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(self._build_topbar())

        # 三栏
        body = QWidget()
        body_lay = QHBoxLayout(body)
        body_lay.setContentsMargins(20, 20, 20, 20)
        body_lay.setSpacing(20)

        body_lay.addWidget(self._build_left_pane(), 0)
        body_lay.addWidget(self._build_center_pane(), 1)
        body_lay.addWidget(self._build_right_pane(), 0)

        outer.addWidget(body, 1)

        outer.addWidget(self._build_status_bar())

    def _build_topbar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("TopBar")
        bar.setFixedHeight(56)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(20, 0, 20, 0)
        lay.setSpacing(12)

        # 真实图标 + 文字标题（替代之前的 📦 emoji）
        icon_lb = QLabel()
        icon_lb.setPixmap(app_icon().pixmap(28, 28))
        icon_lb.setFixedSize(28, 28)
        lay.addWidget(icon_lb)

        title = QLabel(i18n.APP_NAME)
        title.setObjectName("H2")
        lay.addWidget(title)

        lay.addStretch()

        health_btn = IconButton("🩺", tooltip="健康检查 — 扫所有项目找隐患")
        health_btn.clicked.connect(self._show_health_check)
        lay.addWidget(health_btn)

        about_btn = IconButton("ⓘ", tooltip="关于 ClaudeBackup")
        about_btn.clicked.connect(self._show_about)
        lay.addWidget(about_btn)

        help_btn = IconButton("?", tooltip="帮助 / 重看引导")
        help_btn.clicked.connect(self._show_help)
        lay.addWidget(help_btn)

        settings_btn = IconButton("⚙", tooltip="设置")
        settings_btn.clicked.connect(self._show_settings)
        lay.addWidget(settings_btn)

        return bar

    def _build_left_pane(self) -> QWidget:
        pane = QWidget()
        pane.setFixedWidth(260)
        pane.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        lay = QVBoxLayout(pane)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        title = QLabel("项目")
        title.setObjectName("Dim")
        lay.addWidget(title)

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("🔍 搜索项目…")
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.textChanged.connect(self._on_search_changed)
        lay.addWidget(self._search_edit)

        # 项目列表（可滚动）
        self._project_list_widget = QWidget()
        self._project_list_layout = QVBoxLayout(self._project_list_widget)
        self._project_list_layout.setContentsMargins(0, 0, 0, 0)
        self._project_list_layout.setSpacing(6)
        self._project_list_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(self._project_list_widget)
        lay.addWidget(scroll, 1)

        self._add_btn = PrimaryButton(i18n.LEFT_ADD_PROJECT)
        self._add_btn.clicked.connect(self.action_register)
        lay.addWidget(self._add_btn)

        return pane

    def _build_center_pane(self) -> QWidget:
        self._center_stack = QWidget()
        lay = QVBoxLayout(self._center_stack)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(16)

        # 空状态视图
        self._empty_view = EmptyProjectsHint()
        self._empty_view.add_clicked.connect(self.action_register)

        # 详情卡
        self._detail_card = Card()
        self._detail_title = QLabel("")
        self._detail_title.setObjectName("H1")
        self._detail_card.addWidget(self._detail_title)

        self._detail_path = QLabel("")
        self._detail_path.setObjectName("Dim")
        self._detail_card.addWidget(self._detail_path)

        # GitHub 状态行
        gh_row = QHBoxLayout()
        gh_row.setSpacing(8)
        self._detail_github = QLabel("")
        self._detail_github.setObjectName("Dim")
        gh_row.addWidget(self._detail_github, 1)
        self._btn_config_gh = SecondaryButton("⚙️ 配置 GitHub")
        self._btn_config_gh.clicked.connect(self.action_configure_github)
        gh_row.addWidget(self._btn_config_gh)
        self._detail_card.addLayout(gh_row)

        self._detail_card.addWidget(make_separator())

        self._stat_row = StatRow()
        self._detail_card.addWidget(self._stat_row)

        self._detail_card.addWidget(make_separator())

        # 时间线标题行 + 按文件查看历史按钮
        tl_row = QHBoxLayout()
        timeline_label = QLabel(i18n.DETAIL_TIMELINE)
        timeline_label.setObjectName("H3")
        tl_row.addWidget(timeline_label, 1)
        self._btn_file_history = SecondaryButton("📄 按文件查看历史")
        self._btn_file_history.setToolTip(
            "选项目里的某个文件 → 看它每次备份的版本，可对比 / 单文件恢复"
        )
        self._btn_file_history.clicked.connect(self.action_file_history)
        tl_row.addWidget(self._btn_file_history)
        self._detail_card.addLayout(tl_row)

        self._timeline = QListWidget()
        self._timeline.setMinimumHeight(220)
        self._timeline.setAlternatingRowColors(False)
        self._timeline.itemDoubleClicked.connect(self._on_timeline_dbl_click)
        self._detail_card.addWidget(self._timeline)

        lay.addWidget(self._empty_view)
        lay.addWidget(self._detail_card)

        return self._center_stack

    def _build_right_pane(self) -> QWidget:
        pane = QWidget()
        pane.setFixedWidth(280)
        lay = QVBoxLayout(pane)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        title = QLabel("操作")
        title.setObjectName("Dim")
        lay.addWidget(title)

        self._btn_backup = ActionCardButton(i18n.ACTION_BACKUP_NOW, i18n.ACTION_BACKUP_NOW_DESC)
        self._btn_release = ActionCardButton(i18n.ACTION_RELEASE, i18n.ACTION_RELEASE_DESC)
        self._btn_compare = ActionCardButton(i18n.ACTION_COMPARE, i18n.ACTION_COMPARE_DESC)
        self._btn_list = ActionCardButton(i18n.ACTION_LIST, i18n.ACTION_LIST_DESC)

        self._btn_backup.clicked.connect(self.action_backup)
        self._btn_release.clicked.connect(self.action_release)
        self._btn_compare.clicked.connect(self.action_compare)
        self._btn_list.clicked.connect(self.action_list)

        for b in (self._btn_backup, self._btn_release, self._btn_compare, self._btn_list):
            lay.addWidget(b)

        lay.addStretch()

        # 危险区：删除项目（视觉降权）
        self._btn_delete = SecondaryButton("🗑 删除此项目")
        self._btn_delete.setToolTip(
            "把这个项目从备份列表移除（不会删本地文件夹；NAS 上的备份可选是否一起清）"
        )
        self._btn_delete.clicked.connect(self.action_delete_project)
        lay.addWidget(self._btn_delete)
        return pane

    def _build_status_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("StatusBar")
        bar.setFixedHeight(36)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(20, 0, 20, 0)
        lay.setSpacing(20)

        self._status_next_daily = QLabel("")
        self._status_last_auto = QLabel("")
        self._status_total = QLabel("")
        for w in (self._status_next_daily, self._status_last_auto, self._status_total):
            w.setObjectName("Mini")
            lay.addWidget(w)
        lay.addStretch()

        self._update_status_bar()
        return bar

    # ---------- 数据刷新 ----------

    def refresh_projects(self):
        """从 registry 重新加载项目列表."""
        # 清空旧按钮
        for btn in self._project_buttons:
            self._project_btn_group.removeButton(btn)
            btn.deleteLater()
        self._project_buttons.clear()

        # 移除 stretch 之前的所有 widget
        layout = self._project_list_layout
        while layout.count() > 0:
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        reg = registry.load()
        if not reg.projects:
            # 空态
            self._empty_view.show()
            self._detail_card.hide()
            self._enable_actions(False)
            layout.addStretch()
            return

        self._empty_view.hide()
        self._detail_card.show()

        for entry in reg.projects:
            status_text, status_kind = self._compute_status(entry)
            btn = ProjectCardButton(entry, status_text, status_kind)
            btn.clicked.connect(lambda _=False, e=entry: self.select_project(e))
            self._project_buttons.append(btn)
            self._project_btn_group.addButton(btn)
            layout.addWidget(btn)
        layout.addStretch()

        # 默认选中第一个
        if reg.projects:
            target = self._current_project
            if target is None or reg.find_by_path(target.path) is None:
                target = reg.projects[0]
            self.select_project(target)
        # 任何项目刷新都顺便刷状态栏（"最近一次备份" / NAS 占用）
        self._update_status_bar()

    def _on_search_changed(self, query: str) -> None:
        """实时过滤项目列表 — 大小写不敏感，匹配 name 或 path."""
        q = query.strip().lower()
        for btn in self._project_buttons:
            entry = btn.entry
            visible = (
                not q
                or q in entry.name.lower()
                or q in entry.path.lower()
            )
            btn.setVisible(visible)

    def _compute_status(self, e: registry.ProjectEntry) -> tuple[str, str]:
        if not Path(e.path).exists():
            return (i18n.STATUS_PATH_MISSING, "missing")
        if not git_ops.is_git_repo(e.path):
            return (i18n.STATUS_PATH_MISSING, "missing")
        try:
            s = change_detect.detect(e.path)
        except Exception:  # noqa: BLE001
            return (i18n.STATUS_PATH_MISSING, "missing")
        if s.last_backup_hash is None:
            return (i18n.STATUS_NEVER_BACKED_UP, "never")
        if s.has_changes:
            return (i18n.STATUS_HAS_CHANGES, "changes")
        return (i18n.STATUS_HEALTHY, "healthy")

    def select_project(self, entry: registry.ProjectEntry):
        self._current_project = entry
        # 同步选中态
        for b in self._project_buttons:
            b.setChecked(b.entry.path == entry.path)
        self._refresh_detail()
        self._enable_actions(True)

    def _refresh_detail(self):
        e = self._current_project
        if e is None:
            return
        self._detail_title.setText(e.name)
        self._detail_path.setText(f"📁  {e.path}")

        # GitHub 状态
        if e.github_url:
            self._detail_github.setText(f"🐙 GitHub：{e.github_url}")
            self._detail_github.setToolTip(e.github_url)
        else:
            self._detail_github.setText("🐙 GitHub：未配置（发布版本只会上传到 NAS）")
            self._detail_github.setToolTip("")

        # 统计
        nas_count = "—"
        bundle_count = "—"
        release_count = "—"
        dir_count = "—"
        try:
            if Path(e.path).exists() and git_ops.is_git_repo(e.path):
                commits = git_ops.log_oneline(e.path, limit=10000)
                nas_count = str(len(commits))
        except Exception:
            pass
        bdir = Path(e.bundle_dir)
        if bdir.exists():
            bundles = list(bdir.glob("*.bundle"))
            bundle_count = str(len(bundles))
            rdir = bdir / "releases"
            if rdir.exists():
                release_count = str(len(list(rdir.glob("*.bundle"))))

        from .. import paths as _paths
        snap_root = _paths.NAS_SNAPSHOTS_DIR / e.name
        if snap_root.exists():
            dir_count = str(len([d for d in snap_root.iterdir() if d.is_dir()]))

        self._stat_row.set_stats([
            (i18n.DETAIL_NAS_COUNT, nas_count),
            (i18n.DETAIL_BUNDLE_COUNT, bundle_count),
            (i18n.DETAIL_DIR_SNAPSHOT_COUNT, dir_count),
            (i18n.DETAIL_RELEASE_COUNT, release_count),
        ])

        # 时间线（紧凑列表，每行单行不换行；双击 = 打开 NAS 目录/文件）
        self._timeline.clear()
        try:
            res = core.list_backup_points(e.path, limit_commits=20)
        except Exception as ex:  # noqa: BLE001
            err_item = QListWidgetItem(f"读取失败：{ex}")
            err_item.setFlags(Qt.NoItemFlags)
            self._timeline.addItem(err_item)
            return

        if not res.points:
            empty = QListWidgetItem(
                "（还没有备份点 — 点右侧「📸 立即备份」开始）"
            )
            empty.setFlags(Qt.NoItemFlags)
            self._timeline.addItem(empty)
            return

        kinds_zh = {"commit": "提交", "bundle": "时间快照",
                    "dir_snapshot": "目录快照", "release": "发布版本"}
        for p in res.points[:60]:
            when = p.when.strftime("%Y-%m-%d %H:%M") if p.when else "—"
            kind_zh = kinds_zh.get(p.kind, p.kind)
            # 卡片化：左侧类型色条 + 时间 + 徽章 + 详情副文字
            row = TimelineRow(p.kind, when, p.label, p.detail)
            item = QListWidgetItem()
            item.setData(Qt.UserRole, p)
            item.setSizeHint(row.sizeHint())
            item.setToolTip(f"[{kind_zh}] {p.label}\n{p.detail}\n（双击打开 NAS）")
            self._timeline.addItem(item)
            self._timeline.setItemWidget(item, row)

    def _on_timeline_dbl_click(self, item: QListWidgetItem):
        p = item.data(Qt.UserRole)
        if p is None:
            return
        target = getattr(p, "fs_path", None)
        if target is None:
            return
        try:
            tp = Path(target)
            if tp.is_dir():
                os.startfile(str(tp))
            elif tp.exists():
                os.startfile(str(tp.parent))
        except OSError as e:  # noqa: BLE001
            dialogs.error(self, "打开失败", str(e))

    def _enable_actions(self, enabled: bool):
        for b in (self._btn_backup, self._btn_release, self._btn_compare,
                  self._btn_list, self._btn_delete, self._btn_config_gh,
                  self._btn_file_history):
            b.setEnabled(enabled)

    def _update_status_bar(self):
        cfg = config.load()
        self._status_next_daily.setText(
            f"{i18n.STATUS_NEXT_DAILY}: 每日 {cfg.schedule_time}" +
            (" (已暂停)" if cfg.schedule_paused else "")
        )
        # 最近一次备份：取所有项目 last_backup_at 的最大值，再合并 Stop hook 日志
        from .. import paths as p
        candidates: list[str] = []
        try:
            reg = registry.load()
            for entry in reg.projects:
                if entry.last_backup_at:
                    candidates.append(entry.last_backup_at)
        except Exception:  # noqa: BLE001
            pass
        if p.HOOK_LOG_FILE.exists():
            try:
                lines = p.HOOK_LOG_FILE.read_text("utf-8").strip().splitlines()[-50:]
                for ln in reversed(lines):
                    if "INFO" in ln and "pushed" in ln:
                        # hook log 行首是 ISO 时间戳前 19 字符
                        candidates.append(ln[:19])
                        break
            except OSError:
                pass
        if candidates:
            latest = max(candidates)
            # 标准化展示：YYYY-MM-DD HH:MM
            display = latest.replace("T", " ")[:16]
        else:
            display = "—"
        self._status_last_auto.setText(f"{i18n.STATUS_LAST_AUTO}: {display}")

        # NAS 总占用：用上次算好的缓存值（启动时 + 每 5min + 备份完成时各算一次）
        self._status_total.setText(f"{i18n.STATUS_TOTAL_SIZE}: {self._nas_total_cache}")

    def _refresh_nas_total(self):
        """后台异步重算 NAS 占用并刷新到状态栏 + 缓存."""
        from .workers import run_async
        from .. import paths as _p

        def _calc():
            total = 0
            for sub in (_p.NAS_BACKUPS_DIR, _p.NAS_BUNDLES_DIR, _p.NAS_SNAPSHOTS_DIR):
                if not sub.exists():
                    continue
                for root, _dirs, files in __import__("os").walk(sub):
                    for f in files:
                        try:
                            total += (Path(root) / f).stat().st_size
                        except OSError:
                            pass
            return total

        def on_ok(total: int):
            self._nas_total_cache = self._fmt_size(total)
            self._status_total.setText(f"{i18n.STATUS_TOTAL_SIZE}: {self._nas_total_cache}")

        def on_err(_msg: str):
            self._nas_total_cache = "—"
            self._status_total.setText(f"{i18n.STATUS_TOTAL_SIZE}: —")

        t = run_async(self, _calc, on_ok, on_err)
        self._active_threads.append(t)

    @staticmethod
    def _fmt_size(n: int) -> str:
        for unit, threshold in (("TB", 1 << 40), ("GB", 1 << 30),
                                ("MB", 1 << 20), ("KB", 1 << 10)):
            if n >= threshold:
                return f"{n / threshold:.1f} {unit}"
        return f"{n} B"

    # ---------- 操作 ----------

    def action_register(self):
        dlg = dialogs.RegisterProjectDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        path, github_url = dlg.values()
        if not path or not Path(path).exists():
            dialogs.error(self, "添加项目", "目录不存在")
            return

        from .progress_dialog import ProgressDialog
        prog = ProgressDialog(self, title="添加项目", subtitle=f"正在配置 {Path(path).name}…")
        prog.show()

        def on_ok(res: core.InitResult):
            parts = [f"已配好 {res.project.name}"]
            if res.wrote_gitignore:
                heavy = ", ".join(res.detected_heavy_dirs[:3])
                more = f" 等 {len(res.detected_heavy_dirs)} 项" if len(res.detected_heavy_dirs) > 3 else ""
                parts.append(f"已写入推荐 .gitignore（避免 {heavy}{more} 拖慢备份）")
            prog.finish(success=True, summary="；".join(parts))
            self.refresh_projects()
            self.select_project(res.project)

        def on_err(msg: str):
            prog.finish(success=False, summary=msg)

        t = run_async(self, core.init_project, on_ok, on_err,
                      path, github_url=github_url,
                      on_progress=prog.add_stage)
        self._active_threads.append(t)

    def action_backup(self):
        e = self._current_project
        if e is None:
            return

        from .progress_dialog import ProgressDialog
        prog = ProgressDialog(self, title="立即备份", subtitle=f"正在备份 {e.name}…")
        prog.show()

        def on_ok(res: core.BackupResult):
            parts = []
            if res.dir_snapshot_path:
                parts.append(f"完整目录: {res.dir_snapshot_path.name}")
            if res.bundle_path:
                parts.append(f"时间快照: {res.bundle_path.name}")
            if res.pushed_to_nas:
                parts.append("已上传 NAS")
            if not parts:
                parts.append("完成")
            if res.auto_committed:
                parts.append("（已自动保存当前修改）")
            if res.git_baseline_warning:
                parts.append(f"⚠️ {res.git_baseline_warning}")
            prog.finish(success=True, summary="；".join(parts))
            level = "warn" if res.git_baseline_warning else "info"
            title = ("⚠️ " if res.git_baseline_warning else "✅ ") + f"已备份 {e.name}"
            self._notify(title, "；".join(parts), level)
            self._refresh_detail()
            self.refresh_projects()
            self._refresh_nas_total()  # 备份成功 → 占用变了，主动刷

        def on_err(msg: str):
            prog.finish(success=False, summary=msg)
            self._notify(f"⚠️ {e.name} 备份失败", msg[:200], "error")

        t = run_async(self, core.backup_project, on_ok, on_err, e.path,
                      on_progress=prog.add_stage)
        self._active_threads.append(t)

    def action_release(self):
        e = self._current_project
        if e is None:
            return

        # 收集上下文：上一个 tag + commit log
        tags = git_ops.list_tags(e.path) if Path(e.path).exists() else []
        last_tag = tags[0] if tags else None
        log_text = ""
        try:
            rng = f"{last_tag}..HEAD" if last_tag else None
            log_text = "\n".join(
                f"  • {s}" for _, s in git_ops.log_oneline(e.path, rng=rng, limit=20)
            )
        except Exception:
            pass

        dlg = dialogs.ReleaseDialog(self, last_tag=last_tag, commit_log_text=log_text)
        if dlg.exec() != QDialog.Accepted:
            return
        version, desc = dlg.values()
        if not version:
            dialogs.error(self, "缺少版本号", "请填写版本号，例如 v1.0.0")
            return

        push_github = bool(e.github_url)
        if not push_github:
            ok = dialogs.confirm(
                self, "未配置 GitHub",
                "这个项目还没配 GitHub 远程。要继续吗？\n（只会上传到 NAS 并归档时间快照）",
                ok_text="继续", cancel_text="先去配置",
            )
            if not ok:
                return

        def on_ok(res: core.ReleaseResult):
            msg = (
                f"已发布 {res.project_name} {res.version}\n"
                f"NAS 上传：{'✅' if res.pushed_to_nas else '⏭️'}\n"
                f"GitHub 上传：{'✅' if res.pushed_to_github else '⏭️'}\n"
                f"归档快照：{res.bundle_path}"
            )
            dialogs.info(self, "🚀 发布完成", msg)
            self._notify(f"🚀 已发布 {res.project_name} {res.version}",
                         f"NAS:{res.pushed_to_nas} GitHub:{res.pushed_to_github}", "info")
            self._refresh_detail()

        def on_err(msg: str):
            dialogs.error(self, "发布失败", msg)
            self._notify(f"⚠️ 发布失败", msg[:200], "error")

        t = run_async(self, core.release_project, on_ok, on_err,
                      e.path, version, description=desc,
                      push_github=push_github)
        self._active_threads.append(t)

    def action_compare(self, preselect_end=None):
        e = self._current_project
        if e is None:
            return
        try:
            res = core.list_backup_points(e.path, limit_commits=200)
            points = res.points
        except Exception as ex:  # noqa: BLE001
            dialogs.error(self, "读取备份点失败", str(ex))
            return

        dlg = dialogs.CompareDialog(self, points=points, preselect_end=preselect_end)
        if dlg.exec() != QDialog.Accepted:
            return
        p1, p2 = dlg.selected_points()
        if not p1 or not p2:
            return

        def _fmt_label(p):
            when = p.when.strftime("%Y-%m-%d %H:%M") if p.when else ""
            return f"[目录快照] {p.label}" + (f"  ·  {when}" if when else "")

        label1 = _fmt_label(p1)
        label2 = _fmt_label(p2)

        def on_ok(res: core.CompareResult):
            d = dialogs.CompareResultDialog(self, res.summary, res.files,
                                             label1, label2)
            d.exec()

        def on_err(msg: str):
            dialogs.error(self, "对比失败", msg)

        t = run_async(self, core.compare_dir_snapshots, on_ok, on_err,
                      p1.fs_path, p2.fs_path)
        self._active_threads.append(t)

    def action_list(self):
        """时间机器 — 滑块式回看任意时刻 + 一键恢复."""
        e = self._current_project
        if e is None:
            return
        try:
            res = core.list_backup_points(e.path, limit_commits=200)
        except Exception as ex:  # noqa: BLE001
            dialogs.error(self, "读取失败", str(ex))
            return

        from .timeline_dialog import TimelineDialog
        dlg = TimelineDialog(self, e.name, res.points, project_path=e.path)
        dlg.request_open.connect(self._timeline_open)
        dlg.request_restore.connect(self._browse_restore)
        dlg.exec()

    def action_file_history(self):
        """打开文件级历史回溯对话框."""
        e = self._current_project
        if e is None:
            return
        try:
            points = core.list_backup_points(e.path, limit_commits=200).points
        except Exception as ex:  # noqa: BLE001
            dialogs.error(self, "读取失败", str(ex))
            return
        from .file_history_dialog import FileHistoryDialog
        dlg = FileHistoryDialog(self, e, points)
        dlg.exec()

    def _timeline_open(self, point):
        """时间机器里点了「在 NAS 打开」."""
        target = getattr(point, "fs_path", None)
        if target is None:
            return
        try:
            tp = Path(target)
            if tp.is_dir():
                os.startfile(str(tp))
            elif tp.exists():
                os.startfile(str(tp.parent))
        except OSError as e:  # noqa: BLE001
            dialogs.error(self, "打开失败", str(e))

    def _browse_compare(self, point):
        """从浏览备份对话框点了"对比此版本"."""
        self.action_compare(preselect_end=point)

    def _browse_restore(self, point):
        """从浏览备份对话框点了"恢复到这个版本"."""
        e = self._current_project
        if e is None or point is None or point.kind != "dir_snapshot":
            return
        from .progress_dialog import ProgressDialog
        prog = ProgressDialog(
            self, title="恢复版本",
            subtitle=f"把 {e.name} 恢复到 {point.label}…",
        )
        prog.show()

        def on_ok(res: core.RestoreResult):
            prog.finish(
                success=True,
                summary=(f"已恢复 {res.restored_count} 个文件；"
                         f"安全备份：{res.safety_backup.name}"),
            )
            self._refresh_detail()
            self.refresh_projects()
            self._refresh_nas_total()  # 恢复也写了 safety 副本，占用变了

        def on_err(msg: str):
            prog.finish(success=False, summary=msg)

        t = run_async(self, core.restore_from_dir_snapshot,
                      on_ok, on_err,
                      point.fs_path, e.path,
                      on_progress=prog.add_stage)
        self._active_threads.append(t)

    def action_delete_project(self):
        e = self._current_project
        if e is None:
            return
        confirmed, also_clean_nas = dialogs.confirm_delete_project(self, e.name)
        if not confirmed:
            return
        try:
            registry.remove(e.path)
        except Exception as ex:  # noqa: BLE001
            dialogs.error(self, "删除失败", str(ex))
            return

        cleaned_paths: list[str] = []
        clean_errors: list[str] = []
        if also_clean_nas:
            from .. import paths as _paths
            for p in (Path(e.nas_mirror), Path(e.bundle_dir),
                      _paths.NAS_SNAPSHOTS_DIR / e.name):
                if p.exists():
                    try:
                        _force_rmtree(p)
                        cleaned_paths.append(str(p))
                    except OSError as ex:
                        clean_errors.append(f"{p}: {ex}")
            if clean_errors:
                dialogs.error(
                    self, "NAS 清理部分失败",
                    "\n\n".join(clean_errors)
                    + "\n\n项目已从列表移除；剩余 NAS 文件请手动清理。",
                )

        msg = f"已把「{e.name}」从备份列表移除。"
        if cleaned_paths:
            msg += f"\n\n同时清空了 NAS 上 {len(cleaned_paths)} 个目录。"
        dialogs.info(self, "已删除", msg)
        self._current_project = None
        self.refresh_projects()

    def action_configure_github(self):
        e = self._current_project
        if e is None:
            return
        dlg = dialogs.ConfigGitHubDialog(self, current_url=e.github_url,
                                          project_name=e.name)
        if dlg.exec() != QDialog.Accepted:
            return
        new_url = dlg.value()
        # 更新 git remote + registry
        try:
            if new_url:
                if not git_ops.has_remote(e.path, "origin"):
                    git_ops.add_remote(e.path, "origin", new_url)
                else:
                    existing = git_ops.list_remotes(e.path).get("origin")
                    if existing != new_url:
                        git_ops.set_remote_url(e.path, "origin", new_url)
            e.github_url = new_url
            registry.upsert(e)
            self._refresh_detail()
            dialogs.info(self, "✅ 已更新",
                         f"GitHub 远程：{new_url or '(已清空)'}")
        except Exception as ex:  # noqa: BLE001
            dialogs.error(self, "更新失败", str(ex))

    def _show_health_check(self):
        from .health_dialog import HealthCheckDialog
        dlg = HealthCheckDialog(self)
        dlg.exec()

    def _show_about(self):
        from .about_dialog import AboutDialog
        AboutDialog(self).exec()

    def _show_help(self):
        from .onboarding import OnboardingWizard
        w = OnboardingWizard(self)
        w.exec()

    def _show_settings(self):
        from .settings_dialog import SettingsDialog
        d = SettingsDialog(self)
        if d.exec() == QDialog.Accepted:
            self._update_status_bar()
            self.refresh_projects()
