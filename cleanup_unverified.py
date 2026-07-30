# -*- coding: utf-8 -*-
"""Удаляет неподтверждённых пользователей (is_verified=False) старше 7 дней —
защита от накопления bot-регистраций, которые прошли Turnstile (или были
созданы до его подключения) но так и не подтвердили email.

Ничего не трогает у явно верифицированных (is_verified=True) и у "старых"
аккаунтов с is_verified=NULL (ретроактивно проставлены True миграцией,
см. database.py migrate_db()) — под удаление попадают только явные False.

Удаление идёт через delete_user_cascade: раньше скрипт чистил только users
и resumes, оставляя данные в двух десятках таблиц. SQLite переиспользует
освободившиеся id, поэтому новый пользователь мог унаследовать чужие письма
и дневник (BACKLOG №11).

Запуск по расписанию: последним шагом в .github/workflows/backup.yml, раз
в сутки сразу после отправки архива. Порядок именно такой, потому что архив
этого дня — единственная страховка, если порог или сам скрипт однажды
окажутся неправы. Упал бэкап — удаления в этот день не будет.

Вручную:
    python cleanup_unverified.py [--dry-run]

--dry-run — посчитать и показать отчёт по таблицам, ничего не удаляя.
Ручной запуск workflow по умолчанию тоже идёт в --dry-run: проверка
«работает ли задача» не должна стоить кому-то аккаунта.
"""
import sys
from datetime import datetime, timedelta

from dotenv import load_dotenv
load_dotenv()

from database import (SessionLocal, User, delete_user_cascade,  # noqa: E402
                      check_user_tables_complete)

DAYS_THRESHOLD = 7


def main():
    dry_run = "--dry-run" in sys.argv
    cutoff = datetime.utcnow() - timedelta(days=DAYS_THRESHOLD)

    # Список таблиц в delete_user_cascade устареет в день, когда добавится новая
    # модель с user_id. Проверяем до удаления, а не после
    забыты = check_user_tables_complete()
    if забыты:
        print("ОСТАНОВЛЕНО: в каскаде не учтены таблицы:", ", ".join(забыты))
        print("Добавьте их в USER_TABLES в database.py, иначе останутся сироты.")
        return

    db = SessionLocal()
    try:
        stale = db.query(User).filter(
            User.is_verified == False,  # noqa: E712 — явный False, не NULL
            User.created_at < cutoff,
        ).all()
        if not stale:
            print("Неподтверждённых аккаунтов старше %d дней не найдено." % DAYS_THRESHOLD)
            return
        цели = [(u.id, u.email, (datetime.utcnow() - u.created_at).days) for u in stale]
    finally:
        db.close()

    print("Найдено %d неподтверждённых аккаунтов старше %d дней:" % (len(цели), DAYS_THRESHOLD))
    for _, email, дней in цели:
        print("  — %s (создан %d дн. назад)" % (email, дней))

    # Отчёт по таблицам: сколько и где будет удалено. Когда эту же функцию
    # позовёт кнопка «Удалить аккаунт», такой отчёт станет последней проверкой
    # перед необратимым действием
    итог = {}
    for uid, _, _ in цели:
        for таблица, n in delete_user_cascade(uid, dry_run=True).items():
            итог[таблица] = итог.get(таблица, 0) + n

    print("")
    print("Будет затронуто записей:")
    непусто = {т: n for т, n in итог.items() if n}
    for таблица, n in sorted(непусто.items(), key=lambda x: -x[1]):
        print("  %-34s %d" % (таблица, n))
    if len(непусто) <= 1:
        print("  (кроме самих аккаунтов данных за ними нет)")

    if dry_run:
        print("")
        print("--dry-run: ничего не удалено.")
        return

    удалено = 0
    for uid, email, _ in цели:
        try:
            delete_user_cascade(uid)
            удалено += 1
        except Exception as e:
            # Один сбойный аккаунт не должен останавливать остальные: его
            # удаление откатится целиком внутри delete_user_cascade
            print("  ОШИБКА на %s: %s: %s" % (email, type(e).__name__, e))
    print("")
    print("Удалено пользователей: %d из %d" % (удалено, len(цели)))


if __name__ == "__main__":
    main()
