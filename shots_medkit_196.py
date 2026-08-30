# -*- coding: utf-8 -*-
"""СНИМКИ ЗАХОДА 196: диалог ассистента и панель участников без прокрутки.

НЕ ПРОВЕРКА, кадры смотрит человек. Код возврата всегда 0.

═══════════════════════════════════════════════════════════════════════
ЧТО СНИМАЕТСЯ И ПОЧЕМУ ИМЕННО ТАК
═══════════════════════════════════════════════════════════════════════

БЛОК A — ДИАЛОГ. Реплики идут ПОДРЯД, с хвостом переписки, и первой
стоит та, что даёт СТОП: без неё дефект захода не воспроизводится
вовсе (замер — BACKLOG №196, A.1). Ответы ЖИВЫЕ: подставленный
показывал бы не то, что увидит владелец.

ДИАЛОГ ВЕДЁТСЯ ОДИН РАЗ, А СНИМАЕТСЯ ДВАЖДЫ. Переписка хранится
на СЕРВЕРЕ и общая для всех устройств (§5.8), поэтому вторая ширина
открывает ТУ ЖЕ беседу, не тратя ни одного вызова модели. Это не
экономия ради экономии: так и выглядит боевой случай владельца —
один разговор, два экрана.

БЛОК B — ПАНЕЛЬ УЧАСТНИКОВ, все четыре вкладки. Кадр снимается
ПОСЛЕ прохода по вкладкам, а не на первой: прокрутка, ради которой
заход и был, появлялась на всех четырёх сразу, а исчезала сама
от одного наведения на кнопку «?» (`ui.js` ставит подсказке
инлайновый `position: fixed` и обратно не снимает).

    py make_local_user.py --seed
    py -m uvicorn main:app --port 8899
    py shots_medkit_196.py
"""
import asyncio
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace")

БАЗА = os.environ.get("MEDKIT_BASE", "http://127.0.0.1:8899")
ПОЧТА = "screenshot@local.dev"
ПАРОЛЬ = "Screenshot-Local-2026"
КУДА = "review_screenshots"
# ШИРИНЫ НАЗВАЛ ВЛАДЕЛЕЦ: два его монитора и телефон. 1440 среди них
# нет намеренно — экрана такой ширины у него не существует (§5.8)
ШИРИНЫ = (2560, 390)

ДИАЛОГ = (
    "Я приняла препарат Б 2 часа назад, поспала, симптомы вернулись. "
    "Что можно сделать? Может другое обезболивающее?",
    "Привет, у меня сдулся живот, болит. Что мне можно принять?",
    "Я ещё ничего не принимал, просто скажи, что у меня есть в аптечке",
    "Ну да, речь про эту пачку. Стоит ещё одну принять "
    "или другое лекарство посоветуешь?",
    "болит голова",
    "что от аллергии",
    "выпила препарат А, не помогло",
    "сколько дней пить препарат Б",
)


async def _войти(pg):
    await pg.goto(БАЗА + "/login", wait_until="domcontentloaded")
    await pg.fill("input[name=email]", ПОЧТА)
    await pg.fill("input[name=password]", ПАРОЛЬ)
    if await pg.query_selector(".cf-turnstile"):
        for _ in range(60):
            if await pg.evaluate(
                    "() => { const t = document.querySelector("
                    "'[name=\"cf-turnstile-response\"]'); return t && t.value; }"):
                break
            await pg.wait_for_timeout(500)
    await pg.click("button[type=submit]")
    await pg.wait_for_load_state("networkidle")
    if "/login" in pg.url:
        raise SystemExit("ВХОД НЕ СОСТОЯЛСЯ — снимать нечего")


async def _спросить(pg, текст):
    """Задать вопрос и ДОЖДАТЬСЯ ответа, а не таймера.

    Снимок по таймеру ловит «Смотрю…» — и кадр показывает не ответ,
    а ожидание. Ждём разблокировки кнопки отправки, тем же признаком,
    что у съёмок захода 193.
    """
    await pg.fill("#apt-ai-in", текст)
    await pg.click("#apt-ai-send")
    ЖДЁМ = ("() => { const к = document.getElementById('apt-ai-send');"
            "  return !!к && к.disabled; }")
    for _ in range(120):
        if not await pg.evaluate(ЖДЁМ):
            break
        await pg.wait_for_timeout(500)
    await pg.wait_for_timeout(400)


