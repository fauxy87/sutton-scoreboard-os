#!/usr/bin/env python3

import subprocess
from urllib.parse import quote

import camera_manager


def build_rtsp_url(use_substream=True):
    camera = camera_manager.load()

    host = str(camera.get("host", "")).strip()
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

    auth = username

    if password:
        auth += ":" + password

    if auth:
        auth += "@"

    return (
        f"rtsp://{auth}{host}:{port}{path}"
    )


def start_preview():
    camera = camera_manager.load()

    if not camera.get("enabled"):
        raise RuntimeError(
            "Camera is disabled."
        )

    if not camera.get("host"):
        raise RuntimeError(
            "Camera is not configured."
        )

    rtsp_url = build_rtsp_url(
        use_substream=True
    )

    command = [
        "/usr/bin/ffmpeg",

        "-hide_banner",
        "-loglevel",
        "error",

        "-rtsp_transport",
        "tcp",

        # Do not leave the TV showing a frozen frame forever
        # if the RTSP connection stops delivering data.
        "-rw_timeout",
        "8000000",

        "-i",
        rtsp_url,

        "-an",

        "-vf",
        "fps=8,scale=960:-2",

        "-q:v",
        "6",

        "-f",
        "mpjpeg",

        "-boundary_tag",
        "scoreosframe",

        "pipe:1",
    ]

    return subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
    )
