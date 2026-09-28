"""Предварительная проверка роликов (№352, письмо «Админка», блок 2):
разбор ответа модели, счёт меток и выгрузка справочника.

Прогон целиком — фоном, с заглушками модели и YouTube, с пределом денег
и в браузере — гоняет проба 73 (`check_video_precheck.py`); здесь то,
что проверяется без сети и без стенда.
"""
import os
import sqlite3

os.environ.setdefault("DB_PATH", "./test_model_usage.db")
os.environ.setdefault("AGENT_WEBHOOK_KEY", "test-key-8f3a91")

import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import database  # noqa: E402
import dump_exercises  # noqa: E402
import main  # noqa: E402


# ── 1. Ответ модели — строго одно из трёх слов плюс короткая причина ──

@pytest.mark.parametrize("текст, код", [
    ('{"verdict": "похоже", "reason": "заголовок называет упражнение"}', "match"),
    ('{"verdict": "Не похоже", "reason": "ролик про бег"}', "mismatch"),
    ('```json\n{"verdict": " не  уверена ", "reason": "общий заголовок"}\n```', "unsure"),
])
def test_три_слова_принимаются(текст, код):
    к, причина, беда = main._видео_разобрать(текст)
    assert (к, беда) == (код, None) and причина


@pytest.mark.parametrize("текст", [
    '{"verdict": "да", "reason": "похоже на правду"}',
    '{"verdict": "не уверен", "reason": "не наше слово"}',
    '{"verdict": "match", "reason": "код вместо слова"}',
    '{"verdict": "похоже"}',
    '{"verdict": "похоже", "reason": "' + "очень " * 60 + '"}',
    "Похоже: заголовок совпадает",
    '["похоже", "причина"]',
])
def test_иной_ответ_отвергается(текст):
    к, причина, беда = main._видео_разобрать(текст)
    assert к is None and not причина and беда


# ── 2. Счёт: метки модели — не «Проверено» ──────────────────────────

@pytest.fixture
def db():
    движок = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    database.Base.metadata.create_all(движок)
    сессия = sessionmaker(bind=движок)()
    yield сессия
    сессия.close()


def _упр(db, ид, статус, ролик, метка=None):
    db.add(database.Exercise(id=ид, name=ид, name_ru=ид, level="beginner",
                             category="strength", youtube_id=ролик,
                             video_status=статус, model_verdict=метка))


def test_метки_модели_не_растят_проверено_и_очередь_без_отмеченных(db):
    _упр(db, "a", "unchecked", "yt1", "match")
    _упр(db, "b", "unchecked", "yt2", "mismatch")
    _упр(db, "c", "approved", "yt3", "match")      # владелец уже решил
    _упр(db, "d", "unchecked", "yt4")               # метки нет
    _упр(db, "e", "no_video", None)
    _упр(db, "f", "unchecked", "yt6", "nodata")
    db.commit()
    п = main._упр_проверка(db)
    assert п["готово"] == 1                                   # только «одобрено»
    assert (п["счёт"]["m-match"], п["счёт"]["m-mismatch"], п["счёт"]["m-unsure"]) == (1, 1, 0)
    assert п["модель"]["метки"] == {"match": 2, "mismatch": 1, "unsure": 0, "nodata": 1}
    assert (п["модель"]["к_разбору"], п["модель"]["размечено"]) == (4, 3)


def test_замена_ролика_стирает_метку(monkeypatch):
    """Метка была про прежний ролик — после замены её быть не должно."""
    движок = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    database.Base.metadata.create_all(движок)
    Сессия = sessionmaker(bind=движок)
    db = Сессия()
    _упр(db, "a", "unchecked", "yt1", "mismatch")
    db.commit()
    e = db.get(database.Exercise, "a")
    e.model_reason = "про другое упражнение"
    db.commit()
    from fastapi.testclient import TestClient
    from auth import create_token, hash_password
    админ = database.User(email="adm@video.test", password_hash=hash_password("x-123456"),
                          is_verified=True, is_admin=True)
    db.add(админ)
    db.commit()
    main.app.dependency_overrides[main.get_db] = lambda: db
    # ГЕЙТ ПОДТВЕРЖДЁННОЙ ПОЧТЫ — middleware (§5.3): зависимостей он не видит
    # и берёт пользователя через `SessionLocal`. Без подмены тест зависел
    # от общей базы: в CI там засеянный стенд, где пользователь с тем же
    # номером не подтверждён, — гейт ответил 428 (прогон 36486120393),
    # локально прошло. Тот же случай, что у `test_admin_usage`
    monkeypatch.setattr(main, "SessionLocal", Сессия)
    try:
        к = TestClient(main.app)
        к.cookies.set("access_token", create_token(админ.id))
        r = к.post("/admin/exercises/a/replace",
                   json={"youtube_url": "https://youtu.be/dQw4w9WgXcQ"})
    finally:
        main.app.dependency_overrides.pop(main.get_db, None)
    assert r.status_code == 200, r.text
    db.expire_all()
    e = db.get(database.Exercise, "a")
    assert (e.youtube_id, e.model_verdict, e.model_reason) == ("dQw4w9WgXcQ", None, None)
    db.close()


# ── 3. Выгрузка справочника: метки модели — осознанно вне снимка ──────

def test_выгрузка_знает_метки_модели_и_ловит_новую_колонку(tmp_path):
    путь = tmp_path / "ex.db"
    движок = create_engine("sqlite:///" + str(путь))
    database.Base.metadata.create_all(движок, tables=[database.Exercise.__table__])
    движок.dispose()
    conn = sqlite3.connect(путь)
    try:
        assert dump_exercises._проверить_поля(conn)
        conn.execute("ALTER TABLE exercises ADD COLUMN probe_new VARCHAR")
        assert not dump_exercises._проверить_поля(conn)
    finally:
        conn.close()
