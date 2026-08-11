"""Persistent Faster-Whisper adapter isolated behind a dedicated Python environment."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path


class FasterWhisperSTT:
    """Keep one external Whisper model resident and serialize transcription requests."""

    def __init__(
        self,
        python: Path,
        model: Path,
        *,
        device: str = "cuda",
        device_index: int = 2,
        compute_type: str = "float16",
        startup_timeout: float = 120.0,
    ) -> None:
        self.python = python
        self.model = model
        self.device = device
        self.device_index = device_index
        self.compute_type = compute_type
        self.startup_timeout = startup_timeout
        self.model_load_seconds: float | None = None
        self._process: asyncio.subprocess.Process | None = None
        self._lock = asyncio.Lock()
        self._request_id = 0

    async def start(self) -> float:
        if self._process is not None and self._process.returncode is None:
            return self.model_load_seconds or 0.0
        worker = Path(__file__).with_name("whisper_worker.py")
        self._process = await asyncio.create_subprocess_exec(
            str(self.python),
            str(worker),
            "--model",
            str(self.model),
            "--device",
            self.device,
            "--device-index",
            str(self.device_index),
            "--compute-type",
            self.compute_type,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        assert self._process.stdout is not None
        try:
            line = await asyncio.wait_for(self._process.stdout.readline(), self.startup_timeout)
        except TimeoutError:
            await self.close()
            raise RuntimeError("Whisper worker timed out while loading the model") from None
        if not line:
            raise RuntimeError("Whisper worker exited before loading the model")
        ready = json.loads(line)
        if ready.get("event") != "ready":
            raise RuntimeError(f"unexpected Whisper worker response: {ready}")
        self.model_load_seconds = float(ready["model_load_seconds"])
        print(f"[STT MODEL] loaded_once={self.model_load_seconds:.3f}s", flush=True)
        return self.model_load_seconds

    async def warm(self, wav: Path) -> str:
        started = time.monotonic()
        text = await self.transcribe(wav)
        print(f"[STT WARMUP] duration={time.monotonic() - started:.3f}s", flush=True)
        return text

    async def transcribe(self, wav: Path) -> str:
        async with self._lock:
            await self.start()
            assert self._process is not None
            assert self._process.stdin is not None
            assert self._process.stdout is not None
            self._request_id += 1
            payload = json.dumps({"id": self._request_id, "wav": str(wav)}) + "\n"
            self._process.stdin.write(payload.encode())
            await self._process.stdin.drain()
            line = await self._process.stdout.readline()
            if not line:
                error = ""
                if self._process.stderr is not None:
                    error = (await self._process.stderr.read()).decode(errors="replace")[-500:]
                raise RuntimeError("Whisper worker stopped unexpectedly: " + error)
            response = json.loads(line)
            if response.get("id") != self._request_id:
                raise RuntimeError("Whisper worker response correlation failed")
            if "error" in response:
                raise RuntimeError("STT failed: " + response["error"])
            print(
                f"[STT WORKER] transcription={float(response['transcription_seconds']):.3f}s",
                flush=True,
            )
            return str(response["text"])

    async def close(self) -> None:
        process, self._process = self._process, None
        if process is None or process.returncode is not None:
            return
        if process.stdin is not None:
            process.stdin.close()
        try:
            await asyncio.wait_for(process.wait(), 3.0)
        except TimeoutError:
            process.terminate()
            await process.wait()
