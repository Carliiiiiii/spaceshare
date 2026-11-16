import pytest

import db
from logic import (
    create_listing,
    create_rental_request,
    get_messages,
    get_unread_message_count,
    mark_messages_read,
    register_user,
    send_message,
    update_rental_request_status,
)


def make_listing(connection):
    owner_id = register_user(connection, "owner@example.com", "secret")
    requester_id = register_user(connection, "requester@example.com", "secret")
    listing_id = create_listing(
        connection,
        owner_id,
        "Garage",
        "Lisbon",
        "Secure garage",
        10,
        50,
        "2026-12-01",
        30,
        "2027-01-31",
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
    [
        ("2026-11-30", "2026-12-31"),
        ("2026-12-01", "2027-02-01"),
        ("2026-12-01", "2026-12-15"),
    ],
)
def test_rental_request_rejects_out_of_range_or_short_period(
    connection, start_date, end_date
):
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

    assert (
        db.get_rental_requests_for_user(connection, requester_id)[0]["status"]
        == "accepted"
    )


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

    statuses = {
        row["id"]: row["status"]
        for row in db.get_rental_requests_for_user(connection, owner_id)
    }
    assert statuses[second_request] == "pending"


def test_overlapping_request_is_created_pending_when_period_is_already_accepted(connection):
    owner_id, requester_id, listing_id = make_listing(connection)
    accepted_id = create_rental_request(
        connection, listing_id, requester_id, "2026-12-01", "2026-12-31"
    )
    update_rental_request_status(connection, accepted_id, owner_id, "accepted")

    overlapping_id = create_rental_request(
        connection, listing_id, requester_id, "2026-12-15", "2027-01-14"
    )
    request = db.get_rental_requests_for_user(connection, owner_id)[0]
    assert request["id"] == overlapping_id
    assert request["status"] == "pending"


def test_directly_following_request_can_be_accepted(connection):
    owner_id, requester_id, listing_id = make_listing(connection)
    first_request = create_rental_request(
        connection, listing_id, requester_id, "2026-12-01", "2026-12-31"
    )
    update_rental_request_status(connection, first_request, owner_id, "accepted")

    following_request = create_rental_request(
        connection, listing_id, requester_id, "2026-12-31", "2027-01-30"
    )

    update_rental_request_status(connection, following_request, owner_id, "accepted")

    statuses = {
        row["id"]: row["status"]
        for row in db.get_rental_requests_for_user(connection, owner_id)
    }
    assert statuses[following_request] == "accepted"


@pytest.mark.parametrize(
    ("requested_start", "requested_end"),
    [
        ("2026-12-01", None),
        (None, "2026-12-31"),
        ("2026-12-31", "2026-12-31"),
        ("2027-01-01", "2026-12-31"),
    ],
)
def test_requested_date_range_requires_complete_chronological_dates(
    connection, requested_start, requested_end
):
    with pytest.raises(ValueError):
        db.get_listings(
            connection,
            requested_start=requested_start,
            requested_end=requested_end,
        )


def test_requested_date_range_hides_accepted_overlaps_only(connection):
    owner_id, requester_id, occupied_listing_id = make_listing(connection)
    pending_listing_id = create_listing(
        connection,
        owner_id,
        "Pending-request garage",
        "Lisbon",
        "Still available until a request is accepted.",
        10,
        50,
        "2026-12-01",
        30,
        "2027-01-31",
    )
    accepted_request_id = create_rental_request(
        connection,
        occupied_listing_id,
        requester_id,
        "2026-12-01",
        "2026-12-31",
    )
    create_rental_request(
        connection,
        pending_listing_id,
        requester_id,
        "2026-12-01",
        "2026-12-31",
    )
    update_rental_request_status(
        connection, accepted_request_id, owner_id, "accepted"
    )

    listing_ids = {
        listing["id"]
        for listing in db.get_listings(
            connection,
            requested_start="2026-12-15",
            requested_end="2027-01-15",
        )
    }

    assert occupied_listing_id not in listing_ids
    assert pending_listing_id in listing_ids


