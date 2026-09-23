# -*- coding: utf-8 -*-
"""ПРОВЕРКА 61: АПТЕЧКА ПОСЛЕ РЕДИЗАЙНА (№352, «аптечка-1»).

ПРОВЕРКА, код 1 при находке, 2 — спросить нечем (базы стенда нет,
аккаунта нет, браузера нет).

ЧТО СПРАШИВАЕТСЯ, и каждое — замером живой страницы:

  2.1 ШАПКА. Справа налево: «Добавить» (главная, цвет инструмента),
      «AI-ассистент», «Перепроверить» со счётчиком неполных карточек
      (при нуле счётчика НЕТ), дальше участники. Число у кнопки равно
      числу, которое отдаёт сервер.
  2.2 ВКЛАДКИ. Три вкладки, по умолчанию «Лекарства»; «Купить» несёт
      счётчик; пояснение ленты видно БЕЗ ПРОКРУТКИ.
  2.4 ПАНЕЛЬ «ЧЕГО НЕ ХВАТАЕТ». Сверху число неполных карточек, ниже
      одна кнопка, ниже список. «Поискать в справочнике» находит схему
      там, где её нет, и найденное УХОДИТ ИЗ СПИСКА. Нажатие на строку
      закрывает панель и открывает правку этого лекарства.
  3.1 ЧИПЫ СОСТОЯНИЯ. «Просрочено» и «Истекает за месяц» первыми
      в ряду, с числами; при нуле чипа нет (вычисленный стиль).
  3.2 КАРТОЧКА. Низ прижат: верх строки остатка у карточек ОДНОГО РЯДА
      совпадает (≤ 1 px) при разной длине названия и состава. Корзины
      на карточке нет, удаление — в окне правки. Кнопка приёма
      без заливки.
  3.3 МОНОШИРИННЫХ ЭЛЕМЕНТОВ НА ЭКРАНЕ НЕТ.

ГДЕ ЭТО ГОНЯЕТСЯ. В СВОЁМ ПРОЦЕССЕ, на КОПИИ базы стенда: проба ПИШЕТ
данные (шесть выдуманных позиций с разными пробелами и сроками), а ряд
стенда обязан быть безопасным для любого прогона (§6.0.2). Стенд
на :8899 не трогается вовсе.

СПРАВОЧНИК ЖИВЬЁМ НЕ ВЫЗЫВАЕТСЯ: `main._апт_найти_дозы` подменяется
заглушкой, которая находит схему РОВНО ОДНОМУ препарату. Это условие
самого замера, а не экономия: «нашлось у одного из трёх» проверяет,
что найденное уходит из списка, а живой справочник отвечал бы
по-разному от прогона к прогону.

ДАННЫЕ ВЫДУМАННЫЕ («Препарат А»), и это правило §8.0: названия
настоящих лекарств в пробы, фикстуры и снимки не попадают.

БРАУЗЕР ВИДИМЫЙ (§6.0.3): здесь меряются ширины и совпадение верха
элементов в ряду, а headless прячет полосу прокрутки без изъятия места.

    py check_medkit_v2.py               # все вопросы, три ширины
    py check_medkit_v2.py --ширина 1600
    py check_medkit_v2.py --контроль    # подлоги, каждый роняет СВОЮ строку
"""
import datetime as dt
import os
import socket
import sqlite3
import sys
import tempfile
import threading
import time

try:
    import probe_guard  # noqa: F401  ПРОПУСК вместо трассы (§6.0.1)
except ImportError:
    pass

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

КОРЕНЬ = os.path.dirname(os.path.abspath(__file__))
ИСХОДНАЯ = os.environ.get("STAND_DB") or os.path.join(КОРЕНЬ, "app.db")
ПОЧТА = os.environ.get("STAND_EMAIL", "screenshot@local.dev")
ПАРОЛЬ = os.environ.get("STAND_PASS", "Screenshot-Local-2026")
ШИРИНЫ = [int(ш) for ш in os.environ.get("MEDKIT_V2_WIDTHS",
                                         "1600,1280,390").split(",")]


def _пропуск(причина):
    print("ПРОПУСК: " + причина)
    sys.exit(2)


def _копия_базы():
    if "/data/" in ИСХОДНАЯ.replace("\\", "/"):
        _пропуск("путь к боевой базе — проба ходит только по стенду")
    if not os.path.exists(ИСХОДНАЯ):
        _пропуск("базы стенда нет — посейте: py make_local_user.py --seed")
    путь = os.path.join(tempfile.mkdtemp(prefix="medkit_v2_"), "app.db")
    исх, нов = sqlite3.connect(ИСХОДНАЯ), sqlite3.connect(путь)
    исх.backup(нов)
    исх.close()
    нов.close()
    return путь


os.environ["DB_PATH"] = _копия_базы()
os.environ.pop("FLY_APP_NAME", None)
sys.path.insert(0, КОРЕНЬ)

import main                                                    # noqa: E402
from database import (SessionLocal, User, MedkitItem,           # noqa: E402
                      MedkitItemCategory, MedkitCategory,
                      MedkitBuyItem, MedkitEvent)

