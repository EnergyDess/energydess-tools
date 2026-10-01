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

Письмо B2, блок 2:
11. «ПО СЛУХАМ» ДВАЖДЫ в разделе — раздел переписан; модель упорствует
   с запрещённой фразой — строка помечена «язык: …».
12. ВЫДУМАННАЯ СЦЕНА в списке съёмок — «найди в трейлере: …»; сцена трейлера
   с настоящим таймкодом и место из базы знаний — остаются.
13. ПРЕВЬЮ ДЛИННЕЕ 4 СЛОВ — переписано моделью, не обрезано; модель
   упорствует — текст целиком и пометка «перепиши».
14. БЮДЖЕТ сохраняется полем «Кухни»; досев меняет прежнее 1.0 на 2.0,
   своё значение владельца не трогает. Стиль уходит в модель дословно.
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
        self.системы = []
        self.поведение = {"стоп_раз": 0, "всегда_стоп": False, "сбой_сценария": False,
                          "факты": 6, "опора": {}, "доп_строки": [], "волна": None,
                          "упорствует": False, "превью_упорно": False, "съёмки": None}
        self.Сессия = None

    async def __call__(self, клиент, инструмент, система, вопрос, потолок, модель=None, температура=0):
        self.вызовы.append(вопрос[:40])
        self.системы.append(система)
        if self.Сессия is not None:
            db = self.Сессия()
            db.add(database.ModelUsage(tool=инструмент, model=модель or "m", cost=0.01, ok=True,
                                       created_at=datetime.utcnow()))
            db.commit()
            db.close()
        if "Перепиши раздел сценария" in вопрос:
            if self.поведение["упорствует"]:
                строки = re.findall(r"^- (.*) \(fact:", вопрос, re.M)
                return json.dumps({"lines": [{"text": т, "fact": False, "src": []} for т in строки]}), None
            return json.dumps({"lines": [{"text": "По слухам Insider, карта большая.", "fact": True,
                                          "src": [self.ид["слух"]]},
                                         {"text": "Посмотрим, что скажет Rockstar.", "fact": False, "src": []}]}), None
        if "Текст на превью" in вопрос:
            return json.dumps({"text": "Шесть слов на превью это много" if self.поведение["превью_упорно"]
                               else "Ты это заметил"}), None
        if "Перепиши крючок" in вопрос:
            return json.dumps({"text": "Rockstar спрятала деталь."}), None
        if "Записи СМИ за те же дни" in вопрос:
            if self.поведение["волна"] is None:
                return None, "волну не спрашивали"
            return json.dumps({"same": self.поведение["волна"]}), None
        if "Выпиши УНИКАЛЬНЫЕ факты" in вопрос and self.поведение.get("факты_список") is not None:
            return json.dumps({"facts": self.поведение["факты_список"]}), None
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
        if "Дай 3 названия" in вопрос and self.поведение.get("названия"):
            return json.dumps({"titles": self.поведение["названия"].pop(0),
                               "thumbnail": {"frame": "кадр", "screenshot": "трейлер", "text": "Звери GTA 6"}}), None
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
        if "Список съёмок" in вопрос and self.поведение["съёмки"] is not None:
            return json.dumps({"shots": self.поведение["съёмки"]}), None
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


def test_четыре_факта_предложение_shorts_длинный_не_собран(стенд):
    """B3, 2.1 (было B2: три факта — «до 5 минут»): меньше 6 фактов — пакет
    останавливается на предложении Shorts, сценария нет; выбор «длинный»
    собирает длинный, «Shorts» — короткий."""
    стенд["модель"].поведение["факты"] = 4
    п = _собрать(стенд)
    assert п.state == "suggest"
    д = json.loads(п.data)
    assert д["material"]["facts"] == 4 and д["material"]["shorts"] and "Shorts" in д["material"]["suggest"]
    assert "script" not in д and not any("Сценарий ролика" in в for в in стенд["модель"].вызовы)
    с = TestClient(main.app)
    с.cookies.set("access_token", create_token(стенд["ид"]["админ"], 0))
    стр = с.get(f"/content/package/{п.id}").text
    assert 'data-kind="shorts"' in стр and 'data-kind="long"' in стр
    for вид, ждём in (("long", "long"), ("shorts", "shorts")):
        db = стенд["Сессия"]()
        итог = cp.начать(db, стенд["ид"]["идея"], заново=True, вид=вид)
        db.close()
        asyncio.run(стенд["запущено"][-1][1]("probe"))
        db = стенд["Сессия"]()
        п2 = db.get(ContentPackage, итог["id"])
        assert п2.state == "ok" and п2.kind == ждём, (п2.state, п2.note)
        assert json.loads(п2.data)["script"]
        db.close()


