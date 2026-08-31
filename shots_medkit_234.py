# -*- coding: utf-8 -*-
"""СНИМКИ ЗАХОДА 234: происхождение вещества на карточке.

НЕ ПРОВЕРКА, кадры смотрит человек: кода «правильно» тут нет,
решает глаз владельца. Код возврата всегда 0.

ШИРИНЫ 2560 И 390 — их назвал владелец; 1440 среди них нет
намеренно, экрана такой ширины у него не существует (тот же довод,
что у `shots_medkit.py`).

═══════════════════════════════════════════════════════════════════════
ЧТО СНИМАЕТСЯ И ПОЧЕМУ ИМЕННО ЭТО
═══════════════════════════════════════════════════════════════════════

  1. РЯД КАРТОЧЕК, где видны РАЗНЫЕ источники подряд. Один кадр
     с одной подписью не отвечает на главный вопрос — различаются ли
     они на экране; пять одинаковых строк выглядели бы исправно.
  2. КАРТОЧКА КРУПНО с известным источником и рядом — с неизвестным.
     Подпись мелкая и служебная, и увидеть её надо в масштабе.

СОСТОЯНИЕ ЗАВОДИТСЯ ЗДЕСЬ ЖЕ, а не берётся у seed: снимки гоняются
после других проб, а те правят позиции (§8.0 — «седьмой экземпляр»).
Пишем в базу СТЕНДА и говорим это до прогона; после — пересеять.
"""
import asyncio
import os
import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from playwright.async_api import async_playwright     # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import medkit_defs as опр                             # noqa: E402

БАЗА = os.getenv("HOVER_BASE", "http://127.0.0.1:8899")
DB = os.getenv("DB_PATH", "./app.db")
ПОЧТА = "screenshot@local.dev"
ПАРОЛЬ = "Screenshot-Local-2026"
КУДА = os.getenv("SHOTS_DIR", "review_screenshots")
ШИРИНЫ = [(2560, 1440), (390, 844)]


def расставить_источники():
    """Пять кодов по пяти позициям, остальные — без записи.

    Возвращает число проставленных. Состояние «без записи» остаётся
    НАРОЧНО: кадр обязан показать, что известное и неизвестное
    различаются, а не что подпись есть у всех.
    """
    коды = list(опр.ИСТОЧНИК_ВЕЩЕСТВА)
    conn = sqlite3.connect(DB)
    try:
        ид = [r[0] for r in conn.execute(
            "SELECT id FROM medkit_items WHERE user_id="
            "(SELECT id FROM users WHERE email=?)"
            " AND TRIM(COALESCE(substance,''))<>'' ORDER BY id LIMIT ?",
            (ПОЧТА, len(коды)))]
        for i, п in enumerate(ид):
            conn.execute("UPDATE medkit_items SET substance_src=? WHERE id=?",
                         (коды[i], п))
        conn.commit()
        return len(ид)
    finally:
        conn.close()


async def войти(pg):
    """Селекторы — ПО ИМЕНИ ПОЛЯ, как у `check_medkit_ui._войти`.

    Первая версия искала `#email`, которого в форме нет вовсе, и падала
    по таймауту в 30 с. Второго способа входа тут заводить нечего: он
    один на все пробы, и расхождение видно только в день прогона.
    """
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


async def main():
    os.makedirs(КУДА, exist_ok=True)
    сколько = расставить_источники()
    print("[стенд] проставлено источников: %d — ПОСЛЕ ПРОГОНА ПЕРЕСЕЯТЬ"
          % сколько)
    async with async_playwright() as p:
        бр = await p.chromium.launch()
        for ш, в in ШИРИНЫ:
            к = await бр.new_context(viewport={"width": ш, "height": в},
                                     device_scale_factor=1)
            pg = await к.new_page()
            await войти(pg)
            await pg.goto(БАЗА + "/medkit", wait_until="networkidle")
            await pg.wait_for_timeout(700)

            подписи = await pg.evaluate(
                """() => [...document.querySelectorAll('.apt-mnn-src')]
                           .map(э => э.textContent.trim())""")
            свод = {}
            for с in подписи:
                свод[с] = свод.get(с, 0) + 1
            print("  %4d  подписей %d, различных %d: %s"
                  % (ш, len(подписи), len(свод), sorted(свод)))

            имя = os.path.join(КУДА, "234-ряд-источников-%d.png" % ш)
            await pg.screenshot(path=имя, animations="disabled")
            print("     " + имя)

            # КРУПНО: первая карточка с ИЗВЕСТНЫМ источником.
            цель = await pg.evaluate(
                """() => {
              const к = [...document.querySelectorAll('.apt-card')].find(c => {
                const s = c.querySelector('.apt-mnn-src');
                return s && s.textContent.trim() !== 'происхождение неизвестно';
              });
              if (!к) return null;
              к.scrollIntoView({block: 'center'});
              return +к.dataset.id;
            }""")
            await pg.wait_for_timeout(400)
            if цель:
                эл = pg.locator('.apt-card[data-id="%d"]' % цель)
                имя2 = os.path.join(КУДА, "234-карточка-крупно-%d.png" % ш)
                await эл.screenshot(path=имя2, animations="disabled")
                print("     " + имя2)
            else:
                # НЕ МОЛЧА: кадра нет — сказано, почему
                print("     карточки с известным источником НЕТ — "
                      "снимать нечего")
            await к.close()
        await бр.close()
    print()
    print("СТЕНД ИЗМЕНЁН: py make_local_user.py --seed")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
