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


def is_sutton_team(name):
    return "sutton" in str(
        name or ""
    ).strip().lower()


def session_teams(event):
    batting_team = str(
        event.get("batting_team")
        or ""
    ).strip()

    fielding_team = str(
        event.get("fielding_team")
        or ""
    ).strip()

    invalid = {
        "",
        "-",
        "Team 1",
        "Team 2",
    }

    if (
        batting_team not in invalid
        and fielding_team not in invalid
    ):
        return batting_team, fielding_team

    session_id = str(
        event.get("session_id")
        or ""
    ).strip()

    if (
        not session_id
        or session_id != Path(session_id).name
    ):
        return batting_team, fielding_team

    matches = sorted(
        Path(
            "/var/lib/scoreos/recordings"
        ).glob(
            f"*/{session_id}/match.json"
        )
    )

    for metadata_path in matches:
        try:
            metadata = json.loads(
                metadata_path.read_text(
                    encoding="utf-8"
                )
            )
        except (
            OSError,
            json.JSONDecodeError,
        ):
            continue

        saved_batting = str(
            metadata.get("batting_team")
            or ""
        ).strip()

        saved_fielding = str(
            metadata.get("fielding_team")
            or ""
        ).strip()

        if saved_batting:
            batting_team = saved_batting

        if saved_fielding:
            fielding_team = saved_fielding

        break

    return batting_team, fielding_team


def should_build_highlight(event):
    event_type = str(
        event.get("type")
        or ""
    ).strip().upper()

    batting_team, fielding_team = (
        session_teams(event)
    )

    sutton_batting = is_sutton_team(
        batting_team
    )

    sutton_fielding = is_sutton_team(
        fielding_team
    )

    # When Sutton bat, keep every Sutton batting
    # highlight including Sutton wickets.
    if sutton_batting:
        return event_type in {
            "FOUR",
            "SIX",
            "WICKET",
            "FIFTY",
            "HUNDRED",
        }

    # When the opposition bat, only keep wickets
    # taken by Sutton.
    if sutton_fielding:
        return event_type == "WICKET"

    invalid = {
        "",
        "-",
        "Team 1",
        "Team 2",
    }

    # A match can start before Play-Cricket has supplied
    # the team names. Do not permanently discard an event
    # while the team identity is still unknown.
    if (
        batting_team in invalid
        or fielding_team in invalid
    ):
        return None

    # Teams are known and Sutton is not involved.
    return False


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

        highlight_decision = (
            should_build_highlight(event)
        )

        if highlight_decision is None:
            session_id = str(
                event.get("session_id")
                or ""
            ).strip()

            # Old diagnostics/test events can exist without
            # a real match session. They can never acquire
            # valid team metadata, so do not let one block
            # the highlight worker forever.
            if (
                not session_id
                or session_id != Path(session_id).name
            ):
                print(
                    "Highlight skipped invalid event:",
                    event_type,
                    event.get("session_id"),
                    flush=True,
                )

                state["processed"] = processed + 1
                state["retry_count"] = 0
                save_state(state)
                continue

            print(
                "Highlight waiting for team names:",
                event_type,
                session_id,
                flush=True,
            )

            time.sleep(2)
            continue

        if highlight_decision is False:
            print(
                "Highlight filtered:",
                event_type,
                event.get("batting_team"),
                "v",
                event.get("fielding_team"),
                flush=True,
            )

            state["processed"] = processed + 1
            state["retry_count"] = 0
            save_state(state)
            continue

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
