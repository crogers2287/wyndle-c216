import pytest

from wyndle.agent.session import ConversationSession
from wyndle.agent.state_machine import AgentState, AgentStateMachine
from wyndle.audio.runtime import PCMFrame, Utterance, VoiceRuntime, VoiceRuntimeConfig


class Clock:
    value = 0.0

    def __call__(self):
        return self.value


class Source:
    def __init__(self, frames):
        self.frames = frames

    def __aiter__(self):
        return self._items().__aiter__()

    async def _items(self):
        for frame in self.frames:
            yield frame


class Wake:
    def detect(self, frame):
        return frame.data == b"wake"


class VAD:
    def is_speech(self, frame):
        return frame.data.startswith(b"s")


class STT:
    def __init__(self):
        self.calls = []

    async def transcribe(self, utterance: Utterance):
        self.calls.append(utterance)
        return "hello"


class Router:
    def __init__(self):
        self.calls = []

    async def route(self, transcript, context):
        self.calls.append((transcript, context))
        return "hi there"


class TTS:
    def __init__(self):
        self.calls = []

    async def synthesize(self, text):
        self.calls.append(text)
        return text.encode()


class Output:
    def __init__(self):
        self.calls = []

    async def play(self, audio):
        self.calls.append(audio)


def runtime(frames, *, backchannel=None, vad=None, cooldown=0):
    clock = Clock()
    deps = STT(), Router(), TTS(), Output()
    machine = AgentStateMachine(initial=AgentState.IDLE_WATCHING)
    item = VoiceRuntime(
        pcm_source=Source(frames),
        wake_detector=Wake(),
        vad=vad,
        stt=deps[0],
        router=deps[1],
        tts=deps[2],
        audio_output=deps[3],
        session=ConversationSession(monotonic=clock),
        state=machine,
        monotonic=clock,
        config=VoiceRuntimeConfig(
            max_utterance_seconds=1,
            trailing_silence_seconds=0.2,
            backchannel=backchannel,
            echo_cooldown_seconds=cooldown,
        ),
    )
    return item, deps


@pytest.mark.asyncio
async def test_wake_to_vad_utterance_routes_and_speaks_with_session_context():
    frames = [
        PCMFrame(b"wake", 0),
        PCMFrame(b"speech", 0.1),
        PCMFrame(b"quiet", 0.2),
        PCMFrame(b"quiet", 0.4),
    ]
    item, (stt, router, tts, output) = runtime(frames, vad=VAD())
    await item.run()
    assert stt.calls[0].pcm == b"speechquietquiet"
    assert router.calls[0][0] == "hello"
    assert [x["content"] for x in router.calls[0][1]] == ["hello"]
    assert tts.calls == ["hi there"]
    assert output.calls == [b"hi there"]
    assert item.session.is_open
    assert item.state.state is AgentState.CONVERSATION_OPEN


@pytest.mark.asyncio
async def test_fixed_duration_capture_without_vad_and_backchannel():
    frames = [PCMFrame(b"wake", 0), PCMFrame(b"a", 0.1), PCMFrame(b"b", 1.1)]
    item, (stt, _, tts, _) = runtime(frames, backchannel="Ready")
    await item.run()
    assert stt.calls[0].pcm == b"ab"
    assert tts.calls == ["Ready", "hi there"]


@pytest.mark.asyncio
async def test_output_frames_are_echo_guarded_not_wake_detected():
    # The clock is at zero during synthetic output, so captured_at=.1 is inside cooldown.
    frames = [
        PCMFrame(b"wake", 0),
        PCMFrame(b"speech", 0.6),
        PCMFrame(b"quiet", 0.8),
        PCMFrame(b"quiet", 1.1),
        PCMFrame(b"wake", 0.1),
    ]
    item, (stt, _, _, _) = runtime(frames, backchannel="Ready", vad=VAD(), cooldown=0.5)
    await item.run()
    assert len(stt.calls) == 1
    assert item.session.is_open


@pytest.mark.asyncio
async def test_dependency_failure_marks_runtime_degraded():
    class BadSTT(STT):
        async def transcribe(self, utterance):
            raise RuntimeError("offline")

    frames = [PCMFrame(b"wake", 0), PCMFrame(b"x", 0.1), PCMFrame(b"y", 1.1)]
    item, _ = runtime(frames)
    item.stt = BadSTT()
    with pytest.raises(RuntimeError, match="offline"):
        await item.run()
    assert item.state.state is AgentState.DEGRADED
