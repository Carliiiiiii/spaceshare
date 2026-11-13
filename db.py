"""SQLite storage for SpaceShare accounts."""

import sqlite3
from pathlib import Path
from typing import Optional


def connect(database_path: Path) -> sqlite3.Connection:
    """Open the database and create required tables if they do not exist."""
    # Streamlit may run script reruns in different threads.
    connection = sqlite3.connect(str(database_path), check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            city TEXT NOT NULL,
            description TEXT NOT NULL,
            size_sqm REAL NOT NULL,
            price_per_month_eur REAL NOT NULL,
            available_from TEXT NOT NULL,
            available_until TEXT,
            photo_data BLOB,
            photo_mime_type TEXT,
            minimum_rental_days INTEGER NOT NULL,
            FOREIGN KEY (owner_id) REFERENCES users (id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS rental_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            listing_id INTEGER NOT NULL,
            requester_id INTEGER NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            FOREIGN KEY (listing_id) REFERENCES listings (id),
            FOREIGN KEY (requester_id) REFERENCES users (id)
        )
        """
    )
    listing_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(listings)")
    }
    if "available_until" not in listing_columns:
        connection.execute("ALTER TABLE listings ADD COLUMN available_until TEXT")
    if "photo_data" not in listing_columns:
        connection.execute("ALTER TABLE listings ADD COLUMN photo_data BLOB")
    if "photo_mime_type" not in listing_columns:
        connection.execute("ALTER TABLE listings ADD COLUMN photo_mime_type TEXT")
    connection.commit()
    return connection


def create_user(connection: sqlite3.Connection, email: str, password_hash: str) -> int:
    """Store one account and return its id."""
    try:
        cursor = connection.execute(
            "INSERT INTO users (email, password_hash) VALUES (?, ?)",
            (email, password_hash),
        )
        connection.commit()
    except sqlite3.IntegrityError as error:
        raise ValueError("An account with this email already exists.") from error
    return int(cursor.lastrowid)


def get_user_by_email(
    connection: sqlite3.Connection, email: str
) -> Optional[sqlite3.Row]:
    """Return an account by normalized email, or None if it does not exist."""
    return connection.execute(
        "SELECT id, email, password_hash FROM users WHERE email = ?",
        (email,),
    ).fetchone()


def create_listing(
    connection: sqlite3.Connection,
    owner_id: int,
    title: str,
    city: str,
    description: str,
    size_sqm: float,
    price_per_month_eur: float,
    available_from: str,
    minimum_rental_days: int,
    available_until: Optional[str] = None,
    photo_data: Optional[bytes] = None,
    photo_mime_type: Optional[str] = None,
) -> int:
    """Store one storage listing and return its id."""
    cursor = connection.execute(
        """
        INSERT INTO listings (
            owner_id, title, city, description, size_sqm,
            price_per_month_eur, available_from, available_until,
            photo_data, photo_mime_type, minimum_rental_days
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            owner_id,
            title,
            city,
            description,
            size_sqm,
            price_per_month_eur,
            available_from,
            available_until,
            photo_data,
            photo_mime_type,
            minimum_rental_days,
        ),
    )
    connection.commit()
    return int(cursor.lastrowid)


def get_listings(
    connection: sqlite3.Connection,
    *,
    city: Optional[str] = None,
    minimum_size_sqm: Optional[float] = None,
    maximum_price_per_month_eur: Optional[float] = None,
    available_on: Optional[str] = None,
) -> list:
    """Return public listing fields, optionally limited by browse filters."""
    filters = []
    parameters = []

    if city is not None and city.strip():
        filters.append("LOWER(city) LIKE ?")
        parameters.append(f"%{city.strip().lower()}%")
    if minimum_size_sqm is not None:
        filters.append("size_sqm >= ?")
        parameters.append(minimum_size_sqm)
    if maximum_price_per_month_eur is not None:
        filters.append("price_per_month_eur <= ?")
        parameters.append(maximum_price_per_month_eur)
    if available_on is not None:
        filters.append(
            "available_from <= ? "
            "AND (available_until IS NULL OR available_until >= ?)"
        )
        parameters.extend((available_on, available_on))

    query = """
        SELECT id, title, city, description, size_sqm,
               price_per_month_eur, available_from, available_until,
               photo_data, photo_mime_type,
               minimum_rental_days
        FROM listings
    """
    if filters:
        query += " WHERE " + " AND ".join(filters)
    query += " ORDER BY id DESC"
    return connection.execute(query, parameters).fetchall()


