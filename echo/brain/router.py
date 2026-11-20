from typing import Optional
from echo.brain.mock_provider import MockProvider
from echo.brain.ollama_provider import OllamaProvider
from echo.brain.openai_provider import OpenAICompatibleProvider
from echo.brain.provider import ModelProvider, ProviderConfig
from echo.core.config import get_settings
from echo.core.database import get_database


class BrainRouter:
    """Manages active AI model provider and handles dynamic reconfiguration from database or environment."""

    def __init__(self):
        self._provider: Optional[ModelProvider] = None

    def get_provider(self) -> ModelProvider:
        # Load from DB settings if present, otherwise fallback to environment
        settings = get_settings()
        db = get_database()

        provider_name = settings.ai_provider
        model = settings.ai_model
        api_key = settings.ai_api_key
        api_base = settings.ai_api_base
        temperature = settings.ai_temperature

        with db.get_connection() as conn:
            cur = conn.execute("SELECT key, value FROM app_settings WHERE key LIKE 'ai_%';")
            rows = dict(cur.fetchall())
            if "ai_provider" in rows:
                provider_name = rows["ai_provider"]
            if "ai_model" in rows:
                model = rows["ai_model"]
            if "ai_api_key" in rows:
                api_key = rows["ai_api_key"]
            if "ai_api_base" in rows:
                api_base = rows["ai_api_base"]
            if "ai_temperature" in rows:
                try:
                    temperature = float(rows["ai_temperature"])
                except ValueError:
                    pass

        config = ProviderConfig(
            provider_name=provider_name,
            model=model,
            api_key=api_key,
            api_base=api_base,
            temperature=temperature,
            max_tokens=settings.ai_max_tokens,
        )

        if provider_name.lower() == "openai" or provider_name.lower() == "openrouter":
            return OpenAICompatibleProvider(config)
        elif provider_name.lower() == "ollama":
            return OllamaProvider(config)
        else:
            return MockProvider(config)


_brain_router: Optional[BrainRouter] = None


def get_brain_router() -> BrainRouter:
    global _brain_router
    if _brain_router is None:
        _brain_router = BrainRouter()
    return _brain_router

