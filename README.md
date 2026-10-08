# 🏏 SCOREOS
![Version](https://img.shields.io/badge/version-v2.1.0-blue)
![Platform](https://img.shields.io/badge/platform-Raspberry%20Pi-success)
![Python](https://img.shields.io/badge/python-3.x-blue)
![License](https://img.shields.io/badge/license-MIT-green)


---

# 🏏 MATCH DAY — START HERE

For the tested Sutton CC field setup, the normal pre-match routine is deliberately simple:

```bash
~/scoreos
```

1. Power on the scoreboard system and allow the Raspberry Pi to boot.
2. Run `~/scoreos`.
3. Run **Option 1** and check the result shown on screen.
4. Run **Option 7** and check the result shown on screen.
5. If both checks are healthy, SCOREOS is ready for the match.

The field system uses the **TP-Link UB500 USB Bluetooth adapter** (normally via the long USB extension) for improved range and reliability. At home/development, SCOREOS can use the Raspberry Pi's built-in Bluetooth. Adapter selection is automatic, with the field USB adapter preferred when available.

The Reolink camera system includes a rolling camera buffer, match recording and automatic highlight generation. See [Match Day & Troubleshooting](docs/MATCH_DAY.md) for the full operating guide, useful service checks and highlight troubleshooting.

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
- 🎥 Reolink camera recording and rolling buffer
- ✂️ Automatic match highlight generation
- 📦 Highlight export tools
- 🌐 Web-based management
- ⚡ Raspberry Pi powered

---
# 🖥️ Hardware Requirements

### Recommended Hardware

| Component | Recommendation |
|-----------|----------------|
| Computer | Raspberry Pi 5 (Pi 4 supported) |
| Operating System | Raspberry Pi OS Trixie (Bookworm also supported) |
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

---.
# 🚀 Installation

SCOREOS is designed to run on Raspberry Pi OS Trixie using a Raspberry Pi 4 or Raspberry Pi 5. Existing Bookworm installations remain supported.

### Requirements

- Raspberry Pi OS Trixie (or an existing Bookworm installation)
- Python 3
- Bluetooth adapter (TP-Link UB500 recommended)
- Arduino scoreboard controller
- HDMI display
- Local network connection (optional but recommended)

### Install SCOREOS

Clone the repository and run the main installer as your normal user:

```bash
./install.sh
```

The installer handles required packages, Python dependencies, systemd services and SCOREOS configuration.

Do not run `install.sh` directly as root. It uses `sudo` automatically where required.

---
# 📁 Project Structure

```
SCOREOS
├── arduino/         Arduino communication
├── bluetooth/       Bluetooth GATT server
├── docs/            Project documentation
├── engine/          Runtime and match engine
├── installer/       Modular installer components
├── scripts/         Helper and recovery scripts
├── services/        Canonical systemd service files
├── web/             Dashboard, Ground Control and TV display
├── install.sh       Main SCOREOS installer
├── README.md
└── CHANGELOG.md
```

The project has been designed with separate components for the runtime engine, Bluetooth communication, web interface and supporting services to make future development and maintenance straightforward.

---
# 🏏 Why SCOREOS?

# 🌟 Feature Highlights

## 📺 Live TV Scoreboard
Display a clear, professional scoreboard on any HDMI-connected television or monitor with real-time score updates.

## 📡 Bluetooth Integration
Wirelessly receives scoring data from Play-Cricket Scorer using Bluetooth Low Energy (BLE), removing the need for long cable runs.

## 🎛️ Ground Control
A browser-based control panel allowing operators to monitor the system, restart services and manage the scoreboard from any device on the local network.

## 📊 Live Diagnostics
Monitor Bluetooth connections, system health and runtime information in real time, making troubleshooting quick and easy.

## 🚀 Intelligent Startup
Startup V2 automatically checks system services, Bluetooth hardware and application status before bringing the scoreboard online.

## 🔧 Modular Design
Built with separate components for Bluetooth, the web interface, match engine and hardware communication, making future development straightforward.

---

SCOREOS was created to provide cricket clubs with a modern, reliable and affordable electronic scoreboard system built using readily available hardware.

Unlike traditional scoreboards, SCOREOS combines live scoring, Bluetooth communication, system diagnostics and a web-based management interface into a single platform.

The project has been designed with three core principles:

- **Reliable** – Stable operation throughout an entire day's cricket.
- **Simple** – Easy for volunteers to operate and maintain.
- **Expandable** – Designed so new features can be added without redesigning the system.

Whether it's a friendly match or a league fixture, SCOREOS aims to provide a professional scoring experience for players, scorers and spectators.

---
# ✅ Current Capabilities

SCOREOS currently includes the following functionality:

- Bluetooth Low Energy (BLE) communication
- Play-Cricket scorer integration
- Automatic Bluetooth adapter detection
- Live TV scoreboard display
- Ground Control management interface
- Startup V2 with health checks
- Live diagnostics dashboard
- Automatic service startup
- Real-time score updates
- Raspberry Pi 4 and Raspberry Pi 5 support
- Web-based administration
- Modular architecture for future expansion

# 🛠️ Built With

- Raspberry Pi OS Trixie
- Python 3
- Flask
- HTML5 / CSS3 / JavaScript
- Bluetooth Low Energy (BLE)
- Arduino
- Systemd Services
- Chromium Kiosk Mode

---

---
# 🛣️ Project Roadmap

SCOREOS is actively developed, with new features and improvements planned for future releases.

| Version | Status | Planned Features |
|---------|:------:|------------------|
| v2.1.0 | ✅ Current | Startup V2, Ground Control, Live Diagnostics |
| v2.2.0 | 🚧 Planned | Enhanced health monitoring, improved diagnostics, repository cleanup |
| v2.3.0 | 🚧 In development | Camera recording, rolling buffer, automatic highlights, improved Ground Control |
| v2.4.0 | 📅 Planned | Match statistics, reporting and export |
| Future | 💡 Ideas | Multi-ground support, remote management, additional scoreboard themes |

---
# 👨‍💻 About SCOREOS

SCOREOS started as a project to modernise the electronic scoreboard at Sutton Cricket Club.

The aim was simple: build a reliable, affordable and expandable scoreboard system using readily available hardware rather than expensive commercial equipment.

What began as a basic scoreboard controller has evolved into a complete scoring platform featuring Bluetooth communication, live score displays, web-based management tools, automatic diagnostics and intelligent startup routines.

The project continues to evolve with a focus on reliability, ease of use and supporting grassroots cricket clubs with modern technology.

---
# 🤝 Contributing

Contributions, suggestions and bug reports are always welcome.

If you have an idea to improve SCOREOS, please open an issue or submit a pull request.

Whether it's fixing a bug, improving documentation or adding a new feature, every contribution is appreciated.

---
# 💬 Support

If you discover a bug or have a feature request, please open an issue on GitHub.

Questions, suggestions and feedback are always welcome and help improve SCOREOS for everyone.

---

# 📄 Licence

This project is released under the MIT License.

See the `LICENSE` file for full details.

---
<div align="center">

### 🏏 Developed for Sutton Cricket Club

Designed and developed by Craig Faux.

Built to provide a reliable, modern and affordable electronic scoreboard system for grassroots cricket.

⭐ If you find SCOREOS useful, consider starring the repository.

</div>
