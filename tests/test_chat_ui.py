"""Chat interactions preserve the conversation and clear only sent drafts."""

from unittest.mock import Mock

import pytest
from streamlit.testing.v1 import AppTest

import app


def _chat_page(kind):
    import streamlit as st
    import app

    _, chat_tab = st.tabs(
        ["Browse", "Chats"],
        key="main_navigation",
        on_change="rerun",
    )
    conversation = {"id": 1, "owner_id": 2, "title": "Garage", "owner_name": "Owner"}
    with chat_tab:
        if kind == "listing":
            app.show_listing_conversation_chat(None, 1, conversation)
        else:
            app.show_request_chat(None, 1, conversation)


@pytest.mark.parametrize("kind", ["listing", "request"])
def test_chat_send_and_refresh_preserve_drafts_and_open_chat(monkeypatch, kind):
    if kind == "listing":
        read, mark, send = (
            "get_listing_conversation_messages",
            "mark_listing_conversation_messages_read",
            "send_listing_conversation_message",
        )
        chat_key, input_key = "listing_chat_1", "listing_conversation_message_text_1"
    else:
        read, mark, send = "get_messages", "mark_messages_read", "send_message"
        chat_key, input_key = "request_chat_1", "message_text_1"
    monkeypatch.setattr(app, read, lambda *args: [])
    monkeypatch.setattr(app, mark, lambda *args: None)
    sender = Mock()
    monkeypatch.setattr(app, send, sender)
    page = AppTest.from_function(_chat_page, args=(kind,))
    page.session_state["main_navigation"] = "Chats"
    page.session_state[chat_key] = True
    page.run()
    page.text_area(key=input_key).input("Hello")
    page.button[0].click().run()
    assert not page.exception
    sender.assert_called_once_with(None, 1, 1, "Hello")
    assert page.text_area(key=input_key).value == ""
    assert page.session_state["active_chat"] == chat_key
    assert page.session_state["main_navigation"] == "Chats"
    assert page.expander[0].proto.expanded

    page.text_area(key=input_key).input("Unsent draft")
    page.button[1].click().run()
    assert not page.exception
    assert page.text_area(key=input_key).value == "Unsent draft"
    assert page.expander[0].proto.expanded
    assert sender.call_count == 1

    sender.side_effect = ValueError("Please try again")
    page.button[0].click().run()
    assert not page.exception
    assert page.text_area(key=input_key).value == "Unsent draft"
    assert page.error[0].value == "Please try again"
