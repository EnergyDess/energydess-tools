"""Идеи роликов, конвейер, радар и «Кухня» (BACKLOG №370, 371).

Сети нет, модель — подменённый `content_engine._спросить`. База своя, в памяти.
Негативные контроли письма, у каждого обратный случай:
1. ВЫДУМАННОЕ ЧИСЛО в тексте модели — текст отклонён и спрошен заново;
   модель упорствует — текст собирает код. Подлог: проверка снята — число
   проходит (иначе «отклонено» неотличимо от «проверка ничего не видит»).
2. ПОВТОРНЫЙ ПРОГОН не повторяет пару «сюжет + формат».
3. «НЕ ТО» с причиной «не мой формат» снижает вес формата: следующий прогон
   его не предлагает первым.
4. ВКЛЮЧЁННЫЙ ИСТОЧНИК сломан 2+ ч — радар красный с причиной; свежий
   сбой и выключенный источник — не красный.
5. REDDIT без ключа — «выключен, ждёт ключ», цикл из-за него не «частично».
"""
import asyncio
import json
import os
import re
from datetime import datetime, timedelta

os.environ.setdefault("DB_PATH", "./test_model_usage.db")
os.environ.setdefault("AGENT_WEBHOOK_KEY", "test-key-8f3a91")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import content_collect as cc  # noqa: E402
import content_db as cdb  # noqa: E402
import content_engine as ce  # noqa: E402
import content_ideas as ci  # noqa: E402
import database  # noqa: E402
import main  # noqa: E402
from auth import create_token, hash_password  # noqa: E402
from content_db import (ContentArchVideo, ContentFormat, ContentIdea, ContentItem,  # noqa: E402
                        ContentRun, ContentSource, ContentStory, ContentVideo)

ТЕМА = "gta"


def _честная_модель(вызовы):
    """Модель, пишущая только числа из вопроса: название — сюжет/формат."""
    async def _спросить(клиент, инструмент, система, вопрос, потолок):
        вызовы.append(вопрос)
        n = len(re.findall(r"^\d+\. \[", вопрос, re.M))
        return json.dumps({"ideas": [{"n": i, "format": 1, "title": "Ролик номер один",
                                      "why": "Свежий повод"} for i in range(1, n + 1)]}), None
    return _спросить


