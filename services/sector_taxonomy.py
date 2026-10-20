"""Canonical US sector taxonomy with Finviz display-name compatibility.

GICS is the reference framework. These labels are aliases only; they do
not assert that a third-party provider's company-level classifications
are licensed or identical to official GICS classifications.
"""
GICS_US_SECTORS = {
    "energy": ("10", "Energy", "에너지", "Energy"),
    "materials": ("15", "Materials", "소재", "Basic Materials"),
    "industrials": ("20", "Industrials", "산업재", "Industrials"),
    "consumer_discretionary": ("25", "Consumer Discretionary", "경기소비재", "Consumer Cyclical"),
    "consumer_staples": ("30", "Consumer Staples", "필수소비재", "Consumer Defensive"),
    "healthcare": ("35", "Health Care", "헬스케어", "Healthcare"),
    "financials": ("40", "Financials", "금융", "Financial"),
    "technology": ("45", "Information Technology", "정보기술", "Technology"),
    "communication": ("50", "Communication Services", "커뮤니케이션", "Communication Services"),
    "utilities": ("55", "Utilities", "유틸리티", "Utilities"),
    "real_estate": ("60", "Real Estate", "부동산", "Real Estate"),
}


def us_sector_metadata(sector_id):
    code, english, korean, finviz = GICS_US_SECTORS[sector_id]
    return {
        "taxonomy": "GICS",
        "gics_sector_code": code,
        "gics_sector_name": english,
        "sector_name_ko": korean,
        "finviz_sector_label": finviz,
        "classification_level": "sector",
    }
