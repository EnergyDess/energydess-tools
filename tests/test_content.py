"""Модуль «Контент» (BACKLOG №365, 366): сбор, хранение, сюжеты, доступ.

Сети нет: чужие сайты отвечают `httpx.MockTransport`, модель — подменённым
`content_engine._спросить` (путь кода дальше боевой). База своя, в памяти.

Вопросы — те, что задаёт письмо, у каждого подлог либо обратный случай:
1. ДОСТУП: гость и не-админ получают 403 на страницу и на действия;
   пункт меню «Контент» — только у администратора.
2. ПОВТОРНЫЙ ЦИКЛ не даёт дублей, а снимки счётчиков добавляются.
3. ИСТОЧНИК С НЕВЕРНЫМ АДРЕСОМ красный с текстом ошибки, соседи отработали.
4. «УБРАТЬ» — канал не опрашивается со следующего цикла.
5. КВОТА YouTube считается до вызова и не выходит за потолок из базы.
6. ТРИ ЗАПИСИ ОБ ОДНОМ СОБЫТИИ из разных источников — один сюжет,
   источников 3; другая тема — отдельный сюжет; утечка — флаг и заметка.
7. НАЛОЖЕНИЕ: запуск во время идущего прогона — пропуск СТРОКОЙ.
8. АРХЕОЛОГИЯ: в таблицу попадают только хиты ПРО ТЕМУ (замер на проде
   2026-09-29 — рэп и другие игры канала), язык канала — по тексту,
   а не по подсказке запроса; прогон пересобирает таблицу целиком,
   пустая выдача прежнего не стирает, прогон прежней версии правил
   повторяется сам один раз. Обратный случай — отбор снят, чужое
   попадает: иначе «чужого нет» неотличимо от «чужого не присылали».
"""
import asyncio
import json
import os
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit

os.environ.setdefault("DB_PATH", "./test_model_usage.db")
os.environ.setdefault("AGENT_WEBHOOK_KEY", "test-key-8f3a91")

import httpx  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import content_collect as cc  # noqa: E402
import content_db as cdb  # noqa: E402
import content_engine as ce  # noqa: E402
import database  # noqa: E402
import main  # noqa: E402
from auth import create_token, hash_password  # noqa: E402
from content_db import (ContentArchVideo, ContentChannel, ContentItem, ContentQuota,  # noqa: E402
                        ContentRun, ContentSetting, ContentSnapshot, ContentSource,
                        ContentStory)

PS_ЛЕНТА = "https://blog.playstation.com/feed/"
YT = "https://yt.test/youtube/v3"


def _iso(момент: datetime) -> str:
    return момент.replace(microsecond=0).isoformat() + "Z"


class Сеть:
    """Чужие сайты: Rockstar (GraphQL), PlayStation (RSS), YouTube Data API.
    Счётчики просмотров растут от вызова к вызову — снимки обязаны это видеть."""

    def __init__(self):
        self.запросы = []
        self.сейчас = datetime.utcnow()
        self.прирост = 0

    def rockstar(self):
        посты = [
            {"id": "a1", "url": "/newswire/article/a1", "title": "GTA Online: Bonus Week",
             "created": "9/24/26, 11:00 AM", "primary_tags": [{"name": "GTA Online"}],
             "secondary_tags": []},
            {"id": "a2", "url": "/newswire/article/a2", "title": "Red Dead Online: Moonshiners",
             "created": "9/23/26, 10:00 AM", "primary_tags": [{"name": "Red Dead Online"}],
             "secondary_tags": []},
        ]
        return {"data": {"meta": {"title": "Newswire"}, "posts": {"results": посты}}}

    def rss(self):
        когда = (self.сейчас - timedelta(hours=3)).strftime("%a, %d %b %Y %H:%M:%S +0000")
        return f"""<?xml version="1.0"?><rss version="2.0"><channel><title>PS Blog</title>
<item><title>Grand Theft Auto VI launch date confirmed</title><link>https://blog.playstation.com/gta6</link>
<guid>ps-1</guid><pubDate>{когда}</pubDate><description>&lt;p&gt;Rockstar confirms&lt;/p&gt;</description></item>
<item><title>Astro Bot update</title><link>https://blog.playstation.com/astro</link>
<guid>ps-2</guid><pubDate>{когда}</pubDate><description>nothing</description></item>
</channel></rss>"""

    def yt(self, путь: str, q: dict):
        if путь.endswith("/search"):
            return {"items": [{"id": {"channelId": "UC1"}}, {"id": {"channelId": "UC2"}},
                              {"id": {"channelId": "UC3"}}, {"id": {"channelId": "UC4"}}]}
        if путь.endswith("/channels"):
            данные = {
                "UC1": ("GTA Radar", 500000, "UU1"), "UC2": ("ГТА Новости", 80000, "UU2"),
                "UC3": ("Cooking Daily", 900000, "UU3"), "UC4": ("GTA Tiny", 500, "UU4")}
            return {"items": [{"id": c, "snippet": {"title": данные[c][0], "description": ""},
                               "statistics": {"subscriberCount": str(данные[c][1]),
                                              "videoCount": "100", "viewCount": "1000"},
                               "contentDetails": {"relatedPlaylists": {"uploads": данные[c][2]}}}
                              for c in q.get("id", "").split(",") if c in данные]}
        if путь.endswith("/playlistItems"):
            ролики = {"UU1": ["v1", "v2"], "UU2": ["v3"]}.get(q.get("playlistId"), [])
            return {"items": [{"contentDetails": {"videoId": v}} for v in ролики]}
        if путь.endswith("/videos"):
            канал = {"v1": "UC1", "v2": "UC1", "v3": "UC2"}
            имя = {"v1": "GTA 6 trailer breakdown", "v2": "GTA 5 funny moments",
                   "v3": "ГТА 6: дата выхода"}
            итог = []
            for v in q.get("id", "").split(","):
                if v not in канал:
                    continue
                итог.append({"id": v, "snippet": {
                    "title": имя[v], "description": "", "channelId": канал[v],
                    "channelTitle": канал[v], "publishedAt": _iso(self.сейчас - timedelta(hours=2))},
                    "statistics": {"viewCount": str(1000 + self.прирост), "likeCount": "10",
                                   "commentCount": "5"}})
            return {"items": итог}
        return None

    def __call__(self, запрос: httpx.Request) -> httpx.Response:
        адрес = str(запрос.url)
        self.запросы.append(адрес)
        части = urlsplit(адрес)
        if части.path == "/robots.txt":
            return httpx.Response(404, text="")
        if части.netloc == "graph.rockstargames.com":
            return httpx.Response(200, json=self.rockstar())
        if адрес.startswith(PS_ЛЕНТА):
            return httpx.Response(200, text=self.rss(),
                                  headers={"Content-Type": "application/rss+xml"})
        if адрес.startswith(YT):
            q = {к: v[0] for к, v in parse_qs(части.query).items()}
            тело = self.yt(части.path, q)
            if тело is not None:
                return httpx.Response(200, json=тело)
        return httpx.Response(404, text="not found")


