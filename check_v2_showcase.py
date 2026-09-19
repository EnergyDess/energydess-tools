"""ВИТРИНА ДИЗАЙН-СИСТЕМЫ v2: ФОКУС, КРАЯ ГРАДИЕНТА, ЗАГРУЗКА, ПОДПИСИ
ШКАЛЫ, ШАПКА (BACKLOG №352, письмо 2, блок 1).

ПРОВЕРКА, код 1 при находке, 2 — замерить нечем (стенда нет).

ЧТО СПРАШИВАЕТСЯ — по пункту письма на шаг:
  1. ФОКУС. Мышью — кольца нет; с клавиатуры (настоящий Tab) — кольцо
     2 px вплотную (`outline-offset: 0` у кнопок) в цвете самого органа:
     главная — цвет инструмента, опасная — красный, градиентная — середина
     градиента, вторичная и пункт меню — светлая линия. Контраст кольца
     к фону страницы — не ниже 3.
  2. КРАЯ ГРАДИЕНТА. Пиксели кнопки при DPR 3: столбец у левого края
     обязан быть ближе к НАЧАЛУ градиента, у правого — к КОНЦУ. Плюс
     у всех видов кнопок: где рамка прозрачна, а фон — градиент, фон
     обязан отсчитываться от края рамки.
  3. ЗАГРУЗКА. Ширина кнопки в загрузке равна обычной ±0 px; центр группы
     «кольцо + текст» совпадает с центром кнопки ±1 px — у всех видов,
     со значком и без.
  4. ШКАЛА. Подпись у образца кегля равна кеглю, вычисленному браузером;
     у трёх образцов Unbounded подписи разные.
  5. ШАПКА. Без рамки и скругления, линия под вкладками есть.
  6. ФИОЛЕТОВЫЙ. `--v2-workout` = #D08CFF.
  7. «НОВОСТИ» — с пометкой «скоро», не ссылка.

КЛЮЧИ:
  --снимки     кадры витрины на 390, 1920, 2560 в review_screenshots/redesign-v2/
  --контроль   три подлога в СТРАНИЦУ (кода не трогают), у каждого своё
               доказательство:
                 фокус    — вернуть `:focus` вместо `:focus-visible`
                            → кольцо появляется при клике мышью;
                 градиент — `background-origin: padding-box` → левый край
                            ближе к концу градиента;
                 загрузка — снять сужение полей → ширина вырастает.

Браузер НЕВИДИМЫЙ: ширины здесь собственные ширины кнопок, от контейнера
и полосы прокрутки они не зависят (§6.0.3).
"""
import io
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

АДРЕС = ch.БАЗА + "/admin/design-v2"
находок = 0
пропусков = 0

КОЛЬЦО = {  # вид -> ожидаемый цвет кольца (rgb)
    "главная": (79, 143, 255),       # --v2-hh, секция кнопок .v2-tool-hh
    "опасная": (239, 68, 68),        # --v2-danger
    "градиентная": (130, 87, 162),   # --v2-grad-b
    "вторичная": (174, 184, 212),    # --v2-ring-neutral
    "пункт меню": (174, 184, 212),
}
СЕЛЕКТОР = {
    "главная": ".v2s-btns .v2-btn-primary:not([disabled]):not([class*='is-'])",
    "опасная": ".v2s-btns .v2-btn-danger:not([disabled]):not([class*='is-'])",
    "градиентная": ".v2s-btns .v2-btn-gradient:not([disabled]):not([class*='is-'])",
    "вторичная": ".v2s-btns .v2-btn-secondary:not([disabled]):not([class*='is-'])",
    "пункт меню": ".v2-menu .v2-menu-item",
}
ФОН = (10, 11, 18)  # --v2-bg


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


def _lin(c):
    c /= 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def контраст(a, b):
    la = 0.2126 * _lin(a[0]) + 0.7152 * _lin(a[1]) + 0.0722 * _lin(a[2])
    lb = 0.2126 * _lin(b[0]) + 0.7152 * _lin(b[1]) + 0.0722 * _lin(b[2])
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _rgb(s):
    import re
    ч = [int(float(x)) for x in re.findall(r"[\d.]+", s)[:3]]
    return tuple(ч)


def дальность(a, b):
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


# ---------------------------------------------------------------- замеры

