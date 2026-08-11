"""Physical C216 voice runtime wiring for the local development host."""

from __future__ import annotations

import argparse
import asyncio
import math
import os
import struct
import sys
import tempfile
import time
import wave
from collections.abc import AsyncIterator
from pathlib import Path

from onvif import ONVIFCamera

from wyndle.agent.session import ConversationSession
from wyndle.agent.state_machine import AgentState, AgentStateMachine
from wyndle.agent.tools import PTZTools
from wyndle.audio.runtime import PCMFrame, Utterance, VoiceRuntime, VoiceRuntimeConfig
from wyndle.audio.stt import FasterWhisperSTT
from wyndle.audio.tts import PiperTTS
from wyndle.camera.go2rtc import Go2RTCBackchannel
from wyndle.camera.media import capture_jpeg
from wyndle.camera.ptz import ONVIFPTZAdapter
from wyndle.config import Settings
from wyndle.providers import OpenAICompatibleLanguageProvider, OpenAICompatibleVisionProvider
from wyndle.vision import VisualQuestionRouter


class FFmpegPCMSource:
    """Continuously decode the camera microphone to 16 kHz mono signed PCM."""

    def __init__(self, url: str, *, chunk_ms: int = 100) -> None:
        self.url = url
        self.chunk_bytes = 16_000 * 2 * chunk_ms // 1000
        self._process: asyncio.subprocess.Process | None = None

    def __aiter__(self) -> AsyncIterator[PCMFrame]:
        return self._frames()

    async def _frames(self) -> AsyncIterator[PCMFrame]:
        self._process = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-rtsp_transport",
            "tcp",
            "-i",
            self.url,
            "-vn",
            "-ar",
            "16000",
            "-ac",
            "1",
            "-f",
            "s16le",
            "pipe:1",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        assert self._process.stdout is not None
        try:
            while True:
                data = await self._process.stdout.readexactly(self.chunk_bytes)
                yield PCMFrame(data=data, captured_at=time.monotonic())
        except asyncio.IncompleteReadError as exc:
            if self._process.returncode not in (None, 0):
                raise RuntimeError("camera microphone stream ended unexpectedly") from exc
        finally:
            if self._process.returncode is None:
                self._process.terminate()
                await self._process.wait()


class EnergyVAD:
    def __init__(self, threshold: float = 0.012) -> None:
        self.threshold = threshold

    def is_speech(self, frame: PCMFrame) -> bool:
        count = len(frame.data) // 2
        if not count:
            return False
        values = struct.unpack(f"<{count}h", frame.data)
        rms = math.sqrt(sum(value * value for value in values) / count) / 32768.0
        return rms >= self.threshold


class EnergyWakeDetector:
    """Local temporary wake fallback while the custom name model is tuned."""

    def __init__(self, vad: EnergyVAD, consecutive_chunks: int = 3) -> None:
        self.vad = vad
        self.consecutive_chunks = consecutive_chunks
        self._count = 0

    def detect(self, frame: PCMFrame) -> bool:
        self._count = self._count + 1 if self.vad.is_speech(frame) else 0
        if self._count >= self.consecutive_chunks:
            self._count = 0
            print("[WAKE] voiced local wake accepted", flush=True)
            return True
        return False


class WhisperRuntimeAdapter:
    def __init__(self, stt: FasterWhisperSTT) -> None:
        self.stt = stt

    async def transcribe(self, utterance: Utterance) -> str:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as file:
            path = Path(file.name)
        try:
            with wave.open(str(path), "wb") as output:
                output.setnchannels(1)
                output.setsampwidth(2)
                output.setframerate(utterance.sample_rate)
                output.writeframes(utterance.pcm)
            return await self.stt.transcribe(path)
        finally:
            path.unlink(missing_ok=True)


