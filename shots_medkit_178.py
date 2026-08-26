"""СНИМКИ ЗАХОДА 178 — ДЛЯ ПРИЁМКИ ВЛАДЕЛЬЦЕМ.

НЕ ПРОВЕРКА: кода «правильно» у неё нет, кадры смотрит человек.
Код возврата всегда 0.

Что снимается — ровно то, что просила постановка (пункт 5 общих
требований):

  1. СПИСОК ПОКУПОК со ВСЕМИ ЧЕТЫРЬМЯ видами позиций сразу, включая
     одну зачёркнутую купленную;
  2. ЛЕНТА ЧАТА с разделителем дня и кнопкой «в список покупок»
     в ответе, где ассистент сказал «этого нет»;
  3. ОКНО СПОСОБА ПРИЁМА для СОЛОДКИ СИРОПА — то есть тот исход блока
     A, который заход и завёл: форма и вещество сошлись, мешает только
     отсутствующая у нас дозировка.

ШИРИНЫ 2560 И 390 — их назвал владелец; 1440 среди них нет намеренно,
экрана такой ширины у него не существует (тот же довод, что у задач
143, 176 и 177).

═══════════════════════════════════════════════════════════════════════
ДАННЫЕ КАДРА ЗАВОДЯТСЯ САМИ И УБИРАЮТСЯ ЗА СОБОЙ

Ни один из трёх кадров на стенде не воспроизводится «как есть»: список
покупок пуст, переписки нет, а «Солодки сироп» в аптечке стенда нет
вовсе. Съёмка заводит их сама — и в БАЗУ, то есть ровно туда, откуда
их читает боевой код, — а в конце убирает.

ПОЧЕМУ ЭТО НЕ ПОДЛОГ: подставляется СОСТОЯНИЕ, а не поведение. Строки
списка рисует настоящий `_medkit_buy.html`, ленту — настоящая
`аптАИВспомнить`, окно приёма — настоящая `аптДозыОткрыть`. Подставь мы
разметку — кадр показывал бы не то, что увидит владелец.

ОТВЕТ АССИСТЕНТА ЛОЖИТСЯ В ПЕРЕПИСКУ ГОТОВЫМ ТЕЛОМ, и это названо:
живой вызов модели стоит токенов и не воспроизводится (два прогона
дают разные наборы), а вопрос кадра — «есть ли разделитель дня и кнопка
покупок», а не «что ответила модель». Живьём ответ снимает
`check_medkit_query.py` — там ему и место.

    py shots_medkit_178.py                # обе ширины
    py shots_medkit_178.py --ширина 390
"""

import argparse
import asyncio
import io
import json
import os
import pathlib
import sqlite3
import sys

БАЗА = os.environ.get("HOVER_BASE", "http://127.0.0.1:8899")
DB = os.environ.get("DB_PATH", "app.db")
ПОЧТА = "screenshot@local.dev"
ПАРОЛЬ = "Screenshot-Local-2026"
КУДА = pathlib.Path(os.environ.get("SHOTS_DIR", "C:/Temp/claude/shots178"))
ШИРИНЫ = [2560, 390]

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace")

# Имена пробных записей вынесены сюда: уборка ищет их по этим же
# строкам, и разойдись два перечня — мусор остался бы на стенде
# и поехал бы в чужой кадр (BACKLOG №152)
СИРОП = "Солодки сироп"
ПОКУПКИ_МЕТКА = "Кадр178"


def _в_базу(запрос, параметры=()):
    conn = sqlite3.connect(DB)
    try:
        cur = conn.cursor()
        cur.execute(запрос, параметры)
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def _прибрать():
    conn = sqlite3.connect(DB)
    try:
        conn.execute("DELETE FROM medkit_buy_items WHERE user_id = "
                     "(SELECT id FROM users WHERE email = ?)", (ПОЧТА,))
        conn.execute("DELETE FROM chat_messages WHERE tool = 'medkit' "
                     "AND user_id = (SELECT id FROM users WHERE email = ?)",
                     (ПОЧТА,))
        conn.execute("DELETE FROM medkit_items WHERE name = ?", (СИРОП,))
        conn.commit()
    finally:
        conn.close()


