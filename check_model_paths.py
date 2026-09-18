"""ПУТИ ВЫЗОВА МОДЕЛИ НА ПОДДЕЛЬНЫХ ОТВЕТАХ (BACKLOG №346, заход 3, блок 2).

ПРОВЕРКА, код 1 при беде, 2 — спросить нечем. Живых вызовов НОЛЬ: модель
отвечает заглушкой (`model_stub.py`), приложение — настоящее, в процессе,
на КОПИИ базы стенда.

ЗАЧЕМ. Живые пробы аптечки, письма и дневника платили с ключа прода и
при этом проверяли две разные вещи сразу: КАЧЕСТВО ответа модели (это
вопрос к модели, и ему место в ручном замере `--живьём`) и НАШ КОД
вокруг вызова — собрался ли запрос, разобрался ли ответ, что увидит
человек при сбое. Второе от модели не зависит и проверяется подделкой.

ПУТЕЙ ПЯТЬ — это все двери, через которые ходили живые пробы:

  письмо   анализ вакансии (ANALYZE_MODEL) + письмо (LETTER_MODEL)
  заведение  текст упаковки → черновик карточки (ANALYZE_MODEL)
  запрос   «что есть от …» → маршрут + ответ по базе (ANALYZE_MODEL ×2)
  фото     снимок упаковки → черновик (LETTER_MODEL, картинка)
  дневник  реплика ассистента питания (LETTER_MODEL)
  тренер   реплика тренера (LETTER_MODEL)

Дневник и тренер добавлены не ради полноты: первый же прогон нашёл, что
оба чата отвечали 500 с 2026-09-08 — `user.id` читался после `commit`
и `db.close()`, объект был погашен и отцеплён (`DetachedInstanceError`).

У КАЖДОГО ТРИ ШАГА, и они про разное:

  сборка  модель, потолок, политика данных, обязательные части запроса;
  разбор  ответ заглушки разобран и лёг куда надо (ответ + база);
  ошибка  отказ сервиса → человеку сообщение, в базе ничего лишнего.

ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ (`--контроль`) — три подлога, у каждого своё
звено, и засчитан он, только если у ВСЕХ пяти путей упал ЕГО шаг:

  сборка-без-части   из запроса пропадает текст сообщений;
  разбор-сломан      `_model_output` отдаёт текст задом наперёд;
  ошибка-вместо-успеха  заглушка на успешном сценарии отвечает 500.

    py check_model_paths.py            # пять путей, код 0/1/2
    py check_model_paths.py --контроль
"""
import io
import json
import os
import re
import sqlite3
import sys
import tempfile
import uuid

import probe_guard  # noqa: F401 — внешний отказ говорится словом (§3)
import model_stub

КОРЕНЬ = os.path.dirname(os.path.abspath(__file__))
ИСХОДНАЯ = os.environ.get("STAND_DB") or os.path.join(КОРЕНЬ, "app.db")
ПОЧТА = os.environ.get("STAND_EMAIL", "screenshot@local.dev")
ВАКАНСИЯ = ("Инженер по автоматизации тестирования. Требования: Python, "
            "pytest, опыт с REST API от двух лет. Обязанности: писать "
            "автотесты, разбирать сбои в CI. Метка-вакансии-7Q.")
УПАКОВКА = "Препарат Проба 200 мг, таблетки, 20 шт, годен до 05.2028"
ВОПРОС = "что у меня есть от простуды?"
РЕПЛИКА = "Съел 100 г гречки на обед"
РЕПЛИКА_ТРЕНЕРУ = "Сегодня болит колено, что заменить?"


def _пропуск(причина: str):
    print("ПРОПУСК: " + причина)
    sys.exit(2)


