# 🏏 SCOREOS

**Bluetooth cricket scoreboard system for Play-Cricket Scorer**

SCOREOS is a Raspberry Pi and Arduino based scoreboard system designed for cricket clubs.

It connects directly to **Play-Cricket Scorer** over Bluetooth and automatically updates a physical LED scoreboard while also providing live spectator and control webpages over Wi-Fi.

---

# Features

✅ Play-Cricket Bluetooth integration

✅ Arduino LED scoreboard

✅ Live spectator webpage

✅ Manual scoring webpage

✅ Wi-Fi Hotspot

✅ Automatic startup

✅ Raspberry Pi 4 compatible

✅ Installable from GitHub

---

# Hardware

- Raspberry Pi 4
- Arduino Uno
- LED scoreboard
- USB cable
- Bluetooth
- Wi-Fi

---

# Screenshots

Coming soon

- Spectator webpage
- Control webpage
- Physical scoreboard

---

# Installation

Clone the repository

```bash
git clone https://github.com/fauxy87/sutton-scoreboard-os.git

cd sutton-scoreboard-os
```

Install

```bash
sudo ./install/install.sh
```

Configure hotspot

```bash
sudo ./install/setup-hotspot.sh
```

---

# Default Hotspot

SSID

```
SuttonCC-Scoreboard
```

Password

```
Sutton1877
```

Control Page

```
http://192.168.4.1:8080/control
```

Spectator Page

```
http://192.168.4.1:8080
```

---

# Bluetooth

Bluetooth Device Name

```
SCOREOS
```

Connect using the Play-Cricket Scorer App.

---

# Arduino Protocol

The Arduino receives:

```
4,BatAScore,Total,BatBScore,Wickets,Overs,Target#
```

Example

```
4,045,123,033,4,17,201#
```

Display Test

```
5#
```

---

# Repository Structure

```
arduino/
bluetooth/
engine/
install/
scripts/
services/
web/
README.md
```

---

# Current Version

**SCOREOS v1.0.0**

Features

- Bluetooth
- Arduino
- Web Interface
- Manual Scoring
- Wi-Fi Hotspot
- Automatic Services

---

# Roadmap

## Version 1.1

- Admin Dashboard
- Match Archive
- GitHub Updater
- Improved Installer
- Settings Page
- Branding Support

---

# Developed By

Craig Faux

Facilities Manager

Sutton Cricket Club

Cambridgeshire

---

# Licence

MIT Licence
