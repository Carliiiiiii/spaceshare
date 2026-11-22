"""Validation and authentication rules for SpaceShare accounts."""

import sqlite3
from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from math import isfinite
from typing import Optional

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from PIL import Image, UnidentifiedImageError

import db


password_hasher = PasswordHasher()
MAX_PHOTO_SIZE_BYTES = 5 * 1024 * 1024
MAX_MESSAGE_LENGTH = 1000
MESSAGE_LIMIT = 10
MESSAGE_LIMIT_WINDOW_MINUTES = 5
PUBLIC_LOCATION_DECIMAL_PLACES = 2
RENTAL_REQUEST_EXPIRY_DAYS = db.RENTAL_REQUEST_EXPIRY_DAYS


def normalize_email(email: str) -> str:
    """Trim and lowercase an email address."""
    if not isinstance(email, str):
        raise ValueError("Email is required.")
    normalized_email = email.strip().lower()
    if not normalized_email:
        raise ValueError("Email is required.")
    return normalized_email


def register_user(
    connection: sqlite3.Connection,
    email: str,
    password: str,
    display_name: str = "Storage user",
) -> int:
    """Validate and register an account."""
    normalized_email = normalize_email(email)
    if not isinstance(password, str) or not password:
        raise ValueError("Password is required.")
    if not isinstance(display_name, str) or not display_name.strip():
        raise ValueError("Display name is required.")
    display_name = display_name.strip()
    if len(display_name) > 80:
        raise ValueError("Display name must be 80 characters or fewer.")

    password_hash = password_hasher.hash(password)
    return db.create_user(connection, normalized_email, password_hash, display_name)


def update_display_name(connection, user_id, display_name: str) -> None:
    """Validate and update the authenticated user's public display name."""
    if not isinstance(display_name, str) or not display_name.strip():
        raise ValueError("Display name is required.")
    cleaned_name = display_name.strip()
    if len(cleaned_name) > 80:
        raise ValueError("Display name must be 80 characters or fewer.")
    db.update_user_display_name(connection, user_id, cleaned_name)


