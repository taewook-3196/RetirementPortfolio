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
    assert 'sessionStorage.setItem(' not in html
    assert 'sessionStorage.getItem(' not in html
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
    assert 'method: "DELETE"' in html or 'method:\n                                    "DELETE"' in html


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

    assert "회원 계정을 삭제하시겠습니까?\\n\\n앱 로그인" in html
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
    assert "async function loadTransactionTab(accounts, accessToken, options = {})" in html
    assert "if (!options.preserveVisibleCount)" in html
    assert "{preserveVisibleCount: true}" in html
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
    assert 'settings: ["settings-navigation-section", "account-management-section", "morning-report-settings-section"' in html



def test_account_settings_and_deletion_live_in_settings_tab(monkeypatch):
    html = _html(monkeypatch)

    assert 'id="account-management-section"' in html
    assert 'id="account-management-list"' in html
    assert 'settings: ["settings-navigation-section", "account-management-section"' in html
    assert "async function renderAccountManagement(accounts, accessToken)" in html

    render_accounts = html[html.index("async function renderAccounts("):]
    assert 'card.appendChild(\n            createAccountEditor(' not in render_accounts
    assert 'deleteAccountButton.textContent' not in render_accounts
    assert 'card.appendChild(createAccountEditor(account, accessToken));' in html
    assert 'deleteButton.textContent = "계좌 삭제";' in html



def test_new_account_creation_lives_in_settings_account_management(monkeypatch):
    html = _html(monkeypatch)

    assert 'id="account-creator"' in html
    assert "async function renderAccountCreator(accounts, accessToken)" in html
    assert 'createHeader.textContent =\n        "+ 새 계좌 추가";' in html
    assert "await renderAccountCreator(accounts, accessToken);" in html

    render_accounts = html[html.index("async function renderAccounts("):]
    assert '"+ 새 계좌 추가"' not in render_accounts
    assert '"새 계좌 입력"' not in render_accounts



def test_admin_has_separate_member_management_tab(monkeypatch):
    html = _html(monkeypatch)

    assert 'id="member-management-tab-button"' in html
    assert 'data-app-tab="members" hidden>회원관리</button>' in html
    assert 'members: ["admin-section"]' in html
    assert 'settings: ["settings-navigation-section", "account-management-section", "morning-report-settings-section", "kakao-settings-section", "investment-settings-section"]' in html
    assert "memberManagementTabButton.hidden = false;" in html
    assert "memberManagementTabButton.hidden = true;" in html
    assert "repeat(auto-fit, minmax(64px, 1fr))" in html



def test_member_management_tab_fails_closed_when_admin_check_fails(monkeypatch):
    html = _html(monkeypatch)

    admin_loader = html[html.index("async function loadAdminPanel(accessToken)"):html.index("adminSignupEnabled.addEventListener")]
    assert "if (!statusResponse.ok)" in admin_loader
    assert "memberManagementTabButton.hidden = true;" in admin_loader
    assert "adminSection.hidden = true;" in admin_loader
    assert 'if (activeAppTab === "members") setAppTab("home", {scroll: false});' in admin_loader



def test_transaction_entry_error_state_resets_before_reuse(monkeypatch):
    html = _html(monkeypatch)

    entry = html[html.index("async function showTransactionEntryForm()"):html.index("const openCashFlowEntry")]
    assert 'transactionEntryForm.className = "";' in entry
    assert 'transactionEntryForm.className = "error";' in entry
    close_handler = entry[entry.index('closeTransactionEntry.addEventListener("click"'):]
    assert 'transactionEntryForm.className = "";' in close_handler



def test_chart_offsets_overlapping_transaction_markers(monkeypatch):
    html = _html(monkeypatch)

    chart = html[html.index("function renderAssetChart("):html.index("function createAccountEditor(")]
    assert "const transactionMarkerCounts = new Map();" in chart
    assert "const markerGroupKey =" in chart
    assert "const markerOffsetStep = 11;" in chart
    assert "Math.ceil(markerGroupIndex / 2)" in chart
    assert "baseX + markerOffsetDirection * markerOffsetLevel * markerOffsetStep" in chart



