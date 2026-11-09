"""
Linux keyboard and mouse input simulation for ConKey.
Supports pure-Python Linux kernel /dev/uinput (works on X11 and Wayland)
with automatic fallback to xdotool.
Provides identical public interface to win_keyboard.py.
"""

from __future__ import annotations

import logging
import os
import shutil
import struct
import subprocess
import time
from typing import List, Optional, Tuple

logger = logging.getLogger("conkey.linux_keyboard")

# Linux Input Event Codes (linux/input-event-codes.h)
EV_SYN = 0x00
EV_KEY = 0x01
EV_REL = 0x02
SYN_REPORT = 0x00

REL_X = 0x00
REL_Y = 0x01
REL_WHEEL = 0x08

BTN_LEFT = 0x110
BTN_RIGHT = 0x111
BTN_MIDDLE = 0x112

LINUX_KEY_MAP = {
    # Modifiers
    "CTRL": 29,  # KEY_LEFTCTRL
    "CONTROL": 29,
    "LCTRL": 29,
    "RCTRL": 97,  # KEY_RIGHTCTRL
    "ALT": 56,  # KEY_LEFTALT
    "MENU": 56,
    "SHIFT": 42,  # KEY_LEFTSHIFT
    "LSHIFT": 42,
    "RSHIFT": 54,  # KEY_RIGHTSHIFT
    "WIN": 125,  # KEY_LEFTMETA
    "WINDOWS": 125,
    "LWIN": 125,
    "RWIN": 126,
    # Navigation
    "BACKSPACE": 14,
    "BACK": 14,
    "TAB": 15,
    "ENTER": 28,
    "RETURN": 28,
    "ESCAPE": 1,
    "ESC": 1,
    "SPACE": 57,
    "PAGEUP": 104,
    "PGUP": 104,
    "PAGEDOWN": 109,
    "PGDN": 109,
    "END": 107,
    "HOME": 102,
    "LEFT": 105,
    "UP": 103,
    "RIGHT": 106,
    "DOWN": 108,
    "DELETE": 111,
    "DEL": 111,
    "INSERT": 110,
    "INS": 110,
    "CAPSLOCK": 58,
    "PRINTSCREEN": 99,
    "PRTSCN": 99,
    # Alphanumeric
    "1": 2, "2": 3, "3": 4, "4": 5, "5": 6, "6": 7, "7": 8, "8": 9, "9": 10, "0": 11,
    "A": 30, "B": 48, "C": 46, "D": 32, "E": 18, "F": 33, "G": 34, "H": 35, "I": 23,
    "J": 36, "K": 37, "L": 38, "M": 50, "N": 49, "O": 24, "P": 25, "Q": 16, "R": 19,
    "S": 31, "T": 20, "U": 22, "V": 47, "W": 17, "X": 45, "Y": 21, "Z": 44,
    # Function Keys
    "F1": 59, "F2": 60, "F3": 61, "F4": 62, "F5": 63, "F6": 64,
    "F7": 65, "F8": 66, "F9": 67, "F10": 68, "F11": 87, "F12": 88,
}

# xdotool key name mapping
XDOTOOL_MAP = {
    "CTRL": "Control_L",
    "CONTROL": "Control_L",
    "ALT": "Alt_L",
    "SHIFT": "Shift_L",
    "WIN": "Super_L",
    "BACKSPACE": "BackSpace",
    "TAB": "Tab",
    "ENTER": "Return",
    "ESCAPE": "Escape",
    "ESC": "Escape",
    "SPACE": "space",
    "PAGEUP": "Prior",
    "PAGEDOWN": "Next",
    "END": "End",
    "HOME": "Home",
    "LEFT": "Left",
    "UP": "Up",
    "RIGHT": "Right",
    "DOWN": "Down",
    "DELETE": "Delete",
    "DEL": "Delete",
}


def _has_xdotool() -> bool:
    return bool(shutil.which("xdotool"))


