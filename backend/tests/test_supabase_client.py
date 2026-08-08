import pytest

from app.config import Settings
from app.supabase_client import get_service_client, get_user_client


def test_user_client_uses_callers_access_token() -> None:
    settings = Settings(
        supabase_url="https://example.supabase.co",
        supabase_publishable_key="sb_publishable_test",
    )

    client = get_user_client("user-access-token", settings)

    assert client.postgrest.headers["Authorization"] == "Bearer user-access-token"


def test_service_client_requires_backend_secret() -> None:
    settings = Settings(
        _env_file=None,
        supabase_url="https://example.supabase.co",
        supabase_publishable_key="sb_publishable_test",
    )

    with pytest.raises(RuntimeError, match="SUPABASE_SECRET_KEY"):
        get_service_client(settings)
