#!/usr/bin/env python3

import glob
import os
import threading
import time

import serial


SERIAL_CANDIDATES = [
    "/dev/serial/by-id/usb-Arduino__www.arduino.cc__0043_0353534353535151D2E2-if00",
    "/dev/ttyACM0",
    "/dev/ttyUSB0",
]

BAUD_RATE = 57600


class ArduinoConnection:
    def __init__(self):
        self.serial = None
        self.device = None
        self.lock = threading.Lock()
        self.last_message = None

    def find_device(self):
        by_id = sorted(glob.glob("/dev/serial/by-id/*"))
        if by_id:
            return by_id[0]

        for device in SERIAL_CANDIDATES:
            if os.path.exists(device):
                return device

        return None

    def connect(self):
        if self.serial is not None and self.serial.is_open:
            return True

        device = self.find_device()
        if device is None:
            print("Arduino not found")
            return False

        try:
            self.serial = serial.Serial(
                device,
                BAUD_RATE,
                timeout=1,
                write_timeout=2,
            )
            self.device = device

            # Allow the Arduino to settle after opening the port.
            time.sleep(1.5)

            print("Arduino connected:", device)
            return True

        except Exception as exc:
            print("Arduino connection failed:", exc)
            self.close()
            return False

    def close(self):
        try:
            if self.serial is not None:
                self.serial.close()
        except Exception:
            pass

        self.serial = None
        self.device = None

    def send(self, message, force=False):
        with self.lock:
            if not force and message == self.last_message:
                return True

            if not self.connect():
                return False

            try:
                self.serial.write(message.encode("utf-8"))
                self.serial.flush()
                self.last_message = message
                print("Sent to Arduino:", message)
                return True

            except Exception as exc:
                print("Arduino send failed:", exc)
                self.close()
                return False
