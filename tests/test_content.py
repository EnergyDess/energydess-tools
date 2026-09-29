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
    страница = к["админ"].get("/content?tab=sources").text
    assert 'data-source="%d" data-state="error"' % ps.id in страница
    assert "HTTP 404" in страница


def test_reddit_красный_с_причиной_и_в_сеть_не_ходит(стенд):
    db, _, сеть = стенд
    _цикл()
    db.expire_all()
    рд = db.query(ContentSource).filter(ContentSource.kind == "reddit").one()
    assert рд.last_state == "error" and "robots.txt" in рд.last_error
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
    страница = к["админ"].get("/content").text
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
    assert ce.оценка(ф, 5000, 3, 0)[0] == 100
    assert ce.оценка(ф, 0, 1, 3)[0] == 10
    assert ce.оценка(ф, 0, 0, 0)[0] == 25
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
    }
    # Описание канала — признак языка латиницы: заголовки испанского канала
    # от английских не отличить («(Funny Moments)»), описание — отличить.
    КАНАЛЫ = {
        "UCA": ("Funny Channel", "Funny moments and glitches from the best games, new videos every week."),
        "UCE": ("SquidLike", "Physics tests and experiments with your favourite games."),
        "UCR": ("Русский канал", "Угарные моменты из игр каждую неделю."),
        "UCS": ("Canal Divertido",
                "Hola a todos! Videos de juegos y momentos divertidos en el canal cada semana."),
    }
    ОПИСАНИЯ = {"d1": "Check out my GTA 5 playlist!"}

    def __init__(self, только_чужое=False):
        super().__init__()
        self.поиски = []
        self.только_чужое = только_чужое

    def yt(self, путь, q):
        if путь.endswith("/search") and q.get("publishedAfter"):
            self.поиски.append(q)
            if self.только_чужое:
                ids = ["x1", "m1"]
            elif q.get("channelId"):
                ids = [v for v, р in self.РОЛИКИ.items() if р[0] == q["channelId"]]
            elif q.get("relevanceLanguage") == "ru":
                ids = ["r1", "e1", "m1"]
            else:
                ids = ["g1", "m1", "e1", "s1"]
            return {"items": [{"id": {"videoId": v}} for v in ids]}
        if путь.endswith("/channels"):
            ids = [c for c in q.get("id", "").split(",") if c in self.КАНАЛЫ]
            if ids:
                return {"items": [{"id": c, "snippet": {"title": self.КАНАЛЫ[c][0],
                                                       "description": self.КАНАЛЫ[c][1]}}
                                  for c in ids]}
        if путь.endswith("/videos"):
            ids = [v for v in q.get("id", "").split(",") if v in self.РОЛИКИ]
            if ids:
                return {"items": [{"id": v, "snippet": {
                    "title": self.РОЛИКИ[v][2], "description": self.ОПИСАНИЯ.get(v, ""),
                    "channelId": self.РОЛИКИ[v][0],
                    "channelTitle": self.РОЛИКИ[v][1], "publishedAt": "2014-03-01T10:00:00Z"},
                    "statistics": {"viewCount": str(self.РОЛИКИ[v][3])}} for v in ids]}
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
    по_каналу = [п for п in сеть.поиски if п.get("channelId")]
    # Поиск по каналу идёт С ЗАПРОСОМ ТЕМЫ — без него топ канала периода всё подряд
    assert по_каналу and all(п.get("q") for п in по_каналу)
    db.expire_all()
    хиты = {в.yt_id: в for в in db.query(ContentArchVideo).all()}
    assert set(хиты) == {"g1", "g2", "e1", "r1"}, sorted(хиты)
    # «GTA5» слитно — тоже про тему (ключевое «GTA 5»), Goat Simulator и рэп — нет
    assert "x1" not in хиты and "m1" not in хиты
    # Язык по тексту, а не по подсказке запроса: e1 найден русским запросом
    assert хиты["e1"].channel_lang == "en" and хиты["r1"].channel_lang == "ru"
    assert all(в.format_id is not None for в in хиты.values())
    assert итог["версия"] == ce.АРХЕОЛОГИЯ_ВЕРСИЯ
    # Версия 3: тема только в ЗАГОЛОВКЕ. Описание d1 теме отвечает,
    # а ролик про Gmod — в таблицу он не идёт.
    assert cc.совпало(СетьАрх.ОПИСАНИЯ["d1"], cc.шаблон_ключевых(["GTA 5"]))
    assert "d1" not in хиты
    # Латиница — ещё не английский: у испанского канала самый большой хит,
    # но в англоязычные он не встаёт и назван в сводке.
    assert "s1" not in хиты and итог["gta"]["другой_язык"] == ["Canal Divertido"], итог["gta"]


def test_подлог_без_проверки_языка_испанский_канал_в_англоязычных(стенд, monkeypatch):
    """Обратный случай версии 3: проверка языка снята — испанский канал
    встаёт в англоязычные, как Fernanfloo на проде в версии 2 (семь хитов
    из первой десятки). Без этого «испанского нет» неотличимо от «его
    не присылали»: подставная сеть его присылает."""
    db, _, _ = стенд
    monkeypatch.setattr(cc, "латиница_не_английская", lambda текст: False)
    _археология(monkeypatch, СетьАрх())
    db.expire_all()
    хиты = {в.yt_id: в for в in db.query(ContentArchVideo).all()}
    assert "s1" in хиты and хиты["s1"].channel_lang == "en"


def test_латиница_не_английская_по_описанию():
    assert cc.латиница_не_английская(
        "Hola a todos! Videos de juegos y momentos divertidos en el canal cada semana.")
    assert cc.латиница_не_английская("Canal de rap sobre games. Inscreva-se para mais vídeos da série")
    # Ссылки не дают португальского «com», одно «Pokémon» решение не переворачивает
    assert not cc.латиница_не_английская(
        "Welcome to the channel! Pokémon and GTA videos every week. twitter.com/me www.site.com")
    # По одному заголовку испанский канал не отличить — поэтому решает описание
    assert not cc.латиница_не_английская("GTA V | Momentos Divertidos (Funny Moments)")


def test_подлог_без_отбора_по_теме_чужое_попадает(стенд, monkeypatch):
    """Обратный случай: отбор по теме снят (метки не переданы) — прежнее
    поведение, и чужая игра в таблице оказывается. Без этого «чужого нет»
    неотличимо от «чужого не присылали»: подставная сеть его присылает."""
    db, _, _ = стенд
    сеть = СетьАрх()
    настоящий = cc.хиты_периода

    async def прежний(client, база, ключ, квота, параметры, метки=None):
        return await настоящий(client, база, ключ, квота, параметры, None)
    monkeypatch.setattr(cc, "хиты_периода", прежний)
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
