"""Пакет ролика (письмо B, блок 2).

Сети нет: модель — подменённый `content_engine._спросить`, отвечающий по
тому, какой блок у неё спросили. База своя, в памяти. Негативные контроли
письма, у каждого обратный случай:
1. СТОП-СЛОВО в названии — перегенерация, в итоге его нет; модель упорствует —
   такие названия выкинуты кодом.
2. ФРАЗА-ФАКТ БЕЗ ИСТОЧНИКА (и с номером не из набора) — «проверь»; с номером
   записи — нет. Слух, поданный как «официально», — «проверь».
3. СЮЖЕТ С УТЕЧКОЙ — в списке съёмок нет кадров утечки, есть предупреждение.
4. ОШИБКА НА ШАГЕ «Сценарий» — пакет «ошибка» с текстом, сборка снова доступна.
5. ПОВТОРНОЕ ОТКРЫТИЕ пакета — ни одного вызова модели.
6. БЮДЖЕТ ИСЧЕРПАН — текст вместо сборки.

Письмо B2, блок 1:
7. «ВПЕРВЫЕ В СЕРИИ» без источника — подсвечено, даже если проверщик фактов
   его не выписал; с опорой на пункт базы — нет.
8. ФРАЗА ПРОТИВ БАЗЫ ЗНАНИЙ — переписана; проверщик выдумал опору (номер не
   из набора, пункта базы нет) — «проверь».
9. ТРИ ФАКТА в источниках — предложение Shorts или ролика до 5 минут; десять —
   нет.
10. СЮЖЕТ С ЗАПИСЬЮ GAME INFORMER — она первая в источниках пакета; запись
   первоисточника из соседнего сюжета той же волны — тоже первая.
"""
import re
import asyncio
import json
import os
from datetime import datetime, timedelta

os.environ.setdefault("DB_PATH", "./test_model_usage.db")
os.environ.setdefault("AGENT_WEBHOOK_KEY", "test-key-8f3a91")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import content_db as cdb  # noqa: E402
import content_engine as ce  # noqa: E402
import content_package as cp  # noqa: E402
import content_worker as cw  # noqa: E402
import database  # noqa: E402
import main  # noqa: E402
from auth import create_token, hash_password  # noqa: E402
from content_db import (ContentFormat, ContentIdea, ContentItem, ContentPackage, ContentRef,  # noqa: E402
                        ContentStory, ContentVideo)