def _копия_базы() -> str:
    if "/data/" in ИСХОДНАЯ.replace("\\", "/"):
        _пропуск("путь к боевой базе — проверка ходит только по стенду")
    if not os.path.exists(ИСХОДНАЯ):
        _пропуск(f"базы стенда нет ({ИСХОДНАЯ}) — посейте: py make_local_user.py --seed")
    каталог = tempfile.mkdtemp(prefix="model_paths_")
    путь = os.path.join(каталог, "app.db")
    исх = sqlite3.connect(ИСХОДНАЯ)
    нов = sqlite3.connect(путь)
    исх.backup(нов)
    исх.close()
    нов.close()
    return путь


# ── окружение ставится ДО импорта main: ключ и адрес читаются при импорте ──
os.environ["DB_PATH"] = _копия_базы()
os.environ.pop("FLY_APP_NAME", None)
os.environ["OPENROUTER_STAND_KEY"] = "stub-model-paths"
ЗАГЛУШКА = model_stub.Заглушка().__enter__()
os.environ["OPENROUTER_URL"] = ЗАГЛУШКА.адрес_чата
os.environ["OPENROUTER_AUDIO_URL"] = ЗАГЛУШКА.адрес_речи

import main                                     # noqa: E402
from auth import create_token                   # noqa: E402
from database import (SessionLocal, User, CoverLetter,  # noqa: E402
                      ChatMessage)
from fastapi.testclient import TestClient       # noqa: E402

ИТОГ: dict = {}


def шаг(имя: str, условие: bool, подробно: str = "",
        собрано=None, печать=True):
    """Исход шага «путь/звено». `собрано=0` — замер не состоялся, это ПРОПУСК."""
    путь, имя = имя.split("/", 1)
    if собрано == 0:
        исход = "ПРОПУСК"
    else:
        исход = "OK" if условие else "ПЛОХО"
    ИТОГ.setdefault(путь, {})[имя] = исход
    if печать:
        print(f"  {исход:7s} {путь:9s} {имя:7s} {подробно}")
    return исход == "OK"


# ── ответы заглушки по сценарию ─────────────────────────────────────────
class Сценарий:
    """Что отвечает заглушка. `сбой` — на все запросы отказ сервиса."""

    def __init__(self):
        self.сбой = False
        self.всегда_сбой = False    # подлог: успешный сценарий тоже получает 500
        self.метка = uuid.uuid4().hex[:8]

    def __call__(self, запрос):
        if self.сбой or self.всегда_сбой:
            return model_stub.ошибка(500, "stub: service failure")
        j = запрос.get("json") or {}
        модель, потолок = j.get("model"), j.get("max_tokens")
        текст = json.dumps(j.get("messages") or [], ensure_ascii=False)
        есть_картинка = "image_url" in текст
        if модель == main.ANALYZE_MODEL and потолок == main.ANALYZE_MAX_TOKENS:
            return model_stub.тело(json.dumps({
                "job_title": "Инженер-проба", "company_name": "Проба",
                "relevance_score": 8, "relevance_reason": "проба",
                "key_matches": ["совпадение-" + self.метка],
                "missing_skills": [], "tone_suggestion": "деловой",
                "relevant_portfolio_links": [], "focus_points": []},
                ensure_ascii=False))
        if модель == main.ANALYZE_MODEL and потолок == main.MEDKIT_QUERY_MAX_TOKENS:
            номера = re.findall(r"(?m)(?:^|\\n)(\d+) — ", текст)
            return model_stub.тело(json.dumps({
                "тип": "поиск", "подходят": [int(номера[0])] if номера else [],
                "нет": "", "группа": ""}, ensure_ascii=False))
        if модель == main.ANALYZE_MODEL and "Препарат Проба" in текст:
            return model_stub.тело(json.dumps({
                "вид": "заведение", "name": "Препарат Проба", "form": "tablet",
                "qty_total": 20}, ensure_ascii=False))
        if модель == main.ANALYZE_MODEL:
            return model_stub.тело(json.dumps({"вид": "запрос"}, ensure_ascii=False))
        if есть_картинка:
            return model_stub.тело(json.dumps({
                "name": "Препарат Снимок", "form": "tablet",
                "видно": "Препарат Снимок таблетки"}, ensure_ascii=False))
        if потолок == main.CHAT_MAX_TOKENS and "EnergyDess Workout" in запрос.get("title", ""):
            return model_stub.тело("Ответ тренера " + self.метка)
        if потолок == main.CHAT_MAX_TOKENS:
            return model_stub.тело("Ответ дневника " + self.метка)
        return model_stub.тело("Письмо-проба " + self.метка)


СЦЕНАРИЙ = Сценарий()
ЗАГЛУШКА.ответ = СЦЕНАРИЙ


def _клиент():
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.email == ПОЧТА).first()
        if not u:
            _пропуск(f"на стенде нет аккаунта {ПОЧТА} — посейте стенд")
        uid = u.id
    finally:
        db.close()
    c = TestClient(main.app)
    c.cookies.set("access_token", create_token(uid))
    c.uid = uid
    return c


def _новые_запросы(было: int):
    return ЗАГЛУШКА.запросы[было:]


def _картинка() -> bytes:
    from PIL import Image
    буф = io.BytesIO()
    Image.new("RGB", (64, 48), (200, 200, 200)).save(буф, "PNG")
    return буф.getvalue()


def _число(модель, *условие):
    db = SessionLocal()
    try:
        return db.query(модель).filter(*условие).count()
    finally:
        db.close()


# ── пять путей ──────────────────────────────────────────────────────────
def путь_письмо(c, печать=True):
    было = len(ЗАГЛУШКА.запросы)
    писем = _число(CoverLetter, CoverLetter.user_id == c.uid)
    r = c.post("/api/generate-letter", json={"job_text": ВАКАНСИЯ, "lang": "ru"})
    з = _новые_запросы(было)
    беды = []
    if len(з) != 2:
        беды.append(f"запросов {len(з)} вместо 2")
    else:
        беды += model_stub.проверить_запрос(з[0], main.ANALYZE_MODEL,
                                            main.ANALYZE_MAX_TOKENS,
                                            ("Метка-вакансии-7Q", "РЕЗЮМЕ:"))
        беды += model_stub.проверить_запрос(
            з[1], main.LETTER_MODEL, main.LETTER_MAX_TOKENS,
            ("Метка-вакансии-7Q", "РЕЗЮМЕ:", "совпадение-" + СЦЕНАРИЙ.метка))
    шаг("письмо/сборка", not беды, "; ".join(беды) or f"запросов {len(з)}",
        собрано=len(з), печать=печать)
    тело = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    письмо = str(тело.get("letter") or "")
    db = SessionLocal()
    try:
        последнее = (db.query(CoverLetter).filter(CoverLetter.user_id == c.uid)
                     .order_by(CoverLetter.id.desc()).first())
        в_базе = (последнее.letter_text or "", последнее.job_title or "") if последнее else ("", "")
    finally:
        db.close()
    ок = (r.status_code == 200 and письмо == "Письмо-проба " + СЦЕНАРИЙ.метка
          and в_базе == (письмо, "Инженер-проба")
          and _число(CoverLetter, CoverLetter.user_id == c.uid) == писем + 1)
    шаг("письмо/разбор", ок, f"HTTP {r.status_code}, письмо {письмо[:30]!r}, "
        f"в базе {в_базе[1]!r}", печать=печать)
    # ошибка: сервис отказал — человеку ошибка, письма в истории не прибавилось
    СЦЕНАРИЙ.сбой = True
    try:
        писем = _число(CoverLetter, CoverLetter.user_id == c.uid)
        r = c.post("/api/generate-letter", json={"job_text": ВАКАНСИЯ, "lang": "ru"})
        т = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        ок = (r.status_code >= 400 and bool(т.get("error"))
              and _число(CoverLetter, CoverLetter.user_id == c.uid) == писем)
        шаг("письмо/ошибка", ок, f"HTTP {r.status_code}, «{str(т.get('error'))[:50]}»",
            печать=печать)
    finally:
        СЦЕНАРИЙ.сбой = False


def _апт(c, **тело):
    c.delete("/medkit/api/chat")
    return c.post("/medkit/api/assist", **тело)


def путь_заведение(c, печать=True):
    было = len(ЗАГЛУШКА.запросы)
    r = _апт(c, json={"text": УПАКОВКА})
    з = _новые_запросы(было)
    беды = ([f"запросов {len(з)} вместо 1"] if len(з) != 1 else
            model_stub.проверить_запрос(з[0], main.ANALYZE_MODEL,
                                        main.MEDKIT_MAX_TOKENS, (УПАКОВКА,)))
    шаг("заведение/сборка", not беды, "; ".join(беды) or "запрос 1",
        собрано=len(з), печать=печать)
    т = r.json() if r.status_code == 200 else {}
    имя = ((т.get("поля") or {}).get("name") or "")
    шаг("заведение/разбор", r.status_code == 200 and т.get("вид") == "заведение"
        and имя == "Препарат Проба", f"HTTP {r.status_code}, вид {т.get('вид')!r}, "
        f"name {имя!r}", печать=печать)
    СЦЕНАРИЙ.сбой = True
    try:
        r = _апт(c, json={"text": УПАКОВКА})
        т = r.json()
        шаг("заведение/ошибка", r.status_code >= 400 and bool(т.get("error"))
            and "вид" not in т, f"HTTP {r.status_code}, «{str(т.get('error'))[:50]}»",
            печать=печать)
    finally:
        СЦЕНАРИЙ.сбой = False


def путь_запрос(c, печать=True):
    было = len(ЗАГЛУШКА.запросы)
    r = _апт(c, json={"text": ВОПРОС})
    з = _новые_запросы(было)
    беды = []
    if len(з) != 2:
        беды.append(f"запросов {len(з)} вместо 2")
    else:
        беды += model_stub.проверить_запрос(з[0], main.ANALYZE_MODEL,
                                            main.MEDKIT_MAX_TOKENS, (ВОПРОС,))
        беды += model_stub.проверить_запрос(з[1], main.ANALYZE_MODEL,
                                            main.MEDKIT_QUERY_MAX_TOKENS, (ВОПРОС, " — "))
    шаг("запрос/сборка", not беды, "; ".join(беды) or "запросов 2",
        собрано=len(з), печать=печать)
    т = r.json() if r.status_code == 200 else {}
    номер = None
    if len(з) == 2:
        н = re.findall(r"(?m)(?:^|\\n)(\d+) — ",
                       json.dumps(з[1]["json"]["messages"], ensure_ascii=False))
        номер = int(н[0]) if н else None
    нашлось = [п.get("id") for п in (т.get("нашлось") or []) if isinstance(п, dict)]
    шаг("запрос/разбор", r.status_code == 200 and т.get("вид") == "запрос"
        and номер is not None and номер in нашлось,
        f"HTTP {r.status_code}, номер {номер}, нашлось {нашлось[:4]}", печать=печать)
    СЦЕНАРИЙ.сбой = True
    try:
        r = _апт(c, json={"text": ВОПРОС})
        т = r.json()
        шаг("запрос/ошибка", r.status_code >= 400 and bool(т.get("error")),
            f"HTTP {r.status_code}, «{str(т.get('error'))[:50]}»", печать=печать)
    finally:
        СЦЕНАРИЙ.сбой = False


