"""
ConKey Host Server for Windows.
Provides unified HTTP + WebSocket server, UDP auto-discovery, PIN pairing,
and keystroke dispatch via Win32 SendInput.
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
    """Responds to UDP broadcast discovery requests from mobile devices."""
    def __init__(self, http_port: int, pin: str, hostname: str):
        self.http_port = http_port
        self.pin = pin
        self.hostname = hostname
        self.transport: Optional[asyncio.DatagramTransport] = None

    def connection_made(self, transport: asyncio.BaseTransport):
        self.transport = transport  # type: ignore

    def datagram_received(self, data: bytes, addr):
        msg = data.decode("utf-8", errors="ignore").strip()
        if msg.startswith("CONKEY_DISCOVER"):
            reply = {
                "service": "conkey",
                "hostname": self.hostname,
                "port": self.http_port,
                "version": "1.0",
            }
            if self.transport:
                self.transport.sendto(json.dumps(reply).encode("utf-8"), addr)


class ConKeyServer:
    def __init__(
        self,
        port: int = 8765,
        discovery_port: int = 8766,
        pin: Optional[str] = None,
        static_dir: Optional[Path] = None,
        apk_path: Optional[Path] = None,
    ):
        self.port = port
        self.discovery_port = discovery_port
        self.pin = pin or f"{random.randint(1000, 9999)}"
        self.static_dir = static_dir or (Path(__file__).parent / "web")
        self.apk_path = apk_path or (Path(__file__).parent.parent / "conkey.apk")
        
        self.app = web.Application()
        self.sessions: Dict[web.WebSocketResponse, SessionState] = {}
        self.runner: Optional[web.AppRunner] = None
        self.discovery_transport: Optional[asyncio.DatagramTransport] = None

        self._setup_routes()

    def _setup_routes(self):
        self.app.router.add_get("/", self.handle_index)
        self.app.router.add_get("/ws", self.handle_ws)
        self.app.router.add_get("/api/info", self.handle_info)
        self.app.router.add_get("/download/conkey.apk", self.handle_download_apk)
        if self.static_dir.exists():
            self.app.router.add_static("/static/", path=str(self.static_dir), name="static")

    async def handle_index(self, request: web.Request) -> web.Response:
        index_file = self.static_dir / "index.html"
        if not index_file.exists():
            return web.Response(
                text=f"<h1>ConKey Server Running</h1><p>PIN: {self.pin}</p>",
                content_type="text/html"
            )
        content = index_file.read_text(encoding="utf-8")
        # Template replacements for seamless web client pairing
        content = content.replace("{{DEFAULT_PORT}}", str(self.port))
        content = content.replace("{{SERVER_PIN}}", self.pin)
        return web.Response(text=content, content_type="text/html")

    async def handle_info(self, request: web.Request) -> web.Response:
        return web.json_response({
            "service": "conkey",
            "hostname": socket.gethostname(),
            "port": self.port,
            "pin_required": True,
        })

    async def handle_download_apk(self, request: web.Request) -> web.StreamResponse:
        # Check standard APK locations
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
            # Send initial greeting asking for authentication
            await ws.send_json({
                "type": "auth_required",
                "message": "Enter PIN to control laptop",
            })

            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    await self._process_ws_message(ws, session, msg.data)
                elif msg.type == WSMsgType.ERROR:
                    logger.warning("WS error: %s", ws.exception())
                    break
        finally:
            # Clean up modifiers held down by this session to prevent stuck keys
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

        # Require auth for all operational commands
        if not session.authenticated:
            await ws.send_json({
                "type": "error",
                "message": "Authentication required. Send auth command first.",
            })
            return

        # Operational commands
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

    async def start(self):
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "0.0.0.0", self.port)
        await site.start()

        # Start UDP Discovery
        try:
            loop = asyncio.get_running_loop()
            transport, _ = await loop.create_datagram_endpoint(
                lambda: DiscoveryProtocol(self.port, self.pin, socket.gethostname()),
                local_addr=("0.0.0.0", self.discovery_port),
                allow_broadcast=True,
            )
            self.discovery_transport = transport
        except Exception as e:
            logger.warning("Could not bind UDP discovery port %d: %s", self.discovery_port, e)

        local_ip = get_local_ip()
        print("\n" + "=" * 54)
        print("          CONKEY LAPTOP RECEIVER ACTIVE")
        print("=" * 54)
        print(f"  Mobile Browser URL:  http://{local_ip}:{self.port}/")
        print(f"  Direct Web Auth:     http://{local_ip}:{self.port}/?pin={self.pin}")
        print(f"  Host IP for App:     {local_ip}:{self.port}")
        print(f"  Pairing PIN:         {self.pin}")
        print("=" * 54)
        print("  Tips for broken laptop keys:")
        print("  - Type 'A', 'S', '!' or any key directly from phone")
        print("  - Use phone hotkey buttons for Ctrl+C, Ctrl+V, etc.")
        print("  - Press Ctrl+C in terminal to stop server\n")

    async def stop(self):
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
