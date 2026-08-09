#!/usr/bin/env python3

import argparse
import json
import subprocess
import tempfile
import time

from datetime import datetime
from pathlib import Path


EVENT_FILE = Path(
    "/var/lib/scoreos/events/events.jsonl"
)

RECORDING_ROOT = Path(
    "/var/lib/scoreos/recordings"
)

HIGHLIGHT_ROOT = Path(
    "/var/lib/scoreos/highlights"
)

CLIP_LENGTHS = {
    "FOUR": {
        "before": 8,
        "after": 10,
    },
    "SIX": {
        "before": 10,
        "after": 12,
    },
    "WICKET": {
        "before": 12,
        "after": 18,
    },
}


def log(message):
    timestamp = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    print(
        f"{timestamp} {message}",
        flush=True,
    )


def read_events():
    if not EVENT_FILE.exists():
        return []

    events = []

    with EVENT_FILE.open(
        "r",
        encoding="utf-8",
    ) as handle:
        for line_number, line in enumerate(
            handle,
            start=1,
        ):
            line = line.strip()

            if not line:
                continue

            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                log(
                    f"Ignoring invalid event on line "
                    f"{line_number}: {exc}"
                )
                continue

            if event.get("type") not in CLIP_LENGTHS:
                continue

            try:
                event["timestamp"] = float(
                    event["timestamp"]
                )
            except (KeyError, TypeError, ValueError):
                log(
                    f"Ignoring event without a valid "
                    f"timestamp on line {line_number}"
                )
                continue

            events.append(event)

    return events


def segment_start_time(path):
    try:
        parsed = datetime.strptime(
            path.stem,
            "%Y-%m-%d_%H-%M-%S",
        )
    except ValueError:
        return None

    return time.mktime(parsed.timetuple())


def probe_duration(path):
    command = [
        "/usr/bin/ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:"
        "nokey=1",
        str(path),
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )

    if result.returncode != 0:
        return None

    try:
        duration = float(result.stdout.strip())
    except ValueError:
        return None

    if duration <= 0:
        return None

    return duration


def find_recording_segments(
    clip_start,
    clip_end,
):
    day_folders = {
        datetime.fromtimestamp(
            clip_start
        ).strftime("%Y-%m-%d"),
        datetime.fromtimestamp(
            clip_end
        ).strftime("%Y-%m-%d"),
    }

    candidates = []

    for day_folder_name in day_folders:
        day_folder = (
            RECORDING_ROOT /
            day_folder_name
        )

        if not day_folder.exists():
            continue

        candidates.extend(
            day_folder.glob("*.mp4")
        )

    segments = []

    for path in sorted(candidates):
        start = segment_start_time(path)

        if start is None:
            continue

        duration = probe_duration(path)

        if duration is None:
            continue

        end = start + duration

        if end >= clip_start and start <= clip_end:
            segments.append(
                {
                    "path": path,
                    "start": start,
                    "end": end,
                    "duration": duration,
                }
            )

    return sorted(
        segments,
        key=lambda item: item["start"],
    )


def safe_text(value):
    text = str(value or "").strip()

    if not text:
        return "unknown"

    cleaned = []

    for character in text:
        if character.isalnum():
            cleaned.append(character)
        elif character in (" ", "-", "_"):
            cleaned.append("-")

    result = "".join(cleaned)

    while "--" in result:
        result = result.replace("--", "-")

    return result.strip("-").lower() or "unknown"


def output_path(event):
    timestamp = datetime.fromtimestamp(
        event["timestamp"]
    )

    event_type = safe_text(
        event.get("type")
    )

    batter = safe_text(
        event.get("batter")
    )

    score = safe_text(
        event.get("score")
    )

    filename = (
        f"{timestamp:%Y-%m-%d_%H-%M-%S}"
        f"_{event_type}"
        f"_{batter}"
        f"_{score}.mp4"
    )

    day_folder = (
        HIGHLIGHT_ROOT /
        timestamp.strftime("%Y-%m-%d")
    )

    day_folder.mkdir(
        parents=True,
        exist_ok=True,
    )

    return day_folder / filename


def escape_concat_path(path):
    return str(path).replace(
        "'",
        "'\\''",
    )


def create_clip(event, overwrite=False):
    event_type = event["type"]
    timing = CLIP_LENGTHS[event_type]

    clip_start = (
        event["timestamp"] -
        timing["before"]
    )

    clip_end = (
        event["timestamp"] +
        timing["after"]
    )

    clip_duration = clip_end - clip_start

    segments = find_recording_segments(
        clip_start,
        clip_end,
    )

    if not segments:
        log(
            f"No recording found for "
            f"{event_type} at "
            f"{datetime.fromtimestamp(event['timestamp'])}"
        )
        return {
            "ok": False,
            "event": event,
            "error": "No matching recording found",
        }

    first_start = segments[0]["start"]

    seek_offset = max(
        0,
        clip_start - first_start,
    )

    destination = output_path(event)

    if destination.exists() and not overwrite:
        log(
            f"Clip already exists: "
            f"{destination}"
        )

        return {
            "ok": True,
            "event": event,
            "output": str(destination),
            "skipped": True,
        }

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".txt",
        delete=False,
    ) as concat_file:
        concat_path = Path(concat_file.name)

        for segment in segments:
            concat_file.write(
                "file '"
                + escape_concat_path(
                    segment["path"]
                )
                + "'\n"
            )

    command = [
        "/usr/bin/ffmpeg",
        "-hide_banner",
        "-loglevel",
        "warning",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_path),
        "-ss",
        f"{seek_offset:.3f}",
        "-t",
        f"{clip_duration:.3f}",
        "-map",
        "0:v:0",
        "-c",
        "copy",
        "-movflags",
        "+faststart",
        "-y",
        str(destination),
    ]

    log(
        f"Creating {event_type} clip: "
        f"{destination.name}"
    )

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
    finally:
        concat_path.unlink(
            missing_ok=True
        )

    if result.returncode != 0:
        destination.unlink(
            missing_ok=True
        )

        error = (
            result.stderr.strip()
            or "FFmpeg failed"
        )

        log(
            f"Unable to create clip: "
            f"{error}"
        )

        return {
            "ok": False,
            "event": event,
            "error": error,
        }

    log(
        f"Highlight ready: "
        f"{destination}"
    )

    return {
        "ok": True,
        "event": event,
        "output": str(destination),
        "skipped": False,
    }


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Create SCOREOS highlight clips "
            "from recorded match events."
        )
    )

    parser.add_argument(
        "--latest",
        action="store_true",
        help="Build only the latest event",
    )

    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace clips that already exist",
    )

    args = parser.parse_args()

    events = read_events()

    if not events:
        log(
            f"No supported events found in "
            f"{EVENT_FILE}"
        )
        return 1

    if args.latest:
        events = [events[-1]]

    HIGHLIGHT_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    successful = 0
    failed = 0

    for event in events:
        result = create_clip(
            event,
            overwrite=args.overwrite,
        )

        if result["ok"]:
            successful += 1
        else:
            failed += 1

    log(
        f"Highlight build complete: "
        f"{successful} successful, "
        f"{failed} failed"
    )

    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
