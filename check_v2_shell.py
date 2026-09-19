"""КАРКАС v2 НА СТРАНИЦАХ ЗАЛОГИНЕННОЙ ЧАСТИ (BACKLOG №352, письмо 2, блок 2).

ПРОВЕРКА, код 1 при находке, 2 — замерить нечем (стенда нет, экранов ноль).

ЧТО СПРАШИВАЕТСЯ:
  1. КАРКАС РОВНО ОДИН. Каждая страница из роутов, открытая вошедшим
     (список ВЫВОДИТСЯ — `check_hover.экраны_из_роутов`, перечня нет):
     `.v2-shell` один, `.v2-side` одно, второго бокового меню нет
     (`.nut-nav` — прежнее меню дневника), подвал внутри колонки
     содержимого, а не под меню.
  2. ССЫЛКИ бокового меню и меню аватара отвечают 200.
  3. «АДМИН-ПАНЕЛЬ» в меню аватара — только администратору: живой вход
     соседом (не админ) и отрисовка шаблона шапки в процессе.
  4. «ИНСТРУМЕНТЫ»: открывается наведением и кликом, стрелка ведёт
     по пунктам, Esc закрывает и возвращает фокус на кнопку.
  5. ПОЛОСА: «Свернуть» переключает и переживает перезагрузку.
  6. ПОСЛЕДНИЕ: заход в A, B, C — порядок C, B, A, не больше трёх;
     при повреждённом и при недоступном хранилище список пуст и ошибок
     в консоли нет.

КЛЮЧИ:
  --контроль   три подлога, у каждого своё доказательство:
                 меню    — вернуть второе боковое меню (`.nut-nav`)
                           на страницу дневника → проверка 1 его находит;
                 админ   — снять условие `user.is_admin` в шаблоне шапки
                           → «Админ-панель» у не-админа;
                 полоса  — не сохранять состояние → после перезагрузки
                           меню развёрнуто.

  --приёмка    блок 3: за краем окна, пересечения меню, верхней строки,
               шапки и кнопок — 390, 1920, 2560, ВИДИМЫЙ браузер (ширина)
  --снимки     кадры всех страниц на 390 и 1920 в review_screenshots/redesign-shell/
  --кадры      МЕРКА: p95 кадра при прокрутке Enshrouded и аптечки (HOVER_BASE — стенд)

Основной прогон — НЕВИДИМЫЙ браузер: состав дерева и поведение.
"""
import os
import re
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

находок = 0
пропусков = 0


def шаг(имя, условие, подробность="", собрано=None):
    """`собрано` — сколько собрано для замера; ноль — ПРОПУСК (проверка 33)."""
    global находок, пропусков
    if собрано is not None and not собрано:
        пропусков += 1
        print("  %-7s %s — сбор пуст, мерить нечего" % ("ПРОПУСК", имя))
        return
    if not условие:
        находок += 1
    print("  %-4s %s%s" % ("OK" if условие else "ПЛОХО", имя,
                           (" — " + подробность) if подробность else ""))


ЗАМЕР_КАРКАСА = """() => {
  const каркас = document.querySelectorAll('.v2-shell').length;
  // образцы витрины `/admin/design-v2` — не меню страницы: считается
  // меню, стоящее в самом каркасе
  const меню = document.querySelectorAll('.v2-shell > .v2-side').length;
  const гость = !document.querySelector('.site-header .avatar-wrap');
  const второе = document.querySelectorAll('.nut-nav, .wkp-back').length;
  const подвал = document.querySelector('.site-footer');
  return {каркас, меню, второе, гость,
          подвал_в_колонке: подвал ? !!подвал.closest('.v2-shell-main') : null};
}"""


# Страницы вошедшего, у которых каркаса нет ОСОЗНАННО (`shell_off` в роуте),
# с причиной у каждой. Новая страница без каркаса и без строки здесь — находка.
ОСОЗНАННО_БЕЗ_КАРКАСА = {
    "/botamin": "витрина тестового задания, не часть залогиненной части",
}


