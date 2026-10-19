    appendCreateField(
        "계좌 시작 현금잔고",
        initialCapitalInput
    );
    const createCashHelp = document.createElement("p");
    createCashHelp.className = "field-help";
    createCashHelp.textContent = "계좌 등록 시점의 현금만 입력하세요. 보유 종목 평가금액이나 별도로 등록할 입금액을 포함하지 마세요.";
    initialCapitalInput.after(createCashHelp);


    /*
    월 기본 매수 한도
    */

    const baseMonthlyInput =
        document.createElement(
            "input"
        );

    baseMonthlyInput.type =
        "number";

    baseMonthlyInput.min =
        "0";

    baseMonthlyInput.step =
        "any";

    baseMonthlyInput.value =
        "0";

    appendCreateField(
        "월 기본 매수 한도",
        baseMonthlyInput
    );


    /*
    월 추가 매수 한도
    */

    const additionalMonthlyInput =
        document.createElement(
            "input"
        );

    additionalMonthlyInput.type =
        "number";

    additionalMonthlyInput.min =
        "0";

    additionalMonthlyInput.step =
        "any";

    additionalMonthlyInput.value =
        "0";

    appendCreateField(
        "월 추가 매수 한도",
        additionalMonthlyInput
    );


    /*
    외부자금 납입 방식
    */

    const contributionTypeSelect =
        document.createElement(
            "select"
        );

    contributionTypeSelect.innerHTML = `
        <option value="none">없음</option>
        <option value="monthly">매월</option>
        <option value="yearly">매년</option>
        <option value="irregular">비정기</option>
    `;

    appendCreateField(
        "외부자금 납입 방식",
        contributionTypeSelect
    );


    /*
    외부자금 납입 금액
    */

    const contributionAmountInput =
        document.createElement(
            "input"
        );

    contributionAmountInput.type =
        "number";

    contributionAmountInput.min =
        "0";

    contributionAmountInput.step =
        "any";

    contributionAmountInput.value =
        "0";

    appendCreateField(
        "외부자금 납입 금액",
        contributionAmountInput
    );


    /*
    연간 납입 월
    */

    const contributionMonthSelect =
        document.createElement(
            "select"
        );

    contributionMonthSelect.innerHTML =
        '<option value="">선택 안 함</option>';

    for (
        let month = 1;
        month <= 12;
        month++
    ) {
        const option =
            document.createElement(
                "option"
            );

        option.value =
            String(month);

        option.textContent =
            month + "월";

        contributionMonthSelect
            .appendChild(
                option
            );
    }

    contributionMonthSelect.disabled =
        true;

    appendCreateField(
        "연간 납입 월",
        contributionMonthSelect
    );


    contributionTypeSelect
        .addEventListener(
            "change",
            () => {

                const yearly =
                    contributionTypeSelect
                    .value
                    === "yearly";

                contributionMonthSelect
                    .disabled =
                    !yearly;

                if (!yearly) {
                    contributionMonthSelect
                        .value = "";
                }
            }
        );


    /*
    매수 주기
    */

    const buyCycleTypeSelect =
        document.createElement(
            "select"
        );

    buyCycleTypeSelect.innerHTML = `
        <option value="monthly">매월</option>
        <option value="weekly">매주</option>
        <option value="manual">수동</option>
    `;

    appendCreateField(
        "매수 주기",
        buyCycleTypeSelect
    );


    /*
    매수 주기 상세
    */

    const buyCycleDetailInput =
        document.createElement(
            "input"
        );

    buyCycleDetailInput.type =
        "text";

    buyCycleDetailInput.value =
        "25";

    buyCycleDetailInput.placeholder =
        "매월이면 매수일 입력";

    appendCreateField(
        "매수 주기 상세",
        buyCycleDetailInput
    );


    /*
    기본 계좌
    */

    const defaultWrapper =
        document.createElement(
            "label"
        );

    const defaultCheckbox =
        document.createElement(
            "input"
        );

    defaultCheckbox.type =
        "checkbox";

    defaultWrapper.appendChild(
        defaultCheckbox
    );

    defaultWrapper.appendChild(
        document.createTextNode(
            " 이 계좌를 기본 계좌로 설정"
        )
    );

    createForm.appendChild(
        defaultWrapper
    );


    /*
    메모
    */

    const memoInput =
        document.createElement(
            "textarea"
        );

    memoInput.placeholder =
        "선택사항";

    appendCreateField(
        "메모",
        memoInput
    );


    /*
    생성 / 취소 버튼
    */

    const createButton =
        document.createElement(
            "button"
        );

    createButton.type =
        "submit";

    createButton.textContent =
        "계좌 생성";


    const cancelButton =
        document.createElement(
            "button"
        );

    cancelButton.type =
        "button";

    cancelButton.textContent =
        "취소";


    const createMessage =
        document.createElement(
            "div"
        );

    createMessage.className =
        "transaction-message";


    createForm.appendChild(
        createButton
    );

    createForm.appendChild(
        cancelButton
    );

    createForm.appendChild(
        createMessage
    );


    openCreateButton
        .addEventListener(
            "click",
            () => {

                createForm.style.display =
                    "block";

                openCreateButton.style.display =
                    "none";

                createForm.scrollIntoView({
                    behavior: "smooth",
                    block: "nearest"
                });
            }
        );


    cancelButton
        .addEventListener(
            "click",
            () => {

                createForm.style.display =
                    "none";

                openCreateButton.style.display =
                    "inline-block";

                createMessage.textContent =
                    "";
            }
        );


    /*
    계좌 생성 API 호출
    */

    createForm.addEventListener(
        "submit",
        async (event) => {

            event.preventDefault();


            createButton.disabled =
                true;

            createButton.textContent =
                "생성 중...";

            createMessage.textContent =
                "";


            const contributionMonth =
                contributionMonthSelect.value
                ? Number(
                    contributionMonthSelect.value
                )
                : null;


            const payload = {

                account_name:
                    accountNameInput
                    .value
                    .trim(),

                account_number:
                    accountNumberInput
                    .value
                    .trim(),

                broker:
                    brokerInput
                    .value
                    .trim(),

                initial_capital:
                    Number(
                        initialCapitalInput
                        .value || 0
                    ),

                base_monthly:
                    Number(
                        baseMonthlyInput
                        .value || 0
                    ),

                max_additional_monthly:
                    Number(
                        additionalMonthlyInput
                        .value || 0
                    ),

                buy_cycle_type:
                    buyCycleTypeSelect.value,

                buy_cycle_detail:
                    buyCycleDetailInput
                    .value
                    .trim(),

                currency:
                    currencySelect.value,

                account_type:
                    accountTypeSelect.value,

                market_scope:
                    marketScopeSelect.value,

                contribution_type:
                    contributionTypeSelect.value,

                contribution_amount:
                    Number(
                        contributionAmountInput
                        .value || 0
                    ),

                contribution_month:
                    contributionMonth,

                strategy_type:
                    strategyTypeSelect.value,

                is_default:
                    defaultCheckbox.checked,

                memo:
                    memoInput
                    .value
                    .trim()
            };


            try {

                const response =
                    await apiRequest(
                        "/api/accounts",
                        accessToken,
                        {
                            method:
                                "POST",

                            headers: {
                                "Content-Type":
                                    "application/json"
                            },

                            body:
                                JSON.stringify(
                                    payload
                                )
                        }
                    );


                if (
                    !response.created
                    || !response.account
                ) {
                    throw new Error(
                        "계좌 생성 결과를 확인할 수 없습니다."
                    );
                }


                createMessage.textContent =
                    response.account
                    .account_name
                    + " 계좌가 생성되었습니다.";

                createMessage.className =
                    "transaction-message success";


                /*
                서버에서 계좌 목록을 다시 가져옵니다.
                */

                const refreshed =
                    await apiRequest(
                        "/api/accounts",
                        accessToken
                    );


                const refreshedAccounts =
                    Array.isArray(
                        refreshed
                    )
                    ? refreshed
                    : (
                        refreshed.accounts
                        || []
                    );


                await renderAccounts(refreshedAccounts, accessToken);
                await renderAccountCreator(refreshedAccounts, accessToken);
                await renderAccountManagement(refreshedAccounts, accessToken);
                await loadTransactionTab(refreshedAccounts, accessToken);


            } catch (error) {

                createMessage.textContent =
                    error.message
                    || "계좌 생성에 실패했습니다.";

                createMessage.className =
                    "transaction-message error";


                createButton.disabled =
                    false;

                createButton.textContent =
                    "계좌 생성";
            }
        }
    );


    createSection.appendChild(
        createForm
    );

    accountCreator.appendChild(
        createSection
    );


    /*
    등록된 계좌가 없는 경우에도
    신규 계좌 추가 UI는 유지합니다.
    */

    if (accounts.length === 0) {

        const empty =
            document.createElement(
                "div"
            );

        empty.className =
            "empty";

        empty.textContent =
            "아직 등록된 계좌가 없습니다. 위에서 첫 계좌를 추가해주세요.";

        accountCreator.appendChild(
            empty
        );

        return;
    }


}

