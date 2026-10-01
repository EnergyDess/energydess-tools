"""Пакет ролика, письмо B4 (задача 380): связки, крючок, статус по всем
источникам волны, повторы образца речи.

Стенд и подменённая модель — общие с `test_content_package.py`. Контроли,
у каждого обратный случай:
1. СВЯЗКА С УТВЕРЖДЕНИЕМ БЕЗ ОПОРЫ («один особый зверь на всю карту…») —
   переписана мнением либо убрана; «представь…» и вопрос зрителю остаются.
2. КРЮЧОК СИЛЬНЕЕ ИСТОЧНИКА («сносят мусор» при «поднимает мусор») —
   переписан ближе к источнику; строка не сильнее — не тронута.
3. УТВЕРЖДЕНИЕ РОЛИКА, СОВПАВШЕЕ С IGN, — «официально» и ссылка на IGN;
   номер не из посланных — не меняет ничего.
4. ДВЕ ПОЧТИ ДОСЛОВНЫЕ ЦИТАТЫ ОБРАЗЦА в пакете — остаётся одна.
5. ОДНА И ТА ЖЕ ЦИТАТА В ДВУХ ПАКЕТАХ ПОДРЯД — во втором переписана.
"""
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

import content_db as cdb  # noqa: E402
import content_package as cp  # noqa: E402
from content_db import ContentIdea, ContentItem, ContentSetting  # noqa: E402
from test_content_package import _собрать, стенд  # noqa: E402,F401

СТИЛЬ = ("Живая речь.\n\nКак я говорю (образец интонации — копируй манеру, не слова):\n"
         "- «Я представляю, как играл когда-то в Red Dead Redemption и просто офигевал от погоды, "
         "эмбиента, окружения. А GTA 6 делают с наработками RDR 2 — сколько же нас всего ждёт».\n"
         "- «Многие будут вонять, что GTA уже не та. Но лично мне в Red Dead было кайфово: "
         "сел на лошадь, сменил оружие».\n"
         "Особенности: опора на личный опыт.")


def _данные(п):
    return json.loads(п.data)


def _тексты(д):
    return [л["text"] for с in д["script"] for л in с["lines"]]


def _стиль(стенд):
    db = стенд["Сессия"]()
    с = db.get(ContentSetting, "style")
    if с is None:
        db.add(ContentSetting(key="style", value=json.dumps({"text": СТИЛЬ}, ensure_ascii=False),
                              updated_at=datetime.utcnow()))
    else:
        с.value = json.dumps({"text": СТИЛЬ}, ensure_ascii=False)
    db.commit()
    db.close()


# ── 1.1 СВЯЗКИ ────────────────────────────────────────────────────────

def test_связка_без_опоры_переписана_мнением_или_убрана(стенд):
    м = стенд["модель"]
    зверь = "Один особый зверь на всю карту. Выследил, добыл — получил что-то крутое."
    игуаны = "Во Флориде реально проблема с игуанами, они падают с деревьев."
    м.поведение["доп_строки"] = [
        {"text": зверь, "fact": False, "src": []},
        {"text": игуаны, "fact": False, "src": []},
        {"text": "Представь: едешь по трассе, а на дороге греется игуана.", "fact": False, "src": []},
        {"text": "А вы бы пошли на такую охоту?", "fact": False, "src": []},
        {"text": "Короче, слушай дальше.", "fact": False, "src": []},
    ]
    м.поведение["опора"] = {
        зверь: {"fix": "Думаю, легендарные звери будут штучными, как в RDR 2."},
        игуаны: {"fix": ""},
    }
    д = _данные(_собрать(стенд))
    тексты = _тексты(д)
    assert зверь not in тексты and игуаны not in тексты
    assert "Думаю, легендарные звери будут штучными, как в RDR 2." in тексты
    assert "Представь: едешь по трассе, а на дороге греется игуана." in тексты
    assert "А вы бы пошли на такую охоту?" in тексты
    assert "Короче, слушай дальше." in тексты  # проверщик не выписал — связка без утверждения
    assert д["factcheck"]["bridges"] == 2