def страницы_каркаса():
    """Пути страниц, которые вошедший видит сам (без перенаправления)."""
    экраны = ch.экраны_из_роутов()
    return sorted({п for п, имя, вход, подг in экраны if подг is None})


def вход_как(стр, почта, пароль):
    прежние = ch.ПОЧТА, ch.ПАРОЛЬ
    ch.ПОЧТА, ch.ПАРОЛЬ = почта, пароль
    try:
        ch._войти(стр)
    finally:
        ch.ПОЧТА, ch.ПАРОЛЬ = прежние


def проверить(подлог=None, печать=True):
    """Возвращает словарь сырых замеров. `подлог` — имя подлога страницы."""
    from playwright.sync_api import sync_playwright
    замеры = {}
    with sync_playwright() as p:
        бр = p.chromium.launch()
        к = бр.new_context(viewport={"width": 1440, "height": 900})
        ошибки = []
        if подлог == "меню":
            к.add_init_script("""addEventListener('DOMContentLoaded', () => {
                if (location.pathname !== '/nutrition') return;
                const n = document.createElement('nav'); n.className = 'nut-nav';
                document.querySelector('.nut-app').appendChild(n); });""")
        if подлог == "полоса":
            к.add_init_script("""(() => { const s = Storage.prototype.setItem;
                Storage.prototype.setItem = function (k, v) { if (k === 'v2-rail') return; return s.call(this, k, v); }; })();""")
        стр = к.new_page()
        стр.on("console", lambda m: ошибки.append(m.text) if m.type == "error" else None)
        стр.on("pageerror", lambda e: ошибки.append(str(e)))
        ch._войти(стр)

        # 1. каркас на каждой странице
        пути = страницы_каркаса()
        итог = []
        for путь in пути:
            ответ = стр.goto(ch.БАЗА + путь, wait_until="domcontentloaded")
            конечный = re.sub(r"^https?://[^/]+", "", стр.url).split("?")[0]
            if конечный != путь:
                итог.append((путь, None, f"ушла на {конечный}"))
                continue
            итог.append((путь, стр.evaluate(ЗАМЕР_КАРКАСА), ответ.status if ответ else None))
        замеры["страницы"] = итог

        # 2. ссылки меню и аватара
        стр.goto(ch.БАЗА + "/hh", wait_until="domcontentloaded")
        ссылки = стр.evaluate("""() => [...document.querySelectorAll('.v2-side a[href], .avatar-dropdown a[href]')]
            .map(a => a.getAttribute('href')).filter(h => h.startsWith('/'))""")
        ответы = {}
        for h in sorted(set(ссылки)):
            if h == "/logout":
                continue      # выход разлогинит пробу: проверяется последним отдельным запросом
            r = стр.request.get(ch.БАЗА + h, max_redirects=0)
            ответы[h] = r.status
        замеры["ссылки"] = ответы
        замеры["админ_у_админа"] = стр.locator(".avatar-dropdown a[href^='/admin']").count()
        замеры["подпись_админа"] = (стр.locator(".avatar-dropdown a[href^='/admin']").first.inner_text().strip()
                                    if замеры["админ_у_админа"] else "")

        # 4. «Инструменты»
        кн = стр.locator("#v2-tools-btn")
        стр.mouse.move(1000, 600)
        кн.hover()
        стр.wait_for_timeout(150)
        наведение = стр.evaluate("!document.getElementById('v2-tools-pop').hidden")
        стр.mouse.move(1000, 600)
        стр.wait_for_timeout(400)
        ушло = стр.evaluate("document.getElementById('v2-tools-pop').hidden")
        кн.focus()
        стр.keyboard.press("Enter")
        клик = стр.evaluate("!document.getElementById('v2-tools-pop').hidden")
        стр.keyboard.press("ArrowDown")
        стр.keyboard.press("ArrowDown")
        стрелки = стр.evaluate("""() => { const п = [...document.querySelectorAll('#v2-tools-pop [role=menuitem]')];
            return п.indexOf(document.activeElement); }""")
        стр.keyboard.press("Escape")
        esc = стр.evaluate("""() => [document.getElementById('v2-tools-pop').hidden,
            document.activeElement === document.getElementById('v2-tools-btn')]""")
        замеры["инструменты"] = {"наведение": наведение, "ушло": ушло, "клик": клик,
                                 "стрелки": стрелки, "esc_закрыл": esc[0], "фокус_вернулся": esc[1]}

        # 5. полоса
        стр.evaluate("try{localStorage.removeItem('v2-rail')}catch(e){}")
        стр.reload(wait_until="domcontentloaded")
        до = стр.evaluate("document.documentElement.classList.contains('v2-rail')")
        стр.click("#v2-side-fold")
        после_клика = стр.evaluate("document.documentElement.classList.contains('v2-rail')")
        ширина = стр.evaluate("document.getElementById('v2-side').getBoundingClientRect().width")
        стр.reload(wait_until="domcontentloaded")
        после_перезагрузки = стр.evaluate("document.documentElement.classList.contains('v2-rail')")
        подсказка = стр.evaluate("document.getElementById('v2-tools-btn').title")
        if после_перезагрузки:
            стр.click("#v2-side-fold")     # вернуть развёрнутым
        замеры["полоса"] = {"до": до, "после_клика": после_клика, "ширина": ширина,
                            "после_перезагрузки": после_перезагрузки, "подсказка": подсказка}

        # 6. последние
        стр.evaluate("try{localStorage.removeItem('v2-recent')}catch(e){}")
        for путь in ("/hh", "/medkit", "/enshrouded"):
            стр.goto(ch.БАЗА + путь, wait_until="domcontentloaded")
        стр.goto(ch.БАЗА + "/", wait_until="domcontentloaded")
        порядок = стр.evaluate("[...document.querySelectorAll('#v2-recent [data-recent]:not([hidden])')].map(e => e.dataset.recent)")
        стр.goto(ch.БАЗА + "/nutrition", wait_until="domcontentloaded")
        стр.goto(ch.БАЗА + "/", wait_until="domcontentloaded")
        четыре = стр.evaluate("[...document.querySelectorAll('#v2-recent [data-recent]:not([hidden])')].map(e => e.dataset.recent)")
        ошибки.clear()
        стр.evaluate("localStorage.setItem('v2-recent', '{битое')")
        стр.reload(wait_until="domcontentloaded")
        битое = стр.evaluate("document.querySelectorAll('#v2-recent [data-recent]:not([hidden])').length")
        ош_битое = list(ошибки)
        замеры["последние"] = {"порядок": порядок, "четыре": четыре, "битое": битое, "ошибки_битое": ош_битое}
        бр.close()

        # 6б. хранилище недоступно вовсе
        бр = p.chromium.launch()
        к = бр.new_context(viewport={"width": 1440, "height": 900})
        к.add_init_script("""Object.defineProperty(window, 'localStorage', {get() { throw new Error('заблокировано'); }});""")
        стр = к.new_page()
        ош2 = []
        стр.on("pageerror", lambda e: ош2.append(str(e)))
        ch._войти(стр)
        стр.goto(ch.БАЗА + "/", wait_until="domcontentloaded")
        нет = стр.evaluate("document.querySelectorAll('#v2-recent [data-recent]:not([hidden])').length")
        замеры["без_хранилища"] = {"видно": нет, "ошибки": [е for е in ош2 if "v2" in е or "recent" in е or "localStorage" in е]}
        бр.close()

        # 3. не-админ, живым входом соседа
        бр = p.chromium.launch()
        стр = бр.new_context(viewport={"width": 1440, "height": 900}).new_page()
        import make_local_user as мл
        вход_как(стр, мл.EMAIL_СОСЕД, мл.PASSWORD_СОСЕД)
        стр.goto(ch.БАЗА + "/hh", wait_until="domcontentloaded")
        замеры["админ_у_соседа"] = стр.locator(".avatar-dropdown a[href^='/admin']").count()
        бр.close()
    замеры["шаблон"] = админ_в_шаблоне(подлог == "админ")
    if печать:
        печатать(замеры)
    return замеры


