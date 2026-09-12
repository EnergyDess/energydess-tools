# -*- coding: utf-8 -*-
"""СНИМКИ ЗАХОДА 246: список долгов, шторка способа приёма, ответ.

НЕ ПРОВЕРКА — кадры смотрит человек, код возврата всегда 0.

ЧТО СНИМАЕТСЯ И ПОЧЕМУ ИМЕННО ЭТО:

  · СПИСОК ДОЛГОВ (блок B) — новый раздел окна перепроверки; кадр
    нужен, чтобы увидеть чипы «чего не хватает» и порядок строк;
  · ШТОРКА СПОСОБА ПРИЁМА во ВСЕХ достижимых состояниях (блок D) —
    ровно там владелец увидел «текст расписан хаотично»;
  · ОТВЕТ АССИСТЕНТА с разведёнными карточками и блоком различий
    (блоки C и E) — ответ модели ЖИВОЙ, и кадр ждёт разблокировки
    кнопки отправки, а не таймера: снимок по таймеру ловил бы
    «Смотрю…», а подставленный показывал бы не то, что увидит
    владелец.

ПЕРЕПИСКА ЧИСТИТСЯ БОЕВЫМ ЭНДПОИНТОМ перед прогоном: хвост прошлого
разговора уезжает в промпт, и ответ на «что из этого выбрать»
относился бы к чужому списку.

ШИРИНЫ 2560 И 390 — их назвал владелец; 1440 среди них нет намеренно,
экрана такой ширины у него не существует (тот же довод, что у задачи
143).

КАДРЫ ЛОЖАТСЯ В `review_screenshots/`, закрытый `.gitignore`:
на них видно содержимое аптечки, а названия лекарств — сведения
о здоровье (§5.1, §8.0).

    py shots_medkit_246.py
"""
import asyncio
import os
import sys

# ВЫВОД В UTF-8: без этого печать знака вне cp1251 роняет пробу
# `UnicodeEncodeError` при ЛЮБОМ перенаправлении (`> файл`,
# конвейер, `capture_output`) — то есть у всякого, кто запустит
# её не в консоль. Найдено проверкой 35 (BACKLOG №307).
sys.stdout.reconfigure(encoding="utf-8")

БАЗА = os.getenv("HOVER_BASE", "http://127.0.0.1:8899")
ПОЧТА = os.getenv("STAND_EMAIL", "screenshot@local.dev")
ПАРОЛЬ = os.getenv("STAND_PASSWORD", "Screenshot-Local-2026")
КУДА = "review_screenshots"
ШИРИНЫ = [2560, 390]


async def _войти(pg):
    await pg.goto(БАЗА + "/login", wait_until="domcontentloaded")
    await pg.fill("input[name=email]", ПОЧТА)
    await pg.fill("input[name=password]", ПАРОЛЬ)
    if await pg.query_selector(".cf-turnstile"):
        for _ in range(60):
            if await pg.evaluate("() => { const t = document.querySelector("
                                 "'[name=\"cf-turnstile-response\"]');"
                                 " return t && t.value; }"):
                break
            await pg.wait_for_timeout(500)
    await pg.click("button[type=submit]")
    await pg.wait_for_load_state("networkidle")
    if "/login" in pg.url:
        raise SystemExit("ВХОД НЕ СОСТОЯЛСЯ — снимать нечего")


async def кадр(pg, имя, ш):
    путь = os.path.join(КУДА, "246-%s-%s.png" % (имя, ш))
    await pg.screenshot(path=путь)
    print("   %s" % путь)


async def прогон():
    from playwright.async_api import async_playwright
    os.makedirs(КУДА, exist_ok=True)
    async with async_playwright() as pw:
        бр = await pw.chromium.launch()
        for ш in ШИРИНЫ:
            ctx = await бр.new_context(
                viewport={"width": ш, "height": 900 if ш > 500 else 780},
                device_scale_factor=1, has_touch=(ш <= 500),
                is_mobile=(ш <= 500))
            pg = await ctx.new_page()
            await _войти(pg)
            await pg.goto(БАЗА + "/medkit", wait_until="networkidle")
            print("── %s px" % ш)

            # ── СПИСОК ДОЛГОВ ────────────────────────────────────
            await pg.click("#apt-recheck-open")
            await pg.wait_for_timeout(1500)
            await кадр(pg, "долги", ш)
            await pg.keyboard.press("Escape")
            await pg.wait_for_timeout(300)

            # ── ШТОРКА ВО ВСЕХ ДОСТИЖИМЫХ СОСТОЯНИЯХ ─────────────
            ид = await pg.evaluate(
                "() => [...document.querySelectorAll('[data-doses]')]"
                ".map(к => к.dataset.doses)")
            видано = set()
            for i in ид:
                await pg.evaluate("(id) => аптДозыОткрыть(id)", str(i))
                await pg.wait_for_timeout(400)
                метка = await pg.evaluate("""() => {
                  const т = document.getElementById('apt-doses-body');
                  const в = !!т.querySelector('.apt-doses-text, .apt-doses-blocks');
                  const с = !!т.querySelector('.apt-own');
                  return (в ? 'выдержка' : 'нет') + (с ? '-своя' : '');
                }""")
                if метка not in видано:
                    видано.add(метка)
                    await кадр(pg, "шторка-" + метка, ш)
                await pg.keyboard.press("Escape")
                await pg.wait_for_timeout(150)

            # ── ОТВЕТ АССИСТЕНТА ─────────────────────────────────
            await pg.evaluate("fetch('/medkit/api/chat',{method:'DELETE'})")
            await pg.wait_for_timeout(400)
            await pg.click("#apt-ai-open")
            await pg.wait_for_timeout(700)
            for вопрос, имя in (("болит живот, что выпить", "ответ"),
                                ("что из этого выбрать", "различия")):
                await pg.fill("#apt-ai-in", вопрос)
                await pg.click("#apt-ai-send")
                # ЖДЁМ РАЗБЛОКИРОВКИ КНОПКИ, А НЕ ТАЙМЕРА
                await pg.wait_for_function(
                    "() => !document.getElementById('apt-ai-send').disabled",
                    timeout=150000)
                await pg.wait_for_timeout(800)
                await кадр(pg, имя, ш)
            await ctx.close()
        await бр.close()


if __name__ == "__main__":
    asyncio.run(прогон())
    sys.exit(0)