@pytest.fixture
def стенд(monkeypatch):
    движок = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    database.Base.metadata.create_all(движок)
    Сессия = sessionmaker(bind=движок)
    db = Сессия()
    админ = database.User(email="adm@content.test", password_hash=hash_password("x-123456"),
                          is_verified=True, is_admin=True)
    простой = database.User(email="usr@content.test", password_hash=hash_password("x-123456"),
                            is_verified=True, is_admin=False)
    db.add_all([админ, простой])
    db.commit()
    cdb.засеять(db)
    # Источник YouTube — на подставной адрес API
    yt = db.query(ContentSource).filter(ContentSource.kind == "youtube").one()
    yt.url = YT
    db.commit()

    def _db():
        с = Сессия()
        try:
            yield с
        finally:
            с.close()

    main.app.dependency_overrides[main.get_db] = _db
    monkeypatch.setattr(main, "SessionLocal", Сессия)
    monkeypatch.setattr(ce, "SessionLocal", Сессия)
    сеть = Сеть()
    monkeypatch.setattr(cc, "новый_клиент", lambda: httpx.AsyncClient(
        transport=httpx.MockTransport(сеть), follow_redirects=True))
    cc._РОБОТС.clear()
    monkeypatch.setenv("CONTENT_YOUTUBE_API_KEY", "test-key")
    monkeypatch.setenv("CONTENT_SCHEDULER", "0")
    # Модель: по умолчанию каждая запись — шум (тестам сюжетов — своя)
    async def _шум(клиент, инструмент, система, вопрос, потолок):
        n = len(re.findall(r"^\d+\. \[", вопрос.split("Новые записи:")[-1], re.M))
        return json.dumps({"items": [{"n": i, "noise": True} for i in range(1, n + 1)],
                           "new": []}), None
    monkeypatch.setattr(ce, "_спросить", _шум)
    клиенты = {}
    for имя, u in (("админ", админ), ("простой", простой)):
        к = TestClient(main.app)
        к.cookies.set("access_token", create_token(u.id))
        клиенты[имя] = к
    клиенты["гость"] = TestClient(main.app)
    yield db, клиенты, сеть
    main.app.dependency_overrides.pop(main.get_db, None)
    db.close()


def _цикл():
    return asyncio.run(ce.цикл("test"))


# ── 1. ДОСТУП ─────────────────────────────────────────────────────────

def test_не_админу_403_на_страницу_и_действия(стенд):
    _, к, _ = стенд
    assert к["админ"].get("/content").status_code == 200
    for кто in ("простой", "гость"):
        assert к[кто].get("/content").status_code == 403, кто
        assert к[кто].get("/content/kitchen").status_code == 403, кто
        assert к[кто].get("/content/api/ideas/state").status_code == 403, кто
        assert к[кто].post("/content/api/ideas/run").status_code in (403, 428), кто
        assert к[кто].post("/content/api/ideas/1", json={"action": "plan"}).status_code in (403, 428), кто
        assert к[кто].post("/content/api/videos/1", json={"status": "plan"}).status_code in (403, 428), кто
        assert к[кто].get("/content/api/state").status_code == 403, кто
        assert к[кто].post("/content/api/run", json={"kind": "cycle"}).status_code in (403, 428), кто
        assert к[кто].post("/content/api/channels/1", json={"status": "removed"}).status_code in (403, 428), кто


def test_пункт_меню_только_админу(стенд):
    _, к, _ = стенд
    assert 'href="/content"' in к["админ"].get("/profile").text
    assert 'href="/content"' not in к["простой"].get("/profile").text


def test_подлог_снятая_проверка_прав_открывает(стенд, monkeypatch):
    """Обратный случай: без проверки прав не-админ видит страницу —
    значит 403 выше давала именно проверка, а не что-то другое."""
    import content_app
    _, к, _ = стенд
    monkeypatch.setattr(content_app, "_админ", lambda user: bool(user))
    assert к["простой"].get("/content").status_code == 200


# ── 2–3. ЦИКЛ: ДУБЛЕЙ НЕТ, СНИМКИ ЕСТЬ, СЛОМАННЫЙ ИСТОЧНИК КРАСНЫЙ ─────

def test_повторный_цикл_без_дублей_и_со_снимками(стенд):
    db, _, сеть = стенд
    итог = _цикл()
    assert итог["state"] in ("ok", "partial"), итог
    записей = db.query(ContentItem).count()
    снимков = db.query(ContentSnapshot).count()
    ключи = [r[0] for r in db.query(ContentItem.ext_id).all()]
    assert len(ключи) == len(set(ключи))
    # Rockstar: «Red Dead» без ключевых слов отфильтрован; PS: «Astro Bot» тоже
    assert db.query(ContentItem).filter(ContentItem.ext_id == "rockstar:a1").count() == 1
    assert db.query(ContentItem).filter(ContentItem.ext_id == "rockstar:a2").count() == 0
    assert db.query(ContentItem).filter(ContentItem.title.like("%Astro%")).count() == 0
    # YouTube: три ролика двух каналов реестра; «Cooking» (нет метки темы)
    # и «GTA Tiny» (мало подписчиков) в реестр не попали
    assert {к.yt_id for к in db.query(ContentChannel).all()} == {"UC1", "UC2"}
    assert db.query(ContentItem).filter(ContentItem.platform == "youtube").count() == 3
    assert снимков == 3
    сеть.прирост = 500
    # Снимки «час назад» — через объекты: вычитание интервала в SQL
    # SQLite делает числом, и дата превратилась бы в мусор
    for с in db.query(ContentSnapshot).all():
        с.taken_at -= timedelta(hours=1)
    db.commit()
    _цикл()
    db.expire_all()
    assert db.query(ContentItem).count() == записей, "повторный цикл завёл дубли"
    assert db.query(ContentSnapshot).count() == снимков + 3, "снимки не добавились"
    ролик = db.query(ContentItem).filter(ContentItem.ext_id == "yt:v1").one()
    assert ролик.metric == 1500 and ролик.growth and ролик.growth > 0


def test_неверный_адрес_красный_с_текстом_соседи_работают(стенд):
    db, к, _ = стенд
    ps = db.query(ContentSource).filter(ContentSource.name == "PlayStation Blog").one()
    ps.url = "https://blog.playstation.com/feed-wrong/"
    db.commit()
    итог = _цикл()
    assert итог["state"] == "partial"
    db.expire_all()
    ps = db.get(ContentSource, ps.id)
    assert ps.last_state == "error" and "HTTP 404" in (ps.last_error or "")
    rs = db.query(ContentSource).filter(ContentSource.kind == "rockstar").one()
    assert rs.last_state == "ok" and rs.last_ok_at is not None
    страница = к["админ"].get("/content/kitchen?tab=sources").text
    assert 'data-source="%d" data-state="error"' % ps.id in страница
    assert "HTTP 404" in страница


def test_reddit_без_ключа_выключен_и_в_сеть_не_ходит(стенд):
    """С №370: без ключа Reddit — «выключен, ждёт ключ» (серый), не ошибка;
    причина остаётся пометкой источника (`note`)."""
    db, _, сеть = стенд
    _цикл()
    db.expire_all()
    рд = db.query(ContentSource).filter(ContentSource.kind == "reddit").one()
    assert рд.last_state == "off" and not рд.last_error
    assert not any("reddit.com" in а for а in сеть.запросы)