def test_шкала_длины_по_фактам_и_из_настроек():
    """B3, 2.1: 13 фактов — 8–10 минут, 7 — 5–7, 25 — до 12; шкала из настроек
    «Кухни» меняет результат."""
    assert cp.длина_по_фактам(4, "long", {})["shorts"]
    assert cp.длина_по_фактам(7, "long", {})["range"] == "5–7 минут"
    assert cp.длина_по_фактам(13, "long", {})["range"] == "8–10 минут"
    assert cp.длина_по_фактам(25, "long", {})["range"] == "до 12 минут"
    своя = {"length": {"shorts_below": 3, "steps": [{"upto": 5, "min": 2, "max": 3},
                                                     {"upto": None, "min": 4, "max": 6}]}}
    assert not cp.длина_по_фактам(4, "long", своя).get("shorts")
    assert cp.длина_по_фактам(4, "long", своя)["range"] == "2–3 минут"
    assert cp.длина_по_фактам(13, "long", своя)["range"] == "до 6 минут"


def test_шкала_длины_сохраняется_полем_кухни(стенд):
    с = TestClient(main.app)
    с.cookies.set("access_token", create_token(стенд["ид"]["админ"], 0))
    r = с.post("/content/api/settings/length", json={"shorts_below": 4, "mid_upto": 10, "mid_min": 4,
                                                     "mid_max": 6, "long_upto": 18, "long_min": 7,
                                                     "long_max": 9, "max_min": 9, "max_max": 11})
    assert r.status_code == 200, r.text
    db = стенд["Сессия"]()
    н = cdb.настройка(db, "package")
    db.close()
    assert cp.длина_по_фактам(5, "long", н)["range"] == "4–6 минут"
    assert с.post("/content/api/settings/length", json={"shorts_below": 4, "mid_upto": 3, "mid_min": 4,
                                                        "mid_max": 6, "long_upto": 18, "long_min": 7,
                                                        "long_max": 9, "max_min": 9,
                                                        "max_max": 11}).status_code == 400


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


def test_первоисточник_из_сюжета_найденной_записи_волны(стенд):
    """Без модели: запись волны найдена по словам, первоисточник её сюжета —
    добран кодом, хотя слов общих с сюжетом пакета у него нет."""
    db = стенд["Сессия"]()
    тема = db.query(ContentStory).first().theme_id
    чужой = ContentStory(theme_id=тема, title="Обложка журнала", first_seen_at=datetime.utcnow())
    db.add(чужой)
    db.commit()
    сюжет_волны = чужой.id
    db.close()
    gi = _добавить(стенд, ext_id="rss:gi4", source_key="rss:9", source_name="Game Informer",
                   url="https://gameinformer.test/4", title="The Digital Issue Is Now Live", story_id=сюжет_волны)
    ign = _добавить(стенд, ext_id="rss:ign4", source_key="rss:10", source_name="IGN",
                    url="https://ign.test/4", title="Map is huge, insiders say", story_id=сюжет_волны)
    п = _собрать(стенд)
    ид = [и["id"] for и in json.loads(п.data)["src"]]
    assert ид[0] == gi and ign in ид


# ── письмо B2, блок 2 ──────────────────────────────────────────────────

