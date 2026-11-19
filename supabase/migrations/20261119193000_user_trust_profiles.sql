-- Public, optional trust-profile fields. Verification can only be requested;
-- an administrator must set the value to verified outside the app.
ALTER TABLE public.users
    ADD COLUMN IF NOT EXISTS bio text NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS verification_status text NOT NULL DEFAULT 'unverified',
    ADD COLUMN IF NOT EXISTS profile_photo_path text,
    ADD COLUMN IF NOT EXISTS profile_photo_url text;

ALTER TABLE public.users DROP CONSTRAINT IF EXISTS users_verification_status_check;
ALTER TABLE public.users ADD CONSTRAINT users_verification_status_check
    CHECK (verification_status IN ('unverified', 'pending', 'verified'));
ALTER TABLE public.users DROP CONSTRAINT IF EXISTS users_bio_length;
ALTER TABLE public.users ADD CONSTRAINT users_bio_length CHECK (char_length(bio) <= 300);
