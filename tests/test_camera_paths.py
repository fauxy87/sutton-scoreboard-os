import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import camera_buffer
from scripts import camera_recorder

import sys

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

import camera_manager


class CameraPathTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config = Path(self.temp_dir.name) / "camera.json"
        self.config.write_text(
            json.dumps(
                {
                    "enabled": True,
                    "host": "192.168.0.100",
                    "port": 554,
                    "username": "score user",
                    "password": "p@ss/word",
                    "rtsp_path": "/custom_main",
                    "sub_rtsp_path": "/custom_sub",
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_recorder_uses_explicit_main_and_substream_paths(self):
        with mock.patch.object(
            camera_recorder,
            "CAMERA_CONFIG",
            self.config,
        ):
            main_url, sub_url = camera_recorder.load_camera_paths()

        base = "rtsp://score%20user:p%40ss%2Fword@192.168.0.100:554"
        self.assertEqual(main_url, base + "/custom_main")
        self.assertEqual(sub_url, base + "/custom_sub")

    def test_buffer_uses_configured_substream(self):
        with mock.patch.object(
            camera_buffer,
            "CAMERA_CONFIG",
            self.config,
        ):
            url = camera_buffer.camera_url()

        self.assertTrue(url.endswith("/custom_sub"))

    def test_saved_camera_credentials_are_private(self):
        target = Path(self.temp_dir.name) / "saved-camera.json"

        with mock.patch.object(
            camera_manager,
            "CAMERA_CONFIG",
            target,
        ):
            camera_manager.save(
                {
                    "enabled": True,
                    "host": "192.168.0.100",
                    "username": "admin",
                    "password": "secret",
                }
            )

        self.assertEqual(target.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
