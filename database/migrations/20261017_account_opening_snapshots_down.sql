-- DESTRUCTIVE: removes all opening snapshot rows. Back up first.
-- Only run after explicit rollback approval; never run automatically.
BEGIN;
DROP TABLE IF EXISTS account_opening_holdings;
DROP TABLE IF EXISTS account_opening_snapshots;
COMMIT;
