# -*- coding: utf-8 -*-
"""СНИМКИ ЗАХОДА 239: предложение из справочника и новая подложка.

Кадры смотрит ЧЕЛОВЕК — это не проверка, кода «правильно» тут нет.

ЧТО СНИМАЕТСЯ

  · ПРЕДЛОЖЕНИЕ ИЗ СПРАВОЧНИКА с ДВУМЯ ЗНАЧЕНИЯМИ РЯДОМ (блок B):
    что записано в карточке и что подставится, плюс слово источника
    дословно. Главный кадр захода: до него показывалось только новое
    значение, а прежнее человек узнавал уже затерев его;
  · КАРТОЧКА С МЕТКОЙ «из справочника» после подстановки (B.3);
  · ОКНО ПОВЕРХ НОВОЙ ПОДЛОЖКИ (блок D) — 0.85 вместо 0.75.

СОСТОЯНИЕ ЗАВОДИТСЯ ЗДЕСЬ ЖЕ, а не берётся у seed: подсказка
приезжает только из поиска по справочнику, то есть из сети, и кадр,
зависящий от чужого сайта, снимался бы то с предложением, то без.
Пишем прямо в базу и говорим это.

ШИРИНЫ 2560 И 390 — их назвал владелец; 1440 среди них нет
намеренно, экрана такой ширины у него не существует (§3).

    py -m uvicorn main:app --port 8899
    py shots_medkit_239.py
"""
import asyncio
import os
import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

БАЗА = os.getenv("HOVER_BASE", "http://127.0.0.1:8899")
DB = os.getenv("DB_PATH", "app.db")
ПОЧТА = "screenshot@local.dev"
ПАРОЛЬ = "Screenshot-Local-2026"
КУДА = os.path.join("review_screenshots", "medkit_239")
ШИРИНЫ = (2560, 390)


def _завести_подсказку():
    """Позиция с подсказкой формы И вещества — обе строки предложения.

    Возвращает id либо None. Пишем в базу, потому что боевого пути
    «поставить подсказку готовой позиции» не существует: она приходит
    только из ответа справочника.
    """
    conn = sqlite3.connect(DB)
    try:
        ряд = conn.execute(
            "SELECT id FROM medkit_items WHERE user_id="
            "(SELECT id FROM users WHERE email=?) AND form<>'solution'"
            " ORDER BY id LIMIT 1", (ПОЧТА,)).fetchone()
        if not ряд:
            return None
        conn.execute(
            "UPDATE medkit_items SET dosage_hint_form='solution',"
            " dosage_hint_form_word='раствор для приема внутрь',"
            " dosage_hint_substance='амброксол', form_src=NULL"
            " WHERE id=?", (ряд[0],))
        conn.commit()
        return ряд[0]
    finally:
        conn.close()


async def _войти(pg):
    await pg.goto(БАЗА + "/login", wait_until="domcontentloaded")
    await pg.fill("input[name=email]", ПОЧТА)
    await pg.fill("input[name=password]", ПАРОЛЬ)
    await pg.click("button[type=submit]")
    await pg.wait_for_load_state("networkidle")
    if "/login" in pg.url:
        raise SystemExit("ВХОД НЕ СОСТОЯЛСЯ — снимать нечего")


