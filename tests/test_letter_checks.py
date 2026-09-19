"""Журнал нарушений письма HH (задача 346, заход 6, блок 1, пункт 8).

Подлог по постановке: поддельное письмо с находкой уходит в обработку —
в журнале появляется строка, а на `/admin/usage` счётчик вырастает на 1.
Плюс обратный случай (чистое письмо — строк нет) и сбой проверки: письмо
не роняется, в журнал ложится `сбой_проверки`.

База своя, в памяти — как у `test_admin_usage.py`.
"""
import os
import re
from datetime import datetime

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

ПИСЬМО = "Здравствуйте!\n\nДелаю API на FastAPI.\n\nС уважением, Денис"
НАРУШЕНИЕ = ПИСЬМО.replace("С уважением", "Готов созвониться, чтобы обсудить детали.\n\nС уважением")


class _Досье:
    ending_style = {"suggest_call": False, "suggest_test_task": False, "just_farewell": True}
    never_mention = "Не упоминать зарплату."


@pytest.fixture
def стенд(monkeypatch):
    движок = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    database.Base.metadata.create_all(движок)
    Сессия = sessionmaker(bind=движок)
    db = Сессия()
    админ = database.User(email="adm@checks.test", password_hash=hash_password("x-123456"),
                          is_verified=True, is_admin=True)
    db.add(админ)
    db.commit()

    def _db():
        с = Сессия()
        try:
            yield с
        finally:
            с.close()

    main.app.dependency_overrides[main.get_db] = _db
    monkeypatch.setattr(main, "_расход_остаток_спросить",
                        lambda: {"остаток": 12.5, "причина": None, "при": datetime.utcnow()})
    к = TestClient(main.app)
    к.cookies.set("access_token", create_token(админ.id))
    yield db, к
    main.app.dependency_overrides.pop(main.get_db, None)
    db.close()


def _счёт_на_странице(к, вид):
    html = к.get("/admin/usage").text
    м = re.search(r'data-violation="%s"><td>[^<]*</td><td class="usage-n">(\d+)</td>' % вид, html)
    return int(м.group(1)) if м else 0


def _проверить(db, текст, номер=7):
    return main._проверить_письмо(db, номер, текст, "Навыки: FastAPI", "", "", [], _Досье())


def test_поддельное_письмо_с_находкой_даёт_строку_и_плюс_один(стенд):
    db, к = стенд
    до = _счёт_на_странице(к, "созвон")
    виды = _проверить(db, НАРУШЕНИЕ)
    assert виды == ["созвон"]
    строки = db.query(database.LetterCheck).all()
    assert [(с.letter_id, с.kind) for с in строки] == [(7, "созвон")]
    assert _счёт_на_странице(к, "созвон") == до + 1


def test_чистое_письмо_строк_не_даёт(стенд):
    db, к = стенд
    assert _проверить(db, ПИСЬМО) == []
    assert db.query(database.LetterCheck).count() == 0
    assert "Нарушений в письмах за 7 дней нет" in к.get("/admin/usage").text


def test_спорное_и_отрицание_в_журнал_не_идут_а_приписка_идёт(стенд):
    """Задача 346, заход 7: счётчик на /admin/usage считает только однозначные
    находки. Отрицание и упоминание без признаков строк не дают; приписка
    технологии вне досье себе — даёт."""
    db, к = стенд
    assert _проверить(db, "Здравствуйте! С PostgreSQL не работал. Groq — любопытная вещь.") == []
    assert db.query(database.LetterCheck).count() == 0
    assert _проверить(db, "Здравствуйте! Работаю с Groq каждый день.", номер=8) == ["вне_досье"]
    assert _счёт_на_странице(к, "вне_досье") == 1


def test_сбой_проверки_не_роняет_и_пишется(стенд, monkeypatch):
    db, к = стенд

    def _упасть(*a, **kw):
        raise RuntimeError("подложенный сбой")

    monkeypatch.setattr(main._письмо_факты, "проверить", _упасть)
    assert _проверить(db, НАРУШЕНИЕ) == ["сбой_проверки"]
    assert _счёт_на_странице(к, "сбой_проверки") == 1


def test_журнал_без_текста_и_без_user_id():
    колонки = set(database.LetterCheck.__table__.columns.keys())
    assert колонки == {"id", "created_at", "letter_id", "kind"}
