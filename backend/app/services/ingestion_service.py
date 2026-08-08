"""Synchronous orchestration for idempotent video ingestion."""

from __future__ import annotations

import logging
from dataclasses import replace
from uuid import UUID

from langchain_core.documents import Document

from app.services.embedding_service import EmbeddingService
from app.services.transcript_service import (
    InvalidYouTubeURL,
    TranscriptService,
    TranscriptServiceError,
    extract_video_id,
)
from app.services.vectorstore_service import VideoRecord, VectorStoreService

logger = logging.getLogger(__name__)


class IngestionService:
    def __init__(
        self,
        transcript_service: TranscriptService,
        embedding_service: EmbeddingService,
        vectorstore_service: VectorStoreService,
    ) -> None:
        self.transcript_service = transcript_service
        self.embedding_service = embedding_service
        self.vectorstore_service = vectorstore_service

    def ingest(self, youtube_url: str, user_id: UUID) -> VideoRecord:
        youtube_id = extract_video_id(youtube_url)
        claim = self.vectorstore_service.claim_ingestion(youtube_id)
        self.vectorstore_service.add_to_library(user_id, claim.video.id)
        if not claim.acquired:
            return claim.video
        if claim.ingestion_token is None:
            raise RuntimeError("Claimed ingestion did not include an attempt token")

        token = claim.ingestion_token
        try:
            transcript = self.transcript_service.fetch(youtube_id)
            chunks = self.transcript_service.chunk(transcript)
            documents = self._tag_documents(
                chunks,
                video_id=claim.video.id,
                youtube_id=youtube_id,
                ingestion_token=str(token),
            )
            vectors = self.embedding_service.embed_documents(
                [document.page_content for document in documents]
            )
            self.vectorstore_service.add_documents(documents, vectors)
            finalized = self.vectorstore_service.finalize_ingestion(
                claim.video.id,
                token,
            )
            if not finalized:
                current = self.vectorstore_service.get_video(claim.video.id)
                return current or claim.video
        except InvalidYouTubeURL:
            raise
        except TranscriptServiceError as exc:
            return self._record_failure(claim.video, token, str(exc))
        except Exception as exc:
            logger.error(
                "Video ingestion failed for youtube_id=%s error_type=%s",
                youtube_id,
                type(exc).__name__,
            )
            return self._record_failure(
                claim.video,
                token,
                "Video ingestion failed. Please retry.",
            )

        current = self.vectorstore_service.get_video(claim.video.id)
        if current is None:
            raise RuntimeError("Finalized video could not be reloaded")
        return current

    def list_videos(self, user_id: UUID) -> list[VideoRecord]:
        return self.vectorstore_service.list_videos(user_id)

    def delete_video(self, user_id: UUID, video_id: int) -> bool:
        return self.vectorstore_service.remove_from_library(user_id, video_id)

    def _record_failure(
        self,
        video: VideoRecord,
        token: UUID,
        safe_message: str,
    ) -> VideoRecord:
        self.vectorstore_service.fail_ingestion(
            video.id,
            token,
            safe_message,
        )
        current = self.vectorstore_service.get_video(video.id)
        return current or replace(
            video,
            status="failed",
            error_message=safe_message,
        )

    @staticmethod
    def _tag_documents(
        chunks: list[Document],
        *,
        video_id: int,
        youtube_id: str,
        ingestion_token: str,
    ) -> list[Document]:
        return [
            Document(
                page_content=chunk.page_content,
                metadata={
                    **chunk.metadata,
                    "video_id": video_id,
                    "youtube_id": youtube_id,
                    "ingestion_token": ingestion_token,
                    "chunk_index": index,
                },
            )
            for index, chunk in enumerate(chunks)
        ]
