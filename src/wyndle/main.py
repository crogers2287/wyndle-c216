"""Wyndle command entry point (bootstrap milestone)."""

import json

from wyndle import __version__
from wyndle.config import get_settings
from wyndle.logging import configure_logging


def main() -> None:
    configure_logging()
    settings = get_settings()
    print(
        json.dumps(
            {
                "name": settings.wyndle_name,
                "version": __version__,
                "camera_configured": bool(settings.tapo_ip),
                "persistent_memory": settings.persistent_memory_enabled,
                "proactive_speech": settings.proactive_speech_enabled,
                "status": "bootstrap_ready",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