# ── ЗАГЛУШКА СПРАВОЧНИКА ────────────────────────────────────────────
#
# Находит схему РОВНО ОДНОМУ названию. Живой vidal.ru не вызывается
# ни разу: подменяется та самая функция, которую зовут все три точки
# поиска (фон при заведении, фон при правке, кнопка панели).
НАХОДИТ = "Препарат Г"
СХЕМА = "По 1 таблетке 2 раза в день после еды."
ПОКАЗАНИЯ = "Головная боль, зубная боль."
_звали = []


async def _заглушка_справочника(поз):
    _звали.append(getattr(поз, "name", "?"))
    if НАХОДИТ.lower() in (getattr(поз, "name", "") or "").lower():
        return ((СХЕМА, "https://www.vidal.ru/drugs/proba", None,
                 ПОКАЗАНИЯ, None), "", "", "")
    return None, "в справочнике такого названия нет", "нет_названия", ""


main._апт_найти_дозы = _заглушка_справочника

# ── ВЫДУМАННЫЕ ПОЗИЦИИ ──────────────────────────────────────────────
#
# Разная длина названия и состава — условие замера 3.3: низ карточек
# в ряду обязан совпасть, ЧТО БЫ ни стояло выше. Одинаковые названия
# отвечали бы на вопрос, которого никто не задавал (§8.0).
ДЛИННОЕ_ИМЯ = "Препарат Б с очень длинным названием на две строки"
ПЯТЬ_СТРОК = ("Вещество В, вещество Г, вещество Д, вещество Е, "
              "вещество Ж, вещество З, вещество И, вещество К, "
              "вещество Л, вещество М, вещество Н")


def _месяц(сдвиг_дней):
    д = dt.date.today() + dt.timedelta(days=сдвиг_дней)
    return "%04d-%02d" % (д.year, д.month)


def _завести(uid):
    """Шесть выдуманных позиций. Возвращает сроки, которые проставлены.

    ЧИСТЯТСЯ ПОЗИЦИИ ВСЕГО КРУГА, а не только владельца, и это замер,
    а не осторожность: экран показывает множество `_апт_круг`, и первый
    прогон насчитал шесть неполных карточек вместо трёх — три лишние
    принадлежали соседу по кругу. Проба идёт по КОПИИ базы, возвращать
    чужие позиции некуда и незачем.
    """
    db = SessionLocal()
    try:
        хозяин = db.query(User).filter(User.id == uid).first()
        # СНИМОК БЕРЁТСЯ У ПОСЕВА, а не выдумывается: файл уже лежит
        # на томе, и без него состояние «у карточки есть фото»
        # на копии недостижимо (§8.0) — плитка без адреса не кнопка
        снимок = next((п.image_path for п in db.query(MedkitItem).all()
                       if п.image_path), None)
        _круг, свои = main._апт_круг(db, хозяин)
        свои = list(свои) or [uid]
        db.query(MedkitItemCategory).filter(
            MedkitItemCategory.item_id.in_(
                [i.id for i in db.query(MedkitItem)
                 .filter(MedkitItem.user_id.in_(свои)).all()] or [0])).delete(
            synchronize_session=False)
        db.query(MedkitItem).filter(MedkitItem.user_id.in_(свои)).delete(
            synchronize_session=False)
        db.commit()
        кат = (db.query(MedkitCategory)
               .filter(MedkitCategory.user_id.is_(None)).first())
        # СВОИ КАТЕГОРИИ — УСЛОВИЕ ЗАМЕРА 3.1, А НЕ УКРАШЕНИЕ (§8.0).
        # Без них ряд чипов на копии базы влезает в две строки САМ,
        # и подлог «хвост не свёрнут» не может уронить шаг по построению:
        # замер — видимых 18, строк 2 и с подлогом, и без него.
        db.query(MedkitCategory).filter(
            MedkitCategory.user_id == uid,
            MedkitCategory.name.like("Раздел %")).delete(
            synchronize_session=False)
        for б in "АБВГДЕЖЗИК":
            db.add(MedkitCategory(user_id=uid, name="Раздел %s аптечки" % б))
        db.commit()
        набор = [
            # имя, вещество, срок, своя схема, своё «от чего», категория
            ("Препарат А", "Вещество А", _месяц(-40), "По 1 таблетке",
             "Кашель.", True),
            # СРОК «ИСТЕКАЕТ» — КОНЕЦ ТЕКУЩЕГО МЕСЯЦА, а не «через восемь
            # дней», и это починка КРАСНОГО НА СТАРТЕ 2026-09-23 (№352,
            # «аптечка-2»). Срок хранится месяцем и разворачивается
            # в ПОСЛЕДНИЙ его день (§5.8), поэтому `_месяц(8)` ближе
            # к концу месяца даёт СЛЕДУЮЩИЙ месяц: 23.09 плюс 8 дней —
            # это октябрь, до конца которого 38 дней, то есть позиция
            # перестаёт быть истекающей и чип «Истекает за месяц»
            # пропадает. Проба краснела от КАЛЕНДАРЯ, а не от кода.
            # `_месяц(0)` истекает всегда: до конца текущего месяца
            # не больше 30 дней при пороге ДНЕЙ_ДО_ИСТЕЧЕНИЯ = 30.
            (ДЛИННОЕ_ИМЯ, "Вещество Б, вещество В", _месяц(0), "По 2 капсулы",
             "Простуда.", True),
            ("Препарат В", ПЯТЬ_СТРОК, _месяц(45), "По 5 мл", "Аллергия.", True),
            ("Препарат Г", "Вещество Г", _месяц(60), None, None, True),
            ("Препарат Д", None, _месяц(60), None, None, True),
            ("Препарат Е", "Вещество Е", _месяц(60), "По 1 таблетке",
             "Температура.", False),
        ]
        сроки = {}
        for имя, вещ, срок, схема, отчего, с_кат in набор:
            п = MedkitItem(user_id=uid, name=имя, substance=вещ,
                           form="tablet", unit="tablet", qty_total=20,
                           qty_left=13, dose=1, expires_ym=срок,
                           own_dosage_text=схема, own_indications_text=отчего,
                           own_dosage_at=dt.datetime.utcnow() if схема else None,
                           image_path=(снимок if имя == ДЛИННОЕ_ИМЯ else None),
                           own_indications_at=(dt.datetime.utcnow()
                                               if отчего else None))
            db.add(п)
            db.flush()
            сроки[имя] = срок
            if с_кат and кат:
                db.add(MedkitItemCategory(item_id=п.id, category_id=кат.id))
        db.commit()
        return сроки
    finally:
        db.close()


# ── СВОЙ СЕРВЕР ─────────────────────────────────────────────────────

def _свободный_порт():
    с = socket.socket()
    с.bind(("127.0.0.1", 0))
    порт = с.getsockname()[1]
    с.close()
    return порт


def _поднять():
    import uvicorn
    порт = _свободный_порт()
    конф = uvicorn.Config(main.app, host="127.0.0.1", port=порт,
                          log_level="error")
    сервер = uvicorn.Server(конф)
    поток = threading.Thread(target=сервер.run, daemon=True)
    поток.start()
    for _ in range(120):
        if сервер.started:
            return сервер, "http://127.0.0.1:%d" % порт
        time.sleep(0.25)
    _пропуск("свой сервер не поднялся за 30 с")


# ── ЗАМЕРЫ В СТРАНИЦЕ ───────────────────────────────────────────────

ШАПКА = r"""
() => {
  const кор = э => { if (!э) return null; const b = э.getBoundingClientRect();
    return {x: +b.x.toFixed(1), y: +b.y.toFixed(1), w: +b.width.toFixed(1),
            h: +b.height.toFixed(1), центр: +(b.top + b.height / 2).toFixed(1)}; };
  const видно = э => !!э && getComputedStyle(э).display !== 'none'
                  && э.getBoundingClientRect().height > 0;
  const кнопки = [...document.querySelectorAll('.apt-bar-act > *')].map(э => ({
    id: э.id, текст: (э.innerText || '').replace(/\s+/g, ' ').trim(),
    класс: э.className, x: +э.getBoundingClientRect().x.toFixed(1),
    фон: getComputedStyle(э).backgroundColor,
  }));
  const счёт = document.getElementById('apt-gaps-n');
  const h1 = document.querySelector('.v2-head-title');
  const вкладки = [...document.querySelectorAll('.apt-tabbtn')].map(э => ({
    tab: э.dataset.tab, текст: (э.innerText || '').replace(/\s+/g, ' ').trim(),
    активна: э.classList.contains('active'),
  }));
  return {
    кнопки,
    счётчик: счёт ? {виден: видно(счёт), текст: счёт.textContent.trim()} : null,
    лица: document.querySelectorAll('.apt-who-row .avatar').length,
    пригласить: видно(document.querySelector('.apt-invite')),
    h1: кор(h1),
    вкладки,
    видна: {items: !document.getElementById('tab-items').hidden,
            buy: !document.getElementById('tab-buy').hidden},
  };
}
"""

# ── 1.3 КНОПКА «ПЕРЕПРОВЕРИТЬ» ПРИ НУЛЕ НЕПОЛНЫХ КАРТОЧЕК ──────────
# Состояние «ноль» ставится БОЕВОЙ функцией счётчика — той самой,
# которой сервер сообщает число (`аптДолгиСчётчик`). Набора с нулём
# долгов у пробы нет и быть не может: шесть позиций заводятся
# с пробелами нарочно, ради остальных шагов (§8.0), а второй набор
# ради одного вида кнопки означал бы второй прогон целиком.
#
# ЧТО СПРАШИВАЕТСЯ: приглушена ли кнопка, скрыт ли счётчик и РАБОТАЕТ
# ЛИ НАЖАТИЕ. Последнее — половина требования: `disabled` тут был бы
# неправдой, обход можно запустить и когда неполных карточек нет.
ТИХАЯ_КНОПКА = r"""
async () => {
  const кн = document.getElementById('apt-recheck-open');
  const счёт = document.getElementById('apt-gaps-n');
  const тон = () => { const c = getComputedStyle(кн);
    return {цвет: c.color, рамка: c.borderTopColor}; };
  const было = {тихо: кн.classList.contains('is-quiet'),
                счётчик: !счёт.hidden, тон: тон()};
  аптДолгиСчётчик(0);
  /* ТОН СНИМАЕТСЯ ПОСЛЕ ПЕРЕХОДА, А НЕ СРАЗУ. У `.v2-btn` объявлен
     `transition: border-color`, и `getComputedStyle` сразу после смены
     класса отдаёт цвет из СЕРЕДИНЫ анимации: замер дал рамку
     rgba(255,255,255,0.14) — ровно прежнюю, — при том что правило
     применилось (цвет текста сменился в тот же миг, он без перехода).
     Тот же урок, что у контраста вкладки Enshrouded (задача 144). */
  await new Promise(r => setTimeout(r, 400));
  const стало = {тихо: кн.classList.contains('is-quiet'),
                 счётчик: !счёт.hidden, тон: тон(),
                 выключена: кн.disabled};
  кн.click();
  await new Promise(r => setTimeout(r, 400));
  стало.панель = !document.getElementById('apt-recheck-panel').hidden;
  аптДолгиЗакрыть();
  аптДолгиСчётчик(было.счётчик ? 3 : 0);
  return {было, стало};
}"""


