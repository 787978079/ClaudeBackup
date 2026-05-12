"""QApplication 启动器 — 提供 run_main / run_tray / run_action 三种模式."""
from __future__ import annotations
import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QSharedMemory
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from . import dialogs, i18n, theme
from .assets import app_icon
from .. import config, core, git_ops, logger, paths, registry


# Windows AppUserModelID — 让任务栏图标正确分组、toast 显示发件人为本应用
# 而不是 "Python"。任意稳定字符串都行，约定 CompanyName.ProductName.Version。
_AUMID = "lin.ClaudeBackup.App"


_app: QApplication | None = None
_tray = None
_window = None
_single_instance_lock: QSharedMemory | None = None


def _install_excepthook() -> None:
    """全局异常 hook — 未捕获异常一律写 crash.log + 弹友好对话框.

    Qt 内部异常（信号槽里抛的）走 sys.excepthook 而不是默认的 print。
    """
    import traceback
    orig_hook = sys.excepthook

    def _hook(exc_type, exc_value, exc_tb):
        # KeyboardInterrupt 不打扰
        if issubclass(exc_type, KeyboardInterrupt):
            orig_hook(exc_type, exc_value, exc_tb)
            return
        tb_text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        log = logger.get(__name__)
        log.error("Unhandled exception", exc_info=(exc_type, exc_value, exc_tb))
        try:
            crash_path = logger.write_crash(tb_text, "unhandled-excepthook")
        except OSError:
            crash_path = None
        # 弹友好崩溃对话框（QApplication 必须已 init）
        try:
            box = QMessageBox()
            box.setIcon(QMessageBox.Critical)
            box.setWindowTitle(f"{i18n.APP_NAME} 出错了")
            crash_hint = f"\n\n详细信息已写入：\n{crash_path}" if crash_path else ""
            box.setText(
                f"程序遇到一个未预期的错误。\n\n"
                f"{exc_type.__name__}: {exc_value}{crash_hint}\n\n"
                f"可点「Show Details」看完整 traceback，或复制后发给开发者。"
            )
            box.setDetailedText(tb_text)
            from PySide6.QtGui import QGuiApplication
            box.addButton(QMessageBox.Ok)
            copy_btn = box.addButton("复制完整 traceback", QMessageBox.ActionRole)
            box.exec()
            if box.clickedButton() is copy_btn:
                cb = QGuiApplication.clipboard()
                if cb is not None:
                    cb.setText(tb_text)
        except Exception:  # noqa: BLE001
            # 弹窗本身崩了 — 不要无限递归
            pass

    sys.excepthook = _hook


