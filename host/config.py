"""
Configuration management for ConKey.
Persists PIN, ports, and preferences across system restarts.
Follows principle-make-operations-idempotent.
"""

from dataclasses import dataclass, asdict
import json
import os
from pathlib import Path
import random
import tempfile
from typing import Optional

CONFIG_FILE_NAME = "config.json"


@dataclass
class ConKeyConfig:
    port: int = 8765
    discovery_port: int = 8766
    pin: str = "2026"
    autostart: bool = True

    @classmethod
    def from_dict(cls, data: dict) -> "ConKeyConfig":
        port = int(data.get("port", 8765))
        discovery_port = int(data.get("discovery_port", 8766))
        pin = str(data.get("pin", "2026")).strip()
        if not pin:
            pin = "2026"
        autostart = bool(data.get("autostart", True))
        return cls(port=port, discovery_port=discovery_port, pin=pin, autostart=autostart)


def get_default_config_path() -> Path:
    return Path(__file__).parent.parent / CONFIG_FILE_NAME


def load_config(config_path: Optional[Path] = None) -> ConKeyConfig:
    path = config_path or get_default_config_path()
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return ConKeyConfig.from_dict(data)
        except Exception:
            # Fall back to new defaults if corrupted
            pass

    # Generate initial persistent config
    config = ConKeyConfig()
    save_config(config, path)
    return config


def save_config(config: ConKeyConfig, config_path: Optional[Path] = None) -> None:
    path = config_path or get_default_config_path()
    data = asdict(config)
    dir_path = path.parent
    dir_path.mkdir(parents=True, exist_ok=True)

    # Atomic write via temporary file
    temp_fd, temp_path = tempfile.mkstemp(dir=dir_path, prefix="conkey_cfg_")
    try:
        with open(temp_fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(temp_path, path)
    except Exception:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise
