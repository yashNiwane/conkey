"""
Windows Startup Management for ConKey.
Registers ConKey as a user-level Windows startup program using pythonw.exe
so it runs silently in the background whenever the laptop boots up.
Follows principle-make-operations-idempotent.
"""

import argparse
import os
from pathlib import Path
import sys
import win32com.client

SHORTCUT_NAME = "ConKey.lnk"


def get_startup_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise RuntimeError("APPDATA environment variable not found")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def get_shortcut_path() -> Path:
    return get_startup_dir() / SHORTCUT_NAME


def is_startup_enabled() -> bool:
    return get_shortcut_path().exists()


def enable_startup(project_root: Path = None) -> Path:
    """
    Idempotently creates or updates the Windows Startup shortcut pointing to pythonw.exe.
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

    ws = win32com.client.Dispatch("WScript.Shell")
    shortcut = ws.CreateShortcut(str(shortcut_path))
    shortcut.TargetPath = str(pythonw)
    shortcut.Arguments = f'"{run_script}"'
    shortcut.WorkingDirectory = str(root)
    shortcut.Description = "ConKey Remote Keyboard Background Service"
    shortcut.Save()

    return shortcut_path


def disable_startup() -> bool:
    """
    Idempotently removes the Windows Startup shortcut if it exists.
    """
    shortcut_path = get_shortcut_path()
    if shortcut_path.exists():
        shortcut_path.unlink()
        return True
    return False


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
