import asyncio
from datetime import UTC, datetime
from uuid import UUID

import httpx

from app.auth.dependencies import get_current_user
from app.main import app
from app.routers.ingest_router import get_ingestion_service
from app.services.vectorstore_service import VideoRecord

USER_ID = UUID("f442dfa1-ccac-4409-9b93-947e3bb39630")
VIDEO_ID = "dQw4w9WgXcQ"


def ready_video() -> VideoRecord:
    now = datetime.now(UTC)
    return VideoRecord(
        id=1,
        youtube_id=VIDEO_ID,
        title=None,
        status="ready",
        error_message=None,
        created_at=now,
        updated_at=now,
    )


class FakeIngestionService:
    def ingest(self, youtube_url: str, user_id: UUID) -> VideoRecord:
        assert user_id == USER_ID
        return ready_video()

    def list_videos(self, user_id: UUID) -> list[VideoRecord]:
        assert user_id == USER_ID
        return [ready_video()]

    def delete_video(self, user_id: UUID, video_id: int) -> bool:
        return user_id == USER_ID and video_id == 1


async def request(method: str, path: str, **kwargs: object) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        return await client.request(method, path, **kwargs)


def test_video_routes_require_authentication() -> None:
    response = asyncio.run(request("GET", "/videos"))

    assert response.status_code == 401


def test_ingest_and_list_video_routes() -> None:
    app.dependency_overrides[get_current_user] = lambda: USER_ID
    app.dependency_overrides[get_ingestion_service] = FakeIngestionService
    try:
        ingest_response = asyncio.run(
            request(
                "POST",
                "/videos/ingest",
                json={"youtube_url": f"https://youtu.be/{VIDEO_ID}"},
            )
        )
        list_response = asyncio.run(request("GET", "/videos"))
        delete_response = asyncio.run(request("DELETE", "/videos/1"))
    finally:
        app.dependency_overrides.clear()

    assert ingest_response.status_code == 200
    assert ingest_response.json()["status"] == "ready"
    assert list_response.status_code == 200
    assert list_response.json()[0]["youtube_id"] == VIDEO_ID
    assert delete_response.status_code == 204
