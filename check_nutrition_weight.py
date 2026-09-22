"""ПРОВЕРКА 57: ВКЛАДКИ «ВЕС» И «ПРОФИЛЬ» ДНЕВНИКА (№352, «питание-3», блок 2).

ПРОВЕРКА, код 1 при находке, 2 — замерить нечем (стенда нет, вкладок нет).

Что спрашивается, и каждое — замером живой страницы, а не классом:
  2.1 ГРАФИК ВЕСА. Последний замер старше месяца, а по умолчанию стоит
      «Месяц» — карточка была пустой и читалась как поломка. Правило:
      за месяц 0 точек, за всё время есть — сразу «Всё время», и эта
      кнопка подсвечена. Данные подаются ПЕРЕХВАТОМ `/nutrition/api/weight`
      (тот же ряд стенда, сдвинутый на 40 дней назад): базу не трогаем.
  2.3 СРАВНЕНИЕ ФОТО. Пока дат нет — списков дат НЕ ВИДНО, стоит одна
      строка «Загрузите фото хотя бы за одну дату». Есть дата — списки
      видны. Видимость — по вычисленному стилю и размеру.
  2.4 СБРОС ВЫБОРА ФОТО. После «Сохранить» выбор очищен целиком: второе
      нажатие не шлёт НИ ОДНОГО запроса, кнопка неактивна. Отправка
      перехватывается и в базу не доходит.
  2.5 КОНТРАСТ «АКТИВНОСТИ». Невыбранные варианты: текст ≥ 4.5 к своему
      фону, значок ≥ 3 (фон сложен по цепочке предков с прозрачностью).
  1.3 ПРЕДУПРЕЖДЕНИЕ АНКЕТЫ («аптечка-1»). Меняется рост в форме — видна
      ОДНА фраза «Новая норма действует с сегодняшнего дня, у прошлых дней
      остаётся своя», текст берётся из DOM (`innerText`), видимость —
      по вычисленному стилю. Форма не сохраняется, база не трогается.
  2.6 ЛЕВЫЙ КРАЙ. В каждой карточке «Веса» и «Профиля» элемент, стоящий
      в начале строки (ближе 40 px к краю содержимого), стоит РОВНО на нём,
      ±1 px. Край содержимого — край карточки плюс рамка и поле. Вложенный
      блок с рамкой либо фоном — своя карточка. Центрированные по замыслу
      элементы (центр совпадает с центром карточки) не спрашиваются
      и печатаются списком.

Браузер ВИДИМЫЙ, на втором мониторе (§6.0.3): край содержимого зависит
от ширины карточки. В базу НЕ ПИШЕТ.

КЛЮЧИ:
  --замер      только числа, без вердикта (код 0)
  --контроль   четыре подлога, каждый обязан уронить СВОЮ строку:
               автопереключение снято, списки дат видны без дат,
               выбор фото не сброшен (прежний `undefined`), лишний
               `margin-left: 8px` у кнопки карточки весов; плюс
               контраст — невыбранный вариант прежним тусклым цветом.
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

ФРАЗА_НОРМЫ = "Новая норма действует с сегодняшнего дня, у прошлых дней остаётся своя"
НОРМА = """() => {
  const поле = document.getElementById('p-height');
  const было = поле.value;
  поле.value = String((parseFloat(было) || 170) + 3);
  поле.dispatchEvent(new Event('input', {bubbles: true}));
  проверитьСменуНормы();
  const б = document.getElementById('p-norm-warn');
  const итог = {видно: getComputedStyle(б).display !== 'none' && б.getBoundingClientRect().height > 0,
                текст: (б.innerText || '').replace(/\s+/g, ' ').trim()};
  поле.value = было;
  проверитьСменуНормы();
  итог.после_возврата_скрыто = getComputedStyle(б).display === 'none';
  return итог;
}"""

ГЛУШИТЕЛЬ = """addEventListener('DOMContentLoaded', () => { const s = document.createElement('style');
  s.textContent = '*, *::before, *::after { transition: none !important; animation: none !important; }';
  document.head.appendChild(s); });"""


def _стиль(css):
    return """addEventListener('DOMContentLoaded', () => { const s = document.createElement('style');
      s.textContent = %r; document.head.appendChild(s); });""" % css


# Функции контраста — тот же разбор цвета канвой, что у проверки 55
ЦВЕТ = r"""
  const кв = document.createElement('canvas'); кв.width = кв.height = 1;
  const к = кв.getContext('2d', {willReadFrequently: true});
  const цвет = (s) => { к.clearRect(0, 0, 1, 1); к.fillStyle = '#000';
    к.fillStyle = s; к.fillRect(0, 0, 1, 1);
    const d = к.getImageData(0, 0, 1, 1).data; return [d[0], d[1], d[2], d[3] / 255]; };
  const поверх = (низ, верх, а) => низ.map((v, i) => i < 3 ? v * (1 - а) + верх[i] * а : 1);
  const фон = (e) => { const цепь = []; for (let x = e; x; x = x.parentElement) цепь.unshift(x);
    let с = [255, 255, 255, 1], непр = 1;
    for (const x of цепь) { const st = getComputedStyle(x); непр *= parseFloat(st.opacity);
      const b = цвет(st.backgroundColor);
      if (b[3] > 0) с = поверх(с, b, b[3] * (x === цепь[0] ? 1 : непр)); }
    return {с, непр}; };
  const свет = (c) => { const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
    return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]); };
  const контраст = (a, b) => { const x = свет(a), y = свет(b);
    return Math.round((Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05) * 100) / 100; };
  const против = (e, css) => { const {с, непр} = фон(e); const т = цвет(css);
    return контраст(поверх(с, т, т[3] * непр), с); };
