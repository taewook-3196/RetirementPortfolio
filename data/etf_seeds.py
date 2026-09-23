"""
data/etf_seeds.py
국내 시장의 대표적이고 인기 있는 ETF 마스터 기본 시드 데이터.
- 퇴직연금/개인연금 인기 TDF
- 미국 및 글로벌 대표 지수 (S&P500, 나스닥100, 다우존스 등)
- 국내 대표 지수 (코스피200, 코스닥150 등)
- 배당 및 인컴 (배당다우존스, 리츠, 고배당 등)
- 주요 섹터 및 테마 (반도체, AI, 2차전지, 헬스케어 등)
- 채권 및 안전자산 (미국국채, 한국국채, 금, 달러 등)
"""

POPULAR_ETF_SEEDS = [
    # 1. TDF (Target Date Fund)
    {"ticker": "442560", "name": "RISE TDF2040액티브"},
    {"ticker": "442550", "name": "RISE TDF2030액티브"},
    {"ticker": "442570", "name": "RISE TDF2050액티브"},
    {"ticker": "442540", "name": "RISE TDF2020액티브"},
    {"ticker": "442580", "name": "PLUS 글로벌HBM반도체"},
    {"ticker": "439220", "name": "KODEX TDF2040액티브"},
    {"ticker": "439210", "name": "KODEX TDF2030액티브"},
    {"ticker": "439230", "name": "KODEX TDF2050액티브"},
    {"ticker": "439270", "name": "TIGER TDF2040액티브"},
    {"ticker": "439260", "name": "TIGER TDF2030액티브"},
    {"ticker": "439280", "name": "TIGER TDF2050액티브"},
    {"ticker": "442740", "name": "ACE TDF2040액티브"},
    {"ticker": "442750", "name": "ACE TDF2050액티브"},

    # 2. 미국 대표 지수
    {"ticker": "488500", "name": "TIGER 미국S&P500동일가중"},
    {"ticker": "494840", "name": "TIGER 미국나스닥TOP10"},
    {"ticker": "360750", "name": "TIGER 미국S&P500"},
    {"ticker": "133690", "name": "TIGER 미국나스닥100"},
    {"ticker": "379800", "name": "KODEX 미국S&P500TR"},
    {"ticker": "379810", "name": "KODEX 미국나스닥100TR"},
    {"ticker": "360200", "name": "ACE 미국S&P500"},
    {"ticker": "367380", "name": "ACE 미국나스닥100"},
    {"ticker": "448290", "name": "SOL 미국S&P500"},
    {"ticker": "488510", "name": "KODEX 미국S&P500동일가중"},

    # 3. 배당 및 인컴 (월배당, 배당다우존스)
    {"ticker": "446720", "name": "SOL 미국배당다우존스"},
    {"ticker": "458730", "name": "TIGER 미국배당다우존스"},
    {"ticker": "458760", "name": "ACE 미국배당다우존스"},
    {"ticker": "488520", "name": "KODEX 미국배당다우존스"},
    {"ticker": "441680", "name": "SOL 미국배당다우존스(H)"},
    {"ticker": "465580", "name": "TIGER 미국배당다우존스+3%프리미엄"},
    {"ticker": "465590", "name": "TIGER 미국배당다우존스+7%프리미엄"},
    {"ticker": "161510", "name": "ARIRANG 고배당주"},
    {"ticker": "104480", "name": "TIGER 200 커버드콜5%OTM"},
    {"ticker": "290080", "name": "KBSTAR 대형고배당10TR"},

    # 4. 국내 대표 지수
    {"ticker": "069500", "name": "KODEX 200"},
    {"ticker": "102110", "name": "TIGER 200"},
    {"ticker": "278530", "name": "KODEX 200TR"},
    {"ticker": "229200", "name": "KODEX 코스닥150"},
    {"ticker": "232080", "name": "TIGER 코스닥150"},
    {"ticker": "148020", "name": "KBSTAR 200"},
    {"ticker": "105190", "name": "ACE 200"},
    {"ticker": "292150", "name": "TIGER TOP10"},
    {"ticker": "091160", "name": "KODEX 반도체"},
    {"ticker": "091230", "name": "TIGER 반도체"},

    # 5. 글로벌 테크 / 반도체 / AI / 미래성장
    {"ticker": "381170", "name": "TIGER 미국테크TOP10 INDXX"},
    {"ticker": "381180", "name": "TIGER 미국필라델피아반도체나스닥"},
    {"ticker": "446770", "name": "ACE 미국필라델피아반도체나스닥"},
    {"ticker": "453330", "name": "RISE 미국S&P500(H)"},
    {"ticker": "453850", "name": "ACE 글로벌반도체TOP4 Plus SOLACTIVE"},
    {"ticker": "462900", "name": "KODEX 미국서학개미"},
    {"ticker": "465540", "name": "TIGER 글로벌AI&로보틱스INDXX"},
    {"ticker": "481060", "name": "KODEX 테슬라커버드콜채권혼합액티브"},

    # 6. 채권 및 금리 / 안전자산
    {"ticker": "453850", "name": "ACE 미국30년국채액티브(H)"},
    {"ticker": "476550", "name": "TIGER 미국30년국채프리미엄액티브(H)"},
    {"ticker": "449450", "name": "KODEX 미국종합채권SRI액티브(H)"},
    {"ticker": "305080", "name": "TIGER 미국채10년선물"},
    {"ticker": "329750", "name": "TIGER 미국채20년스트립액티브(H)"},
    {"ticker": "148070", "name": "KOSEF 국고채10년"},
    {"ticker": "153130", "name": "KODEX 단기채권"},
    {"ticker": "357870", "name": "TIGER CD금리투자KIS(합성)"},
    {"ticker": "423160", "name": "KODEX KOFR금리액티브(합성)"},
    {"ticker": "457490", "name": "TIGER 1년은행양도성예금증서액티브(합성)"},

    # 7. 원자재 / 금 / 리츠
    {"ticker": "411060", "name": "ACE KRX금현물"},
    {"ticker": "132030", "name": "KODEX 골드선물(H)"},
    {"ticker": "329200", "name": "TIGER 부동산인프라고배당"},
    {"ticker": "352560", "name": "TIGER 일본엔선물"},
    {"ticker": "261220", "name": "KODEX WTI원유선물(H)"},

    # 8. 국내 대표 개별 종목 (유가증권 KOSPI / 코스닥 KOSDAQ)
    {"ticker": "005930", "name": "삼성전자"},
    {"ticker": "005935", "name": "삼성전자우"},
    {"ticker": "000660", "name": "SK하이닉스"},
    {"ticker": "373220", "name": "LG에너지솔루션"},
    {"ticker": "207940", "name": "삼성바이오로직스"},
    {"ticker": "005380", "name": "현대차"},
    {"ticker": "000270", "name": "기아"},
    {"ticker": "068270", "name": "셀트리온"},
    {"ticker": "005490", "name": "POSCO홀딩스"},
    {"ticker": "035420", "name": "NAVER"},
    {"ticker": "035720", "name": "카카오"},
    {"ticker": "051910", "name": "LG화학"},
    {"ticker": "006400", "name": "삼성SDI"},
    {"ticker": "012330", "name": "현대모비스"},
    {"ticker": "105560", "name": "KB금융"},
    {"ticker": "055550", "name": "신한지주"},
    {"ticker": "086790", "name": "하나금융지주"},
    {"ticker": "323410", "name": "카카오뱅크"},
    {"ticker": "247540", "name": "에코프로비엠"},
    {"ticker": "086520", "name": "에코프로"},
    {"ticker": "196170", "name": "알테오젠"},
    {"ticker": "028300", "name": "HLB"},
    {"ticker": "041510", "name": "에스엠"},
    {"ticker": "259960", "name": "크래프톤"},
]