def админ_в_шаблоне(снять_условие=False):
    """Отрисовка `_header.html` в процессе для админа и не-админа: сколько
    раз стоит ссылка на админ-панель. `снять_условие` — подлог: шаблон
    без `{% if user.is_admin %}`."""
    import main
    from types import SimpleNamespace as NS
    исходник = open(os.path.join("templates", "_header.html"), encoding="utf-8").read()
    if снять_условие:
        исходник = исходник.replace("{% if user.is_admin %}", "{% if true %}")
    шаблон = main.templates.env.from_string(исходник)
    запрос = NS(url=NS(path="/hh"), cookies={})
    итог = {}
    for кто, админ in (("админ", True), ("не-админ", False)):
        u = NS(is_admin=админ, is_verified=True, email="x@local.dev", display_name="Икс",
               avatar_updated_at=None, id=1)
        html = шаблон.render(user=u, request=запрос)
        итог[кто] = html.count('href="/admin')
    return итог


def печатать(з):
    print("1. КАРКАС НА СТРАНИЦАХ")
    стр = [x for x in з["страницы"] if x[1] is not None]
    for путь, м, код in з["страницы"]:
        if м is None:
            print(f"  --   {путь}: {код}, не страница вошедшего")
            continue
        if путь in ОСОЗНАННО_БЕЗ_КАРКАСА:
            print(f"  --   {путь}: без каркаса осознанно — {ОСОЗНАННО_БЕЗ_КАРКАСА[путь]}")
            шаг(f"{путь}: каркаса нет", м["каркас"] == 0)
            continue
        if м["гость"]:
            # страницы входа (сброс пароля, ожидание письма) рисуются
            # гостевой шапкой даже вошедшему: пользователя в контексте нет
            print(f"  --   {путь}: страница входа, гостевая шапка — каркаса не должно быть")
            шаг(f"{путь}: каркаса нет", м["каркас"] == 0)
            continue
        хорошо = м["каркас"] == 1 and м["меню"] == 1 and м["второе"] == 0 and м["подвал_в_колонке"] in (True, None)
        шаг(f"{путь}: каркас {м['каркас']}, меню {м['меню']}, второе меню {м['второе']}, подвал в колонке {м['подвал_в_колонке']}",
            хорошо)
    шаг("страниц вошедшего проверено", len(стр) >= 10, f"{len(стр)}", собрано=len(стр))
    print("2. ССЫЛКИ МЕНЮ И АВАТАРА")
    for h, код in з["ссылки"].items():
        шаг(f"{h} отвечает {код}", код == 200)
    шаг("ссылок собрано", len(з["ссылки"]) >= 3, f"{len(з['ссылки'])}", собрано=len(з["ссылки"]))
    print("3. АДМИН-ПАНЕЛЬ")
    шаг(f"у администратора есть «{з['подпись_админа']}»", з["админ_у_админа"] == 1 and "Админ-панель" in з["подпись_админа"])
    шаг("у соседа (не админ) ссылки нет — живой вход", з["админ_у_соседа"] == 0, f"{з['админ_у_соседа']}")
    шаг("шаблон: у админа ссылка есть, у не-админа нет",
        з["шаблон"]["админ"] == 1 and з["шаблон"]["не-админ"] == 0, str(з["шаблон"]))
    print("4. «ИНСТРУМЕНТЫ»")
    и = з["инструменты"]
    шаг("открывается наведением", и["наведение"])
    шаг("закрывается, когда указатель ушёл", и["ушло"])
    шаг("открывается кликом (Enter)", и["клик"])
    шаг("стрелка ведёт по пунктам", и["стрелки"] == 1, f"фокус на пункте {и['стрелки']}")
    шаг("Esc закрывает", и["esc_закрыл"])
    шаг("фокус вернулся на «Инструменты»", и["фокус_вернулся"])
    print("5. ПОЛОСА")
    п = з["полоса"]
    шаг("до нажатия меню развёрнуто", not п["до"])
    шаг(f"«Свернуть» сворачивает — ширина меню {п['ширина']:.0f}", п["после_клика"] and п["ширина"] < 100)
    шаг("полоса пережила перезагрузку", п["после_перезагрузки"])
    шаг("у пункта в полосе есть подсказка с названием", п["подсказка"] == "Инструменты", п["подсказка"])
    print("6. ПОСЛЕДНИЕ")
    по = з["последние"]
    шаг("после A, B, C порядок C, B, A", по["порядок"] == ["enshrouded", "medkit", "hh"], str(по["порядок"]))
    шаг("после четвёртого — не больше трёх, свежий сверху", по["четыре"] == ["nutrition", "enshrouded", "medkit"], str(по["четыре"]))
    шаг("повреждённое хранилище — список пуст", по["битое"] == 0, f"{по['битое']}")
    шаг("повреждённое хранилище — ошибок в консоли нет", not по["ошибки_битое"], str(по["ошибки_битое"][:2]))
    б = з["без_хранилища"]
    шаг("хранилище недоступно — список пуст, ошибок каркаса нет", б["видно"] == 0 and not б["ошибки"], str(б))


