from io import BytesIO
import sqlite3

import pytest
from PIL import Image

import db
from logic import (
    create_listing,
    delete_listing,
    register_user,
    update_listing,
    verify_user_password,
)


def make_png() -> bytes:
    image = Image.new("RGB", (2, 2), color="red")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_register_normalizes_email_and_does_not_store_plaintext(connection):
    user_id = register_user(connection, "  Alice@Example.COM ", "correct horse")

    user = db.get_user_by_email(connection, "alice@example.com")
    assert user["id"] == user_id
    assert user["email"] == "alice@example.com"
    assert user["password_hash"] != "correct horse"
    assert user["password_hash"].startswith("$argon2")


@pytest.mark.parametrize(
    ("email", "password"),
    [("", "secret"), ("   ", "secret"), ("user@example.com", "")],
)
def test_register_rejects_empty_inputs(connection, email, password):
    with pytest.raises(ValueError):
        register_user(connection, email, password)


def test_register_rejects_duplicate_email_after_normalization(connection):
    register_user(connection, "user@example.com", "secret")

    with pytest.raises(ValueError):
        register_user(connection, " USER@EXAMPLE.COM ", "another secret")


def test_password_verification_accepts_correct_and_rejects_incorrect_password(
    connection,
):
    register_user(connection, "user@example.com", "secret")

    assert verify_user_password(connection, "USER@EXAMPLE.COM", "secret") is True
    assert verify_user_password(connection, "user@example.com", "wrong") is False


def test_account_survives_closing_and_reopening_database(tmp_path):
    database_path = tmp_path / "persistent_test.sqlite3"
    first_connection = db.connect(database_path)
    register_user(first_connection, "user@example.com", "secret")
    first_connection.close()

    second_connection = db.connect(database_path)
    try:
        assert verify_user_password(second_connection, "user@example.com", "secret") is True
    finally:
        second_connection.close()


def test_authenticated_user_can_create_and_reopen_listing(tmp_path):
    database_path = tmp_path / "listing_test.sqlite3"
    first_connection = db.connect(database_path)
    owner_id = register_user(first_connection, "owner@example.com", "secret")
    create_listing(
        first_connection,
        owner_id,
        "Dry and secure garage",
        "Lisbon",
        "A clean garage near the city center.",
        12.5,
        80.0,
        "2026-12-01",
        30,
        "2027-01-15",
    )
    first_connection.close()

    second_connection = db.connect(database_path)
    try:
        listings = db.get_listings(second_connection)
        assert len(listings) == 1
        assert listings[0]["title"] == "Dry and secure garage"
        assert listings[0]["available_until"] == "2027-01-15"
        assert "owner@example.com" not in dict(listings[0]).values()
    finally:
        second_connection.close()


def test_get_listing_by_id_returns_only_the_requested_listing(connection):
    owner_id = register_user(connection, "owner@example.com", "secret")
    first_listing_id = create_listing(
        connection,
        owner_id,
        "Garage",
        "Lisbon",
        "Dry storage.",
        12,
        80,
        "2026-12-01",
        30,
    )
    create_listing(
        connection,
        owner_id,
        "Basement",
        "Porto",
        "Secure storage.",
        8,
        50,
        "2026-12-01",
        30,
    )

    listing = db.get_listing_by_id(connection, first_listing_id)

    assert listing["id"] == first_listing_id
    assert listing["title"] == "Garage"
    assert db.get_listing_by_id(connection, 99999) is None


@pytest.mark.parametrize(
    "values",
    [
        ("", "Lisbon", "Description", 10, 50, "2026-12-01", 30),
        ("Title", "", "Description", 10, 50, "2026-12-01", 30),
        ("Title", "Lisbon", "", 10, 50, "2026-12-01", 30),
        ("Title", "Lisbon", "Description", 0, 50, "2026-12-01", 30),
        ("Title", "Lisbon", "Description", 10, -1, "2026-12-01", 30),
        ("Title", "Lisbon", "Description", 10, 50, "2026-12-01", 0),
    ],
)
def test_listing_validation_rejects_invalid_values(connection, values):
    owner_id = register_user(connection, "owner@example.com", "secret")
    with pytest.raises(ValueError):
        create_listing(connection, owner_id, *values)


