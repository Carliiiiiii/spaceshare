# SpaceShare Handover

## Current status

The current project is on the `main` branch in the public GitHub repository:

https://github.com/Carliiiiiii/spaceshare

The app currently supports:

- account registration, login, and logout with secure Argon2 password hashes;
- SQLite persistence for accounts, listings, photos, and rental requests;
- creating storage listings after login, with title, city, description, size,
  monthly price, availability, minimum rental duration, and an optional end
  date;
- optional JPG or PNG photos up to 5 MB, including validation, replacement,
  removal, and a public placeholder when there is no photo;
- editing and confirmed deletion of a user's own listings, protected by owner
  checks in both the business logic and database queries;
- public browsing before login, with filters for city, minimum size, maximum
  monthly price, and a desired rental start/end date range;
- rental requests with `pending`, `accepted`, and `rejected` statuses;
- a **My requests** area that separates sent requests from requests for a
  user's listings; only the listing owner can accept or reject a pending
  request;
- availability filtering and acceptance checks that prevent overlapping
  accepted rentals. Pending overlaps remain possible, and a rental may start
  on the date a previous accepted rental ends.

Rental periods use half-open intervals: `[start date, end date)`. An accepted
request blocks an overlapping range, while a request ending on a given date
does not block a following request starting on that same date.

There is no payment, chat, contact-email workflow, listing detail page, or
final booking/contract workflow yet. A rental request alone is not a payment
or confirmed booking.

## Local setup and start

From the project directory:

```bash
uv sync
uv run streamlit run app.py
```

Open the local URL shown by Streamlit, normally:

```text
http://localhost:8501
```

The local SQLite database is created as `spaceshare.sqlite3` in the project
working directory. It is intentionally ignored by Git.

Anonymous users see **Find storage**, **Register**, and **Log in**. Logged-in
users see **Find storage**, **List a space**, and **My requests**.

## Run the tests

```bash
uv run pytest -q
```

The tests use temporary SQLite databases. They cover accounts, password
verification, persistence, listing validation, ownership, photos, public
filters, rental-request validation, request visibility and status permissions,
and accepted-rental overlap and date-range availability rules.

## Manual browser checks

1. Without logging in, browse listings and try the city, minimum-size,
   maximum-price, and desired rental date-range filters.
2. Register an account, log in, and confirm the three logged-in navigation
   tabs are visible.
3. Create a listing without a photo and check that the placeholder is shown.
4. Create another listing with a JPG or PNG photo smaller than 5 MB.
5. In **List a space**, replace the photo, save, remove it, and verify the
   placeholder returns.
6. Create a second account and verify it cannot edit or delete the first
   account's listings.
7. With the second account, send a valid rental request from a listing card.
   Verify it appears as sent for the requester and incoming for the owner.
8. As the owner, accept the request. Search an overlapping desired date range
   and verify the listing is hidden; then try to accept an overlapping pending
   request and verify it remains pending.
9. Verify a request beginning on the accepted request's end date can be
   accepted.
10. Restart Streamlit and confirm that accounts, listings, photos, and rental
    requests persist.

## Open points

- Add requester cancellation, owner/requester notifications, and a clear
  booking or contract flow before treating rental requests as reservations.
- Add a listing detail page and a privacy-conscious contact workflow.
- The app currently stores photo bytes in SQLite. This is appropriate for the
  small local project, but a public deployment needs durable database and
  object-storage services.
- Before public production use, define backups, HTTPS, data retention, and
  privacy requirements.

## Repository and data safety

The repository is public, so do not commit user data or credentials. The
`.gitignore` excludes `*.sqlite3`, `.env`, virtual environments, caches, and
Python bytecode. Before every push, inspect the staged file list and confirm
that no database, secret, token, or credential file is included.
