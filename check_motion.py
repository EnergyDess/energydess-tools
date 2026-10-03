"""ПРОБА ПЛАВНОСТИ АНИМАЦИЙ: «Сегодня» модуля «Контент» (письмо M1, BACKLOG №384).

Правила движения — `.claude/skills/energydess-motion/SKILL.md`, примитивы —
`static/motion.css` и `static/motion.js`. Проба спрашивает то, чего не видит
ни одна прежняя: что происходит МЕЖДУ двумя готовыми кадрами анимации.

Действия на 1920 и 390 (с касанием):
  · загрузка — волна появления карточек;
  · переключение «Длинные / Shorts» туда-обратно 5 раз (`Motion.swap`);
  · «Убрать» у находки «от тебя» — уход и схлопывание (без перезагрузки);
  · «В работу» — перезагрузка и тост.

Что меряется (сэмплер в странице ставится ДО её скриптов, init-скриптом):
  · кадры длиннее 50 мс — не больше одного на действие (`requestAnimationFrame`);
  · CLS во время переключения — 0 (`layout-shift` по правилу метрики:
    сдвиги в 500 мс после ввода не считаются — поэтому swap обязан уложить
    всё движение раскладки в это окно);
  · нет мигания: высота ящика панелей ни в один кадр не 0, и в любой кадр
    в нём есть видимый пункт либо пункт в анимации;
  · нет скачка высоты: за один кадр ящик меняется не больше чем на
    половину всей разницы высот (без фиксации — вся разница за кадр);
  · `prefers-reduced-motion: reduce` — все анимации (WAAPI и CSS) ≤ 120 мс.

Стенд свой, на копии базы (засев идей и находок — боевыми функциями
проверки 74, модель подменена, в сеть 0 вызовов). Браузер невидимый:
вопрос — про время и раскладку кадров, не про ширину (§6.0.3).

ПОДЛОГ (--контроль): из отданного браузеру `motion.js` вырезается фиксация
высоты в `swap` — шаг «переключение/скачок» обязан покраснеть;
доказательство независимо: наибольший скачок высоты за кадр до и после.
"""
import os
import shutil
import sys

import probe_guard  # noqa: F401 — внешний отказ говорится словом (§3)

sys.stdout.reconfigure(encoding="utf-8")
ПОЧТА = "screenshot@local.dev"
ШИРИНЫ = ((1920, 1080, False), (390, 844, True))
ДЛИННЫЙ_КАДР = 50          # мс
ПОТОЛОК_РЕДКО = 120        # мс — потолок движения при reduced-motion
ПОВТОРОВ = 5
ТОЛЬКО_СТРОКИ = "--строки" in sys.argv or "--контроль-строк" in sys.argv   # быстрый прогон одних строк (замер «до»)

# Доказательство подлога (§6.0.3) — независимо от вердикта шага:
ДОКАЗАТЕЛЬСТВА = {"фиксация-высоты": "наибольший скачок высоты ящика за кадр — чисто и с подлогом"}

шаги = []


def шаг(имя, условие, подробно="", собрано=None):
    """Исход шага. `собрано=0` — замер не состоялся: ПРОПУСК, а не OK."""
    исход = "ПРОПУСК" if собрано == 0 else ("OK" if условие else "ПЛОХО")
    шаги.append((имя, исход, подробно))
    print("  %-7s %-34s %s" % (исход, имя, подробно))


# Сэмплер: кадры, сдвиги раскладки, все созданные WAAPI-анимации. Ставится
# до скриптов страницы, поэтому видит и волну появления при загрузке.
САМПЛЕР = r"""
(() => {
  const з = window.__м = {кадры: [], сдвиги: [], анимации: [], ящик: [], идёт: null, скролл: [], список: [], главная: []};
  // флаг перезагрузки после действия (M1b) — до того, как страница его снимет
  try { з.флаг = sessionStorage.getItem('m-after:' + location.pathname); } catch (e) { з.флаг = null; }
  let прошлый = performance.now();
  const тик = (т) => {
    з.кадры.push([т, т - прошлый]); прошлый = т;
    // Ящик панелей; на прежнем коде (`MAIN_DIR`, замер «до») его нет —
    // тогда меряется видимая панель
    const я = document.getElementById('today-panes') || document.querySelector('.today-pane:not([hidden])');
    if (я && з.идёт) {
      const пункты = [...document.querySelectorAll('.today-pane:not([hidden]) > *')];
      const видно = пункты.some((п) => п.getClientRects().length && parseFloat(getComputedStyle(п).opacity) > 0.02);
      const в_анимации = пункты.some((п) => п.getAnimations().length > 0);
      з.ящик.push([т, я.getBoundingClientRect().height, видно, в_анимации]);
    }
    // Строки «Ещё варианты» (письмо M1b): прокрутка — каждый кадр с начала
    // документа (после перезагрузки так виден проезд), список и счётчик
    // «В плане» — во время действия
    з.скролл.push([т, scrollY]);
    // главная карточка с начала документа: видна ли (вспышка — «видно →
    // прозрачно → видно» до волны), первые 400 кадров
    if (з.главная.length < 400) {
      const г = document.querySelector('.today-pane:not([hidden]) > .today-main');
      if (г) з.главная.push([т, parseFloat(getComputedStyle(г).opacity)]);
    }
    if (з.идёт) {
      const сп = document.querySelector('.today-pane:not([hidden]) .today-more');
      const сч = document.querySelector('.today-tile[data-status="plan"] .v2-tile-num');
      з.список.push([т, сп ? сп.getBoundingClientRect().height : null,
                     сч ? parseInt(сч.textContent.replace(/\D/g, '') || '0', 10) : null]);
    }
    requestAnimationFrame(тик);
  };
  requestAnimationFrame(тик);
  try {
    new PerformanceObserver((с) => { for (const e of с.getEntries()) з.сдвиги.push([e.startTime, e.value, e.hadRecentInput]); })
      .observe({type: 'layout-shift', buffered: true});
  } catch (e) {}
  const родной = Element.prototype.animate;
  Element.prototype.animate = function (к, о) {
    const а = родной.call(this, к, о);
    const тт = а.effect.getTiming();
    з.анимации.push([performance.now(), (+тт.duration || 0) + (+тт.delay || 0), String(this.className || '')]);
    return а;
  };
})();
"""

