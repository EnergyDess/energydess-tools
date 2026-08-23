# -*- coding: utf-8 -*-
"""ЗАМЕР ОБЛИКА ENSHROUDED — раздела И экрана управления каталогом.

Не проверка (кода «правильно» у неё нет по половине вопросов) — МЕРКА.
Отвечает числами на вопросы, которые в постановке владельца слиты
в один:

  РАЗДЕЛ /enshrouded
  · сколько раздел занимает от экрана — полоса шапки и полоса сетки
    ОТДЕЛЬНО: они ограничиваются разными правилами и разъехаться могут
    независимо;
  · сколько карточек в ряду и какой они ширины;
  · БАННЕР: какую долю ширины коробки занимает фактически отрисованная
    картинка и сколько пикселей по бокам остаётся пустыми;
  · ВКЛАДКИ КАТЕГОРИЙ: контраст подписи, значка и числа к заливке
    ВЫБРАННОЙ вкладки — по каждой из шести;
  · ПОДПИСЬ УРОВНЯ: сколько карточек её показывают, в разбивке
    по категориям, против числа сетов с полем `lvl` в данных;
  · ЗАЗОР МЕЖДУ СОСЕДНИМИ ПОДПИСЯМИ СЛОТОВ внутри карточки.

  ЭКРАН УПРАВЛЕНИЯ /admin/enshrouded
  · ширина обёртки и таблицы против ширины экрана;
  · переносы строк в ячейках — то есть хватает ли таблице ширины;
  · воздух справа от кнопки «Править»;
  · размер миниатюры картинки.

ПРО ЗАЗОР — ГЛАВНОЕ. Меряется не ширина подписи и не ширина слота,
а РАССТОЯНИЕ МЕЖДУ ФАКТИЧЕСКИМИ ПРЯМОУГОЛЬНИКАМИ ТЕКСТА: `.slot-lbl`
шире своего текста, и по коробке зазор всегда положителен, тогда как
буквы уже слиплись. Текстовый прямоугольник берётся через
Range.getBoundingClientRect — это то, что видит глаз.

Считаются только пары слотов В ОДНОЙ СТРОКЕ (разница верхних краёв
меньше 4px): у перенесённых на другую строку «зазор» отрицателен
по построению и находкой не является.

ПРО КОНТРАСТ ЗНАЧКА И ЧИСЛА. Абсолютного порога тут нет и быть не может:
подпись выбранной вкладки — `--tool-accent-ink` на `--tool-accent`, это
3.19, и проект принял это число осознанно (BACKLOG №33). Значит образец
на месте, и вопрос звучит так: НЕ ХУЖЕ ЛИ соседи подписи. Долгом
считается значок или число, чей контраст к заливке заметно ниже
контраста самой подписи на ТОЙ ЖЕ вкладке.

ШИРИНЫ — 1920, 2560 и 390: у владельца два монитора, 1920 и 2560.
Прежний список начинался с 1440, экрана с такой шириной у него нет.

    py -m uvicorn main:app --port 8899
    py check_ens_width.py;            echo "код=$?"
    py check_ens_width.py --переход   # при какой ширине меняется число колонок
    py check_ens_width.py --колонок 5 # отрицательный контроль мерки зазоров
"""
import os, sys, json, statistics

sys.stdout.reconfigure(encoding="utf-8")

БАЗА = os.environ.get("ENSW_BASE", "http://127.0.0.1:8899")
ШИРИНЫ = [(1920, 1080, False), (2560, 1400, False), (390, 844, True)]

# ЧИСЛО КОЛОНОК МОЖНО НАВЯЗАТЬ — `py check_ens_width.py --колонок 5`.
# Это ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ мерки, а не настройка раздела: «слипшихся
# пар 0» и «карточка выросла» на текущей раскладке ничего не значат,
# пока не показано, что при другой раскладке мерка это ВИДИТ.
# Сетка при этом не правится — правило подкладывается в страницу
# на время замера, и код раздела остаётся тем же.
НАВЯЗАТЬ = None
# Отрицательный контроль контраста: вернуть значку и числу прежний цвет.
ВЕРНУТЬ_ЦВЕТ = False