ЧИПЫ = r"""
() => {
  const видно = э => !!э && getComputedStyle(э).display !== 'none'
                  && э.getBoundingClientRect().height > 0;
  const все = [...document.querySelectorAll('#apt-chips .chip')];
  const ещё = document.getElementById('apt-chips-more');
  const строк = () => new Set([...document.querySelectorAll('#apt-chips .chip')]
    .filter(видно).map(э => Math.round(э.getBoundingClientRect().top))).size;
  window.__ряд = {
    строк: строк(),
    видимых: все.filter(видно).length,
    // СКРЫТЫЕ — ТОЛЬКО ХВОСТ: сама кнопка «Ещё» после раскрытия
    // тоже прячется, и счёт «всех невидимых» давал бы 1 на исправном
    скрытых: все.filter(ч => ч.classList.contains('apt-chip-tail')
                          && !видно(ч)).length,
    ещё: ещё && видно(ещё) ? (ещё.innerText || '').replace(/\s+/g, ' ').trim() : null,
  };
  return все.map((ч, i) => ({
    ключ: ч.dataset.pick || (ч.hasAttribute('data-cats-open') ? 'cats' : '?'),
    место: i,
    текст: (ч.innerText || '').replace(/\s+/g, ' ').trim(),
    видно: видно(ч),
    цвет: getComputedStyle(ч).color,
  }));
}
"""

КАРТОЧКИ = r"""
() => {
  const карточки = [...document.querySelectorAll('#apt-grid .apt-card')]
    .filter(к => !к.hidden);
  const верх = э => э ? +э.getBoundingClientRect().top.toFixed(1) : null;
  const ряды = {};
  for (const к of карточки) {
    const y = Math.round(к.getBoundingClientRect().top);
    (ряды[y] = ряды[y] || []).push({
      имя: (к.querySelector('.apt-name') || {}).textContent || '',
      остаток: верх(к.querySelector('.apt-qty')),
      полоска: верх(к.querySelector('.apt-qty-meter')),
      приём: верх(к.querySelector('.apt-take')),
      действия: верх(к.querySelector('.apt-acts')),
      корзина: !!к.querySelector('[data-del]'),
      приём_фон: (() => { const б = к.querySelector('.apt-take');
        return б ? getComputedStyle(б).backgroundColor : null; })(),
    });
  }
  // МОНОШИРИННЫЕ — ПО ВЫЧИСЛЕННОЙ ГАРНИТУРЕ, а не по имени класса:
  // класс может стоять и не применяться (проверка 21 ловит ровно это)
  const моно = [];
  for (const э of document.querySelectorAll('#tab-items *')) {
    const ш = getComputedStyle(э).fontFamily || '';
    if (/mono/i.test(ш) && э.getBoundingClientRect().height > 0
        && (э.textContent || '').trim()) {
      моно.push((э.className || э.tagName) + ': '
                + (э.textContent || '').trim().slice(0, 20));
    }
  }
  return {ряды, моно: моно.slice(0, 8), моно_всего: моно.length};
}
"""

ЛЕНТА = r"""
() => {
  const н = document.querySelector('.apt-feed-note');
  if (!н) return null;
  const b = н.getBoundingClientRect();
  return {видна_без_прокрутки: b.top >= 0 && b.bottom <= window.innerHeight,
          прокрутка: window.scrollY,
          текст: (н.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 40)};
}
"""

ПАНЕЛЬ = r"""
() => {
  const п = document.getElementById('apt-recheck-panel');
  if (!п || п.hidden) return {открыта: false};
  const н = document.getElementById('apt-recheck-n');
  const к = document.getElementById('apt-recheck-btn');
  const строки = [...document.querySelectorAll('.apt-debt-row-item')];
  return {
    открыта: true,
    у_края: +(document.documentElement.clientWidth
             - п.getBoundingClientRect().right).toFixed(1),
    шапка: н ? н.textContent.trim() : null,
    кнопка: к ? к.textContent.trim() : null,
    // ПОРЯДОК: число, потом кнопка, потом список
    порядок_верный: !!(н && к && строки.length
      && (н.compareDocumentPosition(к) & 4)
      && (к.compareDocumentPosition(строки[0]) & 4)),
    строк: строки.length,
    имена: строки.map(с => (с.querySelector('.apt-debt-name') || {}).textContent || ''),
  };
}
"""

находок = 0
_строки = {}


