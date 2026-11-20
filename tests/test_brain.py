import pytest
from echo.brain.mock_provider import MockProvider
from echo.brain.prompts import build_system_prompt
from echo.brain.provider import ChatMessage, ProviderConfig
from echo.brain.router import BrainRouter


@pytest.mark.asyncio
async def test_mock_provider_streaming():
    provider = MockProvider()
    assert await provider.is_available() is True

    messages = [ChatMessage(role="user", content="Hello Echo")]
    chunks = []
    async for chunk in provider.stream_chat(messages):
        if chunk.content:
            chunks.append(chunk.content)

    full_response = "".join(chunks)
    assert "ECHO" in full_response
    assert len(full_response) > 10


def test_build_system_prompt_with_memory():
    prompt = build_system_prompt(memory_context="• [FACT] Name: Alex")
    assert "ECHO" in prompt
    assert "Alex" in prompt

