"""OpenAI-compatible language and vision providers."""

from __future__ import annotations

import base64
from collections.abc import Mapping, Sequence
from typing import Any

import httpx

from wyndle.providers.base import ChatMessage


class ProviderError(RuntimeError):
    """An inference endpoint returned an unusable response."""


def _chat_completions_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


def _image_data_url(image: bytes, media_type: str) -> str:
    encoded = base64.b64encode(image).decode("ascii")
    return f"data:{media_type};base64,{encoded}"


def _response_text(payload: Mapping[str, Any]) -> str:
    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderError("response did not contain choices[0].message.content") from exc

    if isinstance(content, str):
        text = content.strip()
    elif isinstance(content, list):
        # Some compatible servers return the Responses-style content parts.
        text = "".join(
            str(part.get("text", ""))
            for part in content
            if isinstance(part, Mapping) and part.get("type") in {"text", "output_text"}
        ).strip()
    else:
        text = ""
    if not text:
        raise ProviderError("response contained no text")
    return text


class _OpenAICompatibleClient:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout: float = 30.0,
        client: httpx.AsyncClient | None = None,
        max_tokens: int | None = None,
        system_prompt: str | None = None,
    ) -> None:
        if not base_url:
            raise ValueError("base_url must not be empty")
        if not model:
            raise ValueError("model must not be empty")
        self.model = model
        self._url = _chat_completions_url(base_url)
        self._api_key = api_key
        self._timeout = timeout
        self._client = client
        self._max_tokens = max_tokens
        self._system_prompt = system_prompt

    async def _complete(self, messages: Sequence[ChatMessage]) -> str:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        prepared = list(messages)
        if self._system_prompt and not any(item.get("role") == "system" for item in prepared):
            prepared.insert(0, {"role": "system", "content": self._system_prompt})
        request: dict[str, Any] = {"model": self.model, "messages": prepared, "stream": False}
        if self._max_tokens is not None:
            request["max_tokens"] = self._max_tokens
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient()
        try:
            response = await client.post(
                self._url, json=request, headers=headers, timeout=self._timeout
            )
            response.raise_for_status()
            try:
                payload = response.json()
            except ValueError as exc:
                raise ProviderError("inference endpoint returned invalid JSON") from exc
            return _response_text(payload)
        except httpx.HTTPError as exc:
            raise ProviderError(f"inference request failed: {exc}") from exc
        finally:
            if owns_client:
                await client.aclose()


class OpenAICompatibleLanguageProvider(_OpenAICompatibleClient):
    """Text generation through an OpenAI-compatible chat completions endpoint."""

    async def complete(self, messages: Sequence[ChatMessage] | str) -> str:
        if isinstance(messages, str):
            messages = ({"role": "user", "content": messages},)
        return await self._complete(messages)


class OpenAICompatibleVisionProvider(_OpenAICompatibleClient):
    """Vision inference using OpenAI's multimodal message representation."""

    def __init__(self, *args: Any, media_type: str = "image/jpeg", **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.media_type = media_type

    def _message(self, question: str, images: Sequence[bytes]) -> ChatMessage:
        if not images or any(not image for image in images):
            raise ValueError("vision inference requires non-empty image bytes")
        content: list[dict[str, Any]] = [{"type": "text", "text": question}]
        content.extend(
            {
                "type": "image_url",
                "image_url": {"url": _image_data_url(image, self.media_type)},
            }
            for image in images
        )
        return {"role": "user", "content": content}

    async def answer_visual_question(self, question: str, frame: bytes) -> str:
        return await self._complete((self._message(question, (frame,)),))

    async def describe_scene(self, frame: bytes) -> str:
        return await self.answer_visual_question(
            "Describe the current scene concisely, focusing on people and visible objects.", frame
        )

    async def compare_frames(self, previous: bytes, current: bytes, question: str) -> str:
        prompt = (
            f"The first image is the previous frame and the second is the current frame. {question}"
        )
        return await self._complete((self._message(prompt, (previous, current)),))


# Shorter aliases for applications that are not exposing the transport choice.
OpenAILanguageProvider = OpenAICompatibleLanguageProvider
OpenAIVisionProvider = OpenAICompatibleVisionProvider