ДОЖДАТЬСЯ_ТИШИНЫ = r"""async () => {
  const нач = performance.now();
  await new Promise((r) => setTimeout(r, 60));
  while (document.getAnimations().some((а) => а.playState === 'running') && performance.now() - нач < 4000)
    await new Promise((r) => setTimeout(r, 30));
  await new Promise((r) => setTimeout(r, 60));
  return performance.now();
}"""

ОКНО = r"""([от, до]) => {
  const з = window.__м;
  const кадры = з.кадры.filter(([т]) => т > от && т <= до).map(([, д]) => д);
  const сдвиг = з.сдвиги.filter(([т, , в]) => т >= от && т <= до && !в).reduce((с, [, v]) => с + v, 0);
  const сдвиг_все = з.сдвиги.filter(([т]) => т >= от && т <= до).reduce((с, [, v]) => с + v, 0);
  const я = з.ящик.filter(([т]) => т >= от && т <= до);
  let скачок = 0;
  for (let i = 1; i < я.length; i++) скачок = Math.max(скачок, Math.abs(я[i][1] - я[i - 1][1]));
  const css = document.getAnimations().map((а) => а.effect && а.effect.getTiming())
    .filter(Boolean).map((т) => (+т.duration || 0) + (+т.delay || 0));
  return {кадров: кадры.length, длинных: кадры.filter((д) => д > __ДЛ__).length,
          худший: кадры.length ? Math.round(Math.max(...кадры)) : 0,
          cls: +сдвиг.toFixed(4), cls_все: +сдвиг_все.toFixed(4),
          мин_высота: я.length ? Math.round(Math.min(...я.map((р) => р[1]))) : null,
          пустых: я.filter((р) => !р[2] && !р[3]).length, проб_ящика: я.length,
          скачок: Math.round(скачок),
          анимаций: з.анимации.filter(([т]) => т >= от - 5 && т <= до).length,
          длиннее_потолка: з.анимации.filter(([т, д]) => т >= от - 5 && т <= до && д > __ПТ__).length,
          css_длиннее: css.filter((д) => д > __ПТ__).length};
}""".replace("__ДЛ__", str(ДЛИННЫЙ_КАДР)).replace("__ПТ__", str(ПОТОЛОК_РЕДКО))


def _подложить(маршрут):
    """Подлог: фиксация высоты в swap вырезана из отданного motion.js."""
    тело = маршрут.fetch().text()
    было = тело
    тело = тело.replace("container.style.height = h1 + 'px';", "")
    тело = тело.replace("const рост = container.animate(", "const рост = { finished: Promise.resolve() }; (")
    assert тело != было, "подлог не нашёл фиксацию высоты в motion.js"
    маршрут.fulfill(body=тело, content_type="application/javascript")


def _действие(с, сделать):
    от = с.evaluate("() => { window.__м.идёт = true; return performance.now(); }")
    сделать()
    до = с.evaluate(ДОЖДАТЬСЯ_ТИШИНЫ)
    с.evaluate("() => { window.__м.идёт = null; }")
    return с.evaluate(ОКНО, [от, до])


# ПОДЛОГИ БЛОКА 3 (письмо M1b) — замены в отданной браузеру разметке «Сегодня».
# Пусто — разметка как есть. Каждая замена обязана найтись (иначе подлог
# не состоялся — и проба об этом скажет, а не промолчит).
ЗАМЕНЫ = []
МЕДЛЕННЫЙ = {"порт": None}


