"""ПРОВЕРКА 59: ВКЛАДКА «ИСТОРИЯ» ДНЕВНИКА (№352, «питание-3», блок 3).

ПРОВЕРКА, код 1 при находке, 2 — замерить нечем (стенда нет, календаря нет).

Правило владельца — то же, что у ленты дней (проверка 55), теперь на клетке
календаря месяца:
  · выбранный день ЗАЛИТ цветом питания, НАСТОЯЩАЯ мышь на нём вида
    не меняет;
  · «сегодня» при выбранном другом дне — цифра цвета питания, без заливки;
  · будущие дни читаются: контраст цифры к фону ≥ 4.5 (цвет с прозрачностью
    всей цепочки предков);
  · у дня с записями видна точка;
  · зона наведения — кружок: мышь в углу клетки вне кружка его не красит;
  · на 390 календарь без прокрутки вбок.
ПРОГОН: день с записями в пределах недели → сводка слева совпадает
с `/nutrition/api/diary` за этот день → «Открыть в дневнике» открывает
вкладку «Дневник» на ЭТОМ дне (лента дней выделяет его, загружены его
числа). День дальше недели — кнопки нет, стоит строка почему.

Браузер невидимый (вопрос не про ширину полосы прокрутки, §6.0.3), кроме
замера 390 — там спрашивается прокрутка вбок, и окно видимое. В базу
НЕ ПИШЕТ: выбор дня живёт в странице.

КЛЮЧИ:
  --контроль  пять подлогов, каждый обязан уронить СВОЮ строку.
"""
import os
import sys

try:
    import probe_guard  # noqa: F401  ПРОПУСК вместо трассы (§6.0.1)
except ImportError:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_hover as ch  # noqa: E402
import check_nutrition_weight as cw  # noqa: E402  разбор цвета канвой — один

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

КЛЕТКИ = "() => {" + cw.ЦВЕТ + r"""
  return [...document.querySelectorAll('#cal-grid .cal-c:not(.is-pad)')].map(c => {
    const n = c.querySelector('.cal-n'), st = getComputedStyle(n), т = c.querySelector('.ds-dot');
    return {дата: c.dataset.date, классы: c.className, фон: st.backgroundColor,
      цвет: st.color, к_цифры: против(n, st.color),
      точка: !!т && т.checkVisibility({opacityProperty: true}) && getComputedStyle(т).backgroundColor !== 'rgba(0, 0, 0, 0)',
      записи: !!(S.calData.days[c.dataset.date])};
  });
}"""

ВИД = """(д) => { const n = document.querySelector('#cal-grid .cal-c[data-date="' + д + '"] .cal-n');
  const s = getComputedStyle(n); return [s.backgroundColor, s.borderTopColor, s.color].join('|'); }"""

КОРОБКИ = """(д) => { const c = document.querySelector('#cal-grid .cal-c[data-date="' + д + '"]');
  const a = c.getBoundingClientRect(), b = c.querySelector('.cal-n').getBoundingClientRect();
  return {кл: [a.left, a.top, a.right, a.bottom], кр: [b.left, b.top, b.right, b.bottom]}; }"""

ГЛУШИТЕЛЬ = cw.ГЛУШИТЕЛЬ
_стиль = cw._стиль


def _открыть(стр):
    стр.goto(ch.БАЗА + "/nutrition", wait_until="networkidle", timeout=45000)
    стр.evaluate("() => document.querySelector('.v2-tab[data-tab=history]').click()")
    стр.wait_for_selector("#cal-grid .cal-c:not(.is-pad)", timeout=15000)
    стр.wait_for_timeout(900)


