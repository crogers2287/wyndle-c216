# Wyndle C216

A local-first AI companion prototype built around **one TP-Link Tapo C216**. The first
engineering goal is to prove the physical camera loop—video, microphone, speaker, and PTZ—before
building the conversational agent.

> Status: Milestones 0 and the passive portion of Milestone 1 are implemented. No camera
> capability is claimed as verified until the probe is run against the physical unit.

## Prerequisites

- Linux and Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- FFmpeg (`ffprobe` must be on `PATH`)
- A dedicated local Tapo camera account with RTSP/ONVIF access enabled
- Optional: [go2rtc](https://github.com/AlexxIT/go2rtc) on `127.0.0.1:1984` for Tapo talk tests

On Ubuntu/Debian:

```bash
sudo apt-get install ffmpeg
```

## Setup

```bash
git clone https://github.com/crogers2287/wyndle-c216.git
cd wyndle-c216
cp .env.example .env
# Edit .env. Do not reuse your TP-Link cloud password.
uv sync --extra dev
```

## Probe the C216

The default probe is passive: TCP connectivity, RTSP main/sub media, repeat-open behavior,
ONVIF device/media/PTZ advertisement, ONVIF audio-output advertisement, and go2rtc API state.
It does **not** move the camera or play sound.

```bash
uv run wyndle-probe --output data/capability-report.json
# Equivalent compatibility path:
uv run python tools/probe_c216.py --output data/capability-report.json
```

The CLI prints a readable matrix and writes machine-readable JSON. The JSON is gitignored because
it may contain local device details. Credentials and credentialed URIs are redacted; note that an
RTSP password embedded in the private `ffprobe` process argv can briefly be visible to other local
users on the host.

Speaker output currently requires a manual go2rtc WebRTC confirmation. Only after sound is
actually heard should it be recorded:

```bash
uv run wyndle-probe --confirm-speaker-pass
```

`--test-ptz` currently inspects and labels the opt-in request but deliberately does not actuate the
camera until bounded movement/guaranteed-stop logic is implemented and reviewed.

See [`docs/camera-capabilities.md`](docs/camera-capabilities.md) for the verification ledger.

## Development

```bash
uv run pytest
uv run ruff check .
uv run wyndle
```

## Privacy and security defaults

- LAN/local-first; no public bind, tunnel, UPnP, or cloud recording
- `.env` and capability reports are not committed
- no continuous media storage
- persistent memory and proactive speech default off
- active movement/audio tests require explicit operator action

The complete product brief and milestone plan are in [`CODEX_HANDOFF.md`](CODEX_HANDOFF.md).
