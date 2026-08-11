"""Bounded, in-memory context for the current conversation."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum


class ContextKind(StrEnum):
    USER_UTTERANCE = "user_utterance"
    AGENT_REPLY = "agent_reply"
    VISUAL_ANSWER = "visual_answer"
    PTZ_ACTION = "ptz_action"
    SCENE_STATE = "scene_state"


@dataclass(frozen=True, slots=True)
class ContextEntry:
    kind: ContextKind
    content: str
    created_at: datetime

    def as_prompt_item(self) -> dict[str, str]:
        return {
            "kind": self.kind.value,
            "content": self.content,
            "created_at": self.created_at.isoformat(),
        }


class WorkingContext:
    """A deliberately small FIFO context; it never persists media or transcripts."""

    def __init__(
        self,
        max_entries: int = 20,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be at least 1")
        self._entries: deque[ContextEntry] = deque(maxlen=max_entries)
        self._now = now or (lambda: datetime.now(UTC))

    def add(self, kind: ContextKind, content: str) -> ContextEntry:
        content = content.strip()
        if not content:
            raise ValueError("context content must not be empty")
        entry = ContextEntry(kind, content, self._now())
        self._entries.append(entry)
        return entry

    def recent(
        self, *, limit: int | None = None, kinds: Iterable[ContextKind] | None = None
    ) -> tuple[ContextEntry, ...]:
        entries = tuple(self._entries)
        if kinds is not None:
            allowed = frozenset(kinds)
            entries = tuple(entry for entry in entries if entry.kind in allowed)
        if limit is not None:
            if limit < 0:
                raise ValueError("limit must not be negative")
            entries = entries[-limit:] if limit else ()
        return entries

    def prompt_items(self, *, limit: int | None = None) -> list[dict[str, str]]:
        return [entry.as_prompt_item() for entry in self.recent(limit=limit)]

    def clear(self) -> None:
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)