let selectedHomeAccountId = "";
function openHomeAccountAction(action) {
    if (action === "holdings") {
        setAppTab("portfolio");
        return;
    }
    setAppTab("transactions");
    const accountFilter = document.getElementById("transaction-account-filter");
    if (accountFilter) {
        accountFilter.value = selectedHomeAccountId;
        accountFilter.dispatchEvent(new Event("change"));
    }
    if (action === "deposit") {
        selectedCashFlowAccountId = selectedHomeAccountId;
        const openButton = document.getElementById("open-cash-flow-entry");
        if (openButton) openButton.click();
    } else {
        const openButton = document.getElementById("open-transaction-entry");
        if (openButton) openButton.click();
    }
}
document.getElementById("home-quick-deposit").addEventListener("click", () => openHomeAccountAction("deposit"));
document.getElementById("home-quick-trade").addEventListener("click", () => openHomeAccountAction("trade"));
document.getElementById("home-quick-holdings").addEventListener("click", () => openHomeAccountAction("holdings"));
document.getElementById("home-quick-settings").addEventListener("click", () => { setAppTab("settings"); setSettingsPanel("accounts"); });

function renderHomeAccountDashboard(accounts, summaries) {
    const selector = document.getElementById("home-account-selector");
    if (selector) {
        selector.replaceChildren();

        for (const account of accounts) selector.add(new Option(account.account_name || "계좌 " + account.id, String(account.id)));
        if (!accounts.some(account => String(account.id) === selectedHomeAccountId)) {
            const preferred = accounts.find(a => a.is_default) || accounts[0];
            selectedHomeAccountId = preferred ? String(preferred.id) : "";
        }
        selector.value = selectedHomeAccountId;
        selector.onchange = () => {
            selectedHomeAccountId = selector.value;
            renderHomeAccountDashboard(accounts, summaries);
            showSelectedAccountCard();
            showSelectedAccountSettings();
            syncSelectedAccountToTransactionFilter();
        };
    }
    const visibleAccounts = selectedHomeAccountId ? accounts.filter(a => String(a.id) === selectedHomeAccountId) : accounts;
    const container = document.getElementById("home-dashboard-content");
    if (!container) return;
    container.replaceChildren();
    if (!accounts.length) {
        container.textContent = "등록된 계좌가 없습니다. 설정에서 계좌를 추가하세요.";
        return;
    }

    const currencies = new Set(visibleAccounts.map(a => String(a.currency || "KRW").toUpperCase()));
    if (currencies.size > 1) {
        const notice = document.createElement("p");
        notice.textContent = "계좌 통화가 달라 총자산 합계는 표시하지 않습니다.";
        container.appendChild(notice);
    } else if (visibleAccounts.every(a => summaries.has(String(a.id)))) {
        const total = visibleAccounts.reduce((sum, a) => sum + Number(summaries.get(String(a.id)).total_assets || 0), 0);
        const totalRow = document.createElement("div");
        totalRow.className = "summary-kpi";
        totalRow.textContent = "총자산 · " + formatMoney(total, [...currencies][0]);
        container.appendChild(totalRow);
        const pnl = visibleAccounts.reduce((sum, a) => sum + Number(summaries.get(String(a.id)).total_unrealized_pnl || 0), 0);
        const pnlRow = document.createElement("div");
        pnlRow.className = "summary-kpi";
        pnlRow.textContent = "평가손익 · " + (pnl > 0 ? "+" : "") + formatMoney(pnl, [...currencies][0]);
        container.appendChild(pnlRow);
        const cash = visibleAccounts.reduce((sum, a) => sum + Number(summaries.get(String(a.id)).cash_balance || 0), 0);
        const cashRow = document.createElement("div");
        cashRow.className = "summary-kpi";
        cashRow.textContent = "예수금 · " + formatMoney(cash, [...currencies][0]);
        container.appendChild(cashRow);
    }
    for (const account of visibleAccounts) {
        const row = document.createElement("div");
        row.className = "target-row";
        const label = document.createElement("span");
        label.textContent = account.account_name || "계좌";
        const value = document.createElement("span");
        const summary = summaries.get(String(account.id));
        if (summary) {
            const currency = String(account.currency || "KRW").toUpperCase();
            const pnl = Number(summary.total_unrealized_pnl || 0);
            const assets = Number(summary.total_assets);
            const cash = Number(summary.cash_balance);
            const invested = Number(summary.total_invested);
            const hasCostBasis = Number.isFinite(invested) && invested > 0;
            value.textContent = formatMoney(summary.total_assets, currency)
                + " · 평가손익 " + (hasCostBasis ? (pnl > 0 ? "+" : "") + formatMoney(pnl, currency) : "매입원가 확인 필요");
            if (Number.isFinite(assets) && assets < 0) {
                const warning = document.createElement("small");
                warning.className = "status-box";
                warning.textContent = "총자산 음수: 예수금·거래·시작잔고 입력을 확인하세요. 주식평가액 "
                    + formatMoney(summary.total_current_value, currency) + " · 예수금 " + formatMoney(cash, currency);
                row.appendChild(warning);
            }
        } else {
            value.textContent = "조회 중 또는 데이터 없음";
        }
        row.append(label, value);
        container.appendChild(row);
    }
}

function syncSelectedAccountToTransactionFilter() {
    const filter = document.getElementById("transaction-account-filter");
    if (!filter || !selectedHomeAccountId) return;
    if ([...filter.options].some(option => option.value === selectedHomeAccountId)) {
        filter.value = selectedHomeAccountId;
        filter.dispatchEvent(new Event("change"));
    }
}

function showSelectedAccountSettings() {
    for (const card of accountManagementList.querySelectorAll("[data-account-id]")) {
        card.hidden = card.dataset.accountId !== selectedHomeAccountId;
    }
}

function showSelectedAccountCard() {
    for (const card of accountsList.querySelectorAll("[data-account-id]")) {
        card.hidden = card.dataset.accountId !== selectedHomeAccountId;
    }
}