class Модель:
    """Отвечает по блоку; `поведение` правится тестом."""

    def __init__(self):
        self.вызовы = []
        self.поведение = {"стоп_раз": 0, "всегда_стоп": False, "сбой_сценария": False,
                          "факты": 6, "опора": {}, "доп_строки": [], "волна": None}
        self.Сессия = None

    async def __call__(self, клиент, инструмент, система, вопрос, потолок, модель=None, температура=0):
        self.вызовы.append(вопрос[:40])
        if self.Сессия is not None:
            db = self.Сессия()
            db.add(database.ModelUsage(tool=инструмент, model=модель or "m", cost=0.01, ok=True,
                                       created_at=datetime.utcnow()))
            db.commit()
            db.close()
        if "Записи СМИ за те же дни" in вопрос:
            if self.поведение["волна"] is None:
                return None, "волну не спрашивали"
            return json.dumps({"same": self.поведение["волна"]}), None
        if "Выпиши УНИКАЛЬНЫЕ факты" in вопрос:
            return json.dumps({"facts": [{"text": f"Факт номер {n}", "src": [self.ид["офиц"]]}
                                         for n in range(self.поведение["факты"])]}), None
        if "Ты фактчекер" in вопрос:
            утв = []
            for ключ, текст in re.findall(r"^(S\d+\.L\d+): (.*)$", вопрос, re.M):
                опора = self.поведение["опора"].get(текст)
                if опора is None and текст == "Трейлер вышел вчера.":
                    опора = {"src": [self.ид["офиц"]]}
                if опора is not None:
                    утв.append({"line": ключ, "claim": текст, "src": [], "kb": [], "contradicts": None,
                                "fix": "", **опора})
            return json.dumps({"claims": утв}), None
        if "Дай 3 названия" in вопрос:
            if self.поведение["всегда_стоп"] or self.поведение["стоп_раз"] > 0:
                self.поведение["стоп_раз"] -= 1
                return json.dumps({"titles": ["Деньги бесплатно в GTA 6", "Бонус от Rockstar", "FREE money glitch"],
                                   "thumbnail": {"frame": "Джейсон", "screenshot": "трейлер 2",
                                                 "text": "Бесплатно для всех игроков"}}), None
            return json.dumps({"titles": ["Что показали в трейлере", "Три детали трейлера", "Где это место"],
                               "thumbnail": {"frame": "Люсия у машины", "screenshot": "трейлер 2, 0:45",
                                             "text": "Ты это заметил пять слов"}}), None
        if "Сценарий ролика" in вопрос:
            if self.поведение["сбой_сценария"]:
                return None, "сервис моделей не ответил (ReadTimeout)"
            return json.dumps({"hook": {"text": "Rockstar спрятала в трейлере деталь.", "shown": "кадр трейлера"},
                               "segments": [
                                   {"from": "0:00", "to": "0:30", "role": "крючок", "purpose": "зацепить",
                                    "lines": [{"text": "Трейлер вышел вчера.", "fact": True, "src": [self.ид["офиц"]]},
                                              {"text": "Ты это видел?", "fact": False, "src": []}]},
                                   {"from": "0:30", "to": "9:40", "role": "пик", "purpose": "главное",
                                    "lines": [{"text": "Релиз перенесли на осень.", "fact": True, "src": []},
                                              {"text": "Карта больше вдвое.", "fact": True, "src": [999999]},
                                              {"text": "Rockstar официально подтвердила карту.", "fact": True,
                                               "src": [self.ид["слух"]]}] + self.поведение["доп_строки"]}]}), None
        if "Список съёмок" in вопрос:
            return json.dumps({"shots": [{"what": "Кадры утечки 2022 года", "source": "утечка", "where": "", "for": "0:30"},
                                         {"what": "Геймплей Вайс-Сити в GTA 5", "source": "GTA 5", "where": "Вайнвуд", "for": "0:30"},
                                         {"what": "Трейлер 2", "source": "трейлер", "where": "0:45", "for": "0:00"}]}), None
        return None, "неизвестный вопрос"


@pytest.fixture
def стенд(monkeypatch):
    движок = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    database.Base.metadata.create_all(движок)
    Сессия = sessionmaker(bind=движок)
    db = Сессия()
    админ = database.User(email="adm@pack.test", password_hash=hash_password("x-123456"),
                          is_verified=True, is_admin=True)
    db.add(админ)
    cdb.засеять(db)
    ф = db.query(ContentFormat).filter(ContentFormat.status == "active").order_by(ContentFormat.sort).first()
    сейчас = datetime.utcnow()
    с = ContentStory(theme_id=ф.theme_id, title="Трейлер 2 GTA 6", summary="вышел второй трейлер",
                     first_seen_at=сейчас - timedelta(hours=5), items=2, sources=2, leak=True)
    db.add(с)
    db.flush()
    офиц = ContentItem(theme_id=ф.theme_id, ext_id="rockstar:1", source_id=1, source_key="rockstar:1",
                       source_name="Rockstar Newswire", platform="rockstar", url="https://rockstargames.test/1",
                       title="Trailer 2", official=True, first_seen_at=сейчас, last_seen_at=сейчас,
                       published_at=сейчас, story_id=с.id)
    слух = ContentItem(theme_id=ф.theme_id, ext_id="rss:2", source_id=2, source_key="rss:2",
                       source_name="Insider", platform="rss", url="https://insider.test/2",
                       title="Map is huge", rumor=True, first_seen_at=сейчас, last_seen_at=сейчас,
                       published_at=сейчас, story_id=с.id)
    db.add_all([офиц, слух])
    db.add(ContentRef(theme_id=ф.theme_id, format_id=ф.id, yt_id="ref1", title="GTA 5 разбор трейлера",
                      channel_title="Канал", lang="ru", origin="arch", shot=5.0, state="ok",
                      analysis=json.dumps({"hook": {"said": "смотри", "trick": "вопрос"},
                                           "segments": [{"from": "0:00", "to": "1:00", "role": "завязка", "what": "повод"}]})))
    идея = ContentIdea(theme_id=ф.theme_id, run_id=1, kind="long", sort="hot", title="Разбор трейлера 2",
                       why="свежий трейлер", format_id=ф.id, story_id=с.id,
                       facts=json.dumps({"официально": False}), risks=json.dumps(["leak"]), state="new")
    db.add(идея)
    db.commit()
    ид = {"офиц": офиц.id, "слух": слух.id, "идея": идея.id, "админ": админ.id, "pwd": 0}
    db.close()

    модель = Модель()
    модель.ид = ид
    модель.Сессия = Сессия
    monkeypatch.setattr(ce, "_спросить", модель)
    monkeypatch.setattr(main, "SessionLocal", Сессия)
    monkeypatch.setattr(ce, "SessionLocal", Сессия)
    monkeypatch.setenv("CONTENT_SCHEDULER", "0")
    # исполнитель — синхронно в этом же потоке: тест ждёт итог, а не поток
    запущено = []
    monkeypatch.setattr(cw, "запустить", lambda вид, фабрика, повод: (запущено.append((вид, фабрика)) or {"ok": True}))

    def _db():
        s = Сессия()
        try:
            yield s
        finally:
            s.close()
    main.app.dependency_overrides[main.get_db] = _db
    yield {"Сессия": Сессия, "модель": модель, "ид": ид, "запущено": запущено}
    main.app.dependency_overrides.clear()


def _собрать(стенд) -> ContentPackage:
    db = стенд["Сессия"]()
    итог = cp.начать(db, стенд["ид"]["идея"])
    db.close()
    assert итог.get("ok"), итог
    вид, фабрика = стенд["запущено"][-1]
    asyncio.run(фабрика("probe"))
    db = стенд["Сессия"]()
    п = db.get(ContentPackage, итог["id"])
    db.expunge(п)
    db.close()
    return п


def test_стоп_слово_перегенерация_в_итоге_его_нет(стенд):
    стенд["модель"].поведение["стоп_раз"] = 1
    п = _собрать(стенд)
    д = json.loads(п.data)
    assert п.state == "ok", п.note
    assert д["titles"] == ["Что показали в трейлере", "Три детали трейлера", "Где это место"]
    assert sum(1 for в in стенд["модель"].вызовы if "Ролик:" in в) == 2      # перегенерация была
    assert len(д["thumbnail"]["text"].split()) <= 4
    проверка = {п2["item"]: п2 for п2 in д["check"]}
    assert проверка["Стоп-слова в названиях"]["ok"] is True


def test_модель_упорствует_стоп_слова_выкинуты_кодом(стенд):
    стенд["модель"].поведение["всегда_стоп"] = True
    п = _собрать(стенд)
    assert п.state == "error" and "стоп-слова" in п.note
    assert п.data is None


def test_факт_без_источника_подсвечен_проверь(стенд):
    п = _собрать(стенд)
    строки = {л["text"]: л for с in json.loads(п.data)["script"] for л in с["lines"]}
    assert строки["Трейлер вышел вчера."]["check"] is None
    assert строки["Ты это видел?"]["check"] is None
    assert строки["Релиз перенесли на осень."]["check"] == "нет источника"
    assert строки["Карта больше вдвое."]["check"] == "нет источника"         # номер не из набора
    assert строки["Карта больше вдвое."]["src"] == []
    assert строки["Rockstar официально подтвердила карту."]["check"] == "слух подан как подтверждённый"


def test_утечка_в_съёмках_нет_кадров_утечки_есть_предупреждение(стенд):
    д = json.loads(_собрать(стенд).data)
    assert д["shots_warning"] and "НЕЛЬЗЯ" in д["shots_warning"]
    assert all("утечк" not in (с["what"] + с["source"]).lower() for с in д["shots"])
    assert len(д["shots"]) == 2
    assert {п2["item"]: п2["ok"] for п2 in д["check"]}["Нет кадров утечек"] is True


