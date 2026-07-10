@echo off
title TLL-Voice Launcher
color 0b

:: ============================================================
:: Step 1: Ensure Administrator privileges (keyboard lib requires it)
:: ============================================================
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [INFO] Requesting Administrator privileges...
    powershell -Command "Start-Process '%~dpnx0' -Verb RunAs"
    exit /b
)

:: Set working directory to script location
cd /d "%~dp0"

echo ====================================================
echo  TLL-Voice v0.5.3 Launcher
echo ====================================================

:: ============================================================
:: Step 2: Pre-flight config check
:: Validate that config.json exists AND has a device_index set.
:: If not — run interactive setup in this console window FIRST.
:: Only after a valid config do we hand off to pythonw.exe (no console).
:: ============================================================

.venv\Scripts\python.exe -c ^
  "import json,sys,os; ^
   f=os.path.join(os.path.dirname(os.path.abspath('.')), 'config.json'); ^
   f='config.json'; ^
   d=(json.load(open(f,'r',encoding='utf-8')) if os.path.exists(f) else {}); ^
   sys.exit(0 if d.get('audio',{}).get('device_index') is not None else 1)" 2>nul

if %errorlevel% neq 0 (
    echo.
    echo [SETUP] First run detected or microphone not configured.
    echo [SETUP] Starting interactive setup wizard...
    echo.
    .venv\Scripts\python.exe main.py --setup
    if %errorlevel% neq 0 (
        echo.
        echo [ERROR] Setup failed or was cancelled. Please re-run the launcher.
        pause
        exit /b 1
    )
    echo.
    echo [OK] Setup complete. Launching TLL-Voice in background...
    echo.
) else (
    echo [OK] Configuration valid. Launching TLL-Voice in background...
)

:: ============================================================
:: Step 3: Launch in windowless background mode
:: pythonw.exe has no console — safe because config is validated above.
:: ============================================================
start "" ".venv\Scripts\pythonw.exe" main.py

echo.
echo [SUCCESS] TLL-Voice is running in the background.
echo Hotkeys:
echo   Alt  + Caps Lock         ^> Smart Editor (mode 1)
echo   Ctrl + Caps Lock         ^> Literal Transcription (mode 2)
echo   Ctrl + Shift + Caps Lock ^> Text-to-Speech (mode 3)
echo.
echo You can close this window.
timeout /t 5
exit
