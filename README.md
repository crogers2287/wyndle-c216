# Wyndle C216

Local-first AI companion prototype for one TP-Link Tapo C216. Goal: prove the physical camera loop — video, microphone, speaker, PTZ — before building the conversational agent.

> Status: physical C216 media, microphone, bounded PTZ, local vision/language, TTS, and go2rtc speaker submission paths are working. Wake-word and continuous voice orchestration are implemented and ready for live tuning.

## Quick start

Prerequisites
- Linux, Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- FFmpeg with `ffprobe` on PATH
- Tapo C216 on LAN with RTSP/ONVIF enabled and a dedicated local account
- Optional: go2rtc on `127.0.0.1:1984` for speaker tests

```bash
git clone https://github.com/crogers2287/wyndle-c216.git
cd wyndle-c216
cp .env.example .env
# Edit .env with your camera and model paths
uv sync --extra dev
```

Probe the camera
```bash
uv run wyndle-probe --output data/capability-report.json
```
The probe is passive: connectivity, RTSP main/sub, ONVIF, go2rtc state. No movement or sound.

Start go2rtc for speaker backchannel
```bash
uv run python tools/start_go2rtc.py
```


Run the always-on local voice loop:
```bash
uv run wyndle-live
```
Say “Wyndle” or “Hey Wyndle”; follow-ups remain open for the configured timeout.

Run the localhost debug console:
```bash
uv run wyndle-debug
# open http://127.0.0.1:8765
```

Run a typed demo
```bash
uv run wyndle-demo "What am I holding?"
uv run wyndle-demo "Say hello in one short sentence"
```

## Documentation

- `docs/runbook.md` — concise setup, operations, and troubleshooting
- `docs/camera-capabilities.md` — verified hardware ledger
- `docs/architecture.md` — system overview
- `CODEX_HANDOFF.md` — product brief and milestone plan

## Development

```bash
uv run pytest
uv run ruff check .
uv run wyndle
```

## Privacy & security defaults

- LAN/local-first, no public bind or cloud recording
- `.env` and capability reports are gitignored
- No continuous media storage
- Persistent memory and proactive speech default off
- Active PTZ/audio tests require explicit operator action
