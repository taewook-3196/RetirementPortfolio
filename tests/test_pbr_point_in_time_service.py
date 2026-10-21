from services.pbr_point_in_time_service import build_point_in_time_pbr


def test_filing_cannot_be_used_before_publication():
    result = build_point_in_time_pbr(
        [("2025-01-10", 100), ("2025-02-10", 120), ("2025-03-10", 150)],
        [("2025-02-01", 50), ("2025-03-01", 75)],
        as_of="2025-03-15",
    )
    assert result["observations"] == [("2025-02-10", 2.4), ("2025-03-10", 2.0)]


def test_stale_filing_is_not_reused():
    result = build_point_in_time_pbr(
        [("2025-01-10", 100)], [("2020-01-01", 50)], as_of="2025-02-01"
    )
    assert result["status"] == "withheld"
    assert result["count"] == 0


def test_future_filing_is_excluded():
    result = build_point_in_time_pbr(
        [("2025-01-10", 100)], [("2025-02-01", 50)], as_of="2025-01-31"
    )
    assert result["count"] == 0


def test_invalid_and_unpublished_values_are_ignored():
    result = build_point_in_time_pbr(
        [("2025-01-10", -100), ("2025-01-11", 100), ("2025-01-12", 110)],
        [("2025-01-01", 0), ("2025-01-10", 50)],
        as_of="2025-01-31",
    )
    assert result["observations"] == [("2025-01-11", 2.0), ("2025-01-12", 2.2)]
