"""СНИМКИ ШИРОКОГО РЕЖИМА Enshrouded (№352, «enshrouded-2»).

НЕ проверка, кадры смотрит человек: решение «распространять ли широкий
режим на остальные инструменты» принимает владелец, а числа пробы
(`check_ens_wide.py`) отвечают только на вопрос о невмешательстве.

Ширины 1920 и 2560 — мониторы владельца; 1440 и 1600 сюда не входят,
экрана такой ширины у него нет (тот же довод, что у `shots_medkit`).

Кадры ложатся в `review_screenshots/ens_wide/` — каталог в .gitignore:
на стенде лежат данные, а репозиторий публичный (§5.1).
"""
import os
import sys

import probe_guard  # noqa: F401
import browser_window  # noqa: F401
import check_hover as ch

ШИРИНЫ = (1920, 2560)
КУДА = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    "review_screenshots", "ens_wide")


def main():
    from playwright.sync_api import sync_playwright
    os.makedirs(КУДА, exist_ok=True)
    снято = []
    with sync_playwright() as p:
        бр = p.chromium.launch(headless=False)
        for ш in ШИРИНЫ:
            к = бр.new_context(viewport={"width": ш, "height": 1100})
            стр = к.new_page()
            ch._войти(стр)
            стр.goto(ch.БАЗА + "/enshrouded", wait_until="domcontentloaded")
            # Карточки рисует скрипт: ждём сетку, а не таймер.
            стр.wait_for_selector(".sets-grid .set-card", timeout=15000)
            стр.wait_for_timeout(800)
            путь = os.path.join(КУДА, "enshrouded-%d.png" % ш)
            стр.screenshot(path=путь)
            з = стр.evaluate(
                "() => { const с = document.querySelector('.sets-grid');"
                " const r = с.getBoundingClientRect();"
                " return {сетка: Math.round(r.width),"
                "  колонок: getComputedStyle(с).gridTemplateColumns"
                "    .split(' ').filter(Boolean).length}; }")
            снято.append((ш, з, путь))
            к.close()
        бр.close()
    for ш, з, путь in снято:
        print("  %-5s сетка %d, колонок %d  → %s"
              % (ш, з["сетка"], з["колонок"], путь))
    print("кадров %d" % len(снято))
    return 0


if __name__ == "__main__":
    sys.exit(main())
