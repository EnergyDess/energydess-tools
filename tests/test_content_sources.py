"""Модуль «Контент», A3 (BACKLOG №374): Game Informer и кандидаты в первоисточники.

Сети нет: чужие сайты отвечают `httpx.MockTransport`. База своя, в памяти.

Вопросы письма и их подлоги:
1. ССЫЛКИ берутся из СЫРОГО описания (href и голым текстом), без ссылок
   на сам источник; повторный сбор дублей не даёт, новая ссылка доезжает.
2. КАНДИДАТЫ: считаются записи и источники; площадки из `skip` и уже
   заведённые сайты не показываются (обратный случай — снятый `skip`
   пускает соцсеть наверх: иначе «соцсетей нет» неотличимо от «их
   не было»).
3. «ПРОВЕРИТЬ И ДОБАВИТЬ»: robots.txt запрещает — отказ С ПРИЧИНОЙ,
   источника нет; лента нашлась — источник со строгим фильтром.
4. GAME INFORMER — источник семени и доверенное СМИ; список доверенных
   доезжает до уже заведённой базы, чужой член списка не стирается.
"""
import asyncio
import os

os.environ.setdefault("DB_PATH", "./test_model_usage.db")
os.environ.setdefault("AGENT_WEBHOOK_KEY", "test-key-8f3a91")

import httpx  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import content_app as ca  # noqa: E402
import content_collect as cc  # noqa: E402
import content_db as cdb  # noqa: E402
import content_engine as ce  # noqa: E402
import content_ideas as ci  # noqa: E402
import database  # noqa: E402
from content_db import (ContentDomain, ContentItem, ContentLink, ContentSetting,  # noqa: E402
                        ContentSource)

ЗОНА = __import__("zoneinfo").ZoneInfo("Europe/Moscow")


@pytest.fixture
def база(monkeypatch):
    движок = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    database.Base.metadata.create_all(движок)
    Сессия = sessionmaker(bind=движок)
    db = Сессия()
    cdb.засеять(db)
    monkeypatch.setattr(ce, "SessionLocal", Сессия)
    cc._РОБОТС.clear()
    yield db, Сессия
    db.close()


def _сеть(monkeypatch, ответы: dict):
    """Сайт: адрес -> (код, тело). Чего нет — 404. Счётчик запросов — в списке."""
    запросы = []

    def обработчик(req):
        адрес = str(req.url)
        запросы.append(адрес)
        код, тело = ответы.get(адрес, (404, "not found"))
        return httpx.Response(код, text=тело)

    monkeypatch.setattr(cc, "новый_клиент", lambda: httpx.AsyncClient(
        transport=httpx.MockTransport(обработчик), follow_redirects=True))
    return запросы


ЛЕНТА = """<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
<item><title>GTA 6 trailer 3</title><link>https://leaks.test/a</link>
<pubDate>Tue, 29 Sep 2026 10:00:00 GMT</pubDate><description>x</description></item>
</channel></rss>"""


# ── 1. ССЫЛКИ ─────────────────────────────────────────────────────────

def test_ссылки_из_разметки_и_текста_без_своего_хоста():
    разметка = ('<p>Источник: <a href="https://www.Bloomberg.com/news/gta">Bloomberg</a>, '
                'читайте https://insider-gaming.com/gta6-leak. и '
                '<a href="https://www.ign.com/articles/x">своя</a> '
                '<a href="https://feeds.ign.com/y">своя2</a> <a href="mailto:a@b.c">почта</a></p>')
    ссылки = cc.внешние_ссылки(разметка, свой_хост="www.ign.com")
    assert ссылки == ["https://www.Bloomberg.com/news/gta", "https://insider-gaming.com/gta6-leak"]
    assert cc.домен(ссылки[0]) == "bloomberg.com"
    assert cc.внешние_ссылки(разметка + разметка, свой_хост="www.ign.com") == ссылки   # без дублей