async function renderAccounts(
    accounts,
    accessToken
) {
    accountsList.innerHTML = "";
    const dashboardSummaries = new Map();
    renderHomeAccountDashboard(accounts, dashboardSummaries);

    /*
    기존 계좌 표시
    */

    for (const [accountIndex, account] of accounts.entries()) {

        const card =
            document.createElement(
                "div"
            );

        card.className =
            "account-card";
        card.dataset.accountId = String(account.id);
        card.hidden = String(account.id) !== selectedHomeAccountId;
            
        const name =
            document.createElement(
                "div"
            );

        name.className =
            "account-name";

        name.textContent =
            account.account_name
            + (
                account.is_default
                ? " · 기본 계좌"
                : ""
            );

        card.appendChild(name);

        const summaryTitle =
            document.createElement(
                "div"
            );
        summaryTitle.className =
            "section-title account-summary-title";
        summaryTitle.textContent =
            "계좌 핵심 요약";

        const summaryBox =
            document.createElement(
                "div"
            );
        summaryBox.dataset.role =
            "account-summary";
        summaryBox.className =
            "loading";
        summaryBox.textContent =
            "총자산과 예수금을 불러오는 중...";

        card.appendChild(summaryTitle);
        card.appendChild(summaryBox);

        // 계좌별 세부정보는 기본적으로 접어 화면 길이를 줄입니다.
        const detailsPanel = document.createElement("details");
        detailsPanel.className = "account-details-panel";
        detailsPanel.open = accounts.length === 1 || accountIndex === 0;
        const detailsToggle = document.createElement("summary");
        detailsToggle.className = "account-details-toggle";
        detailsToggle.textContent = "계좌 상세정보 · 목표 비중 · 보유 종목";
        detailsPanel.appendChild(detailsToggle);
        card.appendChild(detailsPanel);

        const readinessPanel = document.createElement("div");
        readinessPanel.className = "status-box";
        const readinessButton = document.createElement("button");
        readinessButton.type = "button";
        readinessButton.textContent = "수익률 계산 준비 상태 확인";
        const readinessResult = document.createElement("div");
        readinessResult.setAttribute("aria-live", "polite");
        readinessButton.addEventListener("click", async () => {
            readinessButton.disabled = true;
            readinessResult.textContent = "진단 중...";
            try {
                const data = await apiRequest(
                    "/api/accounts/" + encodeURIComponent(account.id) + "/return-readiness",
                    accessToken
                );
                readinessResult.replaceChildren();
                const status = document.createElement("p");
                status.textContent = data.ready_for_xirr && data.ready_for_twr
                    ? "수익률 계산에 필요한 데이터가 확인되었습니다."
                    : "정확한 수익률 계산을 위해 추가 확인이 필요합니다.";
                readinessResult.appendChild(status);
                for (const warning of data.warnings || []) {
                    const item = document.createElement("p");
                    item.textContent = "• " + String(warning.message || "추가 확인 필요");
                    readinessResult.appendChild(item);
                }
            } catch (error) {
                readinessResult.textContent = "진단 실패: " + (error.message || "다시 시도해주세요.");
            } finally {
                readinessButton.disabled = false;
            }
        });
        readinessPanel.append(readinessButton, readinessResult);
        detailsPanel.appendChild(readinessPanel);

        // 시작 자산은 명시적으로 펼쳤을 때만 읽고, 사용자가 저장할 때만 기록합니다.
        const openingPanel = document.createElement("details");
        openingPanel.className = "account-details-panel";
        const openingToggle = document.createElement("summary");
        openingToggle.textContent = "계좌 시작 자산 입력 (초안)";
        openingPanel.appendChild(openingToggle);
        const openingForm = document.createElement("form");
        openingForm.className = "status-box";
        const openingStatus = document.createElement("p");
        openingStatus.setAttribute("aria-live", "polite");
        openingStatus.textContent = "시작일과 시작 시점의 자산만 입력합니다. 기존 거래·잔고에 자동 반영되지 않습니다.";
        const openingDate = document.createElement("input");
        openingDate.type = "date";
        openingDate.required = true;
        const openingTodayLocalISO = () => {
            const now = new Date();
            const year = String(now.getFullYear());
            const month = String(now.getMonth() + 1).padStart(2, "0");
            const day = String(now.getDate()).padStart(2, "0");
            return year + "-" + month + "-" + day;
        };
        openingDate.max = openingTodayLocalISO();
        openingDate.setAttribute("aria-label", "계좌 시작일");
        const openingCash = document.createElement("input");
        openingCash.type = "number";
        openingCash.min = "0";
        openingCash.step = "any";
        openingCash.required = true;
        openingCash.placeholder = "시작 현금잔고";
        openingCash.inputMode = "decimal";
        openingCash.setAttribute("aria-label", "시작 현금잔고");
        const openingHoldings = document.createElement("textarea");
        openingHoldings.rows = 3;
        openingHoldings.spellcheck = false;
        openingHoldings.placeholder = "보유종목: 종목코드,수량,평가금액 (한 줄에 한 종목)";
        openingHoldings.setAttribute("aria-label", "시작 보유종목 목록");
        const openingHelp = document.createElement("p");
        openingHelp.textContent = "예시: AAPL,2,500000 (평가금액은 계좌 기준통화). 종목마다 줄을 바꿔 입력하세요.";
        const openingLoad = document.createElement("button");
        openingLoad.type = "button";
        openingLoad.textContent = "기존 초안 불러오기";
        const openingSave = document.createElement("button");
        openingSave.type = "submit";
        openingSave.textContent = "시작 자산 초안 저장";
        const openingCheckResult = document.createElement("div");
        openingCheckResult.setAttribute("aria-live", "polite");
        let openingCheckVersion = 0;
        let openingEditVersion = 0;
        let openingRequestBusy = false;
        let openingDraftConfirmed = false;
        let openingCheckInFlight = false;
        const setOpeningRequestBusy = busy => {
            openingRequestBusy = busy;
            openingLoad.disabled = busy;
            openingSave.disabled = busy || openingDraftConfirmed;
            openingCheck.disabled = busy || openingCheckInFlight;
        };
        const clearOpeningCheck = () => {
            openingCheckVersion += 1;
            openingEditVersion += 1;
            openingCheckResult.textContent = "";
        };
        for (const field of [openingDate, openingCash, openingHoldings]) {
            field.addEventListener("input", clearOpeningCheck);
            field.addEventListener("change", clearOpeningCheck);
        }
        const openingUrl = "/api/accounts/" + encodeURIComponent(account.id) + "/opening-snapshot";
        openingLoad.addEventListener("click", async () => {
            if (openingRequestBusy) return;
            clearOpeningCheck();
            const loadEditVersion = openingEditVersion;
            setOpeningRequestBusy(true);
            openingStatus.textContent = "불러오는 중...";
            try {
                const data = await apiRequest(openingUrl, accessToken);
                if (loadEditVersion !== openingEditVersion) {
                    openingStatus.textContent = "입력값이 변경되어 불러온 결과를 적용하지 않았습니다.";
                    return;
                }
                if (!data.configured || !data.snapshot) {
                    openingDraftConfirmed = false;
                    openingStatus.textContent = "저장된 시작 자산이 없습니다.";
                    return;
                }
                const snapshot = data.snapshot;
                openingDate.value = snapshot.opening_date || "";
                openingCash.value = snapshot.cash_amount || "0";
                openingHoldings.value = (snapshot.holdings || []).map(item =>
                    [item.ticker, item.quantity, item.market_value].join(",")
                ).join("\n");
                openingStatus.textContent = snapshot.status === "confirmed"
                    ? "확정된 시작 자산입니다. 초안으로 덮어쓸 수 없습니다."
                    : "저장된 초안을 불러왔습니다. 통화: " + snapshot.currency;
                openingDraftConfirmed = snapshot.status === "confirmed";
            } catch (error) {
                openingStatus.textContent = "조회 실패: " + (error.message || "다시 시도해주세요.");
            } finally {
                setOpeningRequestBusy(false);
            }
        });
        openingForm.addEventListener("submit", async event => {
            event.preventDefault();
            if (openingRequestBusy || openingDraftConfirmed) return;
            clearOpeningCheck();
            const lines = openingHoldings.value.split(/\r?\n/).map(line => line.trim()).filter(Boolean);
            const holdings = [];
            const seenTickers = new Set();
            if (!openingDate.value || openingDate.value > openingTodayLocalISO()) {
                openingStatus.textContent = "계좌 시작일은 오늘 또는 이전 날짜여야 합니다.";
                return;
            }
            if (!Number.isFinite(Number(openingCash.value)) || Number(openingCash.value) < 0 || openingCash.value.trim() === "") {
                openingStatus.textContent = "시작 현금잔고는 0 이상의 숫자로 입력해주세요.";
                return;
            }
            for (const line of lines) {
                const parts = line.split(",").map(value => value.trim());
                if (parts.length !== 3 || !parts.every(Boolean)) {
                    openingStatus.textContent = "보유종목은 종목코드,수량,평가금액 형식으로 입력해주세요.";
                    return;
                }
                const ticker = parts[0].toUpperCase();
                const quantity = Number(parts[1]);
                const marketValue = Number(parts[2]);
                if (seenTickers.has(ticker)) {
                    openingStatus.textContent = "중복된 종목코드가 있습니다: " + ticker;
                    return;
                }
                if (!Number.isFinite(quantity) || !Number.isFinite(marketValue) || quantity < 0 || marketValue < 0 || (quantity === 0 && marketValue !== 0)) {
                    openingStatus.textContent = "수량과 평가금액은 0 이상의 숫자여야 하며 수량이 0이면 평가금액도 0이어야 합니다.";
                    return;
                }
                seenTickers.add(ticker);
                holdings.push({ticker: ticker, quantity: parts[1], market_value: parts[2]});
            }
            const saveEditVersion = openingEditVersion;
            setOpeningRequestBusy(true);
            openingStatus.textContent = "저장 중...";
            try {
                await apiRequest(openingUrl, accessToken, {
                    method: "PUT",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({
                        opening_date: openingDate.value,
                        cash_amount: openingCash.value,
                        currency: getAccountCurrency(account),
                        holdings: holdings
                    })
                });
                openingStatus.textContent = saveEditVersion === openingEditVersion
                    ? "시작 자산 초안이 저장되었습니다. 기존 잔고에는 반영되지 않습니다."
                    : "이전 입력값은 저장되었지만 이후 수정한 내용은 저장되지 않았습니다. 다시 저장해주세요.";
            } catch (error) {
                openingStatus.textContent = saveEditVersion === openingEditVersion
                    ? "저장 실패: " + (error.message || "다시 시도해주세요.")
                    : "이전 입력값 저장에 실패했습니다. 현재 수정한 내용은 유지됩니다. 다시 저장해주세요.";
            } finally {
                setOpeningRequestBusy(false);
            }
        });
        const openingCheck = document.createElement("button");
        openingCheck.type = "button";
        openingCheck.textContent = "시작 자산 확정 전 검증";

        openingCheck.addEventListener("click", async () => {
            if (openingRequestBusy || openingCheckInFlight) return;
            const checkVersion = ++openingCheckVersion;
            openingCheckInFlight = true;
            openingCheck.disabled = true;
            openingCheckResult.textContent = "저장된 초안을 검증 중입니다...";
            try {
                const result = await apiRequest(openingUrl + "/preflight", accessToken);
                if (checkVersion !== openingCheckVersion) return;
                openingCheckResult.replaceChildren();
                const heading = document.createElement("p");
                heading.textContent = result.can_confirm
                    ? "자동 검증에서 차단 항목은 발견되지 않았습니다. 최종 확정은 아직 지원하지 않습니다."
                    : "확정 전 확인이 필요한 항목이 있습니다.";
                openingCheckResult.appendChild(heading);
                const renderPreflightItems = (title, items) => {
                    if (!Array.isArray(items) || items.length === 0) return;
                    const section = document.createElement("section");
                    const label = document.createElement("strong");
                    label.textContent = title + " (" + items.length + "건)";
                    section.appendChild(label);
                    const list = document.createElement("ul");
                    for (const item of items) {
                        const message = document.createElement("li");
                        message.textContent = String(item.message || "기록 확인 필요")
                            + (Array.isArray(item.tickers) && item.tickers.length
                                ? " (" + item.tickers.join(", ") + ")" : "");
                        list.appendChild(message);
                    }
                    section.appendChild(list);
                    openingCheckResult.appendChild(section);
                };
                renderPreflightItems("확정 차단 사유", result.blockers);
                renderPreflightItems("추가 확인 경고", result.warnings);
            } catch (error) {
                if (checkVersion !== openingCheckVersion) return;
                openingCheckResult.textContent = "검증 실패: " + (error.message || "다시 시도해주세요.");
            } finally {
                openingCheckInFlight = false;
                openingCheck.disabled = openingRequestBusy;
            }
        });
        openingForm.append(openingStatus, openingDate, openingCash, openingHelp, openingHoldings, openingLoad, openingSave, openingCheck, openingCheckResult);
        openingPanel.appendChild(openingForm);
        detailsPanel.appendChild(openingPanel);


        detailsPanel.appendChild(
            createDetail(
                "증권사: "
                + (
                    account.broker
                    || "-"
                )
            )
        );


        detailsPanel.appendChild(
            createDetail(
                "계좌 유형: "
                + accountTypeText(
                    account.account_type
                )
            )
        );


        detailsPanel.appendChild(
            createDetail(
                "기준 통화: "
                + getAccountCurrency(
                    account
                )
            )
        );


        detailsPanel.appendChild(
            createDetail(
                "투자 시장: "
                + marketScopeText(
                    account.market_scope
                )
            )
        );


        detailsPanel.appendChild(
            createDetail(
                "운용 방식: "
                + strategyTypeText(
                    account.strategy_type
                )
            )
        );


        detailsPanel.appendChild(
            createDetail(
                "월 기본 매수 한도: "
                + formatMoney(
                    account.base_monthly,
                    getAccountCurrency(
                        account
                    )
                )
            )
        );


        detailsPanel.appendChild(
            createDetail(
                "월 추가 매수 한도: "
                + formatMoney(
                    account
                    .max_additional_monthly,
                    getAccountCurrency(
                        account
                    )
                )
            )
        );


        let contributionText =
            "외부자금 납입: "
            + contributionTypeText(
                account.contribution_type
            );


        if (
            Number(
                account.contribution_amount
                || 0
            ) > 0
        ) {

            contributionText +=
                " · "
                + formatMoney(
                    account.contribution_amount,
                    getAccountCurrency(
                        account
                    )
                );
        }


        if (
            account.contribution_type
            === "yearly"
            && account.contribution_month
        ) {

            contributionText +=
                " · "
                + account.contribution_month
                + "월";
        }


        detailsPanel.appendChild(
            createDetail(
                contributionText
            )
        );


        const cycleText =
            account.buy_cycle_type
            === "monthly"
            ? (
                "매수주기: 매월 "
                + account.buy_cycle_detail
                + "일"
            )
            : (
                "매수주기: "
                + account.buy_cycle_type
                + " / "
                + account.buy_cycle_detail
            );


        detailsPanel.appendChild(
            createDetail(
                cycleText
            )
        );


        /*
        목표 포트폴리오
        */

        const targetsTitle =
            document.createElement(
                "div"
            );

        targetsTitle.className =
            "section-title";

        targetsTitle.textContent =
            "목표 포트폴리오";

        detailsPanel.appendChild(
            targetsTitle
        );


        const targetsList =
            document.createElement(
                "div"
            );

        targetsList.className =
            "loading";

        targetsList.textContent =
            "목표 비중을 불러오는 중...";

        detailsPanel.appendChild(
            targetsList
        );


        accountsList.appendChild(
            card
        );


        try {

            const targets =
                await loadAccountTargets(
                    accessToken,
                    account.id
                );

            renderTargets(
                targetsList,
                targets
            );
            const editButton = document.createElement("button");
            editButton.type = "button";
            editButton.textContent = "목표 편집";
            editButton.className = "small-button";
            targetsTitle.appendChild(editButton);
            const editPanel = document.createElement("div");
            editPanel.className = "target-editor-panel";
            editPanel.hidden = true;
            targetsList.after(editPanel);
            editButton.addEventListener("click", () => {
                editPanel.hidden = !editPanel.hidden;
                if (editPanel.hidden) return;
                let draft = targets.map(item => ({...item}));
                editPanel.replaceChildren();
                const rows = document.createElement("div");
                const status = document.createElement("div");
                status.setAttribute("role", "status");
                const search = document.createElement("input");
                search.type = "search";
                search.placeholder = "종목명 또는 종목코드 검색";
                search.setAttribute("aria-label", "목표 종목 검색");
                const results = document.createElement("div");
                const redraw = () => {
                    rows.replaceChildren();
                    for (const item of draft) {
                        const row = document.createElement("div");
                        row.className = "target-editor-row";
                        const label = document.createElement("span");
                        label.textContent = (item.name || item.ticker) + " (" + item.ticker + ")";
                        const weight = document.createElement("input");
                        weight.type = "number";
                        weight.min = "0";
                        weight.max = "100";
                        weight.step = "0.01";
                        weight.value = String(Number(item.target_weight) * 100);
                        weight.setAttribute("aria-label", item.ticker + " 목표 비중 (%)");
                        weight.addEventListener("input", () => { item.target_weight = weight.value === "" ? NaN : Number(weight.value) / 100; });
                        const remove = document.createElement("button");
                        remove.type = "button";
                        remove.textContent = "삭제";
                        remove.addEventListener("click", () => { draft = draft.filter(x => x !== item); redraw(); });
                        row.append(label, weight, remove);
                        rows.appendChild(row);
                    }
                };
                let requestId = 0;
                search.addEventListener("input", async () => {
                    const query = search.value.trim();
                    const id = ++requestId;
                    results.replaceChildren();
                    if (query.length < 2) return;
                    try {
                        const data = await apiRequest("/api/assets?q=" + encodeURIComponent(query) + "&limit=15", accessToken);
                        if (id !== requestId) return;
                        if (!(data.assets || []).length) results.textContent = "검색 결과가 없습니다.";
                        for (const asset of data.assets || []) {
                            const option = document.createElement("button");
                            option.type = "button";
                            option.textContent = (asset.name || asset.ticker) + " (" + asset.ticker + ")";
                            option.addEventListener("click", () => {
                                if (!draft.some(x => x.ticker.toUpperCase() === asset.ticker.toUpperCase())) {
                                    draft.push({ticker: asset.ticker, name: asset.name, target_weight: 0});
                                    redraw();
                                }
                                results.replaceChildren();
                                search.value = "";
                            });
                            results.appendChild(option);
                        }
                    } catch (error) {
                        if (id === requestId) results.textContent = error.message || "종목 검색 실패";
                    }
                });
                const save = document.createElement("button");
                save.type = "button";
                save.textContent = "저장";
                save.addEventListener("click", async () => {
                    const total = draft.reduce((sum, item) => sum + Number(item.target_weight), 0);
                    if (!draft.length || draft.some(x => !Number.isFinite(x.target_weight) || x.target_weight < 0 || x.target_weight > 1) || Math.abs(total - 1) > 0.000001) {
                        status.textContent = "목표 비중 합계는 100%여야 합니다.";
                        return;
                    }
                    save.disabled = true;
                    status.textContent = "저장 중...";
                    try {
                        const data = await apiRequest("/api/accounts/" + encodeURIComponent(account.id) + "/targets", accessToken, {
                            method: "PUT",
                            headers: {"Content-Type": "application/json"},
                            body: JSON.stringify({targets: draft.map(x => ({ticker: x.ticker, target_weight: x.target_weight}))}),
                        });
                        targets.splice(0, targets.length, ...(data.targets || []));
                        renderTargets(targetsList, targets);
                        const comparison = card.querySelector(".target-allocation-comparison");
                        if (comparison) {
                            const refreshed = await loadPositions(accessToken, account.id);
                            renderTargetAllocationComparison(comparison, targets, refreshed.positions || []);
                        }
                        editPanel.hidden = true;
                    } catch (error) {
                        status.textContent = error.message || "저장 실패";
                    } finally {
                        save.disabled = false;
                    }
                });
                const cancel = document.createElement("button");
                cancel.type = "button";
                cancel.textContent = "취소";
                cancel.addEventListener("click", () => { editPanel.hidden = true; });
                editPanel.append(rows, search, results, status, save, cancel);
                redraw();
            });



            /*
            보유현황
            */

            const positionsTitle =
                document.createElement(
                    "div"
                );

            positionsTitle.className =
                "section-title";

            positionsTitle.textContent =
                "현재 보유현황";

            detailsPanel.appendChild(
                positionsTitle
            );


            const positionsList =
                document.createElement(
                    "div"
                );

            positionsList.className =
                "loading";

            positionsList.textContent =
                "보유현황을 계산하는 중...";

            detailsPanel.appendChild(
                positionsList
            );


            try {

                const positionData =
                    await loadPositions(
                        accessToken,
                        account.id
                    );

                const positions =
                    positionData.positions
                    || [];

                const summary =
                    positionData.summary;


                /*
                계좌 요약
                */

                renderAccountSummary(
                    summaryBox,
                    summary,
                    account
                );
                if (summary) {
                    dashboardSummaries.set(String(account.id), summary);
                    renderHomeAccountDashboard(accounts, dashboardSummaries);
                }


                renderPositions(
                    positionsList,
                    positions,
                    account,
                    accessToken
                );
                const comparison = document.createElement("div");
                comparison.className = "target-allocation-comparison";
                positionsList.before(comparison);
                renderTargetAllocationComparison(comparison, targets, positions);

            } catch (error) {

                console.error(
                    "보유현황 오류:",
                    error
                );

                positionsList.className =
                    "error";

                positionsList.textContent =
                    "보유현황 오류: "
                    + (
                        error.name
                        || "Error"
                    )
                    + " / "
                    + (
                        error.message
                        || "알 수 없는 오류"
                    );
            }

            /*
            매수 / 매도 관리는 하단 "거래" 탭에서 통합 관리합니다.
            포트폴리오 화면은 계좌 요약과 보유현황에 집중합니다.
            */

            /*
            입금 / 출금 관리는 하단 "거래" 탭에서 통합 관리합니다.
            */
            
        } catch (error) {

            targetsList.className =
                "error";

            targetsList.textContent =
                error.message
                || "목표 비중을 불러오지 못했습니다.";
        }
    }
}