def шаг(имя, условие, подробность="", собрано=None):
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
    ch.БАЗА, ch.ПОЧТА, ch.ПАРОЛЬ = база, ПОЧТА, ПАРОЛЬ
    ширины = ширины or ШИРИНЫ
    разбросы, моно, чипы_по_ширинам, панели = [], [], [], []
    ряды_чипов = []
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
                стр.goto(база + "/medkit", wait_until="networkidle",
                         timeout=45000)
                стр.wait_for_timeout(600)

                if ш == ширины[0]:
                    ш_замер = стр.evaluate(ШАПКА)
                    тихо_замер = стр.evaluate(ТИХАЯ_КНОПКА)
                чипы_по_ширинам.append((ш, стр.evaluate(ЧИПЫ)))
                ряд = стр.evaluate("() => window.__ряд")
                # ХВОСТ ЧИПОВ: две строки, «Ещё N» называет число
                # скрытых, нажатие их показывает
                # ВИДИМА, А НЕ «ЕСТЬ В ДЕРЕВЕ»: подлог «хвост не свёрнут»
                # прячет кнопку, и нажатие по скрытой вешало прогон
                if стр.locator("#apt-chips-more").is_visible():
                    стр.click("#apt-chips-more")
                    стр.wait_for_timeout(200)
                    стр.evaluate(ЧИПЫ)
                    ряд["после"] = стр.evaluate("() => window.__ряд")
                ряды_чипов.append((ш, ряд))
                к = стр.evaluate(КАРТОЧКИ)
                разбросы.append((ш, к["ряды"]))
                моно.append((ш, к["моно_всего"], к["моно"]))

                # ЛЕНТА: пояснение видно без прокрутки
                if стр.locator(".apt-tabbtn[data-tab=feed]").count():
                    стр.click(".apt-tabbtn[data-tab=feed]")
                    стр.wait_for_timeout(700)
                    панели.append((ш, "лента", стр.evaluate(ЛЕНТА)))
                    стр.click(".apt-tabbtn[data-tab=items]")
                    стр.wait_for_timeout(300)

                if ш == ширины[0]:
                    # ── ПАНЕЛЬ «ЧЕГО НЕ ХВАТАЕТ» ──────────────────
                    стр.click("#apt-recheck-open")
                    стр.wait_for_timeout(900)
                    до = стр.evaluate(ПАНЕЛЬ)
                    стр.click("#apt-recheck-btn")
                    стр.wait_for_function(
                        "() => { const к = document.getElementById"
                        "('apt-recheck-btn'); return к && !к.disabled; }",
                        timeout=60000)
                    стр.wait_for_timeout(900)
                    после = стр.evaluate(ПАНЕЛЬ)
                    # НАЖАТИЕ НА СТРОКУ: панель закрывается, форма открыта
                    стр.click(".apt-debt-row-item")
                    стр.wait_for_timeout(900)
                    переход = стр.evaluate(
                        "() => ({панель: !document.getElementById"
                        "('apt-recheck-panel').hidden,"
                        " форма: !!document.querySelector('#apt-form.open')})")
                кон.close()
        finally:
            бр.close()

    # ── 2.1 ШАПКА ───────────────────────────────────────────────────
    порядок = [к["id"] or к["класс"].split()[0] for к in ш_замер["кнопки"]]
    шаг("шапка-порядок-кнопок",
        порядок[-1] == "apt-add" and порядок[-2] == "apt-ai-open"
        and порядок[-3] == "apt-recheck-open",
        " → ".join(порядок))
    шаг("счётчик-у-перепроверки",
        bool(ш_замер["счётчик"]) and ш_замер["счётчик"]["виден"]
        and ш_замер["счётчик"]["текст"] == "3",
        str(ш_замер["счётчик"]))
    # ── 1.3 ПРИГЛУШЕНИЕ ПРИ НУЛЕ ────────────────────────────────────
    шаг("при-долгах-кнопка-обычная",
        not тихо_замер["было"]["тихо"] and тихо_замер["было"]["счётчик"],
        "класс is-quiet %s, счётчик виден %s"
        % (тихо_замер["было"]["тихо"], тихо_замер["было"]["счётчик"]))
    шаг("при-нуле-кнопка-приглушена-и-без-счётчика",
        тихо_замер["стало"]["тихо"] and not тихо_замер["стало"]["счётчик"]
        and тихо_замер["стало"]["тон"] != тихо_замер["было"]["тон"],
        "класс is-quiet %s, счётчик виден %s, тон %s → %s"
        % (тихо_замер["стало"]["тихо"], тихо_замер["стало"]["счётчик"],
           тихо_замер["было"]["тон"], тихо_замер["стало"]["тон"]))
    шаг("при-нуле-нажатие-работает",
        not тихо_замер["стало"]["выключена"] and тихо_замер["стало"]["панель"],
        "disabled %s, панель открылась %s"
        % (тихо_замер["стало"]["выключена"], тихо_замер["стало"]["панель"]))
    шаг("участники-лицами-либо-пригласить",
        (ш_замер["лица"] > 0) != ш_замер["пригласить"],
        "лиц %d, «Пригласить» %s" % (ш_замер["лица"], ш_замер["пригласить"]))

    # ── 2.2 ВКЛАДКИ ─────────────────────────────────────────────────
    вкл = ш_замер["вкладки"]
    шаг("три-вкладки-по-умолчанию-лекарства",
        [в["tab"] for в in вкл][:2] == ["items", "buy"]
        and вкл[0]["активна"] and ш_замер["видна"]["items"]
        and not ш_замер["видна"]["buy"],
        ", ".join("%s%s" % (в["tab"], "*" if в["активна"] else "") for в in вкл))
    л = [з for _, вид, з in панели if вид == "лента" and з]
    шаг("пояснение-ленты-видно-без-прокрутки",
        all(з["видна_без_прокрутки"] for з in л),
        "; ".join(str(з["видна_без_прокрутки"]) for з in л), собрано=len(л))

    # ── 2.4 ПАНЕЛЬ ──────────────────────────────────────────────────
    шаг("панель-справа-и-по-порядку",
        до["открыта"] and до["у_края"] <= 1 and до["порядок_верный"],
        "у края %s px, порядок %s" % (до.get("у_края"), до.get("порядок_верный")))
    шаг("шапка-панели-называет-число",
        (до["шапка"] or "").startswith("У 3 лекарств"), до["шапка"])
    шаг("кнопка-поискать-в-справочнике",
        до["кнопка"] == "Поискать в справочнике", до["кнопка"])
    шаг("найденное-ушло-из-списка",
        до["строк"] == 3 and после["строк"] == 2
        and НАХОДИТ not in " ".join(после["имена"]),
        "было %d, стало %d: %s" % (до["строк"], после["строк"],
                                   ", ".join(после["имена"])))
    шаг("строка-открывает-правку",
        переход["форма"] and not переход["панель"],
        "форма %s, панель %s" % (переход["форма"], переход["панель"]))

    # ── 3.1 ЧИПЫ СОСТОЯНИЯ ──────────────────────────────────────────
    for ш, чипы in чипы_по_ширинам[:1]:
        видимые = [ч for ч in чипы if ч["видно"]]
        просрочено = next((ч for ч in чипы if ч["ключ"] == "expired"), None)
        истекает = next((ч for ч in чипы if ч["ключ"] == "soon"), None)
        шаг("чипы-состояния-сразу-после-«Все»",
            bool(просрочено) and bool(истекает)
            and [ч["ключ"] for ч in видимые[:3]] == ["all", "expired", "soon"],
            ", ".join(ч["ключ"] for ч in видимые[:4]))
        шаг("числа-в-чипах-состояния",
            bool(просрочено) and "1" in просрочено["текст"]
            and bool(истекает) and "1" in истекает["текст"],
            "%s | %s" % ((просрочено or {}).get("текст"),
                         (истекает or {}).get("текст")))

    широкие = [(ш, р) for ш, р in ряды_чипов if ш >= 1280]
    шаг("ряд-чипов-не-выше-двух-строк",
        all(р["строк"] <= 2 for _, р in широкие),
        "; ".join("%d: %d строк, видимых %d" % (ш, р["строк"], р["видимых"])
                  for ш, р in широкие),
        собрано=len(широкие))
    с_хвостом = [(ш, р) for ш, р in ряды_чипов if р["ещё"]]
    шаг("«Ещё N» называет число скрытых и раскрывает их",
        all(str(р["скрытых"]) in р["ещё"]
            and р.get("после", {}).get("скрытых") == 0 for _, р in с_хвостом),
        "; ".join("%d: «%s» при %d скрытых" % (ш, р["ещё"], р["скрытых"])
                  for ш, р in с_хвостом),
        собрано=len(с_хвостом))

    # ── 3.2–3.3 КАРТОЧКИ ────────────────────────────────────────────
    худший = []
    for ш, ряды in разбросы:
        for y, карточки in ряды.items():
            if len(карточки) < 2:
                continue
            for поле in ("остаток", "полоска", "приём", "действия"):
                значения = [к[поле] for к in карточки if к[поле] is not None]
                if len(значения) > 1:
                    худший.append((ш, поле, round(max(значения) - min(значения), 1)))
    шаг("низ-карточек-в-ряду-совпал",
        all(р <= 1.0 for _, _, р in худший),
        "худший разброс %s" % max([("%d %s %.1f px" % х) for х in худший],
                                  default="—",
                                  key=lambda с: float(с.split()[-2])),
        собрано=len(худший))
    корзины = [к["корзина"] for _, ряды in разбросы for с in ряды.values() for к in с]
    шаг("корзины-на-карточке-нет", not any(корзины),
        "карточек с корзиной %d из %d" % (sum(корзины), len(корзины)),
        собрано=len(корзины))
    фоны = [к["приём_фон"] for _, ряды in разбросы for с in ряды.values()
            for к in с if к["приём_фон"]]
    шаг("кнопка-приёма-без-заливки",
        all(ф.startswith("rgba(0, 0, 0, 0") for ф in фоны),
        ", ".join(sorted(set(фоны))[:3]), собрано=len(фоны))
    шаг("моноширинных-нет", all(n == 0 for _, n, _ in моно),
        "; ".join("%d: %d %s" % (ш, n, обр[:2]) for ш, n, обр in моно if n),
        собрано=len(моно))
    return находок


