-- Release audit: the production web client talks to FastAPI, not directly to
-- Supabase Data API. Keep authentication public, but make application data
-- server-only so a still-valid JWT cannot bypass membership suspension.
-- RLS remains enabled as defense in depth.

revoke all on table public.profiles from anon, authenticated;
revoke all on table public.accounts from anon, authenticated;
revoke all on table public.account_targets from anon, authenticated;
revoke all on table public.transactions from anon, authenticated;
revoke all on table public.cash_flows from anon, authenticated;
revoke all on table public.dividends from anon, authenticated;
revoke all on table public.investment_profiles from anon, authenticated;
revoke all on table public.watchlists from anon, authenticated;
revoke all on table public.user_settings from anon, authenticated;
revoke all on table public.recommendation_logs from anon, authenticated;
revoke all on table public.morning_reports from anon, authenticated;
revoke all on table public.kakao_credentials from anon, authenticated;
revoke all on table public.deleted_members from anon, authenticated;
revoke all on table public.app_settings from anon, authenticated;
revoke all on table public.asset_master from anon, authenticated;
revoke all on table public.prices from anon, authenticated;
revoke all on table public.exchange_rates from anon, authenticated;
revoke all on table public.news from anon, authenticated;
