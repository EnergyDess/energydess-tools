# -*- coding: utf-8 -*-
"""
Снимает согласованную копию боевой базы. Запускается ВНУТРИ контейнера:

    flyctl ssh console -a energydess-tools -C "python /app/make_backup.py"

Печатает в stdout строку BACKUP_JSON={...} — её разбирает workflow, чтобы
подставить статистику в подпись к файлу в Telegram.

Почему не копирование файла: копировать app.db под нагрузкой нельзя — можно
поймать копию посреди транзакции и получить битую базу, которая выглядит
целой. sqlite3.Connection.backup() — тот же механизм, что у команды .backup
в CLI: держит блокировку правильно и копирует страницы согласованно, даже
если приложение в этот момент пишет.

Никаких зависимостей: в образе нет ни sqlite3 CLI, ни gpg. Шифрование
делается снаружи, в GitHub Actions.
"""
import json
import os
import sqlite3
import sys
from datetime import datetime

DB_PATH = os.getenv("DB_PATH", "/data/app.db")
BACKUP_DIR = "/data/backup"

# Таблицы для сверки при восстановлении: если их счётчики совпадут с боевыми,
# бэкап заведомо не обрезан
КЛЮЧЕВЫЕ = ["users", "cover_letters", "food_logs", "weight_logs",
            "chat_messages", "enshrouded_slots", "workout_programs", "email_logs"]


def main():
    if not os.path.exists(DB_PATH):
        print("ОШИБКА: база не найдена:", DB_PATH, file=sys.stderr)
        return 1

    os.makedirs(BACKUP_DIR, exist_ok=True)
    имя = "app-%s.db" % datetime.utcnow().strftime("%Y-%m-%d")
    путь = os.path.join(BACKUP_DIR, имя)
    if os.path.exists(путь):
        os.remove(путь)          # повторный запуск в тот же день перезаписывает

    # ── Согласованная копия ──────────────────────────────────────────────
    источник = sqlite3.connect("file:%s?mode=ro" % DB_PATH, uri=True)
    приёмник = sqlite3.connect(путь)
    try:
        источник.backup(приёмник)
    finally:
        приёмник.close()
        источник.close()

    # ── Проверка целостности ─────────────────────────────────────────────
    # Битый бэкап хуже отсутствующего: он создаёт ложное спокойствие.
    # Не прошёл проверку — не отправляем
    проверка = sqlite3.connect(путь)
    try:
        итог = проверка.execute("PRAGMA integrity_check").fetchone()[0]
        if итог != "ok":
            print("ОШИБКА: integrity_check не пройден:", итог, file=sys.stderr)
            os.remove(путь)
            return 1
        счётчики = {}
        for т in КЛЮЧЕВЫЕ:
            try:
                счётчики[т] = проверка.execute("SELECT COUNT(*) FROM %s" % т).fetchone()[0]
            except sqlite3.Error:
                счётчики[т] = None
    finally:
        проверка.close()

    размер = os.path.getsize(путь)
    print("BACKUP_JSON=" + json.dumps({
        "file": имя,
        "path": путь,
        "bytes": размер,
        "integrity": "ok",
        "counts": счётчики,
        "created_utc": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
