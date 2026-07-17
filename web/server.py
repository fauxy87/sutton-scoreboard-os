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


from config.settings import get, getint

STATE_FILE = Path("/run/scoreos/state.json")
CONTROL_SOCKET = "/run/scoreos/control.sock"

HOST = get("web", "host")
PORT = getint("web", "port")

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
    info = run_command([
        "/usr/bin/btmgmt",
        "info",
    ])

    name = "Unknown"

    for line in info.splitlines():
        stripped = line.strip()

        if stripped.startswith("name "):
            name = stripped[5:].strip()
            break

    advert_service = service_status(
        "sutton-scoreboard-advert.service"
    )

    return {
        "service": service_status("bluetooth.service"),
        "name": name,
        "advertising": advert_service == "active",
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

        if path in ("/control", "/control/"):
            self.send_html(CONTROL_HTML)
            return

        if path in ("/admin", "/admin/"):
            self.send_html(ADMIN_HTML)
            return

        self.send_error(404)

    def do_POST(self):
        path = urlparse(self.path).path

        if path != "/api/control":
            self.send_error(404)
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(length)
            request = json.loads(raw_body.decode("utf-8"))

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
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sutton CC Scoreboard Control</title>

<style>
:root {
    --green: #146b3a;
    --green-dark: #0a4323;
    --yellow: #ffd800;
    --red: #c62828;
    --grey: #5c6260;
    --background: #e7ece8;
    --panel: #ffffff;
}

* {
    box-sizing: border-box;
}

html,
body {
    margin: 0;
    min-height: 100%;
    background: var(--background);
    color: #172019;
    font-family: Arial, Helvetica, sans-serif;
}

body {
    overflow-x: hidden;
}

header {
    padding: 6px 10px;
    background: var(--green);
    color: white;
    text-align: center;
    border-bottom: 5px solid var(--yellow);
}

header h1 {
    margin: 0;
    font-size: 1.35rem;
    line-height: 1.15;
}

header p {
    margin: 2px 0 0;
    font-size: .82rem;
    line-height: 1.1;
}

main {
    width: 100%;
    max-width: 1200px;
    margin: 0 auto;
    padding: 6px;
}

.panel {
    margin-bottom: 6px;
    overflow: hidden;
    background: var(--panel);
    border: 2px solid var(--green);
    border-radius: 8px;
}

.panel-title {
    margin: 0;
    padding: 5px;
    background: var(--green);
    color: white;
    text-align: center;
    font-size: .95rem;
    line-height: 1.1;
}

.panel-body {
    padding: 6px;
}

.score-row {
    display: grid;
    grid-template-columns: 2fr 1fr 1fr;
    gap: 6px;
    text-align: center;
    align-items: center;
}

.label {
    color: var(--green-dark);
    font-size: .82rem;
    font-weight: bold;
    line-height: 1.1;
}

.main-score {
    margin-top: 2px;
    font-size: 3.4rem;
    line-height: .95;
    font-weight: bold;
}

.secondary-score {
    margin-top: 3px;
    font-size: 2.4rem;
    line-height: .95;
    font-weight: bold;
}

.batter-row {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 6px;
}

.batter-card {
    overflow: hidden;
    background: white;
    border: 2px solid var(--green);
    border-radius: 8px;
    text-align: center;
}

.batter-heading {
    padding: 5px;
    background: var(--green);
    color: white;
    font-size: .9rem;
    font-weight: bold;
    line-height: 1.1;
}

.batter-score {
    padding: 4px;
    font-size: 3rem;
    font-weight: bold;
    line-height: 1;
}

.button-grid {
    display: grid;
    grid-template-columns: repeat(6, 1fr);
    gap: 5px;
}

.button-grid.four {
    grid-template-columns: repeat(4, 1fr);
}

.button-grid.three {
    grid-template-columns: repeat(3, 1fr);
}

button {
    min-width: 0;
    min-height: 43px;
    padding: 4px 3px;
    border: 0;
    border-radius: 6px;
    background: var(--green);
    color: white;
    box-shadow: 0 2px 3px rgba(0, 0, 0, .18);
    font-size: 1rem;
    font-weight: bold;
    line-height: 1;
    cursor: pointer;
    touch-action: manipulation;
}

button.yellow {
    background: var(--yellow);
    color: #111;
}

button.red {
    background: var(--red);
}

button.grey {
    background: var(--grey);
}

button.selected {
    outline: 4px solid var(--yellow);
    outline-offset: -3px;
}

button:active {
    transform: translateY(1px);
    box-shadow: none;
}

.target-form {
    display: grid;
    grid-template-columns: 2fr 1fr;
    gap: 6px;
}

.target-form input {
    width: 100%;
    min-height: 43px;
    padding: 4px 10px;
    border: 2px solid var(--green);
    border-radius: 6px;
    font-size: 1.35rem;
    font-weight: bold;
    text-align: center;
}

.mode-row {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 6px;
}

.info-row {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 6px;
    text-align: center;
}

.info-value {
    font-size: 1.35rem;
    font-weight: bold;
    line-height: 1.05;
}

.status {
    padding: 6px;
    border-radius: 6px;
    background: var(--green-dark);
    color: white;
    text-align: center;
    font-size: .85rem;
    font-weight: bold;
}

.status.error {
    background: var(--red);
}

.footer {
    margin: 5px 0;
    text-align: center;
    font-size: .8rem;
}

/*
 * Compact landscape mode for tablets.
 * Keeps total, overs, target and batter controls visible together.
 */
@media (orientation: landscape) and (max-height: 800px) {
    header {
        padding: 4px 8px;
        border-bottom-width: 4px;
    }

    header h1 {
        font-size: 1.15rem;
    }

    header p {
        display: none;
    }

    main {
        padding: 4px;
    }

    .panel {
        margin-bottom: 4px;
    }

    .panel-title {
        padding: 4px;
        font-size: .82rem;
    }

    .panel-body {
        padding: 4px;
    }

    .score-row,
    .batter-row,
    .button-grid,
    .target-form,
    .mode-row,
    .info-row {
        gap: 4px;
    }

    .label {
        font-size: .72rem;
    }

    .main-score {
        font-size: 2.8rem;
    }

    .secondary-score {
        font-size: 2rem;
    }

    .batter-heading {
        padding: 3px;
        font-size: .8rem;
    }

    .batter-score {
        padding: 2px;
        font-size: 2.35rem;
    }

    button {
        min-height: 37px;
        padding: 3px 2px;
        font-size: .9rem;
    }

    .target-form input {
        min-height: 37px;
        padding: 3px 8px;
        font-size: 1.15rem;
    }

    .info-value {
        font-size: 1.15rem;
    }

    .status {
        padding: 4px;
        font-size: .75rem;
    }

    .footer {
        margin: 3px 0;
    }
}

/* Smaller phones and portrait tablets remain usable with scrolling. */
@media (max-width: 700px) and (orientation: portrait) {
    .score-row {
        grid-template-columns: 1fr 1fr;
    }

    .score-row > :first-child {
        grid-column: 1 / -1;
    }

    .batter-row {
        grid-template-columns: 1fr;
    }

    .button-grid {
        grid-template-columns: repeat(3, 1fr);
    }

    button {
        min-height: 48px;
    }
}
</style>
</head>

<body>
<header>
    <h1>Sutton CC Scoreboard</h1>
    <p>SCOREOS Manual Control</p>
</header>

<main>
    <section class="panel">
        <div class="panel-body">
            <div class="score-row">
                <div>
                    <div class="label">TOTAL</div>
                    <div class="main-score">
                        <span id="total">0</span>/<span id="wickets">0</span>
                    </div>
                </div>

                <div>
                    <div class="label">OVERS</div>
                    <div class="secondary-score" id="overs">0</div>
                </div>

                <div>
                    <div class="label">TARGET</div>
                    <div class="secondary-score" id="target">0</div>
                </div>
            </div>
        </div>
    </section>

    <section class="batter-row">
        <div class="batter-card">
            <div class="batter-heading">BATTER A</div>
            <div class="batter-score" id="bat-a-score">0</div>

            <div class="panel-body">
                <div class="button-grid">
                    <button class="yellow" onclick="control('bat_a', 1)">+1</button>
                    <button class="yellow" onclick="control('bat_a', 2)">+2</button>
                    <button class="yellow" onclick="control('bat_a', 3)">+3</button>
                    <button class="yellow" onclick="control('bat_a', 4)">+4</button>
                    <button class="yellow" onclick="control('bat_a', 6)">+6</button>
                    <button class="red" onclick="batterWicket('a')">WICKET</button>
                    <button class="grey" onclick="control('bat_a', -1)">−1</button>
                    <button class="grey" onclick="control('bat_a', -4)">−4</button>
                    <button class="grey" onclick="control('bat_a', -6)">−6</button>
                </div>
            </div>
        </div>

        <div class="batter-card">
            <div class="batter-heading">BATTER B</div>
            <div class="batter-score" id="bat-b-score">0</div>

            <div class="panel-body">
                <div class="button-grid">
                    <button class="yellow" onclick="control('bat_b', 1)">+1</button>
                    <button class="yellow" onclick="control('bat_b', 2)">+2</button>
                    <button class="yellow" onclick="control('bat_b', 3)">+3</button>
                    <button class="yellow" onclick="control('bat_b', 4)">+4</button>
                    <button class="yellow" onclick="control('bat_b', 6)">+6</button>
                    <button class="red" onclick="batterWicket('b')">WICKET</button>
                    <button class="grey" onclick="control('bat_b', -1)">−1</button>
                    <button class="grey" onclick="control('bat_b', -4)">−4</button>
                    <button class="grey" onclick="control('bat_b', -6)">−6</button>
                </div>
            </div>
        </div>
    </section>

    <section class="panel">
        <h2 class="panel-title">TOTAL RUNS</h2>
        <div class="panel-body">
            <div class="button-grid">
                <button class="grey" onclick="control('score', -1)">−1</button>
                <button class="yellow" onclick="control('score', 1)">+1</button>
                <button class="yellow" onclick="control('score', 2)">+2</button>
                <button class="yellow" onclick="control('score', 3)">+3</button>
                <button class="yellow" onclick="control('score', 4)">+4</button>
                <button class="yellow" onclick="control('score', 6)">+6</button>
            </div>
        </div>
    </section>

    <section class="panel">
        <h2 class="panel-title">WICKETS AND OVERS</h2>
        <div class="panel-body">
            <div class="button-grid four">
                <button class="red" onclick="control('wickets', 1)">
                    + WICKET
                </button>

                <button class="grey" onclick="control('wickets', -1)">
                    − WICKET
                </button>

                <button onclick="control('overs', 1)">
                    + OVER
                </button>

                <button class="grey" onclick="control('overs', -1)">
                    − OVER
                </button>
            </div>
        </div>
    </section>

    <section class="panel">
        <h2 class="panel-title">TARGET</h2>
        <div class="panel-body">
            <form class="target-form" onsubmit="setExactTarget(event)">
                <input
                    id="target-input"
                    type="number"
                    min="0"
                    max="999"
                    inputmode="numeric"
                    placeholder="Enter target"
                    required>

                <button class="yellow" type="submit">
                    SET TARGET
                </button>
            </form>
        </div>
    </section>

    <section class="panel">
        <div class="panel-body">
            <div class="info-row">
                <div>
                    <div class="label">CURRENT OVER</div>
                    <div class="info-value" id="current-over">-</div>
                </div>

                <div>
                    <div class="label">PARTNERSHIP</div>
                    <div class="info-value" id="partnership">0</div>
                </div>

                <div>
                    <div class="label">LAST WICKET</div>
                    <div class="info-value" id="last-wicket">---</div>
                </div>

                <div>
                    <div class="label">LAST MAN</div>
                    <div class="info-value" id="last-man">---</div>
                </div>

                <div>
                    <div class="label">RUNS REQUIRED</div>
                    <div class="info-value" id="runs-required">---</div>
                </div>
            </div>
        </div>
    </section>

    <section class="panel">
        <div class="panel-body">
            <div class="button-grid three">
                <button class="grey" onclick="refreshState()">REFRESH</button>
                <button class="red" onclick="resetInnings()">RESET INNINGS</button>
                <button onclick="setMode('playcricket')">
                    RETURN TO PLAY-CRICKET
                </button>
            </div>
        </div>
    </section>

    <section class="panel">
        <h2 class="panel-title">CONTROL MODE</h2>
        <div class="panel-body">
            <div class="mode-row">
                <button id="playcricket-mode"
                        onclick="setMode('playcricket')">
                    Play-Cricket
                </button>

                <button id="manual-mode"
                        class="yellow"
                        onclick="setMode('manual')">
                    Manual Control
                </button>
            </div>
        </div>
    </section>

    <div id="status" class="status">
        Connecting to SCOREOS...
    </div>

    <div class="footer">
        <a href="/">Open spectator display</a>
    </div>
</main>

<script>
function visibleNumber(value) {
    if (value === null || value === undefined) {
        return "0";
    }

    const cleaned = String(value).replaceAll("-", "");
    return cleaned === "" ? "0" : cleaned;
}

async function apiControl(action, value = 0) {
    const response = await fetch("/api/control", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            action: action,
            value: value
        })
    });

    const result = await response.json();

    if (!response.ok || !result.ok) {
        throw new Error(result.error || "Control request failed");
    }

    return result;
}

