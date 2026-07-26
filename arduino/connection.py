#!/usr/bin/env python3

import glob
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from web.startup import startup_manager

import serial


SERIAL_CANDIDATES = [
    "/dev/serial/by-id/usb-Arduino__www.arduino.cc__0043_0353534353535151D2E2-if00",
    "/dev/ttyACM0",
    "/dev/ttyUSB0",
]

BAUD_RATE = 57600
LOG_FILE = Path("/run/scoreos/arduino-serial.log")


class ArduinoConnection:
    def __init__(self):
        self.serial = None
        self.device = None
        self.lock = threading.Lock()
        self.last_message = None
        self.sequence = 0

        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        self._log("ArduinoConnection started")

    def _log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        line = f"{timestamp} {message}"

        print(line, flush=True)

        try:
            with LOG_FILE.open("a", encoding="utf-8") as log:
                log.write(line + "\n")
        except Exception as exc:
            print(f"{timestamp} Unable to write Arduino log: {exc}", flush=True)

    def find_device(self):
        by_id = sorted(glob.glob("/dev/serial/by-id/*"))

        if by_id:
            self._log(f"Serial device found by ID: {by_id[0]}")
            return by_id[0]

        for device in SERIAL_CANDIDATES:
            if os.path.exists(device):
                self._log(f"Serial device found: {device}")
                return device

        return None

    def connect(self):
        if self.serial is not None and self.serial.is_open:
            return True

        device = self.find_device()

        if device is None:
            self._log("Arduino not found")
            return False

        try:
            self._log(f"Opening Arduino serial port: {device}")

            self.serial = serial.Serial(
                device,
                BAUD_RATE,
                timeout=1,
                write_timeout=2,
            )

            self.device = device

            # Allow the Arduino to settle after the USB serial port opens.
            time.sleep(1.5)

            self._log(
                "Arduino connected: "
                f"device={device} "
                f"in_waiting={self.serial.in_waiting} "
                f"out_waiting={self.serial.out_waiting}"
            )

            startup_manager.set_stage(
              "arduino",
              "✓ Arduino connected"
            )
            return True

        except Exception as exc:
            self._log(f"Arduino connection failed: {exc!r}")
            self.close()
            return False

    def close(self):
        if self.serial is not None:
            try:
                self._log(
                    "Closing Arduino serial port: "
                    f"device={self.device} "
                    f"in_waiting={self.serial.in_waiting} "
                    f"out_waiting={self.serial.out_waiting}"
                )
            except Exception:
                self._log(
                    f"Closing Arduino serial port: device={self.device}"
                )

            try:
                self.serial.close()
            except Exception as exc:
                self._log(f"Arduino close failed: {exc!r}")

        self.serial = None
        self.device = None

    def send(self, message, force=False):
        with self.lock:
            if not force and message == self.last_message:
                self._log(f"Duplicate skipped: {message!r}")
                return True

            if not self.connect():
                return False

            try:
                self.sequence += 1

                before_in = self.serial.in_waiting
                before_out = self.serial.out_waiting

                encoded = message.encode("utf-8")

                self._log(
                    f"SEND #{self.sequence}: "
                    f"bytes={len(encoded)} "
                    f"in_waiting_before={before_in} "
                    f"out_waiting_before={before_out} "
                    f"packet={message!r}"
                )

                written = self.serial.write(encoded)
                self.serial.flush()

                after_in = self.serial.in_waiting
                after_out = self.serial.out_waiting

                self.last_message = message

                self._log(
                    f"SENT #{self.sequence}: "
                    f"written={written} "
                    f"in_waiting_after={after_in} "
                    f"out_waiting_after={after_out}"
                )

                return True

            except Exception as exc:
                self._log(
                    f"Arduino send failed #{self.sequence}: {exc!r}"
                )
                self.close()
                return False
