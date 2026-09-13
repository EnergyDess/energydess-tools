"""АКТИВНЫЙ ЭЛЕМЕНТ В ПРОКРУЧИВАЕМОЙ ЛЕНТЕ ВИДЕН (задача 326).

ПРОВЕРКА, код 1 при находке, 2 — замерить нечем.

ВОПРОС. Ряд вкладок или чипов на узкой ширине не помещается и листается
вбок. Открывается он с нулевой прокрутки — значит выбранный элемент,
стоящий правее окна, человек не видит, и не видит, в каком разделе стоит.
Замер 2026-09-13 (заход 325): вкладка Enshrouded на 390 — левый край 503
при окне 390, «Главная» — 662.

ЛЕНТА ВЫВОДИТСЯ, А НЕ ПЕРЕЧИСЛЯЕТСЯ. Берётся каждый ВИДИМЫЙ элемент
с признаком выбора (`.active`, `aria-current`, `aria-selected="true"`),
и от него вверх ищется ближайший предок с горизонтальной прокруткой,
которому действительно есть что прокручивать. Нашлась — спрашивается,
какая доля элемента видна в пределах ленты И окна. Меньше целого — находка.

СОСТОЯНИЯ, В КОТОРЫХ ВЫБРАН ДАЛЬНИЙ ЭЛЕМЕНТ, ТОЖЕ ВЫВОДЯТСЯ. У каждой
ленты берутся её элементы-ссылки, и каждая открывается: так проверяются
все пять разделов админки и все чипы-ссылки, а не только то, что
выбрано по умолчанию. Элементы-кнопки (вкладка окна) нажимаются,
окно закрывается и открывается заново — выбор обязан быть виден и тогда.

ГОЛОВНОЙ БРАУЗЕР, 390 с сенсором (§6.0.3): ширина ленты считается
от контейнера, а headless прячет полосу прокрутки без изъятия места.

КЛЮЧИ:
  --ширина N   ширина окна (по умолчанию 390)
  --контроль   подлог: механизм прокрутки к выбранному выключен в странице
               (init-скрипт снимает `прокрутитьКВыбранному`). Проба обязана
               назвать разделы поимённо. Доказательство независимо:
               scrollLeft ленты разделов на /admin/landing, 0 против > 0.
"""
import os
import sys

try:
    import probe_guard  # noqa: F401
except ImportError:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_hover as ch  # noqa: E402

ЗАМЕР = r"""() => {
  const имя = э => э.tagName.toLowerCase() + (э.id ? '#' + э.id : '') +
      [...э.classList].slice(0, 2).map(к => '.' + к).join('');
  const итог = [];
  const маркеры = '.active, [aria-current="page"], [aria-current="true"], [aria-selected="true"]';
  for (const эл of document.querySelectorAll(маркеры)) {
    if (!эл.checkVisibility({checkOpacity: true, checkVisibilityCSS: true})) continue;
    let п = эл.parentElement, лента = null;
    while (п && п !== document.documentElement) {
      const s = getComputedStyle(п);
      if ((s.overflowX === 'auto' || s.overflowX === 'scroll') && п.scrollWidth > п.clientWidth + 1) {
        лента = п; break;
      }
      п = п.parentElement;
    }
    if (!лента) continue;
    const r = эл.getBoundingClientRect(), л = лента.getBoundingClientRect();
    const лево = Math.max(r.left, л.left, 0), право = Math.min(r.right, л.right, innerWidth);
    const видно = Math.max(0, право - лево);
    const ссылки = [...лента.querySelectorAll('a[href]')]
        .map(а => а.href).filter(h => h.startsWith(location.origin));
    итог.push({лента: имя(лента), элемент: имя(эл), текст: (эл.innerText || '').trim().slice(0, 30),
               доля: r.width ? видно / r.width : 0, left: Math.round(r.left),
               right: Math.round(r.right), scrollLeft: Math.round(лента.scrollLeft),
               ссылки});
  }
  return итог;
}"""

# СЦЕНЫ СВЕРХ ОБЩЕГО СПИСКА. Окна «Общая аптечка» в `check_hover.СЦЕНЫ`
# нет, а у него своя лента вкладок. Добавить его туда значит расширить
# обход пяти чужих проверок — отдельное решение; здесь оно нужно одной.
СВОИ_СЦЕНЫ = [("/medkit", "аптечка · общая аптечка", True, "#apt-circle-open")]

ПОДЛОГ = """
Object.defineProperty(window, 'прокрутитьКВыбранному', {
  configurable: false, get() { return function () {}; }, set() {}
});
"""


