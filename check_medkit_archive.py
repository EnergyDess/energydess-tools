# -*- coding: utf-8 -*-
"""АРХИВ УДАЛЁННЫХ УПАКОВОК: ЧТО СОХРАНЯЕТСЯ И ЧТО ПОДСТАВЛЯЕТСЯ.

═══════════════════════════════════════════════════════════════════════
ЧТО ЭТО
═══════════════════════════════════════════════════════════════════════

ПРОВЕРКА, код 1 при беде: здесь спрашивается НАШ код, а не чужой
сайт. Сети не требует вовсе.

Результат читается ИЗ БАЗЫ, а не из ответа сервера (§6.3): вопрос
блока — «переживает ли запись владельца удаление карточки», и ответ
на него лежит в базе, а не в коде HTTP.

═══════════════════════════════════════════════════════════════════════
ГЛАВНЫЙ КОНТРОЛЬ — СТРОГОСТЬ, А НЕ СРАБАТЫВАНИЕ
═══════════════════════════════════════════════════════════════════════

Требование владельца (G3): «Если дозировка или форма отличаются —
не предлагать НИЧЕГО и близкое не показывать. Подставить схему
от других миллиграммов — это „чужая схема хуже её отсутствия",
только чужая от самого владельца».

Поэтому подлогов ДВА рода и оба обязательны:

  · ПОДСТАНОВКА НЕ ПРЕДЛАГАЕТСЯ там, где отличается доза либо форма;
  · ОБРАТНЫЙ: при полном совпадении она ПРЕДЛАГАЕТСЯ.

Без обратного «ничего не предложено» неотличимо от «архив не работает
вовсе» (§6.0.3).

    py check_medkit_archive.py
    py check_medkit_archive.py --контроль
    py check_medkit_archive.py --экран             # видимый блок, засеянный архив
    py check_medkit_archive.py --экран --контроль  # подлог в страницу
"""
import io
import json
import os
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
import http.cookiejar
import probe_guard  # noqa: F401  ПРОПУСК вместо трассы (§6.0.1)

# ВЫВОД В UTF-8: без этого печать знака вне cp1251 роняет пробу
# `UnicodeEncodeError` при ЛЮБОМ перенаправлении (`> файл`,
# конвейер, `capture_output`) — то есть у всякого, кто запустит
# её не в консоль. Найдено проверкой 35 (BACKLOG №307).
sys.stdout.reconfigure(encoding="utf-8")

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace")

БАЗА = os.environ.get("MEDKIT_BASE", "http://127.0.0.1:8899")
ФАЙЛ = os.environ.get("DB_PATH", "app.db")
ПОЧТА = "screenshot@local.dev"
ПАРОЛЬ = "Screenshot-Local-2026"
КОНТРОЛЬ = "--контроль" in sys.argv
# Копия целого файла перед подлогом — см. `контроль()`
КОПИЯ = ".main_before_control.bak"

# БОЕВАЯ БАЗА НЕ ОТКРЫВАЕТСЯ ВОВСЕ: проба ПИШЕТ, и путь с /data/
# отвергается до первого запроса
if "/data/" in ФАЙЛ.replace(chr(92), "/"):
    print("БОЕВАЯ БАЗА НЕ ТРОГАЕТСЯ. Прогон только на стенде.")
    sys.exit(2)

плохих = 0
шагов = 0


пропусков = 0


def шаг(имя, ок, подробно="", собрано=None):
    """`собрано` — сколько записей засеянного архива было под шагом.
    Ноль — ПРОПУСК, а не OK: «не предлагается» на пустом архиве истинно
    по построению и не говорит ничего (задача 293, §6.0.1)."""
    global плохих, шагов, пропусков
    шагов += 1
    if собрано is not None and собрано == 0:
        пропусков += 1
        # что шаг напечатал бы без ключа — чтобы «зелёный на пустом»
        # был виден числом, а не выводом из рассуждения
        print("   ПРОПУСК %s  — архив стенда пуст, спросить нечем "
              "(без ключа было бы %s)" % (имя, "OK" if ок else "ПЛОХО"))
        return
    if not ок:
        плохих += 1
    print("   %s %s%s" % ("OK  " if ок else "ПЛОХО", имя,
                          ("  — " + подробно) if подробно else ""))


_дж = http.cookiejar.CookieJar()
_оп = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_дж))