ПОДЛОГИ = [
    ("низ карточки не прижат (прежний поток)", "низ-карточек-в-ряду-совпал",
     """addEventListener('DOMContentLoaded', () => { const s =
        document.createElement('style');
        s.textContent = '.apt-card-foot { margin-top: 0 !important; }';
        document.head.appendChild(s); });"""),
    ("дата снова моноширинная", "моноширинных-нет",
     """addEventListener('DOMContentLoaded', () => { const s =
        document.createElement('style');
        s.textContent = '.apt-exp { font-family: monospace !important; }';
        document.head.appendChild(s); });"""),
    ("чип «Истекает» показан при нуле", "числа-в-чипах-состояния",
     """addEventListener('DOMContentLoaded', () => { const s =
        document.createElement('style');
        s.textContent = '#apt-chips [data-pick=soon] .chip-n { display: none }';
        document.head.appendChild(s); });"""),
    ("хвост чипов не свёрнут (прежний ряд целиком)",
     "ряд-чипов-не-выше-двух-строк",
     """addEventListener('DOMContentLoaded', () => { const s =
        document.createElement('style');
        s.textContent = '#apt-chips .apt-chip-tail[hidden] '
          + '{ display: inline-flex !important }'
          + '#apt-chips-more { display: none !important }';
        document.head.appendChild(s); });"""),
    ("счётчик неполных карточек погашен", "счётчик-у-перепроверки",
     """addEventListener('DOMContentLoaded', () => { const s =
        document.createElement('style');
        s.textContent = '#apt-gaps-n { display: none !important; }';
        document.head.appendChild(s); });"""),
    # ── 1.3: приглушение при нуле не наступает ──────────────────────
    # Ломается ЗВЕНО: `аптДолгиСчётчик` перестаёт ставить класс.
    # Подмена идёт на ГОТОВОЙ странице (скрипт объявляет функцию
    # на верхнем уровне, и в `DOMContentLoaded` она уже есть).
    ("приглушение при нуле не наступает",
     "при-нуле-кнопка-приглушена-и-без-счётчика",
     """addEventListener('DOMContentLoaded', () => {
        const было = window.аптДолгиСчётчик;
        window.аптДолгиСчётчик = function (n) {
          было(n);
          const кн = document.getElementById('apt-recheck-open');
          if (кн) кн.classList.remove('is-quiet');
        }; });"""),
]


