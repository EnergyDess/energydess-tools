# -*- coding: utf-8 -*-
"""
Проверка сбоев анализа вакансии в истории писем.

Запуск на проде:
    flyctl ssh console -a energydess-tools -C "python /app/check_analysis.py"

Показывает: сколько писем всего, у скольких анализ отработал, и разбивку
сбоев по кодам (timeout / http_<статус> / truncated / parse / empty).
Только чтение, ничего не меняет.
"""
import os
import sqlite3

БД = os.getenv("DB_PATH", "/data/app.db")
c = sqlite3.connect("file:%s?mode=ro" % БД, uri=True)
c.row_factory = sqlite3.Row

всего = c.execute("SELECT COUNT(*) n FROM cover_letters").fetchone()["n"]
если_нет = "Писем пока нет — сгенерируйте хотя бы одно."
if not всего:
    print(если_нет)
    raise SystemExit

ок = c.execute("""SELECT COUNT(*) n FROM cover_letters
                  WHERE analysis_error IS NULL
                    AND analysis_json IS NOT NULL AND analysis_json <> 'null'""").fetchone()["n"]
сбоев = c.execute("SELECT COUNT(*) n FROM cover_letters WHERE analysis_error IS NOT NULL").fetchone()["n"]
старых = всего - ок - сбоев

print("=" * 66)
print("АНАЛИЗ ВАКАНСИИ — СВОДКА")
print("=" * 66)
print("  всего писем              : %d" % всего)
print("  анализ отработал         : %d" % ок)
print("  анализ упал (есть код)   : %d" % сбоев)
if старых:
    print("  до появления учёта причин: %d  (записи старше 26.07.2026)" % старых)

if сбоев:
    print("\nСБОИ ПО КОДАМ:")
    for r in c.execute("""SELECT
            CASE WHEN INSTR(analysis_error, ':') > 0
                 THEN SUBSTR(analysis_error, 1, INSTR(analysis_error, ':') - 1)
                 ELSE analysis_error END код,
            COUNT(*) n
        FROM cover_letters WHERE analysis_error IS NOT NULL
        GROUP BY код ORDER BY n DESC"""):
        print("  %-14s %d" % (r["код"], r["n"]))

    print("\nПОСЛЕДНИЕ СБОИ (детали):")
    for r in c.execute("""SELECT id, created_at, LENGTH(job_text) L, analysis_error
                          FROM cover_letters WHERE analysis_error IS NOT NULL
                          ORDER BY created_at DESC LIMIT 10"""):
        print("  #%-4s %s  вакансия %5d симв" % (r["id"], str(r["created_at"])[:16], r["L"]))
        print("        %s" % r["analysis_error"][:150])

print("\nПОСЛЕДНИЕ ПИСЬМА:")
for r in c.execute("""SELECT id, created_at, COALESCE(job_title,'') jt, COALESCE(company_name,'') cn,
                             LENGTH(job_text) L, analysis_error
                      FROM cover_letters ORDER BY created_at DESC LIMIT 12"""):
    заг = " — ".join(x for x in (r["jt"], r["cn"]) if x) or "‹Без названия›"
    метка = "OK   " if not r["analysis_error"] else "СБОЙ "
    print("  %s #%-4s %s  %5d симв  %s" % (
        метка, r["id"], str(r["created_at"])[:16], r["L"], заг[:48]))

c.close()
