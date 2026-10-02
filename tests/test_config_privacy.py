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


def test_kakao_token_helper_has_no_hardcoded_rest_key():
    """Kakao OAuth helper must never ship a literal REST API credential."""
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "scripts" / "issue_kakao_tokens.py").read_text(encoding="utf-8")
    assert "10dd3be26f85a71a154f11220a776fcb" not in source
    assert 'print(f"• Access Token : {access}")' not in source
    assert 'print(f"• Refresh Token: {refresh}")' not in source