def test_по_слухам_дважды_раздел_переписан(стенд):
    стенд["модель"].поведение["доп_строки"] = [
        {"text": "По слухам, будут ураганы.", "fact": False, "src": []},
        {"text": "Якобы и торнадо тоже.", "fact": False, "src": []}]
    п = _собрать(стенд)
    д = json.loads(п.data)
    второй = " ".join(л["text"] for л in д["script"][1]["lines"])
    assert "Якобы и торнадо тоже." not in второй and len(cp.СЛУХ_ОБОРОТ.findall(второй)) <= 1
    assert д["language"]["rewritten"] >= 1 and д["language"]["left"] == 0
    assert any("Перепиши раздел" in в for в in стенд["модель"].вызовы)
    проверка = {п2["item"]: п2 for п2 in д["check"]}
    assert проверка["Запрещённые фразы и «по слухам»"]["ok"] is True


def test_запрещённая_фраза_упорно_помечена(стенд):
    стенд["модель"].поведение["доп_строки"] = [{"text": "Это другой уровень.", "fact": False, "src": []}]
    стенд["модель"].поведение["упорствует"] = True
    п = _собрать(стенд)
    д = json.loads(п.data)
    строки = _строки(п)
    assert "язык: «другой уровень»" in строки["Это другой уровень."]["check"]
    assert д["language"]["left"] == 1
    assert sum(1 for в in стенд["модель"].вызовы if "Перепиши раздел" in в) == 2   # rewrite_tries
    assert {п2["item"]: п2["ok"] for п2 in д["check"]}["Запрещённые фразы и «по слухам»"] is None


def test_выдуманная_сцена_найди_в_трейлере(стенд, monkeypatch):
    async def трейлеры(клиент, db, тема, настройки, сбои=None):
        return [{"yt_id": "VQRLujxTm3c", "title": "Grand Theft Auto VI Trailer 2",
                 "scenes": [{"t": "0:45", "what": "Люсия у машины на пляже"}]}]
    monkeypatch.setattr(cp, "сцены_трейлеров", трейлеры)
    стенд["модель"].поведение["съёмки"] = [
        {"what": "Сцена на заправке", "source": "трейлер", "where": "", "basis": "trailer:VQRLujxTm3c@2:10", "for": "1:00"},
        {"what": "Прогулка по пляжу", "source": "GTA 5", "where": "Виши-Бич", "basis": "gameplay", "for": "2:00"},
        {"what": "Люсия у машины", "source": "трейлер", "where": "0:45", "basis": "trailer:VQRLujxTm3c@0:45", "for": "0:30"},
        {"what": "Проезд по городу", "source": "GTA 5", "where": "Лос-Сантос", "basis": "kb", "for": "3:00"}]
    п = _собрать(стенд)
    съём = json.loads(п.data)["shots"]
    assert съём[0]["what"] == "найди в трейлере: Сцена на заправке" and съём[0]["note"]
    # B3, 2.2 (было B2: заменялось): строку GTA 5 ведущий записывает сам — не сверяется
    assert съём[1]["what"] == "Прогулка по пляжу" and not съём[1]["note"]
    assert съём[2]["what"] == "Люсия у машины" and "0:45 — Люсия у машины на пляже" in съём[2]["where"]
    assert съём[3]["what"] == "Проезд по городу" and съём[3]["where"] == "Лос-Сантос" and not съём[3]["note"]


def test_превью_длинное_переписано_не_обрезано(стенд):
    п = _собрать(стенд)
    т = json.loads(п.data)["thumbnail"]
    assert т["text"] == "Ты это заметил" and not т.get("too_long")
    assert any("Текст на превью" in в for в in стенд["модель"].вызовы)


def test_превью_упорно_длинное_целиком_и_пометка(стенд):
    стенд["модель"].поведение["превью_упорно"] = True
    п = _собрать(стенд)
    д = json.loads(п.data)
    assert д["thumbnail"]["text"] == "Шесть слов на превью это много" and д["thumbnail"]["too_long"] is True
    assert {п2["item"]: п2["ok"] for п2 in д["check"]}["Текст превью до 4 слов"] is None


def test_бюджет_сохраняется_полем(стенд):
    клиент = TestClient(main.app)
    клиент.cookies.set("access_token", create_token(стенд["ид"]["админ"], 0))
    r = клиент.post("/content/api/settings/budget", json={"usd": 3.5})
    assert r.status_code == 200 and r.json()["потолок"] == 3.5
    db = стенд["Сессия"]()
    assert ce.бюджет(db)["потолок"] == 3.5
    db.close()
    assert клиент.post("/content/api/settings/budget", json={"usd": 0}).status_code == 400
    r = клиент.get("/content/kitchen")
    assert r.status_code == 200 and 'id="content-budget-usd"' in r.text and 'value="3.50"' in r.text


