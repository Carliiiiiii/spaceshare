-- Prevent two accepted rental requests from overlapping for one listing.
-- Rental periods are half-open: [start_date, end_date). Therefore a request
-- starting when another request ends is allowed.
--
-- Before applying this migration, run the diagnostic query below. The DO block
-- also aborts the migration if existing conflicting accepted requests remain.
--
-- SELECT first.id AS first_request_id,
--        second.id AS second_request_id,
--        first.listing_id
-- FROM public.rental_requests AS first
-- JOIN public.rental_requests AS second
--   ON second.listing_id = first.listing_id
--  AND second.id > first.id
--  AND first.status = 'accepted'
--  AND second.status = 'accepted'
--  AND first.start_date::date < second.end_date::date
--  AND second.start_date::date < first.end_date::date;

CREATE EXTENSION IF NOT EXISTS btree_gist;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM public.rental_requests AS first_request
        JOIN public.rental_requests AS second_request
          ON second_request.listing_id = first_request.listing_id
         AND second_request.id > first_request.id
         AND first_request.status = 'accepted'
         AND second_request.status = 'accepted'
         AND first_request.start_date::date < second_request.end_date::date
         AND second_request.start_date::date < first_request.end_date::date
    ) THEN
        RAISE EXCEPTION
            'Accepted rental conflicts exist. Run the diagnostic query in migration 20261119090000 before applying this migration.';
    END IF;
END $$;

ALTER TABLE public.rental_requests
    ADD CONSTRAINT accepted_rental_requests_no_overlap
    EXCLUDE USING gist (
        listing_id WITH =,
        daterange(start_date::date, end_date::date, '[)') WITH &&
    )
    WHERE (status = 'accepted');

CREATE OR REPLACE FUNCTION public.accept_rental_request(
    p_request_id bigint,
    p_owner_id bigint
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    UPDATE public.rental_requests AS request
    SET status = 'accepted'
    FROM public.listings AS listing
    WHERE request.id = p_request_id
      AND request.status = 'pending'
      AND listing.id = request.listing_id
      AND listing.owner_id = p_owner_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'You cannot change this rental request.';
    END IF;
END;
$$;

REVOKE ALL ON FUNCTION public.accept_rental_request(bigint, bigint)
    FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.accept_rental_request(bigint, bigint)
    TO service_role;
