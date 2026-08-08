"""Configurable LangChain chat-model providers."""

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

from app.config import Settings


class LLMConfigurationError(RuntimeError):
    """Raised when the selected LLM provider is not fully configured."""


def get_chat_model(settings: Settings) -> BaseChatModel:
    """Build the selected non-streaming chat model from environment settings."""

    if settings.llm_provider == "ollama":
        return ChatOllama(
            model=settings.ollama_model,
            base_url=str(settings.ollama_base_url).rstrip("/"),
            temperature=settings.llm_temperature,
            client_kwargs={"timeout": settings.llm_request_timeout_seconds},
        )

    if settings.hosted_api_key is None or not settings.hosted_model_name:
        raise LLMConfigurationError(
            "HOSTED_API_KEY and HOSTED_MODEL_NAME are required for hosted LLMs"
        )

    return ChatOpenAI(
        model=settings.hosted_model_name,
        base_url=str(settings.hosted_api_base_url).rstrip("/"),
        api_key=settings.hosted_api_key.get_secret_value(),
        temperature=settings.llm_temperature,
        timeout=settings.llm_request_timeout_seconds,
        max_retries=2,
    )
