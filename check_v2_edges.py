"""ПРОВЕРКА 56: ШАПКА ИНСТРУМЕНТА v2 — ЦЕНТР КНОПОК И ОДНИ КРАЯ
(№352, «питание-3», блок 1).

ПРОВЕРКА, код 1 при находке, 2 — замерить нечем (стенда нет либо ни на одном
экране шапки нет).

Два замечания владельца, оба про ОБОЛОЧКУ, а не про один инструмент:
  (а) кнопки действий шапки («AI-ассистент», «Добавить» и соседи) стояли
      у верхнего края, на уровне мелкой подписи «ПИТАНИЕ». Правило: центр
      группы кнопок по вертикали — на центре строки заголовка h1, ±2 px;
      Кнопка, налезающая на заголовок, — находка при любой ширине (так было
      у аптечки на 1280: колонка текста сжималась уже самого заголовка);
  (б) шапка и линия вкладок шире содержимого: левый край заголовка левее
      первой карточки. Правило: левый и правый края шапки, линии вкладок
      и содержимого совпадают, ±1 px.

ЧТО ТАКОЕ «СОДЕРЖИМОЕ». Самые внешние видимые БЛОКИ под шапкой — элемент
с рамкой либо фоном шириной от 120 px, у которого нет такого же предка
ниже шапки. Край содержимого — наименьший левый и наибольший правый край
таких блоков. Перечня классов карточек нет: у пяти инструментов карточки
названы по-разному, и перечень отстал бы на шестом (§6.0.7).

Экран без шапки v2 печатается «нет шапки», без кнопок — «нет кнопок»;
находкой это не является.

Браузер ВИДИМЫЙ, на втором мониторе (§6.0.3): края считаются от контейнера
страницы, а headless не отнимает у него полосу прокрутки. В базу НЕ ПИШЕТ.

КЛЮЧИ:
  --замер      только таблица чисел, без вердикта (код 0)
  --контроль   подлоги: `align-items: flex-start` у шапки (центр кнопок)
               и свой боковой отступ у шапки (края); каждый обязан уронить
               СВОЮ строку.
"""
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

ШИРИНЫ = (1600, 1280, 390)

# (путь, имя, чем открыть вкладку либо None). Экраны оболочки v2 —
# все страницы вошедшего, у которых есть шапка инструмента, плюс те,
# где её нет: там печатается «нет шапки», и это видно, а не пропущено.
ЭКРАНЫ = [
    ("/hh", "hh · письмо", None),
    ("/hh", "hh · история", "switchView('history')"),
    ("/hh", "hh · досье", "switchView('dossier')"),
    ("/hh", "hh · резюме", "switchView('resume')"),
    ("/nutrition", "питание · дневник", None),
    ("/nutrition", "питание · история", "document.querySelector('.v2-tab[data-tab=history]').click()"),
    ("/nutrition", "питание · вес", "document.querySelector('.v2-tab[data-tab=weight]').click()"),
    ("/nutrition", "питание · профиль", "document.querySelector('.v2-tab[data-tab=profile]').click()"),
    ("/medkit", "аптечка", None),
    ("/enshrouded", "enshrouded", None),
    ("/workout", "тренировки · программа", None),
    ("/workout/profile", "тренировки · профиль", None),
    ("/", "главная", None),
    ("/profile", "профиль", None),
    ("/admin/users", "админ · пользователи", None),
    ("/admin/products", "админ · продукты", None),
    ("/admin/exercises", "админ · упражнения", None),
    ("/admin/enshrouded", "админ · enshrouded", None),
    ("/admin/usage", "админ · расход", None),
]

ЗАМЕР = r"""() => {
  const R = e => e.getBoundingClientRect();
  const вид = e => { if (!e.checkVisibility({opacityProperty: true, visibilityProperty: true})) return false;
    const b = R(e); return b.width > 0 && b.height > 0; };
  const h = [...document.querySelectorAll('.v2-page-head')].find(вид);
  if (!h) return {шапки: false};
  const s = getComputedStyle(h), hb = R(h);
  const т = h.querySelector('.v2-head-title');
  const тб = R(т);
  // ТЕКСТ заголовка, а не его коробка: коробка h1 — ширина колонки
  const диап = document.createRange(); диап.selectNodeContents(т);
  const тт = диап.getBoundingClientRect();
  // центр СТРОКИ h1: при переносе заголовка — первой строки
  const стр = т.getClientRects()[0] || тб;
  const out = {шапки: true,
    шапка: [hb.left + parseFloat(s.paddingLeft), hb.right - parseFloat(s.paddingRight)],
    h1: [тб.left, тб.right], центр_h1: (стр.top + стр.bottom) / 2};
  const tabs = [...h.querySelectorAll('.v2-tabs')].find(вид);
  if (tabs) { const b = R(tabs); out.вкладки = [b.left, b.right]; }
  const кн = [...h.querySelectorAll('.v2-head-actions > *')].filter(вид);
  if (кн.length) {
    const top = Math.min(...кн.map(e => R(e).top)), bot = Math.max(...кн.map(e => R(e).bottom));
    out.центр_кнопок = (top + bot) / 2;
    out.кнопок_рядов = new Set(кн.map(e => Math.round(R(e).top))).size;
    // в строке заголовка — верх группы выше низа h1; под текстом (телефон)
    // центр не спрашивается
    out.кнопки_рядом = top < тб.bottom;
    // наложение кнопки на заголовок — находка при любой раскладке
    out.налезают = кн.some(e => { const b = R(e);
      return b.left < тт.right - 1 && b.right > тт.left + 1 && b.top < тт.bottom - 1 && b.bottom > тт.top + 1; });
  }
  // содержимое: самые внешние видимые блоки с рамкой либо фоном ниже шапки
  const блок = e => { const c = getComputedStyle(e);
    return (parseFloat(c.borderLeftWidth) > 0 && c.borderLeftStyle !== 'none')
        || (c.backgroundColor !== 'rgba(0, 0, 0, 0)' && c.backgroundColor !== 'transparent'); };
  const корень = h.closest('main, .v2-page-wrap, .ens-headwrap') ? document.querySelector('.v2-shell-main') : document.body;
  const блоки = [];
  for (const e of корень.querySelectorAll('*')) {
    if (h.contains(e) || e.closest('.v2-top, .v2-side, footer, .site-footer, .modal-ov, .v2-assist-dock, [role=dialog]')) continue;
    const b = R(e);
    if (b.width < 120 || b.height < 24 || b.top < hb.bottom - 1) continue;
    if (getComputedStyle(e).position === 'fixed') continue;
    if (!вид(e) || !блок(e)) continue;
    let п = e.parentElement, внешний = true;
    while (п && п !== корень) { const pb = R(п);
      if (!h.contains(п) && pb.top >= hb.bottom - 1 && pb.width >= 120 && вид(п) && блок(п)) { внешний = false; break; }
      п = п.parentElement; }
    if (внешний) блоки.push([b.left, b.right, (e.className || e.tagName).toString().slice(0, 30)]);
  }
  if (блоки.length) {
    out.содержимое = [Math.min(...блоки.map(x => x[0])), Math.max(...блоки.map(x => x[1]))];
    out.левый_блок = блоки.reduce((a, x) => x[0] < a[0] ? x : a)[2];
  }
  return out;
}"""

ГЛУШИТЕЛЬ = """addEventListener('DOMContentLoaded', () => { const s = document.createElement('style');
  s.textContent = '*, *::before, *::after { transition: none !important; animation: none !important; }';
  document.head.appendChild(s); });"""


def _стиль(css):
    return """addEventListener('DOMContentLoaded', () => { const s = document.createElement('style');
      s.textContent = %r; document.head.appendChild(s); });""" % css


def замер(подлог=None, ширины=ШИРИНЫ, экраны=None):
    from playwright.sync_api import sync_playwright
    import browser_window  # noqa: F401  окно — на втором мониторе
    итог = []
    with sync_playwright() as p:
        бр = p.chromium.launch(headless=False)
        try:
            for ш in ширины:
                ctx = бр.new_context(viewport={"width": ш, "height": 900},
                                     has_touch=ш < 500, is_mobile=False)
                стр = ctx.new_page()
                стр.add_init_script(ГЛУШИТЕЛЬ)
                if подлог:
                    стр.add_init_script(подлог)
                ch._войти(стр)
                for путь, имя, открыть in (экраны or ЭКРАНЫ):
                    стр.goto(ch.БАЗА + путь, wait_until="networkidle", timeout=45000)
                    if открыть:
                        стр.evaluate("() => { %s }" % открыть)
                    стр.wait_for_timeout(700)
                    итог.append((ш, имя, стр.evaluate(ЗАМЕР)))
                ctx.close()
        finally:
            бр.close()
    return итог


def _разборы(з):
    """[(вид, значение, в_норме)] по одному замеру."""
    р = []
    if not з.get("шапки"):
        return р
    if "центр_кнопок" in з and з.get("кнопки_рядом"):
        д = abs(з["центр_кнопок"] - з["центр_h1"])
        р.append(("центр", д, д <= 2))
    if "центр_кнопок" in з:
        р.append(("наложение", 1 if з.get("налезают") else 0, not з.get("налезают")))
    if "содержимое" in з:
        л = abs(з["шапка"][0] - з["содержимое"][0])
        п = abs(з["шапка"][1] - з["содержимое"][1])
        р.append(("края_шапки", max(л, п), max(л, п) <= 1))
        if "вкладки" in з:
            лв = abs(з["вкладки"][0] - з["содержимое"][0])
            пв = abs(з["вкладки"][1] - з["содержимое"][1])
            р.append(("края_вкладок", max(лв, пв), max(лв, пв) <= 1))
    return р


