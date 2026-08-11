"""Narrow agent-facing PTZ tools; raw coordinates never reach the model."""

from __future__ import annotations

from dataclasses import dataclass

from wyndle.camera.ptz import ONVIFPTZAdapter


@dataclass(frozen=True)
class PTZToolAmounts:
    small: float = 0.04
    medium: float = 0.08

    def resolve(self, amount: str) -> float:
        try:
            return {"small": self.small, "medium": self.medium}[amount]
        except KeyError as exc:
            raise ValueError("amount must be 'small' or 'medium'") from exc


class PTZTools:
    """Deterministic directional commands suitable for agent tool registration."""

    def __init__(self, adapter: ONVIFPTZAdapter, amounts: PTZToolAmounts | None = None) -> None:
        self.adapter = adapter
        self.amounts = amounts or PTZToolAmounts()

    async def look_left(self, amount: str = "small") -> None:
        await self._absolute_delta(pan=-self.amounts.resolve(amount))

    async def look_right(self, amount: str = "small") -> None:
        await self._absolute_delta(pan=self.amounts.resolve(amount))

    async def look_up(self, amount: str = "small") -> None:
        await self._absolute_delta(tilt=self.amounts.resolve(amount))

    async def look_down(self, amount: str = "small") -> None:
        await self._absolute_delta(tilt=-self.amounts.resolve(amount))

    async def _absolute_delta(self, pan: float = 0.0, tilt: float = 0.0) -> None:
        current_pan, current_tilt = await self.adapter.position()
        limits = self.adapter.limits
        target_pan = min(limits.max_absolute_pan, max(limits.min_absolute_pan, current_pan + pan))
        target_tilt = min(
            limits.max_absolute_tilt, max(limits.min_absolute_tilt, current_tilt + tilt)
        )
        await self.adapter.absolute_move(target_pan, target_tilt)

    async def stop_looking(self) -> None:
        await self.adapter.stop()
