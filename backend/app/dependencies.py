"""Shared process-level application dependencies."""

from functools import lru_cache

from app.config import get_settings
from app.services.embedding_service import EmbeddingService


@lru_cache
def get_embedding_service() -> EmbeddingService:
    """Reuse the lazily loaded embedding model across ingestion and chat."""

    return EmbeddingService(get_settings())
