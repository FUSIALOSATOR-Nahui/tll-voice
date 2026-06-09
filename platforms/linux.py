"""
platforms/linux.py
Linux platform adapter.

Uses `pynput` for global hotkey listening (X11 compatible).
CapsLock state inversion is a Windows-specific pynput bug — it does NOT
occur on Linux, so pynput is the correct choice here.

INVARIANT: Does NOT import `keyboard` (Windows-only lib), windows.py,
           or check platform.system().
"""

import time
from typing import Callable

import pyperclip
from pynput import keyboard as pynput_kb
from pynput.keyboard import GlobalHotKeys, Controller as KbController, Key

from platforms.base import PlatformAdapter


def _to_pynput_key(hotkey_str: str) -> str:
    """
    Convert 'alt+caps lock' style string to pynput '<alt>+<caps_lock>' format.
    """
    mapping = {
        "alt": "<alt>",
        "ctrl": "<ctrl>",
        "shift": "<shift>",
        "cmd": "<cmd>",
        "caps lock": "<caps_lock>",
        "caps_lock": "<caps_lock>",
        "enter": "<enter>",
        "space": "<space>",
        "tab": "<tab>",
        "esc": "<esc>",
        "delete": "<delete>",
        "backspace": "<backspace>",
        **{f"f{n}": f"<f{n}>" for n in range(1, 13)},
    }
    raw = hotkey_str.strip().lower().replace("caps lock", "caps_lock")
    parts = [p.strip() for p in raw.split("+")]
    converted = [mapping.get(p, p if len(p) == 1 else f"<{p}>") for p in parts]
    return "+".join(converted)


class LinuxAdapter(PlatformAdapter):
    """Linux-specific implementation of PlatformAdapter using pynput."""

    def __init__(self) -> None:
        self._listener: GlobalHotKeys | None = None

    # ------------------------------------------------------------------
    # PlatformAdapter interface
    # ------------------------------------------------------------------

    def register_hotkeys(self, bindings: dict[str, Callable[[], None]]) -> None:
        """
        Register global hotkeys via pynput GlobalHotKeys.

        Parameters
        ----------
        bindings : {"alt+caps lock": cb1, "ctrl+caps lock": cb2, ...}

        Notes
        -----
        - pynput GlobalHotKeys runs in its own daemon thread.
        - On Linux (X11), pynput does not latch modifier keys.
        - Wayland support is limited; X11 session is recommended (see run.sh).
        """
        pynput_bindings = {
            _to_pynput_key(hotkey_str): callback
            for hotkey_str, callback in bindings.items()
        }
        self._listener = GlobalHotKeys(pynput_bindings)
        self._listener.start()
        for hk in bindings:
            print(f"[Linux] Hotkey registered: {hk} → {_to_pynput_key(hk)}")

    def inject_text(self, text: str) -> None:
        """
        Copy text to clipboard, wait 0.05 s, then emulate Ctrl+V via pynput.
        The sleep matches the Windows adapter contract for consistency.
        """
        pyperclip.copy(text)
        time.sleep(0.05)           # ← Δt ≥ 0.05 s (mirrors Windows contract)
        ctrl = KbController()
        with ctrl.pressed(Key.ctrl):
            ctrl.tap("v")

    def cleanup(self) -> None:
        """Stop the pynput GlobalHotKeys listener."""
        if self._listener:
            try:
                self._listener.stop()
                print("[Linux] Hotkey listener stopped.")
            except Exception as e:
                print(f"[Linux] Cleanup warning: {e}")
            self._listener = None
