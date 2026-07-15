#!/usr/bin/env python3

import json
import os
import socket
import threading
import time

from engine.matchstate import MatchState
from engine.parser import parse_playcricket_packet


STATE_FILE = "/run/scoreos/state.json"
CONTROL_SOCKET = "/run/scoreos/control.sock"


def number(value):
    cleaned = str(value).replace("-", "").strip()

    try:
        return int(cleaned or "0")
    except ValueError:
        return 0


def padded(value, length):
    return str(max(0, int(value))).rjust(length, "-")


class ScoreboardEngine:
    def __init__(self, arduino, publish_delay=0.20):
        self.state = MatchState()
        self.arduino = arduino
        self.publish_delay = publish_delay
        self.last_packet_time = 0.0
        self.lock = threading.RLock()
        self.timer = None
        self.mode = "playcricket"

        self.start_control_server()

    def receive_packet(self, packet):
        packet = packet.strip()

        if not packet:
            return

        if self.mode != "playcricket":
            print("Play-Cricket packet ignored: manual mode")
            return

        print("RXRAW:", packet)

        with self.lock:
            parse_playcricket_packet(self.state, packet)
            self.last_packet_time = time.monotonic()

            if self.timer is not None:
                self.timer.cancel()

            self.timer = threading.Timer(
                self.publish_delay,
                self.publish,
            )
            self.timer.daemon = True
            self.timer.start()

    def arduino_message(self):
        return (
            "4,"
            + self.state.bat_a_runs + ","
            + self.state.total + ","
            + self.state.bat_b_runs + ","
            + self.state.wickets + ","
            + self.state.overs + ","
            + self.state.target + "#"
        )

    def calculate_runs_required(self):
        target = number(self.state.target)
        total = number(self.state.total)

        if target <= 0:
            self.state.runs_required = "---"
        else:
            self.state.runs_required = padded(
                max(0, target - total),
                3,
            )

    def append_current_over(self, value):
        existing = self.state.current_over.strip()

        if existing in ("", "-"):
            updated = str(value)
        else:
            updated = existing + " " + str(value)

        self.state.update("current_over", updated)

    def adjust_partnership(self, delta):
        partnership = max(
            0,
            number(self.state.partnership) + int(delta),
        )
        self.state.update("partnership", str(partnership))

    def write_state_json(self):
        snapshot = self.state.snapshot()
        snapshot["mode"] = self.mode

        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        temporary_file = STATE_FILE + ".tmp"

        with open(temporary_file, "w", encoding="utf-8") as handle:
            json.dump(snapshot, handle, indent=2)

        os.replace(temporary_file, STATE_FILE)
        print("State written:", STATE_FILE)

    def publish_locked(self):
        message = self.arduino_message()
        self.arduino.send(message)
        self.write_state_json()
        self.state.changed = False
        self.timer = None

    def publish(self):
        with self.lock:
            self.publish_locked()

    def adjust_score(self, delta, add_to_over=True):
        old_total = number(self.state.total)
        new_total = max(0, old_total + int(delta))
        actual_delta = new_total - old_total

        self.state.update("total", padded(new_total, 3))
        self.adjust_partnership(actual_delta)
        self.calculate_runs_required()

        if add_to_over and actual_delta >= 0:
            self.append_current_over(actual_delta)

    def adjust_batter(self, batter, delta):
        field = "bat_a_runs" if batter == "a" else "bat_b_runs"

        old_score = number(getattr(self.state, field))
        new_score = max(0, old_score + int(delta))
        actual_delta = new_score - old_score

        self.state.update(field, padded(new_score, 3))
        self.adjust_score(actual_delta, add_to_over=False)

        if actual_delta >= 0:
            self.append_current_over(actual_delta)

    def take_wicket(self, batter):
        if batter not in ("a", "b"):
            raise ValueError("Invalid batter")

        wickets = min(9, number(self.state.wickets) + 1)
        batter_field = (
            "bat_a_runs" if batter == "a" else "bat_b_runs"
        )
        batter_score = number(getattr(self.state, batter_field))
        current_total = number(self.state.total)

        self.state.update("wickets", str(wickets))
        self.state.update("last_man", padded(batter_score, 3))
        self.state.update("last_wicket", padded(current_total, 3))
        self.state.update("partnership", "0")
        self.state.update(batter_field, "--0")
        self.append_current_over("W")

    def adjust_overs(self, delta):
        overs = max(0, number(self.state.overs) + int(delta))
        self.state.update("overs", padded(overs, 2))

        if int(delta) > 0:
            self.state.update("current_over", "-")

    def adjust_target(self, delta):
        target = max(0, number(self.state.target) + int(delta))
        self.state.update("target", padded(target, 3))
        self.calculate_runs_required()

    def apply_control(self, request):
        action = request.get("action")
        value = request.get("value", 0)

        with self.lock:
            if action == "set_mode":
                if value not in ("manual", "playcricket"):
                    raise ValueError("Invalid mode")

                self.mode = value
                print("Control mode:", self.mode)
                self.write_state_json()

                return {
                    "ok": True,
                    "mode": self.mode,
                }

            self.mode = "manual"

            if action == "score":
                self.adjust_score(int(value))

            elif action == "bat_a":
                self.adjust_batter("a", int(value))

            elif action == "bat_b":
                self.adjust_batter("b", int(value))

            elif action == "batter_wicket":
                self.take_wicket(str(value))

            elif action == "wickets":
                wickets = max(
                    0,
                    min(
                        9,
                        number(self.state.wickets) + int(value),
                    ),
                )
                self.state.update("wickets", str(wickets))

                if int(value) > 0:
                    self.state.update(
                        "last_wicket",
                        padded(number(self.state.total), 3),
                    )
                    self.state.update("partnership", "0")
                    self.append_current_over("W")

            elif action == "overs":
                self.adjust_overs(int(value))

            elif action == "target":
                self.adjust_target(int(value))

            elif action == "set_target":
                target = max(0, min(999, int(value)))
                self.state.update("target", padded(target, 3))
                self.calculate_runs_required()

            elif action == "reset":
                self.state = MatchState()

            else:
                raise ValueError("Unknown action")

            self.publish_locked()

            return {
                "ok": True,
                "mode": self.mode,
                "state": self.state.snapshot(),
            }

    def start_control_server(self):
        thread = threading.Thread(
            target=self.control_server,
            name="scoreos-control",
            daemon=True,
        )
        thread.start()

    def control_server(self):
        os.makedirs(os.path.dirname(CONTROL_SOCKET), exist_ok=True)

        try:
            os.unlink(CONTROL_SOCKET)
        except FileNotFoundError:
            pass

        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(CONTROL_SOCKET)
        os.chmod(CONTROL_SOCKET, 0o666)
        server.listen(5)

        print("Control socket ready:", CONTROL_SOCKET)

        while True:
            connection, _ = server.accept()

            with connection:
                try:
                    raw_data = connection.recv(4096)
                    request = json.loads(raw_data.decode("utf-8"))
                    response = self.apply_control(request)

                except Exception as exc:
                    response = {
                        "ok": False,
                        "error": str(exc),
                    }

                connection.sendall(
                    json.dumps(response).encode("utf-8")
                )
