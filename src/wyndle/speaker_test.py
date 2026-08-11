"""Independent Piper and C216 speaker-path diagnostic."""

from __future__ import annotations

import argparse
import asyncio
import wave
from pathlib import Path

from wyndle.audio.tts import PiperTTS
from wyndle.camera.go2rtc import Go2RTCBackchannel
from wyndle.config import Settings

PHRASE = "Hello. This is Wyndle testing the camera speaker."


async def run(*, play: bool) -> None:
    settings = Settings()
    directory = Path(".local/debug")
    directory.mkdir(parents=True, exist_ok=True)
    original = (directory / "speaker-test-piper.wav").resolve()
    pcma = (directory / "speaker-test-pcma.alaw").resolve()
    await PiperTTS(Path(settings.piper_executable), Path(settings.piper_model)).synthesize(
        PHRASE, original
    )
    with wave.open(str(original), "rb") as source:
        channels = source.getnchannels()
        sample_rate = source.getframerate()
        sample_width = source.getsampwidth()
        frames = source.getnframes()
        duration = frames / sample_rate
    print(
        f"PIPER_WAV={original} rate={sample_rate} channels={channels} "
        f"sample_width_bytes={sample_width} format=PCM duration={duration:.3f}s",
        flush=True,
    )
    process = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(original),
        "-ar",
        "8000",
        "-ac",
        "1",
        "-c:a",
        "pcm_alaw",
        "-f",
        "alaw",
        "-y",
        str(pcma),
    )
    if await process.wait():
        raise RuntimeError("failed to create PCMA/8000 debug artifact")
    print(f"PCMA_8000_ARTIFACT={pcma} bytes={pcma.stat().st_size}", flush=True)
    if not play:
        print("C216_PLAYBACK=SKIPPED (rerun with --play after listening to the local WAV)")
        return
    player = Go2RTCBackchannel(settings.go2rtc_url, settings.go2rtc_stream_name)
    print("C216_SUBMISSION=START", flush=True)
    try:
        await player.play_file(original)
        await asyncio.sleep(duration + 0.15)
    finally:
        await player.stop()
    print("C216_SUBMISSION=COMPLETE audible_result=UNCONFIRMED", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Test Piper and C216 output independently of AI")
    parser.add_argument(
        "--play", action="store_true", help="submit to the physical C216 after local WAV review"
    )
    args = parser.parse_args()
    asyncio.run(run(play=args.play))


if __name__ == "__main__":
    main()
