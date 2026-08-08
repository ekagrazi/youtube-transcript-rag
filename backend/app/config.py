"""Application configuration loaded from environment variables."""

from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, HttpUrl, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings.

    Supabase values are optional at import time so the public health endpoint can run
    in build and container checks. Supabase-dependent code validates the required
    values before making a request.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    app_name: str = "YouTube Transcript RAG API"
    app_env: Literal["development", "test", "production"] = "development"
    app_debug: bool = False
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    auth_request_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    ingestion_lease_seconds: int = Field(default=900, ge=60, le=3600)

    supabase_url: HttpUrl | None = None
    supabase_publishable_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "SUPABASE_PUBLISHABLE_KEY",
            "SUPABASE_ANON_KEY",
        ),
    )
    supabase_secret_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "SUPABASE_SECRET_KEY",
            "SUPABASE_SERVICE_ROLE_KEY",
        ),
    )

    llm_provider: Literal["ollama", "hosted"] = "ollama"
    ollama_base_url: HttpUrl = HttpUrl("http://localhost:11434")
    ollama_model: str = "llama3.2:3b"
    hosted_api_base_url: HttpUrl = HttpUrl("https://api.groq.com/openai/v1")
    hosted_api_key: SecretStr | None = None
    hosted_model_name: str | None = None
    llm_temperature: float = Field(default=0.1, ge=0, le=2)
    llm_request_timeout_seconds: float = Field(default=120.0, gt=0, le=600)
    rag_top_k: int = Field(default=4, ge=1, le=20)
    chat_history_messages: int = Field(default=6, ge=0, le=20)
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dimension: int = Field(default=384, ge=1)
    embedding_batch_size: int = Field(default=32, ge=1, le=512)
    vector_insert_batch_size: int = Field(default=100, ge=1, le=500)
    transcript_languages: str = "en"
    transcript_chunk_size: int = Field(default=1000, ge=100, le=10000)
    transcript_chunk_overlap: int = Field(default=200, ge=0, le=5000)
    transcript_proxy_username: str | None = None
    transcript_proxy_password: SecretStr | None = None

    @model_validator(mode="after")
    def validate_ingestion_settings(self) -> "Settings":
        if self.transcript_chunk_overlap >= self.transcript_chunk_size:
            raise ValueError(
                "TRANSCRIPT_CHUNK_OVERLAP must be smaller than "
                "TRANSCRIPT_CHUNK_SIZE"
            )
        if bool(self.transcript_proxy_username) != bool(
            self.transcript_proxy_password
        ):
            raise ValueError(
                "TRANSCRIPT_PROXY_USERNAME and TRANSCRIPT_PROXY_PASSWORD "
                "must be configured together"
            )
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        """Return normalized configured CORS origins."""

        return [
            origin.strip().rstrip("/")
            for origin in self.cors_origins.split(",")
            if origin.strip()
        ]

    @property
    def transcript_language_list(self) -> list[str]:
        languages = [
            language.strip()
            for language in self.transcript_languages.split(",")
            if language.strip()
        ]
        return languages or ["en"]

    def require_supabase_url(self) -> str:
        if self.supabase_url is None:
            raise RuntimeError("SUPABASE_URL is not configured")
        return str(self.supabase_url).rstrip("/")

    def require_supabase_publishable_key(self) -> str:
        if self.supabase_publishable_key is None:
            raise RuntimeError("SUPABASE_PUBLISHABLE_KEY is not configured")
        return self.supabase_publishable_key.get_secret_value()

    def require_supabase_secret_key(self) -> str:
        if self.supabase_secret_key is None:
            raise RuntimeError("SUPABASE_SECRET_KEY is not configured")
        return self.supabase_secret_key.get_secret_value()


@lru_cache
def get_settings() -> Settings:
    """Return one immutable-by-convention settings instance per process."""

    return Settings()