def _медленный_сервер():
    """Скрипт, отвечающий через 600 мс: парсер встаёт на нём ПОСЛЕ </main>,
    браузер успевает нарисовать разобранное до DOMContentLoaded — так
    вспышка до волны становится наблюдаемой (без этого первый кадр часто
    наступает уже после старта волны, и сравнивать нечего)."""
    import http.server
    import threading
    import time as _t

    class Ответ(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            _t.sleep(0.6)
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(b"/* slow */")

        def log_message(self, *a):
            pass
    с = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Ответ)
    threading.Thread(target=с.serve_forever, daemon=True).start()
    return с.server_address[1]


def _разметка(маршрут, медленно=False):
    ответ = маршрут.fetch()
    тело = ответ.text()
    for было, стало in ЗАМЕНЫ:
        if было not in тело:
            raise AssertionError("подлог не нашёл в разметке: %r" % было[:60])
        тело = тело.replace(было, стало)
    if медленно and МЕДЛЕННЫЙ["порт"]:
        тело = тело.replace("</main>", '</main><script src="http://127.0.0.1:%d/slow.js"></script>'
                            % МЕДЛЕННЫЙ["порт"], 1)
    маршрут.fulfill(response=ответ, body=тело)


def _первый_вход(бр, адрес, токен, ширина, высота, касание, редко):
    """Первый вход: волна есть, вспышки нет. Кадры до старта волны
    обязаны существовать (медленный скрипт после </main>), иначе вопрос
    не задан — тогда ПРОПУСК."""
    import re as _re
    к = бр.new_context(viewport={"width": ширина, "height": высота}, has_touch=касание, is_mobile=касание,
                       reduced_motion="reduce" if редко else "no-preference")
    к.add_cookies([{"name": "access_token", "value": токен, "url": адрес}])
    к.add_init_script(САМПЛЕР)
    к.route(_re.compile(r".*/content(\?.*)?$"), lambda м: _разметка(м, медленно=True))
    с = к.new_page()
    с.goto(адрес + "/content?type=long", wait_until="load", timeout=45000)
    с.evaluate(ДОЖДАТЬСЯ_ТИШИНЫ)
    з = с.evaluate("""() => {
      const з = window.__м;
      const нач = (з.анимации.find(([, , к]) => /today-main/.test(к)) || [Infinity])[0];
      const тр = з.главная.map(([, о]) => о);
      let видели = false, вспышка = false;
      for (const о of тр) { if (о >= 0.98) видели = true; else if (видели && о < 0.5) { вспышка = true; break; } }
      return {волна: з.анимации.filter(([, , к]) => /today-main/.test(к)).length,
              кадров_до_волны: з.главная.filter(([т]) => т < нач).length,
              видна_до_волны: з.главная.filter(([т, о]) => т < нач && о > 0.02).length,
              вспышка: вспышка, кадров: тр.length};
    }""")
    к.close()
    return з


def _после_действия(с):
    """«Не сегодня» у главной — действие с перезагрузкой. В новом документе:
    прокрутка на месте с ПЕРВОГО кадра, волны нет."""
    кн = с.query_selector("#today-later-long")
    if not кн:
        return None
    ряд = с.query_selector(СТРОКА) or кн
    ряд.evaluate("(р) => window.scrollTo({top: р.getBoundingClientRect().top + scrollY - innerHeight / 2,"
                 " behavior: 'instant'})")
    с.wait_for_timeout(300)
    with с.expect_navigation(wait_until="load", timeout=20000):
        кн.click()
    с.evaluate(ДОЖДАТЬСЯ_ТИШИНЫ)
    с.wait_for_timeout(300)
    return с.evaluate("""() => {
      const з = window.__м;
      const ф = з.флаг ? JSON.parse(з.флаг) : null;
      const ys = з.скролл.map(([, y]) => y);
      const итог = Math.round(scrollY);
      return {флаг: !!ф, сохранено: ф ? ф.y : null, первый_кадр: ys.length ? Math.round(ys[0]) : null,
              итог: итог, проезд: ys.length ? Math.round(Math.max(...ys.map((y) => Math.abs(y - итог)))) : 0,
              волна: з.анимации.filter(([, , к]) => /today-main|today-row/.test(к)).length,
              класс_после: document.documentElement.className};
    }""")


def _двойной_клик(с):
    """Двойной клик по «+ в план» — запрос к серверу ровно один."""
    ряд = с.query_selector(СТРОКА)
    if not ряд:
        return None
    id_ = ряд.get_attribute("data-idea")
    запросы = []
    обр = lambda r: запросы.append(r.url) if (r.method == "POST" and r.url.endswith("/content/api/ideas/" + id_)) else None
    с.on("request", обр)
    ряд.query_selector("[data-act='plan']").dblclick()
    с.wait_for_timeout(1500)
    с.remove_listener("request", обр)
    return {"запросов": len(запросы)}


