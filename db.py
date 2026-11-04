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
            minimum_rental_days INTEGER NOT NULL,
            FOREIGN KEY (owner_id) REFERENCES users (id)
        )
        """
    )
    listing_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(listings)")
    }
    if "available_until" not in listing_columns:
        connection.execute("ALTER TABLE listings ADD COLUMN available_until TEXT")
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
) -> int:
    """Store one storage listing and return its id."""
    cursor = connection.execute(
        """
        INSERT INTO listings (
            owner_id, title, city, description, size_sqm,
            price_per_month_eur, available_from, available_until,
            minimum_rental_days
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            minimum_rental_days,
        ),
    )
    connection.commit()
    return int(cursor.lastrowid)


def get_listings(connection: sqlite3.Connection) -> list:
    """Return public listing fields without account data."""
    return connection.execute(
        """
        SELECT id, title, city, description, size_sqm,
               price_per_month_eur, available_from, available_until,
               minimum_rental_days
        FROM listings
        ORDER BY id DESC
        """
    ).fetchall()


def get_listings_by_owner(connection: sqlite3.Connection, owner_id: int) -> list:
    """Return listings owned by one account."""
    return connection.execute(
        """
        SELECT id, title, city, description, size_sqm,
               price_per_month_eur, available_from, available_until,
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
) -> None:
    """Update a listing only when the supplied owner owns it."""
    cursor = connection.execute(
        """
        UPDATE listings
        SET title = ?, city = ?, description = ?, size_sqm = ?,
            price_per_month_eur = ?, available_from = ?,
            available_until = ?, minimum_rental_days = ?
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
