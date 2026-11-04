import sqlite3

import pytest

import db
from logic import create_listing, register_user, verify_user_password


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
    )
    first_connection.close()

    second_connection = db.connect(database_path)
    try:
        listings = db.get_listings(second_connection)
        assert len(listings) == 1
        assert listings[0]["title"] == "Dry and secure garage"
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
