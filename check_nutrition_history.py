"""ПРОВЕРКА 59: ВКЛАДКА «ИСТОРИЯ» ДНЕВНИКА (№352, «питание-3», блок 3).

ПРОВЕРКА, код 1 при находке, 2 — замерить нечем (стенда нет, календаря нет).

Правило владельца — то же, что у ленты дней (проверка 55), теперь на клетке
календаря месяца:
  · выбранный день ЗАЛИТ цветом питания, НАСТОЯЩАЯ мышь на нём вида
    не меняет;
  · «сегодня» при выбранном другом дне — цифра цвета питания, без заливки;
  · будущие дни читаются: контраст цифры к фону ≥ 4.5 (цвет с прозрачностью
    всей цепочки предков);
  · вокруг числа — КОЛЬЦО ДОЛИ НОРМЫ («питание-4», блок 1): доля в кольце
    совпадает с сервером и со сводкой дня (дни 40 / 100 / 125 %), до 110 %
    кольцо цветом питания, больше — оранжевым (`--v2-warn`), день без
    записей — нейтральная подложка; точки под числом нет;
  · вкладка открывается на ТЕКУЩЕМ месяце, даже если до этого листали;
  · месяц и год — списки со стрелкой, отвечают на наведение и клавиатуру;
  · снятых текстов («Точка — в дне есть записи…», «Считаем по N дням…»,
    «Норма за этот день не записана…», «Дневник открывает дни в пределах
    недели…») на вкладке нет ни в одном состоянии;
  · зона наведения — кружок: мышь в углу клетки вне кружка его не красит;
  · на 390 календарь без прокрутки вбок.
ПРОГОН: день с записями в пределах недели → сводка слева совпадает
с `/nutrition/api/diary` за этот день → «Открыть в дневнике» открывает
вкладку «Дневник» на ЭТОМ дне (лента дней выделяет его, загружены его
числа). День дальше недели — кнопки нет (и строки «почему» нет).

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
    const n = c.querySelector('.cal-n'), st = getComputedStyle(n), к = c.querySelector('.cal-ring');
    const кs = к ? getComputedStyle(к) : null;
    return {дата: c.dataset.date, классы: c.className, фон: st.backgroundColor,
      цвет: st.color, к_цифры: против(n, st.color),
      кольцо: к ? к.dataset.ring : null, доля: кs ? parseFloat(кs.getPropertyValue('--p')) : null,
      цвет_кольца: кs ? кs.getPropertyValue('--cal-ring-c').trim() : null,
      точка: !!c.querySelector('.ds-dot'),
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
            и["кольца"] = кольца(стр, кл)
            и["тексты"] = [стр.evaluate(ТЕКСТ)]
            и["списки"] = списки(стр)
            и["месяц"] = месяц_при_открытии(стр)
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
                и["дальний"] = стр.evaluate("""() => ({кнопка: !document.getElementById('hd-open').hidden
                    && document.getElementById('hd-open').checkVisibility()})""")
                и["тексты"].append(стр.evaluate(ТЕКСТ))
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


ТЕКСТ = "() => document.getElementById('tab-history').innerText"
СНЯТЫЕ = ["Точка — в дне есть записи", "Считаем по", "своя норма не записана",
          "Норма за этот день не записана", "в пределах недели от сегодня"]


def кольца(стр, кл):
    """Дни 40 / 100 / 125 % — по данным СЕРВЕРА; их кольца и сводка дня."""
    import re
    сервер = стр.evaluate("() => fetch('/nutrition/api/history/month?month=' + S.calMonth).then(r => r.json())")
    варн = стр.evaluate("() => getComputedStyle(document.body).getPropertyValue('--v2-warn').trim()")
    по_дате = {к["дата"] for к in кл}
    итог = {"варн": варн, "дни": {}}
    for цель_доли in (0.40, 1.00, 1.25):
        лучшие = [(abs(д["calories"] / д["goal"] - цель_доли), дата, д)
                  for дата, д in сервер["days"].items() if д.get("goal") and дата in по_дате]
        if not лучшие:
            continue
        откл, дата, д = min(лучшие)
        if откл > 0.02:
            continue
        стр.evaluate("(д) => histSelect(д)", дата)
        стр.wait_for_timeout(1000)
        подпись = стр.evaluate("() => document.getElementById('h-date-lbl').textContent")
        м = re.search(r"(\d+)% от нормы", подпись)
        к = {x["дата"]: x for x in стр.evaluate(КЛЕТКИ)}[дата]
        итог["дни"][цель_доли] = {"дата": дата, "сервер": round(д["calories"] / д["goal"] * 100),
                                  "сводка": int(м.group(1)) if м else None,
                                  "кольцо": к["кольцо"], "p": к["доля"], "цвет": к["цвет_кольца"]}
    пустые = [к for к in кл if not к["записи"]]
    итог["пустой"] = пустые[0] if пустые else None
    итог["точек"] = sum(1 for к in кл if к["точка"])
    return итог


def списки(стр):
    """Месяц и год: стрелка, форма пилюли, отклик на наведение, клавиатура."""
    и = стр.evaluate("""() => { const s = document.getElementById('cal-month'),
        a = getComputedStyle(s.parentElement, '::after');
        return {стрелка: a.content !== 'none' && parseFloat(a.borderRightWidth) > 0,
                радиус: parseFloat(getComputedStyle(s).borderTopLeftRadius)}; }""")
    стр.mouse.move(2, 2)
    стр.wait_for_timeout(200)
    покой = стр.evaluate("() => getComputedStyle(document.getElementById('cal-month')).backgroundColor")
    стр.locator("#cal-month").hover()
    стр.wait_for_timeout(250)
    и["наведение"] = стр.evaluate(
        "() => getComputedStyle(document.getElementById('cal-month')).backgroundColor") != покой
    было = стр.evaluate("() => S.calMonth")
    стр.locator("#cal-month").focus()
    стр.keyboard.press("ArrowUp")
    стр.wait_for_timeout(1200)
    и["клавиатура"] = стр.evaluate("() => S.calMonth") != было
    стр.evaluate("() => { S.calMonth = S.today.slice(0, 7); return loadCalendar(); }")
    стр.mouse.move(2, 2)
    стр.wait_for_timeout(800)
    return и


def месяц_при_открытии(стр):
    """Отлистать назад, уйти на «Дневник», вернуться — открыт текущий месяц."""
    стр.evaluate("() => calShift(-1)")
    стр.wait_for_timeout(900)
    отлистан = стр.evaluate("() => S.calMonth")
    стр.evaluate("() => document.querySelector('.v2-tab[data-tab=diary]').click()")
    стр.wait_for_timeout(700)
    стр.evaluate("() => document.querySelector('.v2-tab[data-tab=history]').click()")
    стр.wait_for_timeout(1200)
    итог = {"отлистан": отлистан, "открыт": стр.evaluate("() => S.calMonth"),
            "сегодня": стр.evaluate("() => S.today")}
    # Дальше проба ходит по дням ТЕКУЩЕГО месяца — возвращает его сама,
    # иначе подлог этой строки ронял бы прогон на соседних
    стр.evaluate("() => { S.calMonth = S.today.slice(0, 7); return loadCalendar(); }")
    стр.wait_for_timeout(800)
    return итог


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
    ко = и.get("кольца") or {"дни": {}}
    дни = ко["дни"]
    полно = len(дни) if len(дни) == 3 else 0
    шаг("доля-в-кольце-равна-серверу-и-сводке",
        all(round(д["p"] * 100) == min(д["сервер"], 100) and д["сводка"] == д["сервер"] for д in дни.values()),
        "; ".join("%s: сервер %s%%, сводка %s%%, кольцо p=%.2f" % (д["дата"], д["сервер"], д["сводка"], д["p"])
                  for д in дни.values()), собрано=полно)
    шаг("кольцо-по-порогу-110",
        all(д["кольцо"] == ("over" if ц > 1.10 else "part") for ц, д in дни.items())
        and 1.25 in дни and дни[1.25]["цвет"].lower() == ко.get("варн", "").lower(),
        ", ".join("%d%% → %s %s" % (round(ц * 100), д["кольцо"], д["цвет"]) for ц, д in дни.items()),
        собрано=полно)
    п = ко.get("пустой")
    шаг("без-записей-нейтральное-кольцо", bool(п) and п["кольцо"] == "none", str(п and п["кольцо"]),
        собрано=1 if п else 0)
    шаг("точки-под-числом-нет", ко.get("точек", 1) == 0, "точек %s" % ко.get("точек"))
    мс = и.get("месяц") or {}
    шаг("открывается-текущий-месяц", мс.get("открыт") == (мс.get("сегодня") or "")[:7]
        and мс.get("отлистан") != мс.get("открыт"), str(мс))
    сп = и.get("списки") or {}
    шаг("списки-стрелка-наведение-клавиатура", bool(сп.get("стрелка") and сп.get("наведение")
        and сп.get("клавиатура") and сп.get("радиус", 0) >= 16), str(сп))
    тексты = и.get("тексты") or []
    найдено = sorted({ф for ф in СНЯТЫЕ for т in тексты if ф in т})
    шаг("снятых-текстов-нет", not найдено, "состояний %d, найдено %s" % (len(тексты), найдено or 0),
        собрано=len(тексты))
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
    шаг("дальний-день-без-кнопки", bool(дл) and not дл["кнопка"],
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
    ("порог 110% сломан — оранжевый с 100%", "кольцо-по-порогу-110",
     "addEventListener('DOMContentLoaded', () => { window.кольцоДня = з => { const ц = з && з.goal;"
     " if (!ц) return {вид: 'none', заливка: 0, доля: null}; const д = з.calories / ц;"
     " return д >= 0.99 ? {вид: 'over', заливка: 1, доля: д}"
     " : {вид: 'part', заливка: д.toFixed(3), доля: д}; }; });"),
    ("доля от неверной нормы", "доля-в-кольце-равна-серверу-и-сводке",
     "addEventListener('DOMContentLoaded', () => { window.кольцоДня = з => { const ц = з && з.goal * 1.2;"
     " if (!ц) return {вид: 'none', заливка: 0, доля: null}; const д = з.calories / ц;"
     " return д > 1.1 ? {вид: 'over', заливка: 1, доля: д}"
     " : {вид: 'part', заливка: Math.min(д, 1).toFixed(3), доля: д}; }; });"),
    ("открывается месяц последней просмотренной записи", "открывается-текущий-месяц",
     "addEventListener('DOMContentLoaded', () => { window.месяцПриОткрытии = () => S.calMonth; });"),
    ("снятый текст вернулся", "снятых-текстов-нет",
     "addEventListener('DOMContentLoaded', () => { const о = window.renderMonthSummary;"
     " window.renderMonthSummary = () => { о(); document.getElementById('mo-basis').textContent"
     " += ' · Считаем по 17 дням'; }; });"),
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
