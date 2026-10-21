from services.sec_pilot_companies import SEC_PILOT_COMPANIES, pilot_companyfacts_urls


def test_pilot_ciks_are_unique_ten_digit_values():
    ciks = [company["cik"] for company in SEC_PILOT_COMPANIES.values()]
    assert len(ciks) == len(set(ciks)) == 3
    assert all(len(cik) == 10 and cik.isdigit() for cik in ciks)


def test_companyfacts_urls_use_sec_official_domain():
    urls = pilot_companyfacts_urls()
    assert set(urls) == {"AAPL", "MSFT", "JNJ"}
    assert urls["AAPL"] == "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json"
    assert all(url.startswith("https://data.sec.gov/api/xbrl/companyfacts/CIK") for url in urls.values())