# ── 4–5. «УБРАТЬ» И КВОТА ─────────────────────────────────────────────

def test_убранный_канал_не_опрашивается(стенд):
    db, к, сеть = стенд
    _цикл()
    uc2 = db.query(ContentChannel).filter(ContentChannel.yt_id == "UC2").one()
    r = к["админ"].post(f"/content/api/channels/{uc2.id}", json={"status": "removed"})
    assert r.status_code == 200 and r.json()["status"] == "removed"
    сеть.запросы.clear()
    _цикл()
    плейлисты = [а for а in сеть.запросы if "/playlistItems" in а]
    assert any("playlistId=UU1" in а for а in плейлисты)
    assert not any("playlistId=UU2" in а for а in плейлисты), "убранный канал опрошен"
    ролики = set()
    for а in сеть.запросы:
        if "/videos?" in а:
            ролики |= set(parse_qs(urlsplit(а).query).get("id", [""])[0].split(","))
    assert "v3" not in ролики, "ролики убранного канала снимаются"


def test_квота_списывается_до_вызова_и_не_выходит_за_потолок(стенд):
    db, _, сеть = стенд
    _цикл()
    строка = db.query(ContentQuota).one()
    # 5 запросов поиска по 100 + channels 1 + два плейлиста + videos 1
    assert строка.units == 504, строка.units
    детали = json.loads(строка.detail)
    assert детали["search"] == 500
    # Потолок из базы: осталось меньше цены поиска — поиск не делается
    db.query(ContentChannel).delete()
    db.query(ContentSetting).filter(ContentSetting.key == "youtube").update(
        {ContentSetting.value: json.dumps({**cdb.настройка(db, "youtube"), "daily_cap": 550})})
    db.commit()
    сеть.запросы.clear()
    _цикл()
    db.expire_all()
    assert db.query(ContentQuota).one().units <= 550
    yt = db.query(ContentSource).filter(ContentSource.kind == "youtube").one()
    assert yt.last_state == "quota" and "исчерпана" in yt.last_error


# ── 6. СЮЖЕТЫ ─────────────────────────────────────────────────────────

def _модель_по_заголовкам(правила):
    """Подменённая модель: решение по подстроке заголовка записи."""
    async def ответ(клиент, инструмент, система, вопрос, потолок):
        записи = re.findall(r"^(\d+)\. \[[^\]]*\] (.+)$", вопрос.split("Новые записи:")[-1], re.M)
        items, new = [], {}
        for n, заголовок in записи:
            for подстрока, решение in правила:
                if подстрока in заголовок:
                    э = {"n": int(n), **решение}
                    if "new" in э:
                        new[э["new"]] = {"key": э["new"], "title": "Сюжет " + э["new"],
                                         "summary": "про " + подстрока}
                    items.append(э)
                    break
            else:
                items.append({"n": int(n), "noise": True})
        return json.dumps({"items": items, "new": list(new.values())}), None
    return ответ


def _запись(db, n, заголовок, источник, площадка, **kw):
    сейчас = datetime.utcnow()
    db.add(ContentItem(theme_id="gta", ext_id=f"t:{n}", source_id=1, source_key=источник,
                       source_name=источник, platform=площадка, url=f"https://x.test/{n}",
                       title=заголовок, published_at=сейчас - timedelta(hours=n),
                       first_seen_at=сейчас, last_seen_at=сейчас, **kw))


def test_три_записи_одного_события_один_сюжет(стенд, monkeypatch):
    db, к, _ = стенд
    _запись(db, 1, "Rockstar: Trailer 3 is out", "rockstar:1", "rockstar", official=True)
    _запись(db, 2, "PS Blog: Trailer 3 on PS5", "rss:2", "playstation", official=True)
    _запись(db, 3, "GTA 6 Trailer 3 breakdown", "yt:UC1", "youtube", lang="ru", metric=100)
    _запись(db, 4, "Map leak shows Leonida", "yt:UC9", "youtube", lang="en", metric=50)
    _запись(db, 5, "funny meme", "yt:UC8", "youtube", lang="en", metric=10)
    db.commit()
    monkeypatch.setattr(ce, "_спросить", _модель_по_заголовкам([
        ("Trailer 3", {"new": "A"}), ("Map leak", {"new": "B", "leak": True})]))
    настройки = {к_: cdb.настройка(db, к_) for к_ in ("stories", "score_formula", "youtube")}
    итог = asyncio.run(ce._сюжеты({"id": "gta", "title": "GTA"}, настройки))
    ce._пересчитать_сюжеты("gta", настройки)
    assert итог["новых_сюжетов"] == 2 and итог["шум"] == 1, итог
    db.expire_all()
    сюжеты = {с.title: с for с in db.query(ContentStory).all()}
    а, б = сюжеты["Сюжет A"], сюжеты["Сюжет B"]
    assert а.items == 3 and а.sources == 3 and а.platforms == 3
    assert а.official and not а.leak and а.ru_videos == 1
    assert б.items == 1 and б.leak
    страница = к["админ"].get("/content/kitchen").text
    import content_app
    assert content_app.ЗАМЕТКА_УТЕЧКИ in страница
    assert f'data-story="{б.id}"' in страница and 'data-leak="true"' in страница


def test_сюжет_существующий_пополняется_по_номеру(стенд, monkeypatch):
    db, _, _ = стенд
    db.add(ContentStory(theme_id="gta", title="Трейлер 3", items=0,
                        last_item_at=datetime.utcnow()))
    _запись(db, 1, "Trailer 3 reaction", "yt:UC5", "youtube", metric=10)
    db.commit()
    monkeypatch.setattr(ce, "_спросить", _модель_по_заголовкам([("Trailer 3", {"story": 1})]))
    настройки = {к_: cdb.настройка(db, к_) for к_ in ("stories", "score_formula", "youtube")}
    asyncio.run(ce._сюжеты({"id": "gta", "title": "GTA"}, настройки))
    db.expire_all()
    assert db.query(ContentStory).count() == 1
    assert db.query(ContentItem).one().story_id == db.query(ContentStory).one().id


def test_номер_вне_списка_и_не_тот_ответ_не_ложатся():
    разбор, беда = ce._разобрать_сюжеты(json.dumps({"items": [
        {"n": 1, "story": 9}, {"n": 2, "new": "Z"}, {"n": 7, "noise": True},
        {"n": True, "noise": True}, {"n": 3, "noise": True}], "new": []}), 3, 2)
    assert беда is None
    assert set(разбор["решения"]) == {3}
    assert ce._разобрать_сюжеты("не json", 3, 2)[0] is None


def test_сбой_модели_не_сжигает_попытки(стенд, monkeypatch):
    db, _, _ = стенд
    _запись(db, 1, "GTA 6 news", "yt:UC1", "youtube")
    db.commit()

    async def отказ(*a):
        return None, "service: сервис моделей вернул ошибку (code=402)"
    monkeypatch.setattr(ce, "_спросить", отказ)
    настройки = {к_: cdb.настройка(db, к_) for к_ in ("stories", "score_formula", "youtube")}
    итог = asyncio.run(ce._сюжеты({"id": "gta", "title": "GTA"}, настройки))
    assert итог["беда"] and "402" in итог["беда"]
    db.expire_all()
    assert db.query(ContentItem).one().classify_tries == 0


