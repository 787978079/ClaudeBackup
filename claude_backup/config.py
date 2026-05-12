"""用户配置 ~/.claude-backup/config.json — 用户级偏好."""
from __future__ import annotations
import json
from dataclasses import asdict, dataclass, field
from typing import Any

from . import paths


@dataclass
class Config:
    schedule_time: str = "23:30"          # 每日定时备份时间 HH:MM
    schedule_paused: bool = False         # 临时暂停定时
    autostart_tray: bool = True           # 登录自启托盘
    theme: str = "dark"                   # dark / light
    onboarding_completed: bool = False    # 是否走过新手引导
    show_tray_notifications: bool = True
    # 备份数据根目录（用户首次启动时由 onboarding 选择；空字符串 = 未配置）
    # 实际存储格式：项目镜像 git-backups/、bundle git-bundles/、目录快照 snapshots/
    nas_root: str = ""
    # ----- 保留策略（避免 NAS 爆盘） -----
    retention_keep_last_dir_snapshots: int = 30   # 每个项目最多保留 N 个目录快照
    retention_keep_last_bundles: int = 30         # 每个项目最多保留 N 个 git bundle
    # 0 = 不限；其它正整数 = 保留最近 N 个，超出按时间从老到新清
    # ----- mirror 排除规则 -----
    mirror_use_gitignore: bool = True             # 用项目 .gitignore 过滤
    mirror_extra_excludes: list[str] = field(default_factory=list)  # 用户自定义额外排除

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Config":
        valid = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in valid})


def load() -> Config:
    if not paths.CONFIG_FILE.exists():
        return Config()
    try:
        # utf-8-sig 兼容带 BOM 的 UTF-8——某些 Windows 工具（PowerShell
        # Out-File -Encoding utf8 默认）会加 BOM，json.loads 不能直接消化。
        return Config.from_dict(json.loads(paths.CONFIG_FILE.read_text("utf-8-sig")))
    except (json.JSONDecodeError, OSError):
        return Config()


def save(cfg: Config) -> None:
    paths.ensure_user_dirs()
    paths.CONFIG_FILE.write_text(
        json.dumps(cfg.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
