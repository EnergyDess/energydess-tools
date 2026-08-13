"""Источник данных о продукте не подменяется молча (BACKLOG.md, задача 74).

Два отказа одного замера, и оба немые:

  1. `except Exception: return []` в `_off_search` не отличался снаружи
     от «справочник честно ничего не нашёл». В обоих случаях включалась
     оценка ИИ, и человек получал придуманные числа там, где ждал
     справочник.
  2. На запрос «йцукенгшщз» модель отвечала карточкой «блюдо не
     существует» с нулями во всех полях, карточка была кликабельной
     и добавлялась в дневник как обычный продукт.

Проверяется подстановкой ответа: живой вызов модели недетерминирован,
а нужен именно разбор её ответа.
"""

import asyncio
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("AGENT_WEBHOOK_KEY", "test-key-8f3a91")

import main


def оценка(ответ_модели: str, monkeypatch) -> list:
    """Прогоняет _ai_food_estimate с подставленным ответом модели."""
    monkeypatch.setattr(main, "OPENROUTER_API_KEY", "тест")
    monkeypatch.setattr(main, "_model_output", lambda *a, **k: (ответ_модели, None))

    class _Ответ:
        def json(self): return {}

    class _Клиент:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, *a, **k): return _Ответ()

    monkeypatch.setattr(main.httpx, "AsyncClient", lambda *a, **k: _Клиент())
    return asyncio.run(main._ai_food_estimate("проба"))


def test_модель_сказала_что_не_знает(monkeypatch):
    assert оценка('{"known": false}', monkeypatch) == []


def test_нулевая_калорийность_отбрасывается(monkeypatch):
    """Вторая застава: она не зависит от послушности модели.

    Ровно этот ответ и приходил на «йцукенгшщз» — имя словами говорит,
    что блюда нет, а числа при этом нули."""
    ответ = ('{"name":"блюдо не существует","calories":0,'
             '"protein":0,"fat":0,"carbs":0}')
    assert оценка(ответ, monkeypatch) == []


def test_настоящая_оценка_проходит_и_помечена_источником(monkeypatch):
    ответ = ('{"known":true,"name":"Сырники","calories":220,'
             '"protein":17,"fat":11,"carbs":15}')
    итог = оценка(ответ, monkeypatch)
    assert len(итог) == 1
    assert итог[0]["calories"] == 220
    assert итог[0]["source"] == "ai", "без метки источника карточку не отличить от записи базы"


def test_отрицательная_калорийность_тоже_отбрасывается(monkeypatch):
    ответ = '{"name":"нечто","calories":-5,"protein":0,"fat":0,"carbs":0}'
    assert оценка(ответ, monkeypatch) == []


def test_сбой_справочника_отличим_от_пустой_выдачи(monkeypatch):
    """`_off_search` возвращает ПАРУ, и вторая половина — причина сбоя."""
    class _Клиент:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, *a, **k): raise main.httpx.ConnectError("сеть легла")

    monkeypatch.setattr(main.httpx, "AsyncClient", lambda *a, **k: _Клиент())
    находки, сбой = asyncio.run(main._off_search("гречка"))
    assert находки == []
    assert сбой == "ConnectError", "иначе сбой неотличим от «ничего не нашлось»"


def test_пустая_выдача_без_сбоя_даёт_пустую_причину(monkeypatch):
    class _Ответ:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"hits": []}

    class _Клиент:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, *a, **k): return _Ответ()

    monkeypatch.setattr(main.httpx, "AsyncClient", lambda *a, **k: _Клиент())
    находки, сбой = asyncio.run(main._off_search("йцукенгшщз"))
    assert находки == []
    assert сбой == ""


def test_ответ_справочника_с_кодом_ошибки_считается_сбоем(monkeypatch):
    """HTTP 500 — не «ничего не нашлось». Раньше `hits` просто не было
    в теле, и код молча возвращал пустой список."""
    class _Ответ:
        status_code = 500
        def raise_for_status(self):
            raise main.httpx.HTTPStatusError("500", request=None, response=None)
        def json(self): return {}

    class _Клиент:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, *a, **k): return _Ответ()

    monkeypatch.setattr(main.httpx, "AsyncClient", lambda *a, **k: _Клиент())
    находки, сбой = asyncio.run(main._off_search("гречка"))
    assert находки == []
    assert сбой == "HTTPStatusError"