@pytest.fixture
def стенд(monkeypatch):
    движок = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    database.Base.metadata.create_all(движок)
    Сессия = sessionmaker(bind=движок)
    db = Сессия()
    админ = database.User(email="adm@ideas.test", password_hash=hash_password("x-123456"),
                          is_verified=True, is_admin=True)
    db.add(админ)
    db.commit()
    cdb.засеять(db)
    тема = db.query(database.Base.metadata.tables["content_themes"].c.id).first()[0]
    сейчас = datetime.utcnow()
    форматы = db.query(ContentFormat).filter(ContentFormat.theme_id == тема).order_by(ContentFormat.sort).all()
    # два формата с выстрелом (×4.2 и ×2.0), остальные без данных
    for i, (ф, выстрел) in enumerate([(форматы[0], 4.2), (форматы[1], 2.0)]):
        for k in range(3):
            db.add(ContentArchVideo(theme_id=тема, yt_id=f"a{i}{k}", title=f"GTA 5 хит {i}{k}",
                                    channel_lang="en", views=100000, shot=выстрел,
                                    format_id=ф.id))
    # свежий сюжет: 2 ролика за 48 ч (1500 + 500), 1 из них RU; новость
    с = ContentStory(theme_id=тема, title="Трейлер GTA 6 номер 3", summary="Rockstar выпустила трейлер",
                     first_seen_at=сейчас - timedelta(hours=10), last_item_at=сейчас,
                     items=3, sources=2, platforms=2, ru_videos=1, score=80, growth=50.0, leak=True)
    db.add(с)
    db.flush()
    db.add_all([
        ContentItem(theme_id=тема, ext_id="yt:x1", source_id=1, source_key="yt", source_name="Канал",
                    platform="youtube", url="https://youtube.com/watch?v=x1", title="Trailer 3",
                    lang="en", published_at=сейчас - timedelta(hours=5), first_seen_at=сейчас,
                    last_seen_at=сейчас, metric=1500, story_id=с.id),
        ContentItem(theme_id=тема, ext_id="yt:x2", source_id=1, source_key="yt", source_name="Канал RU",
                    platform="youtube", url="https://youtube.com/watch?v=x2", title="Трейлер 3",
                    lang="ru", published_at=сейчас - timedelta(hours=3), first_seen_at=сейчас,
                    last_seen_at=сейчас, metric=500, story_id=с.id),
        ContentItem(theme_id=тема, ext_id="yt:old", source_id=1, source_key="yt", source_name="Канал",
                    platform="youtube", url="https://youtube.com/watch?v=old", title="Old",
                    lang="en", published_at=сейчас - timedelta(hours=80), first_seen_at=сейчас,
                    last_seen_at=сейчас, metric=99999, story_id=с.id),
        ContentItem(theme_id=тема, ext_id="rss:1", source_id=2, source_key="rss", source_name="IGN",
                    platform="rss", url="https://ign.test/1", title="GTA 6 trailer 3",
                    published_at=сейчас - timedelta(hours=10), first_seen_at=сейчас,
                    last_seen_at=сейчас, story_id=с.id),
    ])
    db.commit()

    def _db():
        s = Сессия()
        try:
            yield s
        finally:
            s.close()

    main.app.dependency_overrides[main.get_db] = _db
    monkeypatch.setattr(main, "SessionLocal", Сессия)
    monkeypatch.setattr(ce, "SessionLocal", Сессия)
    monkeypatch.setenv("CONTENT_SCHEDULER", "0")
    вызовы = []
    monkeypatch.setattr(ce, "_спросить", _честная_модель(вызовы))
    к = TestClient(main.app)
    к.cookies.set("access_token", create_token(админ.id))
    yield db, к, тема, с, форматы, вызовы
    main.app.dependency_overrides.pop(main.get_db, None)
    db.close()


def _прогон():
    return asyncio.run(ci.сгенерировать("test"))


# ── ФАКТЫ СЧИТАЕТ КОД ─────────────────────────────────────────────────

def test_факты_считает_код_и_нет_данных_не_ноль(стенд):
    db, _, тема, с, форматы, _ = стенд
    итог = _прогон()
    assert итог["state"] == "ok", итог
    db.expire_all()
    горячая = db.query(ContentIdea).filter(ContentIdea.story_id == с.id, ContentIdea.kind == "long").first()
    ф = json.loads(горячая.facts)
    assert ф["спрос"] == 2000, "спрос — ролики за 48 ч, старый ролик (80 ч) не входит"
    assert ф["конкуренция"] == 1 and 37 <= ф["окно_ч"] <= 39
    assert "leak" in json.loads(горячая.risks)
    основа = json.loads(горячая.basis)
    assert len(основа["ролики"]) == 2 and len(основа["новости"]) == 1
    вечная = db.query(ContentIdea).filter(ContentIdea.sort == "evergreen").first()
    fв = json.loads(вечная.facts)
    assert fв["окно_ч"] is None and fв["спрос"] is None
    п = ci.факты_подписи(fв)
    assert п["спрос"] == "нет данных" and п["окно"] == "в любой день"
    assert ci.факты_подписи({"выстрел": None})["выстрел"] == "нет данных"
    # набор: 1 главная long, long ≤ 6, shorts ≤ 5
    # «Съёмки первой недели» (state launch) — отдельный список, в набор не входят
    long_ = db.query(ContentIdea).filter(ContentIdea.kind == "long", ContentIdea.state == "new").all()
    assert sum(1 for и in long_ if и.main) == 1 and len(long_) <= 6
    assert db.query(ContentIdea).filter(ContentIdea.kind == "shorts").count() <= 5
    # шаги прогона записаны все и все отмечены
    шаги = json.loads(db.query(ContentRun).filter(ContentRun.kind == "ideas").one().summary)["шаги"]
    assert len(шаги) == len(ci.ШАГИ) and all(ш["done"] for ш in шаги)


# ── 1. ВЫДУМАННОЕ ЧИСЛО ───────────────────────────────────────────────

