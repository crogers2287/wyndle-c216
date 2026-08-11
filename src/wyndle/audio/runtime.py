"""Continuous, hardware-agnostic voice runtime orchestration.

The runtime consumes timestamped 16-bit mono PCM frames. Camera/FFmpeg adapters,
models, and speakers live outside this module and are injected through protocols,
which keeps orchestration deterministic and testable without physical hardware.
"""

from __future__ import annotations

from collections.abc import AsyncIterable, AsyncIterator, Callable, Sequence
from dataclasses import dataclass
from typing import Protocol, TypeVar

from wyndle.agent.context import ContextKind
from wyndle.agent.session import ConversationSession
from wyndle.agent.state_machine import AgentState, AgentStateMachine


@dataclass(frozen=True, slots=True)
class PCMFrame:
    data: bytes
    captured_at: float


@dataclass(frozen=True, slots=True)
class Utterance:
    pcm: bytes
    sample_rate: int
    started_at: float
    ended_at: float


class WakeDetector(Protocol):
    def detect(self, frame: PCMFrame) -> bool: ...


class VoiceActivityDetector(Protocol):
    def is_speech(self, frame: PCMFrame) -> bool: ...


class SpeechToText(Protocol):
    async def transcribe(self, utterance: Utterance) -> str: ...


class UtteranceRouter(Protocol):
    async def route(self, transcript: str, context: Sequence[dict[str, str]]) -> str: ...


Audio = TypeVar("Audio")


class TextToSpeech(Protocol[Audio]):
    async def synthesize(self, text: str) -> Audio: ...


class AudioOutput(Protocol[Audio]):
    async def play(self, audio: Audio) -> None: ...


@dataclass(frozen=True, slots=True)
class VoiceRuntimeConfig:
    sample_rate: int = 16_000
    max_utterance_seconds: float = 8.0
    leading_silence_seconds: float = 2.0
    trailing_silence_seconds: float = 0.6
    echo_cooldown_seconds: float = 0.35
    backchannel: str | None = "Yes?"

    def __post_init__(self) -> None:
        if self.sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        if self.max_utterance_seconds <= 0:
            raise ValueError("max_utterance_seconds must be positive")
        if self.leading_silence_seconds < 0 or self.trailing_silence_seconds < 0:
            raise ValueError("silence durations must not be negative")
        if self.echo_cooldown_seconds < 0:
            raise ValueError("echo_cooldown_seconds must not be negative")


class EchoGuard:
    """Rejects frames captured while TTS was active or in its cooldown window."""

    def __init__(self, cooldown_seconds: float, *, monotonic: Callable[[], float]) -> None:
        self.cooldown_seconds = cooldown_seconds
        self._monotonic = monotonic
        self._blocked_from: float | None = None
        self._blocked_until: float | None = None

    def output_started(self) -> None:
        self._blocked_from = self._monotonic()
        self._blocked_until = None

    def output_finished(self) -> None:
        if self._blocked_from is None:
            return
        self._blocked_until = self._monotonic() + self.cooldown_seconds

    def blocks(self, frame: PCMFrame) -> bool:
        if self._blocked_from is None or frame.captured_at < self._blocked_from:
            return False
        return self._blocked_until is None or frame.captured_at <= self._blocked_until


