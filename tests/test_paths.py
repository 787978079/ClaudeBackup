from pathlib import Path

import pytest

from claude_backup import paths


def test_nas_root_from_env(tmp_path: Path):
    assert str(paths.NAS_ROOT).startswith(str(tmp_path))
    assert paths.NAS_BACKUPS_DIR.parent == paths.NAS_ROOT
    assert paths.NAS_BUNDLES_DIR.parent == paths.NAS_ROOT


def test_ensure_dirs(tmp_path: Path):
    paths.ensure_user_dirs()
    paths.ensure_nas_dirs()
    assert paths.LOG_DIR.exists()
    assert paths.CACHE_DIR.exists()
    assert paths.NAS_BACKUPS_DIR.exists()
    assert paths.NAS_BUNDLES_DIR.exists()


def test_is_nas_configured_with_env(tmp_path: Path):
    # conftest 已经 setenv CLAUDE_BACKUP_NAS_ROOT 到 tmp_path/nas
    assert paths.is_nas_configured() is True


def test_is_nas_configured_without_anything(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """env 和 config.nas_root 都为空 → 未配置."""
    monkeypatch.delenv("CLAUDE_BACKUP_NAS_ROOT", raising=False)
    paths.reload_cache()
    # config.nas_root 默认就是空字符串，import config 应给空
    from claude_backup import config as cfg_mod
    cfg = cfg_mod.load()
    assert cfg.nas_root == ""
    # 这时 is_nas_configured 应为 False
    assert paths.is_nas_configured() is False
    # 访问 NAS_BACKUPS_DIR 应该 raise
    with pytest.raises(paths.NasNotConfiguredError):
        _ = paths.NAS_BACKUPS_DIR


def test_set_nas_root_persists(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """set_nas_root 写 config + 让 reload_cache 后能立刻拿到新路径."""
    monkeypatch.delenv("CLAUDE_BACKUP_NAS_ROOT", raising=False)
    new_root = tmp_path / "user_chose_this"
    paths.set_nas_root(new_root)
    paths.reload_cache()
    # config 里应该写入了
    from claude_backup import config as cfg_mod
    assert cfg_mod.load().nas_root == str(new_root)
    # 路径解析也用新值
    assert paths.NAS_ROOT == new_root
    assert paths.NAS_BACKUPS_DIR == new_root / "git-backups"


def test_env_overrides_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """即使 config 写了 X，env 优先用 Y."""
    config_path = tmp_path / "from_config"
    env_path = tmp_path / "from_env"
    paths.set_nas_root(config_path)
    monkeypatch.setenv("CLAUDE_BACKUP_NAS_ROOT", str(env_path))
    paths.reload_cache()
    # env 优先
    assert paths.NAS_ROOT == env_path


def test_nas_available_when_unconfigured(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("CLAUDE_BACKUP_NAS_ROOT", raising=False)
    paths.reload_cache()
    from claude_backup import config as cfg_mod
    # 确保 nas_root 是空（autouse fixture 把 USERPROFILE 隔离了，新 config 默认空）
    cfg = cfg_mod.load()
    if cfg.nas_root:
        cfg.nas_root = ""
        cfg_mod.save(cfg)
    paths.reload_cache()
    assert paths.nas_available() is False


def test_ensure_nas_dirs_silent_when_unconfigured(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("CLAUDE_BACKUP_NAS_ROOT", raising=False)
    paths.reload_cache()
    # 不应抛异常
    paths.ensure_nas_dirs()


# ---------- onboarding.detect_git ----------

def test_detect_git_when_available():
    """假设当前开发机有 git 装着（CI 环境也都是有 git 的）."""
    from claude_backup.gui.onboarding import detect_git
    ok, info = detect_git()
    assert ok is True
    assert "git version" in info.lower()


def test_detect_git_when_missing(monkeypatch):
    """模拟 PATH 里没 git——detect_git 应平静返回 (False, msg)，不抛."""
    import shutil
    monkeypatch.setattr(shutil, "which", lambda _: None)
    from claude_backup.gui.onboarding import detect_git
    ok, msg = detect_git()
    assert ok is False
    assert "git" in msg.lower() or "PATH" in msg


def test_recover_legacy_nas_root(monkeypatch, tmp_path):
    """老用户升级：config 已有 onboarding_completed=True 但 nas_root 空。
    若候选路径下存在 .registry.json，应自动写入 config."""
    from claude_backup.gui import app as app_mod
    monkeypatch.delenv("CLAUDE_BACKUP_NAS_ROOT", raising=False)
    paths.reload_cache()

    # 模拟一个老仓库
    legacy = tmp_path / "legacy_nas"
    (legacy / "git-backups").mkdir(parents=True)
    (legacy / "git-backups" / ".registry.json").write_text('{"projects":[]}', encoding="utf-8")

    # 把候选列表替换成只含我们的 legacy 路径
    monkeypatch.setattr(app_mod, "_try_recover_legacy_nas_root",
                        lambda: paths.set_nas_root(legacy))
    app_mod._try_recover_legacy_nas_root()
    paths.reload_cache()

    assert paths.is_nas_configured()
    assert paths.NAS_ROOT == legacy
