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


ЗАМЕР_ПАНЕЛИ = r"""() => {
  const п = document.getElementById('apt-drug');
  if (!п || п.hidden) return {открыта: false};
  const О = {opacityProperty: true, visibilityProperty: true};
  const вид = e => (!e.checkVisibility || e.checkVisibility(О))
    && e.getBoundingClientRect().width > 0;
  /* «ЦВЕТНАЯ РАМКА ИЛИ ПОДЛОЖКА У ТЕКСТА» — ровно то, что запрещает
     письмо: непрозрачный фон либо ненулевая рамка у самого текста
     записи и у всего, что внутри него. */
  const цвет = e => { const c = getComputedStyle(e);
    const фон = c.backgroundColor !== 'rgba(0, 0, 0, 0)'
      && c.backgroundColor !== 'transparent';
    const рамка = ['Top', 'Right', 'Bottom', 'Left'].some(s =>
      parseFloat(c['border' + s + 'Width']) > 0
      && c['border' + s + 'Style'] !== 'none');
    return фон || рамка; };
  const секции = [...п.querySelectorAll('.apt-drug-sec')];
  const записи = [...п.querySelectorAll('.apt-drug-rec')];
  /* СВОЯ ЗАПИСЬ ОПОЗНАЁТСЯ ПО МЕТКЕ, а не по порядку: порядок — ровно
     то, что проверяет соседний шаг, и опираться на него значило бы
     спрашивать у тавтологии. */
  /* СТРОКА ИСТОЧНИКА ОДНА НА ЗАПИСЬ И НЕСЁТ МЕТКУ (№352,
     «аптечка-3», 2.3): «Ваша запись с упаковки · 23.09»,
     «Справочник vidal.ru · 23.09». Отдельной метки `.apt-drug-tag`
     больше нет — вторая строка про то же самое убрана. */
  const своя = r => /^Ваша запись/.test(
    (r.querySelector('.apt-drug-src') || {}).textContent || '');
  return {
    открыта: true,
    секции: секции.map(s => s.dataset.sec),
    заголовки: секции.map(s =>
      (s.querySelector('.apt-drug-sec-h') || {}).textContent || ''),
    метки: записи.map(r => ((r.querySelector('.apt-drug-src') || {})
      .textContent || '').split(' · ')[0]),
    источников: записи.map(r => r.querySelectorAll('.apt-drug-src').length),
    цветных: [...п.querySelectorAll('.apt-drug-txt, .apt-drug-txt *')]
      .filter(цвет).length,
    пустые: секции.filter(s => s.querySelector('.apt-drug-none'))
      .map(s => s.dataset.sec),
    кнопок_у_пустых: [...п.querySelectorAll('.apt-drug-empty-acts')]
      .map(r => [...r.querySelectorAll('button')].filter(вид)
        .map(b => b.textContent.trim())),
    выделений_в_своих: записи.filter(своя)
      .reduce((n, r) => n + r.querySelectorAll('.apt-dose-hit').length, 0),
    выделений_всего: п.querySelectorAll('.apt-dose-hit').length,
    свёрнутых: п.querySelectorAll('.apt-drug-cut').length,
    развернуть: [...п.querySelectorAll('.apt-drug-more')].filter(вид).length,
    строк_видно: [...п.querySelectorAll('.apt-drug-cut')].map(t => {
      const lh = parseFloat(getComputedStyle(t).lineHeight);
      return Math.round(t.clientHeight / lh);
    }),
    сноска: (п.querySelector('.apt-drug-vow') || {}).textContent || '',
    сносок: п.querySelectorAll('.apt-drug-vow').length,
    кнопок_внизу: [...document.querySelectorAll('#apt-drug-acts button')]
      .filter(вид).map(b => b.textContent.trim()),
    моно: [...п.querySelectorAll('*')]
      .filter(e => /mono/i.test(getComputedStyle(e).fontFamily)).length,
  };
}"""


