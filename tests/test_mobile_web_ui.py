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
    assert ".form-row,\n    .transaction-filter-grid {\n        grid-template-columns: 1fr;" in html
    assert ".small-button,\n    .asset-chart-period-button {\n        min-height: 44px;" in html
    assert ".transaction-actions {\n        flex-wrap: wrap;" in html
    assert ".transaction-actions button {\n        flex: 1 1 120px;" in html



def test_mobile_app_has_bottom_navigation_shell(monkeypatch):
    html = _html(monkeypatch)

    assert 'id="app-bottom-nav"' in html
    assert 'data-app-tab="home"' in html
    assert 'data-app-tab="portfolio"' in html
    assert 'data-app-tab="transactions"' in html
    assert 'data-app-tab="settings"' in html
    assert 'function setAppTab(tabName, options = {})' in html
    assert 'setAppTab("home", {scroll: false});' in html
    nav_css = html[html.index(".app-bottom-nav {"):html.index(".app-bottom-nav button {")]
    assert "display: grid;" in nav_css



def test_transaction_history_is_incrementally_revealed(monkeypatch):
    html = _html(monkeypatch)

    assert "const pageSize = 20;" in html
    assert "newestFirst.slice(0, visibleCount)" in html
    assert '"20건 더 보기"' in html
    assert '"최근 "' in html
    assert "visibleCount + pageSize" in html



def test_transactions_tab_is_independent_and_filterable(monkeypatch):
    html = _html(monkeypatch)

    assert 'id="transactions-section"' in html
    assert 'transactions: ["transactions-section"]' in html
    assert 'id="transaction-account-filter"' in html
    assert 'id="transaction-type-filter"' in html
    assert 'id="transaction-search-filter"' in html
    assert "async function loadTransactionTab(accounts, accessToken)" in html
    assert "transactionTabVisibleCount = 20;" in html
    assert '"20건 더 보기"' in html



def test_transactions_tab_has_expandable_entry_panel(monkeypatch):
    html = _html(monkeypatch)

    assert 'id="open-transaction-entry"' in html
    assert '＋ 거래 추가' in html
    assert 'id="transaction-entry-panel"' in html
    assert 'id="transaction-entry-account"' in html
    assert "async function showTransactionEntryForm()" in html
    assert 'transactionEntryPanel.hidden = false;' in html
    assert 'typeof options.onSaved === "function"' in html
    assert "await loadTransactionTab(transactionTabAccounts, transactionTabAccessToken);" in html



def test_transactions_tab_supports_edit_and_delete(monkeypatch):
    html = _html(monkeypatch)

    assert "function showTransactionEditor(" in html
    assert "options = {}" in html
    assert 'editButton.textContent = "수정";' in html
    assert 'deleteButton.textContent = "삭제";' in html
    assert "onCancel: () => renderTransactionTab()" in html
    assert 'await loadTransactionTab(transactionTabAccounts, transactionTabAccessToken);' in html



def test_portfolio_cards_delegate_trades_to_transactions_tab(monkeypatch):
    html = _html(monkeypatch)

    render_accounts = html[html.index("async function renderAccounts("):]
    render_accounts = render_accounts[:render_accounts.index("/*\n미국 종목 검색 / 등록")]
    assert '"매수 / 매도 입력"' not in render_accounts
    assert '"거래 내역"' not in render_accounts
    assert "매수 / 매도 관리는 하단" in render_accounts
    assert "async function refreshPortfolioAfterTransactionChange()" in html
    assert "await refreshPortfolioAfterTransactionChange();" in html



def test_cash_flows_are_managed_from_transactions_tab(monkeypatch):
    html = _html(monkeypatch)

    assert 'id="open-cash-flow-entry"' in html
    assert 'id="cash-flow-entry-panel"' in html
    assert 'id="all-cash-flows-list"' in html
    assert "async function loadCashFlowTab(accounts, accessToken)" in html
    assert "async function showCashFlowEntryForm()" in html
    assert 'typeof options.onChanged === "function"' in html
    assert 'typeof options.onSaved === "function"' in html

    render_accounts = html[html.index("async function renderAccounts("):]
    render_accounts = render_accounts[:render_accounts.index("/*\n미국 종목 검색 / 등록")]
    assert '"입금 / 출금 입력"' not in render_accounts
    assert '"입금 / 출금 내역"' not in render_accounts
    assert "입금 / 출금 관리는 하단" in render_accounts



def test_app_navigation_remains_available_above_phone_width(monkeypatch):
    html = _html(monkeypatch)

    nav_css = html[html.index(".app-bottom-nav {"):html.index(".app-bottom-nav button {")]
    assert "display: grid;" in nav_css
    assert "display: none;" not in nav_css
    assert 'portfolio: ["portfolio-section", "asset-search-section"]' in html
    assert 'transactions: ["transactions-section"]' in html
    assert 'settings: ["morning-report-settings-section"' in html