async function control(action, value) {
    try {
        setStatus("Updating scoreboard...");
        await apiControl(action, value);
        await refreshState();
        setStatus("Scoreboard updated");
    } catch (error) {
        setStatus(error.message, true);
    }
}

async function batterWicket(batter) {
    const confirmed = window.confirm(
        "Record a wicket and reset this batter to zero?"
    );

    if (!confirmed) {
        return;
    }

    try {
        setStatus("Recording wicket...");
        await apiControl("batter_wicket", batter);
        await refreshState();
        setStatus("Wicket recorded");
    } catch (error) {
        setStatus(error.message, true);
    }
}

async function setExactTarget(event) {
    event.preventDefault();

    const input = document.getElementById("target-input");
    const target = Number(input.value);

    if (!Number.isInteger(target) || target < 0 || target > 999) {
        setStatus("Target must be between 0 and 999", true);
        return;
    }

    try {
        setStatus("Setting target...");
        await apiControl("set_target", target);
        input.value = "";
        await refreshState();
        setStatus("Target updated");
    } catch (error) {
        setStatus(error.message, true);
    }
}

async function setMode(mode) {
    try {
        await apiControl("set_mode", mode);
        await refreshState();
        setStatus("Mode changed to " + mode);
    } catch (error) {
        setStatus(error.message, true);
    }
}

