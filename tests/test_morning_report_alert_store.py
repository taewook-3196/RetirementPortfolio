import os
import time

import pytest

from scripts.morning_report_alert_store import claim_alert, claim_alert_with_expiry, release_alert


def test_first_claim_is_unique(tmp_path):
    key = "a" * 24
    assert claim_alert(key, tmp_path)
    assert not claim_alert(key, tmp_path)
    assert (tmp_path / (key + ".claim")).read_text().strip() == key


def test_claims_are_scoped_by_key(tmp_path):
    assert claim_alert("a" * 24, tmp_path)
    assert claim_alert("b" * 24, tmp_path)


def test_failed_send_can_release_claim(tmp_path):
    key = "c" * 24
    assert claim_alert(key, tmp_path)
    release_alert(key, tmp_path)
    assert claim_alert(key, tmp_path)


def test_invalid_keys_cannot_escape_directory(tmp_path):
    with pytest.raises(ValueError):
        claim_alert("../bad", tmp_path)
    with pytest.raises(ValueError):
        release_alert("../bad", tmp_path)


def test_recent_claim_is_not_repeated(tmp_path):
    key = "d" * 24
    assert claim_alert(key, tmp_path)
    assert not claim_alert_with_expiry(key, tmp_path, stale_after_seconds=60)


def test_stale_claim_requires_manual_review(tmp_path):
    key = "e" * 24
    assert claim_alert(key, tmp_path)
    target = tmp_path / (key + ".claim")
    os.utime(target, (time.time() - 7200, time.time() - 7200))
    with pytest.raises(RuntimeError, match="manual review"):
        claim_alert_with_expiry(key, tmp_path, stale_after_seconds=3600)
    assert target.exists()


def test_stale_threshold_must_be_positive(tmp_path):
    with pytest.raises(ValueError):
        claim_alert_with_expiry("f" * 24, tmp_path, stale_after_seconds=0)
