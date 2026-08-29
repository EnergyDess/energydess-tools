# -*- coding: utf-8 -*-
"""СНИМКИ ЗАХОДА 200 — кадры смотрит человек, не проверка.

ЧТО СНИМАЕТСЯ И ПОЧЕМУ ИМЕННО ЭТО:

  A. КАРТОЧКА С НАЙДЕННОЙ СХЕМОЙ И ВИДИМЫМ ИСТОЧНИКОМ. Главный
     вопрос кадра — видно ли, ОТКУДА взялось число: домен, форма,
     дозировка и дата снятия стоят рядом с дословной выдержкой.
     Это единственное место приложения, где выдуманное число опасно
     и при этом незаметно (§5.8, D.1).
  B. ШТОРКА ДЛЯ БАДА — та, у которой схемы нет и не будет:
     у добавки зарегистрированной инструкции не существует
     по построению. Кадр показывает, что отказ НАЗЫВАЕТ причину
     и предлагает выполнимое действие, а не «попробуйте ещё раз».
  C. РЯД КНОПОК ШТОРКИ — F.4. До правки ширины расходились
     на 2 px (бордюр `.btn-secondary` при `flex-basis: 0`), стало
     равно по построению. Кадр нужен на 2560 и 390 сразу: на узком
     ряд идёт столбиком, и «равно» там значит другое.
  D. ХОД ПЕРЕПРОВЕРКИ ВСЕЙ АПТЕЧКИ — блок D. Три кадра: кнопка
     до нажатия, строка хода ПО ДОРОГЕ и итог. Средний кадр —
     главный: молчащая кнопка при двух десятках обращений к чужому
     сайту неотличима от зависшей (D.3).

ПРОГОН D ПИШЕТ В БАЗУ СТЕНДА и ходит в справочник по каждой позиции
без выдержки. После него стенд ПЕРЕСЕЙТЕ: иначе следующий инструмент
снимет аптечку, у которой схемы уже найдены, — и кадр «до» получить
будет неоткуда (§6.0.3, седьмая причина неповторимости).

    py make_local_user.py --seed
    py -m uvicorn main:app --port 8899
    py shots_medkit_200.py
"""
import asyncio
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace")

БАЗА = os.environ.get("MEDKIT_BASE", "http://127.0.0.1:8899")
ПОЧТА, ПАРОЛЬ = "screenshot@local.dev", "Screenshot-Local-2026"
КУДА = os.environ.get("SHOTS_DIR", "C:/Temp/claude/shots200")
# ШИРИНЫ НАЗВАЛ ВЛАДЕЛЕЦ: два монитора плюс телефон. 1440 среди них
# нет — экрана такой ширины у него не существует (тот же довод, что
# у задачи 143)
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


async def _окно(pg, ид):
    """Открыть шторку способа приёма и дождаться её тела."""
    await pg.evaluate("(id) => аптДозыОткрыть(id)", str(ид))
    await pg.wait_for_timeout(500)


async def главная():
    from playwright.async_api import async_playwright
    os.makedirs(КУДА, exist_ok=True)
    async with async_playwright() as pw:
        бр = await pw.chromium.launch()
        for ш in ШИРИНЫ:
            ctx = await бр.new_context(
                viewport={"width": ш, "height": 1000 if ш > 500 else 800},
                device_scale_factor=1,
                has_touch=(ш <= 500), is_mobile=(ш <= 500))
            pg = await ctx.new_page()
            await _войти(pg)
            await pg.goto(БАЗА + "/medkit", wait_until="networkidle")

            # ── A и C: позиция, У КОТОРОЙ ВЫДЕРЖКА ЕСТЬ ──────────────
            # Ищется ПО ФАКТУ выдержки, а не по номеру: первая карточка
            # сегодня одна, завтра другая, и кадр «схема есть»,
            # наведённый на номер, молча снял бы состояние «схемы нет»
            ид_все = await pg.evaluate(
                "() => [...document.querySelectorAll('[data-doses]')]"
                ".map(к => к.dataset.doses)")
            со_схемой = без_схемы = None
            for ид in ид_все:
                await _окно(pg, ид)
                есть = await pg.evaluate(
                    "() => !!document.querySelector('#apt-doses-body "
                    ".apt-doses-text, #apt-doses-body .apt-doses-blocks')")
                if есть and со_схемой is None:
                    со_схемой = ид
                if not есть and без_схемы is None:
                    без_схемы = ид
                await pg.keyboard.press("Escape")
                await pg.wait_for_timeout(150)
                if со_схемой and без_схемы:
                    break

            if со_схемой:
                await _окно(pg, со_схемой)
                окно = pg.locator("#apt-doses .modal-sh")
                await окно.screenshot(
                    path="%s/A-схема-и-источник-%d.png" % (КУДА, ш))
                ряд = pg.locator("#apt-doses-body .apt-doses-acts").first
                if await ряд.count():
                    await ряд.screenshot(
                        path="%s/C-ряд-кнопок-схема-есть-%d.png" % (КУДА, ш))
                await pg.keyboard.press("Escape")
                await pg.wait_for_timeout(200)
                print("A: снято, позиция %s, ширина %d" % (со_схемой, ш))

            if без_схемы:
                await _окно(pg, без_схемы)
                окно = pg.locator("#apt-doses .modal-sh")
                await окно.screenshot(
                    path="%s/B-шторка-без-схемы-%d.png" % (КУДА, ш))
                ряд = pg.locator("#apt-doses-body .apt-doses-acts").first
                if await ряд.count():
                    await ряд.screenshot(
                        path="%s/C-ряд-кнопок-схемы-нет-%d.png" % (КУДА, ш))
                await pg.keyboard.press("Escape")
                await pg.wait_for_timeout(200)
                print("B: снято, позиция %s, ширина %d" % (без_схемы, ш))

            # ── D: ХОД ПЕРЕПРОВЕРКИ ВСЕЙ АПТЕЧКИ ────────────────────
            блок = pg.locator("#apt-recheck")
            await блок.scroll_into_view_if_needed()
            await pg.wait_for_timeout(200)
            await блок.screenshot(path="%s/D-1-кнопка-%d.png" % (КУДА, ш))

            await pg.click("#apt-recheck-btn")
            # КАДР ПО ДОРОГЕ, А НЕ ПО ТАЙМЕРУ ВСЛЕПУЮ: ждём, пока
            # в строке появится «из» — то есть пока обход реально пошёл
            try:
                await pg.wait_for_function(
                    "() => (document.getElementById('apt-recheck-note')"
                    ".textContent || '').includes(' из ')", timeout=60000)
            except Exception:                              # noqa: BLE001
                pass
            await блок.screenshot(path="%s/D-2-ход-%d.png" % (КУДА, ш))
            print("D: ход — %s"
                  % (await pg.inner_text("#apt-recheck-note")).strip()[:70])

            try:
                await pg.wait_for_function(
                    "() => !document.getElementById('apt-recheck-btn')"
                    ".disabled", timeout=900000)
            except Exception:                              # noqa: BLE001
                pass
            await pg.wait_for_timeout(400)
            await блок.scroll_into_view_if_needed()
            await блок.screenshot(path="%s/D-3-итог-%d.png" % (КУДА, ш))
            print("D: итог — %s"
                  % (await pg.inner_text("#apt-recheck-note")).strip()[:90])

            await ctx.close()
        await бр.close()
    print()
    print("кадры: %s" % КУДА)
    print("СТЕНД ИЗМЕНЁН прогоном D — пересейте: py make_local_user.py --seed")


if __name__ == "__main__":
    asyncio.run(главная())
