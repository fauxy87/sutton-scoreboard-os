# Changelog

## 1.0-alpha1 — July 2026

### Added

- Raspberry Pi 4 and Debian Trixie platform
- Android and iPhone Play-Cricket support
- Bluetooth GATT server
- BLE advertising through btmgmt and Expect
- Play-Cricket packet parser
- Match-state engine
- Persistent Arduino connection
- Automatic systemd startup

### Fixed

- Unreliable Android BLE discovery on the older platform
- Stale Android GATT handle problems
- Repeated Arduino serial reconnects
- Bluetooth advertising command timing problems

### Known limitations

- Standalone hotspot not yet configured
- Web spectator display not yet included
- Health dashboard not yet included
