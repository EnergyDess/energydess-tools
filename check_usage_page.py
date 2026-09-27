"""ПРОВЕРКА 70: СТРАНИЦА «РАСХОД» `/admin/usage` (№352, письмо «Расход»).

Зачем. Страница считает деньги: сколько потрачено за период, на что
и кем. Сумма, разошедшаяся с базой, выглядит так же уверенно, как верная,
и по ней решают, пополнять ли счёт и сколько брать за подписку. Поэтому
числа сверяются с ПРЯМЫМ запросом к базе, а не с кодом страницы: сверка
с её же функцией была бы тавтологией.

Две части, обе на КОПИИ базы стенда (стенд не трогается вовсе):

  А. В процессе приложения, без браузера:
     · сумма трёх периодов (7 дней, 30 дней, всё время) против SQL —
       разница 0; сумма столбиков графика — сумма периода;
     · отбор по инструменту (HH) против SQL по префиксу имени операции;
     · «активных» против SQL;
     · история остатка ПОПОЛНЯЕТСЯ: суточный запуск `balance_check`
       (остаток — заглушкой) добавляет строку, повтор в те же сутки —
       нет. Перед замером сутки в истории копии очищаются: мерится
       ПРИРОСТ, а не то, что лежало.
  Б. Живая страница в ВИДИМОМ браузере (§6.0.3: вопрос про ширину,
     headless прячет полосу прокрутки без изъятия места) на своём стенде
     по той же копии и со своей заглушкой остатка:
     · ничто не шире окна на 390 / 1280 / 1920 / 2560 и прокрутки вбок
       нет; законный срез — ТОЛЬКО своя прокрутка вбок (`overflow-x:
       auto|scroll`), а не край `clip` каркаса (тот же довод, что у
       проверки 69);
     · на 390 строки таблиц — карточки (`display: block`), шапки таблиц
       на экране нет;
     · моноширинных узлов в содержимом страницы 0 (прежняя страница
       была моноширинной целиком);
     · подсказка графика: сумма её строк равна сумме столбика, и она
       не вылезает за область графика — у крайних столбиков тоже.

Модель не вызывается ни разу; остаток OpenRouter — заглушка (в части А —
подменой функции, в части Б — своим HTTP-сервером, как у проверки 46).

ПИСЬМО «РАСХОД-2» (№352) РАСШИРИЛО ПРОБУ, и четыре пункта §6.0.3 здесь:
  · прежняя формулировка — суммы трёх периодов (7, 30, всё время);
  · новая — те же плюс пресет 90 и СВОЙ отрезок с границей сверху;
    сравнение с прошлым отрезком ТОЙ ЖЕ длины (на копии стенда против
    прямого запроса и на выдуманных данных с известной дельтой +50 % /
    −25 % / +25 п.п.); стрелки не уводят в будущее; путь по календарю
    своего периода и ширина с открытым календарём на 390;
  · прежняя стала негодной не потому, что врала, а потому, что страница
    получила отрезки, сравнение и календарь, а о них прежняя не спрашивала
    ничего; ни один прежний шаг не снят и не ослаблен — вопрос только шире;
  · отрицательный контроль на новой формулировке — подлог №4 ниже.

БЛОК 2 ТОГО ЖЕ ПИСЬМА (график по макету, «Токены», таблицы) — ещё раз
четыре пункта §6.0.3:
  · прежняя формулировка — сумма столбиков против суммы периода, ширина,
    моноширинные, подсказка у крайних столбиков;
  · новая — те же плюс, у ОБОИХ графиков: подписей видно столько же,
    сколько столбиков, каждая по центру своего столбика и без наложений;
    столбик не шире 40 px; промежуток между частями столбика 2 px;
    у дня без расхода — засечка у нуля; сетка из 4–5 делений, подпись
    деления на своей линии, ось левее столбиков. Токены — сумма столбиков
    против прямого запроса (промпт + ответ удачных вызовов); доля кэша
    в подписи — та же, что на плитке. Таблицы — строки инструментов
    в сумме дают сумму периода, операции внутри — сумму инструмента,
    свёрнуты при загрузке и раскрываются нажатием; мин и макс операции
    и модели — против MIN/MAX прямым запросом. Подсказка пустого дня —
    «записей нет». День без записей заводится на КОПИИ (`_день_без_записей`):
    на засеянном стенде таких дней может не оказаться, и шаг «засечка»
    был бы ПРОПУСКОМ, а подлог №6 — невидимым;
  · прежняя стала негодной потому, что графика с осью, подписями
    и засечкой, карточки токенов и мин/макс не было — вопрос только шире,
    ни один прежний шаг не снят;
  · контроль на новой формулировке — подлоги №5 и №6.

Подлоги (`--контроль`), у каждого ДОКАЗАТЕЛЬСТВО независимо от вердикта:
  №1 цена одной строки подменена В ПАМЯТИ страницы — сумма расходится
     с базой, шаг сверки обязан упасть;
  №2 история остатка не пишется — шаг «пополняется» обязан упасть;
  №3 снято правило «строка таблицы — карточка» на 390 — шаг «ничто
     не шире окна» обязан упасть;
  №4 (письмо «Расход-2», №1) прошлый отрезок на сутки ДЛИННЕЕ выбранного —
     шаги «сравнение/7» и «сравнение/выдуманные» обязаны упасть;
  №5 (письмо «Расход-2», №2) подписи под столбиками сняты — шаг
     «подписи» обязан упасть;
  №6 (письмо «Расход-2», №3) засечка у дней без расхода снята — шаг
     «засечка» обязан упасть.

    py check_usage_page.py              # код 1 при беде, 2 — нечем проверить
    py check_usage_page.py --контроль   # шесть подлогов
"""
import collections
import contextlib
import http.server
import io
import os
import re
import sqlite3
import sys
import tempfile
import threading
from datetime import datetime, timedelta, time as _время, timezone
from zoneinfo import ZoneInfo

import probe_guard  # noqa: F401  ПРОПУСК вместо трассы (§6.0.1)

sys.stdout.reconfigure(encoding="utf-8")
КОРЕНЬ = os.path.dirname(os.path.abspath(__file__))
ПОЧТА = "screenshot@local.dev"
МСК = ZoneInfo("Europe/Moscow")
ШИРИНЫ = (390, 1280, 1920, 2560)
ДОПУСК = 1e-9

шаги = []


def шаг(имя, условие, подробно="", собрано=None):
    """Исход шага. `собрано=0` — замер не состоялся: ПРОПУСК, а не OK."""
    if собрано == 0:
        исход = "ПРОПУСК"
    else:
        исход = "OK" if условие else "ПЛОХО"
    шаги.append((имя, исход, подробно))
    print("  %-7s %s%s" % (исход, имя, (" — " + подробно) if подробно else ""))
    return исход


def _полночь(день):
    """Полночь московских суток → строка UTC для SQLite."""
    м = datetime.combine(день, _время(0), МСК).astimezone(ZoneInfo("UTC"))
    return м.replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S.%f")


def _граница(дней):
    """Полночь первых московских суток периода → строка UTC для SQLite."""
    if дней is None:
        return None
    return _полночь(datetime.now(МСК).date() - timedelta(days=дней - 1))


def _sql(база, дней, префикс=None, с_дня=None, по_дня=None):
    """(сумма с ценой, строк в периоде, людей) — прямым запросом, без кода
    страницы. Свой отрезок — `с_дня`/`по_дня` (даты включительно)."""
    c = sqlite3.connect(база)
    try:
        где, арг = [], []
        г = _полночь(с_дня) if с_дня else _граница(дней)
        if г:
            где.append("created_at >= ?")
            арг.append(г)
        if по_дня:
            где.append("created_at < ?")
            арг.append(_полночь(по_дня + timedelta(days=1)))
        if префикс:
            где.append("tool LIKE ?")
            арг.append(префикс + "%")
        w = (" WHERE " + " AND ".join(где)) if где else ""
        строк = c.execute("SELECT COUNT(*) FROM model_usage" + w, арг).fetchone()[0]
        людей = c.execute("SELECT COUNT(DISTINCT user_id) FROM model_usage"
                          + w + (" AND" if где else " WHERE") + " user_id IS NOT NULL",
                          арг).fetchone()[0]
        сумма = c.execute("SELECT COALESCE(SUM(cost), 0) FROM model_usage" + w
                          + (" AND" if где else " WHERE")
                          + " ok = 1 AND cost_missing = 0 AND cost IS NOT NULL",
                          арг).fetchone()[0]
        return сумма, строк, людей
    finally:
        c.close()


def _копия():
    import check_usage_balance as ч46
    каталог = tempfile.mkdtemp(prefix="usage_page_")
    return ч46._копия_базы(каталог), каталог


def _день_без_записей(база):
    """Засечка у нуля мерится на дне, где записей НЕТ: на КОПИИ убираются
    строки расхода суток `сегодня − 3`. Посев кладёт записи почти каждый
    день, и без этого шаг «засечка» мог бы стать ПРОПУСКОМ, а подлог №6 —
    невидимым. Стенд не трогается: копия своя."""
    день = datetime.now(МСК).date() - timedelta(days=3)
    c = sqlite3.connect(база)
    try:
        c.execute("DELETE FROM model_usage WHERE created_at >= ? AND created_at < ?",
                  (_полночь(день), _полночь(день + timedelta(days=1))))
        c.commit()
    finally:
        c.close()
    return день


def _sql_токены(база, дней):
    """Все токены удачных вызовов периода — промпт плюс ответ."""
    c = sqlite3.connect(база)
    try:
        г = _граница(дней)
        return c.execute("SELECT COALESCE(SUM(COALESCE(prompt_tokens, 0) + COALESCE(completion_tokens, 0)), 0)"
                         " FROM model_usage WHERE ok = 1" + (" AND created_at >= ?" if г else ""),
                         (г,) if г else ()).fetchone()[0]
    finally:
        c.close()


def _sql_мин_макс(база, колонка, имя, дней):
    """MIN и MAX цены ОДНОЙ операции (удачной, с ценой) — прямым запросом."""
    c = sqlite3.connect(база)
    try:
        г = _граница(дней)
        return c.execute("SELECT MIN(cost), MAX(cost) FROM model_usage WHERE %s = ?"
                         " AND ok = 1 AND cost_missing = 0 AND cost IS NOT NULL" % колонка
                         + (" AND created_at >= ?" if г else ""),
                         (имя, г) if г else (имя,)).fetchone()
    finally:
        c.close()


# ── ЧАСТЬ А: В ПРОЦЕССЕ ПРИЛОЖЕНИЯ ───────────────────────────────────

class _Приложение:
    """`main` импортируется ОДИН раз на копии: движок читает `DB_PATH`
    при импорте. Остаток OpenRouter — подменой: сети нет вовсе."""

    def __init__(self, база, каталог):
        os.environ["DB_PATH"] = база
        os.environ.pop("FLY_APP_NAME", None)
        import main
        import balance_check
        from auth import create_token
        from fastapi.testclient import TestClient
        self.main, self.бк, self.база = main, balance_check, база
        main._расход_остаток_спросить = lambda: {
            "остаток": 11.5, "причина": None, "подробно": "",
            "при": datetime.now(timezone.utc).replace(tzinfo=None), "последний": None}
        balance_check.DB_PATH = база
        balance_check.СОСТОЯНИЕ = os.path.join(каталог, "balance_alert.json")
        balance_check.остаток_openrouter = lambda ключ, адрес=None: 11.5
        c = sqlite3.connect(база)
        строка = c.execute("SELECT id FROM users WHERE email = ?", (ПОЧТА,)).fetchone()
        c.close()
        if not строка:
            raise ConnectionError("на копии стенда нет аккаунта %s — посейте стенд" % ПОЧТА)
        self.клиент = TestClient(main.app)
        self.клиент.cookies.set("access_token", create_token(строка[0]))

    def страница(self, запрос=""):
        r = self.клиент.get("/admin/usage" + запрос)
        if r.status_code != 200:
            raise AssertionError("страница ответила HTTP %d" % r.status_code)
        return r.text

    def суточный_запуск(self):
        """Один проход `balance.yml` без отправки: история и решение."""
        os.environ["OPENROUTER_API_KEY"] = "probe-not-a-real-key"
        with contextlib.redirect_stdout(io.StringIO()):
            код = self.бк.main([])
        return код


def _страничная_сумма(html):
    м = re.search(r'id="usage-spent" data-sum="([^"]+)"', html)
    return float(м.group(1)) if м else None


def _сумма_столбиков(html):
    return sum(float(x) for x in re.findall(r'data-total="([^"]+)"', html))


def _группы(html):
    """{группа: (сумма строки инструмента, [суммы операций], скрыто операций,
    всего операций)} — таблица «По операциям», свёрнутая по инструменту."""
    итог = {}
    for м in re.finditer(r'<tbody class="usage-tgroup[^"]*" data-group="([a-z]+)">(.*?)</tbody>',
                         html, re.S):
        тело = м.group(2)
        сум = float(re.search(r'data-group-sum="([^"]+)"', тело).group(1))
        опер = re.findall(r'<tr class="usage-op"[^>]*>', тело)
        итог[м.group(1)] = (сум, [float(re.search(r'data-sum="([^"]+)"', о).group(1)) for о in опер],
                            sum(1 for о in опер if re.search(r"\shidden\b", о)), len(опер))
    return итог


def _мин_макс_строк(html, атр):
    """[(имя, мин, макс)] строк таблицы по `data-<атр>` (tool либо model)."""
    итог = []
    for м in re.finditer(r'<tr [^>]*\bdata-%s="([^"]+)"[^>]*>' % атр, html):
        тег = м.group(0)
        мин = re.search(r'data-min="([^"]*)"', тег).group(1)
        макс = re.search(r'data-max="([^"]*)"', тег).group(1)
        итог.append((м.group(1), float(мин) if мин else None, float(макс) if макс else None))
    return итог


def _история(база):
    c = sqlite3.connect(база)
    try:
        return c.execute("SELECT COUNT(*) FROM balance_history").fetchone()[0]
    finally:
        c.close()


def _атрибуты(html, ид):
    """data-* узла с данным id — словарём."""
    м = re.search(r'<[a-z]+[^>]*\bid="%s"[^>]*>' % re.escape(ид), html)
    return dict(re.findall(r'data-([a-z-]+)="([^"]*)"', м.group(0))) if м else {}


def _ссылка(html, ид):
    """(from, to) ссылки-стрелки либо None, если стрелка выключена."""
    м = re.search(r'<a [^>]*\bid="%s"[^>]*\bhref="([^"]+)"' % re.escape(ид), html)
    if not м:
        return None
    адрес = м.group(1).replace("&amp;", "&")
    return tuple(re.search(r"\b%s=([0-9-]+)" % к, адрес).group(1) for к in ("from", "to"))


def _выдуманные(main):
    """Сравнение на ВЫДУМАННЫХ данных — своя база в памяти, «сегодня»
    закреплено. Текущие 7 суток: 4 операции на 0.60 $ (средняя 0.15),
    кэш 50 %; прошлые 7 суток: 2 операции на 0.40 $ (0.20), кэш 25 %.
    Известно заранее: +50 % расхода, −25 % цены операции, +25 п.п. кэша."""
    import database
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    движок = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    database.Base.metadata.create_all(движок)
    db = sessionmaker(bind=движок)()
    сейчас = datetime(2026, 3, 18, 9, 0)                  # UTC: 12:00 по Москве
    сегодня = сейчас.replace(tzinfo=ZoneInfo("UTC")).astimezone(МСК).date()

    def строка(назад, цена, кэш):
        день = сегодня - timedelta(days=назад)
        момент = datetime.combine(день, _время(12), МСК).astimezone(ZoneInfo("UTC"))
        db.add(database.ModelUsage(created_at=момент.replace(tzinfo=None), tool="hh-letter",
                                   model="anthropic/claude-opus-4-8", prompt_tokens=1000,
                                   completion_tokens=500, cached_tokens=кэш, cost=цена,
                                   cost_missing=False, ok=True))
    for назад, цена in ((0, 0.10), (1, 0.20), (2, 0.15), (6, 0.15)):
        строка(назад, цена, 500)
    for назад in (13, 7):
        строка(назад, 0.20, 250)
    db.commit()
    try:
        return main.расход_сводка(db, "7", сейчас=сейчас)["сравнение"]
    finally:
        db.close()


def часть_а(прил):
    print("ЧАСТЬ А: сверка с базой (копия стенда, в процессе приложения)")
    замер = {}
    сегодня = datetime.now(МСК).date()
    # ТРИ ПРЕСЕТА, «ВСЁ ВРЕМЯ» И ОДИН СВОЙ ОТРЕЗОК («Расход-2», 1.5):
    # свой — 10 суток, кончающиеся 5 суток назад, с границей СВЕРХУ
    свой = (сегодня - timedelta(days=14), сегодня - timedelta(days=5))
    for код, дней in (("7", 7), ("30", 30), ("90", 90), ("all", None), ("свой", None)):
        if код == "свой":
            html = прил.страница("?from=%s&to=%s" % свой)
            база_сумма, строк, _ = _sql(прил.база, None, с_дня=свой[0], по_дня=свой[1])
        else:
            html = прил.страница("?p=" + код)
            база_сумма, строк, _ = _sql(прил.база, дней)
        стр = _страничная_сумма(html)
        столбики = _сумма_столбиков(html)
        разница = None if стр is None else abs(стр - база_сумма)
        замер[код] = (стр, база_сумма)
        шаг("сумма/" + код, разница is not None and разница < ДОПУСК,
            "страница %s, база %.10f, разница %s" % (стр, база_сумма, разница),
            собрано=строк)
        шаг("график/" + код, стр is not None and abs(столбики - стр) < ДОПУСК,
            "столбики %.10f против суммы периода %s" % (столбики, стр), собрано=строк)

    # СРАВНЕНИЕ НА КОПИИ СТЕНДА: у «7 дней» прошлый отрезок той же длины
    # (−13…−7 суток) — против прямого запроса. Его сумма и границы стоят
    # на плитке атрибутами; прошлый отрезок другой длины (подлог №4)
    # разойдётся и по границам, и по сумме.
    html = прил.страница("?p=7")
    а = _атрибуты(html, "usage-spent-tile")
    п_с, п_по = сегодня - timedelta(days=13), сегодня - timedelta(days=7)
    база_п, строк_п, _ = _sql(прил.база, None, с_дня=п_с, по_дня=п_по)
    стр_п = float(а["prev-sum"]) if а.get("prev-sum") else None
    замер["прошлый"] = (int(а.get("prev-days") or 0), а.get("prev-from"), а.get("prev-to"), стр_п, база_п)
    шаг("сравнение/7", а.get("prev-days") == "7" and а.get("prev-from") == п_с.isoformat()
        and а.get("prev-to") == п_по.isoformat() and стр_п is not None
        and abs(стр_п - база_п) < ДОПУСК,
        "прошлый %s…%s (%s сут.), сумма страницы %s, база %.10f"
        % (а.get("prev-from"), а.get("prev-to"), а.get("prev-days"), стр_п, база_п),
        собрано=строк_п)
    # ИЗВЕСТНАЯ ДЕЛЬТА НА ВЫДУМАННЫХ ДАННЫХ
    ср = _выдуманные(прил.main)
    ждём = (("сумма", 50.0), ("средняя", -25.0), ("доля_кэша", 25.0))
    замер["выдуманные"] = {к: ср[к]["знач"] for к, _ in ждём}
    шаг("сравнение/выдуманные", ср["дней"] == 7 and all(
        ср[к]["знач"] is not None and abs(ср[к]["знач"] - ж) < 1e-6 for к, ж in ждём),
        "длина прошлого %d; расход %s %%, операция %s %%, кэш %s п.п. (ждём +50 / −25 / +25)"
        % (ср["дней"], ср["сумма"]["знач"], ср["средняя"]["знач"], ср["доля_кэша"]["знач"]))

    # СТРЕЛКИ НЕ УВОДЯТ В БУДУЩЕЕ: у отрезка по сегодня «вперёд» выключена,
    # «назад» — ровно та же длина; у отрезка в прошлом «вперёд» прижата
    # к сегодня; конец из будущего сервер прижимает к сегодня.
    html = прил.страница("?p=30")
    назад, вперёд = _ссылка(html, "usage-prev"), _ссылка(html, "usage-next")
    ок_30 = (вперёд is None and назад == ((сегодня - timedelta(days=59)).isoformat(),
                                          (сегодня - timedelta(days=30)).isoformat()))
    html = прил.страница("?from=%s&to=%s" % (сегодня - timedelta(days=9), сегодня - timedelta(days=3)))
    вперёд_прошл = _ссылка(html, "usage-next")
    ок_прижат = вперёд_прошл == ((сегодня - timedelta(days=6)).isoformat(), сегодня.isoformat())
    html = прил.страница("?from=%s&to=%s" % (сегодня - timedelta(days=5), сегодня + timedelta(days=10)))
    конец = _атрибуты(html, "usage-range").get("to")
    шаг("стрелки/не-в-будущее", ок_30 and ок_прижат and конец == сегодня.isoformat(),
        "30 дней: вперёд %s, назад %s; отрезок в прошлом: вперёд %s; конец из будущего → %s"
        % (вперёд, назад, вперёд_прошл, конец))
    html = прил.страница("?p=30&tool=hh")
    база_сумма, строк, _ = _sql(прил.база, 30, "hh-")
    стр = _страничная_сумма(html)
    шаг("отбор/hh", стр is not None and abs(стр - база_сумма) < ДОПУСК,
        "страница %s, база %.10f" % (стр, база_сумма), собрано=строк)
    html = прил.страница("?p=30")
    _, строк, людей = _sql(прил.база, 30)
    м = re.search(r'id="usage-active">(\d+)<', html)
    шаг("люди/активных", bool(м) and int(м.group(1)) == людей,
        "страница %s, база %d" % (м.group(1) if м else None, людей), собрано=строк)

    # ── БЛОК 2 («Расход-2»): токены, доля кэша, таблицы по инструментам ──
    # Токены — сумма столбиков карточки «Токены» против прямого запроса:
    # промпт плюс ответ удачных вызовов периода (из кэша — часть промпта)
    for код, дней in (("7", 7), ("30", 30)):
        html = прил.страница("?p=" + код)
        стр_ток = sum(int(x) for x in re.findall(r'data-tok="(\d+)"', html))
        база_ток = _sql_токены(прил.база, дней)
        замер["токены/" + код] = (стр_ток, база_ток)
        шаг("токены/" + код, стр_ток == база_ток,
            "столбики %d, база %d" % (стр_ток, база_ток), собрано=_sql(прил.база, дней)[1])
    html = прил.страница("?p=30")
    доля_плитки = _атрибуты(html, "usage-cache-share").get("share")
    доля_токенов = _атрибуты(html, "usage-tok-cache").get("share")
    шаг("токены/доля-кэша", доля_плитки is not None and доля_плитки == доля_токенов,
        "плитка %s, подпись карточки токенов %s" % (доля_плитки, доля_токенов),
        собрано=1 if доля_плитки else 0)
    # Строки инструментов в сумме — сумма периода; операции внутри — сумма
    # своего инструмента; при загрузке операции свёрнуты
    г = _группы(html)
    стр = _страничная_сумма(html)
    сумма_групп = sum(сум for сум, _, _, _ in г.values())
    внутри = all(abs(сум - sum(о)) < ДОПУСК for сум, о, _, _ in г.values())
    свёрнуто = all(скрыто == всего for _, _, скрыто, всего in г.values())
    замер["группы"] = г
    шаг("таблицы/группы", стр is not None and abs(сумма_групп - стр) < ДОПУСК and внутри and свёрнуто,
        "инструментов %d, их сумма %.10f против %s; операции = инструменту %s; свёрнуты %s"
        % (len(г), сумма_групп, стр, внутри, свёрнуто), собрано=len(г))
    # Мин и макс одной операции и одной модели — против MIN/MAX прямым запросом
    плохие, всего_строк = [], 0
    for атр, колонка in (("tool", "tool"), ("model", "model")):
        for имя, мин, макс in _мин_макс_строк(html, атр):
            всего_строк += 1
            б_мин, б_макс = _sql_мин_макс(прил.база, колонка, имя, 30)
            if not ((мин is None and б_мин is None) or (мин is not None and б_мин is not None
                                                        and abs(мин - б_мин) < ДОПУСК)) \
                    or not ((макс is None and б_макс is None) or (макс is not None and б_макс is not None
                                                                  and abs(макс - б_макс) < ДОПУСК)):
                плохие.append("%s: %s/%s против %s/%s" % (имя, мин, макс, б_мин, б_макс))
    шаг("таблицы/мин-макс", not плохие,
        "строк %d, расхождений %d%s" % (всего_строк, len(плохие),
                                       (": " + "; ".join(плохие[:2])) if плохие else ""),
        собрано=всего_строк)
    # Отрезок целиком до начала учёта — пусто и без засечки (не «ноль потратили»)
    html = прил.страница("?p=90")
    до_учёта = re.findall(r'<button type="button" class="usage-bar([^"]*)"[^>]*data-total="([^"]+)"', html)
    до = [(к, v) for к, v in до_учёта if "is-before" in к]
    шаг("график/до-учёта", all(float(v) == 0 and "is-zero" not in к for к, v in до),
        "отрезков до начала учёта %d, из них с засечкой %d"
        % (len(до), sum(1 for к, _ in до if "is-zero" in к)), собрано=len(до))

    # История остатка: сутки очищаются, затем два запуска подряд
    сегодня = datetime.now(МСК).date().isoformat()
    c = sqlite3.connect(прил.база)
    c.execute("DELETE FROM balance_history WHERE day = ?", (сегодня,))
    c.commit()
    c.close()
    было = _история(прил.база)
    прил.суточный_запуск()
    после1 = _история(прил.база)
    прил.суточный_запуск()
    после2 = _история(прил.база)
    м = re.search(r'id="usage-history" data-days="(\d+)"', прил.страница())
    на_странице = int(м.group(1)) if м else None
    замер["история"] = (было, после1, после2, на_странице)
    шаг("история/пополняется", после1 == было + 1 and на_странице == после1,
        "строк %d → %d, на странице %s" % (было, после1, на_странице))
    шаг("история/без-дубля", после2 == после1,
        "повтор в те же сутки: %d → %d" % (после1, после2))
    return замер


# ── ЧАСТЬ Б: ЖИВАЯ СТРАНИЦА В ВИДИМОМ БРАУЗЕРЕ ───────────────────────

ЗАМЕР = r"""() => {
  const W = innerWidth;
  const легально = e => {
    for (let a = e.parentElement; a && a !== document.body; a = a.parentElement) {
      const ox = getComputedStyle(a).overflowX;
      if (ox === 'auto' || ox === 'scroll') return true;
    }
    return false;
  };
  const видно = e => e.checkVisibility({checkOpacity: true, checkVisibilityCSS: true});
  const шире = [];
  let всего = 0;
  for (const e of document.body.querySelectorAll('*')) {
    if (!видно(e)) continue;
    const r = e.getBoundingClientRect();
    if (!r.width || !r.height) continue;
    всего++;
    if ((r.right > W + 1 || r.left < -1) && !легально(e))
      шире.push((e.id ? '#' + e.id : e.tagName.toLowerCase() + '.' +
                 String(e.className).trim().split(/\s+/).slice(0, 2).join('.'))
                + ' ' + Math.round(r.left) + '..' + Math.round(r.right));
  }
  const стр = document.getElementById('usage');
  const моно = [];
  for (const e of стр.querySelectorAll('*')) {
    if (!видно(e)) continue;
    const свой = [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
    if (!свой) continue;
    const ф = getComputedStyle(e).fontFamily.split(',')[0].replace(/["']/g, '').trim();
    if (/mono|courier|consolas/i.test(ф)) моно.push(e.tagName.toLowerCase() + ' ' + ф);
  }
  const строки = [...document.querySelectorAll('.usage-table tbody tr')].filter(видно);
  const шапки = [...document.querySelectorAll('.usage-table thead')];
  const таблицы = [...document.querySelectorAll('.usage-table')].filter(видно);
  return {
    W, всего, шире, моно,
    вбок: document.documentElement.scrollWidth - W,
    строк: строки.length,
    строк_блоком: строки.filter(tr => getComputedStyle(tr).display === 'block').length,
    шапок_видно: шапки.filter(t => t.getBoundingClientRect().height > 1).length,
    таблица_правее: таблицы.length ? Math.round(Math.max(...таблицы.map(t => t.getBoundingClientRect().right))) : null,
  };
}"""

ПОДСКАЗКА = r"""([ид, атр, i]) => {
  // Графиков два («Расход-2», 2.2) — у каждого своя подсказка
  const поле = document.getElementById(ид);
  const ст = поле.querySelectorAll('.usage-bar')[i];
  const tip = поле.querySelector('.usage-tip');
  const п = поле.getBoundingClientRect();
  const т = tip.getBoundingClientRect();
  // Точные значения строк (`data-v`), а не округлённый текст: сверка
  // «сумма строк равна столбику» с допуском на округление не отличила бы
  // потерянную долю в полцента от округления
  const числа = [...tip.querySelectorAll('.usage-tip-row')]
    .map(e => parseFloat(e.dataset.v));
  const шапка = tip.querySelector('.usage-tip-head');
  return {видна: !tip.hidden && т.width > 0, всего: parseFloat(ст.dataset[атр]),
          строк: числа.length, сумма: числа.reduce((a, b) => a + b, 0),
          шапка: шапка ? шапка.textContent : '',
          левее: п.left - т.left, правее: т.right - п.right};
}"""

# ГРАФИКИ ПО МАКЕТУ («Расход-2», 2.1–2.2): у каждого графика — подписи
# под каждым столбиком (видно, по центру, без наложений), ширина столбика,
# промежуток между частями, засечка у дней без расхода, сетка оси.
ГРАФИК = r"""() => {
  const видно = e => e.checkVisibility({checkOpacity: true, checkVisibilityCSS: true});
  const итог = [];
  for (const поле of document.querySelectorAll('.usage-plot[data-src]')) {
    const бары = [...поле.querySelectorAll('.usage-bar')];
    const метки = [...поле.querySelectorAll('.usage-xl')];
    const видимые = метки.filter(м => видно(м) && м.getBoundingClientRect().width > 0);
    let не_по_центру = 0, наложений = 0;
    метки.forEach((м, i) => {
      const б = бары[i];
      if (!б) { не_по_центру++; return; }
      const r = м.getBoundingClientRect(), rb = б.getBoundingClientRect();
      if (Math.abs((r.left + r.right) / 2 - (rb.left + rb.right) / 2) > 1) не_по_центру++;
    });
    const прям = видимые.map(м => м.getBoundingClientRect());
    for (let i = 0; i < прям.length; i++)
      for (let j = i + 1; j < прям.length; j++) {
        const a = прям[i], b = прям[j];
        if (a.left < b.right - 0.5 && b.left < a.right - 0.5
            && a.top < b.bottom - 0.5 && b.top < a.bottom - 0.5) наложений++;
      }
    let макс_ш = 0, нулей = 0, засечек = 0;
    const промежутки = [];
    for (const б of бары) {
      const ст = б.querySelector('.usage-stack');
      const rs = ст.getBoundingClientRect();
      const всего = parseFloat(б.dataset.total !== undefined ? б.dataset.total : б.dataset.tok);
      if (всего > 0) макс_ш = Math.max(макс_ш, rs.width);
      const части = [...ст.querySelectorAll('.usage-seg')]
        .map(s => s.getBoundingClientRect()).filter(r => r.height > 0.5);
      for (let k = 0; k + 1 < части.length; k++) промежутки.push(части[k].top - части[k + 1].bottom);
      // День без расхода ВНУТРИ учёта обязан нести засечку; отрезок до начала
      // учёта (`is-before`) — нет: трат тогда не считали
      if (всего === 0 && !б.classList.contains('is-before')) {
        нулей++;
        const цвет = getComputedStyle(ст).backgroundColor;
        const м = цвет.match(/rgba?\(([^)]+)\)/);
        const альфа = м ? (м[1].split(',')[3] !== undefined ? parseFloat(м[1].split(',')[3]) : 1) : 0;
        if (rs.height >= 1 && rs.width >= 1 && альфа > 0 && видно(ст)) засечек++;
      }
    }
    const линии = [...поле.querySelectorAll('.usage-gline')].map(e => e.getBoundingClientRect().top);
    const деления = [...поле.querySelectorAll('.usage-ytick')];
    let не_на_линии = 0, правее = -1e9;
    деления.forEach((д, i) => {
      const r = д.getBoundingClientRect();
      if (линии[i] === undefined || Math.abs(r.top - линии[i]) > 1) не_на_линии++;
      const rr = document.createRange();
      rr.selectNodeContents(д);
      правее = Math.max(правее, rr.getBoundingClientRect().right);
    });
    const область = поле.querySelector('.usage-bars').getBoundingClientRect();
    итог.push({ид: поле.id, столбиков: бары.length, подписей: метки.length,
               видно: видимые.length, рядов: +поле.dataset.rows || 0,
               не_по_центру, наложений, макс_ш, промежутки, нулей, засечек,
               линий: линии.length, делений: деления.length, не_на_линии,
               ось_левее: правее <= область.left + 0.5});
  }
  return итог;
}"""

# №3: правило «строка таблицы — карточка» снято — таблица на 390 снова
# таблица из пяти-шести колонок в одну строку
ПОДЛОГ_3 = """@media (max-width: 640px) {
  .usage-table { display: table !important; width: auto !important; }
  .usage-table thead { display: table-header-group !important; position: static !important;
    width: auto !important; height: auto !important; clip-path: none !important; }
  .usage-table tbody { display: table-row-group !important; width: auto !important; }
  .usage-table tr { display: table-row !important; width: auto !important; }
  .usage-table td, .usage-table th { display: table-cell !important; width: auto !important;
    white-space: nowrap !important; }
  .usage-table td::before { content: none !important; }
}"""


def _стенд_б(база):
    """Свой стенд на копии и своя заглушка остатка — как у проверки 46."""
    import check_usage_balance as ч46
    сервер = http.server.ThreadingHTTPServer(("127.0.0.1", 0), ч46._Остаток)
    threading.Thread(target=сервер.serve_forever, daemon=True).start()
    ч46._режим["значение"] = "ok"
    адрес = "http://127.0.0.1:%d/api/v1/credits" % сервер.server_address[1]
    п, база_адрес = ч46._стенд(база, адрес, True)
    return п, база_адрес, сервер


def часть_б(база, ширины=ШИРИНЫ, подлог_css="", подсказка=True):
    from auth import create_token
    from playwright.sync_api import sync_playwright
    print("ЧАСТЬ Б: живая страница, ширины %s" % ", ".join(map(str, ширины)))
    c = sqlite3.connect(база)
    uid = c.execute("SELECT id FROM users WHERE email = ?", (ПОЧТА,)).fetchone()[0]
    c.close()
    п, адрес, сервер = _стенд_б(база)
    замеры = {}
    try:
        with sync_playwright() as pw:
            бр = pw.chromium.launch(headless=False)
            for ш in ширины:
                к = бр.new_context(viewport={"width": ш, "height": 900}, has_touch=ш < 600)
                к.add_cookies([{"name": "access_token", "value": create_token(uid),
                                "url": адрес}])
                с = к.new_page()
                с.goto(адрес + "/admin/usage?p=30", wait_until="load", timeout=45000)
                if подлог_css:
                    с.add_style_tag(content=подлог_css)
                с.wait_for_timeout(150)
                з = с.evaluate(ЗАМЕР)
                замеры[ш] = з
                шаг("ширина/%d" % ш, not з["шире"] and з["вбок"] <= 0,
                    "шире окна %d из %d%s, прокрутка вбок %d px"
                    % (len(з["шире"]), з["всего"],
                       (": " + "; ".join(з["шире"][:3])) if з["шире"] else "", з["вбок"]),
                    собрано=з["всего"])
                шаг("моно/%d" % ш, not з["моно"],
                    "моноширинных %d%s" % (len(з["моно"]),
                                           (": " + "; ".join(з["моно"][:3])) if з["моно"] else ""),
                    собрано=з["всего"])
                if ш < 600:
                    шаг("карточки/%d" % ш,
                        з["строк_блоком"] == з["строк"] and з["шапок_видно"] == 0,
                        "строк карточкой %d из %d, шапок таблиц видно %d"
                        % (з["строк_блоком"], з["строк"], з["шапок_видно"]),
                        собрано=з["строк"])
                з["графики"] = _графики(с, ш)
                if подсказка and ш == 1920:
                    _подсказка(с, "usage-plot", "total")
                    _подсказка(с, "usage-plot-tok", "tok")
                    _пустой_день(с)
                    _раскрытие(с)
                if подсказка and ш in (390, 1920):
                    _календарь(с, ш)
                к.close()
            бр.close()
    finally:
        п.terminate()
        try:
            п.wait(15)
        except Exception:
            п.kill()
        сервер.shutdown()
    return замеры


def _календарь(с, ш):
    """СВОЙ ПЕРИОД — путь человека («Расход-2», 1.1): «Свой период» открывает
    календарь, первое касание — начало, второе — конец, «Показать» ведёт
    на отрезок. Дни позже сегодня и раньше выбранного начала выключены.
    На 390 — тот же замер ширины при ОТКРЫТОМ календаре."""
    сегодня = datetime.now(МСК).date()
    нач, кон = сегодня - timedelta(days=9), сегодня - timedelta(days=3)
    с.locator("#usage-custom").click()
    с.wait_for_timeout(120)

    def день(iso):
        for _ in range(3):
            б = с.locator('#usage-cal-grid [data-day="%s"]' % iso)
            if б.count():
                return б
            с.locator("#usage-cal-prev").click()
        return б

    открыт = с.evaluate("() => !document.getElementById('usage-cal').hidden")
    будущих = с.evaluate("(t) => [...document.querySelectorAll('#usage-cal-grid [data-day]')]"
                         ".filter(b => b.dataset.day > t && !b.disabled).length", сегодня.isoformat())
    if ш < 600:
        з = с.evaluate(ЗАМЕР)
        шаг("ширина/%d/календарь" % ш, открыт and not з["шире"] and з["вбок"] <= 0,
            "календарь открыт %s, шире окна %d из %d%s, прокрутка вбок %d px"
            % (открыт, len(з["шире"]), з["всего"],
               (": " + "; ".join(з["шире"][:3])) if з["шире"] else "", з["вбок"]),
            собрано=з["всего"])
        с.keyboard.press("Escape")
        return
    день(нач.isoformat()).click()
    раньше = с.evaluate("(t) => { const b = document.querySelector('#usage-cal-grid [data-day=\"' + t + '\"]');"
                        " return b ? b.disabled : null; }", (нач - timedelta(days=1)).isoformat())
    день(кон.isoformat()).click()
    можно = с.evaluate("() => !document.getElementById('usage-cal-show').disabled")
    с.locator("#usage-cal-show").click()
    с.wait_for_load_state("load")
    отрезок = с.evaluate("() => { const r = document.getElementById('usage-range');"
                         " return r ? [r.dataset.from, r.dataset.to] : null; }")
    шаг("календарь/путь", открыт and будущих == 0 and раньше is True and можно
        and отрезок == [нач.isoformat(), кон.isoformat()],
        "открыт %s, будущих дней доступно %d, день до начала выключен %s, «Показать» %s, "
        "показан отрезок %s" % (открыт, будущих, раньше, "доступна" if можно else "выключена", отрезок))


def _графики(с, ш):
    """Оба графика по макету («Расход-2», 2.1–2.2) на ширине `ш`."""
    итог = с.evaluate(ГРАФИК)
    for г in итог:
        имя = "деньги" if г["ид"] == "usage-plot" else "токены"
        шаг("подписи/%s/%d" % (имя, ш),
            г["видно"] == г["столбиков"] and г["не_по_центру"] == 0 and г["наложений"] == 0,
            "подписей видно %d при %d столбиках (в дереве %d), рядов %d, не по центру %d, наложений %d"
            % (г["видно"], г["столбиков"], г["подписей"], г["рядов"], г["не_по_центру"], г["наложений"]),
            собрано=г["столбиков"])
        шаг("столбик/%s/%d" % (имя, ш), г["макс_ш"] <= 40.5,
            "самый широкий столбик %.1f px (предел 40)" % г["макс_ш"], собрано=г["столбиков"])
        п = г["промежутки"]
        шаг("промежуток/%s/%d" % (имя, ш), bool(п) and all(1.5 <= x <= 2.5 for x in п),
            "промежутков между частями %d, от %s до %s px"
            % (len(п), ("%.2f" % min(п)) if п else "—", ("%.2f" % max(п)) if п else "—"),
            собрано=len(п))
        шаг("засечка/%s/%d" % (имя, ш), г["засечек"] == г["нулей"],
            "дней без расхода %d, с засечкой у нуля %d" % (г["нулей"], г["засечек"]),
            собрано=г["нулей"])
        шаг("сетка/%s/%d" % (имя, ш),
            г["линий"] in (5, 6) and г["делений"] == г["линий"] and г["не_на_линии"] == 0
            and г["ось_левее"],
            "линий %d (делений %d), подписей не на своей линии %d, ось левее столбиков %s"
            % (г["линий"], г["делений"], г["не_на_линии"], г["ось_левее"]),
            собрано=г["столбиков"])
    if not итог:
        шаг("графики/%d" % ш, False, "графиков на странице нет", собрано=0)
    return итог


def _подсказка(с, ид, атр):
    """Наведение НАСТОЯЩЕЙ мышью на первый и последний непустой столбик
    графика `ид`; `атр` — атрибут итога столбика (`total` либо `tok`)."""
    имя = "деньги" if ид == "usage-plot" else "токены"
    итоги = с.evaluate("([ид, атр]) => [...document.querySelectorAll('#' + ид + ' .usage-bar')]"
                       ".map((b, i) => [i, parseFloat(b.dataset[атр])]).filter(x => x[1] > 0)"
                       ".map(x => x[0])", [ид, атр])
    for i in ([итоги[0], итоги[-1]] if итоги else []):
        бар = с.locator("#%s .usage-bar" % ид).nth(i)
        бар.scroll_into_view_if_needed()
        р = бар.bounding_box()
        с.mouse.move(р["x"] + р["width"] / 2, р["y"] + р["height"] - 2)
        с.wait_for_timeout(120)
        п = с.evaluate(ПОДСКАЗКА, [ид, атр, i])
        допуск = 1e-9 if атр == "total" else 0
        шаг("подсказка/%s/столбик-%d" % (имя, i),
            п["видна"] and abs(п["сумма"] - п["всего"]) <= допуск
            and п["левее"] <= 0.5 and п["правее"] <= 0.5,
            "видна %s, строк %d, сумма строк %s против %s, за край %.1f/%.1f px"
            % (п["видна"], п["строк"], п["сумма"], п["всего"], п["левее"], п["правее"]),
            собрано=п["строк"])
    if not итоги:
        шаг("подсказка/%s" % имя, False, "непустых столбиков нет", собрано=0)
    с.mouse.move(2, 2)


def _пустой_день(с):
    """Подсказка дня БЕЗ ЗАПИСЕЙ (2.1) — «записей нет», строк частей нет.
    День заведён на копии (`_день_без_записей`), поэтому он есть всегда."""
    i = с.evaluate("() => [...document.querySelectorAll('#usage-plot .usage-bar')]"
                   ".findIndex(b => parseFloat(b.dataset.total) === 0 && !b.classList.contains('is-before'))")
    if i is None or i < 0:
        шаг("подсказка/пустой-день", False, "дня без расхода на графике нет", собрано=0)
        return
    бар = с.locator("#usage-plot .usage-bar").nth(i)
    бар.scroll_into_view_if_needed()
    р = бар.bounding_box()
    с.mouse.move(р["x"] + р["width"] / 2, р["y"] + р["height"] - 2)
    с.wait_for_timeout(120)
    п = с.evaluate(ПОДСКАЗКА, ["usage-plot", "total", i])
    шаг("подсказка/пустой-день", п["видна"] and "записей нет" in п["шапка"] and п["строк"] == 0,
        "видна %s, шапка «%s», строк частей %d" % (п["видна"], п["шапка"], п["строк"]))
    с.mouse.move(2, 2)


def _раскрытие(с):
    """«По операциям» свёрнуты по инструменту (2.4): при загрузке операций
    не видно, нажатие на строку инструмента раскрывает ровно его операции."""
    видно = ("() => [...document.querySelectorAll('#usage-tools .usage-op')]"
             ".filter(e => e.checkVisibility()).length")
    до = с.evaluate(видно)
    своих = с.evaluate("() => { const t = document.querySelector('#usage-tools tbody.usage-tgroup');"
                       " return t ? t.querySelectorAll('.usage-op').length : 0; }")
    кн = с.locator("#usage-tools .usage-tgl").first
    if not своих:
        шаг("таблицы/раскрытие", False, "строк инструментов нет", собрано=0)
        return
    кн.scroll_into_view_if_needed()
    кн.click()
    с.wait_for_timeout(80)
    после = с.evaluate(видно)
    открыто = кн.get_attribute("aria-expanded")
    кн.click()
    с.wait_for_timeout(80)
    снова = с.evaluate(видно)
    шаг("таблицы/раскрытие", до == 0 and после == своих and открыто == "true" and снова == 0,
        "видно операций до %d, после нажатия %d из %d своих (aria-expanded %s), после второго %d"
        % (до, после, своих, открыто, снова), собрано=своих)


# ── ПОДЛОГИ ──────────────────────────────────────────────────────────

ДОКАЗАТЕЛЬСТВА = {
    "№1 цена в памяти": "сумма страницы минус сумма базы — ровно подложенная добавка",
    "№2 история не пишется": "строк в истории до и после суточного запуска — равны",
    "№3 таблица на 390": "правый край таблиц на 390 правее окна",
    "№4 прошлый другой длины": "длина прошлого отрезка на странице 8 при выбранных 7, "
                               "дельта выдуманных данных не +50 %",
    "№5 подписи сняты": "подписей в дереве столько же, сколько столбиков, видно — ноль",
    "№6 засечка снята": "дни без расхода на графике есть, засечки у нуля нет ни у одного",
}

