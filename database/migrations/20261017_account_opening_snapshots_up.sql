-- Manual migration only. Do NOT run automatically on app startup.
-- Requires reviewed production backup and explicit approval.
BEGIN;

CREATE TABLE IF NOT EXISTS account_opening_snapshots (
    id BIGSERIAL PRIMARY KEY,
    account_id BIGINT NOT NULL UNIQUE REFERENCES accounts(id) ON DELETE CASCADE,
    opening_date DATE NOT NULL,
    currency TEXT NOT NULL CHECK (currency IN ('KRW', 'USD')),
    cash_amount NUMERIC NOT NULL CHECK (cash_amount >= 0),
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'confirmed')),
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_account_opening_snapshots_account_id
    ON account_opening_snapshots(account_id);

CREATE TABLE IF NOT EXISTS account_opening_holdings (
    id BIGSERIAL PRIMARY KEY,
    opening_snapshot_id BIGINT NOT NULL REFERENCES account_opening_snapshots(id) ON DELETE CASCADE,
    ticker TEXT NOT NULL,
    quantity NUMERIC NOT NULL CHECK (quantity >= 0),
    market_value NUMERIC NOT NULL CHECK (market_value >= 0),
    CONSTRAINT uq_account_opening_holdings_snapshot_ticker
        UNIQUE (opening_snapshot_id, ticker)
);

CREATE INDEX IF NOT EXISTS ix_account_opening_holdings_opening_snapshot_id
    ON account_opening_holdings(opening_snapshot_id);

COMMIT;
