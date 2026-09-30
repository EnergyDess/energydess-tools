"""Библиотека роликов-образцов (письмо B, блок 1).

Сети нет: YouTube `videos.list` и Gemini `generateContent` отвечает
подменённый транспорт httpx. База своя, в памяти. Негативные контроли
письма, у каждого обратный случай:
1. НЕДОСТУПНЫЙ РОЛИК (удалён, приватный, 18+, длинный, отказ Gemini) —
   пропуск с причиной, прогон не падает, соседний ролик разобран.
2. ПОВТОРНЫЙ ПРОГОН не разбирает уже разобранное и пропущенное;
   сбой (не та форма ответа) — пробуется снова.
3. БЮДЖЕТ ИСЧЕРПАН — стоп с понятным текстом, ни одного вызова Gemini.
"""
import asyncio
import json
import os
from datetime import datetime

os.environ.setdefault("DB_PATH", "./test_model_usage.db")
os.environ.setdefault("AGENT_WEBHOOK_KEY", "test-key-8f3a91")

import httpx  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import content_collect as cc  # noqa: E402
import content_db as cdb  # noqa: E402
import content_engine as ce  # noqa: E402
import content_refs as cr  # noqa: E402
import database  # noqa: E402
import main  # noqa: E402
from content_db import ContentArchVideo, ContentFormat, ContentRef, ContentRun  # noqa: E402

РАЗБОР = {"hook": {"said": "Вот что нашли", "shown": "трейлер", "trick": "вопрос"},
          "segments": [{"from": "0:00", "to": "0:40", "role": "завязка", "what": "повод"},
                       {"from": "0:40", "to": "3:00", "role": "пик", "what": "главное"}],
          "retention": ["0:30 — обещание"], "pace": {"cuts_per_min": 12},
          "visuals": ["геймплей"], "ending": {"cta": "подпишись"}, "packaging": {"thumbnail": "лицо"}}


@pytest.fixture
def стенд(monkeypatch):
    движок = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    database.Base.metadata.create_all(движок)
    Сессия = sessionmaker(bind=движок)
    db = Сессия()
    cdb.засеять(db)
    ф = (db.query(ContentFormat).filter(ContentFormat.status == "active",
                                        ContentFormat.phase.in_(("pre", "any")))
         .order_by(ContentFormat.sort).first())
    for ф2 in db.query(ContentFormat).filter(ContentFormat.id != ф.id):
        ф2.phase = "post"                              # один формат в работе — счёт предсказуем
    for yt, язык, выстрел in (("ruok", "ru", 5.0), ("enok", "en", 4.0), ("priv", "en", 3.0),
                              ("gone", "en", 2.0), ("age", "en", 1.9), ("long", "en", 1.8),
                              ("gembad", "en", 1.7)):
        db.add(ContentArchVideo(theme_id=ф.theme_id, yt_id=yt, title="GTA 5 " + yt,
                                channel_title="Канал " + yt, channel_lang=язык, views=10**6,
                                shot=выстрел, format_id=ф.id))
    настройки = cdb.настройка(db, "refs")
    настройки["per_format"] = 7
    db.query(cdb.ContentSetting).filter(cdb.ContentSetting.key == "refs").first().value = cdb.в_json(настройки)
    формат_id = ф.id
    db.commit()
    db.close()
    monkeypatch.setattr(main, "SessionLocal", Сессия)
    monkeypatch.setattr(ce, "SessionLocal", Сессия)
    monkeypatch.setenv("GEMINI_API_KEY", "g-test")
    monkeypatch.setenv("CONTENT_YOUTUBE_API_KEY", "y-test")
    вызовы = {"gemini": [], "youtube": 0}

    def ответ(req: httpx.Request) -> httpx.Response:
        if "googleapis.com/youtube" in str(req.url):
            вызовы["youtube"] += 1
            items = []
            for yt in req.url.params["id"].split(","):
                if yt == "gone":
                    continue
                items.append({"id": yt,
                              "contentDetails": {"duration": "PT95M" if yt == "long" else "PT9M30S",
                                                 "contentRating": ({"ytRating": "ytAgeRestricted"}
                                                                   if yt == "age" else {})},
                              "status": {"privacyStatus": "private" if yt == "priv" else "public"}})
            return httpx.Response(200, json={"items": items})
        if "i.ytimg.com" in str(req.url):
            return httpx.Response(200, content=b"\xff\xd8jpeg")
        if ":generateContent" in str(req.url):
            тело = json.loads(req.content)
            yt = тело["contents"][0]["parts"][0]["fileData"]["fileUri"].split("v=")[1]
            вызовы["gemini"].append(yt)
            if yt == "gembad":
                return httpx.Response(400, json={"error": {"message": "The YouTube video is not available"}})
            if yt == "enok" and стенд_флаги.get("кривой"):
                return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "не json"}]}}]})
            return httpx.Response(200, json={
                "candidates": [{"content": {"parts": [{"text": json.dumps(РАЗБОР)}]}, "finishReason": "STOP"}],
                "usageMetadata": {"promptTokenCount": 40000, "candidatesTokenCount": 1000}})
        return httpx.Response(404)

    стенд_флаги = {}
    monkeypatch.setattr(cc, "новый_клиент",
                        lambda: httpx.AsyncClient(transport=httpx.MockTransport(ответ)))
    return {"Сессия": Сессия, "вызовы": вызовы, "флаги": стенд_флаги, "формат": формат_id}