def test_оценка_по_формуле_из_базы():
    ф = cdb.прочитать_семя()["settings"]["score_formula"]
    assert ce.оценка(ф, 5000, 3, 0, True, 0)[0] == 100
    assert ce.оценка(ф, 5000, 3, 0)[0] == 85             # без опережения — без его 15
    assert ce.оценка(ф, 0, 1, 3)[0] == 8
    assert ce.оценка(ф, 0, 0, 0)[0] == 20
    # Опережение тает с роликами: 2 ролика из насыщения 5 — 15 × 0.6 = 9
    assert ce.оценка(ф, 0, 0, 3, True, 2)[1]["опережение"] == 9.0
    # Формула до правки (весов опережения нет) считается как прежде
    assert "опережение" not in ce.оценка({"веса": {"рост": 45, "площадки": 30, "окно_ru": 25}},
                                          0, 0, 0, True, 0)[1]
    # Веса берутся из базы, а не из кода
    assert ce.оценка({**ф, "веса": {"рост": 0, "площадки": 0, "окно_ru": 50}}, 0, 0, 0)[0] == 50


# ── ФОРМАТЫ ───────────────────────────────────────────────────────────

def test_флаги_монетизации_только_из_трёх():
    разбор, беда = ce._разобрать_форматы(json.dumps({"videos": [
        {"n": 1, "format": 2, "flags": ["18+", "мат"], "why": "клуб"},
        {"n": 2, "new": "A", "flags": []}, {"n": 3, "format": 99}],
        "new": [{"key": "A", "title": "Реакции на трейлер"}]}), 3, 17)
    assert беда is None
    assert разбор["решения"][1][2] == ["18+"]
    assert разбор["решения"][2][0] == "новый" and 3 not in разбор["решения"]


# ── 7. НАЛОЖЕНИЕ ──────────────────────────────────────────────────────

def test_запуск_во_время_прогона_пропускается_строкой(стенд):
    db, _, _ = стенд

    async def два():
        async with ce._замок():
            return await ce.цикл("scheduler")
    итог = asyncio.run(два())
    assert итог["state"] == "skipped"
    db.expire_all()
    строка = db.query(ContentRun).order_by(ContentRun.id.desc()).first()
    assert строка.state == "skipped" and "пропущен" in строка.note


def test_ключ_youtube_только_свой(стенд, monkeypatch):
    """Прежний ключ проекта (`YOUTUBE_API_KEY`) модуль не берёт даже запасным."""
    monkeypatch.delenv("CONTENT_YOUTUBE_API_KEY", raising=False)
    monkeypatch.setenv("YOUTUBE_API_KEY", "old-key")
    assert ce.ключ_youtube() == ""
    db, _, сеть = стенд
    _цикл()
    db.expire_all()
    yt = db.query(ContentSource).filter(ContentSource.kind == "youtube").one()
    assert yt.last_state == "error" and "CONTENT_YOUTUBE_API_KEY" in yt.last_error
    assert not any(а.startswith(YT) for а in сеть.запросы)


# ── РАЗБОР ИСТОЧНИКОВ ─────────────────────────────────────────────────

def test_ключевые_слова_по_границе_слова():
    ш = cc.шаблон_ключевых(["GTA V", "GTA 6", "ГТА 6", "Vice City"])
    assert cc.совпало("New GTA V patch", ш)
    assert not cc.совпало("GTA VI", cc.шаблон_ключевых(["GTA V"]))
    assert cc.совпало("GTA VI trailer", cc.шаблон_ключевых(["GTA VI"]))
    assert cc.совпало("gta6 leak", ш) and cc.совпало("ГТА 6 утечка", ш)
    assert not cc.совпало("GTA 60 fps", cc.шаблон_ключевых(["GTA 6"]))


def test_время_rockstar_нью_йорк_в_utc():
    assert cc._rockstar_время("9/24/26, 11:00 AM") == datetime(2026, 9, 24, 15, 0)


def test_robots_запрет_и_403_стоп_с_причиной():
    async def прогон(обработчик, адрес):
        cc._РОБОТС.clear()
        async with httpx.AsyncClient(transport=httpx.MockTransport(обработчик)) as к:
            return await cc.собрать_rss(к, {"url": адрес, "name": "Лента", "params": {}})

    def запрет(р):
        if р.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /\n")
        return httpx.Response(200, text="<rss/>")
    with pytest.raises(cc.ОтказИсточника) as e:
        asyncio.run(прогон(запрет, "https://feed.test/feed/"))
    assert e.value.блок and "robots.txt" in str(e.value)

    def отказ(р):
        if р.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(429, text="slow down")
    with pytest.raises(cc.ОтказИсточника) as e:
        asyncio.run(прогон(отказ, "https://feed.test/feed/"))
    assert e.value.блок and "429" in str(e.value)


# ── 8. АРХЕОЛОГИЯ: ТОЛЬКО ПРО ТЕМУ, ЯЗЫК ПО ТЕКСТУ, ПЕРЕСБОРКА ─────────