ЗАМЕР_ФОРМЫ = r"""() => {
  const ф = document.getElementById('apt-form');
  if (!ф || !ф.classList.contains('open')) return {открыта: false};
  const О = {opacityProperty: true, visibilityProperty: true};
  const вид = e => (!e.checkVisibility || e.checkVisibility(О))
    && e.getBoundingClientRect().width > 0;
  const подписи = [...ф.querySelectorAll('label')].filter(вид);
  return {
    открыта: true,
    /* НАЧЕРТАНИЕ СПРАШИВАЕТСЯ У ВЫЧИСЛЕННОГО СТИЛЯ: класс на месте
       ещё не значит, что правило применилось (проверка 21). */
    моно: [...ф.querySelectorAll('*')].filter(вид)
      .filter(e => /mono/i.test(getComputedStyle(e).fontFamily)).length,
    прописных: подписи
      .filter(e => getComputedStyle(e).textTransform === 'uppercase').length,
    подписей: подписи.length,
    заголовки_групп: [...ф.querySelectorAll('.apt-fs-t')].filter(вид)
      .map(e => getComputedStyle(e).textTransform),
    старых: ф.querySelectorAll(
      '.input, .select, .textarea, .btn, .btn-icon, .field-label').length,
    нокат: (() => { const э = document.getElementById('apt-f-nocat');
      return э ? !э.hidden && вид(э) : null; })(),
    свёрнут_доп: (() => { const d = document.getElementById('apt-extra');
      return d ? !d.open : null; })(),
    полей: [...ф.querySelectorAll('input, select, textarea')]
      .filter(e => e.type !== 'hidden').length,
  };
}"""

ЗАМЕР_КРУГА = r"""() => {
  const о = document.getElementById('apt-circle');
  if (!о || !о.classList.contains('open')) return {открыто: false};
  const О = {opacityProperty: true, visibilityProperty: true};
  const вид = e => (!e.checkVisibility || e.checkVisibility(О))
    && e.getBoundingClientRect().width > 0;
  const лист = о.querySelector('.modal-sh');
  const тело = о.querySelector('.modal-body');
  /* ВЫСОТА ЛИСТА ПРОТИВ ВЫСОТЫ СОДЕРЖИМОГО, а не высота ТЕЛА.
     Замер: инлайновый `height` у `.modal-body` не меняет ничего —
     лист 371 px и тело 300 и с ним, и без него; высоту держит ЛИСТ
     (`height: 70vh` у него даёт 700 и 629). То есть проба, мерившая
     тело, не увидела бы растянутого окна вовсе — подлог был бы
     не найден при состоявшемся дефекте. */
  const дети = тело ? [...тело.children].filter(вид) : [];
  const занято = дети.reduce((s, e) => {
    const c = getComputedStyle(e);
    return s + e.getBoundingClientRect().height
      + parseFloat(c.marginTop) + parseFloat(c.marginBottom);
  }, 0);
  const c = тело ? getComputedStyle(тело) : null;
  const поля = (c ? parseFloat(c.paddingTop) + parseFloat(c.paddingBottom) : 0)
    + (лист && тело
       ? лист.getBoundingClientRect().height
         - тело.getBoundingClientRect().height : 0);
  return {
    открыто: true,
    высота_окна: лист ? Math.round(лист.getBoundingClientRect().height) : 0,
    запас: лист ? Math.round(лист.getBoundingClientRect().height
                             - занято - поля) : 0,
    прокрутка: тело ? тело.scrollHeight > тело.clientHeight + 1 : false,
    вкладок: [...о.querySelectorAll('[data-ctab]')].filter(вид).length,
    роли: [...о.querySelectorAll('.apt-role')].filter(вид)
      .map(e => [e.textContent.trim(),
                 getComputedStyle(e).textTransform,
                 /mono/i.test(getComputedStyle(e).fontFamily)]),
    моно: [...о.querySelectorAll('*')].filter(вид)
      .filter(e => /mono/i.test(getComputedStyle(e).fontFamily)).length,
    старых: о.querySelectorAll('.input, .btn, .badge, .field-label').length,
    людей: о.querySelectorAll('.apt-person').length,
  };
}"""

# НАБИВКА, А НЕ ПОДЛОГ: на стенде участников двое, и вопрос «растёт ли
# окно по содержимому» на двух строках не задать — при любой вёрстке
# они помещаются. Строки КЛОНИРУЮТСЯ (тот же приём, что у ленты круга
# в `check_medkit_packs`) и убираются тем же действием: окно рисует
# сервер, и вернуть его к прежнему виду можно перерисовкой.
НАБИТЬ_КРУГ = r"""(сколько) => {
  const список = document.querySelector('.apt-people');
  if (!список) return 0;
  const образец = список.querySelector('.apt-person');
  if (!образец) return 0;
  while (список.querySelectorAll('.apt-person').length < сколько)
    список.appendChild(образец.cloneNode(true));
  return список.querySelectorAll('.apt-person').length;
}"""