def замер(подлог=None):
    from playwright.sync_api import sync_playwright
    import browser_window  # noqa: F401
    и = {}
    with sync_playwright() as p:
        бр = p.chromium.launch(headless=True)
        try:
            ctx = бр.new_context(viewport={"width": 1600, "height": 900})
            стр = ctx.new_page()
            стр.add_init_script(ГЛУШИТЕЛЬ)
            if подлог:
                стр.add_init_script(подлог)
            ch._войти(стр)
            _открыть(стр)
            сегодня = стр.evaluate("() => S.today")
            кл = стр.evaluate(КЛЕТКИ)
            if not кл:
                return None
            # день с записями в пределах недели назад, не сегодня
            кандидаты = [к["дата"] for к in кл if к["записи"] and к["дата"] < сегодня
                         and стр.evaluate("(д) => вОкнеДневника(д)", к["дата"])]
            дальний = [к["дата"] for к in кл if к["записи"] and не_в_окне(стр, к["дата"])]
            и["будущие"] = [к for к in кл if "is-fut" in к["классы"]]
            и["с_записями"] = [к for к in кл if к["записи"]]
            if not кандидаты:
                return и
            день = кандидаты[-1]
            # зона наведения: мышь в угол клетки (вне кружка) не красит кружок
            к = стр.evaluate(КОРОБКИ, день)
            покой = стр.evaluate(ВИД, день)
            стр.mouse.move(к["кл"][0] + 1, к["кл"][3] - 1)
            стр.wait_for_timeout(200)
            и["угол"] = стр.evaluate(ВИД, день) == покой
            кр = к["кр"]
            стр.mouse.move((кр[0] + кр[2]) / 2, (кр[1] + кр[3]) / 2)
            стр.wait_for_timeout(200)
            и["кружок_реагирует"] = стр.evaluate(ВИД, день) != покой
            # клик по дню: мышь остаётся на нём
            стр.mouse.click((кр[0] + кр[2]) / 2, (кр[1] + кр[3]) / 2)
            стр.wait_for_timeout(1200)
            под_мышью = стр.evaluate(ВИД, день)
            стр.mouse.move(2, 2)
            стр.wait_for_timeout(250)
            без_мыши = стр.evaluate(ВИД, день)
            после = {x["дата"]: x for x in стр.evaluate(КЛЕТКИ)}
            и["выбранный"] = после[день]
            и["наведение_не_меняет"] = под_мышью == без_мыши
            и["сегодня_при_другом"] = после.get(сегодня)
            и["цвет_питания"] = стр.evaluate("() => getComputedStyle(document.body).getPropertyValue('--v2-tool').trim()")
            # сводка против сервера
            и["сводка"] = стр.evaluate("() => document.getElementById('hist-kcal').textContent.trim()")
            api = стр.evaluate("(д) => fetch('/nutrition/api/diary?date=' + д).then(r => r.json())", день)
            и["api"] = str(round((api.get("totals") or {}).get("calories") or 0))
            и["кнопка_видна"] = стр.evaluate("() => !document.getElementById('hd-open').hidden && document.getElementById('hd-open').checkVisibility()")
            # «Открыть в дневнике»
            стр.evaluate("() => document.getElementById('hd-open').click()")
            стр.wait_for_timeout(1500)
            и["дневник"] = стр.evaluate("""() => ({вкладка: S.activeTab, дата: S.date,
                выбрана_в_ленте: (document.querySelector('#ds-days .ds-day.is-sel') || {}).dataset?.date || null,
                ккал: String(Math.round((S.diary && S.diary.totals && S.diary.totals.calories) || 0))})""")
            и["день"] = день
            # дальний день
            if дальний:
                _открыть(стр)
                стр.evaluate("(д) => histSelect(д)", дальний[0])
                стр.wait_for_timeout(1200)
                и["дальний"] = стр.evaluate("""() => ({кнопка: !document.getElementById('hd-open').hidden,
                    строка: !document.getElementById('hd-open-note').hidden})""")
            ctx.close()
        finally:
            бр.close()
        # 390: прокрутка вбок — видимым окном
        бр = p.chromium.launch(headless=False)
        try:
            ctx = бр.new_context(viewport={"width": 390, "height": 900}, has_touch=True)
            стр = ctx.new_page()
            стр.add_init_script(ГЛУШИТЕЛЬ)
            if подлог:
                стр.add_init_script(подлог)
            ch._войти(стр)
            _открыть(стр)
            и["390"] = стр.evaluate("""() => { const c = document.querySelector('#tab-history .cal');
                return {док: document.documentElement.scrollWidth - document.documentElement.clientWidth,
                        кал: c.scrollWidth - c.clientWidth,
                        край: Math.max(...[...document.querySelectorAll('#cal-grid .cal-n')].map(n => n.getBoundingClientRect().right)) - c.getBoundingClientRect().right}; }""")
            ctx.close()
        finally:
            бр.close()
    return и


def не_в_окне(стр, д):
    return стр.evaluate("(д) => !вОкнеДневника(д)", д)


_строки = {}


def шаг(имя, условие, подробность="", собрано=None):
    if собрано is not None and собрано == 0:
        исход = "ПРОПУСК"
    else:
        исход = "ok" if условие else "ПЛОХО"
    _строки[имя] = исход
    print("  %-8s %s%s" % (исход, имя, (" — " + подробность) if подробность else ""))


def _прозрачный(c):
    return c in ("rgba(0, 0, 0, 0)", "transparent")


