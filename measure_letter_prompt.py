"""ЗАПРОС ПИСЬМА: ИЗ ЧЕГО СОСТОИТ, СКОЛЬКО СТОИТ, РАБОТАЕТ ЛИ КЭШ.

BACKLOG №346, заход 3, блок 3. МЕРКА, код 0 (2 — замер не состоялся).

Цепочка письма: вакансия → разбор на ANALYZE_MODEL → письмо на
LETTER_MODEL. Мерка ставит рядом два пути на ОДНОЙ вакансии и ОДНОМ
аккаунте стенда:

  старый  «полный»: как на проде (`LETTER_PROMPT_VARIANT` по умолчанию);
  новый   «кэш»: те же части, постоянная часть вперёд под отметкой кэша,
          два вызова подряд — запись в кэш и чтение из него.

И считает токены ЧАСТЕЙ запроса настоящим токенизатором — самой моделью
(`max_tokens=1`, число берётся из `usage.prompt_tokens`): у Anthropic
нет свободного счётчика без ключа, а доля по знакам — это «на глаз».

ВЫЗОВОВ РОВНО ВОСЕМЬ: 2 старый путь + 2 новый путь + 4 части (примеры,
правила, досье, вакансия). Остальные части выводятся вычитанием.

    py measure_letter_prompt.py             # на заглушке: механика, 0 денег
    py measure_letter_prompt.py --живьём    # 8 настоящих вызовов, ключ стенда

Все вызовы идут через `_модель_post`, то есть ложатся в `model_usage`
копии базы; строки печатаются без текста.
"""
import json
import os
import sqlite3
import sys
import tempfile
import time

import probe_guard  # noqa: F401 — внешний отказ говорится словом (§3)
import model_stub

ЖИВЬЁМ = model_stub.ФЛАГ_ЖИВЬЁМ in sys.argv
КОРЕНЬ = os.path.dirname(os.path.abspath(__file__))
ИСХОДНАЯ = os.environ.get("STAND_DB") or os.path.join(КОРЕНЬ, "app.db")
ПОЧТА = os.environ.get("STAND_EMAIL", "screenshot@local.dev")
МОДЕЛЬ_ПИСЬМА = os.environ.get("LETTER_MODEL_MEASURE", "anthropic/claude-opus-4-8")
ВЫВОД = os.environ.get("LETTER_MEASURE_OUT") or tempfile.mkdtemp(prefix="letter_measure_")
os.makedirs(ВЫВОД, exist_ok=True)

# Нейтральная вакансия публичного вида, без чьих-либо личных данных
ВАКАНСИЯ = """Python-разработчик (backend), удалённо

Компания разрабатывает сервис онлайн-записи для небольших клиник и салонов.
Ищем разработчика в команду из четырёх человек.

Обязанности:
— разработка и поддержка API на FastAPI;
— интеграции с внешними сервисами: платёжные системы, SMS-шлюзы, календари;
— участие в проектировании схемы базы данных (PostgreSQL);
— написание автотестов, код-ревью.

Требования:
— опыт коммерческой разработки на Python от двух лет;
— уверенное знание SQL и опыт с ORM;
— понимание HTTP, REST, асинхронного кода;
— умение работать с Git и CI.

Будет плюсом: опыт с LLM-API, Docker, деплой на облачные платформы.

Условия: полная занятость, удалённо, оплата от 180 000 ₽ на руки.
В отклике расскажите о проекте, которым гордитесь, и приложите ссылку на код."""


def _пропуск(причина):
    print("ПРОПУСК: " + причина)
    sys.exit(2)


if ЖИВЬЁМ:
    model_stub.живой_замер("measure_letter_prompt (8 вызовов, из них 5 на Opus)")
if "/data/" in ИСХОДНАЯ.replace("\\", "/"):
    _пропуск("путь к боевой базе — мерка ходит только по стенду")
if not os.path.exists(ИСХОДНАЯ):
    _пропуск(f"базы стенда нет ({ИСХОДНАЯ})")
_путь = os.path.join(tempfile.mkdtemp(prefix="letter_db_"), "app.db")
_a, _b = sqlite3.connect(ИСХОДНАЯ), sqlite3.connect(_путь)
_a.backup(_b)
_a.close()
_b.close()
os.environ["DB_PATH"] = _путь
os.environ["LETTER_MODEL"] = МОДЕЛЬ_ПИСЬМА
os.environ.pop("FLY_APP_NAME", None)