def test_бюджет_по_умолчанию_2_досев_не_трогает_своё(стенд):
    db = стенд["Сессия"]()
    assert ce.бюджет(db)["потолок"] == 2.0                         # свежая база — из семени
    строка = db.get(cdb.ContentSetting, "budget")
    строка.value = json.dumps({"daily_usd": 1.0})                  # прежнее умолчание на проде
    db.commit()
    cdb.догнать_семя(db, cdb.прочитать_семя())
    db.commit()
    assert ce.бюджет(db)["потолок"] == 2.0
    строка.value = json.dumps({"daily_usd": 1.0, "v": 2})          # версия поднята без значения (прод)
    db.commit()
    cdb.догнать_семя(db, cdb.прочитать_семя())
    db.commit()
    assert ce.бюджет(db)["потолок"] == 2.0
    строка.value = json.dumps({"daily_usd": 1.5})                  # своё значение владельца
    db.commit()
    cdb.догнать_семя(db, cdb.прочитать_семя())
    db.commit()
    assert ce.бюджет(db)["потолок"] == 1.5
    строка.value = json.dumps({"daily_usd": 1.0, "own": True})     # владелец сам выбрал 1.0
    db.commit()
    cdb.догнать_семя(db, cdb.прочитать_семя())
    db.commit()
    assert ce.бюджет(db)["потолок"] == 1.0
    db.close()


def test_стиль_и_база_знаний_уходят_в_модель_дословно(стенд):
    клиент = TestClient(main.app)
    клиент.cookies.set("access_token", create_token(стенд["ид"]["админ"], 0))
    стиль = "Говори как другу.\nКак я говорю (образец интонации — копируй манеру, не слова):\n- «Сел на лошадь, сменил оружие»."
    assert клиент.post("/content/api/settings/style", json={"text": стиль}).status_code == 200
    база = "GTA VI:\n- Герои — Джейсон и Люсия, пара.\n- Город — Вайс-Сити."
    assert клиент.post("/content/api/settings/knowledge", json={"text": база}).status_code == 200
    _собрать(стенд)
    сценарий = [с for с, в in zip(стенд["модель"].системы, стенд["модель"].вызовы) if в.startswith("Сценарий")]
    assert сценарий and стиль in сценарий[0] and база in сценарий[0]


def test_доверенное_сми_опора_для_подтверждено(стенд):
    """«Rockstar подтвердила» со ссылкой на IGN (доверенное СМИ) — не «слух
    подан как подтверждённый»; со ссылкой на запись-слух — по-прежнему он."""
    ign = _добавить(стенд, ext_id="rss:ign9", source_key="rss:10", source_name="IGN",
                    url="https://ign.test/9", title="Rockstar Confirms storms",
                    story_id=стенд["Сессия"]().query(ContentStory).first().id)
    стенд["модель"].поведение["доп_строки"] = [
        {"text": "Rockstar подтвердила штормы.", "fact": True, "src": [ign]}]
    п = _собрать(стенд)
    строки = _строки(п)
    assert строки["Rockstar подтвердила штормы."]["check"] is None
    assert строки["Rockstar официально подтвердила карту."]["check"] == "слух подан как подтверждённый"


def test_цифра_у_названия_игры_не_слово_превью():
    assert cp.слов_превью("GTA 5 против GTA 6") == 3
    assert cp.слов_превью("Шесть слов на превью это много") == 6


# ── Письмо B3, блок 1: статус фактов и честные названия ──────────────

def _данные(п):
    return json.loads(п.data)


