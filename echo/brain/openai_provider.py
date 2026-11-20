import json
from typing import AsyncIterator, List, Optional
import httpx
from echo.brain.provider import ChatChunk, ChatMessage, ModelProvider, ProviderConfig


class OpenAICompatibleProvider(ModelProvider):
    """Provider for OpenAI-compatible endpoints (OpenAI, OpenRouter, LM Studio, vLLM, DeepSeek)."""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.api_base = (
            config.api_base.rstrip("/")
            if config.api_base
            else "https://api.openai.com/v1"
        )

    async def is_available(self) -> bool:
        if not self.config.api_key and "localhost" not in self.api_base and "127.0.0.1" not in self.api_base:
            return False
        try:
            headers = {}
            if self.config.api_key:
                headers["Authorization"] = f"Bearer {self.config.api_key}"
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(f"{self.api_base}/models", headers=headers)
                return res.status_code in [200, 401, 403]  # 401/403 means host is up
        except Exception:
            return False

    async def stream_chat(
        self,
        messages: List[ChatMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[ChatChunk]:
        temp = temperature if temperature is not None else self.config.temperature
        tokens = max_tokens if max_tokens is not None else self.config.max_tokens

        headers = {
            "Content-Type": "application/json",
        }
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        payload = {
            "model": self.config.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temp,
            "max_tokens": tokens,
            "stream": True,
        }

        url = f"{self.api_base}/chat/completions"

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream("POST", url, headers=headers, json=payload) as response:
                    if response.status_code != 200:
                        error_bytes = await response.aread()
                        error_msg = f"Provider HTTP {response.status_code}: {error_bytes.decode('utf-8', errors='ignore')}"
                        yield ChatChunk(content="", error=error_msg)
                        return

                    async for line in response.aiter_lines():
                        line = line.strip()
                        if not line or not line.startswith("data:"):
                            continue
                        data_str = line[5:].strip()
                        if data_str == "[DONE]":
                            yield ChatChunk(content="", finish_reason="stop")
                            break
                        try:
                            parsed = json.loads(data_str)
                            choices = parsed.get("choices", [])
                            if choices:
                                delta = choices[0].get("delta", {})
                                content_piece = delta.get("content", "")
                                finish = choices[0].get("finish_reason")
                                if content_piece:
                                    yield ChatChunk(content=content_piece)
                                if finish:
                                    yield ChatChunk(content="", finish_reason=finish)
                        except json.JSONDecodeError:
                            continue
        except httpx.TimeoutException:
            yield ChatChunk(content="", error="AI request timed out. Please check your network or provider endpoint.")
        except httpx.ConnectError:
            yield ChatChunk(content="", error=f"Could not connect to AI provider endpoint at {self.api_base}.")
        except Exception as ex:
            yield ChatChunk(content="", error=f"AI streaming error: {str(ex)}")

