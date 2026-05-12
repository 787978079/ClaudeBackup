"""PyInstaller CLI 入口 — console 模式（有控制台输出）.

主要给 Task Scheduler / Stop hook 等后台调用用。
"""
import sys
from claude_backup.cli import main

if __name__ == "__main__":
    sys.exit(main())
