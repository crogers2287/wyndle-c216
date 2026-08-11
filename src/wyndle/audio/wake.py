"""Streaming, microphone-agnostic keyword spotting with sherpa-onnx."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class KeywordStream(Protocol):
    """The small part of a sherpa-onnx OnlineStream used by this adapter."""

    def accept_waveform(self, sample_rate: int, samples: Sequence[float]) -> None: ...

    def input_finished(self) -> None: ...


class KeywordEngine(Protocol):
    """Interface implemented by sherpa-onnx and test doubles."""

    def create_stream(self) -> KeywordStream: ...

    def is_ready(self, stream: KeywordStream) -> bool: ...

    def decode_stream(self, stream: KeywordStream) -> None: ...

    def get_result(self, stream: KeywordStream) -> str: ...

    def reset_stream(self, stream: KeywordStream) -> None: ...


@dataclass(frozen=True, slots=True)
class KeywordSpotterConfig:
    """Model and decoder configuration for a streaming transducer KWS model."""

    tokens: Path
    encoder: Path
    decoder: Path
    joiner: Path
    keywords: Path
    sample_rate: int = 16_000
    num_threads: int = 2
    provider: str = "cpu"
    max_active_paths: int = 4
    keywords_score: float = 1.0
    keywords_threshold: float = 0.25
    num_trailing_blanks: int = 1

    def validate(self) -> None:
        missing = [path for path in self.model_paths if not path.is_file()]
        if missing:
            joined = ", ".join(str(path) for path in missing)
            raise FileNotFoundError(f"Missing keyword spotter file(s): {joined}")
        if self.sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        if self.num_threads <= 0:
            raise ValueError("num_threads must be positive")

    @property
    def model_paths(self) -> tuple[Path, ...]:
        return (self.tokens, self.encoder, self.decoder, self.joiner, self.keywords)


@dataclass(frozen=True, slots=True)
class WakeDetection:
    """A keyword emitted after one incremental decode step."""

    phrase: str


EngineFactory = Callable[[KeywordSpotterConfig], KeywordEngine]


def create_sherpa_engine(config: KeywordSpotterConfig) -> KeywordEngine:
    """Construct sherpa lazily, keeping importing/testing free of native-library needs."""
    config.validate()
    try:
        import sherpa_onnx
    except ImportError:  # pragma: no cover - host native runtime
        # Some Linux wheels require the adjacent versioned ONNX Runtime library
        # to be loaded globally before the sherpa extension is imported.
        try:
            import ctypes
            import importlib
            import site
            import sys

            candidates = [
                Path(base) / "onnxruntime/capi/libonnxruntime.so.1.27.0"
                for base in site.getsitepackages()
            ]
            library = next(path for path in candidates if path.is_file())
            ctypes.CDLL(str(library), mode=ctypes.RTLD_GLOBAL)
            for module_name in tuple(sys.modules):
                if module_name == "sherpa_onnx" or module_name.startswith("sherpa_onnx."):
                    sys.modules.pop(module_name, None)
            sherpa_onnx = importlib.import_module("sherpa_onnx")
        except Exception as exc:
            raise RuntimeError("sherpa-onnx native runtime is not available") from exc

    return sherpa_onnx.KeywordSpotter(
        tokens=str(config.tokens),
        encoder=str(config.encoder),
        decoder=str(config.decoder),
        joiner=str(config.joiner),
        keywords_file=str(config.keywords),
        sample_rate=config.sample_rate,
        num_threads=config.num_threads,
        provider=config.provider,
        max_active_paths=config.max_active_paths,
        keywords_score=config.keywords_score,
        keywords_threshold=config.keywords_threshold,
        num_trailing_blanks=config.num_trailing_blanks,
    )


class StreamingKeywordSpotter:
    """Consume arbitrary float PCM chunks and report locally detected keywords.

    The caller owns capture, decoding, downmixing, and resampling. Chunks may have any
    length, but must contain mono float PCM at ``config.sample_rate``.
    """

    def __init__(
        self,
        config: KeywordSpotterConfig,
        *,
        engine: KeywordEngine | None = None,
        engine_factory: EngineFactory = create_sherpa_engine,
    ) -> None:
        self.config = config
        self._engine = engine if engine is not None else engine_factory(config)
        self._stream = self._engine.create_stream()
        self._finished = False

    def accept_pcm(self, samples: Iterable[float]) -> tuple[WakeDetection, ...]:
        """Feed one mono float PCM chunk and decode all currently available frames."""
        if self._finished:
            raise RuntimeError("cannot accept PCM after finish(); call reset() first")
        chunk = samples if isinstance(samples, Sequence) else tuple(samples)
        if len(chunk) == 0:  # type: ignore[arg-type]
            return ()
        self._stream.accept_waveform(self.config.sample_rate, chunk)  # type: ignore[arg-type]
        return self._drain()

    def finish(self) -> tuple[WakeDetection, ...]:
        """Mark end-of-input and decode frames made ready by final padding/buffering."""
        if self._finished:
            return ()
        self._finished = True
        self._stream.input_finished()
        return self._drain()

    def reset(self) -> None:
        """Discard streaming state and begin accepting a new audio sequence."""
        self._stream = self._engine.create_stream()
        self._finished = False

    def _drain(self) -> tuple[WakeDetection, ...]:
        detections: list[WakeDetection] = []
        while self._engine.is_ready(self._stream):
            self._engine.decode_stream(self._stream)
            phrase = self._engine.get_result(self._stream).strip()
            if phrase:
                detections.append(WakeDetection(phrase=phrase.replace("_", " ")))
                # sherpa requires reset immediately after a keyword; this also prevents
                # the same accumulated audio from producing duplicate detections.
                self._engine.reset_stream(self._stream)
        return tuple(detections)
