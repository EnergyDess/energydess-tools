"""Страница расхода на модели `/admin/usage` (BACKLOG №346; №352, «Расход»).

Вопросы, у каждого — подлог рядом:

1. ДОСТУП: гость и обычный пользователь страницы не видят; подлог
   снимает проверку прав — обычный пользователь её видит.
2. СТРОКА БЕЗ ЦЕНЫ в сумму не входит и печатается отдельным счётчиком;
   подлог считает её нулём-ценой внутри суммы — тест это замечает.
3. ПУСТОЙ УЧЁТ — «данных нет», а не «0 $».
4. ПЕРИОДЫ, ОТБОР, ГРАФИК, ЛЮДИ, КЭШ, ПОСТОЯННЫЕ — суммы сверяются
   с прямым счётом по тем же строкам, а не с числами из кода страницы.

База своя, в памяти: общая база тестов накапливает строки расхода
от других модулей, и «пусто» на ней не поставить. Адреса выдуманные.
"""
import os
import re
from datetime import datetime, timedelta, time as _время
from zoneinfo import ZoneInfo

os.environ.setdefault("DB_PATH", "./test_model_usage.db")
os.environ.setdefault("AGENT_WEBHOOK_KEY", "test-key-8f3a91")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import database  # noqa: E402
import main  # noqa: E402
from auth import create_token, hash_password  # noqa: E402

МСК = ZoneInfo("Europe/Moscow")


@pytest.fixture
def стенд(monkeypatch):
    движок = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    database.Base.metadata.create_all(движок)
    Сессия = sessionmaker(bind=движок)
    db = Сессия()
    админ = database.User(email="adm@usage.test", password_hash=hash_password("x-123456"),
                          is_verified=True, is_admin=True)
    простой = database.User(email="usr@usage.test", password_hash=hash_password("x-123456"),
                            is_verified=True, is_admin=False)
    db.add_all([админ, простой])
    db.commit()

    def _db():
        с = Сессия()
        try:
            yield с
        finally:
            с.close()

    main.app.dependency_overrides[main.get_db] = _db
    # ГЕЙТ ПОДТВЕРЖДЁННОЙ ПОЧТЫ — middleware (§5.3): зависимостей он
    # не видит и берёт пользователя через `SessionLocal` ОБЩЕЙ базы. Без
    # подмены тест зависел от чужого состояния: в CI общая база —
    # засеянный стенд, где пользователь с тем же номером не подтверждён,
    # и гейт отвечал 428 (прогон 36302498005); локально таких номеров
    # в общей базе не было, и тест проходил.
    monkeypatch.setattr(main, "SessionLocal", Сессия)
    # Сети в тестах нет: остаток — заглушкой, а не запросом
    monkeypatch.setattr(main, "_расход_остаток_спросить",
                        lambda: {"остаток": 12.5, "причина": None, "при": datetime.utcnow()})
    клиенты = {}
    for имя, u in (("админ", админ), ("простой", простой)):
        к = TestClient(main.app)
        к.cookies.set("access_token", create_token(u.id))
        клиенты[имя] = к
    клиенты["гость"] = TestClient(main.app)
    клиенты["ид"] = {"админ": админ.id, "простой": простой.id}
    yield db, клиенты
    main.app.dependency_overrides.pop(main.get_db, None)
    db.close()


def _мск(дней_назад, час=12):
    """Полдень московских суток `сегодня − дней_назад` → наивное UTC."""
    день = datetime.now(МСК).date() - timedelta(days=дней_назад)
    return (datetime.combine(день, _время(час), МСК).astimezone(ZoneInfo("UTC"))
            .replace(tzinfo=None))


def _строка(db, **kw):
    поля = dict(created_at=min(_мск(0, 0) + timedelta(minutes=5), datetime.utcnow()),
                tool="hh-letter", model="anthropic/claude-opus-4-8", prompt_tokens=1000,
                completion_tokens=500, cost=0.1, cost_missing=False, ok=True)
    поля.update(kw)
    db.add(database.ModelUsage(**поля))
    db.commit()


def test_гость_и_обычный_пользователь_не_видят(стенд):
    _, к = стенд
    assert к["админ"].get("/admin/usage").status_code == 200
    for кто in ("простой", "гость"):
        r = к[кто].get("/admin/usage", follow_redirects=False)
        assert r.status_code in (302, 401), (кто, r.status_code)
        assert "Остаток OpenRouter" not in r.text


def test_подлог_снятая_проверка_прав_открывает_страницу(стенд, monkeypatch):
    _, к = стенд
    monkeypatch.setattr(main, "_admin_guard", lambda user: bool(user))
    r = к["простой"].get("/admin/usage", follow_redirects=False)
    assert r.status_code == 200, "подлог не состоялся — тест доступа ничего не доказывает"


def test_строка_без_цены_отдельно_и_не_в_сумме(стенд):
    db, к = стенд
    _строка(db, cost=0.25)
    _строка(db, cost=None, cost_missing=True)
    с = main.расход_сводка(db)
    assert с["вызовов"] == 2
    assert с["сумма"] == pytest.approx(0.25)
    assert с["без_цены"] == 1
    html = к["админ"].get("/admin/usage").text
    assert "без цены 1" in html
    assert 'data-missing="7"' in html
    assert 'data-sum="0.25"' in html


def test_подлог_цена_нулём_в_сумме_замечен(стенд, monkeypatch):
    """Подлог: сводка считает строку без цены нулевой и не ведёт счётчик.
    Проверка обязана это заметить — счётчик 0 при одной такой строке."""
    db = стенд[0]
    _строка(db, cost=None, cost_missing=True)
    настоящая = main.расход_сводка

    def подлог(db, *арг, **кв):
        # подпись та же, что у настоящей: страница зовёт её с отрезком
        # и группировкой («Расход-2»), и подлог обязан их пропустить
        с = настоящая(db, *арг, **кв)
        с["без_цены"] = 0
        # «Расход-2», 2.4: операции свёрнуты по инструменту, и у строки
        # инструмента свой счётчик — подлог обязан обнулить и его
        for г in с["по_инструментам"] + с["по_моделям"] + с["по_группам"]:
            г["без_цены"] = 0
        return с

    monkeypatch.setattr(main, "расход_сводка", подлог)
    html = стенд[1]["админ"].get("/admin/usage").text
    # Проверка из теста выше («без цены 1» в разметке) на подлоге падает
    assert "без цены 1" not in html
    assert 'data-missing="7"' not in html


def test_пустой_учёт_пишет_данных_нет_а_не_ноль(стенд):
    _, к = стенд
    html = к["админ"].get("/admin/usage").text
    assert "данных нет" in html.lower()
    assert "0.0000&nbsp;$" not in html and ">0.00&nbsp;$" not in html


def test_неудачи_по_кодам_за_неделю(стенд):
    db, _ = стенд
    _строка(db, ok=False, cost=None, error_code="http_429")
    _строка(db, ok=False, cost=None, error_code="http_429")
    _строка(db, ok=False, cost=None, error_code="http_429", created_at=_мск(9))
    с = main.расход_сводка(db)
    assert с["неудачи"][0]["код"] == "http_429"
    assert с["неудачи"][0]["n"] == 2


def test_время_по_москве():
    assert main._расход_момент(datetime(2026, 9, 18, 21, 30)) == "19.09.2026 00:30"


# ── ПЕРИОДЫ, ОТБОР, ГРАФИК (письмо «Расход», 2.1–2.3, 2.10) ────────────────

def _засеять_периоды(db):
    """Строки на 0, 3, 10, 40 суток назад — по одной границе на период."""
    for назад, цена, инструмент in ((0, 0.10, "hh-letter"), (3, 0.20, "medkit-assist"),
                                    (10, 0.40, "hh-analyze"), (40, 0.80, "nut-chat")):
        _строка(db, created_at=_мск(назад), cost=цена, tool=инструмент)


@pytest.mark.parametrize("период,ждём", [("7", 0.30), ("30", 0.70), ("all", 1.50)])
def test_сумма_периода_и_график(стенд, период, ждём):
    """Сумма периода равна прямому счёту; сумма столбиков графика — сумме
    периода (подпись «макс» считается от тех же столбиков)."""
    db, к = стенд
    _засеять_периоды(db)
    с = main.расход_сводка(db, период)
    assert с["сумма"] == pytest.approx(ждём)
    assert sum(д["всего"] for д in с["столбики"]) == pytest.approx(ждём)
    html = к["админ"].get("/admin/usage?p=%s" % период).text
    assert 'data-sum="%s"' % с["сумма"] in html


def test_отбор_по_инструменту(стенд):
    db, к = стенд
    _засеять_периоды(db)
    с = main.расход_сводка(db, "all", "hh")
    assert с["сумма"] == pytest.approx(0.50)
    assert {г["имя"] for г in с["по_инструментам"]} == {"hh-letter", "hh-analyze"}
    html = к["админ"].get("/admin/usage?p=all&tool=hh").text
    assert '<option value="hh" selected' in html


def test_незнакомый_период_и_инструмент_не_роняют(стенд):
    _, к = стенд
    r = к["админ"].get("/admin/usage?p=999&tool=<script>")
    assert r.status_code == 200 and "&lt;script&gt;" not in r.text


def test_пустой_день_остаётся_столбиком(стенд):
    db, _ = стенд
    _строка(db, created_at=_мск(0), cost=0.1)
    _строка(db, created_at=_мск(2), cost=0.2)
    с = main.расход_сводка(db, "7")
    assert len(с["столбики"]) == 7
    assert [д["всего"] for д in с["столбики"]].count(0.0) == 5


# ── ЛЮДИ (1.3, 2.5) ───────────────────────────────────────────────────────

def test_люди_медиана_процентиль_и_строка_без_аккаунта(стенд):
    db, к = стенд
    ид = к["ид"]
    третий = database.User(email="u3@usage.test", password_hash="x", is_verified=True)
    db.add(третий)
    db.commit()
    for кто, суммы in ((ид["админ"], (0.1, 0.1)), (ид["простой"], (0.5,)), (третий.id, (0.9, 0.1))):
        for ц in суммы:
            _строка(db, cost=ц, user_id=кто)
    _строка(db, cost=5.0, user_id=None)
    л = main.расход_сводка(db, "7")["пользователи"]
    assert л["активных"] == 3
    # ближайший ранг по [0.2, 0.5, 1.0]: медиана 0.5, 90-й — 1.0
    assert л["медиана"] == pytest.approx(0.5) and л["п90"] == pytest.approx(1.0)
    assert л["максимум"] == pytest.approx(1.0)
    без = [с for с in л["строки"] if с["id"] is None]
    assert без and без[0]["подпись"] == "без аккаунта (удалён)"
    html = к["админ"].get("/admin/usage").text
    assert "u3@usage.test" in html and 'id="usage-active">3<' in html


# ── ЭКОНОМИЯ НА КЭШЕ (1.5) ────────────────────────────────────────────────

def test_экономия_кэша_по_правилам_цены(стенд):
    """Opus, вход 5 $/М: prompt 10000, из кэша 8000, выход 500.
    Цена строки 5e-6 · (10000 − 7200 + 2500) = 0.0265; экономия
    5e-6 · 0.9 · 8000 = 0.036; без кэша было бы 0.0625."""
    db, _ = стенд
    _строка(db, prompt_tokens=10000, cached_tokens=8000, completion_tokens=500,
            cost=0.0265)
    # модель не Claude с кэшем — не посчитана, но в сумму «без кэша» входит
    _строка(db, model="openai/whisper-large-v3-turbo", tool="voice",
            cache_write_tokens=300, cost=0.0004)
    к = main.расход_сводка(db)["кэш"]
    assert к["сэкономлено"] == pytest.approx(0.036)
    assert к["без_кэша"] == pytest.approx(0.0625 + 0.0004)
    assert к["строк"] == 2 and к["не_посчитано"] == 1


# ── ПОСТОЯННЫЕ И СЕБЕСТОИМОСТЬ (1.4, 2.6) ─────────────────────────────────

def test_постоянные_правит_только_админ(стенд):
    db, к = стенд
    r = к["простой"].post("/admin/api/usage/fixed", json={"server": "5"})
    assert r.status_code == 403
    r = к["админ"].post("/admin/api/usage/fixed",
                        json={"server": "5,5", "domain": "", "other": "0"})
    assert r.status_code == 200, r.text
    assert main.расход_постоянные(db) == {"server": 5.5, "other": 0.0}
    for плохо in ({"server": "пять"}, {"server": "-1"}, {"server": "1e9"}, [1, 2]):
        assert к["админ"].post("/admin/api/usage/fixed", json=плохо).status_code == 400
    assert main.расход_постоянные(db) == {"server": 5.5, "other": 0.0}