ДОКАЗАТЕЛЬСТВА = {
    "меню": "элементов второго меню на /nutrition: 0 → 1",
    "админ": "ссылок на админ-панель у не-админа в отрисованном шаблоне: 0 → 1",
    "полоса": "полоса после перезагрузки: есть → нет",
}


def контроль():
    global находок
    print("ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ КАРКАСА v2")
    з0 = проверить(печать=False)
    итог = 0
    for имя in ("меню", "админ", "полоса"):
        находок = 0
        import contextlib
        import io
        буф = io.StringIO()
        with contextlib.redirect_stdout(буф):
            з = проверить(подлог=имя)
        if имя == "меню":
            ищем = lambda зз: next((м["второе"] for п, м, _ in зз["страницы"] if п == "/nutrition" and м), None)
        elif имя == "админ":
            ищем = lambda зз: зз["шаблон"]["не-админ"]
        else:
            ищем = lambda зз: зз["полоса"]["после_перезагрузки"]
        до, после = ищем(з0), ищем(з)
        состоялся = до != после
        print(f"\n--- подлог «{имя}» ---\n   доказательство: {ДОКАЗАТЕЛЬСТВА[имя]}: {до} → {после}"
              f" — {'СОСТОЯЛСЯ' if состоялся else 'НЕ СОСТОЯЛСЯ'}")
        print(f"   проба: находок {находок} — {'НАЙДЕН' if находок else 'НЕ НАЙДЕН'}")
        for s in буф.getvalue().splitlines():
            if "ПЛОХО" in s:
                print("     " + s.strip())
        if not (состоялся and находок):
            итог = 1
    print("\nКОНТРОЛЬ:", "3 ПОДЛОГА ИЗ 3 НАЙДЕНЫ" if итог == 0 else "ПРОВАЛЕН")
    return итог