def прогон_пути(база):
    """БЛОК 3.4: путь человека насквозь (§6.3), результат — ИЗ БАЗЫ.

    Приём, правка, удаление «в покупки», раскрытие фото и отбор
    по «Просрочено». Ответ сервера успехом не считается: списание,
    правка и покупка проверяются строкой в базе — «ответил 200»
    о том, что в неё легло, не говорит ничего.
    """
    global находок
    находок = 0
    _строки.clear()
    from playwright.sync_api import sync_playwright
    import check_hover as ch
    import browser_window  # noqa: F401
    ch.БАЗА, ch.ПОЧТА, ch.ПАРОЛЬ = база, ПОЧТА, ПАРОЛЬ

    def поз(имя):
        db = SessionLocal()
        try:
            return db.query(MedkitItem).filter(MedkitItem.name == имя).first()
        finally:
            db.close()

    цель = поз("Препарат В")
    было_ост = цель.qty_left
    with sync_playwright() as p:
        бр = p.chromium.launch(headless=False)
        try:
            стр = бр.new_context(viewport={"width": 1600, "height": 1000}).new_page()
            ch._войти(стр)
            стр.goto(база + "/medkit", wait_until="networkidle", timeout=45000)
            стр.wait_for_timeout(500)

            # 1. ПРИЁМ: остаток в базе меньше на дозу, событие в ленте
            стр.click('[data-take="%d"]' % цель.id)
            стр.wait_for_timeout(1200)
            стало = поз("Препарат В").qty_left
            db = SessionLocal()
            событий = db.query(MedkitEvent).filter(
                MedkitEvent.kind == "take").count()
            db.close()
            шаг("приём-списал-дозу-в-базе", стало == было_ост - (цель.dose or 1),
                "было %s, стало %s" % (было_ост, стало))
            стр.click('.apt-tabbtn[data-tab=feed]')
            стр.wait_for_timeout(900)
            в_ленте = стр.locator(".apt-feed-item").count()
            шаг("приём-виден-в-ленте", событий > 0 and в_ленте > 0,
                "событий приёма %d, строк ленты %d" % (событий, в_ленте))
            стр.click('.apt-tabbtn[data-tab=items]')
            стр.wait_for_timeout(400)

            # 2. ПРАВКА: сохранённое место лежит в базе
            стр.click('[data-edit="%d"]' % цель.id)
            стр.wait_for_timeout(700)
            # ВЕЩЕСТВО, А НЕ МЕСТО И НЕ ЗАМЕТКА: «место» — это <select>,
            # а заметка лежит в свёрнутом «Дополнительно», и правка там
            # проверяла бы раскрытие блока, а не сохранение формы
            стр.fill("#apt-f-sub", "Вещество П")
            стр.click("#apt-save")
            стр.wait_for_timeout(1600)
            шаг("правка-сохранилась-в-базе",
                (поз("Препарат В").substance or "") == "Вещество П",
                "вещество в базе: %r" % (поз("Препарат В").substance,))

            # 4. ОТБОР «ПРОСРОЧЕНО»: на экране остаются только просроченные
            стр.click('#apt-chips [data-pick=expired]')
            стр.wait_for_timeout(600)
            видно = стр.evaluate(
                "() => [...document.querySelectorAll('.apt-card')]"
                ".filter(к => к.offsetParent).map(к => "
                "к.classList.contains('apt-card-dead'))")
            шаг("отбор-просрочено-оставил-просроченные",
                bool(видно) and all(видно),
                "видно карточек %d, из них просроченных %d"
                % (len(видно), sum(видно)), собрано=len(видно))
            стр.click('#apt-chips [data-pick=all]')
            стр.wait_for_timeout(400)

            # 4. РАСКРЫТИЕ ФОТО: плитка открывает системный просмотрщик
            # КНОПКА УВЕЛИЧЕНИЯ ПОВЕРХ ПЛИТКИ, а не сама плитка:
            # в сетке снимок открывает `.apt-ph-zoom` с `data-shot`
            плитка = стр.locator("#apt-grid .apt-ph-zoom[data-shot]").first
            есть_фото = плитка.count() > 0
            if есть_фото:
                плитка.click()
                стр.wait_for_timeout(700)
            открыт = стр.evaluate(
                "() => !!document.querySelector('.modal-ov.open img, "
                ".modal-ov-viewer.open')") if есть_фото else False
            if есть_фото:
                стр.keyboard.press("Escape")
                стр.wait_for_timeout(400)
            шаг("фото-раскрывается", открыт, "просмотрщик открыт %s" % открыт,
                собрано=1 if есть_фото else 0)

            # 5. УДАЛЕНИЕ «В ПОКУПКИ» из окна правки. Берётся ПРОСРОЧЕННАЯ
            # позиция: флажок «в список покупок» показывается только у неё —
            # у рабочей «Удалить» означает «этой записи тут не место»,
            # и предлагать купить то, от чего отказались, незачем
            уйдёт = поз("Препарат А")
            стр.click('[data-edit="%d"]' % уйдёт.id)
            стр.wait_for_timeout(700)
            видна_кнопка = стр.locator("#apt-form-del").is_visible()
            стр.click("#apt-form-del")
            стр.wait_for_timeout(700)
            стр.check("#apt-del-buy-chk")
            стр.click('button[onclick="аптУдалить()"]')
            стр.wait_for_timeout(1600)
            db = SessionLocal()
            в_покупках = db.query(MedkitBuyItem).filter(
                MedkitBuyItem.name == "Препарат А").count()
            db.close()
            шаг("удаление-из-правки-кладёт-в-покупки",
                видна_кнопка and поз("Препарат А") is None and в_покупках == 1,
                "кнопка %s, карточки нет %s, строк покупок %d"
                % (видна_кнопка, поз("Препарат А") is None, в_покупках))
            стр.click('.apt-tabbtn[data-tab=buy]')
            стр.wait_for_timeout(700)
            шаг("покупка-видна-во-вкладке",
                стр.locator("#tab-buy .apt-buy-item").count() > 0,
                "строк во вкладке %d"
                % стр.locator("#tab-buy .apt-buy-item").count())
            стр.click('.apt-tabbtn[data-tab=items]')
            стр.wait_for_timeout(400)

        finally:
            бр.close()
    return находок


