"""Tests for the Streamlit application's local startup behavior."""

import app


class _StreamlitWithoutSecrets:
    class _Secrets:
        def __contains__(self, key):
            raise FileNotFoundError("No local Streamlit secrets file")

    secrets = _Secrets()


def test_get_connection_falls_back_to_sqlite_without_streamlit_secrets(monkeypatch):
    connection = object()
    monkeypatch.setattr(app, "st", _StreamlitWithoutSecrets())
    monkeypatch.setattr(app.db, "connect", lambda path: connection)

    assert app.get_connection() is connection
