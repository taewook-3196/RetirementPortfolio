-- Keep application-wide settings server-managed even though public is an exposed schema.
-- The application backend uses the privileged database connection; browser clients need no direct access.
ALTER TABLE public.app_settings ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.app_settings FROM anon, authenticated;
