"""
ConKey Host Server for Windows.
Provides unified HTTP + WebSocket server, zero-conf UDP discovery beacons,
PIN pairing, and keystroke dispatch via Win32 SendInput.
"""

import asyncio
from dataclasses import asdict
import json
import logging
import os
from pathlib import Path
import random
import socket
import sys
import time
from typing import Dict, Optional, Set

from aiohttp import web, WSMsgType

from host.config import load_config
from host.bt_server import BluetoothServer
from host.protocol import (
    parse_command,
    ProtocolError,
    AuthCommand,
    TypeTextCommand,
    KeyPressCommand,
    KeyDownCommand,
    KeyUpCommand,
    KeyComboCommand,
    MouseMoveCommand,
    MouseClickCommand,
    MouseScrollCommand,
    PingCommand,
    SessionState,
)
from host import win_keyboard

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("conkey.server")


def get_local_ip() -> str:
    """Discovers the primary local LAN IP address."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


class DiscoveryProtocol(asyncio.DatagramProtocol):
    """Responds to UDP broadcast discovery requests and sends periodic beacons."""
    def __init__(self, server: "ConKeyServer"):
        self.server = server
        self.transport: Optional[asyncio.DatagramTransport] = None

    def connection_made(self, transport: asyncio.BaseTransport):
        self.transport = transport  # type: ignore

    def datagram_received(self, data: bytes, addr):
        msg = data.decode("utf-8", errors="ignore").strip()
        if msg.startswith("CONKEY_DISCOVER"):
            reply = self.server.get_device_card()
            if self.transport:
                self.transport.sendto(json.dumps(reply).encode("utf-8"), addr)


class ConKeyServer:
    def __init__(
        self,
        port: int = 8765,
        discovery_port: int = 8766,
        pin: Optional[str] = None,
        device_name: Optional[str] = None,
        device_id: Optional[str] = None,
        static_dir: Optional[Path] = None,
        apk_path: Optional[Path] = None,
    ):
        cfg = load_config()
        self.port = port or cfg.port
        self.discovery_port = discovery_port or cfg.discovery_port
        self.pin = pin or cfg.pin
        self.device_name = device_name or cfg.device_name
        self.device_id = device_id or cfg.device_id
        self.hostname = socket.gethostname()
        self.static_dir = static_dir or (Path(__file__).parent / "web")
        self.apk_path = apk_path or (Path(__file__).parent.parent / "conkey.apk")
        
        self.app = web.Application()
        self.sessions: Dict[web.WebSocketResponse, SessionState] = {}
        self.runner: Optional[web.AppRunner] = None
        self.discovery_transport: Optional[asyncio.DatagramTransport] = None
        self._beacon_task: Optional[asyncio.Task] = None
        self.bt_server = BluetoothServer(channel=4)

        self._setup_routes()

    def get_device_card(self) -> dict:
        return {
            "service": "conkey",
            "device_id": self.device_id,
            "name": self.device_name,
            "hostname": self.hostname,
            "ip": get_local_ip(),
            "port": self.port,
            "pin": self.pin,
            "version": "2.0",
        }

    def _setup_routes(self):
        self.app.router.add_get("/", self.handle_index)
        self.app.router.add_get("/ws", self.handle_ws)
        self.app.router.add_get("/api/info", self.handle_info)
        self.app.router.add_get("/api/device", self.handle_device)
        self.app.router.add_get("/download/conkey.apk", self.handle_download_apk)
        if self.static_dir.exists():
            self.app.router.add_static("/static/", path=str(self.static_dir), name="static")

    async def handle_index(self, request: web.Request) -> web.Response:
        index_file = self.static_dir / "index.html"
        if not index_file.exists():
            return web.Response(
                text=f"<h1>ConKey Server Running</h1><p>Device: {self.device_name}</p><p>PIN: {self.pin}</p>",
                content_type="text/html"
            )
        content = index_file.read_text(encoding="utf-8")
        content = content.replace("{{DEFAULT_PORT}}", str(self.port))
        content = content.replace("{{SERVER_PIN}}", self.pin)
        content = content.replace("{{DEVICE_NAME}}", self.device_name)
        return web.Response(text=content, content_type="text/html")

    async def handle_info(self, request: web.Request) -> web.Response:
        return web.json_response(self.get_device_card())

    async def handle_device(self, request: web.Request) -> web.Response:
        return web.json_response(self.get_device_card())

    async def handle_download_apk(self, request: web.Request) -> web.StreamResponse:
        candidates = [
            self.apk_path,
            Path(__file__).parent.parent / "conkey.apk",
            Path(__file__).parent.parent / "android" / "app" / "build" / "outputs" / "apk" / "debug" / "app-debug.apk",
            Path(__file__).parent.parent / "android" / "app" / "build" / "outputs" / "apk" / "release" / "app-release.apk",
        ]
        target = next((c for c in candidates if c and c.exists()), None)
        if not target:
            return web.Response(status=404, text="APK file not found yet. Please compile with Gradle first.")
        return web.FileResponse(
            target,
            headers={
                "Content-Disposition": 'attachment; filename="conkey.apk"',
                "Content-Type": "application/vnd.android.package-archive",
            }
        )

    async def handle_ws(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(heartbeat=15.0)
        await ws.prepare(request)

        session = SessionState()
        self.sessions[ws] = session
        logger.info("New client connected from %s", request.remote)

        try:
            await ws.send_json({
                "type": "auth_required",
                "device_name": self.device_name,
                "message": "Enter PIN to control laptop",
            })

            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    await self._process_ws_message(ws, session, msg.data)
                elif msg.type == WSMsgType.ERROR:
                    logger.warning("WS error: %s", ws.exception())
                    break
        finally:
            for mod in list(session.active_modifiers):
                try:
                    win_keyboard.key_up(mod)
                except Exception:
                    pass
            self.sessions.pop(ws, None)
            logger.info("Client disconnected from %s", request.remote)

        return ws

    async def _process_ws_message(self, ws: web.WebSocketResponse, session: SessionState, raw_text: str):
        try:
            cmd = parse_command(raw_text)
        except ProtocolError as err:
            await ws.send_json({"type": "error", "message": str(err)})
            return

        # Handle Auth
        if isinstance(cmd, AuthCommand):
            if session.is_locked_out():
                remaining = int(session.lockout_until - time.time())
                await ws.send_json({
                    "type": "auth_result",
                    "success": False,
                    "message": f"Too many failed attempts. Locked out for {remaining}s.",
                })
                return

            if session.authenticate(cmd.pin, self.pin):
                logger.info("Client authenticated successfully")
                await ws.send_json({
                    "type": "auth_result",
                    "success": True,
                    "device_name": self.device_name,
                    "message": "Authenticated. Control active.",
                })
            else:
                logger.warning("Authentication failed (attempt %d)", session.failed_attempts)
                await ws.send_json({
                    "type": "auth_result",
                    "success": False,
                    "message": "Invalid PIN",
                })
            return

        if not session.authenticated:
            await ws.send_json({
                "type": "error",
                "message": "Authentication required. Send auth command first.",
            })
            return

        # Operational commands
        logger.info("Executing cmd: %s (%s)", type(cmd).__name__, getattr(cmd, 'key', getattr(cmd, 'text', getattr(cmd, 'button', ''))))
        if isinstance(cmd, TypeTextCommand):
            win_keyboard.type_text(cmd.text, cmd.delay)
            await ws.send_json({"type": "ack", "action": "type_text", "length": len(cmd.text)})

        elif isinstance(cmd, KeyPressCommand):
            win_keyboard.press_key(cmd.key, cmd.delay)
            await ws.send_json({"type": "ack", "action": "key_press", "key": cmd.key})

        elif isinstance(cmd, KeyDownCommand):
            win_keyboard.key_down(cmd.key)
            session.active_modifiers.add(cmd.key.upper())
            await ws.send_json({"type": "ack", "action": "key_down", "key": cmd.key})

        elif isinstance(cmd, KeyUpCommand):
            win_keyboard.key_up(cmd.key)
            session.active_modifiers.discard(cmd.key.upper())
            await ws.send_json({"type": "ack", "action": "key_up", "key": cmd.key})

        elif isinstance(cmd, KeyComboCommand):
            win_keyboard.key_combo(cmd.modifiers, cmd.key, cmd.delay)
            await ws.send_json({"type": "ack", "action": "key_combo", "modifiers": cmd.modifiers, "key": cmd.key})

        elif isinstance(cmd, MouseMoveCommand):
            win_keyboard.mouse_move(cmd.dx, cmd.dy)

        elif isinstance(cmd, MouseClickCommand):
            win_keyboard.mouse_click(cmd.button)

        elif isinstance(cmd, MouseScrollCommand):
            win_keyboard.mouse_scroll(cmd.dy)

        elif isinstance(cmd, PingCommand):
            await ws.send_json({
                "type": "pong",
                "client_time": cmd.client_time,
                "server_time": time.time(),
            })

    async def _run_beacon_loop(self):
        """Periodically broadcasts UDP beacon so mobile apps detect laptop instantly."""
        beacon_data = json.dumps(self.get_device_card()).encode("utf-8")
        broadcast_addr = ("255.255.255.255", self.discovery_port)

        while True:
            try:
                if self.discovery_transport and not self.discovery_transport.is_closing():
                    self.discovery_transport.sendto(beacon_data, broadcast_addr)
            except Exception as e:
                pass
            await asyncio.sleep(2.5)

    async def start(self):
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "0.0.0.0", self.port)
        await site.start()

        # Start UDP Discovery Listener & Beacon
        try:
            loop = asyncio.get_running_loop()
            transport, _ = await loop.create_datagram_endpoint(
                lambda: DiscoveryProtocol(self),
                local_addr=("0.0.0.0", self.discovery_port),
                allow_broadcast=True,
            )
            self.discovery_transport = transport
            self._beacon_task = asyncio.create_task(self._run_beacon_loop())
        except Exception as e:
            logger.warning("Could not bind UDP discovery port %d: %s", self.discovery_port, e)

        # Start Bluetooth Server
        try:
            self.bt_server.start()
        except Exception as e:
            logger.warning("Could not start Bluetooth server: %s", e)

        local_ip = get_local_ip()
        print("\n" + "=" * 58)
        print(f"       CONKEY LAPTOP RECEIVER: {self.device_name}")
        print("=" * 58)
        print(f"  Bluetooth Ready:     MAC {self.bt_server.mac} (Channel {self.bt_server.channel})")
        print(f"  Mobile Browser URL:  http://{local_ip}:{self.port}/")
        print(f"  Direct Web Auth:     http://{local_ip}:{self.port}/?pin={self.pin}")
        print(f"  Host IP for App:     {local_ip}:{self.port}")
        print(f"  Device Name:         {self.device_name}")
        print(f"  Pairing PIN:         {self.pin}")
        print("=" * 58)
        print("  - Bluetooth direct connection active (Pair & Play)")
        print("  - Local Wi-Fi discovery beacon active")
        print("  - Press Ctrl+C in terminal to stop server\n")

    async def stop(self):
        self.bt_server.stop()
        if self._beacon_task:
            self._beacon_task.cancel()
        if self.discovery_transport:
            self.discovery_transport.close()
        for ws in list(self.sessions.keys()):
            await ws.close()
        if self.runner:
            await self.runner.cleanup()
        logger.info("ConKey Server stopped.")


async def main():
    pin = sys.argv[1] if len(sys.argv) > 1 else None
    server = ConKeyServer(pin=pin)
    await server.start()
    try:
        while True:
            await asyncio.sleep(3600)
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass
    finally:
        await server.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