def test_requested_date_range_hides_accepted_overlap_but_keeps_adjacent_listing(
    connection,
):
    owner_id, requester_id, listing_id = make_listing(connection)
    accepted_id = create_rental_request(
        connection, listing_id, requester_id, "2026-12-01", "2026-12-31"
    )
    update_rental_request_status(connection, accepted_id, owner_id, "accepted")

    assert db.get_listings(
        connection,
        requested_start="2026-12-15",
        requested_end="2027-01-14",
    ) == []

    assert [
        row["id"]
        for row in db.get_listings(
            connection,
            requested_start="2026-12-31",
            requested_end="2027-01-30",
        )
    ] == [listing_id]


def test_accepted_rental_request_overlap_uses_half_open_periods(connection):
    owner_id, requester_id, listing_id = make_listing(connection)
    request_id = create_rental_request(
        connection, listing_id, requester_id, "2026-12-01", "2026-12-31"
    )

    assert not db.has_accepted_rental_request_overlap(
        connection, listing_id, "2026-12-15", "2026-12-20"
    )

    update_rental_request_status(connection, request_id, owner_id, "accepted")

    assert db.has_accepted_rental_request_overlap(
        connection, listing_id, "2026-12-15", "2026-12-20"
    )
    assert not db.has_accepted_rental_request_overlap(
        connection, listing_id, "2026-12-31", "2027-01-30"
    )
    assert not db.has_accepted_rental_request_overlap(
        connection, listing_id, "2026-11-01", "2026-12-01"
    )


def test_request_participants_can_exchange_messages_in_order(connection):
    owner_id, requester_id, listing_id = make_listing(connection)
    request_id = create_rental_request(
        connection, listing_id, requester_id, "2026-12-01", "2026-12-31"
    )

    send_message(connection, request_id, requester_id, "Is the space accessible on weekends?")
    send_message(connection, request_id, owner_id, "Yes, it is accessible every day.")

    messages = get_messages(connection, request_id, requester_id)
    assert [message["message"] for message in messages] == [
        "Is the space accessible on weekends?",
        "Yes, it is accessible every day.",
    ]
    assert messages[0]["sender_id"] == requester_id
    assert messages[1]["sender_id"] == owner_id


def test_third_account_cannot_read_or_send_request_messages(connection):
    owner_id, requester_id, listing_id = make_listing(connection)
    third_user_id = register_user(connection, "third@example.com", "secret")
    request_id = create_rental_request(
        connection, listing_id, requester_id, "2026-12-01", "2026-12-31"
    )

    with pytest.raises(PermissionError):
        send_message(connection, request_id, third_user_id, "Private message")
    with pytest.raises(PermissionError):
        get_messages(connection, request_id, third_user_id)


@pytest.mark.parametrize("message", ["", "   ", "x" * 1001])
def test_messages_reject_empty_or_too_long_text(connection, message):
    _, requester_id, listing_id = make_listing(connection)
    request_id = create_rental_request(
        connection, listing_id, requester_id, "2026-12-01", "2026-12-31"
    )

    with pytest.raises(ValueError):
        send_message(connection, request_id, requester_id, message)


def test_messages_survive_database_reopen(tmp_path):
    database_path = tmp_path / "messages.sqlite3"
    first_connection = db.connect(database_path)
    owner_id = register_user(first_connection, "owner@example.com", "secret")
    requester_id = register_user(first_connection, "requester@example.com", "secret")
    listing_id = create_listing(
        first_connection, owner_id, "Garage", "Lisbon", "Secure garage", 10, 50,
        "2026-12-01", 30
    )
    request_id = create_rental_request(
        first_connection, listing_id, requester_id, "2026-12-01", "2026-12-31"
    )
    send_message(first_connection, request_id, requester_id, "Saved message")
    first_connection.close()

    second_connection = db.connect(database_path)
    try:
        messages = get_messages(second_connection, request_id, owner_id)
        assert messages[0]["message"] == "Saved message"
    finally:
        second_connection.close()


def test_unread_count_tracks_messages_from_other_participant(connection):
    owner_id, requester_id, listing_id = make_listing(connection)
    request_id = create_rental_request(
        connection, listing_id, requester_id, "2026-12-01", "2026-12-31"
    )
    send_message(connection, request_id, requester_id, "Please confirm access.")
    assert get_unread_message_count(connection, owner_id) == 1
    assert get_unread_message_count(connection, requester_id) == 0

    mark_messages_read(connection, request_id, owner_id)
    assert get_unread_message_count(connection, owner_id) == 0
