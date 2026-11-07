"""
Windows Startup Management for ConKey.
Registers ConKey as a user-level Windows startup program using pythonw.exe
so it runs silently in the background whenever the laptop boots up.
Follows principle-make-operations-idempotent.
"""

import argparse
import logging
import os
from pathlib import Path
import sys
import win32com.client
import winreg

logger = logging.getLogger("conkey.startup")

SHORTCUT_NAME = "ConKey.lnk"
REG_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def get_startup_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise RuntimeError("APPDATA environment variable not found")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def get_shortcut_path() -> Path:
    return get_startup_dir() / SHORTCUT_NAME


def is_startup_enabled() -> bool:
    shortcut_exists = get_shortcut_path().exists()
    reg_exists = False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_RUN_KEY, 0, winreg.KEY_READ) as key:
            val, _ = winreg.QueryValueEx(key, "ConKey")
            reg_exists = bool(val)
    except FileNotFoundError:
        reg_exists = False
    return shortcut_exists or reg_exists


def enable_startup(project_root: Path = None) -> Path:
    """
    Idempotently registers ConKey in both Windows Startup Folder and HKCU Run Registry.
    Guarantees silent background execution on every Windows boot/logon.
    """
    root = (project_root or Path(__file__).parent.parent).resolve()
    shortcut_path = get_shortcut_path()

    python_dir = Path(sys.executable).parent
    pythonw = python_dir / "pythonw.exe"
    if not pythonw.exists():
        pythonw = Path(sys.executable)

    run_script = root / "host" / "run_host.py"
    if not run_script.exists():
        raise FileNotFoundError(f"Host script not found at {run_script}")

    # 1. Create or update Windows Startup folder shortcut
    try:
        ws = win32com.client.Dispatch("WScript.Shell")
        shortcut = ws.CreateShortcut(str(shortcut_path))
        shortcut.TargetPath = str(pythonw)
        shortcut.Arguments = f'"{run_script}"'
        shortcut.WorkingDirectory = str(root)
        shortcut.Description = "ConKey Remote Keyboard Background Service"
        shortcut.Save()
    except Exception as e:
        logger.warning("Could not create Startup shortcut: %s", e)

    # 2. Register in Windows HKCU Run Registry key for maximum reliability on Windows 11
    cmd_str = f'"{pythonw}" "{run_script}"'
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "ConKey", 0, winreg.REG_SZ, cmd_str)
    except Exception as e:
        logger.warning("Could not write HKCU Run registry: %s", e)

    return shortcut_path


def disable_startup() -> bool:
    """
    Idempotently removes ConKey from Windows Startup folder and Registry.
    """
    removed = False
    shortcut_path = get_shortcut_path()
    if shortcut_path.exists():
        shortcut_path.unlink()
        removed = True

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, "ConKey")
            removed = True
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.warning("Could not remove HKCU Run registry value: %s", e)

    return removed


def main():
    parser = argparse.ArgumentParser(description="Manage ConKey Windows Startup")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--enable", action="store_true", help="Enable ConKey on Windows startup")
    group.add_argument("--disable", action="store_true", help="Disable ConKey on Windows startup")
    group.add_argument("--status", action="store_true", help="Check if ConKey startup is enabled")
    args = parser.parse_args()

    if args.status:
        enabled = is_startup_enabled()
        print(f"ConKey startup status: {'ENABLED' if enabled else 'DISABLED'}")
        if enabled:
            print(f"Shortcut: {get_shortcut_path()}")
    elif args.enable:
        path = enable_startup()
        print(f"ConKey successfully registered in Windows Startup:")
        print(f"Location: {path}")
    elif args.disable:
        removed = disable_startup()
        if removed:
            print("ConKey removed from Windows Startup.")
        else:
            print("ConKey was not registered in Windows Startup.")


if __name__ == "__main__":
    main()
