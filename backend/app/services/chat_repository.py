"""RLS-scoped Supabase persistence and vector retrieval for chat."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from supabase import Client

from app.services.embedding_service import EmbeddingService
from app.services.vectorstore_service import VIDEO_COLUMNS, VideoRecord

CHAT_COLUMNS = "id,video_id,role,content,created_at"


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    content: str
    metadata: dict[str, Any]
    similarity: float


@dataclass(frozen=True, slots=True)
class ChatMessageRecord:
    id: int
    video_id: int
    role: str
    content: str
    created_at: datetime


class ChatRepository:
    """All operations use a caller-token client so Postgres RLS stays authoritative."""

    def __init__(
        self,
        client: Client,
        user_id: UUID,
        embedding_service: EmbeddingService,
    ) -> None:
        self.client = client
        self.user_id = user_id
        self.embedding_service = embedding_service

    def get_video(self, video_id: int) -> VideoRecord | None:
        response = (
            self.client.table("videos")
            .select(VIDEO_COLUMNS)
            .eq("id", video_id)
            .maybe_single()
            .execute()
        )
        if not response.data:
            return None
        return VideoRecord(
            id=int(response.data["id"]),
            youtube_id=str(response.data["youtube_id"]),
            title=(
                str(response.data["title"])
                if response.data.get("title") is not None
                else None
            ),
            status=str(response.data["status"]),
            error_message=(
                str(response.data["error_message"])
                if response.data.get("error_message") is not None
                else None
            ),
            created_at=datetime.fromisoformat(str(response.data["created_at"])),
            updated_at=datetime.fromisoformat(str(response.data["updated_at"])),
        )

    def retrieve(
        self,
        question: str,
        *,
        video_id: int,
        top_k: int,
    ) -> list[RetrievedChunk]:
        query_embedding = self.embedding_service.embed_query(question)
        response = self.client.rpc(
            "match_documents",
            {
                "query_embedding": query_embedding,
                "match_video_id": video_id,
                "match_count": top_k,
            },
        ).execute()
        return [
            RetrievedChunk(
                content=str(row["content"]),
                metadata=dict(row.get("metadata") or {}),
                similarity=float(row["similarity"]),
            )
            for row in (response.data or [])
            if int((row.get("metadata") or {}).get("video_id", -1)) == video_id
        ]

    def touch_video(self, video_id: int) -> bool:
        response = self.client.rpc(
            "touch_my_video",
            {"target_video_id": video_id},
        ).execute()
        return bool(response.data)

    def list_history(
        self,
        video_id: int,
        *,
        limit: int | None = None,
    ) -> list[ChatMessageRecord]:
        query = (
            self.client.table("chat_messages")
            .select(CHAT_COLUMNS)
            .eq("video_id", video_id)
            .order("created_at", desc=True)
            .order("id", desc=True)
        )
        if limit is not None:
            query = query.limit(limit)
        response = query.execute()
        messages = [self._message_from_row(row) for row in (response.data or [])]
        messages.reverse()
        return messages

    def save_exchange(
        self,
        video_id: int,
        question: str,
        answer: str,
    ) -> list[ChatMessageRecord]:
        response = (
            self.client.table("chat_messages")
            .insert(
                [
                    {
                        "user_id": str(self.user_id),
                        "video_id": video_id,
                        "role": "user",
                        "content": question,
                    },
                    {
                        "user_id": str(self.user_id),
                        "video_id": video_id,
                        "role": "assistant",
                        "content": answer,
                    },
                ]
            )
            .execute()
        )
        return [
            self._message_from_row(row)
            for row in (response.data or [])
        ]

    @staticmethod
    def _message_from_row(row: dict[str, Any]) -> ChatMessageRecord:
        return ChatMessageRecord(
            id=int(row["id"]),
            video_id=int(row["video_id"]),
            role=str(row["role"]),
            content=str(row["content"]),
            created_at=datetime.fromisoformat(str(row["created_at"])),
        )
