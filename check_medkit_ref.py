# -*- coding: utf-8 -*-
"""РАСХОД ЧУЖОГО СПРАВОЧНИКА В РАЗДЕЛЕ АПТЕЧКИ: место, вид, тона,
кому видно.

ЗАЧЕМ ОТДЕЛЬНО ОТ `check_admin_foot`. Та мерит ПОДВАЛ четырёх разделов
админки, и расход стоял там правой половиной с задачи 201. Решением
владельца 2026-09-12 он переехал в `/medkit` (BACKLOG №315) — то есть
вопрос сменил и страницу, и соседей: «виден ли он без нажатий»
и «не показан ли постороннему» на подвале админки не задавались вовсе.

МЕРИТ ВИДИМОЕ, А НЕ ВНУТРЕННЕЕ: доля полоски считается как ВИДИМАЯ
ширина заливки против коробки дорожки, а не как значение атрибута
`style`. Атрибут может стоять и не рисоваться — ровно это ловила
проверка 21 на `.btn-soft` (задача 254).

ТОН СТАВИТ СЕРВЕР, значит подстановкой в страницу его не проверить:
пришлось бы подменить ровно то, что проверяется. `--тона` меняет число
В БАЗЕ СТЕНДА и возвращает журнал в `finally` — при обрыве тоже.
Боевую базу не открывает: путь с `/data/` отвергается.

ГОЛОВНОЙ БРАУЗЕР (§6.0.3): ширина строки считается от контейнера
раздела, а headless прячет полосу прокрутки без изъятия места — все
ширины вышли бы завышенными.

МЕРКА, код возврата 0 (кроме `--контроль` и `--чужой`).

    py check_medkit_ref.py
    py check_medkit_ref.py --ширина 1920
    py check_medkit_ref.py --тона      # четыре состояния полоски
    py check_medkit_ref.py --чужой     # участнику круга строки НЕТ
    py check_medkit_ref.py --контроль  # подлог: заливка полоски мертва
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DB_PATH", "app.db")

import check_hover as ch     # noqa: E402
import make_local_user as _сид  # noqa: E402
import probe_guard  # noqa: F401

sys.stdout.reconfigure(encoding="utf-8")

NL = chr(10)
БАЗА = os.environ.get("STAND", "http://127.0.0.1:8899")
ШИРИНЫ = [2560, 1920, 390]

# ПОДЛОГ ЛОМАЕТ ЗВЕНО, КОТОРОЕ ПРОВЕРЯЕТСЯ: мерка спрашивает, меняет ли
# полоска ширину заливки по доле. Подлог фиксирует её на нуле — узел
# остаётся в дереве, а сказать ему нечего.
ПОДЛОГ = """
(() => {
  addEventListener('DOMContentLoaded', () => {
    const s = document.createElement('style');
    s.textContent = '.apt-quota-meter .meter-fill { width: 0 !important; }';
    document.head.appendChild(s);
  });
})();
"""

# ── ДОКАЗАТЕЛЬСТВО ПОДЛОГА (§6.0.3) ─────────────────────────────────
#
# «Доля стала нулём» — это вердикт самой мерки, и повторять его значило
# бы доказывать вердикт вердиктом. Независимый замер спрашивает ДРУГОЕ:
# жива ли сама дорожка. Заливка шириной 0 при дорожке шириной 0 — это
# не погашенная заливка, а схлопнувшийся блок, и различить эти два
# случая может только замер коробки.
ДОКАЗАТЕЛЬСТВА = {
    "заливка полоски мертва": (
        """() => {
          const d = document.querySelector('.apt-quota-meter');
          const f = document.querySelector('.apt-quota-meter .meter-fill');
          if (!d) return 'дорожки .apt-quota-meter нет';
          return 'дорожка ' + d.getBoundingClientRect().width.toFixed(1)
               + ', заливка ' + (f ? f.getBoundingClientRect().width.toFixed(1)
                                   : 'НЕТ');
        }""",
        "ширина дорожки и заливки по отдельности"),
}

ЗАМЕР = r"""
() => {
  const кор = e => { if (!e) return null; const b = e.getBoundingClientRect();
    return {x: +b.x.toFixed(1), y: +b.y.toFixed(1),
            w: +b.width.toFixed(1), h: +b.height.toFixed(1)}; };

  const ряд = document.querySelector('.apt-bar');
  const чипы = document.querySelector('.apt-chips');
  const кв = document.querySelector('.apt-quota');
  const мет = document.querySelector('.apt-quota-meter');
  const зал = document.querySelector('.apt-quota-meter .meter-fill');
  const кнопка = document.getElementById('apt-recheck-open');

  // ВИДЕН БЕЗ НАЖАТИЙ И БЕЗ ПРОКРУТКИ — главный вопрос места
  // (условие A2 письма). Спрашивается У ОКНА, а не у нашей раскладки:
  // блок целиком выше нижнего края первого экрана.
  const виден = кв ? (() => {
    const b = кв.getBoundingClientRect();
    const до = b.top + window.scrollY;
    return {в_первом_экране: b.bottom <= window.innerHeight,
            прокрутки_до: +Math.max(0, до - window.innerHeight + b.height)
                             .toFixed(1),
            высота_окна: window.innerHeight};
  })() : null;

  return {
    экран: document.body.clientWidth,
    ряд: кор(ряд), чипы: кор(чипы), квота: кор(кв), кнопка: кор(кнопка),
    // Зазоры: строка обязана быть прижата к ряду управления сверху
    // и отбита от ряда чипов снизу.
    зазор_ряд: (ряд && кв) ? +(кв.getBoundingClientRect().top
      - ряд.getBoundingClientRect().bottom).toFixed(1) : null,
    зазор_чипы: (чипы && кв) ? +(чипы.getBoundingClientRect().top
      - кв.getBoundingClientRect().bottom).toFixed(1) : null,
    видимость: виден,
    текст: кв ? кв.innerText.replace(/\s+/g, ' ').trim() : null,
    тон: кв ? кв.className.replace(/\s+/g, ' ').trim() : null,
    кегль: кв ? getComputedStyle(кв).fontSize : null,
    цвет_подписи: кв ? getComputedStyle(кв).color : null,
    // ГАРНИТУРА СПРАШИВАЕТСЯ У БРАУЗЕРА, а не у имени класса: класс
    // может стоять и не применяться (проверка 21 ловит ровно это).
    моно: (() => {
      const n = document.querySelector('.apt-quota-n');
      return n ? getComputedStyle(n).fontFamily : null;
    })(),
    полоска: зал ? {
      ширина: +зал.getBoundingClientRect().width.toFixed(1),
      коробка: +мет.getBoundingClientRect().width.toFixed(1),
      доля: +(зал.getBoundingClientRect().width
              / Math.max(1, мет.getBoundingClientRect().width)).toFixed(3),
      цвет: getComputedStyle(зал).backgroundColor,
    } : null,
    // ПЕРЕЛИВ: строка не имеет права расширить страницу.
    перелив: document.documentElement.scrollWidth - window.innerWidth,
  };
}
"""


def _снять(ширина, подлог=None, почта=None, пароль=None):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        бр = p.chromium.launch(headless=False)
        кон = бр.new_context(viewport={"width": ширина, "height": 900},
                             has_touch=(ширина < 640), is_mobile=False,
                             device_scale_factor=1)
        стр = кон.new_page()
        прежние = (ch.ПОЧТА, ch.ПАРОЛЬ)
        try:
            if почта:
                ch.ПОЧТА, ch.ПАРОЛЬ = почта, пароль
            ch._войти(стр)
        finally:
            ch.ПОЧТА, ch.ПАРОЛЬ = прежние
        if подлог:
            стр.add_init_script(подлог)
        стр.goto(БАЗА + "/medkit", wait_until="load", timeout=45000)
        стр.wait_for_timeout(700)
        о = стр.evaluate(ЗАМЕР)
        доказ = None
        if подлог:
            доказ = стр.evaluate(ДОКАЗАТЕЛЬСТВА["заливка полоски мертва"][0])
        бр.close()
    return о, доказ


def _печать(ширина, о):
    print(NL + "-" * 74)
    print("РАСХОД СПРАВОЧНИКА В АПТЕЧКЕ  —  ширина %d" % ширина)
    print("-" * 74)
    if not о.get("квота"):
        print("  строки `.apt-quota` НЕТ")
        return о
    к = о["квота"]
    print("  строка h=%.1f  w=%.1f  y=%.1f" % (к["h"], к["w"], к["y"]))
    print("  зазор от ряда управления %s px, до ряда чипов %s px"
          % (о["зазор_ряд"], о["зазор_чипы"]))
    в = о["видимость"]
    print("  ВИДНА БЕЗ ПРОКРУТКИ: %s  (прокрутки до неё %.1f px при окне %d)"
          % ("да" if в["в_первом_экране"] else "НЕТ",
             в["прокрутки_до"], в["высота_окна"]))
    print("  текст: %s" % о["текст"])
    print("  кегль %s, цвет %s, моно %s"
          % (о["кегль"], о["цвет_подписи"], (о["моно"] or "")[:28]))
    л = о.get("полоска")
    if л:
        print("  полоска: доля %.3f (%.1f из %.1f), цвет %s"
              % (л["доля"], л["ширина"], л["коробка"], л["цвет"]))
    else:
        print("  полоски НЕТ")
    print("  класс строки: %s" % о["тон"])
    print("  перелив страницы: %d px" % о["перелив"])
    return о


# ── ТОНА ПОЛОСКИ: три порога — три КЛАССА и три ЦВЕТА ────────────────
# Класс ставит СЕРВЕР по доле; меняется число В БАЗЕ СТЕНДА и
# возвращается в `finally`.
ДОЛИ = [("обычный", 0.30), ("предупреждение", 0.75), ("красный", 0.95),
        ("исчерпан", 1.00)]


def _тона():
    import datetime
    import sqlite3
    путь = os.environ.get("DB_PATH", "app.db")
    if "/data/" in путь.replace(chr(92), "/"):
        print("ПРОПУСК: путь похож на боевую базу — %s" % путь)
        return 2
    день = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d")
    месяц = день[:7] + "%"
    c = sqlite3.connect(путь)
    было = c.execute("SELECT id, day, host, n FROM ref_requests "
                     "WHERE day LIKE ?", (месяц,)).fetchall()
    предел = int(os.environ.get("MEDKIT_REF_MONTH_CAP", "3000"))
    print("ТОНА ПОЛОСКИ. Предел %d, строк журнала за месяц %d — "
          "вернутся в конце." % (предел, len(было)))
    try:
        for имя, доля in ДОЛИ:
            n = int(предел * доля)
            c.execute("DELETE FROM ref_requests WHERE day LIKE ?", (месяц,))
            c.execute("INSERT INTO ref_requests (day, host, n) VALUES (?,?,?)",
                      (день, "проба", n))
            c.commit()
            о, _ = _снять(1920)
            л = о.get("полоска") or {}
            print("  %-14s %5d из %d (%.0f%%)  класс=%-24s цвет=%s  доля=%.3f"
                  % (имя, n, предел, доля * 100,
                     (о.get("тон") or "").replace("apt-quota", "").strip()
                     or "(без модификатора)",
                     л.get("цвет"), л.get("доля", 0)))
            print("                 текст: %s" % о.get("текст"))
    finally:
        c.execute("DELETE FROM ref_requests WHERE day LIKE ?", (месяц,))
        for _, d, h, n in было:
            c.execute("INSERT INTO ref_requests (day, host, n) VALUES (?,?,?)",
                      (d, h, n))
        c.commit()
        оста = c.execute("SELECT COALESCE(SUM(n),0) FROM ref_requests "
                         "WHERE day LIKE ?", (месяц,)).fetchone()[0]
        c.close()
        print("  журнал возвращён: за месяц %d" % оста)
    return 0


def _чужой():
    """ВТОРАЯ ПОЛОВИНА ПРАВИЛА: постороннему строки НЕТ.

    Показатель считается по ВСЕМУ приложению, и участнику общей аптечки
    он отвечает на вопрос, которого тот не задавал. Проверяется ОБЕИМИ
    половинами сразу: у владельца строка ЕСТЬ, у соседа по кругу НЕТ, —
    иначе «нет у соседа» прошло бы и у пробы, которая строки не видит
    вовсе (§6.0.3).
    """
    о_вл, _ = _снять(1920)
    о_сос, _ = _снять(1920, почта=_сид.EMAIL_СОСЕД,
                      пароль=_сид.PASSWORD_СОСЕД)
    есть_вл = bool(о_вл.get("квота"))
    есть_сос = bool(о_сос.get("квота"))
    print("  владелец (админ):   строка %s" % ("ЕСТЬ" if есть_вл else "НЕТ"))
    print("  сосед по кругу:     строка %s" % ("ЕСТЬ" if есть_сос else "НЕТ"))
    print("     дерево соседа: %s" % (о_сос.get("текст") or "(нет узла)"))
    ок = есть_вл and not есть_сос
    print(NL + "  ИТОГ: %s" % ("владельцу видно, постороннему нет"
                               if ок else "ПРАВИЛО НАРУШЕНО"))
    return 0 if ок else 1


def _контроль():
    print("КОНТРОЛЬ: подлог обнуляет ЗАЛИВКУ полоски расхода.")
    print("Мерка обязана назвать долю нулём, а не промолчать." + NL)
    итог = {}
    for метка, подлог in (("чисто", None), ("подлог", ПОДЛОГ),
                          ("возврат", None)):
        о, доказ = _снять(1920, подлог)
        л = о.get("полоска") or {}
        итог[метка] = л.get("доля")
        print("  %-8s доля %s  (заливка %s из %s)"
              % (метка, л.get("доля"), л.get("ширина"), л.get("коробка")))
        if доказ:
            print("           ДОКАЗАТЕЛЬСТВО (%s): %s"
                  % (ДОКАЗАТЕЛЬСТВА["заливка полоски мертва"][1], доказ))
    ок = (bool(итог["чисто"]) and итог["подлог"] == 0.0
          and итог["возврат"] == итог["чисто"])
    print(NL + "  КОНТРОЛЬ: %s — %s -> %s -> %s"
          % ("ПОДЛОГ НАЙДЕН" if ок else "НЕ ДОКАЗАН",
             итог["чисто"], итог["подлог"], итог["возврат"]))
    return 0 if ок else 1


def главная():
    if "--тона" in sys.argv:
        return _тона()
    if "--чужой" in sys.argv:
        return _чужой()
    if "--контроль" in sys.argv:
        return _контроль()
    ширины = ШИРИНЫ
    if "--ширина" in sys.argv:
        ширины = [int(sys.argv[sys.argv.index("--ширина") + 1])]
    нет = 0
    for ш in ширины:
        о, _ = _снять(ш)
        _печать(ш, о)
        if not о.get("квота"):
            нет += 1
    if нет == len(ширины):
        # ПУСТОЙ СБОР НЕ РАВЕН УСПЕХУ (правило 3 письма): строки нет
        # ни на одной ширине — мерить было нечего, и печатать нули
        # значило бы выдать «спросить нечем» за «всё в порядке».
        print(NL + "ПРОПУСК: строки расхода нет ни на одной ширине — "
              "нечего мерить (аккаунт не админ либо предел не задан)")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(главная())
