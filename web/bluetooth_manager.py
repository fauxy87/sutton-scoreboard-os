#!/usr/bin/env python3

import re
import subprocess
import threading
import time


PAIRING_SECONDS = 60

_lock = threading.Lock()
_pairing_active = False
_pairing_ends_at = 0.0
_pairing_process = None
_last_message = "Bluetooth manager ready"


def run_command(command, timeout=5):
    """Run a command and return its output and exit code."""
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
            check=False,
        )
        return result.stdout.strip(), result.returncode
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout or ""

        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")

        return output.strip(), 124

    except Exception as exc:
        return str(exc), 1


def bluetoothctl(command, timeout=5):
    """Run a single bluetoothctl command."""
    return run_command(
        ["/usr/bin/bluetoothctl", "--timeout", str(timeout), *command],
        timeout=timeout + 2,
    )


def adapter_info():
    output, code = bluetoothctl(["show"])

    info = {
        "available": code == 0 and "Controller " in output,
        "powered": False,
        "discoverable": False,
        "pairable": False,
        "address": None,
        "name": None,
    }

    for raw_line in output.splitlines():
        line = raw_line.strip()

        if line.startswith("Controller "):
            parts = line.split()
            if len(parts) >= 2:
                info["address"] = parts[1]

        elif line.startswith("Name:"):
            info["name"] = line.split(":", 1)[1].strip()

        elif line.startswith("Powered:"):
            info["powered"] = line.endswith("yes")

        elif line.startswith("Discoverable:"):
            info["discoverable"] = line.endswith("yes")

        elif line.startswith("Pairable:"):
            info["pairable"] = line.endswith("yes")

    return info


def paired_devices():
    devices_seen = {}

    for command in (["devices", "Paired"], ["devices", "Connected"]):
        output, _ = bluetoothctl(command)

        for raw_line in output.splitlines():
            match = re.match(
                r"^Device\s+([0-9A-Fa-f:]{17})\s+(.+)$",
                raw_line.strip(),
            )

            if not match:
                continue

            address = match.group(1).upper()
            name = match.group(2).strip()

            devices_seen[address] = name

    devices = []

    for address, name in devices_seen.items():
        details, _ = bluetoothctl(["info", address])

        connected = "Connected: yes" in details
        trusted = "Trusted: yes" in details
        bonded = (
            "Bonded: yes" in details
            or "Paired: yes" in details
        )

        devices.append(
            {
                "address": address,
                "name": name,
                "connected": connected,
                "trusted": trusted,
                "bonded": bonded,
            }
        )

    return devices

def advertising_active():
    output, code = run_command(
        [
            "/usr/bin/script",
            "-q",
            "-c",
            "/usr/bin/btmgmt --index 0 advinfo",
            "/dev/null",
        ],
        timeout=8,
    )

    match = re.search(
        r"Instances list with\s+(\d+)\s+item",
        output,
        re.IGNORECASE,
    )

    if match:
        return int(match.group(1)) > 0

    return False


def service_active(service_name):
    output, code = run_command(
        ["/usr/bin/systemctl", "is-active", service_name],
        timeout=5,
    )

    return code == 0 and output.strip() == "active"


def pairing_seconds_remaining():
    if not _pairing_active:
        return 0

    return max(0, int(_pairing_ends_at - time.time()))


def get_status():
    adapter = adapter_info()
    devices = paired_devices()

    return {
        "ok": True,
        "adapter": adapter,
        "advertising": advertising_active(),
        "gatt_service": service_active("sutton-scoreboard.service"),
        "advert_service": service_active(
            "sutton-scoreboard-advert.service"
        ),
        "pairing_active": _pairing_active,
        "pairing_seconds_remaining": pairing_seconds_remaining(),
        "paired_devices": devices,
        "connected_devices": [
            device for device in devices if device["connected"]
        ],
        "message": _last_message,
    }


