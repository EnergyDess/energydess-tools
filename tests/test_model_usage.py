"""Учёт расхода на модели (BACKLOG №346).

Четыре вопроса, и у каждого — отрицательный контроль рядом:

1. ПОКРЫТИЕ: каждый вызов модели идёт через `_модель_post`. Разбор
   ДЕРЕВА, а не греп: адрес в комментарии вызовом не является.
2. ЧИСЛА: строка расхода берёт токены и цену из `usage` ответа, а отказ
   сервиса и отказ сети тоже ложатся строкой — с кодом ошибки.
3. СХЕМА: в `model_usage` нет ни одной колонки под текст запроса
   или ответа. Проверяется по МЕТАДАННЫМ таблицы, а не по чтению кода.
4. СБОЙ ЗАПИСИ не роняет инструмент: ответ человеку уходит, а в журнале
   стоит строка `[расход]`.
"""
import asyncio
import ast
import io
import os
import pathlib

os.environ.setdefault("DB_PATH", "./test_model_usage.db")
os.environ.setdefault("AGENT_WEBHOOK_KEY", "test-key-8f3a91")

import pytest  # noqa: E402
from sqlalchemy import Text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

import database  # noqa: E402
import main  # noqa: E402

КОРЕНЬ = pathlib.Path(__file__).resolve().parent.parent
АДРЕСА = ("OPENROUTER_URL", "OPENROUTER_AUDIO_URL")

# Колонки журнала — ПОИМЁННО. Новая колонка обязана попасть сюда
# осознанно: «что спросили» или «что ответили» превратили бы журнал
# расхода в историю обращений человека, в том числе к справочнику лекарств
ДОПУСТИМЫЕ_КОЛОНКИ = {"id", "created_at", "tool", "model", "prompt_tokens",
                      "completion_tokens", "cost", "cost_missing", "user_id",
                      "ok", "error_code", "gen_id"}


def места_вызова(исходник: str) -> tuple[list, list]:
    """(все места, где адрес модели передан в вызов; из них — через обёртку)."""
    все, через_учёт = [], []
    for узел in ast.walk(ast.parse(исходник)):
        if not isinstance(узел, ast.Call):
            continue
        for а in узел.args:
            if isinstance(а, ast.Name) and а.id in АДРЕСА:
                все.append(узел.lineno)
                if isinstance(узел.func, ast.Name) and узел.func.id == "_модель_post":
                    через_учёт.append(узел.lineno)
    return все, через_учёт


def колонки_с_текстом(таблица) -> list:
    """Колонки вне белого списка и любые колонки типа Text."""
    return sorted(к.name for к in таблица.columns
                  if к.name not in ДОПУСТИМЫЕ_КОЛОНКИ or isinstance(к.type, Text))


def _исходник():
    return io.open(КОРЕНЬ / "main.py", encoding="utf-8").read()


# ── 1. Покрытие ─────────────────────────────────────────────────────────

def test_каждый_вызов_модели_идёт_через_учёт():
    все, через_учёт = места_вызова(_исходник())
    print(f"мест вызова модели {len(все)}, через учёт {len(через_учёт)}")
    assert len(все) == 12, все
    assert sorted(все) == sorted(через_учёт)


def test_подлог_вызов_мимо_учёта_ловится():
    """(а) Одно место переписано на голый `client.post` — проверка падает."""
    исходник = _исходник()
    было = '_модель_post(client, "wk-chat", user.id,'
    assert исходник.count(было) == 1
    подлог = исходник.replace(было, "client.post(", 1)
    все, через_учёт = места_вызова(подлог)
    assert len(все) == 12 and len(через_учёт) == 11


# ── 2. Числа из ответа ──────────────────────────────────────────────────

class _Ответ:
    def __init__(self, код, тело):
        self.status_code = код
        self._тело = тело

    def json(self):
        return self._тело


class _Клиент:
    def __init__(self, ответ=None, беда=None):
        self.ответ, self.беда = ответ, беда

    async def post(self, url, **kw):
        if self.беда:
            raise self.беда
        return self.ответ


def _последняя():
    db = database.SessionLocal()
    try:
        return db.query(database.ModelUsage).order_by(database.ModelUsage.id.desc()).first()
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _схема():
    database.init_db()


def _позвать(клиент, инструмент="тест", user_id=7):
    return asyncio.run(main._модель_post(
        клиент, инструмент, user_id, main.OPENROUTER_URL,
        json={"model": "проба/модель", "messages": []}))