def замер_ширины(бр, адрес, токен, ширина, высота, касание, редко, подлог):
    к = бр.new_context(viewport={"width": ширина, "height": высота}, has_touch=касание, is_mobile=касание,
                       reduced_motion="reduce" if редко else "no-preference")
    к.add_cookies([{"name": "access_token", "value": токен, "url": адрес}])
    к.add_init_script(САМПЛЕР)
    if подлог:
        к.route("**/motion.js*", _подложить)
    if ЗАМЕНЫ:
        import re as _re
        к.route(_re.compile(r".*/content(\?.*)?$"), _разметка)
    с = к.new_page()
    итог = {}
    с.goto(адрес + "/content?type=long", wait_until="load", timeout=45000)
    с.evaluate("() => document.fonts.ready")
    до = с.evaluate(ДОЖДАТЬСЯ_ТИШИНЫ)
    итог["загрузка"] = с.evaluate(ОКНО, [с.evaluate("() => performance.timing.domContentLoadedEventStart - performance.timing.navigationStart"), до])
    итог["motion"] = с.evaluate("() => !!window.Motion")
    высоты = с.evaluate("""() => [...document.querySelectorAll('.today-pane')].map((п) => {
      const б = п.hidden; п.hidden = false; const h = п.getBoundingClientRect().height; п.hidden = б; return Math.round(h); })""")
    итог["высоты_панелей"] = высоты
    перекл = []
    for i in range(0 if ТОЛЬКО_СТРОКИ else ПОВТОРОВ):
        for тип in ("shorts", "long"):
            з = _действие(с, lambda: с.click("#today-type-" + тип))
            з["видна"] = с.evaluate("(т) => !document.querySelector('.today-pane[data-pane=\"' + т + '\"]').hidden", тип)
            перекл.append(з)
    итог["переключения"] = перекл
    try:
        _строки(с, итог)
        итог["двойной"] = _двойной_клик(с)
        итог["после"] = _после_действия(с)
    except Exception as e:
        итог["сбой_строк"] = "%s: %s" % (type(e).__name__, str(e)[:200])
        print("    СБОЙ СТРОК:", итог["сбой_строк"])
    if not подлог and not ТОЛЬКО_СТРОКИ:
        try:
            _находки(с, итог)
        except Exception as e:   # прежний код («до») перезагружает страницу на «Убрать»
            итог["сбой_находок"] = type(e).__name__
    к.close()
    итог["вход"] = _первый_вход(бр, адрес, токен, ширина, высота, касание, редко)
    return итог


def _находки(с, итог):
    if True:
        убрать = с.query_selector(".today-inbox-row [data-act='inbox-archive']")
        if убрать:
            рядов = с.evaluate("() => { window.__проба = 1; return document.querySelectorAll('.today-inbox-row').length; }")
            з = _действие(с, lambda: убрать.click())
            з["рядов_до"] = рядов
            з["рядов_после"] = с.evaluate("() => document.querySelectorAll('.today-inbox-row').length")
            з["тот_же_документ"] = с.evaluate("() => window.__проба === 1")
            итог["убрать"] = з
        работа = с.query_selector(".today-inbox-row [data-act='inbox-work']")
        if работа:
            with с.expect_navigation(wait_until="load", timeout=15000):
                работа.click()
            try:
                с.wait_for_selector(".m-toast", timeout=5000)
            except Exception:
                pass   # тоста нет — шаг это назовёт
            до = с.evaluate(ДОЖДАТЬСЯ_ТИШИНЫ)
            з = с.evaluate(ОКНО, [0, до])
            з["тост"] = с.evaluate("() => (document.querySelector('.m-toast') || {}).textContent || ''")
            итог["в_работу"] = з


# ── СТРОКИ «ЕЩЁ ВАРИАНТЫ» (письмо M1b) ─────────────────────────────────
# Четыре сценария на первой строке длинной панели: «+ в план», «Не то»
# (открыть плашку и закрыть повторным нажатием), выбор причины. Каждый —
# со своими замерами: была ли навигация, проезд прокрутки, повтор волны
# главной карточки, длинные кадры, скачок высоты списка и счётчик.
СТРОКА = ".today-pane:not([hidden]) .today-row"

ЗАМЕР_СТРОКИ = r"""([от, до, y0]) => {
  const з = window.__м;
  const кадры = з.кадры.filter(([т]) => т > от && т <= до).map(([, д]) => д);
  const ск = з.скролл.filter(([т]) => т >= от).map(([, y]) => y);
  const сп = з.список.filter(([т]) => т >= от && т <= до);
  let скачок = 0;
  for (let i = 1; i < сп.length; i++)
    if (сп[i][1] != null && сп[i - 1][1] != null) скачок = Math.max(скачок, Math.abs(сп[i][1] - сп[i - 1][1]));
  const сч = сп.map((р) => р[2]).filter((v) => v != null);
  const волна = з.анимации.filter(([т, , к]) => т >= от && /today-main/.test(к)).length;
  return {длинных: кадры.filter((д) => д > __ДЛ__).length, худший: кадры.length ? Math.round(Math.max(...кадры)) : 0,
          y_после: Math.round(scrollY), проезд: ск.length ? Math.round(Math.max(...ск.map((y) => Math.abs(y - y0)))) : 0,
          скачок: Math.round(скачок), счётчик: сч, волна: волна,
          анимаций: з.анимации.filter(([т]) => т >= от - 5 && т <= до).length,
          длиннее_потолка: з.анимации.filter(([т, д]) => т >= от - 5 && т <= до && д > __ПТ__).length,
          css_длиннее: document.getAnimations().map((а) => а.effect && а.effect.getTiming()).filter(Boolean)
            .map((т) => (+т.duration || 0) + (+т.delay || 0)).filter((д) => д > __ПТ__).length};
}""".replace("__ДЛ__", str(ДЛИННЫЙ_КАДР)).replace("__ПТ__", str(ПОТОЛОК_РЕДКО))


