# -*- coding: utf-8 -*-
"""ОБЛИК И ПОЛНОТА ФОРМЫ АПТЕЧКИ: заведение и правка рядом.

МЕРКА, код возврата всегда 0 (кроме `--контроль`): «сколько пикселей
занимает форма» — решение об облике, а не о коде.

СПРАШИВАЕТСЯ ТО, ЧЕГО НЕ СПРАШИВАЛ НИКТО. Проход `check_medkit_ui`
доходит до формы и жмёт в ней кнопки, то есть отвечает «работает ли»;
`check_medkit_look` мерит СЕТКУ карточек и шторку. Вопрос «совпадают ли
ширины колонок от ряда к ряду» и «не потеряно ли поле после правки
раскладки» не задавала ни одна проба.

ЧЕТЫРЕ ВОПРОСА, И ОНИ РАЗНЫЕ:
  ПОЛЯ    — перечень органов ввода в каждом из двух режимов. Счёт
            до и после правки обязан совпасть: раскладка не имеет права
            терять поле, а потерю видно только списком.
  РЯДЫ    — ширины ячеек внутри ряда. Разъезд от ряда к ряду и есть
            то, на что жаловался владелец.
  ГАБАРИТ — высота формы и выход за край окна.
  ФОТО    — размер превью: по нему человек решает, та ли это пачка.

РЕЖИМ ОПОЗНАЁТСЯ ПО ЗАГОЛОВКУ, а не по тому, что мы передали:
`аптОткрытьФорму` может уйти в третий режим («общее»), и подписать
его «правкой» значило бы мерить не то, что подписано.

ПЕРЕМЕННЫЕ СТЕНДА ЧИТАЮТСЯ БЕЗ `window` (§5.8): `АПТ_ПОЗИЦИИ` объявлен
через `let`, свойства `window` он не создаёт вовсе, и обращение через
него напечатало бы пустоту. Ловушка срабатывала трижды — задачи 201,
249, 250; сторожит её `tests/test_stand_globals.py`.
"""
import asyncio
import io
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

БАЗА = os.getenv("HOVER_BASE", "http://127.0.0.1:8899")
ПОЧТА = os.getenv("MEDKIT_EMAIL", "screenshot@local.dev")
ПАРОЛЬ = os.getenv("MEDKIT_PASSWORD", "Screenshot-Local-2026")
ШИРИНЫ = [int(ш) for ш in os.getenv("FORM_WIDTHS", "2560,1920,390").split(",")]


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


# ── ЗАМЕР ────────────────────────────────────────────────────────────
#
# ПОЛЕ СЧИТАЕТСЯ ВИДИМЫМ ПО `checkVisibility`, а не по `offsetParent`:
# закрытый `<details>` прячет содержимое родным правилом, которого
# `offsetParent` не видит (тот же урок, что у проверки 20, задача 198).
ЗАМЕР = r"""() => {
  const форма = document.getElementById('apt-form-el');
  if (!форма) return {ошибка: 'формы нет в дереве'};
  const лист  = форма.closest('.modal-sh');
  const кор = э => { const r = э.getBoundingClientRect();
                     return {x: Math.round(r.x), y: Math.round(r.y),
                             w: Math.round(r.width), h: Math.round(r.height)}; };
  const видно = э => э.checkVisibility ? э.checkVisibility() : (э.offsetParent !== null);

  /* ПОЛЯ — все органы ввода формы, видимые и скрытые по отдельности.
     Скрытые считаются тоже: поле, спрятанное признаком формы выпуска,
     из формы не пропало, и путать «не показано сейчас» с «потеряно»
     нельзя (§6.0.1). */
  const органы = Array.from(форма.querySelectorAll(
      'input, select, textarea, .segmented, .apt-chips')).map(э => ({
    ид: э.id || (э.className || '').split(' ')[0],
    тег: э.tagName.toLowerCase(),
    тип: э.type || '',
    видно: видно(э),
    подпись: (() => {
      const г = э.closest('.form-group, .apt-switch, details');
      const л = г ? г.querySelector('.field-label, summary, .apt-switch-t') : null;
      return л ? (л.textContent || '').replace(/заполнил ассистент/g, '').trim() : '';
    })(),
  })).filter(п => п.тип !== 'hidden' && п.ид !== 'apt-f-photo-cam');

  /* РЯДЫ — ширины ячеек внутри каждого ряда сетки. Меряется ЯЧЕЙКА,
     а не поле: поле бывает у́же ячейки на кнопку рядом, и разъезд
     ячеек — это и есть разъезд сетки. */
  const ряды = Array.from(форма.querySelectorAll('.apt-row')).map((р, i) => {
    const ячейки = Array.from(р.children).filter(э => видно(э));
    return {
      н: i,
      класс: р.className,
      ячеек: ячейки.length,
      ширины: ячейки.map(э => Math.round(э.getBoundingClientRect().width)),
      левые:  ячейки.map(э => Math.round(э.getBoundingClientRect().x)),
    };
  });

  const прев = document.getElementById('apt-f-prev');
  const кнопка = форма.querySelector('.apt-photo-pick button');

  return {
    заголовок: (document.getElementById('apt-form-title') || {}).textContent || '',
    форма: кор(форма),
    лист: лист ? кор(лист) : null,
    /* ВЫСОТА ФОРМЫ, А НЕ ЛИСТА. Лист упирается в `max-height` окна
       и даёт ОДНО И ТО ЖЕ число при любой длине формы — первая версия
       пробы печатала 1014 px до правки и 1014 после, то есть врала
       постоянством (§6.0.1). Мерить надо содержимое. */
    высота_формы: Math.round(форма.scrollHeight),
    высота_листа: лист ? Math.round(лист.scrollHeight) : null,
    перелив_вбок: лист ? Math.round(лист.scrollWidth - лист.clientWidth) : null,
    перелив_страницы: Math.round(
        document.documentElement.scrollWidth - document.documentElement.clientWidth),
    органов: {всего: органы.length, видимых: органы.filter(п => п.видно).length},
    поля: органы,
    ряды: ряды,
    фото: {
      превью_видно: прев ? видно(прев) : false,
      превью: (прев && видно(прев)) ? кор(прев) : null,
      кнопка: кнопка ? кор(кнопка) : null,
    },
  };
}"""


ОТКРЫТЬ_ЗАВЕДЕНИЕ = "() => аптОткрытьФорму()"
# ПОЗИЦИЯ ИЩЕТСЯ ПО ФАКТУ, а не по номеру: первая карточка сегодня одна,
# завтра другая. Нужна позиция С ФОТО — иначе превью не снять вовсе.
ОТКРЫТЬ_ПРАВКУ = r"""() => {
  let ц = null;
  АПТ_ПОЗИЦИИ.forEach(п => {
    (п['группа'] || [п]).forEach(у => { if (!ц && у.photo) ц = у; });
  });
  if (!ц) ц = АПТ_ПОЗИЦИИ[0];
  аптОткрытьФорму(ц);
}"""


async def _снять(pg, ширина, открыть_js, метка):
    await pg.set_viewport_size({"width": ширина, "height": 1080})
    await pg.evaluate("() => { document.querySelectorAll('.modal-ov.open')"
                      ".forEach(м => м.classList.remove('open')); }")
    await pg.wait_for_timeout(150)
    await pg.evaluate(открыть_js)
    await pg.wait_for_timeout(500)
    д = await pg.evaluate(ЗАМЕР)
    # ПРЕВЬЮ МЕРИТСЯ В РАСКРЫТОМ «ДОПОЛНИТЕЛЬНО»: свёрнутый `<details>`
    # прячет его родным правилом, и «не показано» — верный ответ
    # на ДРУГОЙ вопрос. Раскрываем, меряем, сворачиваем обратно —
    # проба обязана оставить стенд таким, каким взяла (§6.0.3).
    await pg.evaluate("() => { const д = document.getElementById('apt-extra');"
                      " if (д) д.open = true; }")
    await pg.wait_for_timeout(250)
    д["фото"] = await pg.evaluate(
        "() => { const п = document.getElementById('apt-f-prev');"
        " const в = п && (п.checkVisibility ? п.checkVisibility()"
        " : п.offsetParent !== null);"
        " const r = в ? п.getBoundingClientRect() : null;"
        " const к = document.querySelector('.apt-photo-pick button');"
        " return {превью_видно: !!в,"
        " превью: r ? {w: Math.round(r.width), h: Math.round(r.height)} : null,"
        " кнопка: к ? {w: Math.round(к.getBoundingClientRect().width)} : null}; }")
    д["раскрыто_доп"] = await pg.evaluate(
        "() => { const э = document.getElementById('apt-extra-n');"
        " return э ? э.textContent : ''; }")
    await pg.evaluate("() => { const д = document.getElementById('apt-extra');"
                      " if (д) д.open = false; }")
    д["ширина"] = ширина
    д["метка"] = метка
    return д


