#!/usr/bin/env python3

import json
import os
import shutil
import socket
import subprocess
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


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
        parts = line.split(":", 3)

        if len(parts) != 4:
            continue

        device, device_type, state, connection = parts

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


def bluetooth_status():
    bluetooth_service = service_status("bluetooth.service")
    advert_service = service_status(
        "sutton-scoreboard-advert.service"
    )

    show_output = run_command([
        "/usr/bin/bluetoothctl",
        "show",
    ])

    mgmt_info = run_command([
        "/usr/bin/btmgmt",
        "info",
    ])

    advert_info = run_command([
        "/usr/bin/btmgmt",
        "advinfo",
    ])

    name = "Unknown"
    powered = False

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

    diagnostics = read_diagnostics().get(
        "bluetooth",
        {}
    )

    return {
        "service": bluetooth_service,
        "advert_service": advert_service,
        "name": name,
        "powered": powered,
        "advertising": advertising,
        "connected": diagnostics.get("connected", False),
        "connected_since": diagnostics.get("connected_since"),
        "last_packet": diagnostics.get("last_packet"),
        "last_packet_iso": diagnostics.get("last_packet_iso"),
        "packet_count": diagnostics.get("packet_count", 0),
        "reconnects": diagnostics.get("reconnects", 0),
        "device_name": diagnostics.get("device_name"),
        "device_alias": diagnostics.get("device_alias"),
        "device_mac": diagnostics.get("device_mac"),
        "device_icon": diagnostics.get("device_icon"),
        "battery": diagnostics.get("battery"),
        "rssi": diagnostics.get("rssi"),
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



def admin_action(action):
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
        "restart_bluetooth": [
            "/usr/bin/sudo",
            "/usr/bin/systemctl",
            "restart",
            "bluetooth.service",
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

        if path in ("/", "/index.html"):
            self.send_html(SPECTATOR_HTML)
            return

        if path in ("/tv", "/tv/"):
            tv_path = Path(__file__).with_name("tv.html")
            self.send_html(tv_path.read_text(encoding="utf-8"))
            return

        if path in ("/control", "/control/"):
            control_path = Path(__file__).with_name("control.html")
            self.send_html(control_path.read_text(encoding="utf-8"))
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

        if path == "/api/admin":
            success, message = admin_action(
                request.get("action", "")
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
    print(f"SCOREOS web server listening on port {PORT}")
    ThreadingHTTPServer((HOST, PORT), ScoreboardHandler).serve_forever()
