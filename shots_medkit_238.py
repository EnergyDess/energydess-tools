# -*- coding: utf-8 -*-
"""СНИМКИ ЗАХОДА 238: единица приёма, диалог заведения, ряд кнопок.

═══════════════════════════════════════════════════════════════════════
ЧТО ЭТО И ЧЕМ НЕ ЯВЛЯЕТСЯ
═══════════════════════════════════════════════════════════════════════

НЕ ПРОВЕРКА: кадры смотрит человек, кода «правильно» тут нет.

ЧЕТЫРЕ КАДРА, И КАЖДЫЙ ПРО СВОЁ:

  · КАРТОЧКА ЖИДКОСТИ С ЕДИНИЦЕЙ ПРИЁМА — главный кадр блока A.
    На ней обязано быть видно «348 из 350 кап · во флаконе 10 мл»:
    первое убывает от кнопки, второе не двигается. Позиция ищется
    ПО ФАКТУ записанного объёма, а не по номеру — первая карточка
    сегодня одна, завтра другая (урок `shots_medkit_200`);

  · ДИАЛОГ ЗАВЕДЕНИЯ ЦЕЛИКОМ — вопрос, ответ числом, дополненный
    черновик и ряд «Открыть карточку / Пропустить». Ответы модели
    ЖИВЫЕ, и кадр ждёт РАЗБЛОКИРОВКИ кнопки отправки, а не таймера:
    снимок по таймеру ловил бы «Смотрю…». Переписка ЧИСТИТСЯ боевым
    эндпоинтом перед прогоном — иначе в кадр попадает хвост прошлого
    разговора, а на второй ширине ещё и заслон повтора;

  · РЯД КНОПОК НА 390 — то, на что жаловался владелец: было 199 px
    пустоты слева во второй строке;

  · ОКНО ПРАВКИ ПОВЕРХ ФОНА — с новым полем «Во флаконе» и меню
    выбора фото (два пути вместо одного).

ПИШЕТ В БАЗУ СТЕНДА (переписка ассистента) и ходит в живую модель.
После прогона стенд пересеять.

    py shots_medkit_238.py
"""
import asyncio
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

БАЗА = os.getenv("HOVER_BASE", "http://127.0.0.1:8899")
ПОЧТА = "screenshot@local.dev"
ПАРОЛЬ = "Screenshot-Local-2026"
КУДА = os.getenv("SHOTS_DIR", "review_screenshots")
ШИРИНЫ = (2560, 390)


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


async def _ждать_ответа(pg, потолок=90):
    """Кнопка отправки разблокирована — значит ответ приехал ЦЕЛИКОМ.

    По таймеру снимок ловил бы «Смотрю…»; признак берётся у самого
    органа, а не у времени.
    """
    for _ in range(потолок * 2):
        if not await pg.evaluate("() => document.getElementById("
                                 "'apt-ai-send')?.disabled"):
            return True
        await pg.wait_for_timeout(500)
    return False


