"""
Configuration management for ConKey.
Persists PIN, ports, device metadata, and preferences across system restarts.
Follows principle-make-operations-idempotent.
"""

from dataclasses import dataclass, asdict
import json
import os
from pathlib import Path
import socket
import tempfile
from typing import Optional
import uuid

CONFIG_FILE_NAME = "config.json"


def get_default_device_name() -> str:
    user = os.environ.get("USERNAME", "User")
    host = socket.gethostname()
    return f"{user}'s Laptop ({host})"


@dataclass
class ConKeyConfig:
    port: int = 8765
    discovery_port: int = 8766
    pin: str = "2026"
    autostart: bool = True
    device_name: str = ""
    device_id: str = ""
    voice_enabled: bool = True
    phonon_model: str = "phonon-2"
    phonon_port: int = 8010
    phonon_threads: int = 0
    phonon_command: str = ""

    def __post_init__(self):
        if not self.device_name:
            self.device_name = get_default_device_name()
        if not self.device_id:
            self.device_id = uuid.uuid4().hex[:12]

    @classmethod
    def from_dict(cls, data: dict) -> "ConKeyConfig":
        port = int(data.get("port", 8765))
        discovery_port = int(data.get("discovery_port", 8766))
        pin = str(data.get("pin", "2026")).strip() or "2026"
        autostart = bool(data.get("autostart", True))
        device_name = str(data.get("device_name", "")).strip() or get_default_device_name()
        device_id = str(data.get("device_id", "")).strip() or uuid.uuid4().hex[:12]
        voice_enabled = bool(data.get("voice_enabled", True))
        phonon_model = str(data.get("phonon_model", "phonon-2")).strip() or "phonon-2"
        try:
            phonon_port = int(data.get("phonon_port", 8010))
        except (TypeError, ValueError):
            phonon_port = 8010
        try:
            phonon_threads = int(data.get("phonon_threads", 0))
        except (TypeError, ValueError):
            phonon_threads = 0
        phonon_command = str(data.get("phonon_command", "")).strip()
        return cls(
            port=port,
            discovery_port=discovery_port,
            pin=pin,
            autostart=autostart,
            device_name=device_name,
            device_id=device_id,
            voice_enabled=voice_enabled,
            phonon_model=phonon_model,
            phonon_port=max(1, min(phonon_port, 65535)),
            phonon_threads=max(0, phonon_threads),
            phonon_command=phonon_command,
        )


def get_default_config_path() -> Path:
    return Path(__file__).parent.parent / CONFIG_FILE_NAME


def load_config(config_path: Optional[Path] = None) -> ConKeyConfig:
    path = config_path or get_default_config_path()
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            config = ConKeyConfig.from_dict(data)
            # Ensure device_name and device_id are saved if they were missing
            if not data.get("device_name") or not data.get("device_id"):
                save_config(config, path)
            return config
        except Exception:
            pass

    config = ConKeyConfig()
    save_config(config, path)
    return config


def save_config(config: ConKeyConfig, config_path: Optional[Path] = None) -> None:
    path = config_path or get_default_config_path()
    data = asdict(config)
    dir_path = path.parent
    dir_path.mkdir(parents=True, exist_ok=True)

    temp_fd, temp_path = tempfile.mkstemp(dir=dir_path, prefix="conkey_cfg_")
    try:
        with open(temp_fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(temp_path, path)
    except Exception:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise
