from datetime import UTC, datetime

import pytest

from wyndle.agent.state_machine import AgentState, AgentStateMachine, InvalidTransition


def test_happy_path_transitions_are_explicit() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    machine = AgentStateMachine(now=lambda: now)

    path = [
        AgentState.CAMERA_CONNECTING, AgentState.IDLE_WATCHING,
        AgentState.WAKE_DETECTED, AgentState.LISTENING, AgentState.THINKING,
        AgentState.SPEAKING, AgentState.CONVERSATION_OPEN,
        AgentState.LISTENING, AgentState.THINKING, AgentState.SPEAKING,
        AgentState.CONVERSATION_OPEN, AgentState.IDLE_WATCHING,
    ]
    for target in path:
        transition = machine.transition(target, reason="test")
        assert transition.current is target
        assert transition.occurred_at == now
    assert machine.state is AgentState.IDLE_WATCHING


def test_invalid_transition_does_not_change_state() -> None:
    machine = AgentStateMachine()
    with pytest.raises(InvalidTransition, match="booting.*speaking"):
        machine.transition(AgentState.SPEAKING, reason="skip lifecycle")
    assert machine.state is AgentState.BOOTING


def test_degraded_state_has_recovery_paths() -> None:
    machine = AgentStateMachine()
    machine.transition(AgentState.DEGRADED, reason="startup failed")
    assert machine.can_transition_to(AgentState.CAMERA_CONNECTING)
    assert machine.can_transition_to(AgentState.IDLE_WATCHING)


def test_transition_requires_observable_reason() -> None:
    with pytest.raises(ValueError, match="reason"):
        AgentStateMachine().transition(AgentState.CAMERA_CONNECTING, reason="  ")
