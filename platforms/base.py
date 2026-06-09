"""
platforms/base.py
Abstract contract (PlatformAdapter) that every OS adapter must implement.
The Core layer depends ONLY on this interface — never on concrete adapters.
"""

from abc import ABC, abstractmethod
from typing import Callable


class PlatformAdapter(ABC):
    """
    Abstract base class defining the three invariant capabilities
    that any platform adapter must provide to the Core engine:

    1. register_hotkeys  — Input Hooking
    2. inject_text       — Output Injection
    3. cleanup           — Resource Release
    """

    @abstractmethod
    def register_hotkeys(self, bindings: dict[str, Callable[[], None]]) -> None:
        """
        Register global hotkeys.

        Parameters
        ----------
        bindings : dict mapping hotkey string → zero-arg callback.
                   Example: {"alt+caps lock": mode1_cb, "ctrl+caps lock": mode2_cb}

        Contract
        --------
        - Hotkeys must NOT block the key event from reaching other applications
          (suppress=False semantics on Windows).
        - Listener must run in a daemon thread so it doesn't prevent exit.
        """

    @abstractmethod
    def inject_text(self, text: str) -> None:
        """
        Insert text into the currently focused OS window.

        Contract
        --------
        - Must copy text to the system clipboard first.
        - Must enforce a minimum Δt ≥ 0.05 s between clipboard write and
          Ctrl+V keystroke emulation to prevent race conditions.
        """

    @abstractmethod
    def cleanup(self) -> None:
        """
        Release all OS-level hooks and resources acquired in register_hotkeys().
        Called once on application exit.
        """
