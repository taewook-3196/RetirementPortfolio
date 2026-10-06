-- Membership controls: public signup gate and per-member access status.
ALTER TABLE profiles
ADD COLUMN IF NOT EXISTS is_active boolean NOT NULL DEFAULT true;

CREATE TABLE IF NOT EXISTS app_settings (
    key varchar(100) PRIMARY KEY,
    value text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO app_settings (key, value)
VALUES ('signup_enabled', 'false')
ON CONFLICT (key) DO NOTHING;

COMMENT ON COLUMN profiles.is_active IS 'Application access flag controlled by administrators.';
COMMENT ON TABLE app_settings IS 'Server-managed application-wide settings.';
