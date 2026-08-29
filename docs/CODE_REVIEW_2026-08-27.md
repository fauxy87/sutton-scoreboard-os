# SCOREOS Offline Code Review — 27 August 2026

## Outcome

The repository compiles successfully and its shell scripts pass syntax checks.
The review fixed the main software blockers found for moving the system to a
Raspberry Pi 5 with a USB SSD. Hardware verification is still required before
the Pi 5 replaces the existing field Pi.

## Fixed during this review

- Systemd services now run with the Python virtual environment populated by
  the installer.
- The virtual environment can also see Raspberry Pi OS packages such as D-Bus,
  PyGObject, pyserial and gpiozero.
- Install and runtime paths no longer depend on `/home/pi`.
- Recording folder ownership follows the account chosen during installation
  instead of assuming username `pi` or UID 1000.
- The installer installs the Chromium kiosk autostart file.
- The installer checks Ground Control on its actual port, 8080.
- Required GPIO, rfkill and Wayland display packages are installed.
- Bluetooth selects the TP-Link field adapter when present and otherwise uses
  built-in Bluetooth for home testing.
- Camera recording honours an explicit substream path.
- Missing audio on either RTSP stream no longer stops FFmpeg from recording.
- Disabled or incomplete camera configuration no longer causes a rapid retry
  loop.
- Camera credentials are saved with mode 0600.
- Version and operating-system documentation now match Raspberry Pi OS
  Trixie, while retaining Bookworm support for existing installations.

## Offline verification completed

- Python compilation: passed
- Shell syntax validation: passed
- Whitespace/error check of source changes: passed
- Parser tests: passed
- FOUR, SIX, WICKET and FIFTY event tests: passed
- Camera main/substream URL tests: passed
- Camera credential permission test: passed
- Service template and path portability tests: passed

## Still requires Raspberry Pi hardware

- BlueZ GATT registration and advertising on built-in Bluetooth
- Preferred TP-Link UB500 selection at the field
- Play-Cricket Scorer connection from Android/iPhone
- Arduino serial reconnect and physical scoreboard output
- Chromium kiosk startup and HDMI mode on the field display
- Reolink RTSP readiness, preview and dual-stream recording
- Full-match assembly and automatic highlight timing
- Physical GPIO shutdown button
- Reboot, power-loss recovery and SSD write performance

## Known non-blocking work

The installer menu still labels update, repair, backup, restore and uninstall
as future features. These are not needed for the initial Pi 5 migration but
should be implemented before the installer is described as a complete
maintenance tool.
