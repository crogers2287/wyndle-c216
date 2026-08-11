"""FFmpeg-backed frame and camera-audio capture."""

from __future__ import annotations

import asyncio


class MediaError(RuntimeError):
    pass


async def _run(*args: str, timeout: float) -> bytes:
    proc = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout)
    except TimeoutError as exc:
        proc.kill()
        await proc.wait()
        raise MediaError(f"media command timed out after {timeout:g}s") from exc
    if proc.returncode:
        raise MediaError("ffmpeg failed: " + stderr.decode(errors="replace").strip()[-500:])
    return stdout


async def capture_jpeg(rtsp_url: str, timeout: float = 12.0) -> bytes:
    return await _run(
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-rtsp_transport",
        "tcp",
        "-i",
        rtsp_url,
        "-frames:v",
        "1",
        "-f",
        "image2pipe",
        "-vcodec",
        "mjpeg",
        "pipe:1",
        timeout=timeout,
    )


async def capture_audio_wav(rtsp_url: str, seconds: float, timeout: float = 20.0) -> bytes:
    if not 0.2 <= seconds <= 30:
        raise ValueError("seconds must be between 0.2 and 30")
    return await _run(
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-rtsp_transport",
        "tcp",
        "-i",
        rtsp_url,
        "-vn",
        "-t",
        str(seconds),
        "-ar",
        "16000",
        "-ac",
        "1",
        "-f",
        "wav",
        "pipe:1",
        timeout=timeout,
    )
