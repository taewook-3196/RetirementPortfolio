import pytest


@pytest.fixture(autouse=True)
def isolate_report_output(monkeypatch, tmp_path):
    """Never let report-generation tests modify tracked export fixtures."""
    monkeypatch.setenv("REPORT_OUTPUT_DIR", str(tmp_path / "reports"))
