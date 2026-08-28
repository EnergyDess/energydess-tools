# -*- coding: utf-8 -*-
"""СНИМКИ ЗАХОДА 190 — ДЛЯ ПРИЁМКИ ВЛАДЕЛЬЦЕМ.

НЕ ПРОВЕРКА: кода «правильно» у неё нет, кадры смотрит человек.
Код возврата всегда 0.

Что снимается — ровно то, что просит пункт 5 постановки:

  1. ЭКРАН ВТОРОГО УЧАСТНИКА С ФОТОГРАФИЯМИ — главный кадр захода.
     Снимается ПОД СОСЕДОМ, а не под владельцем: у владельца всё
     своё, и право «только своё» выглядело исправным. Ровно поэтому
     приёмка задачи 182 была зелёной при девяти подписях «Упаковка: …»
     вместо снимков на чужом экране;
  2. ЧЕТЫРЕ ВКЛАДКИ ПАНЕЛИ — в состоянии БОЕВОГО ЭКРАНА: круг общий,
     лента длинная, приглашений и блока нет. Это то состояние,
     в котором видна пустота под пустым состоянием (блок B), и его
     на сидированном стенде НЕТ — seed наполняет обе вкладки;
  3. ОКНО ПРИ ОШИБКЕ ВВОДА — сообщение об отказе поверх панели,
     высота окна при этом не меняется (блок C);
  4. ПОЛЕ ШТРИХ-КОДА СО СКАНЕРОМ — новое место кнопки (D.1);
  5. ОКНО СКАНЕРА БЕЗ ГОЛУБОЙ РАМКИ (D.5);
  6. ПОЛЕ ВВОДА В ЧАТЕ — пустое, с короткой подсказкой (блок E).

ШИРИНЫ 2560 И 390 — их назвал владелец; 1440 среди них нет намеренно,
экрана такой ширины у него не существует (тот же довод, что у задач
143, 182 и 189).

═══════════════════════════════════════════════════════════════════════
СОСТОЯНИЕ СТЕНДА МЕНЯЕТСЯ И ВОЗВРАЩАЕТСЯ

Кадр 2 требует пустых вкладок «Приглашения» и «Блок», которых seed
не оставляет. Убираются они ТЕМ ЖЕ кодом, что у мерки облика
(`check_medkit_look._приглашения_и_блок_убрать`), а сид возвращается
в `finally` тем же сидировщиком, что у пробы круга: второй сборки
круга в проекте нет (§6.0.7).

Без возврата следующий инструмент снимал бы аптечку без приглашений
и назвал бы это находкой — шестая причина неповторимости из §6.0.3.
"""
import asyncio
import io
import os
import sys
from pathlib import Path

from playwright.async_api import async_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# Консоль Windows — cp1251, и рамки в выводе роняют print целиком (§6.0)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

БАЗА = os.environ.get("MEDKIT_BASE", "http://127.0.0.1:8899")
ПОЧТА = "screenshot@local.dev"
ПАРОЛЬ = "Screenshot-Local-2026"
СОСЕД = ("neighbour@local.dev", "Neighbour-Local-2026")
КУДА = Path("review_screenshots") / "medkit-190"
ШИРИНЫ = [2560, 390]


async def _войти(pg, почта, пароль):
    await pg.goto(БАЗА + "/login", wait_until="domcontentloaded")
    await pg.fill("input[name=email]", почта)
    await pg.fill("input[name=password]", пароль)
    if await pg.query_selector(".cf-turnstile"):
        for _ in range(60):
            if await pg.evaluate(
                    "() => { const t = document.querySelector("
                    "'[name=cf-turnstile-response]'); return t && t.value; }"):
                break
            await pg.wait_for_timeout(500)
    await pg.click("button[type=submit]")
    await pg.wait_for_load_state("networkidle")
    if "/login" in pg.url:
        raise SystemExit("ВХОД НЕ СОСТОЯЛСЯ — снимать нечего")


