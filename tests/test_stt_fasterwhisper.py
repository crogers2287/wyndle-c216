from __future__ import annotations

import json
from pathlib import Path as P
from unittest.mock import patch

import pytest

from wyndle.audio.stt import FasterWhisperSTT


class FakeStdin:
    def __init__(self):
        self.writes = []

    def write(self, data):
        self.writes.append(data)

    async def drain(self):
        pass

    def close(self):
        pass


class FakeStdout:
    def __init__(self, lines):
        self.lines = list(lines)

    async def readline(self):
        return self.lines.pop(0) if self.lines else b""


class FakeProc:
    def __init__(self, lines):
        self.returncode = None
        self.stdin = FakeStdin()
        self.stdout = FakeStdout(lines)
        self.stderr = FakeStdout([])

    async def wait(self):
        self.returncode = 0
        return 0

    def terminate(self):
        self.returncode = -15


@pytest.mark.asyncio
async def test_two_transcriptions_load_one_persistent_worker():
    proc = FakeProc(
        [
            b'{"event":"ready","model_load_seconds":2.5}\n',
            b'{"id":1,"text":"hello","transcription_seconds":0.2}\n',
            b'{"id":2,"text":"world","transcription_seconds":0.1}\n',
        ]
    )
    with patch("wyndle.audio.stt.asyncio.create_subprocess_exec", return_value=proc) as create:
        stt = FasterWhisperSTT(P("/python"), P("/model"))
        assert await stt.transcribe(P("/one.wav")) == "hello"
        assert await stt.transcribe(P("/two.wav")) == "world"
    assert create.call_count == 1
    requests = [json.loads(item) for item in proc.stdin.writes]
    assert [item["id"] for item in requests] == [1, 2]
    assert [item["wav"] for item in requests] == ["/one.wav", "/two.wav"]


@pytest.mark.asyncio
async def test_worker_error_is_reported():
    proc = FakeProc(
        [
            b'{"event":"ready","model_load_seconds":1}\n',
            b'{"id":1,"error":"bad audio"}\n',
        ]
    )
    with patch("wyndle.audio.stt.asyncio.create_subprocess_exec", return_value=proc):
        stt = FasterWhisperSTT(P("/python"), P("/model"))
        with pytest.raises(RuntimeError, match="bad audio"):
            await stt.transcribe(P("/one.wav"))
