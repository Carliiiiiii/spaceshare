# SpaceShare Handover

## Current status

The current project is on the `main` branch and is published in the public
GitHub repository:

https://github.com/Carliiiiiii/spaceshare

The app currently supports:

- account registration, login, and logout;
- secure Argon2 password hashes;
- SQLite account persistence;
- creating storage listings after login;
- listing fields for title, city, description, size, monthly price,
  availability, and minimum rental duration;
- an optional `Available until` date with date-range validation;
- a `My listings` area for editing and confirmed deletion;
- owner checks in both the business logic and database update/delete queries;
- optional JPG or PNG photos up to 5 MB;
- validation that uploaded files are real JPG or PNG images;
- photo replacement and removal for the listing owner;
- public listing display with a placeholder when no photo exists;
- public browsing before login, with optional filters for city, minimum size,
  maximum monthly price, and availability on a selected date.

There is no booking, payment, chat, contact-email workflow, listing detail
page, or photo storage service yet.

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

## Run the tests

```bash
uv run pytest -q
```

The tests use temporary SQLite databases and currently cover registration,
password verification, persistence, listing validation, date validation,
ownership permissions, listing updates/deletions, photo validation and
persistence, and public listing filters.

## Manual browser checks

1. Without logging in, browse the listing overview and try the city, minimum
   size, maximum price, and availability-date filters.
2. Register an account and log in.
3. Create a listing without a photo and check that the placeholder is shown.
4. Create another listing with a JPG or PNG photo smaller than 5 MB.
5. Open `My listings`, replace the photo, save, and verify the new image.
6. Remove the photo and verify the placeholder returns.
7. Create a second account and verify it cannot see or manage the first
   account's listings in `My listings`.
8. Restart Streamlit and confirm that accounts, listings, and photos persist.

## Open points

- The app currently stores photo bytes in SQLite. This is suitable for the
  small local project, but production deployment must use persistent storage;
  otherwise a hosting restart or redeploy could lose the database and photos.
- Before public production use, choose a durable database and decide whether
  photos should move to an object-storage service, with only a reference kept
  in the database.
- Add deployment configuration and verify HTTPS, backups, and data retention.
- Consider adding a listing detail page, contact by email, and later booking
  features as separate small steps.

## Repository and data safety

The repository is public, so do not commit user data or credentials. The
`.gitignore` excludes `*.sqlite3`, `.env`, virtual environments, caches, and
Python bytecode. Before every push, check the GitHub Desktop file list and
confirm that no database, secret, token, or credential file is included.