def войти():
    д = urllib.parse.urlencode({"email": ПОЧТА, "password": ПАРОЛЬ}).encode()
    _оп.open(urllib.request.Request(БАЗА + "/login", data=д, method="POST"))


def зов(путь, метод="GET", тело=None):
    д = json.dumps(тело).encode() if тело is not None else None
    р = urllib.request.Request(БАЗА + путь, data=д, method=метод,
                               headers={"Content-Type": "application/json"})
    try:
        с = _оп.open(р)
        текст = с.read().decode("utf-8", "replace")
        return с.status, (json.loads(текст) if текст.strip() else {})
    except urllib.error.HTTPError as e:
        текст = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(текст)
        except ValueError:
            return e.code, {"error": текст[:120]}


def база():
    return sqlite3.connect(ФАЙЛ)


ЗАВОДИМ = {
    "name": "ПробаАрхив-249",
    "form": "tablet",
    "unit": "tablet",
    "qty_total": 20,
    "qty_left": 20,
    "expires_ym": "2029-01",
    "dose": 2,
    "substance": "проба-вещество",
    "code_gtin": "04600000000017",
}
СХЕМА = "По 1 таблетке 3 раза в день после еды"
ПОКАЗАНИЯ = "При проверке архива"


def завести(поля):
    код, тело = зов("/medkit/api/items", "POST", поля)
    if код != 200:
        return None, (тело or {}).get("error", "код %s" % код)
    c = база()
    r = c.execute("SELECT id FROM medkit_items WHERE name=? "
                  "ORDER BY id DESC LIMIT 1", (поля["name"],)).fetchone()
    c.close()
    return (r[0] if r else None), ""


