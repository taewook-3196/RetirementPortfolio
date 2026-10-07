-- Apply before deploying request-id write code.
ALTER TABLE public.transactions ADD COLUMN IF NOT EXISTS request_id text;
ALTER TABLE public.cash_flows ADD COLUMN IF NOT EXISTS request_id text;
CREATE UNIQUE INDEX IF NOT EXISTS ux_transactions_request_id ON public.transactions (request_id) WHERE request_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_cash_flows_request_id ON public.cash_flows (request_id) WHERE request_id IS NOT NULL;
