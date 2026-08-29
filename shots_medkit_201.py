# -*- coding: utf-8 -*-
"""СНИМКИ ЗАХОДА 201 — кадры смотрит человек, не проверка.

ЧТО СНИМАЕТСЯ И ПОЧЕМУ ИМЕННО ЭТО:

  A. КНОПКА «Перепроверить всю аптечку» с обещанием под ней. Главный
     кадр блока A: гарантия «ваши записи не трогаю» существовала
     в коде и не существовала на экране, и владелец кнопкой
     не пользовался.
  C. ОКНО СПОСОБА ПРИЁМА, где своя запись и выдержка стоят РЯДОМ
     в одном виде. Один кадр показал бы половину: вся суть C.1
     в том, что коробки теперь одинаковые, а различает их МЕТКА.
  D. РЯД КАРТОЧЕК целиком — полоски остатка и ряды кнопок на одном
     уровне. Снимается СЕТКА, а не отдельная карточка: выравнивание
     существует только между соседями.
  E. СТРОКА СЧЁТЧИКА в админке.

ПОЗИЦИЯ ДЛЯ ОКНА ИЩЕТСЯ ПО ФАКТУ, а не по номеру: первая карточка
сегодня одна, завтра другая. Нужна та, у которой ЕСТЬ И выдержка,
И своя запись, — иначе кадр покажет не то состояние, ради которого
заведён (тот же приём, что у `shots_medkit_200.py`).

    py make_local_user.py --seed
    py -m uvicorn main:app --port 8899
    py shots_medkit_201.py
"""
import asyncio
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

БАЗА = os.environ.get("MEDKIT_BASE", "http://127.0.0.1:8899")
ПОЧТА, ПАРОЛЬ = "screenshot@local.dev", "Screenshot-Local-2026"
КУДА = os.environ.get("SHOTS_DIR", "C:/Temp/claude/shots201")
# ШИРИНЫ НАЗВАЛ ВЛАДЕЛЕЦ: у него два монитора, 2560 и 1920, плюс
# телефон. 1440 среди них нет — экрана такой ширины не существует
ШИРИНЫ = [2560, 390]


async def _войти(pg):
    await pg.goto(БАЗА + "/login", wait_until="domcontentloaded")
    await pg.fill("input[name=email]", ПОЧТА)
    await pg.fill("input[name=password]", ПАРОЛЬ)
    await pg.click("button[type=submit]")
    await pg.wait_for_load_state("networkidle")
    if "/login" in pg.url:
        raise SystemExit("ВХОД НЕ СОСТОЯЛСЯ — снимать нечего")


async def _снять(pg, имя, ш, что=None):
    путь = "%s/%s-%d.png" % (КУДА, имя, ш)
    if что is None:
        await pg.screenshot(path=путь, full_page=False)
    else:
        э = pg.locator(что).first
        await э.screenshot(path=путь)
    print("   %s" % путь)


async def прогон(pw, ш):
    br = await pw.chromium.launch()
    ctx = await br.new_context(viewport={"width": ш, "height": 1000},
                               has_touch=(ш == 390), is_mobile=(ш == 390))
    pg = await ctx.new_page()
    await _войти(pg)
    print("── ширина %d ──" % ш)

    # ── A · КНОПКА ПЕРЕПРОВЕРКИ С ОБЕЩАНИЕМ ─────────────────────────
    await pg.goto(БАЗА + "/medkit", wait_until="networkidle")
    await pg.locator("#apt-recheck").scroll_into_view_if_needed()
    await pg.wait_for_timeout(300)
    await _снять(pg, "A-кнопка-перепроверки", ш, "#apt-recheck")

    # ── D · РЯД КАРТОЧЕК ────────────────────────────────────────────
    # СЕТКА ЦЕЛИКОМ, а не одна карточка: выравнивание существует
    # только между соседями, и на одиночном кадре его не видно
    await pg.evaluate("window.scrollTo(0, 0)")
    await pg.wait_for_timeout(200)
    await _снять(pg, "D-ряд-карточек", ш, "#apt-grid")

    # ── C · ОКНО СПОСОБА ПРИЁМА: ОБА БЛОКА В ОДНОМ ВИДЕ ─────────────
    # Позиция ищется ПО ФАКТУ — та, у которой есть и выдержка,
    # и своя запись
    # ЧЕРЕЗ НАСТОЯЩЕЕ НАЖАТИЕ, А НЕ ЧЕРЕЗ ГЛОБАЛ. `АПТ_ПОЗИЦИИ`
    # объявлен через `let`, а `let` свойства `window` НЕ СОЗДАЁТ
    # вовсе — на этом уже спотыкался контроль задачи 181. Карточка
    # с обеими записями ищется по кнопке «Приём», а состояние
    # спрашивается у сервера.
    ид = await pg.evaluate("""async () => {
      const о = await fetch('/medkit/api/grid');
      const т = await о.json();
      const п = (т['позиции'] || []).find(x => x['дозы'] && x['своя_схема']);
      return п ? String(п.id) : null;
    }""")
    if ид is None:
        print("   ПОЗИЦИИ С ОБЕИМИ ЗАПИСЯМИ НЕТ — кадр C не снят")
    else:
        await pg.click("[data-doses='%s']" % ид)
        await pg.wait_for_selector("#apt-doses-body .apt-own", timeout=15000)
        await pg.wait_for_timeout(400)
        await _снять(pg, "C-схема-и-своя-запись", ш)

    await ctx.close()
    await br.close()


async def админка(pw):
    """E · строка счётчика. Одна ширина: это строка текста."""
    br = await pw.chromium.launch()
    ctx = await br.new_context(viewport={"width": 2560, "height": 1000})
    pg = await ctx.new_page()
    await _войти(pg)
    await pg.goto(БАЗА + "/admin/users", wait_until="networkidle")
    await pg.locator("#ref-note").scroll_into_view_if_needed()
    await pg.wait_for_timeout(200)
    await _снять(pg, "E-счётчик-справочника", 2560, "#ref-note")
    await ctx.close()
    await br.close()


async def main():
    os.makedirs(КУДА, exist_ok=True)
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        for ш in ШИРИНЫ:
            await прогон(pw, ш)
        await админка(pw)
    print("\nкадры в %s" % КУДА)


if __name__ == "__main__":
    asyncio.run(main())
