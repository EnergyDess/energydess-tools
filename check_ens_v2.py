# -*- coding: utf-8 -*-
"""ПРОВЕРКА 66: РАЗДЕЛ ENSHROUDED ПОСЛЕ РЕДИЗАЙНА (№352, «enshrouded-1»).

ПРОВЕРКА, код 1 при находке, 2 — замерить нечем (стенда нет, карточек 0).

ЗАЧЕМ ОТДЕЛЬНАЯ ПРОБА. Проверка 60 спрашивает ЦВЕТ и молчит про всё
остальное: она не видит ни моноширинной гарнитуры, ни числа колонок,
ни того, что подпись слота переносится по слогам. Проверка 56 меряет
края шапки инструмента и про содержимое раздела не знает. Вопросы
«сколько колонок в сетке», «стоят ли низы карточек ряда вровень»
и «совпал ли заголовок группы с заголовком раздела аптечки» не задавал
никто.

ЧТО СПРАШИВАЕТСЯ:
  · моноширинных элементов со своим текстом — ноль (гарнитура
    ВЫЧИСЛЕННАЯ, а не имя класса: класс может стоять и не применяться,
    проверка 21 ловит ровно это);
  · колонок сетки — по ПОРОГАМ ШИРИНЫ СЕТКИ (5 от 1800, 4 от 1400,
    3 от 1100, 2 от 700, ниже одна): решение владельца, письмо
    «enshrouded-2». Прежняя таблица «окно → колонок» разобрана
    у самой константы ниже;
  · низ карточек в ряду вровень (разброс ≤ 1 px), как в аптечке;
  · подписи слотов в ОДНУ строку на всех трёх ширинах;
  · заголовок группы совпадает с заголовком раздела аптечки (`.apt-sec-h`)
    по кеглю, весу, регистру, разрядке и линии — ЦВЕТ при этом свой,
    и это не послабление: у обоих он равен `--v2-tool` своего
    инструмента, то есть совпадает ПРАВИЛО, а не значение.

ЗАГОЛОВОК АПТЕЧКИ МЕРИТСЯ НА ЖИВОМ ЭКРАНЕ, а не вписан числами: вписанное
разошлось бы с токеном молча — ровно то, чего избегает проверка 63,
сравнивая панели между собой, а не с числом.

Браузер ВИДИМЫЙ (§6.0.3): меряются ширины и число колонок, а headless
прячет полосу прокрутки без изъятия места — все ширины вышли бы
завышенными.

КЛЮЧИ:
  --ширина N     одна ширина вместо трёх
  --контроль     подлоги (по одному на правило), каждый обязан быть
                 назван СВОИМ шагом
  --прогон       путь человека: отметить предмет, снять отметку,
                 дубликаты, редкость и уровень, поиск, отбор.
                 В РЯД НЕ ИДЁТ — пишет в базу стенда.
"""
import os
import sys

try:
    import probe_guard  # noqa: F401  ПРОПУСК вместо трассы (§6.0.1)
except ImportError:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

КОРЕНЬ = os.path.dirname(os.path.abspath(__file__))
ШИРИНЫ = (1600, 1280, 390)
# КОЛОНКИ СПРАШИВАЮТСЯ У ШИРИНЫ СЕТКИ, А НЕ У ШИРИНЫ ОКНА (№352,
# «enshrouded-2»).
#
# Стояло `КОЛОНОК = {1600: 4, 1280: 3, 390: 1}` — решение владельца
# письма «enshrouded-1». Оно было верно, пока колонка содержимого
# у всех инструментов одна: тогда ширина окна задавала ширину сетки
# однозначно. Письмо «enshrouded-2» завело Enshrouded частный потолок
# (`body.v2-wide`), и та же ширина окна стала давать разную ширину
# сетки — таблица «окно → колонок» превратилась бы в число, которое
# ни из чего не следует, и на 1600 печатала бы находку про исправное
# (сетка там 1246, порог четырёх колонок — 1400).
#
# ПОРОГИ БЕРУТСЯ У `check_ens_wide` ИМПОРТОМ: второй список порогов
# разошёлся бы с первым молча (§6.0.7), а он же повторяет `@container`
# в `static/enshrouded.css`.
from check_ens_wide import ожидаем_колонок  # noqa: E402

