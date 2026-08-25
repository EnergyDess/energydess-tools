# -*- coding: utf-8 -*-
"""СНИМКИ АПТЕЧКИ ДЛЯ ПРИЁМКИ ВЛАДЕЛЬЦЕМ (BACKLOG №172).

НЕ ПРОВЕРКА: кода «правильно» у неё нет, кадры смотрит человек. Код
возврата всегда 0 — то же устройство, что у `check_goal_screens.py`
и `check_scale_screens.py`.

ШИРИНЫ 2560 И 390 — их назвал владелец. 1440 среди них нет намеренно:
экрана такой ширины у него не существует, и прошлый заход мерил ширину,
которой никто не видит (тот же довод, что у задачи 143).

СЦЕНЫ ровно те, что перечислены в постановке: карточка с фото и без,
открытая панель, форма для таблеток и для сиропа, ряд чипов, блок
способа приёма.

С BACKLOG №173 окно способа приёма снимается в ТРЁХ состояниях, а не
в одном: свёрнутом, раскрытом и «схема не найдена». Плюс окно удаления.
На одном кадре они не различаются, а меняли заход все три.

ДО 2026-08-25 СЦЕНА СПОСОБА ПРИЁМА НЕ СНИМАЛАСЬ НИ РАЗУ и честно
печатала «не снят: ни у одной позиции нет выдержки»: seed её
не наполнял (§8.0). Теперь наполняет — `medkit_dosage_seed.json`.
"""

import asyncio
import io
import os
import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

БАЗА = os.environ.get("MEDKIT_BASE", "http://127.0.0.1:8899")
ПОЧТА = "screenshot@local.dev"
ПАРОЛЬ = "Screenshot-Local-2026"
DB = os.environ.get("DB_PATH", "app.db")
КУДА = os.environ.get("SHOTS_DIR", "C:/Temp/claude/shots")
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


async def _кадр(pg, имя, ширина, полный=False):
    путь = os.path.join(КУДА, "%s_%d.png" % (имя, ширина))
    # Указатель уводится в угол: после `click` он остаётся на кнопке,
    # и наведение попадает в кадр случайным образом (§6.0.3)
    await pg.mouse.move(0, 0)
    await pg.wait_for_timeout(200)
    await pg.screenshot(path=путь, full_page=полный, animations="disabled")
    print("   %s" % путь)


async def _фото_первой(pg):
    """Кладёт фото первой позиции — чтобы снять карточку С фото и БЕЗ."""
    from PIL import Image
    буфер = io.BytesIO()
    Image.new("RGB", (900, 560), (208, 214, 226)).save(буфер, "JPEG")
    conn = sqlite3.connect(DB)
    ид = conn.execute("SELECT id FROM medkit_items ORDER BY id LIMIT 1").fetchone()
    conn.close()
    if not ид:
        return None
    await pg.evaluate("""async ([id, данные]) => {
      const б = await (await fetch(данные)).blob();
      const ф = new FormData();
      ф.append('file', б, 'pack.jpg');
      const о = await fetch('/medkit/api/items/' + id + '/photo',
                            {method: 'POST', body: ф});
      return о.ok;
    }""", [ид[0], "data:image/jpeg;base64," +
           __import__("base64").b64encode(буфер.getvalue()).decode()])
    return ид[0]


