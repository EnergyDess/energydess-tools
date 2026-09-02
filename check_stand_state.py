"""СТЕНД ПРИВЕДЁН К ИЗВЕСТНОМУ ВИДУ — ИЛИ НЕТ (BACKLOG №235, блок A).

ЗАЧЕМ. Заход 236 закончился признанием: дефект задачи 161 воспроизводился,
а ПОСЛЕ ПЕРЕЗАПУСКА СТЕНДА перестал — независимо от кода, и что изменилось,
установлено не было. Из этого следует не «странность одной задачи», а вещь
шире: если поведение стенда зависит от того, когда его последний раз
перезапускали и что на нём успели натворить прошлые прогоны, то ЛЮБОЕ
число приёмки может зависеть от того же. Тот же класс, что слепая проба,
только этажом ниже — там врала проба, здесь площадка под ней.

ЧТО НАШЁЛ ПЕРВЫЙ ЖЕ ПРОГОН (2026-09-02). В базе стенда лежало
482 пользователя при шести, которых заводит seed; 478 из них созданы
за ОДИН день, 2026-08-27, — прогоном pytest, ушедшим не в свою базу.
`/admin/users` из-за этого весила 934.6 КБ и несла 482 строки таблицы
вместо шести. Все пробы, снимающие админку, мерили её именно такой,
и ни одна проверка проекта об этом не говорила: они сверяют КОД
с ДОКУМЕНТАМИ, а вопрос «в известном ли состоянии площадка» не задавал
никто.

ПРИЗНАК — СТРУКТУРНЫЙ, А НЕ ПЕРЕЧЕНЬ ИЗВЕСТНЫХ ИМЁН (§6.0.7).
Чужая строка — та, чьего ВЛАДЕЛЬЦА seed не заводит, либо запись общего
справочника, которой нет в семени. Перечень «плохих» адресов пришлось бы
пополнять руками после каждой новой пробы, и первая же неучтённая
прошла бы молча — ровно как проходили мимо `pages`, `names` и `ЭКРАНЫ`.

Список таблиц и то, как они привязаны к человеку, берётся у `database`
ИМПОРТОМ (`USER_TABLES`, `ВСТРЕЧНЫЕ_ССЫЛКИ`, `CHILD_TABLES`) — там он уже
сверяется со схемой (§6.1). Адреса аккаунтов seed берутся у
`make_local_user` импортом же: копия разошлась бы с оригиналом молча.

ГДЕ НАКОПЛЕНИЕ ЗАКОННО — названо поимённо и с причиной (`ЖУРНАЛЫ`).
Это ИСКЛЮЧЕНИЯ с причиной у каждой строки, а не «что не подошло».

ИСХОДА ТРИ, И ТРЕТИЙ ОБЯЗАТЕЛЕН. «Чисто», «есть чужое» и «СПРОСИТЬ
НЕЧЕМ» — базы нет либо в ней нет ни одного аккаунта seed. Свести
последний с «чисто» значило бы объявить порядок там, где не смотрели
(§6.0.1).

БОЕВУЮ БАЗУ НЕ ОТКРЫВАЕТ ВОВСЕ: путь с `/data/` отвергается до первого
запроса, как у `check_medkit_manual`.

    py check_stand_state.py              # опись; код 1, если есть чужое
    py check_stand_state.py --привести   # убрать чужое и перепроверить
    py check_stand_state.py --контроль   # подлог с доказательством
"""

import io
import json
import os
import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8")

# ТАБЛИЦЫ, ГДЕ НАКОПЛЕНИЕ ЗАКОННО. Перечень тут на месте: множество
# конечно и объявляется решением о схеме, у каждой строки причина.
ЖУРНАЛЫ = {
    "email_logs": "журнал отправок: копится по построению",
    "login_attempts": "журнал попыток входа: ленивая уборка по сроку (§8.1)",
    "food_translations": "кеш переводов, общий и без привязки к человеку",
    "ref_requests": "счётчик обращений к справочнику за месяц (§5.8, E)",
    "exercises": "общий справочник, наполняется exercises_seed.json",
}


def путь_базы():
    п = os.getenv("DB_PATH", "app.db")
    if "/data/" in п.replace("\\", "/") or п.startswith("/data"):
        print("ОСТАНОВЛЕНО: это боевая база. Опись стенда её не открывает.")
        sys.exit(2)
    return п


def адреса_семени():
    """Адреса, которые заводит seed. ИМПОРТОМ, а не копией списка."""
    import make_local_user as m
    адреса = set()
    for имя in dir(m):
        if имя.startswith("EMAIL"):
            з = getattr(m, имя)
            if isinstance(з, str) and "@" in з:
                адреса.add(з)
    return адреса


