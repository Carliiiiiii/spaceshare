import pytest

import db
from logic import create_listing, register_user, toggle_listing_favorite


def make_listing(connection):
    owner_id = register_user(connection, "owner@example.com", "secret")
    listing_id = create_listing(
        connection,
        owner_id,
        "Dry garage",
        "Lisbon",
        "Secure storage.",
        12,
        80,
        "2026-12-01",
        30,
    )
    return listing_id


def test_user_can_save_and_remove_a_listing(connection):
    listing_id = make_listing(connection)
    user_id = register_user(connection, "saver@example.com", "secret")

    assert toggle_listing_favorite(connection, user_id, listing_id) is True
    assert db.get_favorite_listing_ids(connection, user_id) == [listing_id]

    assert toggle_listing_favorite(connection, user_id, listing_id) is False
    assert db.get_favorite_listing_ids(connection, user_id) == []


def test_favorites_are_private_to_each_user(connection):
    listing_id = make_listing(connection)
    first_user_id = register_user(connection, "first@example.com", "secret")
    second_user_id = register_user(connection, "second@example.com", "secret")

    toggle_listing_favorite(connection, first_user_id, listing_id)

    assert db.get_favorite_listing_ids(connection, first_user_id) == [listing_id]
    assert db.get_favorite_listing_ids(connection, second_user_id) == []


def test_cannot_save_a_listing_that_does_not_exist(connection):
    user_id = register_user(connection, "saver@example.com", "secret")

    with pytest.raises(ValueError, match="Listing not found"):
        toggle_listing_favorite(connection, user_id, 99999)
