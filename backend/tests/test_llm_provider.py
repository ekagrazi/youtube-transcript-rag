import pytest

from app.config import Settings
from app.services.llm_provider import (
    LLMConfigurationError,
    get_chat_model,
)


def test_ollama_is_the_default_provider() -> None:
    model = get_chat_model(Settings(_env_file=None))

    assert type(model).__name__ == "ChatOllama"
    assert model.model == "llama3.2:3b"
    assert model.base_url == "http://localhost:11434"


def test_hosted_provider_requires_key_and_model() -> None:
    settings = Settings(_env_file=None, llm_provider="hosted")

    with pytest.raises(LLMConfigurationError):
        get_chat_model(settings)


def test_hosted_provider_uses_environment_configuration() -> None:
    settings = Settings(
        _env_file=None,
        llm_provider="hosted",
        hosted_api_base_url="https://api.together.xyz/v1",
        hosted_api_key="test-secret",
        hosted_model_name="provider/model-name",
    )

    model = get_chat_model(settings)

    assert type(model).__name__ == "ChatOpenAI"
    assert model.model_name == "provider/model-name"
    assert model.openai_api_base == "https://api.together.xyz/v1"
