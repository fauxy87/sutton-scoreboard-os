# Raspberry Pi 5 and USB SSD Migration

This guide prepares a Raspberry Pi 5 to become the main SCOREOS computer.
Hardware-dependent verification should be completed at the field before the
old Raspberry Pi is retired.

## Recommended layout

- Raspberry Pi 5 as the main SCOREOS computer
- USB SSD as the boot and recording drive
- TP-Link UB500 on the long USB extension at the field
- Pi 5 built-in Bluetooth available as a fallback and for home testing
- Reolink camera connected to the same local network

## Before migration

1. Keep the existing field Pi unchanged as the rollback system.
2. Back up `/etc/scoreos` from the existing Pi. This contains camera and
   highlights settings and may contain the camera password.
3. Back up any recordings that must be retained from `/var/lib/scoreos`.
4. Record the working camera IP address and confirm that it will not be handed
   to a different device by the router.

## Prepare the Pi 5 SSD

1. Use Raspberry Pi Imager to write the current 64-bit Raspberry Pi OS with
   desktop to the USB SSD.
2. In Imager settings, create the required username, hostname, Wi-Fi and SSH
   configuration.
3. Connect the SSD to a USB 3 port on the Pi 5 and boot it without altering the
   existing field Pi.
4. Update Raspberry Pi OS completely and reboot.

## Install SCOREOS

Clone the repository into the normal user's home directory and run the
installer as that user, not as root:

```bash
cd ~
git clone https://github.com/fauxy87/sutton-scoreboard-os.git
cd sutton-scoreboard-os
./install.sh
```

Select `Install SCOREOS`, then reboot when prompted. The installer uses the
actual repository path and account name; the username does not need to be
`pi`.

## Restore settings

Restore the backed-up `/etc/scoreos` files only after the installer has run.
Keep the restored files readable only by administrators because the camera
configuration can contain credentials.

## Home tests

With the camera and field USB adapter absent, verify:

- Ground Control opens at `http://<pi-address>:8080/groundcontrol`.
- Manual scoring changes the TV display.
- The built-in Bluetooth adapter advertises SCOREOS.
- Missing camera hardware is reported without stopping the web interface.
- Rebooting returns to the SCOREOS startup screen automatically.

## Field tests

Before the first live match, verify in this order:

1. The TP-Link UB500 is selected when connected through the long extension.
2. Play-Cricket Scorer connects and updates every scoreboard field.
3. The Arduino reconnects after being unplugged and reconnected.
4. Camera test and preview both work.
5. Starting a test match preserves the pre-roll and creates both main-stream
   highlight segments and substream full-match segments.
6. FOUR, SIX and WICKET events produce queued TV graphics and highlight clips.
7. Stopping the match produces `full-match.mp4` and, when enabled,
   `match-highlights.mp4`.
8. The safe shutdown button refuses shutdown while match processing is unsafe.
9. Perform a reboot and repeat Bluetooth and camera checks.

## Rollback rule

Do not wipe or repurpose the previous field Pi until the Pi 5 has completed at
least one full test match and one real match without a recording, Bluetooth or
display failure.