def _завести_состояние():
    """Четыре вида строк покупок, двухдневная переписка и сироп солодки."""
    _прибрать()
    u = "(SELECT id FROM users WHERE email = '%s')" % ПОЧТА

    # ── ЧЕТЫРЕ ВИДА СТРОК, включая одну зачёркнутую ─────────────────
    строки = [
        ("Что-то от головной боли", "Спрашивали 26.08 — в аптечке этого "
         "не нашлось", "ai", None, None, None, None),
        ("Креон 10000", "Панкреатин, 10000 ЕД · Капсулы · истёк 03.2026",
         "expired", "Панкреатин, 10000 ЕД", "capsule", "capsule", None),
        ("Необутин", "Тримебутин, 200 мг · осталось 5 из 30", "low",
         "Тримебутин, 200 мг", "tablet", "tablet", None),
        ("Пластырь", "", "hand", None, None, None, "куплено"),
    ]
    for имя, почему, источник, вещество, форма, единица, куплено in строки:
        _в_базу(
            "INSERT INTO medkit_buy_items (user_id, name, why, source,"
            " substance, form, unit, is_rx, bought_on, created_at)"
            " VALUES (%s, ?, ?, ?, ?, ?, ?, 0, %s, datetime('now'))"
            % (u, "date('now', 'localtime')" if куплено else "NULL"),
            (имя, почему, источник, вещество, форма, единица))

    # ── ПЕРЕПИСКА ЗА ДВА ДНЯ ────────────────────────────────────────
    тело = json.dumps({
        "вид": "запрос", "вопрос": "болит голова",
        "вступление": "", "нашлось": [], "просрочено": [],
        "рецептурные": [],
        "нет": "В вашей аптечке нет обезболивающих. Стоит обратиться "
               "в аптеку — фармацевт подберёт средство и учтёт "
               "особенности.",
        "группа": "обезболивающее", "оговорка": ""}, ensure_ascii=False)
    _в_базу("INSERT INTO chat_messages (user_id, role, content, tool,"
            " created_at) VALUES (%s, 'user', ?, 'medkit',"
            " datetime('now', '-1 days'))" % u,
            ("У меня болит голова. Есть что-то в аптечке?",))
    _в_базу("INSERT INTO chat_messages (user_id, role, content, tool,"
            " payload, created_at) VALUES (%s, 'assistant', ?, 'medkit', ?,"
            " datetime('now', '-1 days'))" % u,
            ("В вашей аптечке нет обезболивающих.", тело))
    _в_базу("INSERT INTO chat_messages (user_id, role, content, tool,"
            " created_at) VALUES (%s, 'user', ?, 'medkit', datetime('now'))"
            % u, ("Живот болит, что есть?",))

    # ── СИРОП СОЛОДКИ: ФОРМА И ВЕЩЕСТВО ЕСТЬ, ДОЗИРОВКИ НЕТ ─────────
    #
    # Ровно тот случай блока A, ради которого заход и правил чистку
    # названия: у Видаля страница есть, а у нас в карточке нечему
    # совпадать с её «4 г/100 г»
    return _в_базу(
        "INSERT INTO medkit_items (user_id, name, substance, form, unit,"
        " qty_left, qty_total, dose, expires_ym, is_rx, created_at,"
        " updated_at) VALUES (%s, ?, 'Солодка', 'syrup', 'ml', 60, 100, 5,"
        " '2027-09', 0, datetime('now'), datetime('now'))" % u, (СИРОП,))


async def _войти(pg):
    await pg.goto(БАЗА + "/login", wait_until="domcontentloaded")
    await pg.fill("input[name=email]", ПОЧТА)
    await pg.fill("input[name=password]", ПАРОЛЬ)
    if await pg.query_selector(".cf-turnstile"):
        for _ in range(60):
            if await pg.evaluate("() => { const t = document.querySelector("
                                 "'[name=\"cf-turnstile-response\"]'); "
                                 "return t && t.value; }"):
                break
            await pg.wait_for_timeout(500)
    await pg.click("button[type=submit]")
    await pg.wait_for_load_state("networkidle")
    if "/login" in pg.url:
        raise SystemExit("ВХОД НЕ СОСТОЯЛСЯ — снимать нечего")