async def снять(ширина):
    from playwright.async_api import async_playwright
    сенсор = ширина <= 640
    async with async_playwright() as p:
        br = await p.chromium.launch()
        ctx = await br.new_context(viewport={"width": ширина, "height": 1000},
                                   has_touch=сенсор, is_mobile=сенсор)
        pg = await ctx.new_page()
        await _войти(pg)
        await pg.goto(БАЗА + "/medkit", wait_until="networkidle")
        await pg.wait_for_timeout(700)

        # 1. Экран целиком: ряд чипов, шапка с кнопками, сетка карточек
        await _кадр(pg, "01_экран", ширина)

        # 2. Карточка С ФОТО и БЕЗ — в одном кадре
        ид = await _фото_первой(pg)
        if ид:
            await pg.reload(wait_until="networkidle")
            await pg.wait_for_timeout(800)
            await pg.evaluate(
                "() => document.querySelector('.apt-card')"
                ".scrollIntoView({block: 'start'})")
            await pg.wait_for_timeout(400)
            await _кадр(pg, "02_карточки_фото_и_без", ширина)

        # 3. Форма для ТАБЛЕТОК — полей вскрытия нет
        await pg.evaluate("() => аптОткрытьФорму()")
        await pg.wait_for_timeout(500)
        await pg.select_option("#apt-f-form", "tablet")
        await pg.wait_for_timeout(400)
        await _кадр(pg, "03_форма_таблетки", ширина)

        # 4. Форма для СИРОПА — поля вскрытия на месте
        await pg.select_option("#apt-f-form", "syrup")
        await pg.wait_for_timeout(400)
        await _кадр(pg, "04_форма_сироп", ширина)
        await pg.keyboard.press("Escape")
        await pg.wait_for_timeout(400)

        # 5. Панель ассистента: подсказки под значком, ряд ввода в строку
        await pg.evaluate("() => аптАИОткрыть()")
        await pg.wait_for_timeout(600)
        await _кадр(pg, "05_панель", ширина)

        # 6. Та же панель с РАСКРЫТОЙ подсказкой «?»
        await pg.evaluate(
            "() => document.querySelector('.apt-ai-hint-btn .hint-btn').click()")
        await pg.wait_for_timeout(500)
        await _кадр(pg, "06_панель_подсказка", ширина)
        await pg.keyboard.press("Escape")
        await pg.wait_for_timeout(400)

        # 7. Способ приёма — СВЁРНУТОЕ окно: видна первая секция
        #    инструкции, остальное под «Показать полностью» (BACKLOG №173)
        #
        # Берётся САМАЯ ДЛИННАЯ выдержка, а не первая попавшаяся: у неё
        # два уровня заголовков, таблица и сгиб, то есть на кадре видно
        # всё, что заход менял. `LIMIT 1` без порядка снимал бы то, что
        # СУБД вернёт первым, — и это могла быть выдержка без сгиба
        conn = sqlite3.connect(DB)
        с_дозами = conn.execute(
            "SELECT id FROM medkit_items WHERE dosage_text IS NOT NULL"
            " ORDER BY length(dosage_text) DESC LIMIT 1").fetchone()
        без_доз = conn.execute(
            "SELECT id FROM medkit_items WHERE dosage_text IS NULL"
            " LIMIT 1").fetchone()
        conn.close()
        if с_дозами:
            await pg.evaluate("(id) => аптДозыОткрыть(id)", с_дозами[0])
            await pg.wait_for_timeout(600)
            await _кадр(pg, "07_способ_приёма_свёрнут", ширина)

            # 8. То же окно РАЗВЁРНУТОЕ — «Показать полностью» нажата.
            # Кадр полный: под сгибом 97.7% текста, и в окно 1000 px
            # он не влезает ни на одной ширине
            нажали = await pg.evaluate(
                "() => { const к = document.querySelector('.apt-dose-more');"
                "  if (!к) return false; к.click(); return true; }")
            if нажали:
                await pg.wait_for_timeout(500)
                await _кадр(pg, "08_способ_приёма_раскрыт", ширина, полный=True)
            else:
                print("   (раскрытие не снято: кнопки сгиба нет — "
                      "у этой выдержки заголовков меньше двух)")
            await pg.keyboard.press("Escape")
            await pg.wait_for_timeout(400)
        else:
            print("   (способ приёма не снят: ни у одной позиции нет "
                  "выдержки — пересейте стенд)")

        # 9. Окно «схема ещё не найдена»: сообщение, кнопка поиска
        #    и запасной путь по веществу. Ритм блока C виден здесь
        if без_доз:
            await pg.evaluate("(id) => аптДозыОткрыть(id)", без_доз[0])
            await pg.wait_for_timeout(600)
            await _кадр(pg, "09_схема_не_найдена", ширина)
            await pg.keyboard.press("Escape")
            await pg.wait_for_timeout(400)

        # 10. Окно удаления: текст говорит о действии, а не об устройстве
        #     экрана (BACKLOG №173, блок B)
        await pg.evaluate("() => { const к = document.querySelector"
                          "('.apt-card [data-del]'); к && к.click(); }")
        await pg.wait_for_timeout(500)
        await _кадр(pg, "10_окно_удаления", ширина)
        await pg.keyboard.press("Escape")
        await pg.wait_for_timeout(300)
        await br.close()


async def main():
    os.makedirs(КУДА, exist_ok=True)
    for ш in ШИРИНЫ:
        print("── %d px ──" % ш)
        await снять(ш)
    print()
    print("Снимки: %s" % КУДА)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
