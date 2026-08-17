#!/usr/bin/env python3

import json
import re
import os
import shutil
import socket
import subprocess
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from startup import startup_manager
import bluetooth_manager
from urllib.parse import urlparse
import camera_manager
import camera_stream

STATE_FILE = Path("/run/scoreos/state.json")
CONTROL_SOCKET = "/run/scoreos/control.sock"
DIAGNOSTICS_FILE = Path("/run/scoreos/diagnostics.json")

HOST = "0.0.0.0"
PORT = 8080


DEFAULT_STATE = {
    "total": "--0",
    "wickets": "0",
    "overs": "-0",
    "target": "---",
    "Bat1Name": "-",
    "BatAscore": "--0",
    "BatABallsFaced": "-",
    "Bat2Name": "-",
    "BatBscore": "--0",
    "BatBBallsFaced": "-",
    "BatTeamName": "Waiting for Play-Cricket",
    "FieldTeamName": "-",
    "CurrentOver": "-",
    "PshipTOT": "0",
    "LastWicket": "---",
    "mode": "playcricket",
}


def read_state():
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return {**DEFAULT_STATE, **state}
    except Exception:
        return DEFAULT_STATE.copy()


def send_engine_control(request):
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(5)

    try:
        client.connect(CONTROL_SOCKET)
        client.sendall(json.dumps(request).encode("utf-8"))

        chunks = []

        while True:
            data = client.recv(4096)
            if not data:
                break

            chunks.append(data)

            if len(data) < 4096:
                break

        if not chunks:
            raise RuntimeError("No response from SCOREOS engine")

        return json.loads(b"".join(chunks).decode("utf-8"))

    finally:
        client.close()


def run_command(command, timeout=4):
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
            check=False,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def service_status(service_name):
    output = run_command([
        "/usr/bin/systemctl",
        "is-active",
        service_name,
    ])

    return output if output else "unknown"


def cpu_temperature():
    thermal_file = Path(
        "/sys/class/thermal/thermal_zone0/temp"
    )

    try:
        value = int(thermal_file.read_text().strip())
        return round(value / 1000, 1)
    except Exception:
        return None


def memory_status():
    try:
        values = {}

        for line in Path("/proc/meminfo").read_text().splitlines():
            key, value = line.split(":", 1)
            values[key] = int(value.strip().split()[0])

        total = values.get("MemTotal", 0)
        available = values.get("MemAvailable", 0)
        used = max(total - available, 0)

        if total <= 0:
            return {
                "used_percent": None,
                "used_mb": None,
                "total_mb": None,
            }

        return {
            "used_percent": round((used / total) * 100, 1),
            "used_mb": round(used / 1024),
            "total_mb": round(total / 1024),
        }

    except Exception:
        return {
            "used_percent": None,
            "used_mb": None,
            "total_mb": None,
        }


def format_uptime():
    try:
        seconds = int(float(
            Path("/proc/uptime").read_text().split()[0]
        ))
    except Exception:
        return "Unknown"

    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)

    if days:
        return f"{days}d {hours}h {minutes}m"

    if hours:
        return f"{hours}h {minutes}m"

    return f"{minutes}m {seconds}s"


def network_status():
    device_output = run_command([
        "/usr/bin/nmcli",
        "-t",
        "-f",
        "DEVICE,TYPE,STATE,CONNECTION",
        "device",
        "status",
    ])

    devices = {}

    for line in device_output.splitlines():
        protected = line.replace(r"\:", "__COLON__")
        parts = protected.split(":", 3)

        if len(parts) != 4:
            continue

        device, device_type, state, connection = [
            part.replace("__COLON__", ":")
            for part in parts
        ]

        devices[device] = {
            "type": device_type,
            "state": state,
            "connection": connection,
        }

    ip_output = run_command([
        "/usr/bin/hostname",
        "-I",
    ])

    addresses = [
        address
        for address in ip_output.split()
        if "." in address
    ]

    hotspot = devices.get("wlan0", {})

    return {
        "devices": devices,
        "addresses": addresses,
        "hotspot_active": (
            hotspot.get("connection") == "SCOREOS-Hotspot"
        ),
        "hotspot_address": (
            "192.168.4.1"
            if hotspot.get("connection") == "SCOREOS-Hotspot"
            else None
        ),
    }


RSSI_CACHE = {"mac": None, "value": None, "quality": None, "time": 0}
RSSI_CACHE_SECONDS = 10

def bluetooth_status():
    bluetooth_service = service_status("bluetooth.service")
    global RSSI_CACHE

    preferred_adapter_mac = "18:69:45:F3:58:B9"
    preferred_adapter_present = False
    preferred_adapter_name = None

    bluetooth_root = Path("/sys/class/bluetooth")

    if bluetooth_root.exists():
        for adapter_path in bluetooth_root.glob("hci*"):
            try:
                output = run_command([
                    "/usr/bin/hciconfig",
                    adapter_path.name,
                ])

                if preferred_adapter_mac in output.upper():
                    preferred_adapter_present = True
                    preferred_adapter_name = adapter_path.name
                    break

            except Exception:
                continue
    advert_service = service_status(
        "sutton-scoreboard-advert.service"
    )

    show_output = run_command([
        "/usr/bin/bluetoothctl",
        "show",
    ])

    mgmt_info = ""
    advert_info = ""

    name = "Unknown"
    powered = False
    rssi = None
    signal_quality = None

    # bluetoothctl normally works without sudo and reports:
    # Name: SCOREOS
    # Powered: yes
    for line in show_output.splitlines():
        stripped = line.strip()

        if stripped.startswith("Name:"):
            name = stripped.split(":", 1)[1].strip()

        elif stripped.startswith("Powered:"):
            powered = (
                stripped.split(":", 1)[1].strip().lower()
                == "yes"
            )

    # Fall back to btmgmt if bluetoothctl did not provide a name.
    if name == "Unknown":
        for line in mgmt_info.splitlines():
            stripped = line.strip()

            if stripped.startswith("name "):
                name = stripped[5:].strip()
                break

    # Fall back to btmgmt current settings for powered status.
    if not powered:
        for line in mgmt_info.splitlines():
            stripped = line.strip().lower()

            if stripped.startswith("current settings:"):
                settings = stripped.split(":", 1)[1].split()
                powered = "powered" in settings
                break

    advertising = False

    for line in advert_info.splitlines():
        stripped = line.strip().lower()

        if stripped.startswith("instances list with"):
            try:
                count = int(stripped.split()[3])
                advertising = count > 0
            except (ValueError, IndexError):
                advertising = "with 0 item" not in stripped
            break

    # If btmgmt cannot be queried by the web-service user,
    # retain the advertising-service result as a fallback.
    if not advert_info:
        advertising = advert_service == "active"
    connected_device = {
        "name": None,
        "alias": None,
        "mac": None,
    }

    connected_output = run_command([
        "/usr/bin/bluetoothctl",
        "info",
    ])

    for line in connected_output.splitlines():
        stripped = line.strip()

        if stripped.startswith("Device "):
            parts = stripped.split()

            if len(parts) >= 2:
                connected_device["mac"] = parts[1]

        elif stripped.startswith("Name:"):
            connected_device["name"] = (
                stripped.split(":", 1)[1].strip()
            )

        elif stripped.startswith("Alias:"):
            connected_device["alias"] = (
                stripped.split(":", 1)[1].strip()
            )

    # # if connected_device["mac"]:
##        rssi_output = run_command([
##            "/usr/bin/btmgmt",
##            "--index",
##            "1",
##            "conn-info",
##            "-t",
##            "2",
##            connected_device["mac"],
##        ])
##
##        match = re.search(r"RSSI\s+(-?\d+)", rssi_output)
##
##        if match:
##            rssi = int(match.group(1))
##
##            if rssi >= -60:
##                signal_quality = "Excellent"
##            elif rssi >= -70:
##                signal_quality = "Good"
##            elif rssi >= -80:
##                signal_quality = "Fair"
##            else:
##                signal_quality = "Poor"

    diagnostics = read_diagnostics().get(
        "bluetooth",
        {}
    )

    adapter_status = {
        "preferred_mac": preferred_adapter_mac,
        "preferred_present": preferred_adapter_present,
        "preferred_name": preferred_adapter_name,
    }

    return {
        "preferred_adapter": adapter_status,
        "service": bluetooth_service,
        "advert_service": advert_service,
        "name": name,
        "powered": powered,
        "advertising": advertising,
        "connected": diagnostics.get("connected", False),
        "connected_since": diagnostics.get("connected_since"),
        "service_started": diagnostics.get("service_started"),
        "waiting_for_first_packet": diagnostics.get(
           "waiting_for_first_packet",
            True ,
        ),
        "last_packet": diagnostics.get("last_packet"),
        "last_packet_iso": diagnostics.get("last_packet_iso"),
        "packet_count": diagnostics.get("packet_count", 0),
        "reconnects": diagnostics.get("reconnects", 0),
                "device_name": (
            diagnostics.get("device_name")
            or connected_device["name"]
        ),
        "device_alias": (
            diagnostics.get("device_alias")
            or connected_device["alias"]
        ),
        "device_mac": (
            diagnostics.get("device_mac")
            or connected_device["mac"]
        ),
        "device_icon": diagnostics.get("device_icon"),
        "battery": diagnostics.get("battery"),
        "rssi": diagnostics.get("rssi") or rssi,
        "signal_quality": signal_quality,
    }

def arduino_status():
    candidates = sorted(
        Path("/dev/serial/by-id").glob("*")
    ) if Path("/dev/serial/by-id").exists() else []

    if candidates:
        return {
            "connected": True,
            "device": str(candidates[0]),
        }

    for candidate in (
        "/dev/ttyACM0",
        "/dev/ttyUSB0",
    ):
        if Path(candidate).exists():
            return {
                "connected": True,
                "device": candidate,
            }

    return {
        "connected": False,
        "device": None,
    }


def system_snapshot():
    state = read_state()
    memory = memory_status()
    network = network_status()
    disk = shutil.disk_usage("/")

    try:
        last_update_age = max(
            time.time() - STATE_FILE.stat().st_mtime,
            0,
        )
    except Exception:
        last_update_age = None

    return {
        "version": "1.1.0",
        "hostname": run_command([
            "/usr/bin/hostname",
        ]) or "Unknown",
        "services": {
            "scoreboard": service_status(
                "sutton-scoreboard.service"
            ),
            "advertisement": service_status(
                "sutton-scoreboard-advert.service"
            ),
            "web": service_status(
                "scoreos-web.service"
            ),
        },
        "bluetooth": bluetooth_status(),
        "arduino": arduino_status(),
        "network": network,
        "temperature_c": cpu_temperature(),
        "memory": memory,
        "disk": {
            "free_gb": round(
                disk.free / (1024 ** 3),
                1,
            ),
            "total_gb": round(
                disk.total / (1024 ** 3),
                1,
            ),
        },
        "uptime": format_uptime(),
        "match": state,
        "last_update_age": (
            round(last_update_age, 1)
            if last_update_age is not None
            else None
        ),
    }

def redact_diagnostics_text(text):
    """Remove credentials before logs reach the browser."""
    text = str(text or "")

    # Redact passwords embedded in RTSP URLs.
    text = re.sub(
        r"(rtsp://[^:@\s/]+:)[^@\s/]+(@)",
        r"\g<1>********\g<2>",
        text,
        flags=re.IGNORECASE,
    )

    # Redact common password-style fields.
    text = re.sub(
        r'("password"\s*:\s*")[^"]*(")',
        r"\g<1>********\g<2>",
        text,
        flags=re.IGNORECASE,
    )

    return text


