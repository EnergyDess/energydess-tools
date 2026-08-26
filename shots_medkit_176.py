# -*- coding: utf-8 -*-
"""СНИМКИ ЗАХОДА 176 ДЛЯ ПРИЁМКИ ВЛАДЕЛЬЦЕМ.

НЕ проверка: кода «правильно» у неё нет, кадры смотрит человек.
Четыре кадра на каждой ширине — ровно то, что просила постановка
перед коммитом:

  1. ряд действий на карточке (блок A);
  2. пустой результат поиска (блок B);
  3. панель с ответом на «болит живот» (блок C);
  4. панель с отказом по стоп-симптому (C.7).

ШИРИНЫ 2560, 1920 И 390 — их назвал владелец. 1440 среди них нет
намеренно: экрана такой ширины у него не существует (тот же довод,
что у `shots_medkit.py` и задачи 143).

Третий и четвёртый кадр требуют ЖИВОГО OpenRouter: ответ ассистента
рисуется по настоящему ответу модели, а подставленный показывал бы
не то, что увидит человек.

    py -m uvicorn main:app --port 8899
    py shots_medkit_176.py
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
ШИРИНЫ = [int(ш) for ш in
          os.environ.get("SHOT_WIDTHS", "2560,1920,390").split(",")]


async def _войти(pg):
    await pg.goto(БАЗА + "/login", wait_until="domcontentloaded")
    await pg.fill("input[name=email]", ПОЧТА)
    await pg.fill("input[name=password]", ПАРОЛЬ)
    if await pg.query_selector(".cf-turnstile"):
        for _ in range(60):
            if await pg.evaluate(
                    "() => { const t = document.querySelector"
                    "('[name=cf-turnstile-response]'); return t && t.value; }"):
                break
            await pg.wait_for_timeout(500)
    await pg.click("button[type=submit]")
    await pg.wait_for_load_state("networkidle")
    if "/login" in pg.url:
        raise SystemExit("ВХОД НЕ СОСТОЯЛСЯ — снимать нечего")


async def _ответ(pg, вопрос):
    """Спросить и дождаться ответа. Ждём РАЗБЛОКИРОВКИ КНОПКИ, а не
    таймера: ответ модели приходит когда придёт, и фиксированная пауза
    сняла бы кадр с надписью «Смотрю…»."""
    await pg.fill("#apt-ai-in", вопрос)
    await pg.evaluate("() => аптАИОтправитьТекст()")
    for _ in range(160):
        if await pg.evaluate(
                "() => !document.getElementById('apt-ai-send').disabled"):
            break
        await pg.wait_for_timeout(500)
    await pg.wait_for_timeout(700)


async def прогон():
    from playwright.async_api import async_playwright
    os.makedirs(КУДА, exist_ok=True)
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for ширина in ШИРИНЫ:
            сенсор = ширина < 800
            ctx = await b.new_context(
                viewport={"width": ширина, "height": 900 if not сенсор else 844},
                has_touch=сенсор, is_mobile=сенсор, device_scale_factor=1)
            pg = await ctx.new_page()
            await _войти(pg)
            await pg.goto(БАЗА + "/medkit", wait_until="networkidle")
            await pg.add_style_tag(
                content="html, * { scroll-behavior: auto !important }")
            await pg.wait_for_timeout(400)

            # 1. РЯД ДЕЙСТВИЙ. Снимаем ОКНО, а не всю страницу: ряд
            # виден на первом экране, и полный кадр в девять тысяч
            # пикселей владельцу пришлось бы листать
            await pg.evaluate(
                "() => document.querySelector('.apt-card')"
                ".scrollIntoView({block: 'center'})")
            await pg.wait_for_timeout(300)
            await pg.screenshot(path=f"{КУДА}/176-действия-{ширина}.png")

            # 2. ПУСТОЙ РЕЗУЛЬТАТ ПОИСКА. Запрос набирается тем же
            # путём, что у человека
            await pg.evaluate("() => window.scrollTo(0, 0)")
            await pg.fill("#apt-q", "заведомо-такого-нет-ъ")
            await pg.evaluate("() => аптОтобрать()")
            await pg.wait_for_timeout(400)
            await pg.screenshot(path=f"{КУДА}/176-пусто-{ширина}.png")
            await pg.fill("#apt-q", "")
            await pg.evaluate("() => аптОтобрать()")

            # 3 и 4. ПАНЕЛЬ. Стоп-симптом спрашивается ПОСЛЕДНИМ:
            # он рисуется внизу ленты, и кадр с ним заодно показывает
            # ответ выше — то есть оба состояния разом
            await pg.evaluate("() => аптАИОткрыть()")
            await pg.wait_for_timeout(300)
            await _ответ(pg, "болит живот")
            await pg.screenshot(path=f"{КУДА}/176-ответ-{ширина}.png")
            await _ответ(pg, "болит в груди")
            await pg.screenshot(path=f"{КУДА}/176-стоп-{ширина}.png")

            реплик = await pg.evaluate(
                "() => document.querySelectorAll('.apt-ai-msg').length")
            print("  %5d  снято 4 кадра, реплик в ленте %d" % (ширина, реплик))
            await ctx.close()
        await b.close()


def main():
    print("СНИМКИ ЗАХОДА 176 → %s/" % КУДА)
    asyncio.run(прогон())
    print("Кадры смотрит человек: кода «правильно» у этой пробы нет.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
