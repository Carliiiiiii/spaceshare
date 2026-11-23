# SpaceShare Handover

## Current status

The current published code is on `main`:

- Repository: https://github.com/Carliiiiiii/spaceshare
- App: https://carliiiiiii-spaceshare-app-codexsupabase-storage-luv4lh.streamlit.app/

The interface and documentation are in English. Each account can both search for storage and offer storage.

## Team

- Carla Wischerhoff — student number 83442
- Nele Wittkopf — student number 81811

## Implemented functionality

### Accounts and profiles

- Registration, login, logout, and refresh-persistent signed sessions.
- Argon2 password hashing; passwords are not logged or stored in plain text.
- Public display name, short profile description, optional profile photo, and verification-request status.
- Profile photos must be real JPG or PNG images up to 5 MB. HEIC/HEIF iPhone files are not accepted directly and must be exported first.
- Existing accounts without a display name use a role-based fallback in chat: `Storage seeker` or `Storage owner`.
- E-mail addresses remain private and are not used as public names.

### Listings

- Public browsing before login.
- Listing creation, editing, and confirmed deletion by the owner only.
- Title, city, description, size, monthly price, availability, minimum stay, optional equipment, optional end date, and optional JPG/PNG photo.
- Photo validation, replacement and removal, with a placeholder when no photo exists.
- Public map location, listing detail view, availability calendar, favourites, and advanced filters.

### Rental requests

- A logged-in user can request a period for another user's listing.
- The requested period must fit the listing availability and minimum stay.
- The owner can accept or reject pending requests; the requester can cancel a pending request.
- Accepted requests cannot overlap. Directly adjacent periods are allowed.
- Pending, rejected, cancelled, and expired requests do not block a period.
- Owner checks and requester checks are enforced in the backend.

### Chats

- Private listing-question conversations and rental-request conversations.
- Only the listing owner and the other participant can read or send messages.
- Messages are stored with sender and timestamp, displayed chronologically, and can be refreshed.
- The chat overview and open chat show the listing title and the other participant's display name, without exposing e-mail addresses.
- Unread-message counts are shown in the navigation.

## Data storage

Local development uses SQLite. The database file is `spaceshare.sqlite3` in the project directory and is ignored by Git. Automated tests use temporary databases.

The hosted deployment uses Supabase for accounts, listings, rental requests, photos, profiles, and chat data. Listing photos are stored using the configured Supabase Storage bucket. Streamlit Secrets contain the Supabase URL, service role key, and storage bucket name; these values must never be committed.

Run all relevant SQL migrations from `supabase/migrations/` in the Supabase SQL Editor before deploying schema-dependent changes.

## Local setup and tests

```bash
uv sync
uv run streamlit run app.py
uv run pytest -q
```

The normal local URL is `http://localhost:8501`.

For a two-account browser test:

1. Open two separate browser profiles or private windows.
2. Register one owner and one storage seeker, each with a different name.
3. The owner creates a listing and optionally uploads a photo.
4. The seeker finds the listing, sends a rental request, and starts a chat.
5. The owner checks **My requests**, accepts or rejects the request, and replies in **Chats**.
6. Confirm that each side sees the other person's name, not their e-mail.
7. Test an overlapping accepted period and a directly adjacent period.
8. Restart the app and verify that accounts, listings, photos, requests, and messages remain available.

## Verification before submission

- Run `uv run pytest -q` on `main`. The latest local run completed with 92 passed and 2 skipped; the skipped tests are optional live Supabase concurrency tests requiring dedicated test secrets.
- Confirm that the Streamlit app uses the intended Supabase project and that all required migrations have been applied.
- Check the Streamlit Secrets configuration without copying secrets into the repository.
- Review the staged files and confirm that no `*.sqlite3`, `.env`, secrets, tokens, passwords, photos, or other local user data are included.
- Confirm that the public URL, both team names, and both student numbers are present in `README.md`.

The repository contains hosted database migrations, but not one complete initial migration for the original baseline schema. The deployed Supabase schema was checked manually; this is a documentation limitation rather than a user-facing feature.

## Privacy and security notes

The public repository does not contain database files, passwords, API keys, or Streamlit secrets. Passwords are stored as Argon2 password hashes and are never stored as plain text.

The hosted app reads the Supabase service-role key only from Streamlit Secrets. The key is used server-side and is not stored in GitHub or exposed in the application interface.

Ownership checks for listings and rental requests, as well as participant checks for private chats, are performed in the backend before database operations.

Listing photos are stored in the public `listing-photos` Supabase Storage bucket. They must therefore be treated as publicly accessible listing media. Users should not upload real addresses, identity documents, private documents, or other sensitive personal information.

The public demonstration uses test accounts. No real personal data should be used for testing.

## Remaining limitations

The project does not implement payments, automated e-mail notifications, identity verification, exact-address sharing, or a legally binding contract. These are outside the current small course-project scope unless the team chooses one as a future extension.

Supabase backups, retention rules, and production monitoring are not configured as a production service. The public demonstration should use fictional accounts, listings, photos, and messages only.
