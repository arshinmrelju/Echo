import asyncio
from typing import AsyncIterator, List, Optional
from echo.brain.provider import ChatChunk, ChatMessage, ModelProvider, ProviderConfig


class MockProvider(ModelProvider):
    """Deterministic, offline mock provider for tests and fallback when no external API key is set."""

    def __init__(self, config: Optional[ProviderConfig] = None):
        if config is None:
            config = ProviderConfig(
                provider_name="mock",
                model="echo-mock-v1",
                temperature=0.7,
                max_tokens=1024,
            )
        super().__init__(config)

    async def is_available(self) -> bool:
        return True

    async def stream_chat(
        self,
        messages: List[ChatMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[ChatChunk]:
        last_user_message = ""
        for m in reversed(messages):
            if m.role == "user":
                last_user_message = m.content
                break

        # Generate a friendly, calm, intelligent ECHO response
        query = last_user_message.strip().lower()
        if not query or query in ["hi", "hello", "hey", "who are you"]:
            response_text = (
                "Hello. I am **ECHO**, your personal AI assistant. "
                "I am running locally on your workstation, ready to help you manage tasks, "
                "remember important context, and operate your system within authorized boundaries. "
                "How may I assist you today?"
            )
        elif "help" in query:
            response_text = (
                "I can assist you with:\n\n"
                "- **Conversational reasoning** and problem solving\n"
                "- **Remembering facts & preferences** across sessions in persistent memory\n"
                "- **Organizing tasks** and tracking execution progress\n"
                "- **System monitoring** and status inspection\n\n"
                "You can configure an external AI provider (such as OpenAI, Anthropic, or local Ollama) in **Settings**, "
                "or interact with me directly in offline mode."
            )
        elif "status" in query:
            response_text = (
                "System status is **Optimal**:\n\n"
                "- Core Daemon: `Connected` (WAL SQLite)\n"
                "- Active Model: `" + self.config.model + "` (Provider: `" + self.config.provider_name + "`)\n"
                "- Memory Engine: `Ready`\n"
                "- Permissions: `Strict`"
            )
        else:
            response_text = (
                f"I received your request: *\"{last_user_message}\"*\n\n"
                f"As ECHO, I have analyzed this and stored relevant context. "
                f"When connected to a cloud or local neural model (like Ollama, Claude, or GPT-4), "
                f"I will generate in-depth reasoning and plan tool executions. "
                f"Is there a specific task or memory entry you would like me to record?"
            )

        # Stream words with slight delay to simulate realistic streaming
        words = response_text.split(" ")
        for i, word in enumerate(words):
            yield ChatChunk(content=(word + " " if i < len(words) - 1 else word))
            await asyncio.sleep(0.02)

        yield ChatChunk(content="", finish_reason="stop", token_usage=len(words))

