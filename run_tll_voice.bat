@echo off
title TLL-Voice Launcher
color 0b

:: Check for Administrative privileges
net session >nul 2>&1
if %errorLevel% == 0 (
    echo ====================================================
    echo [OK] Запущено с правами Администратора.
    echo ====================================================
) else (
    echo ====================================================
    echo [INFO] Запрос прав Администратора...
    echo ====================================================
    powershell -Command "Start-Process '%~dpnx0' -Verb RunAs"
    exit /b
)

:: Set working directory to the folder containing this batch script
cd /d "%~dp0"

:: Start the application in the background using pythonw (no terminal window)
echo [STARTING] Запуск TLL-Voice в фоновом режиме...
start "" ".venv\Scripts\pythonw.exe" main.py

if %errorLevel% == 0 (
    echo [SUCCESS] Приложение TLL-Voice успешно запущено!
    echo Вы можете закрыть это окно. Горячие клавиши активны:
    echo Alt + Caps Lock - Умный Редактор
    echo Ctrl + Caps Lock - Буквальная транскрипция
) else (
    echo [ERROR] Не удалось запустить приложение.
)

timeout /t 5
exit