class VoiceRuntime:
    """Owns the continuous wake/listen/transcribe/route/speak lifecycle."""

    def __init__(
        self,
        *,
        pcm_source: AsyncIterable[PCMFrame],
        wake_detector: WakeDetector,
        stt: SpeechToText,
        router: UtteranceRouter,
        tts: TextToSpeech[Audio],
        audio_output: AudioOutput[Audio],
        session: ConversationSession,
        state: AgentStateMachine,
        monotonic: Callable[[], float],
        vad: VoiceActivityDetector | None = None,
        config: VoiceRuntimeConfig | None = None,
    ) -> None:
        self.pcm_source = pcm_source
        self.wake_detector = wake_detector
        self.vad = vad
        self.stt = stt
        self.router = router
        self.tts = tts
        self.audio_output = audio_output
        self.session = session
        self.state = state
        self.monotonic = monotonic
        self.config = config or VoiceRuntimeConfig()
        self.echo_guard = EchoGuard(self.config.echo_cooldown_seconds, monotonic=monotonic)
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    async def run(self) -> None:
        """Run until stopped or the injected PCM source is exhausted."""
        frames = self.pcm_source.__aiter__()
        try:
            while not self._stop:
                frame = await anext(frames)
                if self.echo_guard.blocks(frame):
                    continue
                if self.session.expire_if_needed():
                    self._to_idle("conversation session expired")

                if not self.session.is_open:
                    if not self.wake_detector.detect(frame):
                        continue
                    self.session.open()
                    self.state.transition(AgentState.WAKE_DETECTED, reason="wake word detected")
                    if self.config.backchannel:
                        await self._speak(self.config.backchannel, backchannel=True)
                    else:
                        self.state.transition(AgentState.LISTENING, reason="capture wake utterance")
                    utterance = await self._capture(frames)
                else:
                    # An open session permits hands-free follow-ups. With VAD, wait for
                    # actual speech; without it, the first frame begins fixed-duration capture.
                    if self.vad is not None and not self.vad.is_speech(frame):
                        continue
                    self.state.transition(AgentState.LISTENING, reason="follow-up speech detected")
                    utterance = await self._capture(frames, first=frame)

                if utterance is None:
                    self.state.transition(
                        AgentState.CONVERSATION_OPEN,
                        reason="no speech before utterance timeout",
                    )
                    continue
                await self._handle(utterance)
        except StopAsyncIteration:
            return
        except Exception:
            if self.state.can_transition_to(AgentState.DEGRADED):
                self.state.transition(AgentState.DEGRADED, reason="voice runtime dependency failed")
            raise

    async def _capture(
        self, frames: AsyncIterator[PCMFrame], *, first: PCMFrame | None = None
    ) -> Utterance | None:
        accepted: list[PCMFrame] = []
        first_seen = first
        speech_seen = False
        silence_started: float | None = None

        while not self._stop:
            frame = first_seen or await anext(frames)
            first_seen = None
            if self.echo_guard.blocks(frame):
                continue
            if not accepted:
                capture_started = frame.captured_at
            accepted.append(frame)
            speech = self.vad.is_speech(frame) if self.vad is not None else True
            if speech:
                speech_seen = True
                silence_started = None
            elif speech_seen and silence_started is None:
                silence_started = frame.captured_at

            elapsed = frame.captured_at - capture_started
            if not speech_seen and elapsed >= self.config.leading_silence_seconds:
                return None
            if elapsed >= self.config.max_utterance_seconds:
                break
            if (
                speech_seen
                and silence_started is not None
                and frame.captured_at - silence_started >= self.config.trailing_silence_seconds
            ):
                break

        if not speech_seen:
            return None
        speech_frames = accepted if self.vad is None else [f for f in accepted if speech_seen]
        return Utterance(
            pcm=b"".join(frame.data for frame in speech_frames),
            sample_rate=self.config.sample_rate,
            started_at=accepted[0].captured_at,
            ended_at=accepted[-1].captured_at,
        )

    async def _handle(self, utterance: Utterance) -> None:
        self.state.transition(AgentState.THINKING, reason="utterance captured")
        transcript = (await self.stt.transcribe(utterance)).strip()
        if not transcript:
            self.state.transition(AgentState.CONVERSATION_OPEN, reason="empty transcription")
            return
        self.session.context.add(ContextKind.USER_UTTERANCE, transcript)
        reply = (await self.router.route(transcript, self.session.context.prompt_items())).strip()
        if reply:
            self.session.context.add(ContextKind.AGENT_REPLY, reply)
            await self._speak(reply)
        else:
            self.state.transition(AgentState.CONVERSATION_OPEN, reason="router returned no speech")
        self.session.mark_meaningful_exchange()

    async def _speak(self, text: str, *, backchannel: bool = False) -> None:
        self.state.transition(AgentState.SPEAKING, reason="backchannel" if backchannel else "reply")
        self.echo_guard.output_started()
        try:
            audio = await self.tts.synthesize(text)
            await self.audio_output.play(audio)
        finally:
            self.echo_guard.output_finished()
        target = AgentState.LISTENING if backchannel else AgentState.CONVERSATION_OPEN
        self.state.transition(target, reason="speech output complete")

    def _to_idle(self, reason: str) -> None:
        if self.state.state is AgentState.IDLE_WATCHING:
            return
        if self.state.can_transition_to(AgentState.IDLE_WATCHING):
            self.state.transition(AgentState.IDLE_WATCHING, reason=reason)