def test_без_утечки_предупреждения_нет(стенд):
    """Обратный случай: сюжет без утечки — кадры не вычищаются, предупреждения нет."""
    db = стенд["Сессия"]()
    for с in db.query(ContentStory):
        с.leak = False
    идея = db.get(ContentIdea, стенд["ид"]["идея"])
    идея.risks = "[]"
    db.commit()
    db.close()
    д = json.loads(_собрать(стенд).data)
    assert д["shots_warning"] is None and len(д["shots"]) == 3


def test_ошибка_на_сценарии_статус_ошибки_и_сборка_снова_доступна(стенд):
    стенд["модель"].поведение["сбой_сценария"] = True
    п = _собрать(стенд)
    assert п.state == "error" and "ReadTimeout" in п.note
    шаги = {ш["k"]: ш["done"] for ш in json.loads(п.steps)}
    assert шаги["titles"] is True and шаги["script"] is False and шаги["check"] is False
    стенд["модель"].поведение["сбой_сценария"] = False
    п2 = _собрать(стенд)
    assert п2.id == п.id and п2.state == "ok"


def test_повторное_открытие_без_вызовов_модели(стенд):
    п = _собрать(стенд)
    вызовов = len(стенд["модель"].вызовы)
    db = стенд["Сессия"]()
    assert cp.начать(db, стенд["ид"]["идея"]) == {"ok": True, "id": п.id, "ready": True}
    db.close()
    клиент = TestClient(main.app)
    клиент.cookies.set("access_token", create_token(стенд["ид"]["админ"], 0))
    r = клиент.get(f"/content/package/{п.id}")
    assert r.status_code == 200 and "Что показали в трейлере" in r.text and "проверь: нет источника" in r.text
    md = клиент.get(f"/content/package/{п.id}/download")
    assert md.status_code == 200 and "## Сценарий" in md.text and "ПРОВЕРЬ" in md.text
    assert len(стенд["модель"].вызовы) == вызовов
    assert п.cost and п.cost > 0


def test_бюджет_исчерпан_текст_вместо_сборки(стенд):
    db = стенд["Сессия"]()
    db.add(database.ModelUsage(tool="admin-content-ideas", model="m", cost=5.0, ok=True,
                               created_at=datetime.utcnow()))
    db.commit()
    итог = cp.начать(db, стенд["ид"]["идея"])
    assert итог["code"] == 409 and "Бюджет модели на сегодня исчерпан" in итог["error"]
    assert db.query(ContentPackage).count() == 0 and стенд["запущено"] == []
    db.close()


def test_отметить_снимаю_переводит_в_конвейер(стенд):
    п = _собрать(стенд)
    db = стенд["Сессия"]()
    assert cp.отметить_снимаю(db, п.id)["status"] == "writing"
    р = db.query(ContentVideo).filter(ContentVideo.idea_id == стенд["ид"]["идея"]).one()
    assert р.status == "writing"
    db.close()


# ── письмо B2, блок 1 ──────────────────────────────────────────────────

def _строки(п):
    return {л["text"]: л for с in json.loads(п.data)["script"] for л in с["lines"]}


def test_впервые_в_серии_без_источника_подсвечено(стенд):
    стенд["модель"].поведение["доп_строки"] = [
        {"text": "Раньше в серии такого не было.", "fact": False, "src": []},
        {"text": "Впервые герои — пара.", "fact": False, "src": []}]
    стенд["модель"].поведение["опора"] = {"Впервые герои — пара.": {"kb": ["K1"]}}
    п = _собрать(стенд)
    строки = _строки(п)
    assert строки["Раньше в серии такого не было."]["check"] == "громкое утверждение без подтверждённой опоры"
    assert строки["Впервые герои — пара."]["check"] is None and строки["Впервые герои — пара."]["kb"] == ["K1"]
    фп = json.loads(п.data)["factcheck"]
    assert фп["done"] and фп["loud"] == 1
    проверка = {п2["item"]: п2 for п2 in json.loads(п.data)["check"]}
    assert проверка["Утверждения без подтверждения"]["ok"] is None


