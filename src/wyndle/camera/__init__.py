"""Camera adapters."""

from wyndle.camera.ptz import (
    ONVIFPTZAdapter,
    PTZConnectionError,
    PTZError,
    PTZLimitError,
    PTZLimits,
    PTZStopError,
)

__all__ = [
    "ONVIFPTZAdapter",
    "PTZConnectionError",
    "PTZError",
    "PTZLimits",
    "PTZLimitError",
    "PTZStopError",
]
