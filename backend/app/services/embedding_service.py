"""Lazy Hugging Face embedding service."""

from __future__ import annotations

from threading import Lock

from langchain_core.embeddings import Embeddings
from langchain_huggingface import HuggingFaceEmbeddings

from app.config import Settings


class EmbeddingDimensionError(RuntimeError):
    """Raised if a configured model does not match the database vector size."""


class EmbeddingService(Embeddings):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._backend: HuggingFaceEmbeddings | None = None
        self._load_lock = Lock()

    @property
    def backend(self) -> HuggingFaceEmbeddings:
        if self._backend is None:
            with self._load_lock:
                if self._backend is None:
                    self._backend = HuggingFaceEmbeddings(
                        model_name=self.settings.embedding_model,
                        encode_kwargs={
                            "batch_size": self.settings.embedding_batch_size,
                            "normalize_embeddings": True,
                        },
                    )
        return self._backend

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors = self.backend.embed_documents(texts)
        self._validate_dimensions(vectors)
        return vectors

    def embed_query(self, text: str) -> list[float]:
        vector = self.backend.embed_query(text)
        self._validate_dimensions([vector])
        return vector

    def _validate_dimensions(self, vectors: list[list[float]]) -> None:
        expected = self.settings.embedding_dimension
        if any(len(vector) != expected for vector in vectors):
            raise EmbeddingDimensionError(
                f"Embedding model must return {expected}-dimensional vectors"
            )
