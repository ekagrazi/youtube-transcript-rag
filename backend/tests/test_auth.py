import asyncio
from uuid import UUID

import httpx
import pytest
from fastapi import HTTPException

from app.auth.dependencies import verify_access_token
from app.config import Settings

USER_ID = UUID("2fcaeb9a-7e37-4ba7-92bf-193ce83793bb")


def settings() -> Settings:
    return Settings(
        supabase_url="https://example.supabase.co",
        supabase_publishable_key="sb_publishable_test",
    )


def test_verify_access_token_returns_user_id() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["apikey"] == "sb_publishable_test"
        assert request.headers["authorization"] == "Bearer valid-token"
        return httpx.Response(200, json={"id": str(USER_ID)})

    result = asyncio.run(
        verify_access_token(
            "valid-token",
            settings(),
            transport=httpx.MockTransport(handler),
        )
    )

    assert result == USER_ID


def test_verify_access_token_rejects_invalid_token() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(401, json={"message": "invalid token"})
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            verify_access_token(
                "invalid-token",
                settings(),
                transport=transport,
            )
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid or expired access token"
