"""
High-performance live screen capture module for ConKey.
Captures screen buffer from interactive desktop, overlays the real-time mouse cursor,
and compresses to JPEG for live streaming to the mobile client.
"""

import ctypes
from ctypes import wintypes
from typing import Optional, Tuple
import cv2
import numpy as np
from PIL import ImageGrab

from host.win_keyboard import ensure_desktop


class CURSORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("hCursor", wintypes.HANDLE),
        ("ptScreenPos", wintypes.POINT),
    ]


def get_screen_resolution() -> Tuple[int, int]:
    """Returns the primary screen resolution (width, height)."""
    if hasattr(ctypes, "windll"):
        user32 = ctypes.windll.user32
        w = user32.GetSystemMetrics(0)
        h = user32.GetSystemMetrics(1)
        return w, h
    try:
        img = ImageGrab.grab()
        return img.size
    except Exception:
        return 1920, 1080


def get_cursor_info() -> Tuple[Optional[Tuple[int, int]], bool]:
    """Retrieves current cursor position and visibility state."""
    ensure_desktop()
    if hasattr(ctypes, "windll"):
        try:
            ci = CURSORINFO()
            ci.cbSize = ctypes.sizeof(CURSORINFO)
            if ctypes.windll.user32.GetCursorInfo(ctypes.byref(ci)):
                is_showing = bool(ci.flags & 0x00000001)  # CURSOR_SHOWING
                return (ci.ptScreenPos.x, ci.ptScreenPos.y), is_showing
        except Exception:
            pass
    return None, False


def draw_cursor_overlay(arr: np.ndarray, cx: int, cy: int, scale: float = 1.1) -> None:
    """
    Draws a crisp, anti-aliased Windows pointer arrow with shadow
    at the given pixel coordinates.
    """
    h, w = arr.shape[:2]
    if not (0 <= cx < w and 0 <= cy < h):
        return

    # Classic high-visibility Windows pointer polygon vertices relative to tip (0, 0)
    pts = np.array([
        [0, 0],
        [0, 18],
        [4, 14],
        [7, 21],
        [10, 20],
        [7, 13],
        [13, 13]
    ], dtype=np.float32)

    scaled_pts = (pts * scale + np.array([cx, cy])).astype(np.int32)

    # Subtle drop shadow
    shadow_pts = scaled_pts + np.array([1, 1], dtype=np.int32)
    cv2.fillPoly(arr, [shadow_pts], (20, 20, 20))

    # High-contrast white fill
    cv2.fillPoly(arr, [scaled_pts], (255, 255, 255))

    # Anti-aliased black boundary
    cv2.polylines(arr, [scaled_pts], isClosed=True, color=(0, 0, 0), thickness=1, lineType=cv2.LINE_AA)


def capture_frame_jpeg(max_width: int = 960, quality: int = 65) -> Optional[bytes]:
    """
    Captures desktop frame, overlays visible mouse pointer,
    resizes to max_width, and returns compressed JPEG bytes.
    """
    ensure_desktop()
    try:
        img = ImageGrab.grab()
        orig_w, orig_h = img.size
        arr = np.array(img)
        arr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)

        h, w = arr.shape[:2]
        target_w = w
        target_h = h

        if w > max_width:
            target_w = max_width
            target_h = int(h * (target_w / w))
            arr = cv2.resize(arr, (target_w, target_h), interpolation=cv2.INTER_AREA)

        # Draw real-time mouse cursor arrow on frame
        cur_pos, is_showing = get_cursor_info()
        if cur_pos and is_showing:
            cx, cy = cur_pos
            scale_x = target_w / float(orig_w)
            scale_y = target_h / float(orig_h)
            draw_cx = int(cx * scale_x)
            draw_cy = int(cy * scale_y)
            draw_cursor_overlay(arr, draw_cx, draw_cy, scale=1.1)

        ret, jpeg = cv2.imencode('.jpg', arr, [cv2.IMWRITE_JPEG_QUALITY, quality])
        if ret:
            return jpeg.tobytes()
    except Exception:
        pass
    return None