def test_listing_without_end_date_is_unlimited(connection):
    owner_id = register_user(connection, "owner@example.com", "secret")

    create_listing(
        connection,
        owner_id,
        "Storage room",
        "Lisbon",
        "A dry room.",
        8,
        40,
        "2026-12-01",
        30,
    )

    assert db.get_listings(connection)[0]["available_until"] is None


def test_sqlite_listing_rows_include_an_empty_photo_url(connection):
    owner_id = register_user(connection, "owner@example.com", "secret")
    create_listing(
        connection,
        owner_id,
        "Storage room",
        "Lisbon",
        "A dry room.",
        8,
        40,
        "2026-12-01",
        30,
    )

    assert db.get_listings(connection)[0]["photo_url"] is None
    assert db.get_listings_by_owner(connection, owner_id)[0]["photo_url"] is None


def test_listing_public_location_is_rounded_and_available_to_map_views(connection):
    owner_id = register_user(connection, "owner@example.com", "secret")
    listing_id = create_listing(
        connection,
        owner_id,
        "Map-ready storage",
        "Lisbon",
        "A dry room with an approximate map pin.",
        8,
        40,
        "2026-12-01",
        30,
        public_latitude=38.726,
        public_longitude=-9.134,
    )

    public_listing = db.get_listings(connection)[0]
    owner_listing = db.get_listings_by_owner(connection, owner_id)[0]

    assert public_listing["id"] == listing_id
    assert public_listing["public_latitude"] == 38.73
    assert public_listing["public_longitude"] == -9.13
    assert "owner_id" not in public_listing.keys()
    assert owner_listing["public_latitude"] == 38.73
    assert owner_listing["public_longitude"] == -9.13


@pytest.mark.parametrize(
    ("public_latitude", "public_longitude"),
    [
        (38.72, None),
        (None, -9.13),
        (90.01, 0),
        (-90.01, 0),
        (0, 180.01),
        (0, -180.01),
        ("not a latitude", 0),
        (0, "not a longitude"),
        (float("inf"), 0),
    ],
)
def test_listing_rejects_invalid_public_locations(
    connection, public_latitude, public_longitude
):
    owner_id = register_user(connection, "owner@example.com", "secret")

    with pytest.raises(ValueError):
        create_listing(
            connection,
            owner_id,
            "Storage room",
            "Lisbon",
            "A dry room.",
            8,
            40,
            "2026-12-01",
            30,
            public_latitude=public_latitude,
            public_longitude=public_longitude,
        )


def test_listing_update_can_preserve_change_and_clear_public_location(connection):
    owner_id = register_user(connection, "owner@example.com", "secret")
    listing_id = create_listing(
        connection,
        owner_id,
        "Map-ready storage",
        "Lisbon",
        "A dry room with an approximate map pin.",
        8,
        40,
        "2026-12-01",
        30,
        public_latitude=38.72,
        public_longitude=-9.14,
    )

    update_listing(
        connection,
        owner_id,
        listing_id,
        "Updated storage",
        "Lisbon",
        "An updated room.",
        10,
        45,
        "2026-12-01",
        30,
    )
    listing = db.get_listings(connection)[0]
    assert listing["public_latitude"] == 38.72
    assert listing["public_longitude"] == -9.14

    update_listing(
        connection,
        owner_id,
        listing_id,
        "Updated storage",
        "Porto",
        "An updated room.",
        10,
        45,
        "2026-12-01",
        30,
        public_latitude=41.154,
        public_longitude=-8.629,
        update_public_location=True,
    )
    listing = db.get_listings(connection)[0]
    assert listing["public_latitude"] == 41.15
    assert listing["public_longitude"] == -8.63

    update_listing(
        connection,
        owner_id,
        listing_id,
        "Updated storage",
        "Porto",
        "An updated room.",
        10,
        45,
        "2026-12-01",
        30,
        public_latitude=None,
        public_longitude=None,
        update_public_location=True,
    )
    listing = db.get_listings(connection)[0]
    assert listing["public_latitude"] is None
    assert listing["public_longitude"] is None


