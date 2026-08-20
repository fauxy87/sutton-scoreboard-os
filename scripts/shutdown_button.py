#!/usr/bin/env python3

import json
import os
import time
from urllib import request
from urllib.error import URLError

from gpiozero import Button


BUTTON_GPIO = 17
HOLD_SECONDS = 3

BASE_URL = "http://127.0.0.1:8080"

TEST_MODE = (
    os.environ.get(
        "SCOREOS_SHUTDOWN_BUTTON_TEST",
        "0",
    ) == "1"
)

shutdown_started = False


def log(message):
    print(
        time.strftime("%Y-%m-%d %H:%M:%S"),
        message,
        flush=True,
    )


def get_json(path, timeout=20):
    req = request.Request(
        BASE_URL + path,
        method="GET",
        headers={
            "Cache-Control": "no-store",
        },
    )

    with request.urlopen(
        req,
        timeout=timeout,
    ) as response:
        return json.loads(
            response.read().decode("utf-8")
        )


def post_json(path, payload, timeout=20):
    body = json.dumps(
        payload
    ).encode("utf-8")

    req = request.Request(
        BASE_URL + path,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
        },
    )

    with request.urlopen(
        req,
        timeout=timeout,
    ) as response:
        return json.loads(
            response.read().decode("utf-8")
        )


def safe_shutdown():
    global shutdown_started

    if shutdown_started:
        return

    shutdown_started = True

    log(
        "Shutdown button held for "
        f"{HOLD_SECONDS} seconds"
    )

    if TEST_MODE:
        log(
            "TEST MODE: button detected correctly; "
            "shutdown NOT requested"
        )
        shutdown_started = False
        return

    try:
        status = get_json(
            "/api/shutdown/status"
        )

        if not status.get("ok", False):
            raise RuntimeError(
                "Unable to read shutdown status"
            )

        if status.get("recording"):
            log(
                "Match recording active; "
                "stopping and saving match"
            )

            result = post_json(
                "/api/match/stop",
                {},
                timeout=7500,
            )

            if not result.get("ok", False):
                raise RuntimeError(
                    result.get("error")
                    or "Unable to save match"
                )

            processing_errors = [
                error
                for error in (
                    result.get("build_error"),
                    result.get(
                        "highlights_error"
                    ),
                )
                if error
            ]

            if processing_errors:
                raise RuntimeError(
                    "Match processing failed: "
                    + " | ".join(
                        processing_errors
                    )
                )

            if (
                result.get("session")
                and not result.get("full_match")
            ):
                raise RuntimeError(
                    "Full match was not created; "
                    "shutdown cancelled"
                )

            log(
                "Match saved successfully"
            )

        status = get_json(
            "/api/shutdown/status?_="
            + str(int(time.time()))
        )

        if not status.get("safe", False):
            reasons = status.get(
                "reasons",
                [],
            )

            raise RuntimeError(
                "Shutdown not safe: "
                + (
                    " | ".join(reasons)
                    or "unknown reason"
                )
            )

        log(
            "SCOREOS safe to shut down"
        )

        result = post_json(
            "/api/admin",
            {
                "action": "shutdown",
            },
        )

        if not result.get("ok", False):
            raise RuntimeError(
                result.get("message")
                or result.get("error")
                or "Shutdown refused"
            )

        log(
            "Shutdown command accepted"
        )

    except (
        URLError,
        TimeoutError,
        RuntimeError,
        json.JSONDecodeError,
    ) as exc:
        log(
            "SAFE SHUTDOWN CANCELLED: "
            + str(exc)
        )

        shutdown_started = False


def main():
    log(
        "SCOREOS physical shutdown button ready "
        f"on GPIO{BUTTON_GPIO}"
    )

    if TEST_MODE:
        log(
            f"TEST MODE: hold button for "
            f"{HOLD_SECONDS} seconds; "
            "Pi will NOT shut down"
        )
    else:
        log(
            f"Hold button for {HOLD_SECONDS} seconds "
            "to save and shut down"
        )

    button = Button(
        BUTTON_GPIO,
        pull_up=True,
        bounce_time=0.08,
        hold_time=HOLD_SECONDS,
        hold_repeat=False,
    )

    button.when_held = safe_shutdown

    while True:
        time.sleep(60)


if __name__ == "__main__":
    main()
