#!/usr/bin/env python3

import signal
import subprocess
import time

import dbus

BLUEZ = "org.bluez"
OBJECT_MANAGER = "org.freedesktop.DBus.ObjectManager"

ADVERTISER = (
    "/home/pi/sutton-scoreboard-os/"
    "scripts/legacy-advertisement.sh"
)

running = True


def stop(*_args):
    global running
    running = False


def any_device_connected():
    try:
        bus = dbus.SystemBus()
        manager = dbus.Interface(
            bus.get_object(BLUEZ, "/"),
            OBJECT_MANAGER,
        )

        objects = manager.GetManagedObjects()

        for interfaces in objects.values():
            device = interfaces.get("org.bluez.Device1")

            if device and bool(device.get("Connected", False)):
                return True

    except Exception as error:
        print(
            f"Unable to read Bluetooth connection state: {error}",
            flush=True,
        )

    return False


def start_advertising():
    print("Enabling SCOREOS legacy advertising", flush=True)

    try:
        result = subprocess.run(
            [ADVERTISER, "start"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=10,
            check=False,
        )

        if result.stdout:
            print(result.stdout.strip(), flush=True)

        print(
            f"Advertiser finished with status {result.returncode}",
            flush=True,
        )

    except Exception as error:
        print(f"Advertiser failed: {error}", flush=True)


def main():
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    previous_connected = any_device_connected()
    last_advertising_attempt = 0.0

    if not previous_connected:
        start_advertising()
        last_advertising_attempt = time.monotonic()

    while running:
        connected = any_device_connected()

        if connected and not previous_connected:
            print("Play-Cricket connected", flush=True)

        elif previous_connected and not connected:
            print(
                "Play-Cricket disconnected - waiting for adapter",
                flush=True,
            )
            time.sleep(5)
            start_advertising()
            last_advertising_attempt = time.monotonic()

        elif (
            not connected
            and time.monotonic() - last_advertising_attempt >= 20
        ):
            print(
                "Still disconnected - refreshing advertising",
                flush=True,
            )
            start_advertising()
            last_advertising_attempt = time.monotonic()

        previous_connected = connected
        time.sleep(2)

    subprocess.run(
        [ADVERTISER, "stop"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=5,
        check=False,
    )


if __name__ == "__main__":
    main()
