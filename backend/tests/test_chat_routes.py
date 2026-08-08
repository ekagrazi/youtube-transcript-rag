import asyncio
from datetime import UTC, datetime

import httpx

from app.main import app
from app.routers.chat_router import get_rag_service
from app.schemas.chat import ChatResponse, ChatSource
from app.services.chat_repository import ChatMessageRecord
from app.services.rag_service import VideoNotFoundError, VideoNotReadyError


class FakeRagService:
    def chat(self, video_id: int, question: str) -> ChatResponse:
        return ChatResponse(
            answer="Grounded answer",
            sources=[
                ChatSource(
                    start_time=12,
                    end_time=18,
                    text="Transcript source",
                    similarity=0.9,
                    youtube_id="dQw4w9WgXcQ",
                    youtube_url=(
                        "https://www.youtube.com/watch?"
                        "v=dQw4w9WgXcQ&t=12s"
                    ),
                )
            ],
        )

    def history(self, video_id: int) -> list[ChatMessageRecord]:
        return [
            ChatMessageRecord(
                id=1,
                video_id=video_id,
                role="user",
                content="Question",
                created_at=datetime.now(UTC),
            )
        ]


async def request(
    method: str,
    path: str,
    **kwargs: object,
) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        return await client.request(method, path, **kwargs)


def test_chat_routes_require_authentication() -> None:
    response = asyncio.run(
        request("POST", "/chat/7", json={"question": "What?"})
    )

    assert response.status_code == 401


def test_chat_and_history_routes() -> None:
    app.dependency_overrides[get_rag_service] = FakeRagService
    try:
        chat_response = asyncio.run(
            request(
                "POST",
                "/chat/7",
                json={"question": " What happened? "},
            )
        )
        history_response = asyncio.run(
            request("GET", "/chat/7/history")
        )
    finally:
        app.dependency_overrides.clear()

    assert chat_response.status_code == 200
    assert chat_response.json()["answer"] == "Grounded answer"
    assert chat_response.json()["sources"][0]["start_time"] == 12
    assert history_response.status_code == 200
    assert history_response.json()[0]["role"] == "user"


def test_chat_route_maps_unknown_and_pending_videos() -> None:
    class UnknownService(FakeRagService):
        def chat(self, video_id: int, question: str) -> ChatResponse:
            raise VideoNotFoundError

    app.dependency_overrides[get_rag_service] = UnknownService
    try:
        unknown_response = asyncio.run(
            request("POST", "/chat/999", json={"question": "What?"})
        )
    finally:
        app.dependency_overrides.clear()

    class PendingService(FakeRagService):
        def chat(self, video_id: int, question: str) -> ChatResponse:
            raise VideoNotReadyError("pending")

    app.dependency_overrides[get_rag_service] = PendingService
    try:
        pending_response = asyncio.run(
            request("POST", "/chat/7", json={"question": "What?"})
        )
    finally:
        app.dependency_overrides.clear()

    assert unknown_response.status_code == 404
    assert pending_response.status_code == 409
