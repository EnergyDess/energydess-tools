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
  const з = window.__м = {кадры: [], сдвиги: [], анимации: [], ящик: [], идёт: null};
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
    з.анимации.push([performance.now(), (+тт.duration || 0) + (+тт.delay || 0)]);
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


def замер_ширины(бр, адрес, токен, ширина, высота, касание, редко, подлог):
    к = бр.new_context(viewport={"width": ширина, "height": высота}, has_touch=касание, is_mobile=касание,
                       reduced_motion="reduce" if редко else "no-preference")
    к.add_cookies([{"name": "access_token", "value": токен, "url": адрес}])
    к.add_init_script(САМПЛЕР)
    if подлог:
        к.route("**/motion.js*", _подложить)
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
    for i in range(ПОВТОРОВ):
        for тип in ("shorts", "long"):
            з = _действие(с, lambda: с.click("#today-type-" + тип))
            з["видна"] = с.evaluate("(т) => !document.querySelector('.today-pane[data-pane=\"' + т + '\"]').hidden", тип)
            перекл.append(з)
    итог["переключения"] = перекл
    if not подлог:
        try:
            _находки(с, итог)
        except Exception as e:   # прежний код («до») перезагружает страницу на «Убрать»
            итог["сбой_находок"] = type(e).__name__
    к.close()
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


def оценить(итог, редко=False):
    for ширина, з in итог.items():
        print("— %d%s" % (ширина, " · reduced-motion" if редко else ""))
        шаг("%d/motion подключён" % ширина, з["motion"])
        if редко:
            все = [з["загрузка"]] + з["переключения"] + [з[к] for к in ("убрать", "в_работу") if к in з]
            длиннее = sum(в["длиннее_потолка"] + в["css_длиннее"] for в in все)
            анимаций = sum(в["анимаций"] for в in все)
            шаг("%d/reduced: всё ≤ %d мс" % (ширина, ПОТОЛОК_РЕДКО), длиннее == 0,
                "анимаций %d, длиннее потолка %d" % (анимаций, длиннее), собрано=анимаций)
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
        шаг("%d/переключение: скачок" % ширина, скачок <= разница / 2,
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


def main():
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
