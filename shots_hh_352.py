# -*- coding: utf-8 -*-
"""Снимки захода: вкладка «Резюме» на выдуманном резюме, 390 и 1920.

НЕ проверка, кадры смотрит человек. Резюме на стенде ВЫДУМАННОЕ (§5.1) —
настоящее в отчёт и в репозиторий не попадает.
"""
import os
import sys

sys.path.insert(0, r"E:\РАБОТА\Мои работы\Ai\HH помощник")
os.chdir(r"E:\РАБОТА\Мои работы\Ai\HH помощник")
import probe_guard  # noqa
import check_hover as ch
import browser_window  # noqa: F401  окно пробы на втором мониторе
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")
КУДА = os.path.join("review_screenshots", "352-письмо4")
os.makedirs(КУДА, exist_ok=True)


def снять(стр, имя, ширина):
    путь = os.path.join(КУДА, "%s-%d.png" % (имя, ширина))
    стр.screenshot(path=путь, full_page=True, animations="disabled")
    print("  ", путь)


with sync_playwright() as p:
    # ВИДИМОЕ ОКНО: это замер ВЁРСТКИ — headless прячет полосу прокрутки
    # без изъятия места, и ширины вышли бы завышенными (§6.0.3).
    бр = p.chromium.launch(headless=False)
    for ширина in (1920, 390):
        ctx = бр.new_context(viewport={"width": ширина, "height": 1000},
                             has_touch=(ширина == 390))
        стр = ctx.new_page()
        ch._войти(стр)
        стр.goto(ch.БАЗА + "/hh", wait_until="domcontentloaded")
        стр.wait_for_timeout(900)
        снять(стр, "письмо", ширина)

        стр.click('.v2-tab[data-view="resume"]')
        стр.wait_for_timeout(900)
        снять(стр, "резюме", ширина)

        # Раскрытая правка раздела — кнопки в шапке карточки
        # Карточка С КНОПКОЙ РАЗДЕЛА: у «Опыта работы» её нет вовсе —
        # он правится по местам, — и снимок первой карточки показывал бы
        # не то состояние, которое подписано.
        с = стр.locator(".hh-sec").filter(has=стр.locator(".hh-sec-edit")).first
        if с.count():
            с.locator(".hh-sec-edit").click()
            стр.wait_for_timeout(500)
            снять(стр, "резюме-правка-раздела", ширина)
            с.locator(".hh-sec-cancel").click()
            стр.wait_for_timeout(300)

        # Раскрытая правка ОДНОГО места работы
        if стр.locator(".hh-place-edit").count():
            стр.locator(".hh-place-edit").first.click()
            стр.wait_for_timeout(500)
            снять(стр, "резюме-правка-места", ширина)
            стр.locator(".hh-place-cancel").first.click()
            стр.wait_for_timeout(300)

        стр.click('.v2-tab[data-view="dossier"]')
        стр.wait_for_timeout(700)
        снять(стр, "досье", ширина)

        стр.click('.v2-tab[data-view="history"]')
        стр.wait_for_timeout(900)
        снять(стр, "история", ширина)
        ctx.close()
    бр.close()
print("готово")
