#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
update_version.py — Скрипт автоматического обновления версии проекта TLL-Voice.
Использование: python update_version.py 0.5.4
"""

import sys
import re
from pathlib import Path

def update_file_content(filepath: Path, pattern: str, replacement: str) -> bool:
    if not filepath.exists():
        print(f"[Warn] Файл {filepath} не найден. Пропуск.")
        return False
    try:
        content = filepath.read_text(encoding="utf-8")
        new_content, count = re.subn(pattern, replacement, content)
        if count > 0:
            filepath.write_text(new_content, encoding="utf-8")
            print(f"[OK] {filepath.name}: обновлено вхождений — {count}")
            return True
        else:
            print(f"[Info] {filepath.name}: совпадений не найдено. Файл не изменен.")
            return False
    except Exception as e:
        print(f"[Error] Ошибка при обработке {filepath.name}: {e}")
        return False

def main():
    if len(sys.argv) < 2:
        print("Использование: python update_version.py <новая_версия>")
        print("Пример: python update_version.py 0.5.4")
        sys.exit(1)

    new_version = sys.argv[1].strip()
    # Валидация формата версии (x.y.z)
    if not re.match(r"^\d+\.\d+\.\d+$", new_version):
        print(f"[Error] Неверный формат версии: '{new_version}'. Ожидается формат x.y.z")
        sys.exit(1)

    project_root = Path(__file__).resolve().parent

    print(f"Запуск обновления версии проекта до v{new_version}...\n")

    # 1. Обновление в main.py
    main_path = project_root / "main.py"
    update_file_content(
        filepath=main_path,
        pattern=r"TLL-Voice Bootstrapper \(v\d+\.\d+\.\d+\)",
        replacement=f"TLL-Voice Bootstrapper (v{new_version})"
    )

    # 2. Обновление в run_tll_voice.bat
    bat_path = project_root / "run_tll_voice.bat"
    update_file_content(
        filepath=bat_path,
        pattern=r"TLL-Voice v\d+\.\d+\.\d+ Launcher",
        replacement=f"TLL-Voice v{new_version} Launcher"
    )

    # 3. Обновление в .agent/AGENTS.md
    agents_path = project_root / ".agent" / "AGENTS.md"
    if agents_path.exists():
        # Обновляем версию развития
        update_file_content(
            filepath=agents_path,
            pattern=r"TLL-Voice v\d+\.\d+\.\d+\.",
            replacement=f"TLL-Voice v{new_version}."
        )
        # Обновляем версию архитектуры
        update_file_content(
            filepath=agents_path,
            pattern=r"Architecture \(v\d+\.\d+\.\d+",
            replacement=f"Architecture (v{new_version}"
        )
        # Обновляем версию в заголовке дельты изменений
        update_file_content(
            filepath=agents_path,
            pattern=r"## 12\. Дельта изменений \(v\d+\.\d+\.\d+\)",
            replacement=f"## 12. Дельта изменений (v{new_version})"
        )

    print("\n[Успешно] Все операции завершены.")

if __name__ == "__main__":
    main()
