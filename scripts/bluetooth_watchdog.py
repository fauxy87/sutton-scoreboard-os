#!/usr/bin/env python3

import re
import subprocess
import time
from datetime import datetime
from pathlib import Path


PREFERRED_MAC = "18:69:45:F3:58:B9"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ADAPTER_SCRIPT = str(
    PROJECT_ROOT
    / "scripts"
    / "run-btmgmt-on-scoreos-adapter.sh"
)

CHECK_SECONDS = 15
FAILURES_BEFORE_RECOVERY = 3
RECOVERY_COOLDOWN = 60

LOG_FILE = Path(
    "/var/lib/scoreos/logs/bluetooth-watchdog.log"
)


def log(message):
    timestamp = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    line = f"{timestamp} {message}"
    print(line, flush=True)

    try:
        LOG_FILE.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with LOG_FILE.open(
            "a",
            encoding="utf-8",
        ) as handle:
            handle.write(line + "\n")

    except OSError:
        pass


def run(command, timeout=20):
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

    except Exception as exc:
        return str(exc), 1


def adapter_present():
    root = Path("/sys/class/bluetooth")

    return root.exists() and any(root.glob("hci*"))


def service_active(name):
    output, code = run(
        [
            "/usr/bin/systemctl",
            "is-active",
            name,
        ],
        timeout=5,
    )

    return (
        code == 0
        and output.strip() == "active"
    )


def advertising_active():
    output, code = run(
        [ADAPTER_SCRIPT, "advinfo"],
        timeout=20,
    )

    if code != 0:
        return False

    match = re.search(
        r"Instances list with\s+(\d+)\s+item",
        output,
        re.IGNORECASE,
    )

    if not match:
        return False

    return int(match.group(1)) > 0


def recover_advertising():
    log(
        "Advertising missing - restarting "
        "advertising service"
    )

    output, code = run(
        [
            "/usr/bin/systemctl",
            "restart",
            "sutton-scoreboard-advert.service",
        ],
        timeout=45,
    )

    if code != 0:
        log(
            "Advertising restart failed: "
            + (output or "unknown error")
        )
        return False

    time.sleep(5)

    if advertising_active():
        log("Advertising recovered successfully")
        return True

    log(
        "Advertising service restarted but "
        "advertising is still missing"
    )

    return False


def main():
    failures = 0
    last_recovery = 0.0
    adapter_was_present = None

    log("Bluetooth watchdog started")

    while True:
        adapter_present = (
            adapter_present()
        )

        if not adapter_present:
            failures = 0

            if adapter_was_present is not False:
                log(
                    "SCOREOS Bluetooth adapter is not connected"
                )

            adapter_was_present = False
            time.sleep(CHECK_SECONDS)
            continue

        if adapter_was_present is not True:
            log(
                "SCOREOS Bluetooth adapter detected"
            )

        adapter_was_present = True

        if not service_active("bluetooth.service"):
            failures = 0
            time.sleep(CHECK_SECONDS)
            continue

        if advertising_active():
            failures = 0
            time.sleep(CHECK_SECONDS)
            continue

        failures += 1

        log(
            f"Advertising health check failed "
            f"({failures}/{FAILURES_BEFORE_RECOVERY})"
        )

        if failures >= FAILURES_BEFORE_RECOVERY:
            now = time.time()

            if (
                now - last_recovery
                >= RECOVERY_COOLDOWN
            ):
                recover_advertising()
                last_recovery = now

            failures = 0

        time.sleep(CHECK_SECONDS)


if __name__ == "__main__":
    main()