ПАНЕЛЬ_ОЖИДАНИЕ = {
    # имя позиции: (метки записей, пустые разделы)
    "Препарат П1": (["Ваша запись с упаковки", "Ваша запись с вкладыша"], []),
    "Препарат П2": (["Справочник vidal.ru", "Справочник vidal.ru"], []),
    "Препарат П3": (["Ваша запись с упаковки"], ["показания"]),
    "Препарат П4": ([], ["схема", "показания"]),
}

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

# ── ЧЕТЫРЕ СОСТОЯНИЯ ПАНЕЛИ ЛЕКАРСТВА (блок 2 письма «аптечка-2») ──
#   имя, вещество, своя схема, своё «от чего», схема справочника,
#   показания справочника
#
# ДЛИННАЯ ВЫДЕРЖКА У ВТОРОГО СЛУЧАЯ ОБЯЗАТЕЛЬНА: свёртка до шести
# строк не проверяется текстом, который и так короче шести строк,
# — шаг печатал бы «свёрнутых 0» и на исправном коде, и на сломанном.
# ДОЗА И ЧАСТОТА В ТЕКСТЕ ОБЯЗАТЕЛЬНЫ, и это не украшение: сервер
# отбрасывает выдержку без них как ЗАГЛУШКУ справочника («режим
# дозирования определяет врач», §5.8, задача 201), и раздел оказался бы
# пустым — шаг про свёртку ушёл бы в ПРОПУСК, а шаг про четыре случая
# показал бы «схема пуста» на позиции, заведённой со схемой.
ПАНЕЛЬ_ДЛИННО = ("Взрослым и детям старше 12 лет назначают внутрь "
                 "по 1 таблетке 3 раза в сутки после еды. " * 9)
