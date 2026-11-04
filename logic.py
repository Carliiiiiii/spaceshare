"""Validation and authentication rules for SpaceShare accounts."""

import sqlite3
from datetime import date
from io import BytesIO
from typing import Optional

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from PIL import Image, UnidentifiedImageError

import db


password_hasher = PasswordHasher()
MAX_PHOTO_SIZE_BYTES = 5 * 1024 * 1024


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
    available_until: Optional[str] = None,
    photo_data: Optional[bytes] = None,
    photo_mime_type: Optional[str] = None,
) -> int:
    """Validate and create a listing for an authenticated owner."""
    values = _validated_listing_values(
        title,
        city,
        description,
        size_sqm,
        price_per_month_eur,
        available_from,
        minimum_rental_days,
        available_until,
    )
    photo_data, photo_mime_type = validate_photo(photo_data, photo_mime_type)
    return db.create_listing(
        connection, owner_id, *values, photo_data, photo_mime_type
    )


def validate_photo(
    photo_data: Optional[bytes], photo_mime_type: Optional[str]
) -> tuple:
    """Validate an optional JPG or PNG and return safe storage values."""
    if photo_data is None:
        return None, None
    if len(photo_data) > MAX_PHOTO_SIZE_BYTES:
        raise ValueError("Photo must be 5 MB or smaller.")

    try:
        with Image.open(BytesIO(photo_data)) as image:
            image.verify()
        with Image.open(BytesIO(photo_data)) as image:
            image_format = image.format
    except (UnidentifiedImageError, OSError) as error:
        raise ValueError("Photo must be a valid JPG or PNG image.") from error

    mime_types = {"JPEG": "image/jpeg", "PNG": "image/png"}
    if image_format not in mime_types:
        raise ValueError("Photo must be a valid JPG or PNG image.")
    return photo_data, mime_types[image_format]


def _validated_listing_values(
    title: str,
    city: str,
    description: str,
    size_sqm: float,
    price_per_month_eur: float,
    available_from: str,
    minimum_rental_days: int,
    available_until: Optional[str],
) -> tuple:
    """Validate and normalize fields shared by create and update."""
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

    try:
        start_date = date.fromisoformat(available_from.strip())
    except ValueError as error:
        raise ValueError("Available from must be a valid date.") from error

    if available_until is not None:
        available_until = available_until.strip()
        try:
            end_date = date.fromisoformat(available_until)
        except ValueError as error:
            raise ValueError("Available until must be a valid date.") from error
        if end_date < start_date:
            raise ValueError("Available until cannot be before Available from.")
        if (end_date - start_date).days < minimum_rental_days:
            raise ValueError("Minimum rental duration does not fit the available period.")

    return (
        title.strip(),
        city.strip(),
        description.strip(),
        size_sqm,
        price_per_month_eur,
        available_from.strip(),
        minimum_rental_days,
        available_until,
    )


def update_listing(
    connection: sqlite3.Connection,
    owner_id: int,
    listing_id: int,
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
    """Validate and update a listing only for its owner."""
    values = _validated_listing_values(
        title,
        city,
        description,
        size_sqm,
        price_per_month_eur,
        available_from,
        minimum_rental_days,
        available_until,
    )
    photo_data, photo_mime_type = validate_photo(photo_data, photo_mime_type)
    db.update_listing(
        connection,
        listing_id,
        owner_id,
        *values,
        photo_data,
        photo_mime_type,
    )


def delete_listing(
    connection: sqlite3.Connection, owner_id: int, listing_id: int
) -> None:
    """Delete a listing only for its owner."""
    db.delete_listing(connection, listing_id, owner_id)
