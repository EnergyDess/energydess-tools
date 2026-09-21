"""ПРОВЕРКА 54: ПАНЕЛЬ AI-АССИСТЕНТА ДНЕВНИКА ПИТАНИЯ (№352, «питание-1», блок 2).

ПРОВЕРКА, код 1 при находке, 2 — замерить нечем (стенда нет, ленты нет).

Решение владельца: ассистент открывается ПАНЕЛЬЮ СПРАВА кнопкой
«AI-ассистент» в шапке; в панели ТОЛЬКО переписка — КБЖУ живёт в дневнике;
лента ОБЯЗАНА прокручиваться. До правки ассистент был вкладкой, и лента
не листалась.

ЧТО СПРАШИВАЕТСЯ ЗАМЕРОМ, А НЕ КЛАССОМ:
  · панель видна по вычисленному стилю и размеру, закрыта — не видна;
    закрывается крестиком и Esc; ≤768 px — на весь экран;
  · лента: scrollHeight > clientHeight, колесо меняет scrollTop;
  · после нового сообщения низ последнего внутри видимой ленты (±2 px);
  · колесо над лентой не двигает страницу (scrollY прежний);
  · в панели нет ни одного элемента с КБЖУ;
  · история на месте после закрытия и повторного открытия.

ВЫЗОВОВ МОДЕЛИ НОЛЬ: история (30 реплик) и ответ модели подделываются
перехватом запроса (`page.route`) — путь кода страницы тот же.
Браузер НЕВИДИМЫЙ: вопросы про логику и геометрию окна, не про полосу
прокрутки страницы (§6.0.3).

КЛЮЧИ:
  --контроль   подлоги: лента без прокрутки; панель через [hidden] при
               показе через display; КБЖУ в панели. Каждый обязан уронить
               СВОЮ строку.
"""
import json
import os
import sys

try:
    import probe_guard  # noqa: F401  ПРОПУСК вместо трассы (§6.0.1)
except ImportError:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_hover as ch  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# Селекторы панели. У вкладки до правки их нет — замер ДО идёт по
# запасным: кнопка шапки и лента `#assistant-chat-msgs`.
КНОПКА = ".nut-tabbtn[data-tab=assistant], #nut-assist-open"
ПАНЕЛЬ = "#nut-assist, #tab-assistant"   # второе — вкладка ДО правки
ЛЕНТА = "#assistant-chat-msgs"
ПОЛЕ = "#assistant-chat-in"

ИСТОРИЯ = [{"role": "user" if i % 2 == 0 else "assistant",
            "content": ("Вопрос %d: сколько белка в твороге?" % i) if i % 2 == 0 else
                       ("Ответ %d. В твороге 5%% около 17 г белка на 100 г. "
                        "Это выдуманная реплика пробы, модель не вызывалась." % i)}
           for i in range(30)]
ОТВЕТ = {"reply": "Выдуманный ответ пробы: модель не вызывалась.", "foods": []}

находок = 0
пропусков = 0
_строки = []


def шаг(имя, условие, подробность="", собрано=None):
    global находок, пропусков
    if собрано is not None and собрано == 0:
        пропусков += 1
        исход = "ПРОПУСК"
    elif условие:
        исход = "ok"
    else:
        находок += 1
        исход = "ПЛОХО"
    _строки.append((имя, исход))
    print("  %-8s %s%s" % (исход, имя, (" — " + подробность) if подробность else ""))
    return исход == "ok"


ВИД = """(с) => { const e = document.querySelector(с); if (!e) return null;
  const r = e.getBoundingClientRect(), st = getComputedStyle(e);
  return {display: st.display, x: Math.round(r.left), w: Math.round(r.width),
          h: Math.round(r.height), right: Math.round(r.right),
          // Край окна для `position: fixed` — пробным элементом: `clientWidth`
          // не вычитает резерв `scrollbar-gutter: stable` у <html> (замер:
          // clientWidth 1600, фиксированный правый край 1590).
          окно: (() => { const d = document.createElement('div');
            d.style.cssText = 'position:fixed;right:0;top:0;width:1px;height:1px';
            document.body.appendChild(d); const x = d.getBoundingClientRect().right;
            d.remove(); return Math.round(x); })(),
          видим: e.checkVisibility({checkOpacity: true, checkVisibilityCSS: true})}; }"""

ЛЕНТА_ЗАМЕР = """(с) => { const л = document.querySelector(с); if (!л) return null;
  return {sh: л.scrollHeight, ch: л.clientHeight, st: Math.round(л.scrollTop),
          y: Math.round(window.scrollY)}; }"""

НИЗ = """(с) => { const л = document.querySelector(с); if (!л) return null;
  const м = л.querySelectorAll('.chat-msg'); if (!м.length) return null;
  const п = м[м.length - 1].getBoundingClientRect(), к = л.getBoundingClientRect();
  return {низ_сообщения: Math.round(п.bottom), низ_ленты: Math.round(к.bottom),
          верх_ленты: Math.round(к.top)}; }"""

