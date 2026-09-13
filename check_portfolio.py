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
          ярких_кнопок_шапки: [...шапка.querySelectorAll('.btn-primary')].length,
          имя_в_шапке: лого.textContent.trim(), строк_имени_в_шапке: верхи_лого.length};
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
    png = стр.locator(".pf-hero .pf-grad").screenshot()
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


def экран(контроль_сдвига=False):
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
                шаг("в шапке слева имя", з["имя_в_шапке"] == "Денис Кащеев",
                    "«%s»" % з["имя_в_шапке"])
                шаг("имя в шапке одной строкой", з["строк_имени_в_шапке"] == 1,
                    "строк %d" % з["строк_имени_в_шапке"])
                шаг("в шапке нет яркой кнопки — вход и регистрация обводкой",
                    з["ярких_кнопок_шапки"] == 0, "ярких %d" % з["ярких_кнопок_шапки"])
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
                шаг("в ленте нет плееров и кнопок", кнопок == 0, "органов %d" % кнопок)

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


def _к_тексту(стр, доля_окна):
    """Прокрутка так, чтобы верх абзаца встал на `доля_окна` высоты окна."""
    стр.evaluate("""(д) => { const т = document.querySelector('.pf-about-text');
      const y = т.getBoundingClientRect().top + scrollY - innerHeight * д;
      window.scrollTo(0, Math.max(0, y)); }""", доля_окна)
    стр.wait_for_timeout(600)


def о_себе(контроль=False):
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
                с.goto(БАЗА + "/", wait_until="networkidle", timeout=60000)
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
                _к_тексту(с, 1.0)
                ноль = с.evaluate(ЗАМЕР_О_СЕБЕ)["полных"]
                _к_тексту(с, 0.55)
                середина = с.evaluate(ЗАМЕР_О_СЕБЕ)["полных"]
                _к_тексту(с, -1.0)
                после = с.evaluate(ЗАМЕР_О_СЕБЕ)
                шаг("текст проявляется посимвольно по мере прокрутки",
                    ноль == 0 and 0 < середина < после["знаков"] and после["полных"] == после["знаков"],
                    "полных знаков: у нижнего края %d, посередине %d, выше %d из %d" % (
                        ноль, середина, после["полных"], после["знаков"]), собрано=после["знаков"])
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


def main():
    арг = sys.argv[1:]
    if "--экран" in арг:
        экран(контроль_сдвига="--контроль" in арг)
    elif "--лента" in арг:
        лента(контроль="--контроль" in арг, рывок="--контроль-плавности" in арг)
    elif "--о-себе" in арг:
        о_себе(контроль="--контроль" in арг)
    else:
        print(__doc__)
        return 2
    print("\nИТОГ: ПЛОХО %d, ПРОПУСК %d" % (итог["плохо"], итог["пропуск"]))
    if итог["плохо"]:
        return 1
    return 2 if итог["пропуск"] else 0


if __name__ == "__main__":
    sys.exit(main())
