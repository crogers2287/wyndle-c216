#!/usr/bin/env python3
"""Measure whether the C216 RTSP audio track contains a real signal."""

from __future__ import annotations

import subprocess
import sys
from array import array
from math import sqrt

from wyndle.config import Settings


def main() -> None:
    settings = Settings()
    url = settings.rtsp_url(2)
    if not url:
        raise SystemExit("Camera RTSP is not configured")
    result = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-rtsp_transport",
            "tcp",
            "-i",
            url,
            "-vn",
            "-t",
            "5",
            "-ar",
            "16000",
            "-ac",
            "1",
            "-f",
            "s16le",
            "pipe:1",
        ],
        capture_output=True,
        timeout=15,
        check=True,
    )
    samples = array("h")
    samples.frombytes(result.stdout)
    if sys.byteorder != "little":
        samples.byteswap()
    if not samples:
        raise SystemExit("FAIL: RTSP audio returned no samples")
    rms = sqrt(sum(value * value for value in samples) / len(samples))
    unique = len(set(samples))
    print(
        f"samples={len(samples)} rms_pcm={rms:.2f} "
        f"min={min(samples)} max={max(samples)} unique={unique}"
    )
    if unique <= 2 or rms < 16:
        raise SystemExit(
            "FAIL: camera audio track is digital silence; enable microphone or "
            "disable privacy mode in Tapo settings"
        )
    print("PASS: camera microphone contains a varying audio signal")


if __name__ == "__main__":
    main()