/*
미국 종목 검색 / 등록
*/

const usAssetSearchForm =
    document.getElementById(
        "us-asset-search-form"
    );

const usAssetTickerInput =
    document.getElementById(
        "us-asset-ticker"
    );

const usAssetSearchButton =
    document.getElementById(
        "us-asset-search-button"
    );

const usAssetSearchResult =
    document.getElementById(
        "us-asset-search-result"
    );


async function registerUsAsset(
    accessToken,
    ticker
) {
    const cleanTicker =
        String(
            ticker || ""
        )
        .trim()
        .toUpperCase();

    if (!cleanTicker) {
        throw new Error(
            "등록할 미국 종목이 없습니다."
        );
    }

    return await apiRequest(
        "/api/assets/us/"
        + encodeURIComponent(
            cleanTicker
        )
        + "/register",
        accessToken,
        {
            method: "POST",
        }
    );
}


function renderUsAssetSearchResult(
    asset,
    accessToken
) {
    usAssetSearchResult.innerHTML = "";

    const resultBox =
        document.createElement(
            "div"
        );

    resultBox.className =
        "settings-summary";


    const title =
        document.createElement(
            "div"
        );

    title.style.fontWeight =
        "700";

    title.style.fontSize =
        "16px";

    title.textContent =
        asset.name
        + " ("
        + asset.ticker
        + ")";

    resultBox.appendChild(
        title
    );


    resultBox.appendChild(
        createDetail(
            "시장: "
            + asset.market
        )
    );

    resultBox.appendChild(
        createDetail(
            "거래소: "
            + asset.exchange
        )
    );

    resultBox.appendChild(
        createDetail(
            "자산 유형: "
            + asset.asset_type
        )
    );

    resultBox.appendChild(
        createDetail(
            "통화: "
            + asset.currency
        )
    );


    const registerButton =
        document.createElement(
            "button"
        );

    registerButton.type =
        "button";

    registerButton.textContent =
        "이 종목 등록";


    const registerMessage =
        document.createElement(
            "div"
        );

    registerMessage.className =
        "transaction-message";


    registerButton.addEventListener(
        "click",
        async () => {

            registerButton.disabled =
                true;

            registerButton.textContent =
                "등록 중...";

            registerMessage.textContent =
                "";

            registerMessage.className =
                "transaction-message";


            try {

                const response =
                    await registerUsAsset(
                        accessToken,
                        asset.ticker
                    );


                if (
                    !response.registered
                    || !response.asset
                ) {
                    throw new Error(
                        "종목 등록에 실패했습니다."
                    );
                }


                const savedAsset =
                    response.asset;


                registerMessage.textContent =
                    savedAsset.name
                    + " ("
                    + savedAsset.ticker
                    + ") 등록이 완료되었습니다.";

                registerMessage.className =
                    "transaction-message success";


                registerButton.textContent =
                    "등록 완료";

                /*
                이미 등록된 자산을 다시 눌러
                불필요하게 반복 요청하지 않도록
                현재 화면에서는 버튼을 비활성화합니다.

                서버의 save_etf_master()도
                같은 ticker가 있으면 INSERT가 아니라
                UPDATE하므로 중복 행은 생성되지 않습니다.
                */
                registerButton.disabled =
                    true;


            } catch (error) {

                registerMessage.textContent =
                    error.message
                    || "종목 등록에 실패했습니다.";

                registerMessage.className =
                    "transaction-message error";

                registerButton.disabled =
                    false;

                registerButton.textContent =
                    "이 종목 등록";
            }
        }
    );


    resultBox.appendChild(
        registerButton
    );

    resultBox.appendChild(
        registerMessage
    );


    usAssetSearchResult.appendChild(
        resultBox
    );

    usAssetSearchResult.className =
        "transaction-message";
}


