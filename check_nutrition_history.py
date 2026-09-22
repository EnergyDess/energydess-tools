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
  · на 390 календарь без прокрутки вбок;
  · ВСЕ КЛЕТКИ МЕСЯЦА, а не выборка («питание-5», блок 1): июнь и сентябрь
    2026 (месяц с понедельника и со вторника), данные стенда и выдуманный
    месяц поверх (в каждой колонке и пустые дни, и дни с записями).
    Пустой день — ноль пикселей цвета питания и `--v2-warn` в полосе
    кольца; день с записями — угол дуги равен доле с сервера ±3 %,
    больше 110 % — оранжевое без зелёного. Прежние шаги смотрели выбранные
    дни и пропустили метку у пустых дней первой колонки на проде;
  · промежуток между кольцами не меньше 4 px на 1600, 1280 и 390;
  · пустой месяц — «Записей в этом месяце пока нет»; «Записано N дней
    из M» склоняется (N = 1, 2, 5, 11, 21, 22).
ПРОГОН: день с записями в пределах недели → сводка слева совпадает
с `/nutrition/api/diary` за этот день → «Открыть в дневнике» открывает
вкладку «Дневник» на ЭТОМ дне (лента дней выделяет его, загружены его
числа). День дальше недели — кнопки нет (и строки «почему» нет).

Браузер невидимый (вопрос не про ширину полосы прокрутки, §6.0.3), кроме
замера 390 — там спрашивается прокрутка вбок, и окно видимое. В базу
НЕ ПИШЕТ: выбор дня живёт в странице.

КЛЮЧИ:
  --контроль  подлоги, каждый обязан уронить СВОЮ строку.
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
            и["зазор_390"] = зазоры(стр)
            ctx.close()
        finally:
            бр.close()
    и["все"] = замер_клеток(подлог)
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


# ВСЕ КЛЕТКИ МЕСЯЦА, ПИКСЕЛЕМ («питание-5», блок 1). Прежние шаги смотрели
# выбранные дни и три дня по доле — и пропустили метку цвета питания
# у ПУСТЫХ дней первой колонки: дефект, зависящий от ПОЛОЖЕНИЯ клетки,
# выборкой дней не ловится. Здесь снимается каждая клетка, в полосе
# кольца считаются пиксели цвета питания и `--v2-warn`, у заполненной
# дуги — угол (доля из 180 секторов по 2°).
КЛЕТКИ_КОЛЕЦ = """() => [...document.querySelectorAll('#cal-grid .cal-c:not(.is-pad)')].map(c => {
  const к = c.querySelector('.cal-ring'), r = к.getBoundingClientRect(), д = S.calData.days[c.dataset.date];
  return {дата: c.dataset.date, кол: (new Date(c.dataset.date + 'T00:00:00').getDay() + 6) % 7,
    x: r.left, y: r.top, ш: r.width, в: r.height, вид: к.dataset.ring,
    записи: !!д, доля: д && д.goal ? д.calories / д.goal : null};
})"""

ЦВЕТА_КОЛЕЦ = """() => { const кв = document.createElement('canvas'); кв.width = кв.height = 1;
  const к = кв.getContext('2d', {willReadFrequently: true});
  const ц = s => { к.clearRect(0, 0, 1, 1); к.fillStyle = s; к.fillRect(0, 0, 1, 1);
    return [...к.getImageData(0, 0, 1, 1).data.slice(0, 3)]; };
  // От самой сетки, а не от <body>: `--v2-tool` объявлен оболочкой v2,
  // и у <body> он пуст — цвет разрешался в чёрный, и счёт брал тёмные
  // пиксели цифр за метку (поймано на первом же замере)
  const b = getComputedStyle(document.getElementById('cal-grid'));
  const t = b.getPropertyValue('--v2-tool').trim(), w = b.getPropertyValue('--v2-warn').trim();
  if (!t || !w) return null;
  return {tool: ц(t), warn: ц(w)}; }"""

