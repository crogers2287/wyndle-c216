from __future__ import annotations

from collections import deque
from pathlib import Path

import pytest

from wyndle.audio.wake import KeywordSpotterConfig, StreamingKeywordSpotter


class FakeStream:
    def __init__(self) -> None:
        self.chunks: list[tuple[int, tuple[float, ...]]] = []
        self.finished = False
        self.ready = 0

    def accept_waveform(self, sample_rate: int, samples: object) -> None:
        chunk = tuple(samples)  # type: ignore[arg-type]
        self.chunks.append((sample_rate, chunk))
        self.ready += 1

    def input_finished(self) -> None:
        self.finished = True
        self.ready += 1


class FakeEngine:
    def __init__(self, results: list[str]) -> None:
        self.results = deque(results)
        self.streams: list[FakeStream] = []
        self.decoded = 0
        self.resets = 0

    def create_stream(self) -> FakeStream:
        stream = FakeStream()
        self.streams.append(stream)
        return stream

    def is_ready(self, stream: FakeStream) -> bool:
        return stream.ready > 0

    def decode_stream(self, stream: FakeStream) -> None:
        stream.ready -= 1
        self.decoded += 1

    def get_result(self, stream: FakeStream) -> str:
        return self.results.popleft() if self.results else ""

    def reset_stream(self, stream: FakeStream) -> None:
        self.resets += 1


def config(tmp_path: Path) -> KeywordSpotterConfig:
    paths = [tmp_path / name for name in ("tokens", "encoder", "decoder", "joiner", "keywords")]
    for path in paths:
        path.touch()
    return KeywordSpotterConfig(*paths)


def test_accepts_source_independent_float_chunks_and_reports_keyword(tmp_path: Path) -> None:
    engine = FakeEngine(["Hey Wyndle"])
    spotter = StreamingKeywordSpotter(config(tmp_path), engine=engine)

    found = spotter.accept_pcm(sample / 10 for sample in range(4))

    assert [d.phrase for d in found] == ["Hey Wyndle"]
    assert engine.streams[0].chunks == [(16_000, (0.0, 0.1, 0.2, 0.3))]
    assert engine.resets == 1


def test_empty_chunk_does_not_invoke_engine(tmp_path: Path) -> None:
    engine = FakeEngine([])
    spotter = StreamingKeywordSpotter(config(tmp_path), engine=engine)

    assert spotter.accept_pcm([]) == ()
    assert engine.decoded == 0
    assert engine.streams[0].chunks == []


def test_finish_flushes_and_prevents_more_input_until_reset(tmp_path: Path) -> None:
    engine = FakeEngine(["Wyndle"])
    spotter = StreamingKeywordSpotter(config(tmp_path), engine=engine)

    assert [d.phrase for d in spotter.finish()] == ["Wyndle"]
    assert engine.streams[0].finished is True
    assert spotter.finish() == ()
    with pytest.raises(RuntimeError, match="after finish"):
        spotter.accept_pcm([0.0])

    spotter.reset()
    assert spotter.accept_pcm([0.5]) == ()
    assert len(engine.streams) == 2


def test_factory_receives_model_configuration(tmp_path: Path) -> None:
    cfg = config(tmp_path)
    engine = FakeEngine([])
    received: list[KeywordSpotterConfig] = []

    spotter = StreamingKeywordSpotter(
        cfg, engine_factory=lambda value: received.append(value) or engine
    )

    assert received == [cfg]
    assert spotter.accept_pcm([0.0]) == ()


def test_config_validation_reports_missing_files(tmp_path: Path) -> None:
    cfg = KeywordSpotterConfig(*(tmp_path / name for name in "abcde"))
    with pytest.raises(FileNotFoundError, match="keyword spotter"):
        cfg.validate()