def главная():
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.email == ПОЧТА).first()
        if not u:
            _пропуск("на стенде нет аккаунта %s" % ПОЧТА)
        uid = u.id
    finally:
        db.close()
    _завести(uid)
    сервер, база = _поднять()
    try:
        if "--контроль" in sys.argv:
            print("ЧИСТЫЙ ПРОГОН")
            н = прогон(база, ширины=ШИРИНЫ[:1])
            if н:
                print("КОНТРОЛЬ НЕДЕЙСТВИТЕЛЕН: грязная основа (находок %d)" % н)
                return 2
            не_найдено = 0
            for имя, строка, код in ПОДЛОГИ:
                print("ПОДЛОГ: %s" % имя)
                _завести(uid)
                прогон(база, подлог=код, ширины=ШИРИНЫ[:1])
                упала = _строки.get(строка) == "ПЛОХО"
                print("  → %s строку «%s»"
                      % ("НАЙДЕН, уронил" if упала else "НЕ НАЙДЕН", строка))
                не_найдено += not упала
            print("КОНТРОЛЬ: подлогов %d, не найдено %d"
                  % (len(ПОДЛОГИ), не_найдено))
            return 1 if не_найдено else 0
        if "--прогон" in sys.argv:
            print("ПУТЬ ЧЕЛОВЕКА НАСКВОЗЬ (блок 3.4)")
            н = прогон_пути(база)
            print("ИТОГ: находок %d" % н)
            return 1 if н else 0
        ширины = ШИРИНЫ
        if "--ширина" in sys.argv:
            ширины = [int(sys.argv[sys.argv.index("--ширина") + 1])]
        print("АПТЕЧКА ПОСЛЕ РЕДИЗАЙНА — ширины %s"
              % ", ".join(map(str, ширины)))
        н = прогон(база, ширины=ширины)
        print("ИТОГ: находок %d; справочник вызван %d раз (заглушка)"
              % (н, len(_звали)))
        return 1 if н else 0
    finally:
        сервер.should_exit = True


if __name__ == "__main__":
    sys.exit(главная())
