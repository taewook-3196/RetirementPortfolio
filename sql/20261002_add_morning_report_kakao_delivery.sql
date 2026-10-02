-- Task 13: distinguish report generation from successful Kakao delivery.
ALTER TABLE public.morning_reports
    ADD COLUMN IF NOT EXISTS kakao_sent_at timestamptz NULL;

COMMENT ON COLUMN public.morning_reports.kakao_sent_at IS
    'Timestamp set only after the user-specific Kakao morning report is successfully delivered.';
