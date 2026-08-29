import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class InstallationTemplateTests(unittest.TestCase):
    def test_python_services_use_project_virtual_environment(self):
        for service in (ROOT / "services").glob("*.service"):
            text = service.read_text(encoding="utf-8")

            if "python" not in text:
                continue

            self.assertNotIn("/usr/bin/python3", text, service.name)
            self.assertIn(
                "{{INSTALL_DIR}}/venv/bin/python",
                text,
                service.name,
            )

    def test_runtime_files_do_not_assume_pi_home_directory(self):
        paths = [
            ROOT / "bluetooth" / "server.py",
            ROOT / "web" / "server.py",
            ROOT / "web" / "bluetooth_manager.py",
            ROOT / "scripts" / "bluetooth_watchdog.py",
            ROOT / "scripts" / "legacy_advertisement_watchdog.py",
            ROOT / "services" / "sutton-scoreboard-advert.service",
        ]

        for path in paths:
            self.assertNotIn(
                "/home/pi/sutton-scoreboard-os",
                path.read_text(encoding="utf-8"),
                path.name,
            )

    def test_desktop_startup_is_installed(self):
        installer = (
            ROOT
            / "installer"
            / "services.sh"
        ).read_text(encoding="utf-8")

        self.assertIn(".config/autostart", installer)
        self.assertIn("scoreos.desktop", installer)

    def test_legacy_advertising_uses_selected_adapter(self):
        advertiser = (
            ROOT
            / "scripts"
            / "legacy-advertisement.sh"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "/run/scoreos/bluetooth-adapter",
            advertiser,
        )


if __name__ == "__main__":
    unittest.main()