def прогон():
    print("=" * 72)
    print("АРХИВ УДАЛЁННЫХ УПАКОВОК")
    print("=" * 72)
    войти()

    # ── чистим следы прошлых прогонов ─────────────────────────────
    c = база()
    c.execute("DELETE FROM medkit_archive WHERE name LIKE 'ПробаАрхив%'")
    for (и,) in c.execute("SELECT id FROM medkit_items "
                          "WHERE name LIKE 'ПробаАрхив%'").fetchall():
        c.execute("DELETE FROM medkit_item_categories WHERE item_id=?", (и,))
        c.execute("DELETE FROM medkit_items WHERE id=?", (и,))
    c.commit()
    c.close()

    ид, беда = завести(ЗАВОДИМ)
    шаг("позиция-заведена", bool(ид), беда or "id %s" % ид)
    if not ид:
        return

    зов("/medkit/api/items/%d/own-dosage" % ид, "POST", {"текст": СХЕМА})
    зов("/medkit/api/items/%d/own-indications" % ид, "POST",
        {"текст": ПОКАЗАНИЯ})
    c = база()
    r = c.execute("SELECT own_dosage_text, own_indications_text "
                  "FROM medkit_items WHERE id=?", (ид,)).fetchone()
    c.close()
    шаг("свои-записи-легли", bool(r and r[0] and r[1]),
        "схема %d знаков, показания %d знаков"
        % (len(r[0] or ""), len(r[1] or "")) if r else "строки нет")

    # ── G1: УДАЛЕНИЕ КЛАДЁТ СНИМОК ────────────────────────────────
    код, _ = зов("/medkit/api/items/%d" % ид, "DELETE")
    c = база()
    живых = c.execute("SELECT COUNT(*) FROM medkit_items WHERE id=?",
                      (ид,)).fetchone()[0]
    арх = c.execute("SELECT name, form, dose, substance, code_gtin, "
                    "own_dosage_text, own_indications_text, categories "
                    "FROM medkit_archive WHERE name=?",
                    (ЗАВОДИМ["name"],)).fetchall()
    c.close()
    шаг("позиция-ушла-из-списка", код == 200 and живых == 0,
        "код %s, живых строк %d" % (код, живых))
    шаг("снимок-лёг-в-архив", len(арх) == 1,
        "записей архива %d" % len(арх))
    if len(арх) != 1:
        return
    з = арх[0]
    шаг("схема-пережила-удаление", (з[5] or "") == СХЕМА,
        "в архиве %d знаков" % len(з[5] or ""))
    шаг("показания-пережили-удаление", (з[6] or "") == ПОКАЗАНИЯ,
        "в архиве %d знаков" % len(з[6] or ""))
    шаг("вещество-форма-доза-код-пережили",
        (з[1] == ЗАВОДИМ["form"] and float(з[2] or 0) == ЗАВОДИМ["dose"]
         and (з[3] or "") == ЗАВОДИМ["substance"]
         and (з[4] or "") == ЗАВОДИМ["code_gtin"]),
        "форма=%s доза=%s вещество=%r код=%r" % (з[1], з[2], з[3], з[4]))

    # ── G3: СТРОГОСТЬ. ГЛАВНЫЙ КОНТРОЛЬ БЛОКА ────────────────────
    def спросить(**кв):
        """ОТВЕТ СЕРВЕРА И ЕГО ОТСУТСТВИЕ — РАЗНЫЕ ФАКТЫ.

        Первая версия возвращала `bool(т.get('есть'))` и на HTTP 500
        отдавала False, то есть «совпадения нет». Эндпоинт при этом
        падал `ArgumentError` на КАЖДОМ запросе, а три шага строгости
        из четырёх были ЗЕЛЁНЫМИ: «не предлагается» выходило само
        собой. Ровно §6.0.1 — успехом объявлен результат, который
        успехом не является.
        """
        п = urllib.parse.urlencode(кв)
        код, т = зов("/medkit/api/archive-match?" + п)
        if код != 200:
            шаг("эндпоинт-ответил-200", False,
                "HTTP %s на запрос %s" % (код, кв))
            return None, т
        return bool(т.get("есть")), т

    есть, _ = спросить(name=ЗАВОДИМ["name"], form="tablet", dose=2)
    шаг("совпадение-по-полной-связке-НАЙДЕНО", есть,
        "название + форма + разовая доза")

    есть, _ = спросить(name=ЗАВОДИМ["name"], form="tablet", dose=4)
    шаг("ДРУГАЯ-РАЗОВАЯ-ДОЗА-не-предлагается", есть is False,
        "доза 4 против 2 — предложение %s"
        % ("ЕСТЬ (беда)" if есть else "нет"))

    есть, _ = спросить(name=ЗАВОДИМ["name"], form="syrup", dose=2)
    шаг("ДРУГАЯ-ФОРМА-не-предлагается", есть is False,
        "сироп против таблеток — предложение %s"
        % ("ЕСТЬ (беда)" if есть else "нет"))

    есть, _ = спросить(name=ЗАВОДИМ["name"] + " форте", form="tablet", dose=2)
    шаг("ДРУГОЕ-НАЗВАНИЕ-не-предлагается", есть is False,
        "«форте» — предложение %s" % ("ЕСТЬ (беда)" if есть else "нет"))

    # ── BACKLOG №255, блок E: СИЛА ВЕЩЕСТВА — ОТДЕЛЬНАЯ ОСЬ ОТ ДОЗЫ ──
    #
    # G3 говорит про «другие миллиграммы» — это СИЛА ВЕЩЕСТВА
    # («Ибупрофен, 200 мг»), а не разовая доза приёма («по 1
    # таблетке»), у которой своя проверка ступенью выше. До задачи 255
    # substance в сравнении не участвовал вовсе, и «Нурофен 200 мг» —
    # «Нурофен 400 мг» с одинаковой разовой дозой считались одной
    # упаковкой.
    есть, _ = спросить(name=ЗАВОДИМ["name"], form="tablet", dose=2,
                       substance=ЗАВОДИМ["substance"] + "-ДРУГОЕ")
    шаг("ДРУГАЯ-СИЛА-ВЕЩЕСТВА-не-предлагается", есть is False,
        "%r против %r — предложение %s"
        % (ЗАВОДИМ["substance"] + "-ДРУГОЕ", ЗАВОДИМ["substance"],
           "ЕСТЬ (беда)" if есть else "нет"))

    есть, _ = спросить(name=ЗАВОДИМ["name"], form="tablet", dose=2,
                       substance=ЗАВОДИМ["substance"])
    шаг("ТА-ЖЕ-СИЛА-ВЕЩЕСТВА-предлагается", есть is True,
        "вещество совпало дословно")

    есть, _ = спросить(name=ЗАВОДИМ["name"], form="tablet", dose=2,
                       substance="")
    шаг("ВЕЩЕСТВО-ЕЩЁ-НЕ-ВПИСАНО-не-блокирует", есть is True,
        "пустое поле — не то же самое, что несовпадение")

    # ── G2: ПО КОДУ — БЕЗ СВЯЗКИ ──────────────────────────────────
    есть, т = спросить(code_gtin=ЗАВОДИМ["code_gtin"])
    шаг("по-GTIN-совпадение-найдено", есть,
        "код опознаёт торговую единицу целиком")
    if есть:
        з2 = т.get("запись") or {}
        шаг("по-GTIN-приехала-схема", (з2.get("own_dosage_text") or "") == СХЕМА)
        шаг("по-GTIN-приехала-дата", bool(т.get("когда_словом")),
            "«%s»" % (т.get("когда_словом") or ""))

    есть, _ = спросить(code_gtin="04600000000024")
    шаг("ЧУЖОЙ-GTIN-не-предлагается", есть is False)

    # ── ВЫДЕРЖКИ СПРАВОЧНИКА В АРХИВ НЕ ИДУТ ─────────────────────
    c = база()
    столбцы = [r[1] for r in c.execute("PRAGMA table_info(medkit_archive)")]
    c.close()
    шаг("выдержек-справочника-в-архиве-НЕТ",
        "dosage_text" not in столбцы and "indications_text" not in столбцы,
        "снимок чужой страницы на дату — новая карточка возьмёт свежий")
    шаг("срока-и-количества-в-архиве-НЕТ",
        "expires_ym" not in столбцы and "qty_left" not in столбцы,
        "ими пачки и отличаются")


