# -*- coding: utf-8 -*-
"""
Проверка отправок писем через Resend.

Запуск на проде:
    flyctl ssh console -a energydess-tools -C "python /app/check_emails.py"

Показывает: сколько писем отправлено, сколько принято Resend, разбивку сбоев
по кодам (no_key / timeout / http_<статус> / network / parse) и последние
отправки с их resend_id — по нему статус доставки виден в дашборде Resend.
Только чтение, ничего не меняет.
"""
import os
import sqlite3

БД = os.getenv("DB_PATH", "/data/app.db")
c = sqlite3.connect("file:%s?mode=ro" % БД, uri=True)
c.row_factory = sqlite3.Row

есть = c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='email_logs'").fetchone()
if not есть:
    print("Таблицы email_logs нет — приложение ещё не стартовало с новой версией.")
    raise SystemExit

всего = c.execute("SELECT COUNT(*) n FROM email_logs").fetchone()["n"]
if not всего:
    print("Отправок пока не было. Зарегистрируйте тестового пользователя.")
    raise SystemExit

ок = c.execute("SELECT COUNT(*) n FROM email_logs WHERE error IS NULL").fetchone()["n"]
сбоев = всего - ок

print("=" * 72)
print("ОТПРАВКА ПИСЕМ — СВОДКА")
print("=" * 72)
print("  всего попыток      : %d" % всего)
print("  принято Resend     : %d" % ок)
print("  сбоев              : %d" % сбоев)

print("\nПО ТИПАМ ПИСЕМ:")
for r in c.execute("""SELECT kind, COUNT(*) n,
                             SUM(CASE WHEN error IS NULL THEN 1 ELSE 0 END) ок
                      FROM email_logs GROUP BY kind ORDER BY n DESC"""):
    print("  %-10s всего %-4d принято %d" % (r["kind"], r["n"], r["ок"]))

if сбоев:
    print("\nСБОИ ПО КОДАМ:")
    for r in c.execute("""SELECT
            CASE WHEN INSTR(error, ':') > 0
                 THEN SUBSTR(error, 1, INSTR(error, ':') - 1)
                 ELSE error END код,
            COUNT(*) n
        FROM email_logs WHERE error IS NOT NULL
        GROUP BY код ORDER BY n DESC"""):
        print("  %-14s %d" % (r["код"], r["n"]))

    print("\nПОСЛЕДНИЕ СБОИ (детали):")
    for r in c.execute("""SELECT id, created_at, to_email, kind, error
                          FROM email_logs WHERE error IS NOT NULL
                          ORDER BY created_at DESC LIMIT 10"""):
        print("  #%-4s %s  %-32s %s" % (
            r["id"], str(r["created_at"])[:16], r["to_email"][:32], r["kind"]))
        print("        %s" % r["error"][:180])

print("\nПОСЛЕДНИЕ ОТПРАВКИ:")
print("  %-5s %-17s %-30s %-8s %s" % ("id", "когда", "кому", "тип", "resend_id / ошибка"))
print("  " + "-" * 94)
for r in c.execute("""SELECT id, created_at, to_email, kind, resend_id, error
                      FROM email_logs ORDER BY created_at DESC LIMIT 15"""):
    хвост = r["error"][:44] if r["error"] else (r["resend_id"] or "— (id не пришёл)")
    метка = "СБОЙ " if r["error"] else "OK   "
    print("  %s #%-3s %-17s %-30s %-8s %s" % (
        метка, r["id"], str(r["created_at"])[:16], r["to_email"][:30], r["kind"], хвост))

print("\nПодсказка: resend_id можно найти в дашборде Resend — там видно,")
print("доставлено письмо, отбито (bounced) или помечено спамом (complained).")
c.close()
