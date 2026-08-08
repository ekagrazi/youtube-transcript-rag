"""Authenticated per-user video library and ingestion routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from starlette.concurrency import run_in_threadpool

from app.auth.dependencies import get_current_user
from app.config import Settings, get_settings
from app.dependencies import get_embedding_service
from app.schemas.video import VideoIngestRequest, VideoResponse
from app.services.ingestion_service import IngestionService
from app.services.transcript_service import InvalidYouTubeURL, TranscriptService
from app.services.vectorstore_service import VectorStoreService
from app.supabase_client import get_service_client

router = APIRouter(
    prefix="/videos",
    tags=["videos"],
)


def get_ingestion_service(
    settings: Settings = Depends(get_settings),
) -> IngestionService:
    try:
        client = get_service_client(settings)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Video ingestion is not configured",
        ) from exc

    embedding_service = get_embedding_service()
    return IngestionService(
        transcript_service=TranscriptService(settings),
        embedding_service=embedding_service,
        vectorstore_service=VectorStoreService(
            client,
            embedding_service,
            insert_batch_size=settings.vector_insert_batch_size,
            lease_seconds=settings.ingestion_lease_seconds,
        ),
    )


@router.post("/ingest", response_model=VideoResponse)
async def ingest_video(
    request: VideoIngestRequest,
    user_id: UUID = Depends(get_current_user),
    service: IngestionService = Depends(get_ingestion_service),
) -> VideoResponse:
    try:
        video = await run_in_threadpool(
            service.ingest,
            request.youtube_url,
            user_id,
        )
    except InvalidYouTubeURL as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    return VideoResponse.model_validate(video)


@router.get("", response_model=list[VideoResponse])
async def list_videos(
    user_id: UUID = Depends(get_current_user),
    service: IngestionService = Depends(get_ingestion_service),
) -> list[VideoResponse]:
    videos = await run_in_threadpool(service.list_videos, user_id)
    return [VideoResponse.model_validate(video) for video in videos]


@router.delete("/{video_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_video(
    video_id: int,
    user_id: UUID = Depends(get_current_user),
    service: IngestionService = Depends(get_ingestion_service),
) -> Response:
    removed = await run_in_threadpool(
        service.delete_video,
        user_id,
        video_id,
    )
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video not found in your library",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
