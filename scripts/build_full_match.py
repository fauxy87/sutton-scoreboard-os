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

    mode = parser.add_mutually_exclusive_group()

    mode.add_argument(
        "--master-only",
        action="store_true",
        help=(
            "Build and validate the clean full-match "
            "master without creating the browser copy"
        ),
    )

    mode.add_argument(
        "--browser-only",
        action="store_true",
        help=(
            "Build the browser/score-overlay copy from "
            "an existing full-match master"
        ),
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

    destination = (
        session_folder
        / "full-match.mp4"
    )

    if args.browser_only:
        if (
            not destination.exists()
            or destination.stat().st_size <= 0
        ):
            log(
                "Existing full-match master not found "
                "for browser-only build"
            )
            return 1

        log(
            "Using existing full-match master for "
            "deferred browser build"
        )

    elif not segments:
        log("No recording segments found")
        return 1

    temporary_destination = (
        session_folder
        / "full-match-building.mp4"
    )

    if not args.browser_only:
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


    if args.master_only:
        log(
            "Master-only build complete; "
            "browser conversion deferred"
        )

        # Keep the raw segments until the deferred
        # browser/score-overlay build has completed.
        # build_score_overlay.py can use their timestamped
        # filenames for accurate score synchronisation.
        log(
            f"Full match ready: "
            f"{destination}"
        )

        log(
            "Raw recording segments retained for "
            "deferred browser build"
        )

        return 0

    browser_destination = (
        session_folder
        / "full-match-browser.mp4"
    )

    score_filter = (
        session_folder.parent
        / "score-overlay-filter.txt"
    )

    score_history = (
        session_folder.parent
        / "score-history.jsonl"
    )

    video_filter = "scale=1920:1080"

    if score_history.exists():
        overlay_script = (
            Path(__file__).parent
            / "build_score_overlay.py"
        )

        overlay_result = subprocess.run(
            [
                "/usr/bin/python3",
                str(overlay_script),
                "--date",
                args.date,
                "--session",
                args.session,
                "--output",
                str(score_filter),
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )

        if (
            overlay_result.returncode == 0
            and score_filter.exists()
        ):
            overlay_filters = (
                score_filter.read_text(
                    encoding="utf-8"
                ).strip()
            )

            if overlay_filters:
                video_filter += (
                    ","
                    + overlay_filters
                )

                log(
                    "Adding broadcast score bar "
                    "to browser playback copy"
                )

        else:
            log(
                "Score overlay unavailable; "
                "building clean browser copy"
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
        video_filter,
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
            # A full cricket match can take several
            # hours to transcode on the Pi. Allow up to
            # 12 hours rather than killing a healthy
            # long-match conversion after one hour.
            timeout=43200,
        )

    except subprocess.TimeoutExpired:
        browser_result = None

        log(
            "Browser playback build timed out; "
            "4K master kept"
        )

    browser_valid = False

    if (
        browser_result is not None
        and browser_result.returncode == 0
        and browser_destination.exists()
        and browser_destination.stat().st_size > 0
    ):
        def video_duration(path):
            probe_result = subprocess.run(
                [
                    "/usr/bin/ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(path),
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=60,
            )

            if probe_result.returncode != 0:
                return 0.0

            try:
                return float(
                    probe_result.stdout.strip()
                )
            except ValueError:
                return 0.0

        master_duration = video_duration(
            destination
        )

        browser_duration = video_duration(
            browser_destination
        )

        log(
            "Full match durations: "
            f"master={master_duration:.1f}s, "
            f"browser={browser_duration:.1f}s"
        )

        # Allow a small difference for codec/container
        # timing, but reject clearly incomplete copies.
        minimum_duration = max(
            0.0,
            master_duration - 10.0,
        )

        browser_valid = (
            master_duration > 0
            and browser_duration >= minimum_duration
        )

        if browser_valid:
            log(
                "Browser playback copy ready: "
                f"{browser_destination}"
            )

            if args.browser_only:
                complete_file = Path(
                    "/var/lib/scoreos/"
                    "last-match-complete.json"
                )

                try:
                    if complete_file.exists():
                        complete_status = json.loads(
                            complete_file.read_text(
                                encoding="utf-8"
                            )
                        )

                        if (
                            complete_status.get(
                                "session_id"
                            )
                            == args.session
                        ):
                            complete_status[
                                "browser_video_processing"
                            ] = False

                            complete_status[
                                "browser_video_ready"
                            ] = True

                            complete_file.write_text(
                                json.dumps(
                                    complete_status,
                                    indent=2,
                                ) + "\n",
                                encoding="utf-8",
                            )

                            log(
                                "Browser processing status "
                                "marked complete"
                            )

                except (
                    OSError,
                    json.JSONDecodeError,
                ) as exc:
                    log(
                        "Unable to update browser "
                        "completion status: "
                        f"{exc}"
                    )
        else:
            log(
                "Browser playback copy failed duration "
                "validation; incomplete copy removed"
            )

    if not browser_valid:
        browser_destination.unlink(
            missing_ok=True
        )

        if (
            browser_result is not None
            and browser_result.returncode != 0
        ):
            log(
                "Unable to build browser playback copy: "
                + (
                    browser_result.stderr.strip()
                    or "FFmpeg failed"
                )
            )

        if args.browser_only:
            complete_file = Path(
                "/var/lib/scoreos/"
                "last-match-complete.json"
            )

            try:
                if complete_file.exists():
                    complete_status = json.loads(
                        complete_file.read_text(
                            encoding="utf-8"
                        )
                    )

                    if (
                        complete_status.get(
                            "session_id"
                        )
                        == args.session
                    ):
                        complete_status[
                            "browser_video_processing"
                        ] = False

                        complete_status[
                            "browser_video_ready"
                        ] = False

                        complete_status[
                            "browser_video_error"
                        ] = (
                            "Scored video build failed. "
                            "Raw recording segments retained."
                        )

                        complete_file.write_text(
                            json.dumps(
                                complete_status,
                                indent=2,
                            ) + "\n",
                            encoding="utf-8",
                        )

            except (
                OSError,
                json.JSONDecodeError,
            ) as exc:
                log(
                    "Unable to update failed browser "
                    "build status: "
                    f"{exc}"
                )

        log(
            "Raw recording segments retained because "
            "browser build did not complete successfully"
        )

        return 4


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
