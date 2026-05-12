from claude_backup import config


def test_default_config_when_missing():
    cfg = config.load()
    assert cfg.schedule_time == "23:30"
    assert cfg.theme == "dark"
    assert cfg.onboarding_completed is False


def test_save_and_load_roundtrip():
    cfg = config.Config()
    cfg.schedule_time = "08:15"
    cfg.theme = "light"
    cfg.onboarding_completed = True
    config.save(cfg)

    loaded = config.load()
    assert loaded.schedule_time == "08:15"
    assert loaded.theme == "light"
    assert loaded.onboarding_completed is True


def test_unknown_keys_ignored(tmp_path):
    from claude_backup import paths
    paths.CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    paths.CONFIG_FILE.write_text(
        '{"schedule_time": "10:00", "future_field": "ignored"}',
        encoding="utf-8",
    )
    cfg = config.load()
    assert cfg.schedule_time == "10:00"
    assert not hasattr(cfg, "future_field")


def test_load_handles_bom(tmp_path, monkeypatch):
    """PowerShell Out-File -Encoding utf8 会写带 BOM 的 UTF-8，
    config.load() 必须能正常解析."""
    from claude_backup import config, paths
    bom = b"\xef\xbb\xbf"
    body = b'{"schedule_time": "08:30", "nas_root": "Y:\\\\"}'
    paths.CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    paths.CONFIG_FILE.write_bytes(bom + body)
    cfg = config.load()
    assert cfg.schedule_time == "08:30"
    assert cfg.nas_root == "Y:\\"
