"""Hardware capability probe for one Tapo C216.

The probe is intentionally diagnostic: it reports failures instead of crashing, redacts
credentials, and only performs movement/audio-output tests after explicit opt-in.
"""

from __future__ import annotations

import argparse
import json
import shutil
import socket
import subprocess
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from wyndle.config import Settings


@dataclass
class Check:
    status: str
    detail: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    duration_ms: int | None = None


class CapabilityProbe:
    def __init__(self, settings: Settings, *, test_ptz: bool = False) -> None:
        self.settings = settings
        self.test_ptz = test_ptz
        self.checks: dict[str, Check] = {}
        self._onvif_camera: Any = None
        self._onvif_media: Any = None
        self._onvif_profiles: list[Any] = []
        self._onvif_ptz: Any = None

    def record(self, name: str, status: str, detail: str = "", **data: Any) -> None:
        self.checks[name] = Check(status=status, detail=detail, data=redact(data))

    def timed(self, name: str, fn: Callable[[], None]) -> None:
        started = time.monotonic()
        try:
            fn()
        except Exception as exc:  # each boundary must degrade independently
            self.record(name, "ERROR", actionable_error(exc))
        finally:
            if name in self.checks:
                self.checks[name].duration_ms = round((time.monotonic() - started) * 1000)

    def run(self) -> dict[str, Any]:
        self.timed("ip_connectivity", self.probe_connectivity)
        self.timed("rtsp_main", lambda: self.probe_rtsp("rtsp_main", self.settings.rtsp_url(1)))
        self.timed("rtsp_sub", lambda: self.probe_rtsp("rtsp_sub", self.settings.rtsp_url(2)))
        self.timed("rtsp_reconnect", self.probe_reconnect)
        self.timed("onvif_device", self.probe_onvif_device)
        self.timed("onvif_media", self.probe_onvif_media)
        self.timed("onvif_ptz", self.probe_onvif_ptz)
        self.timed("onvif_audio_output", self.probe_onvif_audio)
        self.timed("go2rtc", self.probe_go2rtc)
        self.record(
            "speaker_playback",
            "SKIPPED",
            "No audio was played automatically. Configure a Tapo source in go2rtc, open its "
            "WebRTC page, enable the microphone, and use --confirm-speaker-pass after hearing it.",
        )
        return {
            "schema_version": 1,
            "generated_at": datetime.now(UTC).isoformat(),
            "probe_version": "0.1.0",
            "camera": {"host": self.settings.tapo_ip, "onvif_port": self.settings.tapo_onvif_port},
            "checks": {name: asdict(check) for name, check in self.checks.items()},
            "summary": summarize(self.checks),
        }

    def probe_connectivity(self) -> None:
        host = self.settings.tapo_ip
        if not host:
            self.record("ip_connectivity", "SKIPPED", "Set TAPO_IP in .env.")
            return
        ports = {"rtsp": self.settings.tapo_rtsp_port, "onvif": self.settings.tapo_onvif_port}
        results: dict[str, str] = {}
        for label, port in ports.items():
            try:
                with socket.create_connection((host, port), timeout=2):
                    results[label] = "open"
            except OSError as exc:
                results[label] = f"unreachable: {type(exc).__name__}"
        status = "PASS" if any(value == "open" for value in results.values()) else "FAIL"
        self.record("ip_connectivity", status, f"TCP port checks: {results}", ports=results)

    def ffprobe(self, url: str, timeout: int = 12) -> dict[str, Any]:
        if not shutil.which("ffprobe"):
            raise RuntimeError("ffprobe is not installed; install FFmpeg and retry")
        command = [
            "ffprobe",
            "-v",
            "error",
            "-rtsp_transport",
            "tcp",
            "-show_entries",
            "stream=index,codec_type,codec_name,width,height,r_frame_rate,"
            "avg_frame_rate,sample_rate,channels",
            "-show_entries",
            "format=format_name,start_time",
            "-of",
            "json",
            url,
        ]
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout, check=False
        )
        if result.returncode:
            raise RuntimeError(clean_text(result.stderr) or f"ffprobe exited {result.returncode}")
        return json.loads(result.stdout)

    def probe_rtsp(self, name: str, url: str | None) -> None:
        if not url:
            self.record(name, "SKIPPED", "Set camera credentials/host or an explicit RTSP URL.")
            return
        info = self.ffprobe(url)
        streams = info.get("streams", [])
        video = [stream for stream in streams if stream.get("codec_type") == "video"]
        audio = [stream for stream in streams if stream.get("codec_type") == "audio"]
        if not video:
            self.record(
                name, "FAIL", "RTSP opened but no video stream was reported.", streams=streams
            )
            return
        v = video[0]
        dimensions = f"{v.get('width')}x{v.get('height')}"
        detail = f"video={v.get('codec_name')} {dimensions} fps={v.get('avg_frame_rate')}"
        if audio:
            detail += f"; microphone={audio[0].get('codec_name')}"
        else:
            detail += "; microphone=not detected"
        self.record(name, "PASS", detail, video=video, audio=audio)

    def probe_reconnect(self) -> None:
        url = self.settings.rtsp_url(2) or self.settings.rtsp_url(1)
        if not url:
            self.record("rtsp_reconnect", "SKIPPED", "RTSP is not configured.")
            return
        attempts = []
        for _ in range(2):
            started = time.monotonic()
            self.ffprobe(url, timeout=12)
            attempts.append(round((time.monotonic() - started) * 1000))
            time.sleep(0.25)
        self.record(
            "rtsp_reconnect",
            "PASS",
            f"Two clean opens completed: {attempts} ms",
            attempts_ms=attempts,
        )

    def onvif_ready(self) -> bool:
        required = [
            self.settings.tapo_ip,
            self.settings.tapo_username,
            self.settings.camera_password(),
        ]
        if not all(required):
            return False
        if self._onvif_camera is None:
            from onvif import ONVIFCamera

            self._onvif_camera = ONVIFCamera(
                self.settings.tapo_ip,
                self.settings.tapo_onvif_port,
                self.settings.tapo_username,
                self.settings.camera_password(),
            )
        return True

    def probe_onvif_device(self) -> None:
        if not self.onvif_ready():
            self.record("onvif_device", "SKIPPED", "Set TAPO_IP, TAPO_USERNAME, and TAPO_PASSWORD.")
            return
        device = self._onvif_camera.create_devicemgmt_service()
        info = serialize(device.GetDeviceInformation())
        capabilities = serialize(device.GetCapabilities({"Category": "All"}))
        self.record(
            "onvif_device",
            "PASS",
            "ONVIF device information retrieved.",
            info=info,
            capabilities=capabilities,
        )

    def probe_onvif_media(self) -> None:
        if not self.onvif_ready():
            self.record("onvif_media", "SKIPPED", "ONVIF is not configured.")
            return
        self._onvif_media = self._onvif_camera.create_media_service()
        self._onvif_profiles = list(self._onvif_media.GetProfiles() or [])
        profiles = []
        for profile in self._onvif_profiles:
            item = serialize(profile)
            try:
                uri = self._onvif_media.GetSnapshotUri({"ProfileToken": profile.token}).Uri
                item["snapshot_uri"] = sanitize_url(uri)
            except Exception as exc:
                item["snapshot_error"] = actionable_error(exc)
            profiles.append(item)
        status = "PASS" if profiles else "FAIL"
        self.record(
            "onvif_media", status, f"Retrieved {len(profiles)} media profile(s).", profiles=profiles
        )

    def probe_onvif_ptz(self) -> None:
        if not self.onvif_ready():
            self.record("onvif_ptz", "SKIPPED", "ONVIF is not configured.")
            return
        try:
            self._onvif_ptz = self._onvif_camera.create_ptz_service()
            nodes = serialize(self._onvif_ptz.GetNodes())
            configs = serialize(self._onvif_ptz.GetConfigurations())
            operations = sorted(getattr(self._onvif_ptz, "operations", {}).keys())
        except Exception as exc:
            self.record("onvif_ptz", "UNSUPPORTED", actionable_error(exc))
            return
        movement = {
            name: name in operations
            for name in (
                "ContinuousMove",
                "RelativeMove",
                "AbsoluteMove",
                "GotoPreset",
                "GotoHomePosition",
            )
        }
        advertised = ", ".join(k for k, value in movement.items() if value)
        detail = f"PTZ service exposed; operations={advertised or 'none detected'}"
        if not self.test_ptz:
            detail += "; physical movement skipped (use --test-ptz)"
        else:
            detail += (
                "; safe movement requested but not executed until bounded movement "
                "and guaranteed-stop logic is reviewed"
            )
        self.record(
            "onvif_ptz", "PASS", detail, movement=movement, nodes=nodes, configurations=configs
        )

    def probe_onvif_audio(self) -> None:
        if self._onvif_media is None:
            if not self.onvif_ready():
                self.record("onvif_audio_output", "SKIPPED", "ONVIF is not configured.")
                return
            self._onvif_media = self._onvif_camera.create_media_service()
        results: dict[str, Any] = {}
        supported = False
        for method in ("GetAudioOutputConfigurations", "GetAudioDecoderConfigurations"):
            try:
                results[method] = serialize(getattr(self._onvif_media, method)())
                supported = supported or bool(results[method])
            except Exception as exc:
                results[method] = {"error": actionable_error(exc)}
        status = "PASS" if supported else "UNSUPPORTED"
        self.record(
            "onvif_audio_output",
            status,
            "Inspected ONVIF audio output/decoder configuration.",
            results=results,
        )

    def probe_go2rtc(self) -> None:
        base = self.settings.go2rtc_url.rstrip("/")
        try:
            with httpx.Client(timeout=3) as client:
                response = client.get(f"{base}/api/streams")
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:
            self.record(
                "go2rtc", "FAIL", f"go2rtc API unavailable at {base}: {actionable_error(exc)}"
            )
            return
        name = self.settings.go2rtc_stream_name
        stream = payload.get(name) if isinstance(payload, dict) else None
        if stream is None:
            self.record(
                "go2rtc",
                "PASS",
                f"API reachable, but stream '{name}' is not configured.",
                api_reachable=True,
                stream_configured=False,
            )
        else:
            self.record(
                "go2rtc",
                "PASS",
                f"API reachable and stream '{name}' exists. "
                "Inspect producers/consumers for backchannel support.",
                api_reachable=True,
                stream_configured=True,
                producer_count=len(stream.get("producers", []))
                if isinstance(stream, dict)
                else None,
                consumer_count=len(stream.get("consumers", []))
                if isinstance(stream, dict)
                else None,
            )