# Признак КБЖУ: слова норм и числа «ккал» и граммы белков/жиров/углеводов
# в ЭЛЕМЕНТАХ разметки панели, кроме самих сообщений переписки — в тексте
# ответа ассистента «ккал» законно.
КБЖУ = """(с) => { const п = document.querySelector(с); if (!п) return null;
  const все = [...п.querySelectorAll('*')].filter(e => !e.closest('.chat-msgs'));
  const знаки = /ккал|белк|жир|углев|кбжу/i;
  return все.filter(e => e.children.length === 0 && знаки.test(e.textContent || ''))
            .map(e => (e.className || e.tagName).toString().slice(0, 30)); }"""


def _страница(бр, подлог=None, ширина=1600):
    ctx = бр.new_context(viewport={"width": ширина, "height": 900})
    стр = ctx.new_page()
    ch._войти(стр)
    # История живёт в подделке так же, как на сервере: отправленное
    # дописывается, и повторное открытие обязано его показать.
    история = list(ИСТОРИЯ)

    def чат(r):
        вопрос = json.loads(r.request.post_data or "{}").get("message", "")
        история.extend([{"role": "user", "content": вопрос},
                        {"role": "assistant", "content": ОТВЕТ["reply"]}])
        r.fulfill(status=200, content_type="application/json",
                  body=json.dumps(ОТВЕТ, ensure_ascii=False))
    стр.route("**/nutrition/api/chat-history*", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"messages": история}, ensure_ascii=False)))
    стр.route("**/nutrition/api/ai-chat", чат)
    if подлог:
        стр.add_init_script(подлог)
    return ctx, стр


def _открыть(стр):
    кнопка = стр.locator(КНОПКА).first
    if not кнопка.count():
        return False
    кнопка.click()
    стр.wait_for_timeout(900)
    return True


def прогон(подлог=None):
    global находок, пропусков, _строки
    находок = пропусков = 0
    _строки = []
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        бр = p.chromium.launch(headless=True)
        try:
            for ширина in (1600, 390):
                print("— ширина %d" % ширина)
                ctx, стр = _страница(бр, подлог, ширина)
                стр.goto(ch.БАЗА + "/nutrition", wait_until="domcontentloaded")
                стр.wait_for_timeout(1500)
                открыто = _открыть(стр)
                панель = стр.evaluate(ВИД, ПАНЕЛЬ)
                шаг("панель-открыта-%d" % ширина,
                    bool(панель) and панель["видим"] and панель["h"] > 0,
                    "панель %s" % панель, собрано=1 if открыто else 0)
                if ширина > 768:
                    шаг("панель-справа-%d" % ширина,
                        bool(панель) and abs(панель["right"] - панель["окно"]) <= 2
                        and панель["w"] < ширина / 2,
                        "x=%s w=%s" % (панель and панель["x"], панель and панель["w"]),
                        собрано=1 if панель else 0)
                else:
                    шаг("панель-на-весь-экран-%d" % ширина,
                        bool(панель) and панель["w"] >= панель["окно"] - 2 and панель["x"] <= 1,
                        "x=%s w=%s" % (панель and панель["x"], панель and панель["w"]),
                        собрано=1 if панель else 0)
                кбжу = стр.evaluate(КБЖУ, ПАНЕЛЬ)
                шаг("в-панели-нет-кбжу-%d" % ширина, кбжу == [],
                    "элементов с КБЖУ: %s" % кбжу, собрано=0 if кбжу is None else 1)

                до = стр.evaluate(ЛЕНТА_ЗАМЕР, ЛЕНТА)
                шаг("лента-длиннее-окна-%d" % ширина,
                    bool(до) and до["sh"] > до["ch"],
                    "scrollHeight %s, clientHeight %s" % (до and до["sh"], до and до["ch"]),
                    собрано=1 if до else 0)
                # Невидимую ленту листать нечем: нажатие по ней уронило бы
                # прогон, а подлог соседней строки унёс бы весь контроль.
                коробка = стр.locator(ЛЕНТА).bounding_box() if до and до["ch"] > 0 else None
                if not коробка:
                    шаг("колесо-листает-ленту-%d" % ширина, False, "ленты не видно", собрано=0)
                if коробка:
                    стр.evaluate("(с) => { document.querySelector(с).scrollTop = 0; }", ЛЕНТА)
                    стр.wait_for_timeout(150)
                    нуль = стр.evaluate(ЛЕНТА_ЗАМЕР, ЛЕНТА)
                    б = стр.locator(ЛЕНТА).bounding_box()
                    стр.mouse.move(б["x"] + б["width"] / 2, б["y"] + б["height"] / 2)
                    стр.mouse.wheel(0, 400)
                    стр.wait_for_timeout(500)
                    после = стр.evaluate(ЛЕНТА_ЗАМЕР, ЛЕНТА)
                    шаг("колесо-листает-ленту-%d" % ширина,
                        после["st"] != нуль["st"],
                        "scrollTop %s → %s" % (нуль["st"], после["st"]))
                    шаг("страница-под-панелью-стоит-%d" % ширина,
                        после["y"] == нуль["y"],
                        "scrollY %s → %s" % (нуль["y"], после["y"]))
                поле = стр.locator(ПОЛЕ).first
                if поле.count() and поле.is_visible():
                    поле.fill("Новый вопрос пробы")
                    поле.press("Enter")
                    стр.wait_for_timeout(1200)
                    низ = стр.evaluate(НИЗ, ЛЕНТА)
                    шаг("последнее-сообщение-видно-%d" % ширина,
                        bool(низ) and низ["низ_сообщения"] <= низ["низ_ленты"] + 2
                        and низ["низ_сообщения"] >= низ["верх_ленты"],
                        "%s" % низ, собрано=1 if низ else 0)
                else:
                    шаг("последнее-сообщение-видно-%d" % ширина, False,
                        "поля ввода не видно", собрано=0)
                if ширина > 768:
                    # закрыть крестиком → открыть → история на месте → Esc
                    было = стр.evaluate("(с) => document.querySelectorAll(с + ' .chat-msg').length", ЛЕНТА)
                    крест = стр.locator("#nut-assist-close")
                    if крест.count() and крест.is_visible():
                        крест.click()
                        стр.wait_for_timeout(500)
                    закрыта = стр.evaluate(ВИД, ПАНЕЛЬ)
                    шаг("крестик-закрывает",
                        bool(закрыта) and not закрыта["видим"],
                        "после крестика %s" % закрыта, собрано=1 if крест.count() else 0)
                    _открыть(стр)
                    стало = стр.evaluate("(с) => document.querySelectorAll(с + ' .chat-msg').length", ЛЕНТА)
                    шаг("история-на-месте-после-повторного-открытия",
                        стало >= было and было > 0, "реплик %s → %s" % (было, стало),
                        собрано=было)
                    стр.keyboard.press("Escape")
                    стр.wait_for_timeout(500)
                    после_esc = стр.evaluate(ВИД, ПАНЕЛЬ)
                    шаг("esc-закрывает",
                        bool(после_esc) and not после_esc["видим"],
                        "после Esc %s" % после_esc, собрано=1 if после_esc else 0)
                ctx.close()
        finally:
            бр.close()
    return находок, пропусков