def test_официальный_пакет_без_слуха_и_шапка_без_слуха(стенд):
    """1.1: материал официального источника не подаётся как слух — ни фраза
    с источником, ни фраза без источника при официальной основе; флаг
    пакета и название идеи — официальные. Обратный случай: факт из
    слухового источника с «говорят» остаётся."""
    м = стенд["модель"]
    м.поведение["доп_строки"] = [
        {"text": "Говорят, карта Леониды больше.", "fact": True, "src": [стенд["ид"]["офиц"]]},
        {"text": "Ещё раз: это пока слух, а не слова самой Rockstar.", "fact": False, "src": []}]
    db = стенд["Сессия"]()
    db.get(ContentIdea, стенд["ид"]["идея"]).title = "По слухам, трейлер 2 спрятал деталь"
    db.commit()
    db.close()
    п = _собрать(стенд)
    assert п.state == "ok", п.note
    д = _данные(п)
    assert д["idea"]["official"] is True
    for с in д["script"]:
        for л in с["lines"]:
            if л.get("status") == cp.СТАТУС_ОФИЦ or (not л["src"] and not any(
                    x.get("status") in (cp.СТАТУС_СЛУХ, cp.СТАТУС_УТЕЧКА) for x in с["lines"])):
                assert not cp.ОБОРОТ_СЛУХА.search(л["text"]), л
    db = стенд["Сессия"]()
    идея = db.get(ContentIdea, стенд["ид"]["идея"])
    assert not идея.title.lower().startswith("по слухам") and json.loads(идея.facts)["официально"]
    db.close()
    с = TestClient(main.app)
    с.cookies.set("access_token", create_token(стенд["ид"]["админ"], 0))
    стр = с.get(f"/content/package/{п.id}").text
    assert "слух — подаётся как слух" not in стр and "официально" in стр


def test_статус_факта_по_источнику():
    ф = {"official_sources": ["Rockstar Newswire"], "trusted_media": ["Game Informer", "IGN"]}
    по_id = {1: {"source": "Game Informer", "official": False, "rumor": False, "leak": False},
             2: {"source": "YouTube · Blogger", "platform": "youtube", "official": False, "rumor": False,
                 "leak": False},
             3: {"source": "Insider", "official": False, "rumor": False, "leak": True}}
    assert cp.статус_по([1], по_id, ф) == "официально"
    assert cp.статус_по([2], по_id, ф) == "слух"
    assert cp.статус_по([3], по_id, ф) == "утечка"
    assert cp.статус_по([2, 1], по_id, ф) == "официально"


def test_название_не_на_утверждении_одного_ролика_youtube(стенд):
    """1.2: «питомец» есть только у блогера на YouTube — в названии его нет,
    название строится на официальном факте. Обратный случай: официальное
    «170 видов» в названии остаётся."""
    db = стенд["Сессия"]()
    ид = стенд["ид"]
    идея = db.get(ContentIdea, ид["идея"])
    сейчас = datetime.utcnow()
    ролик = ContentItem(theme_id=идея.theme_id, ext_id="yt:9", source_id=3, source_key="yt:9",
                        source_name="YouTube · Davy Jones", platform="youtube", url="https://youtu.be/xxxxxxxxxxx",
                        title="Zoo and pet dog in GTA 6", first_seen_at=сейчас, last_seen_at=сейчас,
                        published_at=сейчас, story_id=идея.story_id)
    db.add(ролик)
    db.commit()
    yt = ролик.id
    db.close()
    м = стенд["модель"]
    м.поведение["факты_список"] = [
        {"text": "В игре 170 видов животных и охота", "src": [ид["офиц"]]},
        {"text": "У героя будет собака-питомец и зоопарк", "src": [yt]}] + [
        {"text": f"Факт номер {n}", "src": [ид["офиц"]]} for n in range(6)]
    м.поведение["названия"] = [["Питомец и зоопарк в GTA 6", "Собака-питомец в GTA 6", "Зоопарк GTA 6"],
                               ["170 видов животных в GTA 6", "Охота в GTA 6: 170 видов", "Звери GTA 6"]]
    п = _собрать(стенд)
    д = _данные(п)
    assert д["titles"] and all("питом" not in т.lower() and "зоопарк" not in т.lower() for т in д["titles"]), д["titles"]
    assert any("170" in т for т in д["titles"])


