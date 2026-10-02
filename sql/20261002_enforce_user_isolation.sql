-- Task 12: defense-in-depth RLS for all user-owned portfolio data.
-- Run once in Supabase SQL Editor before merging Task 12.

alter table public.profiles enable row level security;
alter table public.accounts enable row level security;
alter table public.account_targets enable row level security;
alter table public.cash_flows enable row level security;
alter table public.transactions enable row level security;
alter table public.dividends enable row level security;
alter table public.investment_profiles enable row level security;
alter table public.watchlists enable row level security;
alter table public.user_settings enable row level security;
alter table public.recommendation_logs enable row level security;

drop policy if exists "profiles_owner_all" on public.profiles;
create policy "profiles_owner_all" on public.profiles
for all to authenticated using ((select auth.uid()) = id)
with check ((select auth.uid()) = id);

drop policy if exists "accounts_owner_all" on public.accounts;
create policy "accounts_owner_all" on public.accounts
for all to authenticated using ((select auth.uid()) = user_id)
with check ((select auth.uid()) = user_id);

drop policy if exists "investment_profiles_owner_all" on public.investment_profiles;
create policy "investment_profiles_owner_all" on public.investment_profiles
for all to authenticated using ((select auth.uid()) = user_id)
with check ((select auth.uid()) = user_id);

drop policy if exists "watchlists_owner_all" on public.watchlists;
create policy "watchlists_owner_all" on public.watchlists
for all to authenticated using ((select auth.uid()) = user_id)
with check ((select auth.uid()) = user_id);

drop policy if exists "user_settings_owner_all" on public.user_settings;
create policy "user_settings_owner_all" on public.user_settings
for all to authenticated using ((select auth.uid()) = user_id)
with check ((select auth.uid()) = user_id);

drop policy if exists "recommendation_logs_owner_all" on public.recommendation_logs;
create policy "recommendation_logs_owner_all" on public.recommendation_logs
for all to authenticated using ((select auth.uid()) = user_id)
with check ((select auth.uid()) = user_id);

drop policy if exists "account_targets_owner_all" on public.account_targets;
create policy "account_targets_owner_all" on public.account_targets
for all to authenticated
using (exists (
    select 1 from public.accounts a
    where a.id = account_targets.account_id
      and a.user_id = (select auth.uid())
))
with check (exists (
    select 1 from public.accounts a
    where a.id = account_targets.account_id
      and a.user_id = (select auth.uid())
));

drop policy if exists "cash_flows_owner_all" on public.cash_flows;
create policy "cash_flows_owner_all" on public.cash_flows
for all to authenticated
using (exists (
    select 1 from public.accounts a
    where a.id = cash_flows.account_id
      and a.user_id = (select auth.uid())
))
with check (exists (
    select 1 from public.accounts a
    where a.id = cash_flows.account_id
      and a.user_id = (select auth.uid())
));

drop policy if exists "transactions_owner_all" on public.transactions;
create policy "transactions_owner_all" on public.transactions
for all to authenticated
using (exists (
    select 1 from public.accounts a
    where a.id = transactions.account_id
      and a.user_id = (select auth.uid())
))
with check (exists (
    select 1 from public.accounts a
    where a.id = transactions.account_id
      and a.user_id = (select auth.uid())
));

drop policy if exists "dividends_owner_all" on public.dividends;
create policy "dividends_owner_all" on public.dividends
for all to authenticated
using (exists (
    select 1 from public.accounts a
    where a.id = dividends.account_id
      and a.user_id = (select auth.uid())
))
with check (exists (
    select 1 from public.accounts a
    where a.id = dividends.account_id
      and a.user_id = (select auth.uid())
));

revoke all on public.profiles, public.accounts, public.account_targets,
    public.cash_flows, public.transactions, public.dividends,
    public.investment_profiles, public.watchlists, public.user_settings,
    public.recommendation_logs from anon;
