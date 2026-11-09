"""
Cross-platform keyboard & mouse driver dispatcher for ConKey.
Automatically routes input events to Windows SendInput or Linux xdotool/uinput.
"""

from __future__ import annotations

import sys

if sys.platform.startswith("win"):
    from host import win_keyboard as _backend
else:
    from host import linux_keyboard as _backend  # type: ignore

# Expose unified interface
ensure_desktop = _backend.ensure_desktop
key_down = _backend.key_down
key_up = _backend.key_up
press_key = _backend.press_key
key_combo = _backend.key_combo
type_char_unicode = _backend.type_char_unicode
type_text = _backend.type_text
sync_live_text = _backend.sync_live_text
mouse_move = _backend.mouse_move
mouse_move_abs = _backend.mouse_move_abs
mouse_click = _backend.mouse_click
mouse_scroll = _backend.mouse_scroll

__all__ = [
    "ensure_desktop",
    "key_down",
    "key_up",
    "press_key",
    "key_combo",
    "type_char_unicode",
    "type_text",
    "sync_live_text",
    "mouse_move",
    "mouse_move_abs",
    "mouse_click",
    "mouse_scroll",
]
