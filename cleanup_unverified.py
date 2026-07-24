# -*- coding: utf-8 -*-
"""Удаляет неподтверждённых пользователей (is_verified=False) старше 7 дней —
защита от накопления bot-регистраций, которые прошли Turnstile (или были
созданы до его подключения) но так и не подтвердили email.

Ничего не трогает у явно верифицированных (is_verified=True) и у "старых"
аккаунтов с is_verified=NULL (ретроактивно проставлены True миграцией,
см. database.py migrate_db()) — под удаление попадают только явные False.

Запускать вручную:
    python cleanup_unverified.py [--dry-run]

--dry-run — только посчитать и вывести, кто попал бы под удаление, ничего не удалять.

Пока запускается вручную раз в неделю. Позже — вынести в GitHub Actions cron
(по аналогии с автодеплоем, .github/workflows/) отдельной задачей.
"""
import sys
from datetime import datetime, timedelta

from dotenv import load_dotenv
load_dotenv()

from database import SessionLocal, User, Resume  # noqa: E402

DAYS_THRESHOLD = 7


def main():
    dry_run = "--dry-run" in sys.argv
    cutoff = datetime.utcnow() - timedelta(days=DAYS_THRESHOLD)

    db = SessionLocal()
    try:
        stale = db.query(User).filter(
            User.is_verified == False,  # noqa: E712 — явный False, не NULL
            User.created_at < cutoff,
        ).all()

        if not stale:
            print(f"Неподтверждённых аккаунтов старше {DAYS_THRESHOLD} дней не найдено.")
            return

        print(f"Найдено {len(stale)} неподтверждённых аккаунтов старше {DAYS_THRESHOLD} дней:")
        for u in stale:
            age_days = (datetime.utcnow() - u.created_at).days
            print(f"  — {u.email} (создан {age_days} дн. назад)")

        if dry_run:
            print("\n--dry-run: ничего не удалено.")
            return

        ids = [u.id for u in stale]
        db.query(Resume).filter(Resume.user_id.in_(ids)).delete(synchronize_session=False)
        deleted = db.query(User).filter(User.id.in_(ids)).delete(synchronize_session=False)
        db.commit()
        print(f"\nУдалено пользователей: {deleted}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