def test_connect_migrates_existing_listing_for_public_map_locations(tmp_path):
    database_path = tmp_path / "legacy_listing.sqlite3"
    legacy_connection = sqlite3.connect(database_path)
    legacy_connection.execute(
        """
        CREATE TABLE listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            city TEXT NOT NULL,
            description TEXT NOT NULL,
            size_sqm REAL NOT NULL,
            price_per_month_eur REAL NOT NULL,
            available_from TEXT NOT NULL,
            minimum_rental_days INTEGER NOT NULL
        )
        """
    )
    legacy_connection.execute(
        """
        INSERT INTO listings (
            owner_id, title, city, description, size_sqm,
            price_per_month_eur, available_from, minimum_rental_days
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (1, "Legacy listing", "Lisbon", "A legacy room.", 8, 40, "2026-12-01", 30),
    )
    legacy_connection.commit()
    legacy_connection.close()

    connection = db.connect(database_path)
    try:
        columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(listings)")
        }
        listing = db.get_listings(connection)[0]

        assert {"public_latitude", "public_longitude"} <= columns
        assert listing["public_latitude"] is None
        assert listing["public_longitude"] is None
    finally:
        connection.close()


def test_listing_filters_apply_all_criteria(connection):
    owner_id = register_user(connection, "owner@example.com", "secret")
    matching_listing_id = create_listing(
        connection,
        owner_id,
        "Matches all filters",
        "Lisbon",
        "A matching listing.",
        10,
        50,
        "2026-12-01",
        30,
        "2026-12-31",
    )
    create_listing(
        connection,
        owner_id,
        "Different city",
        "Porto",
        "A listing in another city.",
        20,
        40,
        "2026-12-01",
        30,
        "2026-12-31",
    )
    create_listing(
        connection,
        owner_id,
        "Too small",
        "Lisbon",
        "A smaller listing.",
        9,
        40,
        "2026-12-01",
        30,
        "2026-12-31",
    )
    create_listing(
        connection,
        owner_id,
        "Too expensive",
        "Lisbon",
        "A more expensive listing.",
        10,
        51,
        "2026-12-01",
        30,
        "2026-12-31",
    )
    create_listing(
        connection,
        owner_id,
        "Not available yet",
        "Lisbon",
        "A future listing.",
        10,
        40,
        "2027-01-01",
        30,
    )

    listings = db.get_listings(
        connection,
        city="  lisb  ",
        minimum_size_sqm=10,
        maximum_price_per_month_eur=50,
        available_on="2026-12-15",
    )

    assert [listing["id"] for listing in listings] == [matching_listing_id]
    assert "owner_id" not in listings[0].keys()


def test_listing_availability_filter_includes_bounds_and_unlimited_listings(
    connection,
):
    owner_id = register_user(connection, "owner@example.com", "secret")
    available_from_id = create_listing(
        connection,
        owner_id,
        "Available from boundary",
        "Lisbon",
        "Available on its first day.",
        10,
        50,
        "2026-12-15",
        30,
        "2027-01-31",
    )
    available_until_id = create_listing(
        connection,
        owner_id,
        "Available until boundary",
        "Lisbon",
        "Available on its last day.",
        10,
        50,
        "2026-11-01",
        30,
        "2026-12-15",
    )
    unlimited_id = create_listing(
        connection,
        owner_id,
        "Unlimited listing",
        "Lisbon",
        "No end date.",
        10,
        50,
        "2026-11-01",
        30,
    )
    create_listing(
        connection,
        owner_id,
        "Already unavailable",
        "Lisbon",
        "Ended before the selected day.",
        10,
        50,
        "2026-11-01",
        30,
        "2026-12-14",
    )
    create_listing(
        connection,
        owner_id,
        "Not yet available",
        "Lisbon",
        "Starts after the selected day.",
        10,
        50,
        "2026-12-16",
        30,
    )

    listings = db.get_listings(connection, available_on="2026-12-15")

    assert {listing["id"] for listing in listings} == {
        available_from_id,
        available_until_id,
        unlimited_id,
    }


def test_listing_end_date_must_fit_period(connection):
    owner_id = register_user(connection, "owner@example.com", "secret")

    with pytest.raises(ValueError):
        create_listing(
            connection,
            owner_id,
            "Storage room",
            "Lisbon",
            "A dry room.",
            8,
            40,
            "2026-12-10",
            30,
            "2026-12-20",
        )

    with pytest.raises(ValueError):
        create_listing(
            connection,
            owner_id,
            "Storage room",
            "Lisbon",
            "A dry room.",
            8,
            40,
            "2026-12-10",
            5,
            "2026-12-01",
        )


def test_only_owner_can_update_or_delete_listing(connection):
    owner_id = register_user(connection, "owner@example.com", "secret")
    other_user_id = register_user(connection, "other@example.com", "secret")
    listing_id = create_listing(
        connection,
        owner_id,
        "Owner listing",
        "Lisbon",
        "Original description",
        10,
        50,
        "2026-12-01",
        30,
    )

    with pytest.raises(PermissionError):
        update_listing(
            connection,
            other_user_id,
            listing_id,
            "Changed by another user",
            "Porto",
            "Should be rejected",
            20,
            70,
            "2026-12-01",
            30,
        )
    with pytest.raises(PermissionError):
        delete_listing(connection, other_user_id, listing_id)

    listing = db.get_listings(connection)[0]
    assert listing["title"] == "Owner listing"


def test_owner_can_update_and_delete_listing(connection):
    owner_id = register_user(connection, "owner@example.com", "secret")
    listing_id = create_listing(
        connection,
        owner_id,
        "Original title",
        "Lisbon",
        "Original description",
        10,
        50,
        "2026-12-01",
        30,
    )

    update_listing(
        connection,
        owner_id,
        listing_id,
        "Updated title",
        "Porto",
        "Updated description",
        12,
        60,
        "2026-12-10",
        20,
        "2027-01-15",
    )
    assert db.get_listings(connection)[0]["title"] == "Updated title"

    delete_listing(connection, owner_id, listing_id)
    assert db.get_listings(connection) == []


def test_owner_can_store_replace_and_remove_photo(connection):
    owner_id = register_user(connection, "owner@example.com", "secret")
    first_photo = make_png()
    listing_id = create_listing(
        connection,
        owner_id,
        "Photo listing",
        "Lisbon",
        "A listing with a photo.",
        10,
        50,
        "2026-12-01",
        30,
        None,
        first_photo,
        "image/png",
    )
    listing = db.get_listings(connection)[0]
    assert listing["photo_data"] == first_photo
    assert listing["photo_mime_type"] == "image/png"

    second_photo = make_png()
    update_listing(
        connection,
        owner_id,
        listing_id,
        "Photo listing",
        "Lisbon",
        "Updated photo.",
        10,
        50,
        "2026-12-01",
        30,
        None,
        second_photo,
        "image/png",
    )
    assert db.get_listings(connection)[0]["photo_data"] == second_photo

    update_listing(
        connection,
        owner_id,
        listing_id,
        "Photo listing",
        "Lisbon",
        "Photo removed.",
        10,
        50,
        "2026-12-01",
        30,
        None,
        None,
        None,
    )
    assert db.get_listings(connection)[0]["photo_data"] is None


@pytest.mark.parametrize(
    "photo_data",
    [b"not an image", b"x" * (5 * 1024 * 1024 + 1)],
)
def test_listing_rejects_invalid_or_oversized_photo(connection, photo_data):
    owner_id = register_user(connection, "owner@example.com", "secret")

    with pytest.raises(ValueError):
        create_listing(
            connection,
            owner_id,
            "Photo listing",
            "Lisbon",
            "A listing.",
            10,
            50,
            "2026-12-01",
            30,
            None,
            photo_data,
            "image/png",
        )
