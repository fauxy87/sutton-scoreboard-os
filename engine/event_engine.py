#!/usr/bin/env python3

import json
import os
import shutil
import subprocess
import time
from pathlib import Path


EVENT_FILE = Path("/var/lib/scoreos/events/events.jsonl")
MATCH_FILE = Path("/var/lib/scoreos/current-match.json")
RECORDING_ROOT = Path("/var/lib/scoreos/recordings")


def set_recording_owner(path):
    """Match a new path to the installer's recording owner."""
    try:
        owner = RECORDING_ROOT.stat()
        os.chown(path, owner.st_uid, owner.st_gid)
    except OSError:
        pass


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


def write_score_history(snapshot):
    """Save timestamped score states for full-match graphics."""
    session = load_active_session()

    if not session:
        return

    session_id = str(
        session.get("session_id", "")
    ).strip()

    started_iso = str(
        session.get("started_iso", "")
    ).strip()

    if (
        not session_id
        or session_id != Path(session_id).name
        or not session_id.startswith("match-")
    ):
        return

    match_date = (
        started_iso[:10]
        if len(started_iso) >= 10
        else time.strftime("%Y-%m-%d")
    )

    session_folder = (
        Path("/var/lib/scoreos/recordings")
        / match_date
        / session_id
    )

    try:
        session_folder.mkdir(
            parents=True,
            exist_ok=True,
        )

        history_file = (
            session_folder
            / "score-history.jsonl"
        )

        entry = {
            "timestamp": time.time(),
            **snapshot,
        }

        with history_file.open(
            "a",
            encoding="utf-8",
        ) as handle:
            handle.write(
                json.dumps(entry)
                + "\n"
            )

    except OSError as exc:
        print(
            "SCOREOS SCORE HISTORY ERROR:",
            exc,
            flush=True,
        )


