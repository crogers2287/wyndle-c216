"""Condition local speech audio for the C216 PCMA/8000 backchannel."""

from __future__ import annotations

import asyncio
from pathlib import Path


async def condition_c216_audio(
    source: Path,
    output: Path,
    *,
    volume: float = 0.5,
    leading_silence: float = 2.0,
    trailing_silence: float = 1.0,
) -> Path:
    """Create 8 kHz mono PCM with silence padding required by C216 talk startup."""
    if not source.is_file():
        raise ValueError("source audio must exist")
    if not 0 < volume <= 1:
        raise ValueError("volume must be between zero and one")
    output.parent.mkdir(parents=True, exist_ok=True)
    filter_graph = (
        f"volume={volume},highpass=f=180,lowpass=f=3400,"
        f"adelay={round(leading_silence * 1000)}:all=1,"
        f"apad=pad_dur={trailing_silence}"
    )
    process = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(source),
        "-af",
        filter_graph,
        "-ar",
        "8000",
        "-ac",
        "1",
        "-c:a",
        "pcm_s16le",
        "-y",
        str(output),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()
    if process.returncode:
        raise RuntimeError("C216 audio conditioning failed: " + stderr.decode()[-500:])
    return output