ЗАМЕР_JS = r"""
(навязать) => {
  const прям = el => { const r = el.getBoundingClientRect();
                       return {x:r.x, y:r.y, w:r.width, h:r.height}; };
  // Фактический прямоугольник ТЕКСТА внутри элемента, а не коробки.
  const текстПрям = el => {
    const r = document.createRange(); r.selectNodeContents(el);
    const b = r.getBoundingClientRect(); r.detach && r.detach();
    return {x:b.x, y:b.y, w:b.width, h:b.height, t:(el.textContent||'').trim()};
  };
  // ── Контраст по WCAG 2.x. Цвет берём вычисленный, то есть уже
  //    разрешённый из токенов и color-mix; полупрозрачный смешиваем
  //    с подложкой сами — иначе «rgba(…, .5)» дало бы contrast как
  //    у непрозрачного и завысило бы число.
  const разбор = s => {
    const m = String(s).match(/[\d.]+/g) || [];
    return [ +m[0]||0, +m[1]||0, +m[2]||0, m.length>3 ? +m[3] : 1 ];
  };
  const поверх = (пер, зад) => {
    const a = пер[3];
    return [0,1,2].map(i => пер[i]*a + зад[i]*(1-a)).concat([1]);
  };
  const яркость = c => {
    const l = c.slice(0,3).map(v => { v/=255;
      return v <= 0.03928 ? v/12.92 : Math.pow((v+0.055)/1.055, 2.4); });
    return 0.2126*l[0] + 0.7152*l[1] + 0.0722*l[2];
  };
  const контраст = (пер, зад) => {
    const a = яркость(поверх(пер, зад)), b = яркость(зад);
    return +(((Math.max(a,b)+0.05)/(Math.min(a,b)+0.05))).toFixed(2);
  };

  if (навязать) {
    const st = document.createElement('style');
    st.textContent = '.sets-grid { grid-template-columns: repeat('
      + навязать + ', minmax(0, 1fr)) !important; }';
    document.head.appendChild(st);
  }

  const out = {
    экран: window.innerWidth,
    шапка: null, сетка: null, карточки: [], пары: [],
    баннеры: [], вкладки: [], уровни: {}
  };
  const бар = document.querySelector('.ens-bar-row');
  if (бар) out.шапка = прям(бар);
  const сетки = [...document.querySelectorAll('.sets-grid')];
  if (сетки.length) {
    out.сетка = прям(сетки[0]);
    const cs = getComputedStyle(сетки[0]);
    out.колонок = cs.gridTemplateColumns.split(' ').filter(Boolean).length;
    out.колонка_px = cs.gridTemplateColumns.split(' ')[0];
  }
  const карты = [...document.querySelectorAll('.set-card')];
  out.карточек_всего = карты.length;
  if (карты.length) out.карточка = прям(карты[0]);

  for (const карта of карты) {
    const имя = (карта.querySelector('.card-name')||{}).textContent || '?';
    // ── БАННЕР. Картинка вписана `object-fit: contain`, то есть её
    //    ФАКТИЧЕСКИЕ размеры в коробке считаются из натуральных, а не
    //    берутся у элемента: getBoundingClientRect отдаёт коробку.
    const б = карта.querySelector('.card-banner');
    const im = б && б.querySelector('img');
    if (б && im && im.naturalWidth) {
      const r = б.getBoundingClientRect();
      const ar = im.naturalWidth / im.naturalHeight;
      const w = Math.min(r.width, r.height * ar);
      const h = Math.min(r.height, r.width / ar);
      out.баннеры.push({
        сет: имя.trim(), кор_w: +r.width.toFixed(1), кор_h: +r.height.toFixed(1),
        ar: +ar.toFixed(3), карт_w: +w.toFixed(1), карт_h: +h.toFixed(1),
        доля_w: +(w / r.width).toFixed(3), доля_h: +(h / r.height).toFixed(3),
        пусто_бок: Math.round((r.width - w) * r.height),
        обрезка: +(im.naturalWidth / im.naturalHeight - ar).toFixed(4)
      });
    }
    // ── ПОДПИСЬ УРОВНЯ по категориям. Категория лежит на секции.
    const сек = карта.closest('.cat-sec');
    const кат = сек ? сек.getAttribute('data-cat') : '?';
    const у = out.уровни[кат] || (out.уровни[кат] = {карточек: 0, с_подписью: 0, тексты: []});
    у.карточек++;
    const tag = карта.querySelector('.lvl-tag');
    if (tag) { у.с_подписью++; if (у.тексты.length < 3) у.тексты.push(tag.textContent.trim()); }

    const lbl = [...карта.querySelectorAll('.slot-lbl')];
    for (let i = 0; i + 1 < lbl.length; i++) {
      const a = текстПрям(lbl[i]), b = текстПрям(lbl[i+1]);
      if (Math.abs(a.y - b.y) > 4) continue;      // разные строки
      out.пары.push({сет: имя.trim(), a: a.t, b: b.t,
                     зазор: +(b.x - (a.x + a.w)).toFixed(2)});
    }
  }

  // ── ВКЛАДКИ КАТЕГОРИЙ. Каждую по очереди делаем ВЫБРАННОЙ и снимаем
  //    контраст трёх её частей к фактической заливке. Иначе замер
  //    отвечал бы только про ту вкладку, что выбрана по умолчанию.
  const табы = [...document.querySelectorAll('.ens-tab')];
  const былаActive = табы.find(t => t.classList.contains('active'));
  // ПЕРЕХОД ГАСИТСЯ НА ВРЕМЯ ЗАМЕРА. `.segmented-btn` меняет фон
  // за 150 мс, и getComputedStyle сразу после смены класса отдаёт
  // ПРОМЕЖУТОЧНЫЙ цвет: первый замер дал подпись 3.19 у вкладки,
  // которая уже была выбрана, и 5.58 у пяти остальных — то есть
  // мерка описывала не заливку, а середину анимации.
  const глушь = document.createElement('style');
  глушь.textContent = '.ens-tab, .ens-tab * { transition: none !important; }';
  document.head.appendChild(глушь);
  for (const t of табы) {
    табы.forEach(x => x.classList.remove('active'));
    t.classList.add('active');
    const фон = разбор(getComputedStyle(t).backgroundColor);
    const ico = t.querySelector('.ens-tab-ico');
    const cnt = t.querySelector('.ens-tab-cnt');
    out.вкладки.push({
      кат: t.getAttribute('data-cat'),
      фон: getComputedStyle(t).backgroundColor,
      подпись: контраст(разбор(getComputedStyle(t).color), фон),
      подпись_цвет: getComputedStyle(t).color,
      значок: ico ? контраст(разбор(getComputedStyle(ico).color), фон) : null,
      значок_цвет: ico ? getComputedStyle(ico).color : null,
      число: cnt ? контраст(разбор(getComputedStyle(cnt).color), фон) : null,
      число_цвет: cnt ? getComputedStyle(cnt).color : null
    });
  }
  табы.forEach(x => x.classList.remove('active'));
  if (былаActive) былаActive.classList.add('active');
  глушь.remove();
  return out;
}
"""

