"""
ConKey Host Launcher
Run this script on the laptop to start receiving remote keyboard input.
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from host.server import ConKeyServer


def main():
    parser = argparse.ArgumentParser(description="ConKey Laptop Keyboard Remote Host")
    parser.add_argument("--port", type=int, default=8765, help="HTTP/WebSocket port (default: 8765)")
    parser.add_argument("--discovery-port", type=int, default=8766, help="UDP discovery port (default: 8766)")
    parser.add_argument("--pin", type=str, default=None, help="4-digit pairing PIN (default: auto-generated)")
    args = parser.parse_args()

    server = ConKeyServer(port=args.port, discovery_port=args.discovery_port, pin=args.pin)

    try:
        asyncio.run(server.start())
        # Keep alive
        asyncio.run(asyncio.Event().wait())
    except KeyboardInterrupt:
        print("\nStopping ConKey host...")
        asyncio.run(server.stop())


if __name__ == "__main__":
    main()
