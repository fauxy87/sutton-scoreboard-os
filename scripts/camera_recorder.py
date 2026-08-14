#!/usr/bin/env python3

import json
import subprocess
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

CAMERA_CONFIG = Path("/etc/scoreos/camera.json")
RECORDING_ROOT = Path("/var/lib/scoreos/recordings")
LOG_FILE = Path("/var/log/scoreos-camera-recorder.log")
MATCH_FILE = Path("/var/lib/scoreos/current-match.json")


def log(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{timestamp} {message}"

    print(line, flush=True)

    LOG_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with LOG_FILE.open(
        "a",
        encoding="utf-8",
    ) as handle:
        handle.write(line + "\n")


def load_camera_paths():
    if not CAMERA_CONFIG.exists():
        raise RuntimeError(
            f"Camera config not found: {CAMERA_CONFIG}"
        )

    camera = json.loads(
        CAMERA_CONFIG.read_text(encoding="utf-8")
    )

    host = str(
        camera.get("host")
        or camera.get("ip")
        or ""
    ).strip()

    username = quote(
        str(camera.get("username", "")),
        safe="",
    )

    password = quote(
        str(camera.get("password", "")),
        safe="",
    )

    port = int(camera.get("port", 554))

    if not host:
        raise RuntimeError("Camera host is missing")

    auth = username

    if password:
        auth += ":" + password

    if auth:
        auth += "@"

    main_path = str(
        camera.get(
            "rtsp_path",
            "/h264Preview_01_main",
        )
    )

    if not main_path.startswith("/"):
        main_path = "/" + main_path

    # Use the configured working RTSP path for both
    # recorder inputs. Some Reolink models do not expose
    # /h264Preview_01_sub and return 404 for that stream.
    sub_path = main_path

    base = f"rtsp://{auth}{host}:{port}"

    return (
        base + main_path,
        base + sub_path,
    )


def recording_patterns():
    if not MATCH_FILE.exists():
        raise RuntimeError(
            "No active match session."
        )

    session = json.loads(
        MATCH_FILE.read_text(
            encoding="utf-8"
        )
    )

    session_id = str(
        session.get("session_id", "")
    ).strip()

    if not session_id:
        raise RuntimeError(
            "Match session ID is missing."
        )

    session_folder = (
        RECORDING_ROOT
        / datetime.now().strftime("%Y-%m-%d")
        / session_id
    )

    main_folder = session_folder / "main"
    full_folder = session_folder / "full"

    main_folder.mkdir(
        parents=True,
        exist_ok=True,
    )

    full_folder.mkdir(
        parents=True,
        exist_ok=True,
    )

    main_pattern = str(
        main_folder
        / "%Y-%m-%d_%H-%M-%S.ts"
    )

    full_pattern = str(
        full_folder
        / "%Y-%m-%d_%H-%M-%S.ts"
    )

    return main_pattern, full_pattern


def run_recorder():
    main_url, sub_url = load_camera_paths()
    main_pattern, full_pattern = recording_patterns()

    command = [
        "/usr/bin/ffmpeg",
        "-hide_banner",
        "-loglevel",
        "warning",

        "-rtsp_transport",
        "tcp",
        "-i",
        main_url,

        "-rtsp_transport",
        "tcp",
        "-i",
        sub_url,

        "-map",
        "0:v:0",
        "-c",
        "copy",
        "-f",
        "segment",
        "-segment_time",
        "10",
        "-segment_format",
        "mpegts",
        "-reset_timestamps",
        "1",
        "-strftime",
        "1",
        main_pattern,

        "-map",
        "1:v:0",
        "-c",
        "copy",
        "-f",
        "segment",
        "-segment_time",
        "10",
        "-segment_format",
        "mpegts",
        "-reset_timestamps",
        "1",
        "-strftime",
        "1",
        full_pattern,
    ]

    log(
        "Starting dual-stream camera recorder "
        "(4K highlights + H.264 full match)"
    )

    process = subprocess.Popen(
        command,
    )

    main_folder = Path(main_pattern).parent
    full_folder = Path(full_pattern).parent

    startup_time = time.time()
    last_activity = startup_time

    def newest_segment_mtime(folder):
        newest = 0

        try:
            for segment in folder.glob("*.ts"):
                try:
                    newest = max(
                        newest,
                        segment.stat().st_mtime,
                    )
                except OSError:
                    continue
        except OSError:
            pass

        return newest

    while True:
        return_code = process.poll()

        if return_code is not None:
            return return_code

        newest = max(
            newest_segment_mtime(main_folder),
            newest_segment_mtime(full_folder),
        )

        if newest > last_activity:
            last_activity = newest

        now = time.time()

        # Allow plenty of time for the initial RTSP
        # connection and first keyframe.
        grace_period = (
            60
            if now - startup_time < 60
            else 40
        )

        if now - last_activity > grace_period:
            log(
                "Recording stream stalled for "
                f"{int(now - last_activity)} seconds; "
                "restarting FFmpeg"
            )

            process.terminate()

            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()

            return 99

        time.sleep(5)


def main():
    while True:
        try:
            return_code = run_recorder()

            log(
                f"Recorder stopped with code "
                f"{return_code}; restarting in 5 seconds"
            )

        except Exception as exc:
            log(f"Recorder error: {exc}")

        time.sleep(5)


if __name__ == "__main__":
    main()
