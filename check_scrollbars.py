# -*- coding: utf-8 -*-
"""ПОЛОСЫ ПРОКРУТКИ: ширина, резерв под них и дёрганье (BACKLOG №260, F).

МЕРКА, код возврата 0 (кроме `--контроль`): каким должен быть резерв —
решение о ФАКТИЧЕСКОЙ ширине полосы у этого браузера, а не о нашем коде.

═══════════════════════════════════════════════════════════════════════
ГОЛОВНОЙ БРАУЗЕР ОБЯЗАТЕЛЕН (§6.0.3)

Headless прячет полосу прокрутки БЕЗ ИЗЪЯТИЯ МЕСТА: `clientWidth`
там равен `offsetWidth` даже при живой прокрутке. То есть весь класс
вопросов «сколько отнимает полоса» такой пробе невидим по построению —
она печатает ноль не потому, что ноль.

Замер на одном коде: headless 858/858, головной 843/858 — след полосы
15 px.

═══════════════════════════════════════════════════════════════════════
ЧТО СПРАШИВАЕТСЯ

  ШИРИНА    сколько пикселей полоса отнимает у содержимого. Это
            и есть число, которому обязан равняться резерв: больше —
            лишний зазор у окон без прокрутки, меньше — дёрганье
  РЕЗЕРВ    объявлен ли `scrollbar-gutter` и сколько он отнимает
  ДЁРГАНЬЕ  ширина содержимого ДО появления прокрутки и ПОСЛЕ.
            Разница обязана быть 0: иначе текст переезжает в момент,
            когда список дорос до края
"""
import argparse
import asyncio
import os
import sys
import probe_guard  # noqa: F401  ПРОПУСК вместо трассы (§6.0.1)

sys.stdout.reconfigure(encoding="utf-8")

БАЗА = os.getenv("HOVER_BASE", "http://127.0.0.1:8899")
ПОЧТА = os.getenv("MEDKIT_EMAIL", "screenshot@local.dev")
ПАРОЛЬ = os.getenv("MEDKIT_PASSWORD", "Screenshot-Local-2026")
ШИРИНЫ = (2560, 1920, 390)

ПЛОХО = []


def шаг(имя, ок, чем=""):
    if not ок:
        ПЛОХО.append(имя)
    print("  %-5s %-40s %s" % ("OK" if ок else "ПЛОХО", имя, чем))
    return ок


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
        raise SystemExit("ВХОД НЕ СОСТОЯЛСЯ — мерить нечего")


# ШИРИНА ПОЛОСЫ МЕРИТСЯ НА СВОЁМ БЛОКЕ, а не на странице: у страницы
# резерв уже стоит (`scrollbar-gutter` у `html`), и разницы там не будет
# по построению — то есть проба мерила бы собственную починку.
ШИРИНА_ПОЛОСЫ = """() => {
  const d = document.createElement('div');
  d.style.cssText = 'position:absolute;top:-9999px;width:200px;height:100px;overflow-y:scroll';
  d.innerHTML = '<div style="height:400px"></div>';
  document.body.appendChild(d);
  const w = d.offsetWidth - d.clientWidth;
  const стиль = getComputedStyle(d);
  d.remove();
  return {ширина: w, тонкая: стиль.scrollbarWidth || 'auto'};
}"""

# ДЁРГАНЬЕ: блок с резервом и без — сравнение ширины содержимого
# ДО прокрутки и ПОСЛЕ. Меряется НА ЖИВОМ окне, а не на выдуманном
# блоке: резерв объявлен у `.modal-body`, и вопрос ровно про него.
ДЁРГАНЬЕ = """(сел) => {
  const т = document.querySelector(сел);
  if (!т) return null;
  const было = т.clientWidth;
  const проб = document.createElement('div');
  proбHeight(проб);
  т.appendChild(проб);
  const стало = т.clientWidth;
  проб.remove();
  return {до: Math.round(было), после: Math.round(стало),
          разница: Math.round(было - стало),
          прокрутка_была: т.scrollHeight > т.clientHeight + 1,
          резерв: getComputedStyle(т).scrollbarGutter};
  function proбHeight(э) { э.style.cssText = 'height:4000px'; }
}"""


