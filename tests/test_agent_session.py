from datetime import UTC, datetime

import pytest

from wyndle.agent.context import ContextKind
from wyndle.agent.session import ConversationSession


class Clock:
    value = 0.0

    def __call__(self) -> float:
        return self.value


def test_session_times_out_after_last_meaningful_exchange() -> None:
    clock = Clock()
    session = ConversationSession(15, monotonic=clock)
    session.open()
    clock.value = 10
    session.mark_meaningful_exchange()
    clock.value = 24.9
    assert not session.is_expired()
    clock.value = 25
    assert session.expire_if_needed()
    assert not session.is_open


def test_session_snapshot_exposes_prompt_timing_without_internal_clock() -> None:
    clock = Clock()
    now = datetime(2026, 1, 1, tzinfo=UTC)
    session = ConversationSession(monotonic=clock, now=lambda: now)
    session_id = session.open()
    clock.value = 3.5
    snapshot = session.snapshot()
    assert snapshot.session_id == session_id
    assert snapshot.open
    assert snapshot.seconds_since_wake == 3.5
    assert snapshot.seconds_since_last_meaningful_exchange == 3.5


def test_opening_or_closing_session_clears_ephemeral_context() -> None:
    session = ConversationSession()
    session.open()
    session.context.add(ContextKind.USER_UTTERANCE, "private short-term text")
    session.close()
    assert len(session.context) == 0
    session.open()
    assert len(session.context) == 0


def test_closed_session_cannot_record_exchange() -> None:
    with pytest.raises(RuntimeError, match="closed"):
        ConversationSession().mark_meaningful_exchange()
