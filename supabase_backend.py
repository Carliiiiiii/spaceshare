"""Supabase connection configuration for the optional hosted backend."""

from dataclasses import dataclass
from typing import Any

from supabase import Client, create_client


@dataclass(frozen=True)
class SupabaseSettings:
    """Non-secret connection settings loaded from Streamlit secrets."""

    url: str
    service_role_key: str
    storage_bucket: str = "listing-photos"


@dataclass
class SupabaseConnection:
    """Connection wrapper used by the data-access layer."""

    client: Client
    settings: SupabaseSettings

    def close(self) -> None:
        """Match the SQLite connection interface; the client is reusable."""
        return None


def settings_from_streamlit_secrets(secrets: Any) -> SupabaseSettings:
    """Build settings without printing or exposing the secret key."""
    try:
        url = str(secrets["SUPABASE_URL"]).strip()
        service_role_key = str(secrets["SUPABASE_SERVICE_ROLE_KEY"]).strip()
    except (KeyError, TypeError) as error:
        raise RuntimeError(
            "Supabase secrets are incomplete. Configure SUPABASE_URL and "
            "SUPABASE_SERVICE_ROLE_KEY in Streamlit Secrets."
        ) from error

    bucket = str(secrets.get("SUPABASE_STORAGE_BUCKET", "listing-photos")).strip()
    if not url or not service_role_key or not bucket:
        raise RuntimeError(
            "Supabase secrets must contain a URL, service role key, and storage bucket."
        )
    return SupabaseSettings(url, service_role_key, bucket)


def create_supabase_client(secrets: Any) -> SupabaseConnection:
    """Create the server-side client used by Streamlit Community Cloud."""
    settings = settings_from_streamlit_secrets(secrets)
    return SupabaseConnection(create_client(settings.url, settings.service_role_key), settings)