class СетьАрх(Сеть):
    """YouTube для археологии. В выдаче нарочно то, что нашлось на проде
    2026-09-29 в первой версии: у канала рядом с GTA V — ролик про другую
    игру, самый просматриваемый «хит» периода — рэп про Minecraft,
    а англоязычный канал найден русским запросом."""

    РОЛИКИ = {
        # id: (канал, название канала, заголовок, просмотры)
        "g1": ("UCA", "Funny Channel", "GTA V | Momentos Divertidos (Funny Moments)", 9000000),
        "g2": ("UCA", "Funny Channel", "GTA5 heist glitch", 5000000),
        "x1": ("UCA", "Funny Channel", "Goat Simulator - LA JIRAFA VOLADORA", 8000000),
        "r1": ("UCR", "Русский канал", "ГТА 5: угарные моменты", 3000000),
        "e1": ("UCE", "SquidLike", "GTA 5 physics test", 4000000),
        "m1": ("UCM", "Rap Channel", "Rap do Minecraft", 70000000),
        # Версия 3, замер версии 2 на проде: испанский канал с самым большим
        # хитом (Fernanfloo) и ролик про другую игру, у которого GTA только
        # в описании (Gmod у VanossGaming).
        "s1": ("UCS", "Canal Divertido", "GTA V | Momentos Divertidos #3 (Funny Moments)", 12000000),
        "d1": ("UCA", "Funny Channel", "Gmod: Halloween Training", 7000000),
        # Версия 4, замер версии 3: португальский канал с описанием в одну
        # фразу (Tauz) — признаков языка в тексте нет, решает страна.
        "t1": ("UCT", "Rap Canal", "Rap do GTA 5 | RapGame 05", 11000000),
    }
    # Описание канала — признак языка латиницы: заголовки испанского канала
    # от английских не отличить («(Funny Moments)»), описание — отличить.
    КАНАЛЫ = {
        "UCA": ("Funny Channel", "Funny moments and glitches from the best games, new videos every week."),
        "UCE": ("SquidLike", "Physics tests and experiments with your favourite games."),
        "UCR": ("Русский канал", "Угарные моменты из игр каждую неделю."),
        "UCS": ("Canal Divertido",
                "Hola a todos! Videos de juegos y momentos divertidos en el canal cada semana."),
        "UCT": ("Rap Canal", "Canal do Tauz!", "BR"),
    }
    ОПИСАНИЯ = {"d1": "Check out my GTA 5 playlist!"}

    def __init__(self, только_чужое=False):
        super().__init__()
        self.поиски = []
        self.плейлисты = []
        self.только_чужое = только_чужое

    # Соседи для медианы канала (версия 5): у каждого канала шесть роликов
    # НЕ про тему по миллиону просмотров за две недели до хитов. Тогда у g1
    # (9 млн) соседи g2 5 млн, x1 8 млн, d1 7 млн и шесть по 1 млн —
    # медиана 1 млн, выстрел ×9.0: число известно заранее.
    СОСЕДЕЙ = 6

    def _все(self):
        ролики = {v: (р[0], р[1], р[2], р[3], "2014-03-01T10:00:00Z")
                  for v, р in self.РОЛИКИ.items()}
        for cid, к in self.КАНАЛЫ.items():
            for i in range(self.СОСЕДЕЙ):
                ролики[f"f{cid}{i}"] = (cid, к[0], f"Minecraft let's play #{i}", 1000000,
                                        "2014-02-15T10:00:00Z")
        return ролики

    def yt(self, путь, q):
        if путь.endswith("/playlistItems"):
            self.плейлисты.append(q.get("playlistId"))
            cid = "UC" + (q.get("playlistId") or "")[2:]
            return {"items": [{"contentDetails": {"videoId": v, "videoPublishedAt": р[4]}}
                              for v, р in self._все().items() if р[0] == cid]}
        if путь.endswith("/search") and q.get("publishedAfter"):
            self.поиски.append(q)
            if self.только_чужое:
                ids = ["x1", "m1"]
            elif q.get("channelId"):
                ids = [v for v, р in self.РОЛИКИ.items() if р[0] == q["channelId"]]
            elif q.get("relevanceLanguage") == "ru":
                ids = ["r1", "e1", "m1"]
            else:
                ids = ["g1", "m1", "e1", "s1", "t1"]
            return {"items": [{"id": {"videoId": v}} for v in ids]}
        if путь.endswith("/channels"):
            ids = [c for c in q.get("id", "").split(",") if c in self.КАНАЛЫ]
            if ids:
                return {"items": [{"id": c, "snippet": {
                    "title": self.КАНАЛЫ[c][0], "description": self.КАНАЛЫ[c][1],
                    "country": (self.КАНАЛЫ[c][2:] or (None,))[0]},
                    "statistics": {"videoCount": str(len(self.РОЛИКИ) + self.СОСЕДЕЙ)},
                    "contentDetails": {"relatedPlaylists": {"uploads": "UU" + c[2:]}}}
                    for c in ids]}
        if путь.endswith("/videos"):
            все = self._все()
            ids = [v for v in q.get("id", "").split(",") if v in все]
            if ids:
                return {"items": [{"id": v, "snippet": {
                    "title": все[v][2], "description": self.ОПИСАНИЯ.get(v, ""),
                    "channelId": все[v][0],
                    "channelTitle": все[v][1], "publishedAt": все[v][4]},
                    "statistics": {"viewCount": str(все[v][3])}} for v in ids]}
        return super().yt(путь, q)


def _археология(monkeypatch, сеть):
    """Прогон археологии на подставной сети; модель кладёт каждый ролик
    в первый стартовый формат — путь кода дальше боевой."""
    monkeypatch.setattr(cc, "новый_клиент", lambda: httpx.AsyncClient(
        transport=httpx.MockTransport(сеть), follow_redirects=True))

    async def _форматы(клиент, инструмент, система, вопрос, потолок):
        n = len(re.findall(r"^\d+\. \[", вопрос.split("Ролики:")[-1], re.M))
        return json.dumps({"videos": [{"n": i, "format": 1, "flags": [], "why": "тест"}
                                      for i in range(1, n + 1)], "new": []}), None
    monkeypatch.setattr(ce, "_спросить", _форматы)
    return asyncio.run(ce.археология("test"))


def test_археология_только_про_тему_и_язык_по_тексту(стенд, monkeypatch):
    db, _, _ = стенд
    сеть = СетьАрх()
    итог = _археология(monkeypatch, сеть)
    assert итог["state"] == "ok", итог
    # Версия 5: ролики канала — через плейлист загрузок, ПОИСКА ПО КАНАЛУ НЕТ
    # (он стоил 100 ед. на канал); поиск только по запросам темы.
    assert not [п for п in сеть.поиски if п.get("channelId")]
    assert len(сеть.поиски) == len(ce.cdb.прочитать_семя()["темы"][0]["params"]["archaeology"]["queries"])
    assert set(сеть.плейлисты) == {"UUA", "UUE", "UUR"}
    db.expire_all()
    хиты = {в.yt_id: в for в in db.query(ContentArchVideo).all()}
    assert set(хиты) == {"g1", "g2", "e1", "r1"}, sorted(хиты)
    # «GTA5» слитно — тоже про тему (ключевое «GTA 5»), Goat Simulator и рэп — нет
    assert "x1" not in хиты and "m1" not in хиты
    # Язык по тексту, а не по подсказке запроса: e1 найден русским запросом
    assert хиты["e1"].channel_lang == "en" and хиты["r1"].channel_lang == "ru"
    assert all(в.format_id is not None for в in хиты.values())
    assert итог["версия"] == ce.АРХЕОЛОГИЯ_ВЕРСИЯ == 5
    # Выстрел на известных числах подставной сети: у g1 медиана 1 млн по 9 соседям
    assert (хиты["g1"].shot, хиты["g1"].channel_median, хиты["g1"].median_base) == (9.0, 1000000, 9)
    assert хиты["r1"].shot == 3.0 and хиты["e1"].shot == 4.0
    # Версия 3: тема только в ЗАГОЛОВКЕ. Описание d1 теме отвечает,
    # а ролик про Gmod — в таблицу он не идёт.
    assert cc.совпало(СетьАрх.ОПИСАНИЯ["d1"], cc.шаблон_ключевых(["GTA 5"]))
    assert "d1" not in хиты
    # Латиница — ещё не английский: у испанского канала самый большой хит,
    # но в англоязычные он не встаёт и назван в сводке.
    assert "s1" not in хиты and итог["gta"]["другой_язык"][0] == "Canal Divertido", итог["gta"]
    # Версия 4: описание в одну фразу признаков не даёт — решает страна (BR)
    assert "t1" not in хиты and итог["gta"]["другой_язык"] == ["Canal Divertido", "Rap Canal"]


def test_подлог_без_проверки_языка_испанский_канал_в_англоязычных(стенд, monkeypatch):
    """Обратный случай версии 3: проверка языка снята — испанский канал
    встаёт в англоязычные, как Fernanfloo на проде в версии 2 (семь хитов
    из первой десятки). Без этого «испанского нет» неотличимо от «его
    не присылали»: подставная сеть его присылает."""
    db, _, _ = стенд
    monkeypatch.setattr(cc, "латиница_не_английская", lambda *а, **к: False)
    _археология(monkeypatch, СетьАрх())
    db.expire_all()
    хиты = {в.yt_id: в for в in db.query(ContentArchVideo).all()}
    assert "s1" in хиты and хиты["s1"].channel_lang == "en"
    assert "t1" in хиты and хиты["t1"].channel_lang == "en"


