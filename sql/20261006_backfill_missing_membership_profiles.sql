-- Ensure every existing Supabase Auth user has an application membership profile.
-- Existing users are preserved as active non-admin members unless a profile already exists.
INSERT INTO public.profiles (id, is_admin, is_active, created_at, updated_at)
SELECT
    u.id,
    FALSE,
    TRUE,
    COALESCE(u.created_at, NOW()),
    NOW()
FROM auth.users AS u
LEFT JOIN public.profiles AS p ON p.id = u.id
WHERE p.id IS NULL
ON CONFLICT (id) DO NOTHING;
