"""Route user turns to language or on-demand visual inference."""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum

from wyndle.providers import ChatMessage, LanguageProvider, VisionProvider

# Concrete camera-relative wording is intentionally favored over broad words
# such as "see", which is common in non-visual conversation ("I see").
_VISUAL_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bwhat (?:am i|are (?:they|we|you)|is (?:he|she|this|that)) (?:holding|wearing|doing)\b",
        r"\bwhat(?:'s| is) (?:in front of|behind|next to|on)\b",
        r"\bwhat (?:can you|do you) see\b",
        (
            r"\b(?:look at|read|identify|recognize|describe) "
            r"(?:this|that|the (?:image|picture|scene|object|text))\b"
        ),
        r"\b(?:in|from) (?:this|the) (?:image|picture|frame|camera|scene)\b",
        r"\bwhat color is (?:this|that|the object)\b",
    )
)


def is_visual_question(question: str) -> bool:
    """Return whether a turn asks for evidence from the current camera view."""

    normalized = " ".join(question.split())
    return any(pattern.search(normalized) for pattern in _VISUAL_PATTERNS)


class Route(StrEnum):
    LANGUAGE = "language"
    VISION = "vision"


class VisualFrameRequiredError(ValueError):
    """A visual turn was received without a current camera frame."""


@dataclass(frozen=True)
class RoutedAnswer:
    text: str
    route: Route


class VisualQuestionRouter:
    """Dispatch ordinary turns to the LLM and camera questions to the VLM.

    Frame acquisition stays outside this class so providers remain independent
    from RTSP/camera plumbing.  A custom classifier can be supplied later
    without changing the routing contract.
    """

    def __init__(
        self,
        language: LanguageProvider,
        vision: VisionProvider,
        *,
        classifier: Callable[[str], bool] = is_visual_question,
    ) -> None:
        self.language = language
        self.vision = vision
        self.classifier = classifier

    def route(self, question: str) -> Route:
        return Route.VISION if self.classifier(question) else Route.LANGUAGE

    async def answer(
        self,
        question: str,
        *,
        frame: bytes | None = None,
        history: Sequence[ChatMessage] = (),
    ) -> RoutedAnswer:
        route = self.route(question)
        if route is Route.VISION:
            if not frame:
                raise VisualFrameRequiredError("a fresh frame is required for a visual question")
            text = await self.vision.answer_visual_question(question, frame)
        else:
            messages = [*history, {"role": "user", "content": question}]
            text = await self.language.complete(messages)
        return RoutedAnswer(text=text, route=route)
