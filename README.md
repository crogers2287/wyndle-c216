# Wyndle C216

Experimental local-first AI companion built around a single TP-Link Tapo C216.

The first target is a wake-word-gated voice/vision loop using the camera as the physical endpoint: microphone, video, speaker, and pan/tilt.

## Codex

Start with [`CODEX_HANDOFF.md`](./CODEX_HANDOFF.md). It is the authoritative implementation brief and milestone plan.

## Status

Planning/bootstrap only. No camera capability claims should be treated as tested until `tools/probe_c216.py` has been run against the actual device and `docs/camera-capabilities.md` records the result.
