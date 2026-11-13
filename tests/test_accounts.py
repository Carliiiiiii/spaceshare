import sqlite3
from io import BytesIO

import pytest
from PIL import Image

import db
from logic import (
    create_rental_request,
    create_listing,
    delete_listing,
    register_user,
    update_listing,
    verify_user_password,
    update_rental_request_status,
)


def make_png() -> bytes:
    image = Image.new("RGB", (2, 2), color="red")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def connection(tmp_path):
    database_path = tmp_path / "test_spaceshare.sqlite3"
    connection = db.connect(database_path)
    yield connection
    connection.close()


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


def make_listing(connection):
    owner_id = register_user(connection, "owner@example.com", "secret")
    requester_id = register_user(connection, "requester@example.com", "secret")
    listing_id = create_listing(
        connection, owner_id, "Garage", "Lisbon", "Secure garage", 10, 50,
        "2026-12-01", 30, "2027-01-31"
    )
    return owner_id, requester_id, listing_id


def test_rental_request_validates_period_and_is_visible_to_both_users(connection):
    owner_id, requester_id, listing_id = make_listing(connection)
    request_id = create_rental_request(
        connection, listing_id, requester_id, "2026-12-01", "2026-12-31"
    )
    requests_for_owner = db.get_rental_requests_for_user(connection, owner_id)
    requests_for_requester = db.get_rental_requests_for_user(connection, requester_id)
    assert requests_for_owner[0]["id"] == request_id
    assert requests_for_requester[0]["status"] == "pending"


@pytest.mark.parametrize(
    ("start_date", "end_date"),
    [("2026-11-30", "2026-12-31"), ("2026-12-01", "2027-02-01"), ("2026-12-01", "2026-12-15")],
)
def test_rental_request_rejects_out_of_range_or_short_period(connection, start_date, end_date):
    _, requester_id, listing_id = make_listing(connection)
    with pytest.raises(ValueError):
        create_rental_request(connection, listing_id, requester_id, start_date, end_date)


def test_only_listing_owner_can_change_request_status(connection):
    owner_id, requester_id, listing_id = make_listing(connection)
    request_id = create_rental_request(
        connection, listing_id, requester_id, "2026-12-01", "2026-12-31"
    )
    with pytest.raises(PermissionError):
        update_rental_request_status(connection, request_id, requester_id, "accepted")
    update_rental_request_status(connection, request_id, owner_id, "accepted")
    assert db.get_rental_requests_for_user(connection, requester_id)[0]["status"] == "accepted"


def test_overlapping_request_cannot_be_accepted_and_remains_pending(connection):
    owner_id, requester_id, listing_id = make_listing(connection)
    first_request = create_rental_request(
        connection, listing_id, requester_id, "2026-12-01", "2026-12-31"
    )
    second_request = create_rental_request(
        connection, listing_id, requester_id, "2026-12-15", "2027-01-14"
    )
    update_rental_request_status(connection, first_request, owner_id, "accepted")
    with pytest.raises(ValueError, match="overlaps an accepted request"):
        update_rental_request_status(connection, second_request, owner_id, "accepted")
    statuses = {row["id"]: row["status"] for row in db.get_rental_requests_for_user(connection, owner_id)}
    assert statuses[second_request] == "pending"


def test_directly_following_request_can_be_accepted(connection):
    owner_id, requester_id, listing_id = make_listing(connection)
    first_request = create_rental_request(
        connection, listing_id, requester_id, "2026-12-01", "2026-12-31"
    )
    following_request = create_rental_request(
        connection, listing_id, requester_id, "2026-12-31", "2027-01-30"
    )
    update_rental_request_status(connection, first_request, owner_id, "accepted")
    update_rental_request_status(connection, following_request, owner_id, "accepted")
    statuses = {row["id"]: row["status"] for row in db.get_rental_requests_for_user(connection, owner_id)}
    assert statuses[following_request] == "accepted"