def test_себестоимость_приводит_к_месяцу(стенд):
    """Учёт 10 суток: сумма моделей ×3 до месяца, постоянные прибавлены."""
    db, к = стенд
    _строка(db, created_at=_мск(9), cost=0.3, user_id=к["ид"]["админ"])
    _строка(db, created_at=_мск(0), cost=0.1, user_id=к["ид"]["админ"],
            tool="hh-letter")
    db.add(database.FixedCost(key="server", usd_month=6.0))
    db.commit()
    э = main.расход_экономика(db)
    assert э["окно"] == 10 and э["приведено"] is True
    assert э["модели"] == pytest.approx(1.2)
    assert э["всего"] == pytest.approx(7.2)
    assert э["на_пользователя"] == pytest.approx(7.2)
    assert э["доля_постоянных"] == pytest.approx(6.0)
    html = к["админ"].get("/admin/usage").text
    assert 'id="usage-cost-total">7.20&nbsp;$' in html


# ── ИСТОРИЯ ОСТАТКА И ВНИМАНИЕ (1.1–1.2, 2.2, 2.8) ────────────────────────

def test_история_остатка_на_плитке(стенд):
    db, к = стенд
    html = к["админ"].get("/admin/usage").text
    assert 'data-days="0"' in html and "пишется с первого суточного запуска" in html
    for назад, сумма in ((1, 9.5), (0, 9.1)):
        день = (datetime.now(МСК).date() - timedelta(days=назад)).isoformat()
        db.add(database.BalanceHistory(day=день, created_at=datetime.utcnow(), remaining=сумма))
    db.commit()
    html = к["админ"].get("/admin/usage").text
    assert 'data-days="2"' in html and "История остатка: 2 сут." in html


def test_всплеск_на_странице_тем_же_решением(стенд):
    db, к = стенд
    for назад in range(2, 16):
        _строка(db, created_at=_мск(назад), cost=0.5)
    _строка(db, created_at=_мск(1), cost=2.5)
    html = к["админ"].get("/admin/usage").text
    assert "больше 3 медиан" in html


# ── СБОЙ ЗАПРОСА ОСТАТКА (№346, заход 7, блок 2) ──────────────────────────
# Три вида сбоя проходят БОЕВОЙ `_расход_остаток_спросить` с подменённым
# запросом: подменяется ровно сеть, разбор причины и текст — боевые.
import httpx  # noqa: E402
import balance_check  # noqa: E402


def _сбой(исключение):
    def _запрос(ключ, адрес=None):
        raise исключение
    return _запрос


_ЗАПРОС = httpx.Request("GET", "https://openrouter.ai/api/v1/credits")
СБОИ = {
    "сеть": (httpx.ConnectError("нет связи", request=_ЗАПРОС), "не ответил (сеть)"),
    "ключ": (httpx.HTTPStatusError("401", request=_ЗАПРОС,
                                   response=httpx.Response(401, request=_ЗАПРОС)),
             "отклонил ключ (HTTP 401)"),
    "разбор": (KeyError("data"), "не разобран"),
}


@pytest.mark.parametrize("вид", sorted(СБОИ))
def test_сбой_остатка_называет_причину_и_последнее(стенд, monkeypatch, вид):
    _, к = стенд
    monkeypatch.undo()
    monkeypatch.setattr(main, "OPENROUTER_API_KEY", "sk-test-not-real")
    monkeypatch.setattr(main, "РАСХОД_ОСТАТОК_КЕШ_SEC", 0)
    monkeypatch.setattr(main, "_расход_остаток", {"при": 0.0, "итог": None, "последний": None})
    monkeypatch.setattr(balance_check, "остаток_openrouter", lambda ключ, адрес=None: 7.65)
    удачно = к["админ"].get("/admin/usage").text
    assert 'id="usage-balance-note"' in удачно and "7.65&nbsp;$" in удачно
    исключение, причина = СБОИ[вид]
    monkeypatch.setattr(balance_check, "остаток_openrouter", _сбой(исключение))
    html = к["админ"].get("/admin/usage").text
    assert причина in html
    assert "Последний: 7.65" in html            # последнее удачное значение названо
    assert 'id="usage-balance-note"' in html    # тот же узел — та же резервная высота


