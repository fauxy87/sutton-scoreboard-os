#!/usr/bin/env python3

import json
from datetime import datetime
from pathlib import Path


EVENT_FILE = Path("/var/lib/scoreos/events/events.jsonl")
RECORDING_ROOT = Path("/var/lib/scoreos/recordings")
HIGHLIGHT_ROOT = Path("/var/lib/scoreos/highlights")
EXPORT_ROOT = Path("/var/lib/scoreos/exports")


def count_events():
    if not EVENT_FILE.exists():
        return 0

    count = 0

    with EVENT_FILE.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                count += 1

    return count


def count_files(folder, pattern):
    if not folder.exists():
        return 0

    return len(list(folder.rglob(pattern)))


def latest_file(folder, pattern):
    if not folder.exists():
        return None

    files = list(folder.rglob(pattern))

    if not files:
        return None

    latest = max(
        files,
        key=lambda path: path.stat().st_mtime,
    )

    return {
        "path": str(latest),
        "modified": datetime.fromtimestamp(
            latest.stat().st_mtime
        ).isoformat(timespec="seconds"),
        "size_bytes": latest.stat().st_size,
    }


def main():
    status = {
        "events": count_events(),
        "recordings": count_files(
            RECORDING_ROOT,
            "*.ts",
        ),
        "highlights": count_files(
            HIGHLIGHT_ROOT,
            "*.mp4",
        ),
        "exports": count_files(
            EXPORT_ROOT,
            "*.zip",
        ),
        "latest_recording": latest_file(
            RECORDING_ROOT,
            "*.ts",
        ),
        "latest_highlight": latest_file(
            HIGHLIGHT_ROOT,
            "*.mp4",
        ),
        "latest_export": latest_file(
            EXPORT_ROOT,
            "*.zip",
        ),
    }

    print(
        json.dumps(
            status,
            indent=2,
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
