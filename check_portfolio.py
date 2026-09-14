# -*- coding: utf-8 -*-
"""ГОСТЕВАЯ ГЛАВНАЯ-ПОРТФОЛИО ГЛАЗАМИ ЧЕЛОВЕКА (заход 334).

МЕРКА С КОДОМ ВОЗВРАТА: 0 — всё сошлось, 1 — есть ПЛОХО, 2 — есть
ПРОПУСК (мерить было нечего) либо нет стенда. Стенд и ГОЛОВНОЙ браузер
(§6.0.3): ширина и перенос строк в headless меряются не про тот экран.

ПОЧЕМУ ОТДЕЛЬНАЯ ПРОБА. Путь `/` отдаёт ДВЕ страницы по состоянию входа,
и все браузерные пробы ряда стенда ходят туда С СЕССИЕЙ — то есть снимают
лаунчер. Гостевую главную до этого захода не открывала ни одна проба и ни
один тест (замер блока A4). Здесь она открывается гостем.

РЕЖИМЫ — по блокам письма, у каждого свой вопрос:

  py check_portfolio.py --экран     # B: первый экран
  py check_portfolio.py --лента     # C: бегущая лента работ
  py check_portfolio.py --о-себе    # D: о себе
  py check_portfolio.py --инструменты   # E: инструменты
  py check_portfolio.py --проекты   # F: проекты и подвал
  py check_portfolio.py --экран --контроль-магнита  # подлог ввода магнита (339, A4)
  py check_portfolio.py --о-себе --контроль-доли    # подлог расчёта доли (339, B)
  py check_portfolio.py --инструменты --контроль-повтора  # подлог повтора (339, D3)
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
                шаг("шапка плюс первый экран — ровно окно", abs(низ_экрана - з["vh"]) <= 1,
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
  const ролики = [...лента.querySelectorAll('video')].map(в => ({
    src: !!в.getAttribute('src'), играет: !в.paused, время: в.currentTime,
    готов: в.readyState}));
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
        if "/landing-media/" in адрес and ".mp4" in адрес:
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
                с.goto(БАЗА + "/", wait_until="networkidle", timeout=60000)
                с.wait_for_timeout(1500)
                до = с.evaluate(ЛЕНТА_СОСТОЯНИЕ)
                if до is None:
                    шаг("лента есть на странице", False, "нет .pf-feed")
                    к.close()
                    continue
                байт_до, роликов_до = сеть["байт"], сеть["роликов"]
                заполненных = sum(1 for б in до["коробки"] if б[2] == "yes")
                с_адресом_до = sum(1 for р in до["ролики"] if р["src"])
                шаг("в первом экране ролики ленты не грузятся",
                    роликов_до == 0 and с_адресом_до == 0,
                    "запросов роликов %d, роликов с адресом %d из %d; скачано всего %d КБ" % (
                        роликов_до, с_адресом_до, len(до["ролики"]), байт_до // 1024),
                    собрано=len(до["ролики"]))

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
                с_файлом = [р for р in после["ролики"] if р["src"]]
                играют = [р for р in с_файлом if р["играет"] and р["время"] > 0.2]
                шаг("ролики играют сами, без нажатия", len(играют) == len(с_файлом),
                    "с файлом %d, играют %d" % (len(с_файлом), len(играют)), собрано=len(с_файлом))
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
            сторона: д.dataset.side};
  });
  return {vw: document.documentElement.clientWidth, vh: innerHeight, сек: пр(сек),
          тело: пр(тело), текст: пр(сек.querySelector('.pf-about-text')),
          знаков: знаки.length, полных, декор};
}"""

