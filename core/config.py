"""
core/config.py
Configuration loading, validation, and CLI onboarding.
INVARIANT: No imports of keyboard, pynput, or platform.system().
"""

import os
import sys
import json
from pathlib import Path
import sounddevice as sd
from dotenv import load_dotenv

_DEFAULT_PROMPTS = {
    "mode1": "Ты — высокоточный ИИ-редактор устной речи. Исправляй грамматику и запинки, сохраняя 100% смысла.",
    "mode2": "Ты — инструмент буквальной транскрипции (Audio-to-Text). Расставь только точки и запятые для читаемости.",
    "mode3": "Ты — профессиональный диктор. Озвучь предоставленный текст."
}

_DEFAULT_CONFIG = {
    "api_key": "YOUR_GEMINI_API_KEY",
    "model": "gemini-3.1-flash-lite",
    "tts_model": "gemini-3.1-flash-lite",
    "tts_pace": "1.75",
    "temperature": 0.3,
    "hotkeys": {
        "mode1": "alt+caps lock",
        "mode2": "ctrl+caps lock",
        "mode3": "ctrl+shift+caps lock",
    },
    "modes": ["mode1", "mode2", "mode3"],
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
    """Load config.json; raise error on bad JSON or return config."""
    # Load .env first so os.environ.get() works everywhere (Windows + Linux).
    # override=False: system env vars take priority over .env file.
    project_root = Path(__file__).resolve().parent.parent
    _env_path = project_root / ".env"
    if _env_path.exists():
        load_dotenv(dotenv_path=str(_env_path), override=False)

    fpath = _config_path(path)
    if not os.path.exists(fpath):
        import copy
        cfg = copy.deepcopy(_DEFAULT_CONFIG)
    else:
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except json.JSONDecodeError as jde:
            print("\n" + "="*60, file=sys.stderr)
            print(f"[FATAL] JSON Syntax Error in config.json at line {jde.lineno}, column {jde.colno}:", file=sys.stderr)
            print(f"  {jde.msg}", file=sys.stderr)
            print("Please fix the syntax error (check commas, quotes, and braces).", file=sys.stderr)
            print("="*60 + "\n", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"[Config] Ошибка чтения config.json: {e}", file=sys.stderr)
            import copy
            cfg = copy.deepcopy(_DEFAULT_CONFIG)

    # Pre-flight check and prompt files auto-creation/verification
    prompts_dir = project_root / "prompts"
    if not prompts_dir.exists():
        try:
            prompts_dir.mkdir(parents=True, exist_ok=True)
        except Exception as err:
            print(f"[Config] Не удалось создать папку prompts/: {err}", file=sys.stderr)

    modes = cfg.get("modes", ["mode1", "mode2", "mode3"])
    for m in modes:
        pfile = prompts_dir / f"{m}.md"
        if not pfile.exists():
            try:
                content = ""
                if m == "mode1":
                    sys_prompt_path = project_root / "system-promt.md"
                    if sys_prompt_path.exists():
                        content = sys_prompt_path.read_text(encoding="utf-8")
                if not content:
                    content = _DEFAULT_PROMPTS.get(m, "")
                pfile.write_text(content, encoding="utf-8")
            except Exception as write_err:
                print(f"[Config] Ошибка записи промпта по умолчанию для {m}: {write_err}", file=sys.stderr)
        else:
            # Pre-flight readability verification
            try:
                pfile.read_text(encoding="utf-8")
            except Exception as read_err:
                print("\n" + "="*60, file=sys.stderr)
                print(f"[FATAL] Ошибка доступа к файлу промпта {pfile}: {read_err}", file=sys.stderr)
                print("Убедитесь, что у процесса есть права на чтение файлов в папке prompts/.", file=sys.stderr)
                print("="*60 + "\n", file=sys.stderr)
                sys.exit(1)

    return cfg


def load_prompt_by_mode(mode: str) -> tuple[str, str | None]:
    """
    Load and return prompt content from prompts/{mode}.md.
    If file is empty or missing, returns safe fallback.
    Returns: (system_instruction, user_prompt)
    """
    project_root = Path(__file__).resolve().parent.parent
    filepath = project_root / "prompts" / f"{mode}.md"
    try:
        if filepath.exists():
            content = filepath.read_text(encoding="utf-8").strip()
            if content:
                if "===" in content:
                    parts = content.split("===", 1)
                    sys_inst = parts[0].strip()
                    usr_pr = parts[1].strip()
                    return sys_inst, (usr_pr if usr_pr else None)
                return content, None
    except Exception as e:
        print(f"[Config] Ошибка при чтении файла промпта {filepath}: {e}", file=sys.stderr)

    fallbacks = {
        "mode1": "Ты — голосовой ассистент, переведи аудио в текст без изменений.",
        "mode2": "Ты — инструмент буквальной транскрипции (Audio-to-Text). Выдавай чистый транскрибированный текст.",
        "mode3": "Ты — профессиональный диктор. Озвучь предоставленный текст."
    }
    return fallbacks.get(mode, "Ты — голосовой ассистент, переведи аудио в текст без изменений."), None


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