def семя_сетов():
    """Идентификаторы сетов из семени. Пустое множество — НЕ «лишних нет»:
    вернув его, мы объявили бы каталог чистым, не прочитав семени, — тот
    же немой отказ, ради которого написан §6.0.1. Поэтому None."""
    try:
        with io.open("enshrouded_seed.json", encoding="utf-8") as f:
            данные = json.load(f)
        сеты = данные["сеты"] if isinstance(данные, dict) else данные
        return {с["id"] for с in сеты}
    except Exception as e:
        print("[семя] enshrouded_seed.json не прочитан: %s" % e)
        return None


def колонки(c, таблица):
    return {r[1] for r in c.execute('PRAGMA table_info("%s")' % таблица)}


def опись(c):
    """(находки, свои_id, есть_ли_с_чем_сравнивать)."""
    import database as d

    адреса = адреса_семени()
    свои = {r[0] for r in c.execute(
        "SELECT id FROM users WHERE email IN (%s)" % ",".join("?" * len(адреса)),
        tuple(sorted(адреса)))}
    if not свои:
        return None, свои, False
    в_списке = ",".join(str(i) for i in sorted(свои))
    находки = []

    # 1. ЛЮДИ. Аккаунт, которого seed не заводит, — чужой.
    чужие = c.execute(
        "SELECT id, email FROM users WHERE id NOT IN (%s) ORDER BY id" % в_списке
    ).fetchall()
    if чужие:
        примеры = ", ".join(e for _, e in чужие[:3])
        находки.append(("users", len(чужие), "seed их не заводит: " + примеры))

    # 2. ПРЯМАЯ ПРИВЯЗКА: строка чужого человека в таблице с user_id.
    #
    #    ВИДА ДВА, И ОНИ РАЗНЫЕ. «Строка чужого аккаунта» уходит вместе
    #    с этим аккаунтом — её унесёт каскад. А СИРОТА — строка, чьего
    #    владельца нет ВОВСЕ (проба вписала выдуманный номер) — каскадом
    #    людей не убирается по построению: удалять некого. Свести их
    #    в одно число значило бы объявить убранным то, что останется
    #    навсегда. Тот же вид, что СИРОТА у проверки 24 (§6.0.14),
    #    только в таблицах человека.
    for т in d.USER_TABLES:
        if т in ЖУРНАЛЫ:
            continue
        try:
            есть = колонки(c, т)
        except sqlite3.OperationalError:
            continue
        if "user_id" not in есть:
            continue
        чужих = c.execute(
            'SELECT COUNT(*) FROM "%s" t WHERE t.user_id IS NOT NULL '
            "AND t.user_id NOT IN (%s) "
            "AND EXISTS (SELECT 1 FROM users u WHERE u.id = t.user_id)"
            % (т, в_списке)).fetchone()[0]
        сирот = c.execute(
            'SELECT COUNT(*) FROM "%s" t WHERE t.user_id IS NOT NULL '
            "AND NOT EXISTS (SELECT 1 FROM users u WHERE u.id = t.user_id)"
            % т).fetchone()[0]
        if чужих:
            находки.append((т, чужих, "строки чужих аккаунтов"))
        if сирот:
            находки.append((т, сирот, "СИРОТЫ: владельца нет вовсе"))

    # 3. ВСТРЕЧНЫЕ ССЫЛКИ: колонка на человека, названная иначе.
    for т, имя_кол in d.ВСТРЕЧНЫЕ_ССЫЛКИ:
        try:
            есть = колонки(c, т)
        except sqlite3.OperationalError:
            continue
        if имя_кол not in есть:
            continue
        n = c.execute('SELECT COUNT(*) FROM "%s" WHERE %s IS NOT NULL '
                      "AND %s NOT IN (%s)" % (т, имя_кол, имя_кол, в_списке)
                      ).fetchone()[0]
        if n:
            находки.append(("%s.%s" % (т, имя_кол), n, "ссылки на чужих"))

    # 4. ЧЕРЕЗ РОДИТЕЛЯ: своего user_id нет, владелец у родителя.
    for ребёнок, ключ, родитель, ключ2, дед in d.CHILD_TABLES:
        try:
            колонки(c, ребёнок)
        except sqlite3.OperationalError:
            continue
        if дед:
            з = ('SELECT COUNT(*) FROM "%s" r JOIN "%s" p ON r.%s = p.id '
                 'JOIN "%s" g ON p.%s = g.id WHERE g.user_id NOT IN (%s)'
                 % (ребёнок, родитель, ключ, дед, ключ2, в_списке))
        else:
            з = ('SELECT COUNT(*) FROM "%s" r JOIN "%s" p ON r.%s = p.id '
                 "WHERE p.user_id NOT IN (%s)" % (ребёнок, родитель, ключ, в_списке))
        n = c.execute(з).fetchone()[0]
        if n:
            находки.append((ребёнок, n, "через %s" % родитель))

    # 5. ОБЩИЙ СПРАВОЧНИК: сет, которого нет в семени. Ровно тот случай,
    #    что заход 236 нашёл руками (`zz_ui_url` от контроля чужой пробы).
    семя = семя_сетов()
    if семя is None:
        находки.append(("enshrouded_sets", 0, "СПРОСИТЬ НЕЧЕМ: семя не прочитано"))
    else:
        лишние = [r[0] for r in c.execute("SELECT id FROM enshrouded_sets ORDER BY id")
                  if r[0] not in семя]
        if лишние:
            находки.append(("enshrouded_sets", len(лишние),
                            "вне семени: " + ", ".join(лишние[:5])))
    return находки, свои, True