ПОДЛОГИ = {
    "лента-без-прокрутки": ("""addEventListener('DOMContentLoaded', () => {
        const s = document.createElement('style');
        s.textContent = '#assistant-chat-msgs { overflow: visible !important; }';
        document.head.appendChild(s); });""", "колесо-листает-ленту-1600"),
    "панель-через-hidden": ("""addEventListener('DOMContentLoaded', () => {
        const п = document.getElementById('nut-assist');
        if (!п) return;
        new MutationObserver(() => {
          if (!п.hidden) { п.hidden = true; п.style.display = 'flex'; }
        }).observe(п, {attributes: true, attributeFilter: ['hidden']}); });""",
                            "панель-открыта-1600"),
    "кбжу-в-панели": ("""addEventListener('DOMContentLoaded', () => {
        const п = document.getElementById('nut-assist');
        if (!п) return;
        const d = document.createElement('div');
        d.className = 'подлог-кбжу'; d.textContent = '1200 ккал';
        п.appendChild(d); });""", "в-панели-нет-кбжу-1600"),
}


def контроль():
    print("КОНТРОЛЬ: по подлогу на строку")
    н, _ = прогон()
    if н:
        print("ГРЯЗНАЯ ОСНОВА: на чистом коде %d находок" % н)
        return 2
    беда = 0
    for имя, (скрипт, своя) in ПОДЛОГИ.items():
        print("\n— подлог: %s" % имя)
        прогон(подлог=скрипт)
        упали = {и for и, исход in _строки if исход == "ПЛОХО"}
        if своя in упали:
            print("   НАЙДЕН: упала «%s»" % своя)
        else:
            print("   НЕ НАЙДЕН: «%s» зелёная" % своя)
            беда += 1
    print("\nподлогов %d · не найдено %d" % (len(ПОДЛОГИ), беда))
    return 1 if беда else 0


# ── ОБЛИК «ДНЕВНИКА» И «ДОБАВИТЬ» (блок 3) ─────────────────────────────
# Считается у ВИДИМЫХ элементов со СВОИМ текстом (текстовый узел ребёнком),
# вычисленным стилем: класс ничего не говорит о том, что нарисовано.
ОБЛИК = """() => {
  const видим = e => e.checkVisibility({checkOpacity: true, checkVisibilityCSS: true});
  const свой = e => [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
  const все = [...document.querySelectorAll('.v2-page-wrap *, .nut-app *')]
    .filter(e => видим(e) && свой(e));
  const моно = все.filter(e => /mono/i.test(getComputedStyle(e).fontFamily));
  const прописные = все.filter(e => getComputedStyle(e).textTransform === 'uppercase'
    && !e.closest('.v2-head-label'));
  const имя = e => (e.id ? '#' + e.id : '') + '.' + String(e.className).split(' ')[0];
  return {моно: моно.map(имя), прописные: прописные.map(имя)};
}"""
ЭКРАНЫ_ОБЛИКА = (("дневник", None), ("добавить", ".nut-tabbtn[data-tab=search]"))


