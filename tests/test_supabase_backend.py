import pytest

from supabase_backend import SupabaseSettings, settings_from_streamlit_secrets


def test_supabase_settings_read_without_exposing_secret():
    settings = settings_from_streamlit_secrets(
        {
            "SUPABASE_URL": " https://example.supabase.co ",
            "SUPABASE_SERVICE_ROLE_KEY": "test-secret",
            "SUPABASE_STORAGE_BUCKET": "listing-photos",
        }
    )

    assert settings == SupabaseSettings(
        "https://example.supabase.co", "test-secret", "listing-photos"
    )


@pytest.mark.parametrize(
    "secrets",
    [
        {},
        {"SUPABASE_URL": "https://example.supabase.co"},
        {
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_SERVICE_ROLE_KEY": "",
        },
    ],
)
def test_incomplete_supabase_secrets_are_rejected(secrets):
    with pytest.raises(RuntimeError, match="Supabase secrets"):
        settings_from_streamlit_secrets(secrets)
