-- Task 14 step 1: explicit application administrator role.
-- Admin permission is intentionally separate from portfolio ownership.
-- Existing users remain non-admin until explicitly promoted.

alter table public.profiles
    add column if not exists is_admin boolean not null default false;

create index if not exists idx_profiles_is_admin
    on public.profiles (is_admin)
    where is_admin = true;

comment on column public.profiles.is_admin is
    'Application membership administrator only; does not grant access to other users portfolio data.';