def test_связка_переписанная_без_маркера_мнения_убрана(стенд):
    м = стенд["модель"]
    зверь = "Один особый зверь на всю карту."
    м.поведение["доп_строки"] = [{"text": зверь, "fact": False, "src": []}]
    # «fix» снова утверждение, а не мнение — такую правку не берём
    м.поведение["опора"] = {зверь: {"fix": "На карте будет один легендарный зверь."}}
    тексты = _тексты(_данные(_собрать(стенд)))
    assert зверь not in тексты and "На карте будет один легендарный зверь." not in тексты


def test_связка_с_опорой_становится_фактом(стенд):
    м = стенд["модель"]
    строка = "Зверей там будет много."
    м.поведение["доп_строки"] = [{"text": строка, "fact": False, "src": []}]
    м.поведение["опора"] = {строка: {"src": [м.ид["офиц"]]}}
    д = _данные(_собрать(стенд))
    л = next(л for с in д["script"] for л in с["lines"] if л["text"] == строка)
    assert л["fact"] and м.ид["офиц"] in л["src"] and not л.get("check")
    assert д["factcheck"]["bridges"] == 0


# ── 1.2 КРЮЧОК И ВЫВОДЫ НЕ СИЛЬНЕЕ ИСТОЧНИКА ──────────────────────────

def test_крючок_сильнее_источника_переписан(стенд):
    м = стенд["модель"]
    м.поведение["хук"] = "Ураганы, которые сносят мусор с крыш."
    вывод = "Короче, ветер в игре сносит крыши."
    м.поведение["доп_строки"] = [{"text": вывод, "fact": True, "src": [м.ид["офиц"]]}]
    м.поведение["опора"] = {
        "Ураганы, которые сносят мусор с крыш.": {"stronger": True,
                                                   "fix": "Ветер поднимает пыль и мусор на крышах."},
        вывод: {"stronger": True, "src": [м.ид["офиц"]], "fix": "Ветер в игре гоняет мусор по крышам."},
        "Трейлер вышел вчера.": {"src": [м.ид["офиц"]]},
    }
    д = _данные(_собрать(стенд))
    assert д["hook"]["text"] == "Ветер поднимает пыль и мусор на крышах."
    тексты = _тексты(д)
    assert вывод not in тексты and "Ветер в игре гоняет мусор по крышам." in тексты
    assert д["factcheck"]["stronger"] == 2
    assert "Трейлер вышел вчера." in тексты  # не сильнее — не тронута


def test_название_сильнее_источника_переписано(стенд):
    м = стенд["модель"]
    м.поведение["опора"] = {"Три детали трейлера": {"stronger": True, "fix": "Две детали трейлера"}}
    д = _данные(_собрать(стенд))
    assert "Две детали трейлера" in д["titles"] and "Три детали трейлера" not in д["titles"]


# ── 1.3 СТАТУС ПО ВСЕМ ИСТОЧНИКАМ ─────────────────────────────────────

def _ролик_и_ign(стенд):
    db = стенд["Сессия"]()
    офиц = db.get(ContentItem, стенд["ид"]["офиц"])
    сейчас = datetime.utcnow()
    ign = ContentItem(theme_id=офиц.theme_id, ext_id="ign:1", source_id=3, source_key="ign:1",
                      source_name="IGN", platform="rss", url="https://ign.test/1",
                      title="GTA 6: All the Major New Details, Including Animal Species", official=False,
                      first_seen_at=сейчас, last_seen_at=сейчас, published_at=сейчас, story_id=офиц.story_id)
    ролик = ContentItem(theme_id=офиц.theme_id, ext_id="yt:br", source_id=4, source_key="yt:br",
                        source_name="YouTube · Davy Jones", platform="youtube", url="https://youtube.test/br",
                        title="ZOOLÓGICO NO GTA 6", first_seen_at=сейчас, last_seen_at=сейчас,
                        published_at=сейчас, story_id=офиц.story_id)
    db.add_all([ign, ролик])
    db.commit()
    ид = (ign.id, ролик.id)
    db.close()
    return ид


def test_утверждение_ролика_совпало_с_ign_официально(стенд):
    м = стенд["модель"]
    ign, ролик = _ролик_и_ign(стенд)
    шерсть = "Слух: шерсть животных пачкается и реагирует на прикосновения"
    м.поведение["факты_список"] = ([{"text": шерсть, "src": [ролик]}]
                                    + [{"text": f"Факт номер {n}", "src": [м.ид["офиц"]]} for n in range(6)])

    def сверка(вопрос):
        r = next(л.split(":")[0] for л in вопрос.splitlines() if л.startswith("R") and "шерсть" in л)
        o = next(л.split(":")[0] for л in вопрос.splitlines() if л.startswith("O") and "(источник: IGN)" in л)
        return [{"fact": r, "official": o}]
    м.поведение["сверка"] = сверка
    м.поведение["доп_строки"] = [{"text": "Шерсть животных пачкается и реагирует на прикосновения.",
                                  "fact": True, "src": [ролик]}]
    д = _данные(_собрать(стенд))
    ф = next(ф for ф in д["material"]["list"] if "шерсть" in ф["text"].lower())
    assert ф["status"] == cp.СТАТУС_ОФИЦ and ign in ф["src"] and not ф["text"].lower().startswith("слух")
    л = next(л for с in д["script"] for л in с["lines"] if л["text"].startswith("Шерсть"))
    assert л["status"] == cp.СТАТУС_ОФИЦ and ign in л["src"]


def test_сверка_с_чужим_номером_не_меняет_статус(стенд):
    м = стенд["модель"]
    _, ролик = _ролик_и_ign(стенд)
    м.поведение["факты_список"] = ([{"text": "Слух: шерсть пачкается", "src": [ролик]}]
                                    + [{"text": f"Факт номер {n}", "src": [м.ид["офиц"]]} for n in range(6)])
    м.поведение["сверка"] = lambda вопрос: [{"fact": "R1", "official": "O99"}, {"fact": "R7", "official": "O1"}]
    д = _данные(_собрать(стенд))
    ф = next(ф for ф in д["material"]["list"] if "шерсть" in ф["text"].lower())
    assert ф["status"] == cp.СТАТУС_СЛУХ and ф["src"] == [ролик]


def test_официальные_утверждения_берут_пересказ_со_слов_сми():
    источники = [{"id": 1, "source": "Game Informer", "platform": "rss", "title": "GTA VI issue", "text": "",
                  "official": False, "rumor": False, "leak": False},
                 {"id": 2, "source": "YouTube · X", "platform": "youtube", "title": "t", "text": "",
                  "official": False, "rumor": False, "leak": False,
                  "claims": [{"t": "1:00", "text": "Шерсть пачкается", "from": "Game Informer / Майкл Кейн"},
                             {"t": "2:00", "text": "Будет зоопарк", "from": None}]}]
    ф = {"trusted_media": ["Game Informer"], "official_sources": ["Rockstar Newswire"]}
    о = cp.официальные_утверждения(None, "gta", источники, ф)
    assert {(х["record"], х["text"]) for х in о} == {(1, "GTA VI issue."), (1, "Шерсть пачкается")}


# ── 1.4 ПОВТОРЫ ОБРАЗЦА РЕЧИ ──────────────────────────────────────────

ЦИТАТА_1 = "Я представляю, как играл в Red Dead 2 и офигевал от погоды и окружения."
ЦИТАТА_2 = "Многие будут вонять, что GTA уже не та."


def test_цитата_в_порог_почти_дословно():
    ц = cp.цитаты_стиля(СТИЛЬ)
    assert len(ц) == 2
    assert cp.цитата_в(ЦИТАТА_1, ц) == 0
    assert cp.цитата_в(ЦИТАТА_2, ц) == 1
    assert cp.цитата_в("В Red Dead я мог часами просто смотреть на зверьё.", ц) is None
    assert cp.цитата_в("Многие игроки ждут GTA 6 уже десять лет.", ц) is None


