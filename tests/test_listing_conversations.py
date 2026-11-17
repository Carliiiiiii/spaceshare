import pytest

import db
from logic import (
    create_listing,
    get_listing_conversation_messages,
    get_listing_conversations,
    get_unread_message_count,
    mark_listing_conversation_messages_read,
    register_user,
    send_listing_conversation_message,
    send_listing_question,
    start_listing_conversation,
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


def test_listing_question_creates_and_reuses_a_private_conversation(connection):
    owner_id, requester_id, listing_id = make_listing(connection)

    conversation_id = send_listing_question(
        connection, listing_id, requester_id, "Is the garage accessible on weekends?"
    )
    reused_conversation_id = send_listing_question(
        connection, listing_id, requester_id, "What is the ceiling height?"
    )

    assert reused_conversation_id == conversation_id
    assert [conversation["id"] for conversation in get_listing_conversations(connection, requester_id)] == [
        conversation_id
    ]
    assert [conversation["id"] for conversation in get_listing_conversations(connection, owner_id)] == [
        conversation_id
    ]
    assert [
        message["message"]
        for message in get_listing_conversation_messages(
            connection, conversation_id, owner_id
        )
    ] == [
        "Is the garage accessible on weekends?",
        "What is the ceiling height?",
    ]


def test_listing_owner_cannot_start_a_conversation_about_own_listing(connection):
    owner_id, _, listing_id = make_listing(connection)

    with pytest.raises(PermissionError, match="own listing"):
        start_listing_conversation(connection, listing_id, owner_id)


def test_only_conversation_participants_can_read_or_send_messages(connection):
    owner_id, requester_id, listing_id = make_listing(connection)
    third_user_id = register_user(connection, "third@example.com", "secret")
    conversation_id = send_listing_question(
        connection, listing_id, requester_id, "Is there an elevator?"
    )

    send_listing_conversation_message(
        connection, conversation_id, owner_id, "Yes, there is an elevator."
    )

    with pytest.raises(PermissionError):
        get_listing_conversation_messages(connection, conversation_id, third_user_id)
    with pytest.raises(PermissionError):
        send_listing_conversation_message(
            connection, conversation_id, third_user_id, "Private message"
        )


@pytest.mark.parametrize("message", ["", "   ", "x" * 1001])
def test_listing_conversation_messages_reject_invalid_text(connection, message):
    _, requester_id, listing_id = make_listing(connection)
    conversation_id = start_listing_conversation(connection, listing_id, requester_id)

    with pytest.raises(ValueError):
        send_listing_conversation_message(
            connection, conversation_id, requester_id, message
        )


@pytest.mark.parametrize("message", ["", "   ", "x" * 1001])
def test_invalid_first_question_does_not_create_a_conversation(connection, message):
    _, requester_id, listing_id = make_listing(connection)

    with pytest.raises(ValueError):
        send_listing_question(connection, listing_id, requester_id, message)

    assert get_listing_conversations(connection, requester_id) == []


def test_direct_listing_messages_update_the_chat_unread_count(connection):
    owner_id, requester_id, listing_id = make_listing(connection)
    conversation_id = send_listing_question(
        connection, listing_id, requester_id, "Is the space heated?"
    )

    assert get_unread_message_count(connection, owner_id) == 1
    assert get_unread_message_count(connection, requester_id) == 0

    mark_listing_conversation_messages_read(connection, conversation_id, owner_id)
    assert get_unread_message_count(connection, owner_id) == 0

    send_listing_conversation_message(
        connection, conversation_id, owner_id, "Yes, the space is heated."
    )
    assert get_unread_message_count(connection, requester_id) == 1


def test_listing_conversations_survive_database_reopen(tmp_path):
    database_path = tmp_path / "listing_conversations.sqlite3"
    first_connection = db.connect(database_path)
    owner_id, requester_id, listing_id = make_listing(first_connection)
    conversation_id = send_listing_question(
        first_connection, listing_id, requester_id, "Can I visit before renting?"
    )
    first_connection.close()

    second_connection = db.connect(database_path)
    try:
        messages = get_listing_conversation_messages(
            second_connection, conversation_id, owner_id
        )
        assert messages[0]["message"] == "Can I visit before renting?"
    finally:
        second_connection.close()