def замер_фокуса(стр):
    """{вид: (кольцо мышью, кольцо с клавиатуры, цвет, смещение)}."""
    итог = {}
    for вид, сел in СЕЛЕКТОР.items():
        эл = стр.locator(сел).first
        if not эл.count():
            continue
        эл.scroll_into_view_if_needed()
        эл.click()
        мышь = эл.evaluate("e => [document.activeElement === e, getComputedStyle(e).outlineStyle, getComputedStyle(e).outlineWidth]")
        # С клавиатуры: шаг назад и вперёд настоящим Tab — `:focus-visible`
        # браузер ставит по источнику фокуса, программный focus() его
        # на кнопке не зажигает (§6.0.3).
        стр.keyboard.press("Shift+Tab")
        стр.keyboard.press("Tab")
        клав = эл.evaluate("""e => { const s = getComputedStyle(e);
            return [document.activeElement === e, s.outlineStyle, s.outlineWidth, s.outlineColor, s.outlineOffset]; }""")
        стр.mouse.click(1, 1)
        кольцо_мышь = мышь[0] and мышь[1] != "none" and мышь[2] != "0px"
        итог[вид] = {"мышь": кольцо_мышь, "фокус_клав": клав[0],
                     "клав": клав[1] != "none" and клав[2] != "0px",
                     "цвет": _rgb(клав[3]), "смещение": клав[4], "ширина": клав[2]}
    return итог


def замер_краёв(стр):
    """Пиксели градиентной кнопки при DPR 3 и сверка всех видов."""
    from PIL import Image
    эл = стр.locator(СЕЛЕКТОР["градиентная"]).first
    эл.scroll_into_view_if_needed()
    стр.mouse.move(1, 1)
    png = эл.screenshot(animations="disabled")
    im = Image.open(io.BytesIO(png)).convert("RGB")
    w, h = im.size
    y = h // 2
    лево, право = im.getpixel((1, y)), im.getpixel((w - 2, y))
    нач = (0x14, 0x6A, 0xFF)   # --v2-grad-a
    кон = (0xA2, 0x59, 0x04)   # --v2-grad-c
    виды = стр.evaluate("""() => [...new Set([...document.querySelectorAll('.v2s-btns .v2-btn')]
        .map(b => [...b.classList].find(k => /^v2-btn-(primary|secondary|danger|gradient)$/.test(k))))]
        .map(k => { const b = document.querySelector('.v2s-btns .' + k); const s = getComputedStyle(b);
          const прозр = /rgba\\(.*,\\s*0\\)$/.test(s.borderLeftColor) || s.borderLeftColor === 'transparent';
          return {вид: k, прозрачная_рамка: прозр, градиент: s.backgroundImage.includes('gradient'),
                  origin: s.backgroundOrigin}; })""")
    return {"лево": лево, "право": право, "лево_к_началу": дальность(лево, нач) < дальность(лево, кон),
            "право_к_концу": дальность(право, кон) < дальность(право, нач), "виды": виды, "размер": (w, h)}


def замер_загрузки(стр):
    """Пары «обычная / загрузка» из витрины: ширины и центр группы."""
    return стр.evaluate("""() => {
      const пары = [];
      const пусто = b => !b.disabled && ![...b.classList].some(k => k.startsWith('is-'));
      // сетка состояний: в каждом ряду вида первая — обычная, последняя — загрузка
      for (const ряд of document.querySelectorAll('.v2s-btns')) {
        const кн = [...ряд.querySelectorAll('.v2-btn')];
        for (const з of кн.filter(b => b.classList.contains('is-loading'))) {
          const вид = [...з.classList].find(k => /^v2-btn-(primary|secondary|danger|gradient)$/.test(k));
          const есть_значок = !!з.querySelector(':scope > svg');
          const об = кн.find(b => пусто(b) && b.classList.contains(вид)
                                 && !!b.querySelector(':scope > svg') === есть_значок);
          if (!об) continue;
          const rz = з.getBoundingClientRect(), ro = об.getBoundingClientRect();
          const s = getComputedStyle(з), p = getComputedStyle(з, '::before');
          const текст = [...з.childNodes].find(n => n.nodeType === 3 && n.textContent.trim());
          const r = document.createRange(); r.selectNodeContents(текст);
          const tr = r.getBoundingClientRect();
          const кольцо = parseFloat(p.width), зазор = parseFloat(s.columnGap);
          const лево = tr.left - зазор - кольцо;
          пары.push({вид, значок: есть_значок, ширина_обычной: ro.width, ширина_загрузки: rz.width,
                     центр_группы: (лево + tr.right) / 2, центр_кнопки: rz.left + rz.width / 2,
                     кольцо, до_кольца: p.content});
        }
      }
      return пары;
    }""")


def замер_шкалы(стр):
    return стр.evaluate("""() => [...document.querySelectorAll('[data-px]')].map(e =>
        ({подпись: e.textContent.trim(), px: parseFloat(getComputedStyle(e.parentElement).fontSize),
          unbounded: e.parentElement.classList.contains('v2s-fs-display')}))""")