def _врёт_раз(вызовы):
    async def _спросить(клиент, инструмент, система, вопрос, потолок):
        вызовы.append(вопрос)
        n = len(re.findall(r"^\d+\. \[", вопрос, re.M))
        врать = len(вызовы) == 1
        return json.dumps({"ideas": [{"n": i, "format": 1,
                                      "title": "Трейлер собрал 777 тысяч" if врать else "Разбор трейлера",
                                      "why": "Смотрят сейчас"} for i in range(1, n + 1)]}), None
    return _спросить


def test_выдуманное_число_отклонено_и_спрошено_заново(стенд, monkeypatch):
    db, _, _, _, _, _ = стенд
    вызовы = []
    monkeypatch.setattr(ce, "_спросить", _врёт_раз(вызовы))
    _прогон()
    db.expire_all()
    assert len(вызовы) == 2, "после отклонения модель обязана быть спрошена второй раз"
    идеи = db.query(ContentIdea).filter(ContentIdea.state == "new").all()
    assert идеи and not any("777" in и.title for и in идеи)
    assert all(и.text_tries == 2 and и.text_by == "model" for и in идеи)


def test_упорное_враньё_текст_собирает_код(стенд, monkeypatch):
    db, _, _, _, _, _ = стенд
    async def _всегда(клиент, инструмент, система, вопрос, потолок):
        n = len(re.findall(r"^\d+\. \[", вопрос, re.M))
        return json.dumps({"ideas": [{"n": i, "format": 1, "title": "Ровно 12345 просмотров",
                                      "why": "x"} for i in range(1, n + 1)]}), None
    monkeypatch.setattr(ce, "_спросить", _всегда)
    _прогон()
    db.expire_all()
    идеи = db.query(ContentIdea).all()
    assert идеи and all(и.text_by == "code" and "12345" not in и.title for и in идеи)


def test_подлог_проверка_чисел_снята_выдумка_проходит(стенд, monkeypatch):
    db, _, _, _, _, _ = стенд
    monkeypatch.setattr(ce, "_спросить", _врёт_раз([]))
    monkeypatch.setattr(ci, "лишние_числа", lambda текст, разрешено: [])
    _прогон()
    db.expire_all()
    assert any("777" in и.title for и in db.query(ContentIdea).all())


def test_числа_из_фактов_разрешены():
    р = {"сюжет": None, "факты": {"спрос": 2000, "конкуренция": 1, "окно_ч": 38.0}}
    разрешено = ci.разрешённые_числа(р, {"title": "Топ 10", "медиана": 4.2})
    assert ci.лишние_числа("Топ 10 и 4,2 раза, окно 2 дня", разрешено) == []
    assert ci.лишние_числа("Уже 999 роликов", разрешено) == ["999"]


# ── 2. ПОВТОРНЫЙ ПРОГОН БЕЗ ДУБЛЕЙ ────────────────────────────────────

def test_повторный_прогон_не_повторяет_пары(стенд):
    db, _, _, _, _, _ = стенд
    _прогон()
    _прогон()
    db.expire_all()
    пары = [(и.story_id, и.format_id) for и in db.query(ContentIdea).all()]
    assert len(пары) == len(set(пары)), "пара «сюжет + формат» повторилась"
    assert db.query(ContentRun).filter(ContentRun.kind == "ideas").count() == 2


# ── 3. «НЕ ТО» СНИЖАЕТ ВЕС ────────────────────────────────────────────

def test_не_мой_формат_снижает_вес(стенд):
    db, к, тема, с, форматы, _ = стенд
    н = cdb.настройка(db, "ideas")
    до = ci.подобрать(db, тема, {**н, "dedupe_days": 0})
    первый = до["long"][0]["форматы"][0]["id"]
    assert первый == форматы[0].id, "до отказа лучший формат — ×4.2"
    _прогон()
    db.expire_all()
    идея = db.query(ContentIdea).filter(ContentIdea.format_id == первый).first()
    r = к.post(f"/content/api/ideas/{идея.id}", json={"action": "reject", "reason": "format"})
    assert r.status_code == 200
    db.expire_all()
    после = ci.подобрать(db, тема, {**н, "dedupe_days": 0})
    assert после["long"][0]["форматы"][0]["id"] != первый, "отказ не снизил вес формата"
    assert к.post(f"/content/api/ideas/{идея.id}", json={"action": "reject",
                                                        "reason": "лень"}).status_code == 400


