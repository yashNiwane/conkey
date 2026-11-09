"""
One-time setup and verification for ConKey's Phonon-2 voice engine.

Downloads the ~158 MB Phonon-2 weights (cached under the user profile),
prints the CPU kernel tier Fermion selected, and optionally starts the
local speech server once to prove it answers /health.

Usage:
    python host/voice_setup.py
    python host/voice_setup.py --verify --port 8010
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from host.phonon_engine import (  # noqa: E402
    DEFAULT_PORT,
    PhononSettings,
    PhononSupervisor,
    find_fermion_command,
)


def run_step(argv: list[str]) -> int:
    print("+ " + " ".join(argv), flush=True)
    return subprocess.call(argv)


async def verify(port: int, model: str) -> bool:
    settings = PhononSettings(model=model, port=port, startup_timeout=150.0)
    supervisor = PhononSupervisor(settings)
    try:
        health = await supervisor.ensure_ready()
        decode = health.get("decode", {})
        print("\nVerified:")
        print(f"  model:      {health.get('model')}")
        print(f"  profile:    {health.get('profile')}")
        print(f"  runtime:    {decode.get('runtime', health.get('kind'))}")
        print(f"  threads:    {decode.get('threads', 'auto')}")
        print(f"  load time:  {decode.get('load_seconds', '?')} s")
        print(f"  endpoints:  {', '.join(health.get('endpoints', []))}")
        return True
    except Exception as exc:
        print(f"\nVerification failed: {exc}", file=sys.stderr)
        return False
    finally:
        await supervisor.stop()


def main() -> int:
    parser = argparse.ArgumentParser(description="Set up Phonon-2 voice typing for ConKey")
    parser.add_argument("--model", default="phonon-2", help="Phonon model name")
    parser.add_argument(
        "--fermion",
        default="",
        help="Path to the fermion executable if it is not on PATH",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"Temporary/local speech server port (default {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Only check the installation (the model is already cached)",
    )
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="Do not start the model server for a health check",
    )
    args = parser.parse_args()

    command = find_fermion_command(args.fermion)
    if not command:
        print(
            "The Phonon speech engine is not installed.\n"
            "Run:\n"
            "  python -m pip install --user fermion-research\n"
            "then run this script again.",
            file=sys.stderr,
        )
        return 1

    print(f"Fermion command: {' '.join(command)}")
    describe = run_step(command + ["describe"])
    if describe != 0:
        print("`fermion describe` failed; the CPU runtime is not usable.", file=sys.stderr)
        return describe

    if not args.skip_download:
        code = run_step(command + ["transcribe", args.model, "--download-only"])
        if code != 0:
            print(
                "Model download failed. Check the network connection and retry.",
                file=sys.stderr,
            )
            return code

    if not args.no_verify:
        if not asyncio.run(verify(args.port, args.model)):
            return 1

    print(
        "\nPhonon-2 is ready. Start ConKey with `start_conkey.bat` (or "
        "`python host/run_host.py`) and use the microphone button in the "
        "typing bar from the ConKey Android app over Wi-Fi."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
