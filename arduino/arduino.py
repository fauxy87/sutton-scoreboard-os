#!/usr/bin/env python3
import os
import serial
import time

SERIAL_CANDIDATES = [
    "/dev/serial/by-id/usb-Arduino__www.arduino.cc__0043_0353534353535151D2E2-if00",
    "/dev/ttyACM0",
    "/dev/ttyUSB0",
]

BAUD_RATE = 57600

def find_arduino():
    for dev in SERIAL_CANDIDATES:
        if os.path.exists(dev):
            return dev
    return None

def send_to_arduino(message):
    dev = find_arduino()

    if not dev:
        print("Arduino not found")
        return False

    try:
        with serial.Serial(dev, BAUD_RATE, timeout=2) as ser:
            time.sleep(0.2)
            ser.write(message.encode("utf-8"))
            ser.flush()
        print("Sent to Arduino:", message)
        return True

    except Exception as e:
        print("Arduino send failed:", e)
        return False
