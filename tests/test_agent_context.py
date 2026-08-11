from datetime import UTC, datetime

import pytest

from wyndle.agent.context import ContextKind, WorkingContext


def test_context_is_bounded_and_keeps_order() -> None:
    context = WorkingContext(max_entries=2, now=lambda: datetime(2026, 1, 1, tzinfo=UTC))
    context.add(ContextKind.USER_UTTERANCE, "first")
    context.add(ContextKind.AGENT_REPLY, "second")
    context.add(ContextKind.VISUAL_ANSWER, "third")
    assert [item.content for item in context.recent()] == ["second", "third"]


def test_context_can_filter_and_serialize_for_prompt() -> None:
    context = WorkingContext()
    context.add(ContextKind.USER_UTTERANCE, "What am I holding?")
    context.add(ContextKind.VISUAL_ANSWER, "A yellow drill")
    context.add(ContextKind.AGENT_REPLY, "A yellow drill.")
    visual = context.recent(kinds=[ContextKind.VISUAL_ANSWER])
    assert [entry.content for entry in visual] == ["A yellow drill"]
    assert context.prompt_items(limit=1)[0]["kind"] == "agent_reply"


def test_context_rejects_empty_or_invalid_limits() -> None:
    context = WorkingContext()
    with pytest.raises(ValueError):
        context.add(ContextKind.USER_UTTERANCE, " ")
    with pytest.raises(ValueError):
        context.recent(limit=-1)
