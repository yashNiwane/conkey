"""
ConKey Host Launcher
Runs the background keyboard receiver. Can run in console or headless via pythonw.
Follows principle-make-operations-idempotent and principle-boundary-discipline.
"""

import argparse
import asyncio
import logging
import socket
import sys
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from host.config import load_config
from host.server import ConKeyServer

logger = logging.getLogger("conkey.launcher")


def is_port_in_use(port: int) -> bool:
    """Checks whether the server port is already bound by another instance."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


async def run_server(server: ConKeyServer):
    await server.start()
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        await server.stop()


def main():
    parser = argparse.ArgumentParser(description="ConKey Laptop Keyboard Remote Host")
    parser.add_argument("--port", type=int, default=None, help="HTTP/WebSocket port")
    parser.add_argument("--discovery-port", type=int, default=None, help="UDP discovery port")
    parser.add_argument("--pin", type=str, default=None, help="Pairing PIN")
    parser.add_argument(
        "--no-voice",
        action="store_true",
        help="Disable Phonon-2 streaming voice typing",
    )
    parser.add_argument(
        "--phonon-port",
        type=int,
        default=None,
        help="Local port for the Phonon speech server (default 8010)",
    )
    parser.add_argument(
        "--phonon-model",
        type=str,
        default=None,
        help="Phonon model name (default phonon-2)",
    )
    parser.add_argument(
        "--phonon-threads",
        type=int,
        default=None,
        help="CPU threads for Phonon (0 = auto)",
    )
    parser.add_argument(
        "--phonon-command",
        type=str,
        default=None,
        help="Path to the fermion executable if it is not on PATH",
    )
    args = parser.parse_args()

    # Load persistent config
    cfg = load_config()

    port = args.port or cfg.port
    discovery_port = args.discovery_port or cfg.discovery_port
    pin = args.pin or cfg.pin

    # Single-instance guard
    if is_port_in_use(port):
        print(f"ConKey is already running on port {port}. Exiting cleanly.")
        return

    server = ConKeyServer(
        port=port,
        discovery_port=discovery_port,
        pin=pin,
        voice_enabled=False if args.no_voice else None,
        phonon_port=args.phonon_port,
        phonon_model=args.phonon_model,
        phonon_threads=args.phonon_threads,
        phonon_command=args.phonon_command,
    )

    try:
        asyncio.run(run_server(server))
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\nStopping ConKey host...")


if __name__ == "__main__":
    main()
