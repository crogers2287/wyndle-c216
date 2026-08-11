from __future__ import annotations

import tempfile
from pathlib import Path as P
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from wyndle.camera.go2rtc import Go2RTCBackchannel


@pytest.mark.asyncio
async def test_status_returns_json():
    mock_response = MagicMock()
    mock_response.json.return_value = {"ok": True}
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("wyndle.camera.go2rtc.httpx.AsyncClient", return_value=mock_client):
        ch = Go2RTCBackchannel("http://host", "stream1")
        data = await ch.status()
    assert data == {"ok": True}
    mock_client.get.assert_called_once()
    args, kwargs = mock_client.get.call_args
    assert "api/streams" in args[0]


@pytest.mark.asyncio
async def test_play_file_validates_path():
    ch = Go2RTCBackchannel("http://host", "stream1")
    with pytest.raises(ValueError):
        await ch.play_file(P("relative.wav"))
    tmp = P("/tmp/does_not_exist.wav")
    with pytest.raises(ValueError):
        await ch.play_file(tmp)


@pytest.mark.asyncio
async def test_play_file_posts_and_stops():
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("wyndle.camera.go2rtc.httpx.AsyncClient", return_value=mock_client),
        patch("wyndle.camera.go2rtc.asyncio.sleep", new_callable=AsyncMock) as sleep_mock,
    ):
        ch = Go2RTCBackchannel("http://host", "stream1")
        with tempfile.NamedTemporaryFile(delete=False) as tf:
            tf_path = P(tf.name)
        try:
            await ch.play_file(tf_path, duration=2.5)
        finally:
            tf_path.unlink(missing_ok=True)

    assert mock_client.post.call_count == 2
    first_params = mock_client.post.call_args_list[0][1]["params"]
    assert first_params["dst"] == "stream1"
    assert "ffmpeg:" in first_params["src"]
    sleep_mock.assert_awaited_once_with(2.5)


@pytest.mark.asyncio
async def test_stop_posts_empty_src():
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("wyndle.camera.go2rtc.httpx.AsyncClient", return_value=mock_client):
        ch = Go2RTCBackchannel("http://host", "stream1")
        await ch.stop()

    params = mock_client.post.call_args[1]["params"]
    assert params == {"dst": "stream1", "src": ""}