# №5 (письмо «Расход-2», №2): подписи под столбиками сняты
ПОДЛОГ_5 = ".usage-xl { display: none !important; }"
# №6 (письмо «Расход-2», №3): засечка у дней без расхода снята
ПОДЛОГ_6 = ".usage-bar.is-zero .usage-stack { height: 0 !important; background: none !important; }"


def доказать_подлог(имя, замер):
    """Независимо от вердикта: подлог изменил ровно то, что собирался."""
    if имя == "№1":
        стр, база = замер["30"]
        return стр is not None and abs(стр - база - 0.5) < 1e-6
    if имя == "№2":
        было, после1, _, _ = замер["история"]
        return после1 == было
    if имя == "№3":
        з = замер[390]
        return з["таблица_правее"] is not None and з["таблица_правее"] > з["W"]
    if имя == "№4":
        сумма = замер["выдуманные"]["сумма"]
        return замер["прошлый"][0] == 8 and (сумма is None or abs(сумма - 50.0) > 1e-6)
    if имя in ("№5", "№6"):
        г = [x for x in замер[1920]["графики"] if x["ид"] == "usage-plot"]
        if not г:
            return False
        г = г[0]
        if имя == "№5":
            return г["столбиков"] > 0 and г["подписей"] == г["столбиков"] and г["видно"] == 0
        return г["нулей"] > 0 and г["засечек"] == 0
    return False


def _провалено(префикс):
    return any(и.startswith(префикс) and исход == "ПЛОХО" for и, исход, _ in шаги)


def контроль(прил, база):
    import main
    ловит = 0
    # №1 — одна строка периода с подменённой ценой, В ПАМЯТИ страницы
    настоящие = main._расход_строки

    def подложные(db, *арг, **кв):
        # Строка запроса SQLAlchemy `_replace` не умеет — подменяется
        # копией с теми же полями: страница читает их по имени. Аргументы —
        # как у настоящей («Расход-2» добавил границу сверху)
        строки = list(настоящие(db, *арг, **кв))
        for i, с in enumerate(строки):
            if с.ok and not с.cost_missing and с.cost is not None:
                Р = collections.namedtuple("Р", с._fields)
                строки[i] = Р(*с)._replace(cost=с.cost + 0.5)
                break
        return строки

    print("ПОДЛОГ №1: цена одной строки подменена в памяти (+0.5 $)")
    шаги.clear()
    main._расход_строки = подложные
    try:
        замер = часть_а(прил)
    finally:
        main._расход_строки = настоящие
    док = доказать_подлог("№1", замер)
    упал = _провалено("сумма/")
    print("  доказательство: страница − база = +0.5 → %s; шаг сверки упал: %s" % (док, упал))
    ловит += док and упал

    print("ПОДЛОГ №2: история остатка не пишется")
    шаги.clear()
    настоящая = прил.бк.записать_историю
    прил.бк.записать_историю = lambda *a, **k: "added"
    try:
        замер = часть_а(прил)
    finally:
        прил.бк.записать_историю = настоящая
    док = доказать_подлог("№2", замер)
    упал = _провалено("история/пополняется")
    print("  доказательство: строк до и после запуска равны → %s; шаг упал: %s" % (док, упал))
    ловит += док and упал

    print("ПОДЛОГ №3: снято правило «строка таблицы — карточка» на 390")
    шаги.clear()
    замер = часть_б(база, ширины=(390,), подлог_css=ПОДЛОГ_3, подсказка=False)
    док = доказать_подлог("№3", замер)
    упал = _провалено("ширина/390")
    print("  доказательство: правый край таблиц %s при окне %d → %s; шаг упал: %s"
          % (замер[390]["таблица_правее"], замер[390]["W"], док, упал))
    ловит += док and упал

    # №4 — письмо «Расход-2», подлог №1: сравнение с отрезком ДРУГОЙ длины
    print("ПОДЛОГ №4: прошлый отрезок на сутки длиннее выбранного")
    шаги.clear()
    настоящий = main._расход_прошлый
    main._расход_прошлый = lambda с, по: (с - timedelta(days=(по - с).days + 2),
                                          с - timedelta(days=1))
    try:
        замер = часть_а(прил)
    finally:
        main._расход_прошлый = настоящий
    док = доказать_подлог("№4", замер)
    упал = _провалено("сравнение/7") and _провалено("сравнение/выдуманные")
    print("  доказательство: длина прошлого на странице %d, дельта выдуманных %s → %s; "
          "оба шага сравнения упали: %s" % (замер["прошлый"][0], замер["выдуманные"]["сумма"], док, упал))
    ловит += док and упал

    # №5 и №6 — письмо «Расход-2», подлоги №2 и №3: вид графика, в странице
    for имя, css, префикс, текст in (
            ("№5", ПОДЛОГ_5, "подписи/", "подписи под столбиками сняты"),
            ("№6", ПОДЛОГ_6, "засечка/", "засечка у дней без расхода снята")):
        print("ПОДЛОГ %s: %s" % (имя, текст))
        шаги.clear()
        замер = часть_б(база, ширины=(1920,), подлог_css=css, подсказка=False)
        док = доказать_подлог(имя, замер)
        упал = _провалено(префикс)
        г = [x for x in замер[1920]["графики"] if x["ид"] == "usage-plot"]
        г = г[0] if г else {}
        print("  доказательство: столбиков %s, подписей в дереве %s, видно %s; дней без расхода %s, "
              "с засечкой %s → %s; шаг упал: %s" % (г.get("столбиков"), г.get("подписей"), г.get("видно"),
                                                  г.get("нулей"), г.get("засечек"), док, упал))
        ловит += док and упал
    всего = 6
    print("КОНТРОЛЬ: ловит %d из %d" % (ловит, всего))
    return 0 if ловит == всего else 1


def main_():
    база, каталог = _копия()
    _день_без_записей(база)
    прил = _Приложение(база, каталог)
    if "--контроль" in sys.argv:
        return контроль(прил, база)
    часть_а(прил)
    часть_б(база)
    плохо = [ш for ш in шаги if ш[1] == "ПЛОХО"]
    пропуск = [ш for ш in шаги if ш[1] == "ПРОПУСК"]
    print("ИТОГ: шагов %d, плохих %d, пропусков %d" % (len(шаги), len(плохо), len(пропуск)))
    if плохо:
        return 1
    return 2 if пропуск else 0


if __name__ == "__main__":
    sys.exit(main_())
