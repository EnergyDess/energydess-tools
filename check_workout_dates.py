# -*- coding: utf-8 -*-
"""ЧТО СТАЛО С ДАТАМИ ТРЕНИРОВОК ПОСЛЕ ПРАВКИ ПОЯСА (BACKLOG №186, C.4).

═══════════════════════════════════════════════════════════════════════
ЭТО НЕ ПРОВЕРКА И НЕ МИГРАЦИЯ

База открывается ТОЛЬКО НА ЧТЕНИЕ (`mode=ro`), код возврата ВСЕГДА 0.
Ничего не чинится и не переписывается: решение о чужих данных —
владельца, а не захода. Тот же приём, что у `check_medkit_opened.py`.

═══════════════════════════════════════════════════════════════════════
ЧТО СЧИТАЕТСЯ И ПОЧЕМУ ПРИЗНАК УЗКИЙ

До правки раздел брал день через `datetime.now()` — то есть в поясе
ПРОЦЕССА (на Fly это UTC). Подход, записанный в 01:30 по Москве, лёг
ВЧЕРАШНИМ числом.

Признак «дата уехала» ОБЯЗАН быть узким, иначе он объявит находкой
законное. Расхождение `log_date` с днём `created_at` бывает и по делу:

  · человек правит прошлый день — клиент шлёт `log_date` явно;
  · тренировка началась вчера и дописывается сегодня (сессия одна).

Поэтому подозрительной считается запись, у которой ОДНОВРЕМЕННО:

  1. `log_date` РОВНО на день меньше местного дня `created_at`
     (в другую сторону UTC уехать не может — он ПОЗАДИ местного,
     а не впереди);
  2. момент создания попал в окно расхождения: местное время
     от полуночи до величины смещения.

Вторая половина и есть то, что отличает дефект от правки прошлого дня:
правку делают днём, а не в 01:30.

ГРАНИЦА НАЗВАНА: доказать, что запись уехала ИМЕННО из-за пояса,
нечем — человек мог сознательно записать вчерашнюю тренировку в час
ночи. Поэтому печатается «СОВПАЛО С ОКНОМ», а не «испорчено».

═══════════════════════════════════════════════════════════════════════
ЧЕМ ГОНЯТЬ

    py check_workout_dates.py                    # локальная база
    DB_PATH=/data/app.db py check_workout_dates.py   # на Fly, через ssh
"""
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def пояс(имя):
    try:
        return ZoneInfo((имя or "").strip() or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def прогон(путь):
    c = sqlite3.connect("file:%s?mode=ro" % путь, uri=True)
    try:
        люди = {i: (tz or "UTC") for i, tz in
                c.execute("SELECT id, timezone FROM users")}
        строки = list(c.execute(
            "SELECT id, user_id, log_date, created_at, completed, skipped "
            "FROM workout_sessions ORDER BY id"))
        подходов = {s: n for s, n in c.execute(
            "SELECT session_id, COUNT(*) FROM set_logs GROUP BY session_id")}
    finally:
        c.close()

    всего = len(строки)
    расхождений, в_окне = [], []
    без_пояса = 0
    for sid, uid, log_date, created, completed, skipped in строки:
        if not created:
            continue
        зона = пояс(люди.get(uid))
        if зона.key == "UTC":
            без_пояса += 1
        # `created_at` пишется НАИВНЫМ UTC (`datetime.utcnow`), поэтому
        # пояс ему приписывается явно. `astimezone` на наивном моменте
        # взял бы пояс МАШИНЫ — та же ловушка, что чинила §12131
        момент = datetime.fromisoformat(created).replace(tzinfo=timezone.utc)
        местный = момент.astimezone(зона)
        день_utc = момент.date().isoformat()
        день_местный = местный.date().isoformat()
        if log_date == день_местный:
            continue
        расхождений.append((sid, uid, log_date, день_местный, день_utc))
        # ОКНО РАСХОЖДЕНИЯ: местный день ушёл вперёд UTC, а запись
        # легла по UTC — ровно то, что делал прежний код
        if (log_date == день_utc and день_utc != день_местный
                and местный.date() - момент.date() == timedelta(days=1)):
            в_окне.append((sid, uid, log_date, день_местный,
                           местный.strftime("%H:%M"), зона.key,
                           подходов.get(sid, 0), bool(completed),
                           bool(skipped)))

    print("═" * 70)
    print("ДАТЫ ТРЕНИРОВОК: %s" % os.path.abspath(путь))
    print("═" * 70)
    print("тренировок всего:                 %d" % всего)
    print("у пользователей без пояса (UTC):  %d  — у них расхождения быть "
          "не может по построению" % без_пояса)
    print("log_date не равен местному дню:   %d" % len(расхождений))
    print("из них СОВПАЛО С ОКНОМ пояса:     %d" % len(в_окне))
    if в_окне:
        print()
        print("  %-6s %-6s %-11s %-11s %-6s %-18s %s"
              % ("id", "чей", "лежит в", "местный был", "время", "пояс",
                 "подходов"))
        for sid, uid, лежит, местный, время, зона, n, зав, проп in в_окне:
            print("  %-6d %-6d %-11s %-11s %-6s %-18s %d%s"
                  % (sid, uid, лежит, местный, время, зона, n,
                     " (пропущена)" if проп else
                     ("" if зав else " (открыта)")))
        print()
        print("НИЧЕГО НЕ ИСПРАВЛЕНО И НЕ БУДЕТ: доказать, что запись уехала")
        print("именно из-за пояса, нечем — человек мог сознательно записать")
        print("вчерашнюю тренировку в час ночи. Решение за владельцем.")
    else:
        print()
        print("Записей, попавших в окно, нет — править нечего.")
    return 0


if __name__ == "__main__":
    sys.exit(прогон(os.getenv("DB_PATH", "app.db")))
