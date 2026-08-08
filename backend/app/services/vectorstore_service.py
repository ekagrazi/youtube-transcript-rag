"""Supabase persistence operations for videos and transcript vectors."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from langchain_community.vectorstores import SupabaseVectorStore
from langchain_core.documents import Document
from supabase import Client

from app.services.embedding_service import EmbeddingService

VIDEO_COLUMNS = (
    "id,youtube_id,title,status,error_message,created_at,updated_at"
)


@dataclass(frozen=True, slots=True)
class VideoRecord:
    id: int
    youtube_id: str
    title: str | None
    status: str
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    library_created_at: datetime | None = None
    library_last_interacted_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class IngestionClaim:
    video: VideoRecord
    acquired: bool
    ingestion_token: UUID | None


class VectorStoreService:
    def __init__(
        self,
        client: Client,
        embedding_service: EmbeddingService,
        *,
        insert_batch_size: int = 100,
        lease_seconds: int = 900,
    ) -> None:
        self.client = client
        self.embedding_service = embedding_service
        self.lease_seconds = lease_seconds
        self.vector_store = SupabaseVectorStore(
            client=client,
            embedding=embedding_service,
            table_name="documents",
            query_name="match_documents",
            chunk_size=insert_batch_size,
        )

    def claim_ingestion(self, youtube_id: str) -> IngestionClaim:
        response = self.client.rpc(
            "claim_video_ingestion",
            {
                "requested_youtube_id": youtube_id,
                "stale_after_seconds": self.lease_seconds,
            },
        ).execute()
        if not response.data:
            raise RuntimeError("Supabase did not return an ingestion claim")

        row = response.data[0]
        token = row.get("ingestion_token")
        return IngestionClaim(
            video=self._video_from_row(row),
            acquired=bool(row["acquired"]),
            ingestion_token=UUID(token) if token else None,
        )

    def add_documents(
        self,
        documents: list[Document],
        vectors: list[list[float]],
    ) -> list[str]:
        if len(documents) != len(vectors):
            raise ValueError("Each document must have exactly one embedding")
        return self.vector_store.add_vectors(vectors, documents)

    def finalize_ingestion(self, video_id: int, token: UUID) -> bool:
        response = self.client.rpc(
            "finalize_video_ingestion",
            {
                "target_video_id": video_id,
                "target_ingestion_token": str(token),
            },
        ).execute()
        return bool(response.data)

    def fail_ingestion(
        self,
        video_id: int,
        token: UUID,
        safe_error_message: str,
    ) -> bool:
        response = self.client.rpc(
            "fail_video_ingestion",
            {
                "target_video_id": video_id,
                "target_ingestion_token": str(token),
                "safe_error_message": safe_error_message[:500],
            },
        ).execute()
        return bool(response.data)

    def get_video(self, video_id: int) -> VideoRecord | None:
        response = (
            self.client.table("videos")
            .select(VIDEO_COLUMNS)
            .eq("id", video_id)
            .maybe_single()
            .execute()
        )
        return self._video_from_row(response.data) if response.data else None

    def add_to_library(self, user_id: UUID, video_id: int) -> None:
        self.client.rpc(
            "add_user_video",
            {
                "target_user_id": str(user_id),
                "target_video_id": video_id,
            },
        ).execute()

    def list_videos(self, user_id: UUID) -> list[VideoRecord]:
        response = self.client.rpc(
            "list_user_videos",
            {"target_user_id": str(user_id)},
        ).execute()
        return [
            self._video_from_row(row)
            for row in (response.data or [])
        ]

    def remove_from_library(self, user_id: UUID, video_id: int) -> bool:
        response = self.client.rpc(
            "remove_user_video",
            {
                "target_user_id": str(user_id),
                "target_video_id": video_id,
            },
        ).execute()
        return bool(response.data)

    @staticmethod
    def _video_from_row(row: dict[str, object]) -> VideoRecord:
        return VideoRecord(
            id=int(row["id"]),
            youtube_id=str(row["youtube_id"]),
            title=str(row["title"]) if row.get("title") is not None else None,
            status=str(row["status"]),
            error_message=(
                str(row["error_message"])
                if row.get("error_message") is not None
                else None
            ),
            created_at=datetime.fromisoformat(str(row["created_at"])),
            updated_at=datetime.fromisoformat(str(row["updated_at"])),
            library_created_at=(
                datetime.fromisoformat(str(row["library_created_at"]))
                if row.get("library_created_at") is not None
                else None
            ),
            library_last_interacted_at=(
                datetime.fromisoformat(
                    str(row["library_last_interacted_at"])
                )
                if row.get("library_last_interacted_at") is not None
                else None
            ),
        )