def _печать(итог):
    print("  %-5s %-26s %8s %14s %14s" % ("шир", "экран", "центр", "шапка л/п", "вкладки л/п"))
    for ш, имя, з in итог:
        if not з.get("шапки"):
            print("  %-5d %-26s  нет шапки" % (ш, имя))
            continue
        ц = ("нет кнопок" if "центр_кнопок" not in з else
             "%.1f" % abs(з["центр_кнопок"] - з["центр_h1"]) if з.get("кнопки_рядом") else "под текстом")
        if "содержимое" in з:
            с = з["содержимое"]
            шп = "%.1f/%.1f" % (з["шапка"][0] - с[0], з["шапка"][1] - с[1])
            вк = ("%.1f/%.1f" % (з["вкладки"][0] - с[0], з["вкладки"][1] - с[1])) if "вкладки" in з else "—"
        else:
            шп = вк = "нет содержимого"
        if з.get("налезают"):
            ц += " НАЛЕЗ"
        print("  %-5d %-26s %8s %14s %14s" % (ш, имя, ц, шп, вк))


находок = 0
_строки = {}


def проверка(подлог=None, печать=True):
    global находок
    находок = 0
    _строки.clear()
    итог = замер(подлог)
    if печать:
        _печать(итог)
    с_шапкой = [з for _, _, з in итог if з.get("шапки")]
    if not с_шапкой:
        print("  ПРОПУСК  шапки v2 нет ни на одном экране")
        return None
    for вид, строка in (("центр", "центр-кнопок-на-центре-h1"),
                        ("наложение", "кнопки-не-налезают-на-h1"),
                        ("края_шапки", "края-шапки-равны-содержимому"),
                        ("края_вкладок", "края-вкладок-равны-содержимому")):
        замеры = [(ш, имя, р) for ш, имя, з in итог for р in _разборы(з) if р[0] == вид]
        плохие = [(ш, имя, р[1]) for ш, имя, р in замеры if not р[2]]
        if not замеры:
            исход = "ПРОПУСК"
        elif плохие:
            исход = "ПЛОХО"
            находок += 1
        else:
            исход = "ok"
        _строки[строка] = исход
        худ = max((р[1] for _, _, р in замеры), default=0)
        print("  %-8s %s — замеров %d, худшее %.1f px%s" % (
            исход, строка, len(замеры), худ,
            ("; " + ", ".join("%d %s %.1f" % x for x in плохие[:4])) if плохие else ""))
    return находок


ПОДЛОГИ = [
    ("кнопки к верху шапки", "центр-кнопок-на-центре-h1",
     _стиль(".v2-page-head .v2-head-actions { align-self: start !important; grid-row: 1 !important; }"
            ".v2-page-head { align-items: flex-start !important; }")),
    # шапка шире колонки на 18 px с каждой стороны — ровно жалоба владельца
    ("шапка шире колонки на 18 px", "края-шапки-равны-содержимому",
     _стиль(".v2-page-head.is-page { margin-inline: -18px !important; }")),
]


def контроль():
    print("ЧИСТЫЙ ПРОГОН")
    if проверка(печать=False):
        print("КОНТРОЛЬ НЕДЕЙСТВИТЕЛЕН: грязная основа")
        return 2
    не_найдено = 0
    for имя, строка, код in ПОДЛОГИ:
        print("ПОДЛОГ: %s" % имя)
        проверка(код, печать=False)
        упала = _строки.get(строка) == "ПЛОХО"
        print("  → %s строку «%s»" % ("НАЙДЕН, уронил" if упала else "НЕ НАЙДЕН", строка))
        не_найдено += not упала
    print("КОНТРОЛЬ: подлогов %d, не найдено %d" % (len(ПОДЛОГИ), не_найдено))
    return 1 if не_найдено else 0


def main():
    if "--замер" in sys.argv:
        _печать(замер())
        sys.exit(0)
    if "--контроль" in sys.argv:
        sys.exit(контроль())
    print("ШАПКА ИНСТРУМЕНТА v2: центр кнопок и края")
    н = проверка()
    if н is None:
        sys.exit(2)
    print("ИТОГ: находок %d" % н)
    sys.exit(1 if н else 0)


if __name__ == "__main__":
    main()
