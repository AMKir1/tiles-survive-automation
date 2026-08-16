# tests/unit/test_config.py
from tiles_survive_automation import config


def test_ensure_data_dirs_creates_expected_directories(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "TEMPLATES_DIR", tmp_path / "data" / "templates")
    monkeypatch.setattr(config, "SCREENSHOTS_DIR", tmp_path / "data" / "screenshots")
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path / "data" / "logs")

    config.ensure_data_dirs()

    assert (tmp_path / "data" / "templates").is_dir()
    assert (tmp_path / "data" / "screenshots").is_dir()
    assert (tmp_path / "data" / "logs").is_dir()
