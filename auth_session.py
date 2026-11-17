"""Signed, short-lived browser sessions for SpaceShare."""

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path
from typing import Any, Optional


COOKIE_NAME = "spaceshare_session"
SESSION_TTL_SECONDS = 60 * 60 * 24 * 7
LOCAL_SECRET_PATH = Path(".spaceshare_session_secret")


def _secret_from_sources(secrets_mapping: Any = None) -> bytes:
    """Load a persistent signing secret without ever exposing it to the client."""
    if secrets_mapping is not None:
        try:
            configured = str(secrets_mapping["SPACESHARE_SESSION_SECRET"]).strip()
            if configured:
                return configured.encode("utf-8")
        except (KeyError, TypeError, FileNotFoundError):
            pass

    configured = os.environ.get("SPACESHARE_SESSION_SECRET", "").strip()
    if configured:
        return configured.encode("utf-8")

    if LOCAL_SECRET_PATH.exists():
        return LOCAL_SECRET_PATH.read_bytes()

    generated = secrets.token_bytes(32)
    LOCAL_SECRET_PATH.write_bytes(generated)
    try:
        LOCAL_SECRET_PATH.chmod(0o600)
    except OSError:
        pass
    return generated


def create_session(email: str, secrets_mapping: Any = None, now: Optional[int] = None) -> str:
    """Create a signed token containing only the normalized email and expiry."""
    issued_at = int(time.time() if now is None else now)
    payload = {"email": email, "exp": issued_at + SESSION_TTL_SECONDS}
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).rstrip(b"=")
    signature = hmac.new(_secret_from_sources(secrets_mapping), encoded, hashlib.sha256).digest()
    return encoded.decode("ascii") + "." + base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")


def read_session(token: Optional[str], secrets_mapping: Any = None, now: Optional[int] = None) -> Optional[str]:
    """Return the session email only when signature and expiry are valid."""
    if not token or token.count(".") != 1:
        return None
    encoded, encoded_signature = token.split(".", 1)
    try:
        padding = "=" * (-len(encoded_signature) % 4)
        signature = base64.urlsafe_b64decode((encoded_signature + padding).encode("ascii"))
        expected = hmac.new(_secret_from_sources(secrets_mapping), encoded.encode("ascii"), hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            return None
        payload_padding = "=" * (-len(encoded) % 4)
        payload = json.loads(base64.urlsafe_b64decode((encoded + payload_padding).encode("ascii")))
        if int(payload["exp"]) <= int(time.time() if now is None else now):
            return None
        email = payload["email"]
        return email if isinstance(email, str) and email else None
    except (ValueError, TypeError, KeyError, json.JSONDecodeError, UnicodeError):
        return None