def test_латиница_не_английская_по_описанию():
    assert cc.латиница_не_английская(
        "Hola a todos! Videos de juegos y momentos divertidos en el canal cada semana.")
    assert cc.латиница_не_английская("Canal de rap sobre games. Inscreva-se para mais vídeos da série")
    # Ссылки не дают португальского «com», одно «Pokémon» решение не переворачивает
    assert not cc.латиница_не_английская(
        "Welcome to the channel! Pokémon and GTA videos every week. twitter.com/me www.site.com")
    # По одному заголовку испанский канал не отличить — поэтому решает описание
    assert not cc.латиница_не_английская("GTA V | Momentos Divertidos (Funny Moments)")
    # Версия 4: признаков в тексте нет — решает страна, и только без английских слов
    tauz = "Tauz Canal do Tauz! Rap do GTA 5 | Tauz RapGame 05 Rap do GTA 5 (História)"
    assert cc.латиница_не_английская(tauz, "BR")
    assert not cc.латиница_не_английская(tauz, "US") and not cc.латиница_не_английская(tauz)
    assert not cc.латиница_не_английская("GTA 5 - How to Make Money in the Heists", "BR")


def test_подлог_без_отбора_по_теме_чужое_попадает(стенд, monkeypatch):
    """Обратный случай: отбор по теме снят (метки не переданы) — прежнее
    поведение, и чужая игра в таблице оказывается. Без этого «чужого нет»
    неотличимо от «чужого не присылали»: подставная сеть его присылает."""
    db, _, _ = стенд
    сеть = СетьАрх()
    настоящий = cc.хиты_выстрела

    async def прежний(client, база, ключ, квота, параметры, метки=None):
        return await настоящий(client, база, ключ, квота, параметры, None)
    monkeypatch.setattr(cc, "хиты_выстрела", прежний)
    _археология(monkeypatch, сеть)
    db.expire_all()
    assert "x1" in {в.yt_id for в in db.query(ContentArchVideo).all()}


def test_повторная_археология_пересобирает_таблицу(стенд, monkeypatch):
    db, _, _ = стенд
    чужой = cdb.ContentFormat(theme_id="gta", title="Кинематики других игр", origin="model",
                              sort=1000)
    db.add(чужой)
    db.flush()
    db.add_all([
        ContentArchVideo(theme_id="gta", yt_id="old-x", title="Five Nights At Freddy's",
                         format_id=чужой.id, classify_tries=0),
        ContentArchVideo(theme_id="gta", yt_id="g1", title="GTA V | Momentos Divertidos",
                         format_id=чужой.id, classify_tries=2, limited_ads=True,
                         flags='["18+"]', format_reason="старая причина")])
    db.commit()
    итог = _археология(monkeypatch, СетьАрх())
    assert итог["gta"]["убрано_хитов"] == 1 and итог["gta"]["убрано_форматов_модели"] == 1
    db.expire_all()
    assert db.query(ContentArchVideo).filter_by(yt_id="old-x").first() is None
    assert db.query(cdb.ContentFormat).filter_by(title="Кинематики других игр").first() is None
    g1 = db.query(ContentArchVideo).filter_by(yt_id="g1").one()
    первый = (db.query(cdb.ContentFormat).filter_by(theme_id="gta", origin="start")
              .order_by(cdb.ContentFormat.sort, cdb.ContentFormat.id).first())
    assert g1.format_id == первый.id and g1.limited_ads is False and g1.format_reason == "тест"


def test_пустая_выдача_не_стирает_прежнюю_таблицу(стенд, monkeypatch):
    db, _, _ = стенд
    db.add(ContentArchVideo(theme_id="gta", yt_id="keep", title="GTA 5 story",
                            classify_tries=0))
    db.commit()
    итог = _археология(monkeypatch, СетьАрх(только_чужое=True))
    assert итог["state"] == "partial" and "не тронута" in итог["note"]
    db.expire_all()
    assert db.query(ContentArchVideo).filter_by(yt_id="keep").one()


def test_археология_прежней_версии_пересобирается_сама(стенд):
    db, _, _ = стенд
    assert ce._археология_нужна()          # удачного прогона ещё не было
    сейчас = datetime.utcnow()
    db.add(ContentRun(kind="archaeology", trigger="scheduler", state="ok",
                      started_at=сейчас, finished_at=сейчас, summary="{}"))
    db.commit()
    assert ce._археология_нужна()          # прогон прежней версии — нужна
    db.add(ContentRun(kind="archaeology", trigger="scheduler", state="ok",
                      started_at=сейчас, finished_at=сейчас,
                      summary=json.dumps({"версия": ce.АРХЕОЛОГИЯ_ВЕРСИЯ})))
    db.commit()
    assert not ce._археология_нужна()      # текущая версия уже была


def test_автозапуск_оставляет_резерв_циклам_до_сброса(стенд, monkeypatch):
    """Квоты на сам прогон хватает, а циклам до сброса суток Google после
    него — нет: автозапуск ждёт. Замер на проде 2026-09-29: к 15:00 UTC
    израсходовано 6465 из 9000, прогон новой версии в 16:00 оставил бы сбор
    YouTube без квоты на всю ночь. Обратный случай — сброс через минуту."""
    db, _, _ = стенд
    db.query(ContentSetting).filter(ContentSetting.key == "youtube").update(
        {ContentSetting.value: json.dumps({**cdb.настройка(db, "youtube"), "daily_cap": 3000})})
    db.commit()
    assert cdb.квота_израсходовано(db) == 0
    сейчас = datetime.utcnow()
    monkeypatch.setattr(cdb, "сброс_квоты_utc", lambda момент=None: сейчас + timedelta(hours=10))
    цена = ce.цена_археологии(db)        # прогноз версии 5 по параметрам из базы
    assert цена == 8 * 100 + 1800 + 200
    assert not ce._археология_нужна()      # 3000 − 20 циклов × 70 = 1600 < 2800
    monkeypatch.setattr(cdb, "сброс_квоты_utc", lambda момент=None: сейчас + timedelta(minutes=1))
    assert ce._археология_нужна()          # 3000 − 1 цикл × 70 ≥ 2800


# ── 9. ПЕРВОИСТОЧНИКИ (BACKLOG №367), ВЫСТРЕЛ (№368), REDDIT OAUTH (№369) ──

IGN = "https://feeds.feedburner.com/ign/all"
STOPGAME = "https://rss.stopgame.ru/rss_news.xml"


def _лента(элементы, метка="m") -> str:
    когда = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S +0000")
    части = "".join(
        f"<item><title>{з}</title><link>https://{метка}.test/{i}</link><guid>{метка}-{i}</guid>"
        f"<pubDate>{когда}</pubDate><description>{о}</description>"
        + "".join(f"<category>{к}</category>" for к in р) + "</item>"
        for i, (з, о, р) in enumerate(элементы))
    return f'<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>{части}</channel></rss>'