def test_rss_отдаёт_ссылки_из_описания_и_полного_текста(monkeypatch):
    лента = """<?xml version="1.0"?><rss version="2.0"
      xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel>
      <item><title>GTA 6</title><link>https://www.gameinformer.com/n/1</link>
      <description>&lt;a href="https://kotaku.com/gta"&gt;k&lt;/a&gt;</description>
      <content:encoded><![CDATA[<a href="https://www.gameinformer.com/other">своя</a>
        <a href="https://rockstargames.com/newswire/1">rs</a>]]></content:encoded></item>
      </channel></rss>"""
    _сеть(monkeypatch, {"https://gi.test/robots.txt": (404, ""),
                        "https://gi.test/news.xml": (200, лента)})

    async def прогон():
        async with cc.новый_клиент() as к:
            return await cc.собрать_rss(к, {"url": "https://gi.test/news.xml", "name": "GI",
                                            "params": {}})
    записи = asyncio.run(прогон())
    assert записи[0]["ссылки"] == ["https://kotaku.com/gta", "https://rockstargames.com/newswire/1"]


def _запись(ext: str, ссылки: list[str], ключ="yt:UC1") -> dict:
    return {"ext_id": ext, "url": "https://youtube.com/watch?v=" + ext, "title": "GTA 6 " + ext,
            "platform": "youtube", "source_key": ключ, "ссылки": ссылки}


def test_повторный_сбор_не_дублирует_ссылки_а_новая_доезжает(база):
    db, _ = база
    yt = {"id": 99, "kind": "youtube", "name": "YT", "official": False}
    ce._записать("gta", yt, [_запись("v1", ["https://kotaku.com/a"])])
    ce._записать("gta", yt, [_запись("v1", ["https://kotaku.com/a"])])
    assert db.query(ContentLink).count() == 1
    ce._записать("gta", yt, [_запись("v1", ["https://kotaku.com/a", "https://bloomberg.com/b"])])
    assert sorted(л.domain for л in db.query(ContentLink)) == ["bloomberg.com", "kotaku.com"]


# ── 2. КАНДИДАТЫ ──────────────────────────────────────────────────────

def _насеять_ссылки():
    yt = {"id": 99, "kind": "youtube", "name": "YT", "official": False}
    ce._записать("gta", yt, [
        _запись("v1", ["https://kotaku.com/1", "https://x.com/rs", "https://www.ign.com/a"], "yt:A"),
        _запись("v2", ["https://kotaku.com/2", "https://x.com/rs2", "https://ign.com/b"], "yt:B"),
        _запись("v3", ["https://kotaku.com/3", "https://x.com/rs3"], "yt:B"),
        _запись("v4", ["https://once.test/1"], "yt:A"),
    ])


def test_кандидаты_без_площадок_своих_и_редких(база):
    db, _ = база
    _насеять_ссылки()
    к = ca._кандидаты(db, "gta", ЗОНА)
    assert [(с["domain"], с["refs"], с["sources"]) for с in к] == [("kotaku.com", 3, 2)]
    assert к[0]["url"].startswith("https://kotaku.com/")


def test_кандидаты_обратный_случай_skip_снят_соцсеть_наверху(база):
    db, _ = база
    _насеять_ссылки()
    нс = db.query(ContentSetting).filter(ContentSetting.key == "candidates").one()
    значение = cdb.из_json(нс.value, {})
    значение["skip"] = []
    нс.value = cdb.в_json(значение)
    db.commit()
    домены = [с["domain"] for с in ca._кандидаты(db, "gta", ЗОНА)]
    assert "x.com" in домены and "kotaku.com" in домены
    assert "ign.com" not in домены          # сайт заведённого источника (params.site у IGN)


# ── 3. «ПРОВЕРИТЬ И ДОБАВИТЬ» ─────────────────────────────────────────

