"""
core/gui/tray.py
System tray icon via pystray + Pillow.
INVARIANT: No imports of keyboard, pynput, or platform.system().
"""

import threading

import pystray
from PIL import Image, ImageDraw


def _build_icon_image() -> Image.Image:
    """Create a 64×64 RGBA microphone icon programmatically."""
    img = Image.new("RGBA", (64, 64), color=(0, 0, 0, 0))
    dc = ImageDraw.Draw(img)
    # Dark rounded background
    dc.ellipse((4, 4, 60, 60), fill=(30, 30, 46, 255), outline=(137, 180, 250, 255), width=3)
    # Microphone body
    dc.rounded_rectangle((24, 16, 40, 38), radius=8, fill=(137, 180, 250, 255))
    # Microphone stand arc
    dc.arc((18, 24, 46, 44), start=0, end=180, fill=(137, 180, 250, 255), width=3)
    # Stand pole + base
    dc.line((32, 44, 32, 52), fill=(137, 180, 250, 255), width=4)
    dc.line((22, 52, 42, 52), fill=(137, 180, 250, 255), width=4)
    return img


class TrayIcon:
    """Wraps pystray.Icon; runs in a daemon thread."""

    def __init__(self, on_exit_callback) -> None:
        self._on_exit = on_exit_callback
        self._icon: pystray.Icon | None = None

    def start(self) -> None:
        menu = pystray.Menu(pystray.MenuItem("Выход", self._on_exit))
        self._icon = pystray.Icon("TLL-Voice", _build_icon_image(), "TLL-Voice Dictation", menu)
        threading.Thread(target=self._icon.run, daemon=True).start()

    def stop(self) -> None:
        if self._icon:
            self._icon.stop()
            self._icon = None
