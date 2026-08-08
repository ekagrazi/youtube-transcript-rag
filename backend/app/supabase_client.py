"""Supabase client factories with explicit privilege boundaries."""

from supabase import Client, ClientOptions, create_client

from app.config import Settings, get_settings


def _client_options() -> ClientOptions:
    return ClientOptions(
        auto_refresh_token=False,
        persist_session=False,
    )


def get_service_client(settings: Settings | None = None) -> Client:
    """Return a privileged backend-only client.

    This client may bypass RLS and must never be returned to frontend code.
    """

    resolved = settings or get_settings()
    return create_client(
        resolved.require_supabase_url(),
        resolved.require_supabase_secret_key(),
        options=_client_options(),
    )


def get_user_client(access_token: str, settings: Settings | None = None) -> Client:
    """Return a PostgREST client operating with the caller's access token."""

    if not access_token:
        raise ValueError("access_token must not be empty")

    resolved = settings or get_settings()
    client = create_client(
        resolved.require_supabase_url(),
        resolved.require_supabase_publishable_key(),
        options=_client_options(),
    )
    client.postgrest.auth(access_token)
    return client
