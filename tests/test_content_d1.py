"""Письмо D1, блок 1 (задача 383): три мелочи пакета ролика.

1. ПЕРЕСБОРКА НЕ СТИРАЕТ ПРОШЛУЮ ВЕРСИЮ: ошибка (402 OpenRouter) — прошлые
   данные на месте, состояние «ok», на странице плашка с причиной простыми
   словами. Подлог: защита снята — данные пусты, пакет «ошибка».
2. ЛЮДИ ROCKSTAR: «Оуэна Шеппарда», «Кейна», «Гарбута» в съёмках — не «нет
   в источниках», когда раздел «Люди Rockstar» есть в базе знаний. Подлог:
   без раздела — выдумка.
3. КАДР ТРЕЙЛЕРА БЕЗ ТАЙМКОДА при доступном разборе — не принимается
   («найди в трейлере»), даже под видом сравнения с GTA 5; с таймкодом — номер
   трейлера и таймкод в «где». Графика — «графика: <текст плашки>». Своя
   запись GTA 5 без места — пометка.
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import content_engine as ce  # noqa: E402
import content_package as cp  # noqa: E402
import main  # noqa: E402
from auth import create_token  # noqa: E402
from content_db import ContentPackage  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from test_content_package import _собрать, стенд  # noqa: E402,F401

ОТКАЗ_402 = ("service: сервис моделей вернул ошибку (code=402): This request requires more credits, "
             "or fewer max_tokens. You requested up to 12000 tokens, but can only afford 3400. "
             "To increase, visit https://openrouter.ai/settings/credits and add more credits. "
             "This request would exceed your available credits")


def _пересобрать_с_402(стенд, monkeypatch):
    исходная = ce._спросить

    async def с_отказом(клиент, инструмент, система, вопрос, *а, **кв):
        if "Сценарий ролика" in вопрос:
            return None, ОТКАЗ_402
        return await исходная(клиент, инструмент, система, вопрос, *а, **кв)
    monkeypatch.setattr(ce, "_спросить", с_отказом)
    db = стенд["Сессия"]()
    итог = cp.начать(db, стенд["ид"]["идея"], заново=True)
    db.close()
    assert итог.get("ok"), итог
    asyncio.run(стенд["запущено"][-1][1]("probe"))
    db = стенд["Сессия"]()
    п = db.get(ContentPackage, итог["id"])
    db.expunge(п)
    db.close()
    return п


# ── 1.1 ───────────────────────────────────────────────────────────────

def test_ошибка_пересборки_оставляет_прошлую_версию_и_плашку(стенд, monkeypatch):
    п = _собрать(стенд)
    assert п.state == "ok"
    было = json.loads(п.data)
    п2 = _пересобрать_с_402(стенд, monkeypatch)
    assert п2.id == п.id and п2.state == "ok"
    assert json.loads(п2.data)["script"] == было["script"]
    assert п2.rebuild_error == "на счёте OpenRouter не хватает денег"
    клиент = TestClient(main.app)
    клиент.cookies.set("access_token", create_token(стенд["ид"]["админ"], 0))
    r = клиент.get(f"/content/package/{п.id}")
    assert r.status_code == 200
    assert ("Пересборка не удалась: на счёте OpenRouter не хватает денег, показана прошлая версия"
            in r.text)
    assert "Что показали в трейлере" in r.text


def test_подлог_без_защиты_пересборка_стирает_пакет(стенд, monkeypatch):
    _собрать(стенд)
    monkeypatch.setattr(cp, "_прошлая_версия", lambda п: None)
    п2 = _пересобрать_с_402(стенд, monkeypatch)
    assert п2.state == "error" and п2.data is None and not п2.rebuild_error


def test_удачная_пересборка_снимает_плашку(стенд, monkeypatch):
    _собрать(стенд)
    п2 = _пересобрать_с_402(стенд, monkeypatch)
    assert п2.rebuild_error
    monkeypatch.setattr(ce, "_спросить", стенд["модель"])
    db = стенд["Сессия"]()
    итог = cp.начать(db, стенд["ид"]["идея"], заново=True)
    db.close()
    asyncio.run(стенд["запущено"][-1][1]("probe"))
    db = стенд["Сессия"]()
    п3 = db.get(ContentPackage, итог["id"])
    assert п3.state == "ok" and п3.rebuild_error is None
    db.close()


def test_причина_словами():
    assert cp.причина_словами(ОТКАЗ_402) == "на счёте OpenRouter не хватает денег"
    assert cp.причина_словами("сервис моделей не ответил (ReadTimeout)") == "сервис моделей не ответил"
    assert cp.причина_словами("в сценарии нет сегментов") == "в сценарии нет сегментов"


# ── 1.2 ───────────────────────────────────────────────────────────────

ЛЮДИ = ("Люди Rockstar:\n"
        "- Аарон Гарбут (Aaron Garbut) — разработчик Rockstar Games, его цитирует Game Informer.\n"
        "- Оуэн Шеппард (Owen Shepherd) — разработчик Rockstar Games, его цитирует Game Informer.\n"
        "- Майкл Кейн (Michael Kane) — разработчик Rockstar Games, его цитирует Game Informer.")


def _к(база="", трейлеры=None, сбой=None):
    return {"база": база, "источники": [], "образцы": [], "трейлеры": трейлеры or [],
            "трейлеры_сбой": сбой or []}


СЪЁМКА_ЛЮДИ = [{"what": "Скриншот статьи с цитатой Оуэна Шеппарда и Майкла Кейна про погоду, слова Гарбута",
                "source": "Newswire", "where": "скриншот статьи Game Informer", "basis": "kb", "for": "0:30"}]


def test_склонённые_имена_людей_rockstar_не_выдумка():
    итог = cp.обосновать_съёмки(СЪЁМКА_ЛЮДИ, _к(ЛЮДИ))
    assert итог[0]["note"] == "" and not итог[0]["what"].startswith("найди")


def test_подлог_без_раздела_люди_имена_выдумка():
    итог = cp.обосновать_съёмки(СЪЁМКА_ЛЮДИ, _к(""))
    assert "Шеппарда" in итог[0]["note"]


def test_раздел_люди_rockstar_в_досеве():
    семя = json.load(open(os.path.join(os.path.dirname(__file__), "..", "content_seed.json"), encoding="utf-8"))
    доп = семя["knowledge_add"]
    assert доп["v"] >= 4 and len(доп["sections"]["Люди Rockstar"]) == 3
    import content_db as cdb
    текст = cdb.дописать_разделы("Мой текст владельца.", {"Люди Rockstar": доп["sections"]["Люди Rockstar"]})
    assert текст.startswith("Мой текст владельца.") and "Оуэн Шеппард" in текст


# ── 1.3 ───────────────────────────────────────────────────────────────

ТРЕЙЛЕР = {"yt_id": "VQRLujxTm3c", "title": "Grand Theft Auto VI Trailer 2", "scenes": [
    {"t": "1:11", "what": "Джейсон и Люсия целуются в постели"},
    {"t": "0:55", "what": "Мужчина убегает от полиции на автозаправке во время дождя"}]}


def test_кадр_трейлера_без_таймкода_не_принят():
    съём = [{"what": "Нарезка-сравнение: ливень в GTA 5 рядом с дождём в трейлере 6",
             "source": "GTA 5 | трейлер", "where": "мужчина убегает от полиции", "basis": "", "for": "0:00"}]
    итог = cp.обосновать_съёмки(съём, _к(трейлеры=[ТРЕЙЛЕР]))
    assert итог[0]["what"].startswith("найди в трейлере")
    assert итог[0]["note"] == "нет таймкода из разбора трейлера"


def test_кадр_трейлера_с_таймкодом_номер_и_таймкод_в_где():
    съём = [{"what": "Поцелуй пары", "source": "трейлер", "where": "", "basis": "trailer:VQRLujxTm3c@1:11",
             "for": "4:10"}]
    итог = cp.обосновать_съёмки(съём, _к(трейлеры=[ТРЕЙЛЕР]))
    assert итог[0]["note"] == "" and итог[0]["where"].startswith("Grand Theft Auto VI Trailer 2, 1:11")


def test_подлог_своя_запись_gta5_принимается_без_таймкода():
    съём = [{"what": "Дождь в GTA 5: персонаж бежит по мокрой улице", "source": "GTA 5",
             "where": "Лос-Сантос под дождём", "basis": "gameplay", "for": "1:10"}]
    итог = cp.обосновать_съёмки(съём, _к(трейлеры=[ТРЕЙЛЕР]))
    assert итог[0]["note"] == "" and итог[0]["what"] == съём[0]["what"]


def test_своя_запись_gta5_без_места_помечена():
    съём = [{"what": "Звонок другу в GTA 5", "source": "GTA 5", "where": "", "basis": "gameplay", "for": "3:40"}]
    итог = cp.обосновать_съёмки(съём, _к(трейлеры=[ТРЕЙЛЕР]))
    assert итог[0]["note"] == "назови место или действие для своей записи"


def test_графика_помечена_с_текстом_плашки():
    съём = [{"what": "Текстом про отношения: союз героев нельзя разорвать", "source": "Newswire",
             "where": "плашка про влияние игрока на отношения", "basis": "", "for": "3:40"},
            {"what": "Финальный монтаж: GTA 5 слева, GTA 6 справа", "source": "GTA 5 | трейлер",
             "where": "Лос-Сантос", "basis": "", "for": "5:10"}]
    итог = cp.обосновать_съёмки(съём, _к(трейлеры=[ТРЕЙЛЕР]))
    assert итог[0]["what"] == "графика: союз героев нельзя разорвать" and итог[0]["source"] == "графика"
    assert итог[1]["what"] == "графика: GTA 5 слева, GTA 6 справа" and not итог[1]["note"]


def test_разбор_недоступен_прежнее_правило_не_сверен():
    съём = [{"what": "Поцелуй пары", "source": "трейлер", "where": "", "basis": "", "for": "4:10"}]
    итог = cp.обосновать_съёмки(съём, _к(трейлеры=[], сбой=["квота"]))
    assert "не сверен" in итог[0]["unverified"] and not итог[0]["what"].startswith("найди")