def _pairing_worker(seconds):
    global _pairing_active
    global _pairing_ends_at
    global _pairing_process
    global _last_message

    process = None

    try:
        process = subprocess.Popen(
            ["/usr/bin/bluetoothctl"],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )

        _pairing_process = process

        commands = [
            "power on",
            "pairable on",
            "discoverable on",
        ]

        for command in commands:
            if process.stdin is None:
                raise RuntimeError("Bluetooth control input unavailable")

            process.stdin.write(command + "\n")
            process.stdin.flush()
            time.sleep(0.4)

        _last_message = (
            f"Pairing mode enabled for {seconds} seconds"
        )

        end_time = time.time() + seconds

        while time.time() < end_time:
            if process.poll() is not None:
                raise RuntimeError("Bluetooth pairing agent stopped")

            time.sleep(1)

        if process.stdin is not None:
            process.stdin.write("discoverable off\n")
            process.stdin.write("pairable off\n")
            process.stdin.write("quit\n")
            process.stdin.flush()

        _last_message = "Pairing mode finished"

    except Exception as exc:
        _last_message = f"Pairing error: {exc}"

    finally:
        if process is not None and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=2)
            except Exception:
                process.kill()

        with _lock:
            _pairing_active = False
            _pairing_ends_at = 0.0
            _pairing_process = None


def start_pairing(seconds=PAIRING_SECONDS):
    global _pairing_active
    global _pairing_ends_at
    global _last_message

    with _lock:
        if _pairing_active:
            return {
                "ok": True,
                "message": "Pairing mode is already active",
                "seconds_remaining": pairing_seconds_remaining(),
            }

        _pairing_active = True
        _pairing_ends_at = time.time() + seconds
        _last_message = "Starting pairing mode"

        thread = threading.Thread(
            target=_pairing_worker,
            args=(seconds,),
            daemon=True,
        )
        thread.start()

    return {
        "ok": True,
        "message": f"Pairing mode enabled for {seconds} seconds",
        "seconds_remaining": seconds,
    }


def valid_address(address):
    return bool(
        re.fullmatch(
            r"[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}",
            str(address or ""),
        )
    )


def trust_device(address):
    global _last_message

    if not valid_address(address):
        return {
            "ok": False,
            "error": "Invalid Bluetooth address",
        }

    output, code = bluetoothctl(["trust", address.upper()])

    if code == 0 and "succeeded" in output.lower():
        _last_message = f"Trusted device {address.upper()}"
        return {
            "ok": True,
            "message": _last_message,
        }

    return {
        "ok": False,
        "error": output or "Unable to trust device",
    }


def forget_device(address):
    global _last_message

    if not valid_address(address):
        return {
            "ok": False,
            "error": "Invalid Bluetooth address",
        }

    output, code = bluetoothctl(["remove", address.upper()])

    if code == 0 and (
        "removed" in output.lower()
        or "successful" in output.lower()
        or "succeeded" in output.lower()
    ):
        _last_message = f"Forgot device {address.upper()}"
        return {
            "ok": True,
            "message": _last_message,
        }

    return {
        "ok": False,
        "error": output or "Unable to forget device",
    }


def _restart_bluetooth_worker():
    global _last_message

    try:
        _last_message = "Restarting Bluetooth"

        run_command(
            [
                "/usr/bin/systemctl",
                "restart",
                "bluetooth.service",
            ],
            timeout=15,
        )

        time.sleep(2)

        run_command(
            [
                "/usr/bin/systemctl",
                "restart",
                "sutton-scoreboard.service",
            ],
            timeout=15,
        )

        time.sleep(2)

        run_command(
            [
                "/usr/bin/systemctl",
                "restart",
                "sutton-scoreboard-advert.service",
            ],
            timeout=15,
        )

        _last_message = "Bluetooth services restarted"

    except Exception as exc:
        _last_message = f"Bluetooth restart error: {exc}"


def restart_bluetooth():
    thread = threading.Thread(
        target=_restart_bluetooth_worker,
        daemon=True,
    )
    thread.start()

    return {
        "ok": True,
        "message": "Bluetooth restart started",
    }


def restart_advertising():
    global _last_message

    output, code = run_command(
        [
            "/usr/bin/systemctl",
            "restart",
            "sutton-scoreboard-advert.service",
        ],
        timeout=15,
    )

    if code == 0:
        _last_message = "Bluetooth advertising restarted"
        return {
            "ok": True,
            "message": _last_message,
        }

    return {
        "ok": False,
        "error": output or "Unable to restart advertising",
    }


def handle_action(request):
    action = str(request.get("action", "")).strip()
    address = str(request.get("address", "")).strip()

    if action == "start_pairing":
        return start_pairing()

    if action == "trust_device":
        return trust_device(address)

    if action == "forget_device":
        return forget_device(address)

    if action == "restart_bluetooth":
        return restart_bluetooth()

    if action == "restart_advertising":
        return restart_advertising()

    if action == "status":
        return get_status()

    return {
        "ok": False,
        "error": "Unknown Bluetooth action",
    }
