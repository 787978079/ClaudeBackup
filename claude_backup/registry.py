"""Registry：NAS 上 .registry.json 的读写.

记录每个被备份的项目元数据：
- name: 显示名（默认是项目目录名）
- path: 本地路径
- nas_mirror: NAS bare 镜像绝对路径
- bundle_dir: 该项目的 bundle 根目录
- github_url: 可选，GitHub 远程 URL
- last_backup_hash: 最近一次定时/手动备份完成时的 HEAD（用于变化检测）
- last_backup_at: ISO timestamp
- created_at: 注册时间
"""
from __future__ import annotations
import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from . import paths


_LOCK = threading.Lock()


@dataclass
class ProjectEntry:
    name: str
    path: str
    nas_mirror: str
    bundle_dir: str
    github_url: str | None = None
    last_backup_hash: str | None = None
    last_backup_at: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ProjectEntry":
        valid = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in valid})


@dataclass
class Registry:
    projects: list[ProjectEntry] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"projects": [p.to_dict() for p in self.projects]}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Registry":
        ps = d.get("projects", []) or []
        return cls(projects=[ProjectEntry.from_dict(p) for p in ps])

    def find_by_path(self, path: str | Path) -> ProjectEntry | None:
        norm = _norm(path)
        for p in self.projects:
            if _norm(p.path) == norm:
                return p
        return None

    def find_by_name(self, name: str) -> ProjectEntry | None:
        for p in self.projects:
            if p.name == name:
                return p
        return None


def _norm(p: str | Path) -> str:
    return str(Path(p).expanduser().resolve()).lower()


def load() -> Registry:
    """读 registry；未配置 NAS 位置 / 文件不存在 都视为空 Registry.

    GUI 启动期会调到这里——那时用户可能还没走 onboarding，paths.NAS_*
    还没配，不能让一个 NasNotConfiguredError 把整个 GUI 拉黑。
    """
    if not paths.is_nas_configured():
        return Registry()
    paths.ensure_nas_dirs()
    f = paths.NAS_REGISTRY_FILE
    if not f.exists():
        return Registry()
    try:
        return Registry.from_dict(json.loads(f.read_text("utf-8-sig")))
    except (json.JSONDecodeError, OSError):
        return Registry()


def save(reg: Registry) -> None:
    """写 registry；未配置时抛 NasNotConfiguredError——写操作必须先配位置."""
    paths.ensure_nas_dirs()
    paths.NAS_REGISTRY_FILE.write_text(
        json.dumps(reg.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def upsert(entry: ProjectEntry) -> None:
    with _LOCK:
        reg = load()
        existing = reg.find_by_path(entry.path)
        if existing:
            for k, v in entry.to_dict().items():
                if k == "created_at" and existing.created_at:
                    continue
                setattr(existing, k, v)
        else:
            reg.projects.append(entry)
        save(reg)


def update_last_backup(path: str | Path, head_hash: str) -> None:
    with _LOCK:
        reg = load()
        e = reg.find_by_path(path)
        if e is None:
            return
        e.last_backup_hash = head_hash
        e.last_backup_at = datetime.now().isoformat(timespec="seconds")
        save(reg)


def remove(path: str | Path) -> bool:
    with _LOCK:
        reg = load()
        e = reg.find_by_path(path)
        if e is None:
            return False
        reg.projects.remove(e)
        save(reg)
        return True
