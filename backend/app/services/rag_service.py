"""Transcript-grounded retrieval-augmented chat orchestration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import urlencode

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from app.schemas.chat import ChatResponse, ChatSource
from app.services.chat_repository import (
    ChatMessageRecord,
    ChatRepository,
    RetrievedChunk,
)

logger = logging.getLogger(__name__)

NOT_FOUND_ANSWER = (
    "I couldn't find that information in this video's transcript."
)

SYSTEM_PROMPT = """You are a highly knowledgeable and helpful AI assistant. The user is asking questions about a YouTube video.
Below, in TRANSCRIPT CONTEXT, are relevant excerpts from the video's transcript. Use these excerpts as your primary context to understand the speaker's points.
However, you are encouraged to use your own broad knowledge to elaborate, explain concepts, provide examples, and give polished, comprehensive answers.
If the transcript doesn't explicitly answer the user's question, you may provide a helpful answer based on your general knowledge, but clearly distinguish between what the speaker said and your own additions.
If the user asks for the entire transcript, politely explain that you can only answer questions about the video.

TRANSCRIPT CONTEXT:
{context}
"""


class VideoNotFoundError(LookupError):
    """Raised when a requested video does not exist."""


class VideoNotReadyError(RuntimeError):
    """Raised when a requested video has not completed ingestion."""

    def __init__(self, status: str) -> None:
        self.video_status = status
        super().__init__(f"Video is not ready (status: {status})")


class ChatGenerationError(RuntimeError):
    """Safe error raised when the model or persistence step fails."""


@dataclass(frozen=True, slots=True)
class PreparedChat:
    video_id: int
    youtube_id: str
    chunks: list[RetrievedChunk]
    history: list[ChatMessageRecord]


class RagService:
    def __init__(
        self,
        repository: ChatRepository,
        chat_model: BaseChatModel,
        *,
        top_k: int = 4,
        history_messages: int = 6,
    ) -> None:
        self.repository = repository
        self.top_k = top_k
        self.history_messages = history_messages
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", SYSTEM_PROMPT),
                MessagesPlaceholder("history"),
                ("human", "{question}"),
            ]
        ).partial(not_found_answer=NOT_FOUND_ANSWER)
        self.chain = prompt | chat_model | StrOutputParser()

    def chat(self, video_id: int, question: str) -> ChatResponse:
        prepared = self._prepare(video_id, question)
        sources = self._sources(prepared.youtube_id, prepared.chunks)

        try:
            if prepared.chunks:
                answer = self.chain.invoke(
                    {
                        "question": question,
                        "context": self._format_context(prepared.chunks),
                        "history": self._langchain_history(prepared.history),
                    }
                ).strip()
                if not answer:
                    raise ValueError("LLM returned an empty answer")
            else:
                answer = NOT_FOUND_ANSWER

            self.repository.save_exchange(video_id, question, answer)
        except Exception as exc:
            logger.error(
                "Chat generation failed for video_id=%s error_type=%s",
                video_id,
                type(exc).__name__,
            )
            raise ChatGenerationError(
                "Unable to answer the question right now"
            ) from exc

        return ChatResponse(answer=answer, sources=sources)

    def history(self, video_id: int) -> list[ChatMessageRecord]:
        self._require_ready_video(video_id)
        if not self.repository.touch_video(video_id):
            raise VideoNotFoundError("Video not found")
        return self.repository.list_history(video_id)

    def _prepare(self, video_id: int, question: str) -> PreparedChat:
        video = self._require_ready_video(video_id)
        if not self.repository.touch_video(video_id):
            raise VideoNotFoundError("Video not found")
        chunks = self.repository.retrieve(
            question,
            video_id=video_id,
            top_k=self.top_k,
        )
        history = (
            self.repository.list_history(
                video_id,
                limit=self.history_messages,
            )
            if self.history_messages
            else []
        )
        return PreparedChat(
            video_id=video_id,
            youtube_id=video.youtube_id,
            chunks=chunks,
            history=history,
        )

    def _require_ready_video(self, video_id: int):
        video = self.repository.get_video(video_id)
        if video is None:
            raise VideoNotFoundError("Video not found")
        if video.status != "ready":
            raise VideoNotReadyError(video.status)
        return video

    @staticmethod
    def _format_context(chunks: list[RetrievedChunk]) -> str:
        return "\n\n".join(
            (
                "[Excerpt "
                f"{index}; start="
                f"{float(chunk.metadata.get('start', 0)):.1f}s]\n"
                f"{chunk.content}"
            )
            for index, chunk in enumerate(chunks, start=1)
        )

    @staticmethod
    def _langchain_history(
        messages: list[ChatMessageRecord],
    ) -> list[BaseMessage]:
        return [
            (
                HumanMessage(content=message.content)
                if message.role == "user"
                else AIMessage(content=message.content)
            )
            for message in messages
        ]

    @staticmethod
    def _sources(
        youtube_id: str,
        chunks: list[RetrievedChunk],
    ) -> list[ChatSource]:
        sources: list[ChatSource] = []
        for chunk in chunks:
            start = max(float(chunk.metadata.get("start", 0)), 0)
            raw_end = chunk.metadata.get("end")
            end = max(float(raw_end), 0) if raw_end is not None else None
            query = urlencode({"v": youtube_id, "t": f"{int(start)}s"})
            sources.append(
                ChatSource(
                    start_time=start,
                    end_time=end,
                    text=chunk.content,
                    similarity=chunk.similarity,
                    youtube_id=youtube_id,
                    youtube_url=f"https://www.youtube.com/watch?{query}",
                )
            )
        return sources
