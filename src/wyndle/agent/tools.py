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
        await self.adapter.relative_move(pan=-self.amounts.resolve(amount))

    async def look_right(self, amount: str = "small") -> None:
        await self.adapter.relative_move(pan=self.amounts.resolve(amount))

    async def look_up(self, amount: str = "small") -> None:
        await self.adapter.relative_move(tilt=self.amounts.resolve(amount))

    async def look_down(self, amount: str = "small") -> None:
        await self.adapter.relative_move(tilt=-self.amounts.resolve(amount))

    async def stop_looking(self) -> None:
        await self.adapter.stop()
