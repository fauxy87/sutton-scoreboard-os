#!/usr/bin/env python3

import json
import os
import threading
import time

from engine.matchstate import MatchState
from engine.parser import parse_playcricket_packet

STATE_FILE = "/run/scoreos/state.json"


class ScoreboardEngine:
    def __init__(self, arduino, publish_delay=0.20):
        self.state = MatchState()
        self.arduino = arduino
        self.publish_delay = publish_delay
        self.last_packet_time = 0.0
        self.lock = threading.Lock()
        self.timer = None

    def receive_packet(self, packet):
        packet = packet.strip()
        if not packet:
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

    def write_state_json(self):
        snapshot = self.state.snapshot()
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)

        temp_file = STATE_FILE + ".tmp"

        with open(temp_file, "w", encoding="utf-8") as handle:
            json.dump(snapshot, handle, indent=2)

        os.replace(temp_file, STATE_FILE)
        print("State written:", STATE_FILE)

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

    def publish(self):
        with self.lock:
            message = self.arduino_message()
            self.arduino.send(message)
            self.write_state_json()
            self.state.changed = False
            self.timer = None