class СетьСМИ(Сеть):
    """Ленты СМИ. В IGN нарочно лежит то, что общие слова темы пропустили бы:
    отчёт Take-Two про другую игру, новость Rockstar про Red Dead и подборка,
    где GTA упомянута только в анонсе."""
    ЛЕНТЫ = {
        IGN: [("GTA 6 trailer 3 release date leaked", "Rockstar", ["GTA 6"]),
              ("Take-Two earnings: Borderlands 4 sells 5 million", "GTA 6 still on track", []),
              ("Rockstar announces Red Dead Online update", "no", ["Red Dead"]),
              ("The 10 best open world games", "from Skyrim to GTA 5 and beyond", [])],
        STOPGAME: [("ГТА 6: утечка карты Леониды", "подробности", []),
                   ("Обзор Assassin's Creed", "не про ГТА", [])],
    }

    def __call__(self, запрос):
        адрес = str(запрос.url)
        for лента, элементы in self.ЛЕНТЫ.items():
            if адрес.startswith(лента):
                self.запросы.append(адрес)
                return httpx.Response(200, text=_лента(элементы, urlsplit(лента).netloc),
                                      headers={"Content-Type": "application/rss+xml"})
        return super().__call__(запрос)


def test_сми_строгий_фильтр_только_gta_в_заголовке(стенд, monkeypatch):
    db, _, _ = стенд
    сеть = СетьСМИ()
    monkeypatch.setattr(cc, "новый_клиент", lambda: httpx.AsyncClient(
        transport=httpx.MockTransport(сеть), follow_redirects=True))
    итог = _цикл()
    assert итог["state"] in ("ok", "partial"), итог
    ign = db.query(ContentSource).filter(ContentSource.name == "IGN").one()
    sg = db.query(ContentSource).filter(ContentSource.name == "StopGame").one()
    db.refresh(ign), db.refresh(sg)
    assert ign.last_state == "ok" and ign.last_seen == 4 and sg.last_state == "ok"
    заголовки = {и.title for и in db.query(ContentItem).filter(
        ContentItem.source_id.in_([ign.id, sg.id]))}
    # Про GTA — прошло; Take-Two, Red Dead и подборка с GTA в анонсе — нет
    assert заголовки == {"GTA 6 trailer 3 release date leaked", "ГТА 6: утечка карты Леониды"}
    записи = db.query(ContentItem).filter(ContentItem.source_id == ign.id).all()
    assert записи[0].platform == "ign" and записи[0].published_at is not None


def test_подлог_общий_фильтр_для_сми_пропускает_чужое(стенд, monkeypatch):
    """Обратный случай: строгость снята — общие слова темы («Take-Two»,
    «Rockstar») пропускают новости не про GTA. Без него «чужого нет»
    неотличимо от «чужого не присылали»."""
    db, _, _ = стенд
    for и in db.query(ContentSource).filter(ContentSource.kind == "rss").all():
        п = json.loads(и.params or "{}")
        п.pop("strict", None)
        и.params = json.dumps(п)
    db.commit()
    сеть = СетьСМИ()
    monkeypatch.setattr(cc, "новый_клиент", lambda: httpx.AsyncClient(
        transport=httpx.MockTransport(сеть), follow_redirects=True))
    _цикл()
    заголовки = {и.title for и in db.query(ContentItem).all()}
    assert "Take-Two earnings: Borderlands 4 sells 5 million" in заголовки


def _сюжет_из(db, monkeypatch, записи):
    for n, заголовок, ист, пл, kw in записи:
        _запись(db, n, заголовок, ист, пл, **kw)
    db.commit()
    monkeypatch.setattr(ce, "_спросить", _модель_по_заголовкам([("Trailer 3", {"new": "A"})]))
    настройки = {к_: cdb.настройка(db, к_) for к_ in ("stories", "score_formula", "youtube")}
    asyncio.run(ce._сюжеты({"id": "gta", "title": "GTA"}, настройки))
    ce._пересчитать_сюжеты("gta", настройки)
    db.expire_all()
    return db.query(ContentStory).filter(ContentStory.title == "Сюжет A").one()


def test_опережение_сми_раньше_youtube_и_счётчики_на_карточке(стенд, monkeypatch):
    db, к, _ = стенд
    с = _сюжет_из(db, monkeypatch, [
        (6, "IGN: Trailer 3 is coming", "rss:9", "ign", {}),
        (3, "GTA 6 Trailer 3 reaction", "yt:UC1", "youtube", {"lang": "en", "metric": 10}),
        (2, "ГТА 6 Trailer 3 разбор", "yt:UC2", "youtube", {"lang": "ru", "metric": 10}),
        (1, "Trailer 3 again", "yt:UC3", "youtube", {"lang": "en", "metric": 10})])
    assert с.lead and с.first_source == "rss:9" and с.first_platform == "ign"
    assert (с.en_videos, с.ru_videos) == (2, 1)
    части = json.loads(с.score_parts)
    assert части["опережение"] == round(15 * (1 - 3 / 5), 1)
    страница = к["админ"].get("/content/kitchen").text
    assert 'data-lead="true"' in страница and "Опережение: новость вышла в" in страница
    assert 'content-lead-en">2<' in страница and 'content-lead-ru">1<' in страница


def test_без_опережения_если_первым_был_youtube(стенд, monkeypatch):
    db, к, _ = стенд
    с = _сюжет_из(db, monkeypatch, [
        (6, "GTA 6 Trailer 3 early video", "yt:UC1", "youtube", {"lang": "en", "metric": 10}),
        (3, "IGN: Trailer 3 is coming", "rss:9", "ign", {})])
    assert not с.lead and "опережение" in json.loads(с.score_parts)
    assert json.loads(с.score_parts)["опережение"] == 0
    assert 'data-lead="true"' not in к["админ"].get("/content/kitchen").text


def test_выстрел_на_известных_числах():
    t0 = datetime(2014, 3, 1)
    соседи = [{"yt_id": f"n{i}", "views": v, "published_at": t0 + timedelta(days=d)}
              for i, (v, d) in enumerate([(100, -80), (200, -10), (300, 5), (400, 30),
                                          (500, 89), (9999999, 120), (7, -200)])]
    ролик = {"yt_id": "hit", "views": 3000, "published_at": t0}
    # в окне ±90: 100, 200, 300, 400, 500 — медиана 300, выстрел 10.0
    assert cc.выстрел(ролик, соседи + [ролик], 90, 5) == (10.0, 300, 5)
    assert cc.медиана([1, 2, 3, 4]) == 2.5 and cc.медиана([]) is None


def test_без_медианы_канала_ролик_не_ранжируется(стенд):
    db, к, _ = стенд
    t0 = datetime(2014, 3, 1)
    мало = [{"yt_id": "a", "views": 10, "published_at": t0},
            {"yt_id": "b", "views": 20, "published_at": t0}]
    assert cc.выстрел({"yt_id": "h", "views": 10**6, "published_at": t0}, мало, 90, 5) == (None, None, 2)
    db.add_all([ContentArchVideo(theme_id="gta", yt_id="ranked", title="GTA 5 heist",
                                 views=500000, shot=4.0, channel_median=125000,
                                 median_base=9, channel_lang="en", classify_tries=0),
                ContentArchVideo(theme_id="gta", yt_id="lonely", title="GTA 5 lonely hit",
                                 views=9000000, shot=None, channel_lang="en", classify_tries=0)])
    db.commit()
    import content_app
    ф = content_app._форматы(db, "gta", content_app.ZoneInfo("Europe/Moscow"))
    assert [с["url"][-6:] for с in ф["en"]] == ["ranked"] and ф["без_медианы"] == 1
    страница = к["админ"].get("/content/kitchen?tab=formats").text
    assert "lonely hit" not in страница and "×4.0" in страница


