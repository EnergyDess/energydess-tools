# -*- coding: utf-8 -*-
"""ПОЛОСА ОТБОРА АДМИНКИ: высоты органов, этажи чипов, подложка.

ЗАЧЕМ ОТДЕЛЬНЫЙ ФАЙЛ. Соседняя `check_admin_look.py` спрашивает про
ПАНЕЛЬ РАЗДЕЛОВ (`.admin-nav-bar`) — долю экрана, подложку, размер
вкладки. Полосу ОТБОРА (`.admin-bar`) она берёт одним числом
«чип_высота» и только на разделе «Пользователи»; вопрос «совпадают ли
высоты поиска, списка и кнопки МЕЖДУ СОБОЙ и МЕЖДУ РАЗДЕЛАМИ» не задавал
никто. Владелец увидел разнобой глазом, и у этого вопроса есть
буквальный ответ в живом дереве.

ГОЛОВНОЙ БРАУЗЕР ОБЯЗАТЕЛЕН (§6.0.3): ширина полосы считается
от контейнера страницы, а headless прячет полосу прокрутки БЕЗ изъятия
места — все ширины вышли бы завышенными на 15 px, и «поместились ли
чипы в одну строку» проба отвечала бы не про тот экран.

МЕРКА, а не проверка: код возврата 0 (кроме `--контроль`). Сколько
пикселей разбега считать бедой — решение об облике, а не о коде.

    py make_local_user.py --seed
    py -m uvicorn main:app --port 8899

    py check_admin_bar.py                 # 2560, 1920, 390
    py check_admin_bar.py --ширина 1920
    py check_admin_bar.py --контроль      # подлог: орган ниже на 4 px
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DB_PATH", "app.db")

import check_hover as ch     # noqa: E402
import probe_guard  # noqa: F401  ПРОПУСК вместо трассы (§6.0.1)

sys.stdout.reconfigure(encoding="utf-8")

БАЗА = os.environ.get("STAND", "http://127.0.0.1:8899")

РАЗДЕЛЫ = [
    ("/admin/users", "Пользователи"),
    ("/admin/products", "Продукты"),
    ("/admin/exercises", "Упражнения"),
    ("/admin/enshrouded", "Enshrouded"),
]

ШИРИНЫ = [2560, 1920, 390]

# ПОДЛОГ ЛОМАЕТ ТО ЗВЕНО, КОТОРОЕ ПРОВЕРЯЕТСЯ: мерка сравнивает ВЫСОТЫ
# органов между собой, значит подлог занижает высоту ОДНОГО органа.
# Кладётся В СТРАНИЦУ, кода не трогает.
ПОДЛОГ = """
(() => {
  addEventListener('DOMContentLoaded', () => {
    const s = document.createElement('style');
    s.textContent = '.admin-bar .search-input-admin { height: calc(var(--admin-bar-h, 2.5rem) - 4px) !important; min-height: 0 !important; }';
    document.head.appendChild(s);
  });
})();
"""

# ── ДОКАЗАТЕЛЬСТВО ПОДЛОГА (§6.0.3) ─────────────────────────────────
#
# «Разбег вырос» доказательством НЕ является: он вырос бы и от чужой
# правки, и от загрузившегося другим шрифтом чипа. Стилевой подлог
# вдобавок умеет провалиться МОЛЧА — нераспознанное правило браузер
# просто выбрасывает, исключения не бросая.
#
# Замер НЕЗАВИСИМ ОТ ВЕРДИКТА: он спрашивает не «сколько разбега»,
# а высоту ИМЕННО ТОГО органа, в который метит подлог. Логикой мерки
# он не пользуется — свой `getBoundingClientRect` на своём селекторе.
ДОКАЗАТЕЛЬСТВА = {
    "поле поиска ниже на 4 px": (
        """() => {
          const p = document.querySelector('.admin-bar .search-input-admin');
          if (!p) return 'поля поиска в полосе нет';
          return 'высота поля: ' + p.getBoundingClientRect().height.toFixed(1);
        }""",
        "высота поля поиска"),
}


ЗАМЕР = r"""
() => {
  const кор = e => { if (!e) return null;
    const b = e.getBoundingClientRect();
    return {x: +b.x.toFixed(1), y: +b.y.toFixed(1),
            w: +b.width.toFixed(1), h: +b.height.toFixed(1),
            right: +b.right.toFixed(1), bottom: +b.bottom.toFixed(1)}; };

  const бар = document.querySelector('.admin-bar');
  if (!бар) return {бар: null};
  const sb = getComputedStyle(бар);
  const ряд = бар.querySelector('.chip-row');
  const инстр = бар.querySelector('.admin-bar-tools');
  const чипы = [...бар.querySelectorAll('.chip')];
  const поиск = бар.querySelector('.search-input-admin');
  const списки = [...бар.querySelectorAll('select')];
  const кнопки = [...бар.querySelectorAll('button:not(.chip)')];

  // ЭТАЖИ ЧИПОВ — по РАЗНЫМ значениям y, а не по числу чипов:
  // перенос виден только так. Округление до целого: субпиксельная
  // раскладка иначе даёт ложные этажи.
  const этажи = new Set(чипы.map(c => Math.round(
    c.getBoundingClientRect().y)));

  // ОБРЕЗКА ПОДСКАЗКИ ПОЛЯ. Меряется НЕ строка, а её ширина в тех же
  // метриках, что у поля: подсказку рисует браузер, в дерево она
  // не попадает. Канва с той же гарнитурой и кеглем — единственный
  // способ спросить «влезает ли».
  let подсказка = null;
  if (поиск) {
    const sp = getComputedStyle(поиск);
    const cv = document.createElement('canvas').getContext('2d');
    cv.font = sp.fontWeight + ' ' + sp.fontSize + ' ' + sp.fontFamily;
    const текст = поиск.placeholder || '';
    const нужно = cv.measureText(текст).width;
    const место = поиск.clientWidth
                - parseFloat(sp.paddingLeft) - parseFloat(sp.paddingRight);
    подсказка = {текст: текст, нужно: +нужно.toFixed(1),
                 место: +место.toFixed(1), влезает: нужно <= место};
  }

  const орган = (имя, e) => {
    if (!e) return null;
    const s = getComputedStyle(e);
    const b = e.getBoundingClientRect();
    return {имя: имя, h: +b.height.toFixed(1), w: +b.width.toFixed(1),
            x: +b.x.toFixed(1), y: +b.y.toFixed(1),
            кегль: +parseFloat(s.fontSize).toFixed(2)};
  };

  const органы = [];
  if (чипы.length) органы.push(орган('чип', чипы[0]));
  if (поиск) органы.push(орган('поиск', поиск));
  списки.forEach((s, i) => органы.push(орган('список' + (i + 1), s)));
  кнопки.forEach((b, i) => органы.push(орган('кнопка' + (i + 1), b)));

  return {
    экран: document.body.clientWidth,
    бар: кор(бар),
    фон: sb.backgroundColor,
    рамка: sb.borderTopWidth + ' ' + sb.borderTopStyle + ' ' + sb.borderTopColor,
    радиус: sb.borderTopLeftRadius,
    паддинг: [sb.paddingTop, sb.paddingRight,
              sb.paddingBottom, sb.paddingLeft].join(' '),
    фон_страницы: getComputedStyle(document.body).backgroundColor,
    ряд: кор(ряд), инстр: кор(инстр),
    чипов: чипы.length, этажей: этажи.size,
    органы: органы.filter(Boolean),
    подсказка: подсказка,
    // ПОРЯДОК: чипы обязаны стоять ЛЕВЕЕ управления. На узкой ширине
    // ряд ломается в столбик — там сравниваются y, а не x.
    столбиком: sb.flexDirection === 'column',
  };
}
"""


def _снять(ширина, сенсор, подлог=None):
    from playwright.sync_api import sync_playwright
    итог = {}
    with sync_playwright() as p:
        # ГОЛОВНОЙ: headless прячет полосу прокрутки без изъятия места.
        бр = p.chromium.launch(headless=False)
        кон = бр.new_context(viewport={"width": ширина, "height": 900},
                             has_touch=сенсор, is_mobile=False,
                             device_scale_factor=1)
        стр = кон.new_page()
        ch._войти(стр)
        if подлог:
            стр.add_init_script(подлог)
        for путь, имя in РАЗДЕЛЫ:
            стр.goto(f"{БАЗА}{путь}", wait_until="load", timeout=45000)
            стр.wait_for_timeout(400)
            итог[имя] = стр.evaluate(ЗАМЕР)
        # ДОКАЗАТЕЛЬСТВО СНИМАЕТСЯ ЗДЕСЬ ЖЕ, на последней открытой
        # странице и в той же сессии: отдельным заходом браузера оно
        # мерило бы другую загрузку, а объявленное и не прогнанное
        # доказательство ничем не отличается от отсутствующего.
        for _, (js, что) in ДОКАЗАТЕЛЬСТВА.items():
            итог["__док__"] = (что, стр.evaluate(js))
        бр.close()
    return итог


def _печать(ширина, снимок):
    print("\n" + "=" * 74)
    print("ШИРИНА %d" % ширина)
    print("=" * 74)
    все_высоты = []
    for _, имя in РАЗДЕЛЫ:
        о = снимок.get(имя) or {}
        if not о.get("бар"):
            print("  %-14s полосы `.admin-bar` в дереве НЕТ" % имя)
            continue
        высоты = [(г["имя"], г["h"]) for г in о["органы"]]
        все_высоты += [в for _, в in высоты]
        разбег = (max(в for _, в in высоты) - min(в for _, в in высоты)
                  if высоты else 0.0)
        print("  %-14s полоса h=%.1f  фон=%s  этажей=%d (чипов %d)"
              % (имя, о["бар"]["h"], о["фон"], о["этажей"], о["чипов"]))
        print("                 органы: %s"
              % ", ".join("%s %.1f" % (н, в) for н, в in высоты))
        print("                 разбег ВНУТРИ раздела: %.1f px" % разбег)
        п = о.get("подсказка")
        if п:
            print("                 подсказка «%s»: нужно %.1f, место %.1f — %s"
                  % (п["текст"], п["нужно"], п["место"],
                     "влезает" if п["влезает"] else "ОБРЕЗАНА"))
    if все_высоты:
        общий = max(все_высоты) - min(все_высоты)
        print("  ------------------------------------------------------------")
        print("  РАЗБЕГ МЕЖДУ РАЗДЕЛАМИ: %.1f px  (мин %.1f, макс %.1f)"
              % (общий, min(все_высоты), max(все_высоты)))
    return все_высоты


def главная():
    ширины = ШИРИНЫ
    if "--ширина" in sys.argv:
        ширины = [int(sys.argv[sys.argv.index("--ширина") + 1])]
    контроль = "--контроль" in sys.argv

    подлог = ПОДЛОГ if контроль else None
    if контроль:
        print("КОНТРОЛЬ: подлог занижает высоту ПОЛЯ ПОИСКА на 4 px.")
        print("Мерка обязана назвать это ростом разбега ВНУТРИ раздела.\n")

    сводка = {}
    for ш in ширины:
        снимок = _снять(ш, сенсор=(ш < 640), подлог=подлог)
        сводка[ш] = _печать(ш, снимок)
        док = снимок.get("__док__")
        if док:
            print("  ДОКАЗАТЕЛЬСТВО (%s): %s" % док)

    if контроль:
        print("\n" + "=" * 74)
        print("Сравните разбег с чистым прогоном: `py check_admin_bar.py`.")
        print("Не вырос — мерка слепа, и её числам веры нет.")
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(главная())