async function resetInnings() {
    if (!window.confirm("Reset the complete innings to zero?")) {
        return;
    }

    try {
        await apiControl("reset", 0);
        await refreshState();
        setStatus("Innings reset");
    } catch (error) {
        setStatus(error.message, true);
    }
}

function setStatus(message, error = false) {
    const element = document.getElementById("status");
    element.textContent = message;
    element.classList.toggle("error", error);
}

function updateMode(mode) {
    document.getElementById("playcricket-mode")
        .classList.toggle("selected", mode === "playcricket");

    document.getElementById("manual-mode")
        .classList.toggle("selected", mode === "manual");
}

async function refreshState() {
    try {
        const response = await fetch("/api/state", {
            cache: "no-store"
        });

        const state = await response.json();

        document.getElementById("total").textContent =
            visibleNumber(state.total);

        document.getElementById("wickets").textContent =
            visibleNumber(state.wickets);

        document.getElementById("overs").textContent =
            visibleNumber(state.overs);

        document.getElementById("target").textContent =
            visibleNumber(state.target);

        document.getElementById("bat-a-score").textContent =
            visibleNumber(state.BatAscore);

        document.getElementById("bat-b-score").textContent =
            visibleNumber(state.BatBscore);

        document.getElementById("current-over").textContent =
            state.CurrentOver || "-";

        document.getElementById("partnership").textContent =
            visibleNumber(state.PshipTOT);

        document.getElementById("last-wicket").textContent =
            state.LastWicket || "---";

        document.getElementById("last-man").textContent =
            visibleNumber(state.LastMan);

        document.getElementById("runs-required").textContent =
            visibleNumber(state.RunsRequired);

        updateMode(state.mode || "playcricket");
        setStatus("Connected — " + (state.mode || "playcricket"));

    } catch (error) {
        setStatus("Unable to reach SCOREOS", true);
    }
}

refreshState();
setInterval(refreshState, 1000);
</script>
</body>
</html>
"""


if __name__ == "__main__":
    print(f"SCOREOS web server listening on port {PORT}")
    ThreadingHTTPServer((HOST, PORT), ScoreboardHandler).serve_forever()
