from unittest.mock import AsyncMock, patch

import pytest

from wyndle.audio.output import condition_c216_audio


@pytest.mark.asyncio
async def test_condition_c216_audio_adds_padding_and_8k_pcm(tmp_path):
    source = tmp_path / "source.wav"
    source.write_bytes(b"wav")
    output = tmp_path / "conditioned.wav"
    process = AsyncMock()
    process.returncode = 0
    process.communicate.return_value = (b"", b"")
    with patch(
        "wyndle.audio.output.asyncio.create_subprocess_exec", return_value=process
    ) as create:
        assert await condition_c216_audio(source, output) == output
    args = create.call_args.args
    graph = args[args.index("-af") + 1]
    assert "volume=0.5" in graph
    assert "adelay=2000:all=1" in graph
    assert "apad=pad_dur=1.0" in graph
    assert args[args.index("-ar") + 1] == "8000"
    assert args[args.index("-ac") + 1] == "1"
    assert args[args.index("-c:a") + 1] == "pcm_s16le"


@pytest.mark.asyncio
async def test_condition_requires_existing_source(tmp_path):
    with pytest.raises(ValueError):
        await condition_c216_audio(tmp_path / "missing.wav", tmp_path / "out.wav")
