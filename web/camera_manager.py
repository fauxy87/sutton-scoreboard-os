#!/usr/bin/env python3

import json
import socket
import subprocess
import time

from pathlib import Path
from urllib.parse import quote

CAMERA_CONFIG = Path("/etc/scoreos/camera.json")

CAMERA_START_GRACE_SECONDS = 45
CAMERA_REACHABLE_SINCE = None

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
    global CAMERA_REACHABLE_SINCE

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

    if reachable:
        if CAMERA_REACHABLE_SINCE is None:
            CAMERA_REACHABLE_SINCE = time.time()
    else:
        CAMERA_REACHABLE_SINCE = None

    camera_starting = bool(
        reachable
        and CAMERA_REACHABLE_SINCE is not None
        and (
            time.time()
            - CAMERA_REACHABLE_SINCE
        ) < CAMERA_START_GRACE_SECONDS
    )

    def service_active(name):
        result = subprocess.run(
            [
                "/usr/bin/systemctl",
                "is-active",
                name,
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        return (
            result.stdout.strip() == "active"
        )

    recorder_service = service_active(
        "scoreos-camera-recorder.service"
    )

    buffer_service = service_active(
        "scoreos-camera-buffer.service"
    )

    highlight_worker = service_active(
        "scoreos-highlight-worker.service"
    )

    buffering = False

    if buffer_service:
        buffer_root = Path(
            "/var/lib/scoreos/camera-buffer"
        )

        newest_buffer = 0

        if buffer_root.exists():
            for segment in buffer_root.glob("*.ts"):
                try:
                    stat = segment.stat()

                    if stat.st_size > 0:
                        newest_buffer = max(
                            newest_buffer,
                            stat.st_mtime,
                        )
                except OSError:
                    continue

        if newest_buffer:
            buffering = (
                time.time() - newest_buffer
                < 20
            )

    recording = False

    if recorder_service:
        match_file = Path(
            "/var/lib/scoreos/current-match.json"
        )

        if match_file.exists():
            try:
                session = json.loads(
                    match_file.read_text(
                        encoding="utf-8"
                    )
                )

                session_id = str(
                    session.get(
                        "session_id",
                        "",
                    )
                ).strip()

                started_iso = str(
                    session.get(
                        "started_iso",
                        "",
                    )
                )

                match_date = (
                    started_iso[:10]
                    if len(started_iso) >= 10
                    else None
                )

                if session_id and match_date:
                    folder = (
                        Path(
                            "/var/lib/scoreos/recordings"
                        )
                        / match_date
                        / session_id
                    )

                    newest = 0

                    for stream_name in (
                        "main",
                        "full",
                    ):
                        stream_folder = (
                            folder / stream_name
                        )

                        if not stream_folder.exists():
                            continue

                        for segment in (
                            stream_folder.glob("*.ts")
                        ):
                            try:
                                stat = segment.stat()

                                if stat.st_size > 0:
                                    newest = max(
                                        newest,
                                        stat.st_mtime,
                                    )
                            except OSError:
                                continue

                    if newest:
                        recording = (
                            time.time() - newest
                            < 30
                        )

            except (
                OSError,
                json.JSONDecodeError,
            ):
                pass

    # A reachable RTSP port alone does not prove that
    # video is actually flowing. Fresh pre-roll segments
    # prove video health before a match; fresh recording
    # segments prove it while a match is active.
    video_live = bool(
        reachable
        and (
            recording
            or buffering
        )
    )

    video_stalled = bool(
        reachable
        and not video_live
    )

    if not configured:
        state = "not_configured"
    elif not reachable:
        state = "offline"
    elif recording:
        state = "recording"
    elif buffering:
        state = "ready"
    elif camera_starting:
        state = "starting"
    elif recorder_service:
        state = "reconnecting"
    else:
        state = "stalled"

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
        "recording": recording,
        "video_live": video_live,
        "video_stalled": video_stalled,
        "camera_starting": camera_starting,
        "startup_grace_seconds": CAMERA_START_GRACE_SECONDS,
        "recorder_service": recorder_service,
        "buffer_service": buffer_service,
        "buffering": buffering,
        "highlight_worker": highlight_worker,
        "state": state,
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