def diagnostic_service_log(service_name, lines=80):
    try:
        result = subprocess.run(
            [
                "/usr/bin/journalctl",
                "-u",
                service_name,
                "-n",
                str(lines),
                "--no-pager",
                "--output=short-iso",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=10,
            check=False,
        )

        return redact_diagnostics_text(
            result.stdout.strip()
        )

    except Exception as exc:
        return (
            "Unable to read log: "
            + str(exc)
        )


def diagnostic_logs():
    services = {
        "scoreboard": "sutton-scoreboard.service",
        "bluetooth_watchdog":
            "scoreos-bluetooth-watchdog.service",
        "camera_buffer":
            "scoreos-camera-buffer.service",
        "camera_recorder":
            "scoreos-camera-recorder.service",
        "highlights":
            "scoreos-highlight-worker.service",
        "web": "scoreos-web.service",
    }

    return {
        key: diagnostic_service_log(service)
        for key, service in services.items()
    }


def diagnostic_report():
    system_data = system_snapshot()
    camera_data = camera_manager.status()

    match_file = Path(
        "/var/lib/scoreos/current-match.json"
    )

    match_session = None

    if match_file.exists():
        try:
            match_session = json.loads(
                match_file.read_text(
                    encoding="utf-8"
                )
            )
        except Exception as exc:
            match_session = {
                "error": str(exc)
            }

    report = {
        "generated_at": time.strftime(
            "%Y-%m-%dT%H:%M:%S"
        ),
        "system": system_data,
        "camera": camera_data,
        "match_session": match_session,
        "logs": diagnostic_logs(),
    }

    return redact_diagnostics_text(
        json.dumps(
            report,
            indent=2,
            default=str,
        )
    )


def read_diagnostics():
    try:
        data = json.loads(
            DIAGNOSTICS_FILE.read_text(encoding="utf-8")
        )

        if isinstance(data, dict):
            return data

    except Exception:
        pass

    return {}



def fix_scoreos():
    """
    Repair common SCOREOS match-day faults without
    unnecessarily restarting healthy components.
    """
    actions = []
    warnings = []
    failed = []

    system_data = system_snapshot()
    camera_data = camera_manager.status()

    services = system_data.get(
        "services",
        {}
    )

    bluetooth = system_data.get(
        "bluetooth",
        {}
    )

    preferred_adapter_present = bool(
        bluetooth.get(
            "preferred_adapter",
            {}
        ).get(
            "preferred_present"
        )
    )

    # Scoreboard engine
    if services.get("scoreboard") != "active":
        ok, message = admin_action(
            "restart_scoreboard"
        )

        if ok:
            actions.append(
                "Scoreboard restarted"
            )
        else:
            failed.append(
                "Scoreboard: " + message
            )

    # Bluetooth
    #
    # If the preferred USB adapter is physically absent,
    # restarting services cannot fix it.
    if not preferred_adapter_present:
        warnings.append(
            "Connect the SCOREOS USB Bluetooth adapter"
        )

    else:
        bluetooth_ready = bool(
            services.get("advertisement") == "active"
            and bluetooth.get("powered") is True
            and bluetooth.get("advertising") is True
        )

        if not bluetooth_ready:
            ok, message = admin_action(
                "restart_bluetooth"
            )

            if ok:
                actions.append(
                    "Bluetooth recovered"
                )
            else:
                failed.append(
                    "Bluetooth: " + message
                )

    # Highlight worker
    if (
        services.get("highlight_worker") != "active"
        and not camera_data.get(
            "highlight_worker"
        )
    ):
        ok, message = admin_action(
            "restart_highlights"
        )

        if ok:
            actions.append(
                "Highlights restarted"
            )
        else:
            failed.append(
                "Highlights: " + message
            )

    # Camera
    camera_live = bool(
        camera_data.get("video_live")
    )

    recording = bool(
        camera_data.get("recording")
    )

    if not camera_live:
        if recording:
            warnings.append(
                "Camera video problem detected, but automatic "
                "restart was blocked because match recording "
                "is active"
            )

        elif not camera_data.get("configured"):
            warnings.append(
                "Camera is not configured"
            )

        elif not camera_data.get("connected"):
            # Try recovery anyway. The camera may have just
            # dropped off the network.
            ok, message = admin_action(
                "restart_camera"
            )

            if ok:
                actions.append(
                    "Camera recovered"
                )
            else:
                warnings.append(
                    "Camera offline — check camera power "
                    "and network connection"
                )

        else:
            ok, message = admin_action(
                "restart_camera"
            )

            if ok:
                actions.append(
                    "Camera stream recovered"
                )
            else:
                failed.append(
                    "Camera: " + message
                )

    if failed:
        return {
            "ok": False,
            "status": "attention",
            "actions": actions,
            "warnings": warnings,
            "failed": failed,
            "message":
                "SCOREOS repair completed with errors",
        }

    if warnings:
        return {
            "ok": True,
            "status": "attention",
            "actions": actions,
            "warnings": warnings,
            "failed": [],
            "message":
                "SCOREOS checked — attention still required",
        }

    if actions:
        return {
            "ok": True,
            "status": "fixed",
            "actions": actions,
            "warnings": [],
            "failed": [],
            "message":
                "SCOREOS recovery completed",
        }

    return {
        "ok": True,
        "status": "ready",
        "actions": [],
        "warnings": [],
        "failed": [],
        "message":
            "SCOREOS is already healthy — no repairs needed",
    }


def safe_shutdown_status():
    """
    Decide whether SCOREOS can safely power off.
    Never allow shutdown while recording or while
    completed-match processing is still active.
    """
    recorder = subprocess.run(
        [
            "/usr/bin/systemctl",
            "is-active",
            "scoreos-camera-recorder.service",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    recording = (
        recorder.stdout.strip() == "active"
    )

    processing_file = Path(
        "/var/lib/scoreos/match-processing.json"
    )

    processing = None

    if processing_file.exists():
        try:
            processing = json.loads(
                processing_file.read_text(
                    encoding="utf-8"
                )
            )
        except (
            OSError,
            json.JSONDecodeError,
        ):
            processing = {
                "unknown": True
            }

    reasons = []

    if recording:
        reasons.append(
            "Match recording is still active"
        )

    if processing is not None:
        reasons.append(
            "Match processing is still running"
        )

    return {
        "ok": True,
        "safe": len(reasons) == 0,
        "recording": recording,
        "processing": processing,
        "reasons": reasons,
    }


def admin_action(action):
    if action == "shutdown":
        shutdown_status = (
            safe_shutdown_status()
        )

        if not shutdown_status["safe"]:
            return (
                False,
                "Shutdown blocked — "
                + " · ".join(
                    shutdown_status[
                        "reasons"
                    ]
                ),
            )

    # Use the same safe Bluetooth recovery routine as
    # Ground Control so both interfaces behave identically.
    if action == "restart_bluetooth":
        result = bluetooth_manager.restart_bluetooth()

        return (
            bool(result.get("ok")),
            result.get("message")
            or result.get("error")
            or "Bluetooth recovery started",
        )

    if action == "restart_highlights":
        result = subprocess.run(
            [
                "/usr/bin/systemctl",
                "restart",
                "scoreos-highlight-worker.service",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            return (
                False,
                result.stderr.strip()
                or "Unable to restart highlight worker.",
            )

        time.sleep(2)

        active = (
            subprocess.run(
                [
                    "/usr/bin/systemctl",
                    "is-active",
                    "--quiet",
                    "scoreos-highlight-worker.service",
                ],
                capture_output=True,
                text=True,
                check=False,
            ).returncode == 0
        )

        if not active:
            return (
                False,
                "Highlight worker did not stay running.",
            )

        return (
            True,
            "Highlight worker restarted successfully.",
        )

    if action == "restart_camera":
        camera_state = camera_manager.status()

        if camera_state.get("recording"):
            return (
                False,
                "Camera restart blocked while match recording is active.",
            )

        result = subprocess.run(
            [
                "/usr/bin/systemctl",
                "restart",
                "scoreos-camera-buffer.service",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            return (
                False,
                result.stderr.strip()
                or "Unable to restart camera buffer.",
            )

        time.sleep(4)

        stream_test = camera_manager.test_stream()

        if not stream_test.get("ok"):
            return (
                False,
                stream_test.get("error")
                or "Camera stream did not recover.",
            )

        return (
            True,
            "Camera recovered and stream verified.",
        )

    commands = {
        "restart_scoreboard": [
            "/usr/bin/sudo",
            "/usr/bin/systemctl",
            "restart",
            "sutton-scoreboard.service",
        ],
        "restart_web": [
            "/usr/bin/sudo",
            "/usr/bin/systemctl",
            "restart",
            "scoreos-web.service",
        ],
        "restart_advertising": [
            "/usr/bin/sudo",
            "/usr/bin/systemctl",
            "restart",
            "sutton-scoreboard-advert.service",
        ],
        "reboot": [
            "/usr/bin/sudo",
            "/usr/sbin/reboot",
        ],
        "shutdown": [
            "/usr/bin/sudo",
            "/usr/sbin/poweroff",
        ],
    }

    command = commands.get(action)

    if command is None:
        return False, "Unknown action"

    try:
        subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True, "Command started"
    except Exception as exc:
        return False, str(exc)


class ScoreboardHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/api/state":
            self.send_json(read_state())
            return

        if path == "/api/system":
            self.send_json(system_snapshot())
            return

        if path == "/api/shutdown/status":
            self.send_json(
                safe_shutdown_status()
            )
            return

        if path == "/api/diagnostics/logs":
            self.send_json(
                {
                    "ok": True,
                    "logs": diagnostic_logs(),
                }
            )
            return

        if path == "/api/diagnostics/report":
            report = diagnostic_report()
            payload = report.encode("utf-8")

            filename = (
                "scoreos-diagnostics-"
                + time.strftime("%Y%m%d-%H%M%S")
                + ".txt"
            )

            self.send_response(200)
            self.send_header(
                "Content-Type",
                "text/plain; charset=utf-8",
            )
            self.send_header(
                "Content-Disposition",
                'attachment; filename="'
                + filename
                + '"',
            )
            self.send_header(
                "Content-Length",
                str(len(payload)),
            )
            self.end_headers()

            self.wfile.write(payload)
            return

        if path == "/api/camera/status":
            self.send_json(camera_manager.status())
            return

        if path == "/api/camera/test":
            self.send_json(
                camera_manager.test_stream()
            )
            return

        if path == "/api/camera/preview":
            process = None

            try:
                process = camera_stream.start_preview()

                self.send_response(200)
                self.send_header(
                    "Content-Type",
                    "multipart/x-mixed-replace; "
                    "boundary=scoreosframe",
                )
                self.send_header(
                    "Cache-Control",
                    "no-store, no-cache, "
                    "must-revalidate",
                )
                self.send_header(
                    "Pragma",
                    "no-cache",
                )
                self.end_headers()

                while True:
                    chunk = process.stdout.read(16384)

                    if not chunk:
                        break

                    self.wfile.write(chunk)
                    self.wfile.flush()

            except (
                BrokenPipeError,
                ConnectionResetError,
            ):
                pass

            except Exception as exc:
                if not self.wfile.closed:
                    try:
                        self.send_json(
                            {
                                "ok": False,
                                "error": str(exc),
                            },
                            status=500,
                        )
                    except Exception:
                        pass

            finally:
                if (
                    process is not None
                    and process.poll() is None
                ):
                    process.terminate()

                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()

            return

        if path == "/api/camera/settings":
            camera = camera_manager.load()

            safe_camera = {
                **camera,
                "password": "",
                "password_saved": bool(camera.get("password")),
            }

            self.send_json(safe_camera)
            return

        if path == "/api/startup":
            snapshot = system_snapshot()

            startup = startup_manager.get_status()
            startup["bluetooth"] = snapshot["bluetooth"]
            startup["match"] = snapshot["match"]
            startup["network"] = snapshot["network"]

            self.send_json(startup)
            return

        if path == "/api/camera/settings":

            try:
                length = int(
                    self.headers.get(
                        "Content-Length",
                        "0"
                    )
                )

                body = self.rfile.read(length)

                settings = json.loads(
                    body.decode("utf-8")
                )

                camera = camera_manager.save(
                    settings
                )

                self.send_json(
                    {
                        "ok": True,
                        "camera": camera,
                    }
                )

            except Exception as exc:

                self.send_json(
                    {
                        "ok": False,
                        "error": str(exc),
                    },
                    status=500,
                )

            return


        if path == "/api/bluetooth":
            try:
                self.send_json(
                    bluetooth_manager.get_status()
                )
            except Exception as exc:
                self.send_json(
                    {
                        "ok": False,
                        "error": str(exc),
                    },
                    status=500,
                )
            return

        if path.startswith("/images/"):
            image_name = Path(path).name
            image_path = (
                Path(__file__).with_name("images")
                / image_name
            )

            if not image_path.exists():
                self.send_error(404, "Image not found")
                return

            content_type = "image/jpeg"

            if image_path.suffix.lower() == ".png":
                content_type = "image/png"
            elif image_path.suffix.lower() == ".webp":
                content_type = "image/webp"

            body = image_path.read_bytes()

            self.send_response(200)
            self.send_header(
                "Content-Type",
                content_type,
            )
            self.send_header(
                "Cache-Control",
                "public, max-age=3600",
            )
            self.send_header(
                "Content-Length",
                str(len(body)),
            )
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/api/match/status":
            match_file = Path(
                "/var/lib/scoreos/current-match.json"
            )

            session = None

            if match_file.exists():
                try:
                    session = json.loads(
                        match_file.read_text(
                            encoding="utf-8"
                        )
                    )
                except (
                    OSError,
                    json.JSONDecodeError,
                ):
                    session = None

            result = subprocess.run(
                [
                    "/usr/bin/systemctl",
                    "is-active",
                    "scoreos-camera-recorder.service",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            recording = (
                result.stdout.strip() == "active"
            )

            processing_file = Path(
                "/var/lib/scoreos/match-processing.json"
            )

            complete_file = Path(
                "/var/lib/scoreos/last-match-complete.json"
            )

            processing = None
            complete = None
            last_complete = None

            if processing_file.exists():
                try:
                    processing = json.loads(
                        processing_file.read_text(
                            encoding="utf-8"
                        )
                    )
                except (
                    OSError,
                    json.JSONDecodeError,
                ):
                    processing = None

            if complete_file.exists():
                try:
                    last_complete = json.loads(
                        complete_file.read_text(
                            encoding="utf-8"
                        )
                    )

                    complete = dict(
                        last_complete
                    )

                    completed_at = float(
                        complete.get(
                            "completed_at",
                            0,
                        )
                    )

                    # Keep MATCH COMPLETE visible
                    # for five minutes.
                    if (
                        not completed_at
                        or time.time() - completed_at > 300
                    ):
                        complete = None

                except (
                    OSError,
                    ValueError,
                    TypeError,
                    json.JSONDecodeError,
                ):
                    complete = None

            self.send_json(
                {
                    "ok": True,
                    "recording": recording,
                    "session": session,
                    "processing": processing,
                    "complete": complete,
                    "last_complete": last_complete,
                }
            )
            return

        if path == "/api/highlights":
            highlight_root = Path(
                "/var/lib/scoreos/highlights"
            )

            recording_root = Path(
                "/var/lib/scoreos/recordings"
            )

            matches = {}
            unassigned = []

            def get_match(session_id):
                if session_id not in matches:
                    matches[session_id] = {
                        "session_id": session_id,
                        "date": None,
                        "modified": 0,
                        "full_match": None,
                        "match_highlights": None,
                        "highlights": [],
                    }

                return matches[session_id]

            if highlight_root.exists():
                for clip in highlight_root.rglob("*.mp4"):
                    try:
                        stat = clip.stat()
                    except OSError:
                        continue

                    relative = clip.relative_to(
                        highlight_root
                    )

                    parts = clip.stem.split("_")

                    event_type = (
                        parts[2].upper()
                        if len(parts) >= 3
                        else "HIGHLIGHT"
                    )

                    item = {
                        "filename": clip.name,
                        "relative_path": str(relative),
                        "size_bytes": stat.st_size,
                        "modified": stat.st_mtime,
                        "event_type": event_type,
                        "video_url": (
                            "/highlights/video/"
                            + clip.name
                        ),
                        "download_url": (
                            "/highlights/download/"
                            + clip.name
                        ),
                    }

                    session_id = None

                    for parent in clip.parents:
                        if parent == highlight_root:
                            break

                        if parent.name.startswith(
                            "match-"
                        ):
                            session_id = parent.name
                            break

                    if session_id:
                        match = get_match(
                            session_id
                        )

                        match["modified"] = max(
                            match["modified"],
                            stat.st_mtime,
                        )

                        if relative.parts:
                            match["date"] = (
                                relative.parts[0]
                            )

                        if clip.name == "match-highlights.mp4":
                            item["event_type"] = "MATCH"
                            match["match_highlights"] = item
                        else:
                            match["highlights"].append(
                                item
                            )

                    else:
                        # Older clips created before
                        # match-session tagging.
                        unassigned.append(item)

            if recording_root.exists():
                for clip in recording_root.rglob(
                    "*/full/full-match.mp4"
                ):
                    try:
                        stat = clip.stat()
                    except OSError:
                        continue

                    session_folder = (
                        clip.parent.parent
                    )

                    session_id = (
                        session_folder.name
                    )

                    if not session_id.startswith(
                        "match-"
                    ):
                        continue

                    match = get_match(
                        session_id
                    )

                    try:
                        relative = (
                            session_folder.relative_to(
                                recording_root
                            )
                        )

                        if relative.parts:
                            match["date"] = (
                                relative.parts[0]
                            )

                    except ValueError:
                        pass

                    match["modified"] = max(
                        match["modified"],
                        stat.st_mtime,
                    )

                    match["full_match"] = {
                        "filename": clip.name,
                        "size_bytes": stat.st_size,
                        "modified": stat.st_mtime,
                        "session_id": session_id,
                        "video_url": (
                            "/recordings/video/"
                            + session_id
                        ),
                        "download_url": (
                            "/recordings/download/"
                            + session_id
                        ),
                    }

            if recording_root.exists():
                for metadata_path in recording_root.rglob(
                    "match-*/match.json"
                ):
                    try:
                        metadata = json.loads(
                            metadata_path.read_text(
                                encoding="utf-8"
                            )
                        )
                    except (
                        OSError,
                        json.JSONDecodeError,
                    ):
                        continue

                    session_id = metadata_path.parent.name

                    if not session_id.startswith(
                        "match-"
                    ):
                        continue

                    match = get_match(
                        session_id
                    )

                    match["home_team"] = metadata.get(
                        "home_team"
                    )

                    match["away_team"] = metadata.get(
                        "away_team"
                    )

                    match["match_name"] = metadata.get(
                        "match_name"
                    )

                    if not match.get("date"):
                        try:
                            relative = (
                                metadata_path.parent.relative_to(
                                    recording_root
                                )
                            )

                            if relative.parts:
                                match["date"] = (
                                    relative.parts[0]
                                )
                        except ValueError:
                            pass

            for match in matches.values():
                match["highlights"].sort(
                    key=lambda item: item["modified"],
                    reverse=True,
                )

                full_match_bytes = 0

                if match.get("full_match"):
                    full_match_bytes = int(
                        match["full_match"].get(
                            "size_bytes",
                            0,
                        )
                    )

                highlight_bytes = sum(
                    int(
                        item.get(
                            "size_bytes",
                            0,
                        )
                    )
                    for item in match["highlights"]
                )

                if match.get("match_highlights"):
                    highlight_bytes += int(
                        match["match_highlights"].get(
                            "size_bytes",
                            0,
                        )
                    )

                match["storage"] = {
                    "full_match_bytes": full_match_bytes,
                    "highlight_bytes": highlight_bytes,
                    "total_bytes": (
                        full_match_bytes
                        + highlight_bytes
                    ),
                }

            match_list = sorted(
                matches.values(),
                key=lambda item: item["modified"],
                reverse=True,
            )

            unassigned.sort(
                key=lambda item: item["modified"],
                reverse=True,
            )


            disk = shutil.disk_usage(
                "/var/lib/scoreos"
            )

            def folder_size(path):
                total = 0

                if not path.exists():
                    return 0

                for item in path.rglob("*"):
                    if not item.is_file():
                        continue

                    try:
                        total += item.stat().st_size
                    except OSError:
                        continue

                return total

            buffer_root = Path(
                "/var/lib/scoreos/camera-buffer"
            )

            storage = {
                "disk_total_bytes": disk.total,
                "disk_used_bytes": disk.used,
                "disk_free_bytes": disk.free,
                "disk_used_percent": round(
                    (
                        disk.used
                        / disk.total
                        * 100
                    )
                    if disk.total
                    else 0,
                    1,
                ),
                "recordings_bytes": folder_size(
                    recording_root
                ),
                "highlights_bytes": folder_size(
                    highlight_root
                ),
                "buffer_bytes": folder_size(
                    buffer_root
                ),
            }

            warning_bytes = (
                5 * 1024 * 1024 * 1024
            )

            critical_bytes = (
                2 * 1024 * 1024 * 1024
            )

            storage["low_space"] = (
                disk.free < warning_bytes
            )

            storage["critical_space"] = (
                disk.free < critical_bytes
            )

            if storage["critical_space"]:
                storage["level"] = "critical"
            elif storage["low_space"]:
                storage["level"] = "warning"
            else:
                storage["level"] = "normal"

            self.send_json(
                {
                    "ok": True,
                    "matches": match_list,
                    "match_count": len(match_list),
                    "unassigned": unassigned,
                    "unassigned_count": len(unassigned),
                    "storage": storage,
                }
            )
            return


        if path == "/api/highlights/build-match":
            script = Path(
                "/home/pi/sutton-scoreboard-os/scripts/build_match_highlights.py"
            )

            try:
                result = subprocess.run(
                    [
                        "/usr/bin/python3",
                        str(script),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=180,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                self.send_json(
                    {
                        "ok": False,
                        "error": "Match highlights build timed out.",
                    },
                    status=500,
                )
                return

            if result.returncode != 0:
                self.send_json(
                    {
                        "ok": False,
                        "error": (
                            result.stderr.strip()
                            or result.stdout.strip()
                            or "Unable to build match highlights."
                        ),
                    },
                    status=500,
                )
                return

            self.send_json(
                {
                    "ok": True,
                    "message": "Match highlights built successfully.",
                    "output": result.stdout.strip(),
                }
            )
            return

        if path == "/api/events":
            event_file = Path(
                "/var/lib/scoreos/events/events.jsonl"
            )

            events = []

            if event_file.exists():
                with event_file.open(
                    "r",
                    encoding="utf-8",
                ) as handle:
                    for line in handle:
                        line = line.strip()

                        if not line:
                            continue

                        try:
                            event = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        if event.get("type") in (
                            "FOUR",
                            "SIX",
                            "WICKET",
                        ):
                            events.append(event)

            self.send_json(
                {
                    "ok": True,
                    "events": events[-50:],
                }
            )
            return


        if path == "/api/events/latest":
            event_file = Path(
                "/var/lib/scoreos/events/events.jsonl"
            )

            latest_event = None

            if event_file.exists():
                with event_file.open(
                    "r",
                    encoding="utf-8",
                ) as handle:
                    for line in handle:
                        line = line.strip()

                        if not line:
                            continue

                        try:
                            latest_event = json.loads(line)
                        except json.JSONDecodeError:
                            continue

            self.send_json(
                {
                    "ok": True,
                    "event": latest_event,
                }
            )
            return

        if path in ("/highlights", "/highlights/"):
            page = Path(__file__).with_name(
                "highlights.html"
            )

            if not page.exists():
                self.send_error(
                    404,
                    "Highlights page not found",
                )
                return

            self.send_html(
                page.read_text(
                    encoding="utf-8"
                )
            )
            return

        if path.startswith("/recordings/video/") or path.startswith(
            "/recordings/download/"
        ):
            recording_root = Path(
                "/var/lib/scoreos/recordings"
            )

            session_id = path.rsplit("/", 1)[-1]

            if (
                not session_id
                or session_id != Path(session_id).name
                or not session_id.startswith("match-")
            ):
                self.send_error(400, "Invalid recording")
                return

            matches = list(
                recording_root.rglob(
                    f"{session_id}/full/full-match.mp4"
                )
            )

            if not matches:
                self.send_error(
                    404,
                    "Full match not found",
                )
                return

            clip = matches[0]
            file_size = clip.stat().st_size

            is_download = path.startswith(
                "/recordings/download/"
            )

            range_header = self.headers.get("Range")
            start_byte = 0
            end_byte = file_size - 1
            partial = False

            if range_header and not is_download:
                try:
                    units, requested = range_header.split("=", 1)

                    if units.lower() != "bytes":
                        raise ValueError

                    first, last = requested.split("-", 1)

                    if first:
                        start_byte = int(first)

                        if last:
                            end_byte = int(last)
                    else:
                        suffix = int(last)
                        start_byte = max(
                            0,
                            file_size - suffix,
                        )

                    end_byte = min(
                        end_byte,
                        file_size - 1,
                    )

                    if (
                        start_byte < 0
                        or start_byte >= file_size
                        or end_byte < start_byte
                    ):
                        raise ValueError

                    partial = True

                except Exception:
                    self.send_response(416)
                    self.send_header(
                        "Content-Range",
                        f"bytes */{file_size}",
                    )
                    self.end_headers()
                    return

            content_length = (
                end_byte - start_byte + 1
            )

            self.send_response(
                206 if partial else 200
            )

            self.send_header(
                "Content-Type",
                "video/mp4",
            )

            self.send_header(
                "Accept-Ranges",
                "bytes",
            )

            self.send_header(
                "Content-Length",
                str(content_length),
            )

            self.send_header(
                "Content-Disposition",
                (
                    f'attachment; filename="{session_id}-full-match.mp4"'
                    if is_download
                    else "inline"
                ),
            )

            if partial:
                self.send_header(
                    "Content-Range",
                    (
                        f"bytes {start_byte}-{end_byte}"
                        f"/{file_size}"
                    ),
                )

            self.end_headers()

            try:
                with clip.open("rb") as handle:
                    handle.seek(start_byte)

                    remaining = content_length

                    while remaining > 0:
                        chunk = handle.read(
                            min(
                                1024 * 1024,
                                remaining,
                            )
                        )

                        if not chunk:
                            break

                        self.wfile.write(chunk)
                        remaining -= len(chunk)

            except (
                BrokenPipeError,
                ConnectionResetError,
                OSError,
            ):
                pass

            return

        if path.startswith("/highlights/video/") or path.startswith(
            "/highlights/download/"
        ):
            highlight_root = Path(
                "/var/lib/scoreos/highlights"
            )

            filename = path.rsplit("/", 1)[-1]

            if (
                not filename
                or filename != Path(filename).name
                or not filename.lower().endswith(".mp4")
            ):
                self.send_error(400, "Invalid highlight")
                return

            matches = list(
                highlight_root.rglob(filename)
            )

            if not matches:
                self.send_error(
                    404,
                    "Highlight not found",
                )
                return

            clip = matches[0]

            try:
                file_size = clip.stat().st_size
            except OSError:
                self.send_error(
                    500,
                    "Unable to read highlight",
                )
                return

            is_download = path.startswith(
                "/highlights/download/"
            )

            if is_download:
                self.send_response(200)
                self.send_header(
                    "Content-Type",
                    "video/mp4",
                )
                self.send_header(
                    "Content-Disposition",
                    f'attachment; filename="{clip.name}"',
                )
                self.send_header(
                    "Content-Length",
                    str(file_size),
                )
                self.send_header(
                    "Cache-Control",
                    "no-store",
                )
                self.end_headers()

                try:
                    with clip.open("rb") as handle:
                        while True:
                            chunk = handle.read(
                                1024 * 1024
                            )

                            if not chunk:
                                break

                            self.wfile.write(chunk)
                except (
                    OSError,
                    BrokenPipeError,
                    ConnectionResetError,
                ):
                    pass

                return

            range_header = self.headers.get(
                "Range"
            )

            start_byte = 0
            end_byte = file_size - 1
            partial = False

            if range_header:
                try:
                    units, requested = (
                        range_header.split("=", 1)
                    )

                    if units.strip().lower() != "bytes":
                        raise ValueError

                    requested = requested.split(
                        ",",
                        1,
                    )[0].strip()

                    first, last = requested.split(
                        "-",
                        1,
                    )

                    if first:
                        start_byte = int(first)

                        if last:
                            end_byte = int(last)
                    else:
                        suffix_length = int(last)

                        if suffix_length <= 0:
                            raise ValueError

                        start_byte = max(
                            0,
                            file_size - suffix_length,
                        )

                    if (
                        start_byte < 0
                        or start_byte >= file_size
                    ):
                        raise ValueError

                    end_byte = min(
                        end_byte,
                        file_size - 1,
                    )

                    if end_byte < start_byte:
                        raise ValueError

                    partial = True

                except (
                    ValueError,
                    TypeError,
                ):
                    self.send_response(416)
                    self.send_header(
                        "Content-Range",
                        f"bytes */{file_size}",
                    )
                    self.end_headers()
                    return

            content_length = (
                end_byte - start_byte + 1
            )

            self.send_response(
                206 if partial else 200
            )
            self.send_header(
                "Content-Type",
                "video/mp4",
            )
            self.send_header(
                "Accept-Ranges",
                "bytes",
            )
            self.send_header(
                "Content-Length",
                str(content_length),
            )
            self.send_header(
                "Content-Disposition",
                "inline",
            )
            self.send_header(
                "Cache-Control",
                "no-store",
            )

            if partial:
                self.send_header(
                    "Content-Range",
                    (
                        f"bytes "
                        f"{start_byte}-{end_byte}"
                        f"/{file_size}"
                    ),
                )

            self.end_headers()

            try:
                with clip.open("rb") as handle:
                    handle.seek(start_byte)

                    remaining = content_length

                    while remaining > 0:
                        chunk = handle.read(
                            min(
                                1024 * 1024,
                                remaining,
                            )
                        )

                        if not chunk:
                            break

                        self.wfile.write(chunk)
                        remaining -= len(chunk)

            except (
                OSError,
                BrokenPipeError,
                ConnectionResetError,
            ):
                pass

            return

        if path in ("/", "/index.html"):
            self.send_html(SPECTATOR_HTML)
            return

        if path in ("/tv", "/tv/"):
            tv_path = Path(__file__).with_name("tv.html")
            self.send_html(tv_path.read_text(encoding="utf-8"))

            return
        if path in ("/tv-camera", "/tv-camera/"):
            page = Path(__file__).with_name(
                "tv-camera.html"
            )
            self.send_html(
                page.read_text(encoding="utf-8")
            )
            return

        if path in ("/startup", "/startup/"):
            startup_path = Path(__file__).with_name("startup.html")
            self.send_html(startup_path.read_text(encoding="utf-8"))
            return

        if path in ("/startup-v2", "/startup-v2/"):
            startup_path = Path(__file__).with_name("startup-v2.html")
            self.send_html(startup_path.read_text(encoding="utf-8"))
            return

        if path in ("/groundcontrol", "/groundcontrol/"):
            groundcontrol_path = Path(__file__).with_name(
                "groundcontrol.html"
            )
            self.send_html(
                groundcontrol_path.read_text(encoding="utf-8")
            )
            return

        if path in ("/control", "/control/"):
            control_path = Path(__file__).with_name("control.html")
            self.send_html(control_path.read_text(encoding="utf-8"))
            return

        if path in (
            "/control-classic",
            "/control-classic/",
        ):
            classic_path = Path(__file__).with_name(
                "control-classic.html"
            )
            self.send_html(
                classic_path.read_text(encoding="utf-8")
            )
            return

        if path in (
            "/admin",
            "/admin/",
            "/dashboard",
            "/dashboard/",
        ):
            dashboard_path = Path(__file__).with_name(
                "dashboard.html"
            )
            self.send_html(
                dashboard_path.read_text(encoding="utf-8")
            )
            return

        if path in ("/diagnostics", "/diagnostics/"):
            diagnostics_path = Path(__file__).with_name(
                "diagnostics.html"
            )
            self.send_html(
                diagnostics_path.read_text(encoding="utf-8")
            )
            return


        if path in ("/display-test", "/display-test/"):
            page = Path(__file__).with_name("display-test.html")
            self.send_html(page.read_text(encoding="utf-8"))
            return

        self.send_error(404)

    def do_POST(self):
        path = urlparse(self.path).path

        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(length)
            request = json.loads(raw_body.decode("utf-8"))

        except Exception as exc:
            self.send_json(
                {
                    "ok": False,
                    "error": str(exc),
                },
                status=400,
            )
            return

        if path == "/api/match/rename":
            session_id = str(
                request.get("session_id", "")
            ).strip()

            home_team = str(
                request.get("home_team", "")
            ).strip()

            away_team = str(
                request.get("away_team", "")
            ).strip()

            if (
                not session_id
                or session_id != Path(session_id).name
                or not session_id.startswith("match-")
            ):
                self.send_json(
                    {
                        "ok": False,
                        "error": "Invalid match session.",
                    },
                    status=400,
                )
                return

            if not home_team or not away_team:
                self.send_json(
                    {
                        "ok": False,
                        "error": (
                            "Home team and away team "
                            "are required."
                        ),
                    },
                    status=400,
                )
                return

            recording_root = Path(
                "/var/lib/scoreos/recordings"
            )

            matches = list(
                recording_root.rglob(
                    f"{session_id}/match.json"
                )
            )

            if matches:
                metadata_path = matches[0]

                try:
                    metadata = json.loads(
                        metadata_path.read_text(
                            encoding="utf-8"
                        )
                    )
                except (
                    OSError,
                    json.JSONDecodeError,
                ):
                    metadata = {}

            else:
                session_folders = [
                    folder
                    for folder in recording_root.rglob(
                        session_id
                    )
                    if folder.is_dir()
                    and folder.name == session_id
                ]

                if not session_folders:
                    self.send_json(
                        {
                            "ok": False,
                            "error": "Match not found.",
                        },
                        status=404,
                    )
                    return

                metadata_path = (
                    session_folders[0]
                    / "match.json"
                )

                metadata = {
                    "session_id": session_id,
                }

            try:

                metadata["home_team"] = home_team
                metadata["away_team"] = away_team
                metadata["match_name"] = (
                    home_team
                    + " v "
                    + away_team
                )

                metadata_path.write_text(
                    json.dumps(
                        metadata,
                        indent=2,
                    ) + "\n",
                    encoding="utf-8",
                )

            except (
                OSError,
                json.JSONDecodeError,
            ) as exc:
                self.send_json(
                    {
                        "ok": False,
                        "error": str(exc),
                    },
                    status=500,
                )
                return

            self.send_json(
                {
                    "ok": True,
                    "message": "Match renamed.",
                    "session": metadata,
                }
            )
            return

        if path == "/api/match/delete-full":
            session_id = str(
                request.get("session_id", "")
            ).strip()

            if (
                not session_id
                or session_id != Path(session_id).name
                or not session_id.startswith("match-")
            ):
                self.send_json(
                    {
                        "ok": False,
                        "error": "Invalid match session.",
                    },
                    status=400,
                )
                return

            current_match_file = Path(
                "/var/lib/scoreos/current-match.json"
            )

            if current_match_file.exists():
                try:
                    current_match = json.loads(
                        current_match_file.read_text(
                            encoding="utf-8"
                        )
                    )

                    if (
                        current_match.get("session_id")
                        == session_id
                    ):
                        self.send_json(
                            {
                                "ok": False,
                                "error": (
                                    "Cannot delete the active "
                                    "match recording. Stop the "
                                    "match first."
                                ),
                            },
                            status=409,
                        )
                        return

                except (
                    OSError,
                    json.JSONDecodeError,
                ):
                    self.send_json(
                        {
                            "ok": False,
                            "error": (
                                "Unable to verify whether "
                                "this match is currently active."
                            ),
                        },
                        status=500,
                    )
                    return

            recording_root = Path(
                "/var/lib/scoreos/recordings"
            )

            matches = [
                folder
                for folder in recording_root.rglob(
                    session_id
                )
                if folder.is_dir()
                and folder.name == session_id
            ]

            if not matches:
                self.send_json(
                    {
                        "ok": False,
                        "error": "Match not found.",
                    },
                    status=404,
                )
                return

            deleted = False

            for folder in matches:
                full_match = (
                    folder
                    / "full"
                    / "full-match.mp4"
                )

                if full_match.exists():
                    try:
                        full_match.unlink()
                        deleted = True
                    except OSError as exc:
                        self.send_json(
                            {
                                "ok": False,
                                "error": str(exc),
                            },
                            status=500,
                        )
                        return

            if not deleted:
                self.send_json(
                    {
                        "ok": False,
                        "error": (
                            "Full match recording "
                            "not found."
                        ),
                    },
                    status=404,
                )
                return

            complete_status = {
                "completed_at": time.time(),
                "session_id": (
                    session.get("session_id")
                    if session
                    else None
                ),
                "match_name": (
                    session.get("match_name")
                    if session
                    else None
                ),
                "full_match_ready": bool(
                    full_match
                ),
                "match_highlights_ready": bool(
                    match_highlights
                ),
                "build_error": build_error,
                "highlights_error": highlights_error,
            }

            complete_file.write_text(
                json.dumps(
                    complete_status,
                    indent=2,
                ) + "\n",
                encoding="utf-8",
            )

            processing_file.unlink(
                missing_ok=True
            )

            self.send_json(
                {
                    "ok": True,
                    "message": (
                        "Full match recording deleted. "
                        "Highlights kept."
                    ),
                    "session_id": session_id,
                }
            )
            return

        if path == "/api/match/delete":
            session_id = str(
                request.get("session_id", "")
            ).strip()

            if (
                not session_id
                or session_id != Path(session_id).name
                or not session_id.startswith("match-")
            ):
                self.send_json(
                    {
                        "ok": False,
                        "error": "Invalid match session.",
                    },
                    status=400,
                )
                return

            current_match_file = Path(
                "/var/lib/scoreos/current-match.json"
            )

            if current_match_file.exists():
                try:
                    current_match = json.loads(
                        current_match_file.read_text(
                            encoding="utf-8"
                        )
                    )

                    if (
                        current_match.get("session_id")
                        == session_id
                    ):
                        self.send_json(
                            {
                                "ok": False,
                                "error": (
                                    "Cannot delete the active "
                                    "match recording. Stop the "
                                    "match first."
                                ),
                            },
                            status=409,
                        )
                        return

                except (
                    OSError,
                    json.JSONDecodeError,
                ):
                    self.send_json(
                        {
                            "ok": False,
                            "error": (
                                "Unable to verify whether "
                                "this match is currently active."
                            ),
                        },
                        status=500,
                    )
                    return

            recording_root = Path(
                "/var/lib/scoreos/recordings"
            )

            highlight_root = Path(
                "/var/lib/scoreos/highlights"
            )

            recording_matches = [
                folder
                for folder in recording_root.rglob(
                    session_id
                )
                if folder.is_dir()
                and folder.name == session_id
            ]

            highlight_matches = [
                folder
                for folder in highlight_root.rglob(
                    session_id
                )
                if folder.is_dir()
                and folder.name == session_id
            ]

            if (
                not recording_matches
                and not highlight_matches
            ):
                self.send_json(
                    {
                        "ok": False,
                        "error": "Match not found.",
                    },
                    status=404,
                )
                return


            try:
                for folder in recording_matches:
                    shutil.rmtree(folder)

                for folder in highlight_matches:
                    shutil.rmtree(folder)

            except OSError as exc:
                self.send_json(
                    {
                        "ok": False,
                        "error": str(exc),
                    },
                    status=500,
                )
                return

            self.send_json(
                {
                    "ok": True,
                    "message": "Match deleted.",
                    "session_id": session_id,
                }
            )
            return

        if path == "/api/match/start":
            camera_health = camera_manager.status()

            if not camera_health.get("connected"):
                self.send_json(
                    {
                        "ok": False,
                        "error": (
                            "Camera is offline. "
                            "Connect the camera before "
                            "starting the match."
                        ),
                    },
                    status=503,
                )
                return

            if not camera_health.get("buffering"):
                self.send_json(
                    {
                        "ok": False,
                        "error": (
                            "Camera pre-roll is not ready. "
                            "Wait for MATCH DAY READY "
                            "before starting the match."
                        ),
                    },
                    status=503,
                )
                return

            if not camera_health.get(
                "highlight_worker"
            ):
                self.send_json(
                    {
                        "ok": False,
                        "error": (
                            "Highlight worker is not running. "
                            "Match recording has not started."
                        ),
                    },
                    status=503,
                )
                return

            disk = shutil.disk_usage(
                "/var/lib/scoreos"
            )

            critical_bytes = (
                2 * 1024 * 1024 * 1024
            )

            if disk.free < critical_bytes:
                self.send_json(
                    {
                        "ok": False,
                        "error": (
                            "Not enough free storage "
                            "to start a match recording."
                        ),
                    },
                    status=507,
                )
                return

            match_file = Path(
                "/var/lib/scoreos/current-match.json"
            )

            if match_file.exists():
                self.send_json(
                    {
                        "ok": False,
                        "error": "A match recording is already active.",
                    },
                    status=400,
                )
                return

            now = time.time()

            session_id = time.strftime(
                "match-%H-%M-%S"
            )

            home_team = str(
                request.get("home_team", "")
            ).strip()

            away_team = str(
                request.get("away_team", "")
            ).strip()

            if not home_team or not away_team:
                self.send_json(
                    {
                        "ok": False,
                        "error": (
                            "Home team and away team "
                            "are required."
                        ),
                    },
                    status=400,
                )
                return

            session = {
                "session_id": session_id,
                "started": now,
                "started_iso": time.strftime(
                    "%Y-%m-%dT%H:%M:%S"
                ),
                "home_team": home_team,
                "away_team": away_team,
                "match_name": (
                    home_team
                    + " v "
                    + away_team
                ),
            }

            match_file.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            match_file.write_text(
                json.dumps(
                    session,
                    indent=2,
                ) + "\n",
                encoding="utf-8",
            )

            match_date = time.strftime(
                "%Y-%m-%d"
            )

            session_folder = (
                Path("/var/lib/scoreos/recordings")
                / match_date
                / session_id
            )

            session_folder.mkdir(
                parents=True,
                exist_ok=True,
            )

            shutil.chown(
                session_folder,
                user="pi",
                group="pi",
            )

            (
                session_folder / "match.json"
            ).write_text(
                json.dumps(
                    session,
                    indent=2,
                ) + "\n",
                encoding="utf-8",
            )

            # Stop the rolling pre-roll buffer and
            # preserve its most recent footage.
            subprocess.run(
                [
                    "/usr/bin/systemctl",
                    "stop",
                    "scoreos-camera-buffer.service",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            buffer_root = Path(
                "/var/lib/scoreos/camera-buffer"
            )

            full_folder = (
                session_folder / "full"
            )

            full_folder.mkdir(
                parents=True,
                exist_ok=True,
            )

            shutil.chown(
                full_folder,
                user="pi",
                group="pi",
            )

            cutoff = time.time() - 50

            if buffer_root.exists():
                for source in sorted(
                    buffer_root.glob("*.ts")
                ):
                    try:
                        stat = source.stat()
                    except OSError:
                        continue

                    if (
                        stat.st_size <= 0
                        or stat.st_mtime < cutoff
                    ):
                        continue

                    try:
                        shutil.copy2(
                            source,
                            full_folder / source.name,
                        )
                    except OSError:
                        continue

            result = subprocess.run(
                [
                    "/usr/bin/systemctl",
                    "start",
                    "scoreos-camera-recorder.service",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            # systemctl start can return success even if
            # the recorder exits immediately afterwards.
            time.sleep(2)

            recorder_active = (
                subprocess.run(
                    [
                        "/usr/bin/systemctl",
                        "is-active",
                        "--quiet",
                        "scoreos-camera-recorder.service",
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                ).returncode == 0
            )

            if (
                result.returncode != 0
                or not recorder_active
            ):
                match_file.unlink(
                    missing_ok=True
                )

                # Starting a match deliberately stops the
                # rolling pre-roll buffer. If the recorder
                # fails, restore the buffer automatically.
                subprocess.run(
                    [
                        "/usr/bin/systemctl",
                        "start",
                        "scoreos-camera-buffer.service",
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                )

                self.send_json(
                    {
                        "ok": False,
                        "error": (
                            result.stderr.strip()
                            or
                            "Camera recorder did not stay running."
                        ),
                    },
                    status=500,
                )
                return

            self.send_json(
                {
                    "ok": True,
                    "message": "Match recording started.",
                    "session": session,
                }
            )
            return

        if path == "/api/match/stop":
            match_file = Path(
                "/var/lib/scoreos/current-match.json"
            )

            session = None

            if match_file.exists():
                try:
                    session = json.loads(
                        match_file.read_text(
                            encoding="utf-8"
                        )
                    )
                except (
                    OSError,
                    json.JSONDecodeError,
                ):
                    session = None

            processing_file = Path(
                "/var/lib/scoreos/match-processing.json"
            )

            complete_file = Path(
                "/var/lib/scoreos/last-match-complete.json"
            )

            complete_file.unlink(
                missing_ok=True
            )

            processing_status = {
                "started_at": time.time(),
                "stage": "building",
                "session_id": (
                    session.get("session_id")
                    if session
                    else None
                ),
                "match_name": (
                    session.get("match_name")
                    if session
                    else None
                ),
            }

            processing_file.write_text(
                json.dumps(
                    processing_status,
                    indent=2,
                ) + "\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    "/usr/bin/systemctl",
                    "stop",
                    "scoreos-camera-recorder.service",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            if result.returncode != 0:
                self.send_json(
                    {
                        "ok": False,
                        "error": (
                            result.stderr.strip()
                            or "Unable to stop match recording."
                        ),
                    },
                    status=500,
                )
                return

            full_match = None
            build_error = None

            if session:
                session_id = str(
                    session.get("session_id", "")
                ).strip()

                started_iso = str(
                    session.get("started_iso", "")
                )

                match_date = (
                    started_iso[:10]
                    if len(started_iso) >= 10
                    else time.strftime("%Y-%m-%d")
                )

                if session_id:
                    build_script = Path(
                        "/home/pi/sutton-scoreboard-os/scripts/build_full_match.py"
                    )

                    try:
                        build_result = subprocess.run(
                            [
                                "/usr/bin/python3",
                                str(build_script),
                                "--date",
                                match_date,
                                "--session",
                                session_id,
                            ],
                            capture_output=True,
                            text=True,
                            check=False,
                            timeout=300,
                        )

                        if build_result.returncode == 0:
                            full_match_path = (
                                Path("/var/lib/scoreos/recordings")
                                / match_date
                                / session_id
                                / "full"
                                / "full-match.mp4"
                            )

                            if full_match_path.exists():
                                full_match = str(
                                    full_match_path
                                )
                        else:
                            build_error = (
                                build_result.stderr.strip()
                                or build_result.stdout.strip()
                                or "Unable to build full match."
                            )

                    except subprocess.TimeoutExpired:
                        build_error = (
                            "Full match build timed out."
                        )

            match_highlights = None
            highlights_error = None

            if session:
                session_id = str(
                    session.get("session_id", "")
                ).strip()

                started_iso = str(
                    session.get("started_iso", "")
                )

                match_date = (
                    started_iso[:10]
                    if len(started_iso) >= 10
                    else time.strftime("%Y-%m-%d")
                )

                if session_id:
                    highlights_script = Path(
                        "/home/pi/sutton-scoreboard-os/scripts/build_match_highlights.py"
                    )

                    try:
                        highlights_result = subprocess.run(
                            [
                                "/usr/bin/python3",
                                str(highlights_script),
                                "--date",
                                match_date,
                                "--session",
                                session_id,
                            ],
                            capture_output=True,
                            text=True,
                            check=False,
                            timeout=300,
                        )

                        if highlights_result.returncode == 0:
                            highlights_path = (
                                Path("/var/lib/scoreos/highlights")
                                / match_date
                                / session_id
                                / "match-highlights.mp4"
                            )

                            if highlights_path.exists():
                                match_highlights = str(
                                    highlights_path
                                )
                        else:
                            highlights_error = (
                                highlights_result.stderr.strip()
                                or highlights_result.stdout.strip()
                                or "Unable to build match highlights."
                            )

                    except subprocess.TimeoutExpired:
                        highlights_error = (
                            "Match highlights build timed out."
                        )

            match_file.unlink(
                missing_ok=True
            )

            subprocess.run(
                [
                    "/usr/bin/systemctl",
                    "start",
                    "scoreos-camera-buffer.service",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            complete_status = {
                "completed_at": time.time(),
                "session_id": (
                    session.get("session_id")
                    if session
                    else None
                ),
                "match_name": (
                    session.get("match_name")
                    if session
                    else None
                ),
                "full_match_ready": bool(full_match),
                "match_highlights_ready": bool(match_highlights),
                "build_error": build_error,
                "highlights_error": highlights_error,
            }

            complete_file.write_text(
                json.dumps(
                    complete_status,
                    indent=2,
                ) + "\n",
                encoding="utf-8",
            )

            processing_file.unlink(
                missing_ok=True
            )

            self.send_json(
                {
                    "ok": True,
                    "message": (
                        "Match recording stopped "
                        "and match videos built."
                        if full_match or match_highlights
                        else "Match recording stopped."
                    ),
                    "session": session,
                    "full_match": full_match,
                    "match_highlights": match_highlights,
                    "build_error": build_error,
                    "highlights_error": highlights_error,
                }
            )
            return

        if path == "/api/camera/settings":
            try:
                camera = camera_manager.save(request)

                safe_camera = {
                    **camera,
                    "password": "",
                    "password_saved": bool(camera.get("password")),
                }

                self.send_json(
                    {
                        "ok": True,
                        "camera": safe_camera,
                    }
                )

            except Exception as exc:
                self.send_json(
                    {
                        "ok": False,
                        "error": str(exc),
                    },
                    status=500,
                )

            return


        if path == "/api/bluetooth":
            try:
                response = bluetooth_manager.handle_action(request)
                status = 200 if response.get("ok") else 400
                self.send_json(response, status=status)

            except Exception as exc:
                self.send_json(
                    {
                        "ok": False,
                        "error": str(exc),
                    },
                    status=500,
                )

            return

        if path == "/api/admin":
            action = request.get(
                "action",
                ""
            )

            if action == "fix_scoreos":
                result = fix_scoreos()

                self.send_json(
                    result,
                    status=(
                        200
                        if result.get("ok")
                        else 400
                    ),
                )
                return

            success, message = admin_action(
                action
            )

            self.send_json(
                {
                    "ok": success,
                    "message": message,
                },
                status=200 if success else 400,
            )
            return

        if path == "/api/control":
            try:
                response = send_engine_control(request)
                status = 200 if response.get("ok") else 400
                self.send_json(response, status=status)

            except Exception as exc:
                self.send_json(
                    {
                        "ok": False,
                        "error": str(exc),
                    },
                    status=500,
                )

            return

        self.send_error(404)

    def send_json(self, payload, status=200):
        body = json.dumps(payload).encode("utf-8")

        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, html):
        body = html.encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


SPECTATOR_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SCOREOS Spectator</title>
<style>
body {
    font-family: Arial, sans-serif;
    margin: 0;
    background: #111;
    color: #fff;
    text-align: center;
}
main {
    max-width: 900px;
    margin: 0 auto;
    padding: 30px 20px;
}
h1 { margin-bottom: 6px; }
.team { font-size: 1.5rem; margin-bottom: 24px; }
.score { font-size: 6rem; font-weight: bold; }
.overs { font-size: 2rem; margin-bottom: 30px; }
.batters {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 20px;
}
.card {
    background: #222;
    padding: 20px;
    border-radius: 12px;
}
.name { font-size: 1.3rem; }
.runs { font-size: 2.5rem; font-weight: bold; }
.status { margin-top: 24px; opacity: 0.7; }
a { color: #ffd800; }
</style>
</head>
<body>
<main>
    <h1>SCOREOS</h1>
    <div class="team" id="team">Waiting for Play-Cricket</div>

    <div class="score">
        <span id="total">--0</span>/<span id="wickets">0</span>
    </div>

    <div class="overs">
        Overs: <span id="overs">-0</span>
    </div>

    <div class="batters">
        <div class="card">
            <div class="name" id="bat1name">-</div>
            <div class="runs" id="bat1score">--0</div>
        </div>

        <div class="card">
            <div class="name" id="bat2name">-</div>
            <div class="runs" id="bat2score">--0</div>
        </div>
    </div>

    <div class="status" id="status">Connecting...</div>
    <p><a href="/control">Open scoring controls</a></p>
</main>

<script>
async function refreshScore() {
    try {
        const response = await fetch("/api/state", {cache: "no-store"});
        const state = await response.json();

        document.getElementById("team").textContent =
            state.BatTeamName || "Waiting for Play-Cricket";

        document.getElementById("total").textContent =
            state.total || "--0";

        document.getElementById("wickets").textContent =
            state.wickets || "0";

        document.getElementById("overs").textContent =
            state.overs || "-0";

        document.getElementById("bat1name").textContent =
            state.Bat1Name || "-";

        document.getElementById("bat1score").textContent =
            state.BatAscore || "--0";

        document.getElementById("bat2name").textContent =
            state.Bat2Name || "-";

        document.getElementById("bat2score").textContent =
            state.BatBscore || "--0";

        document.getElementById("status").textContent =
            "Live — " + (state.mode || "playcricket");

    } catch (error) {
        document.getElementById("status").textContent =
            "Waiting for scoreboard";
    }
}

refreshScore();
setInterval(refreshScore, 1000);
</script>
</body>
</html>
"""


ADMIN_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport"
      content="width=device-width, initial-scale=1">
<title>SCOREOS Admin</title>

<style>
:root {
    --green: #146b3a;
    --green-dark: #0a4323;
    --yellow: #ffd800;
    --red: #c62828;
    --amber: #e58a00;
    --grey: #59615d;
    --background: #e7ece8;
    --panel: #ffffff;
}

* {
    box-sizing: border-box;
}

body {
    margin: 0;
    background: var(--background);
    color: #172019;
    font-family: Arial, Helvetica, sans-serif;
}

header {
    background: var(--green);
    color: white;
    text-align: center;
    padding: 16px 12px;
    border-bottom: 8px solid var(--yellow);
}

header h1 {
    margin: 0;
    font-size: 2rem;
}

header p {
    margin: 5px 0 0;
}

main {
    max-width: 1100px;
    margin: 0 auto;
    padding: 14px;
}

.ready-banner {
    margin-bottom: 14px;
    padding: 14px;
    border-radius: 10px;
    background: var(--green-dark);
    color: white;
    text-align: center;
    font-size: 1.3rem;
    font-weight: bold;
}

.ready-banner.warning {
    background: var(--amber);
}

.ready-banner.error {
    background: var(--red);
}

.grid {
    display: grid;
    grid-template-columns:
        repeat(auto-fit, minmax(220px, 1fr));
    gap: 12px;
    margin-bottom: 14px;
}

.card {
    background: var(--panel);
    border: 3px solid var(--green);
    border-radius: 11px;
    overflow: hidden;
    box-shadow: 0 2px 5px rgba(0,0,0,.12);
}

.card-title {
    margin: 0;
    padding: 9px;
    background: var(--green);
    color: white;
    text-align: center;
    font-size: 1rem;
}

.card-body {
    padding: 14px;
    text-align: center;
}

.big {
    font-size: 2.3rem;
    line-height: 1.1;
    font-weight: bold;
}

.medium {
    font-size: 1.4rem;
    font-weight: bold;
}

.small {
    margin-top: 6px;
    color: var(--grey);
    word-break: break-word;
}

.status-dot {
    display: inline-block;
    width: 13px;
    height: 13px;
    margin-right: 7px;
    border-radius: 50%;
    background: var(--red);
}

.status-dot.ok {
    background: #18a558;
}

.status-dot.warning {
    background: var(--amber);
}

.match-card {
    margin-bottom: 14px;
}

.match-grid {
    display: grid;
    grid-template-columns:
        repeat(auto-fit, minmax(150px, 1fr));
    gap: 10px;
}

.match-item {
    padding: 12px;
    background: #f3f6f4;
    border: 2px solid #c9d6ce;
    border-radius: 9px;
    text-align: center;
}

.match-label {
    color: var(--green-dark);
    font-weight: bold;
}

.match-value {
    margin-top: 4px;
    font-size: 2rem;
    font-weight: bold;
}

.table {
    width: 100%;
    border-collapse: collapse;
}

.table th,
.table td {
    padding: 10px;
    border-bottom: 1px solid #d5ddd8;
    text-align: left;
}

.table th {
    color: var(--green-dark);
}

.links {
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    gap: 10px;
    margin: 16px 0;
}

.links a,
.refresh-button {
    display: inline-block;
    min-width: 150px;
    padding: 12px 16px;
    border: 0;
    border-radius: 8px;
    background: var(--green);
    color: white;
    text-align: center;
    text-decoration: none;
    font-size: 1rem;
    font-weight: bold;
    cursor: pointer;
}

.refresh-button {
    background: var(--yellow);
    color: #111;
}

footer {
    padding: 15px;
    color: var(--grey);
    text-align: center;
}

@media (max-width: 600px) {
    header h1 {
        font-size: 1.6rem;
    }

    .big {
        font-size: 1.9rem;
    }

    .match-value {
        font-size: 1.6rem;
    }
}
</style>
</head>

<body>
<header>
    <h1>SCOREOS Admin Dashboard</h1>
    <p>Sutton Cricket Club</p>
</header>

<main>
    <div class="ready-banner" id="readyBanner">
        Checking SCOREOS...
    </div>

    <section class="card match-card">
        <h2 class="card-title">LIVE MATCH</h2>
        <div class="card-body">
            <div class="match-grid">
                <div class="match-item">
                    <div class="match-label">Score</div>
                    <div class="match-value">
                        <span id="total">--0</span>/<span id="wickets">0</span>
                    </div>
                </div>

                <div class="match-item">
                    <div class="match-label">Overs</div>
                    <div class="match-value" id="overs">-0</div>
                </div>

                <div class="match-item">
                    <div class="match-label">Target</div>
                    <div class="match-value" id="target">---</div>
                </div>

                <div class="match-item">
                    <div class="match-label">Mode</div>
                    <div class="match-value" id="mode">
                        playcricket
                    </div>
                </div>
            </div>
        </div>
    </section>

    <div class="grid">
        <section class="card">
            <h2 class="card-title">SCOREBOARD ENGINE</h2>
            <div class="card-body">
                <div class="medium" id="engineStatus">
                    Checking...
                </div>
                <div class="small">
                    Sutton SCOREOS service
                </div>
            </div>
        </section>

        <section class="card">
            <h2 class="card-title">BLUETOOTH</h2>
            <div class="card-body">
                <div class="medium" id="bluetoothStatus">
                    Checking...
                </div>
                <div class="small" id="bluetoothName">
                    Device name
                </div>
            </div>
        </section>

        <section class="card">
            <h2 class="card-title">BLE ADVERTISEMENT</h2>
            <div class="card-body">
                <div class="medium" id="advertStatus">
                    Checking...
                </div>
                <div class="small">
                    Play-Cricket discovery
                </div>
            </div>
        </section>

        <section class="card">
            <h2 class="card-title">ARDUINO</h2>
            <div class="card-body">
                <div class="medium" id="arduinoStatus">
                    Checking...
                </div>
                <div class="small" id="arduinoDevice">
                    Serial device
                </div>
            </div>
        </section>

        <section class="card">
            <h2 class="card-title">HOTSPOT</h2>
            <div class="card-body">
                <div class="medium" id="hotspotStatus">
                    Checking...
                </div>
                <div class="small">
                    SuttonCC-Scoreboard
                </div>
            </div>
        </section>

        <section class="card">
            <h2 class="card-title">LAST SCORE UPDATE</h2>
            <div class="card-body">
                <div class="big" id="lastUpdate">--</div>
                <div class="small">
                    Seconds since state update
                </div>
            </div>
        </section>
    </div>

    <div class="grid">
        <section class="card">
            <h2 class="card-title">CPU TEMPERATURE</h2>
            <div class="card-body">
                <div class="big" id="temperature">--</div>
            </div>
        </section>

        <section class="card">
            <h2 class="card-title">MEMORY</h2>
            <div class="card-body">
                <div class="big" id="memory">--</div>
                <div class="small" id="memoryDetail"></div>
            </div>
        </section>

        <section class="card">
            <h2 class="card-title">DISK FREE</h2>
            <div class="card-body">
                <div class="big" id="disk">--</div>
            </div>
        </section>

        <section class="card">
            <h2 class="card-title">UPTIME</h2>
            <div class="card-body">
                <div class="big" id="uptime">--</div>
            </div>
        </section>
    </div>

    <section class="card">
        <h2 class="card-title">NETWORK</h2>
        <div class="card-body">
            <table class="table">
                <tr>
                    <th>Hostname</th>
                    <td id="hostname">--</td>
                </tr>
                <tr>
                    <th>IP addresses</th>
                    <td id="addresses">--</td>
                </tr>
                <tr>
                    <th>Ethernet</th>
                    <td id="ethernet">--</td>
                </tr>
                <tr>
                    <th>Wi-Fi</th>
                    <td id="wifi">--</td>
                </tr>
                <tr>
                    <th>Version</th>
                    <td id="version">--</td>
                </tr>
            </table>
        </div>
    </section>

    <div class="links">
        <a href="/">Live Score</a>
        <a href="/control">Scoring Controls</a>
        <button class="refresh-button"
                onclick="refreshDashboard()">
            Refresh
        </button>
    </div>
</main>

<footer>
    SCOREOS — Sutton Cricket Club
</footer>

<script>
function statusMarkup(ok, text, warning=false) {
    const statusClass = ok
        ? "ok"
        : (warning ? "warning" : "");

    return (
        '<span class="status-dot ' +
        statusClass +
        '"></span>' +
        text
    );
}

function serviceIsHealthy(value) {
    return value === "active" || value === "activating";
}

function deviceDescription(device) {
    if (!device) {
        return "Not available";
    }

    const connection = device.connection &&
        device.connection !== "--"
        ? " — " + device.connection
        : "";

    return device.state + connection;
}

async function refreshDashboard() {
    try {
        const response = await fetch(
            "/api/system",
            {cache: "no-store"}
        );

        if (!response.ok) {
            throw new Error("System API unavailable");
        }

        const data = await response.json();
        const match = data.match || {};
        const services = data.services || {};
        const bluetooth = data.bluetooth || {};
        const arduino = data.arduino || {};
        const network = data.network || {};
        const devices = network.devices || {};

        document.getElementById("total").textContent =
            match.total || "--0";

        document.getElementById("wickets").textContent =
            match.wickets || "0";

        document.getElementById("overs").textContent =
            match.overs || "-0";

        document.getElementById("target").textContent =
            match.target || "---";

        document.getElementById("mode").textContent =
            match.mode || "playcricket";

        const engineOk = serviceIsHealthy(
            services.scoreboard
        );

        document.getElementById(
            "engineStatus"
        ).innerHTML = statusMarkup(
            engineOk,
            services.scoreboard || "unknown"
        );

        const bluetoothOk =
            bluetooth.service === "active";

        document.getElementById(
            "bluetoothStatus"
        ).innerHTML = statusMarkup(
            bluetoothOk,
            bluetooth.service || "unknown"
        );

        document.getElementById(
            "bluetoothName"
        ).textContent =
            "Name: " + (bluetooth.name || "Unknown");

        document.getElementById(
            "advertStatus"
        ).innerHTML = statusMarkup(
            Boolean(bluetooth.advertising),
            bluetooth.advertising
                ? "Active"
                : "Not active"
        );

        document.getElementById(
            "arduinoStatus"
        ).innerHTML = statusMarkup(
            Boolean(arduino.connected),
            arduino.connected
                ? "Connected"
                : "Not detected",
            !arduino.connected
        );

        document.getElementById(
            "arduinoDevice"
        ).textContent =
            arduino.device || "No serial device";

        document.getElementById(
            "hotspotStatus"
        ).innerHTML = statusMarkup(
            Boolean(network.hotspot_active),
            network.hotspot_active
                ? "Active"
                : "Not active",
            !network.hotspot_active
        );

        const updateAge = data.last_update_age;

        document.getElementById(
            "lastUpdate"
        ).textContent =
            updateAge === null ||
            updateAge === undefined
                ? "--"
                : updateAge + "s";

        document.getElementById(
            "temperature"
        ).textContent =
            data.temperature_c === null ||
            data.temperature_c === undefined
                ? "--"
                : data.temperature_c + "°C";

        const memory = data.memory || {};

        document.getElementById(
            "memory"
        ).textContent =
            memory.used_percent === null ||
            memory.used_percent === undefined
                ? "--"
                : memory.used_percent + "%";

        document.getElementById(
            "memoryDetail"
        ).textContent =
            memory.used_mb !== null &&
            memory.used_mb !== undefined
                ? memory.used_mb +
                  " MB of " +
                  memory.total_mb +
                  " MB"
                : "";

        const disk = data.disk || {};

        document.getElementById(
            "disk"
        ).textContent =
            disk.free_gb === undefined
                ? "--"
                : disk.free_gb + " GB";

        document.getElementById(
            "uptime"
        ).textContent =
            data.uptime || "--";

        document.getElementById(
            "hostname"
        ).textContent =
            data.hostname || "--";

        document.getElementById(
            "addresses"
        ).textContent =
            (network.addresses || []).join(", ") || "--";

        document.getElementById(
            "ethernet"
        ).textContent =
            deviceDescription(devices.eth0);

        document.getElementById(
            "wifi"
        ).textContent =
            deviceDescription(devices.wlan0);

        document.getElementById(
            "version"
        ).textContent =
            data.version || "--";

        const coreReady =
            engineOk &&
            bluetoothOk &&
            bluetooth.advertising &&
            services.web === "active";

        const banner = document.getElementById(
            "readyBanner"
        );

        if (coreReady && arduino.connected) {
            banner.className = "ready-banner";
            banner.textContent = "SCOREOS READY";
        } else if (coreReady) {
            banner.className =
                "ready-banner warning";
            banner.textContent =
                "SCOREOS READY — ARDUINO NOT DETECTED";
        } else {
            banner.className = "ready-banner error";
            banner.textContent =
                "SCOREOS REQUIRES ATTENTION";
        }

    } catch (error) {
        const banner = document.getElementById(
            "readyBanner"
        );

        banner.className = "ready-banner error";
        banner.textContent =
            "Unable to read SCOREOS status";
    }
}

refreshDashboard();
setInterval(refreshDashboard, 3000);
</script>
</body>
</html>
"""


CONTROL_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<title>Sutton CC Scoreboard</title>
<style>
:root{
  --black:#11161b;
  --panel:#ffffff;
  --line:#c9c9c9;
  --green:#3d9145;
  --green-dark:#32783a;
  --red:#df2720;
  --red-dark:#bd1f19;
  --blue:#155aa8;
  --blue-dark:#104986;
  --yellow:#f2bd18;
  --grey:#8b8b8b;
  --grey-dark:#6f6f6f;
}
*{box-sizing:border-box}
html,body{margin:0;width:100%;height:100%;font-family:Arial,Helvetica,sans-serif;background:#efefef;color:#111;overflow:hidden}
body{display:flex;flex-direction:column}
header{
  height:54px;
  background:#0e1114;
  color:#fff;
  display:grid;
  grid-template-columns:100px 1fr 170px;
  align-items:center;
  padding:0 18px;
  border-bottom:2px solid #222;
}
.crest{font-weight:700;font-size:13px;letter-spacing:.4px}
.title{text-align:center;font-size:29px;font-weight:700;letter-spacing:1px}
.clock{text-align:right;font-size:16px}
main{
  flex:1;
  padding:8px 10px 6px;
  display:grid;
  grid-template-rows:2.25fr 1.18fr .58fr .52fr .52fr;
  gap:7px;
  min-height:0;
}
.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;min-height:0}
.panel{
  background:var(--panel);
  border:1px solid #aaa;
  border-radius:5px;
  overflow:hidden;
  display:flex;
  flex-direction:column;
  min-height:0;
}
.panel-title{
  background:var(--black);
  color:#fff;
  text-align:center;
  font-size:18px;
  font-weight:700;
  padding:5px 4px;
  letter-spacing:.5px;
}
.display{
  background:#030607;
  color:#fff;
  text-align:center;
  font-family:"Courier New",monospace;
  font-size:56px;
  line-height:1;
  padding:7px 4px 4px;
  font-weight:700;
  letter-spacing:4px;
}
.display.small{font-size:43px;padding:5px 4px 3px}
.pad{
  flex:1;
  padding:7px;
  display:grid;
  gap:7px;
  min-height:0;
}
.two-col{grid-template-columns:1fr 1fr;grid-template-rows:repeat(4,1fr)}
.total-grid{grid-template-columns:repeat(3,1fr);grid-template-rows:repeat(3,1fr)}
.total-grid .zero{grid-column:1/4}
button{
  border:1px solid rgba(0,0,0,.28);
  border-radius:5px;
  color:#fff;
  font-weight:700;
  font-size:24px;
  cursor:pointer;
  touch-action:manipulation;
  min-height:0;
}
button:active{transform:translateY(1px);filter:brightness(.92)}
.green{background:linear-gradient(var(--green),var(--green-dark))}
.red{background:linear-gradient(var(--red),var(--red-dark))}
.blue{background:linear-gradient(#1c66b9,var(--blue-dark))}
.yellow{background:linear-gradient(#ffc91b,#e6ab00);color:#111}
.grey{background:linear-gradient(#aaa,var(--grey-dark))}
.zero{background:linear-gradient(#aaa,#777)}
.compact-controls{
  flex:1;
  display:grid;
  grid-template-columns:1fr 1.15fr 1fr;
  gap:8px;
  padding:8px;
}
.compact-controls button{font-size:23px}
.target-controls{
  padding:6px 8px 7px;
  display:grid;
  grid-template-columns:1fr 145px;
  grid-template-rows:1fr 34px;
  gap:6px;
  flex:1;
}
.target-controls input{
  width:100%;
  font-size:24px;
  font-weight:700;
  padding:4px 10px;
  border:1px solid #999;
  border-radius:5px;
}
.target-controls button{font-size:17px}
.target-controls .clear{grid-column:1/3}
.info-row .panel{justify-content:center}
.info-title{text-align:center;font-size:18px;font-weight:700;padding:5px 4px 0}
.info-value{text-align:center;font-family:"Courier New",monospace;font-size:35px;line-height:1;padding:2px 4px 5px}
.action-row{
  display:grid;
  grid-template-columns:1.25fr repeat(4,1fr);
  gap:9px;
}
.action-row button,.bottom-row button{font-size:17px}
.bottom-row{
  display:grid;
  grid-template-columns:1.05fr 1fr 1fr 1.05fr;
  gap:9px;
}
footer{
  height:38px;
  background:#121619;
  color:#fff;
  display:flex;
  align-items:center;
  justify-content:space-around;
  font-size:12px;
  padding:0 12px;
}
.status{display:flex;align-items:center;gap:7px}
.dot{width:11px;height:11px;border-radius:50%;background:#39b54a;display:inline-block}
@media (max-height:700px){
  header{height:46px}
  .title{font-size:24px}
  main{padding:5px 7px;gap:5px}
  .grid3{gap:7px}
  .panel-title{font-size:15px;padding:3px}
  .display{font-size:46px;padding:4px 3px 2px}
  .display.small{font-size:36px}
  .pad{padding:5px;gap:5px}
  button{font-size:20px}
  .compact-controls{padding:5px;gap:5px}
  .compact-controls button{font-size:19px}
  .target-controls{padding:4px 5px;gap:4px;grid-template-columns:1fr 120px;grid-template-rows:1fr 28px}
  .target-controls input{font-size:20px}
  .target-controls button{font-size:14px}
  .info-title{font-size:15px;padding-top:3px}
  .info-value{font-size:29px}
  .action-row,.bottom-row{gap:6px}
  .action-row button,.bottom-row button{font-size:14px}
  footer{height:32px;font-size:10px}
}
</style>
</head>
<body>
<header>
  <div class="crest">SUTTON CC<br>EST. 1854</div>
  <div class="title">SUTTON CC SCOREBOARD</div>
  <div class="clock" id="clock">--:--:--</div>
</header>

<main>
  <section class="grid3">
    <div class="panel">
      <div class="panel-title">BATSMAN A</div>
      <div class="display" id="batA">000</div>
      <div class="pad two-col">
        <button class="green" onclick="changeBat('a',1)">+1</button>
        <button class="red" onclick="changeBat('a',-1)">-1</button>
        <button class="green" onclick="changeBat('a',4)">+4</button>
        <button class="red" onclick="changeBat('a',-4)">-4</button>
        <button class="green" onclick="changeBat('a',6)">+6</button>
        <button class="red" onclick="changeBat('a',-6)">-6</button>
        <button class="zero" style="grid-column:1/3" onclick="zeroBat('a')">OUT</button>
      </div>
    </div>

    <div class="panel">
      <div class="panel-title">TOTAL SCORE</div>
      <div class="display" id="total">000</div>
      <div class="pad total-grid">
        <button class="green" onclick="change('total',1)">+1</button>
        <button class="green" onclick="change('total',2)">+2</button>
        <button class="green" onclick="change('total',4)">+4</button>
        <button class="red" onclick="change('total',-1)">-1</button>
        <button class="red" onclick="change('total',-2)">-2</button>
        <button class="red" onclick="change('total',-4)">-4</button>
        <button class="zero" onclick="zero('total')">ZERO</button>
      </div>
    </div>

    <div class="panel">
      <div class="panel-title">BATSMAN B</div>
      <div class="display" id="batB">000</div>
      <div class="pad two-col">
        <button class="green" onclick="changeBat('b',1)">+1</button>
        <button class="red" onclick="changeBat('b',-1)">-1</button>
        <button class="green" onclick="changeBat('b',4)">+4</button>
        <button class="red" onclick="changeBat('b',-4)">-4</button>
        <button class="green" onclick="changeBat('b',6)">+6</button>
        <button class="red" onclick="changeBat('b',-6)">-6</button>
        <button class="zero" style="grid-column:1/3" onclick="zeroBat('b')">OUT</button>
      </div>
    </div>
  </section>

  <section class="grid3">
    <div class="panel">
      <div class="panel-title">WICKETS</div>
      <div class="display small" id="wickets">0</div>
      <div class="compact-controls">
        <button class="green" onclick="change('wickets',1)">+1</button>
        <button class="grey" onclick="zero('wickets')">ZERO</button>
        <button class="red" onclick="change('wickets',-1)">-1</button>
      </div>
    </div>

    <div class="panel">
      <div class="panel-title">OVERS</div>
      <div class="display small" id="overs">00</div>
      <div class="compact-controls">
        <button class="green" onclick="change('overs',1)">+1</button>
        <button class="grey" onclick="newOver()">NEW OVER</button>
        <button class="red" onclick="change('overs',-1)">-1</button>
      </div>
    </div>

    <div class="panel">
      <div class="panel-title">TARGET</div>
      <div class="display small" id="target">---</div>
      <div class="target-controls">
        <input id="targetInput" type="number" min="0" max="999" placeholder="Target">
        <button class="blue" onclick="setTarget()">SET TARGET</button>
        <button class="grey clear" onclick="clearTarget()">CLEAR TARGET (---)</button>
      </div>
    </div>
  </section>

  <section class="grid3 info-row">
    <div class="panel"><div class="info-title">PARTNERSHIP</div><div class="info-value" id="partnership">000</div></div>
    <div class="panel"><div class="info-title">LAST MAN</div><div class="info-value" id="lastMan">000</div></div>
    <div class="panel"><div class="info-title">RUNS REQUIRED</div><div class="info-value" id="required">---</div></div>
  </section>

  <section class="action-row">
    <button class="yellow" onclick="undo()">↻ UNDO LAST ACTION</button>
    <button class="blue" onclick="extra(1)">+ WIDE</button>
    <button class="blue" onclick="extra(1)">+ NO BALL</button>
    <button class="blue" onclick="extra(1)">+ BYE</button>
    <button class="blue" onclick="extra(1)">+ LEG BYE</button>
  </section>

  <section class="bottom-row">
    <button class="blue" onclick="resend()">↻ RESEND SCOREBOARD</button>
    <button class="blue" onclick="testBoard()">▣ TEST BOARD</button>
    <button class="blue" onclick="newOver()">● NEW OVER</button>
    <button class="red" onclick="resetMatch()">▱ RESET MATCH</button>
  </section>
</main>

<footer>
  <div class="status">ARDUINO <span class="dot"></span> CONNECTED</div>
  <div class="status">BLUETOOTH <span class="dot"></span> CONNECTED</div>
  <div class="status">PLAY-CRICKET <span class="dot"></span> CONNECTED</div>
  <div class="status">AUTO SAVE <span class="dot"></span> ON</div>
  <div>SCOREOS v2.0</div>
</footer>

<script>
let state={batA:0,batB:0,total:0,wickets:0,overs:0,target:null,lastWicket:0,lastMan:0};
let history=[];

function snap(){history.push(JSON.stringify(state));if(history.length>50)history.shift()}
function clamp(v,min,max){return Math.max(min,Math.min(max,v))}
function pad(v,n){return String(Math.max(0,v)).padStart(n,'0')}

function render(){
  batA.textContent=pad(state.batA,3);
  batB.textContent=pad(state.batB,3);
  total.textContent=pad(state.total,3);
  wickets.textContent=state.wickets;
  overs.textContent=pad(state.overs,2);
  target.textContent=state.target===null?'---':pad(state.target,3);
  partnership.textContent=pad(Math.max(0,state.total-state.lastWicket),3);
  lastMan.textContent=pad(state.lastMan,3);
  required.textContent=state.target===null?'---':pad(Math.max(0,state.target-state.total),3);
  localStorage.setItem('scoreos-ui-state',JSON.stringify(state));
}

function change(field,amount){
  snap();
  const max=field==='wickets'?9:field==='overs'?99:999;
  state[field]=clamp(state[field]+amount,0,max);
  render();sendState();
}

function changeBat(which,amount){
  snap();
  const key=which==='a'?'batA':'batB';
  const before=state[key];
  state[key]=clamp(state[key]+amount,0,999);
  state.total=clamp(state.total+(state[key]-before),0,999);
  render();sendState();
}

function zero(field){
  if(!confirm('Set '+field+' to zero?'))return;
  snap();state[field]=0;render();sendState();
}

function zeroBat(which){
  if(!confirm('Record this batsman as out?'))return;
  snap();
  const key=which==='a'?'batA':'batB';
  state.lastMan=state[key];
  state.lastWicket=state.total;
  state[key]=0;
  state.wickets=clamp(state.wickets+1,0,9);
  render();sendState();
}

function setTarget(){
  const v=Number(targetInput.value);
  if(!Number.isInteger(v)||v<0||v>999)return;
  snap();state.target=v;targetInput.value='';render();sendState();
}
function clearTarget(){snap();state.target=null;render();sendState()}
function newOver(){change('overs',1)}
function extra(n){change('total',n)}
function undo(){if(!history.length)return;state=JSON.parse(history.pop());render();sendState()}
function resetMatch(){if(!confirm('Reset the whole match?'))return;snap();state={batA:0,batB:0,total:0,wickets:0,overs:0,target:null,lastWicket:0,lastMan:0};render();sendState()}
function resend(){sendState()}
function testBoard(){fetch('/api/control',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'test'})}).catch(()=>{})}

function sendState(){
  fetch('/api/control',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({
      action:'set_state',
      state:{
        total:pad(state.total,3),
        wickets:String(state.wickets),
        overs:pad(state.overs,2),
        target:state.target===null?'---':pad(state.target,3),
        BatAscore:pad(state.batA,3),
        BatBscore:pad(state.batB,3),
        PshipTOT:pad(Math.max(0,state.total-state.lastWicket),3),
        LastWicket:pad(state.lastWicket,3),
        LastMan:pad(state.lastMan,3)
      }
    })
  }).catch(()=>{});
}

try{
  const saved=JSON.parse(localStorage.getItem('scoreos-ui-state'));
  if(saved)state={...state,...saved};
}catch(e){}
render();
setInterval(()=>clock.textContent=new Date().toLocaleTimeString(),1000);
</script>
</body>
</html>

"""

if __name__ == "__main__":
    startup_manager.add_log("✓ SCOREOS web server started")

    print(f"SCOREOS web server listening on port {PORT}")
    ThreadingHTTPServer((HOST, PORT), ScoreboardHandler).serve_forever()