def проверка(подлог=None):
    _строки.clear()
    и = замер(подлог)
    if и is None:
        print("  ПРОПУСК  календаря нет")
        return 0, 1
    буд = и.get("будущие", [])
    шаг("будущие-контраст-4.5", all(к["к_цифры"] >= 4.5 for к in буд),
        "худший %.2f" % min((к["к_цифры"] for к in буд), default=0), собрано=len(буд))
    зап = и.get("с_записями", [])
    шаг("точка-у-дней-с-записями", all(к["точка"] for к in зап), "дней %d" % len(зап), собрано=len(зап))
    if "день" not in и:
        шаг("прогон-дня", False, "на стенде нет дня с записями в пределах недели", собрано=0)
        return 0, 1
    в = и["выбранный"]
    шаг("выбранный-залит", not _прозрачный(в["фон"]), "фон %s" % в["фон"])
    шаг("наведение-не-меняет-выбранный", и["наведение_не_меняет"])
    с = и["сегодня_при_другом"]
    шаг("сегодня-без-заливки-цвета-питания", bool(с) and _прозрачный(с["фон"]) and с["цвет"] != в["цвет"],
        "фон %s, цифра %s" % (с and с["фон"], с and с["цвет"]))
    шаг("зона-наведения-кружок", и["угол"] and и["кружок_реагирует"],
        "угол клетки не красит %s, кружок реагирует %s" % (и["угол"], и["кружок_реагирует"]))
    шаг("сводка-равна-дневнику-за-день", и["сводка"] == и["api"] == и["дневник"]["ккал"],
        "история %s, сервер %s, дневник %s" % (и["сводка"], и["api"], и["дневник"]["ккал"]))
    д = и["дневник"]
    шаг("открыть-в-дневнике-этот-день", и["кнопка_видна"] and д["вкладка"] == "diary" and д["дата"] == и["день"]
        and д["выбрана_в_ленте"] == и["день"], "день %s → вкладка %s, дата %s, лента %s"
        % (и["день"], д["вкладка"], д["дата"], д["выбрана_в_ленте"]))
    дл = и.get("дальний")
    шаг("дальний-день-без-кнопки-со-строкой", bool(дл) and not дл["кнопка"] and дл["строка"],
        str(дл), собрано=1 if дл else 0)
    м = и["390"]
    шаг("390-без-прокрутки-вбок", м["док"] <= 0 and м["кал"] <= 0 and м["край"] <= 0, str(м))
    return sum(v == "ПЛОХО" for v in _строки.values()), sum(v == "ПРОПУСК" for v in _строки.values())


ПОДЛОГИ = [
    ("наведение перебивает выбранный", "наведение-не-меняет-выбранный",
     _стиль("#cal-grid .cal-c.is-sel .cal-n:hover { background: transparent !important; }")),
    ("зона наведения — вся клетка", "зона-наведения-кружок",
     _стиль("#cal-grid .cal-c:not(.is-sel):hover .cal-n { background: rgb(40, 80, 60) !important; }")),
    ("будущие прозрачностью 0.35", "будущие-контраст-4.5",
     _стиль("#cal-grid .cal-c.is-fut { opacity: .35 !important; }")),
    ("точки нет", "точка-у-дней-с-записями",
     _стиль("#cal-grid .ds-dot { display: none !important; }")),
    ("«Открыть в дневнике» сбрасывает на сегодня", "открыть-в-дневнике-этот-день",
     "addEventListener('DOMContentLoaded', () => { window.открытьВДневнике = () => перейтиНаВкладку('diary'); });"),
]


def контроль():
    print("ЧИСТЫЙ ПРОГОН")
    н, п = проверка()
    if н or п:
        print("КОНТРОЛЬ НЕДЕЙСТВИТЕЛЕН: грязная основа (находок %d, пропусков %d)" % (н, п))
        return 2
    не_найдено = 0
    for имя, строка, код in ПОДЛОГИ:
        print("ПОДЛОГ: %s" % имя)
        проверка(код)
        упала = _строки.get(строка) == "ПЛОХО"
        print("  → %s строку «%s»" % ("НАЙДЕН, уронил" if упала else "НЕ НАЙДЕН", строка))
        не_найдено += not упала
    print("КОНТРОЛЬ: подлогов %d, не найдено %d" % (len(ПОДЛОГИ), не_найдено))
    return 1 if не_найдено else 0


def main():
    if "--контроль" in sys.argv:
        sys.exit(контроль())
    print("ВКЛАДКА «ИСТОРИЯ»")
    н, п = проверка()
    print("ИТОГ: находок %d, пропусков %d" % (н, п))
    sys.exit(1 if н else (2 if п else 0))


if __name__ == "__main__":
    main()