# ── ЭКРАН УПРАВЛЕНИЯ. Мерка отдельная, потому что вопросы другие:
#    не «сколько занимает раздел», а «хватает ли таблице ширины».
ЗАМЕР_АДМИН_JS = r"""
() => {
  const прям = el => { const r = el.getBoundingClientRect();
                       return {x:+r.x.toFixed(1), y:+r.y.toFixed(1),
                               w:+r.width.toFixed(1), h:+r.height.toFixed(1)}; };
  const out = {экран: window.innerWidth};
  const обёртка = document.querySelector('.admin-wrap');
  const карточка = document.querySelector('.admin-panel');
  const табл = document.querySelector('#ens-table');
  if (обёртка) out.обёртка = прям(обёртка);
  if (карточка) out.карточка = прям(карточка);
  if (табл) out.таблица = прям(табл);
  const скролл = document.querySelector('.table-scroll');
  if (скролл) out.прокрутка_вбок = скролл.scrollWidth - скролл.clientWidth;

  // ПЕРЕНОС СТРОКИ В ЯЧЕЙКЕ — признак «ширины не хватает». Считаем
  // по высоте текста против одной строки: интерлиньяж берём у самой
  // ячейки, а не назначаем числом.
  const строки = [...document.querySelectorAll('#ens-rows tr')];
  out.строк = строки.length;
  out.высота_строки = строки.length ? +строки[0].getBoundingClientRect().height.toFixed(1) : 0;
  let переносов = 0, ячеек = 0;
  const по_колонкам = {};
  for (const tr of строки) {
    [...tr.children].forEach((td, i) => {
      if (td.querySelector('button, img, svg')) return;   // не текст
      const r = document.createRange(); r.selectNodeContents(td);
      const b = r.getBoundingClientRect();
      const lh = parseFloat(getComputedStyle(td).lineHeight) || 20;
      // <br> внутри «Названия» даёт две законные строки: считаем их
      // отдельно, иначе колонка объявлялась бы тесной всегда.
      const законных = td.querySelectorAll('br').length + 1;
      const строк = Math.max(1, Math.round(b.height / lh));
      ячеек++;
      if (строк > законных) { переносов++; по_колонкам[i] = (по_колонкам[i]||0) + 1; }
    });
  }
  out.переносов = переносов; out.ячеек = ячеек; out.переносы_по_колонкам = по_колонкам;

  // Ширины колонок по шапке.
  out.колонки = [...document.querySelectorAll('#ens-table thead th')]
    .map(th => ({имя: th.textContent.trim() || '(кнопка)',
                 w: +th.getBoundingClientRect().width.toFixed(1)}));

  // Воздух справа от кнопки «Править»: расстояние от её правого края
  // до правого края ячейки и до правого края таблицы.
  const кн = document.querySelector('.ens-a-edit');
  if (кн) {
    const тд = кн.closest('td'), r = кн.getBoundingClientRect();
    const t = тд.getBoundingClientRect();
    const cs = getComputedStyle(тд);
    out.кнопка = {w: +r.width.toFixed(1), h: +r.height.toFixed(1),
                  до_края_ячейки: +(t.right - r.right).toFixed(1),
                  до_края_таблицы: +(табл.getBoundingClientRect().right - r.right).toFixed(1),
                  паддинг_ячейки: cs.paddingRight, выключка: cs.textAlign};
  }
  // Миниатюра.
  const мин = document.querySelector('.ens-a-thumb');
  if (мин) {
    const r = мин.getBoundingClientRect();
    out.миниатюра = {w: +r.width.toFixed(1), h: +r.height.toFixed(1),
                     натур: [мин.naturalWidth, мин.naturalHeight]};
    const об = мин.closest('.ens-a-thumbwrap');
    if (об) out.миниатюра.область = прям(об);
  }
  return out;
}
"""