def serialize(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): serialize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [serialize(v) for v in value]
    if hasattr(value, "__keylist__"):
        return {key: serialize(getattr(value, key, None)) for key in value.__keylist__}
    if hasattr(value, "__dict__"):
        return {k: serialize(v) for k, v in vars(value).items() if not k.startswith("_")}
    return str(value)


def sanitize_url(value: str) -> str:
    try:
        parts = urlsplit(value)
        if not parts.scheme:
            return value
        host = parts.hostname or ""
        netloc = host
        if parts.port:
            netloc += f":{parts.port}"
        if parts.username is not None:
            netloc = f"***:***@{netloc}"
        return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
    except Exception:
        return "<redacted-url>"


def clean_text(text: str) -> str:
    return " ".join(text.strip().split())[:800]


def actionable_error(exc: Exception) -> str:
    text = clean_text(str(exc))
    return f"{type(exc).__name__}: {text}" if text else type(exc).__name__


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: (
                "***"
                if any(word in k.lower() for word in ("password", "credential"))
                else redact(v)
            )
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str) and "://" in value:
        return sanitize_url(value)
    return value


def summarize(checks: dict[str, Check]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for check in checks.values():
        summary[check.status] = summary.get(check.status, 0) + 1
    return summary


def print_report(report: dict[str, Any]) -> None:
    print("WYNDLE C216 CAPABILITY REPORT")
    print("=" * 31)
    for name, check in report["checks"].items():
        label = name.replace("_", " ").title()
        detail = check["detail"]
        print(f"{label:<30} {check['status']:<11} {detail}")
    print("-" * 31)
    print("Summary:", ", ".join(f"{k}={v}" for k, v in sorted(report["summary"].items())))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Probe a physical Tapo C216 without exposing credentials."
    )
    parser.add_argument("--output", type=Path, default=Path("data/capability-report.json"))
    parser.add_argument(
        "--test-ptz",
        action="store_true",
        help="Opt in to PTZ diagnostics (movement remains safety-gated).",
    )
    parser.add_argument(
        "--confirm-speaker-pass",
        action="store_true",
        help="Record a manually verified go2rtc speaker test as PASS.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = CapabilityProbe(Settings(), test_ptz=args.test_ptz).run()
    if args.confirm_speaker_pass:
        report["checks"]["speaker_playback"] = asdict(
            Check("PASS", "User confirmed audible camera speaker output via go2rtc.")
        )
        report["summary"] = summarize({k: Check(**v) for k, v in report["checks"].items()})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(redact(report), indent=2, sort_keys=True) + "\n")
    print_report(report)
    print(f"\nJSON report saved to {args.output}")


if __name__ == "__main__":
    main()
