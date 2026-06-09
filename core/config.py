"""
core/config.py
Configuration loading, validation, and CLI onboarding.
INVARIANT: No imports of keyboard, pynput, or platform.system().
"""

import os
import sys
import json
import sounddevice as sd
from dotenv import load_dotenv

_DEFAULT_CONFIG = {
    "api_key": "YOUR_GEMINI_API_KEY",
    "model": "gemini-2.0-flash",
    "tts_model": "gemini-2.5-flash-preview-tts",
    "tts_pace": "1.75",
    "temperature": 0.3,
    "hotkeys": {
        "mode1": "alt+caps lock",
        "mode2": "ctrl+caps lock",
        "mode3": "ctrl+shift+caps lock",
    },
    "prompts": {"mode1": "", "mode2": "", "mode3": ""},
    "audio": {
        "sample_rate": 16000,
        "channels": 1,
        "device_index": None,
        "silence_threshold": 100,
    },
}


def _config_path(path=None):
    if path:
        return path
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json"
    )


def load_config(path=None):
    """Load config.json; fall back to defaults on any error."""
    # Load .env first so os.environ.get() works everywhere (Windows + Linux).
    # override=False: system env vars take priority over .env file.
    _env_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"
    )
    load_dotenv(dotenv_path=_env_path, override=False)

    fpath = _config_path(path)
    try:
        with open(fpath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[Config] Error loading config.json: {e}", file=sys.stderr)
        import copy
        return copy.deepcopy(_DEFAULT_CONFIG)


def save_config(config, path=None):
    """Atomically save config dict to config.json. Returns True on success."""
    fpath = _config_path(path)
    tmp = fpath + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        os.replace(tmp, fpath)
        return True
    except Exception as e:
        print(f"[Config] Error saving config.json: {e}", file=sys.stderr)
        return False


def needs_onboarding(config):
    """Return True if microphone has never been configured."""
    return config.get("audio", {}).get("device_index") is None


def run_onboarding(config, path=None):
    """
    Interactive CLI wizard to select a microphone.
    Updates config['audio']['device_index'] in-place and saves to disk.
    Returns updated config.
    """
    print("\n=== TLL-Voice: Microphone Setup / Nastrojka mikrofona ===")
    try:
        devices = sd.query_devices()
    except Exception as e:
        print(f"[Error] Cannot enumerate audio devices: {e}")
        return config

    input_devices = [
        (idx, dev["name"], dev["hostapi"])
        for idx, dev in enumerate(devices)
        if dev.get("max_input_channels", 0) > 0
    ]

    if not input_devices:
        print("[Error] No input audio devices found!")
        return config

    print("\nAvailable input devices:")
    for i, (idx, name, hostapi) in enumerate(input_devices):
        try:
            hostapi_name = sd.query_hostapis(hostapi)["name"]
        except Exception:
            hostapi_name = "Unknown API"
        print(f"  [{i}] ID {idx}: {name} ({hostapi_name})")

    # Detect default input device
    default_idx = -1
    try:
        default_idx = sd.default.device[0]
    except Exception:
        pass

    default_selection = 0
    for i, (idx, _name, _hostapi) in enumerate(input_devices):
        if idx == default_idx:
            default_selection = i
            break

    print(f"\nRecommended default device: [{default_selection}]")

    selected_idx = input_devices[default_selection][0]
    while True:
        try:
            choice = input(
                f"Select microphone number [0-{len(input_devices) - 1}]"
                f" (default={default_selection}): "
            ).strip()
            if not choice:
                break
            choice_val = int(choice)
            if 0 <= choice_val < len(input_devices):
                selected_idx = input_devices[choice_val][0]
                break
            print(f"Invalid number. Enter 0 to {len(input_devices) - 1}.")
        except ValueError:
            print("Please enter a valid number or press Enter for default.")
        except (KeyboardInterrupt, EOFError):
            print("\nSetup cancelled. Using default.")
            break

    if "audio" not in config:
        config["audio"] = {}
    config["audio"]["device_index"] = selected_idx

    if save_config(config, path):
        print(f"\n[OK] Microphone (ID {selected_idx}) saved to config.json!\n")
    return config


def run_onboarding_if_needed(config, path=None, explicit=False):
    """
    Runs the onboarding wizard when needed or explicitly requested.
    Encapsulates all setup-gate logic so launchers (bat/sh) stay dumb.

    IMPORTANT: This function expects to be called from python.exe (interactive),
    NOT from pythonw.exe (windowless). The run_tll_voice.bat handles this
    split: it calls python.exe --setup first, then pythonw.exe for background.
    """
    should_run = needs_onboarding(config) or explicit

    if not should_run:
        return config

    is_interactive = bool(sys.stdin and sys.stdin.isatty())

    if is_interactive:
        return run_onboarding(config, path)
    else:
        if explicit:
            print("Error: --setup requires an interactive terminal.", file=sys.stderr)
            sys.exit(1)
        else:
            print(
                "[Warning] No interactive terminal for onboarding. Using system defaults.",
                file=sys.stderr,
            )
        return config
