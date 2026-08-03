#!/usr/bin/env python3

import json
import socket
import subprocess

from pathlib import Path
from urllib.parse import quote

CAMERA_CONFIG = Path("/etc/scoreos/camera.json")

DEFAULT_CAMERA = {
    "enabled": False,
    "name": "Reolink Camera",
    "host": "",
    "port": 554,
    "username": "",
    "password": "",
    "rtsp_path": "/h264Preview_01_main",
}


def load():
    camera = DEFAULT_CAMERA.copy()

    if CAMERA_CONFIG.exists():
        try:
            saved = json.loads(
                CAMERA_CONFIG.read_text(encoding="utf-8")
            )

            if isinstance(saved, dict):
                camera.update(saved)

        except (OSError, json.JSONDecodeError):
            pass

    return camera


def save(settings):
    camera = load()

    for key in DEFAULT_CAMERA:
        if key in settings:
            camera[key] = settings[key]

    CAMERA_CONFIG.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    CAMERA_CONFIG.write_text(
        json.dumps(camera, indent=2) + "\n",
        encoding="utf-8",
    )

    return camera


def status():
    camera = load()

    configured = bool(
        camera.get("host")
        and camera.get("username")
        and camera.get("rtsp_path")
    )

    reachable = False
    error = None

    if configured:
        try:
            with socket.create_connection(
                (
                    camera["host"],
                    int(camera.get("port", 554)),
                ),
                timeout=2,
            ):
                reachable = True

        except OSError as exc:
            error = str(exc)

    return {
        "configured": configured,
        "connected": reachable,
        "reachable": reachable,
        "online": reachable,
        "enabled": bool(camera.get("enabled")),
        "name": camera.get("name"),
        "host": camera.get("host"),
        "port": camera.get("port"),
        "rtsp_path": camera.get("rtsp_path"),
        "recording": False,
        "error": error,
    }
def test_stream():
    camera = load()

    configured = bool(
        camera.get("host")
        and camera.get("username")
        and camera.get("rtsp_path")
    )

    if not configured:
        return {
            "ok": False,
            "connected": False,
            "error": "Camera is not fully configured.",
        }

    username = quote(
        str(camera.get("username", "")),
        safe="",
    )

    password = quote(
        str(camera.get("password", "")),
        safe="",
    )

    host = str(camera.get("host", "")).strip()
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

    rtsp_url = (
        f"rtsp://{auth}{host}:{port}{path}"
    )

    command = [
        "/usr/bin/ffprobe",
        "-v",
        "error",
        "-rtsp_transport",
        "tcp",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=codec_name,width,height,avg_frame_rate",
        "-of",
        "json",
        rtsp_url,
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=12,
            check=False,
        )

    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "connected": False,
            "error": "Camera stream test timed out.",
        }

    except OSError as exc:
        return {
            "ok": False,
            "connected": False,
            "error": str(exc),
        }

    if result.returncode != 0:
        error = result.stderr.strip()

        return {
            "ok": False,
            "connected": False,
            "error": (
                error
                or "Unable to open the RTSP stream."
            ),
        }

    try:
        stream_info = json.loads(result.stdout)
    except json.JSONDecodeError:
        stream_info = {}

    streams = stream_info.get("streams", [])
    stream = streams[0] if streams else {}

    return {
        "ok": True,
        "connected": True,
        "message": "RTSP stream opened successfully.",
        "stream": {
            "codec": stream.get("codec_name"),
            "width": stream.get("width"),
            "height": stream.get("height"),
            "frame_rate": stream.get("avg_frame_rate"),
        },
    }