ЗАГЛУШКА = None
if not ЖИВЬЁМ:
    ЗАГЛУШКА = model_stub.Заглушка().__enter__()
    os.environ["OPENROUTER_URL"] = ЗАГЛУШКА.адрес_чата
    os.environ["OPENROUTER_STAND_KEY"] = "stub-letter-measure"

import main                                  # noqa: E402
import database                              # noqa: E402
from database import SessionLocal, User, CoverLetter, ModelUsage  # noqa: E402
from auth import create_token                # noqa: E402
from fastapi.testclient import TestClient    # noqa: E402

if ЖИВЬЁМ and not main.OPENROUTER_API_KEY:
    _пропуск("живого ключа стенда нет: " + main.КЛЮЧ_НЕТ_ПРИЧИНА)


def _ответ_заглушки(запрос):
    """Механика без денег: разбор — JSON, письмо — текст, части — 1 токен."""
    j = запрос.get("json") or {}
    знаков = len(json.dumps(j.get("messages"), ensure_ascii=False))
    if j.get("max_tokens") == 1:
        return model_stub.тело("x", токены_входа=знаков // 2, токены_выхода=1)
    if j.get("model") == main.ANALYZE_MODEL:
        return model_stub.тело(json.dumps({
            "job_title": "Python-разработчик", "company_name": "", "relevance_score": 7,
            "relevance_reason": "", "key_matches": ["FastAPI"], "missing_skills": [],
            "tone_suggestion": "деловой", "relevant_portfolio_links": [],
            "focus_points": ["API"]}, ensure_ascii=False))
    return model_stub.тело("ПИСЬМО-ЗАГЛУШКА (замер на подделке)", токены_входа=знаков // 2)


if ЗАГЛУШКА:
    ЗАГЛУШКА.ответ = _ответ_заглушки

ВРЕМЯ = []
_исх_post = main._модель_post


async def _засекая(client, инструмент, user_id, url, **kw):
    t = time.monotonic()
    try:
        return await _исх_post(client, инструмент, user_id, url, **kw)
    finally:
        ВРЕМЯ.append((инструмент, round(time.monotonic() - t, 1)))
main._модель_post = _засекая


async def _письмо_напрямую(сообщения, инструмент, uid, потолок=None):
    import httpx
    async with httpx.AsyncClient() as client:
        r = await main._модель_post(
            client, инструмент, uid, main.OPENROUTER_URL,
            headers={"Authorization": f"Bearer {main.OPENROUTER_API_KEY}",
                     "HTTP-Referer": "https://energydess.ru",
                     "X-Title": "EnergyDess HH Helper"},
            json={**main.ПОЛИТИКА_ЗАПРОСА, "model": main.LETTER_MODEL,
                  "messages": сообщения, "temperature": 0.5,
                  "max_tokens": потолок or main.LETTER_MAX_TOKENS},
            timeout=120.0)
    т = r.json()
    текст = ((т.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    return текст, т.get("usage") or {}


def main_():
    import asyncio
    db = SessionLocal()
    u = db.query(User).filter(User.email == ПОЧТА).first()
    if not u:
        _пропуск(f"на стенде нет {ПОЧТА}")
    uid = u.id
    # строки учёта ДО замера — чужие (копия стенда хранит прошлые прогоны)
    с_номера = db.query(ModelUsage.id).order_by(ModelUsage.id.desc()).limit(1).scalar() or 0
    db.close()
    c = TestClient(main.app)
    c.__enter__()
    c.cookies.set("access_token", create_token(uid))

    # 1. СТАРЫЙ ПУТЬ — боевой эндпоинт, вариант «полный»
    main.LETTER_PROMPT_VARIANT = "полный"
    r = c.post("/api/generate-letter", json={"job_text": ВАКАНСИЯ, "lang": "ru", "force": True})
    if r.status_code != 200:
        _пропуск(f"старый путь не ответил: HTTP {r.status_code} {r.text[:200]}")
    письмо_старое = r.json().get("letter") or ""
    db = SessionLocal()
    cl = (db.query(CoverLetter).filter(CoverLetter.user_id == uid)
          .order_by(CoverLetter.id.desc()).first())
    анализ = cl.analysis_json or {}
    from database import Resume, HHProfile
    резюме = db.query(Resume).filter(Resume.user_id == uid).first().resume_text
    досье = main._build_full_dossier(db.query(HHProfile).filter(HHProfile.user_id == uid).first())
    db.close()
    prompt, части = main._промпт_письма(резюме, досье, анализ, ВАКАНСИЯ, "ru")

    # 2–3. НОВЫЙ ПУТЬ — та же вакансия, тот же разбор, два раза подряд
    сообщения = main._сообщения_письма(части, "кэш")
    письмо_новое, u1 = asyncio.run(_письмо_напрямую(сообщения, "hh-letter-cache", uid))
    письмо_новое2, u2 = asyncio.run(_письмо_напрямую(сообщения, "hh-letter-cache", uid))

    # 4. ТОКЕНЫ ЧАСТЕЙ — сама модель, max_tokens=1
    токены = {}
    for к in ("примеры", "правила", "досье", "вакансия"):
        _, у = asyncio.run(_письмо_напрямую([{"role": "user", "content": части[к]}],
                                             "hh-token-count", uid, потолок=1))
        токены[к] = у.get("prompt_tokens")

    # СТРОКИ УЧЁТА — без текста
    db = SessionLocal()
    строки = (db.query(ModelUsage).filter(ModelUsage.id > с_номера)
              .order_by(ModelUsage.id).all())
    db.close()
    поля = ("id", "tool", "model", "prompt_tokens", "completion_tokens",
            "cached_tokens", "cache_write_tokens", "cost", "ok", "error_code")
    print("СТРОКИ model_usage (копия базы стенда, без текста):")
    for с in строки:
        print("  " + "  ".join(f"{п}={getattr(с, п)}" for п in поля))
    письмо_строка = [с for с in строки if с.tool == "hh-letter"][-1]
    всего = письмо_строка.prompt_tokens
    кэш1 = [с for с in строки if с.tool == "hh-letter-cache"]

    print()
    print("ЧАСТИ ЗАПРОСА К LETTER_MODEL (%s), токены — usage.prompt_tokens:" % main.LETTER_MODEL)
    знаки = {к: len(в) for к, в in части.items()}
    for к in части:
        print(f"  {к:11s} знаков {знаки[к]:6d}   токенов {токены.get(к, '—')}")
    print(f"  ВСЕГО       знаков {len(prompt):6d}   токенов {всего}")
    print(f"  постоянная часть нового пути в кэше: {кэш1[-1].cached_tokens if кэш1 else '—'}")
    print()
    print("ВРЕМЯ ВЫЗОВОВ, с:", ВРЕМЯ)
    for имя, текст in (("СТАРЫЙ", письмо_старое), ("НОВЫЙ (1-й)", письмо_новое),
                       ("НОВЫЙ (2-й)", письмо_новое2)):
        путь = os.path.join(ВЫВОД, f"письмо_{имя.split()[0].lower()}{'2' if '2-й' in имя else ''}.txt")
        with open(путь, "w", encoding="utf-8") as ф:
            ф.write(текст)
        print(f"{имя}: {len(текст)} знаков → {путь}")
    итог = {"u1": u1, "u2": u2, "токены": токены, "всего": всего, "знаки": знаки,
            "время": ВРЕМЯ, "живьём": ЖИВЬЁМ}
    with open(os.path.join(ВЫВОД, "итог.json"), "w", encoding="utf-8") as ф:
        json.dump(итог, ф, ensure_ascii=False, indent=1, default=str)
    вызовов = len(строки)
    цена = sum(с.cost or 0 for с in строки)
    print(f"ВЫЗОВОВ МОДЕЛИ: {вызовов}, сумма по usage.cost: {цена:.4f} $"
          + ("" if ЖИВЬЁМ else "  (ЗАГЛУШКА — денег нет)"))
    c.__exit__(None, None, None)
    return 0


if __name__ == "__main__":
    try:
        код = main_()
    finally:
        if ЗАГЛУШКА:
            ЗАГЛУШКА.__exit__()
    sys.exit(код)
