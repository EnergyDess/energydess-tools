# -*- coding: utf-8 -*-
"""ПОДСВЕТКА СТРОКИ В ТАБЛИЦАХ АДМИНКИ — ВИДНА ЛИ ОНА ЧЕЛОВЕКУ (задача 279).

МЕРКА, код возврата 0 (кроме `--контроль`). Спрашивает ПИКСЕЛЬ, а не
вычисленный стиль: `check_hover` назвал подсветку каталога Enshrouded
МЁРТВОЙ по стилям, а вопрос человека — «меняется ли цвет строки под
курсором». Стиль может смениться и остаться невидимым (тот же цвет, что
под ячейкой), и наоборот.

ТАБЛИЦЫ ВЫВОДЯТСЯ, А НЕ ПЕРЕЧИСЛЯЮТСЯ (§6.0.7): каждый `<table>` с классом
`admin-table` в `templates/admin_*.html`, адрес — `/admin/<имя шаблона>`.
Пятая таблица попадёт в замер сама.

ЧТО МЕРИТСЯ У КАЖДОЙ ТАБЛИЦЫ. Первая видимая строка данных; в ней —
ячейки без органов управления (кнопка, картинка, ссылка, поле). Цвет
берётся со СНИМКА в полосе внутреннего отступа ячейки, где нет текста,
в покое (указатель в углу окна) и под указателем. Меряются ДВЕ ячейки
строки: подсветка «строки», загоревшаяся в одной ячейке, строкой
не является.

ГОЛОВНОЙ БРАУЗЕР (§6.0.3), ширина 1440: подсветка объявлена под
`@media (hover: hover)`.

    py make_local_user.py --seed
    py -m uvicorn main:app --port 8899
    py check_admin_rows.py
    py check_admin_rows.py --контроль
"""
import asyncio
import glob
import io
import os
import re
import sys
import probe_guard  # noqa: F401  ПРОПУСК вместо трассы (§6.0.1)

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

БАЗА = os.getenv("HOVER_BASE", "http://127.0.0.1:8899")
ПОЧТА = os.getenv("STAND_EMAIL", "screenshot@local.dev")
ПАРОЛЬ = os.getenv("STAND_PASSWORD", "Screenshot-Local-2026")
КОРЕНЬ = os.path.dirname(os.path.abspath(__file__))
# Порог в сумме каналов: подсветка `--surface-1` → `--surface-2` даёт
# разницу порядка двадцати, шум сжатия снимка — единицы
ПОРОГ = 6


def таблицы():
    """(адрес, селектор таблицы) — из шаблонов, а не перечнем."""
    итог = []
    for путь in sorted(glob.glob(os.path.join(КОРЕНЬ, "templates", "admin_*.html"))):
        текст = io.open(путь, encoding="utf-8").read()
        имя = os.path.basename(путь)[len("admin_"):-len(".html")]
        for м in re.finditer(r'<table\s+class="([^"]*\badmin-table\b[^"]*)"', текст):
            классы = [к for к in м.group(1).split() if к != "admin-table"]
            селектор = "table.admin-table" + "".join("." + к for к in классы)
            итог.append(("/admin/" + имя, селектор))
    return итог


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
        raise SystemExit("ВХОД НЕ СОСТОЯЛСЯ — мерить нечего")


# ТОЧКА ЗАМЕРА — ТАМ, ГДЕ ПОД ПИКСЕЛЕМ ЛЕЖИТ САМА ЯЧЕЙКА, а не её потомок:
# `elementFromPoint` возвращает `<td>`. Первая версия отбирала «ячейки без
# органов управления» и у таблицы продуктов не нашла ни одной — там
# в каждой ячейке поле ввода, — то есть молчала про целую таблицу.
# Поиск идёт от левого верхнего угла: там внутренний отступ, текста нет.
ВЫБОР = """(сел) => {
  const т = document.querySelector(сел);
  if (!т) return {беда: 'таблицы нет'};
  const строки = [...т.querySelectorAll('tbody tr')].filter(р =>
    р.checkVisibility({checkOpacity: true, checkVisibilityCSS: true})
    && р.querySelector('td'));
  if (!строки.length) return {беда: 'видимых строк нет'};
  const р = строки[0];
  р.scrollIntoView({block: 'center'});
  const ячейки = [...р.querySelectorAll('td')];
  const точки = [];
  ячейки.forEach((я, i) => {
    const п = я.getBoundingClientRect();
    if (п.width < 12 || п.height < 12) return;
    for (let y = п.top + 3; y < п.bottom - 3; y += 3) {
      for (let x = п.left + 3; x < п.right - 3; x += 6) {
        if (document.elementFromPoint(x, y) === я) {
          точки.push({i, x: Math.round(x), y: Math.round(y),
                      cx: Math.round(п.left + п.width / 2),
                      cy: Math.round(п.top + п.height / 2)});
          return;
        }
      }
    }
  });
  if (точки.length < 2) return {беда: 'ячеек с открытым фоном меньше двух'};
  return {точки: [точки[0], точки[точки.length - 1]], ячеек: точки.length,
          всего_ячеек: ячейки.length};
}"""

СТИЛИ = """(арг) => {
  const т = document.querySelector(арг.сел);
  const р = [...т.querySelectorAll('tbody tr')].find(р =>
    р.checkVisibility({checkOpacity: true, checkVisibilityCSS: true})
    && р.querySelector('td'));
  const я = р.querySelectorAll('td')[арг.i];
  return {td: getComputedStyle(я).backgroundColor,
          tr: getComputedStyle(р).backgroundColor,
          наведено: р.matches(':hover')};
}"""


