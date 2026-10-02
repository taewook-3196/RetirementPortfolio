from pathlib import Path

from core.config import load_config


def test_missing_config_uses_memory_defaults_and_environment(monkeypatch, tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("KAKAO_ACCESS_TOKEN", "test-kakao-token")

    config = load_config(config_path)

    assert not config_path.exists()
    assert config.morning_report.gemini_api_key == "test-gemini-key"
    assert config.morning_report.kakao_access_token == "test-kakao-token"