def test_проверка_robots_запрещает_отказ_с_причиной(база, monkeypatch):
    db, Сессия = база
    запросы = _сеть(monkeypatch, {
        "https://closed.test/robots.txt": (200, "User-agent: *\nDisallow: /\n"),
        "https://closed.test/rss.xml": (200, ЛЕНТА)})
    было = db.query(ContentSource).count()
    итог = asyncio.run(ce.проверить_домен("closed.test", "test"))
    assert not итог["добавлен"] and "robots.txt" in итог["причина"]
    с = Сессия()
    assert с.query(ContentSource).count() == было
    д = с.query(ContentDomain).filter(ContentDomain.domain == "closed.test").one()
    assert д.status == "refused" and "robots.txt" in д.reason
    assert запросы == ["https://closed.test/robots.txt"]     # дальше robots.txt не пошли


def test_проверка_находит_ленту_и_заводит_строгий_источник(база, monkeypatch):
    db, Сессия = база
    _сеть(monkeypatch, {
        "https://leaks.test/robots.txt": (200, "User-agent: *\nDisallow: /private/\n"),
        "https://leaks.test/": (200, '<html><head><link rel="alternate" '
                                     'type="application/rss+xml" href="/feeds/all.xml"></head></html>'),
        "https://leaks.test/feeds/all.xml": (200, ЛЕНТА)})
    итог = asyncio.run(ce.проверить_домен("leaks.test", "test"))
    assert итог["добавлен"] and итог["лента"] == "https://leaks.test/feeds/all.xml"
    с = Сессия()
    и = с.get(ContentSource, итог["источник_id"])
    assert и.kind == "rss" and cdb.из_json(и.params)["strict"] is True and not и.official
    assert с.query(ContentDomain).filter(ContentDomain.domain == "leaks.test").one().status == "added"
    # заведённый сайт из кандидатов уходит и второй раз не заводится
    assert "уже заведён" in asyncio.run(ce.проверить_домен("leaks.test", "test"))["причина"]


def test_проверка_нет_ленты_отказ_со_списком_спрошенного(база, monkeypatch):
    _, Сессия = база
    _сеть(monkeypatch, {"https://nofeed.test/robots.txt": (404, ""),
                        "https://nofeed.test/": (200, "<html></html>")})
    итог = asyncio.run(ce.проверить_домен("nofeed.test", "test"))
    assert not итог["добавлен"] and "ленты RSS/Atom не нашлось" in итог["причина"]
    assert "/rss.xml — HTTP 404" in итог["причина"]


# ── 4. GAME INFORMER ──────────────────────────────────────────────────

def test_game_informer_строгий_источник_и_доверенное_сми(база):
    db, _ = база
    gi = db.query(ContentSource).filter(ContentSource.name == "Game Informer").one()
    assert gi.url == "https://gameinformer.com/news.xml" and cdb.из_json(gi.params)["strict"]
    формулировки = cdb.настройка(db, "wording")
    assert "Game Informer" in формулировки["trusted_media"]

    class З:
        official, rumor, leak, source_name = False, False, False, "Game Informer"
    assert ci.официально([З()], формулировки)
    З.rumor = True
    assert not ci.официально([З()], формулировки)


def test_доверенные_сми_доезжают_до_старой_базы_чужое_не_стирается(база):
    db, _ = база
    нс = db.query(ContentSetting).filter(ContentSetting.key == "wording").one()
    старое = cdb.из_json(нс.value, {})
    старое.pop("v", None)
    старое["trusted_media"] = ["IGN", "Своё СМИ владельца"]
    нс.value = cdb.в_json(старое)
    db.commit()
    assert cdb.догнать_семя(db, cdb.прочитать_семя()) >= 1
    новое = cdb.настройка(db, "wording")
    assert новое["trusted_media"][:2] == ["IGN", "Своё СМИ владельца"]
    assert "Game Informer" in новое["trusted_media"] and новое["v"] == 2
    assert cdb.догнать_семя(db, cdb.прочитать_семя()) == 0      # второй раз — ничего
