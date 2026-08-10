#!/usr/bin/env python3

import json
import time
from pathlib import Path

import build_highlights


EVENT_FILE = Path(
    "/var/lib/scoreos/events/events.jsonl"
)

STATE_FILE = Path(
    "/var/lib/scoreos/highlights/.worker-state.json"
)

AFTER_DELAYS = {
    "FOUR": 18,
    "SIX": 20,
    "WICKET": 33,
    "FIFTY": 27,
    "HUNDRED": 33,
}


def load_state():
    if not STATE_FILE.exists():
        return {"processed": 0}

    try:
        return json.loads(
            STATE_FILE.read_text(
                encoding="utf-8"
            )
        )
    except Exception:
        return {"processed": 0}


def save_state(state):
    STATE_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    STATE_FILE.write_text(
        json.dumps(
            state,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )


def read_events():
    if not EVENT_FILE.exists():
        return []

    events = []

    with EVENT_FILE.open(
        "r",
        encoding="utf-8",
    ) as handle:
        for line in handle:
            line = line.strip()

            if not line:
                continue

            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            if event.get("type") in AFTER_DELAYS:
                events.append(event)

    return events


def main():
    state = load_state()

    while True:
        events = read_events()

        processed = int(
            state.get("processed", 0)
        )

        if processed >= len(events):
            time.sleep(2)
            continue

        event = events[processed]

        try:
            event_time = float(
                event["timestamp"]
            )
        except (
            KeyError,
            TypeError,
            ValueError,
        ):
            state["processed"] = processed + 1
            save_state(state)
            continue

        event_type = event.get("type")

        ready_time = (
            event_time +
            AFTER_DELAYS[event_type]
        )

        now = time.time()

        if now < ready_time:
            time.sleep(
                min(
                    2,
                    ready_time - now,
                )
            )
            continue

        result = build_highlights.create_clip(
            event,
            overwrite=False,
        )

        if result.get("ok"):
            state["processed"] = processed + 1
            state["retry_count"] = 0
            save_state(state)

        else:
            retry_count = int(
                state.get("retry_count", 0)
            ) + 1

            state["retry_count"] = retry_count
            save_state(state)

            if retry_count >= 5:
                print(
                    "Highlight unavailable after "
                    "5 attempts; skipping event:",
                    event.get("type"),
                    event.get("timestamp"),
                    flush=True,
                )

                state["processed"] = processed + 1
                state["retry_count"] = 0
                save_state(state)

            else:
                print(
                    f"Highlight failed; retry "
                    f"{retry_count}/5:",
                    result.get("error"),
                    flush=True,
                )

                time.sleep(5)


if __name__ == "__main__":
    main()
