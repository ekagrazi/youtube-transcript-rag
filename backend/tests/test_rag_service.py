from datetime import UTC, datetime
from typing import Any

import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from app.services.chat_repository import ChatMessageRecord, RetrievedChunk
from app.services.rag_service import (
    NOT_FOUND_ANSWER,
    ChatGenerationError,
    RagService,
    VideoNotFoundError,
    VideoNotReadyError,
)
from app.services.vectorstore_service import VideoRecord


def video(*, video_id: int = 7, status: str = "ready") -> VideoRecord:
    now = datetime.now(UTC)
    return VideoRecord(
        id=video_id,
        youtube_id="dQw4w9WgXcQ",
        title="Test",
        status=status,
        error_message=None,
        created_at=now,
        updated_at=now,
    )


class FakeRepository:
    def __init__(
        self,
        *,
        current_video: VideoRecord | None = None,
        chunks: list[RetrievedChunk] | None = None,
    ) -> None:
        self.current_video = (
            current_video if current_video is not None else video()
        )
        self.chunks = chunks if chunks is not None else [
            RetrievedChunk(
                content="The launch happened on Tuesday.",
                metadata={
                    "video_id": 7,
                    "youtube_id": "dQw4w9WgXcQ",
                    "start": 42.8,
                    "end": 49.1,
                },
                similarity=0.91,
            )
        ]
        self.saved: list[tuple[int, str, str]] = []
        self.retrieval_calls: list[tuple[str, int, int]] = []
        self.history_limit: int | None = None
        self.touch_calls: list[int] = []

    def get_video(self, video_id: int) -> VideoRecord | None:
        return self.current_video

    def touch_video(self, video_id: int) -> bool:
        self.touch_calls.append(video_id)
        return True

    def retrieve(
        self,
        question: str,
        *,
        video_id: int,
        top_k: int,
    ) -> list[RetrievedChunk]:
        self.retrieval_calls.append((question, video_id, top_k))
        return self.chunks

    def list_history(
        self,
        video_id: int,
        *,
        limit: int | None = None,
    ) -> list[ChatMessageRecord]:
        self.history_limit = limit
        now = datetime.now(UTC)
        return [
            ChatMessageRecord(1, video_id, "user", "Earlier?", now),
            ChatMessageRecord(2, video_id, "assistant", "Earlier answer.", now),
        ]

    def save_exchange(
        self,
        video_id: int,
        question: str,
        answer: str,
    ) -> list[ChatMessageRecord]:
        self.saved.append((video_id, question, answer))
        return []


def test_grounded_answer_uses_context_history_and_timestamped_source() -> None:
    repository = FakeRepository()
    seen_messages: list[Any] = []

    def answer(prompt: Any) -> AIMessage:
        seen_messages.extend(prompt.messages)
        return AIMessage(content="It happened on Tuesday.")

    service = RagService(
        repository,
        RunnableLambda(answer),  # type: ignore[arg-type]
        top_k=3,
        history_messages=2,
    )

    response = service.chat(7, "When was the launch?")

    assert repository.retrieval_calls == [
        ("When was the launch?", 7, 3)
    ]
    assert repository.touch_calls == [7]
    assert repository.history_limit == 2
    assert repository.saved == [
        (7, "When was the launch?", "It happened on Tuesday.")
    ]
    assert "The launch happened on Tuesday." in seen_messages[0].content
    assert [message.content for message in seen_messages[1:3]] == [
        "Earlier?",
        "Earlier answer.",
    ]
    assert response.sources[0].start_time == 42.8
    assert response.sources[0].youtube_url.endswith(
        "v=dQw4w9WgXcQ&t=42s"
    )


def test_out_of_context_model_response_is_persisted_consistently() -> None:
    repository = FakeRepository()
    service = RagService(
        repository,
        RunnableLambda(
            lambda _: AIMessage(content=NOT_FOUND_ANSWER)
        ),  # type: ignore[arg-type]
    )

    response = service.chat(7, "Who won the World Cup?")

    assert response.answer == NOT_FOUND_ANSWER
    assert repository.saved[0][2] == NOT_FOUND_ANSWER


def test_no_retrieved_context_skips_model_and_returns_not_found() -> None:
    repository = FakeRepository(chunks=[])

    def unexpected(_: Any) -> AIMessage:
        raise AssertionError("The LLM must not run without transcript context")

    service = RagService(
        repository,
        RunnableLambda(unexpected),  # type: ignore[arg-type]
    )

    response = service.chat(7, "Unrelated question")

    assert response.answer == NOT_FOUND_ANSWER
    assert response.sources == []
    assert len(repository.saved) == 1


def test_generation_failure_does_not_leave_a_user_message() -> None:
    repository = FakeRepository()

    def fail(_: Any) -> AIMessage:
        raise RuntimeError("provider unavailable")

    service = RagService(
        repository,
        RunnableLambda(fail),  # type: ignore[arg-type]
    )

    with pytest.raises(ChatGenerationError):
        service.chat(7, "When?")

    assert repository.saved == []


@pytest.mark.parametrize("status", ["pending", "failed"])
def test_non_ready_video_is_rejected_before_retrieval(status: str) -> None:
    repository = FakeRepository(current_video=video(status=status))
    service = RagService(
        repository,
        RunnableLambda(lambda _: AIMessage(content="unused")),  # type: ignore[arg-type]
    )

    with pytest.raises(VideoNotReadyError) as exc_info:
        service.chat(7, "Question")

    assert exc_info.value.video_status == status
    assert repository.retrieval_calls == []


def test_unknown_video_is_rejected() -> None:
    repository = FakeRepository()
    repository.current_video = None
    service = RagService(
        repository,
        RunnableLambda(lambda _: AIMessage(content="unused")),  # type: ignore[arg-type]
    )

    with pytest.raises(VideoNotFoundError):
        service.chat(99, "Question")