def test_в_план_и_не_сегодня(стенд):
    db, к, тема, _, _, _ = стенд
    _прогон()
    db.expire_all()
    главная = db.query(ContentIdea).filter(ContentIdea.main.is_(True)).one()
    assert к.post(f"/content/api/ideas/{главная.id}", json={"action": "later"}).status_code == 200
    db.expire_all()
    новая = db.query(ContentIdea).filter(ContentIdea.main.is_(True)).one()
    assert новая.id != главная.id and db.get(ContentIdea, главная.id).state == "new"
    r = к.post(f"/content/api/ideas/{новая.id}", json={"action": "plan"}).json()
    р = db.get(ContentVideo, r["video_id"])
    assert р.status == "plan" and р.title == новая.title
    assert к.post(f"/content/api/videos/{р.id}", json={"status": "writing"}).status_code == 200
    assert к.post(f"/content/api/videos/{р.id}", json={"status": "published",
                                                       "url": "https://evil.test/x"}).status_code == 400
    assert к.post(f"/content/api/videos/{р.id}", json={"status": "published",
                                                       "url": "https://youtu.be/abc"}).status_code == 200
    db.expire_all()
    assert ci.неделя(db, тема)["вышло"] == 1
    assert к.post("/content/api/settings/week", json={"goal": 5}).status_code == 200
    assert ci.неделя(db, тема)["цель"] == 5
    assert к.post("/content/api/settings/week", json={"goal": 0}).status_code == 400


# ── 4. РАДАР ──────────────────────────────────────────────────────────

def test_радар_красный_если_источник_падает_дольше_2_ч(стенд):
    db, _, _, _, _, _ = стенд
    сейчас = datetime.utcnow()
    db.add(ContentRun(kind="cycle", trigger="test", state="ok",
                      started_at=сейчас - timedelta(minutes=20), finished_at=сейчас - timedelta(minutes=19)))
    for и in db.query(ContentSource).all():
        и.last_state, и.last_ok_at = "ok", сейчас
    db.commit()
    assert ci.радар(db)["ok"] is True
    ps = db.query(ContentSource).filter(ContentSource.enabled.is_(True),
                                        ContentSource.kind == "rss").first()
    ps.last_state, ps.last_ok_at = "error", сейчас - timedelta(minutes=30)
    db.commit()
    assert ci.радар(db)["ok"] is True, "свежий сбой (30 мин) — ещё не красный"
    ps.last_ok_at = сейчас - timedelta(hours=3)
    db.commit()
    р = ci.радар(db)
    assert р["ok"] is False and ps.name in р["причина"]
    ps.enabled = False
    db.commit()
    assert ci.радар(db)["ok"] is True, "выключенный источник радар не красит"


def test_радар_красный_без_успешного_цикла(стенд):
    db, _, _, _, _, _ = стенд
    р = ci.радар(db)
    assert р["ok"] is False and "сбора не было" in р["причина"]


# ── 5. REDDIT БЕЗ КЛЮЧА НЕ ДЕЛАЕТ ЦИКЛ «ЧАСТИЧНО» ─────────────────────

def test_reddit_выключен_цикл_не_частично(стенд, monkeypatch):
    db, к, _, _, _, _ = стенд
    monkeypatch.delenv("REDDIT_CLIENT_ID", raising=False)
    monkeypatch.delenv("REDDIT_CLIENT_SECRET", raising=False)
    for и in db.query(ContentSource).all():
        и.enabled = и.kind == "reddit"
    db.commit()
    итог = asyncio.run(ce.цикл("test"))
    assert итог["state"] == "ok", итог
    db.expire_all()
    рд = db.query(ContentSource).filter(ContentSource.kind == "reddit").one()
    assert рд.last_state == "off"
    assert "выключен, ждёт ключ" in к.get("/content/kitchen?tab=sources").text
    assert ci.радар(db)["ok"] is True


