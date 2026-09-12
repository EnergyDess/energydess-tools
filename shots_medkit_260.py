# -*- coding: utf-8 -*-
"""СНИМКИ ЗАХОДА 260: окно упаковок, выбор участника, полоса, лента.

НЕ проверка, кадры смотрит человек — код возврата всегда 0.

ШИРИНЫ 2560, 1920 и 390: у владельца два монитора, и 1440 среди них
нет намеренно (тот же довод, что у задачи 143).

ВЫБОР СНИМАЕТСЯ В ДВУХ СОСТОЯНИЯХ — свёрнутом и раскрытом. Вся суть
блока B в том, что список раскрывается НА МЕСТЕ, а не всплывает поверх
окна, и одиночный кадр показал бы только половину.

ГРУППА ИЩЕТСЯ ПО ФАКТУ, а не по номеру позиции: первая карточка
сегодня одна, завтра другая (§8.0).
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
    путь = os.path.join(КУДА, "260-%s-%d.png" % (имя, ш))
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

    await pg.click("[data-packs='%s']" % кид)
    await pg.wait_for_timeout(700)
    await кадр(pg, "упаковки-свёрнуто", ш)

    await pg.click("#apt-packs-for-btn")
    await pg.wait_for_timeout(600)
    await кадр(pg, "упаковки-выбор-раскрыт", ш)

    чужой = await pg.evaluate(
        "() => { const b = [...document.querySelectorAll('#apt-who-list [data-who]')]"
        "        .find(x => (x.textContent||'').trim() !== 'Вы');"
        "        return b ? Number(b.dataset.who) : null; }")
    if чужой:
        await pg.click("#apt-who-list [data-who='%d']" % чужой)
        await pg.wait_for_timeout(600)
        await кадр(pg, "упаковки-отмечаю-за-соседа", ш)

    # ПРИЁМ ИЗ ВТОРОЙ ПАЧКИ — полоса подтверждения со второй строкой
    await pg.click("#apt-packs-body li.apt-pack:nth-child(2) [data-take]")
    await pg.wait_for_timeout(1400)
    await кадр(pg, "полоса-за-другого", ш)

    # ЛЕНТА С КАРАНДАШАМИ
    await pg.evaluate("() => закрыть_модалку('apt-packs-win')")
    await pg.wait_for_timeout(400)
    await pg.click("#apt-circle-open")
    await pg.wait_for_timeout(1200)
    await pg.click("[data-ctab='feed']")
    await pg.wait_for_timeout(700)
    await кадр(pg, "лента-карандаш", ш)


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
