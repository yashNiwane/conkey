"""
ConKey Host Server for Windows.
Provides unified HTTP + WebSocket server, zero-conf UDP discovery beacons,
PIN pairing, and keystroke dispatch via Win32 SendInput.
"""

import asyncio
from dataclasses import asdict, dataclass
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
from host.phonon_engine import PhononSettings, PhononStream, PhononSupervisor
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
    MouseMoveAbsCommand,
    MouseTouchCommand,
    MouseClickCommand,
    MouseScrollCommand,
    PingCommand,
    VoiceStartCommand,
    VoiceStopCommand,
    VoiceCancelCommand,
    SessionState,
)
from host import keyboard_driver as win_keyboard
from host import screen_stream

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("conkey.server")


@dataclass
class ActiveVoice:
    """One authenticated client's live Phonon-2 transcription stream."""

    stream: Optional[PhononStream]
    started_at: float
    current_partial: str = ""
    lock: Optional[asyncio.Lock] = None

    def __post_init__(self):
        if self.lock is None:
            self.lock = asyncio.Lock()


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
        voice_enabled: Optional[bool] = None,
        phonon_model: Optional[str] = None,
        phonon_port: Optional[int] = None,
        phonon_threads: Optional[int] = None,
        phonon_command: Optional[str] = None,
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

        phonon_settings = PhononSettings.from_config(cfg)
        if phonon_model:
            phonon_settings.model = phonon_model
        if phonon_port is not None:
            phonon_settings.port = phonon_port
        if phonon_threads is not None:
            phonon_settings.threads = phonon_threads
        if phonon_command is not None:
            phonon_settings.command = phonon_command
        self.voice_enabled = cfg.voice_enabled if voice_enabled is None else bool(voice_enabled)
        self.phonon: Optional[PhononSupervisor] = (
            PhononSupervisor(phonon_settings) if self.voice_enabled else None
        )
        self._voices: Dict[web.WebSocketResponse, ActiveVoice] = {}
        self._voice_lock = asyncio.Lock()
        self._send_locks: Dict[web.WebSocketResponse, asyncio.Lock] = {}

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
            "voice": self.voice_enabled,
            "voice_model": self.phonon.settings.model if self.phonon else None,
        }

    def _setup_routes(self):
        self.app.router.add_get("/", self.handle_index)
        self.app.router.add_get("/ws", self.handle_ws)
        self.app.router.add_get("/api/info", self.handle_info)
        self.app.router.add_get("/api/device", self.handle_device)
        self.app.router.add_get("/api/voice/status", self.handle_voice_status)
        self.app.router.add_get("/api/screen_info", self.handle_screen_info)
        self.app.router.add_get("/api/screenshot", self.handle_screenshot)
        self.app.router.add_get("/stream.mjpg", self.handle_screen_stream)
        self.app.router.add_get("/download/conkey.apk", self.handle_download_apk)
        self.app.router.add_get("/download/conkey-windows.zip", self.handle_download_windows)
        self.app.router.add_get("/download/conkey-linux.tar.gz", self.handle_download_linux)
        self.app.router.add_get("/api/downloads", self.handle_downloads_list)
        if self.static_dir.exists():
            self.app.router.add_static("/static/", path=str(self.static_dir), name="static")

    async def _send_json(self, ws: web.WebSocketResponse, payload: dict) -> None:
        """Serializes writes so callbacks and command acks cannot interleave frames."""
        if ws.closed:
            return
        lock = self._send_locks.setdefault(ws, asyncio.Lock())
        async with lock:
            if ws.closed:
                return
            try:
                await ws.send_json(payload)
            except (ConnectionResetError, RuntimeError):
                pass

    async def handle_voice_status(self, request: web.Request) -> web.Response:
        if not self.voice_enabled or self.phonon is None:
            return web.json_response({
                "available": False,
                "ready": False,
                "model": None,
                "message": "Voice typing is disabled on this host.",
            })
        health = await self.phonon.health()
        return web.json_response({
            "available": True,
            "ready": bool(health),
            "model": (health or {}).get("model", self.phonon.settings.model),
            "port": self.phonon.settings.port,
            "stream_active": bool(self._voices),
            "error": self.phonon.last_error,
            "download_bytes": (health or {}).get("download_bytes"),
            "load_seconds": ((health or {}).get("decode") or {}).get("load_seconds"),
            "endpoints": (health or {}).get("endpoints", []),
        })

    async def handle_screen_info(self, request: web.Request) -> web.Response:
        w, h = screen_stream.get_screen_resolution()
        return web.json_response({
            "width": w,
            "height": h,
            "status": "ready"
        }, headers={"Access-Control-Allow-Origin": "*"})

    async def handle_screenshot(self, request: web.Request) -> web.Response:
        frame = screen_stream.capture_frame_jpeg(max_width=960, quality=70)
        if not frame:
            return web.Response(status=500, text="Could not capture screen")
        return web.Response(
            body=frame,
            content_type="image/jpeg",
            headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-cache"}
        )

    async def handle_screen_stream(self, request: web.Request) -> web.StreamResponse:
        response = web.StreamResponse(
            status=200,
            reason="OK",
            headers={
                "Content-Type": "multipart/x-mixed-replace; boundary=frame",
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
                "Access-Control-Allow-Origin": "*",
            }
        )
        await response.prepare(request)

        try:
            while True:
                frame = screen_stream.capture_frame_jpeg(max_width=960, quality=65)
                if frame:
                    await response.write(
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
                    )
                await asyncio.sleep(0.06)  # ~16 fps
        except (ConnectionResetError, asyncio.CancelledError):
            pass

        return response

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
            Path(__file__).parent.parent / "downloads" / "conkey.apk",
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

    async def handle_download_windows(self, request: web.Request) -> web.StreamResponse:
        candidates = [
            Path(__file__).parent.parent / "downloads" / "conkey-windows.zip",
            Path(__file__).parent.parent / "conkey-windows.zip",
            Path(__file__).parent / "conkey-windows.zip",
        ]
        target = next((c for c in candidates if c and c.exists()), None)
        if not target:
            return web.Response(status=404, text="Windows package not found yet.")
        return web.FileResponse(
            target,
            headers={
                "Content-Disposition": 'attachment; filename="conkey-windows.zip"',
                "Content-Type": "application/zip",
            }
        )

    async def handle_download_linux(self, request: web.Request) -> web.StreamResponse:
        candidates = [
            Path(__file__).parent.parent / "downloads" / "conkey-linux.tar.gz",
            Path(__file__).parent.parent / "conkey-linux.tar.gz",
            Path(__file__).parent / "conkey-linux.tar.gz",
        ]
        target = next((c for c in candidates if c and c.exists()), None)
        if not target:
            return web.Response(status=404, text="Linux package not found yet.")
        return web.FileResponse(
            target,
            headers={
                "Content-Disposition": 'attachment; filename="conkey-linux.tar.gz"',
                "Content-Type": "application/gzip",
            }
        )

    async def handle_downloads_list(self, request: web.Request) -> web.Response:
        root = Path(__file__).parent.parent
        items = [
            {
                "platform": "android",
                "label": "Android App (APK)",
                "filename": "conkey.apk",
                "url": "/download/conkey.apk",
                "available": (root / "conkey.apk").exists() or (root / "downloads" / "conkey.apk").exists(),
                "size": (root / "conkey.apk").stat().st_size if (root / "conkey.apk").exists() else 0,
            },
            {
                "platform": "windows",
                "label": "Windows Desktop (ZIP)",
                "filename": "conkey-windows.zip",
                "url": "/download/conkey-windows.zip",
                "available": (root / "downloads" / "conkey-windows.zip").exists() or (root / "conkey-windows.zip").exists(),
                "size": (root / "downloads" / "conkey-windows.zip").stat().st_size if (root / "downloads" / "conkey-windows.zip").exists() else 0,
            },
            {
                "platform": "linux",
                "label": "Linux Desktop (TAR.GZ)",
                "filename": "conkey-linux.tar.gz",
                "url": "/download/conkey-linux.tar.gz",
                "available": (root / "downloads" / "conkey-linux.tar.gz").exists() or (root / "conkey-linux.tar.gz").exists(),
                "size": (root / "downloads" / "conkey-linux.tar.gz").stat().st_size if (root / "downloads" / "conkey-linux.tar.gz").exists() else 0,
            },
        ]
        return web.json_response({"downloads": items})

    async def handle_ws(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(heartbeat=15.0, max_msg_size=16 * 1024 * 1024)
        await ws.prepare(request)

        session = SessionState()
        self.sessions[ws] = session
        logger.info("New client connected from %s", request.remote)

        try:
            await self._send_json(ws, {
                "type": "auth_required",
                "device_name": self.device_name,
                "message": "Enter PIN to control laptop",
                "voice": self.voice_enabled,
                "voice_model": self.phonon.settings.model if self.phonon else None,
            })

            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    await self._process_ws_message(ws, session, msg.data)
                elif msg.type == WSMsgType.BINARY:
                    await self._handle_voice_audio(ws, msg.data)
                elif msg.type == WSMsgType.ERROR:
                    logger.warning("WS error: %s", ws.exception())
                    break
        finally:
            await self._stop_voice(ws, cancel=True)
            self._send_locks.pop(ws, None)
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
            await self._send_json(ws, {"type": "error", "message": str(err)})
            return

        # Handle Auth
        if isinstance(cmd, AuthCommand):
            if session.is_locked_out():
                remaining = int(session.lockout_until - time.time())
                await self._send_json(ws, {
                    "type": "auth_result",
                    "success": False,
                    "message": f"Too many failed attempts. Locked out for {remaining}s.",
                })
                return

            if session.authenticate(cmd.pin, self.pin):
                logger.info("Client authenticated successfully")
                await self._send_json(ws, {
                    "type": "auth_result",
                    "success": True,
                    "device_name": self.device_name,
                    "message": "Authenticated. Control active.",
                })
            else:
                logger.warning("Authentication failed (attempt %d)", session.failed_attempts)
                await self._send_json(ws, {
                    "type": "auth_result",
                    "success": False,
                    "message": "Invalid PIN",
                })
            return

        if not session.authenticated:
            await self._send_json(ws, {
                "type": "error",
                "message": "Authentication required. Send auth command first.",
            })
            return

        if isinstance(cmd, VoiceStartCommand):
            await self._handle_voice_start(ws, cmd)
            return
        if isinstance(cmd, VoiceStopCommand):
            await self._handle_voice_stop(ws)
            return
        if isinstance(cmd, VoiceCancelCommand):
            await self._stop_voice(ws, cancel=True)
            return

        # Operational commands
        logger.info("Executing cmd: %s (%s)", type(cmd).__name__, getattr(cmd, 'key', getattr(cmd, 'text', getattr(cmd, 'button', ''))))
        if isinstance(cmd, TypeTextCommand):
            win_keyboard.type_text(cmd.text, cmd.delay)
            await self._send_json(ws, {"type": "ack", "action": "type_text", "length": len(cmd.text)})

        elif isinstance(cmd, KeyPressCommand):
            win_keyboard.press_key(cmd.key, cmd.delay)
            await self._send_json(ws, {"type": "ack", "action": "key_press", "key": cmd.key})

        elif isinstance(cmd, KeyDownCommand):
            win_keyboard.key_down(cmd.key)
            session.active_modifiers.add(cmd.key.upper())
            await self._send_json(ws, {"type": "ack", "action": "key_down", "key": cmd.key})

        elif isinstance(cmd, KeyUpCommand):
            win_keyboard.key_up(cmd.key)
            session.active_modifiers.discard(cmd.key.upper())
            await self._send_json(ws, {"type": "ack", "action": "key_up", "key": cmd.key})

        elif isinstance(cmd, KeyComboCommand):
            win_keyboard.key_combo(cmd.modifiers, cmd.key, cmd.delay)
            await self._send_json(ws, {"type": "ack", "action": "key_combo", "modifiers": cmd.modifiers, "key": cmd.key})

        elif isinstance(cmd, MouseMoveCommand):
            win_keyboard.mouse_move(cmd.dx, cmd.dy)

        elif isinstance(cmd, MouseMoveAbsCommand):
            win_keyboard.mouse_move_abs(cmd.x, cmd.y)

        elif isinstance(cmd, MouseTouchCommand):
            win_keyboard.mouse_move_abs(cmd.x, cmd.y)
            if cmd.click:
                win_keyboard.mouse_click("left")

        elif isinstance(cmd, MouseClickCommand):
            win_keyboard.mouse_click(cmd.button)

        elif isinstance(cmd, MouseScrollCommand):
            win_keyboard.mouse_scroll(cmd.dy)

        elif isinstance(cmd, PingCommand):
            await self._send_json(ws, {
                "type": "pong",
                "client_time": cmd.client_time,
                "server_time": time.time(),
            })

    # ------------------------------------------------------------------ voice
    async def _handle_voice_start(self, ws: web.WebSocketResponse, cmd: VoiceStartCommand) -> None:
        if not self.voice_enabled or self.phonon is None:
            await self._send_json(ws, {
                "type": "voice_error",
                "message": "Voice typing is disabled on this host. Start the host without --no-voice.",
            })
            return

        async with self._voice_lock:
            if self._voices:
                await self._send_json(ws, {
                    "type": "voice_error",
                    "message": "Voice typing is already active. Stop it on the other device first.",
                })
                return

            await self._send_json(ws, {
                "type": "voice_loading",
                "message": "Loading Phonon-2 on the laptop...",
            })

            try:
                health = await self.phonon.ensure_ready()
                if ws.closed:
                    return

                voice = self._make_voice(ws, cmd.audio_format)
                await voice.stream.start()
            except Exception as exc:
                logger.warning("Voice session could not start: %s", exc)
                await self._send_json(ws, {"type": "voice_error", "message": str(exc)})
                return

            self._voices[ws] = voice
            logger.info("Live voice typing stream started (format=%s)", cmd.audio_format)
            await self._send_json(ws, {
                "type": "voice_ready",
                "model": health.get("model", self.phonon.settings.model),
                "profile": health.get("profile"),
                "sample_rate": cmd.sample_rate,
                "format": cmd.audio_format,
                "streaming": True,
            })

    def _make_voice(
        self,
        ws: web.WebSocketResponse,
        audio_format: str,
    ) -> ActiveVoice:
        voice = ActiveVoice(
            stream=None,
            started_at=time.time(),
            current_partial="",
        )

        async def on_partial(text: str) -> None:
            async with voice.lock:
                prev = voice.current_partial
                curr = text
                if curr != prev:
                    await asyncio.to_thread(win_keyboard.sync_live_text, prev, curr)
                    voice.current_partial = curr
            await self._send_json(ws, {"type": "voice_partial", "text": text})

        async def on_final(text: str, segment: int) -> None:
            async with voice.lock:
                prev = voice.current_partial
                curr = f"{text} " if text and not text.endswith(" ") else text
                if curr != prev:
                    await asyncio.to_thread(win_keyboard.sync_live_text, prev, curr)
                voice.current_partial = ""
            await self._send_json(ws, {
                "type": "voice_final",
                "text": text,
                "segment": segment,
                "typed": True,
            })

        async def on_done(text: str) -> None:
            async with voice.lock:
                if voice.current_partial:
                    final_text = f"{voice.current_partial} "
                    await asyncio.to_thread(win_keyboard.sync_live_text, voice.current_partial, final_text)
                    voice.current_partial = ""
            await self._send_json(ws, {
                "type": "voice_done",
                "text": text,
            })

        async def on_error(message: str) -> None:
            async with voice.lock:
                voice.current_partial = ""
            await self._send_json(ws, {"type": "voice_error", "message": message})

        stream = PhononStream(
            self.phonon,
            audio_format=audio_format,
            on_partial=on_partial,
            on_final=on_final,
            on_done=on_done,
            on_error=on_error,
        )
        voice.stream = stream
        return voice

    async def _handle_voice_stop(self, ws: web.WebSocketResponse) -> None:
        voice = self._voices.get(ws)
        if voice is None:
            await self._send_json(ws, {
                "type": "voice_done",
                "text": "",
            })
            return

        try:
            await voice.stream.end()
        except Exception as exc:
            logger.warning("Voice stream finish failed: %s", exc)
            if not voice.stream.error:
                await self._send_json(ws, {"type": "voice_error", "message": str(exc)})
        finally:
            self._voices.pop(ws, None)
            await voice.stream.cancel()

    async def _stop_voice(self, ws: web.WebSocketResponse, *, cancel: bool) -> None:
        voice = self._voices.pop(ws, None)
        if voice is None:
            return
        try:
            if cancel:
                await voice.stream.cancel()
            else:
                await voice.stream.end()
        except Exception as exc:
            logger.debug("Voice stream cleanup: %s", exc)
        finally:
            await voice.stream.cancel()

    async def _handle_voice_audio(self, ws: web.WebSocketResponse, pcm: bytes) -> None:
        voice = self._voices.get(ws)
        if voice is None:
            # Stray binary before voice_start or after voice_stop: ignore.
            return
        try:
            await voice.stream.feed(pcm)
        except Exception as exc:
            logger.warning("Voice audio feed failed: %s", exc)
            self._voices.pop(ws, None)
            await voice.stream.cancel()
            await self._send_json(ws, {"type": "voice_error", "message": str(exc)})

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
        if self.voice_enabled and self.phonon:
            print(
                f"  Voice Typing:        {self.phonon.settings.model} "
                f"(streaming on 127.0.0.1:{self.phonon.settings.port})"
            )
        else:
            print("  Voice Typing:        disabled")
        print("=" * 58)
        print("  - Bluetooth direct connection active (Pair & Play)")
        print("  - Local Wi-Fi discovery beacon active")
        if self.voice_enabled:
            print("  - Phonon-2 voice typing loads on first use (Wi-Fi clients)")
        print("  - Press Ctrl+C in terminal to stop server\n")

    async def stop(self):
        self.bt_server.stop()
        if self._beacon_task:
            self._beacon_task.cancel()
        if self.discovery_transport:
            self.discovery_transport.close()
        for ws in list(self._voices.keys()):
            await self._stop_voice(ws, cancel=True)
        for ws in list(self.sessions.keys()):
            await ws.close()
        if self.phonon:
            await self.phonon.stop()
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
