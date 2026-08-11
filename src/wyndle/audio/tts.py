"""Local Piper TTS adapter."""

from __future__ import annotations

import asyncio
from pathlib import Path


class PiperTTS:
    def __init__(self, executable: Path, model: Path) -> None:
        self.executable = executable
        self.model = model

    async def synthesize(self, text: str, output: Path) -> Path:
        if not text.strip():
            raise ValueError("text must not be empty")
        output.parent.mkdir(parents=True, exist_ok=True)
        proc = await asyncio.create_subprocess_exec(
            str(self.executable),
            "--model",
            str(self.model),
            "--output_file",
            str(output),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate((text.strip() + "\n").encode())
        if proc.returncode:
            raise RuntimeError("Piper failed: " + stderr.decode(errors="replace")[-500:])
        return output