def _строка_действие(с, имя, что):
    """`что(ряд)` — нажатие. Навигация — по метке в окне: перезагрузка её стирает."""
    ряд = с.query_selector(СТРОКА)
    if not ряд:
        return None
    # мгновенно: у <html> scroll-behavior: smooth, и y0 иначе снимался бы посреди проезда
    ряд.evaluate("(р) => { const y = р.getBoundingClientRect().top + scrollY - innerHeight / 2;"
                 " window.scrollTo({top: y, behavior: 'instant'}); }")
    с.wait_for_function("() => new Promise((ок) => { const a = scrollY;"
                        " setTimeout(() => ок(scrollY === a), 120); })", timeout=5000)
    до_нажатия = с.evaluate("""(сел) => {
      window.__проба = 1;
      const р = document.querySelector(сел);
      const сч = document.querySelector('.today-tile[data-status="plan"] .v2-tile-num');
      return {y0: Math.round(scrollY), высота: Math.round(р.getBoundingClientRect().height),
              рядов: document.querySelectorAll(сел).length, id: р.dataset.idea,
              счёт: сч ? parseInt(сч.textContent.replace(/[^0-9]/g, '') || '0', 10) : null};
    }""", СТРОКА)
    навигаций = []
    обр = lambda f: навигаций.append(1) if f == с.main_frame else None
    с.on("framenavigated", обр)
    от = с.evaluate("() => { window.__м.идёт = true; return performance.now(); }")
    что(ряд)
    с.wait_for_timeout(150)
    try:
        с.wait_for_load_state("load", timeout=15000)
    except Exception:
        pass
    y_сразу = с.evaluate("() => Math.round(scrollY)")
    с.wait_for_timeout(1000)
    y_1с = с.evaluate("() => Math.round(scrollY)")
    до = с.evaluate(ДОЖДАТЬСЯ_ТИШИНЫ)
    тот_же = с.evaluate("() => window.__проба === 1")
    if not тот_же:
        от = 0   # новый документ: всё с его начала
    з = с.evaluate(ЗАМЕР_СТРОКИ, [от, до, до_нажатия["y0"]])
    с.evaluate("() => { if (window.__м) window.__м.идёт = null; }")
    с.remove_listener("framenavigated", обр)
    з.update(до_нажатия)
    з.update({"навигация": bool(навигаций) or not тот_же, "y_сразу": y_сразу, "y_1с": y_1с,
              "рядов_после": с.evaluate("(сел) => document.querySelectorAll(сел).length", СТРОКА),
              "тост": с.evaluate("() => [...document.querySelectorAll('.m-toast')].map((т) => т.textContent).join(' | ')"),
              "плашка_открыта": с.evaluate("""(id) => { const р = document.querySelector('.today-row[data-idea="' + id + '"]');
                  const п = р && р.querySelector('.today-reasons'); if (!п) return null;
                  return п.getBoundingClientRect().height > 4 && getComputedStyle(п).visibility !== 'hidden'; }""",
                                            до_нажатия["id"])})
    print("    %-12s навигация %s, y %d → %d → %d, проезд %d, волна %d, длинных %d, скачок %d, рядов %d → %d%s" % (
        имя, з["навигация"], з["y0"], з["y_сразу"], з["y_1с"], з["проезд"], з["волна"], з["длинных"],
        з["скачок"], з["рядов"], з["рядов_после"], (", счётчик %s→%s" % (з["счёт"], з["счётчик"][-1:] or "?"))
        if имя == "в план" else ""))
    return з


def _строки(с, итог):
    итог["строки"] = {
        "в план": _строка_действие(с, "в план", lambda р: р.query_selector("[data-act='plan']").click()),
        "не то: открыть": _строка_действие(с, "не то: открыть", lambda р: р.query_selector("[data-act='reject-open']").click()),
        "не то: закрыть": _строка_действие(с, "не то: закрыть", lambda р: р.query_selector("[data-act='reject-open']").click()),
    }
    # выбор причины: плашка открывается, затем нажата первая причина
    ряд = с.query_selector(СТРОКА)
    if ряд:
        ряд.query_selector("[data-act='reject-open']").click()
        с.wait_for_timeout(500)
    итог["строки"]["не то: причина"] = _строка_действие(
        с, "не то: причина", lambda р: р.query_selector("[data-act='reject']").click())


