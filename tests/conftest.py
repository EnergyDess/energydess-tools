"""Общая обвязка тестов календарных эндпоинтов агента.

Ключ выставляется ДО импорта модуля: `agent_slots` читает AGENT_WEBHOOK_KEY
на уровне файла и без него бросает RuntimeError — это его штатное поведение,
а не помеха тестам, поэтому подсовываем ключ, а не отключаем проверку.
"""

import os
import sys
from datetime import datetime
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
