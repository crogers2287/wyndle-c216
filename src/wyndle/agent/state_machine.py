"""Explicit lifecycle state machine for the Wyndle agent."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum


class AgentState(StrEnum):
    BOOTING = "booting"
    CAMERA_CONNECTING = "camera_connecting"
    IDLE_WATCHING = "idle_watching"
    WAKE_DETECTED = "wake_detected"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    CONVERSATION_OPEN = "conversation_open"
    DEGRADED = "degraded"


_ALLOWED_TRANSITIONS: dict[AgentState, frozenset[AgentState]] = {
    AgentState.BOOTING: frozenset({AgentState.CAMERA_CONNECTING, AgentState.DEGRADED}),
    AgentState.CAMERA_CONNECTING: frozenset({AgentState.IDLE_WATCHING, AgentState.DEGRADED}),
    AgentState.IDLE_WATCHING: frozenset({AgentState.WAKE_DETECTED, AgentState.DEGRADED}),
    AgentState.WAKE_DETECTED: frozenset(
        {AgentState.LISTENING, AgentState.SPEAKING, AgentState.IDLE_WATCHING, AgentState.DEGRADED}
    ),
    AgentState.LISTENING: frozenset(
        {
            AgentState.THINKING,
            AgentState.CONVERSATION_OPEN,
            AgentState.IDLE_WATCHING,
            AgentState.DEGRADED,
        }
    ),
    AgentState.THINKING: frozenset(
        {AgentState.SPEAKING, AgentState.CONVERSATION_OPEN, AgentState.DEGRADED}
    ),
    AgentState.SPEAKING: frozenset(
        {AgentState.LISTENING, AgentState.CONVERSATION_OPEN, AgentState.DEGRADED}
    ),
    AgentState.CONVERSATION_OPEN: frozenset(
        {AgentState.LISTENING, AgentState.IDLE_WATCHING, AgentState.DEGRADED}
    ),
    AgentState.DEGRADED: frozenset({AgentState.CAMERA_CONNECTING, AgentState.IDLE_WATCHING}),
}


class InvalidTransition(ValueError):
    """Raised when a lifecycle transition is not part of the explicit graph."""


@dataclass(frozen=True, slots=True)
class StateTransition:
    previous: AgentState
    current: AgentState
    reason: str
    occurred_at: datetime


class AgentStateMachine:
    """Small synchronous state machine; I/O remains the runtime's responsibility."""

    def __init__(
        self,
        initial: AgentState = AgentState.BOOTING,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._state = initial
        self._now = now or (lambda: datetime.now(UTC))
        self._last_transition: StateTransition | None = None

    @property
    def state(self) -> AgentState:
        return self._state

    @property
    def last_transition(self) -> StateTransition | None:
        return self._last_transition

    def can_transition_to(self, target: AgentState) -> bool:
        return target in _ALLOWED_TRANSITIONS[self._state]

    def transition(self, target: AgentState, *, reason: str) -> StateTransition:
        if not reason.strip():
            raise ValueError("transition reason must not be empty")
        if not self.can_transition_to(target):
            raise InvalidTransition(f"cannot transition from {self._state} to {target}")
        transition = StateTransition(self._state, target, reason, self._now())
        self._state = target
        self._last_transition = transition
        return transition
