"""
platforms/windows.py
Windows platform adapter.

HARD CONSTRAINTS (non-negotiable):
  1. Uses EXCLUSIVELY the `keyboard` library for input hooking. pynput is
     FORBIDDEN here — pynput on Windows inverts CapsLock state when
     Alt+CapsLock is held, causing system-wide modifier latching.
  2. `keyboard.add_hotkey(..., suppress=False)` — key events pass through
     to the OS unchanged. No modifier keys are consumed or latched.
  3. inject_text() enforces a mandatory 0.05 s gap between pyperclip.copy()
     and Ctrl+V emulation to prevent race conditions in the Windows clipboard
     synchronisation layer.

INVARIANT: Does NOT import pynput, linux.py, or check platform.system().
"""

import time
from typing import Callable

import keyboard as kb
import pyperclip

from platforms.base import PlatformAdapter


class WindowsAdapter(PlatformAdapter):
    """Windows-specific implementation of PlatformAdapter."""

    def __init__(self) -> None:
        self._registered_hotkeys: list[str] = []

    # ------------------------------------------------------------------
    # PlatformAdapter interface
    # ------------------------------------------------------------------

    def register_hotkeys(self, bindings: dict[str, Callable[[], None]]) -> None:
        """
        Register global hotkeys using the `keyboard` library.

        Parameters
        ----------
        bindings : {"alt+caps lock": cb1, "ctrl+caps lock": cb2, ...}

        Notes
        -----
        - `suppress=False` is critical: it prevents the `keyboard` hook from
          consuming the key event, which would prevent CapsLock from toggling
          if the user later presses it without the Alt modifier.
        - The `keyboard` library requires Administrator privileges on Windows,
          which the launcher (run_tll_voice.bat) guarantees via UAC elevation.
        """
        for hotkey_str, callback in bindings.items():
            kb.add_hotkey(hotkey_str, callback, suppress=False)
            self._registered_hotkeys.append(hotkey_str)
            print(f"[Windows] Hotkey registered: {hotkey_str}")

    def inject_text(self, text: str) -> None:
        """
        Copy text to clipboard, wait 0.05 s, then emulate Ctrl+V.

        The sleep is a hard requirement: Windows clipboard internals have
        a non-zero synchronisation latency. Without it, the Ctrl+V keystroke
        fires before the clipboard content is visible to the target process,
        resulting in pasting stale or empty content.
        """
        pyperclip.copy(text)
        time.sleep(0.05)           # ← mandatory Δt ≥ 0.05 s (race-condition guard)
        kb.press_and_release("ctrl+v")

    def cleanup(self) -> None:
        """Remove all hotkeys registered by this adapter."""
        try:
            kb.unhook_all_hotkeys()
            print(f"[Windows] Unhooked {len(self._registered_hotkeys)} hotkey(s).")
        except Exception as e:
            print(f"[Windows] Cleanup warning: {e}")
        self._registered_hotkeys.clear()
