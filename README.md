# SpaceShare

SpaceShare is a small web app for Nova SBE that helps users find and offer
private and commercial storage spaces such as garages, basements, or storage
rooms. One account can have both roles: users can search for storage space and
manage their own listings.

## Planned scope

The first version will include registration, login and logout, a listing
overview with detail pages, filtering by location, and the ability to create,
edit, and delete personal listings. A listing contains a photo, description,
location, area, monthly price, availability, and minimum rental period.
Initially, users can contact the owner by email. Bookings, payments, and chat
are possible future extensions.

Passwords must never be stored in plain text; they must be securely hashed.
Only the owner of a listing may edit or delete it.

## Suggested structure

```text
SpaceShare/
├── app.py              # Streamlit user interface and navigation
├── logic.py            # Validation, authentication, and business rules
├── db.py               # SQLite connection, tables, and database access
├── tests/
│   ├── test_logic.py   # Tests for rules and password handling
│   └── test_db.py      # Tests for storage and ownership permissions
├── requirements.txt    # or pyproject.toml when using uv
├── README.md
└── .gitignore
```

The user interface should contain as little business logic as possible:
`app.py` collects input and displays results, `logic.py` decides whether an
action is valid, and `db.py` reads and writes data.

## First small, testable development step

The first small vertical step is to implement the user foundation:

1. Create a SQLite `users` table in `db.py` with `id`, `email`, and
   `password_hash` columns.
2. Add registration and password verification functions in `logic.py`. Use an
   established password-hashing library and never store plain-text passwords.
3. Use pytest to verify that a user can be created, a duplicate email is
   rejected, the correct password is accepted, and an incorrect password is
   rejected.

This step is small enough for both team members to explain and provides the
foundation for ownership permissions on future listings. The Streamlit user
interface can be added after these rules are tested in isolation.

## Storage after deployment

SQLite is suitable for local development and testing. Before deployment, we
must check whether the hosting provider preserves local files permanently. If
the app instance can be reset during restarts or new deployments, the
production version will need an external persistent database, such as a
managed PostgreSQL service, or hosting with persistent storage. This decision
should be made before the public launch to avoid losing user data.
