"""Sector classification consistency tests."""
from services.sector_taxonomy import GICS_US_SECTORS, us_sector_metadata
from services.sector_momentum_service import SECTORS
from services.sector_value_screening_service import UNIVERSE


def test_us_sector_ids_match_momentum_and_value_screening():
    expected = set(GICS_US_SECTORS)
    assert len(expected) == 11
    assert set(SECTORS["us"]) == expected
    assert set(UNIVERSE["us"]) == expected


def test_gics_codes_are_unique_and_labels_present():
    codes = [us_sector_metadata(key)["gics_sector_code"] for key in GICS_US_SECTORS]
    assert len(set(codes)) == 11
    for key in GICS_US_SECTORS:
        item = us_sector_metadata(key)
        assert item["taxonomy"] == "GICS"
        assert item["finviz_sector_label"]
        assert item["gics_sector_name"]
