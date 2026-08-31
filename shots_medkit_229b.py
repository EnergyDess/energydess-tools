"""СНИМКИ ЗАХОДА 229 (второй) — ДЛЯ ПРИЁМКИ ВЛАДЕЛЬЦЕМ.

НЕ ПРОВЕРКА: кода «правильно» у неё нет, кадры смотрит человек.
Код возврата всегда 0.

Что снимается — ровно то, что просит пункт 5 постановки:

  1. ШТОРКА СО СХЕМОЙ И ПОКАЗАНИЯМИ — блоки B.3 и E.1/E.3: строка
     «страница сверена с карточкой по …», единая метка «снято»,
     ряд действий ВНИЗУ, а не над содержимым;
  2. КАРТОЧКА БЕЗ СТРАНИЦЫ В СПРАВОЧНИКЕ, вещество ПУСТО — блок D.2:
     кнопка «Вписать вещество» вместо серого абзаца;
  3. ТА ЖЕ, вещество ЗАПОЛНЕНО — «Искать по веществу» стало КНОПКОЙ,
     а не серой ссылкой в третьем абзаце;
  4. КАРТОЧКА ТОЛЬКО СО СВОЕЙ ЗАПИСЬЮ — раздел «от чего это» стоит
     и там, где сказать нечего (решение B.2 задачи 229).

ПОЗИЦИИ ИЩУТСЯ ПО ФАКТУ, А НЕ ПО НОМЕРУ: состав стенда меняется
с каждым пересевом, и вписанный id снимал бы не то состояние,
которым подписан кадр.

ШИРИНЫ 2560 И 390 — их назвал владелец; 1440 среди них нет намеренно,
экрана такой ширины у него не существует.
"""
import asyncio
import os
import sqlite3
import sys
from pathlib import Path

from playwright.async_api import async_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

БАЗА = os.environ.get("MEDKIT_BASE", "http://127.0.0.1:8899")
ПОЧТА = "screenshot@local.dev"
ПАРОЛЬ = "Screenshot-Local-2026"
КУДА = Path("review_screenshots") / "medkit-229b"
ШИРИНЫ = [2560, 390]


async def _войти(pg):
    await pg.goto(БАЗА + "/login", wait_until="domcontentloaded")
    await pg.fill("input[name=email]", ПОЧТА)
    await pg.fill("input[name=password]", ПАРОЛЬ)
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


def _позиции():
    """ЧЕТЫРЕ СОСТОЯНИЯ ИЗ БАЗЫ, а не номерами.

    Спрашивается ровно то, что рисует шторка: есть ли выдержка, есть
    ли своя запись, заполнено ли вещество. Не нашлось состояния —
    так и говорим строкой: пропущенный кадр обязан быть виден
    (§6.0.1), иначе «снято 3 из 4» неотличимо от «снято всё».
    """
    c = sqlite3.connect("file:app.db?mode=ro", uri=True)
    c.row_factory = sqlite3.Row

    def один(условие):
        r = c.execute("SELECT id, name FROM medkit_items WHERE %s "
                      "ORDER BY id LIMIT 1" % условие).fetchone()
        return (r["id"], r["name"]) if r else None

    нашлось = {
        "схема-и-показания": один(
            "dosage_text IS NOT NULL AND indications_text IS NOT NULL"),
        "нет-страницы-вещество-пусто": один(
            "dosage_text IS NULL AND (substance IS NULL OR substance='')"),
        "нет-страницы-вещество-есть": один(
            "dosage_text IS NULL AND substance IS NOT NULL "
            "AND substance <> ''"),
        "только-своя-запись": один(
            "dosage_text IS NULL AND own_dosage_text IS NOT NULL "
            "AND own_dosage_text <> ''"),
    }
    c.close()
    return нашлось


async def _снять(pg, имя, ширина, селектор=None):
    КУДА.mkdir(parents=True, exist_ok=True)
    путь = КУДА / ("%s-%d.png" % (имя, ширина))
    цель = await pg.query_selector(селектор) if селектор else None
    if селектор and not цель:
        print("   ПРОПУЩЕН %s — %s не найден" % (имя, селектор))
        return
    if цель:
        await цель.screenshot(path=str(путь))
    else:
        await pg.screenshot(path=str(путь))
    print("   %s" % путь)


async def кадры(ширина, pw, позиции):
    br = await pw.chromium.launch()
    ctx = await br.new_context(viewport={"width": ширина, "height": 1100},
                               has_touch=(ширина <= 640))
    pg = await ctx.new_page()
    await _войти(pg)
    await pg.goto(БАЗА + "/medkit", wait_until="networkidle")
    print("### %d px" % ширина)
    for метка, поз in позиции.items():
        if not поз:
            print("   ПРОПУЩЕНО состояние %r — на стенде его нет" % метка)
            continue
        await pg.evaluate("(id) => аптДозыОткрыть(id)", str(поз[0]))
        await pg.wait_for_timeout(600)
        await _снять(pg, метка, ширина, "#apt-doses .modal-sh")
        await pg.keyboard.press("Escape")
        await pg.wait_for_timeout(200)
    await ctx.close()
    await br.close()


async def main_():
    поз = _позиции()
    print("СОСТОЯНИЯ, НАЙДЕННЫЕ НА СТЕНДЕ:")
    for метка, п in поз.items():
        print("   %-30s %s" % (метка, ("id=%d" % п[0]) if п else "НЕТ"))
    print()
    async with async_playwright() as pw:
        for ш in ШИРИНЫ:
            await кадры(ш, pw, поз)
    print()
    print("Кадры смотрит человек: кода «правильно» у снимков нет.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main_()))