def test_фраза_против_базы_переписана_выдуманная_опора_проверь(стенд):
    стенд["модель"].поведение["доп_строки"] = [
        {"text": "Джейсон Люсия — одна героиня.", "fact": True, "src": []},
        {"text": "Карта как в San Andreas.", "fact": True, "src": []}]
    стенд["модель"].поведение["опора"] = {
        "Джейсон Люсия — одна героиня.": {"contradicts": "K1", "fix": "Джейсон и Люсия — пара героев."},
        "Карта как в San Andreas.": {"src": [424242], "kb": ["K999"]}}
    п = _собрать(стенд)
    строки = _строки(п)
    assert "Джейсон Люсия — одна героиня." not in строки
    новая = строки["Джейсон и Люсия — пара героев."]
    assert новая["check"] is None and "противоречило базе" in новая["fixed"]
    assert строки["Карта как в San Andreas."]["check"] == "нет источника"
    assert строки["Карта как в San Andreas."]["src"] == []
    assert json.loads(п.data)["factcheck"]["fixed"] == 1


def test_три_факта_предложение_shorts_или_до_5_минут(стенд):
    стенд["модель"].поведение["факты"] = 3
    п = _собрать(стенд)
    мат = json.loads(п.data)["material"]
    assert мат["facts"] == 3 and мат["minutes"] <= 5 and "Shorts" in мат["suggest"]
    md = cp.в_markdown(п)
    assert "Фактов в источниках: 3" in md and "Shorts" in md


def test_десять_фактов_предложения_нет(стенд):
    стенд["модель"].поведение["факты"] = 10
    п = _собрать(стенд)
    мат = json.loads(п.data)["material"]
    assert мат["facts"] == 10 and мат["suggest"] is None and мат["minutes"] >= 8


def _добавить(стенд, **поля):
    db = стенд["Сессия"]()
    сейчас = datetime.utcnow()
    и = ContentItem(theme_id=db.query(ContentStory).first().theme_id, source_id=9, platform="rss",
                    first_seen_at=сейчас, last_seen_at=сейчас, published_at=сейчас - timedelta(hours=3),
                    **поля)
    db.add(и)
    db.commit()
    номер = и.id
    db.close()
    return номер


def test_запись_game_informer_в_сюжете_первая(стенд):
    сюжет = стенд["Сессия"]().query(ContentStory).first().id
    gi = _добавить(стенд, ext_id="rss:gi1", source_key="rss:9", source_name="Game Informer",
                   url="https://gameinformer.test/1", title="GTA VI cover story", story_id=сюжет)
    п = _собрать(стенд)
    д = json.loads(п.data)
    assert д["src"][0]["id"] == gi and д["src"][0]["role"] == "первоисточник волны"
    assert д["sources"][0]["id"] == gi


def test_первоисточник_из_соседнего_сюжета_волны_первый(стенд):
    gi = _добавить(стенд, ext_id="rss:gi2", source_key="rss:9", source_name="Game Informer",
                   url="https://gameinformer.test/2", title="The Grand Theft Auto VI Digital Issue Is Now Live",
                   text="14-page cover story with new details on Leonida", story_id=None)
    ign = _добавить(стенд, ext_id="rss:ign1", source_key="rss:10", source_name="IGN",
                    url="https://ign.test/1", title="All the new GTA 6 trailer details",
                    text="details revealed in the latest Game Informer cover story", story_id=None)
    чужое = _добавить(стенд, ext_id="rss:ign2", source_key="rss:10", source_name="IGN",
                      url="https://ign.test/2", title="Modder gets cease and desist", story_id=None)
    стенд["модель"].поведение["волна"] = [ign]           # модель узнала пересказ, но не первоисточник
    п = _собрать(стенд)
    ид = [и["id"] for и in json.loads(п.data)["src"]]
    assert ид[0] == gi and ign in ид and чужое not in ид


def test_волна_без_модели_по_словам(стенд):
    ign = _добавить(стенд, ext_id="rss:ign3", source_key="rss:10", source_name="IGN",
                    url="https://ign.test/3", title="Trailer 2 frame by frame", story_id=None)
    стенд["модель"].поведение["волна"] = None              # модель не ответила — запасной отбор
    п = _собрать(стенд)
    assert ign not in [и["id"] for и in json.loads(п.data)["src"]]   # «trailer» — общее слово темы
    шаги = {ш["k"]: ш["note"] for ш in json.loads(п.steps)}
    assert "волна по словам" in шаги["sources"]
