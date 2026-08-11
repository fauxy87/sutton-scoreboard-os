#!/usr/bin/env python3

import json
import subprocess
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

CAMERA_CONFIG = Path("/etc/scoreos/camera.json")
BUFFER_ROOT = Path("/var/lib/scoreos/camera-buffer")

KEEP_SECONDS = 40


def log(message):
    print(
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        message,
        flush=True,
    )


def camera_url():
    camera = json.loads(
        CAMERA_CONFIG.read_text(
            encoding="utf-8"
        )
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

    return (
        f"rtsp://{auth}{host}:{port}"
        "/h264Preview_01_sub"
    )


def cleanup():
    cutoff = time.time() - KEEP_SECONDS

    files = []

    for path in BUFFER_ROOT.glob("*.ts"):
        try:
            stat = path.stat()
        except OSError:
            continue

        files.append(
            (
                stat.st_mtime,
                path,
            )
        )

    files.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    # Never delete the newest few files.
    # One of these may still be open by FFmpeg.
    protected = {
        path
        for _, path in files[:3]
    }

    for modified, path in files:
        if path in protected:
            continue

        if modified >= cutoff:
            continue

        try:
            path.unlink()
        except OSError:
            continue


def run_buffer():
    BUFFER_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    pattern = str(
        BUFFER_ROOT
        / "%Y-%m-%d_%H-%M-%S.ts"
    )

    command = [
        "/usr/bin/ffmpeg",
        "-hide_banner",
        "-loglevel",
        "warning",
        "-rtsp_transport",
        "tcp",
        "-i",
        camera_url(),
        "-map",
        "0:v:0",
        "-c",
        "copy",
        "-f",
        "segment",
        "-segment_time",
        "5",
        "-segment_format",
        "mpegts",
        "-reset_timestamps",
        "1",
        "-strftime",
        "1",
        pattern,
    ]

    log("Starting 40-second camera pre-roll buffer")

    process = subprocess.Popen(command)

    while True:
        code = process.poll()

        if code is not None:
            return code

        cleanup()
        time.sleep(3)


def main():
    while True:
        try:
            code = run_buffer()

            log(
                f"Pre-roll FFmpeg stopped with "
                f"code {code}; restarting in 5 seconds"
            )

        except Exception as exc:
            log(f"Pre-roll buffer error: {exc}")

        time.sleep(5)


if __name__ == "__main__":
    main()
