"""СНИМКИ ШИРОКОГО РЕЖИМА У ВСЕХ ИНСТРУМЕНТОВ (№352, письмо «широкий
режим везде»).

НЕ проверка, кадры смотрит человек: числа даёт `check_v2_wide.py`,
а «стало ли лучше» решает владелец. ЗАМЕНИЛА `shots_ens_wide.py`:
тот снимал один инструмент, потому что режим был пробой одного
инструмента; теперь потолок поднят всем, и смотреть надо пару —
Enshrouded (сетка получила пятую колонку) и аптечку (получила её же
и вдобавок переехавшие в шапку счётчики).

Ширины 1920 и 2560 — мониторы владельца; 1440 и 1600 сюда не входят,
экрана такой ширины у него нет (тот же довод, что у `shots_medkit`).

Кадры ложатся в `review_screenshots/wide_all/` — каталог в .gitignore:
на стенде лежат названия лекарств, а репозиторий публичный (§5.1,
проверка 26). В контекст сессии кадры не читаются, из них берутся
только ЧИСЛА, которые печатает эта же команда (§6.4 «г»).
"""
import os
import sys

import probe_guard  # noqa: F401
import browser_window  # noqa: F401
import check_hover as ch

ШИРИНЫ = (1920, 2560)
# (путь, имя, чего дождаться). Ждём СОДЕРЖИМОГО, а не таймера: сетку
# Enshrouded рисует скрипт, карточки аптечки приходят с сервером.
ЭКРАНЫ = [
    ("/enshrouded", "enshrouded", ".sets-grid .set-card"),
    ("/medkit", "medkit", "#apt-grid .apt-card"),
]
КУДА = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    "review_screenshots", "wide_all")

ЗАМЕР = """() => {
  const окр = (v) => Math.round(v);
  const кол = document.querySelector('.v2-shell-main');
  const ш = document.querySelector('.v2-page-head');
  const сетка = document.querySelector('.sets-grid, #apt-grid .apt-grid, .apt-grid');
  const о = {};
  if (кол) о.колонка = окр(кол.getBoundingClientRect().width);
  if (ш) о.шапка = окр(ш.getBoundingClientRect().width);
  if (сетка) {
    const r = сетка.getBoundingClientRect();
    о.сетка = окр(r.width);
    о.колонок = getComputedStyle(сетка).gridTemplateColumns.split(' ').filter(Boolean).length;
    const к = сетка.querySelector(':scope > *');
    if (к) о.карточка = окр(к.getBoundingClientRect().width);
  }
  return о;
}"""


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
            for путь, имя, ждать in ЭКРАНЫ:
                стр.goto(ch.БАЗА + путь, wait_until="domcontentloaded")
                try:
                    стр.wait_for_selector(ждать, timeout=15000)
                except Exception:
                    pass
                стр.wait_for_timeout(800)
                файл = os.path.join(КУДА, "%s-%d.png" % (имя, ш))
                стр.screenshot(path=файл)
                снято.append((ш, имя, стр.evaluate(ЗАМЕР), файл))
            к.close()
        бр.close()
    for ш, имя, з, файл in снято:
        print("  %-5s %-11s колонка %s, шапка %s, сетка %s, колонок %s, карточка %s → %s"
              % (ш, имя, з.get("колонка"), з.get("шапка"), з.get("сетка"),
                 з.get("колонок"), з.get("карточка"), os.path.basename(файл)))
    print("кадров %d, каталог %s" % (len(снято), КУДА))
    return 0


if __name__ == "__main__":
    sys.exit(main())
