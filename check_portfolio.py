# -*- coding: utf-8 -*-
"""ГОСТЕВАЯ ГЛАВНАЯ-ПОРТФОЛИО ГЛАЗАМИ ЧЕЛОВЕКА (заход 334).

МЕРКА С КОДОМ ВОЗВРАТА: 0 — всё сошлось, 1 — есть ПЛОХО, 2 — есть
ПРОПУСК (мерить было нечего) либо нет стенда. Стенд и ГОЛОВНОЙ браузер
(§6.0.3): ширина и перенос строк в headless меряются не про тот экран.

ПОЧЕМУ ОТДЕЛЬНАЯ ПРОБА. Путь `/` отдаёт ДВЕ страницы по состоянию входа,
и все браузерные пробы ряда стенда ходят туда С СЕССИЕЙ — то есть снимают
лаунчер. Гостевую главную до этого захода не открывала ни одна проба и ни
один тест (замер блока A4). Здесь она открывается гостем.

ВСЕ РЕЖИМЫ РАЗОМ (заход 343):

  py check_portfolio.py                     # сводка «режимов N, прошли X, упали Y»
  py check_portfolio.py --verbose           # то же с полным выводом режимов по ходу
  py check_portfolio.py --только экран,лента  # часть реестра РЕЖИМЫ

  Полный вывод — в файл (путь последней строкой, `PF_LOG` задаёт свой);
  код 1, если упал хоть один режим. Потолок режима — `PF_MODE_TIMEOUT`.

РЕЖИМЫ — по блокам письма, у каждого свой вопрос:

  py check_portfolio.py --экран     # B: первый экран
  py check_portfolio.py --макет [--контроль-якорей|-отступа|-имени|-головы|-градиента|-кнопки]
                                    # макет первого экрана (письмо 2 задачи 343)
  py check_portfolio.py --лента     # C: бегущая лента работ
  py check_portfolio.py --о-себе    # D: о себе
  py check_portfolio.py --инструменты   # E: инструменты
  py check_portfolio.py --проекты   # F: проекты и подвал
  py check_portfolio.py --экран --контроль-магнита  # подлог ввода магнита (339, A4)
  py check_portfolio.py --о-себе --контроль-доли    # подлог расчёта доли (339, B)
  py check_portfolio.py --инструменты --контроль-повтора  # подлог повтора (339, D3)
  py check_portfolio.py --инструменты --контроль-сброса   # макет №1 теряет уход из окна (343, п2.3)
  py check_portfolio.py --связь [--контроль-буфера]  # D (342): две строки связи, уголок, три кнопки, подлог буфера
  ... --контроль                     # подлог звена: B — сдвиг портрета,
                                     #   C — ролики грузятся сразу
  py check_portfolio.py --лента --контроль-плавности   # C: рывок ряда

МЕРКА НЕ БЕРЁТ ДАННЫЕ У ПРОВЕРЯЕМОГО КОДА: ни `landing_defs`, ни шаблон
не читаются — только живое дерево, пиксели снимка и сеть браузера.
"""
import io
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DB_PATH", "app.db")
import probe_guard  # noqa: E402,F401  ПРОПУСК вместо трассы (§6.0.1)

sys.stdout.reconfigure(encoding="utf-8")

БАЗА = os.environ.get("STAND", "http://127.0.0.1:8899")
АДМИН = ("screenshot@local.dev", "Screenshot-Local-2026")
ШИРИНЫ = [(2560, 1440, False), (1920, 1080, False), (390, 844, True)]

итог = {"плохо": 0, "пропуск": 0}


def шаг(имя, условие, подробность="", собрано=None, отрицание=""):
    """Три исхода. `собрано` — сколько собрано для замера: ноль значит,
    что мерить было нечего, и это ПРОПУСК, а не OK (проверка 33)."""
    if собрано is not None and not собрано and not отрицание:
        итог["пропуск"] += 1
        print("  %-7s %s — сбор пуст, мерить нечего" % ("ПРОПУСК", имя))
        return None
    if not условие:
        итог["плохо"] += 1
    print("  %-7s %s%s" % ("OK" if условие else "ПЛОХО", имя,
                           (" — " + подробность) if подробность else ""))
    return bool(условие)


def _войти(стр, почта, пароль):
    стр.goto(БАЗА + "/login", wait_until="domcontentloaded", timeout=45000)
    стр.fill("input[name=email]", почта)
    стр.fill("input[name=password]", пароль)
    if стр.locator(".cf-turnstile").count():
        стр.wait_for_function("() => { const e = document.querySelector"
                              "('[name=\"cf-turnstile-response\"]'); return e && e.value; }",
                              timeout=20000)
    with стр.expect_navigation(timeout=45000):
        стр.click("button[type=submit]")
    if "/login" in стр.url:
        raise RuntimeError("вход не прошёл: остались на /login")


def _контекст(браузер, ширина, высота, сенсор, движение="no-preference"):
    return браузер.new_context(viewport={"width": ширина, "height": высота},
                               has_touch=сенсор, device_scale_factor=1,
                               reduced_motion=движение)


# ══ B. ПЕРВЫЙ ЭКРАН ═══════════════════════════════════════════════════

ЗАМЕР_ЭКРАНА = r"""() => {
  const q = s => document.querySelector(s);
  const пр = e => { const b = e.getBoundingClientRect();
    return {x: b.left, y: b.top, w: b.width, h: b.height, r: b.right, b: b.bottom}; };
  const шапка = q('.site-header'), экран = q('.pf-hero');
  if (!шапка || !экран) return null;
  const vw = document.documentElement.clientWidth, vh = innerHeight;
  // КРАЯ ТЕКСТА — по прямоугольникам строк, а не коробок: коробка
  // заголовка во всю ширину, а буквы в ней могут вылезать.
  let лево = Infinity, право = -Infinity, низ = -Infinity;
  // Края по шапке и экрану; нижний край — только по экрану.
  for (const корень of [шапка, экран]) {
    const свой = корень === экран;
    const обход = document.createTreeWalker(корень, NodeFilter.SHOW_TEXT);
    let узел;
    while ((узел = обход.nextNode())) {
      if (!узел.textContent.trim()) continue;
      const д = document.createRange(); д.selectNodeContents(узел);
      for (const к of д.getClientRects()) {
        if (!к.width) continue;
        лево = Math.min(лево, к.left); право = Math.max(право, к.right);
        if (свой) низ = Math.max(низ, к.bottom);
      }
    }
    for (const э of корень.querySelectorAll('*')) {
      const b = э.getBoundingClientRect();
      if (b.width && b.height) { лево = Math.min(лево, b.left); право = Math.max(право, b.right);
        if (свой) низ = Math.max(низ, b.bottom); }
    }
  }
  // СЛОВО НЕ РВЁТСЯ: у каждого слова имени ровно одна строка.
  const имя = q('.pf-hero .pf-grad');
  const слова = [];
  const т = имя.firstChild;
  let поз = 0;
  for (const с of т.textContent.split(' ')) {
    const д = document.createRange();
    д.setStart(т, поз); д.setEnd(т, поз + с.length); поз += с.length + 1;
    const верхи = [];
    for (const к of д.getClientRects()) {
      if (к.width && !верхи.some(в => Math.abs(в - к.top) < 3)) верхи.push(к.top);
    }
    слова.push({слово: с, строк: верхи.length});
  }
  // ИМЯ В ШАПКЕ одной строкой: считаются строки ТЕКСТА, а не коробка.
  const лого = q('.site-header .header-logo');
  const дл = document.createRange(); дл.selectNodeContents(лого);
  const верхи_лого = [];
  for (const к of дл.getClientRects()) {
    if (к.width && !верхи_лого.some(в => Math.abs(в - к.top) < 3)) верхи_лого.push(к.top);
  }
  const место = q('.pf-hero-portrait .media-slot');
  return {vw, vh, шапка: пр(шапка), экран: пр(экран), лево, право, низ,
          слова,
          заголовок: пр(q('.pf-hero-title')), строка: пр(q('.pf-hero-line')),
          кнопка: пр(q('.pf-hero-cta')), место: пр(место),
          заполнено: место.dataset.filled,
          картинок: место.querySelectorAll('img,video').length,
          // ВИД КНОПОК — по вычисленному фону и рамке, а не по классу:
          // спрашивается то, что видит глаз (заход 339, A1).
          кнопки_шапки: [...шапка.querySelectorAll('.header-right a')].map(а => {
            const с = getComputedStyle(а);
            const альфа = ц => { const м = ц.match(/rgba?\(([^)]+)\)/); if (!м) return 0;
              const ч = м[1].split(',').map(parseFloat); return ч.length > 3 ? ч[3] : 1; };
            return {текст: а.textContent.trim(), фон: альфа(с.backgroundColor),
                    рамка: parseFloat(с.borderTopWidth) > 0 ? альфа(с.borderTopColor) : 0}; }),
          имя_в_шапке: лого.textContent.replace(/\s+/g, ' ').trim(),
          кегль_имени: parseFloat(getComputedStyle(имя).fontSize),
          имя_коробка: пр(имя)};
}"""

# СЭМПЛЕР ПОЯВЛЕНИЯ ставится ДО разбора документа: время, когда каждый
# из пяти элементов впервые стал видимым, и прозрачность в ПЕРВОМ кадре.
СЭМПЛЕР = r"""(() => {
  const сел = ['.site-header', '.pf-hero-title', '.pf-hero-line', '.pf-hero-cta', '.pf-hero-portrait'];
  window.__появление = {когда: {}, первый: {}};
  const t0 = performance.now();
  const тик = () => {
    for (const с of сел) {
      const э = document.querySelector(с);
      if (!э) continue;
      const о = parseFloat(getComputedStyle(э).opacity);
      if (!(с in window.__появление.первый)) window.__появление.первый[с] = о;
      if (о > 0.5 && !(с in window.__появление.когда))
        window.__появление.когда[с] = Math.round(performance.now() - t0);
    }
    if (Object.keys(window.__появление.когда).length < сел.length) requestAnimationFrame(тик);
  };
  requestAnimationFrame(тик);
})();"""

ПОРЯДОК = [".site-header", ".pf-hero-title", ".pf-hero-line", ".pf-hero-cta", ".pf-hero-portrait"]