def _войти(стр):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import make_local_user as _сид
    стр.goto(f"{БАЗА}/login", wait_until="domcontentloaded", timeout=45000)
    стр.fill("input[name=email]", _сид.EMAIL)
    стр.fill("input[name=password]", _сид.PASSWORD)
    if стр.locator(".cf-turnstile").count():
        try:
            стр.wait_for_function(
                "() => { const e = document.querySelector"
                "('[name=\"cf-turnstile-response\"]'); return e && e.value; }",
                timeout=20000)
        except Exception:
            pass
    стр.click("button[type=submit]")
    стр.wait_for_timeout(2500)
    if "/login" in стр.url:
        raise RuntimeError(f"ВХОД НЕ ПРОШЁЛ: остались на {стр.url}")


# Отрицательный контроль контраста: прежние цвета значка и числа.
ПРЕЖНИЙ_ЦВЕТ = (".ens-tab.active .ens-tab-ico { color: var(--cat,"
                " var(--text-faint)) !important; }"
                ".ens-tab.active .ens-tab-cnt { color: var(--text-faint)"
                " !important; }")


def прогон():
    from playwright.sync_api import sync_playwright
    итог = {}
    with sync_playwright() as p:
        бр = p.chromium.launch()
        for ш, в, сенсор in ШИРИНЫ:
            к = бр.new_context(viewport={"width": ш, "height": в},
                               has_touch=сенсор, is_mobile=сенсор)
            стр = к.new_page()
            _войти(стр)
            стр.goto(f"{БАЗА}/enshrouded", wait_until="networkidle", timeout=60000)
            стр.wait_for_selector(".set-card", timeout=30000)
            if ВЕРНУТЬ_ЦВЕТ:
                стр.add_style_tag(content=ПРЕЖНИЙ_ЦВЕТ)
            # Картинки грузятся лениво; без ожидания naturalWidth равен
            # нулю у нижних карточек, и доля ширины считалась бы не по всем.
            стр.evaluate("() => document.querySelectorAll('img[loading]')"
                         ".forEach(i => i.loading = 'eager')")
            стр.wait_for_timeout(300)
            стр.evaluate("() => new Promise(r => { let y = 0;"
                         " const t = setInterval(() => { window.scrollTo(0, y);"
                         " y += 1200; if (y > document.body.scrollHeight)"
                         " { clearInterval(t); window.scrollTo(0,0); r(); } }, 30); })")
            try:
                стр.wait_for_function(
                    "() => [...document.querySelectorAll('.card-banner img')]"
                    ".every(i => i.complete && i.naturalWidth)", timeout=45000)
            except Exception:
                pass
            стр.wait_for_timeout(500)
            итог[ш] = стр.evaluate(ЗАМЕР_JS, НАВЯЗАТЬ)

            стр.goto(f"{БАЗА}/admin/enshrouded", wait_until="networkidle", timeout=60000)
            стр.wait_for_selector("#ens-rows tr", timeout=30000)
            стр.wait_for_timeout(400)
            итог[ш]["каталог"] = стр.evaluate(ЗАМЕР_АДМИН_JS)
            к.close()
        бр.close()
    return итог