ЗАМЕР_ПРИЁМКИ = """() => {
  const ш = document.documentElement.clientWidth;
  const обрезан = э => { for (let п = э.parentElement; п && п !== document.body; п = п.parentElement) {
      const s = getComputedStyle(п); if (['hidden','auto','scroll','clip'].includes(s.overflowX)) return true; }
      return false; };
  const за = [];
  for (const э of document.querySelectorAll('body *')) {
    if (!э.checkVisibility || !э.checkVisibility({checkOpacity: true, checkVisibilityCSS: true})) continue;
    const r = э.getBoundingClientRect();
    if (!r.width || !r.height) continue;
    if ((r.right > ш + 1 || r.left < -1) && !обрезан(э) && getComputedStyle(э).position !== 'fixed')
      за.push(э.tagName.toLowerCase() + '.' + [...э.classList].slice(0, 2).join('.') + ' ' + Math.round(r.left) + '…' + Math.round(r.right));
  }
  const меню = document.querySelector('.v2-shell > .v2-side');
  const колонка = document.querySelector('.v2-shell-main');
  const верх = document.querySelector('.v2-top-bar');
  const шапка = document.querySelector('.v2-page-head.is-page');
  const мв = меню && меню.checkVisibility({checkVisibilityCSS: true}) ? меню.getBoundingClientRect() : null;
  const к = колонка.getBoundingClientRect(), в = верх.getBoundingClientRect();
  const ш2 = шапка ? шапка.getBoundingClientRect() : null;
  const заг = шапка ? шапка.querySelector('.v2-head-title').getBoundingClientRect() : null;
  const кн = шапка ? [...шапка.querySelectorAll('.v2-head-actions > *')].map(e => e.getBoundingClientRect()) : [];
  const пересек = (a, b) => a.left < b.right - 1 && b.left < a.right - 1 && a.top < b.bottom - 1 && b.top < a.bottom - 1;
  return {за: за.slice(0, 5), число: за.length, прокрутка: document.documentElement.scrollWidth - ш,
          меню_колонка: мв ? Math.round(к.left - мв.right) : null,
          верх_шапка: ш2 ? Math.round(ш2.top - в.bottom) : null,
          кнопки_на_заголовке: заг ? кн.filter(b => b.width && пересек(b, заг)).length : 0};
}"""


