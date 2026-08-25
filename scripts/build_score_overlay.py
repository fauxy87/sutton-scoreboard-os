#!/usr/bin/env python3

import argparse
import json
from datetime import datetime
from pathlib import Path


RECORDING_ROOT = Path(
    "/var/lib/scoreos/recordings"
)


def clean(value, fallback="-"):
    value = str(
        value if value is not None else ""
    ).replace("-", "").strip()

    return value or fallback


def ffmpeg_text(value):
    return (
        str(value)
        .replace("\\", r"\\")
        .replace(":", r"\:")
        .replace("'", r"\'")
        .replace("%", r"\%")
    )


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--date",
        required=True,
    )

    parser.add_argument(
        "--session",
        required=True,
    )

    parser.add_argument(
        "--output",
    )

    args = parser.parse_args()

    session_folder = (
        RECORDING_ROOT
        / args.date
        / args.session
    )

    history_file = (
        session_folder
        / "score-history.jsonl"
    )

    metadata_file = (
        session_folder
        / "match.json"
    )

    if not history_file.exists():
        raise SystemExit(
            f"Score history not found: {history_file}"
        )

    if not metadata_file.exists():
        raise SystemExit(
            f"Match metadata not found: {metadata_file}"
        )

    metadata = json.loads(
        metadata_file.read_text(
            encoding="utf-8"
        )
    )

    match_started = float(
        metadata.get("started", 0)
    )

    entries = []

    with history_file.open(
        "r",
        encoding="utf-8",
    ) as handle:
        for line in handle:
            line = line.strip()

            if not line:
                continue

            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            try:
                timestamp = float(
                    entry["timestamp"]
                )
            except (
                KeyError,
                TypeError,
                ValueError,
            ):
                continue

            entries.append(
                (
                    timestamp,
                    entry,
                )
            )

    entries.sort(
        key=lambda item: item[0]
    )

    if not entries:
        raise SystemExit(
            "No valid score-history entries"
        )

    #
    # Synchronise the score history to the actual
    # recording rather than assuming a fixed amount
    # of pre-roll. Segment filenames contain their
    # real start time.
    #
    full_folder = (
        session_folder
        / "full"
    )

    segment_times = []

    for segment in full_folder.glob("*.ts"):
        try:
            parsed = datetime.strptime(
                segment.stem,
                "%Y-%m-%d_%H-%M-%S",
            )
        except ValueError:
            continue

        segment_times.append(
            parsed.timestamp()
        )

    if segment_times:
        recording_start = min(
            segment_times
        )
        timing_source = (
            "first recording segment"
        )
    else:
        # Fallback for older matches whose raw segments
        # have already been cleaned after the master was
        # successfully built.
        recording_start = (
            match_started - 50.0
        )
        timing_source = (
            "50-second fallback"
        )

    filters = [
        # Main TV-style lower-third background.
        (
            "drawbox="
            "x=0:y=944:w=1920:h=136:"
            "color=0x075b36@0.98:t=fill"
        ),

        # Dark right section.
        (
            "drawbox="
            "x=1315:y=944:w=605:h=136:"
            "color=0x07112c@0.98:t=fill"
        ),

        # White centre score panel.
        (
            "drawbox="
            "x=770:y=944:w=545:h=136:"
            "color=0xf4f6fb@1.0:t=fill"
        ),

        # Gold top border.
        (
            "drawbox="
            "x=0:y=940:w=1920:h=4:"
            "color=0xf2c94c@1.0:t=fill"
        ),

        # Gold centre dividers.
        (
            "drawbox="
            "x=767:y=944:w=3:h=136:"
            "color=0xf2c94c@0.95:t=fill"
        ),
        (
            "drawbox="
            "x=1315:y=944:w=3:h=136:"
            "color=0xf2c94c@0.95:t=fill"
        ),
    ]

    font = (
        "/usr/share/fonts/truetype/"
        "liberation2/LiberationSans-Regular.ttf"
    )

    bold_font = (
        "/usr/share/fonts/truetype/"
        "liberation2/LiberationSans-Bold.ttf"
    )

    def add_text(
        text,
        x,
        y,
        size,
        colour,
        start,
        end,
        bold=False,
    ):
        text = ffmpeg_text(text)

        filters.append(
            "drawtext="
            f"fontfile='{bold_font if bold else font}':"
            f"text='{text}':"
            f"x={x}:y={y}:"
            f"fontsize={size}:"
            f"fontcolor={colour}:"
            f"enable='between(t,{start:.3f},{end:.3f})'"
        )

    for index, (
        timestamp,
        state,
    ) in enumerate(entries):

        start = max(
            0.0,
            timestamp - recording_start,
        )

        if index + 1 < len(entries):
            end = max(
                start + 0.01,
                entries[index + 1][0]
                - recording_start,
            )
        else:
            end = 86400.0

        total = clean(
            state.get("total"),
            "0",
        )

        wickets = clean(
            state.get("wickets"),
            "0",
        )

        overs = clean(
            state.get("overs"),
            "0",
        )

        batting_team = str(
            state.get("BatTeamName")
            or "Batting Team"
        ).upper()

        batter_a = (
            state.get("Bat1Name")
            or "-"
        )

        batter_b = (
            state.get("Bat2Name")
            or "-"
        )

        if str(
            state.get("BatAStriker")
        ) == "1":
            batter_a = "* " + batter_a

        if str(
            state.get("BatBStriker")
        ) == "1":
            batter_b = "* " + batter_b

        batter_a_score = clean(
            state.get("BatAscore"),
            "0",
        )

        batter_b_score = clean(
            state.get("BatBscore"),
            "0",
        )

        batter_a_balls = clean(
            state.get("BatABallsFaced"),
            "0",
        )

        batter_b_balls = clean(
            state.get("BatBBallsFaced"),
            "0",
        )

        bowler = (
            state.get("Bowler1Name")
            or "Bowler"
        )

        figures = (
            state.get("Bowler1Figures")
            or "-"
        )

        current_over = (
            state.get("CurrentOver")
            or "-"
        )

        last_wicket = clean(
            state.get("LastWicket"),
            "-",
        )

        target = clean(
            state.get("target"),
            "-",
        )

        runs_required = clean(
            state.get("RunsRequired"),
            "-",
        )

        # LEFT: team + batters
        add_text(
            batting_team,
            30,
            958,
            25,
            "white",
            start,
            end,
            True,
        )

        add_text(
            f"{batter_a}  {batter_a_score} ({batter_a_balls})",
            30,
            1000,
            22,
            "white",
            start,
            end,
            True,
        )

        add_text(
            f"{batter_b}  {batter_b_score} ({batter_b_balls})",
            30,
            1035,
            22,
            "white",
            start,
            end,
            True,
        )

        # CENTRE: score
        add_text(
            f"{total}/{wickets}",
            900,
            955,
            58,
            "0x07112c",
            start,
            end,
            True,
        )

        add_text(
            f"{overs} OVERS",
            930,
            1020,
            20,
            "0x243154",
            start,
            end,
            True,
        )

        if (
            target not in ("-", "0")
            or runs_required not in ("-", "0")
        ):
            add_text(
                f"TARGET {target}  NEED {runs_required}",
                840,
                1050,
                15,
                "0x45506b",
                start,
                end,
                True,
            )

        # RIGHT: bowler / over / wicket
        add_text(
            bowler,
            1345,
            960,
            24,
            "white",
            start,
            end,
            True,
        )

        add_text(
            figures,
            1790,
            960,
            24,
            "white",
            start,
            end,
            True,
        )

        add_text(
            "CURRENT OVER",
            1345,
            1005,
            15,
            "0xc4c8d4",
            start,
            end,
            True,
        )

        add_text(
            current_over,
            1555,
            1005,
            18,
            "white",
            start,
            end,
            True,
        )

        add_text(
            "LAST WICKET",
            1345,
            1042,
            15,
            "0xc4c8d4",
            start,
            end,
            True,
        )

        add_text(
            last_wicket,
            1555,
            1042,
            18,
            "white",
            start,
            end,
            True,
        )

    output = (
        Path(args.output)
        if args.output
        else (
            session_folder
            / "score-overlay-filter.txt"
        )
    )

    output.write_text(
        ",".join(filters) + "\n",
        encoding="utf-8",
    )

    print(
        f"Created: {output}"
    )

    print(
        f"Score states: {len(entries)}"
    )

    print(
        "Recording start: "
        f"{recording_start:.3f}"
    )

    print(
        "Timing source: "
        f"{timing_source}"
    )


if __name__ == "__main__":
    main()
