from auth_session import SESSION_TTL_SECONDS, create_session, read_session


def test_session_token_round_trips_and_expires():
    secrets = {"SPACESHARE_SESSION_SECRET": "test-session-secret"}
    token = create_session("user@example.com", secrets, now=100)

    assert read_session(token, secrets, now=100) == "user@example.com"
    assert read_session(token, secrets, now=100 + SESSION_TTL_SECONDS) is None


def test_session_token_rejects_tampering_and_wrong_secret():
    secrets = {"SPACESHARE_SESSION_SECRET": "test-session-secret"}
    token = create_session("user@example.com", secrets, now=100)
    encoded, signature = token.split(".")

    assert read_session(encoded + "x." + signature, secrets, now=100) is None
    assert read_session(token, {"SPACESHARE_SESSION_SECRET": "other"}, now=100) is None