async def главная():
    from playwright.async_api import async_playwright

    os.makedirs(КУДА, exist_ok=True)

    async with async_playwright() as pw:
        бр = await pw.chromium.launch()
        сделано = []
        for ш in ШИРИНЫ:
            # СОСТОЯНИЕ ЗАВОДИТСЯ ПЕРЕД КАЖДОЙ ШИРИНОЙ, а не один раз
            # на прогон: подстановка на первой ширине РАСХОДУЕТ его —
            # форма становится solution, подсказка обнуляется. Первая
            # версия снимала на 390 кадр с НУЛЁМ предложений и выдавала
            # его за снимок предложения
            ид = _завести_подсказку()
            if not ид:
                print("%d: НЕЧЕГО СНИМАТЬ — позиции с формой, отличной"
                      " от solution, на стенде нет" % ш)
                continue
            print("позиция под предложение: id=%s (ширина %d)" % (ид, ш))
            ctx = await бр.new_context(
                viewport={"width": ш, "height": 900 if ш > 700 else 780},
                has_touch=(ш <= 700), is_mobile=(ш <= 700))
            pg = await ctx.new_page()
            await _войти(pg)
            await pg.goto(БАЗА + "/medkit", wait_until="networkidle")
            await pg.wait_for_timeout(600)

            # ── 1. ПРЕДЛОЖЕНИЕ ИЗ СПРАВОЧНИКА, ОБА ЗНАЧЕНИЯ РЯДОМ ────
            await pg.evaluate("(id) => аптДозыОткрыть(id)", ид)
            await pg.wait_for_timeout(800)
            путь = os.path.join(КУДА, "предложение-%d.png" % ш)
            await pg.screenshot(path=путь)
            сделано.append(путь)

            # Что видно на кадре — печатаем, чтобы снимок не пришлось
            # разглядывать ради одной строки
            вид = await pg.evaluate(
                """() => [...document.querySelectorAll('.apt-ref-offer')]
                     .map(б => ({
                       поле: (б.querySelector('.apt-ref-field')||{}).textContent,
                       было: (б.querySelector('.apt-ref-was')||{}).textContent,
                       будет: (б.querySelector('.apt-ref-new')||{}).textContent,
                       слово: (б.querySelector('.apt-ref-src')||{}).textContent,
                     }))""")
            print("  %d: предложений на кадре %d" % (ш, len(вид)))
            for в in вид:
                print("      %s: %s -> %s | %s"
                      % (в.get("поле"), в.get("было"), в.get("будет"),
                         в.get("слово") or "—"))

            # ── 2. ОКНО ПОВЕРХ ПОДЛОЖКИ (блок D) ─────────────────────
            #
            # Тот же кадр отвечает и на вопрос подложки: окно открыто,
            # страница под ним. Снимаем ОТДЕЛЬНО и во весь экран,
            # чтобы видеть нижние 8 %, которые окно не закрывает
            путь = os.path.join(КУДА, "подложка-%d.png" % ш)
            await pg.screenshot(path=путь, full_page=False)
            сделано.append(путь)

            # ── 3. КАРТОЧКА С МЕТКОЙ ПОСЛЕ ПОДСТАНОВКИ ───────────────
            await pg.evaluate(
                """() => {
              const б = [...document.querySelectorAll('.apt-ref-offer')]
                .find(x => (x.querySelector('.apt-ref-field')||{})
                  .textContent === 'Форма выпуска');
              const к = б && б.querySelector('button');
              if (к) к.click();
            }""")
            await pg.wait_for_timeout(1500)
            await pg.evaluate("() => закрыть_модалку('apt-doses')")
            await pg.wait_for_timeout(500)
            # Карточку прокручиваем к себе — иначе кадр про неё пустой
            await pg.evaluate(
                "(id) => { const к = document.querySelector("
                "  '.apt-card[data-id=\"' + id + '\"]');"
                "  if (к) к.scrollIntoView({block: 'center'}); }", ид)
            await pg.wait_for_timeout(400)
            путь = os.path.join(КУДА, "после-подстановки-%d.png" % ш)
            await pg.screenshot(path=путь)
            сделано.append(путь)

            форма = await pg.evaluate(
                "(id) => { const к = document.querySelector("
                "  '.apt-card[data-id=\"' + id + '\"]');"
                "  return к ? к.textContent.replace(/\\s+/g,' ')"
                "    .slice(0, 90) : null; }", ид)
            print("  %d: карточка после подстановки — %s" % (ш, форма))
            await ctx.close()
        await бр.close()

    print()
    print("КАДРЫ (%d):" % len(сделано))
    for п in сделано:
        print("  " + п)
    print()
    print("Снимки лежат в review_screenshots/ — каталог закрыт .gitignore")
    print("(§8.0: содержимое аптечки в отслеживаемые каталоги не кладётся)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(главная()))
