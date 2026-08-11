import json
from pathlib import Path

from wyndle.config import Settings
from wyndle.probe import CapabilityProbe, clean_text, redact, sanitize_url


def test_sanitize_url_removes_userinfo() -> None:
    safe = sanitize_url("rtsp://user:very-secret@example.test:554/stream1?x=1")
    assert safe == "rtsp://***:***@example.test:554/stream1?x=1"
    assert "very-secret" not in safe


def test_redact_nested_password_and_url() -> None:
    value = {"password": "secret", "nested": ["rtsp://u:p@host/stream1"]}
    rendered = json.dumps(redact(value))
    assert "secret" not in rendered
    assert "u:p" not in rendered


def test_probe_without_config_produces_report(tmp_path: Path) -> None:
    probe = CapabilityProbe(Settings(go2rtc_url="http://127.0.0.1:1", _env_file=None))
    report = probe.run()
    assert report["checks"]["ip_connectivity"]["status"] == "SKIPPED"
    assert report["checks"]["rtsp_main"]["status"] == "SKIPPED"
    assert report["checks"]["onvif_device"]["status"] == "SKIPPED"
    assert report["checks"]["go2rtc"]["status"] == "FAIL"


def test_clean_text_is_single_line_and_bounded() -> None:
    assert clean_text(" a\n  b ") == "a b"
    assert len(clean_text("x" * 1000)) == 800
