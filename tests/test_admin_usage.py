"""Страница расхода на модели `/admin/usage` (BACKLOG №346, заход 5, блок 2).

Три вопроса, у каждого — подлог рядом:

1. ДОСТУП: гость и обычный пользователь страницы не видят; подлог
   снимает проверку прав — обычный пользователь её видит.
2. СТРОКА БЕЗ ЦЕНЫ в сумму не входит и печатается отдельным счётчиком;
   подлог считает её нулём-ценой внутри суммы — тест это замечает.
3. ПУСТОЙ УЧЁТ — «данных нет», а не «0 $».

База своя, в памяти: общая база тестов накапливает строки расхода
от других модулей, и «пусто» на ней не поставить.
"""
import os
from datetime import datetime, timedelta

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
    yield db, клиенты
    main.app.dependency_overrides.pop(main.get_db, None)
    db.close()


def _строка(db, **kw):
    поля = dict(created_at=datetime.utcnow() - timedelta(hours=1), tool="hh-letter",
                model="anthropic/claude-opus-4-8", prompt_tokens=1000,
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
    п7 = с["периоды"][0]
    assert п7["вызовов"] == 2
    assert п7["сумма"] == pytest.approx(0.25)
    assert п7["без_цены"] == 1
    html = к["админ"].get("/admin/usage").text
    assert "без цены 1" in html
    assert 'data-missing="7"' in html
    assert "0.2500 $" in html


def test_подлог_цена_нулём_в_сумме_замечен(стенд, monkeypatch):
    """Подлог: сводка считает строку без цены нулевой и не ведёт счётчик.
    Проверка обязана это заметить — счётчик 0 при одной такой строке."""
    db = стенд[0]
    _строка(db, cost=None, cost_missing=True)
    настоящая = main.расход_сводка

    def подлог(db, сейчас=None):
        с = настоящая(db, сейчас)
        for п in с["периоды"]:
            п["без_цены"] = 0
            for г in п["по_инструментам"] + п["по_моделям"]:
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
    assert "данных нет" in html
    assert "0.0000 $" not in html


def test_неудачи_по_кодам_за_неделю(стенд):
    db, _ = стенд
    _строка(db, ok=False, cost=None, error_code="http_429")
    _строка(db, ok=False, cost=None, error_code="http_429")
    _строка(db, ok=False, cost=None, error_code="http_429",
            created_at=datetime.utcnow() - timedelta(days=9))
    с = main.расход_сводка(db)
    assert с["неудачи"][0]["код"] == "http_429"
    assert с["неудачи"][0]["n"] == 2


def test_время_по_москве():
    assert main._расход_момент(datetime(2026, 9, 18, 21, 30)) == "19.09.2026 00:30"


# ── СБОЙ ЗАПРОСА ОСТАТКА (заход 7, блок 2) ──────────────────────────────
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
    assert 'id="usage-balance-note"' in удачно and "7.65 $" in удачно
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