def путь_фото(c, печать=True):
    было = len(ЗАГЛУШКА.запросы)
    r = _апт(c, files={"file": ("pack.png", _картинка(), "image/png")})
    з = _новые_запросы(было)
    беды = ([f"запросов {len(з)} вместо 1"] if len(з) != 1 else
            model_stub.проверить_запрос(з[0], main.LETTER_MODEL,
                                        main.MEDKIT_MAX_TOKENS, ("фотография упаковки",)))
    if len(з) == 1 and model_stub.устройство(з[0])["images"] != 1:
        беды.append("в запросе нет картинки")
    шаг("фото/сборка", not беды, "; ".join(беды) or "запрос 1, картинка 1",
        собрано=len(з), печать=печать)
    т = r.json() if r.status_code == 200 else {}
    имя = ((т.get("поля") or {}).get("name") or "")
    шаг("фото/разбор", r.status_code == 200 and имя == "Препарат Снимок",
        f"HTTP {r.status_code}, name {имя!r}", печать=печать)
    СЦЕНАРИЙ.сбой = True
    try:
        r = _апт(c, files={"file": ("pack.png", _картинка(), "image/png")})
        т = r.json()
        шаг("фото/ошибка", r.status_code >= 400 and bool(т.get("error")),
            f"HTTP {r.status_code}, «{str(т.get('error'))[:50]}»", печать=печать)
    finally:
        СЦЕНАРИЙ.сбой = False


def путь_дневник(c, печать=True):
    было = len(ЗАГЛУШКА.запросы)
    реплик = _число(ChatMessage, ChatMessage.user_id == c.uid, ChatMessage.role == "assistant")
    r = c.post("/nutrition/api/ai-chat", json={"message": РЕПЛИКА})
    з = _новые_запросы(было)
    беды = ([f"запросов {len(з)} вместо 1"] if len(з) != 1 else
            model_stub.проверить_запрос(з[0], main.LETTER_MODEL,
                                        main.CHAT_MAX_TOKENS, (РЕПЛИКА,)))
    шаг("дневник/сборка", not беды, "; ".join(беды) or "запрос 1",
        собрано=len(з), печать=печать)
    т = r.json() if r.status_code == 200 else {}
    ок = (r.status_code == 200 and т.get("reply") == "Ответ дневника " + СЦЕНАРИЙ.метка
          and _число(ChatMessage, ChatMessage.user_id == c.uid,
                     ChatMessage.role == "assistant") == реплик + 1)
    шаг("дневник/разбор", ок, f"HTTP {r.status_code}, reply {str(т.get('reply'))[:30]!r}",
        печать=печать)
    СЦЕНАРИЙ.сбой = True
    try:
        r = c.post("/nutrition/api/ai-chat", json={"message": РЕПЛИКА})
        т = r.json()
        шаг("дневник/ошибка", r.status_code == 502
            and т.get("error") == main.ТЕКСТ_СБОЯ["service"],
            f"HTTP {r.status_code}, «{str(т.get('error'))[:50]}»", печать=печать)
    finally:
        СЦЕНАРИЙ.сбой = False


def путь_тренер(c, печать=True):
    было = len(ЗАГЛУШКА.запросы)
    реплик = _число(ChatMessage, ChatMessage.user_id == c.uid,
                    ChatMessage.role == "assistant", ChatMessage.tool == "workout")
    r = c.post("/workout/api/chat", json={"message": РЕПЛИКА_ТРЕНЕРУ})
    з = _новые_запросы(было)
    беды = ([f"запросов {len(з)} вместо 1"] if len(з) != 1 else
            model_stub.проверить_запрос(з[0], main.LETTER_MODEL,
                                        main.CHAT_MAX_TOKENS, (РЕПЛИКА_ТРЕНЕРУ,)))
    шаг("тренер/сборка", not беды, "; ".join(беды) or "запрос 1",
        собрано=len(з), печать=печать)
    т = r.json() if r.status_code == 200 else {}
    ок = (r.status_code == 200 and т.get("reply") == "Ответ тренера " + СЦЕНАРИЙ.метка
          and _число(ChatMessage, ChatMessage.user_id == c.uid, ChatMessage.role == "assistant",
                     ChatMessage.tool == "workout") == реплик + 1)
    шаг("тренер/разбор", ок, f"HTTP {r.status_code}, reply {str(т.get('reply'))[:30]!r}",
        печать=печать)
    СЦЕНАРИЙ.сбой = True
    try:
        r = c.post("/workout/api/chat", json={"message": РЕПЛИКА_ТРЕНЕРУ})
        т = r.json()
        шаг("тренер/ошибка", r.status_code == 502
            and т.get("error") == main.ТЕКСТ_СБОЯ["service"],
            f"HTTP {r.status_code}, «{str(т.get('error'))[:50]}»", печать=печать)
    finally:
        СЦЕНАРИЙ.сбой = False


