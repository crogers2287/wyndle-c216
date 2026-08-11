"""Live microphone diagnostics for the physical C216 media path."""

from __future__ import annotations

import argparse
import asyncio
import math
import struct
import time
import wave
from dataclasses import dataclass
from pathlib import Path

from wyndle.audio.runtime import PCMFrame
from wyndle.config import Settings
from wyndle.live import EnergyVAD, FFmpegPCMSource


@dataclass(frozen=True, slots=True)
class AudioMetrics:
    sample_count: int
    rms: float
    peak: int
    minimum: int
    maximum: int
    unique_samples: int
    zero_percent: float


def measure_pcm(pcm: bytes) -> AudioMetrics:
    count = len(pcm) // 2
    if not count:
        return AudioMetrics(0, 0.0, 0, 0, 0, 0, 100.0)
    samples = struct.unpack(f"<{count}h", pcm)
    rms = math.sqrt(sum(value * value for value in samples) / count)
    return AudioMetrics(
        sample_count=count,
        rms=rms,
        peak=max(abs(min(samples)), abs(max(samples))),
        minimum=min(samples),
        maximum=max(samples),
        unique_samples=len(set(samples)),
        zero_percent=100.0 * sum(value == 0 for value in samples) / count,
    )


def write_wav(path: Path, pcm: bytes, sample_rate: int = 16_000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(pcm)


async def capture_source(url: str, seconds: float, path: Path) -> AudioMetrics:
    source = FFmpegPCMSource(url)
    chunks: list[bytes] = []
    deadline = time.monotonic() + seconds
    async for frame in source:
        chunks.append(frame.data)
        if time.monotonic() >= deadline:
            break
    pcm = b"".join(chunks)
    write_wav(path, pcm)
    return measure_pcm(pcm)


async def capture_pair(seconds: float, directory: Path) -> None:
    settings = Settings()
    direct = settings.rtsp_url(2)
    if direct is None:
        raise RuntimeError("direct C216 RTSP stream2 is not configured")
    relay = f"rtsp://127.0.0.1:8554/{settings.go2rtc_stream_name}"
    directory.mkdir(parents=True, exist_ok=True)
    print(f"Capturing both microphone sources for {seconds:g} seconds now...", flush=True)
    results = await asyncio.gather(
        capture_source(direct, seconds, directory / "c216-stream2.wav"),
        capture_source(relay, seconds, directory / "go2rtc-wyndle.wav"),
    )
    for source, path, metrics in zip(
        ("C216 RTSP stream2", "go2rtc relay"),
        (directory / "c216-stream2.wav", directory / "go2rtc-wyndle.wav"),
        results,
        strict=True,
    ):
        print(
            f"SOURCE={source} samples={metrics.sample_count} rms={metrics.rms:.2f} "
            f"peak={metrics.peak} min={metrics.minimum} max={metrics.maximum} "
            f"unique={metrics.unique_samples} zero_percent={metrics.zero_percent:.3f} "
            f"wav={path}",
            flush=True,
        )


async def monitor(source_name: str, output: Path | None) -> None:
    settings = Settings()
    if source_name == "direct":
        url = settings.rtsp_url(2)
        label = "C216 RTSP stream2"
    else:
        url = f"rtsp://127.0.0.1:8554/{settings.go2rtc_stream_name}"
        label = "go2rtc relay"
    if url is None:
        raise RuntimeError("requested microphone source is not configured")
    vad = EnergyVAD()
    source = FFmpegPCMSource(url)
    pending: list[bytes] = []
    recording: list[bytes] = []
    next_report = time.monotonic() + 1.0
    wake_state = "diagnostic-only (disabled)"
    try:
        async for frame in source:
            pending.append(frame.data)
            if output is not None:
                recording.append(frame.data)
            now = time.monotonic()
            if now >= next_report:
                pcm = b"".join(pending)
                metrics = measure_pcm(pcm)
                probe = PCMFrame(pcm, frame.captured_at)
                print(
                    f"{time.strftime('%Y-%m-%dT%H:%M:%S')} SOURCE={label} "
                    f"RMS={metrics.rms:.2f} PEAK={metrics.peak} "
                    f"VAD={'speech' if vad.is_speech(probe) else 'silence'} "
                    f"WAKE_STATE={wake_state}",
                    flush=True,
                )
                pending.clear()
                next_report = now + 1.0
    finally:
        if output is not None and recording:
            write_wav(output, b"".join(recording))
            print(f"WAV saved: {output}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Continuously inspect the live C216 microphone")
    parser.add_argument("--source", choices=("direct", "relay"), default="relay")
    parser.add_argument("--wav", type=Path, help="optionally save all monitored PCM as WAV")
    parser.add_argument(
        "--capture-pair", action="store_true", help="capture both paths concurrently"
    )
    parser.add_argument("--seconds", type=float, default=5.0)
    args = parser.parse_args()
    if args.capture_pair:
        asyncio.run(capture_pair(args.seconds, Path(".local/debug")))
    else:
        asyncio.run(monitor(args.source, args.wav))


if __name__ == "__main__":
    main()