def _градиент_виден(стр):
    """Пиксели снимка имени: у серого края яркость букв ниже, чем у
    светлого. Спрашивается то, что видит глаз, а не значение свойства."""
    from PIL import Image
    # СНИМОК ПО БУКВАМ, А НЕ ПО КОРОБКЕ (заход 339). Коробка имени во всю
    # ширину экрана, а после уменьшения кегля буквы занимают середину:
    # левая пятая часть коробки не содержала ни одной буквы, и шаг
    # сравнивал фон с фоном (яркость 18 и 18) — врала мерка, не градиент.
    к = стр.evaluate("() => { const д = document.createRange();"
                     " д.selectNodeContents(document.querySelector('.pf-hero .pf-grad'));"
                     " const b = д.getBoundingClientRect();"
                     " return {x: b.left, y: b.top, width: b.width, height: b.height}; }")
    png = стр.screenshot(clip=к)
    im = Image.open(io.BytesIO(png)).convert("L")
    w, h = im.size
    пикс = im.load()

    def ярчайший(x0, x1):
        return max(пикс[x, y] for x in range(x0, x1) for y in range(h))
    return ярчайший(0, max(1, w // 5)), ярчайший(w - max(1, w // 5), w)


def _портрет(стр_админа, действие, файл=None):
    if действие == "положить":
        with open(файл, "rb") as ф:
            ответ = стр_админа.request.post(
                БАЗА + "/admin/api/landing/portrait",
                multipart={"file": {"name": "sq.jpg", "mimeType": "image/jpeg", "buffer": ф.read()}},
                timeout=240000)
    else:
        ответ = стр_админа.request.delete(БАЗА + "/admin/api/landing/portrait")
    return ответ.status


def экран(контроль_сдвига=False, контроль_магнита=False):
    from PIL import Image
    from playwright.sync_api import sync_playwright
    print("B. ПЕРВЫЙ ЭКРАН — гостем, головной браузер, стенд %s" % БАЗА)
    каталог = tempfile.mkdtemp(prefix="pf_")
    файл = os.path.join(каталог, "sq.jpg")
    Image.new("RGB", (1200, 1200), (70, 120, 160)).save(файл, quality=90)

    with sync_playwright() as p:
        бр = p.chromium.launch(headless=False)
        админ = бр.new_context()
        ад = админ.new_page()
        _войти(ад, *АДМИН)
        положили = False
        try:
            замеры = {}
            for ш, в, сенсор in ШИРИНЫ:
                print("\n  ── %d×%d%s" % (ш, в, " (сенсор)" if сенсор else ""))
                к = _контекст(бр, ш, в, сенсор)
                к.add_init_script(СЭМПЛЕР)
                с = к.new_page()
                с.goto(БАЗА + "/", wait_until="networkidle", timeout=60000)
                с.wait_for_function("() => window.__появление && Object.keys(window.__появление.когда).length >= 5",
                                    timeout=10000)
                с.wait_for_timeout(700)
                з = с.evaluate(ЗАМЕР_ЭКРАНА)
                if з is None:
                    шаг("первый экран есть на странице", False, "нет .site-header либо .pf-hero")
                    к.close()
                    continue
                низ_экрана = з["шапка"]["h"] + з["экран"]["h"]
                # ЗДЕСЬ СТОЯЛО «ровно окно» на всех ширинах (заход 334). Задача
                # 340: на телефоне первый экран по содержимому — ровно окно
                # давало 164 px пустоты под портретом. Узкая ширина спрашивает
                # «не выше окна»; контроль — `--макет --контроль-зазора`
                # (+200 px: 64 + 832 > 844).
                узко = з["vw"] <= 600
                шаг("шапка плюс первый экран — %s" % ("не выше окна" if узко else "ровно окно"),
                    (низ_экрана <= з["vh"] + 1) if узко else abs(низ_экрана - з["vh"]) <= 1,
                    "шапка %.1f + экран %.1f = %.1f при окне %d" % (
                        з["шапка"]["h"], з["экран"]["h"], низ_экрана, з["vh"]))
                шаг("внутри первого экрана ничего не вылезает ниже его края",
                    з["низ"] <= з["экран"]["b"] + 0.5,
                    "нижний край содержимого %.1f, край экрана %.1f" % (з["низ"], з["экран"]["b"]))
                шаг("за левый и правый край окна не выходит ничего",
                    з["лево"] >= -0.5 and з["право"] <= з["vw"] + 0.5,
                    "содержимое от %.1f до %.1f при окне %d" % (з["лево"], з["право"], з["vw"]))
                шаг("боковое поле не меньше 16 px с обеих сторон",
                    з["лево"] >= 15.5 and з["право"] <= з["vw"] - 15.5,
                    "слева %.1f, справа %.1f" % (з["лево"], з["vw"] - з["право"]))
                рваных = [сл for сл in з["слова"] if сл["строк"] != 1]
                шаг("слова имени не рвутся посреди слова", not рваных,
                    "слов %d, рваных %d" % (len(з["слова"]), len(рваных)), собрано=len(з["слова"]))
                серый, светлый = _градиент_виден(с)
                шаг("градиент имени виден: серый край темнее светлого", серый + 20 < светлый,
                    "яркость букв слева %d, справа %d" % (серый, светлый))
                # ЗАХОД 339, A1: знак сайта вернулся, «Регистрация» акцентная.
                # Здесь стояли шаги «в шапке слева имя» и «ярких кнопок 0» —
                # требование письма 334, отменённое владельцем.
                шаг("в шапке слева знак сайта", "EnergyDess" in з["имя_в_шапке"],
                    "«%s»" % з["имя_в_шапке"])
                по_тексту = {к["текст"]: к for к in з["кнопки_шапки"]}
                вход, рег = по_тексту.get("Войти"), по_тексту.get("Регистрация")
                шаг("«Войти» обводкой: фона нет, рамка видна",
                    bool(вход) and вход["фон"] == 0 and вход["рамка"] > 0,
                    "фон %s, рамка %s" % ((вход or {}).get("фон"), (вход or {}).get("рамка")),
                    собрано=len(з["кнопки_шапки"]))
                шаг("«Регистрация» акцентной: фон залит",
                    bool(рег) and рег["фон"] >= 0.99,
                    "фон %s" % (рег or {}).get("фон"), собрано=len(з["кнопки_шапки"]))
                имя_к, место_к = з["имя_коробка"], з["место"]
                шаг("портрет налезает на имя снизу и стоит по центру",
                    имя_к["y"] < место_к["y"] < имя_к["b"]
                    and abs(место_к["x"] + место_к["w"] / 2 - з["vw"] / 2) <= 1,
                    "имя %.0f..%.0f, верх портрета %.0f, центр портрета %.1f при середине окна %.1f; кегль имени %.1f" % (
                        имя_к["y"], имя_к["b"], место_к["y"], место_к["x"] + место_к["w"] / 2,
                        з["vw"] / 2, з["кегль_имени"]))
                шаг("кнопка связи и строка внизу экрана",
                    з["кнопка"]["b"] <= з["экран"]["b"] and з["кнопка"]["y"] > з["место"]["y"],
                    "кнопка %.0f..%.0f, портрет сверху %.0f" % (з["кнопка"]["y"], з["кнопка"]["b"], з["место"]["y"]))
                когда = с.evaluate("() => window.__появление.когда")
                времена = [когда.get(сел) for сел in ПОРЯДОК]
                по_порядку = all(времена[i] is not None and времена[i + 1] is not None
                                 and времена[i] <= времена[i + 1] for i in range(len(времена) - 1))
                шаг("появление сверху вниз: шапка, заголовок, строка, кнопка, портрет",
                    по_порядку, " < ".join("%s" % т for т in времена), собрано=len(когда))
                замеры[(ш, в)] = з
                к.close()

                # reduced-motion: в первом кадре всё уже видно
                к = _контекст(бр, ш, в, сенсор, движение="reduce")
                к.add_init_script(СЭМПЛЕР)
                с = к.new_page()
                с.goto(БАЗА + "/", wait_until="networkidle", timeout=60000)
                с.wait_for_timeout(300)
                первый = с.evaluate("() => window.__появление.первый")
                невидимых = [сел for сел, о in первый.items() if о < 0.99]
                шаг("при «уменьшить движение» всё видно с первого кадра", not невидимых,
                    "замерено %d, прозрачных в первом кадре %d" % (len(первый), len(невидимых)),
                    собрано=len(первый))
                к.close()

            # ── МАГНИТ ПОРТРЕТА (заход 339, A4) ─────────────────────
            # Мерится СДВИГ, КОТОРЫЙ ВИДЕН: вычисленный transform обёртки
            # после настоящего движения мыши, а не переменная скрипта.
            print("\n  ── магнит портрета%s" % (" · ПОДЛОГ: движение указателя перехвачено до скрипта" if контроль_магнита else ""))
            for ш, в, сенсор in ШИРИНЫ:
                к = _контекст(бр, ш, в, сенсор)
                if контроль_магнита:
                    # ЛОМАЕТСЯ ЗВЕНО ВВОДА: событие гасится на окне в фазе
                    # захвата раньше слушателя страницы. Замер тот же.
                    к.add_init_script("window.addEventListener('pointermove', e => e.stopImmediatePropagation(), true);")
                с = к.new_page()
                с.goto(БАЗА + "/", wait_until="networkidle", timeout=60000)
                с.wait_for_timeout(900)
                сдвиг = lambda: с.evaluate("() => { const m = document.querySelector('[data-pf-magnet]');"
                                          " if (!m) return null; const t = new DOMMatrix(getComputedStyle(m).transform);"
                                          " return Math.hypot(t.m41, t.m42); }")
                центр = с.evaluate("() => { const b = document.querySelector('.pf-hero-portrait').getBoundingClientRect();"
                                   " return [b.left + b.width / 2, b.top + b.height / 2]; }")
                с.mouse.move(*центр, steps=6); с.wait_for_timeout(1200)
                в_центре = сдвиг()
                с.mouse.move(2, в - 2, steps=10); с.wait_for_timeout(1200)
                в_углу = сдвиг()
                if сенсор:
                    с.touchscreen.tap(5, в - 5); с.wait_for_timeout(800)
                    шаг("%d×%d: на сенсорном портрет не двигается" % (ш, в),
                        в_углу is not None and в_углу <= 0.5 and (сдвиг() or 0) <= 0.5,
                        "сдвиг от курсора в углу %s px, после касания %.1f px" % (в_углу, сдвиг() or 0),
                        собрано=0 if в_углу is None else 1)
                else:
                    шаг("%d×%d: курсор в углу двигает портрет, в центре — нет" % (ш, в),
                        в_центре is not None and в_центре <= 0.5 and в_углу >= 20,
                        "сдвиг в центре %.1f px, в углу %.1f px" % (в_центре or 0, в_углу or 0),
                        собрано=0 if в_углу is None else 1)
                    с.mouse.move(*центр, steps=6); с.wait_for_timeout(1500)
                    шаг("%d×%d: курсор вернулся в центр — портрет вернулся" % (ш, в),
                        (сдвиг() or 0) <= 0.5, "сдвиг %.1f px" % (сдвиг() or 0))
                к.close()

            # ── ПОДЛОГ: портрет в хранилище и без него ───────────────
            print("\n  ── подлог: портрет положен, затем убран")
            было = замеры.get((1920, 1080), {}).get("заполнено")
            if было != "no":
                шаг("портрет на стенде пуст — подлог можно провести", False,
                    "место уже заполнено (%s): чужой файл не трогаем" % было)
            else:
                код = _портрет(ад, "положить", файл)
                положили = код == 200
                шаг("портрет положен боевой загрузкой", положили, "HTTP %s" % код)
                сдвиги = []
                for ш, в, сенсор in ШИРИНЫ:
                    к = _контекст(бр, ш, в, сенсор, движение="reduce")
                    с = к.new_page()
                    с.goto(БАЗА + "/", wait_until="networkidle", timeout=60000)
                    с.wait_for_timeout(300)
                    полный = с.evaluate(ЗАМЕР_ЭКРАНА)
                    к.close()
                    сдвиги.append((ш, в, сенсор, полный))
                код = _портрет(ад, "убрать")
                if код == 200:
                    положили = False
                шаг("портрет убран из хранилища", код == 200, "HTTP %s" % код)
                for ш, в, сенсор, полный in сдвиги:
                    к = _контекст(бр, ш, в, сенсор, движение="reduce")
                    с = к.new_page()
                    с.goto(БАЗА + "/", wait_until="networkidle", timeout=60000)
                    if контроль_сдвига:
                        # ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ ЗВЕНА «СДВИГ»: у пустого места
                        # снято соотношение — заглушка схлопывается.
                        с.add_style_tag(content=".pf-hero-portrait,.pf-hero-portrait .media-slot"
                                        "{aspect-ratio:auto!important}")
                    с.wait_for_timeout(300)
                    пустой = с.evaluate(ЗАМЕР_ЭКРАНА)
                    к.close()
                    сдвиг = max(abs(полный[э][ось] - пустой[э][ось])
                                for э in ("место", "заголовок", "строка", "кнопка")
                                for ось in ("x", "y", "w", "h"))
                    шаг("%d×%d: портрет убран — заглушка встала, сдвиг 0 px" % (ш, в),
                        пустой["заполнено"] == "no" and пустой["картинок"] == 0 and сдвиг <= 0.5,
                        "доказательство: заполнено %s→%s, картинок %d→%d; сдвиг %.2f px, место %.1f×%.1f→%.1f×%.1f" % (
                            полный["заполнено"], пустой["заполнено"], полный["картинок"], пустой["картинок"],
                            сдвиг, полный["место"]["w"], полный["место"]["h"],
                            пустой["место"]["w"], пустой["место"]["h"]))
        finally:
            if положили:
                print("  уборка: портрет снят — HTTP %s" % _портрет(ад, "убрать"))
            бр.close()


# ══ МАКЕТ ПЕРВОГО ЭКРАНА (письмо 2 задачи 343) ═══════════════════════
# Шесть вопросов утверждённого макета, у каждого свой подлог. Подлог
# засчитывается, только если упал ЕГО шаг: сломанное соседнее звено
# доказательством не является (код 4 и строка «не пойман своим шагом»).
#   --контроль-якорей    две ссылки ряда переставлены местами
#   --контроль-отступа   у секций снят scroll-margin-top
#   --контроль-имени     кегль имени 11cqi вместо своего коэффициента
#   --контроль-головы    портрет ограничен 30vh
#   --контроль-градиента светлая опорная точка градиента кнопки
#   --контроль-кнопки    кнопка сдвинута на строки о себе
#   --контроль-зазора    портрету margin-bottom 200px (задача 340)
#   --контроль-края      в низ первого экрана подложен блок шириной 500 px

ПОДЛОГИ_МАКЕТА = {
    "якорей": ("порядок якорей", None),
    "отступа": ("переход по якорю", "main section[id]{scroll-margin-top:0!important}"),
    "имени": ("имя одной строкой", ".pf-hero-name{font-size:11cqi!important}"),
    "головы": ("высота головы", ".pf-hero-portrait{max-height:30vh!important}"),
    "градиента": ("контраст кнопки", ".pf-cta-pill{--pf-cta-c:var(--accent-workout)!important}"),
    "кнопки": ("строки и кнопка", None),
    "зазора": ("зазор под портретом", ".pf-hero-portrait{margin-bottom:200px!important}"),
    "края": ("первый экран: за краем окна", None),
}

ШРИФТ_ГОТОВ = ("() => [...document.fonts].some(f => f.family.replace(/[\"']/g, '') === 'Unbounded'"
               " && f.status === 'loaded')")

МАКЕТ_ЗАМЕР = r"""() => {
  const q = s => document.querySelector(s);
  const пр = b => ({l: b.left, t: b.top, r: b.right, b: b.bottom, w: b.width, h: b.height});
  const текст = э => { const д = document.createRange(); д.selectNodeContents(э); return д; };
  // 1. якоря: ссылки слева направо против секций в порядке документа
  const ссылки = [...document.querySelectorAll('.pf-anchors a')]
    .map(а => ({href: а.getAttribute('href'), x: а.getBoundingClientRect().left,
                верх: Math.round(а.getBoundingClientRect().top),
                строк: new Set([...текст(а).getClientRects()].filter(к => к.width).map(к => Math.round(к.top))).size}))
    .sort((а, б) => а.x - б.x);
  const цели = ссылки.map(с => ({href: с.href, э: document.getElementById((с.href || '').replace(/^#/, ''))}));
  const по_документу = цели.filter(ц => ц.э).sort((а, б) =>
    а.э.compareDocumentPosition(б.э) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1).map(ц => ц.href);
  // 3. имя
  const имя = q('.pf-hero-name'), загл = q('.pf-hero-title');
  const ти = текст(имя).getBoundingClientRect();
  const строк_имени = new Set([...текст(имя).getClientRects()].filter(к => к.width).map(к => Math.round(к.top))).size;
  const лх = parseFloat(getComputedStyle(имя).lineHeight);
  // 4. голова
  const место = q('.pf-hero-portrait .media-slot').getBoundingClientRect();
  // 5. опорные точки градиента кнопки — из ВЫЧИСЛЕННОГО фона, не из имён переменных
  const кн = q('.pf-hero-cta .pf-contact-btn');
  const фон = getComputedStyle(кн).backgroundImage;
  const арги = []; let глуб = 0, нач = фон.indexOf('(') + 1;
  for (let i = нач; i < фон.length; i++) {
    const ч = фон[i];
    if (ч === '(') глуб++;
    else if (ч === ')') { if (глуб === 0) { арги.push(фон.slice(нач, i)); break; } глуб--; }
    else if (ч === ',' && глуб === 0) { арги.push(фон.slice(нач, i)); нач = i + 1; }
  }
  const зонд = document.createElement('i'); document.body.appendChild(зонд);
  const в_rgb = с => { зонд.style.color = ''; зонд.style.color = с; const в = getComputedStyle(зонд).color;
    let м = в.match(/^rgba?\(([^)]+)\)/); if (м) return м[1].split(',').slice(0, 3).map(Number);
    м = в.match(/^color\(srgb ([\d.e+-]+) ([\d.e+-]+) ([\d.e+-]+)/); if (м) return [м[1], м[2], м[3]].map(x => Math.round(+x * 255));
    return null; };
  const точки = [];
  for (let а of арги) {
    а = а.trim().replace(/\)\s+[\d.]+(%|px)(\s+[\d.]+(%|px))?$/, ')');
    if (!CSS.supports('color', а)) continue;
    точки.push({css: а, rgb: в_rgb(а)});
  }
  const надпись = в_rgb(getComputedStyle(кн).color); зонд.remove();
  const ярк = c => { const [r, g, b] = c.map(v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
  const контраст = (a, b) => { const [x, y] = [ярк(a), ярк(b)].sort((m, n) => n - m); return (x + 0.05) / (y + 0.05); };
  // 6. строки о себе и кнопка
  const строки = текст(q('.pf-hero-line')).getBoundingClientRect(), кнб = кн.getBoundingClientRect();
  // задача 340: зазор «низ портрета → следующий элемент» против ряда сетки;
  // элементы первого экрана за краем окна — поиском, а не scrollWidth
  // (у html и body overflow-x: clip, вылет им не виден)
  const vw0 = document.documentElement.clientWidth;
  const за_краем = [...q('.pf-hero').querySelectorAll('*')].filter(э => { const b = э.getBoundingClientRect();
    return b.width && b.height && getComputedStyle(э).visibility !== 'hidden' && (b.right > vw0 + 0.5 || b.left < -0.5); })
    .map(э => (э.className && э.className.baseVal === undefined ? э.className : э.tagName));
  return {vw: document.documentElement.clientWidth, vh: innerHeight,
    ссылки: ссылки.map(с => с.href), верхи_ссылок: [...new Set(ссылки.map(с => с.верх))], строк_в_ссылках: ссылки.map(с => с.строк),
    по_документу, нет_цели: цели.filter(ц => !ц.э).map(ц => ц.href),
    имя: пр(ти), место_имени: загл.clientWidth, строк_имени, высота_заголовка: загл.getBoundingClientRect().height, лх,
    голова: место.height / innerHeight,
    точки: точки.map(т => ({css: т.css.slice(0, 60), rgb: т.rgb, контраст: т.rgb && надпись ? +контраст(т.rgb, надпись).toFixed(2) : null})),
    надпись, строки: пр(строки), кнопка: пр(кнб),
    зазор: q('.pf-hero-foot').getBoundingClientRect().top - место.bottom,
    ряд_сетки: parseFloat(getComputedStyle(q('.pf-hero')).rowGap), за_краем};
}"""

# Переход по якорю: ждём, пока прокрутка 15 кадров подряд не меняется,
# и пишем все промежуточные положения — по ним видно, плавно ли шла.
ПЕРЕХОД = r"""(href) => new Promise(готово => {
  const ys = [scrollY]; let тихо = 0; const t0 = performance.now();
  document.querySelector('.pf-anchors a[href="' + href + '"]').click();
  const тик = () => {
    const y = scrollY; if (y === ys[ys.length - 1]) тихо++; else { тихо = 0; ys.push(y); }
    if ((тихо >= 15 && ys.length > 1) || performance.now() - t0 > 6000) {
      const ц = document.getElementById(href.slice(1)).getBoundingClientRect();
      const шапка = document.querySelector('.site-header').getBoundingClientRect();
      готово({положений: ys.length, верх: ц.top, низ_шапки: шапка.bottom, мс: Math.round(performance.now() - t0)});
      return;
    }
    requestAnimationFrame(тик);
  };
  requestAnimationFrame(тик);
})"""


def макет(подлог=None):
    from playwright.sync_api import sync_playwright
    цель, стиль = ПОДЛОГИ_МАКЕТА[подлог] if подлог else (None, None)
    print("МАКЕТ ПЕРВОГО ЭКРАНА — гостем, головной браузер, стенд %s%s" % (
        БАЗА, " · ПОДЛОГ: %s (ждём падения шага «%s»)" % (подлог, цель) if подлог else ""))
    упавшие = []

    def ш(имя, условие, подробность="", собрано=None):
        р = шаг(имя, условие, подробность, собрано=собрано)
        if р is False:
            упавшие.append(имя)

    with sync_playwright() as p:
        бр = p.chromium.launch(headless=False)
        try:
            for шир, выс, сенсор in ШИРИНЫ:
                print("\n  ── %d×%d%s" % (шир, выс, " (сенсор)" if сенсор else ""))
                к = _контекст(бр, шир, выс, сенсор)
                с = к.new_page()
                с.goto(БАЗА + "/", wait_until="networkidle", timeout=60000)
                с.wait_for_function(ШРИФТ_ГОТОВ, timeout=20000)
                с.wait_for_timeout(1200)
                if стиль:
                    с.add_style_tag(content=стиль)
                if подлог == "якорей":
                    с.evaluate("() => { const а = document.querySelectorAll('.pf-anchors a');"
                               " а[0].parentNode.insertBefore(а[1], а[0]); }")
                if подлог == "края":
                    с.evaluate("() => { const d = document.createElement('div');"
                               " d.style.cssText = 'width:500px;min-width:500px;flex:none;height:10px';"
                               " document.querySelector('.pf-hero-foot').appendChild(d); }")
                if подлог == "кнопки":
                    с.evaluate("""() => { const л = document.querySelector('.pf-hero-line').getBoundingClientRect();
                        const к = document.querySelector('.pf-hero-cta .pf-contact-btn'); const б = к.getBoundingClientRect();
                        к.style.translate = (л.left - б.left) + 'px ' + (л.top - б.top) + 'px'; }""")
                с.wait_for_timeout(200)
                з = с.evaluate(МАКЕТ_ЗАМЕР)

                ш("порядок якорей: ссылки слева направо = секции в документе",
                  not з["нет_цели"] and з["ссылки"] == з["по_документу"],
                  "ссылки %s; секции %s; без цели %s" % (з["ссылки"], з["по_документу"], з["нет_цели"] or "нет"),
                  собрано=len(з["ссылки"]))
                ш("якоря в одну строку без переноса",
                  len(з["верхи_ссылок"]) == 1 and all(н == 1 for н in з["строк_в_ссылках"]),
                  "разных верхов %d, строк в ссылках %s" % (len(з["верхи_ссылок"]), з["строк_в_ссылках"]),
                  собрано=len(з["ссылки"]))

                доля = з["имя"]["w"] / з["место_имени"] if з["место_имени"] else 0
                ш("имя одной строкой: 94–100% места, за край не выходит",
                  0.94 <= доля <= 1.0 and з["строк_имени"] == 1 and abs(з["высота_заголовка"] - з["лх"]) <= 2
                  and з["имя"]["l"] >= -0.5 and з["имя"]["r"] <= з["vw"] + 0.5,
                  "доля %.3f, строк %d, высота блока %.1f при строке %.1f, текст %.1f..%.1f при окне %d" % (
                      доля, з["строк_имени"], з["высота_заголовка"], з["лх"], з["имя"]["l"], з["имя"]["r"], з["vw"]))

                if not сенсор:
                    ш("высота головы 60–72% окна", 0.60 <= з["голова"] <= 0.72,
                      "голова %.1f%% окна" % (з["голова"] * 100))

                ш("контраст кнопки: белая надпись к каждой опорной точке не ниже 4.5",
                  len(з["точки"]) >= 3 and all(т["контраст"] is not None and т["контраст"] >= 4.5 for т in з["точки"]),
                  "надпись %s; точки %s" % (з["надпись"], [(т["rgb"], т["контраст"]) for т in з["точки"]]),
                  собрано=len(з["точки"]))

                л, кн = з["строки"], з["кнопка"]
                пересеклись = not (л["r"] <= кн["l"] or кн["r"] <= л["l"] or л["b"] <= кн["t"] or кн["b"] <= л["t"])
                в_окне = all(0 <= б["l"] and б["r"] <= з["vw"] and 0 <= б["t"] and б["b"] <= з["vh"] for б in (л, кн))
                ш("строки и кнопка: не пересекаются, в пределах окна", not пересеклись and в_окне,
                  "строки %.0f..%.0f × %.0f..%.0f, кнопка %.0f..%.0f × %.0f..%.0f, окно %d×%d" % (
                      л["l"], л["r"], л["t"], л["b"], кн["l"], кн["r"], кн["t"], кн["b"], з["vw"], з["vh"]))

                ш("зазор под портретом равен ряду сетки",
                  abs(з["зазор"] - з["ряд_сетки"]) <= 1,
                  "низ портрета → следующий элемент %.1f px, ряд сетки %.1f px" % (з["зазор"], з["ряд_сетки"]))
                ш("первый экран: за краем окна 0 элементов", not з["за_краем"],
                  "за краем %d: %s" % (len(з["за_краем"]), з["за_краем"][:5]))

                # 2. переход по якорю — каждая ссылка, плавно. Плавность меряется
                # кадрами; у окна, где кадры стоят, мерить нечем (как у инструментов).
                for href in (з["ссылки"] if _отрисовка_идёт(с, "%d×%d переход по якорю" % (шир, выс)) else []):
                    с.evaluate("() => window.scrollTo({top: 0, behavior: 'instant'})")
                    с.wait_for_timeout(150)
                    п = с.evaluate(ПЕРЕХОД, href)
                    ш("переход по якорю %s: верх секции не под шапкой, прокрутка плавная" % href,
                      п["верх"] >= п["низ_шапки"] - 0.5 and п["положений"] >= 4,
                      "верх секции %.1f, низ шапки %.1f, положений прокрутки %d за %d мс" % (
                          п["верх"], п["низ_шапки"], п["положений"], п["мс"]))
                к.close()

                # при «уменьшить движение» переход мгновенный
                к = _контекст(бр, шир, выс, сенсор, движение="reduce")
                с = к.new_page()
                с.goto(БАЗА + "/", wait_until="networkidle", timeout=60000)
                с.wait_for_timeout(300)
                if стиль:
                    с.add_style_tag(content=стиль)
                п = с.evaluate(ПЕРЕХОД, "#tools")
                ш("переход по якорю при «уменьшить движение»: мгновенно, верх не под шапкой",
                  п["положений"] <= 2 and п["верх"] >= п["низ_шапки"] - 0.5,
                  "положений прокрутки %d, верх %.1f, низ шапки %.1f" % (п["положений"], п["верх"], п["низ_шапки"]))
                к.close()
        finally:
            бр.close()
    if подлог:
        свои = [у for у in упавшие if у.startswith(цель)]
        print("\n  ДОКАЗАТЕЛЬСТВО ПОДЛОГА «%s»: упал свой шаг %d раз; упали всего: %s" % (
            подлог, len(свои), sorted(set(упавшие)) or "ничего"))
        if not свои:
            print("  ПОДЛОГ НЕ ПОЙМАН своим шагом")
            return 4
    return None


# ══ C. БЕГУЩАЯ ЛЕНТА ══════════════════════════════════════════════════

ЛЕНТА_СОСТОЯНИЕ = r"""() => {
  const лента = document.querySelector('.pf-feed');
  if (!лента) return null;
  const vw = document.documentElement.clientWidth;
  const ряды = [...лента.querySelectorAll('.pf-feed-row')].map(р => {
    const д = р.firstElementChild, к = д.getBoundingClientRect();
    return {знак: Number(р.dataset.feedDir), лево: к.left, право: к.right,
            сдвиг: new DOMMatrix(getComputedStyle(д).transform).m41};
  });
  const коробки = [...лента.querySelectorAll('.media-slot')].map(м => {
    const к = м.getBoundingClientRect(); return [к.width, к.height, м.dataset.filled]; });
  const ролики = [...лента.querySelectorAll('video')].map(в => {
    const к = в.getBoundingClientRect();
    return {src: !!в.getAttribute('src'), играет: !в.paused, время: в.currentTime,
      готов: в.readyState,
      видим: к.width > 0 && к.bottom > 0 && к.top < innerHeight && к.right > 0 && к.left < vw};
  });
  return {vw, scrollY, ряды, коробки, ролики};
}"""

# Сэмплер кадров: пока идёт прокрутка, КАЖДЫЙ кадр пишет сдвиг рядов
# и положение прокрутки; плюс сумма сдвигов раскладки (layout-shift).
СЭМПЛЕР_ЛЕНТЫ = r"""() => {
  window.__кадры = []; window.__сдвиги = 0;
  new PerformanceObserver(с => { for (const з of с.getEntries()) window.__сдвиги += з.value; })
    .observe({type: 'layout-shift', buffered: false});
  const тик = () => {
    const ряды = [...document.querySelectorAll('.pf-feed-row')].map(р => {
      const д = р.firstElementChild, к = д.getBoundingClientRect();
      return [new DOMMatrix(getComputedStyle(д).transform).m41, к.left, к.right];
    });
    const к = document.querySelector('.pf-feed').getBoundingClientRect();
    window.__кадры.push({y: scrollY, ряды, верх: к.top, низ: к.bottom, vh: innerHeight});
    if (window.__кадры.length < 100000) requestAnimationFrame(тик);
  };
  requestAnimationFrame(тик);
}"""

# ПОДЛОГ ЗВЕНА «ЛЕНИВАЯ ЗАГРУЗКА»: адреса роликов подставляются сразу
# после разбора документа — ровно то, от чего блок C3 защищает.
ПОДЛОГ_ЖАДНО = r"""document.addEventListener('DOMContentLoaded', () => {
  for (const в of document.querySelectorAll('.pf-feed video[data-src]')) {
    в.preload = 'auto'; в.setAttribute('src', в.getAttribute('data-src'));
  }
});"""


# ПОДЛОГ ЗВЕНА «ПЛАВНОСТЬ»: каждое пятое событие прокрутки ряд получает
# лишние 12 px. Слушатель ставится ПОСЛЕ страничного (по `load`), иначе
# страничный перезаписал бы сдвиг и подлог не состоялся бы. Доказательство —
# счётчик применённых рывков, а не вердикт пробы.
ПОДЛОГ_РЫВОК = r"""window.__рывков = 0;
window.addEventListener('load', () => {
  let n = 0;
  window.addEventListener('scroll', () => {
    if (++n % 5) return;
    for (const д of document.querySelectorAll('.pf-feed-track')) {
      const v = parseFloat(д.style.getPropertyValue('--pf-shift')) || 0;
      д.style.setProperty('--pf-shift', (v + 12) + 'px');
    }
    window.__рывков++;
  }, {passive: true});
});"""


def _сеть(стр):
    """Счёт байт и запросов роликов ленты — по сети браузера (CDP)."""
    cdp = стр.context.new_cdp_session(стр)
    cdp.send("Network.enable")
    счёт = {"байт": 0, "роликов": 0}

    def при_ответе(с):
        адрес = с.get("response", {}).get("url", "")
        # ТОЛЬКО РОЛИКИ ЛЕНТЫ (заход 343). Здесь стояло «любой .mp4 из
        # /landing-media/», и с захода 342 это ложная находка: верхний
        # ролик ФОНА грузится сразу по замыслу (B5), и шаг «в первом экране
        # ролики ленты не грузятся» краснел на исправном коде.
        if "/landing-media/feed-" in адрес and ".mp4" in адрес:
            счёт["роликов"] += 1

    def при_конце(с):
        счёт["байт"] += int(с.get("encodedDataLength", 0))
    cdp.on("Network.responseReceived", при_ответе)
    cdp.on("Network.loadingFinished", при_конце)
    return счёт


def _прокрутить(стр, ш, в, шагов):
    стр.mouse.move(ш // 2, в // 2)
    for _ in range(шагов):
        стр.mouse.wheel(0, 60)
        стр.wait_for_timeout(16)
    стр.wait_for_timeout(2500)


# ПЕРВЫЙ КАДР РОЛИКА ЛЕНТЫ (письмо 3а задачи 343). Ролик ленты без `poster`
# показывает в рамке пустоту, пока не приехал. Кадр есть на томе — атрибут
# обязан стоять; кадра нет — атрибута нет, и 404 в консоли не бывает.
ЛЕНТА_КАДРЫ = r"""() => [...document.querySelectorAll('.pf-feed video')].map(v =>
  [v.closest('.media-slot').dataset.slot, v.getAttribute('poster')])"""


def _кадры_шаг(с, ответы):
    кадры = с.evaluate(ЛЕНТА_КАДРЫ)
    без = sorted({slot for slot, постер in кадры if not постер})
    шаг("у каждого ролика ленты есть первый кадр (poster)", not без,
        "роликов %d, без кадра %d, мест: %s" % (len(кадры), sum(1 for _, п in кадры if not п),
                                                ", ".join(без) or "—"),
        собрано=len(кадры))
    битых = [а for а, код in ответы if ".poster.webp" in а and код >= 400]
    шаг("адреса кадров не отвечают ошибкой", not битых,
        "ответов ≥400 на кадры %d: %s" % (len(битых), ", ".join(а.rsplit("/", 1)[-1] for а in битых[:3]) or "—"),
        отрицание="шаг про отсутствие ошибок: ноль и есть успех")


def лента_кадры_контроль():
    """ПОДЛОГ: кадр одного ролика убран с тома стенда. Шаг обязан назвать
    это место, а адреса кадров — не дать ни одного 404. Файл возвращается
    в `finally`."""
    import shutil
    from playwright.sync_api import sync_playwright
    import landing_store as хран
    имена = sorted(и for и in хран.файлы() if и.startswith("feed-") and и.endswith(".poster.webp"))
    if not имена:
        шаг("подлог кадра: на стенде есть кадр ленты", False, "кадров ленты на томе 0", собрано=0)
        return
    имя = имена[0]
    исходный = хран.путь(имя)
    отложенный = исходный + ".podlog"
    print("C. ПОДЛОГ КАДРА — убран %s, стенд %s" % (имя, БАЗА))
    shutil.move(исходный, отложенный)
    try:
        with sync_playwright() as p:
            бр = p.chromium.launch(headless=False)
            try:
                к = _контекст(бр, 390, 844, True)
                с = к.new_page()
                ответы = []
                с.on("response", lambda о: ответы.append((о.url, о.status)))
                с.goto(БАЗА + "/", wait_until="networkidle", timeout=60000)
                print("  доказательство подлога: файла кадра на томе %s" % os.path.exists(исходный))
                _кадры_шаг(с, ответы)
                к.close()
            finally:
                бр.close()
    finally:
        shutil.move(отложенный, исходный)


def лента(контроль=False, рывок=False):
    from playwright.sync_api import sync_playwright
    print("C. БЕГУЩАЯ ЛЕНТА — гостем, головной браузер, стенд %s%s" % (
        БАЗА, " · ПОДЛОГ: адреса роликов сразу" if контроль else ""))
    with sync_playwright() as p:
        бр = p.chromium.launch(headless=False)
        try:
            for ш, в, сенсор in ШИРИНЫ:
                print("\n  ── %d×%d%s" % (ш, в, " (сенсор)" if сенсор else ""))
                к = _контекст(бр, ш, в, сенсор)
                if контроль:
                    к.add_init_script(ПОДЛОГ_ЖАДНО)
                if рывок:
                    к.add_init_script(ПОДЛОГ_РЫВОК)
                с = к.new_page()
                сеть = _сеть(с)
                ответы = []
                с.on("response", lambda о: ответы.append((о.url, о.status)))
                с.goto(БАЗА + "/", wait_until="networkidle", timeout=60000)
                с.wait_for_timeout(1500)
                _кадры_шаг(с, ответы)
                до = с.evaluate(ЛЕНТА_СОСТОЯНИЕ)
                if до is None:
                    шаг("лента есть на странице", False, "нет .pf-feed")
                    к.close()
                    continue
                байт_до, роликов_до = сеть["байт"], сеть["роликов"]
                заполненных = sum(1 for б in до["коробки"] if б[2] == "yes")
                с_адресом_до = sum(1 for р in до["ролики"] if р["src"])
                # ЗДЕСЬ СТОЯЛО «в первом экране ролики ленты не грузятся» на всех
                # ширинах. Письмо 2 задачи 343 (задача 340): на телефоне первый
                # экран по содержимому, и лента видна с первого кадра — её ролики
                # грузятся ПО ЗАМЫСЛУ ленивой загрузки. Вопрос остаётся тем же —
                # «пока лента вне окна, не грузятся» — и задаётся там, где она при
                # загрузке вне окна. Контроль — `--лента --контроль` (адреса сразу).
                верх_ленты = с.evaluate("() => document.querySelector('.pf-feed').getBoundingClientRect().top")
                if верх_ленты >= в:
                    шаг("пока лента вне окна, ролики ленты не грузятся",
                        роликов_до == 0 and с_адресом_до == 0,
                        "верх ленты %.0f при окне %d; запросов роликов %d, роликов с адресом %d из %d; скачано всего %d КБ" % (
                            верх_ленты, в, роликов_до, с_адресом_до, len(до["ролики"]), байт_до // 1024),
                        собрано=len(до["ролики"]))
                else:
                    print("  —       лента в окне с первого кадра (верх %.0f при окне %d): ленивость здесь не спрашивается;"
                          " запросов роликов %d, скачано %d КБ" % (верх_ленты, в, роликов_до, байт_до // 1024))

                размеры = {(round(б[0], 1), round(б[1], 1)) for б in до["коробки"]}
                шаг("места ленты одного размера, пустые и заполненные",
                    len(размеры) == 1,
                    "коробок %d (заполненных %d), разных размеров %d: %s" % (
                        len(до["коробки"]), заполненных, len(размеры), sorted(размеры)[:3]),
                    собрано=len(до["коробки"]))

                с.evaluate(СЭМПЛЕР_ЛЕНТЫ)
                верх = с.evaluate("() => document.querySelector('.pf-feed').getBoundingClientRect().top + scrollY")
                высота = с.evaluate("() => document.querySelector('.pf-feed').offsetHeight")
                цель = int(верх + высота / 2 - в / 2)
                шагов = max(10, цель // 60)
                _прокрутить(с, ш, в, шагов)
                после = с.evaluate(ЛЕНТА_СОСТОЯНИЕ)
                кадры = с.evaluate("() => window.__кадры")
                сдвиги_раскладки = с.evaluate("() => window.__сдвиги")
                байт_после, роликов_после = сеть["байт"], сеть["роликов"]
                шаг("доехали до ленты — ролики начали грузиться",
                    роликов_после > 0,
                    "запросов роликов %d → %d; скачано %d КБ → %d КБ" % (
                        роликов_до, роликов_после, байт_до // 1024, байт_после // 1024),
                    собрано=заполненных)
                # ЗАХОД 343, БЛОК 2. Здесь стояло «играют ВСЕ ролики с файлом»:
                # так было устроено до захода — ряд в окне запускал все 36,
                # включая повторы набора за краем окна, и декодирование
                # их разом давало рывки прокрутки. Теперь играет ролик
                # в окне, за окном — пауза. Спрашиваются обе половины.
                с_файлом = [р for р in после["ролики"] if р["src"] and р["видим"]]
                играют = [р for р in с_файлом if р["играет"] and р["время"] > 0.2]
                шаг("ролики в окне играют сами, без нажатия", len(играют) == len(с_файлом),
                    "в окне с файлом %d, играют %d" % (len(с_файлом), len(играют)), собрано=len(с_файлом))
                за_окном = [р for р in после["ролики"] if р["src"] and not р["видим"]]
                шаг("ролики за краем окна стоят на паузе", not any(р["играет"] for р in за_окном),
                    "за окном с файлом %d, играют %d" % (len(за_окном), sum(р["играет"] for р in за_окном)),
                    собрано=len(за_окном))
                кнопок = с.evaluate("() => document.querySelectorAll('.pf-feed video[controls], .pf-feed button').length")
                шаг("в ленте нет плееров и кнопок", кнопок == 0, "органов %d" % кнопок,
                    отрицание="шаг про отсутствие органов: ноль и есть успех")

                ходы = [р["сдвиг"] - до["ряды"][i]["сдвиг"] for i, р in enumerate(после["ряды"])]
                шаг("верхний ряд едет вправо, нижний влево",
                    len(ходы) == 2 and ходы[0] > 1 and ходы[1] < -1,
                    "прокрутка %d px: верхний %s px, нижний %s px" % (
                        после["scrollY"] - до["scrollY"],
                        ("%+.1f" % ходы[0]) if ходы else "-",
                        ("%+.1f" % ходы[1]) if len(ходы) > 1 else "-"),
                    собрано=len(ходы))

                # ПЛАВНОСТЬ — ОТКЛОНЕНИЕ ОТ ПРЯМОЙ «сдвиг ряда ↔ прокрутка». Лента
                # едет от прокрутки, значит в кадрах, где секция в окне, сдвиг
                # лежит на прямой. Рывок — кадр, ушедший с неё. Отклонение
                # берётся меньшее из двух: к прокрутке этого кадра и прошлого —
                # сэмплер и обновление ленты стоят в одном кадре в разном
                # порядке, задержка на кадр законна. Прямую мерка строит сама
                # по кадрам, формулу из кода не берёт.
                видимые = [i for i, кд in enumerate(кадры) if кд["верх"] < кд["vh"] and кд["низ"] > 0]
                худшее = 0.0
                скорости = []
                без_прокрутки = 0
                for р in range(len(после["ряды"])):
                    точки = [(кадры[i]["y"], кадры[i]["ряды"][р][0], i) for i in видимые if i > 0]
                    if len(точки) < 3:
                        continue
                    n = len(точки)
                    sy = sum(x for x, _, _ in точки); ss = sum(s for _, s, _ in точки)
                    sxx = sum(x * x for x, _, _ in точки); sxs = sum(x * s for x, s, _ in точки)
                    знам = n * sxx - sy * sy
                    if not знам:
                        continue
                    k = (n * sxs - sy * ss) / знам
                    c = (ss - k * sy) / n
                    скорости.append(k)
                    for y, s, i in точки:
                        откл = min(abs(s - (c + k * y)), abs(s - (c + k * кадры[i - 1]["y"])))
                        худшее = max(худшее, откл)
                for a_, b_ in zip(кадры, кадры[1:]):
                    if a_["y"] == b_["y"] and any(abs(b_["ряды"][р][0] - a_["ряды"][р][0]) > 0.5
                                                  for р in range(len(b_["ряды"]))):
                        без_прокрутки += 1
                дыр = sum(1 for кд in кадры for _сд, лево, право in кд["ряды"]
                          if лево > 0.5 or право < после["vw"] - 0.5)
                if рывок:
                    print("  доказательство подлога: применено рывков %d" % с.evaluate("() => window.__рывков"))
                шаг("бег плавный: сдвиг ряда идёт за прокруткой без рывков",
                    скорости and худшее <= 2.0 and без_прокрутки == 0,
                    "кадров в окне %d, скорость ряда %s от прокрутки, худшее отклонение %.1f px, ход без прокрутки %d" % (
                        len(видимые), ["%.2f" % abs(k) for k in скорости], худшее, без_прокрутки),
                    собрано=len(видимые))
                шаг("лента бесшовна: ряд перекрывает окно в каждом кадре", дыр == 0,
                    "кадров с краем ряда внутри окна %d" % дыр, собрано=len(кадры))
                шаг("раскладка при беге не дёргается", сдвиги_раскладки < 0.001,
                    "сумма сдвигов раскладки %.4f" % сдвиги_раскладки)
                к.close()

                к = _контекст(бр, ш, в, сенсор, движение="reduce")
                if контроль:
                    к.add_init_script(ПОДЛОГ_ЖАДНО)
                с = к.new_page()
                с.goto(БАЗА + "/", wait_until="networkidle", timeout=60000)
                с.wait_for_timeout(800)
                до_т = с.evaluate(ЛЕНТА_СОСТОЯНИЕ)
                _прокрутить(с, ш, в, шагов)
                после_т = с.evaluate(ЛЕНТА_СОСТОЯНИЕ)
                ход_т = [abs(после_т["ряды"][i]["сдвиг"] - до_т["ряды"][i]["сдвиг"])
                         for i in range(len(до_т["ряды"]))]
                шаг("«уменьшить движение»: лента стоит, выключено — едет",
                    max(ход_т) < 0.5 and min(abs(х) for х in ходы) > 1,
                    "ход рядов: движение включено %s px, уменьшено %s px" % (
                        ["%.1f" % abs(х) for х in ходы], ["%.1f" % х for х in ход_т]),
                    собрано=min(len(ход_т), len(ходы)))
                с_файлом = [р for р in после_т["ролики"] if р["src"]]
                стоят = [р for р in с_файлом if not р["играет"] and р["готов"] >= 2]
                шаг("«уменьшить движение»: ролики не играют, первый кадр показан",
                    len(стоят) == len(с_файлом),
                    "с файлом %d, стоят с кадром %d" % (len(с_файлом), len(стоят)),
                    собрано=len(с_файлом))
                к.close()
        finally:
            бр.close()


# ══ D. О СЕБЕ ═════════════════════════════════════════════════════════

ЗАМЕР_О_СЕБЕ = r"""() => {
  const сек = document.querySelector('.pf-about');
  if (!сек) return null;
  const пр = e => { const b = e.getBoundingClientRect();
    return {x: b.left, y: b.top + scrollY, w: b.width, h: b.height, r: b.right, b: b.bottom + scrollY}; };
  const тело = document.querySelector('.pf-about-body');
  const полный = getComputedStyle(document.documentElement).getPropertyValue('--text-strong').trim();
  // Цвет «полного» знака берётся с эталонного узла, а не из токена: токен
  // приходит строкой #FFFFFF, а вычисленный цвет — rgb(...).
  const эталон = document.createElement('span');
  эталон.style.color = полный; document.body.appendChild(эталон);
  const цвет_полного = getComputedStyle(эталон).color; эталон.remove();
  const знаки = [...сек.querySelectorAll('.pf-ch')];
  const полных = знаки.filter(з => getComputedStyle(з).color === цвет_полного).length;
  const декор = [...сек.querySelectorAll('.pf-decor')].map(д => {
    const м = д.querySelector('.media-slot');
    const подпись = м.querySelector('.media-slot-empty');
    let обрезано = false;
    if (подпись) {
      const км = м.getBoundingClientRect();
      for (const т of подпись.querySelectorAll('span')) {
        const д2 = document.createRange(); д2.selectNodeContents(т);
        for (const к of д2.getClientRects()) {
          if (к.width && (к.left < км.left - 0.5 || к.right > км.right + 0.5 ||
                          к.top < км.top - 0.5 || к.bottom > км.bottom + 0.5)) обрезано = true;
        }
        if (т.scrollWidth > т.clientWidth + 1) обрезано = true;
      }
    }
    return {класс: [...д.classList].find(к => /^pf-decor-/.test(к)), место: пр(м),
            заполнено: м.dataset.filled, пусто: !!подпись, обрезано,
            видимость: parseFloat(getComputedStyle(д).opacity),
            сдвиг: new DOMMatrix(getComputedStyle(д).transform).m41,
            подъём: new DOMMatrix(getComputedStyle(д).transform).m42,
            масштаб: new DOMMatrix(getComputedStyle(д).transform).a};
  });
  return {vw: document.documentElement.clientWidth, vh: innerHeight, сек: пр(сек),
          тело: пр(тело), текст: пр(сек.querySelector('.pf-about-text')),
          знаков: знаки.length, полных, декор};
}"""

ШИРИНЫ_О_СЕБЕ = ШИРИНЫ + [(1101, 900, False)]


def _призыв_по_макету(дж):
    """Карточка-призыв письма 3б задачи 343 (шаг «E» режима инструментов)."""
    return (bool(дж) and дж["после_списка"] and дж["заголовок"] == "Это только начало"
            and bool(дж["кнопка"]) and "pf-cta-pill" in дж["кнопка"]["класс"].split()
            and "pf-cta-ghost" not in дж["кнопка"]["класс"].split() and дж["кнопка"]["высота"] >= 40
            and дж["лента"] == 8 and дж["скоро"] == 2
            and not дж["старое"]["растёт"] and not дж["старое"]["попробуйте"])


def _не_таблетки(вид):
    """Кнопки-призывы главной не того вида: основная обязана быть основной
    таблеткой, вторичная — вторичной (письмо 3б задачи 343)."""
    плохие = []
    for к_ in вид:
        классы = set(к_["класс"].split())
        нужно = {"pf-cta-pill", "pf-cta-ghost"} if к_["роль"] == "вторичная" else {"pf-cta-pill"}
        лишнее = {"pf-cta-ghost"} if к_["роль"] == "основная" else set()
        if not нужно <= классы or лишнее & классы:
            плохие.append("%s «%s» (%s)" % (к_["место"], к_["текст"], к_["класс"]))
    return плохие


def _декор_ждёт(д):
    """До доезда объект спрятан и опущен (письмо 3б задачи 343).

    ЗДЕСЬ СТОЯЛО «спрятан и отведён в свою сторону»: выезд с боков
    (`.pf-side`, заход 339) отменён владельцем — объекты появляются
    по очереди снизу, с `translateY(24px) scale(0.92)`. Подлог прежнего
    решения (сдвиг вбок вместо подъёма) шаг обязан назвать."""
    return д["видимость"] < 0.01 and д["подъём"] > 20 and abs(д["сдвиг"]) < 0.5 and д["масштаб"] < 0.95


def _декор_на_месте(д):
    return д["видимость"] > 0.99 and abs(д["сдвиг"]) < 0.5 and abs(д["подъём"]) < 0.5


def _пересекаются(а, б):
    return not (а["r"] <= б["x"] or б["r"] <= а["x"] or а["b"] <= б["y"] or б["b"] <= а["y"])


def _место(стр_админа, slot, действие, файл=None, тип="image/png"):
    if действие == "положить":
        with open(файл, "rb") as ф:
            ответ = стр_админа.request.post(
                БАЗА + "/admin/api/landing/" + slot,
                multipart={"file": {"name": os.path.basename(файл), "mimeType": тип, "buffer": ф.read()}},
                timeout=240000)
    else:
        ответ = стр_админа.request.delete(БАЗА + "/admin/api/landing/" + slot)
    return ответ.status


ПОЛОЖЕНИЕ_СЕКЦИИ = r"""(вид) => {
  // Положения выводятся из ГЕОМЕТРИИ СЕКЦИИ, а не из формулы скрипта:
  //   начало — верх текста у нижнего края окна;
  //   конец  — секция целиком в окне, а у секции выше окна — её верх
  //            у верхнего края (дальше «целиком» не бывает);
  //   середина — ровно посередине между ними по прокрутке.
  const т = document.querySelector('.pf-about-text'), с = document.querySelector('.pf-about');
  const vh = document.documentElement.clientHeight;
  const нач = т.getBoundingClientRect().top + scrollY - vh;
  const кс = с.getBoundingClientRect();
  const кон = scrollY + (кс.height <= vh ? кс.bottom - vh : кс.top);
  const y = вид === 'начало' ? нач : вид === 'конец' ? кон : (нач + кон) / 2;
  window.scrollTo(0, y);
  return {y, влезает: кс.height <= vh};
}"""

# ПОДЛОГ РАСЧЁТА ДОЛИ (заход 339, B): в отдаваемый скрипт возвращается
# прежняя формула — конец при низе ТЕКСТА на 40% окна. Ломается ровно
# звено «доля», замер и положения остаются прежними.
ПОДЛОГ_ДОЛИ = ("return путь > 0 ? Math.min(1, Math.max(0, пройдено / путь)) : 1;",
               "return Math.min(1, Math.max(0, (0.85 * vh - т.top) / (0.45 * vh + т.height)));")


def о_себе(контроль=False, контроль_доли=False):
    from PIL import Image, ImageDraw
    from playwright.sync_api import sync_playwright
    print("D. О СЕБЕ — гостем, головной браузер, стенд %s" % БАЗА)
    каталог = tempfile.mkdtemp(prefix="pf_")
    файл = os.path.join(каталог, "decor.png")
    im = Image.new("RGBA", (900, 900), (0, 0, 0, 0))
    ImageDraw.Draw(im).ellipse((150, 150, 750, 750), fill=(90, 200, 170, 255))
    im.save(файл)

    with sync_playwright() as p:
        бр = p.chromium.launch(headless=False)
        админ = бр.new_context()
        ад = админ.new_page()
        _войти(ад, *АДМИН)
        положили = False
        try:
            полные = {}
            for ш, в, сенсор in ШИРИНЫ_О_СЕБЕ:
                print("\n  ── %d×%d%s" % (ш, в, " (сенсор)" if сенсор else ""))
                к = _контекст(бр, ш, в, сенсор)
                с = к.new_page()
                замен = {"n": None}
                if контроль_доли:
                    def _подменить(маршрут):
                        тело = маршрут.fetch().text()
                        замен["n"] = тело.count(ПОДЛОГ_ДОЛИ[0])
                        маршрут.fulfill(body=тело.replace(*ПОДЛОГ_ДОЛИ),
                                        headers={"content-type": "application/javascript"})
                    с.route("**/static/landing.js*", _подменить)
                с.goto(БАЗА + "/", wait_until="networkidle", timeout=60000)
                if контроль_доли:
                    print("  ПОДЛОГ ДОЛИ: замен в скрипте %s (обязано быть 1)" % замен["n"])
                if контроль:
                    # ПОДЛОГ ЗВЕНЬЕВ «НА ТЕКСТЕ» И «ОБРЕЗАНО»: колонка во всю
                    # ширину и декор 5rem — ровно первая версия раскладки.
                    с.add_style_tag(content=".pf-about-body{max-width:none!important}"
                                    ".pf-decor{width:5rem!important}")
                с.wait_for_timeout(600)
                до = с.evaluate(ЗАМЕР_О_СЕБЕ)
                if до is None:
                    шаг("секция «О себе» есть", False, "нет .pf-about")
                    к.close()
                    continue
                print("  высота секции %.0f px" % до["сек"]["h"])
                # до доезда: знаки приглушены, декор спрятан и сдвинут наружу
                наружу = [д for д in до["декор"] if _декор_ждёт(д)]
                шаг("до доезда декор спрятан и опущен", len(наружу) == len(до["декор"]),
                    "объектов %d, спрятаны и опущены %d" % (len(до["декор"]), len(наружу)), собрано=len(до["декор"]))
                # ТРИ ПОЛОЖЕНИЯ (заход 339, B): в конце обязано быть 100 %.
                # ЗДЕСЬ СТОЯЛ ШАГ «у нижнего края 0, посередине меньше всего, выше всё»,
                # где «посередине» — верх текста на 55% окна, а «выше» — текст уехал
                # за верх экрана. Он был зелёным при дефекте: полноту спрашивал там,
                # где секции уже не видно. Положения теперь из геометрии секции.
                доли = {}
                for вид in ("начало", "середина", "конец"):
                    пол = с.evaluate(ПОЛОЖЕНИЕ_СЕКЦИИ, вид)
                    с.wait_for_timeout(700)
                    з3 = с.evaluate(ЗАМЕР_О_СЕБЕ)
                    доли[вид] = (з3["полных"], з3["знаков"], пол["влезает"])
                шаг("проявление: в начале меньше, в середине больше, когда секция в окне — 100 %",
                    доли["начало"][0] < доли["середина"][0] < доли["конец"][0] == доли["конец"][1],
                    "; ".join("%s %d/%d = %.0f%%" % (вид, д[0], д[1], 100.0 * д[0] / max(1, д[1]))
                              for вид, д in доли.items())
                    + ("" if доли["конец"][2] else " (секция выше окна: конец — её верх у края)"),
                    собрано=доли["конец"][1])
                с.wait_for_timeout(1200)
                после = с.evaluate(ЗАМЕР_О_СЕБЕ)
                выехали = [д for д in после["декор"] if _декор_на_месте(д)]
                шаг("декор выехал и встал на место", len(выехали) == len(после["декор"]),
                    "объектов %d, на месте %d" % (len(после["декор"]), len(выехали)), собрано=len(после["декор"]))
                на_тексте = [д["класс"] for д in после["декор"] if _пересекаются(д["место"], после["тело"])]
                шаг("декор не лежит на тексте и кнопке", not на_тексте,
                    "пересекают колонку: %s" % (на_тексте or "нет"), собрано=len(после["декор"]))
                пустых = [д for д in после["декор"] if д["пусто"]]
                обрезанных = [д["класс"] for д in пустых if д["обрезано"]]
                шаг("подпись пустого места декора не обрезана", not обрезанных,
                    "пустых %d, обрезанных %s" % (len(пустых), обрезанных or 0), собрано=len(пустых))
                полные[(ш, в)] = после
                к.close()

                к = _контекст(бр, ш, в, сенсор, движение="reduce")
                с = к.new_page()
                с.goto(БАЗА + "/", wait_until="networkidle", timeout=60000)
                с.wait_for_timeout(400)
                т = с.evaluate(ЗАМЕР_О_СЕБЕ)
                видны = [д for д in т["декор"] if _декор_на_месте(д)]
                шаг("«уменьшить движение»: текст целиком и декор на месте сразу, без прокрутки",
                    т["полных"] == т["знаков"] and len(видны) == len(т["декор"]),
                    "полных знаков %d из %d, декора на месте %d из %d" % (
                        т["полных"], т["знаков"], len(видны), len(т["декор"])), собрано=т["знаков"])
                к.close()

            # ── ПОДЛОГ: один декор положен и убран ──
            print("\n  ── подлог: декор «правый низ» положен, затем убран")
            было = next((д["заполнено"] for д in полные.get((1920, 1080), {}).get("декор", [])
                         if д["класс"] == "pf-decor-br"), None)
            if было != "no":
                шаг("правый нижний декор пуст — подлог можно провести", False,
                    "место заполнено (%s): чужой файл не трогаем" % было)
                return
            код = _место(ад, "decor-br", "положить", файл)
            положили = код == 200
            шаг("декор положен боевой загрузкой", положили, "HTTP %s" % код)

            def замер(ш, в, сенсор, подлог_css=None):
                к = _контекст(бр, ш, в, сенсор, движение="reduce")
                с = к.new_page()
                с.goto(БАЗА + "/", wait_until="networkidle", timeout=60000)
                if подлог_css:
                    с.add_style_tag(content=подлог_css)
                с.wait_for_timeout(400)
                з = с.evaluate(ЗАМЕР_О_СЕБЕ)
                к.close()
                return з
            с_файлом = {(ш, в): замер(ш, в, сн) for ш, в, сн in ШИРИНЫ_О_СЕБЕ}
            код = _место(ад, "decor-br", "убрать")
            if код == 200:
                положили = False
            шаг("декор убран из хранилища", код == 200, "HTTP %s" % код)
            for ш, в, сенсор in ШИРИНЫ_О_СЕБЕ:
                пустой = замер(ш, в, сенсор,
                               ".pf-decor-br{position:static!important}" if контроль else None)
                полный = с_файлом[(ш, в)]
                пд = {д["класс"]: д for д in полный["декор"]}
                сд = {д["класс"]: д for д in пустой["декор"]}
                сдвиг = max([abs(пд[к_]["место"][о] - сд[к_]["место"][о])
                             for к_ in пд if к_ != "pf-decor-br" for о in ("x", "y", "w", "h")] +
                            [abs(полный["тело"][о] - пустой["тело"][о]) for о in ("x", "y", "w", "h")])
                шаг("%d×%d: декор убран — заглушка встала, остальные три и текст не сдвинулись" % (ш, в),
                    сд["pf-decor-br"]["заполнено"] == "no" and сд["pf-decor-br"]["пусто"] and сдвиг <= 0.5,
                    "доказательство: заполнено %s→%s; сдвиг соседей %.2f px" % (
                        пд["pf-decor-br"]["заполнено"], сд["pf-decor-br"]["заполнено"], сдвиг))
        finally:
            if положили:
                print("  уборка: декор снят — HTTP %s" % _место(ад, "decor-br", "убрать"))
            бр.close()


# ══ E. ИНСТРУМЕНТЫ ════════════════════════════════════════════════════

СНИМОК_МАКЕТА = r"""(i) => {
  const м = document.querySelectorAll('[data-pf-anim]')[i];
  if (!м) return null;
  const знаки = [...м.querySelectorAll('.pf-t')];
  const видно = знаки.filter(з => getComputedStyle(з).visibility !== 'hidden').length;
  const счёт = [...м.querySelectorAll('[data-count-to]')].map(э => [э.textContent.trim(), э.dataset.countTo]);
  const полосы = [...м.querySelectorAll('.pf-bar-fill')].map(э =>
    [new DOMMatrix(getComputedStyle(э).transform).a, parseFloat(getComputedStyle(э).getPropertyValue('--pf-fill'))]);
  const кольца = [...м.querySelectorAll('.pf-ring-fill')].map(э =>
    // Вычисленное значение приходит строкой `calc(20px)`: голый
    // parseFloat дал бы NaN, а NaN не равен сам себе (первая версия
    // пробы на этом объявила кольцо неготовым).
    [parseFloat(getComputedStyle(э).strokeDashoffset.replace(/[^0-9.\-]/g, '')),
     parseFloat(getComputedStyle(э.closest('.pf-mock-ring')).getPropertyValue('--pf-fill'))]);
  const галочки = [...м.querySelectorAll('.pf-chk')].map(э => parseFloat(getComputedStyle(э).opacity));
  // ШАГИ (заход 339, D2) — по ВИДИМОМУ: рамка шага окрашена акцентом.
  // Цвет акцента берётся с эталонного узла в самом макете, не из класса.
  const эталон = document.createElement('span');
  эталон.style.color = 'var(--pf-acc)'; м.appendChild(эталон);
  const акцент = getComputedStyle(эталон).color; эталон.remove();
  const шаги = [...м.querySelectorAll('[data-pf-step]')];
  const шагов_готово = шаги.filter(ш => getComputedStyle(ш).borderTopColor === акцент).length;
  // Счёт собранного: число в подписи и сколько шагов в разметке.
  const счёт_собранного = [...м.querySelectorAll('[data-pf-tally]')].map(э =>
    [э.textContent.trim(), String((Number(э.dataset.countFrom) || 0) + шаги.length), String(Number(э.dataset.countFrom) || 0)]);
  const к = м.getBoundingClientRect();
  return {имя: м.closest('.pf-tool').querySelector('.pf-tool-h').textContent.trim(),
          состояние: м.dataset.pfState || '', знаков: знаки.length, видно, счёт, полосы, кольца, галочки,
          шагов: шаги.length, шагов_готово, счёт_собранного,
          в_окне: к.bottom > 0 && к.top < innerHeight,
          анимаций: м.getAnimations({subtree: true}).filter(а => а.playState === 'running').length};
}"""


def _конечный(с):
    """Снимок в КОНЕЧНОМ состоянии, записанном в разметке."""
    return (с["видно"] == с["знаков"]
            and all(т == ц for т, ц in с["счёт"])
            and all(abs(м - ц) < 0.01 for м, ц in с["полосы"])
            and all(abs(д - (100 - ц * 100)) < 0.6 for д, ц in с["кольца"])
            and all(г > 0.99 for г in с["галочки"])
            and с["шагов_готово"] == с["шагов"]
            and all(т == ц for т, ц, _ in с["счёт_собранного"]))


def _начальный(с):
    """Снимок в НАЧАЛЕ: ни одного знака, счётчики с начала, полоски пусты."""
    return (с["видно"] == 0
            and all(т == "0" for т, _ in с["счёт"])
            and all(м < 0.01 for м, _ in с["полосы"])
            and all(д > 99.4 for д, _ in с["кольца"])
            and all(г < 0.01 for г in с["галочки"])
            and с["шагов_готово"] == 0
            and all(т == н for т, _, н in с["счёт_собранного"]))


def _ключ(с):
    return (с["видно"], tuple(т for т, _ in с["счёт"]), tuple(round(м, 2) for м, _ in с["полосы"]),
            tuple(round(д, 1) for д, _ in с["кольца"]), tuple(round(г, 2) for г in с["галочки"]),
            с["шагов_готово"], tuple(т for т, _, _ in с["счёт_собранного"]))


# ПОДЛОГ ЗВЕНА «ЗАПУСК ОЖИВЛЕНИЯ»: наблюдатель пропускает интерфейс
# HH-ассистента — он остаётся в начале навсегда.
ПОДЛОГ_ЗАПУСК = r"""(() => {
  const было = IntersectionObserver.prototype.observe;
  window.__пропущено = 0;
  IntersectionObserver.prototype.observe = function (э) {
    if (э && э.dataset && э.dataset.pfAnim === 'hh') { window.__пропущено++; return; }
    return было.call(this, э);
  };
})();"""

# ПОДЛОГ ЗВЕНА «ПОВТОР» (заход 339, D3): в отдаваемый скрипт вставляется
# пропуск возврата в начало у ОДНОГО интерфейса — тренировок. Запуск
# у него и у остальных четырёх остаётся прежним.
ПОДЛОГ_ПОВТОР = ("в_начало(м);   // ушёл из окна целиком",
                 "if (м.dataset.pfAnim !== 'workout') в_начало(м);   // ушёл из окна целиком")

ЗАМЕР_СЕКЦИИ = r"""() => {
  const rgb = s => { const m = s.match(/rgba?\(([^)]+)\)/); const v = m[1].split(',').map(parseFloat);
    return {r: v[0], g: v[1], b: v[2], a: v.length > 3 ? v[3] : 1}; };
  const lum = c => { const f = x => { x /= 255; return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b); };
  const mix = (t, b) => ({r: t.r * t.a + b.r * (1 - t.a), g: t.g * t.a + b.g * (1 - t.a), b: t.b * t.a + b.b * (1 - t.a), a: 1});
  const фон_тела = rgb(getComputedStyle(document.body).backgroundColor);
  const фон = э => { const слои = []; for (let x = э; x; x = x.parentElement) {
      const c = rgb(getComputedStyle(x).backgroundColor); if (c.a > 0) слои.push(c); if (c.a >= 1) break; }
    let итог = фон_тела; for (const c of слои.reverse()) итог = mix(c, итог); return итог; };
  const сек = document.querySelector('.pf-tools');
  if (!сек) return null;
  const hex = c => '#' + [c.r, c.g, c.b].map(x => Math.round(x).toString(16).padStart(2, '0')).join('');
  const вне = {мин: 99, ниже: 0, всего: 0}, внутри = {мин: 99, всего: 0}, кнопки = [];
  const обход = document.createTreeWalker(сек, NodeFilter.SHOW_TEXT);
  const видели = new Set(); let узел;
  while ((узел = обход.nextNode())) {
    if (!узел.textContent.trim()) continue;
    const э = узел.parentElement; if (видели.has(э)) continue; видели.add(э);
    const cs = getComputedStyle(э);
    if (cs.visibility === 'hidden' || !э.getClientRects().length || э.closest('.pf-grad')) continue;
    const ф = фон(э), ц = mix(rgb(cs.color), ф);
    const l1 = lum(ц), l2 = lum(ф), k = (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
    const px = parseFloat(cs.fontSize), крупный = px >= 24 || (parseInt(cs.fontWeight) >= 700 && px >= 18.66);
    // Подпись системной `.btn-primary` (белый на акценте, 3.13) — принятое
    // решение BACKLOG №33, а не находка секции; печатается отдельно.
    // С письма 3б задачи 343 кнопка карточки — таблетка с градиентом: белый
    // на ней проверяется по опорным точкам градиента (режим «макет»), а не
    // по цвету под кнопкой.
    if (э.closest('.btn-primary, .pf-cta-pill')) { кнопки.push(+k.toFixed(2)); continue; }
    if (э.closest('.pf-mock')) { внутри.всего++; внутри.мин = Math.min(внутри.мин, k); }
    else { вне.всего++; вне.мин = Math.min(вне.мин, k); if (k < (крупный ? 3 : 4.5)) вне.ниже++; }
  }
  return {страница: hex(фон_тела), секция: hex(фон(сек)), радиус: parseFloat(getComputedStyle(сек).borderTopLeftRadius),
          вне, внутри, кнопки,
          // Карточка-призыв (письмо 3б задачи 343): после списка, по макету,
          // прежних «список растёт» и «Попробуйте инструменты сами» нет.
          join: (() => { const б = сек.querySelector('.pf-join'), сп = сек.querySelector('.pf-tool-list');
            if (!б) return null; const а = б.querySelector('a[href="/register"]');
            const з = б.querySelector('.pf-join-h');
            return {после_списка: !!сп && б.getBoundingClientRect().top >= сп.getBoundingClientRect().bottom,
                    заголовок: з ? з.textContent.replace(/\s+/g, ' ').trim() : null,
                    кнопка: а ? {класс: а.className, высота: а.getBoundingClientRect().height} : null,
                    лента: б.querySelectorAll('.pf-join-reel .pf-mini').length,
                    скоро: б.querySelectorAll('.pf-soon').length,
                    старое: {растёт: !!document.querySelector('.pf-grow'),
                             попробуйте: /Попробуйте инструменты сами/.test(document.querySelector('main').textContent)}}; })()};
}"""

# До правки захода 339 минимум внутри макетов был 4.12 — метка «AI»
# на своей заливке. Правка C не имела права опустить его.
МАКЕТЫ_КОНТРАСТ_БЫЛО = 4.12


def _въехать(с, i, откуда):
    """Увести интерфейс целиком из окна (выше либо ниже) и вернуть в центр."""
    с.evaluate("""([i, откуда]) => { const м = document.querySelectorAll('[data-pf-anim]')[i];
        const к = м.getBoundingClientRect(), y = к.top + scrollY;
        window.scrollTo(0, откуда === 'сверху' ? y + к.height + 40 : y - innerHeight - к.height - 40); }""",
               [i, откуда])
    с.wait_for_timeout(500)
    вне = с.evaluate(СНИМОК_МАКЕТА, i)
    с.evaluate("""(i) => document.querySelectorAll('[data-pf-anim]')[i]
                  .scrollIntoView({block: 'center', behavior: 'instant'})""", i)
    кадры = []
    for _ in range(90):
        кадр = с.evaluate(СНИМОК_МАКЕТА, i)
        кадры.append(кадр)
        if кадр["состояние"] == "done":
            break
        с.wait_for_timeout(100)
    return вне, кадры


ЦИКЛ_НАБЛЮДАТЕЛЯ = r"""(y) => new Promise(готово => {
  // МГНОВЕННО: у html стоит scroll-behavior: smooth, и голый scrollTo
  // запускал ПЛАВНУЮ прокрутку — прежний шаг читал состояние посреди неё
  window.scrollTo({top: y, behavior: 'instant'});
  window.__скролл_t = performance.now();
  const н = new IntersectionObserver(() => { н.disconnect(); setTimeout(готово, 0); });
  document.querySelectorAll('[data-pf-anim]').forEach(м => н.observe(м));
})"""

# ПОДЛОГ СБРОСА: у макета №1 теряется уведомление наблюдателя страницы
# об уходе из окна — ровно то звено, которое гонка подменяла по времени.
# Свой наблюдатель пробы (без порога 0.35) не трогается.
ПОДЛОГ_СБРОС = r"""(() => {
  const Исх = window.IntersectionObserver;
  window.__уходов_потеряно = 0;
  window.IntersectionObserver = function (cb, opts) {
    const страничный = opts && [].concat(opts.threshold || []).includes(0.35);
    const обёртка = страничный ? (записи, н) => cb(записи.filter(з => {
      const лишний = з.target === document.querySelectorAll('[data-pf-anim]')[1] && !з.isIntersecting;
      if (лишний) window.__уходов_потеряно++;
      return !лишний; }), н) : cb;
    return new Исх(обёртка, opts);
  };
  window.IntersectionObserver.prototype = Исх.prototype;
})();"""


def _кадров(с):
    """Кадров requestAnimationFrame за 500 мс — идёт ли отрисовка окна."""
    return с.evaluate("""() => new Promise(r => { let n = 0; const t0 = performance.now();
        const f = () => { n++; if (performance.now() - t0 < 500) requestAnimationFrame(f); };
        requestAnimationFrame(f); setTimeout(() => r(n), 520); })""")


def _отрисовка_идёт(с, где):
    """ОСТАНОВКА ОТРИСОВКИ ОКНА — НЕ НАХОДКА ПРО МАКЕТЫ (письмо 2 задачи 343).
    Замер 40 прогонов: трижды у головного окна переставали идти кадры
    (0–1 кадр за 500 мс при visibilityState visible), таймеры страницы шли,
    а кадры и наблюдатель — нет, и режим печатал 15 ПЛОХО про исправные
    макеты. Причина не установлена: не свёрнутость, не стык мониторов,
    не перекрытие другим окном (опыты в отчёте). Мерить оживление без кадров
    нечем — это ПРОПУСК с числом кадров, а не OK и не ПЛОХО."""
    кадров = _кадров(с)
    if кадров <= 2:
        итог["пропуск"] += 1
        print("  %-7s %s: отрисовка окна стоит — кадров за 500 мс %d, оживление не мерится"
              % ("ПРОПУСК", где, кадров))
        return False
    return True


def инструменты(контроль=False, контроль_повтора=False, контроль_сброса=False):
    from playwright.sync_api import sync_playwright
    print("E. ИНСТРУМЕНТЫ — гостем, головной браузер, стенд %s%s%s" % (
        БАЗА, " · ПОДЛОГ: запуск оживления HH-ассистента сломан" if контроль else "",
        " · ПОДЛОГ: повтор у программы тренировок сломан" if контроль_повтора else ""))
    with sync_playwright() as p:
        бр = p.chromium.launch(headless=False)
        try:
            for ш, в, сенсор in ШИРИНЫ:
                print("\n  ── %d×%d%s" % (ш, в, " (сенсор)" if сенсор else ""))
                к = _контекст(бр, ш, в, сенсор)
                if контроль:
                    к.add_init_script(ПОДЛОГ_ЗАПУСК)
                if контроль_сброса:
                    к.add_init_script(ПОДЛОГ_СБРОС)
                с = к.new_page()
                замен = {"n": None}
                if контроль_повтора:
                    def _подменить(маршрут):
                        тело = маршрут.fetch().text()
                        замен["n"] = тело.count(ПОДЛОГ_ПОВТОР[0])
                        маршрут.fulfill(body=тело.replace(*ПОДЛОГ_ПОВТОР),
                                        headers={"content-type": "application/javascript"})
                    с.route("**/static/landing.js*", _подменить)
                с.goto(БАЗА + "/", wait_until="networkidle", timeout=60000)
                с.wait_for_timeout(500)
                if контроль_повтора:
                    print("  доказательство подлога: замен в скрипте %s (обязано быть 1)" % замен["n"])
                список = с.evaluate("""() => [...document.querySelectorAll('.pf-tool')].map(л => ({
                    н: (л.querySelector('.pf-tool-n') || {}).textContent,
                    имя: (л.querySelector('.pf-tool-h') || {}).textContent,
                    макет: !!л.querySelector('[data-pf-anim]')}))""")
                шаг("инструментов в списке 5, у каждого номер, название и интерфейс",
                    len(список) == 5 and all(л["н"] and л["имя"] and л["макет"] for л in список),
                    ", ".join("%s %s" % (л["н"], л["имя"]) for л in список), собрано=len(список))
                if контроль:
                    print("  доказательство подлога: наблюдение пропущено у %d интерфейсов" %
                          с.evaluate("() => window.__пропущено"))

                # ── C: секция отделена фоном, контраст не упал ──
                сек = с.evaluate(ЗАМЕР_СЕКЦИИ)
                # ПЕРЕПИСАНО ПИСЬМОМ 3а ЗАДАЧИ 343 (§6.0.3, четыре пункта).
                # Прежде: «секция на ступень светлее страницы, верхние углы
                # скруглены» — фон секции != фону страницы и радиус > 0.
                # Теперь: секция на общем фоне — фон равен фону страницы, радиус 0.
                # Причина: решение владельца убрать подложку с жёсткой верхней
                # границей отменило решение захода 339 (блок C).
                # Контроль на новой формулировке: подложка `--surface-1`
                # со скруглением, подложенная в страницу, даёт ПЛОХО (отчёт захода).
                шаг("секция инструментов на общем фоне: своей подложки нет, верхние углы не скруглены",
                    сек is not None and сек["секция"] == сек["страница"] and сек["радиус"] == 0,
                    "фон страницы %s, секции %s, радиус %.0f px" % (
                        (сек or {}).get("страница"), (сек or {}).get("секция"), (сек or {}).get("радиус", 0)))
                дж = (сек or {}).get("join")
                # ЗДЕСЬ СТОЯЛИ ТРИ ШАГА — «E: блок регистрации…», «E3: строка
                # „список растёт“…» и «E4: заголовок призыва… кнопка со свечением».
                # Решение владельца (письмо 3б задачи 343) объединило оба блока
                # в карточку по макету: прежние шаги требовали отменённое.
                # Подлог: вернуть строку «список растёт» — шаг падает.
                шаг("E: после списка — карточка «Это только начало» с лентой и кнопкой-таблеткой; прежних блоков нет",
                    _призыв_по_макету(дж), "%s" % дж)
                шаг("текст секции вне макетов не ниже порога контраста",
                    сек is not None and сек["вне"]["ниже"] == 0,
                    "текстов %d, минимум %.2f, ниже порога %d" % (
                        сек["вне"]["всего"], сек["вне"]["мин"], сек["вне"]["ниже"]), собрано=сек["вне"]["всего"])
                стоит = False
                for i in range(len(список)):
                    отложено = []

                    def отлож(имя, условие, подробность="", собрано=None, _о=отложено):
                        _о.append((имя, условие, подробность, собрано))
                    # СВОЯ ЗАГРУЗКА НА КАЖДЫЙ ИНТЕРФЕЙС: соседний мог начать
                    # играть, пока проба стояла у предыдущего.
                    с.goto(БАЗА + "/", wait_until="networkidle", timeout=60000)
                    с.wait_for_timeout(300)
                    нач = с.evaluate(СНИМОК_МАКЕТА, i)
                    if not _отрисовка_идёт(с, "%d×%d %s" % (ш, в, нач["имя"])):
                        стоит = True
                        break
                    с.evaluate("""(i) => document.querySelectorAll('[data-pf-anim]')[i]
                                  .scrollIntoView({block: 'center', behavior: 'instant'})""", i)
                    кадры = []
                    for _ in range(90):
                        кадр = с.evaluate(СНИМОК_МАКЕТА, i)
                        кадры.append(кадр)
                        if кадр["состояние"] == "done":
                            break
                        с.wait_for_timeout(100)
                    кон = кадры[-1]
                    промежуточных = len({_ключ(к_) for к_ in кадры})
                    отлож("%s: оживает при доезде — из начала в конец" % нач["имя"],
                        _начальный(нач) and кон["состояние"] == "done" and _конечный(кон) and промежуточных > 2,
                        "в начале %s, в конце %s (%s), разных кадров %d" % (
                            "да" if _начальный(нач) else "нет", "да" if _конечный(кон) else "нет",
                            кон["состояние"] or "без состояния", промежуточных))
                    if нач["шагов"]:
                        ряд = []
                        for к_ in кадры:
                            if not ряд or ряд[-1] != к_["шагов_готово"]:
                                ряд.append(к_["шагов_готово"])
                        по_одному = ряд == list(range(0, нач["шагов"] + 1))
                        отлож("%s: шаги встают по одному" % нач["имя"], по_одному,
                            "готовых шагов по кадрам: %s из %d" % (" → ".join(map(str, ряд)), нач["шагов"]),
                            собрано=нач["шагов"])
                    с.wait_for_timeout(3000)
                    позже = с.evaluate(СНИМОК_МАКЕТА, i)
                    отлож("%s: пока в окне — один проход, через 3 с ничего не движется" % нач["имя"],
                        _ключ(позже) == _ключ(кон) and позже["анимаций"] == 0 and _конечный(позже),
                        "снимок совпал: %s, анимаций идёт %d" % (
                            "да" if _ключ(позже) == _ключ(кон) else "нет", позже["анимаций"]))
                    # ── D3: три новых въезда = три прохода ──
                    проходов, ход = 0, []
                    for откуда in ("снизу", "сверху", "снизу"):
                        вне, кадры = _въехать(с, i, откуда)
                        прошёл = (not вне["в_окне"] and _начальный(вне)
                                  and any(not _конечный(к_) for к_ in кадры) and _конечный(кадры[-1]))
                        проходов += прошёл
                        ход.append("%s: вне окна %s, конец %s" % (
                            откуда, "в начале" if _начальный(вне) else "НЕ в начале",
                            "да" if _конечный(кадры[-1]) else "нет"))
                    отлож("%s: при трёх заездах в окно — три прохода" % нач["имя"], проходов == 3,
                        "проходов %d; %s" % (проходов, "; ".join(ход)))
                    # ОСТАНОВКА ОТРИСОВКИ ПОСРЕДИ ИНТЕРФЕЙСА: шаги этого интерфейса
                    # печатаются ПОСЛЕ замера кадров. Кадры стоят — провалы
                    # не про макет, а про окно: ПРОПУСК с числом кадров.
                    кадров = _кадров(с)
                    for имя, условие, подробность, собрано in отложено:
                        if кадров <= 2 and not условие:
                            итог["пропуск"] += 1
                            print("  %-7s %s — кадров окна за 500 мс после интерфейса %d, мерить нечем (было: %s)"
                                  % ("ПРОПУСК", имя, кадров, подробность[:90]))
                        else:
                            шаг(имя, условие, подробность, собрано=собрано)
                    if кадров <= 2:
                        стоит = True
                        break

                # ── D5: запуск по мере въезда, а не все разом ──
                с.goto(БАЗА + "/", wait_until="networkidle", timeout=60000)
                с.wait_for_timeout(300)
                if стоит or not _отрисовка_идёт(с, "%d×%d запуск по мере въезда" % (ш, в)):
                    верх, низ = 0, -1
                else:
                    верх, низ = с.evaluate("""() => { const с = document.querySelector('.pf-tools').getBoundingClientRect();
                    return [с.top + scrollY - innerHeight, с.bottom + scrollY]; }""")
                одновременно, вне_окна, замеров = 0, 0, 0
                y = верх
                while y <= низ:
                    # ГОНКА, А НЕ ПЛАВАЮЩИЙ СБОЙ (письмо 2 задачи 343, блок 3). Здесь
                    # стояло «прокрутить и подождать 120 мс». Сброс макета ставит
                    # IntersectionObserver страницы, а его уведомление приходит
                    # в цикле отрисовки, не по часам: замер — макет целиком выше
                    # окна (низ −7 px) в состоянии play через 137 мс после
                    # прокрутки, 1 прогон из 20. Теперь прокрутка и СВОЙ
                    # наблюдатель на те же макеты — одним вызовом: первый вызов
                    # нового наблюдателя приходит в том же цикле, что сброс
                    # страницы, и после него (наблюдатели уведомляются в порядке
                    # создания). Ожидание — событие, а не время.
                    с.evaluate(ЦИКЛ_НАБЛЮДАТЕЛЯ, y)
                    играет, играет_вне, подробно = с.evaluate("""() => { const и = [...document.querySelectorAll('[data-pf-anim]')]
                        .filter(м => м.dataset.pfState === 'play');
                      const вне = и.filter(м => { const к = м.getBoundingClientRect();
                        return к.bottom <= 0 || к.top >= innerHeight; });
                      const все = [...document.querySelectorAll('[data-pf-anim]')];
                      return [и.length, вне.length, вне.map(м => { const к = м.getBoundingClientRect();
                        return {i: все.indexOf(м), top: +к.top.toFixed(2), bottom: +к.bottom.toFixed(2), vh: innerHeight,
                                state: м.dataset.pfState, мс_от_прокрутки: Math.round(performance.now() - window.__скролл_t),
                                scrollY}; })]; }""")
                    if подробно:
                        with open(os.environ.get("PF_FLAKE_LOG") or os.path.join(tempfile.gettempdir(), "pf_flake.log"),
                                  "a", encoding="utf-8") as фл:
                            фл.write("%d×%d %s" % (ш, в, подробно) + chr(10))
                    одновременно = max(одновременно, играет)
                    вне_окна = max(вне_окна, играет_вне)
                    замеров += 1
                    y += в / 3
                if контроль_сброса:
                    print("  доказательство подлога: уходов из окна у макета №1 потеряно %s"
                          % с.evaluate("() => window.__уходов_потеряно"))
                шаг("запуск по мере въезда: вне окна не играет ни один, все разом — никогда",
                    вне_окна == 0 and одновременно < len(список),
                    "за прокрутку секции замеров %d, одновременно играло максимум %d из %d, вне окна %d" % (
                        замеров, одновременно, len(список), вне_окна), собрано=замеров)
                к.close()

                к = _контекст(бр, ш, в, сенсор, движение="reduce")
                с = к.new_page()
                с.goto(БАЗА + "/", wait_until="networkidle", timeout=60000)
                с.wait_for_timeout(400)
                снимки = [с.evaluate(СНИМОК_МАКЕТА, i) for i in range(len(список))]
                # Контраст внутри макетов — в КОНЕЧНОМ виде: в начале значения
                # подходов прозрачны нарочно, и мерка засчитала бы их за 1.00.
                сек = с.evaluate(ЗАМЕР_СЕКЦИИ)
                шаг("контраст внутри макетов в конечном виде не опустился ниже прежнего",
                    сек is not None and сек["внутри"]["мин"] >= МАКЕТЫ_КОНТРАСТ_БЫЛО - 0.005,
                    "минимум %.2f, до правки %.2f" % (сек["внутри"]["мин"], МАКЕТЫ_КОНТРАСТ_БЫЛО),
                    собрано=сек["внутри"]["всего"])

                готовых = [сн["имя"] for сн in снимки if сн and _конечный(сн)]
                шаг("«уменьшить движение»: все интерфейсы в конечном состоянии без прокрутки",
                    len(готовых) == len(снимки),
                    "готовых %d из %d" % (len(готовых), len(снимки)), собрано=len(снимки))
                к.close()
        finally:
            бр.close()


# ══ F2. СВЯЗАТЬСЯ (заход 339, блок F) ════════════════════════════════

# ПОДЛОГ ЗВЕНА «БУФЕР»: у страницы нет `navigator.clipboard` — как на
# странице без защищённого соединения или в браузере без разрешения.
ПОДЛОГ_БУФЕР = r"""(() => {
  try { Object.defineProperty(Navigator.prototype, 'clipboard', {get: () => undefined, configurable: true}); } catch (e) {}
  try { Object.defineProperty(navigator, 'clipboard', {get: () => undefined, configurable: true}); } catch (e) {}
})();"""

ЗАМЕР_СВЯЗИ = r"""(место) => {
  const б = document.querySelector('.pf-contact-' + место);
  if (!б) return null;
  const поп = б.querySelector('.pf-contact-pop'), адрес = б.querySelector('[data-pf-contact-addr]');
  const видим = э => !!э && э.checkVisibility({checkOpacity: true, checkVisibilityCSS: true});
  const пр = э => { const r = э.getBoundingClientRect(); return {l: r.left, r: r.right, t: r.top, b: r.bottom, w: r.width, h: r.height}; };
  const итог = б.querySelector('[data-pf-contact-status]');
  const выделено = String(window.getSelection());
  const кп = поп.getBoundingClientRect();
  const кн = б.querySelector('summary').getBoundingClientRect();
  // D1: строки и их части — только то, что видно человеку
  const строки = [...поп.querySelectorAll('.pf-contact-row')].filter(видим).map(с => {
    const гл = с.querySelector('.pf-contact-main'), ико = с.querySelector('.pf-contact-ico'),
          зн = с.querySelector('.pf-contact-val'),
          дей = [...с.querySelectorAll('.pf-contact-act')].filter(видим);
    return {href: гл ? гл.getAttribute('href') : '', значение: видим(зн) ? зн.textContent.trim() : '',
            ико: видим(ико) ? пр(ико) : null, действий: дей.length, дей: дей.length ? пр(дей[0]) : null,
            копия_видна: видим(с.querySelector('.pf-contact-act-copy')),
            галочка_видна: видим(с.querySelector('.pf-contact-act-done'))};
  });
  // D3: уголок — псевдоэлемент; его центр по x = левый край карточки + вычисленный left
  const уг = getComputedStyle(поп, '::after');
  const уголок_x = кп.left + parseFloat(уг.left);
  const ир = итог.getBoundingClientRect();
  return {открыт: б.open, карточка_видна: видим(поп), адрес: видим(адрес) ? адрес.textContent.trim() : '',
          итог: итог.textContent.trim(), итог_виден_глазу: видим(итог) && ир.width > 2 && ир.height > 2,
          выделено, строки,
          текст_карточки: поп.innerText,
          уголок: {x: уголок_x, есть: уг.content !== 'none', кнопка_l: кн.left, кнопка_r: кн.right,
                   под_карточкой: кп.bottom <= кн.top + 0.5},
          анимация: getComputedStyle(поп).animationName, ширина_карточки: кп.width, ширина_кнопки: кн.width,
          в_окне: кп.left >= -0.5 && кп.right <= document.documentElement.clientWidth + 0.5 && кп.top >= 0};
}"""

# D6: «Связаться» ВНЕ первого экрана одного вида — сверяются вычисленные
# свойства кнопки. ЗДЕСЬ СТОЯЛО «все три одного вида» (заход 342). Письмо 2
# задачи 343 дало первому экрану свою кнопку-таблетку с градиентом — решение
# владельца, и прежняя формулировка стала требовать обратного макету. Вид
# таблетки спрашивает `--макет`; здесь — две оставшиеся и текст у всех трёх.
# Отрицательный контроль новой формулировки — в отчёте письма 2 (радиус
# кнопки финала подменён: шаг обязан упасть).
ЗАМЕР_КНОПОК_СВЯЗИ = r"""() => {
  // Все кнопки-призывы главной: «Связаться» (summary) и «Зарегистрироваться»
  // (ссылка). Вторичная — ссылка в ряду финала рядом с основной.
  const кнопки = [...document.querySelectorAll('main summary, main a[href="/register"]')]
    .filter(э => /^(Связаться|Зарегистрироваться)$/i.test(э.textContent.trim()));
  return кнопки.map(э => {
    const вторичная = !!э.closest('.pf-final-btns') && э.tagName === 'A';
    const секция = э.closest('section');
    const r = э.getBoundingClientRect();
    return {место: секция ? (секция.id || секция.className.split(' ')[0]) : '?', текст: э.textContent.trim(),
            класс: э.className, роль: вторичная ? 'вторичная' : 'основная', h: Math.round(r.height * 10) / 10};
  });
}"""


def связь(контроль_буфера=False):
    from playwright.sync_api import sync_playwright
    print("D. СВЯЗАТЬСЯ — гостем, головной браузер, стенд %s%s" % (
        БАЗА, " · ПОДЛОГ: буфер обмена недоступен" if контроль_буфера else ""))
    with sync_playwright() as p:
        бр = p.chromium.launch(headless=False)
        try:
            for ш, в, сенсор in ШИРИНЫ:
                print("\n  ── %d×%d%s" % (ш, в, " (сенсор)" if сенсор else ""))
                к = _контекст(бр, ш, в, сенсор, движение="reduce")
                к.grant_permissions(["clipboard-read", "clipboard-write"], origin=БАЗА)
                if контроль_буфера:
                    к.add_init_script(ПОДЛОГ_БУФЕР)
                с = к.new_page()
                с.goto(БАЗА + "/", wait_until="networkidle", timeout=60000)
                с.wait_for_timeout(300)
                if контроль_буфера:
                    print("  доказательство подлога: navigator.clipboard = %s" %
                          с.evaluate("() => String(navigator.clipboard)"))
                кнопки = с.evaluate("""() => [...document.querySelectorAll('main a, main summary, main button')]
                    .filter(э => э.textContent.trim() === 'Связаться')
                    .map(э => ({тег: э.tagName, href: э.getAttribute('href') || ''}))""")
                шаг("кнопок «Связаться» на странице 3, и ни одна не голый mailto:",
                    len(кнопки) == 3 and all(к_["тег"] == "SUMMARY" for к_ in кнопки),
                    ", ".join("%s %s" % (к_["тег"], к_["href"]) for к_ in кнопки), собрано=len(кнопки))
                вид = с.evaluate(ЗАМЕР_КНОПОК_СВЯЗИ)
                # ЗДЕСЬ СТОЯЛ ШАГ «D6: две „Связаться“ вне первого экрана одного
                # вида»: у «Обо мне» и финала была системная `.btn-primary`,
                # у первого экрана — своя таблетка. Решение владельца (письмо 3б
                # задачи 343): все кнопки-призывы главной — таблетки одного стиля.
                # Подлог: одной кнопке вернуть `.btn-primary` — шаг её называет.
                плохие = _не_таблетки(вид)
                высоты = sorted({к_["h"] for к_ in вид})
                шаг("D6: все кнопки-призывы главной — таблетки одного класса и одной высоты",
                    len(вид) == 5 and not плохие and высоты[-1] - высоты[0] <= 1,
                    "кнопок %d; не тем классом: %s; высоты %s" % (len(вид), "; ".join(плохие) or "нет", высоты),
                    собрано=len(вид))
                if контроль_буфера:
                    # в буфере заранее другое — чтобы «скопировано» нельзя было засчитать
                    с.evaluate("() => { const t = document.createElement('textarea'); t.value = 'другое'; document.body.append(t); t.select(); document.execCommand('copy'); t.remove(); }")
                for место in ("hero", "about", "final"):
                    кн = с.locator(".pf-contact-%s summary" % место)
                    if not кн.count():
                        шаг("%s: кнопка есть" % место, False, "нет .pf-contact-%s" % место)
                        continue
                    кн.scroll_into_view_if_needed()
                    с.wait_for_timeout(200)
                    кн.click()
                    с.wait_for_timeout(300)
                    з = с.evaluate(ЗАМЕР_СВЯЗИ, место)
                    шаг("%s: нажатие раскрывает карточку, адрес виден, карточка в окне" % место,
                        з["открыт"] and з["карточка_видна"] and з["адрес"] == "pr@energydess.ru" and з["в_окне"],
                        "открыт %s, адрес «%s», в окне %s" % (з["открыт"], з["адрес"], з["в_окне"]))
                    ст = з["строки"]
                    ожид = [("mailto:pr@energydess.ru", "pr@energydess.ru"), ("https://t.me/energydess", "@energydess")]
                    факт = [(х["href"], х["значение"]) for х in ст]
                    шаг("%s: D1 — строк 2: почта и телеграм, у каждой значок, значение и одно действие" % место,
                        факт == ожид and all(х["ико"] and х["действий"] == 1 for х in ст),
                        "строк %d: %s; значков %s, действий %s" % (len(ст), факт,
                            [bool(х["ико"]) for х in ст], [х["действий"] for х in ст]),
                        отрицание="ноль строк — это находка, а не пустой замер: список не равен ожидаемым двум")
                    if len(ст) == 2 and all(х["ико"] and х["дей"] for х in ст):
                        dl = abs(ст[0]["ико"]["l"] - ст[1]["ико"]["l"])
                        dr = abs(ст[0]["дей"]["r"] - ст[1]["дей"]["r"])
                        dc = abs((ст[0]["дей"]["l"] + ст[0]["дей"]["r"]) - (ст[1]["дей"]["l"] + ст[1]["дей"]["r"])) / 2
                        шаг("%s: значки на одной вертикали, действия на одной вертикали" % место,
                            dl <= 1 and dr <= 1 and dc <= 1,
                            "значки Δлево %.1f px, действия Δправо %.1f, Δцентр %.1f" % (dl, dr, dc))
                    шаг("%s: D2 — строки «Открыть почтовую программу» нет" % место,
                        "почтовую программу" not in з["текст_карточки"],
                        "текст карточки: %s" % " | ".join(з["текст_карточки"].split("\n")))
                    уг = з["уголок"]
                    шаг("%s: D3 — уголок под карточкой и над кнопкой" % место,
                        уг["есть"] and уг["под_карточкой"] and уг["кнопка_l"] <= уг["x"] <= уг["кнопка_r"],
                        "уголок x %.1f, кнопка %.1f…%.1f, карточка над кнопкой %s" % (
                            уг["x"], уг["кнопка_l"], уг["кнопка_r"], уг["под_карточкой"]))
                    if ш <= 600:
                        шаг("%s: на узком карточка под ширину кнопки" % место,
                            abs(з["ширина_карточки"] - з["ширина_кнопки"]) <= 1,
                            "карточка %.1f px, кнопка %.1f px" % (з["ширина_карточки"], з["ширина_кнопки"]))
                    шаг("%s: D4 — при «уменьшить движение» раскрытие без анимации" % место,
                        з["анимация"] == "none", "animation-name %s" % з["анимация"])
                    с.locator(".pf-contact-%s [data-pf-contact-copy]" % место).click()
                    с.wait_for_timeout(300)
                    з = с.evaluate(ЗАМЕР_СВЯЗИ, место)
                    буфер = с.evaluate("() => navigator.clipboard ? navigator.clipboard.readText() : null") \
                        if not контроль_буфера else None
                    почта = з["строки"][0] if з["строки"] else {}
                    if контроль_буфера:
                        # Доказательство, что обычный шаг копирования не слеп:
                        # на подлоге его условие обязано быть ЛОЖНЫМ.
                        обычный = почта.get("галочка_видна") and з["итог"].startswith("Скопировано")
                        print("  доказательство: обычный шаг «скопировано» на подлоге дал бы %s (галочка %s, итог «%s»)" % (
                            "OK — ШАГ СЛЕП" if обычный else "ПЛОХО", почта.get("галочка_видна"), з["итог"]))
                        шаг("%s: D7 — буфер недоступен: адрес виден, выделен, отказ словами на виду" % место,
                            з["адрес"] == "pr@energydess.ru" and з["выделено"].strip() == "pr@energydess.ru"
                            and "не удалось" in з["итог"] and з["итог_виден_глазу"] and not почта.get("галочка_видна"),
                            "адрес «%s», выделено «%s», итог «%s» виден %s, галочка %s" % (
                                з["адрес"], з["выделено"].strip(), з["итог"], з["итог_виден_глазу"], почта.get("галочка_видна")))
                    else:
                        шаг("%s: D5 — копирование кладёт адрес в буфер, на месте значка галочка" % место,
                            буфер == "pr@energydess.ru" and почта.get("галочка_видна") and not почта.get("копия_видна")
                            and з["итог"].startswith("Скопировано") and not з["итог_виден_глазу"],
                            "в буфере «%s», галочка %s, значок копирования %s, строка для чтения «%s» на виду %s" % (
                                буфер, почта.get("галочка_видна"), почта.get("копия_видна"), з["итог"], з["итог_виден_глазу"]))
                        с.wait_for_timeout(1800)
                        з = с.evaluate(ЗАМЕР_СВЯЗИ, место)
                        почта = з["строки"][0] if з["строки"] else {}
                        шаг("%s: D5 — подтверждение ненадолго: через 2 с снова значок копирования" % место,
                            почта.get("копия_видна") and not почта.get("галочка_видна"),
                            "значок копирования %s, галочка %s" % (почта.get("копия_видна"), почта.get("галочка_видна")))
                    с.keyboard.press("Escape")
                    с.wait_for_timeout(200)
                    з = с.evaluate(ЗАМЕР_СВЯЗИ, место)
                    шаг("%s: Escape закрывает" % место, not з["открыт"] and not з["карточка_видна"],
                        "открыт %s" % з["открыт"])
                к.close()
            if not контроль_буфера:
                # D4 обратная половина: без «уменьшить движение» раскрытие анимировано
                к = _контекст(бр, 1920, 1080, False)
                с = к.new_page()
                с.goto(БАЗА + "/", wait_until="networkidle", timeout=60000)
                с.wait_for_timeout(300)
                с.evaluate("""() => { const п = document.querySelector('.pf-contact-hero .pf-contact-pop');
                    window.__прозрачность = []; const t0 = performance.now();
                    const тик = () => { window.__прозрачность.push([performance.now() - t0, +getComputedStyle(п).opacity]);
                      if (performance.now() - t0 < 600) requestAnimationFrame(тик); };
                    document.querySelector('.pf-contact-hero').addEventListener('toggle', () => requestAnimationFrame(тик), {once: true}); }""")
                с.locator(".pf-contact-hero summary").click()
                с.wait_for_timeout(800)
                ряд = с.evaluate("() => window.__прозрачность")
                имя = с.evaluate("() => getComputedStyle(document.querySelector('.pf-contact-hero .pf-contact-pop')).animationName")
                ступеней = len({round(о, 2) for _, о in ряд})
                шаг("D4: без «уменьшить движение» карточка проявляется плавно (1920)",
                    имя == "pf-pop" and ряд and ряд[0][1] < 1 and ряд[-1][1] == 1 and ступеней >= 4,
                    "animation-name %s, кадров %d, первая прозрачность %.2f, последняя %.2f, ступеней %d" % (
                        имя, len(ряд), ряд[0][1] if ряд else -1, ряд[-1][1] if ряд else -1, ступеней),
                    собрано=len(ряд))
                к.close()
        finally:
            бр.close()


# ══ F. ПРОЕКТЫ И ПОДВАЛ ═══════════════════════════════════════════════

ЗАМЕР_ПРОЕКТОВ = r"""() => {
  const карточки = [...document.querySelectorAll('.pf-proj')];
  if (!карточки.length) return null;
  const пр = e => { const b = e.getBoundingClientRect();
    return {x: b.left, y: b.top, w: b.width, h: b.height, r: b.right, b: b.bottom}; };
  return {vh: innerHeight, vw: document.documentElement.clientWidth, scrollY,
    карточки: карточки.map(к => {
      const коробка = к.firstElementChild;
      const места = {};
      for (const б of ['a', 'b', 'c']) {
        const м = к.querySelector('.pf-proj-' + б + ' .media-slot');
        места[б] = м ? Object.assign(пр(м), {заполнено: м.dataset.filled}) : null;
      }
      const стиль = getComputedStyle(к);
      return {n: (к.querySelector('.pf-proj-n') || {}).textContent,
              род: (к.querySelector('.pf-proj-kind') || {}).textContent,
              имя: (к.querySelector('.pf-proj-title') || {}).textContent,
              // ЗДЕСЬ СТОЯЛО «органов в карточке нет вовсе» (заход 342, E1) —
              // отменено владельцем (письмо 4 задачи 343): у 01 и 02 кнопка
              // «Портфолио». Считаются все органы и отдельно адреса ссылок.
              органов: к.querySelectorAll('a, button, .pf-proj-soon').length,
              ссылки: [...к.querySelectorAll('a')].map(а => а.getAttribute('href')),
              // КАРТОЧКА 03 — масштаб работы без скриншотов (письмо 4 задачи 343)
              масштаб: !!к.querySelector('.pf-scale'),
              медиа: к.querySelectorAll('.media-slot').length,
              числа: Object.fromEntries([...к.querySelectorAll('[data-scale]')].map(б => [б.dataset.scale, б.textContent.trim()])),
              прилипание: стиль.position, верх_прилипания: parseFloat(стиль.top),
              коробка: пр(к), карточка: пр(коробка),
              масштаб: коробка.getBoundingClientRect().width / коробка.offsetWidth,
              места};
    }),
    // Прямые органы ряда: с захода 339 «Связаться» — summary блока почты,
    // и `mailto:` лежит ВНУТРИ него; прежний отбор всех `a` находил скрытую
    // ссылку закрытого блока и объявлял её кнопкой.
    кнопки: [...document.querySelectorAll('.pf-final-btns > a, .pf-final-btns > details > summary')].map(а => Object.assign(пр(а),
            {href: а.tagName === 'SUMMARY' ? (а.parentElement.querySelector('a[href^="mailto:"]') || {getAttribute: () => ''}).getAttribute('href') : а.getAttribute('href'),
             тег: а.tagName, текст: а.textContent.trim()}))};
}"""


# Адрес «Портфолио» у каждой карточки — решение владельца (письмо 4 задачи 343)
ССЫЛКИ_ПРОЕКТОВ = {"01": "https://disk.yandex.ru/d/PFdacTDoN_iwPA",
                   "02": "https://disk.yandex.ru/d/jqvXMaCUNAbvng"}
# ПОДЛОГ «СКРИНШОТ ВЕРНУЛСЯ В 03»: в карточку 03 вставлено место медиа —
# копия первого места карточки 01, то есть ровно прежний вывод картинки.
ПОДЛОГ_МЕДИА_03 = r"""() => { const к = document.querySelectorAll('.pf-proj')[2], м = document.querySelector('.pf-proj-a');
  if (!к || !м) return null; к.firstElementChild.appendChild(м.cloneNode(true));
  return к.querySelectorAll('.media-slot').length; }"""
ПОДЛОГ_ССЫЛОК = r"""() => { const а = [...document.querySelectorAll('.pf-proj-go')];
  if (а.length < 2) return null; const h = а[0].getAttribute('href');
  а[0].setAttribute('href', а[1].getAttribute('href')); а[1].setAttribute('href', h);
  return а.map(х => х.getAttribute('href')); }"""


def _числа_выкладки():
    """Числа карточки 03, которые читает сервер (`landing_stats.json`)."""
    import json
    путь = os.path.join(os.path.dirname(os.path.abspath(__file__)), "landing_stats.json")
    if not os.path.exists(путь):
        return None
    with open(путь, encoding="utf-8") as ф:
        return json.load(ф)


def проекты(контроль=False, контроль_ссылок=False, контроль_медиа=False):
    from PIL import Image
    from playwright.sync_api import sync_playwright
    print("F. ПРОЕКТЫ И ПОДВАЛ — гостем, головной браузер, стенд %s" % БАЗА)
    каталог = tempfile.mkdtemp(prefix="pf_")
    файл = os.path.join(каталог, "proj.png")
    Image.new("RGB", (1600, 1200), (160, 110, 70)).save(файл)

    with sync_playwright() as p:
        бр = p.chromium.launch(headless=False)
        админ = бр.new_context()
        ад = админ.new_page()
        _войти(ад, *АДМИН)
        положили = False
        try:
            пустые = {}
            for ш, в, сенсор in ШИРИНЫ:
                print("\n  ── %d×%d%s" % (ш, в, " (сенсор)" if сенсор else ""))
                к = _контекст(бр, ш, в, сенсор)
                с = к.new_page()
                с.goto(БАЗА + "/", wait_until="networkidle", timeout=60000)
                if контроль:
                    # ПОДЛОГ ЗВЕНА «УМЕНЬШЕНИЕ»: масштаб карточки снят.
                    с.add_style_tag(content=".pf-proj-card{transform:none!important}")
                if контроль_ссылок:
                    print("  доказательство подлога ссылок: адреса после обмена %s" % с.evaluate(ПОДЛОГ_ССЫЛОК))
                if контроль_медиа:
                    print("  доказательство подлога медиа 03: мест медиа в карточке 03 %s" % с.evaluate(ПОДЛОГ_МЕДИА_03))
                с.wait_for_timeout(500)
                з = с.evaluate(ЗАМЕР_ПРОЕКТОВ)
                if з is None:
                    шаг("секция проектов есть", False, "нет .pf-proj")
                    к.close()
                    continue
                # ЗДЕСЬ СТОЯЛО «три картинки» у всех трёх — у карточки 03 скриншоты
                # сняты владельцем (письмо 4 задачи 343), шаг 03 — отдельный ниже.
                полных = [кр for кр in з["карточки"]
                          if кр["n"] and кр["род"] and кр["имя"] and all(з_ for з_ in кр["места"].values())]
                шаг("карточки 01 и 02: номер, род работы, название, три картинки",
                    len(з["карточки"]) == 3 and [кр["n"] for кр in полных] == ["01", "02"],
                    ", ".join("%s %s (мест %d)" % (кр["n"], кр["имя"], кр["медиа"]) for кр in з["карточки"]),
                    собрано=len(з["карточки"]))
                # Подлог: место медиа вставлено в карточку 03 — шаг падает.
                тр = з["карточки"][2] if len(з["карточки"]) == 3 else None
                выкладка = _числа_выкладки()
                ждём_числа = {к_: str(выкладка[к_]) for к_ in ("tools", "closed", "commits", "checks")} if выкладка else None
                шаг("карточка 03: мест медиа 0, «масштаб работы», числа из выкладки, «Открыть» → #tools",
                    тр is not None and тр["масштаб"] and тр["медиа"] == 0 and тр["ссылки"] == ["#tools"]
                    and ждём_числа is not None and тр["числа"] == ждём_числа,
                    "мест медиа %s, масштаб %s, ссылки %s, числа %s при выкладке %s" % (
                        тр and тр["медиа"], тр and тр["масштаб"], тр and тр["ссылки"], тр and тр["числа"], ждём_числа),
                    собрано=len(з["карточки"]))
                # ЗДЕСЬ СТОЯЛ ШАГ «кнопок 0 (E1)» — решение отменено владельцем
                # (письмо 4 задачи 343). Подлог: адреса 01 и 02 обменяны — шаг падает.
                верные = [кр["n"] for кр in з["карточки"]
                          if кр["n"] in ССЫЛКИ_ПРОЕКТОВ and кр["ссылки"] == [ССЫЛКИ_ПРОЕКТОВ[кр["n"]]]]
                шаг("у 01 и 02 ровно по одной ссылке «Портфолио» на свой адрес",
                    len(верные) == len(ССЫЛКИ_ПРОЕКТОВ),
                    "; ".join("%s → %s" % (кр["n"], кр["ссылки"]) for кр in з["карточки"]),
                    собрано=len(з["карточки"]))
                края = [(abs(кр["места"]["c"]["y"] - кр["места"]["a"]["y"]), abs(кр["места"]["c"]["b"] - кр["места"]["b"]["b"]))
                        for кр in з["карточки"] if all(кр["места"].values())]
                с_картинками = [кр for кр in з["карточки"] if all(кр["места"].values())]
                шаг("E2: высокая картинка вровень с левой колонкой — верх и низ Δ ≤ 0.5 px",
                    all(в_ <= 0.5 and н_ <= 0.5 for в_, н_ in края),
                    "Δ верх/низ по карточкам: %s" % ", ".join("%.1f/%.1f" % к_ for к_ in края), собрано=len(края))
                сетка = [кр["имя"] for кр in с_картинками
                         if кр["места"]["c"]["x"] >= кр["места"]["a"]["r"] and кр["места"]["c"]["x"] >= кр["места"]["b"]["r"]
                         and кр["места"]["b"]["y"] >= кр["места"]["a"]["b"]
                         and кр["места"]["c"]["r"] <= кр["карточка"]["r"] + 0.5 and кр["места"]["b"]["b"] <= кр["карточка"]["b"] + 0.5]
                шаг("в карточке с картинками две слева столбцом, высокая справа", len(сетка) == len(с_картинками),
                    "по сетке %d из %d" % (len(сетка), len(с_картинками)), собрано=len(с_картинками))
                # Карточка 03 стала «масштабом работы» (письмо 4 задачи 343): на узком
                # её содержимое идёт столбиком и длиннее окна. Она ПОСЛЕДНЯЯ — на неё
                # никто не наезжает, и прочитать её можно целиком; на широком
                # проверяются все три, как прежде.
                мерим = з["карточки"] if ш > 600 else з["карточки"][:-1]
                влезают = [кр["имя"] for кр in мерим if кр["коробка"]["h"] <= в - кр["верх_прилипания"]]
                шаг("карточка влезает в окно под шапкой — прилипшую видно целиком",
                    len(влезают) == len(мерим),
                    "высота карточек %s при месте %s" % (
                        [round(кр["коробка"]["h"]) for кр in з["карточки"]],
                        [round(в - кр["верх_прилипания"]) for кр in з["карточки"]]), собрано=len(мерим))
                # стопка: вторая наехала на первую на 40% высоты первой
                с.evaluate("""() => { const а = [...document.querySelectorAll('.pf-proj')];
                  const y = а[1].getBoundingClientRect().top + scrollY - (а[0].getBoundingClientRect().height * 0.6
                            + parseFloat(getComputedStyle(а[0]).top));
                  window.scrollTo({top: y, behavior: 'instant'}); }""")
                с.wait_for_timeout(500)
                ст = с.evaluate(ЗАМЕР_ПРОЕКТОВ)
                п0, п1 = ст["карточки"][0], ст["карточки"][1]
                наезд = п0["коробка"]["b"] - п1["коробка"]["y"]
                шаг("стопка: первая прилипла, вторая наехала, первая уменьшилась",
                    п0["прилипание"] == "sticky" and abs(п0["коробка"]["y"] - п0["верх_прилипания"]) <= 1
                    and наезд > 1 and п0["масштаб"] < 0.995 and п1["масштаб"] > 0.999,
                    "верх первой %.0f при прилипании %.0f, наезд %.0f px, масштаб первой %.3f, второй %.3f" % (
                        п0["коробка"]["y"], п0["верх_прилипания"], наезд, п0["масштаб"], п1["масштаб"]))
                кн = з["кнопки"]
                ряд = len(кн) == 2 and (abs(кн[0]["y"] - кн[1]["y"]) < 1 if ш > 600 else кн[1]["y"] >= кн[0]["b"])
                шаг("подвал: «Связаться» и «Зарегистрироваться» рядом (на узком — столбцом)",
                    len(кн) == 2 and кн[0]["тег"] == "SUMMARY" and кн[0]["текст"] == "Связаться"
                    and кн[0]["href"].startswith("mailto:") and кн[1]["href"] == "/register" and ряд,
                    " | ".join("%s → %s" % (к_["текст"], к_["href"]) for к_ in кн), собрано=len(кн))
                пустые[(ш, в)] = з
                к.close()

                к = _контекст(бр, ш, в, сенсор, движение="reduce")
                с = к.new_page()
                с.goto(БАЗА + "/", wait_until="networkidle", timeout=60000)
                с.evaluate("""() => window.scrollTo({top: document.querySelectorAll('.pf-proj')[1].offsetTop - innerHeight / 3, behavior: 'instant'})""")
                с.wait_for_timeout(500)
                т = с.evaluate(ЗАМЕР_ПРОЕКТОВ)
                наездов = sum(1 for а, б in zip(т["карточки"], т["карточки"][1:]) if а["коробка"]["b"] > б["коробка"]["y"] + 0.5)
                шаг("«уменьшить движение»: карточки подряд, без прилипания и масштаба",
                    all(кр["прилипание"] != "sticky" and abs(кр["масштаб"] - 1) < 0.001 for кр in т["карточки"]) and наездов == 0,
                    "прилипают %d, масштаб %s, наездов %d" % (
                        sum(1 for кр in т["карточки"] if кр["прилипание"] == "sticky"),
                        ["%.3f" % кр["масштаб"] for кр in т["карточки"]], наездов), собрано=len(т["карточки"]))
                к.close()

            print("\n  ── подлог: картинка «Проект 2 · справа» положена, затем убрана")
            было = пустые.get((1920, 1080), {}).get("карточки", [{}, {}])[1].get("места", {}).get("c", {}).get("заполнено")
            if было != "no":
                шаг("место проекта 2 справа пусто — подлог можно провести", False,
                    "место заполнено (%s): чужой файл не трогаем" % было)
                return
            код = _место(ад, "project-2-c", "положить", файл)
            положили = код == 200
            шаг("картинка положена боевой загрузкой", положили, "HTTP %s" % код)

            def замер(ш, в, сенсор, css=None):
                к = _контекст(бр, ш, в, сенсор, движение="reduce")
                с = к.new_page()
                с.goto(БАЗА + "/", wait_until="networkidle", timeout=60000)
                if css:
                    с.add_style_tag(content=css)
                с.wait_for_timeout(400)
                з = с.evaluate(ЗАМЕР_ПРОЕКТОВ)
                к.close()
                return з
            с_файлом = {(ш, в): замер(ш, в, сн) for ш, в, сн in ШИРИНЫ}
            код = _место(ад, "project-2-c", "убрать")
            if код == 200:
                положили = False
            шаг("картинка убрана из хранилища", код == 200, "HTTP %s" % код)
            for ш, в, сенсор in ШИРИНЫ:
                пусто = замер(ш, в, сенсор,
                              ".pf-proj-c .media-slot{aspect-ratio:auto!important}" if контроль else None)
                полно = с_файлом[(ш, в)]
                а, б = полно["карточки"][1], пусто["карточки"][1]
                сдвиг = max([abs(а["коробка"][о] - б["коробка"][о]) for о in ("x", "y", "w", "h")] +
                            [abs(а["места"][м][о] - б["места"][м][о]) for м in "abc" for о in ("x", "y", "w", "h")])
                шаг("%d×%d: картинка убрана — заглушка встала, карточка не поехала" % (ш, в),
                    б["места"]["c"]["заполнено"] == "no" and сдвиг <= 0.5,
                    "доказательство: заполнено %s→%s; сдвиг %.2f px" % (
                        а["места"]["c"]["заполнено"], б["места"]["c"]["заполнено"], сдвиг))
        finally:
            if положили:
                print("  уборка: картинка снята — HTTP %s" % _место(ад, "project-2-c", "убрать"))
            бр.close()


# ══ B. ФОН СТРАНИЦЫ (заход 342) ═══════════════════════════════════════
#
# ЧТО СПРАШИВАЕТСЯ — ВИДИМОЕ:
#   · B1 верхний ролик не едет: его коробка стоит у верха окна при трёх
#     положениях прокрутки внутри верхней части;
#   · B4 границы участков без скачка: контент скрыт, по строкам кадра
#     средняя яркость у каждого края слоя фона и подсветки — скачок
#     в уровнях из 255 (жёсткий край даёт десятки);
#   · B5 верхний получает адрес сразу, нижний — не дальше 1.6 и уже
#     на 1.4 экрана до слоя;
#   · B6 «чёрные» миллисекунды: кадр первого экрана виден, а кадра фона
#     нет — на мобильной сети при загрузке и при рывке вниз;
#   · B7 скорость 0.5 у играющего ролика; B8 «уменьшить движение»:
#     ролики без адреса, кадр виден, подсветка стоит;
#   · B9 контраст текста к фону ПОД ним: текст скрыт, p95 яркости фона
#     в прямоугольниках строк, четыре кадра ролика, три положения текста
#     в окне; худший случай против 4.5 (3.0 у крупного).
#
# ПОДЛОГИ ЛОМАЮТ СВОЁ ЗВЕНО:
#   --контроль-сети   кадр верхнего фона — адресом вместо встроенного
#                     (переписанная разметка): чёрные мс обязаны стать > 0;
#   --контроль-рывка  кадр нижнего фона снят: при рывке чёрные мс > 0;
#   --контроль-краёв  маски слоёв сняты: скачок у края обязан вырасти.

МОБИЛЬНАЯ_СЕТЬ = {"offline": False, "latency": 150, "downloadThroughput": 200000,
                  "uploadThroughput": 93750}

ФОН_ТЕКСТЫ = [".pf-hero-name", ".pf-hero-line", "#pf-about-h",
              ".pf-about-text", "#pf-final-h", ".pf-final-sub"]

ЗАМЕР_КРАЁВ = r"""() => {
  const out = [];
  for (const э of document.querySelectorAll('.pf-bg, .pf-glow')) {
    const b = э.getBoundingClientRect();
    out.push({кто: э.className, верх: b.top + scrollY, низ: b.bottom + scrollY,
              маска: getComputedStyle(э).maskImage || getComputedStyle(э).webkitMaskImage});
  }
  return out;
}"""

ЧЁРНЫЕ_МС = r"""(сел) => new Promise(готово => {
  const t0 = performance.now(); let первый = null, конец = null;
  const тик = () => {
    const слой = document.querySelector(сел);
    const п = слой && слой.querySelector('.pf-bg-poster'), в = слой && слой.querySelector('.pf-bg-video');
    const есть = (п && п.complete && п.naturalWidth > 0) || (в && в.classList.contains('pf-on'));
    const b = слой && слой.getBoundingClientRect();
    const виден = b && b.bottom > 0 && b.top < innerHeight;
    if (виден && первый === null) первый = performance.now();
    if (виден && есть) { конец = performance.now(); готово({чёрные: Math.round(конец - первый), с_начала: Math.round(конец - t0)}); return; }
    if (performance.now() - t0 > 8000) { готово({чёрные: первый === null ? null : Math.round(performance.now() - первый), с_начала: null}); return; }
    requestAnimationFrame(тик);
  };
  requestAnimationFrame(тик);
})"""

ПОДЛОГ_КАДР_АДРЕСОМ = r"""(() => {
  new MutationObserver(() => {
    const п = document.querySelector('.pf-bg-top .pf-bg-poster');
    if (п && п.getAttribute('src').startsWith('data:')) п.setAttribute('src', '__АДРЕС__?v=' + Date.now());
  }).observe(document, {childList: true, subtree: true});
})();"""

ПЕРВЫЙ_КАДР_ИНИТ = r"""(() => {
  window.__фон = {герой: null, кадр: null};
  const тик = () => {
    const г = document.querySelector('.pf-hero');
    const п = document.querySelector('.pf-bg-top .pf-bg-poster');
    const t = performance.now();
    if (г && window.__фон.герой === null && getComputedStyle(г).display === 'grid' && г.getBoundingClientRect().height > 0) window.__фон.герой = t;
    if (п && window.__фон.кадр === null && п.complete && п.naturalWidth > 0) window.__фон.кадр = t;
    if (window.__фон.герой === null || window.__фон.кадр === null) requestAnimationFrame(тик);
  };
  requestAnimationFrame(тик);
})();"""


def _яркость(пиксели):
    """Относительная яркость sRGB по WCAG для массива (N, 3) 0..255."""
    import numpy as np
    к = пиксели.astype(np.float64) / 255.0
    к = np.where(к <= 0.04045, к / 12.92, ((к + 0.055) / 1.055) ** 2.4)
    return 0.2126 * к[:, 0] + 0.7152 * к[:, 1] + 0.0722 * к[:, 2]


def _цвет_яркость(css):
    import re as _re
    ч = [float(x) for x in _re.findall(r"[\d.]+", css)[:3]]
    import numpy as np
    return float(_яркость(np.array([ч]))[0])


def _фон_поведение(бр, ш, в, сенсор, контроль_сети, контроль_рывка, контроль_краёв):
    """B1, B4, B5, B6, B7 на одной ширине. False — слоёв фона нет."""
    import io
    import numpy as np
    from PIL import Image
    к = _контекст(бр, ш, в, сенсор)
    с = к.new_page()
    с.goto(БАЗА + "/", wait_until="networkidle", timeout=60000)
    с.wait_for_timeout(800)
    слоёв = с.locator(".pf-bg").count()
    if not слоёв:
        шаг("слои фона есть", False, собрано=слоёв)
        к.close()
        return False
    if контроль_краёв:
        с.add_style_tag(content=".pf-bg,.pf-glow{-webkit-mask-image:none!important;mask-image:none!important}")
    адреса = с.evaluate("() => [...document.querySelectorAll('.pf-bg-video')].map(в => !!в.getAttribute('src'))")
    шаг("B5: при загрузке у верхнего адрес есть, у нижнего нет",
        адреса == [True, False], "адреса %s" % адреса, собрано=len(адреса))

    # B1 — липкость верхнего
    верх_зоны = с.evaluate("() => { const b = document.querySelector('.pf-bg-top').getBoundingClientRect(); return {низ: b.bottom + scrollY}; }")
    сдвиги = []
    for y in (400, 900, int(max(1000, верх_зоны["низ"] - в * 1.6))):
        с.evaluate("y => window.scrollTo({top: y, behavior: 'instant'})", y)
        с.wait_for_timeout(250)
        сдвиги.append(round(с.evaluate("() => document.querySelector('.pf-bg-top .pf-bg-stick').getBoundingClientRect().top"), 1))
    шаг("B1: верхний фон не едет — верх ролика у верха окна при трёх прокрутках",
        all(abs(с_) < 0.6 for с_ in сдвиги), "верх ролика %s px" % сдвиги, собрано=len(сдвиги))

    # B5 — подгрузка нижнего за полтора экрана
    верх_низа = с.evaluate("() => document.querySelector('.pf-bg-bottom').getBoundingClientRect().top + scrollY")
    с.evaluate("y => window.scrollTo({top: y, behavior: 'instant'})", int(верх_низа - в - 1.6 * в))
    с.wait_for_timeout(400)
    на16 = с.evaluate("() => !!document.querySelector('.pf-bg-bottom .pf-bg-video').getAttribute('src')")
    с.evaluate("y => window.scrollTo({top: y, behavior: 'instant'})", int(верх_низа - в - 1.4 * в))
    с.wait_for_timeout(400)
    на14 = с.evaluate("() => !!document.querySelector('.pf-bg-bottom .pf-bg-video').getAttribute('src')")
    шаг("B5: нижний не грузится за 1.6 экрана и грузится за 1.4", (not на16) and на14,
        "адрес на 1.6 %s, на 1.4 %s" % (на16, на14))

    # B7 — скорость
    с.evaluate("y => window.scrollTo({top: y, behavior: 'instant'})", int(верх_низа))
    с.wait_for_timeout(2500)
    скорости = с.evaluate("() => [...document.querySelectorAll('.pf-bg-video')].map(в => [в.playbackRate, в.classList.contains('pf-on')])")
    шаг("B7: у нижнего (играет) скорость 0.5, у верхнего выставлена 0.5",
        скорости[1] == [0.5, True] and скорости[0][0] == 0.5, "скорость и игра %s" % скорости)

    # B4 — края участков. Контент скрыт, подсветка стоит, а ролик и кадр
    # заменены РОВНОЙ светлой заливкой: меряется сам переход, а не
    # содержимое кадра (у нижнего ролика есть резкий горизонт, и первая
    # версия мерки попала на него краем подсветки — ложный скачок 1.88).
    # Жёсткий край при такой заливке даёт скачок в сотню уровней.
    с.add_style_tag(content=".site-header,.pf-zone>:not(.pf-bg):not(.pf-glow),footer{visibility:hidden!important}"
                            ".pf-glow i{animation-play-state:paused!important}"
                            ".pf-bg-poster,.pf-bg-video{visibility:hidden!important}.pf-bg-stick{background:var(--text-strong)}")
    края = с.evaluate(ЗАМЕР_КРАЁВ)
    высота = с.evaluate("document.documentElement.scrollHeight")
    скачки = []
    for к_ in края:
        for имя_края, y_док in (("верх", к_["верх"]), ("низ", к_["низ"])):
            if y_док <= 70 or y_док >= высота - 2:
                continue   # край у верха страницы или у её конца — не граница участков
            прокрутка = max(0, int(y_док - в / 2))
            с.evaluate("y => window.scrollTo({top: y, behavior: 'instant'})", прокрутка)
            с.wait_for_timeout(300)
            факт = с.evaluate("() => scrollY")
            y_окна = int(round(y_док - факт))
            if not (6 <= y_окна <= в - 6):
                continue
            кадр = np.array(Image.open(io.BytesIO(с.screenshot())).convert("RGB")).astype(np.float64)
            строки = кадр.mean(axis=(1, 2))
            скачок = abs(строки[y_окна - 4:y_окна - 1].mean() - строки[y_окна + 1:y_окна + 4].mean())
            скачки.append((к_["кто"].split()[-1] + "·" + имя_края, round(float(скачок), 2)))
    худший = max((с_[1] for с_ in скачки), default=None)
    шаг("B4: у краёв фона и подсветки скачок яркости по строкам ≤ 12 уровней (жёсткий край — около сотни)",
        худший is not None and худший <= 12,
        "%s; маски: %s" % (скачки, [bool(к_["маска"] and к_["маска"] != "none") for к_ in края]),
        собрано=len(скачки))
    к.close()

    # B6 — рывок вниз: сколько мс блок стоит без фона
    к = _контекст(бр, ш, в, сенсор)
    с = к.new_page()
    с.goto(БАЗА + "/", wait_until="networkidle", timeout=60000)
    с.wait_for_timeout(1000)
    if контроль_рывка:
        print("  доказательство подлога: кадров нижнего %d -> " % с.locator(".pf-bg-bottom .pf-bg-poster").count(), end="")
        с.evaluate("() => document.querySelectorAll('.pf-bg-bottom .pf-bg-poster').forEach(э => э.remove())")
        print(с.locator(".pf-bg-bottom .pf-bg-poster").count())
    # замер стартует БЕЗ ожидания: иначе прокрутка случилась бы после его конца
    с.evaluate("(сел) => { window.__рывок = (" + ЧЁРНЫЕ_МС + ")(сел); }", ".pf-bg-bottom")
    # к финальному блоку, а не в конец страницы: на 390 подвал выше окна,
    # и в конце страницы финальный блок уже за верхним краем
    с.evaluate("() => window.scrollTo({top: document.querySelector('.pf-final').getBoundingClientRect().top + scrollY - innerHeight / 3, behavior: 'instant'})")
    рывок = с.evaluate("() => window.__рывок")
    шаг("B6: рывок вниз — нижний блок без фона 0 мс", рывок["чёрные"] == 0,
        "без фона %s мс" % рывок["чёрные"])
    к.close()

    # B6 — мобильная сеть: первый кадр верхнего с первой отрисовкой.
    # ДВА СЛУЧАЯ. Холодный — кеша нет вовсе. Тёплый — стили и скрипты в кеше,
    # как у вернувшегося гостя, а кадр новый (ролик заменили): на холодной
    # загрузке кадр по АДРЕСУ успевает раньше стилей, и мерка не отличала бы
    # встроенный кадр от адреса. Подлог — в тёплом случае: наблюдатель разметки
    # подменяет встроенный кадр некешированным адресом ДО первой отрисовки
    # (перехват маршрута выключил бы кеш браузера и вернул холодный случай).
    for случай in ("холодный", "тёплый"):
        к = _контекст(бр, ш, в, сенсор)
        с = к.new_page()
        cdp = к.new_cdp_session(с)
        cdp.send("Network.enable")
        if случай == "холодный":
            cdp.send("Network.setCacheDisabled", {"cacheDisabled": True})
            if контроль_сети:
                к.close()
                continue
        else:
            с.goto(БАЗА + "/", wait_until="networkidle", timeout=60000)
            видео = с.evaluate("() => (document.querySelector('.pf-bg-top .pf-bg-video') || {getAttribute: () => ''}).getAttribute('data-src')")
            if контроль_сети and видео:
                к.add_init_script(ПОДЛОГ_КАДР_АДРЕСОМ.replace("__АДРЕС__", видео.replace(".mp4", ".poster.webp")))
        к.add_init_script(ПЕРВЫЙ_КАДР_ИНИТ)
        cdp.send("Network.emulateNetworkConditions", МОБИЛЬНАЯ_СЕТЬ)
        с.goto(БАЗА + "/", wait_until="load", timeout=120000)
        с.wait_for_timeout(500)
        м = с.evaluate("() => window.__фон")
        if контроль_сети:
            print("  доказательство подлога: кадр верхнего с адреса %s" % с.evaluate(
                "() => (document.querySelector('.pf-bg-top .pf-bg-poster') || {getAttribute: () => ''}).getAttribute('src').slice(0, 40)"))
        чёрные = None if м["герой"] is None or м["кадр"] is None else max(0, round(м["кадр"] - м["герой"]))
        шаг("B6: мобильная сеть, %s кеш — первый экран без кадра фона 0 мс" % случай, чёрные == 0,
            "первый экран на %s мс, кадр фона на %s мс, без кадра %s мс" % (
                None if м["герой"] is None else round(м["герой"]),
                None if м["кадр"] is None else round(м["кадр"]), чёрные))
        к.close()
    return True


def _фон_уменьшить(бр, ш, в, сенсор):
    к = _контекст(бр, ш, в, сенсор, движение="reduce")
    с = к.new_page()
    с.goto(БАЗА + "/", wait_until="networkidle", timeout=60000)
    с.evaluate("() => window.scrollTo({top: document.documentElement.scrollHeight, behavior: 'instant'})")
    с.wait_for_timeout(1500)
    т = с.evaluate("""() => ({адреса: [...document.querySelectorAll('.pf-bg-video')].map(в => !!в.getAttribute('src')),
        кадры: [...document.querySelectorAll('.pf-bg-poster')].map(п => п.complete && п.naturalWidth > 0),
        подсветка: [...document.querySelectorAll('.pf-glow i')].map(и => getComputedStyle(и).animationName)})""")
    шаг("B8: «уменьшить движение» — роликам адрес не дан, кадры видны, подсветка стоит",
        т["адреса"] == [False, False] and all(т["кадры"]) and all(а == "none" for а in т["подсветка"]),
        str(т), собрано=len(т["кадры"]))
    к.close()


def _фон_контраст(бр, ш, в, сенсор, притемнение=None):
    """B9 на одной ширине. `притемнение` — {'top': 70, 'bottom': 45} поверх
    стилей страницы: перебор долей без правки файла (подбор числа замером)."""
    import io
    import re as _re
    import numpy as np
    from PIL import Image
    к = _контекст(бр, ш, в, сенсор)
    с = к.new_page()
    с.goto(БАЗА + "/", wait_until="networkidle", timeout=60000)
    if притемнение:
        с.add_style_tag(content="".join(".pf-bg-%s{--pf-scrim:%s%%!important}" % (к_, д_) for к_, д_ in притемнение.items()))
        print("  притемнение подложено: %s" % притемнение)
    с.add_style_tag(content=".pf-ch{color:var(--text-strong)!important}.pf-bg-video{transition:none!important}"
                            ".pf-glow i{animation-play-state:paused!important}")
    с.evaluate("""() => document.querySelectorAll('.pf-bg-video').forEach(в => { в.preload = 'auto';
        if (!в.getAttribute('src')) в.setAttribute('src', в.getAttribute('data-src')); })""")
    с.wait_for_timeout(2500)
    фон_hex = с.evaluate("() => getComputedStyle(document.documentElement).getPropertyValue('--surface-0').trim()")
    фон_ярк = _цвет_яркость("rgb(%d,%d,%d)" % tuple(int(фон_hex[i:i + 2], 16) for i in (1, 3, 5)))
    худшие = []
    for сел in ФОН_ТЕКСТЫ:
        сведения = с.evaluate("""(сел) => { const э = document.querySelector(сел); if (!э) return null;
            const ст = getComputedStyle(э); const град = э.classList.contains('pf-grad');
            const цвет = град ? getComputedStyle(document.documentElement).getPropertyValue('--text-faint') : ст.color;
            const кегль = parseFloat(ст.fontSize), вес = parseInt(ст.fontWeight);
            const корень = getComputedStyle(document.documentElement);
            return {цвет: цвет.trim(), град: град, светлый: корень.getPropertyValue('--text-strong').trim(),
                    крупный: кегль >= 24 || (кегль >= 18.66 && вес >= 700), кегль};
        }""", сел)
        if not сведения:
            continue
        цвет_hex = сведения["цвет"]
        if цвет_hex.startswith("#"):
            цвет_css = "rgb(%d,%d,%d)" % tuple(int(цвет_hex[i:i + 2], 16) for i in (1, 3, 5))
        else:
            цвет_css = цвет_hex
        ц_тёмн = [float(x) for x in _re.findall(r"[\d.]+", цвет_css)[:3]]
        св_hex = сведения["светлый"]
        ц_свет = [int(св_hex[i:i + 2], 16) for i in (1, 3, 5)] if св_hex.startswith("#") else ц_тёмн
        порог = 3.0 if сведения["крупный"] else 4.5
        хуже = None
        for доля_окна in (0.25, 0.5, 0.75):
            с.evaluate("""([сел, д]) => { const э = document.querySelector(сел); const b = э.getBoundingClientRect();
                window.scrollTo({top: Math.max(0, b.top + scrollY + b.height / 2 - innerHeight * д), behavior: 'instant'}); }""",
                       [сел, доля_окна])
            for доля_ролика in (0.0, 0.25, 0.5, 0.75):
                с.evaluate("""(д) => Promise.all([...document.querySelectorAll('.pf-bg-video')].map(в => new Promise(r => {
                    в.pause(); в.classList.add('pf-on');
                    const t = (в.duration || 0) * д; if (Math.abs(в.currentTime - t) < 0.01) { r(); return; }
                    в.addEventListener('seeked', () => r(), {once: true}); в.currentTime = t; setTimeout(r, 3000); })))""",
                           доля_ролика)
                прям = с.evaluate("""(сел) => { const э = document.querySelector(сел);
                    const д = document.createRange(); д.selectNodeContents(э);
                    const бокс = э.getBoundingClientRect();
                    return {бокс: [бокс.left, бокс.width],
                      строки: [...д.getClientRects()].filter(к => к.width > 2 && к.height > 2 && к.top >= 64 && к.bottom <= innerHeight)
                      .map(к => [к.left, к.top, к.right, к.bottom])}; }""", сел)
                if not прям["строки"]:
                    continue
                с.add_style_tag(content="%s,%s *{color:transparent!important;-webkit-text-fill-color:transparent!important;"
                                        "background:none!important;text-shadow:none!important}.pf-hero-portrait{visibility:hidden!important}" % (сел, сел))
                с.wait_for_timeout(60)
                кадр = np.array(Image.open(io.BytesIO(с.screenshot())).convert("RGB"))
                с.evaluate("() => document.head.lastElementChild.remove()")
                # ПОЛОСАМИ ВДОЛЬ СТРОКИ: у градиентного заголовка цвет букв
                # меняется от серого края к белому, и фон под каждой полосой
                # сравнивается с цветом букв В ЭТОЙ полосе
                б_л, б_ш = прям["бокс"]
                for l_, t_, r_, b_ in прям["строки"]:
                    полос = max(1, int((r_ - l_) // 24))
                    for i in range(полос):
                        x0 = l_ + (r_ - l_) * i / полос
                        x1 = l_ + (r_ - l_) * (i + 1) / полос
                        кусок = кадр[int(t_):int(b_), max(0, int(x0)):int(x1)].reshape(-1, 3)
                        if not len(кусок):
                            continue
                        доля = min(1.0, max(0.0, ((x0 + x1) / 2 - б_л) / б_ш)) if сведения["град"] else 0.0
                        ц = [ц_тёмн[j] * (1 - доля) + ц_свет[j] * доля for j in range(3)]
                        L_текст = float(_яркость(np.array([ц]))[0])
                        L_фон = float(np.percentile(_яркость(кусок), 95))
                        контраст = (max(L_текст, L_фон) + 0.05) / (min(L_текст, L_фон) + 0.05)
                        if хуже is None or контраст < хуже[0]:
                            хуже = (контраст, доля_окна, доля_ролика)
        if хуже:
            худшие.append((сел, хуже[0], порог, хуже[1], хуже[2]))
    для_печати = ["%s %.2f (порог %.1f; окно %.2f, ролик %.2f)" % (с_, к_, п_, д1, д2) for с_, к_, п_, д1, д2 in худшие]
    шаг("B9: текст на ролике читается — худший контраст не ниже порога в каждом месте",
        худшие and all(к_ >= п_ for _, к_, п_, _, _ in худшие), "; ".join(для_печати), собрано=len(худшие))
    print("  (для сравнения: контраст «серого» --text-faint к фону страницы без ролика %.2f)" % (
        (_цвет_яркость("rgb(122,131,160)") + 0.05) / (фон_ярк + 0.05)))
    к.close()
    return худшие


def фон(контроль_сети=False, контроль_рывка=False, контроль_краёв=False, только_контраст=False, притемнение=None):
    from playwright.sync_api import sync_playwright
    print("B. ФОН СТРАНИЦЫ — гостем, головной браузер, стенд %s%s" % (БАЗА,
          " · ПОДЛОГ: кадр верхнего адресом" if контроль_сети else
          " · ПОДЛОГ: кадр нижнего снят" if контроль_рывка else
          " · ПОДЛОГ: маски слоёв сняты" if контроль_краёв else ""))
    with sync_playwright() as p:
        бр = p.chromium.launch(headless=False)
        try:
            for ш, в, сенсор in ШИРИНЫ:
                print("\n  ── %d×%d%s" % (ш, в, " (сенсор)" if сенсор else ""))
                if not только_контраст:
                    if not _фон_поведение(бр, ш, в, сенсор, контроль_сети, контроль_рывка, контроль_краёв):
                        continue
                    if контроль_сети or контроль_рывка or контроль_краёв:
                        continue
                    _фон_уменьшить(бр, ш, в, сенсор)
                _фон_контраст(бр, ш, в, сенсор, притемнение)
        finally:
            бр.close()



# ══ СВОДКА ЧИСЕЛ (заход 342) ══════════════════════════════════════════
#
# ОДНА МЕРКА НА «ДО» И «ПОСЛЕ»: печатает числа и не судит. Вердикты
# ставят режимы блоков; здесь только то, что меняется правкой, — чтобы
# «до» было снято тем же кодом, что «после», а не пересказано.

ЗАМЕР_СВОДКИ = r"""() => {
  const q = s => document.querySelector(s);
  const пр = e => e ? e.getBoundingClientRect() : null;
  const заголовки = {};
  for (const id of ['pf-about-h', 'pf-tools-h', 'pf-projects-h', 'pf-final-h']) {
    const э = document.getElementById(id);
    if (!э) { заголовки[id] = null; continue; }
    const д = document.createRange(); д.selectNodeContents(э);
    const т = д.getBoundingClientRect(), к = пр(э);
    заголовки[id] = {кегль: parseFloat(getComputedStyle(э).fontSize),
      текст_ш: Math.round(т.width), центр_смещение: Math.round((т.left + т.width / 2) - (к.left + к.width / 2)),
      строк: Math.round(т.height / parseFloat(getComputedStyle(э).lineHeight || 1))};
  }
  const кн = [...document.querySelectorAll('.site-header .pf-header-btn')].map(э => ({т: э.textContent.trim(), ш: Math.round(пр(э).width * 10) / 10}));
  const линия = q('.pf-hero-line');
  const строк = линия ? (() => { const д = document.createRange(); д.selectNodeContents(линия);
    const ys = new Set([...д.getClientRects()].filter(к => к.width).map(к => Math.round(к.top))); return ys.size; })() : null;
  const якоря = [...document.querySelectorAll('.pf-anchors a')];
  const проекты = [...document.querySelectorAll('.pf-proj')].map(к => {
    const а = пр(к.querySelector('.pf-proj-a .media-slot')), б = пр(к.querySelector('.pf-proj-b .media-slot')),
          в = пр(к.querySelector('.pf-proj-c .media-slot'));
    return {кнопок: к.querySelectorAll('.pf-proj-go, .pf-proj-soon, .pf-proj-card a, .pf-proj-card button').length,
      верх: а && в ? Math.round((в.top - а.top) * 10) / 10 : null,
      низ: б && в ? Math.round((в.bottom - б.bottom) * 10) / 10 : null,
      номер_кегль: parseFloat(getComputedStyle(к.querySelector('.pf-proj-n')).fontSize),
      имя_кегль: parseFloat(getComputedStyle(к.querySelector('.pf-proj-title')).fontSize)};
  });
  const поп = q('.pf-contact-hero .pf-contact-pop');
  return {заголовки, кнопки_шапки: кн, строк_в_первом_экране: строк,
    якоря: якоря.length ? {ссылок: якоря.length, кегль: parseFloat(getComputedStyle(якоря[0]).fontSize)} : null,
    проекты, связь_детей: поп ? [...поп.children].filter(э => !э.hidden && getComputedStyle(э).display !== 'none').length : null,
    связь_строк: поп ? поп.querySelectorAll('.pf-contact-row').length : null,
    будущее: !!q('.pf-join-reel'), фон_зон: document.querySelectorAll('[data-pf-bg]').length,
    призыв: (() => { const з = q('.pf-join-h'), а = q('.pf-join-cta'), б = q('.pf-join');
      return з && а ? {заголовок_кегль: parseFloat(getComputedStyle(з).fontSize), вес: +getComputedStyle(з).fontWeight,
        кнопка: Math.round(пр(а).width) + '×' + Math.round(пр(а).height), кнопка_кегль: parseFloat(getComputedStyle(а).fontSize),
        блок_h: Math.round(пр(б).height)} : null; })()};
}"""


def сводка():
    from playwright.sync_api import sync_playwright
    print("СВОДКА — гостем, головной браузер, стенд %s. Числа, без вердиктов." % БАЗА)
    with sync_playwright() as p:
        бр = p.chromium.launch(headless=False)
        try:
            for ш, в, сенсор in ШИРИНЫ:
                к = _контекст(бр, ш, в, сенсор)
                с = к.new_page()
                cdp = к.new_cdp_session(с)
                cdp.send("Network.enable")
                cdp.send("Network.setCacheDisabled", {"cacheDisabled": True})
                байт = {"n": 0, "b": 0, "видео": 0}
                типы = {}
                def ответ(e):
                    типы[e["requestId"]] = (e.get("type"), e["response"]["url"])
                def конец(e):
                    байт["n"] += 1
                    байт["b"] += e.get("encodedDataLength", 0)
                    т = типы.get(e["requestId"], ("", ""))
                    if т[0] == "Media" or т[1].endswith(".mp4"):
                        байт["видео"] += e.get("encodedDataLength", 0)
                cdp.on("Network.responseReceived", ответ)
                cdp.on("Network.loadingFinished", конец)
                с.goto(БАЗА + "/", wait_until="networkidle", timeout=60000)
                с.wait_for_timeout(3000)
                print("\n  ── %d×%d%s" % (ш, в, " (сенсор)" if сенсор else ""))
                print("  вес до прокрутки: %.1f КБ в %d запросах, из них видео %.1f КБ" % (
                    байт["b"] / 1024, байт["n"], байт["видео"] / 1024))
                з = с.evaluate(ЗАМЕР_СВОДКИ)
                for id_, д in з["заголовки"].items():
                    print("  %s: %s" % (id_, д))
                print("  кнопки шапки: %s" % з["кнопки_шапки"])
                print("  строк текста в первом экране: %s; якоря: %s" % (з["строк_в_первом_экране"], з["якоря"]))
                print("  проекты: %s" % з["проекты"])
                с.locator(".pf-contact-hero summary").click()
                с.wait_for_timeout(500)
                з2 = с.evaluate(ЗАМЕР_СВОДКИ)
                print("  блок связи раскрыт: видимых детей %s, строк .pf-contact-row %s" % (
                    з2["связь_детей"], з2["связь_строк"]))
                print("  лента карточки-призыва есть: %s; зон фона: %s" % (з["будущее"], з["фон_зон"]))
                print("  призыв регистрации: %s" % з["призыв"])
                к.close()
        finally:
            бр.close()


# ══ СВОДНЫЙ ПРОГОН ВСЕХ РЕЖИМОВ (заход 343, блок 1) ═══════════════════
#
# Без ключа режима проба гонит ВСЕ зарегистрированные режимы отдельными
# процессами и печатает ОДНУ строку сводки, а под ней — только упавшие.
# Полный вывод всех режимов уходит в файл, путь — последней строкой.
# `--verbose` возвращает прежнюю печать (вывод режимов по ходу).
# `--только имя,имя` — часть реестра; сводка считает выбранные.
#
# N — ДЛИНА РЕЕСТРА (выбранной части), а не число выполненных: режим,
# который не стартовал, не уложился в потолок, упал исключением или
# не дошёл до строки ИТОГ, считается упавшим С ПРИЧИНОЙ. Иначе «22/22»
# при 21 выполненном было бы немым отказом (§6.0.1).
#
# ОЖИДАНИЕ у каждого режима своё: 0 — режим чист; 1 — это подлог, и он
# ПОЙМАН (в ИТОГ есть ПЛОХО). Код 1 без ПЛОХО в ИТОГ (например, трасса)
# подлогом не считается — это падение. ПРОПУСК (код 2) — всегда провал.
РЕЖИМЫ = (
    ("сводка",                  ("--сводка",), 0),
    ("фон",                     ("--фон",), 0),
    ("фон:контраст",            ("--фон", "--контраст"), 0),
    ("фон:контроль-сети",       ("--фон", "--контроль-сети"), 1),
    ("фон:контроль-рывка",      ("--фон", "--контроль-рывка"), 1),
    ("фон:контроль-краёв",      ("--фон", "--контроль-краёв"), 1),
    ("макет",                   ("--макет",), 0),
    ("макет:контроль-якорей",   ("--макет", "--контроль-якорей"), 1),
    ("макет:контроль-отступа",  ("--макет", "--контроль-отступа"), 1),
    ("макет:контроль-имени",    ("--макет", "--контроль-имени"), 1),
    ("макет:контроль-головы",   ("--макет", "--контроль-головы"), 1),
    ("макет:контроль-градиента", ("--макет", "--контроль-градиента"), 1),
    ("макет:контроль-кнопки",   ("--макет", "--контроль-кнопки"), 1),
    ("макет:контроль-зазора",   ("--макет", "--контроль-зазора"), 1),
    ("макет:контроль-края",     ("--макет", "--контроль-края"), 1),
    ("экран",                   ("--экран",), 0),
    ("экран:контроль",          ("--экран", "--контроль"), 1),
    ("экран:контроль-магнита",  ("--экран", "--контроль-магнита"), 1),
    ("лента",                   ("--лента",), 0),
    ("лента:контроль",          ("--лента", "--контроль"), 1),
    ("лента:контроль-плавности", ("--лента", "--контроль-плавности"), 1),
    ("лента:контроль-кадра",    ("--лента", "--контроль-кадра"), 1),
    ("о-себе",                  ("--о-себе",), 0),
    ("о-себе:контроль",         ("--о-себе", "--контроль"), 1),
    ("о-себе:контроль-доли",    ("--о-себе", "--контроль-доли"), 1),
    ("инструменты",             ("--инструменты",), 0),
    ("инструменты:контроль",    ("--инструменты", "--контроль"), 1),
    ("инструменты:контроль-повтора", ("--инструменты", "--контроль-повтора"), 1),
    ("инструменты:контроль-сброса", ("--инструменты", "--контроль-сброса"), 1),
    ("связь",                   ("--связь",), 0),
    ("связь:контроль-буфера",   ("--связь", "--контроль-буфера"), 0),
    ("проекты",                 ("--проекты",), 0),
    ("проекты:контроль",        ("--проекты", "--контроль"), 1),
    ("проекты:контроль-ссылок", ("--проекты", "--контроль-ссылок"), 1),
    ("проекты:контроль-медиа",  ("--проекты", "--контроль-медиа"), 1),
)
ПОТОЛОК_РЕЖИМА = int(os.environ.get("PF_MODE_TIMEOUT", "1500"))
КЛЮЧИ_ПРОГОНА = ("--verbose", "--только")


def _ключи_main():
    """Ключи, которые разбирает main(), — из ТЕКСТА main, а не из реестра:
    ключ, заведённый в main и забытый в реестре, иначе молча не гонялся бы."""
    import inspect
    import re
    return set(re.findall(r'"(--[^"\s]+)" in арг', inspect.getsource(main))) - set(КЛЮЧИ_ПРОГОНА)


def _погасить_дерево(пр, лог):
    """У режима дочерний браузер: гасится дерево, иначе окно Chromium
    переживёт режим. Итог taskkill пишется в журнал, а не глушится."""
    if os.name == "nt":
        import subprocess
        р = subprocess.run(["taskkill", "/PID", str(пр.pid), "/T", "/F"],
                           capture_output=True, text=True, encoding="cp866", errors="replace")
        лог.write("[taskkill код %s] %s%s\n" % (р.returncode, р.stdout.strip(), р.stderr.strip()))
    else:
        пр.kill()


def _причина(ключи, ожидание, код, вывод):
    """Причина провала словами либо None, если режим прошёл."""
    import re
    строки = [с for с in вывод.splitlines() if с.strip()]
    if "Traceback (most recent call last)" in вывод:
        return "упал исключением: " + (строки[-1].strip() if строки else "?")
    итог = re.findall(r"^ИТОГ: ПЛОХО (\d+), ПРОПУСК (\d+)\s*$", вывод, re.M)
    if ключи != ("--сводка",) and not итог:
        return "не дошёл до строки ИТОГ (код %s)" % код
    # ПРОПУСК В ИТОГ — ПРОВАЛ ПРИ ЛЮБОМ ОЖИДАНИИ (письмо 3а задачи 343).
    # Режим-подлог отвечает кодом 1, если есть хоть один ПЛОХО, и ПРОПУСК
    # рядом с пойманным подлогом прежде засчитывался «пройдено»: шаг
    # не мерился, а сводка была зелёной.
    пропуск = [с.strip() for с in строки if с.lstrip().startswith("ПРОПУСК")]
    if код == 2 or (итог and int(итог[-1][1])):
        return "ПРОПУСК %s: %s" % (итог[-1][1] if итог else "?",
                                   пропуск[0] if пропуск else "код %s" % код)
    if код != ожидание:
        return "код %s, ожидался %s" % (код, ожидание)
    if ожидание == 1 and not int(итог[-1][0]):
        return "подлог не пойман: ПЛОХО 0"
    return None


def прогнать_все(подробно, только):
    import subprocess
    import threading
    import time
    from datetime import datetime
    выбрано = [р for р in РЕЖИМЫ if not только or р[0] in только]
    незнакомые = sorted(set(только or ()) - {р[0] for р in РЕЖИМЫ})
    if незнакомые:
        print("НЕЗНАКОМЫЕ РЕЖИМЫ в --только: %s. Реестр: %s" % (
            ", ".join(незнакомые), ", ".join(р[0] for р in РЕЖИМЫ)))
        return 2
    путь = os.environ.get("PF_LOG") or os.path.join(
        tempfile.gettempdir(), "check_portfolio", datetime.now().strftime("%Y%m%d-%H%M%S") + ".log")
    os.makedirs(os.path.dirname(путь), exist_ok=True)
    упали = []
    # ключ main() без записи в реестре — упавший режим, а не молчание
    if not только:
        for ключ in sorted(_ключи_main() - {к for р in РЕЖИМЫ for к in р[1]}):
            упали.append((ключ, "ключ разбирается в main(), но в реестре РЕЖИМЫ его нет", []))
    всего = len(выбрано) + len(упали)
    t0 = time.time()
    окружение = dict(os.environ, PYTHONIOENCODING="utf-8")
    with open(путь, "w", encoding="utf-8") as лог:
        for имя, ключи, ожидание in выбрано:
            заголовок = "\n══ %s  (%s, ожидается код %d)\n" % (имя, " ".join(ключи), ожидание)
            лог.write(заголовок)
            лог.flush()
            if подробно:
                print(заголовок, end="", flush=True)
            собрано = []
            try:
                пр = subprocess.Popen([sys.executable, os.path.abspath(__file__), *ключи],
                                      stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                      text=True, encoding="utf-8", errors="replace", env=окружение)
            except OSError as e:
                упали.append((имя, "не стартовал: %s" % e, []))
                лог.write("НЕ СТАРТОВАЛ: %s\n" % e)
                continue

            def читать(поток=пр.stdout):
                for строка in поток:
                    собрано.append(строка)
                    лог.write(строка)
                    if подробно:
                        print(строка, end="", flush=True)
            чтец = threading.Thread(target=читать, daemon=True)
            чтец.start()
            try:
                код = пр.wait(timeout=ПОТОЛОК_РЕЖИМА)
            except subprocess.TimeoutExpired:
                _погасить_дерево(пр, лог)
                пр.wait()
                чтец.join(10)
                упали.append((имя, "не уложился в %d с" % ПОТОЛОК_РЕЖИМА, собрано[-8:]))
                continue
            чтец.join()
            лог.write("[код %d]\n" % код)
            вывод = "".join(собрано)
            причина = _причина(ключи, ожидание, код, вывод)
            if причина:
                важное = [с for с in собрано if с.lstrip().startswith(("ПЛОХО", "ПРОПУСК", "ИТОГ"))]
                упали.append((имя, причина, (важное or собрано)[-8:]))
    print("ПРОБА ГЛАВНОЙ: режимов %d, прошли %d, упали %d (%.0f с)" % (
        всего, всего - len(упали), len(упали), time.time() - t0))
    for имя, причина, строки in упали:
        print("  УПАЛ %s — %s" % (имя, причина))
        for с in строки:
            print("      " + с.strip())
    print("полный вывод: %s" % путь)
    return 1 if упали else 0


def main():
    арг = sys.argv[1:]
    режим_задан = any(к.startswith("--") and к not in КЛЮЧИ_ПРОГОНА for к in арг)
    if not режим_задан:
        только = None
        if "--только" in арг:
            i = арг.index("--только")
            только = set(арг[i + 1].split(",")) if i + 1 < len(арг) else set()
        return прогнать_все("--verbose" in арг, только)
    if "--сводка" in арг:
        сводка()
        return 0
    if "--фон" in арг:
        # PF_SCRIM=top:70,bottom:45 — перебор долей притемнения без правки стилей
        притемнение = (dict(ч.split(":") for ч in os.environ["PF_SCRIM"].split(","))
                       if os.environ.get("PF_SCRIM") else None)
        фон(контроль_сети="--контроль-сети" in арг, контроль_рывка="--контроль-рывка" in арг,
            контроль_краёв="--контроль-краёв" in арг, только_контраст="--контраст" in арг,
            притемнение=притемнение)
    elif "--макет" in арг:
        подлоги = [к for к in ПОДЛОГИ_МАКЕТА if "--контроль-" + к in арг]
        if len(подлоги) > 1:
            print("подлог макета — по одному за прогон, а задано %s" % подлоги)
            return 2
        код = макет(подлоги[0] if подлоги else None)
        if код:
            print("\nИТОГ: ПЛОХО %d, ПРОПУСК %d" % (итог["плохо"], итог["пропуск"]))
            return код
    elif "--экран" in арг:
        экран(контроль_сдвига="--контроль" in арг, контроль_магнита="--контроль-магнита" in арг)
    elif "--лента" in арг and "--контроль-кадра" in арг:
        лента_кадры_контроль()
    elif "--лента" in арг:
        лента(контроль="--контроль" in арг, рывок="--контроль-плавности" in арг)
    elif "--о-себе" in арг:
        о_себе(контроль="--контроль" in арг, контроль_доли="--контроль-доли" in арг)
    elif "--инструменты" in арг:
        инструменты(контроль="--контроль" in арг, контроль_повтора="--контроль-повтора" in арг,
                    контроль_сброса="--контроль-сброса" in арг)
    elif "--связь" in арг:
        связь(контроль_буфера="--контроль-буфера" in арг)
    elif "--проекты" in арг:
        проекты(контроль="--контроль" in арг, контроль_ссылок="--контроль-ссылок" in арг,
                контроль_медиа="--контроль-медиа" in арг)
    else:
        print(__doc__)
        return 2
    print("\nИТОГ: ПЛОХО %d, ПРОПУСК %d" % (итог["плохо"], итог["пропуск"]))
    if итог["плохо"]:
        return 1
    return 2 if итог["пропуск"] else 0


if __name__ == "__main__":
    sys.exit(main())