ЗАМЕР = r"""
() => {
  const видим = e => e.checkVisibility({checkOpacity: true, checkVisibilityCSS: true});
  const свой = e => [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
  const имя = e => (e.id ? '#' + e.id : '') + '.' + String(e.className).split(' ')[0];

  // МОНОШИРИННЫЕ — ПО ВЫЧИСЛЕННОЙ ГАРНИТУРЕ, а не по имени класса
  const моно = [...document.querySelectorAll('body *')]
    .filter(e => видим(e) && свой(e)
                 && /mono/i.test(getComputedStyle(e).fontFamily))
    .map(имя);

  // СЕТКА: колонок — по числу дорожек, посчитанных браузером
  const сетка = document.querySelector('.sets-grid');
  const колонок = сетка
    ? getComputedStyle(сетка).gridTemplateColumns.split(/\s+/).filter(Boolean).length : 0;
  // ШИРИНА СЕТКИ — то, у чего теперь спрашиваются пороги колонок
  // (см. `ожидаем_колонок` ниже).
  const ширина_сетки = сетка ? +сетка.getBoundingClientRect().width.toFixed(1) : 0;
  const карточки = [...document.querySelectorAll('.set-card')];

  // НИЗ КАРТОЧЕК В РЯДУ: ряд — строка сетки ПО ФАКТУ, по совпадению
  // верха карточки; число колонок задаёт CSS, и вписанное в пробу
  // разошлось бы с ним молча.
  const ряды = {};
  for (const к of карточки) {
    const y = Math.round(к.getBoundingClientRect().top);
    const сл = к.querySelector('.slots');
    const пр = к.querySelector('.ens-pbar');
    (ряды[y] = ряды[y] || []).push({
      слоты: сл ? +сл.getBoundingClientRect().top.toFixed(1) : null,
      полоса: пр ? +пр.getBoundingClientRect().top.toFixed(1) : null,
    });
  }
  let разброс = 0, рядов = 0;
  for (const y in ряды) {
    const строка = ряды[y];
    if (строка.length < 2) continue;
    рядов++;
    for (const поле of ['слоты', 'полоса']) {
      const v = строка.map(с => с[поле]).filter(x => x !== null);
      if (v.length > 1) разброс = Math.max(разброс, Math.max(...v) - Math.min(...v));
    }
  }

  // ПОДПИСИ СЛОТОВ: строк считается по высоте коробки, делением
  // на межстрочный — перенос делает браузер, и в исходнике его
  // не видно вовсе.
  const подписи = [...document.querySelectorAll('.slot-lbl')].filter(видим);
  const многострочные = [], усечённые = [];
  for (const п of подписи) {
    const ст = getComputedStyle(п);
    const строк = Math.round(п.getBoundingClientRect().height / parseFloat(ст.lineHeight));
    if (строк > 1) многострочные.push(п.textContent.trim());
    // УСЕЧЕНИЕ СЧИТАЕТСЯ ТОЛЬКО У ШТАТНЫХ СЛОТОВ. У собственных слотов
    // сета (`data-own`, набор головных уборов) короткого имени нет
    // вовсе, и многоточие там законно — полное имя в подсказке
    // и в окне предмета.
    if (!п.hasAttribute('data-own') && п.scrollWidth > п.clientWidth + 1)
      усечённые.push(п.textContent.trim() + ' (' + п.scrollWidth + '>'
                     + п.clientWidth + ')');
  }

  // БАННЕР: доля высоты карточки и отношение сторон коробки
  const б = карточки.length ? карточки[0].querySelector('.card-banner') : null;
  const кб = б ? б.getBoundingClientRect() : null;
  const кк = карточки.length ? карточки[0].getBoundingClientRect() : null;

  // СТРОКА ПОИСКА И СЧЁТЧИКИ. На узкой ширине счётчики обязаны стоять
  // ОТДЕЛЬНОЙ строкой (поиск занимает свою целиком), на десктопе —
  // в одной строке с поиском; перелива ряда нет нигде.
  const пс = document.querySelector('.ens-search');
  const сч = document.querySelector('.ens-stats');
  const рд = document.querySelector('.ens-bar-row');
  const кор = э => { const b = э.getBoundingClientRect();
    return {y: +b.y.toFixed(1), h: +b.height.toFixed(1),
            правый: +(b.x + b.width).toFixed(1)}; };
  const полоса = пс && сч && рд ? {
    в_одной_строке: кор(пс).y < кор(сч).y + кор(сч).h
                    && кор(сч).y < кор(пс).y + кор(пс).h,
    перелив: +(рд.scrollWidth - рд.clientWidth).toFixed(1),
    за_краем: +(кор(сч).правый - document.documentElement.clientWidth).toFixed(1),
  } : null;

  const зг = document.querySelector('.cat-name');
  const шапка = document.querySelector('.cat-hdr');
  const з = зг ? getComputedStyle(зг) : null;
  const ш = шапка ? getComputedStyle(шапка) : null;
  return {
    моно: [...new Set(моно)], моно_всего: моно.length,
    колонок, ширина_сетки, карточек: карточки.length, рядов,
    ширина_карточки: кк ? +кк.width.toFixed(1) : 0,
    разброс: +разброс.toFixed(1),
    полоса,
    подписей: подписи.length, многострочные: [...new Set(многострочные)],
    усечённые: [...new Set(усечённые)],
    баннер: кб && кк ? {высота: +кб.height.toFixed(1),
                        доля: +(кб.height / кк.height).toFixed(3),
                        отношение: +(кб.width / кб.height).toFixed(3)} : null,
    заголовок: з && ш ? {
      кегль: з.fontSize, вес: з.fontWeight, регистр: з.textTransform,
      разрядка: з.letterSpacing, цвет: з.color,
      рамка: ш.borderBottomWidth, отступ: ш.paddingBottom,
    } : null,
  };
}
"""

# ОКНО ПРЕДМЕТА СПРАШИВАЕТСЯ ОТДЕЛЬНО: оно закрыто, и общий замер
# его не видит по построению — элементы невидимы, а моноширинные
# и прописные считаются только у видимых.
ОКНО = r"""
() => {
  const о = document.getElementById('ens-item');
  if (!о) return null;
  const видим = e => e.checkVisibility({checkOpacity: true, checkVisibilityCSS: true});
  const свой = e => [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
  const имя = e => (e.id ? '#' + e.id : '') + '.' + String(e.className).split(' ')[0];
  const все = [...о.querySelectorAll('*')].filter(e => видим(e) && свой(e));
  return {
    открыто: о.classList.contains('open'),
    моно: все.filter(e => /mono/i.test(getComputedStyle(e).fontFamily)).map(имя),
    прописные: все.filter(e => getComputedStyle(e).textTransform === 'uppercase').map(имя),
    // ЦВЕТНЫЕ ТОЧКИ РЕДКОСТИ — их пять, и они обязаны РАЗЛИЧАТЬСЯ:
    // цвет там единственное, чем уровни отличаются на глаз.
    точки: [...о.querySelectorAll('.r-dot')]
      .map(э => getComputedStyle(э).backgroundColor),
  };
}
"""

АПТ_ЗАГОЛОВОК = r"""
() => {
  const з = document.querySelector('.apt-sec-h');
  const т = document.querySelector('.apt-sec-top');
  if (!з || !т) return null;
  const s = getComputedStyle(з), ts = getComputedStyle(т);
  return {кегль: s.fontSize, вес: s.fontWeight, регистр: s.textTransform,
          разрядка: s.letterSpacing, цвет: s.color,
          рамка: ts.borderBottomWidth, отступ: ts.paddingBottom};
}
"""

# ЦВЕТ ИНСТРУМЕНТА, РАСКРЫТЫЙ БРАУЗЕРОМ. Спрашивается у самой страницы,
# а не вписан: разойдись значение с токеном, сверка печатала бы
# «совпало» про чужой цвет.
ЦВЕТ_ИНСТРУМЕНТА = r"""
() => {
  // ВСТАВЛЯЕТСЯ ВНУТРЬ ОБОЛОЧКИ: `--v2-tool` объявлен на `.v2-shell`
  // (класс `.v2-tool-<инструмент>`), и узел вне её получает не цвет
  // инструмента, а умолчание — первый прогон дал `--v2-text`.
  const п = document.createElement('span');
  п.style.color = 'var(--v2-tool)';
  (document.querySelector('.v2-shell') || document.body).appendChild(п);
  const c = getComputedStyle(п).color;
  п.remove();
  return c;
}
"""