def привести(путь, свои):
    """Убрать чужое: людей — каскадом приложения, сеты — своим запросом."""
    os.environ.setdefault("DB_PATH", путь)
    import database as d
    c = sqlite3.connect(путь)
    чужие = [r[0] for r in c.execute(
        "SELECT id FROM users WHERE id NOT IN (%s)"
        % ",".join(str(i) for i in sorted(свои)))]
    c.close()
    for uid in чужие:
        d.delete_user_cascade(uid)

    # СИРОТЫ — своим запросом: каскад людей их не касается, удалять
    # некого. Идут ПОСЛЕ каскада, иначе половина сирот ещё не сирота.
    c = sqlite3.connect(путь)
    сирот = 0
    for т in d.USER_TABLES:
        if т in ЖУРНАЛЫ:
            continue
        try:
            если_есть = колонки(c, т)
        except sqlite3.OperationalError:
            continue
        if "user_id" not in если_есть:
            continue
        cur = c.execute(
            'DELETE FROM "%s" WHERE user_id IS NOT NULL AND user_id NOT IN '
            "(SELECT id FROM users)" % т)
        сирот += cur.rowcount
    c.commit()
    c.close()

    семя = семя_сетов()
    c = sqlite3.connect(путь)
    лишние = ([r[0] for r in c.execute("SELECT id FROM enshrouded_sets")
               if r[0] not in семя] if семя is not None else [])
    for sid in лишние:
        c.execute("DELETE FROM enshrouded_slots WHERE set_id = ?", (sid,))
        c.execute("DELETE FROM enshrouded_sets WHERE id = ?", (sid,))
    c.commit()
    c.close()
    return len(чужие), len(лишние), сирот


def прогон(показывать=True):
    путь = путь_базы()
    if not os.path.exists(путь):
        if показывать:
            print("СПРОСИТЬ НЕЧЕМ: базы %s нет. Это НЕ «чисто»." % путь)
        return 2, [], set()
    c = sqlite3.connect("file:%s?mode=ro" % путь, uri=True)
    находки, свои, есть = опись(c)
    c.close()
    if not есть:
        if показывать:
            print("СПРОСИТЬ НЕЧЕМ: ни одного аккаунта seed в базе.")
            print("  Это НЕ «стенд чист» — сравнивать не с чем.")
            print("  Сначала: py make_local_user.py --seed")
        return 2, [], свои
    if показывать:
        print("ОПИСЬ СТЕНДА: %s" % os.path.abspath(путь))
        print("аккаунтов seed: %d (%s)"
              % (len(свои), ", ".join(str(i) for i in sorted(свои))))
        print()
        if находки:
            print("ЧУЖОЕ (не заводит seed, не убирают ни --drop, ни --seed):")
            for т, n, что in находки:
                print("  %-32s %6d  %s" % (т, n, что))
            print()
            print("строк чужих: %d" % sum(n for _, n, _ in находки))
        else:
            print("ЧУЖОГО НЕТ — стенд в известном виде.")
    return (1 if находки else 0), находки, свои


def main():
    код, находки, свои = прогон()
    if код == 2:
        return 2
    if код == 0:
        return 0
    if "--привести" in sys.argv:
        print()
        людей, сетов, сирот = привести(путь_базы(), свои)
        print("УБРАНО: аккаунтов %d, сирот %d, сетов вне семени %d"
              % (людей, сирот, сетов))
        код2, ост, _ = прогон(показывать=False)
        print("ПОСЛЕ ПРИВЕДЕНИЯ: %s"
              % ("чужого нет" if код2 == 0 else "ОСТАЛОСЬ %s" % (ост,)))
        return 0 if код2 == 0 else 1
    print()
    print("убрать: py check_stand_state.py --привести")
    return 1


