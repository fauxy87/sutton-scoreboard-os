from dataclasses import asdict, dataclass
import json
from pathlib import Path
from threading import Lock


STARTUP_FILE = Path("/run/scoreos/startup.json")


@dataclass
class StartupStage:
    id: str
    title: str
    progress: int


STARTUP_STAGES = [
    StartupStage("boot", "Starting SCOREOS", 10),
    StartupStage("services", "Loading services", 25),
    StartupStage("arduino", "Checking Arduino", 40),
    StartupStage("display", "Testing scoreboard", 60),
    StartupStage("bluetooth", "Starting Bluetooth", 80),
    StartupStage("ready", "Match Ready", 100),
]


class StartupManager:
    def __init__(self):
        self.lock = Lock()
        self.ensure_file()

    def default_status(self):
        return {
            "started": False,
            "stage": asdict(STARTUP_STAGES[0]),
            "log": [],
        }

    def ensure_file(self):
        STARTUP_FILE.parent.mkdir(parents=True, exist_ok=True)

        if not STARTUP_FILE.exists():
            self.write_status(self.default_status())

    def read_status(self):
        self.ensure_file()

        try:
            return json.loads(STARTUP_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            status = self.default_status()
            self.write_status(status)
            return status

    def write_status(self, status):
        STARTUP_FILE.parent.mkdir(parents=True, exist_ok=True)

        temporary_file = STARTUP_FILE.with_suffix(".tmp")
        temporary_file.write_text(
            json.dumps(status, indent=2),
            encoding="utf-8",
        )
        temporary_file.replace(STARTUP_FILE)

    def get_stage(self):
        return self.read_status()["stage"]

    def get_status(self):
        return self.read_status()

    def add_log(self, message):
        with self.lock:
            status = self.read_status()
            status["log"].append(message)
            self.write_status(status)

    def set_stage(self, stage_id, log_message=None):
        stage = next(
            (stage for stage in STARTUP_STAGES if stage.id == stage_id),
            None,
        )

        if stage is None:
            raise ValueError(f"Unknown startup stage: {stage_id}")

        with self.lock:
            status = self.read_status()
            status["stage"] = asdict(stage)
            status["started"] = stage.id == "ready"

            if log_message and log_message not in status["log"]:
                status["log"].append(log_message)

            self.write_status(status)

        return stage


startup_manager = StartupManager()
