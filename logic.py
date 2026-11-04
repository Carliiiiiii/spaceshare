"""Validation and authentication rules for SpaceShare accounts."""

import sqlite3

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError

import db


password_hasher = PasswordHasher()


def normalize_email(email: str) -> str:
    """Trim and lowercase an email address."""
    if not isinstance(email, str):
        raise ValueError("Email is required.")
    normalized_email = email.strip().lower()
    if not normalized_email:
        raise ValueError("Email is required.")
    return normalized_email


def register_user(connection: sqlite3.Connection, email: str, password: str) -> int:
    """Validate and register an account."""
    normalized_email = normalize_email(email)
    if not isinstance(password, str) or not password:
        raise ValueError("Password is required.")

    password_hash = password_hasher.hash(password)
    return db.create_user(connection, normalized_email, password_hash)


def verify_user_password(
    connection: sqlite3.Connection, email: str, password: str
) -> bool:
    """Return whether the supplied password matches the account."""
    normalized_email = normalize_email(email)
    if not isinstance(password, str) or not password:
        return False

    user = db.get_user_by_email(connection, normalized_email)
    if user is None:
        return False

    try:
        return password_hasher.verify(user["password_hash"], password)
    except VerificationError:
        return False


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
) -> int:
    """Validate and create a listing for an authenticated owner."""
    required_fields = {
        "Title": title,
        "City": city,
        "Description": description,
        "Available from": available_from,
    }
    for field_name, value in required_fields.items():
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field_name} is required.")

    if size_sqm <= 0:
        raise ValueError("Size must be positive.")
    if price_per_month_eur < 0:
        raise ValueError("Price cannot be negative.")
    if minimum_rental_days <= 0:
        raise ValueError("Minimum rental duration must be positive.")

    return db.create_listing(
        connection,
        owner_id,
        title.strip(),
        city.strip(),
        description.strip(),
        size_sqm,
        price_per_month_eur,
        available_from.strip(),
        minimum_rental_days,
    )