ПАНЕЛЬ_НАБОР = [
    ("Препарат П1", "Вещество П1", "По 1 таблетке 2 раза",
     "Кашель, боль в горле.", None, None),
    ("Препарат П2", "Вещество П2", None, None,
     ПАНЕЛЬ_ДЛИННО, "Простуда, грипп, повышенная температура."),
    ("Препарат П3", "Вещество П3", "По 2 капсулы утром", None, None, None),
    ("Препарат П4", "Вещество П4", None, None, None, None),
]
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
        # ── ЧЕТЫРЕ СЛУЧАЯ ПАНЕЛИ ЛЕКАРСТВА (№352, «аптечка-2») ──────
        #
        # Панель показывает ДВА раздела, у каждого ДВА источника —
        # запись человека и выдержка справочника. Сочетаний четыре,
        # и на одной позиции их не различить: с обеими записями
        # не видно пустого состояния, а с пустыми — порядка записей.
        #
        # Имена выдуманные (§8.0): на стенде названий настоящих
        # лекарств не лежит, и в отчёт они не попадают.
        for имя, вещ, схема, отчего, спр_схема, спр_пок in ПАНЕЛЬ_НАБОР:
            п = MedkitItem(
                user_id=uid, name=имя, substance=вещ,
                form="tablet", unit="tablet", qty_total=20, qty_left=9,
                dose=1, expires_ym=_месяц(400),
                own_dosage_text=схема, own_indications_text=отчего,
                own_dosage_at=dt.datetime.utcnow() if схема else None,
                own_indications_at=(dt.datetime.utcnow() if отчего else None),
                dosage_text=спр_схема, indications_text=спр_пок,
                dosage_source=("vidal.ru" if (спр_схема or спр_пок) else None),
                dosage_fetched_at=(dt.datetime.utcnow()
                                   if (спр_схема or спр_пок) else None))
            db.add(п)
        db.commit()

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
    панели_лек, формы_замер, круг_замер = [], [], []
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

                # ── ПАНЕЛЬ ЛЕКАРСТВА: ЧЕТЫРЕ СЛУЧАЯ ───────────────
                # Открывается БОЕВЫМ путём — нажатием кнопки
                # «Инструкция» на карточке: вызов функции проверял бы
                # построитель, а не то, что до него дотягивается рука.
                for имя in ПАНЕЛЬ_ОЖИДАНИЕ:
                    стр.evaluate("(и) => { const к = [...document"
                                 ".querySelectorAll('.apt-card')].find("
                                 "c => c.querySelector('.apt-name')"
                                 ".textContent.trim() === и);"
                                 " if (к) к.scrollIntoView({block:'center'}); }",
                                 имя)
                    кн = стр.locator(".apt-card", has_text=имя).locator(
                        "[data-doses]").first
                    if not кн.count():
                        continue
                    кн.click()
                    стр.wait_for_timeout(350)
                    панели_лек.append((ш, имя, стр.evaluate(ЗАМЕР_ПАНЕЛИ)))
                    стр.keyboard.press("Escape")
                    стр.wait_for_timeout(200)

                # ── БЛОК 3: ОКНО ДОБАВЛЕНИЯ ───────────────────────
                стр.click("#apt-add")
                стр.wait_for_timeout(600)
                формы_замер.append((ш, "до", стр.evaluate(ЗАМЕР_ФОРМЫ)))
                # ПРЕДУПРЕЖДЕНИЕ О КАТЕГОРИИ — ОТВЕТ НА ПОПЫТКУ
                # СОХРАНИТЬ. Нажимается НАСТОЯЩАЯ кнопка: форма
                # отправляется обработчиком `submit`, и вызов функции
                # проверял бы не тот путь.
                # ОБЯЗАТЕЛЬНЫЕ ПОЛЯ ЗАПОЛНЯЮТСЯ, иначе до нашего кода
                # дело не доходит вовсе: `required` у срока
                # останавливает отправку силами браузера, и замер
                # показывал бы «предупреждения нет» про форму,
                # которую никто не пытался сохранить
                стр.fill("#apt-f-name", "Препарат Б3")
                стр.fill("#apt-f-exp", "2028-12")
                стр.click("#apt-save")
                стр.wait_for_timeout(900)
                формы_замер.append((ш, "после", стр.evaluate(ЗАМЕР_ФОРМЫ)))
                стр.keyboard.press("Escape")
                стр.wait_for_timeout(500)

                # ── БЛОК 3: ОКНО «ОБЩАЯ АПТЕЧКА» ──────────────────
                if стр.locator("#apt-circle-open").count():
                    стр.click("#apt-circle-open")
                    стр.wait_for_timeout(900)
                    круг_замер.append((ш, 2, стр.evaluate(ЗАМЕР_КРУГА)))
                    стало = стр.evaluate(НАБИТЬ_КРУГ, 8)
                    стр.wait_for_timeout(400)
                    круг_замер.append((ш, стало, стр.evaluate(ЗАМЕР_КРУГА)))
                    стр.keyboard.press("Escape")
                    стр.wait_for_timeout(500)
                    # ВОЗВРАТ: клоны живут в ДЕРЕВЕ, а окно круга
                    # перечитывается с сервера при каждом открытии
                    # (задача 260, D) — следующее открытие нарисует
                    # настоящий список. Стенд при этом не тронут:
                    # в базу не ушло ни строки.

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
    # ЧИСЛО У КНОПКИ СВЕРЯЕТСЯ СО СПИСКОМ, А НЕ С ВПИСАННЫМ ЧИСЛОМ.
    # Здесь стояло `== "3"`, и оно протухло в первый же заход, который
    # добавил на стенд позиции (№352, «аптечка-2»): проба краснела
    # от СВОЕГО ЖЕ посева, а не от кода. Числа приходят РАЗНЫМИ
    # путями — счётчик с ответом сетки, список из `/dosage/pending`, —
    # и расхождение между ними как раз и есть находка.
    шаг("счётчик-у-перепроверки",
        bool(ш_замер["счётчик"]) and ш_замер["счётчик"]["виден"]
        and ш_замер["счётчик"]["текст"] == str(до["строк"]),
        "у кнопки %s, в списке %s"
        % ((ш_замер["счётчик"] or {}).get("текст"), до["строк"]))
    # ── 1.3 ВИД КНОПКИ НЕ ЗАВИСИТ ОТ ЧИСЛА (2.2 «аптечки-3») ────────
    # ЗДЕСЬ ЖДАЛИ ПРИГЛУШЕНИЯ ПРИ НУЛЕ, и владелец это отменил: тусклая
    # кнопка читается как сломанная. Теперь спрашивается ОБРАТНОЕ —
    # тон не меняется, — и это не ослабление шага: прежний ловил
    # «приглушение не применилось», новый ловит «приглушение вернулось».
    шаг("при-долгах-кнопка-обычная-со-счётчиком",
        not тихо_замер["было"]["тихо"] and тихо_замер["было"]["счётчик"],
        "класс is-quiet %s, счётчик виден %s"
        % (тихо_замер["было"]["тихо"], тихо_замер["было"]["счётчик"]))
    шаг("при-нуле-вид-тот-же-и-без-счётчика",
        not тихо_замер["стало"]["тихо"] and not тихо_замер["стало"]["счётчик"]
        and тихо_замер["стало"]["тон"] == тихо_замер["было"]["тон"],
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
        str(до["строк"]) in (до["шапка"] or ""), до["шапка"])
    шаг("кнопка-поискать-в-справочнике",
        до["кнопка"] == "Поискать в справочнике", до["кнопка"])
    # РОВНО ОДНО НАЙДЕННОЕ УХОДИТ, остальные остаются: заглушка
    # справочника находит схему одному названию, и это условие замера
    шаг("найденное-ушло-из-списка",
        после["строк"] == до["строк"] - 1
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
    # ── БЛОК 3.1: ОКНО ДОБАВЛЕНИЯ ───────────────────────────────────
    формы = [(ш, к, о) for ш, к, о in формы_замер if о.get("открыта")]
    до_нажатия = [(ш, о) for ш, к, о in формы if к == "до"]
    после = [(ш, о) for ш, к, о in формы if к == "после"]
    шаг("подписи-формы-обычным-регистром",
        all(о["прописных"] == 0 and о["подписей"] > 0 for _, о in до_нажатия),
        "; ".join("%d: прописных %d из %d"
                  % (ш, о["прописных"], о["подписей"]) for ш, о in до_нажатия),
        собрано=len(до_нажатия))
    шаг("заголовки-групп-обычным-регистром",
        all(all(т == "none" for т in о["заголовки_групп"])
            for _, о in до_нажатия),
        "; ".join("%d: %s" % (ш, set(о["заголовки_групп"]))
                  for ш, о in до_нажатия),
        собрано=len(до_нажатия))
    шаг("моноширинных-в-форме-нет",
        all(о["моно"] == 0 for _, о in до_нажатия),
        "; ".join("%d: %d" % (ш, о["моно"]) for ш, о in до_нажатия if о["моно"]),
        собрано=len(до_нажатия))
    # ОРГАНОВ СТАРОЙ СИСТЕМЫ НЕТ: `.input`, `.btn`, `.field-label`
    # на экране v2 держат своё оформление и читаются чужими
    шаг("органов-старой-системы-в-форме-нет",
        all(о["старых"] == 0 for _, о in до_нажатия),
        "; ".join("%d: %d" % (ш, о["старых"]) for ш, о in до_нажатия
                  if о["старых"]),
        собрано=len(до_нажатия))
    шаг("«Дополнительно»-свёрнуто",
        all(о["свёрнут_доп"] for _, о in до_нажатия),
        "; ".join("%d: %s" % (ш, о["свёрнут_доп"]) for ш, о in до_нажатия),
        собрано=len(до_нажатия))
    # ПРЕДУПРЕЖДЕНИЕ О КАТЕГОРИИ — ТОЛЬКО ПОСЛЕ ПОПЫТКИ СОХРАНИТЬ.
    # Два замера одной формы: до нажатия скрыто, после — на виду
    шаг("предупреждение-о-категории-при-сохранении",
        bool(до_нажатия) and bool(после)
        and all(о["нокат"] is False for _, о in до_нажатия)
        and all(о["нокат"] for _, о in после),
        "до: %s; после: %s" % ([о["нокат"] for _, о in до_нажатия],
                               [о["нокат"] for _, о in после]),
        собрано=len(до_нажатия) + len(после))

    # ── БЛОК 3.2: ОКНО «ОБЩАЯ АПТЕЧКА» ──────────────────────────────
    круги = [(ш, n, о) for ш, n, о in круг_замер if о.get("открыто")]
    шаг("окно-общей-по-содержимому",
        all(not о["прокрутка"] and о["запас"] <= 24 for _, _, о in круги),
        "; ".join("%d при %d людях: запас %d px, прокрутка %s"
                  % (ш, n, о["запас"], о["прокрутка"]) for ш, n, о in круги),
        собрано=len(круги))
    шаг("три-вкладки-общей",
        all(о["вкладок"] == 3 for _, _, о in круги),
        "; ".join("%d: %d" % (ш, о["вкладок"]) for ш, _, о in круги),
        собрано=len(круги))
    роли = [(ш, р) for ш, _, о in круги for р in о["роли"]]
    шаг("метки-ролей-обычным-регистром",
        bool(роли) and all(т == "none" and not м for _, (_, т, м) in роли),
        "; ".join("%d: %s %s моно=%s" % (ш, п, т, м) for ш, (п, т, м) in роли),
        собрано=len(роли))
    шаг("моноширинных-в-общей-нет",
        all(о["моно"] == 0 for _, _, о in круги),
        "; ".join("%d: %d" % (ш, о["моно"]) for ш, _, о in круги if о["моно"]),
        собрано=len(круги))
    шаг("органов-старой-системы-в-общей-нет",
        all(о["старых"] == 0 for _, _, о in круги),
        "; ".join("%d: %d" % (ш, о["старых"]) for ш, _, о in круги
                  if о["старых"]),
        собрано=len(круги))

    # ── БЛОК 2: ПАНЕЛЬ ЛЕКАРСТВА ────────────────────────────────────
    открылись = [(ш, и, о) for ш, и, о in панели_лек if о.get("открыта")]
    шаг("панель-лекарства-открывается-с-карточки",
        len(открылись) == len(панели_лек) and bool(панели_лек),
        "открылось %d из %d" % (len(открылись), len(панели_лек)),
        собрано=len(панели_лек))
    # ПОРЯДОК РАЗДЕЛОВ НЕ ЗАВИСИТ ОТ ДАННЫХ: четыре случая дают один
    # и тот же список секций, иначе экран каждый раз новый
    порядки = {tuple(о["секции"]) for _, _, о in открылись}
    шаг("порядок-разделов-панели",
        порядки == {("схема", "показания")},
        "; ".join("%s: %s" % (и, " → ".join(о["секции"])) for _, и, о in открылись),
        собрано=len(открылись))
    заг = {tuple(о["заголовки"]) for _, _, о in открылись}
    шаг("заголовки-разделов-названы-полем",
        заг == {("Как принимать", "Показания к применению")},
        "; ".join(" / ".join(х) for х in sorted(заг)), собрано=len(открылись))
    # МЕТКИ И ПУСТЫЕ РАЗДЕЛЫ — ПО КАЖДОМУ СЛУЧАЮ ОТДЕЛЬНО: на одной
    # позиции четырёх сочетаний «своё / справочник» не различить
    расхождения = []
    for _, и, о in открылись:
        ждём = ПАНЕЛЬ_ОЖИДАНИЕ.get(и)
        if not ждём:
            continue
        метки, пусто = ждём
        if о["метки"] != метки or о["пустые"] != пусто:
            расхождения.append("%s: метки %s (ждали %s), пусто %s (ждали %s)"
                               % (и, о["метки"], метки, о["пустые"], пусто))
    шаг("четыре-случая-панели-совпали", not расхождения,
        "; ".join(расхождения) or "случаев %d" % len(ПАНЕЛЬ_ОЖИДАНИЕ),
        собрано=len(открылись))
    шаг("у-каждой-записи-одна-строка-источника",
        all(all(n == 1 for n in о["источников"]) for _, _, о in открылись),
        "; ".join("%s: %s" % (и, о["источников"]) for _, и, о in открылись
                  if any(n != 1 for n in о["источников"])),
        собрано=sum(len(о["источников"]) for _, _, о in открылись))
    шаг("цветных-рамок-и-подложек-у-текста-нет",
        all(о["цветных"] == 0 for _, _, о in открылись),
        "; ".join("%s: %d" % (и, о["цветных"]) for _, и, о in открылись
                  if о["цветных"]),
        собрано=len(открылись))
    # ВЫДЕЛЕНИЕ ДОЗИРОВКИ — ТОЛЬКО ТАМ, ГДЕ ЕГО ПОСТАВИЛ СПРАВОЧНИК
    шаг("в-записи-с-упаковки-дозировка-не-выделена",
        all(о["выделений_в_своих"] == 0 for _, _, о in открылись),
        "; ".join("%s: %d" % (и, о["выделений_в_своих"])
                  for _, и, о in открылись if о["выделений_в_своих"]),
        собрано=len(открылись))
    пустые_ряды = [(и, р) for _, и, о in открылись
                   for р in о["кнопок_у_пустых"]]
    шаг("у-пустого-раздела-есть-ход",
        all(р for _, р in пустые_ряды),
        "; ".join("%s: %s" % (и, р) for и, р in пустые_ряды),
        собрано=len(пустые_ряды))
    # СВЁРТКА: длинная выдержка спрятана, кнопка есть, видно 6 строк
    длинные = [(и, о) for _, и, о in открылись if о["свёрнутых"]]
    шаг("длинный-текст-свёрнут-до-шести-строк",
        bool(длинные)
        and all(о["развернуть"] >= о["свёрнутых"]
                and all(с <= 6 for с in о["строк_видно"]) for _, о in длинные),
        "; ".join("%s: свёрнуто %d, кнопок %d, строк %s"
                  % (и, о["свёрнутых"], о["развернуть"], о["строк_видно"])
                  for и, о in длинные),
        собрано=len(длинные))
    шаг("сноска-одна-и-внизу",
        all(о["сносок"] == 1 and "не назначение" in о["сноска"]
            for _, _, о in открылись),
        "; ".join(sorted({о["сноска"][:48] for _, _, о in открылись})),
        собрано=len(открылись))
    низы = [(и, о["кнопок_внизу"]) for _, и, о in открылись]
    шаг("подвал-панели-три-действия",
        all(к and к[-1] == "Удалить" and "Изменить" in к for _, к in низы),
        "; ".join("%s: %s" % (и, к) for и, к in низы), собрано=len(низы))
    шаг("моноширинных-в-панели-нет",
        all(о["моно"] == 0 for _, _, о in открылись),
        "; ".join("%s: %d" % (и, о["моно"]) for _, и, о in открылись
                  if о["моно"]),
        собрано=len(открылись))

    шаг("моноширинных-нет", all(n == 0 for _, n, _ in моно),
        "; ".join("%d: %d %s" % (ш, n, обр[:2]) for ш, n, обр in моно if n),
        собрано=len(моно))
    return находок


ПОДЛОГИ = [
    # ── ПОДЛОГИ БЛОКА 3 ────────────────────────────────────────────
    ("предупреждение о категории видно сразу",
     "предупреждение-о-категории-при-сохранении",
     """addEventListener('DOMContentLoaded', () => {
        const было = window.аптКатегорииПроверить;
        window.аптКатегорииПроверить = function () {
          было();
          const э = document.getElementById('apt-f-nocat');
          if (э) э.hidden = !!document.querySelector(
            '#apt-f-cats [data-cat].active');
        }; });"""),
    ("метки ролей снова прописными", "метки-ролей-обычным-регистром",
     """addEventListener('DOMContentLoaded', () => { const s =
        document.createElement('style');
        s.textContent = '.apt-role { text-transform: uppercase }';
        document.head.appendChild(s); });"""),
    # ВЫСОТА СТАВИТСЯ ИНЛАЙНОМ, А НЕ ПРАВИЛОМ: `.modal-sh` — флекс,
    # и высоту телу он считает сам; подложенное правило селектором
    # проигрывало расчёту раскладки, то есть подлог НЕ СОСТОЯЛСЯ
    # (замер: высота тела 299.6 px и с ним, и без него).
    ("окно общей аптечки фиксированной высоты", "окно-общей-по-содержимому",
     """addEventListener('DOMContentLoaded', () => {
        const было = window.аптКругОткрыть;
        window.аптКругОткрыть = async function () {
          await было();
          const л = document.querySelector('#apt-circle .modal-sh');
          if (л) л.style.height = '70vh';
        }; });"""),
    # ── ПОДЛОГИ БЛОКА 2 (панель лекарства) ─────────────────────────
    # Все три ломают ЗВЕНО ОТРИСОВКИ, а не вид: подмена идёт поверх
    # боевого построителя, и до неё панель рисуется как обычно.
    ("порядок разделов панели переставлен", "порядок-разделов-панели",
     """addEventListener('DOMContentLoaded', () => {
        const было = window.аптЛекарствоНарисовать;
        window.аптЛекарствоНарисовать = function (п, с) {
          было(п, с);
          const т = document.getElementById('apt-drug-body');
          const сек = [...т.querySelectorAll('.apt-drug-sec')];
          if (сек.length > 1) т.appendChild(сек[0]);
        }; });"""),
    ("дозировка выделена и в записи с упаковки",
     "в-записи-с-упаковки-дозировка-не-выделена",
     """addEventListener('DOMContentLoaded', () => {
        const было = window.аптЛекарствоНарисовать;
        window.аптЛекарствоНарисовать = function (п, с) {
          было(п, с);
          document.querySelectorAll('.apt-drug-rec').forEach(r => {
            const м = r.querySelector('.apt-drug-tag');
            if (м && /^Ваша запись/.test(м.textContent)) {
              const т = r.querySelector('.apt-drug-txt');
              if (т) т.classList.add('apt-dose-hit');
            }
          });
        }; });"""),
    ("служебный абзац вернулся внутрь записи", "сноска-одна-и-внизу",
     """addEventListener('DOMContentLoaded', () => {
        const было = window.аптЛекарствоНарисовать;
        window.аптЛекарствоНарисовать = function (п, с) {
          было(п, с);
          const r = document.querySelector('.apt-drug-rec');
          if (!r) return;
          const p = document.createElement('p');
          p.className = 'apt-drug-vow';
          p.textContent = 'Это выдержка из справочника, а не назначение. '
            + 'Что сказал ваш врач — в поле «Заметка» карточки.';
          r.appendChild(p);
        }; });"""),
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
    # ПРИГЛУШЕНИЕ ВЕРНУЛОСЬ — вот что теперь дефект (2.2 «аптечки-3»).
    # Подлог возвращает прежнее поведение: класс ставится при нуле,
    # и шаг обязан назвать это находкой.
    ("приглушение при нуле вернулось",
     "при-нуле-вид-тот-же-и-без-счётчика",
     """addEventListener('DOMContentLoaded', () => {
        const было = window.аптДолгиСчётчик;
        window.аптДолгиСчётчик = function (n) {
          было(n);
          const кн = document.getElementById('apt-recheck-open');
          if (кн) кн.classList.toggle('is-quiet', !n);
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

            # 5. УДАЛЕНИЕ «В ПОКУПКИ» ИЗ ПАНЕЛИ ЛЕКАРСТВА. Берётся
            # ПРОСРОЧЕННАЯ позиция: флажок «в список покупок»
            # показывается только у неё — у рабочей «Удалить» означает
            # «этой записи тут не место», и предлагать купить то,
            # от чего отказались, незачем.
            #
            # ПУТЬ ПЕРЕЕХАЛ ИЗ ФОРМЫ ПРАВКИ В ПАНЕЛЬ (№352, «аптечка-2»):
            # в форме «Удалить» стояло рядом с «Сохранить», то есть
            # необратимое соседствовало с обычным сохранением. Окно
            # подтверждения и выбор «в покупки» те же — сверка 53
            # видит кнопку переехавшей, а не пропавшей.
            уйдёт = поз("Препарат А")
            стр.click('[data-doses="%d"]' % уйдёт.id)
            стр.wait_for_timeout(700)
            видна_кнопка = стр.locator("#apt-drug-del").is_visible()
            стр.click("#apt-drug-del")
            стр.wait_for_timeout(700)
            стр.check("#apt-del-buy-chk")
            стр.click('button[onclick="аптУдалить()"]')
            стр.wait_for_timeout(1600)
            db = SessionLocal()
            в_покупках = db.query(MedkitBuyItem).filter(
                MedkitBuyItem.name == "Препарат А").count()
            db.close()
            шаг("удаление-из-панели-кладёт-в-покупки",
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