usAssetSearchForm.addEventListener(
    "submit",
    async (event) => {

        event.preventDefault();

        const accessToken =
            localStorage.getItem(
                "access_token"
            );

        if (!accessToken) {

            usAssetSearchResult.textContent =
                "다시 로그인해주세요.";

            usAssetSearchResult.className =
                "transaction-message error";

            return;
        }


        const ticker =
            usAssetTickerInput
            .value
            .trim()
            .toUpperCase();


        if (!ticker) {

            usAssetSearchResult.textContent =
                "미국 종목 티커를 입력해주세요.";

            usAssetSearchResult.className =
                "transaction-message error";

            return;
        }


        usAssetTickerInput.value =
            ticker;

        usAssetSearchButton.disabled =
            true;

        usAssetSearchButton.textContent =
            "검색 중...";

        usAssetSearchResult.textContent =
            "Yahoo Finance에서 종목 정보를 확인하고 있습니다.";

        usAssetSearchResult.className =
            "transaction-message";


        try {

            const response =
                await lookupUsAsset(
                    accessToken,
                    ticker
                );


            if (
                !response.found
                || !response.asset
            ) {
                throw new Error(
                    "종목 정보를 찾지 못했습니다."
                );
            }


            renderUsAssetSearchResult(
                response.asset,
                accessToken
            );


        } catch (error) {

            usAssetSearchResult.textContent =
                error.message
                || "미국 종목 검색에 실패했습니다.";

            usAssetSearchResult.className =
                "transaction-message error";


        } finally {

            usAssetSearchButton.disabled =
                false;

            usAssetSearchButton.textContent =
                "종목 검색";
        }
    }
);