def замер_прочего(стр):
    return стр.evaluate("""() => {
      const h = document.querySelector('.v2-page-head'), s = getComputedStyle(h);
      const t = getComputedStyle(h.querySelector('.v2-tabs'));
      const новости = [...document.querySelectorAll('.v2-side .v2-side-item')]
          .filter(e => e.textContent.includes('Новости'));
      return {рамка: s.borderTopWidth + ' ' + s.borderLeftWidth, радиус: s.borderTopLeftRadius,
              линия: t.borderBottomWidth + ' ' + t.borderBottomStyle,
              workout: getComputedStyle(document.documentElement).getPropertyValue('--v2-workout').trim(),
              новости: новости.length, новости_скоро: новости.filter(e => e.classList.contains('is-soon') && e.tagName !== 'A').length,
              ассистент_hh: [...document.querySelectorAll('.v2-tool-hh .v2-page-head .v2-head-actions')]
                  .some(a => a.textContent.includes('ассистент')),
              ассистент_ens: [...document.querySelectorAll('.v2-tool-enshrouded .v2-page-head .v2-head-actions')]
                  .some(a => a.textContent.includes('ассистент')),
              ассистент_medkit: [...document.querySelectorAll('.v2-tool-medkit .v2-page-head .v2-head-actions')]
                  .some(a => a.textContent.includes('ассистент'))};
    }""")


# ---------------------------------------------------------------- прогон

ПОДЛОГ_ФОКУС = ".v2-btn:focus, .v2-menu-item:focus { outline: 2px solid var(--v2-ring, var(--v2-ring-neutral)) !important; outline-offset: 0 !important; }"
ПОДЛОГ_ГРАДИЕНТ = ".v2-btn-gradient { background-origin: padding-box !important; }"
ПОДЛОГ_ЗАГРУЗКА = ".v2-btn.is-loading:not(:has(> svg)):not(.v2-btn-icon) { padding-inline: var(--v2-sp-5) !important; }"


def страница(p, ширина=1440, dpr=3, стиль=None):
    бр = p.chromium.launch()
    к = бр.new_context(viewport={"width": ширина, "height": 900}, device_scale_factor=dpr)
    стр = к.new_page()
    ch._войти(стр)
    стр.goto(АДРЕС, wait_until="networkidle")
    стр.evaluate("document.fonts.ready")
    if стиль:
        стр.add_style_tag(content=стиль)
    return бр, стр


