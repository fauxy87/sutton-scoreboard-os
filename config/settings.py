"""Central configuration loader for SCOREOS."""

from configparser import ConfigParser
from pathlib import Path
from typing import Optional


CONFIG_FILE = Path(__file__).resolve().parent / "settings.ini"


def load_config() -> ConfigParser:
    """Load and validate the SCOREOS configuration file."""
    parser = ConfigParser()

    if not CONFIG_FILE.exists():
        raise FileNotFoundError(
            f"SCOREOS configuration file not found: {CONFIG_FILE}"
        )

    loaded_files = parser.read(CONFIG_FILE)

    if not loaded_files:
        raise RuntimeError(
            f"Unable to read SCOREOS configuration file: {CONFIG_FILE}"
        )

    return parser


config = load_config()


def get(section: str, option: str, fallback: Optional[str] = None) -> str:
    """Return a text configuration value."""
    value = config.get(section, option, fallback=fallback)

    if value is None:
        raise KeyError(f"Missing configuration value: [{section}] {option}")

    return value


def getint(section: str, option: str, fallback: Optional[int] = None) -> int:
    """Return an integer configuration value."""
    value = config.getint(section, option, fallback=fallback)

    if value is None:
        raise KeyError(f"Missing configuration value: [{section}] {option}")

    return value


def getboolean(
    section: str,
    option: str,
    fallback: Optional[bool] = None,
) -> bool:
    """Return a boolean configuration value."""
    value = config.getboolean(section, option, fallback=fallback)

    if value is None:
        raise KeyError(f"Missing configuration value: [{section}] {option}")

    return value
