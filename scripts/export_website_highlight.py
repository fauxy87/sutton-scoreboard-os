#!/usr/bin/env python3

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

HIGHLIGHT_ROOT = Path('/var/lib/scoreos/highlights')
RECORDING_ROOT = Path('/var/lib/scoreos/recordings')
EVENT_FILE = Path('/var/lib/scoreos/events/events.jsonl')


def read_json(path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return {}


def find_match_metadata(match_date, session_id):
    candidates = []
    if session_id:
        candidates.extend(RECORDING_ROOT.glob(f'*/{session_id}/match.json'))
    candidates.append(RECORDING_ROOT / match_date / (session_id or '') / 'match.json')
    for path in candidates:
        if path.exists():
            data = read_json(path)
            if data:
                return data
    return {}


def team_name(meta):
    for key in ('team', 'sutton_team', 'home_team', 'batting_team', 'team1', 'team_1'):
        value = str(meta.get(key) or '').strip()
        if 'sutton' in value.lower():
            return value
    for key in ('batting_team', 'fielding_team', 'home_team', 'away_team', 'team1', 'team2', 'team_1', 'team_2'):
        value = str(meta.get(key) or '').strip()
        if value:
            return value
    return 'Sutton CC'


def opponent_name(meta, sutton):
    for key in ('opponent', 'opposition'):
        value = str(meta.get(key) or '').strip()
        if value:
            return value
    for key in ('batting_team', 'fielding_team', 'home_team', 'away_team', 'team1', 'team2', 'team_1', 'team_2'):
        value = str(meta.get(key) or '').strip()
        if value and value.lower() != sutton.lower() and 'sutton' not in value.lower():
            return value
    return ''


def event_moments(match_date, session_id):
    counts = {'FOUR': 0, 'SIX': 0, 'WICKET': 0, 'FIFTY': 0, 'HUNDRED': 0}
    if not EVENT_FILE.exists():
        return []
    try:
        lines = EVENT_FILE.read_text(encoding='utf-8').splitlines()
    except OSError:
        return []
    for line in lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if session_id and str(event.get('session_id') or '') != session_id:
            continue
        event_type = str(event.get('type') or '').upper()
        if event_type in counts:
            counts[event_type] += 1
    labels = []
    mapping = [('FOUR', 'Fours'), ('SIX', 'Sixes'), ('WICKET', 'Wickets'), ('FIFTY', 'Fifties'), ('HUNDRED', 'Centuries')]
    for key, label in mapping:
        if counts[key]:
            labels.append(f"{counts[key]} {label}")
    return labels


def main():
    parser = argparse.ArgumentParser(description='Create a Sutton website highlight manifest.')
    parser.add_argument('--date', required=True)
    parser.add_argument('--session', default='')
    parser.add_argument('--video', default='')
    parser.add_argument('--video-url', default='')
    parser.add_argument('--result', default='')
    parser.add_argument('--match-id', default='')
    args = parser.parse_args()

    folder = HIGHLIGHT_ROOT / args.date
    if args.session:
        folder /= args.session
    video = Path(args.video) if args.video else folder / 'match-highlights.mp4'
    if not video.exists():
        raise SystemExit(f'Highlight video not found: {video}')

    meta = find_match_metadata(args.date, args.session)
    sutton = team_name(meta)
    opponent = opponent_name(meta, sutton)
    result = args.result or str(meta.get('result') or meta.get('match_result') or '').strip()
    match_id = args.match_id or str(meta.get('match_id') or meta.get('play_cricket_match_id') or '').strip()
    title = f"{sutton} v {opponent} - Match Highlights" if opponent else f"{sutton} - Match Highlights"

    item = {
        'title': title,
        'team': sutton,
        'opponent': opponent,
        'date': args.date,
        'result': result,
        'match_id': match_id,
        'kind': 'Match highlights',
        'type': 'video/mp4',
        'video_url': args.video_url,
        'moments': event_moments(args.date, args.session),
        'scoreos_session': args.session,
        'local_video': str(video),
        'video_filename': video.name,
        'video_bytes': video.stat().st_size,
        'created_at': datetime.now(timezone.utc).isoformat(),
    }

    manifest = {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'source': 'Sutton Scoreboard OS',
        'highlights': [item],
    }

    destination = folder / 'website-highlight.json'
    destination.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(destination)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
