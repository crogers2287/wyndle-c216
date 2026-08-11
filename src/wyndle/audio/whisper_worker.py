"""Long-lived faster-whisper worker executed in its dedicated Python environment."""

from __future__ import annotations

import argparse
import json
import sys
import time


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--device-index", type=int, default=2)
    parser.add_argument("--compute-type", default="float16")
    args = parser.parse_args()

    from faster_whisper import WhisperModel

    started = time.monotonic()
    model = WhisperModel(
        args.model,
        device=args.device,
        device_index=args.device_index,
        compute_type=args.compute_type,
        cpu_threads=16,
    )
    print(
        json.dumps({"event": "ready", "model_load_seconds": time.monotonic() - started}),
        flush=True,
    )
    for line in sys.stdin:
        try:
            request = json.loads(line)
            started = time.monotonic()
            segments, _ = model.transcribe(
                request["wav"], vad_filter=True, beam_size=1, language="en"
            )
            text = " ".join(segment.text.strip() for segment in segments).strip()
            print(
                json.dumps(
                    {
                        "id": request["id"],
                        "text": text,
                        "transcription_seconds": time.monotonic() - started,
                    }
                ),
                flush=True,
            )
        except Exception as exc:
            print(json.dumps({"id": request.get("id"), "error": str(exc)}), flush=True)


if __name__ == "__main__":
    main()
