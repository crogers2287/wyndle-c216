import httpx
import pytest

from wyndle.providers.openai import (
    OpenAICompatibleLanguageProvider,
    OpenAICompatibleVisionProvider,
)
from wyndle.vision.routing import is_visual_question


@pytest.mark.asyncio
async def test_language_provider() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        return httpx.Response(200, json={"choices": [{"message": {"content": " Seven. "}}]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleLanguageProvider(
        base_url="http://local/v1", model="m", client=client
    )
    assert await provider.complete("say seven") == "Seven."
    await client.aclose()


@pytest.mark.asyncio
async def test_vision_provider_embeds_frame() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        body = __import__("json").loads(request.content)
        url = body["messages"][0]["content"][1]["image_url"]["url"]
        assert url.startswith("data:image/jpeg;base64,")
        return httpx.Response(200, json={"choices": [{"message": {"content": "red tool"}}]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleVisionProvider(base_url="http://local/v1", model="v", client=client)
    assert await provider.answer_visual_question("what?", b"jpeg") == "red tool"
    await client.aclose()


def test_visual_classifier() -> None:
    assert is_visual_question("What am I holding?")
    assert is_visual_question("What color is this?")
    assert not is_visual_question("I see what you mean")
    assert not is_visual_question("Say camera speaker online")


@pytest.mark.asyncio
async def test_language_provider_adds_voice_prompt_and_token_cap() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        body = __import__("json").loads(request.content)
        assert body["max_tokens"] == 40
        assert body["messages"][0] == {"role": "system", "content": "Be brief."}
        return httpx.Response(200, json={"choices": [{"message": {"content": "Brief."}}]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleLanguageProvider(
        base_url="http://local/v1",
        model="m",
        client=client,
        max_tokens=40,
        system_prompt="Be brief.",
    )
    assert await provider.complete("test") == "Brief."
    await client.aclose()