находок = 0
_строки = {}


def шаг(имя, условие, подробность="", собрано=None, отрицание=None):
    # `отрицание` — шаг спрашивает ОТСУТСТВИЕ (расхождений, переносов,
    # усечений), и пустой сбор там и есть успех. Ключ снимает класс
    # «пустой сбор» у проверки 33 и в самой пробе не участвует.
    _ = отрицание
    global находок
    if собрано is not None and собрано == 0:
        исход = "ПРОПУСК"
    else:
        исход = "ok" if условие else "ПЛОХО"
        находок += not условие
    _строки[имя] = исход
    print("  %-8s %s%s" % (исход, имя, (" — " + подробность) if подробность else ""))


def прогон(база, подлог=None, ширины=None):
    global находок
    находок = 0
    _строки.clear()
    from playwright.sync_api import sync_playwright
    import check_hover as ch
    import browser_window  # noqa: F401  окно — на втором мониторе
    ch.БАЗА = база
    ширины = ширины or ШИРИНЫ
    замеры, апт, цвет, окно = [], None, None, None
    with sync_playwright() as p:
        бр = p.chromium.launch(headless=False)
        try:
            for ш in ширины:
                кон = бр.new_context(viewport={"width": ш, "height": 1000},
                                     has_touch=ш < 640)
                стр = кон.new_page()
                if подлог:
                    стр.add_init_script(подлог)
                ch._войти(стр)
                стр.goto(база + "/enshrouded", wait_until="networkidle",
                         timeout=45000)
                стр.wait_for_timeout(1200)
                стр.mouse.move(1, 1)
                з = стр.evaluate(ЗАМЕР)
                замеры.append((ш, з))
                if окно is None:
                    # ОТКРЫВАЕТСЯ НАЖАТИЕМ по слоту (§6.3), а не вызовом
                    # `openPopup`: вызов проверял бы построитель, а не
                    # то, что до окна дотягивается рука.
                    if стр.locator(".slot .slot-btn").count():
                        стр.locator(".slot .slot-btn").first.click()
                        стр.wait_for_timeout(500)
                        окно = стр.evaluate(ОКНО)
                        стр.keyboard.press("Escape")
                        стр.wait_for_timeout(300)
                if цвет is None:
                    цвет = стр.evaluate(ЦВЕТ_ИНСТРУМЕНТА)
                if апт is None:
                    # ЗАГОЛОВОК РАЗДЕЛА АПТЕЧКИ — ОБРАЗЕЦ, и берётся он
                    # с ЖИВОГО экрана: панель лекарства открывается
                    # НАЖАТИЕМ кнопки «Инструкция» на карточке (§6.3).
                    стр.goto(база + "/medkit", wait_until="networkidle",
                             timeout=45000)
                    стр.wait_for_timeout(800)
                    кн = стр.locator("[data-doses]").first
                    if кн.count():
                        кн.click()
                        стр.wait_for_timeout(600)
                        апт = стр.evaluate(АПТ_ЗАГОЛОВОК)
                кон.close()
        finally:
            бр.close()

    карточек = sum(з["карточек"] for _, з in замеры)
    if not карточек:
        print("  ПРОПУСК — на стенде нет ни одного сета: замерить нечем")
        return 2

    моно = sum(з["моно_всего"] for _, з in замеры)
    имена = sorted({и for _, з in замеры for и in з["моно"]})
    шаг("моноширинных-нет", моно == 0,
        "%d  %s" % (моно, имена[:6]), собрано=карточек)

    плохо = [(ш, з["колонок"], ожидаем_колонок(з["ширина_сетки"]))
             for ш, з in замеры
             if з["колонок"] != ожидаем_колонок(з["ширина_сетки"])]
    шаг("колонок-по-порогам-ширины-сетки", not плохо,
        "; ".join("%d: сетка %.0f → %d, ждём %d"
                  % (ш, dict(замеры)[ш]["ширина_сетки"], к, ж)
                  for ш, к, ж in плохо)
        or "; ".join("%d: сетка %.0f → %d" % (ш, з["ширина_сетки"], з["колонок"])
                     for ш, з in замеры),
        отрицание="ширин без ожидаемого числа колонок нет")

    худший = max(замеры, key=lambda х: х[1]["разброс"])
    рядов = sum(з["рядов"] for _, з in замеры)
    шаг("низ-карточек-в-ряду-совпал", худший[1]["разброс"] <= 1.0,
        "худший разброс %.1f px на %d" % (худший[1]["разброс"], худший[0]),
        собрано=рядов)

    перенос = [(ш, з["многострочные"]) for ш, з in замеры if з["многострочные"]]
    подписей = sum(з["подписей"] for _, з in замеры)
    шаг("подписи-слотов-в-одну-строку", not перенос,
        "; ".join("%d: %s" % (ш, м[:4]) for ш, м in перенос)
        or "подписей %d" % подписей, собрано=подписей)
    # ОДНОЙ СТРОКИ МАЛО, и это нашёл контроль: подпись, зажатая
    # `nowrap` с многоточием, в одну строку встаёт ПО ПОСТРОЕНИЮ —
    # шаг выше остался бы зелёным и на «Нагруднике». Второй вопрос:
    # помещается ли штатная подпись целиком.
    усечено = [(ш, з["усечённые"]) for ш, з in замеры if з["усечённые"]]
    шаг("штатные-подписи-помещаются", not усечено,
        "; ".join("%d: %s" % (ш, у[:4]) for ш, у in усечено)
        or "усечённых нет", собрано=подписей)

    if апт is None:
        шаг("заголовок-группы-как-в-аптечке", bool(апт), "образца нет",
            собрано=0)
    else:
        свой = замеры[0][1]["заголовок"]
        разошлось = [к for к in ("кегль", "вес", "регистр", "разрядка",
                                 "рамка", "отступ")
                     if свой and свой[к] != апт[к]]
        шаг("заголовок-группы-как-в-аптечке", свой and not разошлось,
            "аптечка %s / раздел %s%s" % (
                апт, свой, ("; разошлось: " + ", ".join(разошлось))
                if разошлось else ""))
        # ЦВЕТ У НИХ РАЗНЫЙ ПО ПОСТРОЕНИЮ — у каждого свой инструмент.
        # Спрашивается не равенство значений, а ПРАВИЛО: цвет заголовка
        # равен `--v2-tool` своей страницы.
        шаг("цвет-заголовка-инструмента", свой and свой["цвет"] == цвет,
            "заголовок %s, --v2-tool %s" % (свой["цвет"] if свой else None, цвет))

    # СЧЁТЧИКИ НЕ ЛОМАЮТ СТРОКУ С ПОИСКОМ (блок 1.1). На 390 они
    # обязаны стоять ОТДЕЛЬНОЙ строкой, на десктопе — в одной с полем;
    # перелива ряда нет ни на одной ширине.
    полосы = [(ш, з["полоса"]) for ш, з in замеры if з["полоса"]]
    сломано = [(ш, п) for ш, п in полосы
               if п["перелив"] > 0 or п["за_краем"] > 0
               or п["в_одной_строке"] != (ш >= 640)]
    шаг("строка-поиска-и-счётчиков", not сломано,
        "; ".join("%d: %s" % (ш, п) for ш, п in (сломано or полосы)),
        собрано=len(полосы))

    if окно is None or not окно.get("открыто"):
        шаг("окно-предмета-на-v2", bool(окно), "окно не открылось",
            собрано=0)
    else:
        плохо = []
        if окно["моно"]:
            плохо.append("моноширинные: %s" % окно["моно"][:4])
        if окно["прописные"]:
            плохо.append("прописные: %s" % окно["прописные"][:4])
        if len(set(окно["точки"])) != 5:
            плохо.append("точек редкости различимых %d из 5"
                         % len(set(окно["точки"])))
        шаг("окно-предмета-на-v2", not плохо,
            "; ".join(плохо) or "моно 0, прописных 0, точек 5",
            отрицание="моноширинных, прописных и слипшихся точек нет")

    б = замеры[0][1]["баннер"]
    print("  ── баннер: %s" % б)
    print("  ── ширина карточки: %s" % "; ".join(
        "%d → %.1f" % (ш, з["ширина_карточки"]) for ш, з in замеры))
    return 1 if находок else 0