async def _снять(pg, имя, ширина, селектор=None):
    КУДА.mkdir(parents=True, exist_ok=True)
    путь = КУДА / ("%s-%d.png" % (имя, ширина))
    цель = await pg.query_selector(селектор) if селектор else None
    if селектор and not цель:
        print("   ПРОПУЩЕН %s — нет %s" % (имя, селектор))
        return
    if цель:
        await цель.screenshot(path=str(путь), animations="disabled")
    else:
        await pg.screenshot(path=str(путь), animations="disabled")
    print("   %s" % путь.name)


async def кадры(pg, ширина, id_сиропа):
    # ── 1 · СПИСОК ПОКУПОК ──────────────────────────────────────────
    await pg.goto(БАЗА + "/medkit?buy=1", wait_until="networkidle")
    await pg.add_style_tag(content="html,*{scroll-behavior:auto!important}")
    await pg.wait_for_timeout(600)
    await _снять(pg, "pokupki", ширина, "#apt-buy")
    # Он же в составе экрана — чтобы видеть, сколько места блок отнял
    # у сетки карточек
    await _снять(pg, "pokupki-ekran", ширина)

    # ── 2 · ЛЕНТА ЧАТА ──────────────────────────────────────────────
    await pg.evaluate("() => аптАИОткрыть()")
    await pg.wait_for_timeout(1200)
    await _снять(pg, "chat", ширина, "#apt-ai")
    await pg.evaluate("() => аптАИЗакрыть()")
    await pg.wait_for_timeout(300)

    # ── 3 · ОКНО СПОСОБА ПРИЁМА ДЛЯ СИРОПА СОЛОДКИ ──────────────────
    #
    # Кнопка «Найти в справочнике» НЕ НАЖИМАЕТСЯ: она ходит в чужую
    # сеть, и кадр зависел бы от доступности Видаля. Снимается
    # состояние, в котором окно открывается У ВЛАДЕЛЬЦА — с причиной,
    # уже лежащей в базе от фонового поиска при заведении
    есть = await pg.evaluate("(id) => !!аптПозиция(id)", str(id_сиропа))
    if не_ноль(есть):
        await pg.evaluate("(id) => аптДозыОткрыть(id)", str(id_сиропа))
        await pg.wait_for_timeout(900)
        await _снять(pg, "solodka-priyom", ширина, ".modal-ov.open .modal")
        await pg.evaluate("() => закрыть_модалку('apt-doses')")
    else:
        print("   ПРОПУЩЕН solodka-priyom — позиции нет в АПТ_ПОЗИЦИИ")


def не_ноль(з):
    """`evaluate` отдаёт `None` и при отсутствии элемента, и при `false`.
    Отдельное имя — чтобы это не читалось как «проверка на истинность»."""
    return bool(з)


async def прогон(ширина, id_сиропа):
    from playwright.async_api import async_playwright
    сенсор = ширина < 800
    print("── %d px ──" % ширина)
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context(
            viewport={"width": ширина, "height": 1400 if not сенсор else 844},
            has_touch=сенсор, is_mobile=сенсор, device_scale_factor=1)
        pg = await ctx.new_page()
        await _войти(pg)
        try:
            await кадры(pg, ширина, id_сиропа)
        finally:
            await ctx.close()
            await b.close()


def main():
    р = argparse.ArgumentParser()
    р.add_argument("--ширина", type=int)
    a = р.parse_args()
    ширины = [a.ширина] if a.ширина else ШИРИНЫ
    print("СНИМКИ ЗАХОДА 178 -> %s" % КУДА)
    print("Состояние кадра заводится САМО и убирается в конце.")
    id_сиропа = _завести_состояние()
    print("Заведено: 4 строки покупок, 3 реплики, «%s» id %s"
          % (СИРОП, id_сиропа))
    try:
        for ш in ширины:
            asyncio.run(прогон(ш, id_сиропа))
    finally:
        _прибрать()
        print("Пробные записи убраны.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