def test_две_цитаты_образца_остаётся_одна(стенд):
    _стиль(стенд)
    м = стенд["модель"]
    м.поведение["доп_строки"] = [{"text": ЦИТАТА_1, "fact": False, "src": []},
                                  {"text": ЦИТАТА_2, "fact": False, "src": []}]
    м.поведение["свои_слова"] = {ЦИТАТА_2: "Кто-то снова скажет, что серия сдулась, — а я жду."}
    д = _данные(_собрать(стенд))
    ц = cp.цитаты_стиля(СТИЛЬ)
    assert len(cp.цитаты_пакета(д, ц)) <= 1
    тексты = _тексты(д)
    assert ЦИТАТА_1 in тексты and ЦИТАТА_2 not in тексты
    assert "Кто-то снова скажет, что серия сдулась, — а я жду." in тексты
    assert д["style_quotes"]["quotes"] == [0]


def test_одна_цитата_в_двух_пакетах_подряд_во_втором_переписана(стенд):
    _стиль(стенд)
    м = стенд["модель"]
    м.поведение["доп_строки"] = [{"text": ЦИТАТА_1, "fact": False, "src": []}]
    первый = _данные(_собрать(стенд))
    assert ЦИТАТА_1 in _тексты(первый)
    # Вторая идея, второй пакет — та же цитата
    db = стенд["Сессия"]()
    стар = db.get(ContentIdea, стенд["ид"]["идея"])
    нов = ContentIdea(theme_id=стар.theme_id, run_id=1, kind="long", sort="hot", title="Вторая идея",
                      why="ещё повод", format_id=стар.format_id, story_id=стар.story_id,
                      facts=стар.facts, risks="[]", state="new")
    db.add(нов)
    db.commit()
    стенд["ид"]["идея"] = нов.id
    db.close()
    м.поведение["свои_слова"] = {ЦИТАТА_1: "Помню, как в RDR 2 залипал на закаты — тут жду того же."}
    второй = _данные(_собрать(стенд))
    тексты = _тексты(второй)
    assert ЦИТАТА_1 not in тексты
    assert "Помню, как в RDR 2 залипал на закаты — тут жду того же." in тексты
    assert второй["style_quotes"]["quotes"] == []


# ── 2.1 КВОТА GEMINI ──────────────────────────────────────────────────

class _Ответ:
    def __init__(self, код, тело):
        self.status_code, self._тело = код, тело

    def json(self):
        return self._тело


class _Клиент:
    """Подменённый HTTP: 429 «exceeded your current quota» либо 503 по очереди."""

    def __init__(self, коды):
        self.коды, self.вызовы = list(коды), 0

    async def post(self, *a, **k):
        self.вызовы += 1
        код = self.коды.pop(0) if self.коды else 200
        if код == 200:
            return _Ответ(200, {"candidates": [{"content": {"parts": [{"text": '{"scenes": [{"t": "0:10", "what": "Пляж"}]}'}]},
                                                "finishReason": "STOP"}], "usageMetadata": {}})
        текст = "You exceeded your current quota" if код == 429 else "high demand"
        return _Ответ(код, {"error": {"message": текст}})


def _с_ключом(monkeypatch):
    import content_refs as cr
    monkeypatch.setattr(cr, "ключ", lambda: "test-key")
    паузы = []

    async def сон(с):
        паузы.append(с)
    monkeypatch.setattr(cr.asyncio, "sleep", сон)
    return cr, паузы


def test_429_стоп_до_сброса_без_повторов(стенд, monkeypatch):
    import asyncio
    cr, паузы = _с_ключом(monkeypatch)
    клиент = _Клиент([429, 429, 429])
    db = стенд["Сессия"]()
    с = asyncio.run(cr.справка_ролика(клиент, db, "gta", "QdBZY2fkU-0", "trailer", "Trailer 1"))
    assert с["state"] == "quota" and клиент.вызовы == 1 and паузы == []
    # квота отмечена — следующий вызов в HTTP не уходит вовсе
    с2 = asyncio.run(cr.справка_ролика(клиент, db, "gta", "VQRLujxTm3c", "trailer", "Trailer 2"))
    db.close()
    assert с2["state"] == "quota" and клиент.вызовы == 1
    db = стенд["Сессия"]()
    assert cr.сводка(db)["квота"] == cr.КВОТА_ТЕКСТ
    db.close()


