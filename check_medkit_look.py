# -*- coding: utf-8 -*-
"""ОБЛИК АПТЕЧКИ И ЛАУНЧЕРА — числа, по которым принимают решения.

═══════════════════════════════════════════════════════════════════════
ЧТО ЭТО
═══════════════════════════════════════════════════════════════════════

МЕРКА, а не проверка: кода «правильно» у неё нет, код возврата всегда 0.
Сколько пикселей должна занимать плитка фото и сколько колонок держать
лаунчер — решение об ОБЛИКЕ, и порога тут назначать нечему (то же
устройство, что у `check_ens_width.py` и `check_metrics.py`).

Отвечает на четыре вопроса, и все четыре завела постановка задачи 166:

  D.5  сколько пикселей до первой карточки на 390 — ряд чипов там
       занимал семь строк, и на телефоне были видны одни фильтры;
  D.6  какую долю карточки занимает плитка фото;
  D.7  сколько колонок у лаунчера на 2560 — пятая карточка стояла одна;
  B.1  видна ли кнопка панели ассистента и открывается ли панель.

═══════════════════════════════════════════════════════════════════════
ШИРИНЫ — 1920, 2560 И 390
═══════════════════════════════════════════════════════════════════════

У владельца ДВА монитора, 1920 и 2560. Мерить 1440 значит мерить
ширину, которой никто не видит: ровно эту ошибку разбирала задача 143,
и повторять её здесь незачем.

═══════════════════════════════════════════════════════════════════════
ЗАПУСК
═══════════════════════════════════════════════════════════════════════

    py make_local_user.py --seed
    py -m uvicorn main:app --port 8899
    py check_medkit_look.py

Браузер и поднятое приложение. В ряды §6.0.2 НЕ входит.
"""
import asyncio
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

БАЗА = os.environ.get("MEDKIT_BASE", "http://127.0.0.1:8899")
ПОЧТА = "screenshot@local.dev"
ПАРОЛЬ = "Screenshot-Local-2026"
ШИРИНЫ = [int(ш) for ш in
          os.environ.get("LOOK_WIDTHS", "2560,1920,390").split(",")]

# РЕЖИМ ПУСТОГО ЭКРАНА. Он ОПУСТОШАЕТ стенд, поэтому включается ЯВНО
# и говорит об этом ДО прогона, а не после (то же устройство, что
# у `check_medkit_ui.py --пустое`).
ПУСТОЕ = "--пустое" in sys.argv


async def _войти(pg):
    await pg.goto(БАЗА + "/login", wait_until="domcontentloaded")
    await pg.fill("input[name=email]", ПОЧТА)
    await pg.fill("input[name=password]", ПАРОЛЬ)
    if await pg.query_selector(".cf-turnstile"):
        for _ in range(60):
            if await pg.evaluate(
                    "() => { const t = document.querySelector("
                    "'[name=\"cf-turnstile-response\"]'); return t && t.value; }"):
                break
            await pg.wait_for_timeout(500)
    await pg.click("button[type=submit]")
    await pg.wait_for_load_state("networkidle")
    if "/login" in pg.url:
        raise SystemExit("ВХОД НЕ СОСТОЯЛСЯ — мерить нечего")


ЗАМЕР = """() => {
  const п = (с) => document.querySelector(с);
  const кор = (э) => э ? э.getBoundingClientRect() : null;
  const карт = п('.apt-card');
  const плитка = карт ? карт.querySelector('.apt-ph') : null;
  const ккор = кор(карт), пкор = кор(плитка);
  /* ДО ПЕРВОЙ КАРТОЧКИ — от верха документа, а не от верха окна:
     окно можно прокрутить, а вопрос про то, сколько занимает всё,
     что стоит ВЫШЕ карточек */
  const доКарточки = карт
    ? Math.round(карт.getBoundingClientRect().top + window.scrollY) : null;
  const сетка = п('.apt-grid');
  let колонок = null;
  if (сетка) {

    колонок = getComputedStyle(сетка).gridTemplateColumns.split(' ').length;
  }
  const кнопка = п('#apt-ai-open');
  return {
    доКарточки,
    карточка: ккор ? Math.round(ккор.width) : null,
    карточкаВысота: ккор ? Math.round(ккор.height) : null,
    плитка: пкор ? Math.round(пкор.height) : null,
    доляПлитки: (пкор && ккор) ? +(пкор.height / ккор.height).toFixed(3) : null,
    колонок,
    чиповРядов: (() => {
      const ч = [...document.querySelectorAll('#apt-chips .chip')]
        .filter(э => !э.hidden);
      const верх = new Set(ч.map(э => Math.round(э.getBoundingClientRect().top)));
      return {штук: ч.length, рядов: верх.size};
    })(),
    кнопкаАссистента: кнопка ? {
      есть: true,
      видна: !!(кнопка.offsetWidth || кнопка.offsetHeight),
      ширина: Math.round(кнопка.getBoundingClientRect().width),
    } : {есть: false},
    высотаСтраницы: Math.round(document.body.scrollHeight),
  };
}"""

