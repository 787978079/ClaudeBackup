from pathlib import Path

from claude_backup import registry


def _entry(path: Path, name: str = "demo") -> registry.ProjectEntry:
    return registry.ProjectEntry(
        name=name,
        path=str(path),
        nas_mirror=str(path) + ".git",
        bundle_dir=str(path) + "_bundles",
    )


def test_empty_registry_when_missing():
    reg = registry.load()
    assert reg.projects == []


def test_upsert_and_find(tmp_path: Path):
    e = _entry(tmp_path / "demo")
    registry.upsert(e)
    reg = registry.load()
    assert len(reg.projects) == 1
    found = reg.find_by_path(tmp_path / "demo")
    assert found and found.name == "demo"


def test_upsert_updates_existing(tmp_path: Path):
    e = _entry(tmp_path / "p")
    registry.upsert(e)
    e2 = _entry(tmp_path / "p", name="renamed")
    e2.github_url = "https://github.com/x/y"
    registry.upsert(e2)
    reg = registry.load()
    assert len(reg.projects) == 1
    assert reg.projects[0].name == "renamed"
    assert reg.projects[0].github_url == "https://github.com/x/y"


def test_update_last_backup(tmp_path: Path):
    e = _entry(tmp_path / "p")
    registry.upsert(e)
    registry.update_last_backup(tmp_path / "p", "abc123")
    reg = registry.load()
    assert reg.projects[0].last_backup_hash == "abc123"
    assert reg.projects[0].last_backup_at is not None


def test_remove(tmp_path: Path):
    e = _entry(tmp_path / "p")
    registry.upsert(e)
    assert registry.remove(tmp_path / "p") is True
    assert registry.load().projects == []
    assert registry.remove(tmp_path / "p") is False


def test_load_returns_empty_when_nas_not_configured(monkeypatch):
    """GUI 启动期：用户还没走 onboarding 选备份位置 → registry.load 应该返回空，
    不能抛 NasNotConfiguredError 让 MainWindow.__init__ 崩."""
    from claude_backup import paths, registry
    monkeypatch.delenv("CLAUDE_BACKUP_NAS_ROOT", raising=False)
    paths.reload_cache()
    # 把 config.nas_root 也清掉（autouse fixture 设过 USERPROFILE 隔离）
    from claude_backup import config as cfg_mod
    cfg = cfg_mod.load()
    if cfg.nas_root:
        cfg.nas_root = ""
        cfg_mod.save(cfg)
    paths.reload_cache()
    assert paths.is_nas_configured() is False
    # load 应平静返回空 Registry
    reg = registry.load()
    assert reg.projects == []
