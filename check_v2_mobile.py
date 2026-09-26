"""ПРОВЕРКА 69: ОБОЛОЧКА v2 НА ТЕЛЕФОНЕ (№352, письмо «мобильный-1», блок 2).

Спрашивает на 360, 390 и 430 (эмуляция телефона с сенсором) по всем
экранам оболочки, КРОМЕ тренировок (они уйдут в свой редизайн, письмо
их не трогает — числа по ним печатаются справкой и в код не идут):

  1. ЩЕЛИ НАД ШАПКОЙ НЕТ — верх шапки инструмента совпадает с низом
     верхней полосы (`.v2-top-bar`) ±1 px. Мерится ЖИВАЯ полоса, а не
     токен: разойдись они, сверка печатала бы «совпало» про щель.
  2. ОДИН БОКОВОЙ ОТСТУП — левый и правый отступ у шапки, группы кнопок,
     вкладок, ряда чипов, карточек и списка: у каждого ряда |Л − П| ≤ 1
     и у всех рядов экрана один и тот же левый отступ ±1.
  3. НИЧТО НЕ ШИРЕ ЭКРАНА — видимых элементов, вылезающих за окно, 0
     (элемент внутри своей прокрутки вбок законно обрезан и не считается);
     горизонтальной прокрутки у страницы нет. Отдельным проходом —
     СООБЩЕНИЯ: тосты и предупреждения поднимаются настоящим кодом
     страницы (успех, ошибка, предупреждение) с длинным текстом.
  4. ТЕКСТ НЕ ВЫЛЕЗАЕТ ЗА СВОЮ КАРТОЧКУ — посимвольный `Range` текстового
     узла против ближайшего предка с рамкой либо фоном.
  5. ГРУППЫ КНОПОК ОДНОЙ ШИРИНЫ — разброс ширин в объявленной группе
     ≤ 1 px; КРЕСТИКИ КРУГЛЫЕ — ширина равна высоте ±1.
  6. ОКНО ОТКРЫТО — ФОН СТОИТ: окно открывается НАЖАТИЕМ, внутри окна
     крутится колесо (как рука), положение страницы сверяется до,
     во время и после закрытия.

Браузер ВИДИМЫЙ (§6.0.3): меряются ширины и полоса прокрутки. В базу
не пишет.

  --замер     таблица чисел без вердикта (код 0) — замер «до/после»
  --контроль  подлоги №2 (элемент шире экрана) и №3 (прокрутка фона)
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

ШИРИНЫ = (360, 390, 430)

# (путь, имя, чем открыть раздел — селектор кнопки, по которой жмём)
ЭКРАНЫ = [
    ("/hh", "hh · письмо", None),
    ("/hh", "hh · история", ".v2-tab[data-view=history]"),
    ("/hh", "hh · досье", ".v2-tab[data-view=dossier]"),
    ("/hh", "hh · резюме", ".v2-tab[data-view=resume]"),
    ("/nutrition", "питание · дневник", None),
    ("/nutrition", "питание · история", ".v2-tab[data-tab=history]"),
    ("/nutrition", "питание · вес", ".v2-tab[data-tab=weight]"),
    ("/nutrition", "питание · профиль", ".v2-tab[data-tab=profile]"),
    ("/medkit", "аптечка · лекарства", None),
    ("/medkit", "аптечка · купить", ".v2-tab[data-tab=buy]"),
    ("/medkit", "аптечка · лента", ".v2-tab[data-tab=feed]"),
    ("/enshrouded", "enshrouded", None),
    ("/", "главная", None),
    ("/profile", "профиль", None),
    ("/admin/users", "админ · пользователи", None),
    ("/admin/products", "админ · продукты", None),
    ("/admin/exercises", "админ · упражнения", None),
    ("/admin/enshrouded", "админ · enshrouded", None),
    ("/admin/usage", "админ · расход", None),
    # справкой: тренировки письмо не трогает
    ("/workout", "тренировки · программа", None),
    ("/workout/profile", "тренировки · профиль", None),
]
СПРАВКОЙ = ("тренировки",)

ГЛУШИТЕЛЬ = """addEventListener('DOMContentLoaded', () => { const s = document.createElement('style');
  s.textContent = '*, *::before, *::after { transition: none !important; animation: none !important; }';
  document.head.appendChild(s); });"""

ЗАМЕР = r"""() => {
  const W = document.documentElement.clientWidth;
  const R = e => e.getBoundingClientRect();
  const вид = e => { if (!e.checkVisibility({opacityProperty: true, visibilityProperty: true})) return false;
    const b = R(e); return b.width > 0 && b.height > 0; };
  const имя = e => (e.id ? '#' + e.id : '') + '.' + String(e.className && e.className.baseVal !== undefined
    ? e.className.baseVal : e.className || e.tagName).trim().split(/\s+/).slice(0, 2).join('.');
  const чужое = e => e.closest('.v2-top, .v2-top-bar, .site-header, .v2-side, .v2-side-scrim, footer, .site-footer, .modal-ov:not(.open), [hidden]');
  // ЗАКОННО ТОЛЬКО В СВОЕЙ ПРОКРУТКЕ ВБОК (лента вкладок, таблица
  // в обёртке): до края там дотягивается палец. Срез краем `hidden` /
  // `clip` — НЕ законно: каркас держит `overflow-x: clip` (под свечение
  // шапки), и элемент шире окна под ним просто теряет край молча —
  // подлог №2 первой версии это и показал (заголовок в 140vw — 0 находок)
  const обрезан = e => { let п = e.parentElement;
    while (п && п !== document.body && п !== document.documentElement) {
      const c = getComputedStyle(п);
      if ((c.overflowX === 'auto' || c.overflowX === 'scroll') && п.scrollWidth > п.clientWidth + 1) return true;
      п = п.parentElement; }
    return false; };
  const out = {W, прокрутка: document.documentElement.scrollWidth - document.documentElement.clientWidth,
               шире: [], края: [], текст: []};
  // 1. щель над шапкой
  const top = [...document.querySelectorAll('.v2-top-bar, .site-header')].find(вид);
  const h = [...document.querySelectorAll('.v2-page-head')].find(вид);
  if (top && h) out.щель = Math.round((R(h).top - R(top).bottom) * 10) / 10;
  // 3. шире экрана
  for (const e of document.body.querySelectorAll('*')) {
    if (чужое(e) || !вид(e)) continue;
    const b = R(e);
    if (b.left < -1 || b.right > W + 1) { if (обрезан(e)) continue;
      // объявленное многоточие — законный срез (бренд в строке еды)
      let мн = false, а = e; while (а && а !== document.body) {
        if (getComputedStyle(а).textOverflow === 'ellipsis') { мн = true; break; } а = а.parentElement; }
      if (мн) continue;
      out.шире.push([имя(e), Math.round(b.left), Math.round(b.right)]); }
  }
  // 2. края рядов: ряд = контейнер, края = крайние видимые дети либо сама коробка
  const ряды = [];
  const добавить = (кат, e, по_детям) => {
    if (!e || чужое(e) || !вид(e)) return;
    let л, п; const b = R(e), c = getComputedStyle(e);
    if (по_детям) { const д = [...e.children].filter(вид);
      if (!д.length) return;
      л = Math.min(...д.map(x => R(x).left)); п = Math.max(...д.map(x => R(x).right));
    } else if (кат === 'шапка') { л = b.left + parseFloat(c.paddingLeft); п = b.right - parseFloat(c.paddingRight); }
    else { л = b.left; п = b.right; }
    ряды.push([кат, имя(e), Math.round(л * 10) / 10, Math.round((W - п) * 10) / 10]);
  };
  if (h) добавить('шапка', h, false);
  document.querySelectorAll('.v2-head-actions').forEach(e => добавить('кнопки', e, true));
  document.querySelectorAll('.v2-tabs').forEach(e => { if (getComputedStyle(e).position !== 'fixed') добавить('вкладки', e, false); });
  const чипряды = new Set();
  const блок = e => { const c = getComputedStyle(e);
    return (parseFloat(c.borderLeftWidth) > 0 && c.borderLeftStyle !== 'none')
        || (c.backgroundColor !== 'rgba(0, 0, 0, 0)' && c.backgroundColor !== 'transparent'); };
  const корень = document.querySelector('.v2-shell-main') || document.body;
  // ряд чипов — только ВНЕ карточки: внутри неё отступ задаёт поле
  // карточки, и это законно (замер «до»: навыки резюме 33 при 16)
  const в_блоке = e => { let п = e.parentElement;
    // фон ВО ВСЮ ШИРИНУ — фон страницы (`.v2-shell`), а не карточка
    while (п && п !== корень) { if (блок(п) && getComputedStyle(п).position !== 'fixed'
                                    && R(п).width < W - 2) return true; п = п.parentElement; }
    return false; };
  document.querySelectorAll('.v2-chip, .chip').forEach(e => {
    if (вид(e) && !e.closest('.modal-ov') && !в_блоке(e.parentElement)) чипряды.add(e.parentElement); });
  чипряды.forEach(e => добавить('чипы', e, false));
  // карточки и списки: самые внешние видимые блоки с рамкой либо фоном ниже шапки
  const hb = h ? R(h).bottom : 0;
  for (const e of корень.querySelectorAll('*')) {
    if (чужое(e) || (h && h.contains(e)) || e.closest('.modal-ov, [role=dialog], .v2-assist-dock')) continue;
    const c = getComputedStyle(e); if (c.position === 'fixed' || c.position === 'absolute') continue;
    const b = R(e);
    if (b.width < W * 0.5 || b.height < 24 || b.top < hb - 1) continue;
    if (!вид(e) || !блок(e)) continue;
    let п = e.parentElement, внешний = true;
    while (п && п !== корень) { const pb = R(п);
      if (pb.top >= hb - 1 && pb.width >= W * 0.5 && вид(п) && блок(п) && getComputedStyle(п).position !== 'fixed') { внешний = false; break; }
      п = п.parentElement; }
    if (!внешний) continue;
    // поле в ряду с кнопкой — ряд целиком: правый край поля законно
    // отстоит на ширину кнопки (замер «Купить» на 430: П161 у поля)
    const род = e.parentElement, рс = род ? getComputedStyle(род) : null;
    if (рс && (рс.display === 'flex' || рс.display === 'grid') && [...род.children].filter(вид).length > 1)
      добавить('ряды', род, true);
    else добавить('карточки', e, false);
  }
  out.края = ряды;
  // 4. текст за пределами своей карточки
  const tw = document.createTreeWalker(корень, NodeFilter.SHOW_TEXT);
  let n;
  while ((n = tw.nextNode())) {
    if (!n.data.trim()) continue;
    // ОБРЕЗАННЫЙ ТЕКСТ — ТОЖЕ НАХОДКА (строка, срезанная краем карточки,
    // не прочитается), кроме объявленного многоточия
    const e = n.parentElement; if (!e || чужое(e) || !вид(e)) continue;
    // законно: объявленное многоточие у самого узла либо предка и своя
    // прокрутка вбок (лента вкладок, таблица в обёртке)
    let законно = false, а = e;
    while (а && а !== корень) { const c = getComputedStyle(а);
      if (c.textOverflow === 'ellipsis' || c.overflowX === 'auto' || c.overflowX === 'scroll') { законно = true; break; }
      а = а.parentElement; }
    if (законно) continue;
    let к = e; while (к && к !== корень && !блок(к)) к = к.parentElement;
    if (!к || к === корень) continue;
    const r = document.createRange(); r.selectNodeContents(n);
    const tb = r.getBoundingClientRect(), kb = R(к);
    if (tb.width < 1) continue;
    if (tb.right > kb.right + 1 || tb.left < kb.left - 1)
      out.текст.push([имя(e), n.data.trim().slice(0, 24), Math.round(tb.right - kb.right)]);
  }
  return out;
}"""


def _сессия(p, ш):
    ctx = p.new_context(viewport={"width": ш, "height": 800}, has_touch=True,
                        is_mobile=False, device_scale_factor=2)
    стр = ctx.new_page()
    стр.add_init_script(ГЛУШИТЕЛЬ)
    return ctx, стр


def открыть(стр, путь, кнопка):
    стр.goto(ch.БАЗА + путь, wait_until="networkidle", timeout=45000)
    if кнопка:
        эл = стр.locator(кнопка).first
        if эл.count() and эл.is_visible():
            эл.click()
        else:
            return False
    стр.wait_for_timeout(500)
    return True


def замер(подлог=None, ширины=ШИРИНЫ, экраны=None):
    from playwright.sync_api import sync_playwright
    import browser_window  # noqa: F401  окно — на втором мониторе
    итог = []
    with sync_playwright() as p:
        бр = p.chromium.launch(headless=False)
        try:
            for ш in ширины:
                ctx, стр = _сессия(бр, ш)
                if подлог:
                    стр.add_init_script(подлог)
                ch._войти(стр)
                for путь, имя, кнопка in (экраны or ЭКРАНЫ):
                    if not открыть(стр, путь, кнопка):
                        итог.append((ш, имя, None))
                        continue
                    итог.append((ш, имя, стр.evaluate(ЗАМЕР)))
                ctx.close()
        finally:
            бр.close()
    return итог


def _разброс(края):
    """Разбор краёв экрана: худшая асимметрия ряда и разброс левых отступов."""
    if not края:
        return None, None, []
    асим = max(края, key=lambda x: abs(x[2] - x[3]))
    левые = [x[2] for x in края]
    return abs(асим[2] - асим[3]), max(левые) - min(левые), асим


def печать_замера(итог):
    print("%-4s %-26s %6s %5s %5s %6s %6s %s" % ("шир", "экран", "щель", "шире", "текст", "|Л−П|", "ΔЛ", "худший ряд"))
    for ш, имя, з in итог:
        if з is None:
            print("%-4d %-26s раздел не открылся" % (ш, имя))
            continue
        асим, дл, худ = _разброс(з["края"])
        print("%-4d %-26s %6s %5d %5d %6s %6s %s" % (
            ш, имя, з.get("щель", "—"), len(з["шире"]), len(з["текст"]),
            "—" if асим is None else "%.1f" % асим, "—" if дл is None else "%.1f" % дл,
            "" if not худ else "%s %s Л%.1f П%.1f" % (худ[0], худ[1][:22], худ[2], худ[3])))
        if з["прокрутка"] > 0:
            print("       прокрутка вбок %d px" % з["прокрутка"])
        for эл in з["шире"][:3]:
            print("       шире: %s [%d, %d]" % tuple(эл))
        for эл in з["текст"][:3]:
            print("       текст: %s «%s» +%d" % tuple(эл))


ДЛИННОЕ = ("Не удалось сохранить изменения: сервер ответил ошибкой, "
           "проверьте соединение и попробуйте ещё раз через минуту")

# СООБЩЕНИЯ: поднимаются кодом самой страницы (успех, ошибка,
# предупреждение) с длинным текстом, затем — тот же замер ширины.
# (путь, имя, раздел, вызовы). Предупреждения-плашки (`.alert`,
# `.v2-alert`), спрятанные атрибутом, раскрываются с тем же текстом.
СООБЩЕНИЯ = [
    ("/hh", "hh · тост", None, ["showToast(Д)"]),
    ("/nutrition", "питание · тост успех", None, ["toast(Д, true)"]),
    ("/nutrition", "питание · тост ошибка", None, ["toast(Д, false)"]),
    ("/medkit", "аптечка · полоса отмены", None,
     ["(() => { const u = document.getElementById('undo-bar'); "
      "document.getElementById('undo-bar-text').textContent = Д; u.classList.add('show'); })()"]),
]
ПЛАШКИ = r"""(Д) => { let n = 0;
  document.querySelectorAll('.alert, .v2-alert, [role=alert]').forEach(e => {
    if (e.closest('.modal-ov:not(.open), template')) return;
    e.hidden = false; e.style.display = ''; e.textContent = Д; n++; });
  return n; }"""

# ГРУППЫ КНОПОК ОДНОЙ ШИРИНЫ (2.5): (путь, имя, чем открыть, родитель, дети)
ГРУППЫ = [
    ("/nutrition", "питание · кнопки шапки", None, ".v2-head-fill", ".v2-btn"),
    ("/medkit", "аптечка · кнопки шапки", None, ".apt-head-main", ".v2-btn"),
    ("/enshrouded", "enshrouded · счётчики", None, ".ens-stats", ".ens-stat"),
    ("/hh", "hh · резюме: загрузка и досье", ".v2-tab[data-view=resume]", ".upload-row", ".v2-btn"),
    ("/medkit", "аптечка · участник: роль и выход", "#apt-circle-open", ".apt-person", ".apt-role, .v2-btn"),
]
ГРУППА = r"""([родитель, дети]) => {
  const вид = e => e.checkVisibility({opacityProperty: true, visibilityProperty: true}) && e.getBoundingClientRect().width > 0;
  const out = [];
  const сел = дети.split(',').map(x => ':scope > ' + x.trim()).join(', ');
  document.querySelectorAll(родитель).forEach(п => { if (!вид(п)) return;
    const д = [...п.querySelectorAll(сел)].filter(вид)
      .map(e => Math.round(e.getBoundingClientRect().width * 10) / 10);
    if (д.length >= 2) out.push(д); });
  return out; }"""

# КРЕСТИКИ: кнопка, чьё видимое содержимое — один значок «x»
КРЕСТИКИ = r"""() => {
  const вид = e => e.checkVisibility({opacityProperty: true, visibilityProperty: true}) && e.getBoundingClientRect().width > 0;
  const out = [];
  document.querySelectorAll('button, [role=button]').forEach(к => {
    if (!вид(к)) return;
    const зн = к.querySelector('svg.lucide-x, [data-lucide=x]');
    if (!зн || к.textContent.trim()) return;
    const b = к.getBoundingClientRect();
    out.push([(к.id ? '#' + к.id : '') + '.' + String(к.className).trim().split(/\s+/).slice(0, 2).join('.'),
              Math.round(b.width * 10) / 10, Math.round(b.height * 10) / 10]); });
  return out; }"""
ЭКРАНЫ_КРЕСТИКОВ = [
    ("/hh", "hh", None), ("/hh", "hh · досье", ".v2-tab[data-view=dossier]"),
    ("/nutrition", "питание", None),
    ("/medkit", "аптечка", None),
    ("/medkit", "аптечка · общая аптечка", "#apt-circle-open"),
    ("/medkit", "аптечка · ассистент", "#apt-ai-open"),
    ("/medkit", "аптечка · перепроверить", "#apt-recheck-open"),
    ("/nutrition", "питание · ассистент", "#nut-assist-open"),
    ("/medkit", "аптечка · инструкция", "[data-doses]"),
]

# ОКНО ОТКРЫТО — ФОН СТОИТ (2.4): (путь, имя, чем открыть, что крутить)
ОКНА = [
    ("/medkit", "аптечка · инструкция", "[data-doses]", "#apt-drug"),
    ("/medkit", "аптечка · ассистент", "#apt-ai-open", "#apt-ai"),
    ("/medkit", "аптечка · перепроверить", "#apt-recheck-open", "#apt-recheck-panel"),
    ("/medkit", "аптечка · общая аптечка", "#apt-circle-open", "#apt-circle .modal-sh"),
    ("/nutrition", "питание · ассистент", "#nut-assist-open", "#nut-assist"),
]

ПОДЛОГ_ШИРЕ = """addEventListener('DOMContentLoaded', () => { const s = document.createElement('style');
  s.textContent = '.v2-head-title { width: 140vw !important; }';
  document.head.appendChild(s); });"""
ПОДЛОГ_ФОН = """addEventListener('DOMContentLoaded', () => { const s = document.createElement('style');
  s.textContent = 'html, body { overflow: visible !important; overflow-y: auto !important; } [data-panel] *, .modal-ov * { overscroll-behavior: auto !important; }';
  document.head.appendChild(s); });"""

_шаги = []


def шаг(имя, ок, подробно="", собрано=None):
    исход = "ПРОПУСК" if собрано == 0 else ("OK" if ок else "ПЛОХО")
    _шаги.append((имя, исход))
    print("  %-6s %-52s %s" % (исход, имя, подробно))


def _жать(стр, сел):
    эл = стр.locator(сел).filter(visible=True).first
    if not эл.count():
        return False
    эл.scroll_into_view_if_needed()
    эл.click(timeout=5000)
    стр.wait_for_timeout(500)
    return True


def _экраны(стр, ш):
    for путь, имя, кнопка in ЭКРАНЫ:
        справка = any(имя.startswith(x) for x in СПРАВКОЙ)
        if not открыть(стр, путь, кнопка):
            шаг("%d %s: раздел открылся" % (ш, имя), False, "кнопки нет")
            continue
        з = стр.evaluate(ЗАМЕР)
        асим, дл, худ = _разброс(з["края"])
        if справка:
            print("  справка %s: щель %s, шире %d, |Л−П| %s" % (имя, з.get("щель"), len(з["шире"]), асим))
            continue
        if "щель" in з:
            шаг("%d %s: шапка вплотную к верхней полосе" % (ш, имя),
                abs(з["щель"]) <= 1, "щель %s px" % з["щель"])
        # края: у каждого ряда |Л−П| ≤ 1, левый отступ один на экран ±1
        # (ряд во всю ширину 0/0 — полоса, законно)
        ряды = [x for x in з["края"] if not (x[2] <= 0.5 and x[3] <= 0.5)]
        плохие = [x for x in ряды if abs(x[2] - x[3]) > 1]
        левые = sorted(set(x[2] for x in ряды))
        # и ОДИН НА ВСЕ ЭКРАНЫ: `--v2-gutter-sm` (16) — поле колонки
        # каркаса; внутри карточек ряды законно глубже и сюда не входят
        шаг("%d %s: один боковой отступ" % (ш, имя),
            not плохие and (not левые or (левые[-1] - левые[0] <= 1 and abs(левые[0] - 16) <= 1)),
            "рядов %d, левые %s%s" % (len(ряды), левые[:4],
                                       "; несимметричны: " + ", ".join(
                                           "%s %s Л%s П%s" % tuple(x) for x in плохие[:2]) if плохие else ""),
            собрано=len(ряды))
        шаг("%d %s: ничто не шире экрана" % (ш, имя),
            not з["шире"] and з["прокрутка"] <= 0,
            "шире %d, прокрутка %d %s" % (len(з["шире"]), з["прокрутка"], з["шире"][:2]))
        шаг("%d %s: текст внутри карточек" % (ш, имя), not з["текст"],
            "вылезло %d %s" % (len(з["текст"]), з["текст"][:2]))


def _сообщения(стр, ш):
    for путь, имя, кнопка, вызовы in СООБЩЕНИЯ:
        открыть(стр, путь, кнопка)
        for в in вызовы:
            стр.evaluate("(Д) => { %s }" % в, ДЛИННОЕ)
        n = стр.evaluate(ПЛАШКИ, ДЛИННОЕ)
        стр.wait_for_timeout(400)
        з = стр.evaluate(ЗАМЕР)
        шаг("%d %s: сообщение не шире экрана" % (ш, имя),
            not з["шире"] and з["прокрутка"] <= 0,
            "вызовов %d, плашек %d, шире %d %s" % (len(вызовы), n, len(з["шире"]), з["шире"][:2]),
            собрано=len(вызовы) + n)


def _группы(стр, ш):
    for путь, имя, кнопка, род, дети in ГРУППЫ:
        открыть(стр, путь, None)
        if кнопка and not _жать(стр, кнопка):
            шаг("%d %s: одной ширины" % (ш, имя), False, "не открылось", собрано=0)
            continue
        гр = стр.evaluate(ГРУППА, [род, дети])
        разброс = max((max(г) - min(г) for г in гр), default=0)
        шаг("%d %s: одной ширины" % (ш, имя), разброс <= 1,
            "групп %d, ширины %s, разброс %.1f" % (len(гр), гр[:2], разброс), собрано=len(гр))
    for путь, имя, кнопка in ЭКРАНЫ_КРЕСТИКОВ:
        открыть(стр, путь, None)
        if кнопка and not _жать(стр, кнопка):
            шаг("%d %s: крестики круглые" % (ш, имя), False, "не открылось", собрано=0)
            continue
        кр = стр.evaluate(КРЕСТИКИ)
        овал = [к for к in кр if abs(к[1] - к[2]) > 1]
        шаг("%d %s: крестики круглые" % (ш, имя), not овал,
            "крестиков %d, овальных %d %s" % (len(кр), len(овал), овал[:2]), собрано=len(кр))


def _окна(стр, ш):
    for путь, имя, кнопка, окно in ОКНА:
        открыть(стр, путь, None)
        # страница — вниз колесом, как рукой; затем открыватель в окно,
        # чтобы нажатие не прокручивало страницу само (иначе «до» и
        # «открыто» разошлись бы по вине пробы, а не окна)
        стр.mouse.move(ш / 2, 400)
        стр.mouse.wheel(0, 120)
        стр.wait_for_timeout(300)
        эл = стр.locator(кнопка).filter(visible=True).first
        if not эл.count():
            шаг("%d %s: фон стоит" % (ш, имя), False, "открыть нечем", собрано=0)
            continue
        эл.scroll_into_view_if_needed()
        стр.wait_for_timeout(300)
        y1 = стр.evaluate("scrollY")
        эл.click(timeout=5000)
        стр.wait_for_timeout(600)
        y_откр = стр.evaluate("scrollY")
        бокс = стр.locator(окно).first.bounding_box()
        if not бокс:
            шаг("%d %s: фон стоит" % (ш, имя), False, "окно не открылось", собрано=0)
            continue
        стр.mouse.move(бокс["x"] + бокс["width"] / 2, бокс["y"] + бокс["height"] / 2)
        for _ in range(4):
            стр.mouse.wheel(0, 1500)
            стр.wait_for_timeout(120)
        y2 = стр.evaluate("scrollY")
        стр.keyboard.press("Escape")
        стр.wait_for_timeout(500)
        y3 = стр.evaluate("scrollY")
        шаг("%d %s: фон стоит, положение сохранено" % (ш, имя),
            abs(y1 - y2) <= 1 and abs(y1 - y3) <= 1 and y1 > 0,
            "до %d, открыто %d, после прокрутки в окне %d, после закрытия %d" % (y1, y_откр, y2, y3))


def проверка(подлог=None, печать=True, только=None):
    from playwright.sync_api import sync_playwright
    import browser_window  # noqa: F401  окно — на втором мониторе
    _шаги.clear()
    with sync_playwright() as p:
        бр = p.chromium.launch(headless=False)
        try:
            for ш in ШИРИНЫ:
                ctx, стр = _сессия(бр, ш)
                if подлог:
                    стр.add_init_script(подлог)
                ch._войти(стр)
                print("\n── ширина %d ──" % ш)
                if только in (None, "экраны"):
                    _экраны(стр, ш)
                if только in (None, "сообщения"):
                    _сообщения(стр, ш)
                if только in (None, "группы"):
                    _группы(стр, ш)
                if только in (None, "окна"):
                    _окна(стр, ш)
                ctx.close()
        finally:
            бр.close()
    плохих = sum(1 for _, и in _шаги if и == "ПЛОХО")
    пропусков = sum(1 for _, и in _шаги if и == "ПРОПУСК")
    if печать:
        print("\nИТОГ: шагов %d, плохих %d, пропусков %d" % (len(_шаги), плохих, пропусков))
    return плохих, пропусков


def контроль():
    print("ЧИСТЫЙ ПРОГОН")
    плохих, _ = проверка(печать=False)
    if плохих:
        print("КОНТРОЛЬ НЕДЕЙСТВИТЕЛЕН: грязная основа (%d плохих)" % плохих)
        return 2
    итог = []
    for имя, код, раздел, признак in (
            ("№2: заголовок шире экрана", ПОДЛОГ_ШИРЕ, "экраны", "ничто не шире экрана"),
            ("№3: прокрутка фона разрешена", ПОДЛОГ_ФОН, "окна", "фон стоит")):
        print("\nПОДЛОГ %s" % имя)
        проверка(код, печать=False, только=раздел)
        упало = [и for и, х in _шаги if х == "ПЛОХО" and признак in и]
        print("  упало шагов «%s»: %d" % (признак, len(упало)))
        итог.append(len(упало) > 0)
    print("\nКОНТРОЛЬ: %s" % ("ОБА ПОДЛОГА НАЙДЕНЫ" if all(итог) else "ЕСТЬ НЕНАЙДЕННЫЕ"))
    return 0 if all(итог) else 1


def main():
    if "--замер" in sys.argv:
        печать_замера(замер())
        sys.exit(0)
    if "--контроль" in sys.argv:
        sys.exit(контроль())
    только = None
    for к in ("экраны", "сообщения", "группы", "окна"):
        if "--" + к in sys.argv:
            только = к
    print("ОБОЛОЧКА v2 НА ТЕЛЕФОНЕ")
    плохих, пропусков = проверка(только=только)
    sys.exit(1 if плохих else 0)


if __name__ == "__main__":
    main()
