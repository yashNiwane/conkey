"""
Windows keyboard and mouse input simulation using Win32 SendInput via ctypes.
Provides high-fidelity unicode typing, virtual key codes, modifier chords,
and comprehensive PC keyboard keys (F1-F12, Numpad, Navigation, Media).
Ensures attachment to interactive 'Default' desktop so inputs reach physical display.
"""

import ctypes
from ctypes import wintypes
import logging
import threading
import time
from typing import List, Optional

logger = logging.getLogger("conkey.win_keyboard")

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

GENERIC_ALL = 0x10000000

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
    "LWIN": 0x5B,
    "RWIN": 0x5C,
    "APPS": 0x5D,
    
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
    "PGUP": 0x21,
    "PAGEDOWN": 0x22,
    "PGDN": 0x22,
    "END": 0x23,
    "HOME": 0x24,
    "LEFT": 0x25,
    "UP": 0x26,
    "RIGHT": 0x27,
    "DOWN": 0x28,
    "DELETE": 0x2E,
    "DEL": 0x2E,
    "INSERT": 0x2D,
    "INS": 0x2D,
    "CAPSLOCK": 0x14,
    "PRINTSCREEN": 0x2C,
    "PRTSCN": 0x2C,
    "SCROLLLOCK": 0x91,
    "PAUSE": 0x13,
    "BREAK": 0x13,
    
    # Punctuation & Symbols
    "SEMICOLON": 0xBA,
    "PLUS": 0xBB,
    "EQUALS": 0xBB,
    "COMMA": 0xBC,
    "MINUS": 0xBD,
    "HYPHEN": 0xBD,
    "PERIOD": 0xBE,
    "DOT": 0xBE,
    "SLASH": 0xBF,
    "TILDE": 0xC0,
    "GRAVE": 0xC0,
    "LBRACKET": 0xDB,
    "BRACKET_LEFT": 0xDB,
    "BACKSLASH": 0xDC,
    "RBRACKET": 0xDD,
    "BRACKET_RIGHT": 0xDD,
    "QUOTE": 0xDE,
    "APOSTROPHE": 0xDE,

    # Numeric Keypad (Numpad)
    "NUMLOCK": 0x90,
    "NUMPAD0": 0x60,
    "NUMPAD1": 0x61,
    "NUMPAD2": 0x62,
    "NUMPAD3": 0x63,
    "NUMPAD4": 0x64,
    "NUMPAD5": 0x65,
    "NUMPAD6": 0x66,
    "NUMPAD7": 0x67,
    "NUMPAD8": 0x68,
    "NUMPAD9": 0x69,
    "MULTIPLY": 0x6A,
    "ADD": 0x6B,
    "SEPARATOR": 0x6C,
    "SUBTRACT": 0x6D,
    "DECIMAL": 0x6E,
    "DIVIDE": 0x6F,

    # Media & Volume
    "VOLUME_MUTE": 0xAD,
    "VOLUME_DOWN": 0xAE,
    "VOLUME_UP": 0xAF,
    "MEDIA_NEXT": 0xB0,
    "MEDIA_PREV": 0xB1,
    "MEDIA_STOP": 0xB2,
    "MEDIA_PLAY_PAUSE": 0xB3,
    
    # Function keys (F1 - F12)
    **{f"F{i}": 0x6F + i for i in range(1, 13)},
    
    # Alphanumeric
    **{chr(c): c for c in range(ord('A'), ord('Z') + 1)},
    **{chr(c): c for c in range(ord('0'), ord('9') + 1)},
}