async def _снять(pg, имя, ширина, селектор=None):
    КУДА.mkdir(parents=True, exist_ok=True)
    путь = КУДА / ("%s-%d.png" % (имя, ширина))
    цель = await pg.query_selector(селектор) if селектор else None
    if селектор and not цель:
        print("   ПРОПУЩЕН %s — нет %s" % (имя, селектор))
        return
    if цель:
        await цель.screenshot(path=str(путь), animations="disabled")
    else:
        await pg.screenshot(path=str(путь), animations="disabled")
    print("   %s" % путь.name)


# ПОДДЕЛЬНАЯ КАМЕРА — ИНАЧЕ КАДР ОКНА СКАНЕРА ПОКАЗЫВАЕТ ОТКАЗ.
# Без этих ключей Chromium камеры не даёт вовсе, и снимок «окно без
# голубой рамки» вышел бы про чёрный прямоугольник с красной строкой:
# рамки на нём нет, но и видоискателя тоже, то есть кадр отвечал бы
# не на тот вопрос. Те же ключи, что у прохода сканера.
КЛЮЧИ_КАМЕРЫ = ["--use-fake-ui-for-media-stream",
                "--use-fake-device-for-media-stream"]


async def кадры(ширина, pw):
    сенсор = ширина <= 480
    br = await pw.chromium.launch(args=КЛЮЧИ_КАМЕРЫ)

    # ── 1. ЭКРАН ВТОРОГО УЧАСТНИКА ──────────────────────────────────
    ctx = await br.new_context(
        viewport={"width": ширина, "height": 1200 if not сенсор else 844},
        has_touch=сенсор, is_mobile=сенсор, device_scale_factor=1)
    pg = await ctx.new_page()
    await _войти(pg, *СОСЕД)
    await pg.goto(БАЗА + "/medkit", wait_until="networkidle")
    await pg.wait_for_timeout(900)
    # КАРТИНКИ ЖДЁМ ФАКТИЧЕСКОЙ ЗАГРУЗКИ: `loading=lazy` снимается,
    # иначе на кадре пустые рамки вместо снимков — ровно то, на что
    # жаловался владелец, только по другой причине (§6.0.3)
    await pg.evaluate(
        "() => { document.querySelectorAll('.apt-ph img').forEach("
        "и => { и.loading = 'eager';"
        " и.scrollIntoView({block: 'center'}); }); }")
    await pg.wait_for_timeout(1500)
    видно = await pg.evaluate(
        "() => { const и = [...document.querySelectorAll('.apt-ph img')];"
        " return {всего: и.length,"
        " загружено: и.filter(э => э.complete && э.naturalWidth > 0).length,"
        " лиц: document.querySelectorAll('.apt-who img.avatar').length}; }")
    print("   участник видит: снимков %s из %s, лиц на карточках %s"
          % (видно["загружено"], видно["всего"], видно["лиц"]))
    # ВЕРНУТЬСЯ НАВЕРХ И ДОЖДАТЬСЯ: прокрутка к картинкам увела кадр
    # вниз, и первый снимок начинался с середины списка
    await pg.evaluate("() => scrollTo({top: 0, behavior: 'instant'})")
    await pg.wait_for_timeout(600)
    await _снять(pg, "участник-видит-фото", ширина)
    await pg.evaluate("() => аптКругОткрыть()")
    await pg.wait_for_timeout(800)
    await _снять(pg, "участник-панель-с-лицами", ширина,
                 "#apt-circle .modal-sh")
    await ctx.close()

    # ── 2–6. ВЛАДЕЛЕЦ ───────────────────────────────────────────────
    ctx = await br.new_context(
        viewport={"width": ширина, "height": 1200 if not сенсор else 844},
        has_touch=сенсор, is_mobile=сенсор, device_scale_factor=1,
        permissions=["camera"])
    pg = await ctx.new_page()
    await _войти(pg, ПОЧТА, ПАРОЛЬ)
    await pg.goto(БАЗА + "/medkit", wait_until="networkidle")
    await pg.wait_for_timeout(700)

    # ЧЕТЫРЕ ВКЛАДКИ ПАНЕЛИ
    await pg.evaluate("() => аптКругОткрыть()")
    await pg.wait_for_timeout(800)
    for вкл, имя in (("people", "вкладка-участники"),
                     ("invites", "вкладка-приглашения"),
                     ("feed", "вкладка-лента"),
                     ("block", "вкладка-блок")):
        await pg.evaluate("(в) => аптКругВкладка(в)", вкл)
        await pg.wait_for_timeout(400)
        await _снять(pg, имя, ширина, "#apt-circle .modal-sh")

    # ОКНО ПРИ ОШИБКЕ ВВОДА
    await pg.evaluate("() => аптКругВкладка('people')")
    await pg.wait_for_timeout(300)
    await pg.fill("#apt-circle-who", "нетакого@nowhere.dev")
    await pg.click(".apt-circle-invite button[type=submit]")
    await pg.wait_for_selector("#apt-circle-err:not([hidden])", timeout=15000)
    await pg.wait_for_timeout(400)
    await _снять(pg, "панель-отказ", ширина, "#apt-circle .modal-sh")
    await pg.evaluate("() => закрыть_модалку('apt-circle')")
    await pg.wait_for_timeout(400)

    # ПОЛЕ ШТРИХ-КОДА СО СКАНЕРОМ
    await pg.evaluate("() => аптОткрытьФорму()")
    await pg.wait_for_timeout(700)
    await pg.evaluate("() => { const к = document.getElementById("
                      "'apt-scan-field'); if (к) к.scrollIntoView("
                      "{block: 'center'}); }")
    await pg.wait_for_timeout(400)
    await _снять(pg, "поле-кода-со-сканером", ширина, ".apt-code-row")
    await pg.evaluate("() => закрыть_модалку('apt-form')")
    await pg.wait_for_timeout(400)

    # ОКНО СКАНЕРА БЕЗ ГОЛУБОЙ РАМКИ
    await pg.evaluate("() => аптСканОткрыть('чат')")
    await pg.wait_for_timeout(3500)
    рамок = await pg.evaluate(
        "() => document.querySelectorAll('#apt-scan .scan-overlay').length")
    print("   своих рамок в окне сканера: %s (обязан быть 0)" % рамок)
    await _снять(pg, "окно-сканера", ширина, "#apt-scan .modal-sh")
    await pg.evaluate("() => закрыть_модалку('apt-scan')")
    await pg.wait_for_timeout(500)

    # ПОЛЕ ВВОДА В ЧАТЕ
    await pg.evaluate("() => аптАИОткрыть()")
    await pg.wait_for_timeout(900)
    поле = await pg.evaluate(
        "() => { const п = document.getElementById('apt-ai-in');"
        " return {подсказка: п.placeholder,"
        " прокрутка: п.scrollHeight > п.clientHeight + 1}; }")
    print("   поле ввода: подсказка %r, прокрутка пустого %s"
          % (поле["подсказка"], поле["прокрутка"]))
    await _снять(pg, "поле-ввода-чата", ширина, ".apt-ai-row")
    await ctx.close()
    await br.close()


async def главное():
    import check_medkit_circle as _кр
    import check_medkit_look as _look
    print("СНИМКИ ЗАХОДА 190 → %s" % КУДА)
    print("Стенд будет ИЗМЕНЁН: приглашения и блокировки убираются "
          "ради кадра пустых вкладок. Сказано ДО прогона, а не после.")
    _look._приглашения_и_блок_убрать()
    try:
        async with async_playwright() as pw:
            for ш in ШИРИНЫ:
                print("\n── %d ──" % ш)
                await кадры(ш, pw)
    finally:
        print("\nстенд возвращён в сидированное: %s"
              % ("да" if _кр.вернуть_сид() else "НЕТ"))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(главное()))