# ── ПОДЛОГИ ────────────────────────────────────────────────────────────
# Каждый ломает СВОЁ звено и обязан быть назван СВОИМ шагом: общий подлог
# закрыл бы находкой от одного правила молчание про другое.
ПОДЛОГИ = [
    ("моноширинная подпись счётчику", "моноширинных-нет", """
      const s = document.createElement('style');
      s.textContent = '.ens-stat-v { font-family: var(--v2-font-mono) !important; }';
      document.addEventListener('DOMContentLoaded', () => document.head.appendChild(s));
    """),
    ("длинная подпись слота", "штатные-подписи-помещаются", """
      const s = document.createElement('style');
      s.textContent = '.slot-lbl::after { content: "Нагрудник"; }'
        + '.slot-lbl { font-size: 13px; }';
      document.addEventListener('DOMContentLoaded', () => document.head.appendChild(s));
    """),
    ("прописная подпись в окне предмета", "окно-предмета-на-v2", """
      const s = document.createElement('style');
      s.textContent = '#ens-item .field-label { text-transform: uppercase !important; }';
      document.addEventListener('DOMContentLoaded', () => document.head.appendChild(s));
    """),
    # ПОДЛОГ САМ ЗАВОДИТ РАЗНИЦУ ВЫСОТ, А НЕ НАДЕЕТСЯ НА ДАННЫЕ (§8.0).
    #
    # Стояло: снять прижатие (`display: block`) плюс `white-space: nowrap`
    # названию. Работало, пока карточка узкая: при четырёх колонках
    # на 1600 она была 299.5 px, названия переносились по-разному,
    # и содержимое соседей выходило разной высоты — было чему разъехаться.
    # Письмо «enshrouded-2» дало на 1600 три колонки по 404.7 px, все
    # названия встали в одну строку, и подлог ПЕРЕСТАЛ СОСТАВЛЯТЬСЯ:
    # разброс 0.1 px при пороге 1.0, контроль печатал «НЕ НАЙДЕН»
    # про исправную пробу.
    #
    # Теперь разницу заводит сам подлог — дописывает второй карточке
    # длинный хвост имени, — и от ширины карточки он больше не зависит
    # ни на одной ширине окна.
    ("низ карточки не прижат", "низ-карточек-в-ряду-совпал", """
      const s = document.createElement('style');
      s.textContent = '.set-card { display: block !important; }'
        + '.card-body { display: block !important; }'
        + '.sets-grid .set-card:nth-child(2) .card-name::after'
        + ' { content: " — хвост имени, занимающий вторую строку"; }';
      document.addEventListener('DOMContentLoaded', () => document.head.appendChild(s));
    """),
]


