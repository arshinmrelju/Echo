import json
from typing import AsyncIterator, List, Optional
import httpx
from echo.brain.provider import ChatChunk, ChatMessage, ModelProvider, ProviderConfig


class OllamaProvider(ModelProvider):
    """Direct local Ollama HTTP API provider (/api/chat)."""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.api_base = (
            config.api_base.rstrip("/")
            if config.api_base
            else "http://127.0.0.1:11434"
        )

    async def is_available(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                res = await client.get(f"{self.api_base}/api/tags")
                return res.status_code == 200
        except Exception:
            return False

    async def stream_chat(
        self,
        messages: List[ChatMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[ChatChunk]:
        temp = temperature if temperature is not None else self.config.temperature

        payload = {
            "model": self.config.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "options": {
                "temperature": temp,
            },
            "stream": True,
        }

        url = f"{self.api_base}/api/chat"

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream("POST", url, json=payload) as response:
                    if response.status_code != 200:
                        error_body = await response.aread()
                        yield ChatChunk(
                            content="",
                            error=f"Ollama error ({response.status_code}): {error_body.decode('utf-8', errors='ignore')}",
                        )
                        return

                    async for line in response.aiter_lines():
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            parsed = json.loads(line)
                            msg = parsed.get("message", {})
                            content_piece = msg.get("content", "")
                            done = parsed.get("done", False)

                            if content_piece:
                                yield ChatChunk(content=content_piece)
                            if done:
                                yield ChatChunk(content="", finish_reason="stop")
                                break
                        except json.JSONDecodeError:
                            continue
        except httpx.ConnectError:
            yield ChatChunk(
                content="",
                error="Ollama service is unreachable at 127.0.0.1:11434. Please ensure Ollama is running.",
            )
        except httpx.TimeoutException:
            yield ChatChunk(content="", error="Ollama request timed out.")
        except Exception as ex:
            yield ChatChunk(content="", error=f"Ollama streaming exception: {str(ex)}")

