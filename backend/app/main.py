"""FastAPI application entry point."""

from uuid import UUID

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth.dependencies import get_current_user
from app.config import get_settings
from app.routers.chat_router import router as chat_router
from app.routers.ingest_router import router as ingest_router

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    debug=settings.app_debug,
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(ingest_router)
app.include_router(chat_router)


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    """Return a cheap, non-mutating liveness response."""

    return {"status": "ok"}


@app.get("/auth/me", tags=["auth"])
async def auth_me(user_id: UUID = Depends(get_current_user)) -> dict[str, str]:
    """Return the ID from a verified Supabase session."""

    return {"user_id": str(user_id)}
