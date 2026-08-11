"""Bounded ONVIF PTZ control for the verified C216.

This module never discovers or probes hardware on import.  Callers must provide an
already-created ONVIF PTZ service and media profile token.
"""

from __future__ import annotations

import asyncio
import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

_T = TypeVar("_T")


class PTZError(RuntimeError):
    """Base error for safe PTZ operations."""


class PTZLimitError(PTZError, ValueError):
    """A command exceeded a configured hard safety limit."""


class PTZConnectionError(PTZError):
    """The ONVIF service rejected or failed a movement command."""


class PTZStopError(PTZError):
    """The adapter could not confirm a stop after a command."""


@dataclass(frozen=True)
class PTZLimits:
    """Hard limits chosen to keep agent-issued C216 movement conservative."""

    max_relative_pan: float = 0.15
    max_relative_tilt: float = 0.15
    max_speed: float = 0.25
    min_absolute_pan: float = -1.0
    max_absolute_pan: float = 1.0
    min_absolute_tilt: float = -1.0
    max_absolute_tilt: float = 1.0
    operation_timeout: float = 3.0
    movement_settle_seconds: float = 1.0


class ONVIFPTZAdapter:
    """Serialize and safety-bound ONVIF RelativeMove/AbsoluteMove calls.

    Every attempted movement is followed by ``Stop`` even if the movement RPC
    raises.  Values outside the limits are rejected, not silently clamped.
    """

    def __init__(self, service: Any, profile_token: str, limits: PTZLimits | None = None) -> None:
        if not profile_token:
            raise ValueError("profile_token is required")
        self._service = service
        self._profile_token = profile_token
        self.limits = limits or PTZLimits()
        self._lock = asyncio.Lock()

    async def relative_move(self, pan: float = 0.0, tilt: float = 0.0, speed: float = 0.15) -> None:
        """Move by a small normalized displacement, then guarantee a stop attempt."""
        pan = self._bounded("pan", pan, -self.limits.max_relative_pan, self.limits.max_relative_pan)
        tilt = self._bounded(
            "tilt", tilt, -self.limits.max_relative_tilt, self.limits.max_relative_tilt
        )
        speed = self._bounded("speed", speed, 0.0, self.limits.max_speed)
        if pan == 0.0 and tilt == 0.0:
            raise PTZLimitError("relative movement must change pan or tilt")
        request = {
            "ProfileToken": self._profile_token,
            "Translation": {"PanTilt": {"x": pan, "y": tilt}},
            "Speed": {"PanTilt": {"x": speed, "y": speed}},
        }
        await self._move_with_stop("RelativeMove", request)

    async def absolute_move(self, pan: float, tilt: float, speed: float = 0.15) -> None:
        """Move to a bounded normalized position, then guarantee a stop attempt."""
        pan = self._bounded("pan", pan, self.limits.min_absolute_pan, self.limits.max_absolute_pan)
        tilt = self._bounded(
            "tilt", tilt, self.limits.min_absolute_tilt, self.limits.max_absolute_tilt
        )
        speed = self._bounded("speed", speed, 0.0, self.limits.max_speed)
        request = {
            "ProfileToken": self._profile_token,
            "Position": {"PanTilt": {"x": pan, "y": tilt}},
            "Speed": {"PanTilt": {"x": speed, "y": speed}},
        }
        await self._move_with_stop("AbsoluteMove", request)

    async def position(self) -> tuple[float, float]:
        """Return the current normalized pan/tilt position."""
        async with self._lock:
            try:
                status = await self._call(
                    self._service.GetStatus, {"ProfileToken": self._profile_token}
                )
                pan_tilt = status.Position.PanTilt
                return float(pan_tilt.x), float(pan_tilt.y)
            except Exception as exc:
                raise self._connection_error("GetStatus", exc) from exc

    async def stop(self) -> None:
        """Explicitly stop both pan/tilt and zoom axes."""
        async with self._lock:
            await self._stop_unlocked()

    async def _move_with_stop(self, method_name: str, request: dict[str, Any]) -> None:
        async with self._lock:
            move_error: PTZConnectionError | None = None
            try:
                await self._call(getattr(self._service, method_name), request)
                await asyncio.sleep(self.limits.movement_settle_seconds)
            except Exception as exc:
                move_error = self._connection_error(method_name, exc)
            try:
                await self._stop_unlocked()
            except PTZStopError as stop_error:
                if move_error is not None:
                    raise PTZStopError(
                        f"{method_name} failed and the recovery Stop also failed: "
                        f"{move_error}; {stop_error}"
                    ) from stop_error
                raise
            if move_error is not None:
                raise move_error

    async def _stop_unlocked(self) -> None:
        request = {"ProfileToken": self._profile_token, "PanTilt": True, "Zoom": True}
        try:
            await self._call(self._service.Stop, request)
        except Exception as exc:
            if isinstance(exc, asyncio.TimeoutError):
                detail = f"timed out after {self.limits.operation_timeout:g}s"
            else:
                detail = str(exc).strip() or type(exc).__name__
            raise PTZStopError(f"ONVIF Stop failed: {detail}") from exc

    async def _call(self, operation: Callable[[dict[str, Any]], _T], request: dict[str, Any]) -> _T:
        return await asyncio.wait_for(
            asyncio.to_thread(operation, request), timeout=self.limits.operation_timeout
        )

    def _connection_error(self, operation: str, exc: Exception) -> PTZConnectionError:
        if isinstance(exc, asyncio.TimeoutError):
            detail = f"timed out after {self.limits.operation_timeout:g}s"
        else:
            detail = str(exc).strip() or type(exc).__name__
        return PTZConnectionError(f"ONVIF {operation} failed: {detail}")

    @staticmethod
    def _bounded(name: str, value: float, minimum: float, maximum: float) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise PTZLimitError(f"{name} must be a finite number")
        result = float(value)
        if not math.isfinite(result):
            raise PTZLimitError(f"{name} must be a finite number")
        if not minimum <= result <= maximum:
            raise PTZLimitError(
                f"{name}={result:g} is outside hard limit [{minimum:g}, {maximum:g}]"
            )
        return result
