"""
ConKey Bluetooth RFCOMM Server for Windows.
Listens for Bluetooth SPP / RFCOMM connections from the Android app,
providing zero-router, pair-and-play keyboard control.
"""

import json
import logging
import socket
import threading
import time
from typing import Callable, Optional

import psutil

from host import win_keyboard
from host.protocol import (
    parse_command,
    ProtocolError,
    TypeTextCommand,
    KeyPressCommand,
    KeyDownCommand,
    KeyUpCommand,
    KeyComboCommand,
    MouseMoveCommand,
    MouseClickCommand,
    MouseScrollCommand,
)

logger = logging.getLogger("conkey.bluetooth")

DEFAULT_RFCOMM_CHANNEL = 4


def get_local_bluetooth_mac() -> str:
    """Finds the local Bluetooth adapter MAC address."""
    for name, addrs in psutil.net_if_addrs().items():
        if "bluetooth" in name.lower() or "bth" in name.lower():
            for addr in addrs:
                if addr.family == psutil.AF_LINK and addr.address:
                    return addr.address.replace("-", ":").lower()
    return "14:13:33:58:2a:b6"


class BluetoothServer:
    def __init__(self, channel: int = DEFAULT_RFCOMM_CHANNEL):
        self.channel = channel
        self.mac = get_local_bluetooth_mac()
        self.running = False
        self.server_sock: Optional[socket.socket] = None
        self.thread: Optional[threading.Thread] = None

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True, name="ConKey-Bluetooth")
        self.thread.start()
        logger.info("Bluetooth RFCOMM service started on MAC %s channel %d", self.mac, self.channel)

    def stop(self):
        self.running = False
        if self.server_sock:
            try:
                self.server_sock.close()
            except Exception:
                pass
        self.server_sock = None

    def _run(self):
        while self.running:
            sock = None
            try:
                sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
                sock.bind((self.mac, self.channel))
                sock.listen(1)
                self.server_sock = sock
                logger.info("Bluetooth listening on %s:%d (Pair & Play ready)", self.mac, self.channel)

                while self.running:
                    client_sock, client_info = sock.accept()
                    logger.info("Bluetooth device connected: %s", client_info)
                    self._handle_client(client_sock)
            except Exception as e:
                if self.running:
                    err_str = str(e)
                    if "10050" in err_str:
                        # Windows Bluetooth radio is selectively suspended / soft-off
                        logger.debug("Bluetooth radio suspended by Windows power-management; retrying in 15s...")
                        time.sleep(15.0)
                    else:
                        logger.warning("Bluetooth socket notice: %s (retrying in 5s)", e)
                        time.sleep(5.0)
            finally:
                if sock:
                    try:
                        sock.close()
                    except Exception:
                        pass

    def _handle_client(self, client_sock: socket.socket):
        buffer = ""
        try:
            client_sock.settimeout(60.0)
            while self.running:
                data = client_sock.recv(1024)
                if not data:
                    break
                buffer += data.decode("utf-8", errors="ignore")
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if line:
                        self._dispatch_command(line, client_sock)
        except Exception as e:
            logger.info("Bluetooth client disconnected: %s", e)
        finally:
            try:
                client_sock.close()
            except Exception:
                pass

    def _dispatch_command(self, raw_json: str, client_sock: socket.socket):
        try:
            cmd = parse_command(raw_json)
        except ProtocolError as err:
            logger.warning("Invalid Bluetooth command: %s", err)
            return

        if isinstance(cmd, TypeTextCommand):
            win_keyboard.type_text(cmd.text, cmd.delay)
        elif isinstance(cmd, KeyPressCommand):
            win_keyboard.press_key(cmd.key, cmd.delay)
        elif isinstance(cmd, KeyDownCommand):
            win_keyboard.key_down(cmd.key)
        elif isinstance(cmd, KeyUpCommand):
            win_keyboard.key_up(cmd.key)
        elif isinstance(cmd, KeyComboCommand):
            win_keyboard.key_combo(cmd.modifiers, cmd.key, cmd.delay)
        elif isinstance(cmd, MouseMoveCommand):
            win_keyboard.mouse_move(cmd.dx, cmd.dy)
        elif isinstance(cmd, MouseClickCommand):
            win_keyboard.mouse_click(cmd.button)
        elif isinstance(cmd, MouseScrollCommand):
            win_keyboard.mouse_scroll(cmd.dy)
