import json
import os
import urllib.parse
import urllib.request


API_URL = "https://apps.bea.gov/api/data/"


def call_bea(params):
    params = {
        "UserID": os.environ["BEA_API_KEY"],
        "ResultFormat": "JSON",
        **params,
    }

    url = API_URL + "?" + urllib.parse.urlencode(params)

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "RetirementPortfolio/1.0",
        },
    )

    with urllib.request.urlopen(
        request,
        timeout=30,
    ) as response:
        return json.loads(
            response.read().decode("utf-8")
        )


# --------------------------------------------------
# 1. NIPA TableName 목록 조회
# --------------------------------------------------

result = call_bea(
    {
        "method": "GetParameterValues",
        "datasetname": "NIPA",
        "ParameterName": "TableName",
    }
)

results = result.get("BEAAPI", {}).get("Results", {})

if "Error" in results:
    raise RuntimeError(
        "BEA metadata error: "
        + json.dumps(
            results["Error"],
            ensure_ascii=False,
        )
    )

tables = results.get("ParamValue", [])

print("BEA TABLE COUNT:", len(tables))
print()
print("=== TABLE 2.8.4 SEARCH ===")

matches = []

for table in tables:
    raw = json.dumps(
        table,
        ensure_ascii=False,
    )

    normalized = raw.lower().replace(" ", "")

    if (
        "2.8.4" in normalized
        or "20804" in normalized
        or (
            "priceindexes" in normalized
            and "personalconsumption" in normalized
            and "monthly" in normalized
        )
    ):
        matches.append(table)
        print(
            json.dumps(
                table,
                ensure_ascii=False,
                indent=2,
            )
        )

print()
print("MATCH COUNT:", len(matches))


# --------------------------------------------------
# 2. 발견한 TableName으로 실제 데이터 조회
# --------------------------------------------------

if not matches:
    raise RuntimeError(
        "Table 2.8.4를 BEA metadata에서 찾지 못했습니다."
    )


table = matches[0]

table_name = (
    table.get("TableName")
    or table.get("Key")
    or table.get("ParamValue")
)


if not table_name:
    print()
    print("MATCHED TABLE RAW:")
    print(
        json.dumps(
            table,
            ensure_ascii=False,
            indent=2,
        )
    )

    raise RuntimeError(
        "TableName 필드를 확인할 수 없습니다."
    )


print()
print("SELECTED TABLE NAME:", table_name)


data_result = call_bea(
    {
        "method": "GetData",
        "datasetname": "NIPA",
        "TableName": table_name,
        "Frequency": "M",
        "Year": "2025,2026",
    }
)

data_results = (
    data_result
    .get("BEAAPI", {})
    .get("Results", {})
)

if "Error" in data_results:
    raise RuntimeError(
        "BEA data error: "
        + json.dumps(
            data_results["Error"],
            ensure_ascii=False,
        )
    )

rows = data_results.get("Data", [])

print("DATA ROW COUNT:", len(rows))


# --------------------------------------------------
# 3. 근원 PCE 행 검색
# --------------------------------------------------

print()
print("=== CORE PCE ROWS ===")

core_rows = []

for row in rows:
    description = str(
        row.get("LineDescription", "")
    ).lower()

    if (
        "excluding food and energy"
        in description
    ):
        core_rows.append(row)


print("CORE PCE ROW COUNT:", len(core_rows))


def period_key(row):
    return str(
        row.get("TimePeriod", "")
    )


core_rows.sort(
    key=period_key,
)


for row in core_rows[-15:]:
    print(
        row.get("TimePeriod"),
        "|",
        row.get("LineNumber"),
        "|",
        row.get("LineDescription"),
        "|",
        row.get("DataValue"),
    )
