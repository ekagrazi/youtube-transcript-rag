"""Authenticated, video-scoped transcript chat routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from starlette.concurrency import run_in_threadpool

from app.auth.dependencies import get_access_token, get_current_user
from app.config import Settings, get_settings
from app.dependencies import get_embedding_service
from app.schemas.chat import (
    ChatMessageResponse,
    ChatRequest,
    ChatResponse,
)
from app.services.chat_repository import ChatRepository
from app.services.llm_provider import LLMConfigurationError, get_chat_model
from app.services.rag_service import (
    ChatGenerationError,
    RagService,
    VideoNotFoundError,
    VideoNotReadyError,
)
from app.supabase_client import get_user_client

router = APIRouter(prefix="/chat", tags=["chat"])


def get_rag_service(
    user_id: UUID = Depends(get_current_user),
    access_token: str = Depends(get_access_token),
    settings: Settings = Depends(get_settings),
) -> RagService:
    try:
        client = get_user_client(access_token, settings)
        chat_model = get_chat_model(settings)
    except (RuntimeError, LLMConfigurationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Chat service is not configured",
        ) from exc

    return RagService(
        ChatRepository(client, user_id, get_embedding_service()),
        chat_model,
        top_k=settings.rag_top_k,
        history_messages=settings.chat_history_messages,
    )


@router.post("/{video_id}", response_model=ChatResponse)
async def chat(
    video_id: int,
    request: ChatRequest,
    service: RagService = Depends(get_rag_service),
) -> ChatResponse:
    try:
        return await run_in_threadpool(
            service.chat,
            video_id,
            request.question,
        )
    except VideoNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video not found",
        ) from exc
    except VideoNotReadyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Video is not ready (status: {exc.video_status})",
        ) from exc
    except ChatGenerationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc


@router.get(
    "/{video_id}/history",
    response_model=list[ChatMessageResponse],
)
async def history(
    video_id: int,
    service: RagService = Depends(get_rag_service),
) -> list[ChatMessageResponse]:
    try:
        messages = await run_in_threadpool(service.history, video_id)
    except VideoNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video not found",
        ) from exc
    except VideoNotReadyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Video is not ready (status: {exc.video_status})",
        ) from exc
    return [
        ChatMessageResponse.model_validate(message)
        for message in messages
    ]