ШИРИНЫ_О_СЕБЕ = ШИРИНЫ + [(1101, 900, False)]


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
                наружу = [д for д in до["декор"]
                          if д["видимость"] < 0.01 and (д["сдвиг"] < 0 if д["сторона"] == "l" else д["сдвиг"] > 0)]
                шаг("до доезда декор спрятан и отведён в свою сторону", len(наружу) == len(до["декор"]),
                    "объектов %d, спрятаны наружу %d" % (len(до["декор"]), len(наружу)), собрано=len(до["декор"]))
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
                выехали = [д for д in после["декор"] if д["видимость"] > 0.99 and abs(д["сдвиг"]) < 0.5]
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
                видны = [д for д in т["декор"] if д["видимость"] > 0.99 and abs(д["сдвиг"]) < 0.5]
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
    if (э.closest('.btn-primary')) { кнопки.push(+k.toFixed(2)); continue; }
    if (э.closest('.pf-mock')) { внутри.всего++; внутри.мин = Math.min(внутри.мин, k); }
    else { вне.всего++; вне.мин = Math.min(вне.мин, k); if (k < (крупный ? 3 : 4.5)) вне.ниже++; }
  }
  return {страница: hex(фон_тела), секция: hex(фон(сек)), радиус: parseFloat(getComputedStyle(сек).borderTopLeftRadius),
          вне, внутри, кнопки,
          // E (заход 339): блок регистрации идёт ПОСЛЕ списка и зовёт кнопкой
          join: (() => { const б = сек.querySelector('.pf-join'), сп = сек.querySelector('.pf-tool-list');
            if (!б) return null; const а = б.querySelector('a[href="/register"]');
            return {после_списка: !!сп && б.getBoundingClientRect().top >= сп.getBoundingClientRect().bottom,
                    высота: б.getBoundingClientRect().height,
                    кнопка: а ? {фон: getComputedStyle(а).backgroundColor, высота: а.getBoundingClientRect().height} : null,
                    свой_фон: hex(фон(б)) !== hex(фон(сек))}; })()};
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