def замер(подлог=False, редко=False):
    """Каждая ширина — на СВОЕЙ копии базы: «Убрать» и «В работу» тратят
    находки, и вторая ширина на общей копии мерила бы пустой блок.
    `MAIN_DIR=<каталог>` поднимает стенд из другого дерева (замер «до»)."""
    from auth import create_token
    from playwright.sync_api import sync_playwright
    import check_content_ui as ч74
    import check_usage_balance as ч46
    # Копии и засев — ДО открытия браузера: засев идей зовёт asyncio.run,
    # а внутри sync_playwright уже крутится свой цикл событий
    копии = []
    for ширина, высота, касание in ШИРИНЫ:
        база, каталог = ч74._копия()
        копии.append((ширина, высота, касание, база, каталог))
        uid = ч74._база(база, "SELECT id FROM users WHERE email = ?", ПОЧТА)
        if not uid:
            raise ConnectionError("на копии стенда нет аккаунта %s — посейте стенд" % ПОЧТА)
        ч74._засеять_идеи(база)
        ч74._засеять_находки(база)
    токен = create_token(uid[0][0])
    if not МЕДЛЕННЫЙ["порт"]:
        МЕДЛЕННЫЙ["порт"] = _медленный_сервер()
    итог = {}
    try:
        with sync_playwright() as pw:
            бр = pw.chromium.launch()
            for ширина, высота, касание, база, каталог in копии:
                прежний = ч46.КОРЕНЬ
                if os.environ.get("MAIN_DIR"):
                    ч46.КОРЕНЬ = os.environ["MAIN_DIR"]   # только на подъём стенда
                try:
                    п, адрес = ч74._стенд(база)
                finally:
                    ч46.КОРЕНЬ = прежний
                try:
                    итог[ширина] = замер_ширины(бр, адрес, токен, ширина, высота, касание, редко, подлог)
                finally:
                    п.kill()
            бр.close()
    finally:
        for *_, каталог in копии:
            shutil.rmtree(каталог, ignore_errors=True)
    return итог


СКАЧОК_СПИСКА = 32   # px за кадр — потолок swap из M1


def оценить_строки(ширина, з):
    """Шаги письма M1b: строки «Ещё варианты», двойной клик, перезагрузка
    после действия, первый вход. Не собрано — ПРОПУСК, а не OK."""
    стр = з.get("строки") or {}
    if з.get("сбой_строк"):
        шаг("%d/строки: сбой" % ширина, False, з["сбой_строк"])
    for имя in ("в план", "не то: открыть", "не то: закрыть", "не то: причина"):
        в = стр.get(имя)
        if not в:
            шаг("%d/строка %s" % (ширина, имя), False, "строки нет", собрано=0)
            continue
        уходит = имя in ("в план", "не то: причина")
        сдвиг = max(abs(в["y_сразу"] - в["y0"]), abs(в["y_1с"] - в["y0"]), в["проезд"])
        шаг("%d/строка %s: без перезагрузки" % (ширина, имя), not в["навигация"],
            "навигация %s" % в["навигация"])
        шаг("%d/строка %s: прокрутка" % (ширина, имя), сдвиг <= (в["высота"] if уходит else 0),
            "y %d → %d → %d, проезд %d при строке %d px" % (в["y0"], в["y_сразу"], в["y_1с"], в["проезд"], в["высота"]))
        шаг("%d/строка %s: волна не повторилась" % (ширина, имя), в["волна"] == 0, "анимаций главной %d" % в["волна"])
        шаг("%d/строка %s: кадры" % (ширина, имя), в["длинных"] <= 1,
            "длиннее %d мс: %d, худший %d мс" % (ДЛИННЫЙ_КАДР, в["длинных"], в["худший"]))
        шаг("%d/строка %s: скачок высоты" % (ширина, имя), в["скачок"] <= СКАЧОК_СПИСКА,
            "наибольший за кадр %d px (потолок %d)" % (в["скачок"], СКАЧОК_СПИСКА))
        if уходит:
            шаг("%d/строка %s: строка ушла" % (ширина, имя), в["рядов_после"] == в["рядов"] - 1,
                "рядов %d → %d" % (в["рядов"], в["рядов_после"]))
        if имя == "в план":
            сч = в["счётчик"]
            ждём = (в["счёт"] or 0) + 1
            шаг("%d/строка в план: счётчик" % ширина, bool(сч) and сч[-1] == ждём and max(сч) <= ждём,
                "было %s, кадры %s…%s, ждём %d" % (в["счёт"], сч[:1], сч[-1:], ждём), собрано=len(сч))
            шаг("%d/строка в план: тост" % ширина, "в плане" in (в["тост"] or ""), "«%s»" % в["тост"])
        if имя == "не то: открыть":
            шаг("%d/плашка открылась" % ширина, в["плашка_открыта"] is True, str(в["плашка_открыта"]))
        if имя == "не то: закрыть":
            шаг("%d/плашка закрылась повторным нажатием" % ширина, в["плашка_открыта"] is False,
                str(в["плашка_открыта"]))
    д = з.get("двойной")
    шаг("%d/двойной клик: один запрос" % ширина, bool(д) and д["запросов"] == 1,
        "запросов %s" % (д or {}).get("запросов"), собрано=1 if д else 0)
    п = з.get("после")
    if п:
        шаг("%d/после перезагрузки: прокрутка до первого кадра" % ширина,
            п["флаг"] and п["первый_кадр"] == п["итог"] and п["проезд"] == 0
            and п["сохранено"] is not None and abs(п["итог"] - п["сохранено"]) <= 2,
            "сохранено %s, первый кадр %s, итог %s, проезд %d" % (п["сохранено"], п["первый_кадр"], п["итог"], п["проезд"]))
        шаг("%d/после перезагрузки: волны нет" % ширина, п["волна"] == 0, "анимаций появления %d" % п["волна"])
    else:
        шаг("%d/после перезагрузки" % ширина, False, "главной нет", собрано=0)
    вх = з.get("вход")
    if вх:
        шаг("%d/первый вход: волна есть" % ширина, вх["волна"] >= 1, "анимаций главной %d" % вх["волна"])
        шаг("%d/первый вход: без вспышки" % ширина, not вх["вспышка"] and вх["видна_до_волны"] == 0,
            "кадров до волны %d, из них главная видна %d, вспышка %s" % (вх["кадров_до_волны"], вх["видна_до_волны"],
                                                                     вх["вспышка"]), собрано=вх["кадров_до_волны"])


