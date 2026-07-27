##!/usr/bin/env python3

import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path

DIAGNOSTICS_FILE = Path("/run/scoreos/diagnostics.json")
_lock = threading.Lock()
_last_device_refresh = 0.0
SERVICE_STARTED = time.time()


def _default():
    return {
        "bluetooth": {
            "connected": False,
            "connected_since": None,
            "service_started": SERVICE_STARTED,
            "waiting_for_first_packet": True,
            "last_packet": None,
            "packet_count": 0,
            "reconnects": 0,
            "device_name": None,
            "device_alias": None,
            "device_mac": None,
            "device_icon": None,
            "battery": None,
            "rssi": None,
        }
    }


def read():
    try:
        data = json.loads(DIAGNOSTICS_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return _default()


def write(data):
    DIAGNOSTICS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = DIAGNOSTICS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, DIAGNOSTICS_FILE)

def initialise():
    """Create a fresh diagnostics file whenever the service starts."""
    write(_default())

def _run_bluetoothctl(*arguments):
    try:
        result = subprocess.run(
            ["bluetoothctl", *arguments],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return result.stdout.strip()
    except Exception:
        return ""

def _connected_device_info():
    output = _run_bluetoothctl("devices", "Connected")

    if not output:
        return {}

    lines = [
        line.strip()
        for line in output.splitlines()
        if line.strip()
    ]

    SCORER_MAC = "80:19:31:6C:1B:61"

    first_line = next(
      (
        line
        for line in lines
        if SCORER_MAC in line.upper()
      ),
      lines[0],
    )

    parts = first_line.split(maxsplit=2)

    if len(parts) < 2 or parts[0] != "Device":
        return {}

    address = parts[1]
    fallback_name = parts[2] if len(parts) > 2 else None
    info_output = _run_bluetoothctl("info", address)

    device = {
        "device_mac": address,
        "device_name": fallback_name,
        "device_alias": fallback_name,
        "device_icon": None,
        "battery": None,
        "rssi": None,
    }

    for line in info_output.splitlines():
        stripped = line.strip()

        if stripped.startswith("Name:"):
            device["device_name"] = stripped.split(":", 1)[1].strip()

        elif stripped.startswith("Alias:"):
            device["device_alias"] = stripped.split(":", 1)[1].strip()

        elif stripped.startswith("Icon:"):
            device["device_icon"] = stripped.split(":", 1)[1].strip()

        elif stripped.startswith("RSSI:"):
            match = re.search(r"-?\d+", stripped.split(":", 1)[1])
            if match:
                device["rssi"] = int(match.group())

        elif stripped.startswith("Battery Percentage:"):
            match = re.search(r"\((\d+)\)", stripped)
            if match:
                device["battery"] = int(match.group(1))
            else:
                value = stripped.split(":", 1)[1].strip().split()[0]
                try:
                    device["battery"] = int(value, 0)
                except ValueError:
                    pass

    return device


def packet_received():
    global _last_device_refresh

    with _lock:
        data = read()
        bt = data.setdefault("bluetooth", _default()["bluetooth"])
        now = time.time()

        if (
            now - _last_device_refresh >= 60
            or not bt.get("device_mac")
        ):
            device = _connected_device_info()
            if device:
                bt.update(device)
            _last_device_refresh = now

        if not bt.get("connected", False):
            bt["connected"] = True
            bt["connected_since"] = now
            bt["reconnects"] = int(bt.get("reconnects", 0)) + 1

        bt["waiting_for_first_packet"] = False

        bt["last_packet"] = now
        bt["last_packet_iso"] = time.strftime(
            "%Y-%m-%d %H:%M:%S",
            time.localtime(now)
        )
        bt["packet_count"] = int(bt.get("packet_count", 0)) + 1

        write(data)
