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
| RTSP microphone | PASS | G.711 A-law / `pcm_alaw`, 8 kHz advertised by ONVIF |
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
| Camera speaker submission | PASS | Local Piper WAV transcoded to PCMA/8000 and attached to Tapo send channel |
| Camera speaker audible | UNCONFIRMED | API/media path verified; no independent human/microphone confirmation recorded |

## Next hardware actions

1. Implement bounded ONVIF relative movement with a guaranteed `Stop`/recovery path, then test each
   direction at a very small displacement.
2. Install/configure go2rtc on loopback using its Tapo source, verify media connectivity, then send
   a short low-amplitude PCMA sample and confirm it is audible from the camera.
3. Record actual movement and speaker latency without claiming success from API responses alone.