def контроль(база):
    беда = 0
    for имя, шаг_имя, код in ПОДЛОГИ:
        print("\n── ПОДЛОГ: %s ──" % имя)
        прогон(база, подлог=код, ширины=(1600,))
        нашёл = _строки.get(шаг_имя) == "ПЛОХО"
        print("  %s — шаг «%s» %s" % ("НАЙДЕН" if нашёл else "НЕ НАЙДЕН",
                                      шаг_имя, _строки.get(шаг_имя)))
        беда += not нашёл
    print("\nподлогов %d · не найдено %d" % (len(ПОДЛОГИ), беда))
    return 1 if беда else 0


# ── ПУТЬ ЧЕЛОВЕКА (§6.3) ──────────────────────────────────────────────
# В РЯД НЕ ИДЁТ: пишет в базу стенда, а ряд обязан быть безопасным
# для любого прогона. Результат берётся С ЭКРАНА И ИЗ БАЗЫ: ответ
# сервера говорит о намерении, а не о том, что легло в строку.
СЧЁТЧИКИ = """() => ({
  предметы: document.getElementById('stPieces').textContent,
  сеты: document.getElementById('stDone').textContent,
})"""


def _из_базы(set_id, slot_id):
    """Строка отметки ИЗ БАЗЫ стенда, а не из ответа сервера."""
    import sqlite3
    путь = os.environ.get("DB_PATH", os.path.join(КОРЕНЬ, "app.db"))
    if "/data/" in путь.replace("\\", "/"):
        raise SystemExit("боевая база не открывается")
    с = sqlite3.connect("file:%s?mode=ro" % путь, uri=True)
    try:
        р = с.execute("SELECT owned, rarity, level, duplicates FROM "
                      "enshrouded_slots WHERE set_id=? AND slot_id=? "
                      "ORDER BY id DESC LIMIT 1", (set_id, slot_id)).fetchone()
    finally:
        с.close()
    return р