def test_account_edit_refreshes_all_account_dependent_tabs(monkeypatch):
    html = _html(monkeypatch)

    editor = html[html.index("function createAccountEditor("):html.index("async function renderAccountManagement")]
    assert "await renderAccounts(" in editor
    assert "await renderAccountCreator(" in editor
    assert "await renderAccountManagement(" in editor
    assert "await loadTransactionTab(" in editor



def test_settings_tab_uses_compact_subnavigation(monkeypatch):
    html = _html(monkeypatch)

    assert 'id="settings-navigation-section"' in html
    assert 'id="settings-subnav"' in html
    for panel in ("accounts", "report", "kakao", "strategy"):
        assert f'data-settings-panel="{panel}"' in html
    assert 'function setSettingsPanel(panelName, options = {})' in html
    assert 'function applySettingsPanel()' in html
    assert 'section.hidden = !settingsActive || panelName !== activeSettingsPanel;' in html
    assert '.settings-subnav {\n        grid-template-columns: repeat(2, minmax(0, 1fr));' in html



def test_cash_flow_history_is_incrementally_revealed(monkeypatch):
    html = _html(monkeypatch)

    cash_flows = html[html.index("function renderCashFlows("):html.index("async function refreshPortfolioData(")]
    assert "const pageSize = 20;" in cash_flows
    assert "newestFirst.slice(0, visibleCount)" in cash_flows
    assert '"20건 더 보기"' in cash_flows
    assert '"최근 " + visibleCashFlows.length + "건 / 전체 " + newestFirst.length + "건"' in cash_flows
    assert "visibleCount + pageSize" in cash_flows



def test_account_filter_applies_to_cash_flow_history(monkeypatch):
    html = _html(monkeypatch)

    cash_tab = html[html.index("async function loadCashFlowTab("):html.index("async function showCashFlowEntryForm(")]
    assert "const selectedAccountId = transactionAccountFilter.value;" in cash_tab
    assert "String(group.account.id) !== selectedAccountId" in cash_tab
    assert 'transactionAccountFilter.addEventListener("change", async () =>' in html
    assert "await loadCashFlowTab(transactionTabAccounts, transactionTabAccessToken);" in html



def test_bottom_navigation_supports_admin_fifth_tab(monkeypatch):
    html = _html(monkeypatch)

    assert "grid-auto-flow: column;" in html
    assert "grid-auto-columns: minmax(0, 1fr);" in html
    assert "grid-template-columns: repeat(4, 1fr);" not in html
    assert 'data-app-tab="members"' in html



def test_settings_has_logout_that_clears_session_and_app_state(monkeypatch):
    html = _html(monkeypatch)

    assert 'id="logout-button"' in html
    assert 'logoutButton.addEventListener("click", () =>' in html
    assert "clearAuthTokens();" in html
    assert "memberManagementTabButton.hidden = true;" in html
    assert 'appArea.style.display = "none";' in html
    assert 'loginCard.style.display = "block";' in html
    assert "loginForm.reset();" in html



def test_logout_clears_previous_users_rendered_data(monkeypatch):
    html = _html(monkeypatch)

    assert "transactionTabRows = [];" in html
    assert 'transactionAccountFilter.innerHTML = \'<option value="">전체 계좌</option>\';' in html
    assert 'transactionSearchFilter.value = "";' in html
    assert 'allTransactionsList.innerHTML = "";' in html
    assert 'allCashFlowsList.innerHTML = "";' in html
    assert 'accountsList.innerHTML = "";' in html
    assert 'accountCreator.innerHTML = "";' in html
    assert 'accountManagementList.innerHTML = "";' in html


def test_transaction_and_cash_flow_entry_panels_are_mutually_exclusive(monkeypatch):
    html = _html(monkeypatch)

    assert 'cashFlowEntryPanel.hidden = true;' in html
    assert 'cashFlowEntryAccount.value = "";' in html
    assert 'transactionEntryPanel.hidden = true;' in html
    assert 'transactionEntryAccount.value = "";' in html