def preserve_preroll(full_folder):
    buffer_root = Path(
        "/var/lib/scoreos/camera-buffer"
    )

    subprocess.run(
        [
            "/usr/bin/systemctl",
            "stop",
            "scoreos-camera-buffer.service",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    full_folder.mkdir(
        parents=True,
        exist_ok=True,
    )

    set_recording_owner(full_folder)

    copied = 0
    cutoff = time.time() - 50

    if buffer_root.exists():
        for source in sorted(
            buffer_root.glob("*.ts")
        ):
            try:
                stat = source.stat()
            except OSError:
                continue

            if (
                stat.st_size <= 0
                or stat.st_mtime < cutoff
            ):
                continue

            destination = (
                full_folder / source.name
            )

            try:
                shutil.copy2(
                    source,
                    destination,
                )
                copied += 1
            except OSError as exc:
                print(
                    "SCOREOS PRE-ROLL COPY ERROR:",
                    exc,
                    flush=True,
                )

    print(
        "SCOREOS PRE-ROLL:",
        copied,
        "segments preserved",
        flush=True,
    )

    return copied


def save_active_session(session):
    MATCH_FILE.write_text(
        json.dumps(
            session,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    session_id = str(
        session.get("session_id", "")
    ).strip()

    started_iso = str(
        session.get("started_iso", "")
    )

    match_date = (
        started_iso[:10]
        if len(started_iso) >= 10
        else time.strftime("%Y-%m-%d")
    )

    if session_id:
        metadata_path = (
            Path("/var/lib/scoreos/recordings")
            / match_date
            / session_id
            / "match.json"
        )

        try:
            metadata_path.write_text(
                json.dumps(
                    session,
                    indent=2,
                ) + "\n",
                encoding="utf-8",
            )
        except OSError:
            pass


def load_active_session():
    if not MATCH_FILE.exists():
        return None

    try:
        return json.loads(
            MATCH_FILE.read_text(
                encoding="utf-8"
            )
        )
    except (
        OSError,
        json.JSONDecodeError,
    ):
        return None


def teams_swapped(previous, current):
    if not previous:
        return False

    previous_batting = str(
        previous.get("BatTeamName", "")
    ).strip()

    previous_fielding = str(
        previous.get("FieldTeamName", "")
    ).strip()

    current_batting = str(
        current.get("BatTeamName", "")
    ).strip()

    current_fielding = str(
        current.get("FieldTeamName", "")
    ).strip()

    invalid = ("", "-")

    if (
        previous_batting in invalid
        or previous_fielding in invalid
        or current_batting in invalid
        or current_fielding in invalid
    ):
        return False

    return (
        previous_batting != current_batting
        and previous_batting == current_fielding
        and previous_fielding == current_batting
    )


def bowler_selected(current):
    """Return True once Play-Cricket has a real bowler."""
    bowler = str(
        current.get("Bowler1Name", "") or ""
    ).strip()

    return (
        bool(bowler)
        and bowler not in {
            "-",
            "---",
            "Bowler",
        }
    )


def start_recorder_for_innings(session, current):
    """
    Preserve the rolling pre-roll and start the match
    recorder when the first bowler is selected.
    """
    session_id = str(
        session.get("session_id", "")
    ).strip()

    if not session_id:
        return False

    started_iso = str(
        session.get("started_iso", "")
    )

    match_date = (
        started_iso[:10]
        if len(started_iso) >= 10
        else time.strftime("%Y-%m-%d")
    )

    full_folder = (
        Path("/var/lib/scoreos/recordings")
        / match_date
        / session_id
        / "full"
    )

    bowler = str(
        current.get("Bowler1Name", "")
        or ""
    ).strip()

    print(
        "SCOREOS BOWLER SELECTED:",
        bowler,
        flush=True,
    )

    preserve_preroll(full_folder)

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

    time.sleep(2)

    recorder_active = (
        subprocess.run(
            [
                "/usr/bin/systemctl",
                "is-active",
                "--quiet",
                "scoreos-camera-recorder.service",
            ],
            capture_output=True,
            text=True,
            check=False,
        ).returncode == 0
    )

    if (
        result.returncode == 0
        and recorder_active
    ):
        session["waiting_for_bowler"] = False
        session["innings_break"] = False
        session["recording_started"] = time.time()
        session["recording_started_by"] = "bowler"
        session["starting_bowler"] = bowler

        save_active_session(session)

        print(
            "SCOREOS RECORDING STARTED:",
            f"innings {session.get('innings', 1)}",
            bowler,
            flush=True,
        )

        return True

    # If the camera/recorder cannot start, restore the
    # rolling buffer and leave waiting_for_bowler set.
    subprocess.run(
        [
            "/usr/bin/systemctl",
            "start",
            "scoreos-camera-buffer.service",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    print(
        "SCOREOS RECORDING START FAILED:",
        result.stderr.strip()
        or "recorder did not stay running",
        flush=True,
    )

    return False


def delivery_changed(previous, current):
    if not previous:
        return False

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

    return (
        current_over != previous_over
        or current_overs != previous_overs
    )


def handle_waiting_for_bowler(current):
    """
    Start recording when Play-Cricket supplies the first
    bowler for an innings.
    """
    session = load_active_session()

    if not session:
        return False

    if not session.get("waiting_for_bowler"):
        return False

    if not bowler_selected(current):
        return False

    return start_recorder_for_innings(
        session,
        current,
    )


def session_teams_swapped(session, current):
    """
    Detect an innings change against the active match
    session rather than the immediately previous packet.

    Play-Cricket sends BatTeamName and FieldTeamName as
    separate packets, so comparing adjacent snapshots can
    miss the swap while the state is temporarily half-updated.
    """
    session_batting = str(
        session.get("batting_team", "") or ""
    ).strip()

    session_fielding = str(
        session.get("fielding_team", "") or ""
    ).strip()

    current_batting = str(
        current.get("BatTeamName", "") or ""
    ).strip()

    current_fielding = str(
        current.get("FieldTeamName", "") or ""
    ).strip()

    invalid = {
        "",
        "-",
        "Team 1",
        "Team 2",
    }

    if (
        session_batting in invalid
        or session_fielding in invalid
        or current_batting in invalid
        or current_fielding in invalid
    ):
        return False

    return (
        current_batting == session_fielding
        and current_fielding == session_batting
    )


def handle_innings_break(previous, current):
    session = load_active_session()

    if not session:
        return False

    # A normal ScoreOS match has two innings.
    # Once innings 2 has started, a later Play-Cricket
    # team-state refresh must not create a false innings 3.
    current_innings = int(
        session.get("innings", 1)
    )

    if current_innings >= 2:
        return False

    if session_teams_swapped(
        session,
        current,
    ):
        innings = current_innings + 1

        subprocess.run(
            [
                "/usr/bin/systemctl",
                "stop",
                "scoreos-camera-recorder.service",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        subprocess.run(
            [
                "/usr/bin/systemctl",
                "start",
                "scoreos-camera-buffer.service",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        session["innings"] = innings
        session["innings_break"] = True
        session["waiting_for_bowler"] = True
        session["batting_team"] = str(
            current.get("BatTeamName", "")
        ).strip()
        session["fielding_team"] = str(
            current.get("FieldTeamName", "")
        ).strip()
        session["innings_break_started"] = time.time()

        save_active_session(session)

        print(
            "SCOREOS INNINGS BREAK:",
            f"innings {innings} waiting to start",
            flush=True,
        )

        return True

    return False


def detect_match_finished(previous, current):
    session = load_active_session()

    if not session:
        return False

    if session.get("match_finished"):
        return True

    innings = int(
        session.get("innings", 1)
    )

    if innings < 2:
        return False

    if session.get("innings_break"):
        return False

    target_text = str(
        current.get("target", "") or ""
    ).strip()

    runs_required_text = str(
        current.get("RunsRequired", "") or ""
    ).strip()

    # Do not treat blank/default "---" values as zero.
    if (
        not target_text
        or target_text in ("-", "---")
        or not runs_required_text
        or runs_required_text in ("-", "---")
    ):
        return False

    target = number(target_text)
    runs_required = number(
        runs_required_text
    )

    if target <= 0:
        return False

    if runs_required > 0:
        return False

    session["match_finished"] = True
    session["match_finished_at"] = time.time()
    session["match_finished_iso"] = time.strftime(
        "%Y-%m-%dT%H:%M:%S"
    )
    session["match_finished_reason"] = (
        "target_reached"
    )

    save_active_session(session)

    print(
        "SCOREOS MATCH FINISHED:",
        session.get("match_name", ""),
        "target reached",
        flush=True,
    )

    return True


def auto_start_match(previous, current):
    if MATCH_FILE.exists():
        existing_session = load_active_session()

        recorder_active = (
            subprocess.run(
                [
                    "/usr/bin/systemctl",
                    "is-active",
                    "--quiet",
                    "scoreos-camera-recorder.service",
                ],
                capture_output=True,
                text=True,
                check=False,
            ).returncode == 0
        )

        # The recorder is deliberately stopped while
        # waiting for the first bowler and during a genuine
        # innings break, so the session must remain active.
        innings_break = bool(
            existing_session
            and existing_session.get("innings_break")
        )

        waiting_for_bowler = bool(
            existing_session
            and existing_session.get(
                "waiting_for_bowler"
            )
        )

        if (
            recorder_active
            or innings_break
            or waiting_for_bowler
        ):
            # The match may have auto-started before
            # Play-Cricket supplied the team names.
            # Update the active session as soon as valid
            # names become available.
            batting_team = str(
                current.get("BatTeamName", "")
            ).strip()

            fielding_team = str(
                current.get("FieldTeamName", "")
            ).strip()

            valid_teams = (
                batting_team
                and batting_team != "-"
                and fielding_team
                and fielding_team != "-"
            )

            if (
                valid_teams
                and existing_session
            ):
                current_batting = str(
                    existing_session.get(
                        "batting_team",
                        "",
                    )
                ).strip()

                current_fielding = str(
                    existing_session.get(
                        "fielding_team",
                        "",
                    )
                ).strip()

                placeholder_values = {
                    "",
                    "-",
                    "Team 1",
                    "Team 2",
                }

                if (
                    current_batting in placeholder_values
                    or current_fielding in placeholder_values
                ):
                    existing_session[
                        "home_team"
                    ] = batting_team

                    existing_session[
                        "away_team"
                    ] = fielding_team

                    existing_session[
                        "batting_team"
                    ] = batting_team

                    existing_session[
                        "fielding_team"
                    ] = fielding_team

                    existing_session[
                        "match_name"
                    ] = (
                        batting_team
                        + " v "
                        + fielding_team
                    )

                    save_active_session(
                        existing_session
                    )

                    print(
                        "SCOREOS AUTO MATCH: "
                        "team names updated:",
                        existing_session[
                            "match_name"
                        ],
                        flush=True,
                    )

            return active_session_id()

        # A session file with no running recorder and no
        # innings break is stale, normally after a crash,
        # power loss or interrupted test. Preserve it for
        # diagnostics, then allow a fresh match to start.
        stale_name = (
            "stale-match-"
            + time.strftime("%Y%m%d-%H%M%S")
            + ".json"
        )

        stale_file = MATCH_FILE.with_name(
            stale_name
        )

        try:
            MATCH_FILE.replace(stale_file)

            print(
                "SCOREOS AUTO MATCH: "
                "archived stale session:",
                stale_file,
                flush=True,
            )

        except OSError as exc:
            print(
                "SCOREOS AUTO MATCH: "
                "unable to archive stale session:",
                exc,
                flush=True,
            )

            return None

    disk = shutil.disk_usage(
        "/var/lib/scoreos"
    )

    critical_bytes = (
        2 * 1024 * 1024 * 1024
    )

    if disk.free < critical_bytes:
        print(
            "SCOREOS AUTO MATCH BLOCKED: "
            "less than 2 GB free storage",
            flush=True,
        )
        return None

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

    teams_available = (
        batting_team
        and batting_team != "-"
        and fielding_team
        and fielding_team != "-"
    )

    if not teams_available:
        batting_team = "Team 1"
        fielding_team = "Team 2"

        print(
            "SCOREOS AUTO MATCH: "
            "starting before team names are available",
            flush=True,
        )

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
        "innings": 1,
        "innings_break": False,
        "waiting_for_bowler": True,
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

    set_recording_owner(session_folder.parent)
    set_recording_owner(session_folder)

    (
        session_folder / "match.json"
    ).write_text(
        json.dumps(
            session,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    # Keep the rolling camera buffer active until
    # Play-Cricket supplies a real first bowler.
    subprocess.run(
        [
            "/usr/bin/systemctl",
            "start",
            "scoreos-camera-buffer.service",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    print(
        "SCOREOS AUTO MATCH CREATED:",
        session["match_name"],
        session_id,
        "- waiting for bowler",
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
