#!/usr/bin/env python3

import json
import os
import subprocess
import time
from pathlib import Path


EVENT_FILE = Path("/var/lib/scoreos/events/events.jsonl")
MATCH_FILE = Path("/var/lib/scoreos/current-match.json")


def number(value):
    cleaned = str(value).replace("-", "").strip()

    try:
        return int(cleaned or "0")
    except ValueError:
        return 0


def batter_details(previous, current):
    previous_a = number(previous.get("BatAscore"))
    current_a = number(current.get("BatAscore"))

    previous_b = number(previous.get("BatBscore"))
    current_b = number(current.get("BatBscore"))

    delta_a = current_a - previous_a
    delta_b = current_b - previous_b

    if delta_a > 0:
        return {
            "name": current.get("Bat1Name", "Batter A"),
            "runs": current_a,
            "delta": delta_a,
        }

    if delta_b > 0:
        return {
            "name": current.get("Bat2Name", "Batter B"),
            "runs": current_b,
            "delta": delta_b,
        }

    return {
        "name": "Unknown batter",
        "runs": 0,
        "delta": 0,
    }


def active_session_id():
    if not MATCH_FILE.exists():
        return None

    try:
        session = json.loads(
            MATCH_FILE.read_text(
                encoding="utf-8"
            )
        )
    except (
        OSError,
        json.JSONDecodeError,
    ):
        return None

    session_id = str(
        session.get("session_id", "")
    ).strip()

    return session_id or None


def auto_start_match(previous, current):
    if MATCH_FILE.exists():
        return active_session_id()

    if not previous:
        return None

    previous_over = str(
        previous.get("CurrentOver", "-") or "-"
    ).strip()

    current_over = str(
        current.get("CurrentOver", "-") or "-"
    ).strip()

    previous_overs = str(
        previous.get("overs", "-") or "-"
    ).strip()

    current_overs = str(
        current.get("overs", "-") or "-"
    ).strip()

    delivery_changed = (
        current_over != previous_over
        or current_overs != previous_overs
    )

    if not delivery_changed:
        return None

    batting_team = str(
        current.get("BatTeamName", "")
    ).strip()

    fielding_team = str(
        current.get("FieldTeamName", "")
    ).strip()

    if (
        not batting_team
        or batting_team == "-"
        or not fielding_team
        or fielding_team == "-"
    ):
        print(
            "SCOREOS AUTO MATCH: "
            "waiting for team names",
            flush=True,
        )
        return None

    now = time.time()

    session_id = time.strftime(
        "match-%H-%M-%S"
    )

    session = {
        "session_id": session_id,
        "started": now,
        "started_iso": time.strftime(
            "%Y-%m-%dT%H:%M:%S"
        ),
        "home_team": batting_team,
        "away_team": fielding_team,
        "batting_team": batting_team,
        "fielding_team": fielding_team,
        "match_name": (
            batting_team
            + " v "
            + fielding_team
        ),
        "auto_started": True,
    }

    MATCH_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    MATCH_FILE.write_text(
        json.dumps(
            session,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    match_date = time.strftime(
        "%Y-%m-%d"
    )

    session_folder = (
        Path("/var/lib/scoreos/recordings")
        / match_date
        / session_id
    )

    session_folder.mkdir(
        parents=True,
        exist_ok=True,
    )

    try:
        os.chown(
            session_folder.parent,
            1000,
            1000,
        )
        os.chown(
            session_folder,
            1000,
            1000,
        )
    except OSError:
        pass

    (
        session_folder / "match.json"
    ).write_text(
        json.dumps(
            session,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            "/usr/bin/systemctl",
            "start",
            "scoreos-camera-recorder.service",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        MATCH_FILE.unlink(
            missing_ok=True
        )

        print(
            "SCOREOS AUTO MATCH: "
            "camera recorder failed to start:",
            result.stderr.strip(),
            flush=True,
        )

        return None

    print(
        "SCOREOS AUTO MATCH STARTED:",
        session["match_name"],
        session_id,
        flush=True,
    )

    return session_id


def detect_events(previous, current):
    if not previous:
        return []

    events = []

    previous_total = number(previous.get("total"))
    current_total = number(current.get("total"))

    previous_wickets = number(previous.get("wickets"))
    current_wickets = number(current.get("wickets"))

    total_delta = current_total - previous_total
    wicket_delta = current_wickets - previous_wickets

    batter = batter_details(previous, current)

    base_event = {
        "timestamp": time.time(),
        "session_id": active_session_id(),
        "score": current.get("total", "--0"),
        "wickets": current.get("wickets", "0"),
        "overs": current.get("overs", "-0"),
        "batting_team": current.get("BatTeamName", "-"),
        "fielding_team": current.get("FieldTeamName", "-"),
        "batter": batter["name"],
        "current_over": current.get("CurrentOver", "-"),
    }

    if wicket_delta > 0:
        events.append(
            {
                **base_event,
                "type": "WICKET",
                "wickets_added": wicket_delta,
                "last_wicket": current.get(
                    "LastWicket",
                    "---",
                ),
            }
        )

    if (
        total_delta == 4
        and batter["delta"] == 4
        and wicket_delta == 0
    ):
        events.append(
            {
                **base_event,
                "type": "FOUR",
                "runs_added": 4,
                "batter_score": batter["runs"],
            }
        )

    if (
        total_delta == 6
        and batter["delta"] == 6
        and wicket_delta == 0
    ):
        events.append(
            {
                **base_event,
                "type": "SIX",
                "runs_added": 6,
                "batter_score": batter["runs"],
            }
        )

    if batter["delta"] > 0:
        previous_batter_runs = (
            batter["runs"] - batter["delta"]
        )

        milestones = (
            (50, "FIFTY"),
            (100, "HUNDRED"),
        )

        for milestone, event_type in milestones:
            if (
                previous_batter_runs < milestone
                <= batter["runs"]
            ):
                events.append(
                    {
                        **base_event,
                        "type": event_type,
                        "milestone": milestone,
                        "batter_score": batter["runs"],
                    }
                )

    return events


def write_events(events):
    if not events:
        return

    EVENT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with EVENT_FILE.open(
        "a",
        encoding="utf-8",
    ) as handle:
        for event in events:
            handle.write(
                json.dumps(event) + "\n"
            )

            print(
                "SCOREOS EVENT:",
                event["type"],
                event.get("batter", ""),
                event.get("score", ""),
                "/",
                event.get("wickets", ""),
            )
