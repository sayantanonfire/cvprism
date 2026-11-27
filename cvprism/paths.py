"""Local (never-synced) device state locations. See ADR-004 and ADR-013."""
from __future__ import annotations

import os
from pathlib import Path

from platformdirs import user_data_dir


def home() -> Path:
    env = os.environ.get("CVPRISM_HOME")
    return Path(env).expanduser() if env else Path(user_data_dir("cvprism", appauthor=False))


def device_file() -> Path:
    return home() / "device.yaml"


def outbox_dir() -> Path:
    return home() / "outbox"


def counters_file() -> Path:
    return home() / "counters.json"


def registry_cache() -> Path:
    return home() / "registry.cache.json"


def queue_dir() -> Path:
    return home() / "queue"


def logs_dir() -> Path:
    return home() / "logs"