def замерить(стр, адрес, где, находки, счёт, подготовка=None, ленты=None):
    стр.goto(адрес, wait_until="load", timeout=45000)
    if подготовка:
        try:
            стр.click(подготовка, timeout=8000)
        except Exception as e:
            print("  ПРОПУСК %-40s подготовка не нажалась: %s" % (где, type(e).__name__))
            return []
    стр.wait_for_timeout(900)
    замер = стр.evaluate(ЗАМЕР)
    for з in замер:
        счёт[0] += 1
        if ленты is not None:
            ленты.setdefault(з["лента"], set()).add(где)
        ок = з["доля"] >= 0.99
        if not ок:
            находки.append("%s · %s «%s» видно %.0f%% (left %s, right %s, scrollLeft %s)"
                           % (где, з["лента"], з["текст"], з["доля"] * 100,
                              з["left"], з["right"], з["scrollLeft"]))
    return замер


def прогон(ширина, подлог):
    from playwright.sync_api import sync_playwright
    экраны = ch.экраны_из_роутов() + СВОИ_СЦЕНЫ
    находки, счёт, обошли, ленты = [], [0], set(), {}
    with sync_playwright() as pw:
        бр = pw.chromium.launch(headless=False)
        кт = бр.new_context(viewport={"width": ширина, "height": 844},
                            has_touch=True, is_mobile=True, device_scale_factor=1)
        if подлог:
            кт.add_init_script(ПОДЛОГ)
        стр = кт.new_page()
        ch._войти(стр)
        доказательство = None
        for путь, имя, вход, подготовка in экраны:
            if not вход:
                continue
            адрес = ch.БАЗА + путь
            if not подготовка and адрес in обошли:
                continue
            замер = замерить(стр, адрес, имя, находки, счёт, подготовка, ленты)
            обошли.add(адрес)
            if подготовка:
                # Кнопки ленты внутри открытого окна: выбрать ПОСЛЕДНЮЮ,
                # закрыть окно, открыть заново — выбор обязан быть виден.
                кнопки = стр.evaluate(r"""() => {
                  const о = [...document.querySelectorAll('.modal-ov.open [role=tab], .modal-ov.open .tab-btn')]
                     .filter(э => э.checkVisibility());
                  return о.length;
                }""")
                if кнопки > 1:
                    стр.locator(".modal-ov.open [role=tab], .modal-ov.open .tab-btn").nth(кнопки - 1).click()
                    стр.wait_for_timeout(400)
                    стр.keyboard.press("Escape")
                    стр.wait_for_timeout(500)
                    стр.click(подготовка, timeout=8000)
                    стр.wait_for_timeout(900)
                    for з in стр.evaluate(ЗАМЕР):
                        счёт[0] += 1
                        ленты.setdefault(з["лента"], set()).add(имя + " (последняя вкладка)")
                        if з["доля"] < 0.99:
                            находки.append("%s (последняя вкладка, окно заново) · %s «%s» видно %.0f%%"
                                           % (имя, з["лента"], з["текст"], з["доля"] * 100))
            for з in замер:
                for ссылка in з["ссылки"]:
                    if ссылка in обошли:
                        continue
                    обошли.add(ссылка)
                    замерить(стр, ссылка, ссылка.replace(ch.БАЗА, ""), находки, счёт,
                             ленты=ленты)
        # ДОКАЗАТЕЛЬСТВО НЕЗАВИСИМО ОТ ВЕРДИКТА: прокрутка ряда разделов на
        # последнем разделе. Без механизма она 0 при любом числе находок.
        стр.goto(ch.БАЗА + "/admin/landing", wait_until="load")
        стр.wait_for_timeout(500)
        доказательство = стр.evaluate("() => document.querySelector('.admin-tabs').scrollLeft")
        бр.close()
    return находки, счёт[0], доказательство, ленты


def main():
    ширина = 390
    if "--ширина" in sys.argv:
        ширина = int(sys.argv[sys.argv.index("--ширина") + 1])
    подлог = "--контроль" in sys.argv
    находки, всего, док, ленты = прогон(ширина, подлог)
    print("ширина %d, выбранных элементов в прокручиваемых лентах замерено: %d"
          % (ширина, всего))
    print("прокручиваемых лент с выбранным элементом: %d" % len(ленты))
    for л, где in sorted(ленты.items()):
        print("  %-34s экранов %d: %s" % (л, len(где), ", ".join(sorted(где))[:150]))
    print("доказательство: scrollLeft ряда разделов на /admin/landing = %s" % док)
    for н in находки:
        print("  НЕ ВИДНО  " + н)
    if всего == 0:
        print("ПРОПУСК: ни одной прокручиваемой ленты с выбранным элементом — замерить нечем")
        return 2
    print("ИТОГ: %s" % ("чисто" if not находки else "находок %d" % len(находки)))
    if подлог:
        найден = bool(находки) and (док == 0)
        print("КОНТРОЛЬ: %s" % ("НАЙДЕН" if найден else "НЕ НАЙДЕН"))
        return 0 if найден else 1
    return 1 if находки else 0


if __name__ == "__main__":
    sys.exit(main())