def переход():
    """При какой ширине окна меняется число колонок сетки.

    Не бинарный поиск, а ПРОХОД шагом 10px: число колонок функция
    не монотонная по построению (медиазапросы могут задать что угодно),
    и бинарный поиск нашёл бы одну границу из нескольких.
    """
    from playwright.sync_api import sync_playwright
    ряд = []
    with sync_playwright() as p:
        бр = p.chromium.launch()
        к = бр.new_context(viewport={"width": 1200, "height": 900})
        стр = к.new_page()
        _войти(стр)
        стр.goto(f"{БАЗА}/enshrouded", wait_until="networkidle", timeout=60000)
        стр.wait_for_selector(".set-card", timeout=30000)
        for ш in range(600, 2801, 10):
            стр.set_viewport_size({"width": ш, "height": 900})
            n = стр.evaluate(
                "() => { const g = document.querySelector('.sets-grid');"
                " if (!g) return 0;"
                " const cs = getComputedStyle(g).gridTemplateColumns;"
                " const c = document.querySelector('.set-card');"
                " return [cs.split(' ').filter(Boolean).length,"
                "  c ? +c.getBoundingClientRect().width.toFixed(1) : 0]; }")
            ряд.append((ш, n[0], n[1]))
        к.close(); бр.close()
    print("ПЕРЕХОДЫ ЧИСЛА КОЛОНОК (шаг 10px по ширине окна)")
    пред = None
    for ш, n, w in ряд:
        if пред is not None and n != пред:
            print(f"  {пред} → {n} колонок между {ш-10} и {ш} px; "
                  f"карточка становится {w}")
        пред = n
    for ш, n, w in ряд:
        if ш in (1440, 1920, 2560, 2800):
            print(f"  на {ш}: колонок {n}, карточка {w}")


