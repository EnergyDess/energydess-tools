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
  const имя = q('.pf-grad');
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
    png = стр.locator(".pf-grad").screenshot()
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


def main():
    арг = sys.argv[1:]
    if "--экран" in арг:
        экран(контроль_сдвига="--контроль" in арг)
    else:
        print(__doc__)
        return 2
    print("\nИТОГ: ПЛОХО %d, ПРОПУСК %d" % (итог["плохо"], итог["пропуск"]))
    if итог["плохо"]:
        return 1
    return 2 if итог["пропуск"] else 0


if __name__ == "__main__":
    sys.exit(main())