async def снимки():
    from playwright.async_api import async_playwright
    os.makedirs(КУДА, exist_ok=True)
    сделано = []
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for н, ширина in enumerate(ШИРИНЫ):
            сенсор = ширина < 800
            ctx = await b.new_context(
                viewport={"width": ширина,
                          "height": 1200 if not сенсор else 844},
                has_touch=сенсор, is_mobile=сенсор, device_scale_factor=1)
            pg = await ctx.new_page()
            await _войти(pg)
            await pg.goto(БАЗА + "/medkit", wait_until="networkidle")
            await pg.add_style_tag(
                content="html, * { scroll-behavior: auto !important }")
            await pg.evaluate("() => аптАИОткрыть && аптАИОткрыть()")
            await pg.wait_for_timeout(900)

            if н == 0:
                # ПЕРЕПИСКА ЧИСТИТСЯ ПЕРЕД ПРОГОНОМ: кадр обязан
                # показывать ответы на ЭТИ вопросы, а не хвост
                # прошлого разговора
                await pg.evaluate(
                    "async () => { await fetch('/medkit/api/chat',"
                    " {method: 'DELETE'});"
                    " if (window.аптАИПеречитать) await аптАИПеречитать(); }")
                await pg.wait_for_timeout(500)
                for текст in ДИАЛОГ:
                    await _спросить(pg, текст)
                print("диалог проведён живыми вызовами: реплик %d"
                      % await pg.evaluate(
                          "() => document.getElementById('apt-ai-log')"
                          ".children.length"))
            else:
                # ТА ЖЕ БЕСЕДА НА ВТОРОМ ЭКРАНЕ — без единого вызова
                # модели: переписка лежит на сервере и общая (§5.8)
                await pg.evaluate(
                    "async () => { if (window.аптАИПеречитать)"
                    " await аптАИПеречитать(); }")
                await pg.wait_for_timeout(600)

            имя = "%s/196-диалог-%d.png" % (КУДА, ширина)
            await pg.screenshot(path=имя, full_page=False)
            сделано.append(имя)

            # ── ХВОСТ ЛЕНТЫ КРУПНО: последние ответы читаются глазом ──
            await pg.evaluate(
                "() => { const л = document.getElementById('apt-ai-log');"
                " if (л) л.scrollTop = л.scrollHeight; }")
            await pg.wait_for_timeout(300)
            имя = "%s/196-диалог-хвост-%d.png" % (КУДА, ширина)
            await pg.screenshot(path=имя, full_page=False)
            сделано.append(имя)

            # ── ПАНЕЛЬ УЧАСТНИКОВ, ЧЕТЫРЕ ВКЛАДКИ ────────────────────
            await pg.evaluate("() => аптАИЗакрыть && аптАИЗакрыть()")
            await pg.wait_for_timeout(300)
            await pg.evaluate("() => аптКругОткрыть()")
            await pg.wait_for_timeout(800)
            вкладки = await pg.evaluate(
                "() => Array.from(document.querySelectorAll("
                "'#apt-circle [data-ctab]')).map(к => к.dataset.ctab)")
            for вк in вкладки:
                await pg.evaluate(
                    "(и) => { const к = document.querySelector("
                    "'#apt-circle [data-ctab=\"'+и+'\"]'); if (к) к.click(); }",
                    вк)
                await pg.wait_for_timeout(400)
                перелив = await pg.evaluate(
                    "() => { const т = document.querySelector("
                    "'#apt-circle .modal-body'); return т ?"
                    " Math.max(0, Math.round(т.scrollWidth - т.clientWidth))"
                    " : null; }")
                имя = "%s/196-круг-%s-%d.png" % (КУДА, вк, ширина)
                await pg.screenshot(path=имя, full_page=False)
                сделано.append("%s  (перелив вбок %s px)" % (имя, перелив))
            await ctx.close()
        await b.close()
    print()
    for с in сделано:
        print("  " + с)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(снимки()))
