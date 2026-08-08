"""Video ingestion API schemas."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


VideoStatus = Literal["pending", "ready", "failed"]


class VideoIngestRequest(BaseModel):
    youtube_url: str = Field(min_length=1, max_length=2048)


class VideoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    youtube_id: str
    title: str | None = None
    status: VideoStatus
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
    library_created_at: datetime | None = None
    library_last_interacted_at: datetime | None = None