def test_entry_panels_prefill_filtered_or_single_account(monkeypatch):
    html = _html(monkeypatch)

    assert 'const preferredAccountId = transactionAccountFilter.value' in html
    assert 'transactionTabAccounts.length === 1' in html
    assert 'transactionEntryAccount.value = preferredAccountId;' in html
    assert 'cashFlowEntryAccount.value = preferredAccountId;' in html
    assert 'await showTransactionEntryForm();' in html
    assert 'await showCashFlowEntryForm();' in html


def test_account_creation_form_opens_without_forced_mobile_keyboard(monkeypatch):
    html = _html(monkeypatch)

    assert 'createForm.scrollIntoView({' in html
    assert 'accountNameInput.focus();' not in html


def test_logout_clears_cash_flow_visible_counts(monkeypatch):
    html = _html(monkeypatch)

    assert 'cashFlowVisibleCounts.clear();' in html


def test_logout_clears_search_and_settings_status(monkeypatch):
    html = _html(monkeypatch)

    assert 'usAssetTickerInput.value = "";' in html
    assert 'usAssetSearchResult.innerHTML = "";' in html
    assert 'morningReportSettingsMessage.textContent = "";' in html
    assert 'kakaoStatus.textContent = "연결 상태 확인 중...";' in html
    assert 'kakaoTestButton.style.display = "none";' in html
    assert 'kakaoDisconnectButton.style.display = "none";' in html


def test_logout_clears_private_report_and_profile_state(monkeypatch):
    html = _html(monkeypatch)

    assert 'document.getElementById("investment-preference-text").value = "";' in html
    assert 'document.getElementById("investment-profile-message").textContent = "";' in html
    assert 'reportFrame.srcdoc = "";' in html
    assert 'reportFrame.style.display = "none";' in html
    assert 'reportSection.style.display = "none";' in html


def test_account_creation_labels_are_associated_with_fields(monkeypatch):
    html = _html(monkeypatch)

    assert '"account-create-field-"' in html
    assert 'element.id = fieldId;' in html
    assert 'label.htmlFor =' in html


def test_account_editor_labels_are_associated_with_fields(monkeypatch):
    html = _html(monkeypatch)

    assert '"account-editor-"' in html
    assert 'label.htmlFor =' in html
    assert 'defaultLabel.htmlFor =' in html
    assert 'isDefault.id =' in html


def test_transaction_and_cash_flow_labels_are_associated(monkeypatch):
    html = _html(monkeypatch)

    assert '"transaction-"' in html
    assert '"cash-flow-"' in html
    assert html.count('element.id = fieldId;') >= 4
    assert html.count('label.htmlFor =') >= 4


def test_cash_flow_edit_labels_are_associated(monkeypatch):
    html = _html(monkeypatch)

    assert '"cash-flow-edit-"' in html
    assert '+ cashFlow.id' in html
    assert html.count('label.htmlFor =') >= 5


def test_transaction_edit_labels_are_associated(monkeypatch):
    html = _html(monkeypatch)

    assert '"transaction-edit-"' in html
    assert '+ transaction.id' in html
    assert html.count('label.htmlFor =') >= 6


def test_chart_close_button_has_accessible_name(monkeypatch):
    html = _html(monkeypatch)

    assert '"aria-label",' in html
    assert '"차트 닫기"' in html


def test_admin_member_actions_recover_from_request_errors(monkeypatch):
    html = _html(monkeypatch)
    assert 'id="admin-member-action-message"' in html
    assert 'adminMemberActionMessage.textContent = "";' in html
    assert 'throw new Error(data.detail || (deleting' in html
    assert 'button.disabled = false;' in html


def test_home_response_has_browser_security_headers(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")
    response = home()

    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert "base-uri 'none'" in response.headers["content-security-policy"]
