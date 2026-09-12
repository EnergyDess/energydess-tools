# -*- coding: utf-8 -*-
"""ПОДВАЛ РАЗДЕЛА «ПОЛЬЗОВАТЕЛИ»: высота, строки, подложка, полоска.

ЗАЧЕМ ОТДЕЛЬНО ОТ `check_admin_bar`. Та мерит ПОЛОСУ ОТБОРА над
таблицей — высоты органов. Здесь другой вопрос: под таблицей слиплись
ДВА разных куска (подсказка к таблице и расход чужого справочника),
и ни один инструмент проекта не спрашивал ни высоту подвала, ни число
строк текста в нём.

МЕРИТ ВИДИМОЕ, А НЕ ВНУТРЕННЕЕ: число строк считается не по длине
строки в исходнике, а делением фактической высоты блока текста
на межстрочный интервал — то есть так, как их видит человек.

ГОЛОВНОЙ БРАУЗЕР (§6.0.3): ширина подвала считается от контейнера
страницы, headless прячет полосу прокрутки без изъятия места.

МЕРКА, код возврата 0 (кроме `--контроль`).

    py check_admin_foot.py
    py check_admin_foot.py --ширина 1920
    py check_admin_foot.py --контроль   # подлог: полоска расхода мертва
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DB_PATH", "app.db")

import check_hover as ch     # noqa: E402
import probe_guard  # noqa: F401

sys.stdout.reconfigure(encoding="utf-8")

БАЗА = os.environ.get("STAND", "http://127.0.0.1:8899")
ШИРИНЫ = [2560, 1920, 390]

# ПОДЛОГ ЛОМАЕТ ЗВЕНО, КОТОРОЕ ПРОВЕРЯЕТСЯ: мерка спрашивает, меняет ли
# полоска расхода ширину заливки по доле. Подлог фиксирует её на нуле —
# полоска остаётся в дереве, а сказать ей нечего.
ПОДЛОГ = """
(() => {
  addEventListener('DOMContentLoaded', () => {
    const s = document.createElement('style');
    s.textContent = '.ref-meter .meter-fill { width: 0 !important; }';
    document.head.appendChild(s);
  });
})();
"""

# ── ДОКАЗАТЕЛЬСТВО ПОДЛОГА (§6.0.3) ─────────────────────────────────
#
# Подлог гасит ЗАЛИВКУ полоски. «Доля стала нулём» — это вердикт самой
# мерки, и повторять его значило бы доказывать вердикт вердиктом.
# Независимый замер спрашивает ДРУГОЕ: жива ли сама дорожка. Полоска
# шириной 0 при дорожке шириной 0 — это не погашенная заливка,
# а схлопнувшийся блок, и различить эти два случая может только
# замер коробки.
ДОКАЗАТЕЛЬСТВА = {
    "полоска расхода мертва": (
        """() => {
          const d = document.querySelector('.ref-meter');
          const f = document.querySelector('.ref-meter .meter-fill');
          if (!d) return 'дорожки .ref-meter нет';
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

  // СТРОКИ СЧИТАЮТСЯ ПО ВЫСОТЕ, А НЕ ПО ТЕКСТУ: перенос делает браузер,
  // и в исходнике его не видно вовсе. Межстрочный берётся у самого
  // элемента; `normal` разрешается через кегль (Chrome даёт ~1.2).
  const строк = e => {
    if (!e) return null;
    const s = getComputedStyle(e);
    let lh = parseFloat(s.lineHeight);
    if (!isFinite(lh)) lh = parseFloat(s.fontSize) * 1.2;
    // Высота ТЕКСТА, а не коробки: у блока бывают свои паддинги.
    const r = document.createRange();
    r.selectNodeContents(e);
    const rs = [...r.getClientRects()];
    const h = rs.length ? Math.max(...rs.map(x => x.bottom))
                        - Math.min(...rs.map(x => x.top)) : 0;
    return {строк: Math.max(1, Math.round(h / lh)),
            высота_текста: +h.toFixed(1), межстрочный: +lh.toFixed(1)};
  };

  const подвал = document.querySelector('.admin-foot');
  const нота = document.getElementById('note');
  const реф = document.querySelector('.admin-foot-ref')
            || document.getElementById('ref-note');
  const полоска = document.querySelector('.ref-meter .meter-fill');
  const мет = document.querySelector('.ref-meter');
  const sp = подвал ? getComputedStyle(подвал) : null;

  return {
    экран: document.body.clientWidth,
    подвал: кор(подвал),
    фон: sp && sp.backgroundColor,
    рамка: sp && (sp.borderTopWidth + ' ' + sp.borderTopColor),
    радиус: sp && sp.borderTopLeftRadius,
    нота: кор(нота), нота_строк: строк(нота),
    нота_текст: нота ? нота.textContent.trim() : null,
    реф: кор(реф), реф_строк: строк(реф),
    реф_текст: реф ? реф.textContent.replace(/\s+/g, ' ').trim() : null,
    // ПОЛОСКА: доля заливки — ВИДИМАЯ ширина против коробки, а не
    // значение атрибута. Атрибут может стоять и не рисоваться.
    тон: реф ? реф.className.replace(/\s+/g, ' ').trim() : null,
    полоска: полоска ? {
      ширина: +полоска.getBoundingClientRect().width.toFixed(1),
      коробка: +мет.getBoundingClientRect().width.toFixed(1),
      доля: +(полоска.getBoundingClientRect().width
              / Math.max(1, мет.getBoundingClientRect().width)).toFixed(3),
      цвет: getComputedStyle(полоска).backgroundColor,
    } : null,
    // Порядок: подсказка обязана стоять ЛЕВЕЕ расхода на десктопе.
    столбиком: sp && sp.flexDirection === 'column',
    // Моноширинные числа в подсказке — есть ли носители.
    моно: [...document.querySelectorAll('.admin-foot .mono, .admin-foot b')]
            .map(e => e.textContent.trim()).slice(0, 8),
  };
}
"""


def _снять(ширина, подлог=None):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        бр = p.chromium.launch(headless=False)
        кон = бр.new_context(viewport={"width": ширина, "height": 900},
                             has_touch=(ширина < 640), is_mobile=False,
                             device_scale_factor=1)
        стр = кон.new_page()
        ch._войти(стр)
        if подлог:
            стр.add_init_script(подлог)
        стр.goto(f"{БАЗА}/admin/users", wait_until="load", timeout=45000)
        стр.wait_for_timeout(500)
        о = стр.evaluate(ЗАМЕР)
        бр.close()
    return о


def _печать(ширина, о):
    print("\n" + "=" * 74)
    print("ШИРИНА %d" % ширина)
    print("=" * 74)
    if не_подвал := (not о.get("подвал")):
        print("  общего подвала `.admin-foot` НЕТ — куски лежат врозь")
    else:
        п = о["подвал"]
        print("  подвал h=%.1f  фон=%s  рамка=%s  радиус=%s"
              % (п["h"], о["фон"], о["рамка"], о["радиус"]))
    for имя, ключ, ткл in (("подсказка", "нота", "нота_строк"),
                           ("расход", "реф", "реф_строк")):
        к, с = о.get(ключ), о.get(ткл)
        if not к:
            print("  %-10s блока НЕТ" % имя)
            continue
        print("  %-10s h=%.1f  строк ВИДНО: %s  (текст %.1f / межстрочный %.1f)"
              % (имя, к["h"], с["строк"], с["высота_текста"], с["межстрочный"]))
    if о.get("полоска"):
        л = о["полоска"]
        print("  полоска расхода: доля %.3f (%.1f из %.1f), цвет %s"
              % (л["доля"], л["ширина"], л["коробка"], л["цвет"]))
    else:
        print("  полоски расхода НЕТ")
    if о.get("тон"):
        print("  класс расхода: %s" % о["тон"])
    if о.get("моно"):
        print("  моноширинные числа: %s" % ", ".join(о["моно"]))
    if не_подвал and о.get("нота") and о.get("реф"):
        print("  ОБЩАЯ ВЫСОТА ДВУХ КУСКОВ: %.1f px"
              % (о["реф"]["y"] + о["реф"]["h"] - о["нота"]["y"]))
    return о


# ── ТОНА ПОЛОСКИ: три порога — три КЛАССА и три ЦВЕТА ────────────────
# Класс ставит СЕРВЕР по доле, значит подстановкой в страницу его
# не проверить: пришлось бы подменить ровно то, что проверяется.
# Меняется число В БАЗЕ СТЕНДА (боевую проба не открывает вовсе)
# и возвращается в `finally` — при обрыве тоже.
ДОЛИ = [("обычный", 0.30), ("предупреждение", 0.75), ("красный", 0.95),
        ("исчерпан", 1.00)]


def _тона():
    import datetime
    import sqlite3
    путь = os.environ.get("DB_PATH", "app.db")
    if "/data/" in путь.replace("\\", "/"):
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
            о = _снять(1920)
            л = о.get("полоска") or {}
            print("  %-14s %5d из %d (%.0f%%)  класс=%-28s цвет=%s  доля=%.3f"
                  % (имя, n, предел, доля * 100,
                     (о.get("тон") or "").replace("admin-foot-ref", "").strip()
                     or "(без модификатора)",
                     л.get("цвет"), л.get("доля", 0)))
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


def главная():
    ширины = ШИРИНЫ
    if "--ширина" in sys.argv:
        ширины = [int(sys.argv[sys.argv.index("--ширина") + 1])]
    if "--тона" in sys.argv:
        return _тона()
    контроль = "--контроль" in sys.argv
    if контроль:
        print("КОНТРОЛЬ: подлог обнуляет ЗАЛИВКУ полоски расхода.")
        print("Мерка обязана назвать долю нулём, а не промолчать.\n")
    for ш in ширины:
        _печать(ш, _снять(ш, ПОДЛОГ if контроль else None))
    if контроль:
        print("\nСравните долю с чистым прогоном: `py check_admin_foot.py`.")
    return 0


if __name__ == "__main__":
    sys.exit(главная())