def update_user_profile(connection, user_id, display_name, bio, request_verification, photo_data=None, photo_mime_type=None):
    """Validate and update the public profile without self-verification."""
    if not isinstance(display_name, str) or not display_name.strip() or len(display_name.strip()) > 80:
        raise ValueError("Display name must be between 1 and 80 characters.")
    if not isinstance(bio, str) or len(bio.strip()) > 300:
        raise ValueError("Profile description must be 300 characters or fewer.")
    photo_data, photo_mime_type = validate_photo(photo_data, photo_mime_type)
    status = "pending" if request_verification else "unverified"
    db.update_user_profile(connection, user_id, display_name.strip(), bio.strip(), status, photo_data, photo_mime_type)


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
    *,
    public_latitude: Optional[float] = None,
    public_longitude: Optional[float] = None,
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
    public_latitude, public_longitude = validate_public_location(
        public_latitude, public_longitude
    )
    return db.create_listing(
        connection,
        owner_id,
        *values,
        photo_data,
        photo_mime_type,
        public_latitude=public_latitude,
        public_longitude=public_longitude,
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


def validate_gallery_photos(photos):
    """Validate up to eight uploaded gallery images."""
    if len(photos) > 8:
        raise ValueError("A listing can have at most 8 photos.")
    return [validate_photo(data, mime_type) for data, mime_type in photos]


def replace_listing_gallery(connection, listing_id, owner_id, photos, cover_index=0):
    """Validate and store a gallery with one selected cover image."""
    validated = validate_gallery_photos(photos)
    if validated and not 0 <= cover_index < len(validated):
        raise ValueError("Choose a valid cover photo.")
    db.replace_listing_images(connection, listing_id, owner_id, [(data, mime_type, index == cover_index) for index, (data, mime_type) in enumerate(validated)])


def validate_public_location(
    public_latitude: Optional[float], public_longitude: Optional[float]
) -> tuple:
    """Validate and round an optional, intentionally approximate map point."""
    if (public_latitude is None) != (public_longitude is None):
        raise ValueError("Select both map coordinates or leave both empty.")
    if public_latitude is None:
        return None, None

    try:
        latitude = float(public_latitude)
        longitude = float(public_longitude)
    except (TypeError, ValueError) as error:
        raise ValueError("Map coordinates must be numbers.") from error

    if not isfinite(latitude) or not -90 <= latitude <= 90:
        raise ValueError("Map latitude must be between -90 and 90.")
    if not isfinite(longitude) or not -180 <= longitude <= 180:
        raise ValueError("Map longitude must be between -180 and 180.")

    return (
        round(latitude, PUBLIC_LOCATION_DECIMAL_PLACES),
        round(longitude, PUBLIC_LOCATION_DECIMAL_PLACES),
    )


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
    *,
    public_latitude: Optional[float] = None,
    public_longitude: Optional[float] = None,
    update_public_location: bool = False,
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
    if update_public_location:
        public_latitude, public_longitude = validate_public_location(
            public_latitude, public_longitude
        )
    elif public_latitude is not None or public_longitude is not None:
        raise ValueError(
            "Set update_public_location to update map coordinates."
        )
    db.update_listing(
        connection,
        listing_id,
        owner_id,
        *values,
        photo_data,
        photo_mime_type,
        public_latitude=public_latitude,
        public_longitude=public_longitude,
        update_public_location=update_public_location,
    )


def delete_listing(
    connection: sqlite3.Connection, owner_id: int, listing_id: int
) -> None:
    """Delete a listing only for its owner."""
    db.delete_listing(connection, listing_id, owner_id)


def toggle_listing_favorite(connection, user_id, listing_id):
    """Save or remove a listing from the authenticated user's shortlist."""
    if db.get_listing_by_id(connection, listing_id) is None:
        raise ValueError("Listing not found.")
    saved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return db.toggle_listing_favorite(connection, user_id, listing_id, saved_at)


def create_rental_request(connection, listing_id, requester_id, start_date, end_date):
    listing = db.get_listing_for_request(connection, listing_id)
    if listing is None:
        raise ValueError("Listing not found.")
    if listing["owner_id"] == requester_id:
        raise PermissionError("You cannot request your own listing.")
    try:
        requested_start = date.fromisoformat(start_date.strip())
        requested_end = date.fromisoformat(end_date.strip())
        available_from = date.fromisoformat(listing["available_from"])
    except (AttributeError, ValueError) as error:
        raise ValueError("Rental dates must be valid dates.") from error
    if requested_end < requested_start:
        raise ValueError("End date cannot be before start date.")
    if requested_start < available_from:
        raise ValueError("Start date is before the listing becomes available.")
    if listing["available_until"] is not None:
        if requested_end > date.fromisoformat(listing["available_until"]):
            raise ValueError("End date is after the listing's availability.")
    if (requested_end - requested_start).days < listing["minimum_rental_days"]:
        raise ValueError(
            "The requested period is shorter than the minimum rental duration."
        )
    created_at = datetime.now(timezone.utc)
    return db.create_rental_request(
        connection,
        listing_id,
        requester_id,
        requested_start.isoformat(),
        requested_end.isoformat(),
        created_at.isoformat(timespec="seconds"),
        (created_at + timedelta(days=RENTAL_REQUEST_EXPIRY_DAYS)).isoformat(
            timespec="seconds"
        ),
    )


def update_rental_request_status(connection, request_id, owner_id, status):
    if status not in {"accepted", "rejected"}:
        raise ValueError("Invalid rental request status.")
    db.update_rental_request_status(connection, request_id, owner_id, status)


def cancel_rental_request(connection, request_id, requester_id):
    """Let a requester withdraw an unanswered rental request."""
    expire_pending_rental_requests(connection)
    db.cancel_rental_request(connection, request_id, requester_id)


def expire_pending_rental_requests(connection):
    """Expire unanswered requests seven days after they were created."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return db.expire_pending_rental_requests(connection, now)


def send_message(connection, request_id, sender_id, message):
    """Validate and send a message as a participant in a request."""
    cleaned_message = _validated_message_text(message)
    sent_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _check_message_rate_limit(connection, sender_id)
    return db.create_message(
        connection, request_id, sender_id, cleaned_message, sent_at
    )


def get_messages(connection, request_id, user_id):
    """Return messages only for a renter or the listing owner."""
    return db.get_messages(connection, request_id, user_id)


def start_listing_conversation(connection, listing_id, participant_id):
    """Create or return a direct conversation about a listing."""
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return db.get_or_create_listing_conversation(
        connection, listing_id, participant_id, created_at
    )


def send_listing_conversation_message(connection, conversation_id, sender_id, message):
    """Validate and send a direct listing-chat message."""
    cleaned_message = _validated_message_text(message)
    sent_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _check_message_rate_limit(connection, sender_id)
    return db.create_listing_conversation_message(
        connection, conversation_id, sender_id, cleaned_message, sent_at
    )


def send_listing_question(connection, listing_id, sender_id, message):
    """Start or reuse a listing conversation and send its first question."""
    _validated_message_text(message)
    conversation_id = start_listing_conversation(connection, listing_id, sender_id)
    send_listing_conversation_message(connection, conversation_id, sender_id, message)
    return conversation_id


def _validated_message_text(message):
    """Return a non-empty, safely sized message string."""
    if not isinstance(message, str) or not message.strip():
        raise ValueError("Message cannot be empty.")
    cleaned_message = message.strip()
    if len(cleaned_message) > MAX_MESSAGE_LENGTH:
        raise ValueError("Message must be 1000 characters or fewer.")
    return cleaned_message


def _check_message_rate_limit(connection, user_id):
    since = (datetime.now(timezone.utc) - timedelta(minutes=MESSAGE_LIMIT_WINDOW_MINUTES)).isoformat(timespec="seconds")
    if db.count_recent_messages(connection, user_id, since) >= MESSAGE_LIMIT:
        raise ValueError("Too many messages. Please wait a few minutes before sending more.")


def block_user(connection, blocker_id, blocked_id):
    if blocker_id == blocked_id:
        raise ValueError("You cannot block yourself.")
    db.block_user(connection, blocker_id, blocked_id, datetime.now(timezone.utc).isoformat(timespec="seconds"))


def report_content(connection, reporter_id, target_type, target_id, reason):
    if target_type not in {"listing", "message"}:
        raise ValueError("Invalid report type.")
    if not isinstance(reason, str) or not reason.strip() or len(reason.strip()) > 500:
        raise ValueError("Please provide a report reason of up to 500 characters.")
    db.create_safety_report(connection, reporter_id, target_type, target_id, reason.strip(), datetime.now(timezone.utc).isoformat(timespec="seconds"))


def get_listing_conversations(connection, user_id):
    """Return direct listing conversations visible to a user."""
    return db.get_listing_conversations_for_user(connection, user_id)


def get_listing_conversation_messages(connection, conversation_id, user_id):
    """Return direct listing-chat messages only for either participant."""
    return db.get_listing_conversation_messages(connection, conversation_id, user_id)


def mark_listing_conversation_messages_read(connection, conversation_id, user_id):
    db.mark_listing_conversation_messages_read(connection, conversation_id, user_id)


def get_unread_message_count(connection, user_id):
    return db.get_unread_message_count(connection, user_id)


def get_pending_incoming_rental_request_count(connection, user_id):
    """Count open requests received for the user's own listings."""
    return db.get_pending_incoming_rental_request_count(connection, user_id)


def mark_messages_read(connection, request_id, user_id):
    db.mark_messages_read(connection, request_id, user_id)
