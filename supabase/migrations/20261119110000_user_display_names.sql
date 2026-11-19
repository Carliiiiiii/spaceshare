-- Public names for private chats. Email addresses remain private.
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS display_name text;

UPDATE public.users
SET display_name = 'Storage user'
WHERE display_name IS NULL OR btrim(display_name) = '';

ALTER TABLE public.users
    ALTER COLUMN display_name SET DEFAULT 'Storage user';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'users_display_name_length'
          AND conrelid = 'public.users'::regclass
    ) THEN
        ALTER TABLE public.users
            ADD CONSTRAINT users_display_name_length
            CHECK (char_length(display_name) BETWEEN 1 AND 80);
    END IF;
END $$;
