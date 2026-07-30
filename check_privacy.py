# -*- coding: utf-8 -*-
"""
Сверка политики конфиденциальности со схемой базы.

Запуск локально (базы не касается, только читает схему и текст):
    python check_privacy.py

Отвечает на один вопрос: названа ли в политике каждая таблица
с пользовательскими данными. Прогонять при добавлении любой такой
таблицы — полный перечень обрабатываемых данных требует закон,
а забыть категорию легко: таблица объявляется в database.py,
а называть её нужно в тексте внутри main.py.

Так однажды и выпал целый инструмент: трекер Enshrouded не упоминался
в политике вовсе, хотя данные по нему хранились.

Проверка не судит формулировки, только наличие. Если текст переписан
и слово поменялось — поправьте PRIVACY_MENTIONS в database.py.
Код выхода 1 при расхождениях: годится для CI.
"""
import sys

from database import (check_privacy_coverage, PRIVACY_MENTIONS,  # noqa: E402
                      PRIVACY_NOT_PERSONAL, Base)
from main import STATIC_PAGES                                    # noqa: E402

политика = STATIC_PAGES.get("privacy", {}).get("content") or ""
if not политика:
    print("Текста политики нет — STATIC_PAGES['privacy']['content'] пуст.")
    raise SystemExit(1)

расхождения = check_privacy_coverage(политика)

print("Таблиц в схеме: %d, из них без персональных данных: %d"
      % (len(Base.metadata.tables), len(PRIVACY_NOT_PERSONAL)))
print("Проверено категорий: %d" % len(PRIVACY_MENTIONS))
for имя, причина in sorted(PRIVACY_NOT_PERSONAL.items()):
    print("  вне перечня: %-14s — %s" % (имя, причина))

print("")
if расхождения:
    print("РАСХОЖДЕНИЯ (%d):" % len(расхождения))
    for с in расхождения:
        print("  -", с)
    sys.exit(1)

print("Все таблицы с пользовательскими данными названы в политике.")