def test_удачный_ответ_ложится_своими_числами():
    тело = {"id": "gen-123", "choices": [{"message": {"content": "секрет"}}],
            "usage": {"prompt_tokens": 111, "completion_tokens": 22, "cost": 0.00345}}
    _позвать(_Клиент(_Ответ(200, тело)), "тест-удача")
    с = _последняя()
    assert (с.tool, с.model, с.prompt_tokens, с.completion_tokens) == \
        ("тест-удача", "проба/модель", 111, 22)
    assert abs(с.cost - 0.00345) < 1e-12 and с.cost_missing is False
    assert с.ok is True and с.error_code is None and с.user_id == 7
    assert с.gen_id == "gen-123"


def test_без_стоимости_цена_пуста_и_помечена():
    тело = {"choices": [{"message": {"content": "x"}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 1}}
    _позвать(_Клиент(_Ответ(200, тело)), "тест-без-цены")
    с = _последняя()
    assert с.cost is None and с.cost_missing is True and с.ok is True


def test_отказ_сервиса_ложится_с_кодом():
    тело = {"error": {"code": 402, "message": "Insufficient credits"}}
    _позвать(_Клиент(_Ответ(402, тело)), "тест-отказ")
    с = _последняя()
    assert с.ok is False and с.error_code == "http_402" and (с.cost or 0) == 0


def test_ошибка_в_теле_при_200_ложится_с_кодом():
    _позвать(_Клиент(_Ответ(200, {"error": {"code": 429}})), "тест-тело")
    с = _последняя()
    assert с.ok is False and с.error_code == "error_429"


def test_отказ_сети_ложится_и_пробрасывается():
    import httpx
    with pytest.raises(httpx.ReadTimeout):
        _позвать(_Клиент(беда=httpx.ReadTimeout("x")), "тест-сеть")
    с = _последняя()
    assert с.ok is False and с.error_code == "ReadTimeout"


# ── 3. Схема: текста нет ────────────────────────────────────────────────

def test_в_журнале_расхода_нет_текста():
    таблица = database.Base.metadata.tables["model_usage"]
    print("колонки:", sorted(к.name for к in таблица.columns))
    assert колонки_с_текстом(таблица) == []


def test_подлог_колонка_с_текстом_ловится():
    """(в) Колонка под текст ответа — проверка обязана её назвать."""
    from sqlalchemy import Column, MetaData, Table
    копия = Table("model_usage", MetaData(),
                  *[к.copy() for к in database.Base.metadata.tables["model_usage"].columns],
                  Column("reply_text", Text))
    assert колонки_с_текстом(копия) == ["reply_text"]


# ── 4. Сбой записи не роняет инструмент ─────────────────────────────────

class _БитаяСессия:
    def add(self, *_):
        pass

    def commit(self):
        raise OperationalError("INSERT", {}, Exception("database is locked"))

    def close(self):
        pass


def _оценка_еды(monkeypatch):
    """Настоящий инструмент — оценка КБЖУ — на поддельном ответе модели."""
    monkeypatch.setattr(main, "OPENROUTER_API_KEY", "тест")
    ответ = _Ответ(200, {"choices": [{"message": {"content":
        '{"known":true,"name":"суп","calories":100,"protein":5,"fat":3,"carbs":10}'},
        "finish_reason": "stop"}], "usage": {"prompt_tokens": 9, "completion_tokens": 9}})

    class _КлиентКонтекст(_Клиент):
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(main.httpx, "AsyncClient",
                        lambda *a, **k: _КлиентКонтекст(ответ))
    return asyncio.run(main._ai_food_estimate("суп", user_id=7))


def test_сбой_записи_не_роняет_инструмент(monkeypatch, capsys):
    monkeypatch.setattr(main, "SessionLocal", lambda: _БитаяСессия())
    итог = _оценка_еды(monkeypatch)
    assert итог and итог[0]["calories"] == 100
    assert "[расход] запись НЕ удалась" in capsys.readouterr().out


def test_подлог_сбой_записи_без_перехвата_роняет(monkeypatch):
    """(б) Перехват снят — тот же сбой записи роняет инструмент.

    Доказывает, что предыдущий тест проверяет перехват, а не то, что
    запись до базы не доходит вовсе."""
    monkeypatch.setattr(main, "SessionLocal", lambda: _БитаяСессия())
    monkeypatch.setattr(main, "РАСХОД_СБОИ_ЗАПИСИ", ())
    итог = _оценка_еды(monkeypatch)
    # _ai_food_estimate сам ловит любую беду и отдаёт «оценить не удалось»
    assert итог == []
