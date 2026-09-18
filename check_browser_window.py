# -*- coding: utf-8 -*-
"""ОКНО ПРОБЫ НА ВТОРОМ МОНИТОРЕ ИЛИ НЕТ — замер, а не допущение.

Запускает Chromium ТЕМ ЖЕ путём, что пробы (через `probe_guard`),
спрашивает у браузера координаты окна (CDP `Browser.getWindowForTarget`)
и называет монитор, в границы которого они легли.

    py check_browser_window.py              # код 0 — второй монитор, 1 — основной
    py check_browser_window.py --контроль   # смещение снято: обязан назвать основной
    py check_browser_window.py --ширина     # вьюпорт 2560 на втором и на основном:
                                            # совпадают ли замеры

Код 2 — второго монитора нет, спросить нечем.
"""
import os
import sys

import probe_guard  # noqa: F401  (ПРОПУСК вместо трассы; окно на второй монитор)
import browser_window as bw

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def _чей(x, y):
    for мx, мy, ш, в, основной in bw.мониторы():
        if мx <= x < мx + ш and мy <= y < мy + в:
            return ("ОСНОВНОЙ" if основной else "ВТОРОЙ"), (мx, мy, ш, в)
    return "ВНЕ МОНИТОРОВ", None


def _окно(вьюпорт=None):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        бр = p.chromium.launch(headless=False)
        try:
            кон = бр.new_context(viewport=вьюпорт) if вьюпорт else бр.new_context()
            стр = кон.new_page()
            стр.set_content("<html><body style='margin:0'>"
                            "<div id=b style='height:300vh'></div></body></html>")
            сес = кон.new_cdp_session(стр)
            окно = сес.send("Browser.getWindowForTarget")
            г = окно["bounds"]
            замер = стр.evaluate("""() => ({внутр: innerWidth,
                полоса: innerWidth - document.documentElement.clientWidth,
                dpr: devicePixelRatio})""")
            return г["left"], г["top"], замер
        finally:
            бр.close()


def main():
    второй = bw.второй_монитор()
    for x, y, ш, в, осн in bw.мониторы():
        print("монитор (%d,%d) %dx%d%s" % (x, y, ш, в, " основной" if осн else ""))
    if not второй:
        print("ПРОПУСК: второго монитора нет — спросить нечем")
        return 2
    контроль = "--контроль" in sys.argv
    if контроль:
        os.environ[bw.ОТКЛЮЧИТЬ_ПЕРЕМЕННАЯ] = "primary"
    if "--ширина" in sys.argv:
        _, _, на_втором = _окно({"width": 2560, "height": 1440})
        os.environ[bw.ОТКЛЮЧИТЬ_ПЕРЕМЕННАЯ] = "primary"
        _, _, на_основном = _окно({"width": 2560, "height": 1440})
        print("вьюпорт 2560 на втором:   %s" % на_втором)
        print("вьюпорт 2560 на основном: %s" % на_основном)
        сошлось = на_втором == на_основном
        print("ИТОГ: замеры %s" % ("СОВПАЛИ" if сошлось else "РАЗОШЛИСЬ"))
        return 0 if сошлось else 1
    x, y, _ = _окно()
    чей, _ = _чей(x, y)
    print("окно: левый верхний угол (%d,%d) — монитор %s" % (x, y, чей))
    if контроль:
        ок = чей == "ОСНОВНОЙ"
        print("КОНТРОЛЬ: смещение снято, проба %s" % (
            "НАЗВАЛА ОСНОВНОЙ — видит" if ок else "НЕ НАЗВАЛА ОСНОВНОЙ — слепа"))
        return 0 if ок else 1
    return 0 if чей == "ВТОРОЙ" else 1


if __name__ == "__main__":
    sys.exit(main())