# Выдуманный месяц поверх настоящего: запись у дня, если (неделя + колонка)
# чётны, — так в КАЖДОЙ колонке есть и пустые дни, и дни с записями,
# а доли идут по кругу 40 / 70 / 100 / 125 %. Стенд не трогается.
ВЫДУМАННЫЙ_МЕСЯЦ = """() => { const [г, м] = S.calMonth.split('-').map(Number);
  const отступ = (new Date(Date.UTC(г, м - 1, 1)).getUTCDay() + 6) % 7, всего = new Date(Date.UTC(г, м, 0)).getUTCDate();
  const дни = {}, доли = [0.4, 0.7, 1.0, 1.25];
  for (let д = 1; д <= всего; д++) { const п = отступ + д - 1;
    if ((Math.floor(п / 7) + п % 7) % 2 === 0) дни[`${г}-${String(м).padStart(2,'0')}-${String(д).padStart(2,'0')}`] =
      {calories: Math.round(2000 * доли[д % 4]), goal: 2000}; }
  S.calData = Object.assign({}, S.calData, {days: дни}); renderCalendar(); }"""


def _полоса_кольца(img, к, dpr, цвета):
    """Пиксели цвета питания и предупреждения в полосе кольца и угол дуги."""
    import math
    cx, cy = (к["x"] + к["ш"] / 2) * dpr, (к["y"] + к["в"] / 2) * dpr
    R = min(к["ш"], к["в"]) / 2 * dpr
    внутр, внеш = R - 2.6 * dpr, R - 0.4 * dpr
    px = img.load()
    зел = ор = 0
    сектора = set()
    for yy in range(int(cy - R) - 1, int(cy + R) + 2):
        for xx in range(int(cx - R) - 1, int(cx + R) + 2):
            dx, dy = xx + 0.5 - cx, yy + 0.5 - cy
            r = math.hypot(dx, dy)
            if not (внутр <= r <= внеш):
                continue
            c = px[xx, yy][:3]
            dт = sum((a - b) ** 2 for a, b in zip(c, цвета["tool"])) ** 0.5
            dв = sum((a - b) ** 2 for a, b in zip(c, цвета["warn"])) ** 0.5
            if dт < 60:
                зел += 1
            elif dв < 60:
                ор += 1
            else:
                continue
            угол = (math.degrees(math.atan2(dx, -dy)) + 360) % 360
            сектора.add(int(угол // 2))
    return {"зел": зел, "ор": ор, "угол": len(сектора) / 180, "сектора": sorted(сектора)}


def все_клетки(стр, dpr=1):
    """Каждая клетка текущего месяца: цвет в полосе кольца, угол дуги, зазоры."""
    import io
    from PIL import Image
    стр.mouse.move(2, 2)
    стр.wait_for_timeout(300)
    цвета = стр.evaluate(ЦВЕТА_КОЛЕЦ)
    if not цвета:
        raise RuntimeError("цвета кольца не разрешились: замерить нечем")
    # Снимок ОКНА после прокрутки к сетке, а не `full_page`: полный снимок
    # временно меняет окно, раскладка съезжает, и координаты клеток,
    # снятые до него, указывают мимо колец (замер: счёт находил цвет
    # у пустых дней, на кадре которых метки не было).
    # Снимков ДВА — чётные и нечётные колонки: иначе в полосу кольца
    # попадает дуга соседа, если кольца сошлись вплотную или наложились
    # (замер «до»: зазор −3.6 px на 1600), и сосед выдаёт себя за метку
    стр.evaluate("() => document.getElementById('cal-grid').scrollIntoView({block: 'center'})")
    стр.wait_for_timeout(200)
    кл = стр.evaluate(КЛЕТКИ_КОЛЕЦ)
    for чёт in (0, 1):
        стр.evaluate("""(ч) => document.querySelectorAll('#cal-grid .cal-c:not(.is-pad)').forEach(c => {
          const к = (new Date(c.dataset.date + 'T00:00:00').getDay() + 6) % 7;
          c.querySelector('.cal-ring').style.visibility = к % 2 === ч ? '' : 'hidden'; })""", чёт)
        img = Image.open(io.BytesIO(стр.screenshot())).convert("RGB")
        for к in кл:
            if к["кол"] % 2 == чёт:
                к.update(_полоса_кольца(img, к, dpr, цвета))
    стр.evaluate("() => document.querySelectorAll('#cal-grid .cal-ring').forEach(к => к.style.visibility = '')")
    return кл


def зазоры(стр):
    """Наименьший промежуток между внешними краями соседних колец, px."""
    кл = стр.evaluate(КЛЕТКИ_КОЛЕЦ)
    гор = []
    вер = []
    for а in кл:
        for б in кл:
            if abs(а["y"] - б["y"]) < 1 and 0 < б["x"] - а["x"] < а["ш"] * 2.5:
                гор.append(б["x"] - (а["x"] + а["ш"]))
            if abs(а["x"] - б["x"]) < 1 and 0 < б["y"] - а["y"] < а["в"] * 2.5:
                вер.append(б["y"] - (а["y"] + а["в"]))
    return {"гор": round(min(гор), 1) if гор else None, "вер": round(min(вер), 1) if вер else None}


def месяц_кольца(стр, месяц, выдуманный=False, dpr=1):
    стр.evaluate("(м) => { S.calMonth = м; return loadCalendar(); }", месяц)
    стр.wait_for_timeout(900)
    if выдуманный:
        стр.evaluate(ВЫДУМАННЫЙ_МЕСЯЦ)
        стр.wait_for_timeout(300)
    return все_клетки(стр, dpr)


СКЛОНЕНИЯ = {1: "1 день", 2: "2 дня", 5: "5 дней", 11: "11 дней", 21: "21 день", 22: "22 дня"}
ПУСТОЙ_МЕСЯЦ = "Записей в этом месяце пока нет"

ТЕКСТЫ_СВОДКИ = """(ns) => { const о = S.calData.summary, итог = {};
  S.calData.summary = Object.assign({}, о, {days: 0, elapsed: 22}); renderMonthSummary();
  итог.пусто = document.getElementById('mo-basis').textContent.trim();
  итог.n = {};
  for (const n of ns) { S.calData.summary = Object.assign({}, о, {days: n, elapsed: 22}); renderMonthSummary();
    итог.n[n] = document.getElementById('mo-basis').textContent.trim(); }
  S.calData.summary = о; renderMonthSummary(); return итог; }"""


def замер_клеток(подлог=None):
    """Все клетки июня и сентября 2026 (месяц с понедельника и со вторника),
    данные стенда и выдуманный месяц поверх; зазоры на 1600 и 1280;
    тексты сводки. Невидимый браузер, dpr 2: на dpr 1 кольцо в 40 px
    даёт по периметру меньше пикселей, чем секторов, и угол дуги
    дрожит на 0.12 при верной отрисовке."""
    from playwright.sync_api import sync_playwright
    и = {"клетки": [], "зазоры": {}}
    with sync_playwright() as p:
        бр = p.chromium.launch(headless=True)
        try:
            ctx = бр.new_context(viewport={"width": 1600, "height": 1100}, device_scale_factor=2)
            стр = ctx.new_page()
            стр.add_init_script(ГЛУШИТЕЛЬ)
            if подлог:
                стр.add_init_script(подлог)
            ch._войти(стр)
            _открыть(стр)
            for мес in ("2026-06", "2026-09"):
                for выд in (False, True):
                    for к in месяц_кольца(стр, мес, выд, 2):
                        к["проход"] = мес + (" выдуманный" if выд else " стенд")
                        и["клетки"].append(к)
            и["тексты"] = стр.evaluate(ТЕКСТЫ_СВОДКИ, list(СКЛОНЕНИЯ))
            и["зазоры"][1600] = зазоры(стр)
            стр.set_viewport_size({"width": 1280, "height": 1000})
            стр.wait_for_timeout(500)
            и["зазоры"][1280] = зазоры(стр)
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


ВД = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]


def клетки(и):
    """Шаги по ВСЕМ клеткам месяца («питание-5», блок 1)."""
    вс = и["все"]
    кл = вс["клетки"]
    пустые = [к for к in кл if not к["записи"]]
    с_цветом = [к for к in пустые if к["зел"] or к["ор"]]
    по_кол = {}
    for к in пустые:
        по_кол.setdefault(ВД[к["кол"]], [0, 0])[1] += 1
        if к["зел"] or к["ор"]:
            по_кол[ВД[к["кол"]]][0] += 1
    шаг("все-клетки-пустые-без-цвета", not с_цветом,
        "пустых %d, с цветом %d; по колонкам (с цветом/пустых) %s%s" % (
            len(пустые), len(с_цветом), по_кол,
            "; " + ", ".join("%s %s (%s): зел %d, ор %d" % (к["проход"], к["дата"][-2:], ВД[к["кол"]], к["зел"], к["ор"])
                             for к in с_цветом[:6]) if с_цветом else ""),
        собрано=len(пустые))
    полные = [к for к in кл if к["записи"] and к["доля"] is not None]
    плохие = []
    for к in полные:
        ждём = 1.0 if к["доля"] > 1.10 else min(к["доля"], 1.0)
        цвет_ок = (к["зел"] == 0) if к["доля"] > 1.10 else (к["ор"] == 0)
        if abs(к["угол"] - ждём) > 0.03 or not цвет_ок:
            плохие.append("%s %s: доля %.2f, дуга %.2f, зел %d, ор %d" % (к["проход"], к["дата"][-2:], к["доля"], к["угол"], к["зел"], к["ор"]))
    шаг("все-клетки-дуга-равна-доле", not плохие,
        "клеток %d, расхождений %d%s" % (len(полные), len(плохие), ("; " + "; ".join(плохие[:4])) if плохие else ""),
        собрано=len(полные))
    колонки_пустые = {к["кол"] for к in пустые}
    колонки_полные = {к["кол"] for к in полные}
    шаг("все-колонки-покрыты", len(колонки_пустые) == 7 and len(колонки_полные) == 7,
        "колонок с пустым днём %d, с записями %d" % (len(колонки_пустые), len(колонки_полные)), собрано=len(кл))
    з = dict(вс["зазоры"]); з[390] = и.get("зазор_390")
    мин = [v for z in з.values() if z for v in (z["гор"], z["вер"]) if v is not None]
    шаг("зазор-колец-не-меньше-4px", bool(мин) and min(мин) >= 4,
        "; ".join("%s: гор %s, вер %s" % (ш, z and z["гор"], z and z["вер"]) for ш, z in з.items()), собрано=len(мин))
    т = вс.get("тексты") or {}
    шаг("пустой-месяц-текст", т.get("пусто") == ПУСТОЙ_МЕСЯЦ, repr(т.get("пусто")))
    неверно = {n: т.get("n", {}).get(str(n)) for n, ф in СКЛОНЕНИЯ.items()
               if т.get("n", {}).get(str(n)) != "Записано %s из 22" % ф}
    шаг("записано-склонения", not неверно, "N %s, неверно %s" % (list(СКЛОНЕНИЯ), неверно or 0),
        собрано=len(т.get("n", {})))


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
    клетки(и)
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
    ("метка цвета питания у пустых дней первой колонки (исходный дефект)", "все-клетки-пустые-без-цвета",
     _стиль('#cal-grid .cal-c:nth-child(7n+1) .cal-ring[data-ring="none"]'
            ' { --cal-ring-c: var(--v2-tool) !important; --p: 0.02 !important; }')),
    ("сетка без промежутка (gap: 0)", "зазор-колец-не-меньше-4px",
     _стиль("#cal-grid { gap: 0 !important; }")),
    ("старый текст пустого месяца", "пустой-месяц-текст",
     "addEventListener('DOMContentLoaded', () => { const о = window.renderMonthSummary;"
     " window.renderMonthSummary = () => { о(); const s = S.calData.summary;"
     " if (!s.days) document.getElementById('mo-basis').textContent ="
     " 'Записей за этот месяц нет — ни одного дня из ' + днейСловами(s.elapsed); }; });"),
    ("склонение сломано", "записано-склонения",
     "addEventListener('DOMContentLoaded', () => { window.днейСловами = n => n + ' дней'; });"),
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