def test_503_повтор_с_паузой_429_нет(стенд, monkeypatch):
    import asyncio
    cr, паузы = _с_ключом(monkeypatch)
    клиент = _Клиент([503, 200])
    db = стенд["Сессия"]()
    с = asyncio.run(cr.справка_ролика(клиент, db, "gta", "QdBZY2fkU-0", "trailer", "Trailer 1"))
    db.close()
    assert с["state"] == "ok" and клиент.вызовы == 2 and len(паузы) == 1
    assert cr.квота_до() is None


def test_после_сброса_gemini_пробуется_снова(стенд, monkeypatch):
    from datetime import datetime, timedelta
    cr, _ = _с_ключом(monkeypatch)
    утро = datetime(2026, 10, 1, 6, 30)            # 09:30 МСК
    до = cr.отметить_квоту("тест", утро)
    assert до == datetime(2026, 10, 1, 7, 0)        # 10:00 МСК того же дня
    assert cr.квота_до(сейчас=утро + timedelta(minutes=20)) == до
    assert cr.квота_до(сейчас=до + timedelta(seconds=1)) is None
    вечер = datetime(2026, 10, 1, 17, 0)           # 20:00 МСК — сброс завтра
    assert cr.сброс_квоты(вечер) == datetime(2026, 10, 2, 7, 0)


def test_пакет_при_квоте_честно_и_без_вызовов(стенд, monkeypatch):
    cr, _ = _с_ключом(monkeypatch)
    cr.отметить_квоту("тест")
    вызовы = []

    async def gemini(*a, **k):
        вызовы.append(1)
        raise AssertionError("Gemini не должен зваться при исчерпанной квоте")
    monkeypatch.setattr(cr, "_gemini", gemini)
    db = стенд["Сессия"]()
    н = cdb.настройка(db, "package")
    н["trailers"] = [{"yt_id": "QdBZY2fkU-0", "title": "Trailer 1"}]
    с = db.get(ContentSetting, "package")
    с.value = json.dumps(н, ensure_ascii=False)
    db.commit()
    db.close()
    д = _данные(_собрать(стенд))
    assert вызовы == [] and "квота Gemini" in д["trailers_note"]


# ── ПО ПРУФУ С ПРОДА (пересборка №59 и №70) ───────────────────────────

def test_связка_с_опорой_в_базе_знаний_не_убирается(стенд):
    м = стенд["модель"]
    строка = "В GTA 5 у Франклина был пёс Чоп."
    м.поведение["доп_строки"] = [{"text": строка, "fact": False, "src": []}]
    м.поведение["опора"] = {строка: {"fix": ""}}  # проверщик не связал с базой
    д = _данные(_собрать(стенд))
    л = next(л for с in д["script"] for л in с["lines"] if л["text"] == строка)
    assert л.get("kb") and not л.get("check")
    assert д["factcheck"]["bridges"] == 0


def test_правка_сильнее_источника_снова_проходит_статус(стенд):
    м = стенд["модель"]
    вывод = "Трейлер вышел вчера, и это главное."
    м.поведение["доп_строки"] = [{"text": вывод, "fact": True, "src": [м.ид["офиц"]]}]
    # «ближе к источнику», но официальный факт назван слухом — как в №70
    м.поведение["опора"] = {вывод: {"stronger": True, "src": [м.ид["офиц"]],
                                    "fix": "Трейлер вышел вчера — но это пока слух."}}
    д = _данные(_собрать(стенд))
    тексты = _тексты(д)
    assert "Трейлер вышел вчера — но это пока слух." not in тексты
    assert д["factcheck"].get("language_after") is not None