def облик(снимки=None, подлог=None):
    """Моноширинные и прописные подписи; код 1, если моноширинных больше нуля."""
    from playwright.sync_api import sync_playwright
    итог_моно = 0
    with sync_playwright() as p:
        бр = p.chromium.launch(headless=True)
        try:
            for ширина in (1600, 1280, 390):
                ctx = бр.new_context(viewport={"width": ширина, "height": 900})
                стр = ctx.new_page()
                ch._войти(стр)
                if подлог:
                    стр.add_init_script(подлог)
                for экран, кнопка in ЭКРАНЫ_ОБЛИКА:
                    стр.goto(ch.БАЗА + "/nutrition", wait_until="domcontentloaded")
                    стр.wait_for_timeout(1500)
                    if кнопка:
                        стр.click(кнопка)
                        стр.wait_for_timeout(1200)
                    стр.mouse.move(1, 1)
                    о = стр.evaluate(ОБЛИК)
                    итог_моно += len(о["моно"])
                    print("  %-9s %4d  моноширинных %2d, прописных %2d  %s" % (
                        экран, ширина, len(о["моно"]), len(о["прописные"]),
                        sorted(set(о["моно"]))[:6]))
                    if снимки:
                        os.makedirs(снимки, exist_ok=True)
                        стр.screenshot(path=os.path.join(снимки, "%s-%d.png" % (экран, ширина)),
                                       full_page=True, animations="disabled")
                ctx.close()
        finally:
            бр.close()
    print("ИТОГ ОБЛИКА: моноширинных на двух экранах × трёх ширинах %d" % итог_моно)
    return 1 if итог_моно else 0


# ── ВКЛАДКИ «ВЕС» И «ПРОФИЛЬ» (№352, «питание-2», блоки 2 и 3) ─────────
# Пустота колонки — от низа её последнего видимого блока до низа самой
# высокой колонки той же вкладки. Замер до правки: под «Записать замер»
# на «Весе» и под «Сохранить» на «Профиле» стояли сотни пикселей пустоты.
# Колонки — прямые дети вкладки либо её сетки (`.w-cols`, `.p-cols`),
# у которых больше одного ребёнка в ряду: одна колонка пустоты не даёт.
ПУСТОТЫ = """(вкладка) => {
  const т = document.getElementById(вкладка); if (!т) return null;
  const видим = e => e.checkVisibility({checkOpacity: true, checkVisibilityCSS: true})
    && e.getBoundingClientRect().height > 0;
  const сетка = т.querySelector(':scope > .w-cols, :scope > .p-cols') || т;
  const колонки = [...сетка.children].filter(видим);
  if (колонки.length < 2) return {колонок: колонки.length, пустота: 0, по_колонкам: []};
  const ряды = {};
  колонки.forEach(к => { const y = Math.round(к.getBoundingClientRect().top);
    (ряды[y] = ряды[y] || []).push(к); });
  let худшая = 0; const по = [];
  Object.values(ряды).filter(р => р.length > 1).forEach(р => {
    const низ = Math.max(...р.map(к => {
      const д = [...к.children].filter(видим);
      return д.length ? Math.max(...д.map(x => x.getBoundingClientRect().bottom)) : к.getBoundingClientRect().top; }));
    р.forEach(к => { const д = [...к.children].filter(видим);
      const свой = д.length ? Math.max(...д.map(x => x.getBoundingClientRect().bottom)) : к.getBoundingClientRect().top;
      let п = Math.round(низ - свой);
      // Пустота, перенесённая ВНУТРЬ растянутой последней карточки, — та же
      // пустота: от низа её содержимого до низа её поля
      const последняя = д[д.length - 1];
      if (последняя) {
        const вн = [...последняя.children].filter(видим);
        if (вн.length) {
          const пол = parseFloat(getComputedStyle(последняя).paddingBottom) || 0;
          п += Math.max(0, Math.round(последняя.getBoundingClientRect().bottom - пол
                 - Math.max(...вн.map(x => x.getBoundingClientRect().bottom))));
        }
      }
      по.push((к.className.split(' ')[0] || к.tagName) + ':' + п);
      худшая = Math.max(худшая, п); }); });
  return {колонок: колонки.length, пустота: худшая, по_колонкам: по};
}"""
ВКЛАДКИ_ОБЛИКА = (("вес", "weight"), ("профиль", "profile"))