def test_факт_из_базы_знаний_без_проверь(стенд):
    """1.3: Нико и свидания, Си-Джей и девушки, дата релиза — в базе знаний,
    «ПРОВЕРЬ» не получают, даже если проверщик их не связал. Обратный
    случай: легендарные животные RDR2 без опоры — «проверь» остаётся."""
    м = стенд["модель"]
    м.поведение["доп_строки"] = [
        {"text": "В GTA IV у Нико были свидания и друзья, которых зовёшь по телефону.", "fact": True, "src": []},
        {"text": "В San Andreas у Си-Джея были девушки и свидания.", "fact": True, "src": []},
        {"text": "GTA 6 выходит девятнадцатого ноября 2026 года на PS5 и Xbox Series.", "fact": True, "src": []},
        {"text": "GTA 6 выходит двадцатого ноября 2026 года.", "fact": True, "src": []},
        {"text": "В Red Dead Redemption 2 легендарные животные были отдельным ритуалом.", "fact": True, "src": []}]
    д = _данные(_собрать(стенд))
    строки = {л["text"]: л for с in д["script"] for л in с["lines"]}
    for т in ("В GTA IV у Нико", "В San Andreas у Си-Джея", "GTA 6 выходит девятнадцатого"):
        л = next(v for k, v in строки.items() if k.startswith(т))
        assert л["check"] is None and л.get("kb"), л
    assert next(v for k, v in строки.items() if k.startswith("В Red Dead"))["check"]
    assert next(v for k, v in строки.items() if k.startswith("GTA 6 выходит двадцатого"))["check"]


def test_личная_фраза_без_ссылки(стенд):
    """1.4: опыт ведущего и вопрос зрителю — без [ист.]. Обратный случай:
    факт с источником ссылку сохраняет."""
    ид = стенд["ид"]
    стенд["модель"].поведение["доп_строки"] = [
        {"text": "Я представляю, как играл в Red Dead Redemption 2 и офигевал от ливня.", "fact": True,
         "src": [ид["офиц"]]},
        {"text": "Мне было кайфово смотреть на ураган.", "fact": True, "src": [ид["офиц"]]}]
    д = _данные(_собрать(стенд))
    строки = {л["text"]: л for с in д["script"] for л in с["lines"]}
    for т in ("Я представляю", "Мне было кайфово"):
        л = next(v for k, v in строки.items() if k.startswith(т))
        assert л["src"] == [] and not л.get("check"), л
    assert строки["Трейлер вышел вчера."]["src"] == [ид["офиц"]]


def test_unlockable_одинаково_в_двух_пакетах():
    """1.5: «unlockable» — «открываемые» в обоих пакетах, хотя модель в одном
    написала «открытые». Обратный случай: «открытые миры» не трогаются."""
    база = cdb.прочитать_семя()["settings"]["knowledge"]["text"]
    к = {"база": база, "источники": [{"title": "Unlockable animal species", "text": "rare and legendary"}]}
    итоги = []
    for слово in ("открытые", "открываемые"):
        д = {"script": [{"lines": [{"text": f"Есть {слово} виды животных, а открытые миры — нет."}]}],
             "titles": [f"Все {слово} звери"]}
        cp.привести_термины(д, к)
        итоги.append(д)
    for д in итоги:
        assert "открываемые виды" in д["script"][0]["lines"][0]["text"]
        assert "открытые миры" in д["script"][0]["lines"][0]["text"]
        assert д["titles"] == ["Все открываемые звери"]


def test_досев_базы_знаний_дописывает_и_не_затирает():
    """1.6: дополнения дописываются к тексту владельца, своё не трогается,
    повтор ничего не меняет."""
    текст = "GTA V (2013):\n- Своя строка владельца.\n\nGTA IV (2008):\n- Нико."
    доп = cdb.прочитать_семя()["knowledge_add"]
    новое = cdb.дописать_разделы(текст, доп["sections"])
    assert "Своя строка владельца." in новое and "Нико." in новое
    assert "Чоп (Chop) — пёс Франклина." in новое and "Rockstar Newswire" in новое
    assert новое.index("Чоп") < новое.index("GTA IV")
    assert cdb.дописать_разделы(новое, доп["sections"]) == новое


# ── Письмо B3, блок 2: длина и честный список съёмок ─────────────────

