#!/usr/bin/env python3

import json
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


STATE_FILE = Path("/run/scoreos/state.json")
CONTROL_SOCKET = "/run/scoreos/control.sock"

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


class ScoreboardHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/api/state":
            self.send_json(read_state())
            return

        if path in ("/", "/index.html"):
            self.send_html(SPECTATOR_HTML)
            return

        if path in ("/control", "/control/"):
            self.send_html(CONTROL_HTML)
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

body {
    margin: 0;
    background: var(--background);
    font-family: Arial, Helvetica, sans-serif;
    color: #172019;
}

header {
    background: var(--green);
    color: white;
    text-align: center;
    padding: 12px;
    border-bottom: 8px solid var(--yellow);
}

header h1 {
    margin: 0;
    font-size: 1.7rem;
}

header p {
    margin: 4px 0 0;
}

main {
    max-width: 1100px;
    margin: 0 auto;
    padding: 12px;
}

.panel {
    background: var(--panel);
    border: 3px solid var(--green);
    border-radius: 10px;
    margin-bottom: 12px;
    overflow: hidden;
}

.panel-title {
    margin: 0;
    padding: 8px;
    background: var(--green);
    color: white;
    text-align: center;
    font-size: 1.1rem;
}

.panel-body {
    padding: 12px;
}

.score-row {
    display: grid;
    grid-template-columns: 2fr 1fr 1fr;
    gap: 10px;
    text-align: center;
}

.label {
    color: var(--green-dark);
    font-weight: bold;
}

.main-score {
    font-size: 4.5rem;
    line-height: 1;
    font-weight: bold;
    margin-top: 4px;
}

.secondary-score {
    font-size: 3rem;
    line-height: 1;
    font-weight: bold;
    margin-top: 10px;
}

.batter-row {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
}

.batter-card {
    border: 3px solid var(--green);
    border-radius: 9px;
    overflow: hidden;
    background: white;
    text-align: center;
}

.batter-heading {
    background: var(--green);
    color: white;
    font-weight: bold;
    padding: 8px;
}

.batter-score {
    font-size: 4.5rem;
    font-weight: bold;
    line-height: 1;
    padding: 12px 8px;
}

.button-grid {
    display: grid;
    grid-template-columns: repeat(6, 1fr);
    gap: 8px;
}

.button-grid.four {
    grid-template-columns: repeat(4, 1fr);
}

.button-grid.three {
    grid-template-columns: repeat(3, 1fr);
}

button {
    border: 0;
    border-radius: 8px;
    min-height: 62px;
    font-size: 1.3rem;
    font-weight: bold;
    cursor: pointer;
    touch-action: manipulation;
    color: white;
    background: var(--green);
    box-shadow: 0 2px 3px rgba(0,0,0,.22);
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
    outline: 5px solid var(--yellow);
}

button:active {
    transform: translateY(2px);
    box-shadow: none;
}

.target-form {
    display: grid;
    grid-template-columns: 2fr 1fr;
    gap: 10px;
}

.target-form input {
    min-height: 62px;
    width: 100%;
    padding: 8px 14px;
    border: 3px solid var(--green);
    border-radius: 8px;
    font-size: 2rem;
    font-weight: bold;
    text-align: center;
}

.mode-row {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
}

.info-row {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 10px;
    text-align: center;
}

.info-value {
    font-size: 1.8rem;
    font-weight: bold;
}

.status {
    padding: 11px;
    border-radius: 8px;
    background: var(--green-dark);
    color: white;
    text-align: center;
    font-weight: bold;
}

.status.error {
    background: var(--red);
}

.footer {
    text-align: center;
    margin: 12px 0;
}

.footer a {
    color: var(--green-dark);
    font-weight: bold;
}

@media (max-width: 760px) {
    .score-row {
        grid-template-columns: 1fr 1fr;
    }

    .score-row > div:first-child {
        grid-column: 1 / -1;
    }

    .batter-row {
        grid-template-columns: 1fr;
    }

    .button-grid {
        grid-template-columns: repeat(3, 1fr);
    }

    .button-grid.four {
        grid-template-columns: repeat(2, 1fr);
    }

    .info-row {
        grid-template-columns: 1fr;
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