class LocalRouter:
    def __init__(self, router: VisualQuestionRouter, rtsp_url: str, ptz: PTZTools) -> None:
        self.router = router
        self.rtsp_url = rtsp_url
        self.ptz = ptz

    async def route(self, transcript: str, context: list[dict[str, str]]) -> str:
        normalized = transcript.lower().strip(" .!?")
        commands = {
            "look left": self.ptz.look_left,
            "look right": self.ptz.look_right,
            "look up": self.ptz.look_up,
            "look down": self.ptz.look_down,
            "stop looking": self.ptz.stop_looking,
        }
        for phrase, command in commands.items():
            if phrase in normalized:
                await command()
                return ""
        frame = (
            await capture_jpeg(self.rtsp_url)
            if self.router.route(transcript).value == "vision"
            else None
        )
        history = [
            {
                "role": "user" if item["kind"] == "user_utterance" else "assistant",
                "content": item["content"],
            }
            for item in context
            if item["kind"] in {"user_utterance", "agent_reply"}
        ]
        answer = await self.router.answer(transcript, frame=frame, history=history)
        return answer.text


class CameraSpeech:
    def __init__(self, tts: PiperTTS, player: Go2RTCBackchannel, directory: Path) -> None:
        self.tts = tts
        self.player = player
        self.directory = directory

    async def synthesize(self, text: str) -> Path:
        path = (self.directory / "live-response.wav").resolve()
        return await self.tts.synthesize(text, path)

    async def play(self, audio: Path) -> None:
        with wave.open(str(audio), "rb") as wav:
            duration = wav.getnframes() / wav.getframerate()
        await self.player.play_file(audio)
        await asyncio.sleep(duration + 0.15)
        await self.player.stop()


def build_ptz(settings: Settings) -> PTZTools:
    camera = ONVIFCamera(
        settings.tapo_ip,
        settings.tapo_onvif_port,
        settings.tapo_username,
        settings.camera_password(),
    )
    profile = camera.create_media_service().GetProfiles()[0]
    return PTZTools(ONVIFPTZAdapter(camera.create_ptz_service(), profile.token))


async def run() -> None:
    settings = Settings()
    stream = f"rtsp://127.0.0.1:8554/{settings.go2rtc_stream_name}"
    language = OpenAICompatibleLanguageProvider(
        base_url=settings.llm_base_url, model=settings.llm_model, timeout=120
    )
    vision = OpenAICompatibleVisionProvider(
        base_url=settings.vision_base_url, model=settings.vision_model, timeout=120
    )
    piper = PiperTTS(Path(settings.piper_executable), Path(settings.piper_model))
    player = Go2RTCBackchannel(settings.go2rtc_url, settings.go2rtc_stream_name)
    state = AgentStateMachine(initial=AgentState.IDLE_WATCHING)
    vad = EnergyVAD()
    runtime = VoiceRuntime(
        pcm_source=FFmpegPCMSource(stream),
        wake_detector=EnergyWakeDetector(vad),
        vad=vad,
        stt=WhisperRuntimeAdapter(
            FasterWhisperSTT(Path(settings.whisper_python), Path(settings.whisper_model))
        ),
        router=LocalRouter(VisualQuestionRouter(language, vision), stream, build_ptz(settings)),
        tts=CameraSpeech(piper, player, Path(".local")),
        audio_output=CameraSpeech(piper, player, Path(".local")),
        session=ConversationSession(settings.conversation_timeout_seconds),
        state=state,
        monotonic=time.monotonic,
        config=VoiceRuntimeConfig(backchannel="Yeah?"),
    )
    print("Wyndle is listening locally. Say 'Wyndle'. Ctrl-C to stop.")
    await runtime.run()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the physical Wyndle voice loop")
    parser.parse_args()
    if "WYNDLE_NATIVE_REEXEC" not in os.environ:
        import onnxruntime

        library_dir = str(Path(onnxruntime.__file__).parent / "capi")
        environment = os.environ.copy()
        environment["LD_LIBRARY_PATH"] = library_dir + ":" + environment.get("LD_LIBRARY_PATH", "")
        environment["WYNDLE_NATIVE_REEXEC"] = "1"
        os.execvpe(sys.executable, [sys.executable, "-m", "wyndle.live"], environment)
    asyncio.run(run())


if __name__ == "__main__":
    main()
