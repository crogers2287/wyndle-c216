# C216 camera capabilities

This file is the source of truth for **physically verified** capabilities.

## Test device

- Model: TP-Link Tapo C216
- Hardware: 1.0
- Firmware: 1.0.4 Build 250208 Rel.48070n
- Probe date: 2026-08-10
- Connection: LAN at the configured private address

The machine-readable report is stored locally at `data/capability-report.json` and is gitignored.
Camera credentials, IP address, and serial number are intentionally omitted here.

## Verification ledger

| Capability | Status | Measured result |
|---|---|---|
| IP connectivity | PASS | TCP ports 554 (RTSP) and 2020 (ONVIF) reachable |
| RTSP main video | PASS | H.264, 2304×1296, 15 FPS |
| RTSP sub video | PASS | H.264, 1280×720, 15 FPS |
| RTSP microphone track | DEGRADED / NOT YET INTELLIGIBLE | 2026-08-11 simultaneous 5 s capture: direct stream2 and go2rtc relay each decoded 76,800 samples at 16 kHz, RMS 111.01, peak 2,788, min/max -2,752/+2,788, 1,021 unique values, 1.746% exact zeros. Both WAVs are saved under `.local/debug/`. Faster-Whisper returned an empty transcript for both, so intelligible speech is **not yet proven**. |
| Repeat RTSP opens | PASS | Two fresh substream opens completed in about 2.75–2.80 s |
| ONVIF device | PASS | Identity and capabilities retrieved |
| ONVIF media profiles | PASS | Two profiles retrieved |
| ONVIF snapshot URI | FAIL/UNSUPPORTED | Both profile calls returned an ONVIF error |
| ONVIF PTZ service | ADVERTISED | Absolute move, relative move, and up to 8 presets advertised |
| ONVIF absolute PTZ | PASS | Small +0.04 pan move reached target and returned to starting position |
| ONVIF continuous PTZ | NOT ADVERTISED | No continuous velocity space returned |
| ONVIF home | NOT ADVERTISED | `HomeSupported=false` |
| ONVIF audio output/backchannel | UNSUPPORTED | No audio output or decoder configurations returned |
| go2rtc Tapo media | PASS | v1.9.14 connected; H.264 receive, PCMA/8000 receive, PCMA/8000 send advertised |
| Piper local WAV | SIGNAL VERIFIED / HUMAN REVIEW PENDING | Fixed phrase produced PCM mono/16 kHz/16-bit, 2.400 s. Faster-Whisper independently transcribed it as “Hello, this is Wendell testing the camera speaker.” Original is `.local/debug/speaker-test-piper.wav`. |
| Camera speaker submission | PATH VERIFIED ONLY | Deterministic PCMA/8000 sidecar is `.local/debug/speaker-test-pcma.alaw` (19,200 bytes). go2rtc attachment alone is not audible proof. |
| Camera speaker audible | UNCONFIRMED | API/media path verified; no independent human/microphone confirmation recorded |

## 2026-08-11 media-pipeline milestone

The live AI runtime remains stopped. Feature work is blocked until the saved go2rtc microphone WAV contains clearly intelligible speech and produces a sensible transcript. Use `uv run wyndle-audio-debug --capture-pair` while speaking normally, then listen to both artifacts.

## Next hardware actions

1. Implement bounded ONVIF relative movement with a guaranteed `Stop`/recovery path, then test each
   direction at a very small displacement.
2. Install/configure go2rtc on loopback using its Tapo source, verify media connectivity, then send
   a short low-amplitude PCMA sample and confirm it is audible from the camera.
3. Record actual movement and speaker latency without claiming success from API responses alone.
