# SCOREOS Match Day & Troubleshooting Guide

This guide records the tested Sutton Cricket Club field workflow so the scoreboard can be operated without needing old chat notes.

## Match-day startup

Power on the scoreboard equipment and allow the Raspberry Pi to finish booting. Then run:

```bash
~/scoreos
```

From the SCOREOS menu:

1. Run **Option 1** and review the result.
2. Run **Option 7** and review the result.
3. If both checks report the expected healthy state, the system is ready for scoring.

This is the normal pre-match check. Do not make unnecessary service changes when these checks are healthy.

## Field and home Bluetooth

SCOREOS supports both the Raspberry Pi's built-in Bluetooth and an external adapter.

- **FIELD:** use the **TP-Link UB500 USB Bluetooth adapter**, normally connected through the long USB extension for better range/reliability.
- **HOME / development:** the Raspberry Pi's built-in Bluetooth can be used.
- SCOREOS is designed to prefer the field USB adapter when it is available and fall back to built-in Bluetooth.

Avoid adding blocking `bluetoothctl` polling to diagnostics. A previous field issue caused services to appear stuck because Bluetooth diagnostic calls could block. Current diagnostics/watchdog logic is designed to avoid that failure mode.

## Camera and highlights

The field camera is a Reolink camera. SCOREOS now includes:

- camera availability checks;
- a rolling camera buffer;
- match recording;
- automatic highlight generation;
- full-match video building;
- score-overlay generation;
- highlight ZIP/website export tooling.

Relevant scripts live in `scripts/`, including `camera_buffer.py`, `camera_recorder.py`, `highlight_worker.py`, `build_highlights.py`, `build_full_match.py` and `highlights_status.py`.

## Quick service check

If something does not look right, this single block gives a useful overview without repeatedly switching commands:

```bash
echo "=== SCOREOS SERVICES ==="
for s in \
  scoreos-web.service \
  scoreos-camera-buffer.service \
  scoreos-camera-recorder.service; do
  printf "%-34s " "$s"
  systemctl is-active "$s" || true
done

echo
echo "=== FAILED SERVICES ==="
systemctl --failed --no-pager

echo
echo "=== CAMERA BUFFER LOG ==="
journalctl -u scoreos-camera-buffer.service -n 20 --no-pager

echo
echo "=== CAMERA RECORDER LOG ==="
journalctl -u scoreos-camera-recorder.service -n 20 --no-pager
```

A service being intentionally inactive is not automatically a fault; interpret the output in the context of HOME/FIELD mode and whether a match is currently recording.

## Highlight generation

Highlight generation can take time because video has to be processed by FFmpeg. A progress percentage that remains unchanged for a while does not by itself mean the job has failed.

If a command exits with code **124**, that normally indicates a timeout occurred. Check the highlight status and logs before deleting files or restarting multiple services.

Useful commands:

```bash
cd ~/sutton-scoreboard-os
python3 scripts/highlights_status.py
journalctl -u scoreos-camera-buffer.service -n 50 --no-pager
journalctl -u scoreos-camera-recorder.service -n 50 --no-pager
```

Do not repeatedly restart the camera buffer while a highlight/full-match build is actively using recorded segments unless troubleshooting has shown that the buffer itself is the problem.

## Updating SCOREOS from GitHub

Before a match, avoid pulling untested changes just for the sake of being current. Update during a maintenance/test session instead:

```bash
cd ~/sutton-scoreboard-os
git status
git pull --ff-only
```

If `git status` shows local changes, stop and review them before pulling. Do not overwrite field configuration or local work blindly.

After code changes, use the SCOREOS menu/normal project procedures to test the system. Run the match-day Option 1 and Option 7 checks again before relying on it at the ground.

## If the field system appears stuck

First collect evidence rather than rebooting immediately:

```bash
systemctl --failed --no-pager
systemctl status scoreos-web.service --no-pager
systemctl status scoreos-camera-buffer.service --no-pager
systemctl status scoreos-camera-recorder.service --no-pager
```

Then inspect the relevant journal with `journalctl -u <service> -n 50 --no-pager`.

This preserves the useful error information and makes the fault much easier to diagnose.

## Golden rule

On a normal match day the intended workflow is:

**Power on → `~/scoreos` → Option 1 → Option 7 → healthy results → score the match.**

Keep development, updates and major troubleshooting for a separate test session wherever possible.