def test_ключа_нет_и_удачных_не_было(стенд, monkeypatch):
    _, к = стенд
    monkeypatch.undo()
    monkeypatch.setattr(main, "OPENROUTER_API_KEY", "")
    monkeypatch.setattr(main, "РАСХОД_ОСТАТОК_КЕШ_SEC", 0)
    monkeypatch.setattr(main, "_расход_остаток", {"при": 0.0, "итог": None, "последний": None})
    html = к["админ"].get("/admin/usage").text
    assert "Ключа OpenRouter нет." in html and "Удачных запросов с запуска не было" in html


# ── «РАСХОД-2», БЛОК 1: ПЕРИОД, СТРЕЛКИ, ГРУППИРОВКА, СРАВНЕНИЕ ───────────

def _день(назад):
    return (datetime.now(МСК).date() - timedelta(days=назад)).isoformat()


def test_пресет_90_и_свой_отрезок_против_прямого_счёта(стенд):
    """Сумма пресета 90 и произвольного отрезка — прямым счётом по тем же
    строкам; строка ПОСЛЕ конца своего отрезка в сумму не входит."""
    db, к = стенд
    for назад, цена in ((0, 0.10), (3, 0.20), (10, 0.40), (40, 0.80), (100, 1.60)):
        _строка(db, created_at=_мск(назад), cost=цена)
    assert main.расход_сводка(db, "90")["сумма"] == pytest.approx(1.50)
    с = main.расход_сводка(db, "", с_стр=_день(12), по_стр=_день(2))
    assert с["код"] == "custom" and с["дней"] == 11
    assert с["сумма"] == pytest.approx(0.60)
    assert sum(д["всего"] for д in с["столбики"]) == pytest.approx(0.60)
    html = к["админ"].get("/admin/usage?from=%s&to=%s" % (_день(12), _день(2))).text
    assert 'name="from" value="%s"' % _день(12) in html
    assert 'data-sum="%s"' % с["сумма"] in html


def test_свой_отрезок_проверяется_сервером(стенд):
    db, _ = стенд
    сегодня = datetime.now(МСК).date()
    # совпал с пресетом — называется пресетом
    assert main.расход_сводка(db, "", с_стр=_день(6), по_стр=_день(0))["код"] == "7"
    # конец позже сегодня — прижат к сегодня
    с = main.расход_сводка(db, "", с_стр=_день(20), по_стр=(сегодня + timedelta(days=9)).isoformat())
    assert с["по_iso"] == сегодня.isoformat() and с["код"] == "custom"
    # конец раньше начала — отказ словами и «7 дней», даты не переставлены
    с = main.расход_сводка(db, "", с_стр=_день(2), по_стр=_день(9))
    assert с["код"] == "7" and "раньше начала" in с["замечание"]
    с = main.расход_сводка(db, "", с_стр="вчера", по_стр=_день(0))
    assert с["код"] == "7" and "не разобран" in с["замечание"]
    # пресет сильнее своего периода: форма везёт обе пары
    assert main.расход_сводка(db, "30", с_стр=_день(12), по_стр=_день(2))["код"] == "30"


def test_стрелки_листают_целиком_и_не_уходят_в_будущее(стенд):
    db, к = стенд
    с = main.расход_сводка(db, "30")
    assert с["вперёд"] == ""                       # отрезок кончается сегодня
    assert "from=%s" % _день(59) in с["назад"] and "to=%s" % _день(30) in с["назад"]
    # отрезок 7 дней, кончающийся 3 дня назад: вперёд — прижат к сегодня
    с = main.расход_сводка(db, "", с_стр=_день(9), по_стр=_день(3))
    assert "from=%s" % _день(6) in с["вперёд"] and "to=%s" % _день(0) in с["вперёд"]
    # переход по стрелке вернул на сегодня — это снова пресет «7 дней»
    html = к["админ"].get(с["вперёд"]).text
    assert re.search(r'class="v2-seg-btn is-active"\s+name="p" value="7"', html)
    assert main.расход_сводка(db, "", с_стр=_день(6), по_стр=_день(0))["код"] == "7"
    # у «всего времени» стрелок нет
    с = main.расход_сводка(db, "all")
    assert с["назад"] == "" and с["вперёд"] == ""