/*
투자성향 저장
*/

const investmentProfileForm =
    document.getElementById(
        "investment-profile-form"
    );


investmentProfileForm.addEventListener(
    "submit",
    async (event) => {

        event.preventDefault();

        const profileMessage =
            document.getElementById(
                "investment-profile-message"
            );

        const accessToken =
            localStorage.getItem(
                "access_token"
            );

        if (!accessToken) {

            profileMessage.textContent =
                "다시 로그인해주세요.";

            profileMessage.className =
                "transaction-message error";

            return;
        }


        const horizonValue =
            document.getElementById(
                "investment-horizon"
            ).value;


        const payload = {

            risk_profile:
                document.getElementById(
                    "risk-profile"
                ).value,

            investment_horizon_years:
                horizonValue
                ? Number(
                    horizonValue
                )
                : null,

            /*
            사용자 전체 월 투자금은 더 이상 사용하지
            않습니다. DB 호환성을 위해 0으로 저장합니다.
            */
            monthly_investment: 0,

            ai_advice_style:
                document.getElementById(
                    "ai-advice-style"
                ).value,

            ai_advice_enabled:
                document.getElementById(
                    "ai-advice-enabled"
                ).checked,

            investment_preference_text:
                document.getElementById(
                    "investment-preference-text"
                ).value.trim(),
        };


        profileMessage.textContent =
            "저장 중...";

        profileMessage.className =
            "transaction-message";


        try {

            const result =
                await saveInvestmentProfile(
                    accessToken,
                    payload
                );

            if (!result.saved) {

                throw new Error(
                    "저장에 실패했습니다."
                );
            }

            profileMessage.textContent =
                "투자전략이 저장되었습니다.";

            profileMessage.className =
                "transaction-message success";

        } catch (error) {

            profileMessage.textContent =
                error.message
                || "투자전략을 저장하지 못했습니다.";

            profileMessage.className =
                "transaction-message error";
        }
    }
);


/*
로그인 및 로그인 상태 유지
*/

const adminEmailTestButton = document.getElementById("admin-email-test-button");
const adminEmailTestResult = document.getElementById("admin-email-test-result");
if (adminEmailTestButton && adminEmailTestResult) {
    adminEmailTestButton.addEventListener("click", () =>
        runAdminEmailDiagnostic(adminEmailTestButton, adminEmailTestResult)
    );
}


function saveAuthTokens(
    accessToken,
    refreshToken
) {
    const safeAccessToken =
        accessToken || "";

    const safeRefreshToken =
        refreshToken || "";


    localStorage.setItem(
        "access_token",
        safeAccessToken
    );

    localStorage.setItem(
        "refresh_token",
        safeRefreshToken
    );
}


function clearAuthTokens() {

    localStorage.removeItem(
        "access_token"
    );

    localStorage.removeItem(
        "refresh_token"
    );
}


