# -*- coding: utf-8 -*-
"""СНИМКИ ЗАХОДА 312: полоса отбора всех четырёх разделов и подвал
«Пользователей» на трёх ширинах.

НЕ ПРОВЕРКА — кадры смотрит человек.

РАСХОД СПРАВОЧНИКА ПОДСТАВЛЯЕТСЯ БОЕВЫМ ЧИСЛОМ и возвращается
в `finally`: на стенде журнал накопил 3000 из 3000, то есть кадр
показывал бы КРАЙНЕЕ состояние («предел исчерпан», красная полоска)
вместо обычного, которое владелец и видит. Состояние, противоположное
нужному, — то же упущение, что §8.0 разбирает у seed.

Кадр исчерпания снимается ОТДЕЛЬНО: оба состояния настоящие, и одно
не заменяет другое.

    py make_local_user.py --seed
    py -m uvicorn main:app --port 8899
    py shots_admin_312.py
"""
import datetime
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DB_PATH", "app.db")

import check_hover as ch     # noqa: E402
import probe_guard  # noqa: F401

sys.stdout.reconfigure(encoding="utf-8")

БАЗА = os.environ.get("STAND", "http://127.0.0.1:8899")
КУДА = os.environ.get("SHOTS_DIR", "review_screenshots")
ШИРИНЫ = [2560, 1920, 390]
РАЗДЕЛЫ = [("/admin/users", "users"), ("/admin/products", "products"),
           ("/admin/exercises", "exercises"),
           ("/admin/enshrouded", "enshrouded")]

# Боевое число на 2026-09-12: 733 из 3000 (24.4%) — обычное состояние.
БОЕВОЙ_РАСХОД = 733


def _подставить(n):
    """Вернуть прежние строки журнала, поставив своё число."""
    день = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d")
    месяц = день[:7] + "%"
    c = sqlite3.connect(os.environ.get("DB_PATH", "app.db"))
    было = c.execute("SELECT day, host, n FROM ref_requests WHERE day LIKE ?",
                     (месяц,)).fetchall()
    c.execute("DELETE FROM ref_requests WHERE day LIKE ?", (месяц,))
    c.execute("INSERT INTO ref_requests (day, host, n) VALUES (?,?,?)",
              (день, "проба", n))
    c.commit()
    c.close()
    return было, месяц


def _вернуть(было, месяц):
    c = sqlite3.connect(os.environ.get("DB_PATH", "app.db"))
    c.execute("DELETE FROM ref_requests WHERE day LIKE ?", (месяц,))
    for d, h, n in было:
        c.execute("INSERT INTO ref_requests (day, host, n) VALUES (?,?,?)",
                  (d, h, n))
    c.commit()
    итог = c.execute("SELECT COALESCE(SUM(n),0) FROM ref_requests "
                     "WHERE day LIKE ?", (месяц,)).fetchone()[0]
    c.close()
    return итог


def главная():
    from playwright.sync_api import sync_playwright
    os.makedirs(КУДА, exist_ok=True)
    путь = os.environ.get("DB_PATH", "app.db")
    if "/data/" in путь.replace("\\", "/"):
        print("ПРОПУСК: путь похож на боевую базу — %s" % путь)
        return 2

    было, месяц = _подставить(БОЕВОЙ_РАСХОД)
    снято = 0
    try:
        with sync_playwright() as p:
            бр = p.chromium.launch(headless=False)
            for ш in ШИРИНЫ:
                кон = бр.new_context(viewport={"width": ш, "height": 1100},
                                     has_touch=(ш < 640), is_mobile=False,
                                     device_scale_factor=1)
                стр = кон.new_page()
                ch._войти(стр)
                for адрес, имя in РАЗДЕЛЫ:
                    стр.goto(f"{БАЗА}{адрес}", wait_until="load", timeout=45000)
                    стр.wait_for_timeout(600)
                    # Полоса отбора вместе с заголовком раздела: кадр
                    # обязан показать, с чем она выровнена.
                    файл = os.path.join(КУДА, "312-bar-%s-%d.png" % (имя, ш))
                    стр.screenshot(path=файл, clip={
                        "x": 0, "y": 0, "width": ш,
                        "height": min(560, 1100)})
                    снято += 1
                # Подвал — только у «Пользователей», и он внизу страницы.
                стр.goto(f"{БАЗА}/admin/users", wait_until="load", timeout=45000)
                стр.wait_for_timeout(500)
                эл = стр.query_selector(".admin-foot")
                if эл:
                    эл.scroll_into_view_if_needed()
                    стр.wait_for_timeout(300)
                    эл.screenshot(path=os.path.join(
                        КУДА, "312-foot-%d.png" % ш))
                    снято += 1
                кон.close()

            # ИСЧЕРПАНИЕ — ОТДЕЛЬНЫМ КАДРОМ: состояние настоящее
            # и выглядит иначе (красная полоска плюс слово).
            _вернуть(было, месяц)
            было2, месяц2 = _подставить(3000)
            кон = бр.new_context(viewport={"width": 1920, "height": 1100},
                                 device_scale_factor=1)
            стр = кон.new_page()
            ch._войти(стр)
            стр.goto(f"{БАЗА}/admin/users", wait_until="load", timeout=45000)
            стр.wait_for_timeout(500)
            эл = стр.query_selector(".admin-foot")
            if эл:
                эл.scroll_into_view_if_needed()
                стр.wait_for_timeout(300)
                эл.screenshot(path=os.path.join(
                    КУДА, "312-foot-исчерпан-1920.png"))
                снято += 1
            кон.close()
            бр.close()
            было, месяц = было2, месяц2
    finally:
        итог = _вернуть(было, месяц)
        print("журнал расхода возвращён: за месяц %d" % итог)
    print("кадров снято: %d  →  %s" % (снято, КУДА))
    return 0


if __name__ == "__main__":
    sys.exit(главная())
