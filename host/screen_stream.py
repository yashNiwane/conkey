"""
High-performance live screen capture module for ConKey.
Captures screen buffer from interactive desktop and compresses to JPEG
for live streaming to the mobile client.
"""

import ctypes
from typing import Optional, Tuple
import cv2
import numpy as np
from PIL import ImageGrab

from host.win_keyboard import ensure_desktop


def get_screen_resolution() -> Tuple[int, int]:
    """Returns the primary screen resolution (width, height)."""
    user32 = ctypes.windll.user32
    w = user32.GetSystemMetrics(0)
    h = user32.GetSystemMetrics(1)
    return w, h


def capture_frame_jpeg(max_width: int = 960, quality: int = 65) -> Optional[bytes]:
    """
    Captures a single frame of the laptop desktop, resizes to max_width preserving aspect ratio,
    and returns compressed JPEG bytes.
    """
    ensure_desktop()
    try:
        img = ImageGrab.grab()
        arr = np.array(img)
        arr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)

        h, w = arr.shape[:2]
        if w > max_width:
            target_w = max_width
            target_h = int(h * (target_w / w))
            arr = cv2.resize(arr, (target_w, target_h), interpolation=cv2.INTER_AREA)

        ret, jpeg = cv2.imencode('.jpg', arr, [cv2.IMWRITE_JPEG_QUALITY, quality])
        if ret:
            return jpeg.tobytes()
    except Exception:
        pass
    return None
