#!/usr/bin/env python3

import argparse
import json
from datetime import datetime
from pathlib import Path


ROOT = Path("/var/lib/scoreos/recordings")


def clean(value, fallback="-"):
    text = str(
        value if value is not None else ""
    ).replace("-", "").strip()

    return text or fallback


def escape(value):
    return (
        str(value)
        .replace("\\", r"\\")
        .replace("{", "(")
        .replace("}", ")")
        .replace("\r", " ")
        .replace("\n", " ")
    )


def timestamp(seconds):
    total = int(
        round(max(0.0, float(seconds)) * 100)
    )

    hours, total = divmod(total, 360000)
    minutes, total = divmod(total, 6000)
    seconds, centiseconds = divmod(total, 100)

    return (
        f"{hours}:{minutes:02d}:"
        f"{seconds:02d}.{centiseconds:02d}"
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

    folder = (
        ROOT
        / args.date
        / args.session
    )

    history_path = (
        folder
        / "score-history.jsonl"
    )

    metadata_path = (
        folder
        / "match.json"
    )

    if not history_path.exists():
        raise SystemExit(
            f"Score history not found: {history_path}"
        )

    if not metadata_path.exists():
        raise SystemExit(
            f"Match metadata not found: {metadata_path}"
        )

    metadata = json.loads(
        metadata_path.read_text(
            encoding="utf-8"
        )
    )

    entries = []

    with history_path.open(
        "r",
        encoding="utf-8",
    ) as handle:
        for line in handle:
            try:
                state = json.loads(line)
                event_time = float(
                    state["timestamp"]
                )
            except (
                json.JSONDecodeError,
                KeyError,
                TypeError,
                ValueError,
            ):
                continue

            entries.append(
                (
                    event_time,
                    state,
                )
            )

    entries.sort(
        key=lambda item: item[0]
    )

    if not entries:
        raise SystemExit(
            "No valid score-history entries"
        )

    segment_times = []

    for segment in (
        folder
        / "full"
    ).glob("*.ts"):
        try:
            value = datetime.strptime(
                segment.stem,
                "%Y-%m-%d_%H-%M-%S",
            ).timestamp()
        except ValueError:
            continue

        segment_times.append(value)

    if segment_times:
        recording_start = min(
            segment_times
        )
        timing_source = (
            "first recording segment"
        )
    else:
        recording_start = (
            float(metadata.get("started", 0))
            - 50.0
        )
        timing_source = (
            "50-second fallback"
        )

    header = """[Script Info]
Title: SCOREOS Full Match Scoreboard
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Liberation Sans,24,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    events = []

    def dialogue(
        layer,
        start,
        end,
        content,
    ):
        events.append(
            "Dialogue: "
            f"{layer},"
            f"{timestamp(start)},"
            f"{timestamp(end)},"
            "Default,,0,0,0,,"
            f"{content}"
        )

    video_end = 86400.0

    shapes = [
        (
            0,
            "365B07",
            "m 0 944 l 1920 944 "
            "1920 1080 0 1080",
        ),
        (
            1,
            "2C1107",
            "m 1315 944 l 1920 944 "
            "1920 1080 1315 1080",
        ),
        (
            1,
            "FBF6F4",
            "m 770 944 l 1315 944 "
            "1315 1080 770 1080",
        ),
        (
            2,
            "4CC9F2",
            "m 0 940 l 1920 940 "
            "1920 944 0 944 "
            "m 767 944 l 770 944 "
            "770 1080 767 1080 "
            "m 1315 944 l 1318 944 "
            "1318 1080 1315 1080",
        ),
    ]

    for layer, colour, drawing in shapes:
        dialogue(
            layer,
            0,
            video_end,
            (
                r"{\an7\pos(0,0)\p1"
                r"\bord0\shad0"
                f"\\1c&H{colour}&"
                "}"
                + drawing
            ),
        )

    def add_text(
        start,
        end,
        text,
        x,
        y,
        size,
        colour,
        bold=True,
    ):
        tag = (
            r"{\an7"
            f"\\pos({x},{y})"
            r"\fnLiberation Sans"
            f"\\fs{size}"
            f"\\b{1 if bold else 0}"
            f"\\1c&H{colour}&"
            r"\bord0\shad0}"
        )

        dialogue(
            5,
            start,
            end,
            tag + escape(text),
        )

    for index, (
        event_time,
        state,
    ) in enumerate(entries):

        start = max(
            0.0,
            event_time - recording_start,
        )

        if index + 1 < len(entries):
            end = max(
                start + 0.01,
                entries[index + 1][0]
                - recording_start,
            )
        else:
            end = video_end

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

        target = clean(
            state.get("target"),
            "-",
        )

        required = clean(
            state.get("RunsRequired"),
            "-",
        )

        fields = [
            (
                str(
                    state.get("BatTeamName")
                    or "Batting Team"
                ).upper(),
                30,
                958,
                25,
                "FFFFFF",
            ),
            (
                f"{batter_a}  "
                f"{clean(state.get('BatAscore'), '0')} "
                f"({clean(state.get('BatABallsFaced'), '0')})",
                30,
                1000,
                22,
                "FFFFFF",
            ),
            (
                f"{batter_b}  "
                f"{clean(state.get('BatBscore'), '0')} "
                f"({clean(state.get('BatBBallsFaced'), '0')})",
                30,
                1035,
                22,
                "FFFFFF",
            ),
            (
                f"{total}/{wickets}",
                900,
                955,
                58,
                "2C1107",
            ),
            (
                f"{overs} OVERS",
                930,
                1020,
                20,
                "543124",
            ),
            (
                state.get("Bowler1Name")
                or "Bowler",
                1345,
                960,
                24,
                "FFFFFF",
            ),
            (
                state.get("Bowler1Figures")
                or "-",
                1790,
                960,
                24,
                "FFFFFF",
            ),
            (
                "CURRENT OVER",
                1345,
                1005,
                15,
                "D4C8C4",
            ),
            (
                state.get("CurrentOver")
                or "-",
                1555,
                1005,
                18,
                "FFFFFF",
            ),
            (
                "LAST WICKET",
                1345,
                1042,
                15,
                "D4C8C4",
            ),
            (
                clean(
                    state.get("LastWicket"),
                    "-",
                ),
                1555,
                1042,
                18,
                "FFFFFF",
            ),
        ]

        for (
            text,
            x,
            y,
            size,
            colour,
        ) in fields:
            add_text(
                start,
                end,
                text,
                x,
                y,
                size,
                colour,
            )

        if (
            target not in ("-", "0")
            or required not in ("-", "0")
        ):
            add_text(
                start,
                end,
                f"TARGET {target}  NEED {required}",
                840,
                1050,
                15,
                "6B5045",
            )

    output = (
        Path(args.output)
        if args.output
        else (
            folder
            / "score-overlay.ass"
        )
    )

    output.write_text(
        header
        + "\n".join(events)
        + "\n",
        encoding="utf-8",
    )

    print(f"Created: {output}")
    print(f"Score states: {len(entries)}")
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
