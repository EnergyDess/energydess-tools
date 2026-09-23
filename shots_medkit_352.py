# -*- coding: utf-8 -*-
"""СНИМКИ АПТЕЧКИ ДО И ПОСЛЕ РЕДИЗАЙНА (№352, «аптечка-1»).

НЕ проверка, кадры смотрит человек: «стало ли лучше» машине не выводится
(§6.0.8 называет виды изменений, а решение остаётся за владельцем).

    py shots_medkit_352.py --в medkit_after
    py shots_medkit_352.py --в medkit_before --база http://127.0.0.1:8896

КАДРЫ. Экран целиком на 1600 и 390, карточка крупно, панель «чего
не хватает» (после редизайна) либо окно перепроверки (до), вкладка
«Купить». Ширины — те, на которых меряет проверка 61; 2560 нет
намеренно: письмо владельца называет 1600 и 390.

БРАУЗЕР ВИДИМЫЙ И НА ВТОРОМ МОНИТОРЕ (§6.0.3, `browser_window`): кадр
снимается с тем же резервом полосы прокрутки, что видит человек.

СНИМКИ В РЕПОЗИТОРИЙ НЕ ПОПАДАЮТ — `review_screenshots/` в .gitignore,
и это не удобство: на стенде лежат названия лекарств, а репозиторий
публичный (§5.1, проверка 26).
"""
import os
import sys

try:
    import probe_guard  # noqa: F401
except ImportError:
    pass

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

КОРЕНЬ = os.path.dirname(os.path.abspath(__file__))
КУДА = os.path.join(КОРЕНЬ, "review_screenshots")
ШИРИНЫ = (1600, 390)


def главная():
    import browser_window  # noqa: F401  окно — на втором мониторе
    import check_hover as ch
    from playwright.sync_api import sync_playwright

    каталог = "medkit_after"
    if "--в" in sys.argv:
        каталог = sys.argv[sys.argv.index("--в") + 1]
    if "--база" in sys.argv:
        ch.БАЗА = sys.argv[sys.argv.index("--база") + 1]
    путь = os.path.join(КУДА, каталог)
    os.makedirs(путь, exist_ok=True)

    снято = []
    with sync_playwright() as p:
        бр = p.chromium.launch(headless=False)
        try:
            for ш in ШИРИНЫ:
                кон = бр.new_context(viewport={"width": ш, "height": 1100},
                                     has_touch=ш < 640)
                стр = кон.new_page()
                ch._войти(стр)
                стр.goto(ch.БАЗА + "/medkit", wait_until="networkidle",
                         timeout=45000)
                стр.wait_for_timeout(900)

                def кадр(имя, **как):
                    файл = os.path.join(путь, "%s-%d.png" % (имя, ш))
                    стр.screenshot(path=файл, animations="disabled", **как)
                    снято.append(os.path.basename(файл))

                кадр("экран", full_page=True)
                карточка = стр.locator(".apt-card").first
                if карточка.count():
                    файл = os.path.join(путь, "карточка-%d.png" % ш)
                    карточка.screenshot(path=файл, animations="disabled")
                    снято.append(os.path.basename(файл))

                # ПАНЕЛЬ «ЧЕГО НЕ ХВАТАЕТ» — после редизайна панель справа,
                # до него то же действие открывало модальное окно
                кнопка = ("#apt-recheck-open" if стр.locator("#apt-recheck-open").count()
                          else "#apt-recheck")
                if стр.locator(кнопка).count():
                    стр.click(кнопка)
                    стр.wait_for_timeout(1200)
                    кадр("перепроверка")
                    стр.keyboard.press("Escape")
                    стр.wait_for_timeout(500)

                # ПАНЕЛЬ ЛЕКАРСТВА (№352, «аптечка-2», блок 2).
                # Кадров ДВА, и одного мало: у позиции с обеими записями
                # видны порядок разделов и метки, у позиции без записей —
                # пустое состояние с двумя ходами. На одной карточке
                # ни того ни другого не снять.
                for сел, имя in ((".apt-card [data-doses]", "лекарство"),
                                 (".apt-card:has(.apt-gap) [data-doses]",
                                  "лекарство-пусто")):
                    орган = стр.locator(сел).first
                    if not орган.count():
                        continue
                    орган.click()
                    стр.wait_for_timeout(700)
                    кадр(имя)
                    стр.keyboard.press("Escape")
                    стр.wait_for_timeout(400)

                # СПИСОК ПОКУПОК: вкладка после редизайна, свёрнутый блок до
                if стр.locator(".apt-tabbtn[data-tab=buy]").count():
                    стр.click(".apt-tabbtn[data-tab=buy]")
                elif стр.locator("#apt-buy summary").count():
                    стр.click("#apt-buy summary")
                стр.wait_for_timeout(700)
                кадр("купить")
                кон.close()
        finally:
            бр.close()
    print("Снято %d кадров в %s:" % (len(снято), путь))
    for и in sorted(снято):
        print("   " + и)
    return 0


if __name__ == "__main__":
    sys.exit(главная())
