# -*- coding: utf-8 -*-
"""СНИМКИ ЗАХОДА 249: новая раскладка карточки, шторка, окна.

НЕ проверка — кадры смотрит человек, код возврата всегда 0.

ПРОСРОЧЕННАЯ КАРТОЧКА СНИМАЕТСЯ ОТДЕЛЬНЫМ КАДРОМ, и это требование
письма: у неё красный срок стоит рядом с красной корзиной, и вопрос
«не сливаются ли два красных» на кадре обычной карточки не задать
вовсе — там срока такого тона нет.

ПОЗИЦИЯ ИЩЕТСЯ ПО ФАКТУ, а не по номеру: первая карточка сегодня
одна, завтра другая (тот же довод, что у `shots_medkit_201`).

    py shots_medkit_249.py
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
ШИРИНЫ = (2560, 1920, 390)


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


async def главное():
    from playwright.async_api import async_playwright
    os.makedirs(КУДА, exist_ok=True)
    сняли = []
    async with async_playwright() as p:
        бр = await p.chromium.launch()
        for ш in ШИРИНЫ:
            ктх = await бр.new_context(viewport={"width": ш, "height": 900},
                                       has_touch=(ш == 390),
                                       is_mobile=(ш == 390))
            pg = await ктх.new_page()
            await _войти(pg)
            await pg.goto(БАЗА + "/medkit", wait_until="networkidle")
            await pg.wait_for_timeout(800)

            # ── РЯД КАРТОЧЕК ЦЕЛИКОМ ─────────────────────────────
            имя = "%s/249-карточки-%d.png" % (КУДА, ш)
            сетка = await pg.query_selector("#apt-grid, .apt-grid")
            if сетка:
                await сетка.screenshot(path=имя)
            else:
                await pg.screenshot(path=имя)
            сняли.append(имя)

            # ── ПРОСРОЧЕННАЯ КАРТОЧКА ────────────────────────────
            #
            # По ФАКТУ: ищем карточку с тоном `bad` у срока
            дохлая = await pg.query_selector(".apt-card:has(.apt-exp-bad)")
            if дохлая:
                имя2 = "%s/249-просрочена-%d.png" % (КУДА, ш)
                await дохлая.screenshot(path=имя2)
                сняли.append(имя2)
            else:
                print("   [%d] просроченной карточки на стенде НЕТ — "
                      "кадр не снят (состояние не воспроизведено)" % ш)

            # ── ОДНА РАБОЧАЯ КАРТОЧКА КРУПНО ─────────────────────
            живая = await pg.query_selector(".apt-card:has(.apt-take)")
            if живая:
                имя3 = "%s/249-карточка-крупно-%d.png" % (КУДА, ш)
                await живая.screenshot(path=имя3)
                сняли.append(имя3)
            # ── ОКНО ПЕРЕПРОВЕРКИ, НИЗ (блок E) ─────────────────
            #
            # Прокручивается ДОНИЗУ: вопрос блока — что под последней
            # кнопкой, и на неприкрученном окне его не задать вовсе
            await pg.click("#apt-recheck-open")
            await pg.wait_for_timeout(2500)
            await pg.evaluate(
                "() => { const т = document.querySelector("
                "'#apt-recheck-win .modal-body');"
                " if (т) т.scrollTop = т.scrollHeight; }")
            await pg.wait_for_timeout(400)
            имя4 = "%s/249-перепроверка-низ-%d.png" % (КУДА, ш)
            await pg.screenshot(path=имя4)
            сняли.append(имя4)
            await ктх.close()
        await бр.close()

    print("СНЯТО %d кадров:" % len(сняли))
    for и in сняли:
        print("   %s" % и)


if __name__ == "__main__":
    asyncio.run(главное())