async def замер(pg, ш):
    print("── ширина окна %d ──" % ш)
    await pg.goto(БАЗА + "/medkit", wait_until="networkidle")
    await pg.wait_for_selector(".apt-card", timeout=20000)

    п = await pg.evaluate(ШИРИНА_ПОЛОСЫ)
    print("     ФАКТИЧЕСКАЯ ШИРИНА ПОЛОСЫ: %s px (scrollbar-width: %s)"
          % (п["ширина"], п["тонкая"]))

    # окна, у которых тело прокручивается
    окна = (("apt-circle-open", "#apt-circle .modal-body", "Общая аптечка"),)
    for кнопка, сел, имя in окна:
        await pg.click("#" + кнопка)
        await pg.wait_for_timeout(900)
        д = await pg.evaluate(ДЁРГАНЬЕ, сел)
        if д:
            шаг("%s-без-дёрганья" % имя.replace(" ", "-"), д["разница"] == 0,
                "ширина содержимого %d → %d (резерв: %s)"
                % (д["до"], д["после"], д["резерв"]))
        await pg.keyboard.press("Escape")
        await pg.wait_for_timeout(400)
    return п["ширина"]


# ПОДЛОГ: РЕЗЕРВ СНЯТ. Возвращает состояние, при котором появление
# полосы сжимает содержимое — то есть дёрганье, которое резерв и лечит.
# Кладётся В СТРАНИЦУ, кода экрана не трогает.
ПОДЛОГ_БЕЗ_РЕЗЕРВА = (
    "document.addEventListener('DOMContentLoaded', () => {"
    "  const s = document.createElement('style');"
    "  s.textContent = '.modal-body { scrollbar-gutter: auto !important; }';"
    "  document.head.appendChild(s); });")


async def прогон(головной=True, подлог=None):
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        br = await p.chromium.launch(headless=not головной)
        ширины_полосы = {}
        for ш in ШИРИНЫ:
            pg = await br.new_page(viewport={"width": ш, "height": 1000},
                                   has_touch=(ш <= 560))
            if подлог:
                await pg.add_init_script(подлог)
            await войти(pg)
            ширины_полосы[ш] = await замер(pg, ш)
            await pg.close()
        await br.close()
        return ширины_полосы


def главная():
    р = argparse.ArgumentParser()
    р.add_argument("--headless", action="store_true",
                   help="прогон БЕЗ головы — для доказательства слепоты")
    р.add_argument("--контроль", action="store_true",
                   help="подлог: резерв снят, дёрганье обязано вернуться")
    а = р.parse_args()
    print("=" * 70)
    print("ПОЛОСЫ ПРОКРУТКИ — BACKLOG №260, блок F")
    print("браузер: %s" % ("HEADLESS (слеп к ширине полосы)" if а.headless
                           else "ГОЛОВНОЙ"))
    print("=" * 70)
    ширины = asyncio.run(прогон(головной=not а.headless,
                                подлог=(ПОДЛОГ_БЕЗ_РЕЗЕРВА if а.контроль else None)))
    print()
    print("ШИРИНА ПОЛОСЫ ПО ШИРИНАМ ОКНА: %s" % ширины)
    print("плохих %d %s" % (len(ПЛОХО), ПЛОХО or ""))
    if а.контроль:
        # С ПОДЛОГОМ ПРОБА ОБЯЗАНА НАЙТИ ДЁРГАНЬЕ. Не нашла — она
        # не отвечает ни на что, и «дёрганья нет» без этого прогона
        # не значит ничего (§6.0.3)
        print("КОНТРОЛЬ: %s" % ("проба ВИДИТ дёрганье" if ПЛОХО
                                else "ПРОБА СЛЕПА — находок нет при снятом резерве"))
        sys.exit(0 if ПЛОХО else 1)
    sys.exit(0)


if __name__ == "__main__":
    главная()