async def кадры(pw, ширина):
    бр = await pw.chromium.launch()
    к = await бр.new_context(viewport={"width": ширина, "height": 900},
                             has_touch=(ширина <= 640),
                             device_scale_factor=1)
    pg = await к.new_page()
    await _войти(pg)

    # ── 1. КАРТОЧКА ЖИДКОСТИ С ЕДИНИЦЕЙ ПРИЁМА ──────────────────────
    await pg.goto(БАЗА + "/medkit", wait_until="networkidle")
    await pg.wait_for_timeout(900)
    # КАРТОЧКА ИЩЕТСЯ ПО ФАКТУ ОБЪЁМА, и не любая: нужна та, где
    # единицы РАЗНЫЕ («кап» против «мл»), — на ней и видно, что объём
    # не участвует в счёте. У сиропа приписки нет вовсе, и такой кадр
    # ответил бы не на тот вопрос
    ид = await pg.evaluate("""() => {
      const карт = [...document.querySelectorAll('.apt-card')];
      const с = карт.find(к => /кап · во флаконе/.test(
        (к.querySelector('.apt-qty-cap') || {}).textContent || ''))
        || карт.find(к => /во флаконе/.test(
        (к.querySelector('.apt-qty-cap') || {}).textContent || ''));
      if (!с) return null;
      с.scrollIntoView({block: 'center'});
      с.setAttribute('data-кадр', '1');
      return (с.querySelector('.apt-qty-cap') || {}).textContent || 'есть';
    }""")
    print("  [%d] карточка с объёмом: %s"
          % (ширина, (ид or "НЕ НАЙДЕНА").strip()))
    await pg.wait_for_timeout(400)
    # СНИМАЕТСЯ САМА КАРТОЧКА, А НЕ ЭКРАН. Первый прогон показал,
    # почему: `scrollIntoView` привёл к нужной карточке, а в кадр
    # попала соседняя — экран шире одной карточки, и что на нём
    # окажется, решает раскладка, а не прицел
    карточка = await pg.query_selector("[data-кадр]")
    if карточка:
        await карточка.screenshot(
            path="%s/238-карточка-жидкость-%d.png" % (КУДА, ширина))
    else:
        await pg.screenshot(
            path="%s/238-карточка-жидкость-%d.png" % (КУДА, ширина))

    # ── 3. РЯД КНОПОК (главный кадр E.2 — на 390) ───────────────────
    #
    # СНИМАЕТСЯ САМ РЯД, а не экран: первый прогон дал кадр, на котором
    # ряда нет вовсе — страница уехала прокруткой предыдущего шага,
    # и что попадёт в кадр, решала раскладка, а не прицел. Та же
    # ошибка, что с карточкой, и в том же скрипте
    ряд = await pg.query_selector(".apt-bar")
    if ряд:
        await ряд.scroll_into_view_if_needed()
        await pg.wait_for_timeout(300)
        await ряд.screenshot(path="%s/238-ряд-кнопок-%d.png" % (КУДА, ширина))

    # ── 4. ОКНО ПРАВКИ ПОВЕРХ ФОНА ──────────────────────────────────
    ред = await pg.query_selector("[data-edit]")
    if ред:
        await ред.click()
        await pg.wait_for_timeout(800)
        await pg.screenshot(path="%s/238-окно-правки-%d.png" % (КУДА, ширина))
        await pg.keyboard.press("Escape")
        await pg.wait_for_timeout(400)

    # ── 2. ДИАЛОГ ЗАВЕДЕНИЯ ЦЕЛИКОМ ─────────────────────────────────
    #
    # ПЕРЕПИСКА ЧИСТИТСЯ БОЕВЫМ ЭНДПОИНТОМ, а не подстановкой в базу:
    # подставленная показала бы не то состояние, которое рисует сервер
    await pg.evaluate("async () => { await fetch('/medkit/api/chat',"
                      " {method: 'DELETE'}); }")
    await pg.wait_for_timeout(400)
    await pg.evaluate("() => window.аптАИОткрыть && аптАИОткрыть()")
    await pg.wait_for_timeout(900)
    for реплика in ("занеси Стрепсилс, срок годности 06.2028", "24"):
        await pg.fill("#apt-ai-in", реплика)
        await pg.click("#apt-ai-send")
        if not await _ждать_ответа(pg):
            print("  [%d] ответ не приехал за потолок — кадр диалога "
                  "показал бы «Смотрю…»" % ширина)
            break
        await pg.wait_for_timeout(600)
    await pg.evaluate("() => { const л = document.getElementById('apt-ai-log');"
                      " if (л) л.scrollTop = 1e6; }")
    await pg.wait_for_timeout(400)
    await pg.screenshot(path="%s/238-диалог-заведения-%d.png" % (КУДА, ширина))
    await бр.close()


async def главное():
    from playwright.async_api import async_playwright
    os.makedirs(КУДА, exist_ok=True)
    print("СНИМКИ ЗАХОДА 238 → %s/" % КУДА)
    print("ПИШЕТ В БАЗУ СТЕНДА (переписка) и ходит в живую модель — "
          "после прогона стенд пересеять")
    async with async_playwright() as pw:
        for ш in ШИРИНЫ:
            await кадры(pw, ш)
    for имя in sorted(os.listdir(КУДА)):
        if имя.startswith("238-"):
            print("  %s" % имя)


if __name__ == "__main__":
    asyncio.run(главное())
