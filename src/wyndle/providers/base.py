"""Provider interfaces used by the Wyndle agent.

The protocols deliberately model Wyndle's needs rather than a vendor SDK.  A
language and vision provider may point at the same server/model, but callers do
not need to know that.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol, runtime_checkable

ChatMessage = Mapping[str, Any]


@runtime_checkable
class LanguageProvider(Protocol):
    """Generate a text response from an OpenAI-style message history."""

    async def complete(self, messages: Sequence[ChatMessage]) -> str: ...


@runtime_checkable
class VisionProvider(Protocol):
    """Answer questions whose evidence is in one or more camera frames."""

    async def answer_visual_question(self, question: str, frame: bytes) -> str: ...

    async def describe_scene(self, frame: bytes) -> str: ...

    async def compare_frames(self, previous: bytes, current: bytes, question: str) -> str: ...
