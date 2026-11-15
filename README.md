# SpaceShare

SpaceShare is a small Streamlit web app for Nova SBE that helps people find
and offer private or commercial storage spaces, such as garages, basements,
and storage rooms. One account can both publish listings and request storage.

## Current features

- Browse storage listings without an account.
- Filter public listings by city, minimum size, maximum monthly price, and a
  desired rental start and end date.
- Register, log in, and log out. Passwords are stored as Argon2 hashes, never
  as plain text.
- Create, edit, and delete only your own listings.
- Add an optional JPG or PNG photo up to 5 MB to a listing; owners can replace
  or remove it later.
- Send a rental request for a listing after logging in.
- See sent and incoming requests in **My requests**; the listing owner can
  accept or reject pending requests.
- Validate listing dates, requested dates, minimum rental duration, ownership,
  uploaded images, and conflicting accepted requests.

## Rental-period behaviour

The public availability filter shows listings whose own availability covers
the requested date range and which have no overlapping **accepted** rental
request. Pending requests do not hide a listing, so an owner can decide among
them.

Rental periods use a half-open interval: `[start date, end date)`. Therefore,
a rental that starts on the date a previous accepted rental ends is allowed.
Accepted rental requests cannot overlap; an attempt to accept a conflicting
pending request is rejected and leaves that request pending.

Rental requests are not payments, contracts, or final bookings.

## Run locally

From the project directory:

```bash
uv sync
uv run streamlit run app.py
```

Open the URL printed by Streamlit, normally:

```text
http://localhost:8501
```

The local SQLite database is created as `spaceshare.sqlite3` in the project
directory. It is intentionally ignored by Git.

## Run the tests

```bash
uv run pytest -q
```

## Project structure

```text
SpaceShare/
├── app.py                         # Streamlit interface and navigation
├── logic.py                       # Validation, authentication, business rules
├── db.py                          # SQLite schema and data access
├── tests/
│   ├── conftest.py                # Shared test database fixture
│   ├── test_accounts.py           # Accounts, listings, photos, basic filters
│   └── test_rental_requests.py    # Requests and date-range availability
├── pyproject.toml                 # Dependencies and pytest configuration
├── README.md
└── HANDOVER.md
```

The user interface collects input and displays results, `logic.py` applies
the business rules, and `db.py` reads and writes SQLite data.

## Current limitations and deployment

There is no payment, chat, contact-email workflow, listing detail page, or
external photo storage yet. Requesters also cannot currently cancel a request.

SQLite and photo bytes stored in the database are appropriate for local
development and this small course project. Before a public deployment, choose
durable database and object-storage services, verify HTTPS and backups, and
define data-retention rules.

## Repository and data safety

The repository is public. Never commit user data, database files, passwords,
tokens, or credentials. Check the staged file list before every push.