ПУТИ = [путь_письмо, путь_заведение, путь_запрос, путь_фото, путь_дневник,
        путь_тренер]


def прогон(c, печать=True) -> dict:
    ИТОГ.clear()
    for п in ПУТИ:
        п(c, печать)
    return {к: dict(в) for к, в in ИТОГ.items()}


# ── подлоги ─────────────────────────────────────────────────────────────
def _подлог_сборка():
    исх = main._модель_post

    async def без_части(client, инструмент, user_id, url, **kw):
        j = dict(kw.get("json") or {})
        j["messages"] = [{"role": м.get("role", "user"), "content": ""}
                         for м in (j.get("messages") or [])]
        kw["json"] = j
        return await исх(client, инструмент, user_id, url, **kw)
    main._модель_post = без_части
    return lambda: setattr(main, "_модель_post", исх)


def _подлог_разбор():
    исх = main._model_output

    def задом(payload, метка, лимит):
        текст, сбой = исх(payload, метка, лимит)
        return (текст[::-1] if текст else текст), сбой
    main._model_output = задом
    return lambda: setattr(main, "_model_output", исх)


def _подлог_ошибка():
    СЦЕНАРИЙ.всегда_сбой = True
    return lambda: setattr(СЦЕНАРИЙ, "всегда_сбой", False)


ПОДЛОГИ = [("сборка-без-части", "сборка", _подлог_сборка),
           ("разбор-сломан", "разбор", _подлог_разбор),
           ("ошибка-вместо-успеха", "разбор", _подлог_ошибка)]


def main_() -> int:
    контроль = "--контроль" in sys.argv
    with _клиент() as c:
        print("ПУТИ ВЫЗОВА МОДЕЛИ НА ПОДДЕЛЬНЫХ ОТВЕТАХ (заглушка, живых вызовов 0)")
        чисто = прогон(c)
        плохо = [(п, ш) for п, шаги in чисто.items() for ш, и in шаги.items() if и == "ПЛОХО"]
        пропуск = [(п, ш) for п, шаги in чисто.items() for ш, и in шаги.items() if и == "ПРОПУСК"]
        print(f"ИТОГ: путей {len(чисто)}, шагов {sum(len(ш) for ш in чисто.values())}, "
              f"плохо {len(плохо)}, пропуск {len(пропуск)}; запросов к заглушке "
              f"{len(ЗАГЛУШКА.запросы)}")
        if not контроль:
            return 1 if плохо else (2 if пропуск else 0)
        if плохо or пропуск:
            print("КОНТРОЛЬ НЕДЕЙСТВИТЕЛЕН: чистый прогон не чист")
            return 2
        беды = 0
        for имя, звено, завести in ПОДЛОГИ:
            вернуть = завести()
            try:
                с_подлогом = прогон(c, печать=False)
            finally:
                вернуть()
            упали = [п for п, шаги in с_подлогом.items() if шаги.get(звено) != "OK"]
            всё = len(упали) == len(с_подлогом)
            беды += 0 if всё else 1
            print(f"  подлог {имя:22s} звено «{звено}» упало у {len(упали)} из "
                  f"{len(с_подлогом)} путей: {'НАЙДЕН' if всё else 'НЕ НАЙДЕН'} {упали}")
        после = прогон(c, печать=False)
        чисто_после = all(и == "OK" for ш in после.values() for и in ш.values())
        print(f"  после подлогов прогон чист: {чисто_после}")
        print("КОНТРОЛЬ: " + ("подлоги найдены" if not беды and чисто_после else "БЕДА"))
        return 0 if not беды and чисто_после else 1


if __name__ == "__main__":
    try:
        код = main_()
    finally:
        ЗАГЛУШКА.__exit__()
    sys.exit(код)