def оценить(итог, редко=False):
    for ширина, з in итог.items():
        print("— %d%s" % (ширина, " · reduced-motion" if редко else ""))
        шаг("%d/motion подключён" % ширина, з["motion"])
        if редко:
            все = [з["загрузка"]] + з["переключения"] + [з[к] for к in ("убрать", "в_работу") if к in з]
            все += [в for в in (з.get("строки") or {}).values() if в]
            длиннее = sum(в["длиннее_потолка"] + в["css_длиннее"] for в in все)
            анимаций = sum(в["анимаций"] for в in все)
            шаг("%d/reduced: всё ≤ %d мс" % (ширина, ПОТОЛОК_РЕДКО), длиннее == 0,
                "анимаций %d, длиннее потолка %d" % (анимаций, длиннее), собрано=анимаций)
            continue
        оценить_строки(ширина, з)
        if ТОЛЬКО_СТРОКИ:
            continue
        зг = з["загрузка"]
        шаг("%d/загрузка: кадры" % ширина, зг["длинных"] <= 1,
            "кадров %d, длиннее %d мс: %d, худший %d мс" % (зг["кадров"], ДЛИННЫЙ_КАДР, зг["длинных"], зг["худший"]),
            собрано=зг["анимаций"])
        пк = з["переключения"]
        разница = abs(з["высоты_панелей"][0] - з["высоты_панелей"][1]) if len(з["высоты_панелей"]) == 2 else 0
        шаг("%d/переключение: кадры" % ширина, all(в["длинных"] <= 1 for в in пк),
            "длинных по действиям %s, худший %d мс" % ([в["длинных"] for в in пк], max(в["худший"] for в in пк)),
            собрано=len(пк))
        шаг("%d/переключение: CLS" % ширина, all(в["cls"] == 0 for в in пк),
            "CLS %s (со сдвигами после ввода: макс %.4f)" % (sorted({в["cls"] for в in пк}), max(в["cls_все"] for в in пк)),
            собрано=len(пк))
        шаг("%d/переключение: без мигания" % ширина,
            all(в["мин_высота"] and в["пустых"] == 0 for в in пк) and all(в["видна"] for в in пк),
            "мин. высота ящика %s, пустых кадров %d из %d" % (min(в["мин_высота"] or 0 for в in пк),
                                                            sum(в["пустых"] for в in пк), sum(в["проб_ящика"] for в in пк)),
            собрано=sum(в["проб_ящика"] for в in пк))
        скачок = max(в["скачок"] for в in пк)
        # порог — половина разницы, но не ниже 32 px (уровень swap, принятый в M1):
        # строки стали ниже на межстрочный зазор (M1b), разница панелей на 390
        # 59 px, и «половина» 29.5 px краснела бы на том же самом swap
        шаг("%d/переключение: скачок" % ширина, скачок <= max(разница / 2, СКАЧОК_СПИСКА),
            "наибольший за кадр %d px при разнице высот панелей %d px %s" % (скачок, разница, з["высоты_панелей"]),
            собрано=0 if разница < 48 else len(пк))
        if "убрать" in з:
            у = з["убрать"]
            шаг("%d/убрать: уход и схлопывание" % ширина,
                у["длинных"] <= 1 and у["рядов_после"] == у["рядов_до"] - 1 and у["тот_же_документ"],
                "кадров длиннее %d мс: %d, рядов %d → %d, худший %d мс" % (ДЛИННЫЙ_КАДР, у["длинных"], у["рядов_до"],
                                                                           у["рядов_после"], у["худший"]))
        else:
            шаг("%d/убрать: уход и схлопывание" % ширина, False, "находок нет", собрано=0)
        if "в_работу" in з:
            в = з["в_работу"]
            шаг("%d/в работу: тост" % ширина, в["длинных"] <= 1 and bool(в["тост"]),
                "тост «%s», кадров длиннее %d мс: %d" % (в["тост"], ДЛИННЫЙ_КАДР, в["длинных"]))
        else:
            шаг("%d/в работу: тост" % ширина, False, "находок нет", собрано=0)


