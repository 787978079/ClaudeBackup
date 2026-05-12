"""命令行入口 — 被 Task Scheduler / 右键菜单 / Stop hook / 手动调用.

子命令：
  init <path> [--github URL] [--name NAME]
  backup <path> [--no-bundle] [--note TEXT]
  release <path> <version> [--desc TEXT] [--no-github]
  compare <path> <ref1> <ref2>
  list <path>
  scheduled-daily
  hook-push                            # Stop hook 调用：当前 cwd 推 nas（容错）
  gui                                  # 启动 GUI（默认行为）
  tray                                 # 仅启动托盘
  ui-action <name> --path <p>          # 右键菜单/托盘等触发的 GUI 动作

退出码：0=成功，1=参数错误/通用失败，2=未注册项目
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

from . import __version__, core, git_ops, logger, paths, registry


def _print_kv(d: dict[str, object]) -> None:
    for k, v in d.items():
        print(f"  {k}: {v}")


# ---------- 子命令 ----------

def cmd_init(args: argparse.Namespace) -> int:
    res = core.init_project(args.path, github_url=args.github, display_name=args.name)
    print(f"已注册项目: {res.project.name}")
    _print_kv({
        "本地路径": res.project.path,
        "NAS 镜像": res.project.nas_mirror,
        "Bundle 目录": res.project.bundle_dir,
        "GitHub": res.project.github_url or "(未配置)",
        "新建镜像": res.created_mirror,
        "新建 bundle 目录": res.created_bundle_dir,
        "新加 nas remote": res.added_remote,
        "新加 GitHub remote": res.added_github_remote,
    })
    return 0


def cmd_backup(args: argparse.Namespace) -> int:
    try:
        res = core.backup_project(
            args.path,
            make_bundle=not args.no_bundle,
            skip_if_no_change=False,
            commit_dirty=False,
            note=args.note,
        )
    except ValueError as e:
        print(f"错误: {e}", file=sys.stderr)
        return 2
    print(f"项目 {res.project_name} 备份完成")
    _print_kv({
        "推 NAS": res.pushed_to_nas,
        "时间快照": res.bundle_path or "(跳过)",
        "HEAD": res.new_head[:12] if res.new_head else "(无 commit)",
    })
    return 0


def cmd_release(args: argparse.Namespace) -> int:
    res = core.release_project(
        args.path, args.version,
        description=args.desc or "",
        push_github=not args.no_github,
    )
    print(f"项目 {res.project_name} 已发布版本 {res.version}")
    _print_kv({
        "新建 tag": res.tag_created,
        "推 NAS": res.pushed_to_nas,
        "推 GitHub": res.pushed_to_github,
        "归档 bundle": res.bundle_path,
    })
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    res = core.compare_refs(args.path, args.ref1, args.ref2)
    print(f"对比 {res.ref1} → {res.ref2}")
    print(res.summary)
    print(f"\n变更文件 {len(res.files)} 个:")
    for status, fname in res.files:
        print(f"  [{status}] {fname}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    res = core.list_backup_points(args.path)
    print(f"{res.project_name} — 共 {len(res.points)} 个备份点")
    for p in res.points:
        when = p.when.strftime("%Y-%m-%d %H:%M") if p.when else "      -      "
        print(f"  [{p.kind:8s}] {when}  {p.label:14s}  {p.detail}")
    return 0


def cmd_scheduled_daily(args: argparse.Namespace) -> int:
    logger.init(verbose=args.verbose)
    res = core.scheduled_daily()
    print(f"开始: {res.started_at:%Y-%m-%d %H:%M:%S}")
    print(f"结束: {res.finished_at:%Y-%m-%d %H:%M:%S}")
    print(f"成功 {len(res.backed_up)}: {', '.join(res.backed_up) or '(无)'}")
    print(f"跳过 {len(res.skipped)}:")
    for n, r in res.skipped:
        print(f"  - {n}: {r}")
    if res.failed:
        print(f"失败 {len(res.failed)}:")
        for n, r in res.failed:
            print(f"  - {n}: {r}")
    return 0 if not res.failed else 1


def cmd_hook_push(args: argparse.Namespace) -> int:
    """Stop hook 备用入口（PowerShell 也可以直接调 git push，这里给 Python 路径备选）.

    永远 exit 0，避免阻塞 Claude. 错误写入 hook.log.
    """
    cwd = Path.cwd()
    try:
        if not git_ops.is_git_repo(cwd):
            return 0
        if not git_ops.has_remote(cwd, paths.NAS_REMOTE_NAME):
            return 0
        if not git_ops.has_any_commit(cwd):
            return 0
        git_ops.push_all(cwd, paths.NAS_REMOTE_NAME)
        logger.hook_log(f"pushed {cwd} to nas", "INFO")
    except Exception as e:  # noqa: BLE001
        logger.hook_log(f"push failed at {cwd}: {e}", "ERROR")
    return 0


def cmd_gui(args: argparse.Namespace) -> int:
    try:
        from .gui.app import run_main
    except ImportError as e:
        print(f"GUI 启动失败（缺少 PySide6）: {e}", file=sys.stderr)
        return 1
    return run_main()


def cmd_tray(args: argparse.Namespace) -> int:
    try:
        from .gui.app import run_tray
    except ImportError as e:
        print(f"托盘启动失败（缺少 PySide6）: {e}", file=sys.stderr)
        return 1
    return run_tray()


def cmd_ui_action(args: argparse.Namespace) -> int:
    """右键菜单等触发的 GUI 动作 — 把 GUI 拉起来并预填动作上下文."""
    try:
        from .gui.app import run_action
    except ImportError as e:
        print(f"GUI 启动失败: {e}", file=sys.stderr)
        return 1
    return run_action(args.name, args.path)


# ---------- 主入口 ----------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="claude-backup",
        description="ClaudeBackup — Git 三层备份 (Stop hook + NAS + GitHub release)",
    )
    p.add_argument("--version", action="version", version=__version__)
    p.add_argument("-v", "--verbose", action="store_true", help="控制台输出 DEBUG 日志")
    sub = p.add_subparsers(dest="cmd")

    sp = sub.add_parser("init", help="注册一个项目为备份对象")
    sp.add_argument("path", help="项目路径")
    sp.add_argument("--github", help="GitHub 远程 URL（可选）")
    sp.add_argument("--name", help="显示名（默认目录名）")
    sp.set_defaults(func=cmd_init)

    sp = sub.add_parser("backup", help="立即对项目做一次快照")
    sp.add_argument("path")
    sp.add_argument("--no-bundle", action="store_true", help="只推 NAS，不生成 bundle")
    sp.add_argument("--note", help="备注（写入日志）")
    sp.set_defaults(func=cmd_backup)

    sp = sub.add_parser("release", help="打 tag 并发布到 GitHub")
    sp.add_argument("path")
    sp.add_argument("version", help="版本号，例如 v1.0.0")
    sp.add_argument("--desc", help="发布描述")
    sp.add_argument("--no-github", action="store_true", help="跳过 GitHub 推送")
    sp.set_defaults(func=cmd_release)

    sp = sub.add_parser("compare", help="对比两个备份点")
    sp.add_argument("path")
    sp.add_argument("ref1")
    sp.add_argument("ref2")
    sp.set_defaults(func=cmd_compare)

    sp = sub.add_parser("list", help="列出所有备份点")
    sp.add_argument("path")
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("scheduled-daily", help="Task Scheduler 调用：变化检测 + 全量备份")
    sp.set_defaults(func=cmd_scheduled_daily)

    sp = sub.add_parser("hook-push", help="Stop hook 调用：当前 cwd 推 NAS（容错）")
    sp.set_defaults(func=cmd_hook_push)

    sp = sub.add_parser("gui", help="启动 GUI 主面板（默认行为）")
    sp.set_defaults(func=cmd_gui)

    sp = sub.add_parser("tray", help="仅启动系统托盘（不弹主窗）")
    sp.set_defaults(func=cmd_tray)

    sp = sub.add_parser("ui-action", help="右键菜单触发的 GUI 动作")
    sp.add_argument("name", help="动作名: register / backup / release / list / compare")
    sp.add_argument("--path", required=True)
    sp.set_defaults(func=cmd_ui_action)

    return p


def main(argv: list[str] | None = None) -> int:
    logger.init()
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "cmd", None):
        # 默认行为：拉 GUI
        return cmd_gui(argparse.Namespace())
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
