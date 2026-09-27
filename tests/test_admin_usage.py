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

    def подлог(db, период="7", инструмент="", сейчас=None):
        с = настоящая(db, период, инструмент, сейчас)
        с["без_цены"] = 0
        for г in с["по_инструментам"] + с["по_моделям"]:
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