def _refs(Сессия):
    db = Сессия()
    try:
        return {р.yt_id: (р.state, р.reason, р.tries) for р in db.query(ContentRef)}
    finally:
        db.close()


def test_недоступный_ролик_пропуск_с_причиной_а_не_падение(стенд):
    итог = asyncio.run(cr.прогон("probe"))
    р = _refs(стенд["Сессия"])
    assert итог["state"] == "ok", итог
    assert р["ruok"][0] == "ok" and р["enok"][0] == "ok"
    assert р["priv"][0] == "skipped" and "не публичный" in р["priv"][1]
    assert р["gone"][0] == "skipped" and "удалён" in р["gone"][1]
    assert р["age"][0] == "skipped" and "18+" in р["age"][1]
    assert р["long"][0] == "skipped" and "длиннее" in р["long"][1]
    assert р["gembad"][0] == "skipped" and "не смог открыть" in р["gembad"][1]
    # Пропущенные проверкой ДО модели Gemini не звали
    assert sorted(стенд["вызовы"]["gemini"]) == ["enok", "gembad", "ruok"]


def test_повторный_прогон_не_разбирает_разобранное(стенд):
    стенд["флаги"]["кривой"] = True
    asyncio.run(cr.прогон("probe"))
    assert _refs(стенд["Сессия"])["enok"][0] == "error"
    стенд["вызовы"]["gemini"].clear()
    стенд["флаги"]["кривой"] = False
    итог = asyncio.run(cr.прогон("probe"))
    # второй раз — только сбойный «enok»; ok и skipped не трогаются
    assert стенд["вызовы"]["gemini"] == ["enok"], стенд["вызовы"]["gemini"]
    assert итог["разобрано"] == 1 and _refs(стенд["Сессия"])["enok"][0] == "ok"
    стенд["вызовы"]["gemini"].clear()
    итог = asyncio.run(cr.прогон("probe"))
    assert стенд["вызовы"]["gemini"] == [] and итог["кандидатов"] == 0


def test_бюджет_исчерпан_стоп_с_текстом(стенд):
    db = стенд["Сессия"]()
    db.add(database.ModelUsage(tool="admin-content-ideas", model="m", cost=5.0, ok=True,
                               created_at=datetime.utcnow()))
    db.commit()
    db.close()
    итог = asyncio.run(cr.прогон("probe"))
    assert стенд["вызовы"]["gemini"] == []
    assert итог["стоп"] == "бюджет" and итог["state"] == "partial"
    assert "Бюджет модели на сегодня исчерпан" in итог["note"]


def test_расход_пишется_строкой_образцы(стенд):
    asyncio.run(cr.прогон("probe"))
    db = стенд["Сессия"]()
    try:
        строки = db.query(database.ModelUsage).filter(database.ModelUsage.tool == cr.ИНСТРУМЕНТ).all()
        assert len(строки) == 3
        удачные = [с for с in строки if с.ok]
        assert len(удачные) == 2 and all(abs(с.cost - 0.0145) < 1e-9 for с in удачные)
        расход = ce.расход_по_задачам(db)
        assert расход["сегодня"]["образцы"]["вызовов"] == 3
        assert cr.сводка(db)["разобрано"] == 2
    finally:
        db.close()


def test_подлог_проверки_до_модели_снят(стенд, monkeypatch):
    """Обратный случай: без проверки до модели приватный ролик уходит в Gemini."""
    monkeypatch.setattr(cr, "причина_пропуска", lambda с, есть, предел: None)
    asyncio.run(cr.прогон("probe"))
    assert "priv" in стенд["вызовы"]["gemini"]


def test_без_ключа_gemini_прогон_ошибка_словами(стенд, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY")
    итог = asyncio.run(cr.прогон("probe"))
    assert итог["state"] == "error" and "GEMINI_API_KEY" in итог["note"]
    assert cr.нужны() is False
