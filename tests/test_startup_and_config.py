from pathlib import Path
import pytest
from host.config import ConKeyConfig, load_config, save_config
from host.startup import (
    get_shortcut_path,
    is_startup_enabled,
    enable_startup,
    disable_startup,
)

def test_config_lifecycle(tmp_path: Path):
    cfg_path = tmp_path / "test_config.json"
    assert not cfg_path.exists()

    # Load defaults
    cfg = load_config(cfg_path)
    assert cfg.port == 8765
    assert cfg.discovery_port == 8766
    assert cfg.pin == "2026"
    assert cfg_path.exists()

    # Save custom config
    cfg.pin = "9988"
    cfg.port = 8770
    save_config(cfg, cfg_path)

    reloaded = load_config(cfg_path)
    assert reloaded.pin == "9988"
    assert reloaded.port == 8770

def test_startup_idempotence():
    # Ensure clean starting state
    disable_startup()
    assert not is_startup_enabled()

    # Enable
    path = enable_startup()
    assert path.exists()
    assert is_startup_enabled()

    # Re-enable should not fail (idempotent)
    path2 = enable_startup()
    assert path2.exists()
    assert is_startup_enabled()

    # Disable
    assert disable_startup() is True
    assert not is_startup_enabled()

    # Second disable should be safe (idempotent)
    assert disable_startup() is False
    assert not is_startup_enabled()