def печать(итог):
    for ш, d in итог.items():
        print(f"\n══ ШИРИНА ОКНА {ш} ═══════════════════════════════════")
        э = d["экран"]
        for имя, ключ in (("шапка (.ens-bar-row)", "шапка"),
                          ("сетка (.sets-grid)", "сетка"),
                          ("карточка", "карточка")):
            r = d.get(ключ)
            if not r:
                print(f"  {имя:24} — нет в дереве"); continue
            print(f"  {имя:24} ширина {r['w']:7.1f} из {э} "
                  f"({100*r['w']/э:5.1f}%), левый край {round(r['x'],1)}")
        print(f"  колонок в сетке          {d.get('колонок','?')} "
              f"(колонка {d.get('колонка_px','?')})")
        print(f"  карточек всего           {d.get('карточек_всего',0)}")

        # ── БАННЕР
        б = d.get("баннеры") or []
        if б:
            доли = [x["доля_w"] for x in б]
            полных = sum(1 for x in доли if x >= 0.999)
            print(f"\n  БАННЕР: коробка {б[0]['кор_w']}×{б[0]['кор_h']}, "
                  f"картинок замерено {len(б)}")
            print(f"    доля ширины  мин {min(доли):.3f} / медиана "
                  f"{statistics.median(доли):.3f} / макс {max(доли):.3f}")
            print(f"    заполняют ширину коробки ЦЕЛИКОМ   {полных} из {len(б)}")
            print(f"    пусто по бокам, px²  медиана "
                  f"{int(statistics.median(x['пусто_бок'] for x in б))}")
            узкие = sorted(б, key=lambda x: x["доля_w"])[:3]
            for x in узкие:
                print(f"      {x['доля_w']:.3f}  ar {x['ar']:.3f}  "
                      f"картинка {x['карт_w']}×{x['карт_h']}  — {x['сет']}")

        # ── ВКЛАДКИ
        в = d.get("вкладки") or []
        if в:
            print("\n  ВКЛАДКИ КАТЕГОРИЙ — контраст к заливке ВЫБРАННОЙ вкладки")
            print("    категория      подпись   значок    число")
            for t in в:
                зн = f"{t['значок']:.2f}" if t['значок'] else "  —  "
                чс = f"{t['число']:.2f}" if t['число'] else "  —  "
                метка = ""
                for имя, знач in (("значок", t['значок']), ("число", t['число'])):
                    if знач and знач < t['подпись'] - 0.3:
                        метка += f"  ← {имя} ХУЖЕ подписи"
                print(f"    {t['кат']:<14} {t['подпись']:5.2f}     {зн:>6}   {чс:>6}{метка}")

        # ── ПОДПИСЬ УРОВНЯ
        у = d.get("уровни") or {}
        if у:
            print("\n  ПОДПИСЬ УРОВНЯ НА КАРТОЧКЕ")
            for кат, v in у.items():
                прим = ("  напр. «" + v["тексты"][0] + "»") if v["тексты"] else ""
                print(f"    {кат:<12} карточек {v['карточек']:>3}, "
                      f"с подписью {v['с_подписью']:>3}{прим}")

        # ── ЗАЗОРЫ
        пары = d["пары"]
        if not пары:
            print("\n  пар подписей             НЕТ")
        else:
            зазоры = [p["зазор"] for p in пары]
            плохие = [p for p in пары if p["зазор"] <= 0]
            print(f"\n  пар подписей в строке    {len(пары)}")
            print(f"  зазор мин / медиана / макс   "
                  f"{min(зазоры):.2f} / {statistics.median(зазоры):.2f} / {max(зазоры):.2f}")
            print(f"  СЛИПШИХСЯ ПАР (зазор ≤ 0)    {len(плохие)}")
            for p in плохие[:12]:
                print(f"      {p['зазор']:7.2f}  «{p['a']}» + «{p['b']}»   — {p['сет']}")
            if len(плохие) > 12:
                print(f"      … ещё {len(плохие)-12}")

        # ── КАТАЛОГ В АДМИНКЕ
        к = d.get("каталог") or {}
        if к:
            print(f"\n  КАТАЛОГ /admin/enshrouded")
            for имя, ключ in (("обёртка (.admin-wrap)", "обёртка"),
                              ("карточка (.admin-panel)", "карточка"),
                              ("таблица", "таблица")):
                r = к.get(ключ)
                if not r:
                    print(f"    {имя:26} — нет в дереве"); continue
                print(f"    {имя:26} ширина {r['w']:7.1f} из {к['экран']} "
                      f"({100*r['w']/к['экран']:5.1f}%), левый край {r['x']}")
            print(f"    прокрутка вбок             {к.get('прокрутка_вбок','?')}")
            print(f"    строк / переносов          {к.get('строк')} / "
                  f"{к.get('переносов')} из {к.get('ячеек')} ячеек "
                  f"{к.get('переносы_по_колонкам')}")
            print(f"    высота строки              {к.get('высота_строки')}")
            кол = к.get("колонки") or []
            if кол:
                print("    колонки: " + ", ".join(f"{c['имя']} {c['w']:.0f}" for c in кол))
            кн = к.get("кнопка")
            if кн:
                print(f"    кнопка «Править»           {кн['w']}×{кн['h']}, "
                      f"до края ячейки {кн['до_края_ячейки']}, "
                      f"до края таблицы {кн['до_края_таблицы']}, "
                      f"паддинг ячейки {кн['паддинг_ячейки']}, выключка {кн['выключка']}")
            мн = к.get("миниатюра")
            if мн:
                об = мн.get("область") or {}
                print(f"    миниатюра                  {мн['w']}×{мн['h']} "
                      f"(натуральная {мн['натур'][0]}×{мн['натур'][1]}), "
                      f"область нажатия {об.get('w')}×{об.get('h')}")