"""

АКТИВНОСТЬ = "() => {" + ЦВЕТ + r"""
  return [...document.querySelectorAll('#rg-act .v2-choice-item:not(.active)')].map(b => {
    const ик = b.querySelector('svg');
    return {подпись: b.textContent.trim().slice(0, 18),
      текст: против(b, getComputedStyle(b).color),
      значок: ик ? против(b, getComputedStyle(ик).stroke === 'none' ? getComputedStyle(ик).color : getComputedStyle(ик).stroke) : null};
  });
}"""

# ЗНАЧОК КЛЮЧА В ПЛАШКЕ ОТЗЫВА («питание-4», 3.2) — в одной строке с первым
# словом: верх значка и верх первой строки текста ±2 px, значок левее текста
КЛЮЧ = """() => { const a = document.getElementById('scale-reauth'); if (!a || !a.checkVisibility()) return null;
  const i = a.querySelector('svg'), t = a.querySelector('span'), r = document.createRange();
  r.setStart(t.firstChild, 0); r.setEnd(t.firstChild, 1); const л = r.getClientRects()[0];
  return {разница: Math.round((i.getBoundingClientRect().top - л.top) * 10) / 10,
          левее: i.getBoundingClientRect().right <= л.left}; }"""

ЛЕВЫЕ_КРАЯ = r"""(вкладка) => {
  const R = e => e.getBoundingClientRect();
  const вид = e => e.checkVisibility({opacityProperty: true, visibilityProperty: true}) && R(e).width > 0 && R(e).height > 0;
  const блок = e => { const c = getComputedStyle(e);
    return (parseFloat(c.borderLeftWidth) > 0 && c.borderLeftStyle !== 'none')
        || !['rgba(0, 0, 0, 0)', 'transparent'].includes(c.backgroundColor); };
  const таб = document.getElementById(вкладка);
  const карточки = [...таб.querySelectorAll('*')].filter(e => вид(e) && блок(e) && R(e).width >= 160 && R(e).height >= 40
    && !e.matches('input, select, textarea, button, a, svg, img, .segmented, .segmented-btn, .v2-seg, .v2-seg-btn, .v2-choice, .v2-choice-item, .v2-select-wrap, .chip, .meter, .meter-fill, .scale, .scale *, .body-photo-slot, .compare-shot, .alert, .p-msg'));
  const ЛИСТЬЯ = 'h1, h2, h3, h4, p, label, input, select, textarea, button, a, .f-label, .field-label, .nut-card-title, .segmented, .v2-seg, .v2-choice, .p-note, .p-note-inline';
  const итог = [], центр = [];
  for (const к of карточки) {
    const c = getComputedStyle(к), b = R(к);
    const край = b.left + parseFloat(c.borderLeftWidth) + parseFloat(c.paddingLeft);
    const ширина = b.width - parseFloat(c.borderLeftWidth) - parseFloat(c.borderRightWidth)
                 - parseFloat(c.paddingLeft) - parseFloat(c.paddingRight);
    const середина = край + ширина / 2;
    for (const e of к.querySelectorAll(ЛИСТЬЯ)) {
      if (!вид(e)) continue;
      // ближайшая карточка элемента — эта; вложенная меряется сама
      let п = e.parentElement, своя = true;
      while (п && п !== к) { if (карточки.includes(п)) { своя = false; break; } п = п.parentElement; }
      if (!своя) continue;
      // лист внутри другого листа (значок в кнопке, текст в подписи) не спрашивается
      if (e.parentElement && e.parentElement.closest(ЛИСТЬЯ) && к.contains(e.parentElement.closest(ЛИСТЬЯ))) continue;
      // ВИДИМЫЙ край: у элемента без рамки и фона (призрачная кнопка,
      // абзац, подпись) видно ТЕКСТ, а не коробку — меряется текст
      let eb = R(e);
      if (!блок(e) && !e.matches('input, select, textarea')) {
        const д = document.createRange(); д.selectNodeContents(e);
        const т = [...д.getClientRects()].filter(r => r.width > 0);
        if (т.length) eb = {left: Math.min(...т.map(r => r.left)), width: Math.max(...т.map(r => r.right)) - Math.min(...т.map(r => r.left))};
      }
      const откл = eb.left - край;
      if (откл > 40 || откл < -40) continue;
      const имя = (e.id ? '#' + e.id : '') + (e.className && e.className.baseVal === undefined ? '.' + e.className.toString().trim().split(/\s+/)[0] : '') || e.tagName;
      if (eb.width < ширина - 2 && Math.abs(eb.left + eb.width / 2 - середина) <= 1 && откл > 1) {
        центр.push((к.id || к.className.toString().split(' ')[0]) + ' ' + имя); continue; }
      итог.push({карточка: к.id || к.className.toString().trim().split(/\s+/).slice(0, 2).join('.'),
                 элемент: имя, текст: (e.textContent || e.value || '').trim().slice(0, 24),
                 откл: Math.round(откл * 10) / 10});
    }
  }
  return {замеров: итог.length, смещены: итог.filter(x => Math.abs(x.откл) > 1), центр};
}"""

ПЕРИОД = r"""() => {
  const акт = document.querySelector('#wt-period .v2-seg-btn.active');
  const svg = document.getElementById('wt-svg');
  return {период: акт ? акт.dataset.period : null, точек: svg.querySelectorAll('circle').length,
          пусто: svg.innerHTML.trim() === ''};
}"""

СРАВНЕНИЕ = r"""() => {
  const R = e => e.getBoundingClientRect();
  const вид = e => !!e && e.checkVisibility({opacityProperty: true, visibilityProperty: true}) && R(e).width > 0 && R(e).height > 0;
  const стр = document.querySelector('#compare-view');
  return {списки_видны: вид(document.getElementById('compare-date-old')) || вид(document.getElementById('compare-date-new')),
          строка: (стр.textContent || '').replace(/\s+/g, ' ').trim()};
}"""


def _сдвинутый_вес(route, request):
    """Ряд стенда, сдвинутый так, что последний замер — 40 дней назад."""
    import datetime as dt
    import json
    ответ = route.fetch()
    тело = ответ.json()
    логи = [л for л in тело.get("logs", []) if л.get("weight_kg")]
    if логи:
        последний = max(dt.date.fromisoformat(л["date"]) for л in логи)
        сдвиг = (последний - (dt.date.today() - dt.timedelta(days=40)))
        for л in тело["logs"]:
            л["date"] = (dt.date.fromisoformat(л["date"]) - сдвиг).isoformat()
    route.fulfill(status=200, content_type="application/json", body=json.dumps(тело))


def _ключ_отозван(route, request):
    """Статус весов «ключ отозван»: Zepp не вызывается, база не трогается."""
    import json
    тело = route.fetch().json()
    тело["состояние"] = "reauth"
    route.fulfill(status=200, content_type="application/json", body=json.dumps(тело))


def _пустые_фото(route, request):
    route.fulfill(status=200, content_type="application/json", body='{"photos": {}, "dates": []}')


def _картинка():
    import io
    from PIL import Image
    б = io.BytesIO()
    Image.new("RGB", (64, 48), (120, 90, 60)).save(б, "JPEG")
    return б.getvalue()


def замер(подлог=None, ширины=ШИРИНЫ):
    from playwright.sync_api import sync_playwright
    import browser_window  # noqa: F401  окно — на втором мониторе
    итог = {"период": [], "сравнение": [], "сброс": None, "активность": [], "края": []}
    with sync_playwright() as p:
        бр = p.chromium.launch(headless=False)
        try:
            for ш in ширины:
                ctx = бр.new_context(viewport={"width": ш, "height": 900}, has_touch=ш < 500)
                стр = ctx.new_page()
                стр.add_init_script(ГЛУШИТЕЛЬ)
                if подлог:
                    стр.add_init_script(подлог)
                ch._войти(стр)

                # 2.6 и 2.5 — живые данные стенда
                стр.goto(ch.БАЗА + "/nutrition", wait_until="networkidle", timeout=45000)
                for вкладка in ("weight", "profile"):
                    стр.evaluate("(t) => document.querySelector('.v2-tab[data-tab=' + t + ']').click()", вкладка)
                    стр.wait_for_timeout(900)
                    к = стр.evaluate(ЛЕВЫЕ_КРАЯ, "tab-" + вкладка)
                    итог["края"].append((ш, вкладка, к))
                    if вкладка == "profile":
                        итог.setdefault("норма", []).append((ш, стр.evaluate(НОРМА)))
                        итог["активность"].append((ш, стр.evaluate(АКТИВНОСТЬ)))
                        # то же при отозванном ключе: плашка, форма и «Стереть привязку»
                        стр.route("**/nutrition/api/scale/status", _ключ_отозван)
                        стр.evaluate("() => loadScaleStatus()")
                        стр.wait_for_timeout(900)
                        итог["края"].append((ш, "profile/ключ", стр.evaluate(ЛЕВЫЕ_КРАЯ, "tab-profile")))
                        итог.setdefault("ключ", []).append((ш, стр.evaluate(КЛЮЧ)))
                        стр.unroute("**/nutrition/api/scale/status")
                    else:
                        итог["сравнение"].append((ш, "есть даты", стр.evaluate(СРАВНЕНИЕ)))

                # 2.1 — последний замер 40 дней назад (перехват, база не трогается)
                стр.route("**/nutrition/api/weight", _сдвинутый_вес)
                стр.route("**/nutrition/api/body-photos", _пустые_фото)
                стр.goto(ch.БАЗА + "/nutrition", wait_until="networkidle", timeout=45000)
                стр.evaluate("() => document.querySelector('.v2-tab[data-tab=weight]').click()")
                стр.wait_for_timeout(900)
                итог["период"].append((ш, стр.evaluate(ПЕРИОД)))
                # 2.3 — дат фото нет
                итог["сравнение"].append((ш, "нет дат", стр.evaluate(СРАВНЕНИЕ)))

                # 2.4 — один раз, на первой ширине: отправка перехвачена
                if итог["сброс"] is None:
                    запросы = []

                    def _фото(route, request):
                        запросы.append(request.post_data_buffer or b"")
                        route.fulfill(status=200, content_type="application/json", body='{"ok": true}')
                    стр.route("**/nutrition/api/body-photo", _фото)
                    стр.set_input_files("#photo-front", files=[{"name": "f.jpg", "mimeType": "image/jpeg", "buffer": _картинка()}])
                    стр.wait_for_function("() => document.querySelector('#slot-front img')", timeout=10000)
                    стр.evaluate("() => uploadBodyPhotos()")
                    стр.wait_for_timeout(800)
                    первых = len(запросы)
                    неактивна = стр.evaluate("() => !!document.getElementById('body-photo-save') && document.getElementById('body-photo-save').disabled")
                    стр.evaluate("() => uploadBodyPhotos()")
                    стр.wait_for_timeout(800)
                    вторых = len(запросы) - первых
                    с_undefined = sum(1 for т in запросы[первых:] if b"undefined" in т)
                    итог["сброс"] = {"первое": первых, "второе": вторых, "undefined": с_undefined,
                                     "кнопка_неактивна": неактивна}
                ctx.close()
        finally:
            бр.close()
    return итог


def _печать(и):
    print("  2.1 период при последнем замере 40 дней назад:")
    for ш, з in и["период"]:
        print("      %-5d выбрано %-6s точек %d%s" % (ш, з["период"], з["точек"], "  ПУСТО" if з["пусто"] else ""))
    print("  2.3 сравнение фото:")
    for ш, случай, з in и["сравнение"]:
        print("      %-5d %-9s списки видны %-5s строка «%s»" % (ш, случай, з["списки_видны"], з["строка"][:40]))
    с = и["сброс"] or {}
    print("  2.4 повторное «Сохранить»: первое нажатие — запросов %s; второе — %s (с undefined %s); кнопка неактивна %s"
          % (с.get("первое"), с.get("второе"), с.get("undefined"), с.get("кнопка_неактивна")))
    print("  2.5 «Активность», невыбранные (текст / значок):")
    for ш, в in и["активность"]:
        print("      %-5d %s" % (ш, "  ".join("%.2f/%s" % (x["текст"], "%.2f" % x["значок"] if x["значок"] else "—") for x in в)))
    print("  2.6 левый край в карточках:")
    for ш, вкл, к in и["края"]:
        print("      %-5d %-12s замеров %d, смещено %d%s" % (ш, вкл, к["замеров"], len(к["смещены"]),
              ("; " + ", ".join("%s %s «%s» %+.1f" % (x["карточка"], x["элемент"], x["текст"], x["откл"]) for x in к["смещены"][:6])) if к["смещены"] else ""))
        if к["центр"]:
            print("            центрированы по замыслу: %s" % ", ".join(sorted(set(к["центр"]))))


_строки = {}


def шаг(имя, условие, подробность="", собрано=None):
    if собрано is not None and собрано == 0:
        исход = "ПРОПУСК"
    elif условие:
        исход = "ok"
    else:
        исход = "ПЛОХО"
    _строки[имя] = исход
    print("  %-8s %s%s" % (исход, имя, (" — " + подробность) if подробность else ""))


def проверка(подлог=None, печать=True):
    _строки.clear()
    и = замер(подлог)
    if печать:
        _печать(и)
    п = и["период"]
    шаг("пустой-месяц-показывает-всё-время",
        all(з["период"] == "all" and з["точек"] > 0 for _, з in п),
        "; ".join("%d: %s, точек %d" % (ш, з["период"], з["точек"]) for ш, з in п), собрано=len(п))
    нет = [(ш, з) for ш, с, з in и["сравнение"] if с == "нет дат"]
    есть = [(ш, з) for ш, с, з in и["сравнение"] if с == "есть даты"]
    шаг("без-дат-списков-нет-одна-строка",
        all(not з["списки_видны"] and з["строка"] == "Загрузите фото хотя бы за одну дату" for _, з in нет),
        собрано=len(нет))
    шаг("с-датами-списки-видны", all(з["списки_видны"] for _, з in есть), собрано=len(есть))
    с = и["сброс"] or {}
    шаг("повтор-сохранения-не-шлёт-запросов",
        с.get("первое", 0) >= 1 and с.get("второе") == 0 and с.get("кнопка_неактивна") is True,
        "первое %s, второе %s, кнопка неактивна %s" % (с.get("первое"), с.get("второе"), с.get("кнопка_неактивна")),
        собрано=с.get("первое", 0))
    нр = и.get("норма", [])
    шаг("предупреждение-анкеты-одной-фразой",
        all(з["видно"] and з["текст"] == ФРАЗА_НОРМЫ and з["после_возврата_скрыто"] for _, з in нр),
        "; ".join("%d: видно %s, «%s»" % (ш, з["видно"], з["текст"][:60]) for ш, з in нр), собрано=len(нр))
    акт = [x for _, в in и["активность"] for x in в]
    шаг("активность-текст-4.5", all(x["текст"] >= 4.5 for x in акт),
        "худший %.2f" % min((x["текст"] for x in акт), default=0), собрано=len(акт))
    зн = [x["значок"] for x in акт if x["значок"] is not None]
    шаг("активность-значок-3", all(z >= 3 for z in зн), "худший %.2f" % min(зн, default=0), собрано=len(зн))
    кл = [(ш, к) for ш, к in и.get("ключ", []) if к]
    шаг("значок-ключа-в-строке-текста", all(abs(к["разница"]) <= 2 and к["левее"] for _, к in кл),
        "; ".join("%d: %+.1f px, левее %s" % (ш, к["разница"], к["левее"]) for ш, к in кл), собрано=len(кл))
    замеров = sum(к["замеров"] for _, _, к in и["края"])
    смещ = [(ш, вкл, x) for ш, вкл, к in и["края"] for x in к["смещены"]]
    шаг("левый-край-в-карточках", not смещ,
        ", ".join("%d %s %s %+.1f" % (ш, вкл, x["элемент"], x["откл"]) for ш, вкл, x in смещ[:5]), собрано=замеров)
    return sum(1 for v in _строки.values() if v == "ПЛОХО"), sum(1 for v in _строки.values() if v == "ПРОПУСК")


ПОДЛОГИ = [
    ("предупреждение анкеты прежними тремя предложениями", "предупреждение-анкеты-одной-фразой",
     """addEventListener('DOMContentLoaded', () => { window.проверитьСменуНормы = function () {
        const б = document.getElementById('p-norm-warn'); б.style.display = '';
        б.textContent = 'Нормы пересчитаются с сегодняшнего дня. У дней с 20 августа 2026 остаётся своя норма. '
          + 'Дни раньше считаются по действующей — их доли в календаре изменятся.'; }; });"""),
    ("автопереключение периода снято", "пустой-месяц-показывает-всё-время",
     "addEventListener('DOMContentLoaded', () => { S.wtPeriodChosen = true; });"),
    ("списки дат видны без дат", "без-дат-списков-нет-одна-строка",
     _стиль("#compare-row[hidden] { display: flex !important; }")),
    ("выбор фото не сброшен (прежний undefined)", "повтор-сохранения-не-шлёт-запросов",
     """addEventListener('DOMContentLoaded', () => { window.очиститьВыборФотоТела = function () {
        bodyPhotoFiles.front = bodyPhotoFiles.side = bodyPhotoFiles.back = undefined; }; });"""),
    ("невыбранная активность прежним тусклым цветом", "активность-текст-4.5",
     _стиль("#rg-act .v2-choice-item:not(.active) { color: rgb(90, 96, 115) !important; }")),
    ("значок ключа отдельной строкой (прежний flex-wrap)", "значок-ключа-в-строке-текста",
     _стиль("#tab-profile .scale-reauth { display: flex !important; flex-wrap: wrap !important; }")),
    ("кнопка карточки весов на 8 px правее", "левый-край-в-карточках",
     _стиль("#tab-profile .btn-block, #tab-profile .scale-drop { margin-left: 8px !important; }")),
]


def контроль():
    print("ЧИСТЫЙ ПРОГОН")
    н, п = проверка(печать=False)
    if н or п:
        print("КОНТРОЛЬ НЕДЕЙСТВИТЕЛЕН: грязная основа (находок %d, пропусков %d)" % (н, п))
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
    print("ВКЛАДКИ «ВЕС» И «ПРОФИЛЬ»")
    н, п = проверка()
    print("ИТОГ: находок %d, пропусков %d" % (н, п))
    sys.exit(1 if н else (2 if п else 0))


if __name__ == "__main__":
    main()