def инструменты(контроль=False, контроль_повтора=False):
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
                шаг("секция инструментов на ступень светлее страницы, верхние углы скруглены",
                    сек is not None and сек["секция"] != сек["страница"] and сек["радиус"] > 0,
                    "фон страницы %s, секции %s, радиус %.0f px" % (
                        (сек or {}).get("страница"), (сек or {}).get("секция"), (сек or {}).get("радиус", 0)))
                дж = (сек or {}).get("join")
                шаг("E: блок регистрации после списка, отделён фоном, кнопка залита и не ниже 40 px",
                    bool(дж) and дж["после_списка"] and дж["свой_фон"] and дж["кнопка"]
                    and "rgba(0, 0, 0, 0)" not in дж["кнопка"]["фон"] and дж["кнопка"]["высота"] >= 40,
                    "высота блока %.1f, кнопка %s, контраст подписей кнопок %s" % (
                        (дж or {}).get("высота", 0), (дж or {}).get("кнопка"), (сек or {}).get("кнопки")))
                шаг("текст секции вне макетов не ниже порога контраста",
                    сек is not None and сек["вне"]["ниже"] == 0,
                    "текстов %d, минимум %.2f, ниже порога %d" % (
                        сек["вне"]["всего"], сек["вне"]["мин"], сек["вне"]["ниже"]), собрано=сек["вне"]["всего"])
                for i in range(len(список)):
                    # СВОЯ ЗАГРУЗКА НА КАЖДЫЙ ИНТЕРФЕЙС: соседний мог начать
                    # играть, пока проба стояла у предыдущего.
                    с.goto(БАЗА + "/", wait_until="networkidle", timeout=60000)
                    с.wait_for_timeout(300)
                    нач = с.evaluate(СНИМОК_МАКЕТА, i)
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
                    шаг("%s: оживает при доезде — из начала в конец" % нач["имя"],
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
                        шаг("%s: шаги встают по одному" % нач["имя"], по_одному,
                            "готовых шагов по кадрам: %s из %d" % (" → ".join(map(str, ряд)), нач["шагов"]),
                            собрано=нач["шагов"])
                    с.wait_for_timeout(3000)
                    позже = с.evaluate(СНИМОК_МАКЕТА, i)
                    шаг("%s: пока в окне — один проход, через 3 с ничего не движется" % нач["имя"],
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
                    шаг("%s: при трёх заездах в окно — три прохода" % нач["имя"], проходов == 3,
                        "проходов %d; %s" % (проходов, "; ".join(ход)))

                # ── D5: запуск по мере въезда, а не все разом ──
                с.goto(БАЗА + "/", wait_until="networkidle", timeout=60000)
                с.wait_for_timeout(300)
                верх, низ = с.evaluate("""() => { const с = document.querySelector('.pf-tools').getBoundingClientRect();
                    return [с.top + scrollY - innerHeight, с.bottom + scrollY]; }""")
                одновременно, вне_окна, замеров = 0, 0, 0
                y = верх
                while y <= низ:
                    с.evaluate("(y) => window.scrollTo(0, y)", y)
                    с.wait_for_timeout(120)
                    играет, играет_вне = с.evaluate("""() => { const и = [...document.querySelectorAll('[data-pf-anim]')]
                        .filter(м => м.dataset.pfState === 'play');
                      return [и.length, и.filter(м => { const к = м.getBoundingClientRect();
                        return к.bottom <= 0 || к.top >= innerHeight; }).length]; }""")
                    одновременно = max(одновременно, играет)
                    вне_окна = max(вне_окна, играет_вне)
                    замеров += 1
                    y += в / 3
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
              кнопка: !!к.querySelector('.pf-proj-go, .pf-proj-soon'),
              прилипание: стиль.position, верх_прилипания: parseFloat(стиль.top),
              коробка: пр(к), карточка: пр(коробка),
              масштаб: коробка.getBoundingClientRect().width / коробка.offsetWidth,
              места};
    }),
    кнопки: [...document.querySelectorAll('.pf-final-btns a')].map(а => Object.assign(пр(а),
            {href: а.getAttribute('href'), текст: а.textContent.trim()}))};
}"""


def проекты(контроль=False):
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
                с.wait_for_timeout(500)
                з = с.evaluate(ЗАМЕР_ПРОЕКТОВ)
                if з is None:
                    шаг("секция проектов есть", False, "нет .pf-proj")
                    к.close()
                    continue
                полных = [кр for кр in з["карточки"]
                          if кр["n"] and кр["род"] and кр["имя"] and кр["кнопка"] and all(з_ for з_ in кр["места"].values())]
                шаг("карточек 3: номер, род работы, название, кнопка, три картинки",
                    len(з["карточки"]) == 3 and len(полных) == 3,
                    ", ".join("%s %s" % (кр["n"], кр["имя"]) for кр in з["карточки"]), собрано=len(з["карточки"]))
                сетка = [кр["имя"] for кр in з["карточки"]
                         if кр["места"]["c"]["x"] >= кр["места"]["a"]["r"] and кр["места"]["c"]["x"] >= кр["места"]["b"]["r"]
                         and кр["места"]["b"]["y"] >= кр["места"]["a"]["b"]
                         and кр["места"]["c"]["r"] <= кр["карточка"]["r"] + 0.5 and кр["места"]["b"]["b"] <= кр["карточка"]["b"] + 0.5]
                шаг("в карточке две картинки слева столбцом, высокая справа", len(сетка) == len(з["карточки"]),
                    "по сетке %d из %d" % (len(сетка), len(з["карточки"])), собрано=len(з["карточки"]))
                влезают = [кр["имя"] for кр in з["карточки"] if кр["коробка"]["h"] <= в - кр["верх_прилипания"]]
                шаг("карточка влезает в окно под шапкой — прилипшую видно целиком",
                    len(влезают) == len(з["карточки"]),
                    "высота карточек %s при месте %s" % (
                        [round(кр["коробка"]["h"]) for кр in з["карточки"]],
                        [round(в - кр["верх_прилипания"]) for кр in з["карточки"]]), собрано=len(з["карточки"]))
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
                    len(кн) == 2 and кн[0]["href"].startswith("mailto:") and кн[1]["href"] == "/register" and ряд,
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


def main():
    арг = sys.argv[1:]
    if "--экран" in арг:
        экран(контроль_сдвига="--контроль" in арг, контроль_магнита="--контроль-магнита" in арг)
    elif "--лента" in арг:
        лента(контроль="--контроль" in арг, рывок="--контроль-плавности" in арг)
    elif "--о-себе" in арг:
        о_себе(контроль="--контроль" in арг, контроль_доли="--контроль-доли" in арг)
    elif "--инструменты" in арг:
        инструменты(контроль="--контроль" in арг, контроль_повтора="--контроль-повтора" in арг)
    elif "--проекты" in арг:
        проекты(контроль="--контроль" in арг)
    else:
        print(__doc__)
        return 2
    print("\nИТОГ: ПЛОХО %d, ПРОПУСК %d" % (итог["плохо"], итог["пропуск"]))
    if итог["плохо"]:
        return 1
    return 2 if итог["пропуск"] else 0


if __name__ == "__main__":
    sys.exit(main())
