# C216 camera capabilities

This file is the source of truth for **physically verified** capabilities.

## Current status

No physical C216 probe has been run from this repository yet. No media, PTZ, ONVIF, or
speaker capability is claimed as working.

Run:

```bash
cp .env.example .env
# Edit .env with the dedicated camera account and LAN address.
uv run wyndle-probe --output data/capability-report.json
```

For tests that can move the camera or make sound, opt in explicitly:

```bash
uv run wyndle-probe --test-ptz
uv run wyndle-probe --speaker-test-file ./private/test-tone.wav
```

Then summarize the actual result here. The JSON report is intentionally gitignored because it
may contain local IP addresses and device metadata.

## Verification ledger

| Capability | Status | Last tested | Notes |
|---|---|---:|---|
| IP connectivity | NOT TESTED | — | — |
| RTSP main/sub video | NOT TESTED | — | — |
| RTSP microphone | NOT TESTED | — | — |
| ONVIF device/media | NOT TESTED | — | — |
| ONVIF PTZ | NOT TESTED | — | Movement tests are opt-in |
| go2rtc connectivity | NOT TESTED | — | — |
| C216 speaker output | NOT TESTED | — | Audible test is opt-in |
