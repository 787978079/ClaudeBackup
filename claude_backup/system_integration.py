"""Windows 系统集成：右键菜单 / 登录自启 / 每日定时备份 — 检测 + 一键开关.

打包模式：用 D:\\Program Files\\ClaudeBackup\\ClaudeBackup.exe
源码模式：自动生成 dev-run.cmd 包装当前 Python + pyi-entry-cli.py，让 .ps1 脚本能注册成可执行入口.

注意：subprocess 调 schtasks/powershell 用 CREATE_NO_WINDOW，避免在 windowed exe
里每次弹一个黑窗口闪烁、阻塞用户感觉.
"""
from __future__ import annotations
import os
import subprocess
import sys
from pathlib import Path

# Windows 下 console exe 子进程默认会弹一个 cmd 窗口（即使 windowed 父进程）
# 这个 flag 让子进程完全无窗口
_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


INSTALLED_EXE = Path(r"D:\Program Files\ClaudeBackup\ClaudeBackup.exe")
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
DEV_RUNNER = PROJECT_ROOT / "dev-run.cmd"
CLI_ENTRY = PROJECT_ROOT / "pyi-entry-cli.py"

TASK_NAME = "ClaudeBackup-Daily"


def _ensure_dev_runner() -> Path:
    """开发模式包装器：生成 dev-run.cmd，让 .ps1 脚本把它当 exe 注册."""
    py = sys.executable
    content = (
        "@echo off\r\n"
        f'"{py}" "{CLI_ENTRY}" %*\r\n'
    )
    DEV_RUNNER.write_text(content, encoding="utf-8")
    return DEV_RUNNER


def resolve_exe() -> str:
    """返回当前可用的 exe 路径.

    优先级：
      1. 当前进程本身就是打包 exe（PyInstaller frozen）→ 返回 sys.executable
         （这样不论 setup.exe 把程序装到哪，系统集成都精准指向当前 exe）
      2. 默认安装路径有 exe → 返回它
      3. 否则源码模式 → 生成 dev-run.cmd 包装
    """
    if getattr(sys, 'frozen', False):
        return sys.executable
    if INSTALLED_EXE.exists():
        return str(INSTALLED_EXE)
    return str(_ensure_dev_runner())


def is_packaged() -> bool:
    return getattr(sys, 'frozen', False) or INSTALLED_EXE.exists()


# ---------- 右键菜单 ----------

def context_menu_installed() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Classes\Directory\shell\ClaudeBackup"):
            return True
    except OSError:
        return False


def install_context_menu() -> tuple[bool, str]:
    return _run_ps(SCRIPTS_DIR / "install-context-menu.ps1",
                   ["-Exe", resolve_exe()])


def uninstall_context_menu() -> tuple[bool, str]:
    return _run_ps(SCRIPTS_DIR / "uninstall-context-menu.ps1")


# ---------- 登录自启 ----------

def autostart_installed() -> bool:
    if sys.platform != "win32":
        return False
    startup = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    return (startup / "ClaudeBackup.lnk").exists()


def install_autostart() -> tuple[bool, str]:
    return _run_ps(SCRIPTS_DIR / "install-autostart.ps1",
                   ["-Exe", resolve_exe()])


def uninstall_autostart() -> tuple[bool, str]:
    return _run_ps(SCRIPTS_DIR / "uninstall-autostart.ps1")


# ---------- 每日定时备份 ----------

def task_scheduler_installed() -> bool:
    if sys.platform != "win32":
        return False
    try:
        r = subprocess.run(
            ["schtasks", "/Query", "/TN", TASK_NAME],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=10,
            creationflags=_NO_WINDOW,
        )
        return r.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def install_task_scheduler(time: str = "23:30") -> tuple[bool, str]:
    return _run_ps(SCRIPTS_DIR / "install-task-scheduler.ps1",
                   ["-Time", time, "-Exe", resolve_exe()])


def uninstall_task_scheduler() -> tuple[bool, str]:
    return _run_ps(SCRIPTS_DIR / "uninstall-task-scheduler.ps1")


# ---------- helper ----------

def _run_ps(script: Path, args: list[str] | None = None) -> tuple[bool, str]:
    if not script.exists():
        return False, f"脚本不存在: {script}"
    cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
           "-File", str(script)]
    if args:
        cmd.extend(args)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=60,
                           creationflags=_NO_WINDOW)
        ok = (r.returncode == 0)
        out = (r.stdout or "") + ("\n--- stderr ---\n" + r.stderr if r.stderr else "")
        return ok, out
    except Exception as e:  # noqa: BLE001
        return False, str(e)


def status_summary() -> dict[str, bool]:
    return {
        "context_menu": context_menu_installed(),
        "autostart": autostart_installed(),
        "task_scheduler": task_scheduler_installed(),
    }