def приёмка():
    """Блок 3: каждая страница вошедшего на 390, 1920, 2560 — за краем окна
    ноль элементов, меню и колонка содержимого не пересекаются, шапка
    страницы ниже верхней строки, кнопки действий не налезают на заголовок.
    Браузер ВИДИМЫЙ: это замер ширины (§6.0.3)."""
    from playwright.sync_api import sync_playwright
    пути = страницы_каркаса()
    with sync_playwright() as p:
        for ширина in (390, 1920, 2560):
            print(f"ширина {ширина}")
            бр = p.chromium.launch(headless=False)
            к = бр.new_context(viewport={"width": ширина, "height": 900},
                               has_touch=ширина < 600, is_mobile=ширина < 600)
            стр = к.new_page()
            ch._войти(стр)
            собрано = 0
            for путь in пути:
                стр.goto(ch.БАЗА + путь, wait_until="networkidle")
                if re.sub(r"^https?://[^/]+", "", стр.url).split("?")[0] != путь:
                    continue
                if not стр.locator(".v2-shell").count():
                    continue
                стр.wait_for_timeout(300)
                м = стр.evaluate(ЗАМЕР_ПРИЁМКИ)
                собрано += 1
                шаг(f"{ширина} {путь}: за краем 0, прокрутка вбок 0",
                    м["число"] == 0 and м["прокрутка"] <= 0,
                    f"за краем {м['число']} {м['за']}, прокрутка {м['прокрутка']}")
                if м["меню_колонка"] is not None:
                    шаг(f"{ширина} {путь}: меню и колонка не пересекаются", м["меню_колонка"] >= 0, f"{м['меню_колонка']}")
                if м["верх_шапка"] is not None:
                    шаг(f"{ширина} {путь}: шапка страницы ниже верхней строки", м["верх_шапка"] >= 0, f"{м['верх_шапка']}")
                    шаг(f"{ширина} {путь}: кнопки не налезают на заголовок", м["кнопки_на_заголовке"] == 0,
                        f"{м['кнопки_на_заголовке']}")
            шаг(f"{ширина}: страниц с каркасом замерено", собрано >= 10, f"{собрано}", собрано=собрано)
            бр.close()


