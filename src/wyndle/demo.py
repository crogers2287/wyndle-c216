"""Developer end-to-end demo using the physical C216."""

from __future__ import annotations

import argparse
import asyncio
import time
from pathlib import Path

from wyndle.audio.tts import PiperTTS
from wyndle.camera.go2rtc import Go2RTCBackchannel
from wyndle.camera.media import capture_jpeg
from wyndle.config import Settings
from wyndle.providers import OpenAICompatibleLanguageProvider, OpenAICompatibleVisionProvider
from wyndle.vision import VisualQuestionRouter


async def run(question: str, speak: bool) -> str:
    settings = Settings()
    rtsp = f"rtsp://127.0.0.1:8554/{settings.go2rtc_stream_name}"
    language = OpenAICompatibleLanguageProvider(
        base_url=settings.llm_base_url, model=settings.llm_model, timeout=120
    )
    vision = OpenAICompatibleVisionProvider(
        base_url=settings.vision_base_url, model=settings.vision_model, timeout=120
    )
    router = VisualQuestionRouter(language, vision)
    frame = await capture_jpeg(rtsp) if router.route(question).value == "vision" else None
    started = time.monotonic()
    result = await router.answer(question, frame=frame)
    print(f"[{result.route.value} {time.monotonic() - started:.2f}s] {result.text}")
    if speak:
        output = Path(".local/tts-response.wav").resolve()
        tts = PiperTTS(Path(settings.piper_executable), Path(settings.piper_model))
        await tts.synthesize(result.text, output)
        player = Go2RTCBackchannel(settings.go2rtc_url, settings.go2rtc_stream_name)
        await player.play_file(output)
    return result.text


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("question", nargs="+", help="Question for Wyndle")
    parser.add_argument("--no-speak", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(" ".join(args.question), not args.no_speak))


if __name__ == "__main__":
    main()
