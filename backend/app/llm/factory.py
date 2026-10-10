"""Select the LLM provider from settings (``LLM_PROVIDER``)."""

from app.core.config import Settings
from app.llm.base import LLMProvider
from app.llm.mock import MockProvider
from app.llm.truth import TruthIndex


def build_provider(settings: Settings, truth: TruthIndex | None = None) -> LLMProvider:
    if settings.llm_provider == "anthropic":
        from app.llm.anthropic_provider import AnthropicProvider

        return AnthropicProvider(
            settings.anthropic_api_key, settings.anthropic_model, settings.llm_timeout_seconds
        )
    if settings.llm_provider == "openai":
        from app.llm.openai_provider import OpenAIProvider

        return OpenAIProvider(
            settings.openai_api_key, settings.openai_model, settings.llm_timeout_seconds
        )
    return MockProvider(truth or TruthIndex(settings.fixtures_dirs), seed=settings.mock_seed)