def get_listings_by_owner(connection: sqlite3.Connection, owner_id: int) -> list:
    """Return listings owned by one account."""
    return connection.execute(
        """
        SELECT id, title, city, description, size_sqm,
               price_per_month_eur, available_from, available_until,
               photo_data, photo_mime_type,
               minimum_rental_days
        FROM listings
        WHERE owner_id = ?
        ORDER BY id DESC
        """,
        (owner_id,),
    ).fetchall()


def update_listing(
    connection: sqlite3.Connection,
    listing_id: int,
    owner_id: int,
    title: str,
    city: str,
    description: str,
    size_sqm: float,
    price_per_month_eur: float,
    available_from: str,
    minimum_rental_days: int,
    available_until: Optional[str] = None,
    photo_data: Optional[bytes] = None,
    photo_mime_type: Optional[str] = None,
) -> None:
    """Update a listing only when the supplied owner owns it."""
    cursor = connection.execute(
        """
        UPDATE listings
        SET title = ?, city = ?, description = ?, size_sqm = ?,
            price_per_month_eur = ?, available_from = ?,
            available_until = ?, photo_data = ?, photo_mime_type = ?,
            minimum_rental_days = ?
        WHERE id = ? AND owner_id = ?
        """,
        (
            title,
            city,
            description,
            size_sqm,
            price_per_month_eur,
            available_from,
            available_until,
            photo_data,
            photo_mime_type,
            minimum_rental_days,
            listing_id,
            owner_id,
        ),
    )
    if cursor.rowcount != 1:
        connection.rollback()
        raise PermissionError("You do not own this listing.")
    connection.commit()


def delete_listing(
    connection: sqlite3.Connection, listing_id: int, owner_id: int
) -> None:
    """Delete a listing only when the supplied owner owns it."""
    cursor = connection.execute(
        "DELETE FROM listings WHERE id = ? AND owner_id = ?",
        (listing_id, owner_id),
    )
    if cursor.rowcount != 1:
        connection.rollback()
        raise PermissionError("You do not own this listing.")
    connection.commit()


def create_rental_request(connection, listing_id, requester_id, start_date, end_date):
    cursor = connection.execute(
        "INSERT INTO rental_requests (listing_id, requester_id, start_date, end_date) VALUES (?, ?, ?, ?)",
        (listing_id, requester_id, start_date, end_date),
    )
    connection.commit()
    return int(cursor.lastrowid)


def get_rental_requests_for_user(connection, user_id):
    return connection.execute(
        """SELECT requests.id, requests.listing_id, requests.requester_id,
                  requests.start_date, requests.end_date, requests.status,
                  listings.title, listings.owner_id
           FROM rental_requests AS requests
           JOIN listings ON listings.id = requests.listing_id
           WHERE requests.requester_id = ? OR listings.owner_id = ?
           ORDER BY requests.id DESC""",
        (user_id, user_id),
    ).fetchall()


def update_rental_request_status(connection, request_id, owner_id, status):
    if status == "accepted":
        conflicting_request = connection.execute(
            """SELECT 1
               FROM rental_requests AS candidate
               JOIN rental_requests AS accepted
                 ON accepted.listing_id = candidate.listing_id
                AND accepted.status = 'accepted'
                AND candidate.id <> accepted.id
                AND candidate.start_date < accepted.end_date
                AND candidate.end_date > accepted.start_date
               JOIN listings ON listings.id = candidate.listing_id
               WHERE candidate.id = ? AND listings.owner_id = ?""",
            (request_id, owner_id),
        ).fetchone()
        if conflicting_request is not None:
            raise ValueError(
                "This rental period overlaps an accepted request. "
                "The request remains pending."
            )
    cursor = connection.execute(
        """UPDATE rental_requests SET status = ?
           WHERE id = ? AND listing_id IN
           (SELECT id FROM listings WHERE owner_id = ?) AND status = 'pending'""",
        (status, request_id, owner_id),
    )
    if cursor.rowcount != 1:
        connection.rollback()
        raise PermissionError("You cannot change this rental request.")
    connection.commit()
