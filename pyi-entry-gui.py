"""PyInstaller GUI 入口 — windowed 模式（无控制台）.

支持参数：
  无参数           → 启动主面板
  tray             → 仅启动托盘
  ui-action <name> --path <p>  → 右键菜单触发的动作
  scheduled-daily  → Task Scheduler 调用（这个一般走 CLI exe，但保留兼容）
"""
import sys
from claude_backup.cli import main

if __name__ == "__main__":
    if len(sys.argv) == 1:
        sys.argv.append("gui")
    sys.exit(main())