const logoutButton = document.getElementById("logout-button");
logoutButton.addEventListener("click", () => {
    clearAuthTokens();
    memberManagementTabButton.hidden = true;
    adminSection.hidden = true;
    transactionTabAccounts = [];
    transactionTabAccessToken = "";
    transactionTabRows = [];
    transactionTabVisibleCount = 20;
    cashFlowVisibleCounts.clear();
    transactionAccountFilter.innerHTML = '<option value="">전체 계좌</option>';
    transactionTypeFilter.value = "";
    transactionSearchFilter.value = "";
    allTransactionsList.innerHTML = "";
    allCashFlowsList.innerHTML = "";
    accountsList.innerHTML = "";
    accountCreator.innerHTML = "";
    accountManagementList.innerHTML = "";
    adminMembers.innerHTML = "불러오는 중...";
    usAssetTickerInput.value = "";
    usAssetSearchResult.innerHTML = "";
    usAssetSearchResult.className = "transaction-message";
    morningReportSettingsMessage.textContent = "";
    kakaoStatus.textContent = "연결 상태 확인 중...";
    kakaoStatus.className = "status-box";
    kakaoTestButton.style.display = "none";
    kakaoDisconnectButton.style.display = "none";
    kakaoConnectButton.textContent = "카카오톡 연결";
    document.getElementById("risk-profile").value = "balanced";
    document.getElementById("investment-horizon").value = "";
    document.getElementById("ai-advice-style").value = "balanced";
    document.getElementById("ai-advice-enabled").checked = true;
    document.getElementById("investment-preference-text").value = "";
    document.getElementById("investment-profile-message").textContent = "";
    const reportSection = document.getElementById("report-section");
    const reportFrame = document.getElementById("report-frame");
    const reportMessage = document.getElementById("report-message");
    reportFrame.srcdoc = "";
    reportFrame.style.display = "none";
    reportMessage.textContent = "모닝 리포트를 불러오는 중...";
    reportMessage.className = "status-box";
    reportMessage.style.display = "block";
    reportSection.style.display = "none";
    activeSettingsPanel = "accounts";
    setAppTab("home", {scroll: false});
    appArea.style.display = "none";
    loginCard.style.display = "block";
    loginStatus.textContent = "로그인 완료";
    loginForm.reset();
    message.textContent = "";
    window.scrollTo({top: 0, behavior: "smooth"});
});


async function showAuthenticatedApp(
    accessToken
) {
    const user =
        await verifyUser(
            accessToken
        );


    const bootstrapResponse =
        await fetch(
            "/api/bootstrap",
            {
                method: "POST",
                headers: {
                    "Authorization":
                        "Bearer "
                        + accessToken,
                },
            }
        );

    if (!bootstrapResponse.ok) {
        let detail =
            "사용자 초기 설정을 준비하지 못했습니다.";

        try {
            const bootstrapData =
                await bootstrapResponse.json();

            detail =
                bootstrapData.detail
                || detail;
        } catch (error) {}

        throw new Error(detail);
    }


    const [
        accounts,
        investmentProfile
    ] = await Promise.all([

        loadAccounts(
            accessToken
        ),

        loadInvestmentProfile(
            accessToken
        ),
    ]);


    if (investmentProfile) {

        document.getElementById(
            "risk-profile"
        ).value =
            investmentProfile
            .risk_profile
            || "balanced";


        document.getElementById(
            "investment-horizon"
        ).value =
            investmentProfile
            .investment_horizon_years
            ?? "";


        document.getElementById(
            "ai-advice-style"
        ).value =
            investmentProfile
            .ai_advice_style
            || "balanced";


        document.getElementById(
            "ai-advice-enabled"
        ).checked =
            investmentProfile
            .ai_advice_enabled
            !== false;


        document.getElementById(
            "investment-preference-text"
        ).value =
            investmentProfile
            .investment_preference_text
            || "";
    }


    await renderAccounts(
        accounts,
        accessToken
    );
    await renderAccountCreator(accounts, accessToken);
    await renderAccountManagement(accounts, accessToken);

    try {
        await loadTransactionTab(accounts, accessToken);
    } catch (error) {
        allTransactionsList.className = "error";
        allTransactionsList.textContent = error.message || "전체 거래 내역을 불러오지 못했습니다.";
    }

    try {
        await loadAdminPanel(accessToken);
    } catch (error) {
        console.error("관리자 화면 로딩 오류:", error);
        memberManagementTabButton.hidden = true;
        adminSection.hidden = true;
    }

    try {
        await loadMorningReportSettings(accessToken);
    } catch (error) {
        morningReportSettingsMessage.textContent = error.message || "모닝 리포트 설정을 불러오지 못했습니다.";
    }

    try {
        await loadKakaoStatus(accessToken);
    } catch (error) {
        kakaoStatus.textContent = error.message || "카카오 연결 상태를 확인하지 못했습니다.";
        kakaoStatus.className = "status-box error";
    }


    loginStatus.textContent =
        "로그인 완료 · "
        + (
            user.email
            || "사용자"
        )
        + " · 등록된 계좌 "
        + accounts.length
        + "개";


    loginCard.style.display =
        "none";


    appArea.style.display =
        "flex";

    if (!reportRequested) {
        setAppTab("home", {scroll: false});
    }

    if (reportRequested) {
        document.getElementById("kakao-settings-section").style.display = "none";
        document.getElementById("investment-settings-section").style.display = "none";
        document.getElementById("asset-search-section").style.display = "none";
        document.getElementById("portfolio-section").style.display = "none";
        await showPrivateReport(accessToken);
    }


    /*
    앱 영역을 먼저 표시한 뒤
    직접 연결된 종목으로 이동합니다.
    */
    openLinkedAssetChart();
}


async function refreshLoginSession(
    refreshToken
) {
    if (!refreshToken) {
        return null;
    }


    const response =
        await fetch(
            SUPABASE_URL
            + "/auth/v1/token"
            + "?grant_type=refresh_token",
            {
                method:
                    "POST",

                headers: {
                    "Content-Type":
                        "application/json",

                    "apikey":
                        SUPABASE_KEY,
                },

                body:
                    JSON.stringify({
                        refresh_token:
                            refreshToken,
                    }),
            }
        );


    const data =
        await response.json();


    if (
        !response.ok
        || !data.access_token
    ) {
        return null;
    }


    saveAuthTokens(
        data.access_token,
        data.refresh_token
        || refreshToken
    );


    return data.access_token;
}


async function restoreLoginSession() {

    const savedAccessToken =
        localStorage.getItem(
            "access_token"
        );


    const savedRefreshToken =
        localStorage.getItem(
            "refresh_token"
        );


    console.log(
        "자동 로그인 확인:",
        {
            hasAccessToken:
                Boolean(
                    savedAccessToken
                ),

            hasRefreshToken:
                Boolean(
                    savedRefreshToken
                ),
        }
    );


    if (
        !savedAccessToken
        && !savedRefreshToken
    ) {

        console.log(
            "저장된 로그인 정보가 없습니다."
        );

        return;
    }


    message.textContent =
        "로그인 상태를 확인하고 있습니다.";

    message.className = "";


    let accessToken =
        savedAccessToken;


    /*
    1단계:
    저장된 access token 자체가
    유효한지만 먼저 확인합니다.

    계좌 로딩이나 화면 렌더링 오류를
    인증 실패로 판단하지 않습니다.
    */
    if (accessToken) {

        try {

            await verifyUser(
                accessToken
            );


            console.log(
                "저장된 access token이 유효합니다."
            );


        } catch (error) {

            console.log(
                "access token 확인 실패. "
                + "refresh token을 사용합니다."
            );


            accessToken =
                null;
        }
    }


    /*
    2단계:
    access token이 없거나 만료된 경우에만
    refresh token으로 새 access token을 받습니다.
    */
    if (!accessToken) {

        if (!savedRefreshToken) {

            clearAuthTokens();


            message.textContent =
                "로그인 시간이 만료되었습니다. 다시 로그인해주세요.";

            message.className =
                "error";


            return;
        }


        try {

            accessToken =
                await refreshLoginSession(
                    savedRefreshToken
                );


        } catch (error) {

            console.error(
                "로그인 갱신 오류:",
                error
            );


            accessToken =
                null;
        }


        if (!accessToken) {

            clearAuthTokens();


            message.textContent =
                "로그인 시간이 만료되었습니다. 다시 로그인해주세요.";

            message.className =
                "error";


            return;
        }


        console.log(
            "refresh token으로 로그인 상태를 갱신했습니다."
        );
    }


    /*
    갱신 과정에서 refresh token이 회전했을 수 있으므로
    영구 로그인 저장소의 최신 토큰 쌍을 유지합니다.
    */
    const currentRefreshToken =
        localStorage.getItem(
            "refresh_token"
        )
        || savedRefreshToken
        || "";


    saveAuthTokens(
        accessToken,
        currentRefreshToken
    );


    /*
    3단계:
    인증 성공 이후에 앱 데이터를 불러옵니다.

    여기서 오류가 발생해도 인증 토큰을
    삭제하지 않습니다.
    */
    try {

        await showAuthenticatedApp(
            accessToken
        );


        message.textContent = "";


        console.log(
            "자동 로그인 완료"
        );


    } catch (error) {

        console.error(
            "자동 로그인 후 앱 로딩 오류:",
            error
        );


        message.textContent =
            "로그인은 유지되어 있지만 "
            + "포트폴리오를 불러오지 못했습니다. "
            + "페이지를 다시 열어주세요.";

        message.className =
            "error";
    }
}