ЛАУНЧЕР = """() => {
  const сетка = document.querySelector('.tools-grid, .tool-grid, .cards-grid');
  if (!сетка) return {найдено: false};
  const карточки = [...сетка.querySelectorAll('.tool-card')];
  const верх = new Map();
  карточки.forEach(к => {
    const t = Math.round(к.getBoundingClientRect().top);
    верх.set(t, (верх.get(t) || 0) + 1);
  });
  return {
    найдено: true,
    карточек: карточки.length,
    ряды: [...верх.values()],
    ширинаКарточки: карточки.length
      ? Math.round(карточки[0].getBoundingClientRect().width) : null,
    колонок: getComputedStyle(сетка).gridTemplateColumns.split(' ').length,
  };
}"""


# ─────────────────────────────────────────────────────────────────────
# ЗАМЕРЫ ЗАХОДА 2026-08-25 (доводка после ed8c269)
#
# Три вопроса, и все три задал владелец, посмотрев на живой экран:
#
#   A  что видно на ПУСТОМ экране. Прошлый заход спрятал там чипы
#      категорий, и экран стал выглядеть мёртвым. Мерка перечисляет
#      органы поимённо, а не отвечает «да/нет»: «чипы спрятаны»
#      и «чипов нет в разметке» — разные вещи, и лечатся они по-разному;
#   B  геометрия панели ассистента: где висит первое сообщение
#      и сколько под ним пустоты. «Панель выглядит сломанной» — это
#      про долю пустого места, и её можно посчитать;
#   C  геометрия формы: на одном ли уровне подпись штрих-кода и подпись
#      свёрнутой ссылки, сколько строки занимает блок фото.
# ─────────────────────────────────────────────────────────────────────

ПУСТОЙ_ЭКРАН = r"""() => {
  const видно = (э) => {
    if (!э) return null;
    const к = э.getBoundingClientRect();
    return (к.width > 0 && к.height > 0) ? Math.round(к.height) : 0;
  };
  const п = (с) => document.querySelector(с);
  const чипы = [...document.querySelectorAll('#apt-chips .chip')];
  const виден = (э) => {
    const к = э.getBoundingClientRect();
    return к.width > 0 && к.height > 0;
  };
  return {
    приглашение: видно(п('#apt-empty-all')),
    поиск: видно(п('.apt-search')),
    рядЧипов: видно(п('#apt-chips')),
    легенда: видно(п('.apt-legend')),
    кнопкаШапки: видно(п('.apt-add')),
    кнопкаАссистента: видно(п('#apt-ai-open')),
    чипы: {
      вРазметке: чипы.length,
      видимых: чипы.filter(виден).length,
      подписи: чипы.filter(виден).map(э => э.textContent.trim()
                                            .replace(/\s+/g, ' ')),
    },
    /* ВЫСОТА ВСЕГО, ЧТО СТОИТ ВЫШЕ ПРИГЛАШЕНИЯ — «экран выглядит
       мёртвым» это про пустоту сверху, и её видно числом */
    доПриглашения: (() => {
      const э = п('#apt-empty-all');
      return э ? Math.round(э.getBoundingClientRect().top + window.scrollY) : null;
    })(),
    высотаСтраницы: Math.round(document.body.scrollHeight),
  };
}"""

