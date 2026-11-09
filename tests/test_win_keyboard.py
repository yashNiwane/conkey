import ctypes
import pytest
from host.win_keyboard import (
    VK_MAP,
    INPUT,
    KEYBDINPUT,
    MOUSEINPUT,
    key_down,
    key_up,
    press_key,
    key_combo,
    type_char_unicode,
    type_text,
    mouse_move,
    mouse_click,
    mouse_scroll,
)

def test_vk_map_essentials():
    for key in ["CTRL", "ALT", "SHIFT", "WIN", "ENTER", "BACKSPACE", "TAB", "ESC", "SPACE", "LEFT", "RIGHT", "UP", "DOWN", "A", "S", "C", "V", "Z"]:
        assert key in VK_MAP, f"Missing key in VK_MAP: {key}"
        assert isinstance(VK_MAP[key], int)

def test_struct_sizes():
    # In 64-bit Windows:
    # type (DWORD 4) + padding 4 + union (32 bytes) = 40 bytes
    assert ctypes.sizeof(INPUT) in (28, 40)
    assert ctypes.sizeof(KEYBDINPUT) > 0
    assert ctypes.sizeof(MOUSEINPUT) > 0

def test_unknown_key_raises_error():
    with pytest.raises(ValueError):
        key_down("NON_EXISTENT_KEY_XYZ_123")
    with pytest.raises(ValueError):
        key_up("NON_EXISTENT_KEY_XYZ_123")

def test_mouse_unknown_button_raises():
    with pytest.raises(ValueError):
        mouse_click("invalid_button")

def test_simulated_calls_do_not_crash():
    # We test that the API calls succeed cleanly
    type_char_unicode("A")
    type_char_unicode("!")
    type_char_unicode("S")
    press_key("SHIFT")
    key_combo(["CTRL"], "C")
    key_combo(["CTRL"], "V")
    mouse_move(0, 0)
    mouse_scroll(0)

def test_sync_live_text_simulation():
    from host.win_keyboard import sync_live_text
    # Sequential partial updates
    sync_live_text("", "Best")
    sync_live_text("Best", "Best restaurants")
    sync_live_text("Best restaurants", "Best restaurants near")
    sync_live_text("Best restaurants near", "Best restaurants near me")
    # Punctuation / segment commit
    sync_live_text("Best restaurants near me", "Best restaurants near me. ")
    # Correction simulation
    sync_live_text("Hullo", "Hello world")
    # Identical text no-op
    sync_live_text("Same", "Same")
