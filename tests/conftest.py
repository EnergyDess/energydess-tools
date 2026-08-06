"""Общая обвязка тестов календарных эндпоинтов агента.

Ключ выставляется ДО импорта модуля: `agent_slots` читает AGENT_WEBHOOK_KEY
на уровне файла и без него бросает RuntimeError — это его штатное поведение,
а не помеха тестам, поэтому подсовываем ключ, а не отключаем проверку.
"""

import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

os.environ.setdefault("AGENT_WEBHOOK_KEY", "test-key-8f3a91")

# Корень проекта в sys.path: pytest кладёт туда каталог с тестом, а не корень.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI                       # noqa: E402
from fastapi.testclient import TestClient         # noqa: E402

import agent_slots                                # noqa: E402

KEY = os.environ["AGENT_WEBHOOK_KEY"]


@pytest.fixture
def client():
    """Приложение только с роутером агента.

    Полный main.py не поднимаем намеренно: он тянет базу, миграции и шаблоны,
    к календарной арифметике отношения не имеющие, и тесты стали бы зависеть
    от состояния app.db.
    """
    app = FastAPI()
    app.include_router(agent_slots.router)
    return TestClient(app)


@pytest.fixture
def freeze(monkeypatch):
    """Замораживает «сейчас». Подменяется функция now_msk, а не datetime:

    ради этого она и вынесена отдельно — вызов datetime.now прямо в теле
    обработчика подменить было бы нечем.
    """
    def _freeze(момент: str):
        dt = datetime.fromisoformat(момент).replace(tzinfo=agent_slots.TZ)
        monkeypatch.setattr(agent_slots, "now_msk", lambda: dt)
        return dt
    return _freeze


def auth(**kwargs):
    """Заголовки с верным ключом."""
    h = {"X-Agent-Key": KEY}
    h.update(kwargs)
    return h


def час_дня(строка: str) -> int:
    """Час из id слота «2026-08-07T10:00»."""
    return int(строка[11:13])


def свободный_час(день: date) -> int:
    """Любой свободный час дня. Занятость синтетическая, но детерминированная,
    поэтому хардкодить конкретные часы в тестах нельзя — они меняются вместе
    с BUSY_SHARE, и тест ломался бы на правке константы, а не на ошибке."""
    свободные = agent_slots.free_hours(день)
    assert свободные, f"{день}: свободных слотов нет вовсе"
    return свободные[0]


def занятый_час(день: date) -> int:
    """Любой занятый час дня. None не возвращает: если день свободен целиком,
    тест должен упасть здесь, а не притвориться пройденным."""
    занятые = [ч for ч in agent_slots.working_hours()
               if ч not in agent_slots.free_hours(день)]
    assert занятые, f"{день}: занятых слотов нет, тест бессмыслен"
    return занятые[0]


def первый_день_с_занятым_слотом(старт: date) -> date:
    """Ближайший рабочий день, где есть хотя бы один занятый час."""
    д = старт
    for _ in range(30):
        if agent_slots.is_working_day(д) and len(agent_slots.free_hours(д)) < 9:
            return д
        д += timedelta(days=1)
    raise AssertionError("за месяц не нашлось дня с занятым слотом")
