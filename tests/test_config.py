from wyndle.config import Settings


def test_rtsp_url_encodes_credentials() -> None:
    settings = Settings(
        tapo_ip="192.0.2.4",
        tapo_username="a@b",
        tapo_password="p:/?#@",
        _env_file=None,
    )
    assert settings.rtsp_url(1) == "rtsp://a%40b:p%3A%2F%3F%23%40@192.0.2.4:554/stream1"
    assert "p:/?#@" not in repr(settings)


def test_explicit_rtsp_url_wins() -> None:
    settings = Settings(rtsp_main="rtsp://example.test/custom", _env_file=None)
    assert settings.rtsp_url(1) == "rtsp://example.test/custom"