@pytest.mark.parametrize("дней,ждём", [(7, "day"), (45, "day"), (46, "week"),
                                       (366, "week"), (400, "month")])
def test_группировка_сама_по_длине(стенд, дней, ждём):
    db, _ = стенд
    с = main.расход_сводка(db, "", с_стр=_день(дней - 1), по_стр=_день(0))
    assert с["группировка"] == ждём and с["группировка_выбор"] == ""


def test_ручная_группировка_сильнее_но_не_дальше_предела(стенд):
    db, _ = стенд
    for назад, цена in ((1, 0.1), (8, 0.2), (40, 0.3), (80, 0.4)):
        _строка(db, created_at=_мск(назад), cost=цена)
    for вид in ("week", "month"):
        с = main.расход_сводка(db, "90", группировка=вид)
        assert с["группировка"] == вид and с["группировка_выбор"] == вид
        assert sum(д["всего"] for д in с["столбики"]) == pytest.approx(с["сумма"])
    # 200 дней по дням — больше предела столбиков: остаётся автоматическая
    с = main.расход_сводка(db, "", с_стр=_день(199), по_стр=_день(0), группировка="day")
    assert с["группировка"] == "week" and с["группировка_выбор"] == ""
    assert not next(г for г in с["группировки"] if г["код"] == "day")["можно"]


def _засеять_сравнение(db):
    """Текущие 7 суток: 4 операции на 0.60 $ (0.15 в среднем), кэш 50 %.
    Прошлые 7 суток ТОЙ ЖЕ длины: 2 операции на 0.40 $ (0.20), кэш 25 %.
    Строка на 13-е сутки назад — первая в учёте: прошлый отрезок покрыт."""
    for назад, цена in ((0, 0.10), (1, 0.20), (2, 0.15), (6, 0.15)):
        _строка(db, created_at=_мск(назад), cost=цена, prompt_tokens=1000, cached_tokens=500)
    for назад, цена in ((13, 0.20), (7, 0.20)):
        _строка(db, created_at=_мск(назад), cost=цена, prompt_tokens=1000, cached_tokens=250)


def test_сравнение_с_отрезком_той_же_длины_на_выдуманных_данных(стенд):
    db, к = стенд
    _засеять_сравнение(db)
    с = main.расход_сводка(db, "7")
    ср = с["сравнение"]
    assert ср["покрыт"] and ср["дней"] == 7 and ср["с"] == _день(13) and ср["по"] == _день(7)
    assert ср["сумма"]["знач"] == pytest.approx(50.0) and ср["сумма"]["тон"] == "warn"
    assert ср["средняя"]["знач"] == pytest.approx(-25.0) and ср["средняя"]["тон"] == "ok"
    assert ср["доля_кэша"]["знач"] == pytest.approx(25.0) and "п.п." in ср["доля_кэша"]["текст"]
    html = к["админ"].get("/admin/usage?p=7").text
    assert 'data-prev-sum="0.4' in html and "+50&nbsp;%" not in html
    assert "+50 %" in html and 'class="usage-delta is-warn"' in html


def test_подлог_сравнение_с_отрезком_другой_длины_замечен(стенд, monkeypatch):
    """Подлог: прошлый отрезок на сутки длиннее. Известная дельта +50 %
    обязана разойтись, а длина прошлого — не совпасть с выбранной."""
    db, _ = стенд
    _засеять_сравнение(db)
    monkeypatch.setattr(main, "_расход_прошлый",
                        lambda с, по: (с - timedelta(days=(по - с).days + 2), с - timedelta(days=1)))
    ср = main.расход_сводка(db, "7")["сравнение"]
    assert ср["дней"] == 8
    assert ср["сумма"]["знач"] != pytest.approx(50.0)


def test_прошлого_отрезка_нет_в_учёте_процент_не_выдумывается(стенд):
    db, к = стенд
    _строка(db, created_at=_мск(2), cost=0.3)
    ср = main.расход_сводка(db, "7")["сравнение"]
    assert not ср["покрыт"]
    for ключ in ("сумма", "средняя", "доля_кэша"):
        assert ср[ключ]["знач"] is None
    assert ср["сумма"]["текст"] == "нет данных за прошлый период"
    html = к["админ"].get("/admin/usage?p=7").text
    assert "нет данных за прошлый период" in html and 'data-prev-sum=""' in html


