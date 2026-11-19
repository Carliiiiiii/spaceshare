-- Personal saved listings. Apply this migration to the hosted project before
-- deploying the corresponding app code.

DO $$
DECLARE
    listing_id_type text;
    user_id_type text;
BEGIN
    SELECT format_type(attribute.atttypid, attribute.atttypmod)
      INTO listing_id_type
      FROM pg_attribute AS attribute
     WHERE attribute.attrelid = 'public.listings'::regclass
       AND attribute.attname = 'id'
       AND NOT attribute.attisdropped;

    SELECT format_type(attribute.atttypid, attribute.atttypmod)
      INTO user_id_type
      FROM pg_attribute AS attribute
     WHERE attribute.attrelid = 'public.users'::regclass
       AND attribute.attname = 'id'
       AND NOT attribute.attisdropped;

    IF listing_id_type IS NULL OR user_id_type IS NULL THEN
        RAISE EXCEPTION 'Expected public.listings(id) and public.users(id) before creating listing favorites.';
    END IF;

    EXECUTE format(
        'CREATE TABLE IF NOT EXISTS public.listing_favorites (
            user_id %1$s NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
            listing_id %2$s NOT NULL REFERENCES public.listings(id) ON DELETE CASCADE,
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (user_id, listing_id)
        )',
        user_id_type,
        listing_id_type
    );
END $$;

CREATE INDEX IF NOT EXISTS listing_favorites_user_created_idx
    ON public.listing_favorites (user_id, created_at DESC);

ALTER TABLE public.listing_favorites ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.listing_favorites FROM anon, authenticated;
GRANT ALL ON TABLE public.listing_favorites TO service_role;