def облик_вкладок(снимки=None, подлог=None, порог=24):
    """Моноширинные, прописные и пустоты колонок на «Весе» и «Профиле»."""
    from playwright.sync_api import sync_playwright
    плохо = 0
    with sync_playwright() as p:
        бр = p.chromium.launch(headless=True)
        try:
            for ширина in (1600, 1280, 390):
                ctx = бр.new_context(viewport={"width": ширина, "height": 900})
                стр = ctx.new_page()
                ch._войти(стр)
                if подлог:
                    стр.add_init_script(подлог)
                for экран, вкладка in ВКЛАДКИ_ОБЛИКА:
                    стр.goto(ch.БАЗА + "/nutrition", wait_until="domcontentloaded")
                    стр.wait_for_timeout(1500)
                    стр.click(".nut-tabbtn[data-tab=%s]" % вкладка)
                    стр.wait_for_timeout(1500)
                    стр.mouse.move(1, 1)
                    о = стр.evaluate(ОБЛИК)
                    п = стр.evaluate(ПУСТОТЫ, "tab-" + вкладка)
                    пуст = п["пустота"] if п else None
                    ок = not о["моно"] and пуст_ок(пуст, порог)
                    плохо += not ок
                    print("  %-8s %4d  моно %2d, прописных %2d, пустота колонки %s px %s  %s" % (
                        экран, ширина, len(о["моно"]), len(о["прописные"]), пуст,
                        п["по_колонкам"] if п else "", sorted(set(о["моно"]))[:5]))
                    if снимки:
                        os.makedirs(снимки, exist_ok=True)
                        стр.screenshot(path=os.path.join(снимки, "%s-%d.png" % (экран, ширина)),
                                       full_page=True, animations="disabled")
                ctx.close()
        finally:
            бр.close()
    print("ИТОГ ВКЛАДОК: плохих замеров %d из 6" % плохо)
    return 1 if плохо else 0


def _сделать_фото(путь):
    """Сгенерированная картинка: заливка и фигуры, не фото человека (§5.1)."""
    from PIL import Image, ImageDraw
    к = Image.new("RGB", (600, 800), (70, 110, 150))
    р = ImageDraw.Draw(к)
    р.rectangle((200, 150, 400, 650), fill=(150, 190, 220))
    р.ellipse((250, 60, 350, 160), fill=(200, 210, 230))
    к.save(путь, "PNG")


ТОЧКИ = "() => document.querySelectorAll('#wt-svg .wt-dot').length"


def прогон_веса():
    """Путь человека по «Весу»: замер → точка на графике; фото → сравнение
    → удаление. ПИШЕТ В БАЗУ СТЕНДА; после — `py make_local_user.py --seed`."""
    import tempfile
    global находок, пропусков, _строки
    находок = пропусков = 0
    _строки = []
    from playwright.sync_api import sync_playwright
    фото = os.path.join(tempfile.gettempdir(), "nut_probe_body.png")
    _сделать_фото(фото)
    with sync_playwright() as p:
        бр = p.chromium.launch(headless=True)
        try:
            ctx = бр.new_context(viewport={"width": 1600, "height": 900})
            стр = ctx.new_page()
            стр.on("dialog", lambda д: д.accept())
            ch._войти(стр)
            стр.goto(ch.БАЗА + "/nutrition", wait_until="domcontentloaded")
            стр.wait_for_timeout(1200)
            стр.click(".nut-tabbtn[data-tab=weight]")
            стр.wait_for_timeout(1500)
            было = стр.evaluate("() => ({n: S.weight.logs.length, w: (S.weight.logs[0]||{}).weight_kg,"
                                " д: (S.weight.logs[0]||{}).date})")
            точек_до = стр.evaluate(ТОЧКИ)
            новый = round((было["w"] or 80) - 0.4, 1)
            стр.click(".wt-hero-btn")
            стр.wait_for_timeout(500)
            стр.fill("#mw-kg", str(новый))
            стр.click("#modal-measure button[onclick='saveMeasure()']")
            стр.wait_for_timeout(1500)
            стало = стр.evaluate("() => ({n: S.weight.logs.length, w: (S.weight.logs[0]||{}).weight_kg,"
                                 " д: (S.weight.logs[0]||{}).date, сегодня: S.today})")
            точек_после = стр.evaluate(ТОЧКИ)
            шаг("замер-лёг-точкой-на-графике",
                стало["w"] == новый and стало["д"] == стало["сегодня"]
                and точек_после >= точек_до + (0 if было["д"] == стало["сегодня"] else 1),
                "вес %s → %s, записей %d → %d, точек %d → %d" % (
                    было["w"], стало["w"], было["n"], стало["n"], точек_до, точек_после))
            шаг("цифра-карточки-обновилась",
                стр.inner_text("#cur-wt").strip() == str(новый), стр.inner_text("#cur-wt"))

            стр.set_input_files("#photo-front", фото)
            стр.wait_for_timeout(800)
            стр.click(".wt-photos > .btn-primary")
            стр.wait_for_timeout(2000)
            сегодня = стало["сегодня"]
            есть = стр.evaluate("(д) => !!(bodyPhotosCache[д] || {}).front", сегодня)
            шаг("фото-появилось", есть, "за %s" % сегодня)
            даты = стр.evaluate("() => [...document.querySelectorAll('#compare-date-old option')].map(o => o.value)")
            прошлые = [д for д in даты if д and д != сегодня]
            if прошлые:
                стр.select_option("#compare-date-old", прошлые[0])
            стр.select_option("#compare-date-new", сегодня)
            стр.wait_for_timeout(600)
            снимков = стр.evaluate("() => document.querySelectorAll('#compare-view img').length")
            подписи = стр.evaluate("() => [...document.querySelectorAll('#compare-view .compare-col-label')].map(e => e.textContent)")
            шаг("сравнение-по-двум-датам",
                len(set(подписи)) == 2 and сегодня in подписи and снимков >= 2,
                "подписи %s, снимков %d" % (подписи, снимков), собрано=len(прошлые))
            стр.evaluate("(д) => deleteBodyPhoto(д, 'front')", сегодня)
            стр.wait_for_timeout(1500)
            есть = стр.evaluate("(д) => !!(bodyPhotosCache[д] || {}).front", сегодня)
            шаг("фото-удалено", not есть)
        finally:
            бр.close()
    return находок, пропусков