ПАНЕЛЬ_ГЕОМЕТРИЯ = r"""() => {
  const п = (с) => document.querySelector(с);
  const кор = (с) => { const э = п(с); return э ? э.getBoundingClientRect() : null; };
  /* ТЕКСТ, А НЕ КОРОБКА. Первая версия сравнивала `top` элементов
     и печатала «зазор 0 px» И ДО правки, И ПОСЛЕ: воздух добавлен
     внутренним отступом, а он живёт ВНУТРИ коробки. То есть мерка
     отвечала на вопрос уже, чем задан, и правку объявила бы
     несделанной. Тот же класс, что у разъезда подписей ниже. */
  const текстКор = (сел) => {
    const э = document.querySelector(сел);
    if (!э) return null;
    const r = document.createRange();
    r.selectNodeContents(э);
    return r.getBoundingClientRect();
  };
  const шапка = кор('.apt-ai-head');
  const подсказка = текстКор('.apt-ai-sub');
  const лента = кор('.apt-ai-log');
  const бар = кор('.apt-ai-bar');
  const первое = кор('.apt-ai-msg');
  const сообщения = [...document.querySelectorAll('.apt-ai-msg')];
  const последнее = сообщения.length
    ? сообщения[сообщения.length - 1].getBoundingClientRect() : null;
  const подПоследним = (последнее && лента)
    ? Math.round(лента.bottom - последнее.bottom) : null;
  return {
    шапкаНиз: шапка ? Math.round(шапка.bottom) : null,
    подсказкаВерх: подсказка ? Math.round(подсказка.top) : null,
    подсказкаНиз: подсказка ? Math.round(подсказка.bottom) : null,
    /* ЗАЗОР ШАПКА→ПОДСКАЗКА и ПОДСКАЗКА→ПЕРВОЕ СООБЩЕНИЕ. Жалоба
       владельца («подсказка прилипла к заголовку, а под ней дыра») —
       это про разницу этих двух чисел */
    зазорШапкаПодсказка: (шапка && подсказка)
      ? Math.round(подсказка.top - шапка.bottom) : null,
    /* ПУСТОТА НАД ПЕРВЫМ СООБЩЕНИЕМ — это НЕ дефект, а прижатие
       содержимого книзу (B.3). Она равна незанятой высоте ленты
       и растёт с высотой окна; смотреть надо на пустоту ПОД
       последним сообщением */
    пустотаНадПервым: (подсказка && первое)
      ? Math.round(первое.top - подсказка.bottom) : null,
    лентаВысота: лента ? Math.round(лента.height) : null,
    сообщений: сообщения.length,
    /* ПУСТОТА ПОД ПОСЛЕДНИМ СООБЩЕНИЕМ — «три четверти высоты панели
       чернота». Доля от высоты ленты */
    подПоследним,
    доляПустоты: (подПоследним !== null && лента && лента.height)
      ? +(подПоследним / лента.height).toFixed(3) : null,
    подсказкаВнизу: (() => {
      const х = п('.apt-ai-hint');
      if (!х) return null;
      const к = х.getBoundingClientRect();
      return (к.width > 0 && к.height > 0) ? х.textContent.trim().slice(0, 40) : 0;
    })(),
    кнопокВРяду: [...document.querySelectorAll('.apt-ai-tools > *')]
      .filter(э => { const к = э.getBoundingClientRect();
                     return к.width > 0 && к.height > 0; })
      .map(э => э.textContent.trim().replace(/\s+/g, ' ')),
    барВерх: бар ? Math.round(бар.top) : null,
  };
}"""

ФОРМА_ГЕОМЕТРИЯ = r"""() => {
  const п = (с) => document.querySelector(с);
  const кор = (с) => { const э = п(с); return э ? э.getBoundingClientRect() : null; };
  /* ТЕКСТ, А НЕ КОРОБКА — по той же причине, что у панели выше.
     Замер 2026-08-25: коробки подписей стояли вровень (0 px),
     а текст разъезжался на 4 px, и это было видно глазом. Мерка
     по коробкам утверждала бы, что править нечего. */
  const текстКор = (э) => {
    if (!э) return null;
    const r = document.createRange();
    r.selectNodeContents(э);
    return r.getBoundingClientRect();
  };
  const корПодписи = (id) => текстКор(
    document.querySelector('label[for="' + id + '"]'));
  const подписьКода = корПодписи('apt-f-code');
  const сум = текстКор(document.querySelector('.apt-url-sum'));
  const полеКода = кор('#apt-f-code');
  const фотоГруппа = (() => {
    const э = document.querySelector('#apt-f-photo');
    if (!э) return null;
    const г = э.closest('.form-group');
    return г ? г.getBoundingClientRect() : null;
  })();
  /* СКОЛЬКО ЗВЁЗДОЧЕК В ФОРМЕ — обязательных полей по обещанию экрана.
     Считается по РАЗМЕТКЕ подписи, а не по списку в голове */
  const звёзд = [...document.querySelectorAll('.apt-form .field-label')]
    .filter(л => { const к = л.getBoundingClientRect();
                   return к.width > 0 && /\*/.test(л.textContent); })
    .map(л => л.textContent.replace(/заполнил ассистент/g, '')
                .trim().replace(/\s+/g, ' '));
  return {
    подписьКодаВерх: подписьКода ? Math.round(подписьКода.top) : null,
    ссылкаСуммаВерх: сум ? Math.round(сум.top) : null,
    /* РАЗЪЕЗД ПОДПИСЕЙ В ОДНОМ РЯДУ. Ноль — стоят вровень.

       НА УЗКОМ ЭКРАНЕ РЯД СХЛОПНУТ В КОЛОНКУ, и подписи стоят одна
       ПОД другой законно. Первая версия печатала там 137 px и читалась
       как находка — то есть мерка называла дефектом нормальную
       раскладку. Признак схлопывания: подписи не пересекаются
       по горизонтали. */
    вОдномРяду: (подписьКода && сум)
      ? (сум.left >= подписьКода.right - 1) : null,
    разъездПодписей: (подписьКода && сум)
      ? Math.round(сум.top - подписьКода.top) : null,
    полеКодаВерх: полеКода ? Math.round(полеКода.top) : null,
    фотоВысота: фотоГруппа ? Math.round(фотоГруппа.height) : null,
    /* «ЗАНИМАЕТ ЦЕЛУЮ ПОЛОСУ РАДИ ОДНОЙ КНОПКИ» — это про ШИРИНУ.
       Мерка сперва спрашивала одну высоту и правку не увидела */
    фотоОрган: (() => {
      const в = document.querySelector('#apt-f-photo');
      if (!в) return null;
      const орган = в.hidden ? в.closest('label') : в;
      const к = орган.getBoundingClientRect();
      const ряд = document.querySelector('.apt-photo-row')
                          .getBoundingClientRect();
      return {ширина: Math.round(к.width), высота: Math.round(к.height),
              доляРяда: +(к.width / ряд.width).toFixed(3),
              родная: !в.hidden};
    })(),
    звёзд: звёзд.length,
    звёздочки: звёзд,
    высотаФормы: (() => { const ф = кор('.apt-form');
                          return ф ? Math.round(ф.height) : null; })(),
  };
}"""