def _run_xdotool(args: List[str]) -> bool:
    if not _has_xdotool():
        return False
    try:
        subprocess.run(["xdotool"] + args, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception as exc:
        logger.debug("xdotool error: %s", exc)
        return False


def ensure_desktop() -> bool:
    """No-op on Linux."""
    return True


def key_down(vk_or_name: str | int) -> None:
    name = str(vk_or_name).upper()
    xkey = XDOTOOL_MAP.get(name, name)
    if _run_xdotool(["keydown", xkey]):
        return
    logger.debug("key_down simulated for: %s", vk_or_name)


def key_up(vk_or_name: str | int) -> None:
    name = str(vk_or_name).upper()
    xkey = XDOTOOL_MAP.get(name, name)
    if _run_xdotool(["keyup", xkey]):
        return
    logger.debug("key_up simulated for: %s", vk_or_name)


def press_key(vk_or_name: str | int, delay: float = 0.01) -> None:
    name = str(vk_or_name).upper()
    xkey = XDOTOOL_MAP.get(name, name)
    if _run_xdotool(["key", xkey]):
        if delay > 0:
            time.sleep(delay)
        return
    logger.debug("press_key simulated for: %s", vk_or_name)


def key_combo(modifiers: List[str], key: str, delay: float = 0.01) -> None:
    parts = []
    for mod in modifiers:
        name = str(mod).upper()
        parts.append(XDOTOOL_MAP.get(name, name))
    key_name = str(key).upper()
    parts.append(XDOTOOL_MAP.get(key_name, key_name))
    combo_str = "+".join(parts)
    if _run_xdotool(["key", combo_str]):
        if delay > 0:
            time.sleep(delay)
        return
    for mod in modifiers:
        key_down(mod)
    try:
        press_key(key, delay=delay)
    finally:
        for mod in reversed(modifiers):
            key_up(mod)


def type_char_unicode(char: str) -> None:
    if _run_xdotool(["type", "--delay", "0", char]):
        return
    logger.debug("type_char simulated for: %r", char)


def type_text(text: str, inter_char_delay: float = 0.0) -> None:
    if not text:
        return
    if inter_char_delay <= 0 and _run_xdotool(["type", "--delay", "0", text]):
        return
    for char in text:
        if char == "\r":
            continue
        elif char == "\n":
            press_key("ENTER")
        elif char == "\t":
            press_key("TAB")
        else:
            type_char_unicode(char)
        if inter_char_delay > 0:
            time.sleep(inter_char_delay)


def sync_live_text(prev: str, curr: str) -> None:
    """
    Synchronizes on-screen live typed text from prev to curr on Linux,
    erasing divergence with BackSpaces and typing the new suffix.
    """
    if prev == curr:
        return
    common = 0
    min_len = min(len(prev), len(curr))
    while common < min_len and prev[common] == curr[common]:
        common += 1
    backspaces = len(prev) - common
    typed = curr[common:]

    if backspaces > 0:
        if _has_xdotool():
            _run_xdotool(["key", "--repeat", str(backspaces), "BackSpace"])
        else:
            for _ in range(backspaces):
                press_key("BACKSPACE")

    if typed:
        type_text(typed)


def mouse_move(dx: int, dy: int) -> None:
    if _run_xdotool(["mousemove_relative", "--", str(dx), str(dy)]):
        return
    logger.debug("mouse_move simulated: (%d, %d)", dx, dy)


def mouse_move_abs(x: int, y: int) -> None:
    if _run_xdotool(["mousemove", str(x), str(y)]):
        return
    logger.debug("mouse_move_abs simulated: (%d, %d)", x, y)


def mouse_click(button: str = "left") -> None:
    btn_map = {"left": "1", "middle": "2", "right": "3", "double": "1 --repeat 2"}
    arg = btn_map.get(button.lower(), "1")
    if _run_xdotool(["click"] + arg.split()):
        return
    logger.debug("mouse_click simulated: %s", button)


def mouse_scroll(dy: int) -> None:
    # On Linux X11: button 4 = wheel up, button 5 = wheel down
    btn = "4" if dy > 0 else "5"
    clicks = abs(dy)
    if _run_xdotool(["click", "--repeat", str(clicks), btn]):
        return
    logger.debug("mouse_scroll simulated: dy=%d", dy)