# Extended keys that require KEYEVENTF_EXTENDEDKEY flag
EXTENDED_VKS = {
    0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28,  # Arrows, Home, End, PgUp, PgDn
    0x2D, 0x2E,                                      # Insert, Delete
    0x5B, 0x5C, 0x5D,                                # Win keys, Apps
    0x6F,                                            # Numpad divide
    0x2C,                                            # PrintScreen
    0x90,                                            # NumLock
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

_desktop_lock = threading.Lock()
_default_desktop = None


def ensure_desktop() -> bool:
    """
    Attaches current thread to the user's interactive 'Default' desktop.
    Critical when Python server is started via background runners or services,
    ensuring SendInput injects into the physical display session.
    """
    global _default_desktop
    try:
        with _desktop_lock:
            if not _default_desktop:
                _default_desktop = ctypes.windll.user32.OpenDesktopW("Default", 0, False, GENERIC_ALL)
            if _default_desktop:
                if ctypes.windll.user32.SetThreadDesktop(_default_desktop) != 0:
                    return True
                # Re-open if cached handle stale
                _default_desktop = ctypes.windll.user32.OpenDesktopW("Default", 0, False, GENERIC_ALL)
                if _default_desktop:
                    return ctypes.windll.user32.SetThreadDesktop(_default_desktop) != 0
    except Exception as e:
        logger.debug("ensure_desktop error: %s", e)
    return False


def _send_inputs(inputs: List[INPUT]) -> int:
    if not inputs:
        return 0
    ensure_desktop()
    n = len(inputs)
    arr = (INPUT * n)(*inputs)
    sent = _SendInput(n, arr, ctypes.sizeof(INPUT))
    if sent != n:
        err = ctypes.GetLastError()
        logger.debug("SendInput: sent %d/%d (err: %d)", sent, n, err)
    return sent


def key_down(vk_or_name: str | int) -> None:
    ensure_desktop()
    vk = VK_MAP.get(vk_or_name.upper(), 0) if isinstance(vk_or_name, str) else vk_or_name
    if not vk:
        if isinstance(vk_or_name, str) and len(vk_or_name) == 1:
            type_char_unicode(vk_or_name)
            return
        raise ValueError(f"Unknown virtual key: {vk_or_name}")
    
    flags = 0
    if vk in EXTENDED_VKS:
        flags |= KEYEVENTF_EXTENDEDKEY

    inp = INPUT(
        type=INPUT_KEYBOARD,
        ki=KEYBDINPUT(wVk=vk, wScan=0, dwFlags=flags, time=0, dwExtraInfo=0)
    )
    sent = _send_inputs([inp])
    if sent == 0:
        # Fallback to keybd_event
        ctypes.windll.user32.keybd_event(vk, 0, flags, 0)


def key_up(vk_or_name: str | int) -> None:
    ensure_desktop()
    vk = VK_MAP.get(vk_or_name.upper(), 0) if isinstance(vk_or_name, str) else vk_or_name
    if not vk:
        if isinstance(vk_or_name, str) and len(vk_or_name) == 1:
            return
        raise ValueError(f"Unknown virtual key: {vk_or_name}")
    
    flags = KEYEVENTF_KEYUP
    if vk in EXTENDED_VKS:
        flags |= KEYEVENTF_EXTENDEDKEY

    inp = INPUT(
        type=INPUT_KEYBOARD,
        ki=KEYBDINPUT(wVk=vk, wScan=0, dwFlags=flags, time=0, dwExtraInfo=0)
    )
    sent = _send_inputs([inp])
    if sent == 0:
        # Fallback to keybd_event
        ctypes.windll.user32.keybd_event(vk, 0, flags, 0)


def press_key(vk_or_name: str | int, delay: float = 0.01) -> None:
    ensure_desktop()
    if isinstance(vk_or_name, str) and len(vk_or_name) == 1 and vk_or_name.upper() not in VK_MAP:
        type_char_unicode(vk_or_name)
        return

    key_down(vk_or_name)
    if delay > 0:
        time.sleep(delay)
    key_up(vk_or_name)


def key_combo(modifiers: List[str], key: str, delay: float = 0.01) -> None:
    """Presses a combination such as ['CTRL'], 'C' or ['ALT'], 'TAB'."""
    ensure_desktop()
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
    ensure_desktop()
    code = ord(char)
    inp_down = INPUT(
        type=INPUT_KEYBOARD,
        ki=KEYBDINPUT(wVk=0, wScan=code, dwFlags=KEYEVENTF_UNICODE, time=0, dwExtraInfo=0)
    )
    inp_up = INPUT(
        type=INPUT_KEYBOARD,
        ki=KEYBDINPUT(wVk=0, wScan=code, dwFlags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, time=0, dwExtraInfo=0)
    )
    _send_inputs([inp_down, inp_up])


def type_text(text: str, inter_char_delay: float = 0.0) -> None:
    """Types a string of text character by character using Unicode injection."""
    ensure_desktop()
    for char in text:
        if char == '\r':
            continue
        elif char == '\n':
            press_key("ENTER")
        elif char == '\t':
            press_key("TAB")
        else:
            type_char_unicode(char)
        if inter_char_delay > 0:
            time.sleep(inter_char_delay)


def sync_live_text(prev: str, curr: str) -> None:
    """
    Synchronizes the on-screen live typed text from `prev` to `curr`
    in whichever text field currently has focus, erasing divergence
    with backspaces and typing the new suffix via SendInput unicode events.
    """
    if prev == curr:
        return
    ensure_desktop()
    common = 0
    min_len = min(len(prev), len(curr))
    while common < min_len and prev[common] == curr[common]:
        common += 1
    backspaces = len(prev) - common
    typed = curr[common:]

    inputs: List[INPUT] = []
    # Send backspaces for diverging characters
    for _ in range(backspaces):
        inputs.append(INPUT(
            type=INPUT_KEYBOARD,
            ki=KEYBDINPUT(wVk=VK_MAP["BACKSPACE"], wScan=0, dwFlags=0, time=0, dwExtraInfo=0)
        ))
        inputs.append(INPUT(
            type=INPUT_KEYBOARD,
            ki=KEYBDINPUT(wVk=VK_MAP["BACKSPACE"], wScan=0, dwFlags=KEYEVENTF_KEYUP, time=0, dwExtraInfo=0)
        ))

    # Type new characters
    for char in typed:
        if char == '\r':
            continue
        elif char == '\n':
            inputs.append(INPUT(
                type=INPUT_KEYBOARD,
                ki=KEYBDINPUT(wVk=VK_MAP["ENTER"], wScan=0, dwFlags=0, time=0, dwExtraInfo=0)
            ))
            inputs.append(INPUT(
                type=INPUT_KEYBOARD,
                ki=KEYBDINPUT(wVk=VK_MAP["ENTER"], wScan=0, dwFlags=KEYEVENTF_KEYUP, time=0, dwExtraInfo=0)
            ))
        elif char == '\t':
            inputs.append(INPUT(
                type=INPUT_KEYBOARD,
                ki=KEYBDINPUT(wVk=VK_MAP["TAB"], wScan=0, dwFlags=0, time=0, dwExtraInfo=0)
            ))
            inputs.append(INPUT(
                type=INPUT_KEYBOARD,
                ki=KEYBDINPUT(wVk=VK_MAP["TAB"], wScan=0, dwFlags=KEYEVENTF_KEYUP, time=0, dwExtraInfo=0)
            ))
        else:
            code = ord(char)
            inputs.append(INPUT(
                type=INPUT_KEYBOARD,
                ki=KEYBDINPUT(wVk=0, wScan=code, dwFlags=KEYEVENTF_UNICODE, time=0, dwExtraInfo=0)
            ))
            inputs.append(INPUT(
                type=INPUT_KEYBOARD,
                ki=KEYBDINPUT(wVk=0, wScan=code, dwFlags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, time=0, dwExtraInfo=0)
            ))

    if inputs:
        _send_inputs(inputs)


def mouse_move(dx: int, dy: int) -> None:
    ensure_desktop()
    inp = INPUT(
        type=INPUT_MOUSE,
        mi=MOUSEINPUT(dx=dx, dy=dy, mouseData=0, dwFlags=MOUSEEVENTF_MOVE, time=0, dwExtraInfo=0)
    )
    sent = _send_inputs([inp])
    if sent == 0:
        ctypes.windll.user32.mouse_event(MOUSEEVENTF_MOVE, dx, dy, 0, 0)


def mouse_move_abs(x: int, y: int) -> None:
    """Sets cursor to absolute screen coordinates."""
    ensure_desktop()
    ctypes.windll.user32.SetCursorPos(int(x), int(y))


def mouse_click(button: str = "left") -> None:
    ensure_desktop()
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
    sent = _send_inputs([inp_down, inp_up])
    if sent == 0:
        ctypes.windll.user32.mouse_event(down_flag | up_flag, 0, 0, 0, 0)


def mouse_scroll(dy: int) -> None:
    ensure_desktop()
    wheel_amount = dy * 120
    inp = INPUT(
        type=INPUT_MOUSE,
        mi=MOUSEINPUT(dx=0, dy=0, mouseData=wheel_amount, dwFlags=MOUSEEVENTF_WHEEL, time=0, dwExtraInfo=0)
    )
    sent = _send_inputs([inp])
    if sent == 0:
        ctypes.windll.user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, wheel_amount, 0)
