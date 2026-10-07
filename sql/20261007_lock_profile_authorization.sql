-- Release audit: application authorization fields are server-managed.
-- Browser-authenticated users may read their own profile, but must never be
-- able to promote themselves to admin or reactivate a suspended account.

drop policy if exists "profiles_owner_all" on public.profiles;
drop policy if exists "Users can insert their own profile" on public.profiles;
drop policy if exists "Users can update their own profile" on public.profiles;

-- Keep the existing owner-only SELECT policy if present.
drop policy if exists "Users can view their own profile" on public.profiles;
create policy "Users can view their own profile"
on public.profiles
for select
to authenticated
using ((select auth.uid()) = id);

revoke insert, update, delete on table public.profiles from authenticated;
revoke all on table public.profiles from anon;
grant select on table public.profiles to authenticated;
