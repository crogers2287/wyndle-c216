"""Faster-Whisper adapter isolated behind an external Python environment."""

from __future__ import annotations

import asyncio
from pathlib import Path


class FasterWhisperSTT:
    def __init__(
        self, python: Path, model: Path, *, device: str = "cpu", compute_type: str = "int8"
    ) -> None:
        self.python = python
        self.model = model
        self.device = device
        self.compute_type = compute_type

    async def transcribe(self, wav: Path) -> str:
        code = (
            "from faster_whisper import WhisperModel;"
            "m=WhisperModel("
            f"{str(self.model)!r},device={self.device!r},"
            f"compute_type={self.compute_type!r},cpu_threads=16);"
            f"s,_=m.transcribe({str(wav)!r},vad_filter=True,beam_size=1);"
            "print(' '.join(x.text.strip() for x in s))"
        )
        proc = await asyncio.create_subprocess_exec(
            str(self.python),
            "-c",
            code,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode:
            raise RuntimeError("STT failed: " + stderr.decode(errors="replace")[-500:])
        return stdout.decode().strip()
