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

Вручную (ИМЕННО py на машине разработчика — python в PATH заглушка Store):
    py cleanup_unverified.py [--dry-run]
    py cleanup_unverified.py --критерий   — печатает КРИТЕРИЙ бота из кода
    py cleanup_unverified.py --сироты     — строки с мёртвым user_id

--dry-run — посчитать и показать отчёт по таблицам, ничего не удаляя.
Ручной запуск workflow по умолчанию тоже идёт в --dry-run: проверка
«работает ли задача» не должна стоить кому-то аккаунта.
"""
import sys
from datetime import datetime, timedelta

from dotenv import load_dotenv
load_dotenv()

from database import (SessionLocal, User, delete_user_cascade,  # noqa: E402
                      check_user_tables_complete, user_data_counts)

DAYS_THRESHOLD = 7


def критерий():
    """КРИТЕРИЙ БОТА — печатается ИЗ КОДА, а не пересказывается словами.

    Заведено 2026-08-20. До этого «по какому признаку аккаунт признаётся
    ботом» отвечалось прозой в отчёте, и проверить пересказ было нечем:
    порог живёт константой, фильтр — выражением SQLAlchemy, а «пустота»
    — списком таблиц в `database.py`. Три места, и разъехаться с рассказом
    о них они могут молча, ровно как разъезжались числа в §6.0.4.

    Здесь каждое из трёх читается у самого источника: `DAYS_THRESHOLD`
    отсюда, `USER_TABLES`/`CHILD_TABLES`/`ПУСТЫЕ_ПО_УМОЛЧАНИЮ` — из
    `database`. Копии ни одной величины тут нет.
    """
    from database import (USER_TABLES, CHILD_TABLES,  # noqa: E402
                          ПУСТЫЕ_ПО_УМОЛЧАНИЮ)

    print("=" * 74)
    print("КРИТЕРИЙ, ПО КОТОРОМУ АККАУНТ ПРИЗНАЁТСЯ БОТОМ")
    print("=" * 74)
    print()
    print("Три условия, И ВСЕ ТРИ обязательны. Ни одно не выводится")
    print("из остальных — второе и третье добавлены после того, как")
    print("допущение «неподтверждённый значит пустой» оказалось неверным.")
    print()
    print("  1. ФЛАГ    users.is_verified = 0")
    print("     Именно 0, а НЕ NULL: NULL стоит у старых аккаунтов,")
    print("     которым миграция проставила подтверждение ретроактивно.")
    print("     Строка кода: User.is_verified == False")
    print()
    print("  2. ВОЗРАСТ users.created_at < utcnow() - %d дней"
          % DAYS_THRESHOLD)
    print("     Порог — константа DAYS_THRESHOLD в этом файле, число")
    print("     на месте вызова не стоит.")
    print()
    print("  3. ПУСТОТА user_data_counts(id) не нашёл ни одной записи")
    print("     Считается по тому же списку таблиц, по которому идёт")
    print("     каскадное удаление, — разойтись они не могут:")
    print("     user_data_counts зовёт delete_user_cascade(dry_run=True).")
    print()
    print("     таблиц с прямым user_id (USER_TABLES) : %d" % len(USER_TABLES))
    for т in USER_TABLES:
        print("        %s" % т)
    print("     таблиц через родителя (CHILD_TABLES)  : %d" % len(CHILD_TABLES))
    for строка in CHILD_TABLES:
        print("        %s (через %s)" % (строка[0], строка[2]))
    print("     «пусто по умолчанию» — заготовки регистрации: %d"
          % len(ПУСТЫЕ_ПО_УМОЛЧАНИЮ))
    for т, условие in ПУСТЫЕ_ПО_УМОЛЧАНИЮ.items():
        print("        %s: пусто, если %s" % (т, условие))
    print()
    print("ЧЕГО КРИТЕРИЙ НЕ ДЕЛАЕТ. Он не смотрит ни на адрес почты, ни")
    print("на домен, ни на поведение: «бот» здесь — не догадка о природе")
    print("аккаунта, а три проверяемых факта. Живой человек, забывший")
    print("подтвердить почту и ничего не заполнивший, под них подходит")
    print("и будет удалён — это осознанная цена, а не просмотр.")
    return 0


def сироты():
    """Строки, чей user_id не ведёт ни к одному живому пользователю.

    Вопрос отдельный от критерия и задаётся ПОСЛЕ удаления: каскад мог
    забыть таблицу, и тогда данные ушедшего достанутся следующему —
    SQLite переиспользует освободившиеся id (BACKLOG №11).

    Ходит по СХЕМЕ, а не по списку `USER_TABLES`: список — whitelist,
    и таблица, которую в него забыли внести, невидима ровно тогда, когда
    она и опасна. `check_user_tables_complete` сторожит список с другой
    стороны — по моделям; здесь третья точка зрения, по фактическим
    колонкам базы.
    """
    import sqlite3
    from database import DB_PATH  # noqa: E402

    c = sqlite3.connect("file:%s?mode=ro" % DB_PATH, uri=True)
    живых = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    таблиц = всего = 0
    print("СИРОТЫ: строки с user_id, которого нет в users")
    print("база: %s, живых пользователей: %d" % (DB_PATH, живых))
    print()
    print("%-34s %8s %8s" % ("таблица", "строк", "сирот"))
    имена = [r[0] for r in c.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    for т in имена:
        колонки = [r[1] for r in c.execute("PRAGMA table_info(%s)" % т)]
        if "user_id" not in колонки:
            continue
        таблиц += 1
        строк = c.execute("SELECT COUNT(*) FROM %s" % т).fetchone()[0]
        n = c.execute("SELECT COUNT(*) FROM %s WHERE user_id IS NOT NULL "
                      "AND user_id NOT IN (SELECT id FROM users)" % т).fetchone()[0]
        всего += n
        print("%-34s %8d %8d%s" % (т, строк, n, "   <-- СИРОТЫ" if n else ""))
    print()
    print("таблиц с колонкой user_id: %d" % таблиц)
    print("СИРОТ ВСЕГО: %d" % всего)
    if всего:
        print()
        print("Это значит, что каскад удаления не знает про названные")
        print("таблицы. Внести их в USER_TABLES (database.py, §6.1)")
        print("и разобраться, чьи это строки, ДО следующей очистки.")
    return 1 if всего else 0


def main():
    if "--критерий" in sys.argv:
        return критерий()
    if "--сироты" in sys.argv:
        return сироты()
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

    print("Найдено %d неподтверждённых аккаунтов старше %d дней." % (len(цели), DAYS_THRESHOLD))

    # ── Третье условие: аккаунт должен быть ПУСТ ──────────────────────────
    #
    # Раньше условий было два — флаг и возраст, — а пустота считалась
    # само собой разумеющейся: неподтверждённый ведь не доберётся
    # до инструментов. Проверка 2026-07-31 показала, что это допущение,
    # а не факт: вход для неподтверждённых открыт (main.py, роут POST
    # /login), гейт стоит на страницах инструментов, но НЕ на API записи
    # данных. То есть аккаунт с флагом «неподтверждён» может оказаться
    # полным — сегодня через прямые запросы к API, завтра через смену
    # почты, которая сбросит флаг у живого пользователя.
    #
    # Механизм, который удаляет необратимо, должен смотреть на то, что
    # удаляет. Ботов это не задевает: они пусты и уходят как прежде.
    пустые, пропущенные = [], []
    for uid, email, дней in цели:
        данные = user_data_counts(uid)
        (пропущенные if данные else пустые).append((uid, email, дней, данные))

    for _, email, дней, _ in пустые:
        print("  — %s (создан %d дн. назад), пуст" % (email, дней))

    if пропущенные:
        print("")
        print("ПРОПУЩЕНО %d: аккаунт неподтверждён и стар, но НЕ пуст." % len(пропущенные))
        print("Это сигнал: данные накоплены в обход подтверждения почты.")
        for uid, email, дней, данные in пропущенные:
            состав = ", ".join("%s=%d" % кв for кв in sorted(данные.items()))
            print("  — id=%s %s (создан %d дн. назад): %s" % (uid, email, дней, состав))
        # Строка для workflow: по ней он поймёт, что надо разбудить человека
        print("SKIPPED_NONEMPTY=%d" % len(пропущенные))

    цели = [(uid, email, дней) for uid, email, дней, _ in пустые]
    if not цели:
        print("")
        print("Удалять нечего: все найденные аккаунты содержат данные.")
        return

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
    sys.exit(main() or 0)