КОЛЬЦО = """() => ({норма: S.diary && S.diary.goals ? S.diary.goals.calories : null,
  съедено: S.diary ? Math.round(S.diary.totals.calories) : null,
  остаток: document.getElementById('ring-remain').textContent.trim()})"""


def прогон_профиля():
    """Цель → «Сохранить» → нормы пересчитаны → кольцо дневника с новой нормой;
    «Переподключить» при отозванном ключе открывает прежнюю форму. Весы
    живьём НЕ зовутся: состояние ставит `make_local_user.py --scale reauth`.
    ПИШЕТ В БАЗУ СТЕНДА; после — `py make_local_user.py --seed`."""
    import subprocess
    global находок, пропусков, _строки
    находок = пропусков = 0
    _строки = []
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        бр = p.chromium.launch(headless=True)
        try:
            ctx = бр.new_context(viewport={"width": 1600, "height": 900})
            стр = ctx.new_page()
            ch._войти(стр)
            стр.goto(ch.БАЗА + "/nutrition", wait_until="domcontentloaded")
            стр.wait_for_timeout(1500)
            кольцо_до = стр.evaluate(КОЛЬЦО)
            стр.click(".nut-tabbtn[data-tab=profile]")
            стр.wait_for_timeout(1500)
            норма_до = стр.inner_text("#t-cal").strip()
            цель_до = стр.evaluate("() => document.querySelector('#rg-goal .segmented-btn.active').dataset.val")
            новая = "gain" if цель_до != "gain" else "lose"
            стр.click("#rg-goal .segmented-btn[data-val=%s]" % новая)
            стр.click(".p-form button[onclick='saveProfile()']")
            стр.wait_for_timeout(2000)
            норма_после = стр.inner_text("#t-cal").strip()
            шаг("нормы-пересчитаны-после-сохранения", норма_после != норма_до and норма_после.isdigit(),
                "цель %s → %s, ккал %s → %s" % (цель_до, новая, норма_до, норма_после))
            стр.click(".nut-tabbtn[data-tab=diary]")
            стр.wait_for_timeout(1500)
            кольцо = стр.evaluate(КОЛЬЦО)
            ожидаем = int(норма_после) - кольцо["съедено"] if норма_после.isdigit() else None
            шаг("кольцо-дневника-с-новой-нормой",
                кольцо["норма"] == int(норма_после or 0) and кольцо["остаток"] == str(ожидаем),
                "норма кольца %s → %s, осталось «%s» → «%s»" % (
                    кольцо_до["норма"], кольцо["норма"], кольцо_до["остаток"], кольцо["остаток"]))
            ctx.close()
        finally:
            бр.close()

    корень = os.path.dirname(os.path.abspath(__file__))
    subprocess.run([sys.executable, os.path.join(корень, "make_local_user.py"), "--scale", "reauth"],
                   capture_output=True, cwd=корень)
    with sync_playwright() as p:
        бр = p.chromium.launch(headless=True)
        try:
            ctx = бр.new_context(viewport={"width": 1600, "height": 900})
            стр = ctx.new_page()
            ch._войти(стр)
            стр.goto(ch.БАЗА + "/nutrition", wait_until="domcontentloaded")
            стр.wait_for_timeout(1200)
            стр.click(".nut-tabbtn[data-tab=profile]")
            стр.wait_for_timeout(1500)
            кнопка = стр.evaluate(ВИДЕН_ЭЛ, "#scale-reauth-btn")
            форма_до = стр.evaluate(ВИДЕН_ЭЛ, "#scale-password")
            if кнопка:
                стр.click("#scale-reauth-btn")
                стр.wait_for_timeout(400)
            форма = стр.evaluate(ВИДЕН_ЭЛ, "#scale-password")
            фокус = стр.evaluate("() => document.activeElement && document.activeElement.id")
            шаг("переподключить-открывает-форму", bool(кнопка) and not форма_до and bool(форма),
                "кнопка %s, поле пароля до %s после %s, фокус %s" % (кнопка, форма_до, форма, фокус),
                собрано=1 if кнопка is not None else 0)
            ctx.close()
        finally:
            бр.close()
    return находок, пропусков