if __name__ == "__main__":
    if "--переход" in sys.argv:
        переход(); sys.exit(0)
    if "--колонок" in sys.argv:
        НАВЯЗАТЬ = int(sys.argv[sys.argv.index("--колонок") + 1])
        print(f"КОНТРОЛЬ: навязано {НАВЯЗАТЬ} колонок на КАЖДОЙ ширине")
    if "--прежний-цвет" in sys.argv:
        ВЕРНУТЬ_ЦВЕТ = True
        print("КОНТРОЛЬ: значку и числу вкладки возвращён ПРЕЖНИЙ цвет")
    итог = прогон()
    печать(итог)
    if "--json" in sys.argv:
        путь = sys.argv[sys.argv.index("--json") + 1]
        with open(путь, "w", encoding="utf-8") as f:
            json.dump(итог, f, ensure_ascii=False, indent=1)
        print(f"\nсырые числа: {путь}")
    плохих = sum(1 for d in итог.values() for p in d["пары"] if p["зазор"] <= 0)
    тусклых = sum(1 for d in итог.values() for t in (d.get("вкладки") or [])
                  for з in (t["значок"], t["число"])
                  if з and з < t["подпись"] - 0.3)
    print(f"\nИТОГО СЛИПШИХСЯ ПАР ПО ТРЁМ ШИРИНАМ: {плохих}")
    print(f"ИТОГО ЧАСТЕЙ ВКЛАДКИ ТУСКЛЕЕ ПОДПИСИ:  {тусклых}")
    sys.exit(1 if (плохих or тусклых) else 0)
