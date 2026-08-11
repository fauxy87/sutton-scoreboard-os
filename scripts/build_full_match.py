#!/usr/bin/env python3

import argparse
import subprocess
import tempfile

from datetime import datetime
from pathlib import Path


RECORDING_ROOT = Path(
    "/var/lib/scoreos/recordings"
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
        description="Build one full SCOREOS match recording."
    )

    parser.add_argument(
        "--date",
        default=datetime.now().strftime(
            "%Y-%m-%d"
        ),
    )

    parser.add_argument(
        "--session",
        required=True,
        help="Match session ID",
    )

    args = parser.parse_args()

    session_folder = (
        RECORDING_ROOT
        / args.date
        / args.session
        / "full"
    )

    if not session_folder.exists():
        log(
            f"Session folder not found: "
            f"{session_folder}"
        )
        return 1

    segments = sorted(
        path
        for path in session_folder.glob("*.ts")
        if path.stat().st_size > 0
    )

    if not segments:
        log("No recording segments found")
        return 1

    destination = (
        session_folder
        / "full-match.mp4"
    )

    log(
        f"Building full match from "
        f"{len(segments)} segments"
    )

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".txt",
        delete=False,
    ) as handle:
        concat_file = Path(handle.name)

        for segment in segments:
            handle.write(
                "file '"
                + escape_path(segment)
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
            timeout=1800,
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
            "Unable to build full match: "
            + (
                result.stderr.strip()
                or "FFmpeg failed"
            )
        )

        return 2

    if (

        not destination.exists()

        or destination.stat().st_size <= 0

    ):

        log(

            "Full match output validation failed"

        )

        return 3


    deleted = 0

    deleted_bytes = 0


    for segment in segments:

        try:

            size = segment.stat().st_size

            segment.unlink()

            deleted += 1

            deleted_bytes += size

        except OSError as exc:

            log(

                f"Unable to remove raw segment "

                f"{segment}: {exc}"

            )


    log(

        f"Full match ready: "

        f"{destination}"

    )


    log(

        f"Cleaned {deleted} raw segments "

        f"({deleted_bytes / 1024 / 1024:.1f} MB)"

    )


    return 0


if __name__ == "__main__":
    raise SystemExit(main())