async def прогон():
    from playwright.async_api import async_playwright
    итог = {}
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for ширина in ШИРИНЫ:
            сенсор = ширина < 800
            ctx = await b.new_context(
                viewport={"width": ширина, "height": 900 if not сенсор else 844},
                has_touch=сенсор, is_mobile=сенсор, device_scale_factor=1)
            pg = await ctx.new_page()
            await _войти(pg)
            await pg.goto(БАЗА + "/medkit", wait_until="networkidle")
            await pg.add_style_tag(
                content="html, * { scroll-behavior: auto !important }")
            await pg.wait_for_timeout(500)
            медкит = await pg.evaluate(ЗАМЕР)
            if ПУСТОЕ:
                медкит["пустой"] = await pg.evaluate(ПУСТОЙ_ЭКРАН)
            # ПАНЕЛЬ ОТКРЫВАЕТСЯ — вопрос не «есть ли класс», а видно ли
            await pg.evaluate("() => аптАИОткрыть()")
            await pg.wait_for_timeout(500)
            медкит["панель"] = await pg.evaluate("""() => {
              const п = document.getElementById('apt-ai');
              const к = п.getBoundingClientRect();
              const в = document.getElementById('apt-ai-in');
              /* ЖИВОСТЬ ОРГАНА, а не наличие в дереве: `elementFromPoint`
                 в центре поля обязан вернуть его самого (§6.3) */
              const вк = в.getBoundingClientRect();
              const т = document.elementFromPoint(
                вк.left + вк.width / 2, вк.top + вк.height / 2);
              return {
                ширина: Math.round(к.width),
                внутриЭкрана: к.right <= window.innerWidth + 1 && к.left >= -1,
                полеЖивое: !!(т && (т === в || в.contains(т))),
                реплик: document.querySelectorAll('.apt-ai-msg').length,
              };
            }""")
            медкит["панельГеом"] = await pg.evaluate(ПАНЕЛЬ_ГЕОМЕТРИЯ)
            await pg.evaluate("() => аптАИЗакрыть()")
            await pg.wait_for_timeout(300)

            # ФОРМА. Открывается ТЕМ ЖЕ вызовом, что и у человека:
            # подставить класс `.open` руками значило бы мерить окно,
            # которое никто не открывал
            await pg.evaluate("() => аптОткрытьФорму()")
            await pg.wait_for_timeout(400)
            медкит["формаГеом"] = await pg.evaluate(ФОРМА_ГЕОМЕТРИЯ)
            await pg.evaluate("() => закрыть_модалку('apt-form')")
            await pg.wait_for_timeout(200)

            await pg.goto(БАЗА + "/", wait_until="networkidle")
            # АНИМАЦИЯ ПОЯВЛЕНИЯ ГЛУШИТСЯ, И ЭТО НЕ ПЕРЕСТРАХОВКА.
            # Карточки лаунчера появляются `.stagger-in` с разной
            # задержкой и со сдвигом по вертикали. Меря через 400 мс,
            # проба видела их НА РАЗНОЙ ВЫСОТЕ и печатала ряды
            # [3, 1, 1] там, где фактически [3, 2], — то есть объявляла
            # находкой собственную торопливость. Поймано сверкой
            # с прямым замером координат, а не чтением.
            #
            # Тот же класс, что недосчитанный переход у пиксельного
            # дифа (§6.0.3): врёт харнесса, а не код.
            await pg.add_style_tag(content=(
                # НЕ `animation: none`, А МГНОВЕННЫЙ ПРОИГРЫШ ДО КОНЦА.
                # `.stagger-in` объявляет `opacity: 0` У САМОГО ЭЛЕМЕНТА,
                # а видимость даёт анимация: выключив её, кадр получаешь
                # с НЕВИДИМЫМИ карточками. Замер геометрии при этом верен
                # (положение не смещается), а снимок — нет, и на первом
                # же кадре лаунчер вышел пустым.
                #
                # `duration: 1ms` доигрывает до конечного кадра, то есть
                # снимает и дрожание, и невидимость разом.
                "*, *::before, *::after { animation-duration: 1ms !important;"
                " animation-delay: 0s !important;"
                " transition-duration: 1ms !important;"
                " transition-delay: 0s !important }"))
            await pg.wait_for_timeout(400)
            лаунчер = await pg.evaluate(ЛАУНЧЕР)
            итог[ширина] = {"медкит": медкит, "лаунчер": лаунчер}
            await ctx.close()
        await b.close()
    return итог