def test_подлог_reddit_ошибкой_цикл_частично(стенд, monkeypatch):
    """Обратный случай: без ветки «выключен» Reddit снова ошибка и цикл частичный."""
    db, _, _, _, _, _ = стенд
    monkeypatch.setattr(cc, "reddit_ключи", lambda: ("id", "secret"))
    async def _отказ(client, и):
        raise cc.ОтказИсточника("нет ключа")
    monkeypatch.setattr(cc, "собрать_reddit", _отказ)
    for и in db.query(ContentSource).all():
        и.enabled = и.kind == "reddit"
    db.commit()
    assert asyncio.run(ce.цикл("test"))["state"] == "partial"


# ── СТРАНИЦЫ ──────────────────────────────────────────────────────────

def test_сегодня_и_кухня_открываются(стенд):
    db, к, _, _, _, _ = стенд
    пусто = к.get("/content").text
    assert "Первые идеи появятся после прогона в 08:00" in пусто
    _прогон()
    for адрес in ("/content", "/content?type=shorts", "/content/kitchen"):
        r = к.get(адрес)
        assert r.status_code == 200, адрес
    сегодня = к.get("/content").text
    assert "Снимай это" in сегодня and "Кухня" in сегодня
    кухня = к.get("/content/kitchen?tab=formats").text
    assert "данные появятся после прогона археологии" in кухня


def test_утренний_прогон_по_расписанию(стенд):
    db, _, _, _, _, _ = стенд
    мск_9 = datetime(2026, 9, 30, 6, 0)          # 09:00 МСК
    мск_7 = datetime(2026, 9, 30, 4, 0)          # 07:00 МСК
    assert ci.пора_утром(db, мск_7) is False
    assert ci.пора_утром(db, мск_9) is True
    db.add(ContentRun(kind="ideas", trigger="morning", state="ok",
                      started_at=datetime(2026, 9, 30, 5, 1), finished_at=datetime(2026, 9, 30, 5, 2)))
    db.commit()
    assert ci.пора_утром(db, мск_9) is False
    assert ci.горячий_без_идеи(db) is True
    _прогон()
    assert ci.горячий_без_идеи(db) is False


# ── ПИСЬМО A2: ЧЕСТНЫЕ ФОРМУЛИРОВКИ, ФАЗЫ, БЮДЖЕТ, ВОЛНЫ, ЧИСТКА ─────

НАСТОЯЩИЙ_СПРОСИТЬ = ce._спросить        # до подмены фикстурой


def _сюжет_фаната(db, тема):
    """Сюжет из ОДНОГО фанатского ролика: официального источника нет."""
    сейчас = datetime.utcnow()
    с = ContentStory(theme_id=тема, title="Карта Вайс-Сити из утечки", summary="Фанат разобрал карту",
                     first_seen_at=сейчас - timedelta(hours=5), last_item_at=сейчас,
                     items=1, sources=1, platforms=1, ru_videos=0, score=95, growth=10.0)
    db.add(с)
    db.flush()
    db.add(ContentItem(theme_id=тема, ext_id="yt:fan", source_id=1, source_key="yt:fan",
                       source_name="Фанатский канал", platform="youtube",
                       url="https://youtube.com/watch?v=fan", title="Карта GTA 6", lang="en",
                       published_at=сейчас - timedelta(hours=5), first_seen_at=сейчас,
                       last_seen_at=сейчас, metric=900, story_id=с.id))
    db.commit()
    return с


def _официально_врёт(вызовы):
    async def _спросить(клиент, инструмент, система, вопрос, потолок):
        вызовы.append(вопрос)
        n = len(re.findall(r"^\d+\. \[", вопрос, re.M))
        return json.dumps({"ideas": [{"n": i, "format": 1,
                                      "title": "Rockstar официально подтвердила карту",
                                      "why": "Смотрят сейчас"} for i in range(1, n + 1)]}), None
    return _спросить


def test_слух_без_официального_источника_называется_слухом(стенд, monkeypatch):
    db, _, тема, _, _, _ = стенд
    с = _сюжет_фаната(db, тема)
    вызовы = []
    monkeypatch.setattr(ce, "_спросить", _официально_врёт(вызовы))
    _прогон()
    db.expire_all()
    идеи = db.query(ContentIdea).filter(ContentIdea.story_id == с.id).all()
    assert идеи
    for и in идеи:
        assert "официальн" not in (и.title + и.why).lower(), и.title
        assert "rumor" in json.loads(и.risks)
        assert и.text_by == "code" and и.title.startswith("По слухам")
    assert any("СЛУХ" in в for в in вызовы), "модель обязана знать, что сюжет — слух"


def test_официальный_источник_формулировку_пропускает(стенд, monkeypatch):
    """Обратный случай: у сюжета фикстуры есть запись IGN (доверенное СМИ) —
    «официально» законно, текст модели не отклоняется."""
    db, _, _, с, _, _ = стенд
    monkeypatch.setattr(ce, "_спросить", _официально_врёт([]))
    _прогон()
    db.expire_all()
    идея = db.query(ContentIdea).filter(ContentIdea.story_id == с.id, ContentIdea.state == "new").first()
    assert идея.text_by == "model" and "официально" in идея.title
    assert "rumor" not in json.loads(идея.risks)


def test_подлог_проверка_слуха_снята_официально_проходит(стенд, monkeypatch):
    db, _, тема, _, _, _ = стенд
    с = _сюжет_фаната(db, тема)
    monkeypatch.setattr(ce, "_спросить", _официально_врёт([]))
    monkeypatch.setattr(ci, "запрещённые_при_слухе", lambda текст, ф: [])
    _прогон()
    db.expire_all()
    assert any("официально" in и.title
               for и in db.query(ContentIdea).filter(ContentIdea.story_id == с.id).all())


def _дать_выстрел(db, тема, название, выстрел=6.0):
    ф = db.query(ContentFormat).filter(ContentFormat.theme_id == тема, ContentFormat.title == название).one()
    for k in range(3):
        db.add(ContentArchVideo(theme_id=тема, yt_id=f"l{ф.id}{k}", title=f"GTA 5 тайник {k}",
                                channel_lang="en", views=100000, shot=выстрел, format_id=ф.id))
    db.commit()
    return ф


def test_фазы_проставлены_всем_стартовым_форматам(стенд):
    db, _, тема, _, _, _ = стенд
    без = [ф.title for ф in db.query(ContentFormat).filter(ContentFormat.theme_id == тема) if not ф.phase]
    assert без == []
    assert db.query(ContentFormat).filter_by(title="Тайники и секретные места").one().phase == "launch"


def test_launch_формат_до_релиза_не_в_идеях_а_в_первой_неделе(стенд):
    db, _, тема, _, _, _ = стенд
    ф = _дать_выстрел(db, тема, "Тайники и секретные места")   # выстрел выше всех
    _прогон()
    db.expire_all()
    assert db.query(ContentIdea).filter(ContentIdea.format_id == ф.id, ContentIdea.state == "new").count() == 0
    assert db.query(ContentIdea).filter(ContentIdea.format_id == ф.id, ContentIdea.state == "launch").count() == 1
    assert ci.первая_неделя(db, тема) >= 1


def test_launch_формат_после_релиза_попадает_в_идеи(стенд):
    """Подмена даты: релиз три дня назад — фаза launch, формат идёт в идеи."""
    db, _, тема, _, _, _ = стенд
    ф = _дать_выстрел(db, тема, "Тайники и секретные места")
    запись = db.query(cdb.ContentSetting).filter_by(key="phases").one()
    фазы = json.loads(запись.value)
    фазы["release_date"] = (datetime.utcnow() - timedelta(days=3)).strftime("%Y-%m-%d")
    запись.value = json.dumps(фазы)
    db.commit()
    _прогон()
    db.expire_all()
    assert db.query(ContentIdea).filter(ContentIdea.format_id == ф.id, ContentIdea.state == "new").count() >= 1
    # и обратно: pre-формат после релиза в идеи не идёт
    трейлеры = db.query(ContentFormat).filter_by(title="Трейлеры по кадрам").one()
    assert db.query(ContentIdea).filter(ContentIdea.format_id == трейлеры.id,
                                        ContentIdea.run_id == ci.последний_прогон(db).id).count() == 0