# ═══════════════════════════════════════════════════════════════════════
# ЭКРАН: ВИДИМЫЙ БЛОК НА ЗАСЕЯННОМ АРХИВЕ (BACKLOG №317, заход 320)
# ═══════════════════════════════════════════════════════════════════════
#
# Прогон выше спрашивает ЭНДПОИНТ и свою же запись. Блок «Такую упаковку
# вы уже заводили», который видит человек, не проверял НИКТО: ни одна
# проба не открывала форму и не смотрела, показан ли он (§6.3, мерка
# меряет видимое). До задачи 317 и смотреть было не на чем — архив
# стенда был пуст.
#
# Путь ЧЕЛОВЕКА: кнопка «Вручную», поля формы, уход фокуса — тот же
# `blur`, от которого страница спрашивает архив. Видимость — у самого
# блока `checkVisibility` с опциями (у `[hidden]` он честно false).
# ГОЛОВНОЙ браузер (§6.0.3).
#
# СЛУЧАИ ПАРАМИ «ЕСТЬ / НЕТ»: без обратного «блока нет» неотличимо
# от «блок не показывается вовсе».
ЭКРАН_СЛУЧАИ = (
    # (имя шага, поля формы, ждём блок, что обязано быть в тексте)
    ("та-же-пачка-ДРУГОЕ-КОЛИЧЕСТВО-предлагается",
     dict(name="Пенталгин", form="tablet", dose="1", total="10"), True,
     "Пенталгин"),
    ("по-GTIN-без-названия-предлагается",
     dict(code="04607000000026"), True, "Пенталгин"),
    ("полная-связка-предлагается", dict(name="Имодиум", form="capsule",
                                        dose="2"), True, "Имодиум"),
    ("ДРУГАЯ-РАЗОВАЯ-ДОЗА-не-предлагается",
     dict(name="Имодиум", form="capsule", dose="1"), False, ""),
    ("ДРУГАЯ-ФОРМА-не-предлагается",
     dict(name="Имодиум", form="tablet", dose="2"), False, ""),
    ("ДВЕ-СИЛЫ-ВЕЩЕСТВА-без-вещества-не-предлагается",
     dict(name="Кетонал", form="tablet", dose="1"), False, ""),
    ("СИЛА-ВЕЩЕСТВА-названа-предлагается",
     dict(name="Кетонал", form="tablet", dose="1", sub="Кетопрофен, 150 мг"),
     True, "Кетонал"),
)
# ПОДЛОГ В СТРАНИЦУ — блок не показывается никогда. Ломает ровно звено
# «ответ сервера → видимый блок»; сервер не тронут.
ПОДЛОГ_ЭКРАНА = (
    "document.addEventListener('DOMContentLoaded', () => {"
    " window.аптИскатьВАрхиве = async function () {"
    "  /*ПОДЛОГ-317*/ document.getElementById('apt-arch').hidden = true; };"
    "});")