def test_остаток_ниже_порога_число_цветом_предупреждения(стенд, monkeypatch):
    _, к = стенд
    import balance_check
    monkeypatch.setattr(main, "_расход_остаток_спросить",
                        lambda: {"остаток": balance_check.ПОРОГ - 0.5, "причина": None,
                                 "при": datetime.utcnow()})
    html = к["админ"].get("/admin/usage").text
    assert 'usage-low" id="usage-balance"' in html and 'data-low="true"' in html
    monkeypatch.setattr(main, "_расход_остаток_спросить",
                        lambda: {"остаток": balance_check.ПОРОГ + 5, "причина": None,
                                 "при": datetime.utcnow()})
    html = к["админ"].get("/admin/usage").text
    assert 'data-low="false"' in html and "usage-low" not in html.split('id="usage-balance"')[0][-80:]


def test_тренд_по_дням_в_плитках(стенд):
    db, к = стенд
    _засеять_сравнение(db)
    т = main.расход_сводка(db, "7")["тренды"]
    assert т["сумма"]["d"].startswith("M0 ") and т["сумма"]["w"] == 6
    assert т["остаток"]["d"] == ""               # истории остатка нет — линии нет
    # день без операций у средней — разрыв, а не ноль
    assert main._расход_линия([1.0, None, 3.0])["d"].count("M") == 2
    html = к["админ"].get("/admin/usage?p=7").text
    assert 'id="usage-spark-spent"' in html
    assert 'id="usage-spark-balance"' in html and 'data-empty="true"' in html


# ── «РАСХОД-2», БЛОК 2: ГРАФИК ПО МАКЕТУ, ТОКЕНЫ, ТАБЛИЦЫ ─────────────────

def test_таблица_мин_средняя_макс_и_свёртка_по_инструменту(стенд):
    """Цена ОДНОЙ операции — мин, средняя, макс; строка без цены в минимум
    не попадает. Строка инструмента — сумма своих операций."""
    db, _ = стенд
    _строка(db, created_at=_мск(0), tool="hh-letter", cost=0.1)
    _строка(db, created_at=_мск(1), tool="hh-letter", cost=0.3)
    _строка(db, created_at=_мск(1), tool="hh-analyze", cost=0.2)
    _строка(db, created_at=_мск(2), tool="hh-analyze", cost=None, cost_missing=True)
    _строка(db, created_at=_мск(2), tool="nut-chat", cost=0.05)
    с = main.расход_сводка(db, "7")
    письмо = next(г for г in с["по_инструментам"] if г["имя"] == "hh-letter")
    assert (письмо["мин"], письмо["макс"]) == (pytest.approx(0.1), pytest.approx(0.3))
    разбор = next(г for г in с["по_инструментам"] if г["имя"] == "hh-analyze")
    assert разбор["мин"] == pytest.approx(0.2) and разбор["без_цены"] == 1
    группы = с["по_группам"]
    assert [г["группа"] for г in группы] == ["hh", "nutrition"]      # по сумме
    hh = группы[0]
    assert hh["сумма"] == pytest.approx(0.6) and hh["средняя"] == pytest.approx(0.2)
    assert (hh["мин"], hh["макс"]) == (pytest.approx(0.1), pytest.approx(0.3))
    assert sum(о["сумма"] for о in hh["операции"]) == pytest.approx(hh["сумма"])
    assert sum(г["сумма"] for г in группы) == pytest.approx(с["сумма"])


def test_шапка_столбика_называет_причину_нуля(стенд):
    """Нулевой столбик — словами и по причине: до начала учёта, вызовы
    без цены, записей нет."""
    db, _ = стенд
    _строка(db, created_at=_мск(3), cost=0.2)                       # первая в учёте
    _строка(db, created_at=_мск(1), cost=None, cost_missing=True)   # вызов без цены
    с = main.расход_сводка(db, "7")
    шапки = {д["день"]: д["шапка"] for д in с["столбики"]}
    assert шапки[_день(6)].endswith("учёт ещё не вёлся")
    assert шапки[_день(1)].endswith("расхода нет: без цены или неудачные (вызовов 1)")
    assert шапки[_день(0)].endswith("записей нет")
    assert шапки[_день(3)].endswith("0.20 $")
    подсказки = с["подсказки"]
    assert len(подсказки) == 7 and подсказки[3]["ч"][0]["v"] == pytest.approx(0.2)


