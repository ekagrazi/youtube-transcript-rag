"""Request and response schemas for transcript-grounded chat."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)

    @field_validator("question")
    @classmethod
    def normalize_question(cls, value: str) -> str:
        question = value.strip()
        if not question:
            raise ValueError("question must not be blank")
        return question


class ChatSource(BaseModel):
    start_time: float = Field(ge=0)
    end_time: float | None = Field(default=None, ge=0)
    text: str
    similarity: float
    youtube_id: str
    youtube_url: str


class ChatResponse(BaseModel):
    answer: str
    sources: list[ChatSource]


class ChatMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    video_id: int
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime
