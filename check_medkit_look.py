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
    py check_medkit_look.py --контроль   # ОБЯЗАТЕЛЬНО после правки мерки

Браузер и поднятое приложение. В ряды §6.0.2 НЕ входит.

С 2026-08-26 отвечает ещё на два вопроса (BACKLOG №176):

  E  РЯД ДЕЙСТВИЙ на карточке — доли, зазоры, есть ли у каждого рамка.
     Спрашивается у РАБОЧЕЙ карточки и у ПРОСРОЧЕННОЙ отдельно:
     действий там разное число, и «делят ровно» у каждой своё;
  F  ПУСТАЯ ВЫДАЧА ПОИСКА — одна ли система координат у частей блока,
     размер плитки значка и элементы, ПЕРЕЖИВШИЕ СВОЁ СОДЕРЖИМОЕ
     (легенда цветов срока и подпись сетки при нуле карточек).

Запрос набирается ТЕМ ЖЕ путём, что у человека, — через поле и его
обработчик: подставить `hidden=false` руками значило бы мерить блок,
который никто не показывал.
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
# ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ БЛОКОВ E и F. Подлоги кладутся В СТРАНИЦУ
# (`add_init_script`), кода экрана не трогают: проба обязана назвать
# разъезд, который они возвращают, — иначе её зелёный не значит ничего
КОНТРОЛЬ = "--контроль" in sys.argv


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
    /* ── СТРОКА УПРАВЛЕНИЯ И СОСЕДИ (BACKLOG №188) ──────────────────
       Три блока подряд — «Купить», строка поиска с действиями и ряд
       чипов — обязаны держать ОДНУ ширину. До 2026-08-28 ряд чипов
       мерился `fit-content`, то есть его ширина зависела от ЧИСЛА
       КАТЕГОРИЙ у человека, а не от раскладки: при 10 чипах на 2560
       правый край расходился со строкой на 514 px, при 3 — на 1483.
       На заполненном стенде этого НЕ ВИДНО (17 чипов дают 0), и ровно
       поэтому число нужно в мерке, а не в отчёте одного захода. */
    строкаУправления: (() => {
      const к = (с) => { const э = п(с); if (!э) return null;
        const r = э.getBoundingClientRect();
        return {left: Math.round(r.left), right: Math.round(r.right),
                w: Math.round(r.width)}; };
      const купить = к('.apt-buy'), строка = к('.apt-bar'), чипы = к('.apt-chips');
      const поиск = к('.apt-search'), действия = к('.apt-bar-act');
      const края = [купить, строка, чипы].filter(Boolean)
        .map(б => б.left + ':' + б.right);
      return {
        купить, строка, чипы, поиск, действия,
        краяСовпали: края.length === 3 && new Set(края).size === 1,
        /* ВОЗДУХ между поиском и группой действий. Отрицательный
           на узкой ширине — там они в РАЗНЫХ строках, и это
           не дефект, а перенос */
        воздух: (поиск && действия) ? действия.left - поиск.right : null,
        /* ДЕЙСТВИЯ У ПРАВОГО КРАЯ: их правый край совпадает
           с правым краем содержимого */
        уПравогоКрая: (действия && строка)
          ? Math.abs(действия.right - строка.right) <= 1 : null,
        чиповВидно: [...document.querySelectorAll('#apt-chips .chip')]
          .filter(ч => !ч.hidden).length,
      };
    })(),
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


# ─────────────────────────────────────────────────────────────────────
# ЗАМЕРЫ ЗАХОДА 2026-08-26 (BACKLOG №176, блоки A и B)
#
# ЧЕТЫРЕ ПУНКТА §6.0.3 — правка МЕРКИ в заходе, который правит меряемое:
#
#   ПРЕЖНЯЯ ФОРМУЛИРОВКА: про ряд действий на карточке и про пустую
#     выдачу поиска мерка не спрашивала НИЧЕГО.
#   НОВАЯ ФОРМУЛИРОВКА: те же вопросы плюс `E` (доли ряда действий,
#     зазоры, есть ли у каждого действия рамка) и `F` (одна ли система
#     координат у пустой выдачи, размер плитки значка, элементы,
#     пережившие своё содержимое).
#   ПОЧЕМУ ПРЕЖНЯЯ СТАЛА НЕГОДНОЙ: владелец увидел на живом экране
#     «ряд плавающего текста с неравными промежутками» и «два элемента
#     одного состояния в разных системах координат». Мерка молчала
#     об обоих — вопроса такого никто не задавал.
#   ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ НА НОВОЙ: `--контроль`, три подлога
#     В СТРАНИЦУ, у каждого НЕЗАВИСИМОЕ доказательство того, что подлог
#     состоялся (§6.0.3): вердикт самой мерки доказательством не является.
#
# Сузить вопрос эти правки не могут по построению: вопросы добавлены,
# ни один прежний не снят и не ослаблен.

РЯД_ДЕЙСТВИЙ = r"""(вид) => {
  const кор = (э) => э.getBoundingClientRect();
  const карточки = [...document.querySelectorAll('.apt-card')]
    .filter(к => !к.hidden && к.dataset.state
                 && ((вид === 'expired') === (к.dataset.state === 'expired')));
  if (!карточки.length) return {найдено: 0};
  const к = карточки[0];
  const ряд = к.querySelector('.apt-acts');
  if (!ряд) return {найдено: карточки.length, ряда: false};
  const дети = [...ряд.children].filter(э => !э.hidden);
  const рк = кор(ряд);
  const доли = дети.map(э => {
    const s = getComputedStyle(э);
    const c = кор(э);
    /* РАМКА — ЭТО ШИРИНА ПЛЮС ВИДИМЫЙ ЦВЕТ. Нулевая ширина
       и `transparent` дают одинаково невидимую рамку, и спрашивать
       одну только `border-width` значило бы засчитать вторую за первую */
    const ш = parseFloat(s.borderTopWidth) || 0;
    const ц = s.borderTopColor || '';
    const прозрачна = /,[ ]*0\)$/.test(ц) || ц === 'transparent';
    return {
      имя: (э.className.split(' ').filter(x => x.indexOf('apt-') === 0)[0]
            || э.className.split(' ')[0]),
      ширина: +c.width.toFixed(1),
      доля: +(c.width / рк.width).toFixed(3),
      рамка: (ш > 0 && !прозрачна) ? +ш.toFixed(1) : 0,
      подпись: (э.textContent || '').trim().slice(0, 20),
    };
  });
  /* ЗАЗОРЫ МЕЖДУ КОРОБКАМИ, а не объявленный `gap`: объявленный говорит
     о намерении, а разъезд виден только в фактических координатах */
  const зазоры = [];
  for (let i = 1; i < дети.length; i++) {
    зазоры.push(+(кор(дети[i]).left - кор(дети[i - 1]).right).toFixed(1));
  }
  const ш = доли.map(д => д.ширина);
  return {
    найдено: карточки.length,
    ряда: true,
    ширинаРяда: +рк.width.toFixed(1),
    действий: дети.length,
    доли,
    зазоры,
    /* РАЗБРОС ШИРИН — одно число, по которому и читают «делят ровно» */
    разброс: +(Math.max.apply(null, ш) - Math.min.apply(null, ш)).toFixed(1),
    сРамкой: доли.filter(д => д.рамка > 0).length,
    /* ХВОСТ СПРАВА: от правого края последнего действия до правого края
       ряда. Это и есть «корзина улетела к правому краю» — числом */
    хвостСправа: +(рк.right - кор(дети[дети.length - 1]).right).toFixed(1),
  };
}"""


ПУСТОЙ_ПОИСК = """() => {
  const блок = document.getElementById('apt-empty-find');
  const легенда = document.querySelector('.apt-legend');
  const видно = (э) => !!(э && !э.hidden && (э.offsetWidth || э.offsetHeight)
                          && getComputedStyle(э).display !== 'none');
  if (!видно(блок)) return {показан: false};
  const цх = (э) => {
    if (!э) return null;
    const к = э.getBoundingClientRect();
    return {левый: Math.round(к.left), центр: Math.round(к.left + к.width / 2),
            ширина: Math.round(к.width), высота: Math.round(к.height)};
  };
  const бк = блок.getBoundingClientRect();
  const центрБлока = Math.round(бк.left + бк.width / 2);
  const части = {
    значок: цх(блок.querySelector('.empty-state-icon')),
    заголовок: цх(блок.querySelector('.empty-state-title')),
    строка: цх(блок.querySelector('.empty-state-sub')),
    кнопка: цх(блок.querySelector('button')),
  };
  const отклонения = {};
  for (const и in части) {
    отклонения[и] = части[и] ? Math.abs(части[и].центр - центрБлока) : null;
  }
  const числа = [];
  for (const и in отклонения) if (отклонения[и] !== null) числа.push(отклонения[и]);
  /* ПЕРЕЖИВШИЕ СВОЁ СОДЕРЖИМОЕ: карточек на экране ноль, а элементы,
     которые их объясняют, ещё видны. Тот же класс, что чинил чип
     «Просрочено» и заголовок «Просрочено — выбросить» */
  return {
    показан: true,
    центрБлока,
    центрОкна: Math.round(window.innerWidth / 2),
    части,
    отклонения,
    /* САМОЕ БОЛЬШОЕ ОТКЛОНЕНИЕ — одно число, по которому читают
       «одна система координат или две» */
    разъезд: Math.max.apply(null, числа),
    плиткаЗначка: части.значок
      ? части.значок.ширина + 'x' + части.значок.высота : null,
    кегльЗаголовка: (() => {
      const з = блок.querySelector('.empty-state-title');
      return з ? Math.round(parseFloat(getComputedStyle(з).fontSize) * 10) / 10
               : null;
    })(),
    карточекВидно: [...document.querySelectorAll('.apt-card')]
      .filter(к => !к.hidden).length,
    пережили: {
      легенда: видно(легенда),
      подписьСетки: видно(document.getElementById('apt-note')),
      шапкаПросроченного: видно(document.getElementById('apt-dead-head')),
    },
  };
}"""



# ═════════════════════════════════════════════════════════════════════
# РЕЖИМ `--круг` (BACKLOG №184, блоки B, C, D)
#
# ТРИ ВОПРОСА, И ВСЕ ТРИ ЗАДАЛ ВЛАДЕЛЕЦ, ПОСМОТРЕВ НА ЖИВОЙ ЭКРАН
# ПОСЛЕ ЭТАПА 4:
#
#   B  где стоят органы управления списком. «Завести», «Вручную»
#      и «Участники» висели В СТРОКЕ ЗАГОЛОВКА, то есть по другую
#      сторону от ряда покупок и в метре пустоты от поиска, которым
#      этот же список отбирают;
#   C  кнопка-значок участников рядом с двумя подписанными кнопками:
#      габарит и контраст к подложке;
#   D  высота панели участников на каждой из ЧЕТЫРЁХ вкладок. Четыре
#      разные высоты означают, что окно прыгает при переключении.
#
# КРУГ ЗАВОДИТСЯ ПРОБОЙ И ЕЮ ЖЕ УБИРАЕТСЯ. Без круга три вкладки
# из четырёх пусты, и «высоты совпали» вышло бы про четыре пустых
# состояния — то есть про то, чего человек не увидит. Заводится
# НАСТОЯЩИМ путём (приглашение — принятие), а не строками в базе:
# подставленный круг показал бы не то, что показывает сервер.
# ═════════════════════════════════════════════════════════════════════

КРУГ = "--круг" in sys.argv
# C.3 ПИШЕТ В БАЗУ СИЛЬНЕЕ ОСТАЛЬНОГО — он нажимает «Принять»,
# «Отклонить» и «Убрать», — поэтому отдельным ключом: прогон
# облика не обязан каждый раз перебирать круг заново
СКАЧКИ = "--скачки" in sys.argv

СОСЕД = ("neighbour@local.dev", "Neighbour-Local-2026")


def _круг_завести():
    """Завести круг двумя НАСТОЯЩИМИ запросами и вернуть, убирать ли."""
    import http.cookiejar
    import json as _js
    import urllib.error
    import urllib.parse
    import urllib.request

    def клиент():
        cj = http.cookiejar.CookieJar()
        return urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(cj))

    def войти(op, почта, пароль):
        d = urllib.parse.urlencode({"email": почта, "password": пароль})
        op.open(urllib.request.Request(БАЗА + "/login", data=d.encode()),
                timeout=30)

    def зов(op, путь, метод="GET", тело=None):
        д = _js.dumps(тело).encode() if тело is not None else None
        req = urllib.request.Request(БАЗА + путь, data=д, method=метод)
        if д:
            req.add_header("Content-Type", "application/json")
        try:
            r = op.open(req, timeout=60)
            return r.status, _js.loads(r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            try:
                return e.code, _js.loads(e.read().decode("utf-8", "replace"))
            except Exception:
                return e.code, {}

    я, сосед = клиент(), клиент()
    войти(я, ПОЧТА, ПАРОЛЬ)
    войти(сосед, *СОСЕД)
    к, т = зов(я, "/medkit/api/circle")
    if т.get("общая"):
        return False           # круг уже был — не наш, не убираем
    зов(я, "/medkit/api/circle/invite", "POST", {"кого": СОСЕД[0]})
    к, т = зов(сосед, "/medkit/api/circle")
    пришедшие = т.get("полученные") or []
    if not пришедшие:
        print("   КРУГ НЕ ЗАВЁЛСЯ: приглашение не дошло до соседа")
        return False
    зов(сосед, "/medkit/api/circle/invite/%d/accept" % пришедшие[0]["id"],
        "POST")
    к, т = зов(я, "/medkit/api/circle")
    if not т.get("общая"):
        print("   КРУГ НЕ ЗАВЁЛСЯ: после принятия аптечка осталась личной")
        return False
    return True


# ── ЗАМЕР C.3 (BACKLOG №190): ОКНО НЕ ПРЫГАЕТ НИ ОТ ОДНОГО ДЕЙСТВИЯ ──
#
# ВОПРОС НЕ «ОТВЕТИЛ ЛИ СЕРВЕР», А «СДВИНУЛОСЬ ЛИ ОКНО». Отказ и успех
# оба меняют содержимое панели, и оба до правки раздвигали её: замер
# на приглашении несуществующему дал 694 → 761 → 694 на 2560 и
# 707 → 811 → 707 на 390.
#
# ДЕЙСТВИЯ БЕРУТСЯ ПОИМЁННО, И ПЕРЕЧЕНЬ ТУТ ЗАКОННЫЙ: каждая строка —
# кнопка, которую человек нажимает, и новая появляется решением
# о разметке, а не сама собой. Чего у действия нет на стенде (некого
# отклонять, некого разблокировать) — печатается словом «нет цели»,
# а не пропускается молча: пропуск читался бы как «прошло».
ДЕЙСТВИЯ_ПАНЕЛИ = [
    ("позвать-несуществующего", "people", None),
    ("позвать-себя", "people", None),
    ("принять", "invites", ".apt-person-acts button.btn-primary"),
    ("отклонить", "invites", ".apt-person-acts button.btn-secondary"),
    ("заблокировать", "invites", ".apt-person-acts button.btn-danger"),
    ("разблокировать", "block", ".apt-person > button.btn-secondary"),
    ("отозвать", "invites", ".apt-person-acts button.btn-secondary"),
    ("убрать-участника", "people", ".apt-person button.btn-danger"),
    ("выйти", "people", ".apt-person button.btn-secondary"),
]

ВЫСОТА_ОКНА = ("() => { const э = document.querySelector('#apt-circle .modal-sh');"
               " return э ? Math.round(э.getBoundingClientRect().height) : null; }")


async def _скачки(pg):
    """Высота окна ДО действия, ВО ВРЕМЯ ответа и ПОСЛЕ. Три числа
    обязаны совпасть.

    СИД ВОЗВРАЩАЕТСЯ ПЕРЕД КАЖДЫМ ДЕЙСТВИЕМ, а не один раз на прогон.
    Первая версия этого не делала — и первое же «Принять» съедало
    приглашение, после чего восемь действий из девяти печатали
    «нет цели». Не ложь, но и не замер: пропуск читался бы как
    «прошло». Тот же класс, что нашло доказательство подлога
    в `check_medkit_circle`: замер по стенду, испорченному
    собственной пробой.
    """
    import check_medkit_circle as _кр
    из = []
    for имя, вкладка, селектор in ДЕЙСТВИЯ_ПАНЕЛИ:
        _кр.вернуть_сид()
        await pg.reload(wait_until="networkidle")
        await pg.evaluate("() => аптКругОткрыть()")
        await pg.wait_for_timeout(500)
        await pg.evaluate("(в) => аптКругВкладка(в)", вкладка)
        await pg.wait_for_timeout(200)
        до = await pg.evaluate(ВЫСОТА_ОКНА)
        цель = None
        if селектор:
            панель = "[data-cpane='%s'] %s" % (вкладка, селектор)
            цель = await pg.query_selector(панель)
            if not цель:
                из.append((имя, до, None, None, "нет цели"))
                continue
            await цель.click()
        elif имя == "позвать-несуществующего":
            await pg.fill("#apt-circle-who", "нетакого@nowhere.dev")
            await pg.click(".apt-circle-invite button[type=submit]")
        else:
            await pg.fill("#apt-circle-who", ПОЧТА)
            await pg.click(".apt-circle-invite button[type=submit]")
        await pg.wait_for_timeout(900)
        во = await pg.evaluate(ВЫСОТА_ОКНА)
        # ОКНО ПОДТВЕРЖДЕНИЯ ЗАКРЫВАЕТСЯ, если действие его открыло:
        # иначе следующее действие било бы по перекрытой панели
        await pg.evaluate("() => { const о = document.querySelector("
                          "'.modal-ov.open:not(#apt-circle)');"
                          " if (о) о.classList.remove('open'); }")
        await pg.evaluate("() => { const п = document.getElementById("
                          "'apt-circle-err'); if (п) п.hidden = true; }")
        await pg.wait_for_timeout(250)
        после = await pg.evaluate(ВЫСОТА_ОКНА)
        из.append((имя, до, во, после,
                   "" if до == во == после else "СКАЧОК"))
    return из


def _приглашения_и_блок_убрать():
    """Убрать приглашения и блокировки, КРУГ ОСТАВИВ.

    Так на стенде получается состояние боевого экрана: аптечка общая,
    лента длинная, а вкладки «Приглашения» и «Блок» пусты. Именно
    на нём и видна пустота под пустым состоянием — seed эти две
    вкладки наполняет, и без очистки мерить нечего.
    """
    import sqlite3
    from database import DB_PATH
    c = sqlite3.connect(DB_PATH)
    было = (c.execute("SELECT COUNT(*) FROM medkit_invites").fetchone()[0],
            c.execute("SELECT COUNT(*) FROM medkit_blocks").fetchone()[0])
    c.execute("DELETE FROM medkit_invites")
    c.execute("DELETE FROM medkit_blocks")
    c.commit()
    c.close()
    print("   приглашений было %d, блокировок %d — убраны" % было)


def _круг_убрать():
    """Убрать круг ПРЯМО В БАЗЕ — тем же приёмом, что `удалить_всё`."""
    import sqlite3
    from database import DB_PATH
    c = sqlite3.connect(DB_PATH)
    for t in ("medkit_events", "medkit_members", "medkit_invites"):
        c.execute("DELETE FROM " + t)
    c.execute("DELETE FROM medkit_circles")
    c.commit()
    c.close()
    print("   круг и приглашения убраны")


# ── ЗАМЕР B и C: строка управления списком ────────────────────────────
#
# ПУСТОТА МЕРИТСЯ МЕЖДУ ПРЯМОУГОЛЬНИКАМИ КОРОБОК, а не по `left`
# соседей: вопрос владельца — «сколько пустого места между поиском
# и кнопками», и это расстояние от правого края одного до левого
# края другого.
СТРОКА_УПРАВЛЕНИЯ = r"""() => {
  const п = (с) => document.querySelector(с);
  const кор = (э) => { if (!э) return null; const к = э.getBoundingClientRect();
    return {л: Math.round(к.left), п: Math.round(к.right),
            в: Math.round(к.top), н: Math.round(к.bottom),
            ш: Math.round(к.width), вы: Math.round(к.height)}; };
  const видно = (э) => { if (!э) return false;
    const с = getComputedStyle(э), к = э.getBoundingClientRect();
    return с.display !== 'none' && с.visibility !== 'hidden'
        && к.width > 0 && к.height > 0; };

  const разбор = s => { const m = String(s).match(/[\d.]+/g) || [];
    return [+m[0]||0, +m[1]||0, +m[2]||0, m.length>3 ? +m[3] : 1]; };
  const поверх = (пер, зад) => { const a = пер[3];
    return [0,1,2].map(i => пер[i]*a + зад[i]*(1-a)).concat([1]); };
  const яркость = c => { const l = c.slice(0,3).map(v => { v/=255;
      return v <= 0.03928 ? v/12.92 : Math.pow((v+0.055)/1.055, 2.4); });
    return 0.2126*l[0] + 0.7152*l[1] + 0.0722*l[2]; };
  const контраст = (пер, зад) => { const a = яркость(поверх(пер, зад)),
    b = яркость(зад);
    return +(((Math.max(a,b)+0.05)/(Math.min(a,b)+0.05))).toFixed(2); };
  /* ПОДЛОЖКА ИЩЕТСЯ ВВЕРХ ПО ДЕРЕВУ до первого непрозрачного предка:
     у самой кнопки `background` часто `rgba(...,0)`, и контраст к нему
     вышел бы делением на собственный цвет */
  const подложка = (э) => { let у = э;
    while (у) { const ц = разбор(getComputedStyle(у).backgroundColor);
      if (ц[3] > 0.99) return ц; у = у.parentElement; }
    return [10, 11, 13, 1]; };

  const поиск  = п('.apt-search');
  const ассист = п('#apt-ai-open');
  const вручную = п('.apt-add');
  const кружок = п('#apt-circle-open');

  /* ЗАЗОР — от правого края поиска до левого края САМОЙ ЛЕВОЙ
     из видимых кнопок, и только если они в ОДНОЙ строке: на узкой
     ширине кнопки уходят под поиск, и «зазор» там не про пустоту */
  const кп = кор(поиск);
  const кнопки = [ассист, вручную, кружок].filter(видно).map(кор);
  let зазор = null, вОднойСтроке = null;
  if (кп && кнопки.length) {
    const слева = Math.min.apply(null, кнопки.map(к => к.л));
    вОднойСтроке = кнопки.every(к => к.в < кп.н && к.н > кп.в);
    зазор = вОднойСтроке ? слева - кп.п : null;
  }

  /* ГАБАРИТ КРУЖКА против ПОДПИСАННЫХ СОСЕДЕЙ — вопрос C.1.
     Высота, а не площадь: в ряду органы равняются по высоте,
     и «меньше соседних» человек видит именно так */
  const кк = кор(кружок), ка = кор(ассист), кв = кор(вручную);
  const св = [ка, кв].filter(Boolean).map(к => к.вы);

  let знЦвет = null, знКонтраст = null, знРазмер = null, рамка = null;
  let подпись = null;
  if (кружок) {
    const с_ = getComputedStyle(кружок);
    const зад = подложка(кружок.parentElement || document.body);
    знЦвет = с_.color;
    знКонтраст = контраст(разбор(с_.color), зад);
    рамка = {ширина: с_.borderTopWidth, цвет: с_.borderTopColor,
             контраст: контраст(разбор(с_.borderTopColor), зад)};
    const svg = кружок.querySelector('svg');
    if (svg) { const к = svg.getBoundingClientRect();
      знРазмер = Math.round(к.width) + 'x' + Math.round(к.height); }
    подпись = (кружок.textContent || '').trim();
  }

  /* ГДЕ ОНИ СТОЯТ — в шапке или в строке поиска. Отвечает на B.1
     прямо, а не через координаты */
  const вШапке = (э) => !!(э && э.closest('.apt-head'));
  const вСтроке = (э) => !!(э && э.closest('.apt-bar'));

  return {
    зазор: зазор, вОднойСтроке: вОднойСтроке,
    поиск: кп,
    места: {
      ассистент: вШапке(ассист) ? 'шапка' : (вСтроке(ассист) ? 'строка' : '?'),
      вручную:   вШапке(вручную) ? 'шапка' : (вСтроке(вручную) ? 'строка' : '?'),
      участники: вШапке(кружок) ? 'шапка' : (вСтроке(кружок) ? 'строка' : '?')},
    кружок: {коробка: кк, высотаСоседей: св,
             разницаВысот: (кк && св.length) ? Math.max.apply(null,
               св.map(в => Math.abs(в - кк.вы))) : null,
             значок: знРазмер, цвет: знЦвет, контраст: знКонтраст,
             рамка: рамка, подпись: подпись},
    строкаВысота: (() => { const б = п('.apt-bar'); return б ?
      Math.round(б.getBoundingClientRect().height) : null; })(),
    /* ЗНАЧКИ ТРЁХ КНОПОК ОБЯЗАНЫ БЫТЬ ОДНОГО РАЗМЕРА: разнобой здесь
       и есть «выглядит как случайно попавший символ» */
    значки: [ассист, вручную, кружок].map(э => { if (!э) return null;
      const s = э.querySelector('svg'); if (!s) return null;
      const к = s.getBoundingClientRect();
      return Math.round(к.width) + 'x' + Math.round(к.height); }),
    /* ЗА КРАЙ ЭКРАНА НИЧЕГО НЕ УЕЗЖАЕТ. Ровно этот замер поймал
       2026-08-26 третью кнопку, стоявшую на 406 при окне 390 */
    заКраем: Array.from(document.querySelectorAll('.apt-bar *'))
      .filter(э => э.getBoundingClientRect().right > window.innerWidth + 1)
      .length,
    гориз: document.documentElement.scrollWidth > window.innerWidth + 1,
  };
}"""

# ── ЗАМЕР A (BACKLOG №189): СЕТКА ПАНЕЛИ И ПОДСВЕТКА ВКЛАДКИ ─────────
#
# ДВА ВОПРОСА, И ОНИ РАЗНЫЕ.
#
# ПЕРВЫЙ — ВИДНО ЛИ, ГДЕ ЧЕЛОВЕК НАХОДИТСЯ. До 2026-08-28 панель
# ставила класс `is-active`, а системный `.tab-btn` знает только
# `.active`: замер дал у активной вкладки ТЕ ЖЕ вычисленные стили, что
# у неактивных — цвет rgb(174,184,212) и ПРОЗРАЧНОЕ подчёркивание
# у всех четырёх. Отличий ноль. Ни одна проверка ряда такого не берёт
# по построению: они ищут страницу, которая ПЕРЕОПРЕДЕЛЯЕТ систему,
# а тут страница ссылается на класс, которого у компонента нет.
#
# ВТОРОЙ — ОДНА ЛИ СЕТКА У ЗАГОЛОВКА, ВКЛАДОК И ТЕЛА. Постановка
# называла три разных отступа; замер дал ДВА — вкладки и тело
# совпадают до знака, а заголовок сдвинут на ширину значка шапки
# (26 px слева) и крестика (30 справа). Расхождение принадлежит
# СИСТЕМНОЙ шапке и одинаково у всех модалок проекта, поэтому оно
# печатается ЧИСЛОМ и выносится владельцу, а не чинится молча (§6.0.8).
СЕТКА_ПАНЕЛИ = r"""() => {
  const к = (с) => { const э = document.querySelector(с); if (!э) return null;
    const r = э.getBoundingClientRect();
    return {л: Math.round(r.left * 10) / 10,
            п: Math.round(r.right * 10) / 10}; };
  const вкладки = [...document.querySelectorAll('#apt-circle [data-ctab]')]
    .map(б => { const s = getComputedStyle(б);
      return {имя: б.dataset.ctab,
              активна: б.classList.contains('active'),
              цвет: s.color,
              подчёркивание: s.borderBottomColor,
              значок: (() => { const g = б.querySelector('svg');
                return g ? getComputedStyle(g).color : null; })()}; });
  const акт = вкладки.find(в => в.активна) || {};
  const неакт = вкладки.filter(в => !в.активна);
  return {
    заголовок: к('#apt-circle .modal-title'),
    вкладки_ряд: к('#apt-circle .apt-circle-tabs'),
    тело_панели: к('#apt-circle .apt-circle-panes'),
    вкладки: вкладки,
    /* ОТЛИЧАЕТСЯ ЛИ АКТИВНАЯ ОТ НЕАКТИВНЫХ — спрашивается у ВСЕХ
       свойств сразу: совпадение хотя бы по одному ещё ничего
       не значит, а совпадение по всем и есть тот дефект.

       ИСХОДОВ ТРИ, А НЕ ДВА, И ТРЕТИЙ ХУЖЕ ОБОИХ. Первая версия
       считала `акт = вкладки.find(в => в.активна) || {}` и сравнивала
       `undefined` с цветом соседа — то есть на коде, где активной
       вкладки НЕТ ВОВСЕ, печатала «отличается: ДА». Ровно на том
       состоянии, ради которого замер и написан. Поймал это контроль
       мерки на прежнем коде, а не чтение (§6.0.3): вердикт был
       правдоподобен и неверен.

       Теперь отсутствие подсветки называется своим словом: искать
       различия не в чем, и «да» тут значило бы «дефекта нет». */
    активной_нет: !вкладки.some(в => в.активна),
    активная_отличается: (!вкладки.some(в => в.активна) || !неакт.length)
      ? null
      : (акт.цвет !== неакт[0].цвет ||
         акт.подчёркивание !== неакт[0].подчёркивание ||
         акт.значок !== неакт[0].значок),
    /* ПУСТЫЕ СОСТОЯНИЯ: сколько их видно и все ли одного компонента */
    пустые: [...document.querySelectorAll('#apt-circle .empty-state')]
      .map(э => э.className),
    /* B.1 (BACKLOG №190): ПУСТОТА НАД СОДЕРЖИМЫМ И ПОД НИМ.
       Высота вкладки равна самой рослой из четырёх, и короткая
       получает от неё лишнее место. Прижато содержимое к верху или
       стоит по центру, видно ТОЛЬКО по этой паре чисел: сама высота
       вкладки одинакова в обоих случаях, и D.3 про это молчит
       по построению.

       Меряется ВИДИМАЯ вкладка со своим пустым состоянием; нет
       такой — null, и это честнее нуля: ноль читался бы как
       «пустоты нет». */
    воздух: (() => {
      /* ИЩЕТСЯ ЛЮБАЯ ВКЛАДКА С ПУСТЫМ СОСТОЯНИЕМ, а не только видимая.
         Все четыре лежат в ОДНОЙ ячейке сетки, то есть высота у них
         общая и у скрытой она та же — а дефект живёт ровно на скрытой:
         у владельца лента длинная, а «Блок» пуст, и пустоту под ним
         видно при первом же переключении. Замер по видимой вкладке
         молчал бы про это по построению. */
      const вид = [...document.querySelectorAll('.apt-circle-pane')]
        .find(п => п.querySelector(':scope > .empty-state'));
      if (!вид) return null;
      const б = вид.querySelector(':scope > .empty-state');
      const кв = вид.getBoundingClientRect();
      /* МЕРИТСЯ СОДЕРЖИМОЕ, А НЕ КОРОБКА БЛОКА. Тот же урок, что
         у панели ассистента 2026-08-25: центрирующая форма
         растягивается на всю вкладку (`flex: 1`), и её собственные
         края дают 0/0 И ДО правки, И ПОСЛЕ — то есть замер по коробке
         молчит ровно про то, ради чего написан. Края СОДЕРЖИМОГО
         (первый и последний видимый ребёнок) двигаются. */
      const дети = [...б.children].filter(э => э.offsetWidth || э.offsetHeight);
      if (!дети.length) return null;
      const кб = {top: дети[0].getBoundingClientRect().top,
                  bottom: дети[дети.length - 1].getBoundingClientRect().bottom};
      return {вкладка: вид.dataset.cpane,
              сверху: Math.round(кб.top - кв.top),
              снизу: Math.round(кв.bottom - кб.bottom),
              высотаВкладки: Math.round(кв.height),
              значок: (() => {
                const з = б.querySelector('.empty-state-icon');
                if (!з) return null;
                const к = з.getBoundingClientRect();
                const с = з.querySelector('svg');
                const кс = с && с.getBoundingClientRect();
                return {плитка: Math.round(к.width),
                        знак: кс ? Math.round(кс.width) : null};
              })()};
    })(),
    /* СОСЕДИ ПУСТОГО СОСТОЯНИЯ на ВИДИМОЙ вкладке: блок, выровненный
       иначе, рядом с центрированным — и есть разнобой, ради которого
       заводился A.4 */
    выравнивания: (() => {
      const вид = document.querySelector('.apt-circle-pane:not(.is-off)');
      if (!вид) return null;
      return [...вид.children].filter(э => э.offsetWidth).map(э => ({
        класс: э.className.split(' ')[0],
        вырав: getComputedStyle(э).textAlign,
        ширина: Math.round(э.getBoundingClientRect().width)}));
    })(),
  };
}"""


# ── ЗАМЕР D: высота панели на каждой из четырёх вкладок ───────────────
#
# МЕРИТСЯ КОРОБКА ОКНА, а не содержимое: прыгает на глазах именно она.
# Вкладки переключаются ТЕМ ЖЕ обработчиком, что у человека, —
# нажатием по кнопке: подставить `hidden` руками значило бы мерить
# состояние, в которое экран никто не приводил.
ВЫСОТЫ_ВКЛАДОК = r"""async () => {
  const сон = (мс) => new Promise(r => setTimeout(r, мс));
  const окно = document.querySelector('#apt-circle .modal-box') ||
               document.querySelector('#apt-circle .modal') ||
               document.querySelector('#apt-circle > *');
  const итог = {};
  const кнопки = Array.from(
    document.querySelectorAll('#apt-circle [data-ctab]'));
  for (const к of кнопки) {
    к.click();
    await сон(150);
    const пан = document.querySelector('.apt-circle');
    const пкор = пан ? пан.getBoundingClientRect() : null;
    const окор = окно ? окно.getBoundingClientRect() : null;
    /* ПРОКРУТКА — отдельным числом: вкладка «Лента» обязана
       прокручиваться ВНУТРИ, не меняя габарит окна */
    const тело = document.querySelector('#apt-circle .modal-body') ||
                 (пан ? пан.parentElement : null);
    /* ПРОКРУТОК ДВЕ, И ОНИ ОТВЕЧАЮТ НА РАЗНЫЕ ВОПРОСЫ. Своя —
       рослая вкладка листается ВНУТРИ СЕБЯ, так и надо. Тела окна —
       вкладка переросла окно и потащила за собой ВСЕ ОСТАЛЬНЫЕ:
       по короткой пришлось бы листать пустоту. Первая версия мерила
       только вторую и печатала одно число там, где их два. */
    const вкл = document.querySelector(
      '[data-cpane="' + к.dataset.ctab + '"]');
    итог[к.dataset.ctab] = {
      панель: пкор ? Math.round(пкор.height) : null,
      окно: окор ? Math.round(окор.height) : null,
      прокрутка: тело ? Math.max(0,
        Math.round(тело.scrollHeight - тело.clientHeight)) : null,
      своя: вкл ? Math.max(0,
        Math.round(вкл.scrollHeight - вкл.clientHeight)) : null,
      строк: document.querySelectorAll(
        '[data-cpane="' + к.dataset.ctab + '"] li').length,
    };
  }
  /* вернуть на первую вкладку, чтобы следующий замер начинался
     с того же состояния */
  if (кнопки.length) { кнопки[0].click(); await сон(80); }
  return итог;
}"""


def _ленту_набить(сколько):
    """Набить ленту строками — D.4 иначе не задаётся вовсе.

    На стенде лента короткая (две-три строки), и «высоты совпали»
    на ней вышло бы про случай, в котором совпасть им нечему.
    Вопрос D.4 — что будет, когда одна вкладка ПЕРЕРАСТЁТ окно.

    Строки кладутся ПРЯМО В БАЗУ, а не действиями: восемьдесят
    списаний через интерфейс — работа не про то, а вопрос тут
    к раскладке, а не к пути записи.
    """
    import sqlite3
    from database import DB_PATH
    c = sqlite3.connect(DB_PATH)
    try:
        круг = c.execute("SELECT id FROM medkit_circles").fetchone()
        участник = c.execute(
            "SELECT user_id FROM medkit_members LIMIT 1").fetchone()
        if not круг or not участник:
            return 0
        for i in range(сколько):
            c.execute("INSERT INTO medkit_events "
                      "(circle_id, user_id, kind, name, created_at) "
                      "VALUES (?, ?, 'take', ?, datetime('now'))",
                      (круг[0], участник[0], "проба ленты %d" % i))
        c.commit()
        return c.execute("SELECT COUNT(*) FROM medkit_events").fetchone()[0]
    finally:
        c.close()


async def прогон_круга():
    from playwright.async_api import async_playwright
    итог = {}
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for ширина in ШИРИНЫ:
            сенсор = ширина < 800
            ctx = await b.new_context(
                viewport={"width": ширина,
                          "height": 900 if not сенсор else 844},
                has_touch=сенсор, is_mobile=сенсор, device_scale_factor=1)
            pg = await ctx.new_page()
            await _войти(pg)
            await pg.goto(БАЗА + "/medkit", wait_until="networkidle")
            await pg.add_style_tag(
                content="html, * { scroll-behavior: auto !important }")
            await pg.wait_for_timeout(400)
            д = {"строка": await pg.evaluate(СТРОКА_УПРАВЛЕНИЯ)}
            # ПАНЕЛЬ ОТКРЫВАЕТСЯ ТЕМ ЖЕ ВЫЗОВОМ, ЧТО У ЧЕЛОВЕКА
            await pg.evaluate("() => аптКругОткрыть()")
            await pg.wait_for_timeout(700)
            д["сетка"] = await pg.evaluate(СЕТКА_ПАНЕЛИ)
            д["вкладки"] = await pg.evaluate(ВЫСОТЫ_ВКЛАДОК)
            # C.3 ИДЁТ ПОСЛЕДНИМ: он НАЖИМАЕТ кнопки и меняет состояние
            # круга — принимает, отклоняет, блокирует. Стой он раньше,
            # замеры сетки и высот шли бы по стенду, испорченному
            # собственной пробой (§6.0.3, шестая причина)
            if СКАЧКИ:
                д["скачки"] = await _скачки(pg)
            итог[ширина] = д
            await ctx.close()
        await b.close()
    return итог


def печать_круга(итог):
    print("СТРОКА УПРАВЛЕНИЯ И ПАНЕЛЬ УЧАСТНИКОВ (BACKLOG №184)")
    print("=" * 72)
    for ширина, д in итог.items():
        с, в = д["строка"], д["вкладки"]
        print()
        print("── %d ──" % ширина)
        м = с["места"]
        print("  B.1  где стоят: ассистент=%s вручную=%s участники=%s"
              % (м["ассистент"], м["вручную"], м["участники"]))
        print("  B.3  пустота между поиском и кнопками: %s px "
              "(в одной строке: %s)"
              % ("—" if с["зазор"] is None else с["зазор"], с["вОднойСтроке"]))
        к = с["кружок"]
        кор = к["коробка"] or {}
        print("  C.1  участники: коробка %sx%s, высота соседей %s, "
              "расхождение %s px"
              % (кор.get("ш"), кор.get("вы"), к["высотаСоседей"],
                 к["разницаВысот"]))
        print("       значок %s, контраст к подложке %s (порог 3.0), "
              "рамка %s / контраст %s"
              % (к["значок"], к["контраст"],
                 (к["рамка"] or {}).get("ширина"),
                 (к["рамка"] or {}).get("контраст")))
        print("  C.2  подпись у кнопки: %r" % (к["подпись"] or ""))
        с2 = д.get("сетка") or {}
        if с2:
            з, вр, тл = (с2.get("заголовок"), с2.get("вкладки_ряд"),
                         с2.get("тело_панели"))
            print("  A.2  края: заголовок %s  ряд вкладок %s  тело %s"
                  % (з, вр, тл))
            if вр and тл:
                print("       вкладки и тело совпали: %s"
                      % (вр == тл))
            if з and вр:
                print("       заголовок сдвинут от сетки: слева %+.1f, "
                      "справа %+.1f — это значок и крестик СИСТЕМНОЙ шапки"
                      % (з["л"] - вр["л"], з["п"] - вр["п"]))
            if с2.get("активной_нет"):
                print("  A.1  АКТИВНОЙ ВКЛАДКИ НЕТ ВОВСЕ — ни одна кнопка "
                      "не несёт класса `active`; сравнивать не с чем, "
                      "и человек не видит, где находится")
            else:
                print("  A.1  активная вкладка отличается от неактивных: %s"
                      % с2.get("активная_отличается"))
            for вкл in с2.get("вкладки", []):
                print("       %-8s активна=%-5s цвет=%-20s подчёрк=%s"
                      % (вкл["имя"], вкл["активна"], вкл["цвет"],
                         вкл["подчёркивание"]))
            print("  A.3  пустых состояний видно %d: %s"
                  % (len(с2.get("пустые") or []),
                     "; ".join(с2.get("пустые") or []) or "нет"))
            в_ = с2.get("воздух")
            if в_:
                з_ = в_.get("значок") or {}
                print("  B.1  пустота вокруг пустого состояния «%s»: "
                      "сверху %s, снизу %s px (высота вкладки %s) — "
                      "после правки обязаны сравняться"
                      % (в_.get("вкладка"), в_["сверху"], в_["снизу"],
                         в_["высотаВкладки"]))
                print("  B.2  значок пустого состояния: плитка %s, знак %s"
                      % (з_.get("плитка"), з_.get("знак")))
            else:
                print("  B.1  на видимой вкладке пустого состояния нет — "
                      "мерить воздух не у чего")
            вырав = с2.get("выравнивания") or []
            набор = sorted({б["вырав"] for б in вырав})
            print("  A.4  на видимой вкладке блоков %d, выравниваний %d: %s"
                  % (len(вырав), len(набор), ", ".join(набор) or "—"))
            for б in вырав:
                print("       %-24s вырав=%-8s ширина %s"
                      % (б["класс"], б["вырав"], б["ширина"]))
        высоты = [(и, з["окно"]) for и, з in в.items()]
        числа = [з for _, з in высоты if з]
        разброс = (max(числа) - min(числа)) if числа else None
        print("  D.3  высоты окна по вкладкам: %s"
              % ", ".join("%s=%s" % (и, з) for и, з in высоты))
        print("       РАЗБРОС %s px  (после правки обязан быть 0)" % разброс)
        for и, з in в.items():
            print("       %-8s строк %-3s внутри вкладки %s px, "
                  "тело окна %s px"
                  % (и, з["строк"], з.get("своя"), з["прокрутка"]))
        print("  D.4  прокрутку заводит ТОЛЬКО рослая вкладка: тело окна "
              "листается на %s px (обязан быть 0)"
              % max((з["прокрутка"] or 0) for з in в.values()))
        print("  C.1  значки трёх кнопок: %s   за краем экрана %s, "
              "горизонтальная прокрутка %s"
              % (", ".join(str(з) for з in с["значки"]),
                 с["заКраем"], с["гориз"]))
        for имя, до, во, после, пометка in (д.get("скачки") or []):
            print("  C.3  %-26s окно: до=%s во=%s после=%s %s"
                  % (имя, до, во, после, пометка))


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
            if КОНТРОЛЬ:
                await pg.add_init_script(ПОДЛОГИ)
            await _войти(pg)
            await pg.goto(БАЗА + "/medkit", wait_until="networkidle")
            await pg.add_style_tag(
                content="html, * { scroll-behavior: auto !important }")
            await pg.wait_for_timeout(500)
            медкит = await pg.evaluate(ЗАМЕР)
            if ПУСТОЕ:
                медкит["пустой"] = await pg.evaluate(ПУСТОЙ_ЭКРАН)
            # E. РЯД ДЕЙСТВИЙ — на рабочей карточке и на просроченной.
            # Два вида, потому что действий там РАЗНОЕ число (три против
            # двух), и «делят ровно» проверяется у каждого своё
            медкит["рядДействий"] = await pg.evaluate(РЯД_ДЕЙСТВИЙ, "ok")
            медкит["рядПросроченного"] = await pg.evaluate(
                РЯД_ДЕЙСТВИЙ, "expired")
            # F. ПУСТАЯ ВЫДАЧА ПОИСКА. Запрос набирается ТЕМ ЖЕ путём,
            # что у человека, — через поле и его обработчик: подставить
            # `hidden=false` руками значило бы мерить блок, который никто
            # не показывал
            await pg.fill("#apt-q", "заведомо-такого-нет-ъ")
            await pg.evaluate("() => аптОтобрать()")
            await pg.wait_for_timeout(300)
            медкит["пустойПоиск"] = await pg.evaluate(ПУСТОЙ_ПОИСК)
            await pg.fill("#apt-q", "")
            await pg.evaluate("() => аптОтобрать()")
            await pg.wait_for_timeout(200)
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
        су = м.get("строкаУправления") or {}
        if су:
            print("     · СТРОКА УПРАВЛЕНИЯ (BACKLOG №188)")
            for имя in ("купить", "строка", "чипы"):
                б = су.get(имя)
                if б:
                    print("         %-7s left=%-5s right=%-5s w=%s"
                          % (имя, б["left"], б["right"], б["w"]))
            print("         края трёх блоков совпали: %s   (чипов видно %s)"
                  % ("ДА" if су.get("краяСовпали") else "НЕТ",
                     су.get("чиповВидно")))
            print("         действия у правого края: %s   воздух %s px"
                  % ("ДА" if су.get("уПравогоКрая") else "НЕТ",
                     су.get("воздух")))
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
        # ── E. РЯД ДЕЙСТВИЙ НА КАРТОЧКЕ (блок A) ──────────────────
        for метка, ключ in (("рабочая", "рядДействий"),
                            ("просроченная", "рядПросроченного")):
            р = м.get(ключ) or {}
            if not р.get("ряда"):
                print("  E    %s карточка: ряда действий нет (найдено %s)"
                      % (метка, р.get("найдено")))
                continue
            print("  E    %s: ряд %s px, действий %s, разброс ширин %s px, "
                  "с рамкой %s из %s"
                  % (метка, р["ширинаРяда"], р["действий"], р["разброс"],
                     р["сРамкой"], р["действий"]))
            print("       доли: %s"
                  % " | ".join("%s %s px (%s)"
                               % (д["имя"], д["ширина"], д["доля"])
                               for д in р["доли"]))
            print("       зазоры %s px, хвост справа %s px"
                  % (р["зазоры"], р["хвостСправа"]))
        # ── F. ПУСТАЯ ВЫДАЧА ПОИСКА (блок B) ──────────────────────────
        пп = м.get("пустойПоиск") or {}
        if not пп.get("показан"):
            print("  F    пустая выдача поиска НЕ ПОКАЗАНА — мерить нечего")
        else:
            print("  F    пустая выдача: разъезд от центра блока %s px "
                  "(центр блока %s, центр окна %s)"
                  % (пп["разъезд"], пп["центрБлока"], пп["центрОкна"]))
            print("       отклонения: %s"
                  % " | ".join("%s %s" % (и, з)
                               for и, з in пп["отклонения"].items()))
            print("       плитка значка %s, кегль заголовка %s, "
                  "карточек видно %s"
                  % (пп["плиткаЗначка"], пп["кегльЗаголовка"],
                     пп["карточекВидно"]))
            print("       пережили содержимое: %s"
                  % " | ".join("%s %s" % (и, "ВИДЕН" if з else "нет")
                               for и, з in пп["пережили"].items()))
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



# ── ПОДЛОГИ ОТРИЦАТЕЛЬНОГО КОНТРОЛЯ (блоки E и F) ────────────────────
#
# Кладутся В СТРАНИЦУ и кода экрана не трогают. Каждый возвращает ровно
# то состояние, которое заход починил, — то есть мерка обязана назвать
# его теми же числами, какими назвала дефект до правки.
#
# ОДИН ПОДЛОГ — ОДНО СВОЙСТВО. Общий доказывал бы, что мерка видит хоть
# что-то, и находка от одного закрыла бы собой молчание про остальные.
ПОДЛОГИ = {
    # E: крестик снова не сжимается — доли ряда разъезжаются
    "крестик-не-делит-ряд":
        ".apt-act:last-child { flex: 0 0 auto !important; }",
    # E: рамок у действий снова нет — ряд читается полосой текста
    "рамок-у-действий-нет":
        ".apt-acts > * { border-color: transparent !important; }",
    # F: блочные дети пустой выдачи снова у левого края
    "пустая-выдача-влево":
        ".apt-empty-find { display: block !important; }",
}

# ── ДОКАЗАТЕЛЬСТВА ПОДЛОГОВ ──────────────────────────────────────────
#
# НЕЗАВИСИМЫЙ замер того, что подлог собирался изменить. Вердикт самой
# мерки доказательством НЕ ЯВЛЯЕТСЯ: подлог, не состоявшийся молча, даёт
# ровно тот же вердикт, что и слепая проба (§6.0.3).
#
# Смотрим ВЫЧИСЛЕННОЕ СВОЙСТВО, а не факт вставки стиля: «правило
# добавлено» и «правило применилось» — разные утверждения.
ДОКАЗАТЕЛЬСТВА = {
    "крестик-не-делит-ряд": (
        "() => { const к = document.querySelector('.apt-acts > :last-child');"
        "  return к ? getComputedStyle(к).flexGrow : 'ряда нет'; }",
        "flex-grow у последнего действия"),
    "рамок-у-действий-нет": (
        "() => { const к = document.querySelector('.apt-act');"
        "  return к ? getComputedStyle(к).borderTopColor : 'действий нет'; }",
        "цвет рамки первого действия"),
    "пустая-выдача-влево": (
        "() => { const б = document.getElementById('apt-empty-find');"
        "  return б ? getComputedStyle(б).display : 'блока нет'; }",
        "display у блока пустой выдачи"),
}


async def контроль():
    """Каждый подлог — свой прогон, своё доказательство, свой вердикт."""
    from playwright.async_api import async_playwright
    найдено, не_состоялось = 0, 0
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for имя, стиль in ПОДЛОГИ.items():
            print("─" * 70)
            print("ПОДЛОГ «%s»" % имя)
            замер, что = ДОКАЗАТЕЛЬСТВА[имя]
            значения = {}
            числа = {}
            for метка, подложить in (("чисто", False), ("с подлогом", True)):
                ctx = await b.new_context(
                    viewport={"width": 1920, "height": 900},
                    device_scale_factor=1)
                pg = await ctx.new_page()
                await _войти(pg)
                await pg.goto(БАЗА + "/medkit", wait_until="networkidle")
                if подложить:
                    await pg.add_style_tag(content=стиль)
                    await pg.wait_for_timeout(200)
                значения[метка] = await pg.evaluate(замер)
                числа[метка] = {
                    "разброс": (await pg.evaluate(РЯД_ДЕЙСТВИЙ, "ok")
                                ).get("разброс"),
                    "рамок": (await pg.evaluate(РЯД_ДЕЙСТВИЙ, "ok")
                              ).get("сРамкой"),
                }
                # Пустая выдача набирается ТЕМ ЖЕ путём, что у человека
                await pg.fill("#apt-q", "заведомо-такого-нет-ъ")
                await pg.evaluate("() => аптОтобрать()")
                await pg.wait_for_timeout(250)
                if подложить:
                    await pg.add_style_tag(content=стиль)
                    await pg.wait_for_timeout(150)
                    значения[метка] = await pg.evaluate(замер)
                числа[метка]["разъезд"] = (
                    await pg.evaluate(ПУСТОЙ_ПОИСК)).get("разъезд")
                await ctx.close()
            состоялся = значения["чисто"] != значения["с подлогом"]
            print("  доказательство (%s): чисто=%r с подлогом=%r → подлог %s"
                  % (что, значения["чисто"], значения["с подлогом"],
                     "состоялся" if состоялся else "ПУСТОЙ"))
            if not состоялся:
                не_состоялось += 1
                print("  ПОДЛОГ НЕ СОСТОЯЛСЯ — ломать было нечего, вердикт "
                      "мерки ничего не значит")
                continue
            ч, п_ = числа["чисто"], числа["с подлогом"]
            print("  мерка: разброс %s → %s, рамок %s → %s, разъезд %s → %s"
                  % (ч["разброс"], п_["разброс"], ч["рамок"], п_["рамок"],
                     ч["разъезд"], п_["разъезд"]))
            назвала = (ч != п_)
            print("  %s" % ("НАЙДЕН" if назвала else "НЕ НАЙДЕН — мерка слепа"))
            найдено += 1 if назвала else 0
        await b.close()
    print("─" * 70)
    print("ИТОГ КОНТРОЛЯ: найдено %d из %d, не состоялось подлогов %d"
          % (найдено, len(ПОДЛОГИ), не_состоялось))


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
    if КОНТРОЛЬ:
        asyncio.run(контроль())
        return 0
    if КРУГ:
        # КРУГ ЗАВОДИТСЯ НАСТОЯЩИМ ПУТЁМ и убирается в `finally`:
        # оставленный круг превратил бы следующий снимок аптечки
        # в снимок ОБЩЕЙ, и пиксельный диф назвал бы находкой мусор
        # чужой пробы (§6.0.3, шестая причина неповторимости)
        print("РЕЖИМ --круг: на стенде заводится общая аптечка "
              "на двоих. Сказано ДО прогона, а не после.")
        наш = _круг_завести()
        try:
            print("\n### ЛЕНТА КОРОТКАЯ — обычное состояние стенда")
            печать_круга(asyncio.run(прогон_круга()))
            # D.4: ОДНА ВКЛАДКА ПЕРЕРАСТАЕТ ОКНО. Без этого прохода
            # «высоты совпали» относится к случаю, в котором совпасть
            # им нечему
            всего = _ленту_набить(80)
            print("\n### ЛЕНТА ДЛИННАЯ — строк событий в базе: %s" % всего)
            печать_круга(asyncio.run(прогон_круга()))
            # ── B.1/B.2 (BACKLOG №190): ПУСТОЕ СОСТОЯНИЕ ────────────
            #
            # СОСТОЯНИЕ БОЕВОГО ЭКРАНА: круг общий, лента длинная,
            # а приглашений и блокировок НЕТ. Ровно оно у владельца —
            # он никого не блокировал, — и ровно на нём видна пустота:
            # высота вкладки равна ленте, а «Блок» пуст.
            #
            # НА СИДИРОВАННОМ СТЕНДЕ ЭТОГО СОСТОЯНИЯ НЕТ ВОВСЕ: seed
            # наполняет и приглашения, и блок, и замер печатал «пустых
            # состояний видно 0». Мерить пустоту в ЛИЧНОЙ аптечке
            # бесполезно — там все четыре вкладки пусты и одинаковы,
            # лишней высоты не берётся ниоткуда (замер прежнего кода:
            # сверху 32, снизу 32 — симметрия БЫЛА и без правки).
            #
            # Мерка ПИШЕТ в базу и говорит это до прогона; сид
            # возвращается в `finally`.
            _приглашения_и_блок_убрать()
            print("\n### ОБЩАЯ АПТЕЧКА, ЛЕНТА ДЛИННАЯ, "
                  "ПРИГЛАШЕНИЙ И БЛОКА НЕТ")
            печать_круга(asyncio.run(прогон_круга()))
        finally:
            if наш:
                _круг_убрать()
            # СТЕНД ВОЗВРАЩАЕТСЯ ВСЕГДА, а не только когда круг завела
            # сама мерка: личный замер выше распускает и СИДИРОВАННЫЙ
            # круг. Оставленная личная аптечка превратила бы следующий
            # снимок в снимок не того состояния — шестая причина
            # неповторимости из §6.0.3. Сеет тем же `_сид_круга`,
            # что и сидирование: второй сборки круга в проекте нет
            import check_medkit_circle as _кр
            print("   стенд возвращён в сидированное: %s"
                  % ("да" if _кр.вернуть_сид() else "НЕТ"))
        return 0
    if ПУСТОЕ:
        print("РЕЖИМ --пустое: стенд будет ОПУСТОШЁН (все позиции аптечки "
              "удалены). Сказано ДО прогона, а не после.")
        удалить_всё()
    печать(asyncio.run(прогон()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
