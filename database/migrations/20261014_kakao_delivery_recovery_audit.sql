-- Preparation only. Do not apply to production without migration review.
-- Append-only operator recovery review evidence. A review never authorizes
-- sending: claim_kakao_delivery_attempt continues blocking historical attempts.
CREATE TABLE IF NOT EXISTS public.kakao_delivery_recovery_audit (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    actor_id uuid NOT NULL REFERENCES public.profiles(id),
    target_user_id uuid NOT NULL REFERENCES public.profiles(id),
    attempt_id uuid NOT NULL REFERENCES public.kakao_delivery_attempts(attempt_id),
    reviewed_at timestamptz NOT NULL,
    evidence_reference text NOT NULL CHECK (
        length(btrim(evidence_reference)) BETWEEN 1 AND 256
    ),
    decision text NOT NULL CHECK (
        decision IN ('denied', 'eligible_for_future_recovery')
    ),
    reason text NOT NULL CHECK (length(reason) BETWEEN 1 AND 512),
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT kakao_delivery_recovery_same_user CHECK (actor_id = target_user_id),
    CONSTRAINT kakao_delivery_recovery_attempt_owner_fk
        FOREIGN KEY (target_user_id, attempt_id)
        REFERENCES public.kakao_delivery_attempts(user_id, attempt_id)
);

CREATE INDEX IF NOT EXISTS kakao_delivery_recovery_audit_target_idx
ON public.kakao_delivery_recovery_audit (target_user_id, created_at DESC);

ALTER TABLE public.kakao_delivery_recovery_audit ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.kakao_delivery_recovery_audit FROM PUBLIC, anon, authenticated;
REVOKE ALL ON SEQUENCE public.kakao_delivery_recovery_audit_id_seq FROM PUBLIC, anon, authenticated;

-- Even trusted application code must not edit or erase audit history.
-- A separate DBA-controlled migration is required for retention changes.
CREATE OR REPLACE FUNCTION public.reject_kakao_recovery_audit_mutation()
RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path = ''
AS $$
BEGIN
    RAISE EXCEPTION 'recovery audit records are append-only';
END;
$$;
CREATE TRIGGER kakao_recovery_audit_immutable
BEFORE UPDATE OR DELETE ON public.kakao_delivery_recovery_audit
FOR EACH ROW EXECUTE FUNCTION public.reject_kakao_recovery_audit_mutation();
REVOKE ALL ON FUNCTION public.reject_kakao_recovery_audit_mutation()
FROM PUBLIC, anon, authenticated;
