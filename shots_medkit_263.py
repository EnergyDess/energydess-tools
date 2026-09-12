# -*- coding: utf-8 -*-
"""СНИМКИ ЗАХОДА 263 — кадры смотрит человек, НЕ проверка.

Что снимается и почему именно это:

  окно упаковок, три ширины   блок B: лист 540 -> 860 на десктопе,
                              текстовой колонке 149 -> 469 px. На 390
                              лист как был — снимок это и показывает
  лента круга с прокруткой    блок C: полоса у ПРАВОГО КРАЯ окна.
                              Лента НАБИВАЕТСЯ: на стенде она в десять
                              строк, прокрутки нет вовсе, и кадр
                              показывал бы случай, которого нет (§8.0)
  шапка «Общей аптечки»       блок D: промежуток между знаком справки
                              и крестиком, 0 -> 8 px
  окно категорий              блок A: перечитывается при открытии;
                              на кадре видно, что список полон

ЛЕНТА ВОЗВРАЩАЕТСЯ к сидированному состоянию в `finally`: проба,
оставившая за собой шестьдесят строк, ломает не свой прогон,
а следующий (§6.0.3, шестая причина неповторимости).
"""
import io
import os
import sys
import probe_guard  # noqa: F401  ПРОПУСК вместо трассы (§6.0.1)

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

БАЗА = os.environ.get("HOVER_BASE", "http://127.0.0.1:8899")
ПОЧТА = os.environ.get("STAND_EMAIL", "screenshot@local.dev")
ПАРОЛЬ = os.environ.get("STAND_PASSWORD", "Screenshot-Local-2026")
КУДА = "review_screenshots"
ШИРИНЫ = (2560, 1920, 390)


def _лента(сколько):
    import sqlite3
    from database import DB_PATH
    c = sqlite3.connect(DB_PATH)
    try:
        круг = c.execute("SELECT id FROM medkit_circles").fetchone()
        кто = c.execute("SELECT user_id FROM medkit_members LIMIT 1").fetchone()
        if not круг or not кто:
            return 0
        for i in range(сколько):
            c.execute("INSERT INTO medkit_events "
                      "(circle_id, user_id, kind, name, created_at) "
                      "VALUES (?, ?, 'take', ?, datetime('now'))",
                      (круг[0], кто[0], "проба ленты %d" % i))
        c.commit()
        return сколько
    finally:
        c.close()


def _лента_убрать():
    import sqlite3
    from database import DB_PATH
    c = sqlite3.connect(DB_PATH)
    try:
        n = c.execute("DELETE FROM medkit_events "
                      "WHERE name LIKE 'проба ленты%'").rowcount
        c.commit()
        return n
    finally:
        c.close()


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright не установлен")
        return 2
    os.makedirs(КУДА, exist_ok=True)
    набито = _лента(60)
    print("лента набита: строк %d" % набито)
    кадров = 0
    try:
        with sync_playwright() as p:
            br = p.chromium.launch(headless=False)
            for ш in ШИРИНЫ:
                ctx = br.new_context(viewport={"width": ш, "height": 1000},
                                     has_touch=(ш <= 640))
                pg = ctx.new_page()
                pg.goto(БАЗА + "/login")
                pg.fill('input[name="email"]', ПОЧТА)
                pg.fill('input[name="password"]', ПАРОЛЬ)
                pg.click('button[type="submit"]')
                pg.wait_for_url(lambda u: "/login" not in u, timeout=25000)
                pg.goto(БАЗА + "/medkit")
                pg.wait_for_timeout(1600)

                # ── B: окно упаковок ─────────────────────────────────
                кн = pg.query_selector("[data-packs]")
                if кн:
                    кн.click()
                    pg.wait_for_timeout(1100)
                    pg.screenshot(path="%s/263-упаковки-%d.png" % (КУДА, ш))
                    кадров += 1
                    pg.keyboard.press("Escape")
                    pg.wait_for_timeout(400)

                # ── C и D: панель круга ──────────────────────────────
                кн = pg.query_selector("#apt-circle-open")
                if кн:
                    кн.click()
                    pg.wait_for_timeout(1400)
                    # вкладка ленты — там и живёт прокрутка
                    вкл = pg.query_selector('[data-ctab="feed"]')
                    if вкл:
                        вкл.click()
                        pg.wait_for_timeout(700)
                    pg.screenshot(path="%s/263-лента-полоса-%d.png" % (КУДА, ш))
                    кадров += 1
                    # шапка крупно: знак справки и крестик рядом
                    шапка = pg.query_selector("#apt-circle .modal-hdr")
                    if шапка:
                        шапка.screenshot(path="%s/263-шапка-%d.png" % (КУДА, ш))
                        кадров += 1
                    pg.keyboard.press("Escape")
                    pg.wait_for_timeout(400)

                # ── A: окно категорий (перечитывается при открытии) ──
                кн = pg.query_selector("[data-cats-open]")
                if кн:
                    кн.click()
                    pg.wait_for_timeout(1200)
                    pg.screenshot(path="%s/263-категории-%d.png" % (КУДА, ш))
                    кадров += 1
                    pg.keyboard.press("Escape")
                    pg.wait_for_timeout(300)
                ctx.close()
            br.close()
    finally:
        print("лента возвращена: убрано строк %d" % _лента_убрать())
    print("кадров снято: %d, каталог %s" % (кадров, КУДА))
    return 0


if __name__ == "__main__":
    sys.exit(main())
