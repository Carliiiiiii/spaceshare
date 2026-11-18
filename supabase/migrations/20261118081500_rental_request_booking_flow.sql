-- Pending rental requests have seven days to receive an owner response.
-- Existing pending requests receive a fresh seven-day deadline when this
-- migration is first applied.

ALTER TABLE public.rental_requests
    ADD COLUMN IF NOT EXISTS created_at timestamptz,
    ADD COLUMN IF NOT EXISTS expires_at timestamptz;

UPDATE public.rental_requests
SET created_at = COALESCE(created_at, now()),
    expires_at = COALESCE(
        expires_at,
        COALESCE(created_at, now()) + interval '7 days'
    )
WHERE created_at IS NULL OR expires_at IS NULL;

ALTER TABLE public.rental_requests
    ALTER COLUMN created_at SET DEFAULT now(),
    ALTER COLUMN created_at SET NOT NULL,
    ALTER COLUMN expires_at SET DEFAULT now() + interval '7 days',
    ALTER COLUMN expires_at SET NOT NULL;

CREATE INDEX IF NOT EXISTS rental_requests_pending_expiry_idx
    ON public.rental_requests (expires_at)
    WHERE status = 'pending';
