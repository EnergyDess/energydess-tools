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
    py check_stand_state.py --контроль   # подлоги с доказательством
    py check_stand_state.py --эталон     # снять эталон посева (зовёт --seed)
    py check_stand_state.py --покрытие   # что опись спрашивает, по сущностям
"""

import io
import json
import os
import sqlite3
import sys
import probe_guard  # noqa: F401  ПРОПУСК вместо трассы (§6.0.1)

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

    # 6. ЧУЖОЕ ЗНАЧЕНИЕ, А НЕ ЧУЖАЯ СТРОКА (заход 290, остаток задачи 284).
    #
    #    Статус упражнения на стенде ВЫВОДИТСЯ из ролика: seed модерации
    #    не заводит, ролика нет — «no_video», ролик есть — «unchecked»
    #    (та же миграция в `database.py`). «Одобрено» либо «неверно» —
    #    след пробы, нажавшей кнопку модерации: проба админки однажды
    #    оставила «approved» при пустом ролике, и опись этого не видела —
    #    она искала чужие СТРОКИ, а строка была своя. Замер до правки:
    #    подложенный статус — код 0, «ЧУЖОГО НЕТ».
    #
    #    ГРАНИЦА: подменённый САМ РОЛИК из ролика не выводится — сверяется
    #    только статус при данном ролике.
    if "video_status" in колонки(c, "exercises"):
        n = c.execute(ЗАПРОС_СТАТУСОВ.replace("SELECT id", "SELECT COUNT(*)")
                      ).fetchone()[0]
        if n:
            находки.append(("exercises.video_status", n,
                            "статус не выводится из ролика (след модерации)"))

    # 7. МЕСТА ГЛАВНОЙ ВНЕ СЕМЕНИ (BACKLOG №325). Панель загрузки пишет
    #    строку и файл на том; проба, загрузившая файл и не убравшая его,
    #    оставила бы стенд с заполненным местом, которого seed не заводит.
    #    Два вида, как у людей: СТРОКА вне семени и ФАЙЛ без строки
    #    (сирота на томе — его не покажет ни одна страница и не уберёт
    #    ни одна уборка).
    try:
        строки = [r[0] for r in c.execute("SELECT slot_id FROM landing_media")]
    except sqlite3.OperationalError:
        строки = []
    семя_гл = семя_главной()
    лишние_гл = [с for с in строки if с not in семя_гл]
    if лишние_гл:
        находки.append(("landing_media", len(лишние_гл),
                        "места вне семени: " + ", ".join(лишние_гл[:5])))
    сироты_гл = сироты_тома(c)
    if сироты_гл:
        находки.append(("landing (том)", len(сироты_гл),
                        "файлы без строки: " + ", ".join(сироты_гл[:3])))
    return находки, свои, True


# ══════════════════════════════════════════════════════════════════════
# ПРОПАЖА ПОСЕЯННОГО (BACKLOG №332)
# ══════════════════════════════════════════════════════════════════════
#
# ЗАЧЕМ. Всё выше спрашивает одну сторону — не появилось ли ЛИШНЕЕ.
# Замер 2026-09-13: полный прогон проверки 35 унёс у стенда ВСЕ позиции
# аптечки (38 → 0), а опись напечатала «ЧУЖОГО НЕТ — стенд в известном
# виде», код 0. Пустой стенд под видом известного — немой отказ
# в самом инструменте, на который опираются все замеры приёмки.
#
# ЭТАЛОН СНИМАЕТСЯ В МОМЕНТ ПОСЕВА, А НЕ ВЫВОДИТСЯ ИЗ КОДА SEED. Прочитать
# «что заводит seed» из 3000 строк нечем, а вписанное число разошлось бы
# с посевом при первой его правке (§6.0.4). `make_local_user.py --seed`
# последним действием зовёт `записать_эталон`, и файл лежит РЯДОМ С БАЗОЙ:
# эталон другой базы о этой не говорит ничего.
#
# СЧИТАЕТСЯ ВИДИМОЕ ЧЕЛОВЕКУ: строки аккаунтов seed по каждой таблице
# схемы и ФАЙЛЫ, на которые эти строки ссылаются. Строка есть, а файла
# нет — на экране пустая плитка, и это такая же пропажа. Пути к файлам
# записаны ЗДЕСЬ, а не взяты у `main`: мерка не берёт данные у
# проверяемого кода. Разойдись схема хранения — опись назовёт пропажу,
# и это честнее, чем согласиться с кодом.
#
# ГРАНИЦА, И ОНА НАЗВАНА. Спрашивается «стало МЕНЬШЕ». Не видны:
# строка, заменённая другой (удалили одну, добавили одну), изменённое
# ЗНАЧЕНИЕ посеянной строки (остаток, срок) и прирост своих строк
# (проба дописала реплику). Журналы из `ЖУРНАЛЫ` не спрашиваются —
# там убывание законно (ленивая уборка по сроку), кроме справочника
# упражнений: его число семенем задано.

ЭТАЛОН_ИМЯ = "stand_seed_ref.json"

# Файлы, на которые ссылаются строки: (таблица, вид каталога media).
МЕДИА_СТРОК = (("chat_messages", "chat"), ("body_photos", "body"),
               ("medkit_items", "medkit"))


def путь_эталона(путь):
    return os.path.join(os.path.dirname(os.path.abspath(путь)), ЭТАЛОН_ИМЯ)


def посев_счёт(c, путь):
    """{ключ: число} — видимое состояние посева. Ключ «таблица|почта»."""
    import database as d

    адреса = sorted(адреса_семени())
    ид = dict(c.execute(
        "SELECT id, email FROM users WHERE email IN (%s)"
        % ",".join("?" * len(адреса)), tuple(адреса)).fetchall())
    сч = {}
    for e in ид.values():
        сч["users|" + e] = 1
    if not ид:
        return сч
    в_списке = ",".join(str(i) for i in sorted(ид))

    def по_владельцу(таблица, запрос):
        for uid, n in c.execute(запрос):
            if uid in ид:
                сч["%s|%s" % (таблица, ид[uid])] = n

    for т in d.USER_TABLES:
        if т in ЖУРНАЛЫ:
            continue
        try:
            есть = колонки(c, т)
        except sqlite3.OperationalError:
            continue
        if "user_id" in есть:
            по_владельцу(т, 'SELECT user_id, COUNT(*) FROM "%s" WHERE user_id '
                            "IN (%s) GROUP BY user_id" % (т, в_списке))
    for т, кол in d.ВСТРЕЧНЫЕ_ССЫЛКИ:
        try:
            if кол not in колонки(c, т):
                continue
        except sqlite3.OperationalError:
            continue
        по_владельцу("%s.%s" % (т, кол),
                     'SELECT %s, COUNT(*) FROM "%s" WHERE %s IN (%s) GROUP BY %s'
                     % (кол, т, кол, в_списке, кол))
    for ребёнок, ключ, родитель, ключ2, дед in d.CHILD_TABLES:
        try:
            колонки(c, ребёнок)
        except sqlite3.OperationalError:
            continue
        if дед:
            з = ('SELECT g.user_id, COUNT(*) FROM "%s" r JOIN "%s" p ON r.%s = p.id '
                 'JOIN "%s" g ON p.%s = g.id WHERE g.user_id IN (%s) '
                 "GROUP BY g.user_id" % (ребёнок, родитель, ключ, дед, ключ2, в_списке))
        else:
            з = ('SELECT p.user_id, COUNT(*) FROM "%s" r JOIN "%s" p ON r.%s = p.id '
                 "WHERE p.user_id IN (%s) GROUP BY p.user_id"
                 % (ребёнок, родитель, ключ, в_списке))
        по_владельцу(ребёнок, з)

    # ОБЩИЕ СПРАВОЧНИКИ: столько, сколько задаёт семя
    семя = семя_сетов()
    if семя is not None:
        сч["enshrouded_sets|семя"] = sum(
            1 for r in c.execute("SELECT id FROM enshrouded_sets") if r[0] in семя)
    сч["exercises|всего"] = c.execute("SELECT COUNT(*) FROM exercises").fetchone()[0]
    try:
        места = c.execute("SELECT slot_id, version, ext FROM landing_media").fetchall()
    except sqlite3.OperationalError:
        места = []
    семя_гл = семя_главной()
    кат = os.path.dirname(os.path.abspath(путь))
    сч["landing_media|семя"] = sum(1 for r in места if r[0] in семя_гл)
    сч["файлы строк landing|семя"] = sum(
        1 for s, v, e in места if s in семя_гл
        and os.path.isfile(os.path.join(кат, "landing", "%s-%s.%s" % (s, v, e))))

    # ФАЙЛЫ СТРОК: аватар по отметке времени, медиа по токену
    for uid, e in ид.items():
        отм = c.execute("SELECT avatar_updated_at FROM users WHERE id = ?",
                        (uid,)).fetchone()[0]
        if отм:
            сч["файлы строк avatars|" + e] = int(os.path.isfile(
                os.path.join(кат, "avatars", "%d.png" % uid)))
    for т, вид in МЕДИА_СТРОК:
        try:
            if "image_path" not in колонки(c, т):
                continue
        except sqlite3.OperationalError:
            continue
        for uid, токен in c.execute(
                'SELECT user_id, image_path FROM "%s" WHERE image_path IS NOT NULL '
                "AND image_path <> '' AND user_id IN (%s)" % (т, в_списке)):
            if os.path.isfile(os.path.join(кат, "media", вид, str(uid), токен + ".jpg")):
                к = "файлы строк media/%s|%s" % (вид, ид[uid])
                сч[к] = сч.get(к, 0) + 1
    return {к: n for к, n in сч.items() if n}


def записать_эталон(путь=None):
    """Снять эталон посева. Зовётся последним действием `--seed`."""
    путь = путь or путь_базы()
    c = sqlite3.connect("file:%s?mode=ro" % путь, uri=True)
    try:
        сч = посев_счёт(c, путь)
    finally:
        c.close()
    import time
    io.open(путь_эталона(путь), "w", encoding="utf-8").write(json.dumps(
        {"база": os.path.abspath(путь), "снят": time.strftime("%Y-%m-%d %H:%M:%S"),
         "счёт": сч}, ensure_ascii=False, indent=1, sort_keys=True))
    return сч


def прочитать_эталон(путь):
    try:
        return json.loads(io.open(путь_эталона(путь), encoding="utf-8").read())
    except (OSError, ValueError):
        return None


def пропажа(c, путь):
    """([(ключ, было, стало)], эталон|None). None — спросить нечем."""
    эт = прочитать_эталон(путь)
    if not эт:
        return [], None
    сейчас = посев_счёт(c, путь)
    return ([(к, n, сейчас.get(к, 0)) for к, n in sorted(эт["счёт"].items())
             if сейчас.get(к, 0) < n], эт)


def семя_главной():
    """Места, которые заводит seed. ИМПОРТОМ, а не копией списка."""
    import make_local_user as m
    return set(m.СЕМЯ_ГЛАВНОЙ)


def каталог_главной():
    return os.path.join(os.path.dirname(os.path.abspath(путь_базы())), "landing")


def сироты_тома(c):
    """Файлы в каталоге мест, на которые не указывает ни одна строка."""
    к = каталог_главной()
    if not os.path.isdir(к):
        return []
    try:
        строки = c.execute("SELECT slot_id, version, ext FROM landing_media").fetchall()
    except sqlite3.OperationalError:
        строки = []
    # Первый кадр ролика принадлежит строке-ролику той же версии (заход 342)
    живые = ({"%s-%s.%s" % r for r in строки}
             | {"%s-%s.poster.webp" % (с, в) for с, в, е in строки if е == "mp4"})
    return sorted(f for f in os.listdir(к) if f not in живые)


# ВЫВОДИМЫЙ СТАТУС — ОДНИМ ЗАПРОСОМ на опись и на приведение: два текста
# одного условия разошлись бы молча (§6.0.7)
ВЫВОД_СТАТУСА = ("CASE WHEN youtube_id IS NULL OR youtube_id = '' "
                 "THEN 'no_video' ELSE 'unchecked' END")
ЗАПРОС_СТАТУСОВ = ("SELECT id FROM exercises WHERE video_status IS NULL "
                   "OR video_status <> " + ВЫВОД_СТАТУСА)


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
    статусов = c.execute("UPDATE exercises SET video_status = %s WHERE id IN (%s)"
                         % (ВЫВОД_СТАТУСА, ЗАПРОС_СТАТУСОВ)).rowcount
    c.commit()
    # Места главной вне семени — строка и файл вместе, потом сироты тома.
    try:
        вне = [r for r in c.execute("SELECT slot_id, version, ext FROM landing_media")
               if r[0] not in семя_главной()]
    except sqlite3.OperationalError:
        вне = []
    for slot_id, _в, _е in вне:
        c.execute("DELETE FROM landing_media WHERE slot_id = ?", (slot_id,))
    c.commit()
    for имя in сироты_тома(c):
        os.remove(os.path.join(каталог_главной(), имя))
    c.close()
    return len(чужие), len(лишние) + len(вне), сирот, статусов


def прогон(показывать=True):
    путь = путь_базы()
    if not os.path.exists(путь):
        if показывать:
            print("СПРОСИТЬ НЕЧЕМ: базы %s нет. Это НЕ «чисто»." % путь)
        return 2, [], set()
    c = sqlite3.connect("file:%s?mode=ro" % путь, uri=True)
    находки, свои, есть = опись(c)
    пропало, эталон = пропажа(c, путь) if есть else ([], None)
    c.close()
    # ПРОПАЖА — ТАКАЯ ЖЕ НАХОДКА, КАК ЛИШНЕЕ: в тот же список и в тот же
    # код возврата. Отдельный флаг «а ещё пропало» читали бы как примечание
    if есть:
        for к, было, стало in пропало:
            т, _, чей = к.partition("|")
            находки.append((т, было - стало, "ПРОПАЛО посеянное (%s): было %d, стало %d"
                            % (чей, было, стало)))
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
        лишн = [з for з in находки if not з[2].startswith("ПРОПАЛО")]
        проп = [з for з in находки if з[2].startswith("ПРОПАЛО")]
        if лишн:
            print("ЧУЖОЕ (не заводит seed, не убирают ни --drop, ни --seed):")
            for т, n, что in лишн:
                print("  %-32s %6d  %s" % (т, n, что))
            print("строк чужих: %d" % sum(n for _, n, _ in лишн))
        else:
            print("ЧУЖОГО НЕТ.")
        if эталон is None:
            print("ПРОПАЖУ СПРОСИТЬ НЕЧЕМ: эталона посева нет (%s)." % ЭТАЛОН_ИМЯ)
            print("  Это НЕ «ничего не пропало». Пересейте: py make_local_user.py --seed")
        elif проп:
            print("ПРОПАЛО ПОСЕЯННОЕ (эталон %s; приведение это не лечит — "
                  "пересейте):" % эталон["снят"])
            for т, n, что in проп:
                print("  %-32s %6d  %s" % (т, n, что))
        else:
            print("ПОСЕЯННОЕ НА МЕСТЕ: ключей эталона %d, убыло 0 (эталон %s)."
                  % (len(эталон["счёт"]), эталон["снят"]))
        if not находки and эталон is not None:
            print("СТЕНД В ИЗВЕСТНОМ ВИДЕ — лишнего нет, пропажи нет.")
    if есть and эталон is None and not находки:
        return 2, находки, свои
    return (1 if находки else 0), находки, свои


def покрытие():
    """ЧТО ОПИСЬ СПРАШИВАЕТ — по каждой сущности стенда, в обе стороны.

    Сущности ВЫВОДЯТСЯ: все таблицы схемы плюс каталоги файлов рядом
    с базой. Перечня «что проверять» здесь нет — только ответ по каждой.
    """
    import database as d
    путь = путь_базы()
    c = sqlite3.connect("file:%s?mode=ro" % путь, uri=True)
    таблицы = sorted(r[0] for r in c.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%'"))
    эт = прочитать_эталон(путь)
    ключи_эт = {к.partition("|")[0] for к in (эт or {}).get("счёт", {})}
    c.close()
    с_хозяином = (set(d.USER_TABLES) | {т for т, _ in d.ВСТРЕЧНЫЕ_ССЫЛКИ}
                  | {х[0] for х in d.CHILD_TABLES})
    лишнее_общее = {"users", "enshrouded_sets", "exercises", "landing_media"}
    строки = []
    for т in таблицы:
        лишн = т not in ЖУРНАЛЫ and (т in с_хозяином or т in лишнее_общее) \
            or т == "exercises"
        проп = (т not in ЖУРНАЛЫ or т == "exercises") and (
            т in с_хозяином or т in лишнее_общее)
        причина = ЖУРНАЛЫ.get(т, "") if т != "exercises" else ""
        строки.append((т, лишн, проп, т in ключи_эт, причина))
    for кат, лишн in (("файлы строк landing", True), ("файлы строк avatars", False),
                      ("файлы строк media/*", False), ("файлы enshrouded (том)", False),
                      ("файлы previews", False)):
        проп = кат in ("файлы строк landing", "файлы строк avatars", "файлы строк media/*")
        причина = ("кеш кадров, не посев" if "previews" in кат else
                   "загрузки экрана каталога, seed их не заводит"
                   if "enshrouded" in кат else "")
        в_эт = any(к.startswith(кат.replace("/*", "")) for к in ключи_эт)
        строки.append((кат, лишн, проп, в_эт, причина))
    print("ПОКРЫТИЕ ОПИСИ: сущностей %d" % len(строки))
    print("  %-28s %-7s %-8s %-10s %s" % ("сущность", "лишнее", "пропажа",
                                         "в эталоне", "почему нет"))
    for т, л, п, в, прич in строки:
        print("  %-28s %-7s %-8s %-10s %s" % (т, "да" if л else "НЕТ",
                                             "да" if п else "НЕТ",
                                             "да" if в else "-", прич))
    print("  лишнее спрашивается у %d из %d, пропажа — у %d из %d"
          % (sum(1 for з in строки if з[1]), len(строки),
             sum(1 for з in строки if з[2]), len(строки)))
    return 0


def main():
    if "--эталон" in sys.argv:
        сч = записать_эталон()
        print("ЭТАЛОН ПОСЕВА снят: ключей %d, %s" % (len(сч), путь_эталона(путь_базы())))
        return 0
    if "--покрытие" in sys.argv:
        return покрытие()
    код, находки, свои = прогон()
    if код == 2:
        return 2
    if код == 0:
        return 0
    if "--привести" in sys.argv:
        print()
        людей, сетов, сирот, статусов = привести(путь_базы(), свои)
        print("УБРАНО: аккаунтов %d, сирот %d, сетов и мест главной вне семени %d, "
              "статусов упражнений возвращено %d" % (людей, сирот, сетов, статусов))
        код2, ост, _ = прогон(показывать=False)
        проп = [з for з in ост if з[2].startswith("ПРОПАЛО")]
        print("ПОСЛЕ ПРИВЕДЕНИЯ: %s"
              % ("чужого нет" if код2 == 0 else "ОСТАЛОСЬ %s" % (ост,)))
        if проп:
            print("  Пропажу приведение не возвращает: py make_local_user.py --seed")
        return 0 if код2 == 0 else 1
    print()
    if any(not з[2].startswith("ПРОПАЛО") for з in находки):
        print("убрать чужое: py check_stand_state.py --привести")
    if any(з[2].startswith("ПРОПАЛО") for з in находки):
        print("вернуть посеянное: py make_local_user.py --seed")
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
    "чужой-статус": "SELECT COUNT(*) FROM exercises WHERE video_status = 'approved'",
    # ПОДЛОГ ОБРАТНЫЙ ПРЕЖНИМ ТРЁМ: строк становится МЕНЬШЕ. Считаются
    # позиции аптечки аккаунтов seed прямо в базе, а не через `посев_счёт`
    # описи — иначе доказательство и вердикт были бы одной функцией
    "пропажа-аптечки": ("SELECT COUNT(*) FROM medkit_items WHERE user_id IN "
                        "(SELECT id FROM users WHERE email LIKE '%@local.dev')"),
}

# Сдвиг числа строк, который обязан дать подлог
ОЖИДАНИЕ = {"пропажа-аптечки": -1}


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
    # ЧУЖОЕ ЗНАЧЕНИЕ СВОЕЙ СТРОКИ — ровно то, что оставила проба админки
    # (задача 284): «одобрено» при пустом ролике. Строк не прибавляется,
    # поэтому доказательство считает сами одобренные
    ("чужой-статус",
     "UPDATE exercises SET video_status = 'approved' WHERE id = (SELECT MIN(id) "
     "FROM exercises WHERE (youtube_id IS NULL OR youtube_id = '') "
     "AND video_status = 'no_video')",
     "UPDATE exercises SET video_status = 'no_video' WHERE video_status = "
     "'approved' AND (youtube_id IS NULL OR youtube_id = '')"),
    # ПОСЕЯННАЯ ПОЗИЦИЯ УНЕСЕНА — ровно то, что сделал `--очистить`, только
    # одной строкой. Возвращается ТА ЖЕ строка с тем же id: копия берётся
    # в свою таблицу в той же базе ДО удаления. Категории позиции не
    # трогаются — после возврата они снова ссылаются на живую строку.
    ("пропажа-аптечки",
     ["DROP TABLE IF EXISTS zz_control_item",
      "CREATE TABLE zz_control_item AS SELECT * FROM medkit_items WHERE id = "
      "(SELECT MIN(id) FROM medkit_items WHERE user_id IN "
      "(SELECT id FROM users WHERE email LIKE '%@local.dev'))",
      "DELETE FROM medkit_items WHERE id IN (SELECT id FROM zz_control_item)"],
     ["INSERT INTO medkit_items SELECT * FROM zz_control_item",
      "DROP TABLE zz_control_item"]),
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
            for з in (вставка if isinstance(вставка, list) else [вставка]):
                c.execute(з)
            c.commit()
        except sqlite3.OperationalError as e:
            print("  %-16s ПОДЛОГ НЕ СОСТОЯЛСЯ: %s" % (имя, e))
            c.close()
            ок = False
            continue
        c.close()
        после = доказать_подлог(путь, ДОКАЗАТЕЛЬСТВА[имя])
        состоялся = после == до + ОЖИДАНИЕ.get(имя, 1)
        к, наход, _ = прогон(показывать=False)
        # НАЙТИ ОБЯЗАНА СВОЁ: подлог пропажи назван пропажей, лишнего —
        # лишним. Иначе «нашла» могло бы значить «нашла что-то другое»
        пропажа_названа = any(з[2].startswith("ПРОПАЛО") for з in наход)
        нашла = к == 1 and (пропажа_названа == (имя in ОЖИДАНИЕ))
        c = sqlite3.connect(путь)
        for з in (чистка if isinstance(чистка, list) else [чистка]):
            c.execute(з)
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
