"""go2rtc Tapo backchannel client."""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx


class Go2RTCError(RuntimeError):
    pass


class Go2RTCBackchannel:
    def __init__(self, base_url: str, stream: str, *, timeout: float = 10) -> None:
        self.base_url = base_url.rstrip("/")
        self.stream = stream
        self.timeout = timeout

    async def status(self) -> dict:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                f"{self.base_url}/api/streams", params={"src": self.stream, "microphone": "all"}
            )
            response.raise_for_status()
            return response.json()

    async def play_file(self, path: Path, *, duration: float | None = None) -> None:
        if not path.is_absolute() or not path.is_file():
            raise ValueError("audio path must be an existing absolute file")
        source = f"ffmpeg:{path}#audio=pcma#input=file"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/api/streams", params={"dst": self.stream, "src": source}
            )
            response.raise_for_status()
        if duration is not None:
            await asyncio.sleep(duration)
            await self.stop()

    async def stop(self) -> None:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/api/streams", params={"dst": self.stream, "src": ""}
            )
            response.raise_for_status()
