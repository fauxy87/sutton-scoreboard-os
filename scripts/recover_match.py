#!/usr/bin/env python3

import json
import subprocess
import sys
import time
from pathlib import Path


CURRENT_MATCH = Path(
    "/var/lib/scoreos/current-match.json"
)

PROCESSING = Path(
    "/var/lib/scoreos/match-processing.json"
)

COMPLETE = Path(
    "/var/lib/scoreos/last-match-complete.json"
)

RECORDINGS = Path(
    "/var/lib/scoreos/recordings"
)

HIGHLIGHTS = Path(
    "/var/lib/scoreos/highlights"
)

INSTALL_DIR = Path(__file__).resolve().parent.parent


def log(message):
    print(
        time.strftime("%Y-%m-%d %H:%M:%S"),
        message,
        flush=True,
    )


def write_processing(session, stage):
    data = {
        "started_at": time.time(),
        "stage": stage,
        "session_id": session["session_id"],
        "match_name": session.get(
            "match_name",
            "Recovered Match",
        ),
        "recovery": True,
    }

    PROCESSING.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary = PROCESSING.with_suffix(
        ".tmp"
    )

    temporary.write_text(
        json.dumps(data, indent=2),
        encoding="utf-8",
    )

    temporary.replace(PROCESSING)


def find_match_dir(session_id):
    matches = [
        path
        for path in RECORDINGS.rglob(session_id)
        if path.is_dir()
        and path.name == session_id
    ]

    if not matches:
        return None

    return matches[0]


def run_script(script, arguments, timeout):
    command = [
        sys.executable,
        str(INSTALL_DIR / "scripts" / script),
        *arguments,
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )

    if result.stdout.strip():
        log(result.stdout.strip())

    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.strip()
            or f"{script} failed"
        )


def main():
    if not CURRENT_MATCH.exists():
        log(
            "No interrupted match found; "
            "nothing to recover"
        )
        return 0

    try:
        session = json.loads(
            CURRENT_MATCH.read_text(
                encoding="utf-8"
            )
        )
    except (
        OSError,
        json.JSONDecodeError,
    ) as exc:
        log(
            "Unable to read interrupted match: "
            + str(exc)
        )
        return 1

    session_id = str(
        session.get("session_id", "")
    ).strip()

    if not session_id.startswith("match-"):
        log(
            "Interrupted match has invalid "
            "session ID; leaving files untouched"
        )
        return 1

    match_dir = find_match_dir(
        session_id
    )

    if match_dir is None:
        log(
            "Interrupted match directory was not "
            "found; leaving state untouched"
        )
        return 1

    date = match_dir.parent.name

    full_dir = match_dir / "full"

    segments = list(
        full_dir.glob("*.ts")
    )

    full_match = (
        full_dir / "full-match.mp4"
    )

    full_match_ready = bool(
        full_match.exists()
        and full_match.stat().st_size > 0
    )

    if (
        not segments
        and not full_match_ready
    ):
        log(
            "No full-match recording or source "
            "segments found; leaving match untouched"
        )
        return 1

    log(
        "Interrupted match detected: "
        + session.get(
            "match_name",
            session_id,
        )
    )

    if segments:
        log(
            f"Found {len(segments)} "
            "recording segments"
        )
    else:
        log(
            "Recovered full match already exists"
        )

    try:
        write_processing(
            session,
            "recovering-full-match",
        )

        if not full_match_ready:
            log(
                "Building recovered full match"
            )

            # Recovery must first create the clean master.
            # The browser/score-overlay copy is deliberately
            # deferred, matching the normal match-stop flow.
            # A browser conversion failure must not cause an
            # otherwise healthy interrupted match to fail
            # recovery.
            run_script(
                "build_full_match.py",
                [
                    "--date",
                    date,
                    "--session",
                    session_id,
                    "--master-only",
                ],
                timeout=7200,
            )

        else:
            log(
                "Full match already exists"
            )

        write_processing(
            session,
            "recovering-highlights",
        )

        highlight_dir = (
            HIGHLIGHTS
            / date
            / session_id
        )

        individual = []

        if highlight_dir.exists():
            individual = [
                clip
                for clip in highlight_dir.glob(
                    "*.mp4"
                )
                if clip.name
                != "match-highlights.mp4"
            ]

        combined = (
            highlight_dir
            / "match-highlights.mp4"
        )

        build_combined_highlights = bool(
            session.get(
                "build_combined_highlights",
                False,
            )
        )

        if not build_combined_highlights:
            log(
                "Combined match highlights "
                "were disabled for this match"
            )

        elif individual:
            if (
                not combined.exists()
                or combined.stat().st_size <= 0
            ):
                log(
                    "Building recovered "
                    "match highlights"
                )

                run_script(
                    "build_match_highlights.py",
                    [
                        "--date",
                        date,
                        "--session",
                        session_id,
                    ],
                    timeout=1800,
                )

            else:
                log(
                    "Combined highlights "
                    "already exist"
                )

        else:
            log(
                "No individual highlights "
                "to combine"
            )

        write_processing(
            session,
            "recovery-complete",
        )

        full_match_ready = bool(
            full_match.exists()
            and full_match.stat().st_size > 0
        )

        match_highlights_ready = bool(
            combined.exists()
            and combined.stat().st_size > 0
        )

        # Recovery mirrors the normal match-stop flow:
        # the clean master is considered complete first,
        # while the scored browser copy is built separately.
        complete_status = {
            "completed_at": time.time(),
            "session_id": session_id,
            "match_name": session.get(
                "match_name"
            ),
            "full_match_ready": full_match_ready,
            "browser_video_processing": False,
            "browser_video_ready": False,
            "match_highlights_ready": (
                match_highlights_ready
            ),
            "build_error": None,
            "highlights_error": None,
            "recovery": True,
        }

        COMPLETE.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        COMPLETE.write_text(
            json.dumps(
                complete_status,
                indent=2,
            ) + "\n",
            encoding="utf-8",
        )

        browser_started = False

        if full_match_ready:
            browser_log = (
                full_dir
                / "browser-build.log"
            )

            try:
                log_handle = browser_log.open(
                    "a",
                    encoding="utf-8",
                )

                subprocess.Popen(
                    [
                        sys.executable,
                        str(
                            INSTALL_DIR
                            / "scripts"
                            / "build_full_match.py"
                        ),
                        "--date",
                        date,
                        "--session",
                        session_id,
                        "--browser-only",
                    ],
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )

                browser_started = True

            except OSError as exc:
                log(
                    "Unable to start recovered "
                    "browser build: "
                    + str(exc)
                )

        if browser_started:
            complete_status[
                "browser_video_processing"
            ] = True

            COMPLETE.write_text(
                json.dumps(
                    complete_status,
                    indent=2,
                ) + "\n",
                encoding="utf-8",
            )

            log(
                "Recovered browser playback "
                "build started"
            )

        CURRENT_MATCH.unlink(
            missing_ok=True
        )

        PROCESSING.unlink(
            missing_ok=True
        )

        log(
            "Interrupted match recovery complete"
        )

        return 0

    except (
        OSError,
        RuntimeError,
        subprocess.TimeoutExpired,
    ) as exc:
        log(
            "Match recovery failed: "
            + str(exc)
        )

        # Deliberately preserve current-match,
        # processing state and all source segments.
        # Nothing is deleted after a failed recovery.
        return 1


if __name__ == "__main__":
    sys.exit(main())

