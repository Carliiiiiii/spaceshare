# SpaceShare

SpaceShare is a small English-language Streamlit web app for the Nova SBE programming project. It helps people find and offer private or commercial storage spaces such as garages, basements, and storage rooms. Every account can both search for storage and publish a space.

## Team

- Carla Wischerhoff — 83442
- Nele Wittkopf — 81811

## Links

- Public repository: https://github.com/Carliiiiiii/spaceshare
- Public app: https://carliiiiiii-spaceshare-app-fznqzk.streamlit.app/

## Current features

- Browse storage listings without logging in.
- Search by city, minimum size, maximum monthly price, desired rental dates, distance, listing equipment, and favourites.
- View listing details, photos, public map locations, availability calendars, listing equipment, and the owner's public trust profile.
- Register, log in, log out, and keep a login session after a browser refresh.
- Store passwords as Argon2 hashes; passwords are never stored as plain text.
- Set and edit a public display name, profile description, and optional profile photo. E-mail addresses are not used as public names.
- Create, edit, and delete only the listings owned by the signed-in user.
- Add, replace, or remove an optional validated JPG/PNG listing photo up to 5 MB.
- Set and edit an optional public profile photo as a validated JPG/PNG up to 5 MB. HEIC/HEIF iPhone files are not supported directly; export them as JPG or PNG first.
- Send rental requests with a start date, end date, and status.
- Accept or reject pending requests as the listing owner and cancel a request as its requester.
- Prevent overlapping accepted rentals while allowing directly adjacent periods. Pending and rejected requests do not block availability.
- Use private chats for listing questions and rental requests. Only the two participants can read or send messages. Chats show the other participant's public name and unread-message indicators.
- Store data locally in SQLite or use Supabase for the hosted deployment.

## Rental-period behaviour

Rental periods use half-open intervals: `[start date, end date)`. For example, an accepted rental ending on 31 December does not block a new rental starting on 31 December. Accepted overlapping requests cannot be confirmed. The second request remains pending and receives a clear error message.

A rental request is not a payment, contract, or legally binding booking.

## Local setup

From the project directory:

```bash
uv sync
uv run streamlit run app.py
```

Open the local URL printed by Streamlit, normally `http://localhost:8501`.

The local SQLite database is created as `spaceshare.sqlite3` in the project directory and is ignored by Git.

## Hosted setup

The deployed app uses Streamlit Community Cloud and Supabase. Configure these values in Streamlit Secrets; never commit them to GitHub:

```toml
SUPABASE_URL = "https://your-project.supabase.co"
SUPABASE_SERVICE_ROLE_KEY = "your-service-role-key"
SUPABASE_STORAGE_BUCKET = "listing-photos"
```

Apply the SQL migrations in `supabase/migrations/` to the Supabase project before deploying. The Supabase service-role key must remain private.

## Tests

```bash
uv run pytest -q
```

Tests use isolated temporary SQLite databases. The latest local run completed with 92 passed and 2 skipped; the skipped tests are optional live Supabase concurrency tests that require dedicated test secrets.

The test suite covers accounts, password verification, persistence, listings, photos, filtering, profiles, ownership checks, rental-request validation, availability and overlap rules, private chats, unread messages, and invalid inputs.

## Project structure

```text
SpaceShare/
├── app.py                         # Streamlit interface and navigation
├── logic.py                       # Validation and business rules
├── db.py                          # SQLite and Supabase data access
├── supabase_backend.py            # Hosted Supabase connection setup
├── supabase/migrations/           # Explicit hosted database migrations
├── tests/                         # Automated tests
├── pyproject.toml                 # Dependencies and pytest configuration
├── README.md
└── HANDOVER.md
```

The interface collects input and displays results, `logic.py` validates and applies business rules, and `db.py` performs database operations. Ownership and participant checks are enforced in the backend, not only by hiding UI buttons.

## Known limitations and next steps

- Payments, automated e-mails, exact-address sharing, and a legal booking contract are outside the current course-project scope.
- Supabase backups, retention rules, and production monitoring are not configured for a long-term public service.
- HEIC/HEIF image uploads are not supported; users must convert iPhone photos to JPG or PNG.
- Before submission, confirm the public URL, migration state, secrets, and the final test result on `main`.

## Repository and data safety

The repository is public. Never commit database files, passwords, tokens, Supabase keys, Streamlit secrets, `.env` files, or private user data. Inspect the staged file list before every push. Local SQLite files, caches, virtual environments, and secret files are excluded by `.gitignore`.
