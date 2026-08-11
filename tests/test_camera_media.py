from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from wyndle.camera.media import MediaError, capture_audio_wav, capture_jpeg


class FakeProc:
    def __init__(self, returncode=0, stdout=b"", stderr=b""):
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr

    async def communicate(self):
        return self._stdout, self._stderr

    async def wait(self):
        return self.returncode

    def kill(self):
        pass


@pytest.mark.asyncio
async def test_capture_jpeg_returns_stdout():
    fake = FakeProc(stdout=b"jpegbytes")
    with patch("wyndle.camera.media.asyncio.create_subprocess_exec", return_value=fake):
        data = await capture_jpeg("rtsp://example/stream")
    assert data == b"jpegbytes"


@pytest.mark.asyncio
async def test_capture_jpeg_raises_on_error():
    fake = FakeProc(returncode=1, stderr=b"ffmpeg error")
    with (
        patch("wyndle.camera.media.asyncio.create_subprocess_exec", return_value=fake),
        pytest.raises(MediaError, match="ffmpeg failed"),
    ):
        await capture_jpeg("rtsp://example/stream")


@pytest.mark.asyncio
async def test_capture_jpeg_timeout():
    async def boom():
        raise TimeoutError

    fake = FakeProc()
    fake.communicate = boom  # type: ignore[assignment]
    with (
        patch("wyndle.camera.media.asyncio.create_subprocess_exec", return_value=fake),
        pytest.raises(MediaError, match="timed out"),
    ):
        await capture_jpeg("rtsp://example/stream", timeout=0.001)


@pytest.mark.asyncio
async def test_capture_audio_wav_valid_range():
    fake = FakeProc(stdout=b"wavbytes")
    with patch("wyndle.camera.media.asyncio.create_subprocess_exec", return_value=fake) as m:
        data = await capture_audio_wav("rtsp://example/stream", seconds=5)
    assert data == b"wavbytes"
    # ensure ffmpeg args include -t 5
    args = m.call_args[0]
    assert "-t" in args and "5" in args


@pytest.mark.parametrize("seconds", [0.1, 30.1])
def test_capture_audio_wav_invalid_seconds(seconds):
    with pytest.raises(ValueError):
        asyncio.run(capture_audio_wav("rtsp://x", seconds=seconds))
