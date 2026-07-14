# SCOREOS

SCOREOS is a Raspberry Pi cricket scoreboard system created for Sutton Cricket Club.

It receives live scoring data from the Play-Cricket Scorer app over Bluetooth Low Energy, processes the match state and sends the display frame to an Arduino-controlled physical scoreboard.

## Current release

**Version 1.0-alpha1**

## Working features

- Android and iPhone Play-Cricket support
- Automatic BLE advertising
- Bluetooth GATT server
- Play-Cricket packet parsing
- Match-state processing
- Persistent Arduino serial connection
- Automatic startup using systemd
- Raspberry Pi 4
- Debian 13 Trixie
- BlueZ 5.82

## Architecture

```text
Play-Cricket Scorer
        |
        v
BLE Advertisement
        |
        v
Python GATT Server
        |
        v
Play-Cricket Parser
        |
        v
Match State
        |
        v
Arduino
        |
        v
Physical Scoreboard
```

## Services

```text
sutton-scoreboard-advert.service
sutton-scoreboard.service
```

Check the services:

```bash
systemctl is-active sutton-scoreboard-advert.service
systemctl is-active sutton-scoreboard.service
sudo btmgmt advinfo
```

Expected:

```text
active
active
Instances list with 1 item
```

View live scoring logs:

```bash
sudo journalctl -fu sutton-scoreboard.service
```

## Bluetooth UUIDs

Service UUID:

```text
5a0d6a15-b664-4304-8530-3a0ec53e5bc1
```

Write characteristic UUID:

```text
df531f62-fc0b-40ce-81b2-32a6262ea440
```

## Status

This is an alpha release. Bluetooth reception, automatic startup and physical scoreboard output have been successfully tested after reboot.
