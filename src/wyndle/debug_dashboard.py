"""Local-only developer dashboard with explicitly injected, inert-by-default hooks."""

# ruff: noqa: E501

from __future__ import annotations

import argparse
import inspect
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import asdict, dataclass, is_dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

HookResult = Mapping[str, Any] | str | None


class DebugServices(Protocol):
    """Runtime integration boundary. Implementations decide whether an action is safe."""

    def snapshot(self) -> object: ...

    async def latest_frame(self) -> bytes | None: ...

    async def analyze(self, prompt: str) -> HookResult: ...

    async def speak(self, text: str) -> HookResult: ...

    async def ptz(self, action: str) -> HookResult: ...


@dataclass(frozen=True, slots=True)
class DisabledDebugServices:
    """Safe default: exposes status, but cannot touch camera, audio, or models."""

    reason: str = "debug hooks are not configured"

    def snapshot(self) -> dict[str, object]:
        return {"state": "unconfigured", "hooks_enabled": False, "detail": self.reason}

    async def latest_frame(self) -> None:
        return None

    async def analyze(self, prompt: str) -> HookResult:
        raise NotImplementedError(self.reason)

    async def speak(self, text: str) -> HookResult:
        raise NotImplementedError(self.reason)

    async def ptz(self, action: str) -> HookResult:
        raise NotImplementedError(self.reason)


class TextRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1000)


class AnalyzeRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=1000)


class PTZRequest(BaseModel):
    action: str = Field(pattern=r"^(left|right|up|down|home|stop)$")


def _jsonable_snapshot(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")  # type: ignore[union-attr]
    if isinstance(value, Mapping):
        return dict(value)
    return value


async def _call_hook(
    hook: Callable[..., HookResult | Awaitable[HookResult]], *args: str
) -> HookResult:
    try:
        result = hook(*args)
        if inspect.isawaitable(result):
            result = await result
        return result
    except NotImplementedError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


_DASHBOARD = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Wyndle Debug</title><style>
body{font:15px system-ui;max-width:900px;margin:2rem auto;padding:0 1rem;background:#111;color:#eee}
section{border:1px solid #444;border-radius:8px;padding:1rem;margin:1rem 0}button,input{padding:.55rem;margin:.2rem}
input{min-width:18rem}img{max-width:100%;background:#222}pre{white-space:pre-wrap;color:#9ef}
</style></head><body><h1>Wyndle local debug</h1>
<section><h2>Runtime state</h2><pre id="state">loading…</pre></section>
<section><h2>Latest frame</h2><img id="frame" alt="No latest frame"><br><button onclick="frame.src='/api/frame/latest?'+Date.now()">Refresh</button></section>
<section><h2>Hooks</h2>
<input id="analyze" placeholder="Analysis prompt"><button onclick="post('/api/controls/analyze',{prompt:analyze.value})">Analyze</button><br>
<input id="speech" placeholder="Text to speak"><button onclick="post('/api/controls/speak',{text:speech.value})">Speak</button><br>
<button onclick="post('/api/controls/ptz',{action:'left'})">←</button><button onclick="post('/api/controls/ptz',{action:'stop'})">Stop</button><button onclick="post('/api/controls/ptz',{action:'right'})">→</button>
<pre id="result"></pre></section><script>
const state=document.querySelector('#state'),frame=document.querySelector('#frame'),result=document.querySelector('#result');
async function refresh(){let r=await fetch('/api/status');state.textContent=JSON.stringify(await r.json(),null,2)}
async function post(url,body){let r=await fetch(url,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body)});result.textContent=JSON.stringify(await r.json(),null,2);refresh()}
frame.src='/api/frame/latest';refresh();setInterval(refresh,2000);
</script></body></html>"""


def create_app(services: DebugServices | None = None) -> FastAPI:
    """Build the dashboard without constructing hardware-facing services."""
    runtime = services or DisabledDebugServices()
    app = FastAPI(title="Wyndle local debug dashboard", docs_url=None, redoc_url=None)

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def dashboard() -> str:
        return _DASHBOARD

    @app.get("/health")
    async def health() -> dict[str, object]:
        return {"ok": True, "service": "wyndle-debug", "time": datetime.now(UTC).isoformat()}

    @app.get("/api/status")
    async def status() -> dict[str, object]:
        return {"ok": True, "runtime": _jsonable_snapshot(runtime.snapshot())}

    @app.get("/api/frame/latest")
    async def latest_frame() -> Response:
        frame = await runtime.latest_frame()
        if frame is None:
            raise HTTPException(status_code=404, detail="no frame is available")
        return Response(frame, media_type="image/jpeg", headers={"Cache-Control": "no-store"})

    @app.post("/api/controls/analyze")
    async def analyze(request: AnalyzeRequest) -> dict[str, object]:
        return {"ok": True, "result": await _call_hook(runtime.analyze, request.prompt.strip())}

    @app.post("/api/controls/speak")
    async def speak(request: TextRequest) -> dict[str, object]:
        return {"ok": True, "result": await _call_hook(runtime.speak, request.text.strip())}

    @app.post("/api/controls/ptz")
    async def ptz(request: PTZRequest) -> dict[str, object]:
        return {"ok": True, "result": await _call_hook(runtime.ptz, request.action)}

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the inert local Wyndle debug dashboard")
    parser.add_argument("--host", default="127.0.0.1", help="bind address (default: localhost)")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    import uvicorn

    uvicorn.run(create_app(), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
