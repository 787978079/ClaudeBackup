"""系统托盘 — QSystemTrayIcon 常驻 + 右键菜单 + 通知."""
from __future__ import annotations
import os
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from . import i18n
from .assets import tray_pixmap
from .. import config, core, git_ops, paths, registry
from .workers import run_async


# 状态着色 — 在主图标右下角叠一个色点（busy=黄/ok=绿/error=红），idle 时不叠.
STATUS_COLORS = {
    "idle":  None,
    "busy":  "#FBBF24",
    "ok":    "#34D399",
    "error": "#F87171",
}


def _icon_with_status(status: str) -> QIcon:
    """返回主图标 + 右下角状态指示点。idle 时直接返回原图标."""
    base = tray_pixmap(64)
    color = STATUS_COLORS.get(status)
    if color is None:
        return QIcon(base)
    pm = QPixmap(base)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor(color))
    painter.setPen(QColor("#0E0E10"))   # 深色描边让色点在浅色任务栏上也清晰
    # 右下角 18px 圆点
    painter.drawEllipse(40, 40, 20, 20)
    painter.end()
    return QIcon(pm)


class TrayController(QObject):
    """托盘控制器 — 负责图标、菜单、通知；不直接持有主窗口逻辑."""

    request_open_window = Signal()
    request_quit = Signal()
    request_show_logs = Signal()

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)

        self._icon = QSystemTrayIcon(_icon_with_status("idle"), self)
        self._icon.setToolTip(i18n.TRAY_TOOLTIP)

        self._menu = QMenu()
        self._build_menu()
        self._icon.setContextMenu(self._menu)
        self._icon.activated.connect(self._on_activated)
        # 菜单弹出前刷新项目状态摘要（懒加载，避免常驻 IO）
        self._menu.aboutToShow.connect(self._refresh_status_submenu)
        self._icon.show()

    def _build_menu(self):
        self._open_act = QAction(i18n.TRAY_OPEN, self)
        self._open_act.triggered.connect(self.request_open_window.emit)
        self._menu.addAction(self._open_act)

        self._backup_here_act = QAction(i18n.TRAY_BACKUP_HERE, self)
        self._backup_here_act.triggered.connect(self._backup_cwd)
        self._menu.addAction(self._backup_here_act)

        self._backup_all_act = QAction(i18n.TRAY_BACKUP_ALL, self)
        self._backup_all_act.triggered.connect(self._backup_all)
        self._menu.addAction(self._backup_all_act)

        # 项目状态摘要子菜单 — 内容在 aboutToShow 时刷新
        self._status_submenu = self._menu.addMenu("📊 项目状态")

        self._menu.addSeparator()

        self._open_nas_act = QAction(i18n.TRAY_OPEN_NAS, self)
        self._open_nas_act.triggered.connect(self._open_nas_root)
        self._menu.addAction(self._open_nas_act)

        self._toggle_pause_act = QAction("", self)
        self._toggle_pause_act.triggered.connect(self._toggle_pause)
        self._menu.addAction(self._toggle_pause_act)
        self._refresh_pause_label()

        self._logs_act = QAction(i18n.TRAY_VIEW_LOGS, self)
        self._logs_act.triggered.connect(self.request_show_logs.emit)
        self._menu.addAction(self._logs_act)

        self._menu.addSeparator()

        self._about_act = QAction(i18n.TRAY_ABOUT, self)
        self._about_act.triggered.connect(self._show_about)
        self._menu.addAction(self._about_act)

        self._quit_act = QAction(i18n.TRAY_QUIT, self)
        self._quit_act.triggered.connect(self.request_quit.emit)
        self._menu.addAction(self._quit_act)

    def _refresh_status_submenu(self):
        """菜单弹出前重建项目状态子菜单 — 每个项目一行，带状态点 + 时间."""
        from datetime import datetime
        from .. import change_detect
        self._status_submenu.clear()
        try:
            reg = registry.load()
        except Exception:  # noqa: BLE001
            return
        if not reg.projects:
            empty = QAction("（还没有项目）", self)
            empty.setEnabled(False)
            self._status_submenu.addAction(empty)
            return

        dot = {"healthy": "🟢", "changes": "🟡", "missing": "🔴", "never": "⚪"}
        for entry in reg.projects[:30]:  # 防止项目特别多时菜单过长
            kind = "missing"
            sub_text = ""
            try:
                from pathlib import Path as _P
                if _P(entry.path).exists() and git_ops.is_git_repo(entry.path):
                    s = change_detect.detect(entry.path, reg)
                    if s.last_backup_hash is None:
                        kind = "never"
                    elif s.has_changes:
                        kind = "changes"
                    else:
                        kind = "healthy"
            except Exception:  # noqa: BLE001
                kind = "missing"
            if entry.last_backup_at:
                sub_text = f"  ·  {entry.last_backup_at[:16].replace('T', ' ')}"
            act = QAction(f"{dot.get(kind, '⚪')}  {entry.name}{sub_text}", self)
            # 点项目 → 打开主窗口
            act.triggered.connect(self.request_open_window.emit)
            self._status_submenu.addAction(act)

    def _refresh_pause_label(self):
        cfg = config.load()
        if cfg.schedule_paused:
            self._toggle_pause_act.setText(i18n.TRAY_RESUME_DAILY)
        else:
            self._toggle_pause_act.setText(i18n.TRAY_PAUSE_DAILY)

    def _on_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self.request_open_window.emit()

    def _toggle_pause(self):
        cfg = config.load()
        cfg.schedule_paused = not cfg.schedule_paused
        config.save(cfg)
        self._refresh_pause_label()
        self.notify(
            "已暂停每日备份" if cfg.schedule_paused else "已恢复每日备份",
            "在主面板的设置里也可以再切换。",
        )

    def _backup_cwd(self):
        from pathlib import Path
        cwd = Path.cwd()
        if not git_ops.is_git_repo(cwd):
            self.notify(
                "当前文件夹不是 git 项目",
                "请把当前工作目录切到一个 git 项目，再点这个菜单。",
                level="warn",
            )
            return
        reg = registry.load()
        entry = reg.find_by_path(cwd)
        if entry is None:
            self.notify(
                "项目还没注册",
                "请先在主面板里 \"添加项目\"。",
                level="warn",
            )
            self.request_open_window.emit()
            return

        # 异步：大项目同步备份要 10+ 秒，会冻结托盘菜单导致用户右键无反应
        self.set_status("busy")

        def _on_ok(res):
            self.set_status("ok")
            if res.bundle_path:
                self.notify(
                    i18n.NOTIFY_BACKUP_OK.format(name=entry.name),
                    f"快照：{res.bundle_path.name}",
                )
            else:
                self.notify(i18n.NOTIFY_BACKUP_OK.format(name=entry.name), "已上传备份位置")

        def _on_err(msg: str):
            self.set_status("error")
            self.notify(
                i18n.NOTIFY_BACKUP_FAIL.format(name=entry.name),
                msg,
                level="error",
            )

        t = run_async(self, core.backup_project, _on_ok, _on_err, str(cwd))
        # 防 GC
        if not hasattr(self, "_active_threads"):
            self._active_threads = []
        self._active_threads.append(t)

    def _backup_all(self):
        """遍历 registry 对所有项目跑一次备份."""
        reg = registry.load()
        if not reg.projects:
            self.notify("还没有项目", "先在主面板「➕ 添加项目」。", level="warn")
            self.request_open_window.emit()
            return
        # 异步：N 个项目顺序备份是分钟级，主线程跑会冻结整个托盘
        self.set_status("busy")
        entries = list(reg.projects)

        def _do_all():
            ok, fail = 0, 0
            for entry in entries:
                try:
                    core.backup_project(entry.path)
                    ok += 1
                except Exception:  # noqa: BLE001
                    fail += 1
            return ok, fail

        def _on_ok(result):
            ok_count, fail_count = result
            self.set_status("ok" if fail_count == 0 else "error")
            msg = f"成功 {ok_count} 个"
            if fail_count:
                msg += f"，失败 {fail_count} 个（详情见日志）"
            self.notify("📸 全部项目备份完成", msg,
                        level="info" if fail_count == 0 else "warn")

        def _on_err(msg: str):
            self.set_status("error")
            self.notify("📸 批量备份异常中断", msg, level="error")

        t = run_async(self, _do_all, _on_ok, _on_err)
        if not hasattr(self, "_active_threads"):
            self._active_threads = []
        self._active_threads.append(t)

    def _open_nas_root(self):
        """打开 NAS 备份根目录（资源管理器）."""
        # 动态解析当前配置的备份位置 — 模块级 paths.NAS_ROOT 是首次导入时的快照，
        # 用户在设置里改了备份位置后不会更新；这里每次按钮触发时重新读 config。
        root = paths._resolve_nas_root()
        if root is None:
            self.notify("还没配置备份位置",
                        "请打开主面板的 ⚙️ 设置 → 📂 备份位置 先选一个文件夹。",
                        level="warn")
            self.request_open_window.emit()
            return
        if not root.exists():
            self.notify("备份位置不可访问",
                        f"{root} 现在打不开（盘没挂上？）", level="warn")
            return
        try:
            os.startfile(str(root))
        except OSError as e:
            self.notify("打开失败", str(e), level="error")

    def _show_about(self):
        # 优先开正经 About 对话框；纯托盘模式（无 QApp 主面板）则用通知作为回退
        try:
            from .about_dialog import AboutDialog
            dlg = AboutDialog()
            dlg.show()
            dlg.raise_()
            from PySide6.QtCore import QEventLoop
            loop = QEventLoop()
            dlg.finished.connect(loop.quit)
            loop.exec()
        except Exception:  # noqa: BLE001
            from .. import __version__
            self.notify(
                f"{i18n.APP_NAME} {__version__}",
                "Win11 Git 三层备份工具",
            )

    # ---------- 公共方法 ----------

    def set_status(self, status: str):
        """status: idle / busy / ok / error — 在主图标右下角叠一个状态色点."""
        self._icon.setIcon(_icon_with_status(status))

    def notify(self, title: str, message: str, level: str = "info"):
        cfg = config.load()
        if not cfg.show_tray_notifications:
            return
        icon_kind = {
            "info": QSystemTrayIcon.Information,
            "warn": QSystemTrayIcon.Warning,
            "error": QSystemTrayIcon.Critical,
        }.get(level, QSystemTrayIcon.Information)
        self._icon.showMessage(title, message, icon_kind, 5000)

    def hide(self):
        self._icon.hide()
