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

def _connected_device_info():
    """Return scorer metadata without launching bluetoothctl."""
    return {"device_mac": "80:19:31:6C:1B:61", "device_name": "Play-Cricket Scorer", "device_alias": "Play-Cricket Scorer", "device_icon": None, "battery": None, "rssi": None}



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