def _печать(д):
    if д.get("ошибка"):
        print("  %s %s: ОШИБКА — %s" % (д["метка"], д["ширина"], д["ошибка"]))
        return
    о = д["органов"]
    print("  %-10s %5dpx  «%s»" % (д["метка"], д["ширина"], д["заголовок"]))
    print("      органов: %d (видимых %d) · ВЫСОТА ФОРМЫ %s px"
          " · лист %s · перелив вбок %s / страницы %s"
          % (о["всего"], о["видимых"], д["высота_формы"], д["высота_листа"],
             д["перелив_вбок"], д["перелив_страницы"]))
    for р in д["ряды"]:
        ш = р["ширины"]
        разъезд = (max(ш) - min(ш)) if ш else 0
        знак = "" if разъезд <= 1 else "  ←РАЗЪЕЗД"
        имя = р["класс"].replace("apt-row", "").strip() or "—"
        print("      ряд %d (%s): ячеек %d, ширины %s, разброс %d%s"
              % (р["н"], имя, р["ячеек"], ш, разъезд, знак))
    ф = д["фото"]
    if ф["превью"]:
        print("      превью фото: %d×%d px (в раскрытом «Дополнительно»)"
              % (ф["превью"]["w"], ф["превью"]["h"]))
    else:
        print("      превью фото: не показано")
    if д.get("раскрыто_доп"):
        print("      «Дополнительно»: %s" % д["раскрыто_доп"])


# ── МЕТКА ПРОИСХОЖДЕНИЯ ВЕЩЕСТВА (задача 251, блок C) ────────────
#
# ЗНАЧЕНИЙ ШЕСТЬ: пять кодов `medkit_defs.ИСТОЧНИК_ВЕЩЕСТВА` плюс
# ОТСУТСТВИЕ ЗАПИСИ. Последнее — не прочерк и не «неизвестно»: строки
# нет вовсе, потому что «происхождение неизвестно» стояло у 33 карточек
# из 38 и не сообщало ничего (задача 250, C.1).
#
# ЦЕЛЬ ИЩЕТСЯ ПО ФАКТУ — по коду в самой записи, а не по номеру
# позиции: seed раздаёт коды по одному на позицию, и какая из них
# сегодня какая, знать неоткуда.
ИСТОЧНИК_ЗАМЕР = r"""() => {
  const по = {};
  АПТ_ПОЗИЦИИ.forEach(п => {
    (п['группа'] || [п]).forEach(у => {
      const к = у['вещество_откуда'] || '(нет записи)';
      if (!по[к] && у.substance) по[к] = у.id;
    });
  });
  return по;
}"""


async def _источник(pg):
    """Показывается ли метка при каждом из шести значений."""
    коды = await pg.evaluate(ИСТОЧНИК_ЗАМЕР)
    строки = []
    for код, ид in sorted(коды.items()):
        await pg.evaluate(r"""(ид) => {
          let ц = null;
          АПТ_ПОЗИЦИИ.forEach(п => (п['группа'] || [п]).forEach(
              у => { if (у.id === ид) ц = у; }));
          аптОткрытьФорму(ц);
        }""", ид)
        await pg.wait_for_timeout(300)
        д = await pg.evaluate(r"""(ид) => {
          let ц = null;
          АПТ_ПОЗИЦИИ.forEach(п => (п['группа'] || [п]).forEach(
              у => { if (у.id === ид) ц = у; }));
          const э = document.getElementById('apt-f-sub-src');
          const видно = э && (э.checkVisibility ? э.checkVisibility()
                                                : э.offsetParent !== null);
          return {подпись: ц ? (ц['вещество_откуда_подпись'] || '') : '',
                  видно: !!видно,
                  текст: э ? (э.textContent || '') : ''};
        }""", ид)
        # СОВПАДЕНИЕ С ПОДПИСЬЮ СЕРВЕРА, а не «строка непустая»:
        # метка, показывающая ЧУЖОЙ текст, прошла бы вторую проверку
        # и была бы неправдой ровно в том поле, ради которого заведена.
        ждём = bool(д["подпись"])
        сошлось = (д["видно"] == ждём) and (not ждём or д["текст"] == д["подпись"])
        строки.append({"код": код, "подпись": д["подпись"], "видно": д["видно"],
                       "текст": д["текст"], "сошлось": сошлось})
    return строки


# ── ПОВЕДЕНИЕ: ЧТО РЕДИЗАЙН НЕ ИМЕЛ ПРАВА СЛОМАТЬ ────────────────
#
# Восемь вещей, названных постановкой поимённо. Спрашивается КАЖДАЯ
# ДЕЙСТВИЕМ, а не наличием в дереве: орган, который есть и до которого
# не дотянуться, работой не является (§6.3).
#
# ОРГАН СЧИТАЕТСЯ ЖИВЫМ ПО `elementFromPoint`, и это не педантизм:
# ровно так нашлись мёртвые поля загрузки картинки на экране каталога
# (задача 140) — мерка ответов сервера была зелёной при мёртвой форме.
async def _поведение(pg):
    шаги = []

    def шаг(имя, ок, факт=""):
        шаги.append({"имя": имя, "ок": bool(ок), "факт": факт})

    async def жив(сел):
        # ПРОКРУТКА ПЕРЕД ЗАМЕРОМ ОБЯЗАТЕЛЬНА. `elementFromPoint`
        # спрашивает про ОКНО, и орган ниже его нижнего края возвращает
        # null — первая версия пробы напечатала «жив=False» про
        # исправную кнопку выбора фото (§6.0.11, «под обвязкой»).
        # Человек до неё доходит прокруткой, и проба идёт тем же путём.
        await pg.evaluate("""(с) => {
          const э = document.querySelector(с);
          if (э) э.scrollIntoView({block: 'center', behavior: 'instant'});
        }""", сел)
        await pg.wait_for_timeout(120)
        return await pg.evaluate(r"""(с) => {
          const э = document.querySelector(с);
          if (!э) return false;
          if (э.disabled) return false;
          const r = э.getBoundingClientRect();
          if (!r.width || !r.height) return false;
          const ц = document.elementFromPoint(r.x + r.width / 2,
                                              r.y + r.height / 2);
          return !!(ц && (ц === э || э.contains(ц) || ц.contains(э)));
        }""", сел)

    # 1. ЕДИНИЦА СЛЕДУЕТ ЗА ФОРМОЙ ВЫПУСКА
    await pg.evaluate("() => аптОткрытьФорму()")
    await pg.wait_for_timeout(300)
    ед = {}
    for форма in ("tablet", "syrup", "ointment"):
        await pg.evaluate("""(ф) => {
          const с = document.getElementById('apt-f-form');
          с.value = ф; с.dispatchEvent(new Event('change'));
        }""", форма)
        await pg.wait_for_timeout(200)
        ед[форма] = await pg.evaluate(
            "() => (document.getElementById('apt-u-left') || {}).textContent || ''")
    шаг("единица-следует-за-формой",
        ед["tablet"] == "шт" and ед["syrup"] == "мл",
        "таблетки=%r сироп=%r мазь=%r" % (ед["tablet"], ед["syrup"], ед["ointment"]))

    # 2. КАЛЕНДАРЬ У «ГОДЕН ДО» И «ВСКРЫТО» ЖИВ И ВЫСТАВЛЯЕТ ДАТУ
    await pg.evaluate("""() => {
      const с = document.getElementById('apt-f-form');
      с.value = 'tablet'; с.dispatchEvent(new Event('change'));
    }""")
    await pg.wait_for_timeout(200)
    for ид, зн, имя in (("apt-f-exp", "2027-05", "годен-до"),
                        ("apt-f-open", "2026-09-01", "вскрыто")):
        живой = await жив("#" + ид)
        стало = await pg.evaluate("""(п) => {
          const э = document.getElementById(п[0]);
          if (!э) return null;
          э.value = п[1];
          э.dispatchEvent(new Event('input', {bubbles: true}));
          return э.value;
        }""", [ид, зн])
        шаг("календарь-" + имя, живой and стало == зн,
            "жив=%s значение=%r" % (живой, стало))

    # 3. КНОПКА «СВОЯ» ОТКРЫВАЕТ ОКНО КАТЕГОРИЙ
    #    Чип лежит в СВЁРНУТОМ ряду, и раскрытие — часть пути человека.
    await pg.evaluate("() => аптКатегорииРаскрыть()")
    await pg.wait_for_timeout(250)
    живой = await жив("#apt-f-cats [data-cats-open]")
    await pg.evaluate("() => document.querySelector("
                      "'#apt-f-cats [data-cats-open]').click()")
    await pg.wait_for_timeout(350)
    открылось = await pg.evaluate(
        "() => !!document.querySelector('#apt-cats.open')")
    await pg.evaluate("() => { const м = document.getElementById('apt-cats');"
                      " if (м) м.classList.remove('open'); }")
    шаг("своя-категория-открывает-окно", живой and открылось,
        "жив=%s окно=%s" % (живой, открылось))

    # 4. ВЫБОР КАТЕГОРИИ РАБОТАЕТ И СЧЁТЧИК ЗА НИМ СЛЕДУЕТ
    #    СПРАШИВАЕТСЯ У СВЁРНУТОГО БЛОКА: в раскрытом кнопка называется
    #    «Свернуть» по замыслу, и обе стороны сравнения дали бы одну
    #    строку — первая версия пробы печатала на этом БЕДУ про
    #    исправный код.
    await pg.evaluate("() => { const о = document.getElementById('apt-cats-fold');"
                      " if (о) o_свернуть(о); function o_свернуть(x)"
                      " { x.classList.remove('open'); } аптКатегорииПодпись(); }")
    await pg.wait_for_timeout(200)
    до = await pg.evaluate("() => (document.getElementById('apt-cats-more')"
                           " || {}).textContent || ''")
    await pg.evaluate("() => document.querySelector('#apt-f-cats [data-cat]').click()")
    await pg.wait_for_timeout(250)
    после = await pg.evaluate("() => (document.getElementById('apt-cats-more')"
                              " || {}).textContent || ''")
    выбран = await pg.evaluate(
        "() => !!document.querySelector('#apt-f-cats [data-cat].active')")
    шаг("категория-выбирается-и-счёт-идёт", выбран and до != после,
        "%r -> %r" % (до, после))

    # 5. СКАНЕР ШТРИХ-КОДА ОТКРЫВАЕТСЯ (внутри «Дополнительно»)
    await pg.evaluate("() => { const д = document.getElementById('apt-extra');"
                      " if (д) д.open = true; }")
    await pg.wait_for_timeout(250)
    живой = await жив("#apt-scan-field")
    шаг("сканер-жив", живой, "жив=%s" % живой)

    # 6. ВЫБОР ФОТО ЖИВ
    живой = await жив(".apt-photo-pick button")
    шаг("кнопка-фото-жива", живой, "жив=%s" % живой)

    # 7. СЧЁТЧИК «ДОПОЛНИТЕЛЬНО» СЛЕДИТ ЗА ПОЛЯМИ
    до_н = await pg.evaluate("() => (document.getElementById('apt-extra-n')"
                             " || {}).textContent || ''")
    await pg.evaluate("""() => {
      const э = document.getElementById('apt-f-note');
      э.value = 'проба';
      э.dispatchEvent(new Event('input', {bubbles: true}));
    }""")
    await pg.wait_for_timeout(200)
    после_н = await pg.evaluate("() => (document.getElementById('apt-extra-n')"
                                " || {}).textContent || ''")
    await pg.evaluate("""() => {
      const э = document.getElementById('apt-f-note');
      э.value = '';
      э.dispatchEvent(new Event('input', {bubbles: true}));
    }""")
    шаг("счётчик-дополнительно-считает", до_н != после_н,
        "%r -> %r" % (до_н, после_н))

    # 8. ОБЯЗАТЕЛЬНОСТЬ ПОЛЕЙ СО ЗВЁЗДОЧКОЙ
    обяз = await pg.evaluate(
        "() => ['apt-f-name','apt-f-exp'].map("
        "и => !!(document.getElementById(и)||{}).required)")
    шаг("обязательные-поля-обязательны", all(обяз), "required=%s" % обяз)

    # 9. «ЕЩЁ УПАКОВКА» ЕСТЬ В ПРАВКЕ И НЕТ В ЗАВЕДЕНИИ
    зав = await pg.evaluate(
        "() => (document.getElementById('apt-more-pack')||{}).hidden")
    await pg.evaluate(ОТКРЫТЬ_ПРАВКУ)
    await pg.wait_for_timeout(350)
    прав = await pg.evaluate(
        "() => (document.getElementById('apt-more-pack')||{}).hidden")
    живой = await жив("#apt-more-pack-btn")
    шаг("ещё-упаковка-только-в-правке", зав is True and прав is False and живой,
        "заведение скрыто=%s правка скрыта=%s жива=%s" % (зав, прав, живой))

    # 10. ПОДСТАНОВКА ИЗ СПРАВОЧНИКА СТАВИТ МЕТКУ
    #     Спрашивается не «есть ли функция», а ВСТАЁТ ЛИ МЕТКА:
    #     подстановка, о которой на экране ни слова, неотличима
    #     от выдумки (§5.8).
    подстановка = await pg.evaluate(r"""() => {
      const п = document.getElementById('apt-f-sub');
      const было = п.value;
      аптВещОткуда('справочник', 'из справочника');
      const э = document.getElementById('apt-f-sub-src');
      const вышло = э && !э.hidden && э.textContent === 'из справочника';
      п.value = было;
      return вышло ? 'ок' : 'метка не встала';
    }""")
    шаг("подстановка-ставит-метку", подстановка == "ок", подстановка)

    return шаги



# ── ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ ───────────────────────────────────────
#
# Подлоги кладутся В СТРАНИЦУ (`add_init_script`), кода они не трогают.
#
# У КАЖДОГО СТОИТ ДОКАЗАТЕЛЬСТВО — независимый замер того, что подлог
# СОБИРАЛСЯ изменить (§6.0.3). Без него «проба нашла» неотличимо
# от «проба нашла по другой причине»: исходов четыре, а вердикт один.
# Ровно на этом обжёгся заход 190, где подлог метил в чужой элемент
# и контроль печатал «проба не видит» про исправную пробу.
ПОДЛОГИ = {
    # ПОЛЕ ИСЧЕЗЛО ИЗ ФОРМЫ. Раскладка не имеет права терять поле,
    # а потерю видно только СПИСКОМ: высота при этом даже уменьшится,
    # то есть замер габарита такое пропустит по построению.
    "поле-удалено": {
        # ГОЛЫЙ КОД, А НЕ СТРЕЛОЧНАЯ ФУНКЦИЯ. `add_init_script`
        # исполняет текст КАК ЕСТЬ: обёртка `() => {…}` — выражение,
        # которое вычисляется и отбрасывается, то есть подлог
        # не исполняется вовсе. Первая версия контроля напечатала
        # «ПОДЛОГ НЕ СОСТОЯЛСЯ» на всех четырёх, и поймало это
        # ДОКАЗАТЕЛЬСТВО, а не вердикт (§6.0.3).
        # ПОЛЕ УЕЗЖАЕТ ИЗ ФОРМЫ, А НЕ ИЗ ДОКУМЕНТА. Первая версия
        # звала `remove()`, и `аптОткрытьФорму` падала на `.value`
        # у null — то есть подлог ломал не раскладку, а скрипт,
        # и проба отвечала стектрейсом вместо вердикта (урок задачи
        # 152: падение отвечает хуже, чем «не найдено»). Перенос
        # оставляет поле живым для скрипта и убирает его ИЗ ФОРМЫ —
        # ровно то, что должен ловить счёт полей.
        "js": """document.addEventListener('DOMContentLoaded', () => {
            const э = document.getElementById('apt-f-days');
            if (э) document.body.appendChild(э);
          });""",
        "режим": "поля",
        "ждём": "органов стало меньше",
    },
    # ЕДИНИЦА ПЕРЕСТАЛА СЛЕДОВАТЬ ЗА ФОРМОЙ ВЫПУСКА. Дефект молчащий:
    # поле работает, число вводится, просто «мл» осталось «шт».
    "единица-не-следует": {
        "js": """window.addEventListener('load', () => {
            window.аптФормаСменилась = function () {};
          });""",
        "режим": "поведение",
        "ждём": "единица-следует-за-формой",
    },
    # КАЛЕНДАРЬ МЁРТВ. Поле в дереве есть, до него дотягивается взгляд,
    # а дату выставить нечем — тот же класс, что мёртвые поля загрузки
    # картинки на экране каталога (задача 140).
    "календарь-мёртв": {
        # ПОДЛОГ ЦЕЛИТ В `аптРежимФормы`, а не в поле напрямую: она
        # ставит `disabled` КАЖДОМУ полю пачки при открытии формы,
        # то есть сбрасывала бы подлог в false. Первая версия
        # выставляла атрибут на `load` и печатала «ПОДЛОГ
        # НЕ СОСТОЯЛСЯ» — поймало это доказательство (§6.0.3).
        "js": """window.addEventListener('load', () => {
            const прежняя = window.аптРежимФормы;
            window.аптРежимФормы = function (общее, поз) {
              прежняя(общее, поз);
              ['apt-f-exp', 'apt-f-open'].forEach(и => {
                const э = document.getElementById(и);
                if (э) э.disabled = true;
              });
            };
          });""",
        "режим": "поведение",
        "ждём": "календарь-годен-до",
    },
    # МЕТКА ПРОИСХОЖДЕНИЯ НЕ ПОКАЗЫВАЕТСЯ. Ровно то состояние, в котором
    # форма жила до этого захода: значение есть, на экране его нет.
    "метка-источника-молчит": {
        "js": """window.addEventListener('load', () => {
            const э = document.getElementById('apt-f-sub-src');
            if (э) э.remove();
          });""",
        "режим": "источник",
        "ждём": "метка не показана ни при одном значении",
    },
}


async def _доказать(pg, имя):
    """НЕЗАВИСИМЫЙ замер того, что подлог собирался изменить."""
    if имя == "поле-удалено":
        return await pg.evaluate(
            "() => document.querySelectorAll('#apt-form-el input,"
            " #apt-form-el select, #apt-form-el textarea').length")
    if имя == "единица-не-следует":
        return await pg.evaluate("""() => {
          const с = document.getElementById('apt-f-form');
          с.value = 'syrup'; с.dispatchEvent(new Event('change'));
          return (document.getElementById('apt-u-left') || {}).textContent || '';
        }""")
    if имя == "календарь-мёртв":
        return await pg.evaluate(
            "() => ['apt-f-exp','apt-f-open'].map("
            "и => !!(document.getElementById(и)||{}).disabled)")
    if имя == "метка-источника-молчит":
        return await pg.evaluate("""() => {
          аптВещОткуда('справочник', 'из справочника');
          const э = document.getElementById('apt-f-sub-src');
          return э ? {есть: true, скрыта: !!э.hidden, текст: э.textContent}
                   : {есть: false};
        }""")
    return None


async def _контроль(p):
    print("ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ ФОРМЫ")
    print("=" * 72)
    плохих = 0
    for имя, п in ПОДЛОГИ.items():
        замеры = {}
        вердикты = {}
        for подложить in (False, True):
            br = await p.chromium.launch()
            ctx = await br.new_context(viewport={"width": 1920, "height": 1080})
            if подложить:
                await ctx.add_init_script(п["js"])
            pg = await ctx.new_page()
            await _войти(pg)
            await pg.goto(БАЗА + "/medkit", wait_until="networkidle")
            await pg.evaluate(ОТКРЫТЬ_ЗАВЕДЕНИЕ)
            await pg.wait_for_timeout(400)
            # ПРОБА, УПАВШАЯ НА ПОДЛОГЕ, ОТВЕЧАЕТ ХУЖЕ, ЧЕМ «НЕ НАЙДЕНО»:
            # стектрейс не говорит, увидела она дефект или споткнулась
            # о собственную оснастку (урок задачи 152). Падение здесь —
            # тоже находка, и называется оно словом.
            try:
                замеры[подложить] = await _доказать(pg, имя)
                if п["режим"] == "поведение":
                    шаги = await _поведение(pg)
                    вердикты[подложить] = any(
                        not ш["ок"] for ш in шаги if ш["имя"] == п["ждём"])
                elif п["режим"] == "источник":
                    строки = await _источник(pg)
                    вердикты[подложить] = any(not с["сошлось"] for с in строки)
                else:
                    д = await pg.evaluate(ЗАМЕР)
                    вердикты[подложить] = д["органов"]["всего"] < 21
            except Exception as e:
                замеры.setdefault(подложить, "исключение: %s" % type(e).__name__)
                вердикты[подложить] = True
            await br.close()

        # ПОДЛОГ ОБЯЗАН СОСТОЯТЬСЯ, и это отдельный вопрос от вердикта:
        # не состоялся — «проба не видит» относится к пустому месту.
        состоялся = замеры[False] != замеры[True]
        поймала = вердикты[True] and not вердикты[False]
        если_нет = ("ПОДЛОГ НЕ СОСТОЯЛСЯ" if not состоялся
                    else ("НЕ НАЙДЕН" if not вердикты[True]
                          else "ГРЯЗНАЯ ОСНОВА — проба находит и БЕЗ подлога"))
        print("  %-26s %s" % (имя, "НАЙДЕН" if (состоялся and поймала) else если_нет))
        print("      доказательство: чисто=%r  с подлогом=%r"
              % (замеры[False], замеры[True]))
        плохих += 0 if (состоялся and поймала) else 1
    print("")
    print("  подлогов %d, не найдено %d" % (len(ПОДЛОГИ), плохих))
    return 1 if плохих else 0


async def main():
    from playwright.async_api import async_playwright
    сохранить = "--сохранить" in sys.argv
    только_источник = "--источник" in sys.argv
    только_поведение = "--поведение" in sys.argv
    контроль = "--контроль" in sys.argv
    async with async_playwright() as p:
        if контроль:
            return await _контроль(p)
        br = await p.chromium.launch()
        ctx = await br.new_context(viewport={"width": 1920, "height": 1080})
        pg = await ctx.new_page()
        await _войти(pg)
        await pg.goto(БАЗА + "/medkit", wait_until="networkidle")

        if только_поведение:
            print("ПОВЕДЕНИЕ ФОРМЫ: что редизайн не имел права сломать")
            print("=" * 72)
            шаги = await _поведение(pg)
            плохих = 0
            for ш in шаги:
                знак = "OK  " if ш["ок"] else "БЕДА"
                print("  %s %-34s %s" % (знак, ш["имя"], ш["факт"]))
                плохих += 0 if ш["ок"] else 1
            print("")
            print("  шагов %d, плохих %d" % (len(шаги), плохих))
            await br.close()
            return 1 if плохих else 0

        if только_источник:
            print("МЕТКА ПРОИСХОЖДЕНИЯ ВЕЩЕСТВА В ФОРМЕ ПРАВКИ")
            print("=" * 72)
            строки = await _источник(pg)
            беда = 0
            for с in строки:
                знак = "ок" if с["сошлось"] else "БЕДА"
                print("  %-14s подпись сервера=%-30r метка видна=%-5s  %s"
                      % (с["код"], с["подпись"], с["видно"], знак))
                беда += 0 if с["сошлось"] else 1
            показано = sum(1 for с in строки if с["видно"])
            print("")
            print("  значений проверено: %d, метка показана при %d,"
                  " расхождений: %d" % (len(строки), показано, беда))
            await br.close()
            return 0

        итог = []
        print("ФОРМА АПТЕЧКИ: заведение и правка")
        print("=" * 72)
        for ш in ШИРИНЫ:
            for метка, js in (("заведение", ОТКРЫТЬ_ЗАВЕДЕНИЕ),
                              ("правка", ОТКРЫТЬ_ПРАВКУ)):
                д = await _снять(pg, ш, js, метка)
                итог.append(д)
                _печать(д)
            print()

        # ── СПИСОК ПОЛЕЙ: печатается один раз, по 1920 ──────────────
        зав = next((д for д in итог
                    if д["ширина"] == 1920 and д["метка"] == "заведение"), None)
        пр = next((д for д in итог
                   if д["ширина"] == 1920 and д["метка"] == "правка"), None)
        if зав and пр:
            print("ПОЛЯ ФОРМЫ (1920)")
            print("-" * 72)
            имена_з = [п["ид"] for п in зав["поля"]]
            имена_п = [п["ид"] for п in пр["поля"]]
            for п in зав["поля"]:
                в_пр = "да" if п["ид"] in имена_п else "НЕТ"
                print("  %-20s %-9s видно=%-3s в правке=%-3s «%s»"
                      % (п["ид"], п["тег"], "да" if п["видно"] else "нет",
                         в_пр, п["подпись"][:44]))
            for п in пр["поля"]:
                if п["ид"] not in имена_з:
                    print("  %-20s %-9s видно=%-3s ТОЛЬКО В ПРАВКЕ «%s»"
                          % (п["ид"], п["тег"], "да" if п["видно"] else "нет",
                             п["подпись"][:36]))
            print("\n  ИТОГО органов: заведение %d, правка %d"
                  % (len(имена_з), len(имена_п)))

        if сохранить:
            путь = sys.argv[sys.argv.index("--сохранить") + 1]
            io.open(путь, "w", encoding="utf-8").write(
                json.dumps(итог, ensure_ascii=False, indent=1))
            print("\nснимок замера: %s" % путь)
        await br.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
