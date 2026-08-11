from __future__ import annotations

from pathlib import Path as P
from unittest.mock import patch

import pytest

from wyndle.audio.tts import PiperTTS


class FakeProc:
    def __init__(self, returncode=0, stderr=b""):
        self.returncode = returncode
        self._stderr = stderr

    async def communicate(self, input=None):
        return b"", self._stderr


@pytest.mark.asyncio
async def test_synthesize_creates_parent_and_runs():
    exe = P("/usr/bin/piper")
    model = P("/models/en.onnx")
    out = P("/tmp/out/speech.wav")
    proc = FakeProc()
    with patch("wyndle.audio.tts.asyncio.create_subprocess_exec", return_value=proc) as m:
        tts = PiperTTS(exe, model)
        result = await tts.synthesize("hello", out)
    assert result == out
    assert out.parent.exists()
    args = m.call_args[0]
    assert str(exe) in args and str(model) in args and str(out) in args


@pytest.mark.asyncio
async def test_synthesize_rejects_empty_text():
    tts = PiperTTS(P("/bin/piper"), P("/m.onnx"))
    with pytest.raises(ValueError):
        await tts.synthesize("   ", P("/tmp/out.wav"))


@pytest.mark.asyncio
async def test_synthesize_raises_on_failure():
    exe = P("/usr/bin/piper")
    model = P("/models/en.onnx")
    out = P("/tmp/out.wav")
    proc = FakeProc(returncode=1, stderr=b"model missing")
    with patch("wyndle.audio.tts.asyncio.create_subprocess_exec", return_value=proc):
        tts = PiperTTS(exe, model)
        with pytest.raises(RuntimeError, match="Piper failed"):
            await tts.synthesize("hi", out)