def печать(итог):
    print("ОБЛИК АПТЕЧКИ И ЛАУНЧЕРА")
    print("=" * 72)
    for ширина, д in итог.items():
        м, л = д["медкит"], д["лаунчер"]
        print()
        print("── %d ──" % ширина)
        print("  D.5  до первой карточки: %s px   чипов %s в %s рядов"
              % (м["доКарточки"], м["чиповРядов"]["штук"],
                 м["чиповРядов"]["рядов"]))
        print("  D.6  карточка %sx%s, плитка фото %s px (%s от высоты)"
              % (м["карточка"], м["карточкаВысота"], м["плитка"],
                 м["доляПлитки"]))
        print("       колонок сетки аптечки: %s" % м["колонок"])
        print("  D.7  лаунчер: карточек %s, ряды %s, колонок %s, ширина %s"
              % (л.get("карточек"), л.get("ряды"), л.get("колонок"),
                 л.get("ширинаКарточки")))
        к = м["кнопкаАссистента"]
        print("  B.1  кнопка ассистента: %s"
              % ("видна, %s px" % к["ширина"] if к.get("видна")
                 else "НЕ ВИДНА" if к.get("есть") else "НЕТ В РАЗМЕТКЕ"))
        п = м["панель"]
        print("       панель: %s px, внутри экрана %s, поле живое %s, реплик %s"
              % (п["ширина"], п["внутриЭкрана"], п["полеЖивое"], п["реплик"]))
        print("       высота страницы: %s px" % м["высотаСтраницы"])
        г = м.get("панельГеом") or {}
        print("  B.2  панель: зазор шапка→подсказка %s px (по ТЕКСТУ), "
              "пустота над первым сообщением %s px"
              % (г.get("зазорШапкаПодсказка"), г.get("пустотаНадПервым")))
        print("  B.3  лента %s px, сообщений %s, пустоты под последним %s px "
              "(%s ленты)"
              % (г.get("лентаВысота"), г.get("сообщений"),
                 г.get("подПоследним"), г.get("доляПустоты")))
        print("  B.1  кнопки под полем: %s" % (г.get("кнопокВРяду"),))
        print("  B.4  подсказка про дозу под полем: %s"
              % ("НЕТ" if г.get("подсказкаВнизу") == 0
                 else repr(г.get("подсказкаВнизу"))))
        ф = м.get("формаГеом") or {}
        print("  C.1  звёздочек в форме: %s  %s"
              % (ф.get("звёзд"), ф.get("звёздочки")))
        print("  C.2  разъезд подписей «Штрих-код»↔«Своя ссылка»: %s"
              % ("%s px" % ф.get("разъездПодписей") if ф.get("вОдномРяду")
                 else "ряд схлопнут в колонку — вопрос неприменим"))
        о = ф.get("фотоОрган") or {}
        print("  C.3  блок фото %s px; орган выбора %sx%s (%s ряда), "
              "родное поле браузера: %s"
              % (ф.get("фотоВысота"), о.get("ширина"), о.get("высота"),
                 о.get("доляРяда"), о.get("родная")))
        print("       вся форма %s px" % ф.get("высотаФормы"))
        if м.get("пустой"):
            п = м["пустой"]
            print("  A    ПУСТОЙ ЭКРАН")
            print("       приглашение %s, поиск %s, ряд чипов %s, легенда %s"
                  % (п["приглашение"], п["поиск"], п["рядЧипов"], п["легенда"]))
            print("       кнопки шапки: «Вручную» %s, «ассистент» %s"
                  % (п["кнопкаШапки"], п["кнопкаАссистента"]))
            print("       чипов в разметке %s, видимых %s"
                  % (п["чипы"]["вРазметке"], п["чипы"]["видимых"]))
            print("       подписи: %s" % (п["чипы"]["подписи"],))
            print("       до приглашения %s px, страница %s px"
                  % (п["доПриглашения"], п["высотаСтраницы"]))
    print()
    print("Код возврата 0 всегда: это МЕРКА, а не проверка (§6.0.4).")



def удалить_всё():
    """Опустошает аптечку аккаунта съёмки ПРЯМО В БАЗЕ.

    Через базу, а не через эндпоинт: удаление позиции спрашивает
    подтверждение окном, и проходить его двадцать раз ради ЗАМЕРА —
    работа не про то. Файлы фото при этом остаются на томе сиротами,
    и это названо: мерка не заявляет, что убрала за собой всё.
    """
    import sqlite3
    from database import DB_PATH
    c = sqlite3.connect(DB_PATH)
    было = c.execute("SELECT COUNT(*) FROM medkit_items").fetchone()[0]
    c.execute("DELETE FROM medkit_item_categories")
    c.execute("DELETE FROM medkit_items")
    c.commit()
    стало = c.execute("SELECT COUNT(*) FROM medkit_items").fetchone()[0]
    c.close()
    print("   позиций было %d, стало %d" % (было, стало))


def main():
    if ПУСТОЕ:
        print("РЕЖИМ --пустое: стенд будет ОПУСТОШЁН (все позиции аптечки "
              "удалены). Сказано ДО прогона, а не после.")
        удалить_всё()
    печать(asyncio.run(прогон()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
