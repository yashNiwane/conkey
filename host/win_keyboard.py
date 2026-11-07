"""
Windows keyboard input simulation using Win32 SendInput via ctypes.
Provides high-fidelity unicode typing, virtual key codes, and modifier chords.
"""

import ctypes
from ctypes import wintypes
import time
from typing import List, Optional

# Win32 Constants
INPUT_KEYBOARD = 1
INPUT_MOUSE = 0

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_SCANCODE = 0x0008

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800

# Virtual Key Codes
VK_MAP = {
    # Modifiers
    "CTRL": 0x11,
    "CONTROL": 0x11,
    "LCTRL": 0xA2,
    "RCTRL": 0xA3,
    "ALT": 0x12,
    "MENU": 0x12,
    "SHIFT": 0x10,
    "LSHIFT": 0xA0,
    "RSHIFT": 0xA1,
    "WIN": 0x5B,
    "WINDOWS": 0x5B,
    
    # Common navigation & editing
    "BACKSPACE": 0x08,
    "BACK": 0x08,
    "TAB": 0x09,
    "ENTER": 0x0D,
    "RETURN": 0x0D,
    "ESCAPE": 0x1B,
    "ESC": 0x1B,
    "SPACE": 0x20,
    "PAGEUP": 0x21,
    "PAGEDOWN": 0x22,
    "END": 0x23,
    "HOME": 0x24,
    "LEFT": 0x25,
    "UP": 0x26,
    "RIGHT": 0x27,
    "DOWN": 0x28,
    "DELETE": 0x2E,
    "DEL": 0x2E,
    "INSERT": 0x2D,
    "CAPSLOCK": 0x14,
    
    # Function keys
    **{f"F{i}": 0x6F + i for i in range(1, 13)},
    
    # Alphanumeric
    **{chr(c): c for c in range(ord('A'), ord('Z') + 1)},
    **{chr(c): c for c in range(ord('0'), ord('9') + 1)},
}

# Win32 C Structs
ULONG_PTR = ctypes.c_size_t

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]

class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]

class INPUT(ctypes.Structure):
    class _INPUT_UNION(ctypes.Union):
        _fields_ = [
            ("ki", KEYBDINPUT),
            ("mi", MOUSEINPUT),
            ("hi", HARDWAREINPUT),
        ]
    _anonymous_ = ("_u",)
    _fields_ = [
        ("type", wintypes.DWORD),
        ("_u", _INPUT_UNION),
    ]

_SendInput = ctypes.windll.user32.SendInput
_SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
_SendInput.restype = wintypes.UINT


def _send_inputs(inputs: List[INPUT]) -> int:
    if not inputs:
        return 0
    n = len(inputs)
    arr = (INPUT * n)(*inputs)
    return _SendInput(n, arr, ctypes.sizeof(INPUT))


def key_down(vk_or_name: str | int) -> None:
    vk = VK_MAP.get(vk_or_name.upper(), 0) if isinstance(vk_or_name, str) else vk_or_name
    if not vk:
        raise ValueError(f"Unknown virtual key: {vk_or_name}")
    
    flags = 0
    if vk in (0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E, 0x5B):
        flags |= KEYEVENTF_EXTENDEDKEY

    inp = INPUT(
        type=INPUT_KEYBOARD,
        ki=KEYBDINPUT(wVk=vk, wScan=0, dwFlags=flags, time=0, dwExtraInfo=0)
    )
    _send_inputs([inp])


def key_up(vk_or_name: str | int) -> None:
    vk = VK_MAP.get(vk_or_name.upper(), 0) if isinstance(vk_or_name, str) else vk_or_name
    if not vk:
        raise ValueError(f"Unknown virtual key: {vk_or_name}")
    
    flags = KEYEVENTF_KEYUP
    if vk in (0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E, 0x5B):
        flags |= KEYEVENTF_EXTENDEDKEY

    inp = INPUT(
        type=INPUT_KEYBOARD,
        ki=KEYBDINPUT(wVk=vk, wScan=0, dwFlags=flags, time=0, dwExtraInfo=0)
    )
    _send_inputs([inp])


def press_key(vk_or_name: str | int, delay: float = 0.01) -> None:
    key_down(vk_or_name)
    if delay > 0:
        time.sleep(delay)
    key_up(vk_or_name)


def key_combo(modifiers: List[str], key: str, delay: float = 0.01) -> None:
    """Presses a combination such as ['CTRL'], 'C' or ['CTRL', 'ALT'], 'DELETE'."""
    for mod in modifiers:
        key_down(mod)
    try:
        if key:
            press_key(key, delay=delay)
    finally:
        for mod in reversed(modifiers):
            key_up(mod)


def type_char_unicode(char: str) -> None:
    """Sends a single unicode character using KEYEVENTF_UNICODE."""
    code = ord(char)
    # Down
    inp_down = INPUT(
        type=INPUT_KEYBOARD,
        ki=KEYBDINPUT(wVk=0, wScan=code, dwFlags=KEYEVENTF_UNICODE, time=0, dwExtraInfo=0)
    )
    # Up
    inp_up = INPUT(
        type=INPUT_KEYBOARD,
        ki=KEYBDINPUT(wVk=0, wScan=code, dwFlags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, time=0, dwExtraInfo=0)
    )
    _send_inputs([inp_down, inp_up])


def type_text(text: str, inter_char_delay: float = 0.0) -> None:
    """Types a string of text character by character using Unicode injection."""
    for char in text:
        if char == '\r':
            continue
        if char == '\n':
            press_key("ENTER")
        elif char == '\t':
            press_key("TAB")
        else:
            type_char_unicode(char)
        if inter_char_delay > 0:
            time.sleep(inter_char_delay)


def mouse_move(dx: int, dy: int) -> None:
    inp = INPUT(
        type=INPUT_MOUSE,
        mi=MOUSEINPUT(dx=dx, dy=dy, mouseData=0, dwFlags=MOUSEEVENTF_MOVE, time=0, dwExtraInfo=0)
    )
    _send_inputs([inp])


def mouse_click(button: str = "left") -> None:
    btn = button.lower()
    if btn == "left":
        down_flag, up_flag = MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP
    elif btn == "right":
        down_flag, up_flag = MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP
    elif btn == "middle":
        down_flag, up_flag = MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP
    elif btn == "double":
        mouse_click("left")
        time.sleep(0.05)
        mouse_click("left")
        return
    else:
        raise ValueError(f"Unknown mouse button: {button}")

    inp_down = INPUT(type=INPUT_MOUSE, mi=MOUSEINPUT(dx=0, dy=0, mouseData=0, dwFlags=down_flag, time=0, dwExtraInfo=0))
    inp_up = INPUT(type=INPUT_MOUSE, mi=MOUSEINPUT(dx=0, dy=0, mouseData=0, dwFlags=up_flag, time=0, dwExtraInfo=0))
    _send_inputs([inp_down, inp_up])


def mouse_scroll(dy: int) -> None:
    # dy typically in multiples of 120 (WHEEL_DELTA)
    wheel_amount = dy * 120
    inp = INPUT(
        type=INPUT_MOUSE,
        mi=MOUSEINPUT(dx=0, dy=0, mouseData=wheel_amount, dwFlags=MOUSEEVENTF_WHEEL, time=0, dwExtraInfo=0)
    )
    _send_inputs([inp])
