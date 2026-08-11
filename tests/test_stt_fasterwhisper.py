from __future__ import annotations

from pathlib import Path as P
from unittest.mock import patch

import pytest

from wyndle.audio.stt import FasterWhisperSTT


class FakeProc:
    def __init__(self, returncode=0, stdout=b"", stderr=b""):
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr

    async def communicate(self):
        return self._stdout, self._stderr


@pytest.mark.asyncio
async def test_transcribe_runs_python_and_returns_text():
    python = P("/usr/bin/python3")
    model = P("/models/whisper")
    wav = P("/tmp/audio.wav")
    proc = FakeProc(stdout=b"hello world\n")
    with patch("wyndle.audio.stt.asyncio.create_subprocess_exec", return_value=proc) as m:
        stt = FasterWhisperSTT(python, model)
        text = await stt.transcribe(wav)
    assert text == "hello world"
    args = m.call_args[0]
    assert str(python) in args
    code = args[2]  # -c code
    assert str(model) in code
    assert str(wav) in code


@pytest.mark.asyncio
async def test_transcribe_raises_on_error():
    python = P("/usr/bin/python3")
    model = P("/models/whisper")
    wav = P("/tmp/audio.wav")
    proc = FakeProc(returncode=1, stderr=b"import error")
    with patch("wyndle.audio.stt.asyncio.create_subprocess_exec", return_value=proc):
        stt = FasterWhisperSTT(python, model)
        with pytest.raises(RuntimeError, match="STT failed"):
            await stt.transcribe(wav)