async def _пиксели(pg, точки):
    from PIL import Image
    снимок = await pg.screenshot()
    картинка = Image.open(io.BytesIO(снимок)).convert("RGB")
    dpr = картинка.width / (await pg.evaluate("() => innerWidth"))
    итог = []
    for т in точки:
        x, y = int(т["x"] * dpr), int(т["y"] * dpr)
        соседи = [картинка.getpixel((x + dx, y + dy))
                  for dx in (-1, 0, 1) for dy in (-1, 0, 1)]
        итог.append(tuple(round(sum(c[i] for c in соседи) / 9)
                          for i in range(3)))
    return итог


async def замер(pg, адрес, селектор):
    await pg.goto(БАЗА + адрес, wait_until="networkidle")
    await pg.mouse.move(1, 1)
    await pg.wait_for_timeout(300)
    выбор = await pg.evaluate(ВЫБОР, селектор)
    if выбор.get("беда"):
        return {"беда": выбор["беда"]}
    await pg.mouse.move(1, 1)
    await pg.wait_for_timeout(300)
    арг = {"сел": селектор, "i": выбор["точки"][0]["i"]}
    покой = await _пиксели(pg, выбор["точки"])
    стиль_покой = await pg.evaluate(СТИЛИ, арг)
    ц = выбор["точки"][0]
    await pg.mouse.move(ц["x"], ц["y"])
    await pg.wait_for_timeout(400)
    наведение = await _пиксели(pg, выбор["точки"])
    стиль_наведение = await pg.evaluate(СТИЛИ, арг)
    await pg.mouse.move(1, 1)
    разница = [sum(abs(a - b) for a, b in zip(п, н))
               for п, н in zip(покой, наведение)]
    return {"покой": покой, "наведение": наведение, "разница": разница,
            "стиль_покой": стиль_покой, "стиль_наведение": стиль_наведение,
            "подсвечена": all(р > ПОРОГ for р in разница)}


def _печать(адрес, селектор, р):
    if р.get("беда"):
        print("%-20s %-32s НЕ ИЗМЕРЕНО: %s" % (адрес, селектор, р["беда"]))
        return
    print("%-20s %-32s %s" % (адрес, селектор,
                              "ПОДСВЕЧИВАЕТСЯ" if р["подсвечена"]
                              else "НЕ ПОДСВЕЧИВАЕТСЯ"))
    print("    пиксель в покое %s, под указателем %s, разница %s"
          % (р["покой"], р["наведение"], р["разница"]))
    print("    стиль td: %s → %s; tr: %s → %s; :hover у строки %s"
          % (р["стиль_покой"]["td"], р["стиль_наведение"]["td"],
             р["стиль_покой"]["tr"], р["стиль_наведение"]["tr"],
             р["стиль_наведение"]["наведено"]))


async def прогон(подлог_css=None):
    from playwright.async_api import async_playwright
    итог = {}
    async with async_playwright() as pw:
        бр = await pw.chromium.launch(headless=False)
        ctx = await бр.new_context(viewport={"width": 1440, "height": 900})
        pg = await ctx.new_page()
        await _войти(pg)
        if подлог_css:
            await ctx.add_init_script(
                "document.addEventListener('DOMContentLoaded', () => {"
                " const s = document.createElement('style');"
                " s.textContent = %r; document.head.appendChild(s); });"
                % подлог_css)
        for адрес, селектор in таблицы():
            р = await замер(pg, адрес, селектор)
            итог[(адрес, селектор)] = р
            _печать(адрес, селектор, р)
        await ctx.close()
        await бр.close()
    return итог


def _сводка(итог, заголовок):
    измерено = [р for р in итог.values() if not р.get("беда")]
    да = sum(1 for р in измерено if р["подсвечена"])
    print("%s: таблиц %d, измерено %d, подсвечивается %d"
          % (заголовок, len(итог), len(измерено), да))
    return да, len(измерено)


# ПОДЛОГ ЛОМАЕТ ПРОВЕРЯЕМОЕ ЗВЕНО — ПРАВИЛО ПОДСВЕТКИ СТРОКИ. Стиль
# кладётся в страницу и перекрывает ячейке фон под указателем её же фоном
# в покое, то есть возвращает строку в «не подсвечивается» при целом
# правиле в файле. ДОКАЗАТЕЛЬСТВО — вычисленный фон ячейки под указателем
# равен фону в покое у каждой таблицы.
ПОДЛОГ = ("@media (hover: hover) { .admin-table tr:hover td {"
          " background: transparent !important; } }")
ДОКАЗАТЕЛЬСТВА = {"подсветка снята": "фон td под указателем равен фону в покое"}


def main_():
    if "--контроль" in sys.argv:
        print("── ЧИСТЫЙ ПРОГОН")
        чистый = asyncio.run(прогон())
        да_ч, n_ч = _сводка(чистый, "ЧИСТО")
        print("── ПОДЛОГ: %s" % ПОДЛОГ)
        грязный = asyncio.run(прогон(ПОДЛОГ))
        да_п, n_п = _сводка(грязный, "С ПОДЛОГОМ")
        доказан = all(р["стиль_наведение"]["td"] == р["стиль_покой"]["td"]
                      for р in грязный.values() if not р.get("беда"))
        print("ДОКАЗАТЕЛЬСТВО подлога (фон td под указателем = в покое у всех): %s"
              % доказан)
        верно = n_ч and да_ч == n_ч and да_п == 0 and доказан
        print("КОНТРОЛЬ: %s" % ("ПОДЛОГ ПОЙМАН ЧИСЛОМ (%d → %d)" % (да_ч, да_п)
                              if верно else "НЕ ДОКАЗАНО — разобрать числа выше"))
        return 0 if верно else 1
    итог = asyncio.run(прогон())
    _сводка(итог, "ИТОГ")
    return 0


if __name__ == "__main__":
    sys.exit(main_())