def кадры():
    """p95 интервала кадров при прокрутке колесом — Enshrouded и аптечка,
    самые тяжёлые страницы. МЕРКА, код 0. Адрес стенда — `HOVER_BASE`,
    так тот же замер снимается на стенде «до» каркаса. Браузер видимый:
    невидимый отрисовку кадров не выполняет по-настоящему."""
    from playwright.sync_api import sync_playwright
    сэмплер = """() => { const д = []; let п = performance.now(); window.__кадры = д; window.__жив = true;
      function т(t) { д.push(t - п); п = t; if (window.__жив) requestAnimationFrame(т); }
      requestAnimationFrame(т); }"""
    with sync_playwright() as p:
        бр = p.chromium.launch(headless=False)
        стр = бр.new_context(viewport={"width": 1920, "height": 1000}).new_page()
        ch._войти(стр)
        for путь in ("/enshrouded", "/medkit"):
            ряд = []
            for повтор in range(3):
                стр.goto(ch.БАЗА + путь, wait_until="networkidle")
                стр.wait_for_timeout(800)
                стр.mouse.move(1100, 600)
                стр.evaluate(сэмплер)
                for _ in range(40):
                    стр.mouse.wheel(0, 180)
                    стр.wait_for_timeout(40)
                for _ in range(40):
                    стр.mouse.wheel(0, -180)
                    стр.wait_for_timeout(40)
                ряд += стр.evaluate("() => { window.__жив = false; return window.__кадры; }")[3:]
            ряд.sort()
            p95 = ряд[int(len(ряд) * 0.95)] if ряд else float("nan")
            print(f"{путь}: кадров {len(ряд)}, p95 {p95:.1f} мс, медиана {ряд[len(ряд)//2]:.1f} мс")
        бр.close()


ИМЕНА_СНИМКОВ = {"/": "launcher"}


def снимки():
    """Кадры всех страниц вошедшего на 390 и 1920 в review_screenshots/redesign-shell/,
    имена как у redesign-before (для пар «до / после»)."""
    from playwright.sync_api import sync_playwright
    куда = os.path.join("review_screenshots", "redesign-shell")
    os.makedirs(куда, exist_ok=True)
    пути = страницы_каркаса()
    with sync_playwright() as p:
        for ширина in (390, 1920):
            бр = p.chromium.launch(headless=False)
            к = бр.new_context(viewport={"width": ширина, "height": 900},
                               has_touch=ширина < 600, is_mobile=ширина < 600)
            стр = к.new_page()
            ch._войти(стр)
            for путь in пути:
                стр.goto(ch.БАЗА + путь, wait_until="networkidle")
                if re.sub(r"^https?://[^/]+", "", стр.url).split("?")[0] != путь:
                    continue
                if not стр.locator(".v2-shell").count():
                    continue
                стр.wait_for_timeout(500)
                имя = ИМЕНА_СНИМКОВ.get(путь, путь.strip("/").replace("/", "-"))
                ф = os.path.join(куда, f"{имя}-{ширина}.png")
                стр.screenshot(path=ф, animations="disabled")
                print("снимок:", ф)
            бр.close()


if __name__ == "__main__":
    if "--контроль" in sys.argv:
        sys.exit(контроль())
    if "--снимки" in sys.argv:
        снимки()
        sys.exit(0)
    if "--кадры" in sys.argv:
        кадры()
        sys.exit(0)
    if "--приёмка" in sys.argv:
        приёмка()
        print(f"ИТОГ: находок {находок}, пропусков {пропусков}")
        sys.exit(1 if находок else (2 if пропусков else 0))
    проверить()
    print(f"ИТОГ: находок {находок}, пропусков {пропусков}")
    sys.exit(1 if находок else (2 if пропусков else 0))
