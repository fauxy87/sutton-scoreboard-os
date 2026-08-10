#!/usr/bin/env python3

import json
import os
import time
from pathlib import Path


EVENT_FILE = Path("/var/lib/scoreos/events/events.jsonl")


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
