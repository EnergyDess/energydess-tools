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


def main():
    if "--контроль" in sys.argv:
        sys.exit(контроль())
    print("ПАНЕЛЬ AI-АССИСТЕНТА ДНЕВНИКА")
    н, п = прогон()
    print("ИТОГ: шагов %d, плохих %d, пропусков %d" % (len(_строки), н, п))
    if п and not н:
        sys.exit(2)
    sys.exit(1 if н else 0)


if __name__ == "__main__":
    main()
