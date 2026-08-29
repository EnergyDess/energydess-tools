# -*- coding: utf-8 -*-
"""СНИМКИ ЗАХОДА 199 — кадры смотрит человек, не проверка.

ЧТО СНИМАЕТСЯ И ПОЧЕМУ ИМЕННО ЭТО:

  E.1  ШТОРКА СПОСОБА ПРИЁМА в ДВУХ состояниях — схема есть и схемы
       нет. Набор кнопок у них разный, и весь дефект был в том, что ряд
       выглядел по-разному при разном их числе. Один кадр показал бы
       половину.
  E.2  ПОЛЕ ПОИСКА с набранным текстом: крестик виден только тогда,
       когда есть что чистить. Пустое поле про него не говорит ничего.
  E.3  ГРУППА «2 упаковки» — главный кадр блока E: до правки картинки
       там не было при живом снимке.
  B.1  КАРТОЧКА БЕЗ ВЕЩЕСТВА — строка «вещество не указано», которой
       раньше не было вовсе.

СОСТОЯНИЕ ОПОЗНАЁТСЯ ПО ЭКРАНУ, А НЕ ПО ДАННЫМ СТРАНИЦЫ: `АПТ_ПОЗИЦИИ`
объявлен через `let`, а `let` свойства `window` не создаёт вовсе
(на этом уже спотыкался контроль задачи 181). Окно открывается, и то,
что вышло, читается по блоку выдержки — по тому же, который видит
человек.

ШИРИНЫ НАЗВАЛ ВЛАДЕЛЕЦ: 2560 и 390. Экрана 1440 у него нет.

    py make_local_user.py --seed
    py -m uvicorn main:app --port 8899
    py shots_medkit_199.py
"""
import asyncio
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace")

БАЗА = os.environ.get("MEDKIT_BASE", "http://127.0.0.1:8899")
ПОЧТА, ПАРОЛЬ = "screenshot@local.dev", "Screenshot-Local-2026"
КУДА = os.environ.get("SHOTS_DIR", "C:/Temp/claude/shots199")
ШИРИНЫ = [2560, 390]


async def _войти(pg):
    await pg.goto(БАЗА + "/login", wait_until="domcontentloaded")
    await pg.fill("input[name=email]", ПОЧТА)
    await pg.fill("input[name=password]", ПАРОЛЬ)
    await pg.click("button[type=submit]")
    await pg.wait_for_load_state("networkidle")
    if "/login" in pg.url:
        raise SystemExit("ВХОД НЕ СОСТОЯЛСЯ — снимать нечего")


async def _кадр(pg, имя, ш, элемент=None):
    путь = os.path.join(КУДА, "%s-%s.png" % (имя, ш))
    if элемент:
        э = await pg.query_selector(элемент)
        if not э:
            print("   НЕТ ЭЛЕМЕНТА %s — кадр %s не снят" % (элемент, имя))
            return
        await э.screenshot(path=путь)
    else:
        await pg.screenshot(path=путь, animations="disabled")
    print("   %s" % путь)


async def прогон():
    from playwright.async_api import async_playwright
    os.makedirs(КУДА, exist_ok=True)
    async with async_playwright() as pw:
        бр = await pw.chromium.launch()
        for ш in ШИРИНЫ:
            print("### %s px" % ш)
            ctx = await бр.new_context(
                viewport={"width": ш, "height": 1000 if ш > 500 else 800},
                device_scale_factor=1, has_touch=(ш <= 500),
                is_mobile=(ш <= 500))
            pg = await ctx.new_page()
            await _войти(pg)
            await pg.goto(БАЗА + "/medkit", wait_until="networkidle")
            await pg.wait_for_timeout(500)

            # ── E.2: крестик виден только при непустом запросе ────────
            await pg.fill("#apt-q", "цет")
            await pg.dispatch_event("#apt-q", "input")
            await pg.wait_for_timeout(300)
            await _кадр(pg, "E2-поиск-с-крестиком", ш, ".apt-search")
            await pg.fill("#apt-q", "")
            await pg.dispatch_event("#apt-q", "input")
            await pg.wait_for_timeout(300)

            # ── E.3 и B.1: карточки ──────────────────────────────────
            await _кадр(pg, "E3-сетка-карточек", ш)
            группа = await pg.query_selector(".apt-card:has(.apt-stack)")
            if группа:
                await группа.screenshot(
                    path=os.path.join(КУДА, "E3-группа-2-упаковки-%s.png" % ш))
                print("   %s/E3-группа-2-упаковки-%s.png" % (КУДА, ш))
            else:
                print("   ГРУППЫ ИЗ ДВУХ ПАЧЕК НА СТЕНДЕ НЕТ — кадр не снят")

            # ── E.1: шторка в двух состояниях ────────────────────────
            ид_все = await pg.evaluate(
                "() => [...document.querySelectorAll('[data-doses]')]"
                ".map(к => к.dataset.doses)")
            снято = set()
            for ид in ид_все[:8]:
                await pg.evaluate("(id) => аптДозыОткрыть(id)", str(ид))
                await pg.wait_for_timeout(400)
                есть = await pg.evaluate(
                    "() => !!document.querySelector('#apt-doses-body "
                    ".apt-doses-text, #apt-doses-body .apt-doses-blocks')")
                метка = "схема-есть" if есть else "схемы-нет"
                if метка not in снято:
                    снято.add(метка)
                    await _кадр(pg, "E1-шторка-" + метка, ш, ".modal-sh")
                await pg.keyboard.press("Escape")
                await pg.wait_for_timeout(200)
                if len(снято) == 2:
                    break
            if len(снято) < 2:
                print("   СНЯТО ТОЛЬКО %s — второго состояния на стенде нет"
                      % ", ".join(снято))
            await ctx.close()
        await бр.close()
    print("\nКадры смотрит человек. Проверкой это не является.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(прогон()))
