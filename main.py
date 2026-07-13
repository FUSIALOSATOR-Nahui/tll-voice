"""
main.py — TLL-Voice Bootstrapper (v0.6.4)

Single responsibility: determine the OS, inject the correct platform adapter
into the Core engine, and start the Tkinter event loop.

This file MUST remain under ~40 lines. All business logic lives in core/.
"""

import os
import sys
import platform
import tkinter as tk

# --- pythonw.exe safety (Windows windowless mode: stdout/stderr are None) ---
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

# --- Platform adapter selection (exactly once, at startup) ---
_os = platform.system()
if _os == "Windows":
    from platforms.windows import WindowsAdapter as _Adapter
elif _os == "Linux":
    from platforms.linux import LinuxAdapter as _Adapter
else:
    raise RuntimeError(f"Unsupported OS: {_os}. Only Windows and Linux are supported.")

# --- Core imports (platform-agnostic) ---
from core.config import load_config, run_onboarding_if_needed
from core.engine import TLLVoiceEngine

# --- Entry point ---
if __name__ == "__main__":
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    explicit_setup = "--setup" in sys.argv

    config = load_config(config_path)
    config = run_onboarding_if_needed(config, config_path, explicit=explicit_setup)

    root = tk.Tk()
    root.withdraw()  # Keep root window hidden; overlay manages its own visibility

    TLLVoiceEngine(root, config, adapter=_Adapter())
    root.mainloop()
