# Системные инструкции для разработки TLL-Voice

Этот документ описывает технологический стек, архитектурные правила и стандарты качества для инкрементального развития TLL-Voice v0.4. Все будущие ИИ-агенты обязаны строго придерживаться этих инструкций.

---

## 1. Концепция проекта
**TLL-Voice** — фоновое утилитарное Windows/Linux-приложение на Python для голосового ввода с мгновенным форматированием через API Gemini. Упор делается на **максимальную асимметрию усилий**, минимальное потребление ОЗУ и высокую отзывчивость (latency).

---

## 2. Архитектура (v0.4 — Layered Core/Platform)

Проект разделён на три изолированных слоя:

```
TLL-Voice/
├── main.py                   # Bootstrapper (~35 строк). Определяет ОС, инжектирует адаптер.
├── core/                     # Ядро — инвариантно к ОС. ЗАПРЕЩЕНЫ keyboard/pynput/platform.system()
│   ├── state.py              # Константы состояний
│   ├── config.py             # load_config / save_config / run_onboarding_if_needed
│   ├── audio.py              # AudioRecorder (sounddevice, in-memory WAV)
│   ├── gemini.py             # GeminiClient (transcribe / synthesize)
│   ├── engine.py             # TLLVoiceEngine — главный оркестратор, получает адаптер через DI
│   └── gui/
│       ├── overlay.py        # Tkinter borderless overlay
│       └── tray.py           # pystray системный трей
└── platforms/                # Периферия — адаптеры ОС. Не знают друг о друге.
    ├── base.py               # PlatformAdapter (ABC): register_hotkeys / inject_text / cleanup
    ├── windows.py            # WindowsAdapter — использует ТОЛЬКО библиотеку `keyboard`
    └── linux.py              # LinuxAdapter — использует ТОЛЬКО `pynput`
```

### Инварианты (нарушать ЗАПРЕЩЕНО)

| Правило | Где проверять |
|---|---|
| `core/` не содержит `import keyboard`, `import pynput`, `platform.system()` | `Select-String -Path "core\*.py","core\gui\*.py" -Pattern "platform\.system\|import keyboard\|import pynput"` → только комментарии |
| `platforms/windows.py` использует ТОЛЬКО `keyboard`, не `pynput` | Grep windows.py |
| `platforms/linux.py` использует ТОЛЬКО `pynput`, не `keyboard` | Grep linux.py |
| Адаптеры не импортируют друг друга | windows.py не знает о linux.py и наоборот |
| `inject_text()` имеет `time.sleep(0.05)` до `Ctrl+V` | Оба адаптера |

---

## 3. Контракт взаимодействия (Dependency Injection)

```python
# Паттерн DI в main.py:
if platform.system() == "Windows":
    from platforms.windows import WindowsAdapter as _Adapter
else:
    from platforms.linux import LinuxAdapter as _Adapter

TLLVoiceEngine(root, config, adapter=_Adapter())
```

`TLLVoiceEngine` принимает `PlatformAdapter` и вызывает:
- `adapter.register_hotkeys({"alt+caps lock": cb1, "ctrl+caps lock": cb2, ...})`
- `adapter.inject_text(text)` — вставка результата в активное окно
- `adapter.cleanup()` — при выходе

---

## 4. Технологический стек

- **Язык**: Python 3.10+
- **Изоляция**: `.venv/` в корне проекта
- **Ключевые зависимости** (`requirements.txt`):
  - `google-generativeai` — SDK Gemini API
  - `sounddevice` + `numpy` — захват аудио (кроссплатформенно)
  - `keyboard>=0.13.5` — глобальные хоткеи **только для Windows** (требует прав Admin)
  - `pynput>=1.7.6` — глобальные хоткеи **только для Linux** + вставка текста
  - `pyperclip` — буфер обмена
  - `pystray` + `pillow` — системный трей
  - `tkinter` — оверлей GUI (только main thread!)

---

## 5. Правила многопоточности

1. Tkinter GUI **всегда** в главном потоке (Main Thread)
2. API-запросы и запись звука — в daemon threads
3. Все взаимодействия через `queue.Queue`, GUI опрашивает через `.after(50, poll_queue)`

---

## 6. Безопасность запуска (Windows)

- `pythonw.exe` запускается **только после** валидации `config.json`
- `run_tll_voice.bat` выполняет пре-флай проверку:
  1. UAC-повышение прав
  2. Проверка `config.json` через `python.exe`
  3. Если конфиг неполный → `python.exe main.py --setup` (интерактивный мастер)
  4. Только при валидном конфиге → `pythonw.exe main.py` (фон, без консоли)
- Первые строки `main.py` перенаправляют `stdout/stderr` в `os.devnull` если они `None`

---

## 7. Протокол валидации изменений

```powershell
# 1. Синтаксис всех модулей
$files = @("main.py","core\__init__.py","core\state.py","core\config.py","core\audio.py","core\gemini.py","core\engine.py","core\gui\__init__.py","core\gui\overlay.py","core\gui\tray.py","platforms\__init__.py","platforms\base.py","platforms\windows.py","platforms\linux.py")
foreach($f in $files){ .venv\Scripts\python.exe -m py_compile $f }

# 2. Инвариант изоляции ядра (допустимы только комментарии)
Select-String -Path "core\*.py","core\gui\*.py" -Pattern "platform\.system|import keyboard|from keyboard|import pynput|from pynput"
```

---

## 8. Правила конфигурации

- Конфиг строго в `config.json` в корне проекта
- `core/config.py::load_config()` — единственная точка чтения
- `core/config.py::save_config()` — атомарная запись через `.tmp`-файл

---

## 9. Дельта изменений (v0.4)

- **Архитектурный рефакторинг**: монолит `main.py` (~<844 строки) разбит на `core/` + `platforms/` + bootstrapper (~35 строк)
- **`platforms/windows.py`**: переписан на библиотеку `keyboard` (не pynput) — устранено залипание CapsLock при Alt+CapsLock
- **`platforms/linux.py`**: использует `pynput` (GlobalHotKeys)
- **Онбординг**: инкапсулирован в `core/config.py`, `run_tll_voice.bat` делает пре-флай проверку
- **`inject_text()`**: гарантированный `time.sleep(0.05)` в обоих адаптерах

---

## 10. Бэклог задач инкрементального расширения проекта 
**Только если Автор явно попросил перейти на "Бэклог задач", то: смотри [.agent/backlog_list.md](file://C:/Users/dede/.agent/backlog_list.md)**