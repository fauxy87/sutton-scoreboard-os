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

    if use_substream:
        if path.endswith("_main"):
            path = (
                path[:-5]
                + "_sub"
            )
        else:
            path = "/h264Preview_01_sub"

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


def preview_command(rtsp_url):
    return [
        "/usr/bin/ffmpeg",

        "-hide_banner",
        "-loglevel",
        "error",

        "-rtsp_transport",
        "tcp",

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


def stream_works(rtsp_url):
    command = [
        "/usr/bin/ffprobe",
        "-v",
        "error",
        "-rtsp_transport",
        "tcp",
        "-rw_timeout",
        "5000000",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=codec_name",
        "-of",
        "default=noprint_wrappers=1",
        rtsp_url,
    ]

    try:
        result = subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=7,
            check=False,
        )

        return result.returncode == 0

    except (
        subprocess.TimeoutExpired,
        OSError,
    ):
        return False


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

    substream_url = build_rtsp_url(
        use_substream=True
    )

    mainstream_url = build_rtsp_url(
        use_substream=False
    )

    # Prefer the lower-bandwidth substream for the TV
    # preview. If the Reolink substream is unavailable,
    # automatically fall back to the configured main stream.
    if stream_works(substream_url):
        rtsp_url = substream_url
    elif stream_works(mainstream_url):
        rtsp_url = mainstream_url
    else:
        raise RuntimeError(
            "Camera preview stream unavailable."
        )

    return subprocess.Popen(
        preview_command(rtsp_url),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
    )