def засеяно():
    c = база()
    н = c.execute("SELECT COUNT(*) FROM medkit_archive a JOIN users u "
                  "ON u.id = a.user_id WHERE u.email = ?", (ПОЧТА,)).fetchone()[0]
    c.close()
    return н


async def _экран_прогон(подлог=False):
    from playwright.async_api import async_playwright
    собрано = засеяно()
    print("=" * 72)
    print("АРХИВ НА ЭКРАНЕ: записей архива у аккаунта стенда %d%s"
          % (собрано, " · ПОДЛОГ В СТРАНИЦЕ" if подлог else ""))
    print("=" * 72)
    доказано = None
    async with async_playwright() as p:
        бр = await p.chromium.launch(headless=False)
        ктх = await бр.new_context(viewport={"width": 1920, "height": 1100})
        if подлог:
            await ктх.add_init_script(ПОДЛОГ_ЭКРАНА)
        pg = await ктх.new_page()
        await pg.goto(БАЗА + "/login", wait_until="domcontentloaded")
        await pg.fill("input[name=email]", ПОЧТА)
        await pg.fill("input[name=password]", ПАРОЛЬ)
        await pg.click("button[type=submit]")
        await pg.wait_for_load_state("networkidle")
        if "/login" in pg.url:
            raise SystemExit("ВХОД НЕ СОСТОЯЛСЯ — мерить нечего")
        for имя, поля, ждём, в_тексте in ЭКРАН_СЛУЧАИ:
            await pg.goto(БАЗА + "/medkit", wait_until="networkidle")
            if подлог and доказано is None:
                доказано = await pg.evaluate(
                    "() => String(window.аптИскатьВАрхиве).includes('ПОДЛОГ-317')")
            await pg.click("#apt-add-manual")
            await pg.wait_for_selector("#apt-f-name", state="visible")
            if "form" in поля:
                await pg.select_option("#apt-f-form", поля["form"])
            for ключ, ид in (("name", "#apt-f-name"), ("sub", "#apt-f-sub"),
                             ("dose", "#apt-f-dose"), ("total", "#apt-f-total")):
                if ключ in поля:
                    await pg.fill(ид, поля[ключ])
            if "code" in поля:
                # код лежит в свёрнутом «Дополнительно» — раскрываем, как человек
                if not await pg.evaluate(
                        "() => document.getElementById('apt-f-code')"
                        ".checkVisibility()"):
                    await pg.evaluate(
                        "() => { const d = document.getElementById('apt-f-code')"
                        ".closest('details'); if (d) d.open = true; }")
                await pg.fill("#apt-f-code", поля["code"])
            await pg.wait_for_load_state("networkidle")
            # ПОСЛЕДНИЙ уход фокуса — со всеми полями сразу
            поле = "#apt-f-code" if "code" in поля else "#apt-f-name"
            запросов = []
            pg.on("request", lambda r: запросов.append(1)
                  if "/medkit/api/archive-match" in r.url else None)
            await pg.focus(поле)
            await pg.evaluate("() => document.activeElement.blur()")
            # ОТВЕТ НЕ ОБЯЗАТЕЛЕН: страница, не спросившая архив, — тоже
            # исход, и назвать его обязан ШАГ, а не упавшее ожидание
            for _ in range(40):
                if запросов:
                    break
                await pg.wait_for_timeout(50)
            await pg.wait_for_load_state("networkidle")
            await pg.wait_for_timeout(150)
            виден, текст = await pg.evaluate(
                "() => { const б = document.getElementById('apt-arch');"
                " return [б.checkVisibility({checkOpacity: true,"
                " checkVisibilityCSS: true}),"
                " document.getElementById('apt-arch-text').textContent]; }")
            ок = (виден == ждём) and (not ждём or в_тексте in текст)
            шаг(имя, ок, "запросов к архиву %d, блок %s (ждём %s)%s" % (
                len(запросов),
                "ВИДЕН" if виден else "скрыт", "виден" if ждём else "скрыт",
                ", текст «%s»" % текст[:60] if виден else ""), собрано=собрано)
            if имя.startswith("та-же-пачка") and виден and ждём:
                await pg.click("#apt-arch button")
                вещество = await pg.input_value("#apt-f-sub")
                шаг("заполнить-по-ней-перенесло-вещество",
                    вещество == "Напроксен + дротаверин + кофеин",
                    "в поле «%s»" % вещество, собрано=собрано)
        await бр.close()
    if подлог:
        print("   ДОКАЗАТЕЛЬСТВО ПОДЛОГА: функция в странице подменена — %s"
              % доказано)
    return доказано