# Подлоги блока 3 письма M1b: замены в разметке и чем доказан каждый
ПОДЛОГИ_СТРОК = [
    ("перезагрузка в «+ в план»",
     [("действиеСтроки(к);\n      return;",
       "действиеСтроки(к).then(function () { location.reload(); });\n      return;")],
     "навигация после «+ в план»",
     lambda з: з["строки"]["в план"]["навигация"] if з.get("строки", {}).get("в план") else None),
    ("волна после действия",
     [("if (!после && !корень.classList.contains('m-nowave')) {",
       "if (!корень.classList.contains('m-nowave')) {")],
     "анимаций появления после перезагрузки",
     lambda з: (з.get("после") or {}).get("волна")),
    ("повторное нажатие не заблокировано",
     [("if (!ряд || ряд.dataset.busy) return;", "if (!ряд) return;"),
      ("кнопки.forEach(function (б) { б.disabled = true; });", "")],
     "запросов на двойной клик",
     lambda з: (з.get("двойной") or {}).get("запросов")),
    ("класс-гейт снят из <head>",
     [("h.classList.add('m-wait');", "")],
     "кадров до волны, где главная видна",
     lambda з: (з.get("вход") or {}).get("видна_до_волны")),
]
ДОКАЗАТЕЛЬСТВА["строки M1b"] = "по каждому подлогу — своё число: навигация, волна, запросы, видимость до волны"


def контроль_строк():
    """Каждый подлог — отдельный прогон на 1920; шаги обязаны покраснеть,
    а доказательство — измениться против чистого прогона."""
    global ШИРИНЫ
    ШИРИНЫ = ШИРИНЫ[:1]
    чисто = замер()[ШИРИНЫ[0][0]]
    найдено = 0
    for имя, замены, что, доказ in ПОДЛОГИ_СТРОК:
        ЗАМЕНЫ[:] = замены
        шаги.clear()
        try:
            з = замер()[ШИРИНЫ[0][0]]
        finally:
            ЗАМЕНЫ[:] = []
        print("ПОДЛОГ: %s" % имя)
        оценить_строки(ШИРИНЫ[0][0], з)
        плохо = [н for н, и, _ in шаги if и == "ПЛОХО"]
        было, стало = доказ(чисто), доказ(з)
        ок = bool(плохо) and было != стало
        найдено += ок
        print("  ДОКАЗАТЕЛЬСТВО: %s %s → %s; покраснело шагов %d %s" % (что, было, стало, len(плохо), плохо[:3]))
        print("  ПОДЛОГ", "НАЙДЕН" if ок else "НЕ НАЙДЕН")
    print("ИТОГ КОНТРОЛЯ: найдено %d из %d" % (найдено, len(ПОДЛОГИ_СТРОК)))
    return 0 if найдено == len(ПОДЛОГИ_СТРОК) else 1


def main():
    if "--контроль-строк" in sys.argv:
        return контроль_строк()
    if ТОЛЬКО_СТРОКИ:
        редко = "--редко" in sys.argv
        оценить(замер(редко=редко), редко=редко)
        плохих = sum(1 for _, и, _ in шаги if и == "ПЛОХО")
        print("ИТОГ: шагов %d, плохих %d" % (len(шаги), плохих))
        return 1 if плохих else 0
    if "--контроль" in sys.argv:
        print("КОНТРОЛЬ: фиксация высоты в swap вырезана из motion.js")
        чисто = замер()
        подлог = замер(подлог=True)
        оценить(подлог)
        до = max(в["скачок"] for з in чисто.values() for в in з["переключения"])
        после = max(в["скачок"] for з in подлог.values() for в in з["переключения"])
        print("ДОКАЗАТЕЛЬСТВО: наибольший скачок высоты за кадр %d px → %d px" % (до, после))
        пойман = any(и == "ПЛОХО" and "скачок" in имя for имя, и, _ in шаги)
        print("ПОДЛОГ", "НАЙДЕН" if пойман and после > до else "НЕ НАЙДЕН")
        return 0 if пойман and после > до else 1
    оценить(замер())
    оценить(замер(редко=True), редко=True)
    плохих = sum(1 for _, и, _ in шаги if и == "ПЛОХО")
    пропусков = sum(1 for _, и, _ in шаги if и == "ПРОПУСК")
    print("ИТОГ: шагов %d, плохих %d, пропусков %d" % (len(шаги), плохих, пропусков))
    return 1 if плохих else (2 if пропусков else 0)


if __name__ == "__main__":
    sys.exit(main())
