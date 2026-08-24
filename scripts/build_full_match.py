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

    temporary_destination = (
        session_folder
        / "full-match-building.mp4"
    )

    temporary_destination.unlink(
        missing_ok=True
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
        str(temporary_destination),
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=7200,
        )

    except subprocess.TimeoutExpired:
        temporary_destination.unlink(
            missing_ok=True
        )

        log(
            "Full match build timed out; "
            "raw recording segments have been kept"
        )

        return 2

    finally:
        concat_file.unlink(
            missing_ok=True
        )

    if result.returncode != 0:
        temporary_destination.unlink(
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
        not temporary_destination.exists()
        or temporary_destination.stat().st_size <= 0
    ):
        log(
            "Full match output validation failed"
        )
        return 3

    probe = subprocess.run(
        [
            "/usr/bin/ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_name",
            "-of",
            "default=noprint_wrappers=1",
            str(temporary_destination),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )

    if probe.returncode != 0:
        temporary_destination.unlink(
            missing_ok=True
        )

        log(
            "Full match validation failed; "
            "raw recording segments have been kept"
        )

        return 3

    temporary_destination.replace(
        destination
    )

    browser_destination = (
        session_folder
        / "full-match-browser.mp4"
    )

    browser_command = [
        "/usr/bin/ffmpeg",
        "-hide_banner",
        "-loglevel",
        "warning",
        "-i",
        str(destination),
        "-map",
        "0:v:0",
        "-vf",
        "scale=1920:1080",
        "-c:v",
        "h264_v4l2m2m",
        "-b:v",
        "4M",
        "-movflags",
        "+faststart",
        "-y",
        str(browser_destination),
    ]

    log(
        "Building 1080p H.264 browser playback copy"
    )

    try:
        browser_result = subprocess.run(
            browser_command,
            capture_output=True,
            text=True,
            check=False,
            timeout=3600,
        )

    except subprocess.TimeoutExpired:
        browser_result = None

        log(
            "Browser playback build timed out; "
            "4K master kept"
        )

    if (
        browser_result is not None
        and browser_result.returncode == 0
        and browser_destination.exists()
        and browser_destination.stat().st_size > 0
    ):
        log(
            "Browser playback copy ready: "
            f"{browser_destination}"
        )

    else:
        browser_destination.unlink(
            missing_ok=True
        )

        if browser_result is not None:
            log(
                "Unable to build browser playback copy: "
                + (
                    browser_result.stderr.strip()
                    or "FFmpeg failed"
                )
            )


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