def экран(подлог=False):
    import asyncio
    return asyncio.run(_экран_прогон(подлог))


def контроль():
    """ПОДЛОГ: правило строгости ослаблено — сверка только по имени.

    ДОКАЗАТЕЛЬСТВО НЕЗАВИСИМО ОТ ВЕРДИКТА (§6.0.3): печатается, что
    ОТВЕТИЛ сервер на запрос с ЧУЖОЙ дозировкой, а не число находок
    пробы. «Проба покраснела» и «подлог состоялся» — разные факты.

    ЯКОРЬ ОБНОВЛЁН ЗАДАЧЕЙ 255 (блок E): связка получила третье
    условие, `вещество_не_против(з)` — прежний якорь кончался
    на `доза_та_же(...)` и молча переставал находиться после этой
    правки. Подлог по-прежнему сводит связку к одному названию —
    снимает ВСЕ три условия разом, а не только два.
    """
    print()
    print("── КОНТРОЛЬ: строгость ослаблена ──────────────────────────")
    п = "main.py"
    было = io.open(п, encoding="utf-8").read()
    подлог = было.replace(
        "               and (з.form or \"\") == (form or \"\")\n"
        "               and доза_та_же(з.dose, dose)\n"
        "               and вещество_не_против(з)]",
        "               ]")
    if подлог == было:
        print("   ОСТАНОВЛЕНО: якорь подлога не найден — правило"
              " переписали, контроль недействителен")
        return 2
    # ── ВОЗВРАТ ТОЧНОЙ КОПИЕЙ, А НЕ ОБРАТНОЙ ЗАМЕНОЙ ─────────────
    #
    # Первая версия возвращала код обратной заменой, и якорь `]`
    # нашёлся РАНЬШЕ — в теле запроса разбора фото. Правка встала
    # не туда, файл остался синтаксически верным, а разбор фото был
    # сломан. Копия целого файла такого не умеет по построению.
    io.open(КОПИЯ, "w", encoding="utf-8", newline=chr(10)).write(было)
    io.open(п, "w", encoding="utf-8", newline=chr(10)).write(подлог)
    print("   подлог наложен: связка сведена к одному названию.")
    print("   копия целого файла: %s" % КОПИЯ)
    print("   ПЕРЕЗАПУСТИТЕ СТЕНД и прогоните `py check_medkit_archive.py`.")
    print("   Ожидание: шаги «ДРУГАЯ-ДОЗИРОВКА» и «ДРУГАЯ-ФОРМА» — ПЛОХО.")
    print("   ВОЗВРАТ: py check_medkit_archive.py --вернуть")
    return 0


def вернуть():
    """Возврат кода из копии, снятой перед подлогом."""
    if not os.path.exists(КОПИЯ):
        print("Копии нет — возвращать нечего (подлог не накладывался).")
        return 2
    io.open("main.py", "w", encoding="utf-8", newline=chr(10)).write(
        io.open(КОПИЯ, encoding="utf-8").read())
    os.remove(КОПИЯ)
    print("Код возвращён из копии. ПЕРЕЗАПУСТИТЕ СТЕНД.")
    return 0


if __name__ == "__main__":
    if "--вернуть" in sys.argv:
        sys.exit(вернуть())
    if "--экран" in sys.argv:
        доказано = экран(подлог=КОНТРОЛЬ)
        print()
        print("ШАГОВ %d, ПЛОХИХ %d, ПРОПУСКОВ %d" % (шагов, плохих, пропусков))
        if КОНТРОЛЬ:
            # контроль экрана: подлог обязан СОСТОЯТЬСЯ и быть НАЙДЕН
            sys.exit(0 if (доказано and плохих) else 1)
        sys.exit(1 if плохих else (2 if пропусков else 0))
    if КОНТРОЛЬ:
        sys.exit(контроль())
    прогон()
    print()
    print("ШАГОВ %d, ПЛОХИХ %d" % (шагов, плохих))
    sys.exit(1 if плохих else 0)
