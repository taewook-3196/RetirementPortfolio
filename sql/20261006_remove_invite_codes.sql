-- Obsolete invitation-email workflow cleanup.
-- Run after the application no longer uses invitation codes.
DROP TABLE IF EXISTS invite_codes;