# ══════════════════════════════════════════════════════════════════════
# ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ
# ══════════════════════════════════════════════════════════════════════
#
# ДОКАЗАТЕЛЬСТВО ПОДЛОГА НЕЗАВИСИМО ОТ ВЕРДИКТА (§6.0.3): рядом с каждым
# подлогом стоит прямой счёт строк в базе ДО и ПОСЛЕ. «Проба нашла» —
# это вердикт, и он одинаков у зрячей пробы и у пробы, нашедшей своё же
# прежнее состояние.
ДОКАЗАТЕЛЬСТВА = {
    "чужой-аккаунт": "SELECT COUNT(*) FROM users",
    "чужой-сет": "SELECT COUNT(*) FROM enshrouded_sets",
}


def доказать_подлог(путь, запрос):
    c = sqlite3.connect("file:%s?mode=ro" % путь, uri=True)
    try:
        return c.execute(запрос).fetchone()[0]
    finally:
        c.close()


ПОДЛОГИ = (
    ("чужой-аккаунт",
     "INSERT INTO users (email, password_hash, is_admin, is_verified, "
     "created_at) VALUES ('zz-control@local.test','x',0,1,'2026-01-01')",
     "DELETE FROM users WHERE email = 'zz-control@local.test'"),
    # КОЛОНКИ СВЕРЕНЫ СО СХЕМОЙ, А НЕ ВЗЯТЫ ПО ПАМЯТИ. Первая версия
    # писала `category`, которой в таблице нет (там `crafter`), — вставка
    # падала, и контроль честно печатал «ПОДЛОГ НЕ СОСТОЯЛСЯ». Поймало
    # это ДОКАЗАТЕЛЬСТВО, а не чтение: вердикт был бы тем же и у слепой
    # пробы (§6.0.3).
    ("чужой-сет",
     "INSERT INTO enshrouded_sets (id, name_ru, name_en, crafter, lvl, "
     "pieces, custom, sort_order) "
     "VALUES ('zz_control','Контроль','Control','world',1,'[]',0,999)",
     "DELETE FROM enshrouded_sets WHERE id = 'zz_control'"),
)


def контроль():
    путь = путь_базы()
    код, находки, свои = прогон(показывать=False)
    if код == 2:
        print("ОСТАНОВЛЕНО: спросить нечем — контроль недействителен.")
        return 2
    if код != 0:
        print("ОСТАНОВЛЕНО: на грязной основе контроль недействителен.")
        print("  «нашла» и «нашла подлог» неотличимы. Сначала --привести.")
        return 2

    ок = True
    for имя, вставка, чистка in ПОДЛОГИ:
        до = доказать_подлог(путь, ДОКАЗАТЕЛЬСТВА[имя])
        c = sqlite3.connect(путь)
        try:
            c.execute(вставка)
            c.commit()
        except sqlite3.OperationalError as e:
            print("  %-16s ПОДЛОГ НЕ СОСТОЯЛСЯ: %s" % (имя, e))
            c.close()
            ок = False
            continue
        c.close()
        после = доказать_подлог(путь, ДОКАЗАТЕЛЬСТВА[имя])
        состоялся = после == до + 1
        к, _, _ = прогон(показывать=False)
        нашла = к == 1
        c = sqlite3.connect(путь)
        c.execute(чистка)
        c.commit()
        c.close()
        вернулось = доказать_подлог(путь, ДОКАЗАТЕЛЬСТВА[имя])
        print("  %-16s подлог %s (строк %d→%d, вернулось %d) · проба %s"
              % (имя, "СОСТОЯЛСЯ" if состоялся else "НЕ СОСТОЯЛСЯ",
                 до, после, вернулось, "НАШЛА" if нашла else "НЕ НАШЛА"))
        if not (состоялся and нашла and вернулось == до):
            ок = False

    к, _, _ = прогон(показывать=False)
    print("  после уборки подлогов: %s"
          % ("чисто" if к == 0 else "ОСТАЛОСЬ ЧУЖОЕ"))
    ок = ок and к == 0
    print("КОНТРОЛЬ %s" % ("ПРОЙДЕН" if ок else "НЕ ПРОЙДЕН"))
    return 0 if ок else 1


if __name__ == "__main__":
    sys.exit(контроль() if "--контроль" in sys.argv else main())
