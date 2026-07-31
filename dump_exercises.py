# -*- coding: utf-8 -*-
"""
Выгрузка и восстановление справочника упражнений.

Зачем отдельно от общего бэкапа. В `exercises` лежит слой, который нельзя
воссоздать из репозитория: 852 значения `youtube_id` — результат импорта,
шедшего несколько дней и упиравшегося во внешние ограничения. Общий архив
базы его защищает, но восстановление из него возвращает базу целиком,
то есть чинить справочник пришлось бы ценой отката всех пользовательских
данных. Здесь — отдельный файл, который импортируется поверх живой базы
и трогает только `exercises` (BACKLOG №21, вариант Б).

Выгрузка (локально, из копии базы или с прода через sftp):
    python dump_exercises.py --dump

Восстановление ТОЛЬКО справочника, пользовательские данные не трогаются:
    python dump_exercises.py --restore backups/exercises/exercises-2026-07-31.json

Проверка без записи — что лежит в файле и чем отличается от базы:
    python dump_exercises.py --restore <файл> --dry-run

Персональных данных в справочнике нет: проверено по схеме (ни одного поля
с привязкой к пользователю) и по содержимому. Поэтому файл спокойно
кладётся в репозиторий — там он переживёт смерть тома, ради чего всё
и затевалось.
"""
import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

# Каталог намеренно не в корне и не рядом с exercises_seed.json: два файла
# про упражнения в одном месте однажды перепутают, и импорт устаревшего
# затрёт результат импорта видео
КАТАЛОГ = os.path.join("backups", "exercises")

# Поля, которые переносим. Список явный, а не SELECT *: добавится колонка —
# лучше узнать об этом от проверки ниже, чем молча возить лишнее
ПОЛЯ = [
    "id", "name", "name_ru", "force", "level", "mechanic", "equipment",
    "equipment_cluster", "primary_muscles", "secondary_muscles",
    "instructions", "instructions_ru", "category", "images",
    "youtube_id", "video_status", "video_replaced_at",
]


def _db_path():
    return os.getenv("DB_PATH", "./app.db")


def _проверить_поля(conn):
    """Схема могла уйти вперёд списка ПОЛЯ. Молча потерять колонку при
    выгрузке — то же самое, что не иметь бэкапа этой колонки вовсе."""
    в_базе = {r[1] for r in conn.execute("PRAGMA table_info(exercises)")}
    забыты = в_базе - set(ПОЛЯ)
    if забыты:
        print("ОСТАНОВЛЕНО: в таблице есть колонки, которых нет в ПОЛЯ:",
              ", ".join(sorted(забыты)))
        print("Добавьте их в ПОЛЯ в dump_exercises.py, иначе выгрузка неполная.")
        return False
    лишние = set(ПОЛЯ) - в_базе
    if лишние:
        print("ОСТАНОВЛЕНО: в ПОЛЯ перечислены несуществующие колонки:",
              ", ".join(sorted(лишние)))
        return False
    return True


def выгрузить():
    conn = sqlite3.connect("file:%s?mode=ro" % _db_path(), uri=True)
    try:
        if not _проверить_поля(conn):
            return 1
        строки = conn.execute(
            "SELECT %s FROM exercises ORDER BY id" % ", ".join(ПОЛЯ)).fetchall()
        записи = [dict(zip(ПОЛЯ, r)) for r in строки]
        # datetime не сериализуется в JSON сам
        for з in записи:
            if з.get("video_replaced_at") is not None:
                з["video_replaced_at"] = str(з["video_replaced_at"])
    finally:
        conn.close()

    с_видео = sum(1 for з in записи if з.get("youtube_id"))
    статусы = {}
    for з in записи:
        статусы[з.get("video_status")] = статусы.get(з.get("video_status"), 0) + 1

    os.makedirs(КАТАЛОГ, exist_ok=True)
    имя = "exercises-%s.json" % datetime.now(timezone.utc).strftime("%Y-%m-%d")
    путь = os.path.join(КАТАЛОГ, имя)

    # Структура — объект с метаданными, а не голый список. Это защита
    # от путаницы: exercises_seed.json является списком, и код, который
    # читает seed, на этом файле упадёт сразу, а не примет его молча
    документ = {
        "формат": "energydess-exercises-backup",
        "версия": 1,
        "назначение": "Снимок справочника упражнений для восстановления "
                      "поверх живой базы. НЕ является seed-файлом: "
                      "первичное наполнение делается из exercises_seed.json.",
        "снят_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "источник": _db_path(),
        "счётчики": {
            "всего": len(записи),
            "с_youtube_id": с_видео,
            "по_статусам": статусы,
        },
        "восстановить": "python dump_exercises.py --restore %s" % путь,
        "упражнения": записи,
    }
    with open(путь, "w", encoding="utf-8") as f:
        json.dump(документ, f, ensure_ascii=False, indent=1)

    размер = os.path.getsize(путь)
    print("Выгружено: %s" % путь)
    print("  упражнений:   %d" % len(записи))
    print("  с youtube_id: %d" % с_видео)
    print("  по статусам:  %s" % ", ".join("%s=%d" % кв for кв in sorted(статусы.items())))
    print("  размер:       %.2f МБ" % (размер / 1048576))
    return 0


