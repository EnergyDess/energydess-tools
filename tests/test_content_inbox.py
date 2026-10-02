"""Письмо D1, блок 2 (задача 383): приём находок из бота второго мозга
и карточки «от тебя» на «Сегодня». Вызовов моделей нет. Контроли:

1. ТОКЕН: без токена — 401, с неверным — 401, с верным — 200 и запись
   в базе. Подлог: токена в окружении нет — верный по виду тоже 401.
2. ДУБЛЬ по `tg_message_id` и по `url` не создаёт вторую запись; через
   8 дней та же ссылка — новая запись.
3. ТЕКСТ длиннее 8000 обрезается; пустой текст у идеи — 400.
4. «В РАБОТУ» — идея вида «от тебя» (sort=user) в плане, ролик в конвейере;
   «УБРАТЬ» — карточка пропала, запись в архиве (не удалена).
5. ЛИМИТ 60 в час срабатывает 429; неверные запросы тоже считаются.
6. «Сегодня» показывает карточки «от тебя» с меткой «слух»; нет записей —
   блока нет; ссылка совпала с записью радара — «уже в сюжете».
"""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("DB_PATH", "./test_model_usage.db")
os.environ.setdefault("AGENT_WEBHOOK_KEY", "test-key-8f3a91")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import content_inbox as cin  # noqa: E402
import database  # noqa: E402
import main  # noqa: E402
from auth import create_token  # noqa: E402
from content_db import ContentIdea, ContentInbox, ContentItem, ContentStory, ContentVideo  # noqa: E402
from test_content_package import стенд  # noqa: E402,F401

ТОКЕН = "t" * 48


@pytest.fixture
def вход(стенд, monkeypatch):
    monkeypatch.setenv("CONTENT_INBOX_TOKEN", ТОКЕН)
    db = стенд["Сессия"]()
    db.query(database.LoginAttempt).delete()
    db.commit()
    db.close()
    стенд["клиент"] = TestClient(main.app)
    return стенд


def _шлю(клиент, тело, токен=ТОКЕН):
    заголовки = {"X-Inbox-Token": токен} if токен is not None else {}
    return клиент.post("/content/inbox", json=тело, headers=заголовки)


def _записей(стенд):
    db = стенд["Сессия"]()
    n = db.query(ContentInbox).count()
    db.close()
    return n


ПОСТ = {"kind": "forward", "text": "Rockstar показала новый кадр", "source_name": "Тест-канал",
        "tg_message_id": "101"}


def test_токен_нет_неверный_верный(вход):
    к = вход["клиент"]
    assert _шлю(к, ПОСТ, токен=None).status_code == 401
    assert _шлю(к, ПОСТ, токен="wrong-token").status_code == 401
    assert _записей(вход) == 0
    r = _шлю(к, ПОСТ)
    assert r.status_code == 200 and r.json()["ok"] is True and isinstance(r.json()["id"], int)
    assert _записей(вход) == 1
    r2 = к.post("/content/inbox", json={**ПОСТ, "tg_message_id": "102"},
                headers={"Authorization": "Bearer " + ТОКЕН})
    assert r2.status_code == 200 and _записей(вход) == 2


def test_подлог_токена_в_окружении_нет_всё_401(вход, monkeypatch):
    monkeypatch.setenv("CONTENT_INBOX_TOKEN", "")
    assert _шлю(вход["клиент"], ПОСТ, токен="").status_code == 401
    assert _шлю(вход["клиент"], ПОСТ).status_code == 401
    assert _записей(вход) == 0


def test_дубль_по_tg_и_по_url(вход):
    к = вход["клиент"]
    первый = _шлю(к, ПОСТ).json()["id"]
    r = _шлю(к, {**ПОСТ, "text": "другой текст"})
    assert r.json() == {"ok": True, "id": первый, "duplicate": True}
    ссылка = {"kind": "link", "url": "https://www.reddit.com/r/GTA6/comments/abc/?utm_source=tg"}
    второй = _шлю(к, ссылка).json()["id"]
    r = _шлю(к, {"kind": "link", "url": "https://reddit.com/r/GTA6/comments/abc", "tg_message_id": "999"})
    assert r.json()["id"] == второй and r.json().get("duplicate")
    assert _записей(вход) == 2
    # Через 8 дней — уже не дубль
    db = вход["Сессия"]()
    з = db.get(ContentInbox, второй)
    з.created_at = datetime.utcnow() - timedelta(days=8)
    db.commit()
    db.close()
    r = _шлю(к, {"kind": "link", "url": "https://reddit.com/r/GTA6/comments/abc"})
    assert r.json()["id"] != второй and not r.json().get("duplicate")