async function refreshSignupAvailability() {
    try {
        const response = await fetch("/api/signup-status");
        const data = await response.json();
        const enabled = response.ok && Boolean(data.signup_enabled);
        showSignupButton.style.display = enabled ? "block" : "none";
        if (!enabled) signupForm.style.display = "none";
    } catch (_) {
        showSignupButton.style.display = "none";
        signupForm.style.display = "none";
    }
}

showSignupButton.addEventListener("click", () => {
    const opening = signupForm.style.display === "none";
    signupForm.style.display = opening ? "block" : "none";
    showSignupButton.textContent = opening ? "회원가입 닫기" : "회원가입";
    message.textContent = "";
    message.className = "";
});

signupForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    message.textContent = "";
    message.className = "";
    signupButton.disabled = true;
    signupButton.textContent = "가입 중...";
    const email = document.getElementById("signup-email").value.trim();
    const password = document.getElementById("signup-password").value;
    try {
        const response = await fetch("/api/auth/signup", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({email, password}),
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "회원가입에 실패했습니다.");
        if (data.access_token) {
            saveAuthTokens(data.access_token, data.refresh_token || "");
            await showAuthenticatedApp(data.access_token);
            message.textContent = "";
            return;
        }
        document.getElementById("email").value = email;
        signupForm.style.display = "none";
        showSignupButton.textContent = "회원가입";
        message.textContent = "회원가입이 완료되었습니다.";
        message.className = "success";
    } catch (error) {
        message.textContent = error.message || "회원가입에 실패했습니다.";
        message.className = "error";
        await refreshSignupAvailability();
    } finally {
        signupButton.disabled = false;
        signupButton.textContent = "회원가입";
    }
});

refreshSignupAvailability();

loginForm.addEventListener(
    "submit",
    async (event) => {

        event.preventDefault();


        message.textContent = "";
        message.className = "";


        loginButton.disabled =
            true;


        loginButton.textContent =
            "로그인 중...";


        const email =
            document.getElementById(
                "email"
            ).value.trim();


        const password =
            document.getElementById(
                "password"
            ).value;


        let authenticated = false;

        try {

            const response =
                await fetch(
                    SUPABASE_URL
                    + "/auth/v1/token"
                    + "?grant_type=password",
                    {
                        method:
                            "POST",

                        headers: {
                            "Content-Type":
                                "application/json",

                            "apikey":
                                SUPABASE_KEY,
                        },

                        body:
                            JSON.stringify({
                                email:
                                    email,

                                password:
                                    password,
                            }),
                    }
                );


            const data =
                await response.json();


            if (
                !response.ok
                || !data.access_token
            ) {

                throw new Error(
                    data.error_description
                    || data.msg
                    || "로그인에 실패했습니다."
                );
            }


            saveAuthTokens(
                data.access_token,
                data.refresh_token
                || ""
            );


            authenticated = true;

            loginButton.textContent =
                "계좌 확인 중...";


            await showAuthenticatedApp(
                data.access_token
            );


        } catch (error) {

            if (!authenticated) {
                clearAuthTokens();
            }

            console.error(authenticated ? "로그인 후 앱 로딩 오류:" : "로그인 오류:", error);


            message.textContent = authenticated
                ? "로그인은 성공했지만 포트폴리오를 불러오지 못했습니다. 잠시 후 다시 시도해주세요."
                : (error.message || "로그인에 실패했습니다.");


            message.className =
                "error";


        } finally {

            loginButton.disabled =
                false;


            loginButton.textContent =
                "로그인";
        }
    }
);


/*
페이지를 새로 열었을 때
저장된 Supabase 세션으로 자동 로그인합니다.
*/
async function loadPublicSignupStatus() {
    try {
        const response = await fetch("/api/signup-status");
        const data = await response.json();
        const enabled = response.ok && Boolean(data.signup_enabled);
        showSignupButton.style.display = enabled ? "block" : "none";
        if (!enabled) signupForm.style.display = "none";
    } catch (error) {
        showSignupButton.style.display = "none";
    }
}


/* HTML account pickers avoid native iOS option-sheet contrast bugs. */
function installAccountPicker(select) {
    const host = document.createElement("div");
    host.className = "account-picker-host";
    select.parentNode.insertBefore(host, select);
    host.appendChild(select);
    const trigger = document.createElement("button");
    trigger.type = "button";
    trigger.className = "account-picker-button";
    trigger.setAttribute("aria-label", select.getAttribute("aria-label") || "계좌 선택");
    trigger.setAttribute("aria-expanded", "false");
    const menu = document.createElement("div");
    menu.className = "account-picker-options";
    menu.hidden = true;
    host.append(trigger, menu);

    function close() {
        menu.hidden = true;
        trigger.setAttribute("aria-expanded", "false");
    }
    function sync() {
        const selected = select.selectedOptions[0] || select.options[0];
        trigger.textContent = (selected ? selected.textContent : "계좌를 선택하세요") + " ▾";
        menu.replaceChildren();
        Array.from(select.options).forEach((option) => {
            const item = document.createElement("button");
            item.type = "button";
            item.textContent = option.textContent;
            item.disabled = option.disabled;
            item.setAttribute("aria-selected", String(option.value === select.value));
            item.addEventListener("click", () => {
                select.value = option.value;
                close();
                sync();
                select.dispatchEvent(new Event("change", {bubbles: true}));
            });
            menu.appendChild(item);
        });
    }
    trigger.addEventListener("click", () => {
        sync();
        menu.hidden = !menu.hidden;
        trigger.setAttribute("aria-expanded", String(!menu.hidden));
    });
    document.addEventListener("click", (event) => {
        if (!host.contains(event.target)) close();
    });
    select.addEventListener("change", sync);
    new MutationObserver(sync).observe(select, {childList: true, subtree: true, characterData: true});
    sync();
    return sync;
}
const accountPickerSyncs = [
    "transaction-account-filter",
    "transaction-entry-account",
    "cash-flow-entry-account"
].map((id) => installAccountPicker(document.getElementById(id)));

loadPublicSignupStatus();

restoreLoginSession().finally(() => {
    bootScreen.style.display = "none";

    if (appArea.style.display === "none" || !appArea.style.display) {
        loginCard.style.display = "block";
    }
});

</script>

</body>

</html>
    """

    html = html.replace(
        "__SUPABASE_URL_JSON__",
        json.dumps(supabase_url),
    )

    html = html.replace(
        "__SUPABASE_KEY_JSON__",
        json.dumps(supabase_key),
    )

    return HTMLResponse(
        content=html,
        headers={
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Permissions-Policy": (
                "camera=(), microphone=(), geolocation=(), "
                "payment=(), usb=()"
            ),
            "Content-Security-Policy": (
                "default-src 'none'; "
                "style-src 'unsafe-inline'; "
                "script-src 'unsafe-inline'; "
                "connect-src 'self' https:; "
                "img-src 'self' data: https:; "
                "font-src 'self' data:; "
                "frame-ancestors 'none'; "
                "base-uri 'none'; "
                "form-action 'self'"
            ),
        },
    )
