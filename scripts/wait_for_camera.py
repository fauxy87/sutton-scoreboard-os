#!/usr/bin/env python3

import json
import subprocess
import sys
import time

from pathlib import Path
from urllib.parse import quote

CONFIG = Path("/etc/scoreos/camera.json")
WAIT_MARKER = Path(
    "/run/scoreos/camera-startup-wait-done"
)

WAIT_SECONDS = 90
RETRY_SECONDS = 5


def log(message):
    print(
        time.strftime("%Y-%m-%d %H:%M:%S"),
        message,
        flush=True,
    )


def load_camera():
    if not CONFIG.exists():
        return None

    try:
        camera = json.loads(
            CONFIG.read_text(
                encoding="utf-8"
            )
        )
    except (
        OSError,
        json.JSONDecodeError,
    ):
        return None

    if not camera.get("enabled", True):
        return None

    if (
        not camera.get("host")
        or not camera.get("username")
        or not camera.get("rtsp_path")
    ):
        return None

    return camera


def rtsp_url(camera):
    username = quote(
        str(camera.get("username", "")),
        safe="",
    )

    password = quote(
        str(camera.get("password", "")),
        safe="",
    )

    host = camera["host"]
    port = int(
        camera.get("port", 554)
    )

    path = str(
        camera.get(
            "rtsp_path",
            "/h264Preview_01_main",
        )
    )

    if not path.startswith("/"):
        path = "/" + path

    return (
        f"rtsp://{username}:{password}"
        f"@{host}:{port}{path}"
    )


def camera_ready(url):
    try:
        result = subprocess.run(
            [
                "/usr/bin/ffprobe",
                "-v",
                "error",
                "-rtsp_transport",
                "tcp",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=codec_name,width,height",
                "-of",
                "default=noprint_wrappers=1",
                url,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=8,
            check=False,
        )

        return result.returncode == 0

    except subprocess.TimeoutExpired:
        return False


def main():
    if WAIT_MARKER.exists():
        log(
            "Camera startup wait already completed "
            "for this boot"
        )
        return 0

    WAIT_MARKER.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    camera = load_camera()

    if not camera:
        WAIT_MARKER.touch()
        log(
            "Camera not configured; "
            "continuing SCOREOS startup"
        )
        return 0

    log(
        "Waiting for camera RTSP stream "
        f"at {camera['host']}"
    )

    deadline = (
        time.monotonic()
        + WAIT_SECONDS
    )

    url = rtsp_url(camera)

    while time.monotonic() < deadline:
        if camera_ready(url):
            log(
                "Camera RTSP stream ready"
            )

            WAIT_MARKER.touch()
            return 0

        log(
            "Camera still starting; "
            f"retrying in {RETRY_SECONDS}s"
        )

        time.sleep(
            RETRY_SECONDS
        )

    log(
        "Camera was not ready within "
        f"{WAIT_SECONDS}s; starting buffer "
        "and allowing normal recovery retries"
    )

    WAIT_MARKER.touch()
    return 0


if __name__ == "__main__":
    sys.exit(main())