def восстановить(путь, dry_run=False):
    if not os.path.exists(путь):
        print("Файла нет:", путь)
        return 1
    with open(путь, encoding="utf-8") as f:
        документ = json.load(f)

    # Явная проверка формата: если кто-то подсунет exercises_seed.json,
    # он получит внятный отказ, а не затёртый справочник
    if not isinstance(документ, dict) or документ.get("формат") != "energydess-exercises-backup":
        print("ОСТАНОВЛЕНО: это не выгрузка справочника.")
        print("Ожидался объект с полем «формат»: energydess-exercises-backup.")
        print("Похоже на seed-файл (exercises_seed.json) — он для первичного")
        print("наполнения пустой базы и НЕ содержит youtube_id.")
        return 1

    записи = документ["упражнения"]
    conn = sqlite3.connect(_db_path())
    try:
        if not _проверить_поля(conn):
            return 1
        было = conn.execute("SELECT COUNT(*) FROM exercises").fetchone()[0]
        было_видео = conn.execute(
            "SELECT COUNT(*) FROM exercises WHERE youtube_id IS NOT NULL "
            "AND youtube_id <> ''").fetchone()[0]

        print("В файле:  %d упражнений, %d с youtube_id (снят %s)"
              % (len(записи), документ["счётчики"]["с_youtube_id"],
                 документ.get("снят_utc", "?")))
        print("В базе:   %d упражнений, %d с youtube_id" % (было, было_видео))

        if dry_run:
            в_базе = {r[0] for r in conn.execute("SELECT id FROM exercises")}
            в_файле = {з["id"] for з in записи}
            print("")
            print("--dry-run, ничего не записано:")
            print("  появится новых: %d" % len(в_файле - в_базе))
            print("  исчезнет из базы: %d (НЕ удаляются, импорт только "
                  "добавляет и обновляет)" % len(в_базе - в_файле))
            return 0

        # Одной транзакцией: полусостояние справочника хуже старого справочника
        conn.execute("BEGIN")
        плейсхолдеры = ", ".join("?" * len(ПОЛЯ))
        обновления = ", ".join("%s = excluded.%s" % (п, п) for п in ПОЛЯ if п != "id")
        for з in записи:
            conn.execute(
                "INSERT INTO exercises (%s) VALUES (%s) "
                "ON CONFLICT(id) DO UPDATE SET %s"
                % (", ".join(ПОЛЯ), плейсхолдеры, обновления),
                [json.dumps(з[п], ensure_ascii=False)
                 if isinstance(з[п], (list, dict)) else з[п] for п in ПОЛЯ],
            )
        conn.commit()

        стало = conn.execute("SELECT COUNT(*) FROM exercises").fetchone()[0]
        стало_видео = conn.execute(
            "SELECT COUNT(*) FROM exercises WHERE youtube_id IS NOT NULL "
            "AND youtube_id <> ''").fetchone()[0]
        print("")
        print("Готово: %d упражнений, %d с youtube_id" % (стало, стало_видео))
    except Exception as e:
        conn.rollback()
        print("ОШИБКА, откат: %s: %s" % (type(e).__name__, e))
        return 1
    finally:
        conn.close()
    return 0


def main():
    p = argparse.ArgumentParser(description="Выгрузка/восстановление справочника упражнений")
    p.add_argument("--dump", action="store_true", help="выгрузить справочник в файл")
    p.add_argument("--restore", metavar="ФАЙЛ", help="импортировать справочник из файла")
    p.add_argument("--dry-run", action="store_true", help="с --restore: только показать разницу")
    a = p.parse_args()
    if a.dump:
        return выгрузить()
    if a.restore:
        return восстановить(a.restore, a.dry_run)
    p.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