def test_прогон_археологии_не_берёт_резерв_циклов(стенд, monkeypatch):
    """Ручной прогон упирается в потолок «суточный − потрачено − резерв
    циклам до сброса», а не съедает квоту сбора: при резерве больше
    остатка он встаёт на первом же вызове с пометкой квоты."""
    db, _, _ = стенд
    db.query(ContentSetting).filter(ContentSetting.key == "youtube").update(
        {ContentSetting.value: json.dumps({**cdb.настройка(db, "youtube"), "daily_cap": 1450})})
    db.commit()
    сейчас = datetime.utcnow()
    monkeypatch.setattr(cdb, "сброс_квоты_utc", lambda момент=None: сейчас + timedelta(hours=10))
    итог = _археология(monkeypatch, СетьАрх())
    assert итог["state"] == "error" and "квота" in (итог["note"] or ""), итог
    assert cdb.квота_израсходовано(db) == 0          # 1450 − 20 × 70 = 50 < 100 за поиск


def test_формат_катсцен_с_пометкой_content_id(стенд):
    db, к, _ = стенд
    ф = db.query(cdb.ContentFormat).filter(
        cdb.ContentFormat.title == "Весь сюжет одним фильмом (катсцены)").one()
    assert ф.note == "проверить музыку на Content ID"
    # С №370 строки без данных археологии в рейтинге скрыты: без хитов
    # формата нет и пометки, с хитом — строка и пометка на месте.
    assert "проверить музыку на Content ID" not in к["админ"].get("/content/kitchen?tab=formats").text
    db.add(ContentArchVideo(theme_id=ф.theme_id, yt_id="cut1", title="GTA 5 all cutscenes",
                            channel_lang="en", views=200000, shot=3.0, format_id=ф.id))
    db.commit()
    assert "проверить музыку на Content ID" in к["админ"].get("/content/kitchen?tab=formats").text


def test_досев_доводит_заведённую_тему_до_семени(стенд):
    """Прод заведён до правки: источников СМИ нет, формула без опережения,
    археология версии 4. Досев добавляет недостающее, чужого не трогает."""
    db, _, _ = стенд
    db.query(ContentSource).filter(ContentSource.name.in_(["IGN", "StopGame"])).delete(
        synchronize_session=False)
    тема = db.query(cdb.ContentTheme).filter_by(id="gta").one()
    п = json.loads(тема.params)
    п["archaeology"] = {"from": "2013-09-17", "to": "2014-12-31", "queries": [], "v": 4}
    п.pop("strict_keywords")
    тема.params = json.dumps(п)
    запись = db.query(ContentSetting).filter_by(key="score_formula").one()
    ф = json.loads(запись.value)
    ф["веса"] = {"рост": 45, "площадки": 30, "окно_ru": 25}
    запись.value = json.dumps(ф)
    db.query(cdb.ContentFormat).filter(cdb.ContentFormat.title.like("Весь сюжет%")).delete(
        synchronize_session=False)
    db.commit()
    assert cdb.засеять(db) == {"тем": 0, "источников": 0, "форматов": 0, "настроек": 0}
    db.expire_all()
    assert db.query(ContentSource).filter(ContentSource.name.in_(["IGN", "StopGame"])).count() == 2
    п = json.loads(db.query(cdb.ContentTheme).filter_by(id="gta").one().params)
    assert п["archaeology"]["v"] == 5 and "GTA" in п["strict_keywords"]
    assert json.loads(db.query(ContentSetting).filter_by(key="score_formula").one().value
                      )["веса"]["опережение"] == 15
    assert db.query(cdb.ContentFormat).filter(cdb.ContentFormat.note.isnot(None)).count() == 1
    assert cdb.догнать_семя(db, cdb.прочитать_семя()) == 0       # второй раз — нечего


class СетьReddit(Сеть):
    def __init__(self, токен_код=200):
        super().__init__()
        self.токен_код = токен_код
        self.заголовки = []

    def __call__(self, запрос):
        адрес = str(запрос.url)
        if адрес.startswith("https://www.reddit.com/api/v1/access_token"):
            self.запросы.append(адрес)
            if self.токен_код != 200:
                return httpx.Response(self.токен_код, json={"error": "invalid_grant"})
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        if адрес.startswith("https://oauth.reddit.com/r/"):
            self.запросы.append(адрес)
            self.заголовки.append(dict(запрос.headers))
            return httpx.Response(200, json={"data": {"children": [
                {"data": {"id": "p1", "title": "GTA 6 map theory", "permalink": "/r/GTA6/p1",
                          "created_utc": 1790000000, "score": 120, "num_comments": 30}},
                {"data": {"id": "p2", "title": "My cat", "permalink": "/r/GTA6/p2",
                          "created_utc": 1790000000, "score": 5, "num_comments": 1}}]}})
        return super().__call__(запрос)


def _reddit(monkeypatch, сеть):
    cc._REDDIT_ТОКЕН.clear()

    async def прогон():
        async with httpx.AsyncClient(transport=httpx.MockTransport(сеть)) as client:
            return await cc.собрать_reddit(client, {"name": "Reddit", "params": {"subs": ["GTA6"]}})
    return asyncio.run(прогон())


def test_reddit_oauth_с_ключами_собирает_без_ключей_в_сеть_не_ходит(monkeypatch):
    monkeypatch.delenv("REDDIT_CLIENT_ID", raising=False)
    monkeypatch.delenv("REDDIT_CLIENT_SECRET", raising=False)
    сеть = СетьReddit()
    with pytest.raises(cc.ОтказИсточника):
        _reddit(monkeypatch, сеть)
    assert сеть.запросы == []
    monkeypatch.setenv("REDDIT_CLIENT_ID", "id")
    monkeypatch.setenv("REDDIT_CLIENT_SECRET", "sec")
    записи = _reddit(monkeypatch, сеть)
    assert [з["ext_id"] for з in записи] == ["reddit:p1", "reddit:p2"]
    assert записи[0]["metric"] == 120 and записи[0]["source_key"] == "reddit:GTA6"
    assert сеть.заголовки[0]["authorization"] == "Bearer tok"
    assert сеть.заголовки[0]["user-agent"].startswith("web:energydess-content-radar")
    # сайт reddit.com (robots.txt запрещает всё) не трогаем — только API
    assert not any("reddit.com/r/" in а and "oauth" not in а for а in сеть.запросы)


def test_reddit_токен_отклонён_красный_с_причиной(monkeypatch):
    monkeypatch.setenv("REDDIT_CLIENT_ID", "id")
    monkeypatch.setenv("REDDIT_CLIENT_SECRET", "sec")
    with pytest.raises(cc.ОтказИсточника) as e:
        _reddit(monkeypatch, СетьReddit(токен_код=401))
    assert "HTTP 401" in str(e.value) and "одобрение" in str(e.value)
