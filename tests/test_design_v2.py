"""Витрина дизайн-системы v2 `/admin/design-v2` (BACKLOG №352, письмо 1).

ДОСТУП: администратор видит, обычный пользователь и гость — нет (302
на `/`, как у остальных разделов админки). ПОДЛОГ снимает проверку прав —
и обычный пользователь страницу видит; тест обязан это заметить, иначе
«отказ» мог бы идти от чего-то другого (например, от падения шаблона).

База своя, в памяти: общая база тестов накапливает чужих пользователей.
"""
import os

os.environ.setdefault("DB_PATH", "./test_design_v2.db")
os.environ.setdefault("AGENT_WEBHOOK_KEY", "test-key-8f3a91")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import database  # noqa: E402
import main  # noqa: E402
from auth import create_token, hash_password  # noqa: E402

АДРЕС = "/admin/design-v2"


@pytest.fixture
def клиенты():
    движок = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    database.Base.metadata.create_all(движок)
    Сессия = sessionmaker(bind=движок)
    db = Сессия()
    админ = database.User(email="adm@v2.test", password_hash=hash_password("x-123456"),
                          is_verified=True, is_admin=True)
    простой = database.User(email="usr@v2.test", password_hash=hash_password("x-123456"),
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
    к = {}
    for имя, u in (("админ", админ), ("простой", простой)):
        c = TestClient(main.app)
        c.cookies.set("access_token", create_token(u.id))
        к[имя] = c
    к["гость"] = TestClient(main.app)
    yield к
    main.app.dependency_overrides.pop(main.get_db, None)
    db.close()


def test_админ_видит_остальные_получают_отказ(клиенты):
    r = клиенты["админ"].get(АДРЕС)
    assert r.status_code == 200
    # Страница — витрина, а не пустышка: пять шапок инструментов и v2.css
    assert r.text.count('class="v2-page-head"') == 5
    assert "/static/v2.css" in r.text
    for кто in ("простой", "гость"):
        r = клиенты[кто].get(АДРЕС, follow_redirects=False)
        assert r.status_code == 302, кто
        assert r.headers["location"] == "/", кто
        assert "v2-page-head" not in r.text, кто


def test_подлог_снятая_проверка_прав_замечается(клиенты, monkeypatch):
    """Обратная сторона: без `_admin_guard` обычный пользователь видит
    витрину. Если бы и тогда был отказ, первый тест доказывал бы не права."""
    monkeypatch.setattr(main, "_admin_guard", lambda user: True)
    r = клиенты["простой"].get(АДРЕС, follow_redirects=False)
    assert r.status_code == 200
    assert r.text.count('class="v2-page-head"') == 5
