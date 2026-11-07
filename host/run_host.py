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


def main():
    parser = argparse.ArgumentParser(description="ConKey Laptop Keyboard Remote Host")
    parser.add_argument("--port", type=int, default=None, help="HTTP/WebSocket port")
    parser.add_argument("--discovery-port", type=int, default=None, help="UDP discovery port")
    parser.add_argument("--pin", type=str, default=None, help="Pairing PIN")
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

    server = ConKeyServer(port=port, discovery_port=discovery_port, pin=pin)

    try:
        asyncio.run(server.start())
        # Keep alive until cancelled
        asyncio.run(asyncio.Event().wait())
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\nStopping ConKey host...")
        asyncio.run(server.stop())


if __name__ == "__main__":
    main()
