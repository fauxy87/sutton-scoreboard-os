#!/usr/bin/env python3

import argparse
import subprocess
import tempfile

from datetime import datetime
from pathlib import Path


HIGHLIGHT_ROOT = Path(
    "/var/lib/scoreos/highlights"
)


def log(message):
    print(
        datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
        message,
        flush=True,
    )


def escape_path(path):
    return str(path).replace(
        "'",
        "'\\''",
    )


def main():
    parser = argparse.ArgumentParser(
        description="Build one SCOREOS match highlights video."
    )

    parser.add_argument(
        "--date",
        default=datetime.now().strftime(
            "%Y-%m-%d"
        ),
        help="Match date YYYY-MM-DD",
    )

    args = parser.parse_args()

    day_folder = (
        HIGHLIGHT_ROOT /
        args.date
    )

    if not day_folder.exists():
        log(
            f"No highlights folder for "
            f"{args.date}"
        )
        return 1

    clips = sorted(
        path
        for path in day_folder.glob("*.mp4")
        if path.name != "match-highlights.mp4"
    )

    if not clips:
        log(
            f"No highlight clips found for "
            f"{args.date}"
        )
        return 1

    destination = (
        day_folder /
        "match-highlights.mp4"
    )

    log(
        f"Building match highlights from "
        f"{len(clips)} clips"
    )

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".txt",
        delete=False,
    ) as handle:
        concat_file = Path(handle.name)

        for clip in clips:
            handle.write(
                "file '"
                + escape_path(clip)
                + "'\n"
            )

    command = [
        "/usr/bin/ffmpeg",
        "-hide_banner",
        "-loglevel",
        "warning",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_file),
        "-map",
        "0:v:0",
        "-c",
        "copy",
        "-movflags",
        "+faststart",
        "-y",
        str(destination),
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )

    finally:
        concat_file.unlink(
            missing_ok=True
        )

    if result.returncode != 0:
        destination.unlink(
            missing_ok=True
        )

        log(
            "Unable to build match highlights: "
            + (
                result.stderr.strip()
                or "FFmpeg failed"
            )
        )

        return 2

    log(
        f"Match highlights ready: "
        f"{destination}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
