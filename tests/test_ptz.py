from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock

import pytest

from wyndle.agent.tools import PTZTools
from wyndle.camera.ptz import (
    ONVIFPTZAdapter,
    PTZConnectionError,
    PTZLimitError,
    PTZLimits,
    PTZStopError,
)


class MockPTZService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.move_error: Exception | None = None
        self.stop_error: Exception | None = None

    def RelativeMove(self, request: dict) -> None:
        self.calls.append(("RelativeMove", request))
        if self.move_error:
            raise self.move_error

    def AbsoluteMove(self, request: dict) -> None:
        self.calls.append(("AbsoluteMove", request))
        if self.move_error:
            raise self.move_error

    def GetStatus(self, request: dict):
        self.calls.append(("GetStatus", request))
        pan_tilt = type("PanTilt", (), {"x": 0.1, "y": -0.2})()
        position = type("Position", (), {"PanTilt": pan_tilt})()
        return type("Status", (), {"Position": position})()

    def Stop(self, request: dict) -> None:
        self.calls.append(("Stop", request))
        if self.stop_error:
            raise self.stop_error


@pytest.mark.asyncio
async def test_relative_move_is_bounded_and_always_stops() -> None:
    service = MockPTZService()
    adapter = ONVIFPTZAdapter(service, "profile-1", PTZLimits(movement_settle_seconds=0))

    await adapter.relative_move(pan=-0.05, tilt=0.02, speed=0.1)

    assert [name for name, _ in service.calls] == ["RelativeMove", "Stop"]
    request = service.calls[0][1]
    assert request["ProfileToken"] == "profile-1"
    assert request["Translation"]["PanTilt"] == {"x": -0.05, "y": 0.02}
    assert request["Speed"]["PanTilt"] == {"x": 0.1, "y": 0.1}
    assert service.calls[1][1]["PanTilt"] is True


@pytest.mark.asyncio
async def test_absolute_move_uses_bounded_position_and_stops() -> None:
    service = MockPTZService()
    adapter = ONVIFPTZAdapter(service, "profile-1", PTZLimits(movement_settle_seconds=0))
    await adapter.absolute_move(pan=0.5, tilt=-0.25, speed=0.2)
    assert service.calls[0] == (
        "AbsoluteMove",
        {
            "ProfileToken": "profile-1",
            "Position": {"PanTilt": {"x": 0.5, "y": -0.25}},
            "Speed": {"PanTilt": {"x": 0.2, "y": 0.2}},
        },
    )
    assert service.calls[1][0] == "Stop"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "kwargs"),
    [
        ("relative_move", {"pan": 0.16}),
        ("relative_move", {"tilt": -0.16}),
        ("relative_move", {"pan": 0.01, "speed": 0.26}),
        ("relative_move", {"pan": float("nan")}),
        ("absolute_move", {"pan": 1.01, "tilt": 0.0}),
        ("absolute_move", {"pan": 0.0, "tilt": -1.01}),
    ],
)
async def test_invalid_values_are_rejected_without_touching_service(
    method: str, kwargs: dict
) -> None:
    service = MockPTZService()
    adapter = ONVIFPTZAdapter(service, "profile-1", PTZLimits(movement_settle_seconds=0))
    with pytest.raises(PTZLimitError):
        await getattr(adapter, method)(**kwargs)
    assert service.calls == []


@pytest.mark.asyncio
async def test_move_failure_still_issues_stop_and_returns_clear_error() -> None:
    service = MockPTZService()
    service.move_error = OSError("camera disconnected")
    adapter = ONVIFPTZAdapter(service, "profile-1", PTZLimits(movement_settle_seconds=0))
    with pytest.raises(PTZConnectionError, match="RelativeMove.*camera disconnected"):
        await adapter.relative_move(pan=0.01)
    assert [name for name, _ in service.calls] == ["RelativeMove", "Stop"]


@pytest.mark.asyncio
async def test_stop_failure_is_never_hidden() -> None:
    service = MockPTZService()
    service.stop_error = OSError("stop unavailable")
    adapter = ONVIFPTZAdapter(service, "profile-1", PTZLimits(movement_settle_seconds=0))
    with pytest.raises(PTZStopError, match="Stop failed.*stop unavailable"):
        await adapter.absolute_move(0.0, 0.0)


@pytest.mark.asyncio
async def test_move_and_recovery_stop_failure_reports_both() -> None:
    service = MockPTZService()
    service.move_error = OSError("move unavailable")
    service.stop_error = OSError("stop unavailable")
    adapter = ONVIFPTZAdapter(service, "profile-1", PTZLimits(movement_settle_seconds=0))
    with pytest.raises(PTZStopError, match="move unavailable.*stop unavailable"):
        await adapter.relative_move(pan=0.01)


@pytest.mark.asyncio
async def test_timeout_is_actionable_and_attempts_stop() -> None:
    service = MockPTZService()

    def slow_move(request: dict) -> None:
        service.calls.append(("RelativeMove", request))
        time.sleep(0.05)

    service.RelativeMove = slow_move  # type: ignore[method-assign]
    adapter = ONVIFPTZAdapter(service, "profile-1", PTZLimits(operation_timeout=0.01))
    with pytest.raises(PTZConnectionError, match="timed out after 0.01s"):
        await adapter.relative_move(pan=0.01)
    assert any(name == "Stop" for name, _ in service.calls)


@pytest.mark.asyncio
async def test_commands_are_serialized() -> None:
    service = MockPTZService()
    adapter = ONVIFPTZAdapter(service, "profile-1", PTZLimits(movement_settle_seconds=0))
    await asyncio.gather(
        adapter.relative_move(pan=0.01),
        adapter.relative_move(tilt=0.01),
    )
    assert [name for name, _ in service.calls] == [
        "RelativeMove",
        "Stop",
        "RelativeMove",
        "Stop",
    ]


@pytest.mark.asyncio
async def test_agent_tools_only_expose_fixed_directions_and_amounts() -> None:
    adapter = AsyncMock(spec=ONVIFPTZAdapter)
    adapter.position.return_value = (0.1, -0.2)
    adapter.limits = PTZLimits()
    tools = PTZTools(adapter)
    await tools.look_left("medium")
    await tools.look_up()
    adapter.absolute_move.assert_any_await(pytest.approx(0.02), -0.2)
    adapter.absolute_move.assert_any_await(0.1, -0.16)
    with pytest.raises(ValueError, match="small.*medium"):
        await tools.look_right("large")
