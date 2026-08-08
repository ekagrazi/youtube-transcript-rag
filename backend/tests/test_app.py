import asyncio
from uuid import UUID

import httpx

from app.auth.dependencies import get_current_user
from app.main import app


async def request(path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        return await client.get(path)


def test_health() -> None:
    response = asyncio.run(request("/health"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_protected_route_rejects_missing_token() -> None:
    response = asyncio.run(request("/auth/me"))

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_protected_route_accepts_verified_user() -> None:
    expected_user_id = UUID("7d796a8f-2f89-4dc4-9b67-3996e1e76f23")
    app.dependency_overrides[get_current_user] = lambda: expected_user_id

    try:
        response = asyncio.run(request("/auth/me"))
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"user_id": str(expected_user_id)}
