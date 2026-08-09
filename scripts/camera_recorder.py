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


def load_camera():
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

    path = str(
        camera.get(
            "rtsp_path",
            "/h264Preview_01_main",
        )
    )

    if not path.startswith("/"):
        path = "/" + path

    if not host:
        raise RuntimeError("Camera host is missing")

    auth = username

    if password:
        auth += ":" + password

    if auth:
        auth += "@"

    return (
        f"rtsp://{auth}{host}:{port}{path}"
    )


def recording_pattern():
    day_folder = RECORDING_ROOT / datetime.now().strftime(
        "%Y-%m-%d"
    )

    day_folder.mkdir(
        parents=True,
        exist_ok=True,
    )

    return str(
        day_folder /
        "%Y-%m-%d_%H-%M-%S.mp4"
    )


def run_recorder():
    rtsp_url = load_camera()
    output_pattern = recording_pattern()

    command = [
        "/usr/bin/ffmpeg",
        "-hide_banner",
        "-loglevel",
        "warning",
        "-rtsp_transport",
        "tcp",
        "-i",
        rtsp_url,
        "-map",
        "0:v:0",
        "-c",
        "copy",
        "-f",
        "segment",
        "-segment_time",
        "300",
        "-reset_timestamps",
        "1",
        "-strftime",
        "1",
        output_pattern,
    ]

    log("Starting camera recorder")

    return subprocess.run(
        command,
        check=False,
    ).returncode


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
