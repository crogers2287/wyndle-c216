# Wyndle C216 Runbook

Concise setup, operations, and troubleshooting for the local-first Tapo C216 prototype.

## Prerequisites

- Linux host, Python 3.11+
- uv package manager
- FFmpeg `ffprobe` on PATH
- Tapo C216 on LAN with RTSP and ONVIF enabled
- Dedicated local camera account, not your cloud password
- Optional: go2rtc 1.9+ on 127.0.0.1:1984 for speaker backchannel

Install FFmpeg on Debian/Ubuntu:
```bash
sudo apt-get install ffmpeg
```

## Initial setup

```bash
git clone https://github.com/crogers2287/wyndle-c216.git
cd wyndle-c216
cp .env.example .env
```

Edit `.env`:
- `TAPO_IP`, `TAPO_USERNAME`, `TAPO_PASSWORD`
- `LLM_BASE_URL`, `LLM_MODEL`, `VISION_BASE_URL`, `VISION_MODEL`
- `PIPER_EXECUTABLE`, `PIPER_MODEL`, `WHISPER_PYTHON`, `WHISPER_MODEL`

Install dependencies:
```bash
uv sync --extra dev
```

## Verify camera capabilities

Run passive probe, no movement or sound:
```bash
uv run wyndle-probe --output data/capability-report.json
```

Expected outputs:
- TCP 554/2020 reachable
- RTSP main/sub streams
- ONVIF device/media/PTZ advertised
- go2rtc API state

Confirm speaker manually:
```bash
uv run wyndle-probe --confirm-speaker-pass
```

See `docs/camera-capabilities.md` for the verification ledger. Reports are gitignored.

## Start go2rtc

Generate config under `.local/` and start:
```bash
uv run python tools/start_go2rtc.py
```

Verify at http://127.0.0.1:1984. The Tapo source should show H.264 receive and PCMA send.

## Run demo

```bash
uv run wyndle-demo "What am I holding?"
uv run wyndle-demo "Say hello in one short sentence"
```

The demo uses current `LLM_*` and `VISION_*` settings and routes TTS via go2rtc to the camera speaker.

## Daily operations

Health check:
```bash
uv run wyndle
```
Prints name, version, camera configured flag, memory/speech settings.

Re-probe after firmware or network changes:
```bash
uv run wyndle-probe --output data/capability-report.json
```

Restart go2rtc if speaker stops:
```bash
pkill -f start_go2rtc.py || true
uv run python tools/start_go2rtc.py
```

## Configuration notes

- `RTSP_MAIN`/`RTSP_SUB` override auto-built URLs. Leave blank to build from `TAPO_*`.
- `CONVERSATION_TIMEOUT_SECONDS` defaults to 15s.
- `PERSISTENT_MEMORY_ENABLED` and `PROACTIVE_SPEECH_ENABLED` default off.
- Do not commit `.env`. Credentials are redacted in logs but may appear briefly in `ffprobe` argv.

## Troubleshooting

Camera unreachable
- Check LAN IP and firewall
- Verify dedicated account has RTSP/ONVIF enabled in Tapo app
- Test with `ffprobe rtsp://user:pass@ip:554/stream1`

No audio from camera
- Ensure go2rtc is running and Tapo source configured
- Confirm `GO2RTC_URL` and `GO2RTC_STREAM_NAME`
- Test speaker manually via go2rtc WebRTC UI

Probe fails
- Confirm `TAPO_ONVIF_PORT` matches camera
- Check `ffprobe` is on PATH
- Review `data/capability-report.json` for redacted details

High latency
- Use local models via Ollama
- Reduce `VISION_MODEL` size for quick answers
- Check network RTT to camera

## Security

- LAN only, no public bind
- No continuous recording
- Mute via software; hardware privacy control planned
- Rotate camera password regularly
- Never log secrets

## References

- `docs/camera-capabilities.md`
- `docs/architecture.md`
- `CODEX_HANDOFF.md`