def _расход(db, usd, когда=None):
    db.add(database.ModelUsage(tool="admin-content-ideas", model="m", ok=True, cost=usd,
                               created_at=когда or datetime.utcnow()))
    db.commit()


def test_бюджет_исчерпан_модель_модуля_не_зовётся(стенд, monkeypatch):
    db, _, _, _, _, _ = стенд
    _расход(db, 2.5)   # потолок по умолчанию $2 (письмо B2)
    звали = []

    async def _пост(*a, **k):
        звали.append(a[1])
        raise AssertionError("модель не должна вызываться сверх бюджета")
    monkeypatch.setattr(main, "_модель_post", _пост)
    monkeypatch.setattr(main, "OPENROUTER_API_KEY", "k")
    текст, беда = asyncio.run(НАСТОЯЩИЙ_СПРОСИТЬ(None, "admin-content-ideas", "с", "в", 10))
    assert текст is None and "бюджет" in беда and звали == []
    assert ce.бюджет(db)["исчерпан"] and ci.радар(db)["бюджет"]


def test_бюджет_не_исчерпан_модель_зовётся(стенд, monkeypatch):
    """Обратный случай: расход ниже потолка — вызов идёт."""
    db, _, _, _, _, _ = стенд
    _расход(db, 0.2)
    звали = []

    class Ответ:
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]}

    async def _пост(*a, **k):
        звали.append(a[1])
        return Ответ()
    monkeypatch.setattr(main, "_модель_post", _пост)
    monkeypatch.setattr(main, "OPENROUTER_API_KEY", "k")
    текст, беда = asyncio.run(НАСТОЯЩИЙ_СПРОСИТЬ(None, "admin-content-ideas", "с", "в", 10))
    assert беда is None and звали == ["admin-content-ideas"]


def test_бюджет_считает_сутки_по_москве(стенд):
    db, _, _, _, _, _ = стенд
    полночь = ce._полночь_мск_utc()
    _расход(db, 5.0, полночь - timedelta(minutes=30))     # вчера по Москве
    assert ce.бюджет(db)["исчерпан"] is False
    _расход(db, 5.0, полночь + timedelta(minutes=30))     # сегодня по Москве
    assert ce.бюджет(db)["исчерпан"] is True
    расход = ce.расход_по_задачам(db)
    assert расход["сегодня"]["идеи"]["usd"] == 5.0 and расход["неделя"]["идеи"]["usd"] == 10.0


def test_бюджет_не_трогает_чужие_инструменты(стенд):
    db, _, _, _, _, _ = стенд
    db.add(database.ModelUsage(tool="letter", model="m", ok=True, cost=50.0, created_at=datetime.utcnow()))
    db.commit()
    assert ce.бюджет(db)["исчерпан"] is False


def test_применить_меняет_только_отмеченные(стенд):
    db, к, тема, _, _, _ = стенд
    каналы = []
    for i, (rec, st) in enumerate([("drop", "candidate"), ("drop", "keep"), ("keep", "candidate")]):
        ch = cdb.ContentChannel(theme_id=тема, yt_id=f"UC{i}", title=f"К{i}", status=st, rec=rec,
                                rec_reason="тест")
        db.add(ch)
        каналы.append(ch)
    db.commit()
    r = к.post("/content/api/channels-apply", json={"ids": [каналы[0].id]})
    assert r.status_code == 200 and r.json()["изменено"] == [каналы[0].id]
    db.expire_all()
    assert [db.get(cdb.ContentChannel, ch.id).status for ch in каналы] == ["removed", "keep", "candidate"]


def _волна(db, тема, заголовок, часов_назад, упоминание=True):
    сейчас = datetime.utcnow()
    с = ContentStory(theme_id=тема, title=заголовок, first_seen_at=сейчас - timedelta(hours=часов_назад),
                     last_item_at=сейчас, items=1)
    db.add(с)
    db.flush()
    db.add(ContentItem(theme_id=тема, ext_id="w" + заголовок, source_id=2, source_key="rss:x",
                       source_name="IGN", platform="rss", url="https://x.test/" + str(с.id),
                       title=заголовок + (" — по данным Game Informer" if упоминание else ""),
                       published_at=сейчас - timedelta(hours=часов_назад), first_seen_at=сейчас,
                       last_seen_at=сейчас, story_id=с.id))
    db.commit()
    return с


