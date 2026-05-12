"""变化检测：判断一个项目自上次备份以来是否有变化."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

from . import git_ops, registry


@dataclass
class ChangeStatus:
    has_changes: bool
    reason: str               # 给日志用的简短描述
    head_hash: str | None     # 当前 HEAD（无 commit 时 None）
    dirty: bool               # working tree 是否脏
    last_backup_hash: str | None


def detect(project_path: str | Path,
           reg: registry.Registry | None = None) -> ChangeStatus:
    """判断项目是否需要备份。"""
    reg = reg or registry.load()
    entry = reg.find_by_path(project_path)
    last = entry.last_backup_hash if entry else None

    if not git_ops.has_any_commit(project_path):
        return ChangeStatus(
            has_changes=False,
            reason="no commits in repo",
            head_hash=None,
            dirty=False,
            last_backup_hash=last,
        )

    head = git_ops.head_hash(project_path)
    dirty = git_ops.is_working_tree_dirty(project_path)

    if last is None:
        return ChangeStatus(
            has_changes=True,
            reason="never backed up",
            head_hash=head,
            dirty=dirty,
            last_backup_hash=None,
        )

    if head != last:
        return ChangeStatus(
            has_changes=True,
            reason=f"new commits since last backup ({last[:7]} → {head[:7]})",
            head_hash=head,
            dirty=dirty,
            last_backup_hash=last,
        )

    if dirty:
        return ChangeStatus(
            has_changes=True,
            reason="working tree has uncommitted changes",
            head_hash=head,
            dirty=True,
            last_backup_hash=last,
        )

    return ChangeStatus(
        has_changes=False,
        reason="no changes since last backup",
        head_hash=head,
        dirty=False,
        last_backup_hash=last,
    )
