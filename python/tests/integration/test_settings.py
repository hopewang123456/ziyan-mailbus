"""运行配置：环境变量覆盖必须落到 Settings。"""

from __future__ import annotations

from mailbus.bootstrap.settings import Settings


def test_from_env_honours_data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("MAILBUS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MAILBUS_DISPATCH_MAX_ATTEMPTS", "5")

    settings = Settings.from_env()

    assert settings.data_dir == tmp_path
    assert settings.db_path == tmp_path / "mailbus.db"
    assert settings.dispatch_max_attempts == 5