def test_подлог_без_проверки_дублей_вторая_запись(вход, monkeypatch):
    monkeypatch.setattr(cin, "найти_дубль", lambda db, поля: None)
    _шлю(вход["клиент"], ПОСТ)
    _шлю(вход["клиент"], ПОСТ)
    assert _записей(вход) == 2


def test_длинный_обрезан_пустая_идея_400(вход):
    к = вход["клиент"]
    r = _шлю(к, {"kind": "idea", "text": "а" * 9000})
    assert r.status_code == 200
    db = вход["Сессия"]()
    assert len(db.get(ContentInbox, r.json()["id"]).text) == 8000
    db.close()
    r = _шлю(к, {"kind": "idea", "text": "   "})
    assert r.status_code == 400 and "пустой" in r.json()["error"]
    assert _шлю(к, {"kind": "voice", "text": "x"}).status_code == 400
    assert _шлю(к, {"kind": "link"}).status_code == 400


def _админ(стенд):
    к = стенд["клиент"]
    к.cookies.set("access_token", create_token(стенд["ид"]["админ"], 0))
    return к


def test_в_работу_идея_от_тебя_в_плане_убрать_архив(вход):
    к = вход["клиент"]
    a = _шлю(к, {"kind": "idea", "text": "Снять сравнение погоды\nподробности", "rumor": True}).json()["id"]
    b = _шлю(к, {"kind": "link", "url": "https://example.com/x", "text": "ссылка"}).json()["id"]
    к = _админ(вход)
    r = к.post(f"/content/api/inbox/{a}", json={"action": "work"})
    assert r.status_code == 200, r.text
    db = вход["Сессия"]()
    и = db.get(ContentIdea, r.json()["idea_id"])
    assert и.sort == "user" and и.state == "planned" and и.title == "Снять сравнение погоды"
    assert "подробности" in и.why
    assert db.query(ContentVideo).filter(ContentVideo.idea_id == и.id, ContentVideo.status == "plan").count() == 1
    db.close()
    # повторное нажатие не плодит идей
    assert к.post(f"/content/api/inbox/{a}", json={"action": "work"}).json()["idea_id"] == и.id
    assert к.post(f"/content/api/inbox/{b}", json={"action": "archive"}).status_code == 200
    db = вход["Сессия"]()
    assert db.get(ContentInbox, b).state == "archived"
    db.close()
    стр = к.get("/content").text
    assert 'data-inbox="%d"' % a not in стр and 'data-inbox="%d"' % b not in стр


def test_действия_только_админу(вход):
    к = вход["клиент"]
    a = _шлю(к, ПОСТ).json()["id"]
    assert к.post(f"/content/api/inbox/{a}", json={"action": "work"}).status_code == 403


def test_лимит_60_в_час(вход, monkeypatch):
    к = вход["клиент"]
    for n in range(cin.ЛИМИТ_В_ЧАС - 1):
        assert _шлю(к, {**ПОСТ, "tg_message_id": str(n)}).status_code == 200
    assert _шлю(к, ПОСТ, токен="wrong-token").status_code == 401   # неверный тоже считается
    r = _шлю(к, {**ПОСТ, "tg_message_id": "last"})
    assert r.status_code == 429 and "лимит" in r.json()["error"]


def test_подлог_лимита_нет_вход_открыт(вход, monkeypatch):
    monkeypatch.setattr(cin, "ЛИМИТ_В_ЧАС", 10 ** 6)
    к = вход["клиент"]
    for n in range(65):
        assert _шлю(к, {**ПОСТ, "tg_message_id": str(n)}).status_code == 200


def test_сегодня_карточки_слух_и_сюжет(вход):
    к = _админ(вход)
    assert 'id="today-inbox"' not in к.get("/content").text
    db = вход["Сессия"]()
    сюжет = db.query(ContentStory).first()
    запись = db.query(ContentItem).filter(ContentItem.story_id == сюжет.id).first()
    db.close()
    _шлю(к, {"kind": "forward", "text": "Пост из канала", "source_name": "Тест-канал", "tg_message_id": "1"})
    _шлю(к, {"kind": "link", "url": запись.url, "tg_message_id": "2"})
    _шлю(к, {"kind": "idea", "text": "Идея " + "очень длинная " * 30, "rumor": True, "tg_message_id": "3"})
    стр = к.get("/content").text
    assert стр.count('class="today-row today-inbox-row"') == 3
    assert стр.count("today-inbox-rumor") == 1 and "Тест-канал" in стр
    assert "уже в сюжете: " in стр and сюжет.title in стр
    assert "Показать полностью" in стр