ВИДЕН_ЭЛ = """(с) => { const e = document.querySelector(с); if (!e) return null;
  const r = e.getBoundingClientRect();
  return e.checkVisibility({checkOpacity: true, checkVisibilityCSS: true}) && r.width > 0 && r.height > 0; }"""


def пуст_ок(пуст, порог):
    return пуст is not None and пуст <= порог


# ── СКВОЗНОЙ ПРОГОН «ДНЕВНИК» И «ДОБАВИТЬ» (блок 3.4) ──────────────────
# Путь человека, результат — из состояния страницы (S.diary, то есть ответ
# /nutrition/api/diary после записи), а не из того, что экран не ругнулся.
# Модель не должна вызываться НИ РАЗУ: считается по `model_usage` стенда.
# ПИШЕТ В БАЗУ СТЕНДА; после прогона: `py make_local_user.py --seed`.
ИТОГИ = "() => ({ккал: Math.round(S.diary.totals.calories), вода: S.diary.water_ml,"         " обед: (S.diary.meals.lunch || []).length,"         " позиций: Object.values(S.diary.meals).reduce((a, m) => a + m.length, 0)})"


def _вызовов_модели():
    import sqlite3
    база = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.db")
    return sqlite3.connect(база).execute("SELECT COUNT(*) FROM model_usage").fetchone()[0]


def _в_дневник(стр):
    стр.evaluate("goTab('diary')")
    стр.wait_for_timeout(1200)
    return стр.evaluate(ИТОГИ)


def _добавить_первую(стр, область, запрос=None):
    стр.click(".nut-tabbtn[data-tab=search]")
    стр.wait_for_timeout(900)
    стр.click("#meal-chips [data-meal=lunch]")
    стр.click("#st-" + область)
    стр.wait_for_timeout(900)
    if запрос:
        стр.fill("#s-input", запрос)
        стр.wait_for_timeout(2500)
    карточка = стр.locator("#s-results .r-item").first
    if not карточка.count():
        return None
    стр.locator("#s-results .r-item .r-add").first.click()
    стр.wait_for_timeout(700)
    ккал = стр.evaluate("parseFloat(document.getElementById('ap-kcal').textContent)")
    стр.fill("#ap-grams", "100")
    стр.dispatch_event("#ap-grams", "input")
    стр.click(".ap-add")
    стр.wait_for_timeout(1200)
    return ккал


def прогон_дневника():
    global находок, пропусков, _строки
    находок = пропусков = 0
    _строки = []
    from playwright.sync_api import sync_playwright
    модель_до = _вызовов_модели()
    with sync_playwright() as p:
        бр = p.chromium.launch(headless=True)
        try:
            ctx = бр.new_context(viewport={"width": 1600, "height": 900})
            стр = ctx.new_page()
            ch._войти(стр)
            стр.goto(ch.БАЗА + "/nutrition", wait_until="domcontentloaded")
            стр.wait_for_timeout(1500)
            было = стр.evaluate(ИТОГИ)

            ккал = _добавить_первую(стр, "all", "Гречневая")
            стало = _в_дневник(стр)
            шаг("поиск-и-добавление-в-обед",
                ккал is not None and стало["обед"] == было["обед"] + 1
                and abs((стало["ккал"] - было["ккал"]) - ккал) <= 1,
                "обед %s → %s, кольцо %s → %s ккал (+%s), продукт %s ккал"
                % (было["обед"], стало["обед"], было["ккал"], стало["ккал"],
                   стало["ккал"] - было["ккал"], ккал), собрано=0 if ккал is None else 1)

            до = стало
            кнопки = стр.locator(".meal-card .food-del:visible")
            if кнопки.count():
                кнопки.first.click()
                стр.wait_for_timeout(600)
                подтв = стр.locator(".modal-ov.open .btn-danger, .modal-ov.open [data-confirm]")
                if подтв.count():
                    подтв.first.click()
                стр.wait_for_timeout(1200)
            после = стр.evaluate(ИТОГИ)
            шаг("удаление-позиции", после["позиций"] == до["позиций"] - 1,
                "позиций %s → %s" % (до["позиций"], после["позиций"]), собрано=кнопки.count())

            до = после
            ккал = _добавить_первую(стр, "recent")
            после = _в_дневник(стр)
            шаг("добавление-из-недавних", ккал is not None and после["обед"] == до["обед"] + 1,
                "обед %s → %s" % (до["обед"], после["обед"]), собрано=0 if ккал is None else 1)

            до = после
            стр.click(".nut-tabbtn[data-tab=search]")
            стр.wait_for_timeout(800)
            стр.click("#meal-chips [data-meal=lunch]")
            стр.click(".a-method-manual")
            стр.wait_for_timeout(600)
            стр.fill("#cf-name", "Проба свой продукт")
            стр.fill("#cf-cal", "123")
            стр.click("#modal-custom .add-btn, #modal-custom .btn-primary")
            стр.wait_for_timeout(1000)
            # openPortion на десктопе открывает панель справа, на узком — окно
            запись = стр.locator(".ap-add:visible, #por-add-btn:visible")
            if запись.count():
                запись.first.click()
                стр.wait_for_timeout(1200)
            после = _в_дневник(стр)
            шаг("свой-продукт-записан", после["позиций"] == до["позиций"] + 1,
                "позиций %s → %s" % (до["позиций"], после["позиций"]))

            до = после
            стр.click(".nut-water-chip >> text=+250")
            стр.wait_for_timeout(1200)
            после = стр.evaluate(ИТОГИ)
            шаг("вода-плюс-250", после["вода"] == до["вода"] + 250,
                "вода %s → %s мл" % (до["вода"], после["вода"]))

            стр.click(".nut-tabbtn[data-tab=search]")
            стр.wait_for_timeout(800)
            with стр.expect_file_chooser(timeout=5000) as выбор:
                стр.click(".a-method >> text=Фото")
            шаг("фото-открывает-выбор-файла", выбор.value is not None)
            стр.click(".a-method >> text=Штрихкод")
            стр.wait_for_timeout(1200)
            окно = стр.evaluate("[...document.querySelectorAll('.modal-ov.open')].map(e => e.id)")
            шаг("штрихкод-открывает-окно", bool(окно), "открыто %s" % окно)
            ctx.close()
        finally:
            бр.close()
    модель_после = _вызовов_модели()
    шаг("модель-не-вызывалась", модель_после == модель_до,
        "model_usage %s → %s" % (модель_до, модель_после))
    return находок, пропусков