def test_токены_по_частям_и_доля_кэша_одним_счётом(стенд):
    """Части — промпт без кэша, из кэша, ответ; неудачный вызов не входит.
    Доля кэша в подписи карточки — то же число, что на плитке."""
    db, к = стенд
    _строка(db, created_at=_мск(0), prompt_tokens=1000, cached_tokens=400, completion_tokens=500)
    _строка(db, created_at=_мск(0), prompt_tokens=900, completion_tokens=100, ok=False, cost=None)
    с = main.расход_сводка(db, "7")
    т = с["токены"]
    сегодня = т["столбики"][-1]
    assert сегодня["всего"] == 1500
    assert [(ч["к"], ч["v"]) for ч in сегодня["части"]] == [
        ("usage-t-prompt", 600), ("usage-t-cache", 400), ("usage-t-out", 500)]
    assert т["всего"] == 1500 and [к for к, _ in т["легенда"]] == ["prompt", "cache", "out"]
    html = к["админ"].get("/admin/usage?p=7").text
    плитка = re.search(r'id="usage-cache-share" data-share="([^"]+)"', html).group(1)
    подпись = re.search(r'id="usage-tok-cache" data-share="([^"]*)"', html).group(1)
    assert плитка == подпись and float(плитка) == pytest.approx(40.0)
    assert "Из кэша — 40&nbsp;% промпта" in html


def test_график_подпись_под_каждым_засечка_и_легенда(стенд):
    """Под КАЖДЫМ столбиком подпись; день без расхода — засечка, отрезок
    до начала учёта — нет; легенда есть, даже если цен нет вовсе."""
    db, к = стенд
    _строка(db, created_at=_мск(3), cost=None, cost_missing=True)
    _строка(db, created_at=_мск(1), cost=None, cost_missing=True)
    html = к["админ"].get("/admin/usage?p=7").text
    деньги = html.split('id="usage-plot"')[1].split('id="usage-days"')[0]
    кнопки = re.findall(r'<button type="button" class="usage-bar([^"]*)"', деньги)
    assert len(кнопки) == 7 and деньги.count('class="usage-xl"') == 7
    assert sum("is-before" in к for к in кнопки) == 3        # −6…−4: учёта ещё не было
    assert sum("is-zero" in к for к in кнопки) == 4          # −3…0: ноль в учёте
    assert not any("is-zero" in к and "is-before" in к for к in кнопки)
    легенда = html.split('id="usage-legend"')[1].split("</ul>")[0]
    assert легенда.count("<li") == len(main.РАСХОД_ГРУППЫ)   # цен нет — все инструменты


def test_ось_значений_делится_на_4_5_круглых_шагов():
    for макс in (0.0123, 0.2638, 1.0, 7.3, 98765.0, 0.0):
        ш = main._расход_шкала(макс, "usd")
        шагов = len(ш["деления"]) - 1
        assert шагов in (4, 5) and ш["верх"] >= макс
        assert ш["деления"][0]["подпись"] == "0" and ш["деления"][-1]["доля"] == 100


def test_в_пересчёте_на_месяц_и_доля_постоянных_только_при_постоянных(стенд):
    db, к = стенд
    _строка(db, created_at=_мск(9), cost=0.3, user_id=к["ид"]["админ"])
    _строка(db, created_at=_мск(0), cost=0.1, user_id=к["ид"]["админ"])
    html = к["админ"].get("/admin/usage").text
    assert "в пересчёте на месяц" in html and "приведено к месяцу" not in html
    assert re.search(r'id="usage-monthly" title="Учёт идёт 10 сут\.', html)
    assert 'id="usage-fixed-share"' not in html        # постоянные не заданы
    db.add(database.FixedCost(key="server", usd_month=6.0))
    db.commit()
    html = к["админ"].get("/admin/usage").text
    assert 'id="usage-fixed-share"' in html
