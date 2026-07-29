# 🏏 SCOREOS

![Version](https://img.shields.io/badge/Version-v2.1.0-blue)
![Platform](https://img.shields.io/badge/Platform-Raspberry%20Pi-red)
![Status](https://img.shields.io/badge/Status-Active-success)

---

# What is SCOREOS?

SCOREOS is a Raspberry Pi based electronic cricket scoreboard system designed to provide a reliable, modern and easy-to-use scoreboard for cricket clubs.

Originally developed for **Sutton Cricket Club (Cambridgeshire)**, SCOREOS combines Bluetooth communication, a live TV display, diagnostics and a web-based Ground Control interface into one complete system.

The aim of the project is to provide a professional electronic scoreboard that is simple to install, reliable to operate and easy to expand with new features.

---
# ✨ Features

- 📺 Full screen TV scoreboard display
- 📱 Ground Control web interface
- 📡 Bluetooth Low Energy (BLE) communication
- 🔄 Automatic Bluetooth adapter detection
- 🚀 Startup health checks
- 📊 Real-time score updates
- 🔍 Live diagnostics
- 📈 System health monitoring
- 🌐 Web-based management
- ⚡ Raspberry Pi powered

---
# 🖥️ Hardware Requirements

### Recommended Hardware

| Component | Recommendation |
|-----------|----------------|
| Computer | Raspberry Pi 5 (Pi 4 supported) |
| Operating System | Raspberry Pi OS (Bookworm, based on Debian 12) |
| Bluetooth | TP-Link UB500 USB Bluetooth Adapter |
| Score Controller | Arduino-based BLE controller |
| Display | HDMI TV or Monitor |
| Network | Ethernet or Wi-Fi |

---
# 🏗️ System Overview

SCOREOS is designed around a Raspberry Pi acting as the central controller for an electronic cricket scoreboard.

The Raspberry Pi receives live score data over Bluetooth Low Energy (BLE) from an Arduino-based controller and updates the TV display in real time. A built-in web interface provides Ground Control, diagnostics and system management from any device on the local network.

```text
               Bluetooth LE
                     │
              Arduino Controller
                     │
                     ▼
        Raspberry Pi (SCOREOS)
                     │
      ┌──────────────┼──────────────┐
      │              │              │
 TV Display     Ground Control   Dashboard
```

---