def main():
    if "--прогон-профиля" in sys.argv:
        н, п = прогон_профиля()
        print("ИТОГ ПРОГОНА ПРОФИЛЯ: шагов %d, плохих %d, пропусков %d" % (len(_строки), н, п))
        sys.exit(1 if н else (2 if п else 0))
    if "--прогон-веса" in sys.argv:
        н, п = прогон_веса()
        print("ИТОГ ПРОГОНА ВЕСА: шагов %d, плохих %d, пропусков %d" % (len(_строки), н, п))
        sys.exit(1 if н else (2 if п else 0))
    if "--прогон" in sys.argv:
        н, п = прогон_дневника()
        print("ИТОГ ПРОГОНА: шагов %d, плохих %d, пропусков %d" % (len(_строки), н, п))
        sys.exit(1 if н else (2 if п else 0))
    if "--облик" in sys.argv and "--контроль" in sys.argv:
        # Подлог: вернуть моноширинную подпись заголовку коробки «Добавить»
        код = облик(подлог="""addEventListener('DOMContentLoaded', () => {
          const s = document.createElement('style');
          s.textContent = '#tab-search .a-box-title { font-family: var(--v2-font-mono) !important; }';
          document.head.appendChild(s); });""")
        print("КОНТРОЛЬ ОБЛИКА:", "ЛОВИТ" if код == 1 else "НЕ ЛОВИТ")
        sys.exit(0 if код == 1 else 1)
    if "--вкладки" in sys.argv and "--контроль" in sys.argv:
        # Подлог: колонки ряда «Веса» снова не тянутся до общего низа —
        # ровно раскладка до правки (`align-items: start`)
        код = облик_вкладок(подлог="""addEventListener('DOMContentLoaded', () => {
          const s = document.createElement('style');
          s.textContent = '#tab-weight .w-cols, #tab-profile .p-cols { align-items: start !important; }';
          document.head.appendChild(s); });""")
        print("КОНТРОЛЬ ВКЛАДОК:", "ЛОВИТ" if код == 1 else "НЕ ЛОВИТ")
        sys.exit(0 if код == 1 else 1)
    if "--вкладки" in sys.argv:
        снимки = sys.argv[sys.argv.index("--снимки") + 1] if "--снимки" in sys.argv else None
        sys.exit(облик_вкладок(снимки))
    if "--облик" in sys.argv:
        снимки = sys.argv[sys.argv.index("--снимки") + 1] if "--снимки" in sys.argv else None
        sys.exit(облик(снимки))
    if "--контроль" in sys.argv:
        sys.exit(контроль())
    print("ПАНЕЛЬ AI-АССИСТЕНТА ДНЕВНИКА")
    н, п = прогон()
    print("ОБЛИК «ДНЕВНИКА» И «ДОБАВИТЬ»")
    if облик():
        н += 1
    print("«ВЕС» И «ПРОФИЛЬ»")
    if облик_вкладок():
        н += 1
    print("ИТОГ: шагов %d, плохих %d, пропусков %d" % (len(_строки) + 1, н, п))
    if п and not н:
        sys.exit(2)
    sys.exit(1 if н else 0)


if __name__ == "__main__":
    main()
