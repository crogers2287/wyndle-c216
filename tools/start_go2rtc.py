#!/usr/bin/env python3
"""Download/configure/start a loopback-only go2rtc for the configured C216."""

from __future__ import annotations

import stat
import subprocess
import urllib.request
from pathlib import Path
from urllib.parse import quote

from wyndle.config import Settings

VERSION = "1.9.14"
URL = f"https://github.com/AlexxIT/go2rtc/releases/download/v{VERSION}/go2rtc_linux_amd64"


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    binary = root / ".local/bin/go2rtc"
    config = root / ".local/go2rtc/go2rtc.yaml"
    binary.parent.mkdir(parents=True, exist_ok=True)
    config.parent.mkdir(parents=True, exist_ok=True)
    if not binary.exists():
        urllib.request.urlretrieve(URL, binary)
        binary.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
    settings = Settings()
    password = settings.camera_password()
    if not settings.tapo_ip or not password:
        raise SystemExit("Set TAPO_IP and TAPO_PASSWORD in private .env")
    text = (
        'api:\n  listen: "127.0.0.1:1984"\n'
        'rtsp:\n  listen: "127.0.0.1:8554"\n'
        'webrtc:\n  listen: "127.0.0.1:8555"\n'
        f"streams:\n  {settings.go2rtc_stream_name}: "
        f"tapo://{quote(password, safe='')}@{settings.tapo_ip}\n"
    )
    config.write_text(text)
    config.chmod(0o600)
    print("Starting loopback-only go2rtc; press Ctrl-C to stop")
    subprocess.run([str(binary), "-config", str(config)], cwd=config.parent, check=True)


if __name__ == "__main__":
    main()