def прогон_человека(база):
    global находок
    находок = 0
    _строки.clear()
    from playwright.sync_api import sync_playwright
    import check_hover as ch
    import browser_window  # noqa: F401
    ch.БАЗА = база
    with sync_playwright() as p:
        бр = p.chromium.launch(headless=False)
        try:
            кон = бр.new_context(viewport={"width": 1600, "height": 1000})
            стр = кон.new_page()
            ch._войти(стр)
            стр.goto(база + "/enshrouded", wait_until="networkidle", timeout=45000)
            стр.wait_for_timeout(1200)

            # Берётся ПЕРВЫЙ НЕотмеченный слот: состояние стенда заранее
            # неизвестно, и «отметить уже отмеченное» замерило бы ноль.
            цель = стр.evaluate("""() => {
              for (const с of document.querySelectorAll('.slot')) {
                if (!с.hasAttribute('data-r'))
                  return {set: с.dataset.set, slot: с.dataset.slot};
              }
              return null;
            }""")
            шаг("есть-неотмеченный-слот", bool(цель), str(цель),
                собрано=1 if цель else 0)
            if not цель:
                return 2
            до = стр.evaluate(СЧЁТЧИКИ)

            сел = '.slot[data-set="%s"][data-slot="%s"]' % (цель["set"], цель["slot"])
            стр.eval_on_selector(сел, "э => э.scrollIntoView({block:'center'})")
            стр.click(сел + " .slot-btn")
            стр.wait_for_timeout(400)
            шаг("окно-предмета-открылось",
                стр.locator("#ens-item.modal-ov.open, .modal-ov.open").count() > 0)

            стр.click("#ens-item label.toggle")
            стр.wait_for_timeout(600)
            после = стр.evaluate(СЧЁТЧИКИ)
            ждём = "%d/%s" % (int(до["предметы"].split("/")[0]) + 1,
                              до["предметы"].split("/")[1])
            шаг("счётчик-предметов-вырос-на-один", после["предметы"] == ждём,
                "%s → %s (ждём %s)" % (до["предметы"], после["предметы"], ждём))
            # СЧЁТЧИК СЕТОВ — ВТОРОЕ ОЖИДАЕМОЕ, и оно «без изменений»:
            # отмечен ОДИН предмет из пяти, сет целым не стал. Молчаливо
            # его не проверять значило бы спрашивать половину.
            шаг("счётчик-сетов-по-ожидаемому", после["сеты"] == до["сеты"],
                "%s → %s (сет не собран — ждём прежнее)" % (до["сеты"], после["сеты"]))
            шаг("отметка-легла-в-базу",
                bool(_из_базы(цель["set"], цель["slot"])
                     and _из_базы(цель["set"], цель["slot"])[0]),
                str(_из_базы(цель["set"], цель["slot"])))

            # ДУБЛИКАТЫ: плюс и минус
            стр.click("#ensDupeUp")
            стр.wait_for_timeout(400)
            д1 = стр.text_content("#ensDupeVal")
            стр.click("#ensDupeDown")
            стр.wait_for_timeout(400)
            д0 = стр.text_content("#ensDupeVal")
            шаг("дубликаты-плюс-и-минус", (д1, д0) == ("1", "0"),
                "+ → %s, − → %s" % (д1, д0))

            # РЕДКОСТЬ И УРОВЕНЬ — переживают перезагрузку
            стр.click('#ensRar [data-r="rare"]')
            стр.wait_for_timeout(300)
            стр.fill("#ensLvl", "42")
            стр.dispatch_event("#ensLvl", "change")
            стр.wait_for_timeout(600)
            стр.reload(wait_until="networkidle")
            стр.wait_for_timeout(1200)
            р = _из_базы(цель["set"], цель["slot"])
            шаг("редкость-и-уровень-в-базе", bool(р) and р[1] == "rare" and р[2] == 42,
                str(р))
            вид = стр.evaluate("""(с) => {
              const э = document.querySelector(с);
              return э ? {r: э.getAttribute('data-r'),
                          lvl: (э.querySelector('.slot-lvl')||{}).textContent} : null;
            }""", сел)
            шаг("слот-на-экране-после-перезагрузки",
                bool(вид) and вид["r"] == "rare" and вид["lvl"] == "42", str(вид))

            # СНЯТЬ ОТМЕТКУ — счётчик возвращается
            стр.eval_on_selector(сел, "э => э.scrollIntoView({block:'center'})")
            стр.click(сел + " .slot-btn")
            стр.wait_for_timeout(400)
            стр.click("#ens-item label.toggle")
            стр.wait_for_timeout(600)
            назад = стр.evaluate(СЧЁТЧИКИ)
            шаг("счётчик-вернулся", назад["предметы"] == до["предметы"],
                "%s → %s" % (после["предметы"], назад["предметы"]))
            стр.keyboard.press("Escape")
            стр.wait_for_timeout(300)

            # ПОИСК, ОТБОР, ПУСТАЯ ВЫДАЧА
            имя = стр.text_content(".card-name")
            стр.fill("#searchInput", имя[:6])
            стр.wait_for_timeout(500)
            найдено = стр.locator(".set-card").count()
            шаг("поиск-по-названию", 0 < найдено < 90,
                "«%s» → %d карточек из 90" % (имя[:6], найдено))
            стр.fill("#searchInput", "щщщ-такого-нет")
            стр.wait_for_timeout(500)
            шаг("пустая-выдача-названа",
                стр.locator(".empty-state").count() > 0
                and стр.locator(".set-card").count() == 0,
                "карточек %d" % стр.locator(".set-card").count())
            стр.fill("#searchInput", "")
            стр.wait_for_timeout(400)
            стр.click('.ens-tab[data-cat="blacksmith"]')
            стр.wait_for_timeout(500)
            отбор = стр.evaluate("""() => ({
              карточек: document.querySelectorAll('.set-card').length,
              групп: document.querySelectorAll('.cat-sec').length,
              чип: document.querySelector('.ens-tab[data-cat=blacksmith]')
                     .classList.contains('is-active'),
              обещано: +document.getElementById('tc-blacksmith').textContent,
            })""")
            шаг("отбор-по-категории",
                отбор["чип"] and отбор["групп"] == 1
                and отбор["карточек"] == отбор["обещано"],
                str(отбор))

            # СОБРАННЫЙ СЕТ: рамка и галочка
            собран = стр.evaluate("""() => {
              const к = [...document.querySelectorAll('.set-card')]
                .find(c => c.classList.contains('is-done'));
              if (!к) return null;
              return {рамка: getComputedStyle(к).borderTopColor,
                      галочка: !!к.querySelector('.set-done-mark')};
            }""")
            цвет = стр.evaluate(ЦВЕТ_ИНСТРУМЕНТА)
            шаг("собранный-сет-рамка-и-галочка",
                bool(собран) and собран["галочка"] and собран["рамка"] == цвет,
                "%s, --v2-tool %s" % (собран, цвет),
                собрано=1 if собран else 0)
            кон.close()
        finally:
            бр.close()
    print("\nнаходок %d" % находок)
    return 1 if находок else 0


def main():
    import check_hover as ch
    база = ch.БАЗА
    print("=" * 74)
    print("ПРОВЕРКА 66 — раздел Enshrouded после редизайна")
    print("=" * 74)
    if "--контроль" in sys.argv:
        return контроль(база)
    if "--прогон" in sys.argv:
        return прогон_человека(база)
    ширины = None
    if "--ширина" in sys.argv:
        ширины = (int(sys.argv[sys.argv.index("--ширина") + 1]),)
    код = прогон(база, ширины=ширины)
    print("\nнаходок %d" % находок)
    return код


if __name__ == "__main__":
    sys.exit(main())
