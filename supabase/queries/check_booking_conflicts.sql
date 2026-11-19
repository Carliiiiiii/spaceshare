-- Run this query before applying the atomic booking migration.
-- It must return zero rows before the migration is applied.
SELECT first.id AS first_request_id,
       second.id AS second_request_id,
       first.listing_id,
       first.start_date AS first_start,
       first.end_date AS first_end,
       second.start_date AS second_start,
       second.end_date AS second_end
FROM public.rental_requests AS first
JOIN public.rental_requests AS second
  ON second.listing_id = first.listing_id
 AND second.id > first.id
 AND first.status = 'accepted'
 AND second.status = 'accepted'
 AND first.start_date::date < second.end_date::date
 AND second.start_date::date < first.end_date::date;
