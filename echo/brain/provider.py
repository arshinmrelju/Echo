from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    metadata: Optional[Dict[str, Any]] = None


class ChatChunk(BaseModel):
    content: str
    finish_reason: Optional[str] = None
    token_usage: Optional[int] = None
    error: Optional[str] = None


class ProviderConfig(BaseModel):
    provider_name: str
    model: str
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 2048


class ModelProvider(ABC):
    """Abstract base class for all AI Brain model providers."""

    def __init__(self, config: ProviderConfig):
        self.config = config

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if the provider service or endpoint is reachable."""
        pass

    @abstractmethod
    async def stream_chat(
        self,
        messages: List[ChatMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[ChatChunk]:
        """Stream chat completions chunk by chunk."""
        pass

    async def generate_chat(
        self,
        messages: List[ChatMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Non-streaming convenience helper aggregating stream chunks."""
        full_text = []
        async for chunk in self.stream_chat(messages, temperature, max_tokens):
            if chunk.content:
                full_text.append(chunk.content)
            if chunk.error:
                raise RuntimeError(chunk.error)
        return "".join(full_text)

