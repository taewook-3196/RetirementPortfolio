"""모바일 웹 핵심 DOM과 기존 기능 연결을 보호하는 회귀 테스트."""

from web.app import home


def _html(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "public-anon-key")
    return home().body.decode("utf-8")


def test_mobile_viewport_safe_area_and_primary_summary(monkeypatch):
    html = _html(monkeypatch)

    assert "viewport-fit=cover" in html
    assert "env(safe-area-inset-top)" in html
    assert "env(safe-area-inset-bottom)" in html
    assert '"account-summary-grid"' in html
    assert '"총자산"' in html
    assert '"주식평가액"' in html
    assert '"예수금"' in html
    assert '"총손익"' in html
    assert 'id="portfolio-section"' in html


def test_core_mobile_workflows_and_chart_features_remain(monkeypatch):
    html = _html(monkeypatch)

    # 인증 복구와 Safari의 localStorage 기반 세션 유지
    assert "async function restoreLoginSession()" in html
    assert 'localStorage.getItem("access_token")' in html
    assert 'localStorage.getItem("refresh_token")' in html
    assert 'id="boot-screen"' in html

    # 계좌/보유종목/차트와 기간 선택
    assert "async function loadAccounts(" in html
    assert "function renderPositions(" in html
    assert "function renderAssetChart(" in html
    for period in ("1M", "3M", "6M", "1Y", "ALL"):
        assert f'key: "{period}"' in html
    assert "BUY ▲" in html
    assert "SELL ▼" in html

    # 거래, 입출금 및 수정/삭제 API 연결
    assert ' + "/transactions"' in html
    assert ' + "/cash-flows"' in html
    assert 'method:\n                                    "DELETE"' in html


def test_deep_link_and_accessible_position_interaction_remain(monkeypatch):
    html = _html(monkeypatch)

    assert "function openLinkedAssetChart()" in html
    assert 'params.get(\n                "account"' in html
    assert 'params.get(\n                "ticker"' in html
    assert "openLinkedAssetChart();" in html
    assert 'row.setAttribute(\n            "role",\n            "button"' in html
    assert 'event.key === "Enter"' in html
    assert 'event.key === " "' in html



def test_login_script_has_no_literal_newline_escape_between_statements(monkeypatch):
    html = _html(monkeypatch)

    assert (
        'const kakaoConnectButton = document.getElementById("kakao-connect-button");\\nconst'
        not in html
    )
    assert 'loginForm.addEventListener(' in html
    assert 'event.preventDefault();' in html



def test_generated_browser_script_has_no_statement_newline_escapes(monkeypatch):
    html = _html(monkeypatch)
    script = html.split("<script>", 1)[1].rsplit("</script>", 1)[0]

    # Literal backslash-n is valid inside JS strings, but not between statements.
    assert "{\\n            const detail" not in script
    assert ";\\nconst " not in script



def test_generated_admin_confirm_keeps_newlines_inside_js_string(monkeypatch):
    html = _html(monkeypatch)

    assert "로그인 계정을 삭제하시겠습니까?\\n\\n앱 로그인" in html
    assert "삭제하시겠습니까?\n\n앱 로그인" not in html



def test_kakao_connected_ui_offers_immediate_test_message(monkeypatch):
    html = _html(monkeypatch)

    assert 'id="kakao-test-button"' in html
    assert 'fetch("/api/kakao/test"' in html
    assert 'method: "POST"' in html
    assert 'kakaoTestButton.style.display = data.connected ? "block" : "none";' in html



def test_mobile_layout_stacks_forms_and_keeps_touch_targets(monkeypatch):
    html = _html(monkeypatch)

    assert "@media (max-width: 600px)" in html
    assert ".form-row {\n        grid-template-columns: 1fr;" in html
    assert ".small-button,\n    .asset-chart-period-button {\n        min-height: 44px;" in html
    assert ".transaction-actions {\n        flex-wrap: wrap;" in html
    assert ".transaction-actions button {\n        flex: 1 1 120px;" in html
