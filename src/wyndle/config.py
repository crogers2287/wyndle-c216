"""Environment-backed Wyndle configuration."""

from __future__ import annotations

from functools import lru_cache
from urllib.parse import quote

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    wyndle_name: str = "Wyndle"
    wyndle_wake_word: str = "wyndle"
    wyndle_wake_secondary: str = "hey wyndle"

    tapo_ip: str | None = None
    tapo_username: str | None = None
    tapo_password: SecretStr | None = None
    tapo_onvif_port: int = Field(default=2020, ge=1, le=65535)
    tapo_rtsp_port: int = Field(default=554, ge=1, le=65535)
    rtsp_main: str | None = None
    rtsp_sub: str | None = None

    go2rtc_url: str = "http://127.0.0.1:1984"
    go2rtc_stream_name: str = "wyndle"
    conversation_timeout_seconds: float = Field(default=15, gt=0)
    persistent_memory_enabled: bool = False
    proactive_speech_enabled: bool = False

    def camera_password(self) -> str | None:
        return self.tapo_password.get_secret_value() if self.tapo_password else None

    def rtsp_url(self, stream: int) -> str | None:
        explicit = self.rtsp_main if stream == 1 else self.rtsp_sub
        if explicit:
            return explicit
        if not (self.tapo_ip and self.tapo_username and self.tapo_password):
            return None
        username = quote(self.tapo_username, safe="")
        password = quote(self.camera_password() or "", safe="")
        return f"rtsp://{username}:{password}@{self.tapo_ip}:{self.tapo_rtsp_port}/stream{stream}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
