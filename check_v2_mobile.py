"""ПРОВЕРКА 69: ОБОЛОЧКА v2 НА ТЕЛЕФОНЕ (№352, письмо «мобильный-1», блок 2).

Спрашивает на 360, 390 и 430 (эмуляция телефона с сенсором) по всем
экранам оболочки, КРОМЕ тренировок (они уйдут в свой редизайн, письмо
их не трогает — числа по ним печатаются справкой и в код не идут):

  1. ЩЕЛИ НАД ШАПКОЙ НЕТ — верх шапки инструмента совпадает с низом
     верхней полосы (`.v2-top-bar`) ±1 px. Мерится ЖИВАЯ полоса, а не
     токен: разойдись они, сверка печатала бы «совпало» про щель.
     На страницах админки под верхней полосой законно стоит панель
     разделов (`.admin-nav-bar`) — щель мерится от НИЖНЕЙ из полос.
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
  7. ПОЛОСЫ НЕ ПРОСВЕЧИВАЮТ (письмо «мобильный-2», блок 1): у верхней
     полосы и у нижней панели разделов альфа фона равна 1, а ПИКСЕЛИ
     полос вверху страницы и после прокрутки колесом на 2000 px одни
     и те же (допуск на сглаживание — `ПОРОГ_КАНАЛА`, `ДОЛЯ_ПИКСЕЛЕЙ`).
     Альфа сама по себе не доказывает ничего: полосу, ушедшую ПОД
     содержимое по слою, непрозрачный фон не спасает — это видит только
     снимок.

Браузер ВИДИМЫЙ (§6.0.3): меряются ширины и полоса прокрутки. В базу
не пишет.

  8. ПРАВКИ «МОБИЛЬНОГО-2» (блок 2) — окна и панели, которые письмо
     трогало: ничто не шире окна (и тело окна не листается вбок, если
     оно не лента), моноширинных нет, боковые отступы одинаковые — от
     края области содержимого, без резерва под полосу прокрутки
     (на телефоне полосы накладные). Плюс по пунктам: категории формы
     рядами без прокрутки вбок, подвал формы по правилам v2 от края
     до края ±1, подчёркивание вкладки «Общей аптечки» цветом
     инструмента, рамка микрофона как у скрепки и штрихкода, плавный
     переход под прилипшей полосой Enshrouded (прокрутка колесом туда
     и обратно, пиксели у края перехода — фон страницы ±8), поле уровня
     предмета не ближе 16 px к низу окна.

  --замер     таблица чисел без вердикта (код 0) — замер «до/после»
  --полосы    только вопрос 7 (так же `--экраны`, `--сообщения`,
              `--правки`, …)
  --контроль  подлоги №2 (элемент шире экрана) и №3 (прокрутка фона),
              «мобильный-2» №1 (полосы полупрозрачны) и №3 (категории
              формы лентой — доказательство `flex-wrap`), «Расход» —
              щель 32 px под панелью разделов админки (доказательство —
              расстояние «панель → шапка» отдельным замером); с ключом
              раздела — только чистый проход раздела и его подлог
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
  // 1. щель над шапкой — от НИЖНЕЙ из видимых полос каркаса над ней:
  // верхняя полоса и, на страницах админки, панель разделов (разбор
  // и четыре пункта §6.0.3 — у `ПОДЛОГ_ЩЕЛЬ`)
  const полосы = [...document.querySelectorAll('.v2-top-bar, .site-header, .admin-nav-bar')].filter(вид);
  const h = [...document.querySelectorAll('.v2-page-head')].find(вид);
  if (полосы.length && h) {
    const низ = Math.max(...полосы.map(e => R(e).bottom));
    out.щель = Math.round((R(h).top - низ) * 10) / 10;
    out.полоса = имя(полосы.find(e => R(e).bottom === низ));
  }
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
# ЩЕЛЬ ПОД ПАНЕЛЬЮ РАЗДЕЛОВ АДМИНКИ. ПЕРЕПИСАНО ЗАХОДОМ, КОТОРЫЙ ЧИНИЛ
# ПРОВЕРЯЕМОЕ (№352, письмо «Расход», добивание 2026-09-27), ЧЕТЫРЕ
# ПУНКТА §6.0.3:
#   · было: щель = верх `.v2-page-head` − низ ПЕРВОЙ видимой
#     `.v2-top-bar, .site-header`;
#   · стало: щель = верх `.v2-page-head` − низ САМОЙ НИЖНЕЙ из видимых
#     полос каркаса `.v2-top-bar, .site-header, .admin-nav-bar`;
#   · почему: страница «Расход» ушла на v2 и первой из админки получила
#     `.v2-page-head`, а над ней законно стоит панель разделов (липкая
#     под верхней полосой, одна на пять разделов). Прежняя формула
#     называла щелью её высоту — 70.6 px на 360/390/430 при 0 px между
#     панелью и шапкой (в невидимом браузере 60.6: в видимом у ленты
#     вкладок своя полоса прокрутки 10 px). На экранах инструментов
#     панели разделов нет — там формула прежняя;
#   · контроль на новой формулировке — этот подлог: 32 px между панелью
#     и шапкой ТОЛЬКО на странице админки. Шаг обязан упасть, а
#     доказательство — то же расстояние, снятое отдельным замером
#     (`_доказ["щель_панели"]`), а не формулой шага.
ПОДЛОГ_ЩЕЛЬ = """addEventListener('DOMContentLoaded', () => { const s = document.createElement('style');
  s.textContent = 'body:has(.admin-nav-bar) .v2-page-head { margin-top: 32px !important; }';
  document.head.appendChild(s); });"""

# 7. ПОЛОСЫ НЕ ПРОСВЕЧИВАЮТ: (путь, имя, чем открыть раздел). Раздел —
# самый длинный у инструмента: прокрутка на 2000 px обязана состояться
# (замер на 360: резюме HH 4169 px, дневник 2364, аптечка 18154,
# Enshrouded 39953). Enshrouded — экран БЕЗ нижней панели: верхняя
# полоса сверяется в одиночку.
ПОЛОСЫ = [
    ("/hh", "hh · резюме", ".v2-tab[data-view=resume]"),
    ("/nutrition", "питание · дневник", None),
    ("/medkit", "аптечка · лекарства", None),
    ("/enshrouded", "enshrouded", None),
]
С_ПАНЕЛЬЮ = ("hh", "питание", "аптечка")
ПРОКРУТКА_ПОЛОС = 2000
# ДОПУСК НА СГЛАЖИВАНИЕ. Пиксель изменился, если хоть один канал разошёлся
# больше чем на `ПОРОГ_КАНАЛА` из 255; полоса проходит, если таких пикселей
# не больше `ДОЛЯ_ПИКСЕЛЕЙ` её площади. Замер на исправном коде — 0 пикселей
# на всех 21 паре снимков (DPR 2); допуск оставлен на сглаживание краёв
# букв и значков, которое между двумя кадрами бывает, а нарушение
# с просвечивающей полосой даёт на порядки больше.
ПОРОГ_КАНАЛА = 8
ДОЛЯ_ПИКСЕЛЕЙ = 0.001

ПОЛОСЫ_ЗАМЕР = r"""() => {
  const вид = e => e && e.checkVisibility({opacityProperty: true, visibilityProperty: true})
    && e.getBoundingClientRect().height > 0;
  const альфа = c => { const m = c.match(/rgba?\(([^)]+)\)/); if (!m) return null;
    const ч = m[1].split(/[\s,\/]+/).filter(Boolean); return ч.length > 3 ? parseFloat(ч[3]) : 1; };
  const r = {y: scrollY, dpr: devicePixelRatio,
             макс: document.documentElement.scrollHeight - innerHeight};
  for (const [имя, сел] of [['верх', '.site-header.v2-top-bar'], ['низ', '.v2-tabs-dock']]) {
    const e = [...document.querySelectorAll(сел)].find(вид);
    if (!e) continue;
    const b = e.getBoundingClientRect(), c = getComputedStyle(e);
    r[имя] = {x: b.left, y: b.top, w: b.width, h: b.height, фон: c.backgroundColor,
              альфа: альфа(c.backgroundColor)};
  }
  return r;
}"""

# «мобильный-2» №1: полосам возвращён прежний полупрозрачный фон
# (шапка — `rgba(10,11,13,.7)` из style.css, панель — `--v2-surface-1`)
ПОДЛОГ_ПОЛОСЫ = """addEventListener('DOMContentLoaded', () => { const s = document.createElement('style');
  s.textContent = '.site-header.v2-top-bar { background: rgba(10, 11, 13, 0.7) !important; }'
    + ' .v2-tabs-dock { background: rgba(255, 255, 255, 0.02) !important; }';
  document.head.appendChild(s); });"""

# 8. ПРАВКИ «МОБИЛЬНОГО-2» (блок 2): окна и панели, которые письмо
# трогало. Перечень закрывает СЦЕНЫ («чем открыть»), а не множество
# элементов: какое нажатие открывает окно, из разметки не выводится
# (§6.0.7). (путь, имя, что нажать, корень окна для замера)
ПРАВКИ = [
    ("/medkit", "аптечка · правка", "[data-edit]", "#apt-form .modal-sh"),
    ("/medkit", "аптечка · общая", "#apt-circle-open", "#apt-circle .modal-sh"),
    ("/medkit", "аптечка · ассистент", "#apt-ai-open", "#apt-ai"),
    ("/nutrition", "питание · ассистент", "#nut-assist-open", "#nut-assist"),
    ("/nutrition", "питание · дневник", None, "#tab-diary"),
    ("/enshrouded", "enshrouded", None, "main.ens-main"),
    ("/enshrouded", "enshrouded · предмет", ".slot", "#ens-item .modal-sh"),
]

# ОКНО: моноширинные, «вбок» и боковые отступы. ОТСТУП СЧИТАЕТСЯ ОТ КРАЯ
# ОБЛАСТИ СОДЕРЖИМОГО — клиентской коробки ближайшего прокручиваемого
# предка либо самого окна, БЕЗ резерва под полосу прокрутки. Замер
# захода: при открытом окне лист кончался на 380 из 390, тело окна
# держало ещё 10 px (`scrollbar-gutter: stable`), и отступы выходили
# 16 слева против 36 справа. На телефоне полосы НАКЛАДНЫЕ и места
# не занимают — такое «расхождение» было бы находкой про эмуляцию
# настольного браузера, а не про экран владельца.
#
# «ВБОК» — прокручиваемый блок, который листается вбок, НЕ БУДУЧИ
# ЛЕНТОЙ (лента — дети в одну строку: вкладки, чипы). Замер захода:
# тело окна «Общая аптечка» листалось вбок на 16 px — ряд вкладок
# с отрицательными полями выходил за тело без полей (`modal-ov-flush`),
# и общий замер «шире экрана» его не видел: элемент в своей прокрутке
# вбок он считает законно обрезанным.
ОКНО_ПРАВКИ = r"""(корень) => {
  const к = document.querySelector(корень); if (!к) return null;
  const R = e => e.getBoundingClientRect();
  const вид = e => e.checkVisibility({opacityProperty: true, visibilityProperty: true}) && R(e).width > 0 && R(e).height > 0;
  const имя = e => (e.id ? '#' + e.id : '') + '.' + String(e.className).trim().split(/\s+/).slice(0, 2).join('.');
  const вбок_можно = e => { const c = getComputedStyle(e);
    return (c.overflowX === 'auto' || c.overflowX === 'scroll') && e.scrollWidth > e.clientWidth + 1; };
  const лента = e => { const д = [...e.children].filter(вид); if (д.length < 2) return false;
    return Math.max(...д.map(x => R(x).top)) < Math.min(...д.map(x => R(x).bottom)); };
  const своя = e => { for (let п = e.parentElement; п && п !== к.parentElement; п = п.parentElement)
    if (вбок_можно(п) && лента(п)) return true; return false; };
  const опора = e => { for (let п = e.parentElement; п && п !== к; п = п.parentElement) {
      const c = getComputedStyle(п); if (c.overflowY === 'auto' || c.overflowY === 'scroll') return п; }
    return к; };
  const моно = [], вбок = [], органы = [];
  for (const e of [к, ...к.querySelectorAll('*')]) {
    if (!вид(e)) continue;
    if ([...e.childNodes].some(n => n.nodeType === 3 && n.data.trim()) && /mono/i.test(getComputedStyle(e).fontFamily))
      моно.push(имя(e));
    if (вбок_можно(e) && !лента(e)) вбок.push(имя(e) + ' +' + (e.scrollWidth - e.clientWidth));
    if (e.matches('input:not([type=checkbox]):not([type=radio]):not([type=file]), textarea, select, button, .v2-chip, .chip, .v2-card, .card')
        && !e.closest('.modal-hdr, .v2-assist-head, .apt-ai-head, .modal-drag, .hint-pop') && !своя(e)) {
      const о = опора(e), bо = R(о), b = R(e);
      const л = bо.left + о.clientLeft, п = л + о.clientWidth;
      органы.push([имя(e), Math.round((b.left - л) * 10) / 10, Math.round((п - b.right) * 10) / 10]); }
  }
  const L = органы.length ? Math.min(...органы.map(x => x[1])) : null;
  const Rr = органы.length ? Math.min(...органы.map(x => x[2])) : null;
  return {моно, вбок, органов: органы.length, L, R: Rr,
          лев: органы.find(x => x[1] === L), прав: органы.find(x => x[2] === Rr)};
}"""

# 2.1: категории формы рядами, без прокрутки вбок; подвал по рядам —
# ряд = кнопки, чьи коробки перекрываются по вертикали (подсказка «?»
# ниже кнопки ростом, и равенство верха разнесло бы её в свой «ряд»)
ФОРМА_ПРАВКИ = r"""() => {
  const R = e => e.getBoundingClientRect();
  const вид = e => e.checkVisibility({opacityProperty: true, visibilityProperty: true}) && R(e).width > 0;
  const out = {};
  const к = document.getElementById('apt-f-cats');
  if (к && вид(к)) { const ч = [...к.querySelectorAll('.chip')].filter(вид);
    out.кат = {прокрутка: к.scrollWidth - к.clientWidth, рядов: new Set(ч.map(e => Math.round(R(e).top))).size,
               чипов: ч.length, за_краем: ч.filter(e => R(e).right > R(к).right + 1).length,
               wrap: getComputedStyle(к).flexWrap}; }
  const ф = document.querySelector('#apt-form .apt-foot');
  if (ф && вид(ф)) { const c = getComputedStyle(ф), b = R(ф);
    const лев = b.left + parseFloat(c.borderLeftWidth) + parseFloat(c.paddingLeft);
    const прав = b.right - parseFloat(c.borderRightWidth) - parseFloat(c.paddingRight);
    const ряды = [];
    for (const e of [...ф.querySelectorAll('button')].filter(вид).sort((a, b) => R(a).top - R(b).top)) {
      const bb = R(e), р = ряды.find(р => bb.top < р.низ - 1 && bb.bottom > р.верх + 1);
      if (р) { р.эл.push(e); р.низ = Math.max(р.низ, bb.bottom); } else ряды.push({верх: bb.top, низ: bb.bottom, эл: [e]}); }
    out.подвал = ряды.map(р => ({
      кнопки: р.эл.map(e => (e.textContent.trim() || e.getAttribute('aria-label') || '?').slice(0, 14)),
      главная: р.эл.some(e => e.type === 'submit'), отмена: р.эл.some(e => e.hasAttribute('data-modal-close')),
      слева: Math.round((Math.min(...р.эл.map(e => R(e).left)) - лев) * 10) / 10,
      справа: Math.round((прав - Math.max(...р.эл.map(e => R(e).right))) * 10) / 10})); }
  return out;
}"""

# 2.2: подчёркивание выбранной вкладки — цвет инструмента. Цвет
# инструмента раскрывает браузер (элемент с `color: var(--v2-tool)`
# внутри окна), а не строка из файла: разойдись они, сверка печатала бы
# «совпало» про другой цвет.
ВКЛАДКА_ПРАВКИ = r"""() => {
  const в = [...document.querySelectorAll('#apt-circle [data-ctab]')].find(e => e.checkVisibility() && e.classList.contains('active'));
  if (!в) return null;
  const т = document.createElement('i'); т.style.color = 'var(--v2-tool)';
  т.style.background = 'var(--v2-surface-2)'; в.parentElement.appendChild(т);
  const инстр = getComputedStyle(т).color, ступень = getComputedStyle(т).backgroundColor; т.remove();
  const c = getComputedStyle(в), р = в.closest('.apt-circle-tabsrow');
  // подложка ряда вкладок — ступень v2 (на телефоне; на 1600 её нет,
  // и проверка 60 там её не видит): была `--surface-2` старой палитры
  return {подчёркивание: c.borderBottomColor, толщина: c.borderBottomWidth, инструмент: инстр,
          подложка: р ? getComputedStyle(р).backgroundColor : null, ступень};
}"""

# 2.3: рамка микрофона — как у скрепки и штрихкода
РАМКИ_ПРАВКИ = r"""() => {
  const в = s => { const e = [...document.querySelectorAll(s)].find(x => x.checkVisibility() && x.getBoundingClientRect().width > 0);
    if (!e) return null; const c = getComputedStyle(e), b = e.getBoundingClientRect();
    return {w: Math.round(b.width * 10) / 10, h: Math.round(b.height * 10) / 10,
            рамка: c.borderTopWidth + ' ' + c.borderTopColor, радиус: c.borderTopLeftRadius}; };
  return {скрепка: в('.apt-ai-att .btn-icon'), штрихкод: в('.apt-ai-scan'), микрофон: в('.apt-ai-mic')};
}"""

# 2.6: полоса поиска Enshrouded — прилипла ли, видно ли затемнение под ней
ПОЛОСА_ENS = r"""() => { const e = document.querySelector('.ens-bar'); if (!e) return null;
  const c = getComputedStyle(e), п = getComputedStyle(e, '::after'), b = e.getBoundingClientRect();
  return {y: Math.round(scrollY), прилипла: e.classList.contains('is-stuck'), x: b.left, w: b.width, низ: b.bottom,
          линия: c.borderBottomColor, переход: п.backgroundImage.startsWith('linear-gradient'), видно: parseFloat(п.opacity),
          высота: parseFloat(п.height) || 0, фон: getComputedStyle(document.body).getPropertyValue('--v2-bg').trim()}; }"""
НИЗ_ОКНА_ENS = r"""() => { const в = document.getElementById('ensLvl'), л = document.querySelector('#ens-item .modal-sh');
  if (!в || !л) return null;
  return Math.round((л.getBoundingClientRect().bottom - в.getBoundingClientRect().bottom) * 10) / 10; }"""

# «мобильный-2» №3: категориям формы возвращена лента — ровно прежний
# дефект (15 чипов в строку, прокрутка вбок)
ПОДЛОГ_КАТЕГОРИИ = """addEventListener('DOMContentLoaded', () => { const s = document.createElement('style');
  s.textContent = '.apt-chips.apt-form-cats { flex-wrap: nowrap !important; overflow-x: auto !important; }';
  document.head.appendChild(s); });"""
# доказательство подлога №3 — `flex-wrap` категорий, снятый на каждой ширине
_доказ = {}

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
                abs(з["щель"]) <= 1, "щель %s px от %s" % (з["щель"], з.get("полоса", "?")))
            # доказательство подлога щели — ОТДЕЛЬНЫМ замером, а не формулой
            # шага: расстояние «панель разделов → шапка страницы» напрямую
            панель = стр.evaluate("""() => { const а = document.querySelector('.admin-nav-bar'),
                г = document.querySelector('.v2-page-head');
                return а && г ? Math.round((г.getBoundingClientRect().top
                                            - а.getBoundingClientRect().bottom) * 10) / 10 : null; }""")
            if панель is not None:
                _доказ.setdefault("щель_панели", []).append(панель)
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
        # ОТКРЫВАТЕЛЬ — ПОД ВЕРХНЕЙ ПОЛОСОЙ, А НЕ ЗА НЕЙ («мобильный-2»,
        # блок 1). `scroll_into_view_if_needed` считает кнопку видимой,
        # если она в окне, — а после прокрутки на 120 px открыватель
        # в шапке страницы стоит на 0–5 px, под полосой (низ 64). Пока
        # содержимое лежало ПОВЕРХ полосы (дефект блока 1), такая кнопка
        # нажималась; теперь полоса её закрывает, Playwright находит
        # перекрытие и сам прокручивает страницу к началу — и «положение
        # сбито» печаталось про пробу, а не про окно.
        стр.evaluate("""(e) => { const п = document.querySelector('.site-header');
          const низ = п ? п.getBoundingClientRect().bottom : 0, b = e.getBoundingClientRect();
          if (b.top < низ + 8) scrollBy(0, b.top - низ - 8); }""", эл.element_handle())
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


def _кадр(стр):
    import io
    from PIL import Image
    return Image.open(io.BytesIO(стр.screenshot(animations="disabled"))).convert("RGB")


def _разошлось(к0, к1, б0, б1, dpr):
    """Сколько пикселей полосы разошлось между двумя кадрами окна.
    Кадр — ВСЁ окно, полоса вырезается по её коробке: у `clip` скриншота
    система отсчёта зависит от режима, у выреза из кадра окна — нет."""
    from PIL import ImageChops
    вырез = lambda к, б: к.crop((round(б["x"] * dpr), round(б["y"] * dpr),
                                 round((б["x"] + б["w"]) * dpr), round((б["y"] + б["h"]) * dpr)))
    а, б = вырез(к0, б0), вырез(к1, б1)
    if а.size != б.size or not а.size[0] or not а.size[1]:
        return None, а.size[0] * а.size[1], 0
    r, g, b = ImageChops.difference(а, б).split()
    гист = ImageChops.lighter(ImageChops.lighter(r, g), b).histogram()
    макс = max((i for i, n in enumerate(гист) if n), default=0)
    return sum(гист[ПОРОГ_КАНАЛА + 1:]), а.size[0] * а.size[1], макс


def _полосы(стр, ш):
    for путь, имя, кнопка in ПОЛОСЫ:
        if not открыть(стр, путь, кнопка):
            шаг("%d %s: полосы не просвечивают" % (ш, имя), False, "раздел не открылся", собрано=0)
            continue
        стр.evaluate("scrollTo(0, 0)")
        стр.wait_for_timeout(300)
        з0 = стр.evaluate(ПОЛОСЫ_ЗАМЕР)
        к0 = _кадр(стр)
        # вниз колесом, как рукой: указатель посередине содержимого
        стр.mouse.move(ш / 2, 400)
        for _ in range(ПРОКРУТКА_ПОЛОС // 500):
            стр.mouse.wheel(0, 500)
            стр.wait_for_timeout(150)
        стр.wait_for_timeout(500)
        з1 = стр.evaluate(ПОЛОСЫ_ЗАМЕР)
        к1 = _кадр(стр)
        сдвиг = round(з1["y"] - з0["y"])
        # прокрутка не состоялась — сверять нечего (ПРОПУСК, а не «совпало»)
        сдвинуто = сдвиг if сдвиг >= min(ПРОКРУТКА_ПОЛОС, з0["макс"]) - 5 and сдвиг >= 300 else 0
        ждём = ("верх", "низ") if any(имя.startswith(x) for x in С_ПАНЕЛЬЮ) else ("верх",)
        for полоса in ждём:
            назв = "верхняя полоса" if полоса == "верх" else "нижняя панель"
            б0, б1 = з0.get(полоса), з1.get(полоса)
            if not б0 or not б1:
                шаг("%d %s: %s есть" % (ш, имя, назв), False, "на экране нет", собрано=0)
                continue
            шаг("%d %s: %s непрозрачна (альфа 1)" % (ш, имя, назв), б0["альфа"] == 1 and б1["альфа"] == 1,
                "фон %s" % б0["фон"])
            n, всего, макс = _разошлось(к0, к1, б0, б1, з0["dpr"])
            шаг("%d %s: %s не просвечивает" % (ш, имя, назв),
                n is not None and n <= всего * ДОЛЯ_ПИКСЕЛЕЙ,
                "прокрутка %d px, разошлось %s из %d пикс (%.2f %%), макс канал %d"
                % (сдвиг, n, всего, 100.0 * (n or 0) / max(всего, 1), макс), собрано=сдвинуто)


def _след_перехода(стр, п, dpr):
    """ЧТО ПЕРЕХОД ДЕЛАЕТ С КАРТИНКОЙ: один и тот же кадр прокрутки
    С переходом и БЕЗ него (переход на миг гасится стилем и сразу
    возвращается). Разница по строкам под полосой через 2 px — средний
    худший канал по ширине полосы. Переход нарисован поверх карточек
    и гаснет книзу — разница сверху большая и сходит на нет; переход
    под карточками — разницы нет вовсе.

    Одной строкой «у края цвет фона ±N» это не меряется: переход
    начинается от низа ПОЛЯ полосы, над её линией, и уже на 2 px ниже
    линии сквозь него видно 8 % карточки — замер первой версии дал
    18–19 на исправном переходе."""
    к1 = _кадр(стр)
    стр.evaluate("""() => { const s = document.createElement('style'); s.id = 'probe-no-fade';
      s.textContent = '.ens-bar::after { display: none !important; }'; document.head.appendChild(s); }""")
    стр.wait_for_timeout(150)
    к2 = _кадр(стр)
    стр.evaluate("() => document.getElementById('probe-no-fade').remove()")
    стр.wait_for_timeout(150)
    x0, x1 = round(п["x"] * dpr), round((п["x"] + п["w"]) * dpr)
    y0 = round(п["низ"] * dpr)
    ряды = []
    for r in range(0, round(п["высота"] * dpr), round(2 * dpr)):
        y = y0 + r
        if y >= к1.size[1]:
            break
        s = n = 0
        for x in range(x0, x1, 3):
            а, б = к1.getpixel((x, y)), к2.getpixel((x, y))
            s += max(abs(а[i] - б[i]) for i in range(3))
            n += 1
        ряды.append(round(s / max(n, 1), 1))
    return ряды


def _правки(стр, ш):
    for путь, имя, кнопка, корень in ПРАВКИ:
        открыть(стр, путь, None)
        if кнопка and not _жать(стр, кнопка):
            шаг("%d %s: окно открылось" % (ш, имя), False, "открыть нечем", собрано=0)
            continue
        if имя == "аптечка · правка":
            # категории в правке свёрнуты до выбранных — раскрыть, как рукой
            тк = стр.locator("#apt-cats-more")
            if тк.count() and тк.is_visible() and "Выбрать" in (тк.text_content() or ""):
                тк.click(timeout=5000)
                стр.wait_for_timeout(500)
        стр.wait_for_timeout(400)
        о = стр.evaluate(ОКНО_ПРАВКИ, корень)
        if о is None:
            шаг("%d %s: окно открылось" % (ш, имя), False, "корня %s нет" % корень, собрано=0)
            continue
        з = стр.evaluate(ЗАМЕР)
        шаг("%d %s: ничто не шире окна" % (ш, имя),
            not з["шире"] and з["прокрутка"] <= 0 and not о["вбок"],
            "шире %d, прокрутка %d, вбок %s %s" % (len(з["шире"]), з["прокрутка"], о["вбок"][:2] or "—",
                                                   з["шире"][:2]))
        шаг("%d %s: моноширинных нет" % (ш, имя), not о["моно"], "%d %s" % (len(о["моно"]), о["моно"][:2]))
        шаг("%d %s: боковые отступы одинаковые" % (ш, имя),
            о["L"] is not None and abs(о["L"] - о["R"]) <= 1,
            "органов %d, слева %s (%s), справа %s (%s)" % (
                о["органов"], о["L"], (о["лев"] or ["—"])[0], о["R"], (о["прав"] or ["—"])[0]),
            собрано=о["органов"])
        if имя == "аптечка · правка":
            ф = стр.evaluate(ФОРМА_ПРАВКИ)
            кат = ф.get("кат")
            _доказ.setdefault("категории", []).append(кат["wrap"] if кат else None)
            ч = (кат["чипов"], кат["рядов"], кат["прокрутка"], кат["за_краем"]) if кат else ("—",) * 4
            шаг("%d %s: категории рядами, без прокрутки вбок" % (ш, имя),
                bool(кат) and кат["прокрутка"] <= 0 and кат["рядов"] >= 2 and кат["за_краем"] == 0,
                "чипов %s, рядов %s, прокрутка %s, за краем %s" % ч,
                собрано=кат["чипов"] if кат else 0)
            ряды = ф.get("подвал") or []
            первый = ряды[0] if ряды else {}
            шаг("%d %s: подвал — «Сохранить» и «Отмена» рядом, служебные ниже" % (ш, имя),
                bool(первый.get("главная") and первый.get("отмена"))
                and not any(р["главная"] or р["отмена"] for р in ряды[1:]),
                "; ".join("%s" % "+".join(р["кнопки"]) for р in ряды), собрано=len(ряды))
            шаг("%d %s: кнопки подвала от края до края ±1" % (ш, имя),
                bool(ряды) and all(abs(р["слева"]) <= 1 and abs(р["справа"]) <= 1 for р in ряды),
                "; ".join("%s: слева %s справа %s" % (р["кнопки"][0], р["слева"], р["справа"]) for р in ряды),
                собрано=len(ряды))
        elif имя == "аптечка · общая":
            в = стр.evaluate(ВКЛАДКА_ПРАВКИ)
            шаг("%d %s: подчёркивание вкладки — цвет инструмента" % (ш, имя),
                bool(в) and в["подчёркивание"] == в["инструмент"] and в["толщина"] != "0px",
                "подчёркивание %s %s, инструмент %s" % ((в["толщина"], в["подчёркивание"], в["инструмент"])
                                                        if в else ("—",) * 3),
                собрано=1 if в else 0)
            шаг("%d %s: подложка ряда вкладок — ступень v2" % (ш, имя),
                bool(в) and в["подложка"] == в["ступень"],
                "подложка %s, ступень %s" % ((в["подложка"], в["ступень"]) if в else ("—",) * 2),
                собрано=1 if в and в["подложка"] else 0)
            т = _тень_вкладок(стр)
            if т:
                _доказ.setdefault("тень_слоёв", []).append(т["слоёв"])
                н, к = т["начало"], т["конец"]
                ок = ((not н["тень"] and not к["тень"]) if т["влезает"]
                      else (bool(н["тень"]) and not н["режет"] and not к["режет"]))
            шаг("%d %s: тень вкладок — только когда не влезают, не на тексте" % (ш, имя),
                bool(т) and ок,
                "%s; в начале тень %s, на тексте %s; в конце тень %s, на тексте %s" % (
                    "влезают" if т["влезает"] else "не влезают", т["начало"]["тень"],
                    т["начало"]["режет"] or "нет", т["конец"]["тень"], т["конец"]["режет"] or "нет")
                if т else "ряда вкладок нет", собрано=1 if т else 0)
        elif имя == "аптечка · ассистент":
            р = стр.evaluate(РАМКИ_ПРАВКИ)
            эт, м = [р.get("скрепка"), р.get("штрихкод")], р.get("микрофон")
            ок = bool(м) and all(э and abs(э["w"] - м["w"]) <= 1 and abs(э["h"] - м["h"]) <= 1
                                 and э["рамка"] == м["рамка"] and э["радиус"] == м["радиус"] for э in эт)
            шаг("%d %s: микрофон в рамке, как скрепка и штрихкод" % (ш, имя), ок,
                "микрофон %s; скрепка %s" % (м, эт[0]), собрано=sum(1 for э in эт + [м] if э))
        elif имя == "enshrouded":
            # как рукой: вниз колесом на 2000 px, затем обратно
            п0 = стр.evaluate(ПОЛОСА_ENS)
            стр.mouse.move(ш / 2, 600)
            for _ in range(ПРОКРУТКА_ПОЛОС // 500):
                стр.mouse.wheel(0, 500)
                стр.wait_for_timeout(150)
            стр.wait_for_timeout(500)
            # под переходом обязана оказаться карточка, а не щель между
            # ними: сравнивать фон с фоном нечем. Не она — ещё колесом
            под_карточкой = False
            for _ in range(6):
                п1 = стр.evaluate(ПОЛОСА_ENS)
                под_карточкой = bool(п1) and стр.evaluate(
                    "([x, y]) => !!(document.elementFromPoint(x, y) || document.body).closest('.card')",
                    [п1["x"] + п1["w"] / 2, п1["низ"] + 8])
                if not п1 or под_карточкой:
                    break
                стр.mouse.wheel(0, 150)
                стр.wait_for_timeout(300)
            п1 = стр.evaluate(ПОЛОСА_ENS)
            ряды = _след_перехода(стр, п1, стр.evaluate("devicePixelRatio")) if п1 else []
            прокручено = п1 and п0 and п1["y"] - п0["y"] >= 300
            шаг("%d %s: вверху затемнения нет, линия на месте" % (ш, имя),
                bool(п0) and not п0["прилипла"] and п0["видно"] == 0,
                "прилипла %s, видно %s, линия %s" % ((п0["прилипла"], п0["видно"], п0["линия"]) if п0 else ("—",) * 3))
            шаг("%d %s: под прилипшей полосой затемнение, линии нет" % (ш, имя),
                bool(п1) and п1["прилипла"] and п1["переход"] and п1["видно"] == 1 and п1["высота"] >= 16
                and п1["линия"] in ("rgba(0, 0, 0, 0)", "transparent"),
                "прокрутка %s, прилипла %s, переход %s, видно %s, высота %s, линия %s" % (
                    п1 and п1["y"], п1 and п1["прилипла"], п1 and п1["переход"], п1 and п1["видно"],
                    п1 and п1["высота"], п1 and п1["линия"]),
                собрано=1 if прокручено else 0)
            # затемнение ВИДНО и ПЛАВНОЕ: сверху разница с кадром без
            # перехода есть, книзу сходит на нет
            шаг("%d %s: затемнение поверх карточек и гаснет книзу" % (ш, имя),
                len(ряды) >= 4 and max(ряды[:3]) >= 1 and max(ряды[-3:]) <= max(ряды[:3]) / 2,
                "разница по строкам через 2 px: %s" % ряды,
                собрано=1 if прокручено and под_карточкой else 0)
            for _ in range(ПРОКРУТКА_ПОЛОС // 500):
                стр.mouse.wheel(0, -500)
                стр.wait_for_timeout(150)
            стр.wait_for_timeout(500)
            п2 = стр.evaluate(ПОЛОСА_ENS)
            шаг("%d %s: наверху затемнение снова погасло" % (ш, имя),
                bool(п2) and not п2["прилипла"] and п2["видно"] == 0,
                "прокрутка %s, прилипла %s, видно %s" % ((п2["y"], п2["прилипла"], п2["видно"]) if п2 else ("—",) * 3),
                собрано=1 if прокручено else 0)
        elif имя == "enshrouded · предмет":
            бокс = стр.locator("#ens-item .modal-sh").bounding_box()
            if бокс:
                # низ окна — прокруткой внутри листа, как рукой
                стр.mouse.move(бокс["x"] + бокс["width"] / 2, бокс["y"] + бокс["height"] / 2)
                стр.mouse.wheel(0, 1500)
                стр.wait_for_timeout(400)
            н = стр.evaluate(НИЗ_ОКНА_ENS)
            шаг("%d %s: «Уровень предмета» не ближе 16 px к низу окна" % (ш, имя),
                н is not None and н >= 16, "до низа окна %s px" % н, собрано=1 if н is not None else 0)
        if кнопка:
            стр.keyboard.press("Escape")
            стр.wait_for_timeout(300)


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
                if только in (None, "полосы"):
                    _полосы(стр, ш)
                if только in (None, "правки"):
                    _правки(стр, ш)
                ctx.close()
        finally:
            бр.close()
    плохих = sum(1 for _, и in _шаги if и == "ПЛОХО")
    пропусков = sum(1 for _, и in _шаги if и == "ПРОПУСК")
    if печать:
        print("\nИТОГ: шагов %d, плохих %d, пропусков %d" % (len(_шаги), плохих, пропусков))
    return плохих, пропусков


# ── «Расход-3», 3.3: ТЕНЬ У РЯДА ВКЛАДОК «ОБЩЕЙ АПТЕЧКИ» ──────────────
# Правило владельца: вкладки влезают — тени нет; не влезают — тень
# у видимого края, пока справа есть что листать, и ни на тексте целиком
# видимой вкладки. Тень ищется ПИКСЕЛЕМ, а не по объявлению: снимок
# ряда как есть против снимка с погашенными фоновыми картинками
# и масками ряда. Различающиеся столбцы и есть тень, как бы её
# ни нарисовали (фон, псевдоэлемент, маска) — объявлению тут верить
# нельзя: прежнее правило писало «у ряда, помещающегося целиком, она
# не видна», а лежало на последней вкладке всегда.
ГЕОМ_ВКЛАДОК = r"""() => { const р = document.querySelector('#apt-circle .apt-circle-tabs');
  if (!р) return null; const b = р.getBoundingClientRect();
  const вк = [...р.querySelectorAll('[data-ctab]')].map(в => { const rg = document.createRange();
    rg.selectNodeContents(в); const rr = [...rg.getClientRects()].filter(x => x.width > 0);
    return {имя: в.textContent.trim().replace(/\s+/g, ' ').slice(0, 16),
            л: Math.min(...rr.map(x => x.left)) - b.left + р.scrollLeft,
            п: Math.max(...rr.map(x => x.right)) - b.left + р.scrollLeft}; });
  return {ш: р.clientWidth, sw: р.scrollWidth, sl: р.scrollLeft, w: b.width, вкладки: вк,
          слоёв: getComputedStyle(р).backgroundImage.split('gradient(').length - 1}; }"""
ГАСИТЬ_ТЕНЬ = """() => { const s = document.createElement('style'); s.id = 'zz-no-shade';
  s.textContent = '#apt-circle .apt-circle-tabsrow, #apt-circle .apt-circle-tabsrow *,'
    + ' #apt-circle .apt-circle-tabsrow::before, #apt-circle .apt-circle-tabsrow::after,'
    + ' #apt-circle .apt-circle-tabsrow *::before, #apt-circle .apt-circle-tabsrow *::after'
    + ' { background-image: none !important; -webkit-mask-image: none !important; mask-image: none !important; }';
  document.head.appendChild(s); }"""
# «Расход-3» №3: вернуть прежнюю тень — одна заливка с `local`, то есть
# у конца содержимого, поверх последней вкладки
ПОДЛОГ_ТЕНЬ = """addEventListener('DOMContentLoaded', () => { const s = document.createElement('style');
  s.textContent = '@media (max-width: 560px) { #apt-circle .apt-circle-tabs { background: linear-gradient(to left,'
    + ' var(--v2-surface-pop), transparent) right / 24px 100% no-repeat local !important; } }';
  document.head.appendChild(s); });"""


def _тень_вкладок(стр):
    """Где тень ряда: в начале прокрутки и в конце. Отдаёт полосы тени
    (x от левого края ряда) и имена ЦЕЛИКОМ видимых вкладок, на текст
    которых она легла; частично видимую вкладку режет край ряда, а не тень."""
    import io as _io
    from PIL import Image, ImageChops
    ряд = стр.locator("#apt-circle .apt-circle-tabs").first
    if not ряд.count():
        return None
    итог = {}
    for где in ("начало", "конец"):
        стр.evaluate("(к) => { const р = document.querySelector('#apt-circle .apt-circle-tabs');"
                     " р.scrollLeft = к ? р.scrollWidth : 0; }", где == "конец")
        стр.wait_for_timeout(200)
        г = стр.evaluate(ГЕОМ_ВКЛАДОК)
        а = Image.open(_io.BytesIO(ряд.screenshot(animations="disabled"))).convert("RGB")
        стр.evaluate(ГАСИТЬ_ТЕНЬ)
        стр.wait_for_timeout(100)
        б = Image.open(_io.BytesIO(ряд.screenshot(animations="disabled"))).convert("RGB")
        стр.evaluate("() => document.getElementById('zz-no-shade').remove()")
        р = ImageChops.difference(а.crop((0, 0) + б.size), б.crop((0, 0) + а.size))
        к = а.width / г["w"]
        столбцы = [x / к for x in range(р.width)
                   if max(e[1] for e in р.crop((x, 0, x + 1, р.height)).getextrema()) > ПОРОГ_КАНАЛА]
        тень = []
        for x in столбцы:
            if тень and x - тень[-1][1] <= 1.5:
                тень[-1][1] = x + 1 / к
            else:
                тень.append([x, x + 1 / к])
        тень = [(round(x0, 1), round(x1, 1)) for x0, x1 in тень]
        видно = [(в["имя"], в["л"] - г["sl"], в["п"] - г["sl"]) for в in г["вкладки"]]
        целиком = [в for в in видно if в[1] >= -0.5 and в[2] <= г["ш"] + 0.5]
        режет = sorted({в[0] for в in целиком for т0, т1 in тень if в[1] < т1 and т0 < в[2]})
        итог[где] = {"тень": тень, "режет": режет}
        итог["влезает"] = г["sw"] <= г["ш"] + 1
        итог["слоёв"] = г["слоёв"]
    стр.evaluate("() => { document.querySelector('#apt-circle .apt-circle-tabs').scrollLeft = 0; }")
    return итог


def _доказ_тени():
    """Подлог №3 «Расход-3» состоялся, если у ряда на всех ширинах ОДИН
    слой фоновой заливки — прежнее правило; у нынешнего их три.
    Отдельный замер, а не вердикт шага."""
    в = _доказ.get("тень_слоёв") or []
    return bool(в) and all(x == 1 for x in в), "слоёв фона у ряда по ширинам: %s" % в


def _доказ_категорий():
    """Подлог №3 состоялся, если `flex-wrap` категорий на всех ширинах
    стал `nowrap` — независимо от вердикта шага."""
    в = _доказ.get("категории") or []
    return bool(в) and all(x == "nowrap" for x in в), "flex-wrap по ширинам: %s" % в


def _доказ_щели():
    """Подлог щели состоялся, если расстояние «панель разделов → шапка»,
    снятое ОТДЕЛЬНЫМ замером на каждой ширине, не меньше 31 px."""
    в = _доказ.get("щель_панели") or []
    return bool(в) and all(x >= 31 for x in в), "панель → шапка по ширинам: %s px" % в


def контроль(только=None):
    print("ЧИСТЫЙ ПРОГОН")
    плохих, _ = проверка(печать=False, только=только)
    if плохих:
        print("КОНТРОЛЬ НЕДЕЙСТВИТЕЛЕН: грязная основа (%d плохих)" % плохих)
        return 2
    итог = []
    for имя, код, раздел, признак, доказ in (
            ("№2: заголовок шире экрана", ПОДЛОГ_ШИРЕ, "экраны", "ничто не шире экрана", None),
            # доказательство — расстояние «панель → шапка» отдельным
            # замером (письмо «Расход», новая формула щели)
            ("«Расход»: щель под панелью разделов", ПОДЛОГ_ЩЕЛЬ, "экраны",
             "админ · расход: шапка вплотную", _доказ_щели),
            ("№3: прокрутка фона разрешена", ПОДЛОГ_ФОН, "окна", "фон стоит", None),
            # доказательство — АЛЬФА ФОНА: подлог обязан её опустить, иначе
            # «снимки разошлись» значило бы что угодно, кроме подлога
            ("мобильный-2 №1: полосы полупрозрачны", ПОДЛОГ_ПОЛОСЫ, "полосы", "не просвечивает",
             "непрозрачна"),
            # доказательство — `flex-wrap` категорий, а не упавший шаг
            ("мобильный-2 №3: категории формы лентой", ПОДЛОГ_КАТЕГОРИИ, "правки",
             "категории рядами", _доказ_категорий),
            # доказательство — число слоёв фона у ряда, отдельный замер
            ("«Расход-3» №3: тень поверх последней вкладки", ПОДЛОГ_ТЕНЬ, "правки",
             "тень вкладок", _доказ_тени)):
        if только and раздел != только:
            continue
        print("\nПОДЛОГ %s" % имя)
        _доказ.clear()
        проверка(код, печать=False, только=раздел)
        упало = [и for и, х in _шаги if х == "ПЛОХО" and признак in и]
        print("  упало шагов «%s»: %d" % (признак, len(упало)))
        состоялся = True
        if callable(доказ):
            состоялся, текст = доказ()
            print("  доказательство — %s%s" % (текст, "" if состоялся else " (ПОДЛОГ НЕ СОСТОЯЛСЯ)"))
        elif доказ:
            n = sum(1 for и, х in _шаги if х == "ПЛОХО" and доказ in и)
            состоялся = n > 0
            print("  доказательство — шагов «%s» упало: %d%s" % (
                доказ, n, "" if состоялся else " (ПОДЛОГ НЕ СОСТОЯЛСЯ)"))
        итог.append(len(упало) > 0 and состоялся)
    print("\nКОНТРОЛЬ: %s" % ("ВСЕ ПОДЛОГИ НАЙДЕНЫ" if all(итог) else "ЕСТЬ НЕНАЙДЕННЫЕ"))
    return 0 if all(итог) else 1


def main():
    if "--замер" in sys.argv:
        печать_замера(замер())
        sys.exit(0)
    только = None
    for к in ("экраны", "сообщения", "группы", "окна", "полосы", "правки"):
        if "--" + к in sys.argv:
            только = к
    if "--контроль" in sys.argv:
        sys.exit(контроль(только))
    print("ОБОЛОЧКА v2 НА ТЕЛЕФОНЕ")
    плохих, пропусков = проверка(только=только)
    sys.exit(1 if плохих else 0)


if __name__ == "__main__":
    main()