def test_волна_одного_первоисточника_склеивается(стенд):
    db, _, тема, _, _, _ = стенд
    а = _волна(db, тема, "Скриншоты GTA 6", 10)
    б = _волна(db, тема, "Животные в GTA 6", 20)
    в = _волна(db, тема, "Погода в GTA 6", 30)
    далёкая = _волна(db, тема, "Старый материал", 200)          # за пределами 72 ч
    чужая = _волна(db, тема, "Трейлер вне волны", 15, упоминание=False)
    а, б, в, далёкая, чужая = (x.id for x in (а, б, в, далёкая, чужая))
    итог = ce.склеить_волны(тема, cdb.настройка(db, "waves"))
    db.expire_all()
    assert итог["склеено"] == 2
    живые = {с.id for с in db.query(ContentStory).all()}
    assert len({а, б, в} & живые) == 1
    главный = db.get(ContentStory, ({а, б, в} & живые).pop())
    assert главный.origin == "Game Informer" and len(json.loads(главный.subtopics)) == 2
    assert далёкая in живые and чужая in живые
    assert ce.склеить_волны(тема, cdb.настройка(db, "waves"))["склеено"] == 0   # идемпотентно


def test_язык_канала_по_названиям():
    assert cc.язык_по_названиям(["Тайники GTA 5", "Обзор машин", "GTA 6 trailer"]) == "ru"
    assert cc.язык_по_названиям(["Los mejores momentos de GTA", "Una locura en la ciudad",
                                 "El coche más rápido de los santos"]) == "other"
    assert cc.язык_по_названиям(["Best GTA 5 moments", "How to get rich"]) == "en"
    метки = cc.шаблон_ключевых(["GTA"])
    совет = cc.совет_по_каналу(["GTA 5 moments", "Minecraft build", "Fortnite win", "Roblox",
                                 "Valorant clip"], метки, 0.3)
    assert совет["rec"] == "drop" and совет["доля"] == 0.2
    assert cc.совет_по_каналу(["GTA 5 moments", "GTA 6 news"], метки, 0.3)["rec"] == "keep"


def test_слитый_формат_уводит_хиты_и_становится_псевдонимом(стенд, monkeypatch):
    db, к, тема, _, форматы, _ = стенд
    дубль = ContentFormat(theme_id=тема, title="Нарезка смешных моментов и глюков", origin="model",
                          status="review", sort=1000)
    db.add(дубль)
    db.flush()
    db.add(ContentArchVideo(theme_id=тема, yt_id="dup1", title="GTA 5 funny", format_id=дубль.id, shot=2.0))
    db.commit()
    r = к.post("/content/api/formats/%d" % дубль.id, json={"action": "merge", "into": форматы[0].id})
    assert r.status_code == 200
    db.expire_all()
    assert db.get(ContentFormat, дубль.id).status == "merged"
    assert db.query(ContentArchVideo).filter_by(yt_id="dup1").one().format_id == форматы[0].id
    # на рассмотрении формат в рейтинг не попадал; слитый — тем более
    assert дубль.id not in ci.форматы_с_выстрелом(db, тема)


def test_подлог_волны_признак_первоисточника_снят_чужой_склеивается(стенд, monkeypatch):
    """Без признака «больше половины записей называют первоисточник» волна
    глотает чужой сюжет — иначе «не склеено» неотличимо от слепой склейки."""
    db, _, тема, _, _, _ = стенд
    _волна(db, тема, "Скриншоты GTA 6", 10)
    чужая = _волна(db, тема, "Трейлер вне волны", 15, упоминание=False).id
    monkeypatch.setattr(ce, "первоисточник", lambda записи, источники: "Game Informer")
    ce.склеить_волны(тема, cdb.настройка(db, "waves"))
    db.expire_all()
    assert db.get(ContentStory, чужая) is None