def _set_windows_aumid() -> None:
    """Windows-only：设置 AppUserModelID，影响任务栏分组和 toast 通知归属."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(_AUMID)
    except (OSError, AttributeError):
        # 非 Windows 或老版本没这个 API — 静默跳过
        pass


def _acquire_single_instance() -> bool:
    """QSharedMemory 占位实现单实例。已有实例时返回 False.

    托盘 / 主窗口模式独占；CLI / 右键菜单 action 模式不应锁。
    """
    global _single_instance_lock
    mem = QSharedMemory("ClaudeBackup-SingleInstance-v1")
    if mem.attach():
        # 有别的实例占着 — 直接 detach 退出
        mem.detach()
        return False
    if not mem.create(1):
        # 创建失败 — 不阻塞，但记日志
        return True
    _single_instance_lock = mem
    return True


def _ensure_app() -> QApplication:
    global _app
    if _app is None:
        # 高 DPI / 无系统主题
        QApplication.setAttribute(Qt.AA_DontUseNativeDialogs, False)
        _set_windows_aumid()  # 必须在 QApplication 创建之前调
        _install_excepthook()  # 装在第一时间，覆盖整个 GUI 生命周期
        _app = QApplication.instance() or QApplication(sys.argv)
        _app.setApplicationName(i18n.APP_NAME)
        _app.setApplicationDisplayName(i18n.APP_NAME)
        _app.setOrganizationName("ClaudeBackup")
        _app.setOrganizationDomain("claudebackup.local")
        from .. import __version__
        _app.setApplicationVersion(__version__)
        _app.setWindowIcon(app_icon())
        cfg = config.load()
        _app.setStyleSheet(theme.stylesheet(cfg.theme))
    return _app


def _show_main_window(open_onboarding_if_needed: bool = True):
    global _window
    from .main_window import MainWindow
    if _window is None:
        _window = MainWindow()
        if _tray is not None:
            _window.set_notifier(_tray.notify)
    _window.show()
    _window.raise_()
    _window.activateWindow()

    if open_onboarding_if_needed:
        cfg = config.load()
        # 老用户升级补救：之前已经完成过引导（onboarding_completed=True）但
        # 新版 nas_root 字段还空——说明是从硬编码 Y:\ 时代升级。扫一组
        # 候选位置看哪里已有 .registry.json 直接写回 config，避免把人逼
        # 进 onboarding 再选一次（老数据看似消失的体感很差）。
        if cfg.onboarding_completed and not paths.is_nas_configured():
            _try_recover_legacy_nas_root()
            cfg = config.load()  # 重读

        reg = registry.load()
        needs_wizard = (
            not paths.is_nas_configured()
            or (not cfg.onboarding_completed and not reg.projects)
        )
        if needs_wizard:
            from .onboarding import OnboardingWizard
            w = OnboardingWizard(_window)
            w.exec()
            _window.refresh_projects()


def _try_recover_legacy_nas_root() -> None:
    """老用户从硬编码 Y:\\ 版本升级时，主动扫候选位置找回老数据。"""
    from pathlib import Path
    candidates = [
        Path(r"Y:\\"),
        Path("D:\\ClaudeBackup-Data"),
        paths._user_home() / "ClaudeBackup-Data",
    ]
    for cand in candidates:
        try:
            if (cand / "git-backups" / ".registry.json").exists():
                paths.set_nas_root(cand)
                return
        except OSError:
            continue


def _start_tray():
    global _tray
    from .tray import TrayController
    if _tray is None:
        _tray = TrayController(_app)
        _tray.request_open_window.connect(lambda: _show_main_window())
        _tray.request_quit.connect(_app.quit)
        _tray.request_show_logs.connect(_show_logs)
    return _tray


def _show_logs():
    if paths.LOG_DIR.exists():
        os.startfile(str(paths.LOG_DIR))


# ---------- 入口 ----------

def run_main() -> int:
    """启动主面板（同时启托盘）."""
    app = _ensure_app()
    if not _acquire_single_instance():
        # 已有实例在跑 — 直接弹提示后退出
        QMessageBox.information(
            None, i18n.APP_NAME,
            f"{i18n.APP_NAME} 已经在运行了。\n请从系统托盘打开主面板。",
        )
        return 0
    _start_tray()  # 必须先建 tray 再建 window，window 才能拿到 notifier
    _show_main_window()
    return app.exec()


def run_tray() -> int:
    """仅启动托盘 — 登录自启场景."""
    app = _ensure_app()
    if not _acquire_single_instance():
        # 已有实例占着托盘 — 静默退出（开机自启时一秒钟可能被触发两次）
        return 0
    app.setQuitOnLastWindowClosed(False)
    _start_tray()
    return app.exec()


def run_action(name: str, target_path: str) -> int:
    """右键菜单触发的动作 — 短任务，跑完退出."""
    app = _ensure_app()
    app.setQuitOnLastWindowClosed(True)
    p = Path(target_path).resolve()

    if name == "register":
        # 弹注册对话框
        _show_main_window(open_onboarding_if_needed=False)
        from .dialogs import RegisterProjectDialog
        dlg = RegisterProjectDialog(_window, default_path=str(p))
        if dlg.exec() == QDialog.Accepted:
            path, gh = dlg.values()
            try:
                core.init_project(path, github_url=gh)
                _window.refresh_projects()
                dialogs.info(_window, "添加成功", f"已为 {Path(path).name} 配好备份。")
            except Exception as e:  # noqa: BLE001
                dialogs.error(_window, "添加失败", str(e))
        return app.exec()

    if name == "backup":
        try:
            res = core.backup_project(p)
            dialogs.info(None, "备份完成",
                         f"已备份 {res.project_name}\n时间快照：{res.bundle_path}")
        except ValueError as e:
            dialogs.error(None, "项目未注册",
                          f"{e}\n\n请先在主面板里添加这个项目。")
        except Exception as e:  # noqa: BLE001
            dialogs.error(None, "备份失败", str(e))
        return 0

    if name == "release":
        _show_main_window(open_onboarding_if_needed=False)
        # 选中目标项目后让用户走主面板的发布流程
        reg = registry.load()
        entry = reg.find_by_path(p)
        if entry and _window:
            _window.select_project(entry)
            _window.action_release()
        else:
            dialogs.error(None, "项目未注册", "请先在主面板里添加这个项目。")
        return app.exec()

    if name == "list":
        _show_main_window(open_onboarding_if_needed=False)
        reg = registry.load()
        entry = reg.find_by_path(p)
        if entry and _window:
            _window.select_project(entry)
        return app.exec()

    if name == "compare":
        _show_main_window(open_onboarding_if_needed=False)
        reg = registry.load()
        entry = reg.find_by_path(p)
        if entry and _window:
            _window.select_project(entry)
            _window.action_compare()
        else:
            dialogs.error(None, "项目未注册", "请先在主面板里添加这个项目。")
        return app.exec()

    dialogs.error(None, "未知动作", f"未知动作：{name}")
    return 1
