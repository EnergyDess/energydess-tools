# -*- coding: utf-8 -*-
"""СНИМКИ ЗАХОДА 222 — кадры смотрит человек, не проверка.

BACKLOG №222. НЕ проверка: кода «правильно» тут нет, код возврата
всегда 0. Снимает ровно то, что назвал владелец приёмкой:

  · загрузка с ПУСТЫМ КЕШЕМ — запасной гарнитурой и основной, рядом,
    чтобы подмену было видно глазом, а не только числом;
  · ряд карточек новой раскладки — свёрнутый и РАСКРЫТЫЙ, потому что
    вся суть D.1 в том, что раскрытие ничего не двигает выше кнопок;
  · тюбик с рядом ступеней — орган, которого раньше не было вовсе;
  · `/profile` целиком: часовой пояс до подстановки и после неё,
    и карточка удаления аккаунта, у которой резервируется высота.

ШИРИНЫ 2560 И 390 — их назвал владелец; 1440 среди них нет, экрана
такой ширины у него не существует (тот же довод, что у задачи 143).

СОСТОЯНИЕ ПОЯСА ПОДСТАВЛЯЕТСЯ ПРЯМО В ТЕКСТ, и это названо: скрипт
страницы подставляет настоящее имя зоны СИНХРОННО, до первого кадра,
и «Определяется…» живьём поймать нечем — оно существует ровно те
миллисекунды, пока разбирается разметка. Путь кода при этом тот же:
меняется textContent того же элемента тем же способом.

Кадры уезжают в `review_screenshots/` — каталог закрыт `.gitignore`:
на снимках видно содержимое аптечки, а названия лекарств это сведения
о здоровье (§5.1, §8.0).
"""
import asyncio
import os
import sys

БАЗА = os.environ.get("HOVER_BASE", "http://127.0.0.1:8899")
ПОЧТА = "screenshot@local.dev"
ПАРОЛЬ = "Screenshot-Local-2026"
ШИРИНЫ = [2560, 390]
КУДА = "review_screenshots"

ПОЯС_ПОСТАВИТЬ = """((т) => {
  const э = document.getElementById('tz-auto');
  if (!э) return false;
  э.textContent = т;
  document.body.offsetHeight;
  return true;
})"""

# ШРИФТ ПОДСОВЫВАЕТСЯ ТЕМ ЖЕ СПОСОБОМ, ЧТО В check_font_shift:
# запросы отбиты, значит первый кадр нарисован ЗАПАСНОЙ гарнитурой,
# и это ровно то, что человек видит первые сотни миллисекунд.
ПОДСУНУТЬ = """(async () => {
  const кир = new FontFace('Manrope',
    "url('/static/fonts/manrope-cyrillic.woff2')", {weight: '400 800'});
  const лат = new FontFace('Manrope',
    "url('/static/fonts/manrope-latin.woff2')", {weight: '400 800'});
  await Promise.all([кир.load(), лат.load()]);
  document.fonts.add(кир); document.fonts.add(лат);
  await document.fonts.ready;
  document.body.offsetHeight;
  return document.fonts.size;
})()"""


async def _войти(стр):
    await стр.goto(БАЗА + "/login", wait_until="domcontentloaded",
                   timeout=45000)
    await стр.fill("input[name=email]", ПОЧТА)
    await стр.fill("input[name=password]", ПАРОЛЬ)
    if await стр.query_selector(".cf-turnstile"):
        for _ in range(60):
            если = await стр.evaluate(
                "() => { const t = document.querySelector("
                "'[name=\"cf-turnstile-response\"]'); return t && t.value; }")
            if если:
                break
            await стр.wait_for_timeout(500)
    await стр.click("button[type=submit]")
    await стр.wait_for_load_state("networkidle")
    if "/login" in стр.url:
        raise SystemExit("ВХОД НЕ СОСТОЯЛСЯ — снимать нечего")


async def _снять(стр, имя, ш):
    путь = os.path.join(КУДА, "222-%s-%d.png" % (имя, ш))
    await стр.screenshot(path=путь, full_page=True, animations="disabled")
    print("   %s" % путь)


async def прогон():
    from playwright.async_api import async_playwright
    os.makedirs(КУДА, exist_ok=True)
    async with async_playwright() as p:
        бр = await p.chromium.launch()
        for ш in ШИРИНЫ:
            print("── ширина %d ──" % ш)
            кон = await бр.new_context(viewport={"width": ш, "height": 1000})
            стр = await кон.new_page()
            await _войти(стр)

            # ── ПУСТОЙ КЕШ: запасная гарнитура и основная ────────────
            await стр.route("**/static/fonts/**", lambda r: r.abort())
            о = await стр.goto(БАЗА + "/medkit", wait_until="domcontentloaded",
                               timeout=45000)
            assert о.status == 200, "аптечка ответила %s" % о.status
            try:
                await стр.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            await стр.wait_for_timeout(900)
            await _снять(стр, "аптечка-ЗАПАСНОЙ-шрифт", ш)
            await стр.unroute("**/static/fonts/**")
            await стр.evaluate(ПОДСУНУТЬ)
            await стр.wait_for_timeout(600)
            await _снять(стр, "аптечка-ОСНОВНОЙ-шрифт", ш)

            # ── РЯД КАРТОЧЕК: свёрнутый и раскрытый ─────────────────
            await _снять(стр, "карточки-свёрнуто", ш)
            # СПИСОК УЕХАЛ В ОКНО (BACKLOG №223): раскрывает его
            # МЕТКА «N упак.», а `<details>` в карточке больше нет
            сум = стр.locator(".apt-stack[data-packs]").first
            if await сум.count():
                await сум.click()
                await стр.wait_for_timeout(500)
                await _снять(стр, "карточки-РАСКРЫТО", ш)
                await сум.click()
                await стр.wait_for_timeout(300)

            # ── ТЮБИК: ряд ступеней вместо кнопки списания ──────────
            ряд = стр.locator(".apt-scale").first
            if await ряд.count():
                await ряд.scroll_into_view_if_needed()
                await стр.wait_for_timeout(300)
                карт = ряд.locator("xpath=ancestor::article[1]")
                путь = os.path.join(КУДА, "222-тюбик-ступени-%d.png" % ш)
                await карт.screenshot(path=путь, animations="disabled")
                print("   %s" % путь)

            # ── ПРОФИЛЬ: пояс до подстановки и после ────────────────
            о = await стр.goto(БАЗА + "/profile",
                               wait_until="domcontentloaded", timeout=45000)
            assert о.status == 200, "профиль ответил %s" % о.status
            await стр.wait_for_timeout(900)
            await стр.evaluate(ПОЯС_ПОСТАВИТЬ, "Определяется…")
            await стр.wait_for_timeout(200)
            await _снять(стр, "профиль-пояс-ДО", ш)
            await стр.evaluate(ПОЯС_ПОСТАВИТЬ,
                               "Определён автоматически: Europe/Moscow")
            await стр.wait_for_timeout(200)
            await _снять(стр, "профиль-пояс-ПОСЛЕ", ш)
            await кон.close()
        await бр.close()
    return 0


if __name__ == "__main__":
    print("СНИМКИ ЗАХОДА 222 — кадры смотрит человек (§8.0).")
    print("Каталог %s закрыт .gitignore: на кадрах видно аптечку.\n" % КУДА)
    sys.exit(asyncio.run(прогон()))