def проверить(стиль=None, печать=True):
    """Все шаги на одной странице; возвращает сырые замеры."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        бр, стр = страница(p, стиль=стиль)
        ф = замер_фокуса(стр)
        к = замер_краёв(стр)
        з = замер_загрузки(стр)
        ш = замер_шкалы(стр)
        пр = замер_прочего(стр)
        бр.close()
    if not печать:
        return ф, к, з, ш, пр
    print("1. ФОКУС")
    for вид, м in ф.items():
        жд = КОЛЬЦО[вид]
        кр = контраст(м["цвет"], ФОН)
        шаг(f"{вид}: мышью кольца нет", not м["мышь"])
        шаг(f"{вид}: с клавиатуры кольцо есть", м["фокус_клав"] and м["клав"],
            f"ширина {м['ширина']}, смещение {м['смещение']}")
        шаг(f"{вид}: цвет кольца {м['цвет']}", дальность(м["цвет"], жд) < 3, f"ждали {жд}")
        шаг(f"{вид}: контраст кольца к фону {кр:.2f} ≥ 3", кр >= 3)
        if вид != "пункт меню":
            шаг(f"{вид}: кольцо вплотную, без зазора", м["смещение"] == "0px", м["смещение"])
    шаг("виды кнопок и пункт меню найдены", len(ф) == len(СЕЛЕКТОР), f"{len(ф)} из {len(СЕЛЕКТОР)}",
        собрано=len(ф))
    print("2. КРАЯ ГРАДИЕНТА")
    шаг("левый край ближе к началу градиента", к["лево_к_началу"], f"пиксель {к['лево']}")
    шаг("правый край ближе к концу градиента", к["право_к_концу"], f"пиксель {к['право']}")
    for в in к["виды"]:
        опасно = в["прозрачная_рамка"] and в["градиент"]
        шаг(f"{в['вид']}: фон под прозрачной рамкой от края рамки",
            (not опасно) or в["origin"] == "border-box",
            f"рамка прозрачна {в['прозрачная_рамка']}, градиент {в['градиент']}, origin {в['origin']}")
    print("3. ЗАГРУЗКА")
    for п in з:
        имя = f"{п['вид']}{' со значком' if п['значок'] else ''}"
        разн = п["ширина_загрузки"] - п["ширина_обычной"]
        шаг(f"{имя}: ширина {п['ширина_обычной']:.1f} → {п['ширина_загрузки']:.1f}", abs(разн) < 0.05)
        сдв = п["центр_группы"] - п["центр_кнопки"]
        шаг(f"{имя}: центр группы от центра кнопки {сдв:+.2f} px", abs(сдв) <= 1)
    шаг("пары «обычная / загрузка» найдены", len(з) >= 8, f"{len(з)}", собрано=len(з))
    print("4. ШКАЛА ШРИФТОВ")
    for о in ш:
        шаг(f"подпись «{о['подпись']}» = кегль {о['px']:.1f}",
            о["подпись"] == f"{round(о['px'] * 10) / 10:g} px")
    ун = [о["подпись"] for о in ш if о["unbounded"]]
    шаг("три образца Unbounded подписаны по-разному", len(set(ун)) == len(ун) == 3, ", ".join(ун),
        собрано=len(ун))
    print("5–7. ШАПКА, ФИОЛЕТОВЫЙ, НОВОСТИ, АССИСТЕНТ")
    шаг("шапка без рамки", пр["рамка"] == "0px 0px", пр["рамка"])
    шаг("шапка без скругления", пр["радиус"] == "0px", пр["радиус"])
    шаг("линия под вкладками есть", пр["линия"].startswith("1px solid"), пр["линия"])
    шаг("--v2-workout фиолетовый", пр["workout"].upper() == "#D08CFF", пр["workout"])
    шаг("«Новости» с пометкой «скоро» во всех образцах меню", пр["новости"] and пр["новости_скоро"] == пр["новости"],
        f"{пр['новости_скоро']} из {пр['новости']}", собрано=пр["новости"])
    шаг("кнопки ассистента нет у HH и Enshrouded, есть у аптечки",
        not пр["ассистент_hh"] and not пр["ассистент_ens"] and пр["ассистент_medkit"])
    return ф, к, з, ш, пр


def снимки():
    from playwright.sync_api import sync_playwright
    куда = os.path.join("review_screenshots", "redesign-v2")
    os.makedirs(куда, exist_ok=True)
    with sync_playwright() as p:
        for ш in (390, 1920, 2560):
            бр, стр = страница(p, ширина=ш, dpr=1)
            путь = os.path.join(куда, f"design-v2-{ш}.png")
            стр.screenshot(path=путь, full_page=True, animations="disabled")
            print("снимок:", путь)
            бр.close()


ДОКАЗАТЕЛЬСТВА = {
    "фокус": "кольцо при клике мышью у главной кнопки: нет → есть",
    "градиент": "левый пиксель градиентной кнопки: к началу → к концу",
    "загрузка": "ширина главной кнопки в загрузке: равна обычной → шире",
}


def контроль():
    print("ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ ВИТРИНЫ v2")
    global находок
    ф0, к0, з0, _, _ = проверить(печать=False)
    итог = 0
    for имя, стиль in (("фокус", ПОДЛОГ_ФОКУС), ("градиент", ПОДЛОГ_ГРАДИЕНТ),
                       ("загрузка", ПОДЛОГ_ЗАГРУЗКА)):
        находок = 0
        print(f"\n--- подлог «{имя}» ---")
        ф, к, з, ш, пр = проверить(стиль, печать=False)
        if имя == "фокус":
            до, после = ф0["главная"]["мышь"], ф["главная"]["мышь"]
        elif имя == "градиент":
            до, после = к0["лево_к_началу"], к["лево_к_началу"]
            до, после = not до, not после
        else:
            до = abs(з0[0]["ширина_загрузки"] - з0[0]["ширина_обычной"]) > 0.05
            после = abs(з[0]["ширина_загрузки"] - з[0]["ширина_обычной"]) > 0.05
        print(f"   доказательство: {ДОКАЗАТЕЛЬСТВА[имя]}: дефект {до} → {после}")
        # вердикт пробы — полный печатный прогон с тем же подлогом
        import contextlib
        буф = io.StringIO()
        with contextlib.redirect_stdout(буф):
            проверить(стиль)
        найдено = находок > 0
        print(f"   проба: находок {находок} — {'НАЙДЕН' if найдено else 'НЕ НАЙДЕН'}")
        for стр_ in буф.getvalue().splitlines():
            if "ПЛОХО" in стр_:
                print("     " + стр_.strip())
        if not (not до and после and найдено):
            итог = 1
    print("\nКОНТРОЛЬ:", "3 ПОДЛОГА ИЗ 3 НАЙДЕНЫ" if итог == 0 else "ПРОВАЛЕН")
    return итог


if __name__ == "__main__":
    if "--контроль" in sys.argv:
        sys.exit(контроль())
    if "--снимки" in sys.argv:
        снимки()
        sys.exit(0)
    проверить()
    print(f"ИТОГ: находок {находок}, пропусков {пропусков}")
    sys.exit(1 if находок else (2 if пропусков else 0))
