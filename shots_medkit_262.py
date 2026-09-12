# -*- coding: utf-8 -*-
"""СНИМКИ ЗАХОДА 262: строка упаковки и лента с двумя лицами.

НЕ проверка, кадры смотрит человек — код возврата всегда 0.

ШИРИНЫ 2560, 1920 и 390: у владельца два монитора, и 1440 среди них
нет намеренно (тот же довод, что у задачи 143).

ЛЕНТА СНИМАЕТСЯ ПРОКРУЧЕННОЙ К СТРОКЕ С РАСХОЖДЕНИЕМ ЛИЦ, а не
сверху: приписка «отметка: …» стоит только там, где нажавший
и принявший разные, и кадр «как открылось» показал бы обычные строки,
на которых блок A ничего не меняет (§8.0 — состояние ищется ПО ФАКТУ).

ГРУППА ИЩЕТСЯ ПО ФАКТУ, а не по номеру позиции: первая карточка
сегодня одна, завтра другая.

ГОЛОВНОЙ БРАУЗЕР НЕ НУЖЕН: кадры смотрит глаз, а не мерка, и разница
в 15 px полосы прокрутки для этого несущественна (§6.0.3 требует
головного там, где ответ ЗАВИСИТ от ширины контейнера).
"""
import asyncio
import os
import sys
import probe_guard  # noqa: F401  ПРОПУСК вместо трассы (§6.0.1)

sys.stdout.reconfigure(encoding="utf-8")

БАЗА = os.getenv("HOVER_BASE", "http://127.0.0.1:8899")
ПОЧТА = os.getenv("MEDKIT_EMAIL", "screenshot@local.dev")
ПАРОЛЬ = os.getenv("MEDKIT_PASSWORD", "Screenshot-Local-2026")
КУДА = os.getenv("SHOTS_DIR", "review_screenshots")
ШИРИНЫ = (2560, 1920, 390)


async def войти(pg):
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


async def кадр(pg, имя, ш):
    путь = os.path.join(КУДА, "262-%s-%d.png" % (имя, ш))
    await pg.screenshot(path=путь)
    print("   %s" % путь)


async def снять(pg, ш):
    await pg.goto(БАЗА + "/medkit", wait_until="networkidle")
    await pg.wait_for_selector(".apt-card", timeout=20000)

    кид = await pg.evaluate(
        "() => { const s = document.querySelector('.apt-packs-src');"
        "        return s ? s.id.replace('apt-packs-','') : null; }")
    if not кид:
        raise SystemExit("НА СТЕНДЕ НЕТ ГРУППЫ ИЗ НЕСКОЛЬКИХ ПАЧЕК (§8.0)")

    # ── БЛОК B: СТРОКА УПАКОВКИ ЦЕЛИКОМ И КРУПНО ────────────────────
    await pg.click("[data-packs='%s']" % кид)
    await pg.wait_for_timeout(700)
    await кадр(pg, "окно-упаковок", ш)

    окно = await pg.query_selector("#apt-packs-win .modal-sh, #apt-packs-win")
    if окно:
        await окно.screenshot(
            path=os.path.join(КУДА, "262-упаковки-окно-крупно-%d.png" % ш))
        print("   %s" % os.path.join(КУДА,
                                     "262-упаковки-окно-крупно-%d.png" % ш))

    # ── БЛОК A: ЛЕНТА У СТРОКИ С РАСХОЖДЕНИЕМ ЛИЦ ───────────────────
    await pg.evaluate("() => закрыть_модалку('apt-packs-win')")
    await pg.wait_for_timeout(400)
    await pg.click("#apt-circle-open")
    await pg.wait_for_timeout(1200)
    await pg.click("[data-ctab='feed']")
    await pg.wait_for_timeout(700)
    нашлась = await pg.evaluate(
        "() => { const l = [...document.querySelectorAll('.apt-feed-item')]"
        "        .find(x => x.querySelector('.apt-feed-by'));"
        "        if (!l) return false;"
        "        l.scrollIntoView({block: 'center'}); return true; }")
    await pg.wait_for_timeout(400)
    if not нашлась:
        # НАЗЫВАЕТСЯ ВСЛУХ, а не снимается молча: кадр без строки
        # с расхождением показал бы, что блок A ничего не изменил
        print("   ВНИМАНИЕ: строки «приём за другого» на стенде нет — "
              "пересейте (§8.0)")
    await кадр(pg, "лента-два-лица", ш)


async def главная():
    from playwright.async_api import async_playwright
    os.makedirs(КУДА, exist_ok=True)
    async with async_playwright() as p:
        br = await p.chromium.launch(headless=True)
        for ш in ШИРИНЫ:
            pg = await br.new_page(viewport={"width": ш, "height": 1000},
                                   has_touch=(ш <= 560))
            await войти(pg)
            print("── ширина %d ──" % ш)
            await снять(pg, ш)
            await pg.close()
        await br.close()


if __name__ == "__main__":
    asyncio.run(главная())
