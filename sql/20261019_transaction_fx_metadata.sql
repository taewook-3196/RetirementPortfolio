-- Optional transaction metadata; apply to Supabase before using the new ORM fields.
ALTER TABLE public.transactions ADD COLUMN IF NOT EXISTS execution_fx_rate NUMERIC;
ALTER TABLE public.transactions ADD COLUMN IF NOT EXISTS settlement_amount NUMERIC;
ALTER TABLE public.transactions ADD COLUMN IF NOT EXISTS settlement_currency TEXT;
ALTER TABLE public.transactions ADD COLUMN IF NOT EXISTS fx_source TEXT;
-- Legacy transaction values are not backfilled.