def _к_съёмок(трейлеры=None, сбой=None):
    база = cdb.прочитать_семя()["settings"]["knowledge"]["text"]
    return {"база": база, "источники": [], "образцы": [], "трейлеры": трейлеры or [],
            "трейлеры_сбой": сбой or []}


def test_строка_gta5_не_заменяется_на_найди_в_трейлере():
    к = _к_съёмок()
    итог = cp.обосновать_съёмки([
        {"what": "Запись телефона в GTA 5 и приложений", "source": "GTA 5", "where": "Ryde Хайвей", "basis": "gameplay"},
        {"what": "Запись: подходишь к собаке, это Чоп", "source": "свой геймплей GTA 5", "where": "Вайнвуд-Хиллз Кукушкино"},
        {"what": "Панорама: гора Чилиад, Блэйн-Каунти", "source": "трейлер", "where": "", "basis": "trailer:QdBZY2fkU-0@0:10"}], к)
    assert итог[0]["what"].startswith("Запись телефона") and not итог[0]["note"]
    assert итог[1]["what"].startswith("Запись: подходишь") and not итог[1]["note"]
    assert итог[2]["what"].startswith("найди в трейлере:")


def test_chop_newswire_чилиад_не_выдумка_и_обрывок_не_в_списке():
    к = _к_съёмок()
    итог = cp.обосновать_съёмки([
        {"what": "Скриншот Rockstar Newswire со сценой охоты", "source": "Newswire", "where": "Леонида"},
        {"what": "Пёс как Chop рядом с героем", "source": "Newswire", "where": "Леонида"},
        {"what": "Природа как у горы Чилиад и Палето-Бей", "source": "Newswire", "where": "Леонида"},
        {"what": "Телефон: WAiNK и RydeMe, как у Си-Джея", "source": "Newswire", "where": "Вайс-Сити"}], к)
    for с in итог[:3]:
        assert not с["note"], с
    assert "Ryde" not in итог[3]["note"] and "Джея" not in итог[3]["note"]
    # Обратный случай: выдуманное место GTA 6 по-прежнему ловится
    итог = cp.обосновать_съёмки([{"what": "Пляж Кукуруза-Бич", "source": "Newswire", "where": "Кукуруза-Бич"}], к)
    assert "Кукуруза-Бич" in итог[0]["note"]


def test_разбор_трейлеров_503_повтор_с_паузой(стенд, monkeypatch):
    import content_refs as cr
    вызовы, паузы = [], []

    async def gemini(client, yt_id, промпт, fps, превью=True):
        вызовы.append(yt_id)
        if len(вызовы) <= 2:
            raise cr.Сбой("Gemini: HTTP 503 — This model is currently experiencing high demand.")
        return json.dumps({"scenes": [{"t": "0:10", "what": "Пляж Вайс-Сити"}]}), {"cost": 0.0}

    async def сон(с):
        паузы.append(с)
    monkeypatch.setattr(cr, "_gemini", gemini)
    monkeypatch.setattr(cr.asyncio, "sleep", сон)
    db = стенд["Сессия"]()
    справка = asyncio.run(cr.справка_ролика(None, db, "gta", "QdBZY2fkU-0", "trailer", "Trailer 1"))
    db.close()
    assert справка["state"] == "ok" and len(вызовы) == 3 and len(паузы) == 2 and all(п > 0 for п in паузы)


def test_разбор_трейлеров_недоступен_пакет_говорит_честно(стенд, monkeypatch):
    async def трейлеры(клиент, db, тема, настройки, сбои=None):
        if сбои is not None:
            сбои.append("Trailer 2: Gemini: HTTP 503")
        return []
    monkeypatch.setattr(cp, "сцены_трейлеров", трейлеры)
    стенд["модель"].поведение["съёмки"] = [
        {"what": "Люсия у машины", "source": "трейлер", "where": "0:45", "basis": "trailer:VQRLujxTm3c@0:45", "for": "0:30"}]
    д = json.loads(_собрать(стенд).data)
    assert д["trailers_note"] and "недоступен" in д["trailers_note"]
    assert д["shots"][0]["what"] == "Люсия у машины" and "недоступен" in д["shots"][0]["unverified"]

