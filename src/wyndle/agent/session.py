"""Conversation session timing and ownership of short-lived context."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from wyndle.agent.context import WorkingContext


@dataclass(frozen=True, slots=True)
class SessionSnapshot:
    session_id: str | None
    open: bool
    seconds_since_wake: float | None
    seconds_since_last_meaningful_exchange: float | None


class ConversationSession:
    """Tracks one wake-opened session using a monotonic clock for timeout safety."""

    def __init__(
        self,
        timeout_seconds: float = 15.0,
        *,
        context_max_entries: int = 20,
        monotonic: Callable[[], float] | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        import time

        self.timeout_seconds = timeout_seconds
        self.context = WorkingContext(context_max_entries, now=now)
        self._monotonic = monotonic or time.monotonic
        self._now = now or (lambda: datetime.now(UTC))
        self.session_id: str | None = None
        self.opened_at: datetime | None = None
        self._opened_tick: float | None = None
        self._last_exchange_tick: float | None = None

    @property
    def is_open(self) -> bool:
        return self.session_id is not None

    def open(self) -> str:
        tick = self._monotonic()
        self.session_id = str(uuid4())
        self.opened_at = self._now()
        self._opened_tick = tick
        self._last_exchange_tick = tick
        self.context.clear()
        return self.session_id

    def mark_meaningful_exchange(self) -> None:
        if not self.is_open:
            raise RuntimeError("cannot update a closed session")
        self._last_exchange_tick = self._monotonic()

    def is_expired(self) -> bool:
        if not self.is_open or self._last_exchange_tick is None:
            return False
        return self._monotonic() - self._last_exchange_tick >= self.timeout_seconds

    def expire_if_needed(self) -> bool:
        if not self.is_expired():
            return False
        self.close()
        return True

    def close(self) -> None:
        self.session_id = None
        self.opened_at = None
        self._opened_tick = None
        self._last_exchange_tick = None
        self.context.clear()

    def snapshot(self) -> SessionSnapshot:
        tick = self._monotonic()
        since_wake = tick - self._opened_tick if self._opened_tick is not None else None
        since_exchange = (
            tick - self._last_exchange_tick if self._last_exchange_tick is not None else None
        )
        return SessionSnapshot(self.session_id, self.is_open, since_wake, since_exchange)
