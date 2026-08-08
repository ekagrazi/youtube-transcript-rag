from datetime import UTC, datetime
from uuid import UUID

from langchain_core.documents import Document

from app.services.ingestion_service import IngestionService
from app.services.transcript_service import (
    TranscriptResult,
    TranscriptSegment,
    TranscriptServiceError,
)
from app.services.vectorstore_service import IngestionClaim, VideoRecord

VIDEO_ID = "dQw4w9WgXcQ"
TOKEN = UUID("8d369998-b4a8-4a52-bc33-a69c18e62aac")
USER_ID = UUID("f442dfa1-ccac-4409-9b93-947e3bb39630")


def video(status: str, error_message: str | None = None) -> VideoRecord:
    now = datetime.now(UTC)
    return VideoRecord(
        id=12,
        youtube_id=VIDEO_ID,
        title=None,
        status=status,
        error_message=error_message,
        created_at=now,
        updated_at=now,
    )


class FakeTranscriptService:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.fetch_calls = 0

    def fetch(self, youtube_id: str) -> TranscriptResult:
        self.fetch_calls += 1
        if self.fail:
            raise TranscriptServiceError("A transcript is not available for this video.")
        return TranscriptResult(
            segments=(TranscriptSegment("Transcript text", 0.0, 2.0),),
            language_code="en",
            is_generated=False,
        )

    def chunk(self, transcript: TranscriptResult) -> list[Document]:
        return [
            Document(
                page_content="Transcript text",
                metadata={
                    "start": 0.0,
                    "end": 2.0,
                    "language_code": "en",
                    "is_generated": False,
                },
            )
        ]


class FakeEmbeddingService:
    def __init__(self) -> None:
        self.calls = 0

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        return [[0.0] * 384 for _ in texts]


class FakeVectorStoreService:
    def __init__(self, claim: IngestionClaim) -> None:
        self.claim = claim
        self.current = claim.video
        self.add_calls = 0
        self.fail_calls = 0
        self.finalize_calls = 0
        self.library_users: list[UUID] = []
        self.documents: list[Document] = []

    def claim_ingestion(self, youtube_id: str) -> IngestionClaim:
        if self.current.status == "ready":
            return IngestionClaim(self.current, False, None)
        return self.claim

    def add_documents(
        self,
        documents: list[Document],
        vectors: list[list[float]],
    ) -> list[str]:
        self.add_calls += 1
        self.documents = documents
        return ["1"]

    def add_to_library(self, user_id: UUID, video_id: int) -> None:
        assert video_id == 12
        self.library_users.append(user_id)

    def finalize_ingestion(self, video_id: int, token: UUID) -> bool:
        self.finalize_calls += 1
        self.current = video("ready")
        return True

    def fail_ingestion(
        self,
        video_id: int,
        token: UUID,
        safe_error_message: str,
    ) -> bool:
        self.fail_calls += 1
        self.current = video("failed", safe_error_message)
        return True

    def get_video(self, video_id: int) -> VideoRecord:
        return self.current

    def list_videos(self, user_id: UUID) -> list[VideoRecord]:
        return [self.current]

    def remove_from_library(self, user_id: UUID, video_id: int) -> bool:
        return True


def build_service(
    *,
    acquired: bool = True,
    transcript_failure: bool = False,
) -> tuple[
    IngestionService,
    FakeTranscriptService,
    FakeEmbeddingService,
    FakeVectorStoreService,
]:
    transcript = FakeTranscriptService(fail=transcript_failure)
    embeddings = FakeEmbeddingService()
    store = FakeVectorStoreService(
        IngestionClaim(
            video=video("pending"),
            acquired=acquired,
            ingestion_token=TOKEN if acquired else None,
        )
    )
    service = IngestionService(
        transcript_service=transcript,  # type: ignore[arg-type]
        embedding_service=embeddings,  # type: ignore[arg-type]
        vectorstore_service=store,  # type: ignore[arg-type]
    )
    return service, transcript, embeddings, store


def test_ingestion_is_idempotent_after_video_is_ready() -> None:
    service, transcript, embeddings, store = build_service()

    first = service.ingest(f"https://youtu.be/{VIDEO_ID}", USER_ID)
    second = service.ingest(f"https://youtu.be/{VIDEO_ID}", USER_ID)

    assert first.status == "ready"
    assert second.status == "ready"
    assert transcript.fetch_calls == 1
    assert embeddings.calls == 1
    assert store.add_calls == 1
    assert store.finalize_calls == 1
    assert store.library_users == [USER_ID, USER_ID]
    assert store.documents[0].metadata["video_id"] == 12
    assert store.documents[0].metadata["youtube_id"] == VIDEO_ID
    assert store.documents[0].metadata["ingestion_token"] == str(TOKEN)
    assert store.documents[0].metadata["chunk_index"] == 0


def test_active_concurrent_ingestion_does_no_duplicate_work() -> None:
    service, transcript, embeddings, store = build_service(acquired=False)

    result = service.ingest(
        f"https://youtube.com/watch?v={VIDEO_ID}",
        USER_ID,
    )

    assert result.status == "pending"
    assert transcript.fetch_calls == 0
    assert embeddings.calls == 0
    assert store.add_calls == 0


def test_transcript_failure_is_persisted_with_safe_message() -> None:
    service, transcript, embeddings, store = build_service(
        transcript_failure=True
    )

    result = service.ingest(
        f"https://youtube.com/watch?v={VIDEO_ID}",
        USER_ID,
    )

    assert result.status == "failed"
    assert result.error_message == "A transcript is not available for this video."
    assert store.fail_calls == 1
    assert store.add_calls == 0
    assert embeddings.calls == 0
