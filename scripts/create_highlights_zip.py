#!/usr/bin/env python3

import argparse
import zipfile
from datetime import datetime
from pathlib import Path


HIGHLIGHT_ROOT = Path("/var/lib/scoreos/highlights")
EXPORT_ROOT = Path("/var/lib/scoreos/exports")


def main():
    parser = argparse.ArgumentParser(
        description="Create a ZIP containing SCOREOS highlights."
    )

    parser.add_argument(
        "--date",
        help="Match date in YYYY-MM-DD format. Defaults to today.",
    )

    args = parser.parse_args()

    match_date = (
        args.date
        or datetime.now().strftime("%Y-%m-%d")
    )

    source_folder = HIGHLIGHT_ROOT / match_date

    if not source_folder.exists():
        print(
            f"No highlight folder found: {source_folder}"
        )
        return 1

    clips = sorted(source_folder.glob("*.mp4"))

    if not clips:
        print(
            f"No highlight clips found in {source_folder}"
        )
        return 1

    EXPORT_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    destination = (
        EXPORT_ROOT /
        f"SCOREOS_Highlights_{match_date}.zip"
    )

    with zipfile.ZipFile(
        destination,
        "w",
        compression=zipfile.ZIP_STORED,
    ) as archive:
        for clip in clips:
            archive.write(
                clip,
                arcname=clip.name,
            )

    print(f"Highlights ZIP ready: {destination}")
    print(f"Clips included: {len(clips)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
