"""СЕРИЯ ПИСЕМ ДВУМЯ ПУТЯМИ ВСЛЕПУЮ (BACKLOG №346, заход 4, блок 2).

МЕРКА, код 0 (2 — замер не состоялся). Одна вакансия, один аккаунт стенда,
ОДИН разбор на всю серию, дальше шесть писем:
  3 старым путём («полный», одна строка — как на проде);
  3 новым («кэш»: постоянная часть под `cache_control`), ПОДРЯД —
  чтобы видеть экономику серии: первое пишет кэш, следующие читают.

Разбор общий намеренно: письмо требует ≤ 8 вызовов модели, а шесть пар
«разбор + письмо» — это 12. И сравнение от этого честнее: у шести писем
один и тот же вход, разница только в пути.

ВЫЗОВОВ РОВНО СЕМЬ: 1 разбор + 6 писем. Все через `_модель_post`, строки
учёта ложатся в копию базы стенда и печатаются без текста.

    py measure_letter_series.py            # на заглушке: механика, 0 денег
    py measure_letter_series.py --живьём   # 7 настоящих вызовов, ключ стенда

Письма пишутся в каталог вывода под номерами 1–6 в перемешанном порядке;
ключ соответствия — отдельным файлом `ключ.json` рядом с ними.

КАЖДЫЙ ОПЛАЧЕННЫЙ ОТВЕТ СОХРАНЯЕТСЯ СРАЗУ — `состояние.json` в каталоге
вывода (разбор, тексты, время, строки учёта). Первая живая версия писала
файлы только в конце: 429 на пятом вызове из семи унёс три готовых письма,
за которые уже заплачено (заход 4, блок 2). Повторный запуск с тем же
`LETTER_SERIES_OUT` продолжает С МЕСТА ОБРЫВА и зовёт модель только за тем,
чего нет. Между письмами — пауза `LETTER_SERIES_PAUSE` (30 с): 429 пришёл
через 2 с после третьего письма подряд на ~15 тыс. токенов входа.
"""
import asyncio
import json
import os
import random
import sqlite3
import sys
import tempfile
import time

import probe_guard  # noqa: F401 — внешний отказ говорится словом (§3)
import model_stub

sys.stdout.reconfigure(encoding="utf-8")

ЖИВЬЁМ = model_stub.ФЛАГ_ЖИВЬЁМ in sys.argv
КОРЕНЬ = os.path.dirname(os.path.abspath(__file__))
ИСХОДНАЯ = os.environ.get("STAND_DB") or os.path.join(КОРЕНЬ, "app.db")
ПОЧТА = os.environ.get("STAND_EMAIL", "screenshot@local.dev")
МОДЕЛЬ_ПИСЬМА = os.environ.get("LETTER_MODEL_MEASURE", "anthropic/claude-opus-4-8")
ВЫВОД = os.environ.get("LETTER_SERIES_OUT") or tempfile.mkdtemp(prefix="letter_series_")
os.makedirs(ВЫВОД, exist_ok=True)


def _пропуск(причина):
    print("ПРОПУСК: " + причина)
    sys.exit(2)


if ЖИВЬЁМ:
    model_stub.живой_замер("measure_letter_series (7 вызовов, из них 6 на Opus)")
if "/data/" in ИСХОДНАЯ.replace("\\", "/"):
    _пропуск("путь к боевой базе — мерка ходит только по стенду")
if not os.path.exists(ИСХОДНАЯ):
    _пропуск(f"базы стенда нет ({ИСХОДНАЯ})")
_путь = os.path.join(tempfile.mkdtemp(prefix="letter_series_db_"), "app.db")
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
    os.environ["OPENROUTER_STAND_KEY"] = "stub-letter-series"

import main                                   # noqa: E402
import letter_facts                           # noqa: E402


def _вакансия():
    """Та же вакансия, что в заходе 3 — литерал из `measure_letter_prompt.py`
    РАЗБОРОМ, а не импортом: импорт исполняет чужую шапку (копия базы,
    подмена DB_PATH, баннер живого замера)."""
    import ast
    дерево = ast.parse(open(os.path.join(КОРЕНЬ, "measure_letter_prompt.py"), encoding="utf-8").read())
    for узел in дерево.body:
        if isinstance(узел, ast.Assign) and getattr(узел.targets[0], "id", "") == "ВАКАНСИЯ":
            return ast.literal_eval(узел.value)
    raise ValueError("в measure_letter_prompt.py нет ВАКАНСИЯ")


ВАКАНСИЯ = _вакансия()
# План серии: «оба» — 3 старым путём и 3 новым вслепую (заход 4);
# «кэш» — контрольная серия заход 6: 1 разбор и 3 письма новым путём,
# каждое через проверку 44 с настройками досье аккаунта. Вызовов 4.
ПЛАН = os.environ.get("LETTER_SERIES_PLAN", "оба")
if ПЛАН not in ("оба", "кэш"):
    _пропуск(f"незнакомый LETTER_SERIES_PLAN: {ПЛАН}")
ПАУЗА = float(os.environ.get("LETTER_SERIES_PAUSE", "30" if ЖИВЬЁМ else "0"))
СОСТОЯНИЕ = os.path.join(ВЫВОД, "состояние.json")


def _записать(с):
    with open(СОСТОЯНИЕ, "w", encoding="utf-8") as ф:
        json.dump(с, ф, ensure_ascii=False, indent=1)
from database import SessionLocal, User, Resume, HHProfile, ModelUsage  # noqa: E402

if ЖИВЬЁМ and not main.OPENROUTER_API_KEY:
    _пропуск("живого ключа стенда нет: " + main.КЛЮЧ_НЕТ_ПРИЧИНА)


def _ответ_заглушки(запрос):
    j = запрос.get("json") or {}
    знаков = len(json.dumps(j.get("messages"), ensure_ascii=False))
    if j.get("model") == main.ANALYZE_MODEL:
        return model_stub.тело(json.dumps({
            "job_title": "Python-разработчик", "company_name": "", "relevance_score": 7,
            "relevance_reason": "", "key_matches": ["FastAPI"], "missing_skills": [],
            "tone_suggestion": "деловой", "relevant_portfolio_links": ["https://energydess.ru"],
            "focus_points": ["API"]}, ensure_ascii=False))
    return model_stub.тело("ПИСЬМО-ЗАГЛУШКА energydess.ru", токены_входа=знаков // 2)


if ЗАГЛУШКА:
    ЗАГЛУШКА.ответ = _ответ_заглушки


async def _вызов(модель, сообщения, инструмент, uid, потолок, температура):
    import httpx
    t = time.monotonic()
    async with httpx.AsyncClient() as client:
        r = await main._модель_post(
            client, инструмент, uid, main.OPENROUTER_URL,
            headers={"Authorization": f"Bearer {main.OPENROUTER_API_KEY}",
                     "HTTP-Referer": "https://energydess.ru", "X-Title": "EnergyDess HH Helper"},
            json={**main.ПОЛИТИКА_ЗАПРОСА, "model": модель, "messages": сообщения,
                  "temperature": температура, "max_tokens": потолок},
            timeout=180.0)
    сек = round(time.monotonic() - t, 1)
    if r.status_code != 200:
        _пропуск(f"{инструмент}: HTTP {r.status_code} {r.text[:300]}")
    текст, сбой = main._model_output(r.json(), инструмент, потолок)
    if сбой:
        _пропуск(f"{инструмент}: {сбой}")
    return текст, сек


def _последняя_строка():
    db = SessionLocal()
    try:
        return db.query(ModelUsage.id).order_by(ModelUsage.id.desc()).limit(1).scalar() or 0
    finally:
        db.close()


def _строки_после(номер):
    db = SessionLocal()
    try:
        return db.query(ModelUsage).filter(ModelUsage.id > номер).order_by(ModelUsage.id).all()
    finally:
        db.close()


def main_():
    db = SessionLocal()
    u = db.query(User).filter(User.email == ПОЧТА).first()
    if not u:
        _пропуск(f"на стенде нет {ПОЧТА}")
    uid = u.id
    резюме = db.query(Resume).filter(Resume.user_id == uid).first().resume_text
    проф = db.query(HHProfile).filter(HHProfile.user_id == uid).first()
    полное = main._build_full_dossier(проф)
    группы = letter_facts.ссылки_проектов(проф.projects if проф else [])
    концовка = проф.ending_style if проф else None
    нельзя = (проф.never_mention or "") if проф else ""
    db.close()

    с = json.load(open(СОСТОЯНИЕ, encoding="utf-8")) if os.path.exists(СОСТОЯНИЕ) else {}
    if с:
        print(f"ПРОДОЛЖЕНИЕ: разбор {'есть' if с.get('анализ') else 'нет'}, писем {len(с.get('письма', []))} из 6")

    # 1. ОДИН РАЗБОР — боевым эндпоинтом, второго текста запроса мерка не держит
    if not с.get("анализ"):
        from auth import create_token
        from fastapi.testclient import TestClient
        c = TestClient(main.app)
        c.__enter__()
        c.cookies.set("access_token", create_token(uid))
        до_разбора = _последняя_строка()
        t0 = time.monotonic()
        r = c.post("/api/analyze-vacancy", json={"job_text": ВАКАНСИЯ})
        с["сек_разбора"] = round(time.monotonic() - t0, 1)
        c.__exit__(None, None, None)
        if r.status_code != 200 or "error" in r.json():
            _пропуск(f"разбор: HTTP {r.status_code} {r.text[:200]}")
        с["анализ"] = r.json()
        с["письма"] = []
        строки = _строки_после(до_разбора)
        с["цена_разбора"] = sum(ст.cost or 0 for ст in строки)
        с["вызовов_разбора"] = len(строки)
        с["разбор_только_что"] = True
        _записать(с)
    анализ, сек_разбора = с["анализ"], с["сек_разбора"]
    print(f"РАЗБОР: {сек_разбора} с, ссылки анализатора: {анализ.get('relevant_portfolio_links')}")

    _, части = main._промпт_письма(резюме, полное, анализ, ВАКАНСИЯ, "ru", группы)
    if ПЛАН == "кэш":
        # Контрольная серия (№346, заход 6): только новый путь, 3 письма подряд
        план = (("новый", "кэш", "hh-letter-cache"),) * 3
    else:
        план = (("старый", "полный", "hh-letter"),) * 3 + (("новый", "кэш", "hh-letter-cache"),) * 3
    for путь, вариант, инструмент in план[len(с["письма"]):]:
        # Пауза перед КАЖДЫМ вызовом после первого, включая первое письмо
        # сразу за разбором: иначе разбор и письмо шли вплотную (заход 5).
        if ПАУЗА and (с["письма"] or с.pop("разбор_только_что", False)):
            time.sleep(ПАУЗА)
        с_номера_письма = _последняя_строка()
        текст, сек = asyncio.run(_вызов(main.LETTER_MODEL, main._сообщения_письма(части, вариант),
                                        инструмент, uid, main.LETTER_MAX_TOKENS, 0.5))
        строка = _строки_после(с_номера_письма)[-1]
        с["письма"].append({"путь": путь, "текст": текст, "сек": сек,
                            "вход": строка.prompt_tokens, "из_кэша": строка.cached_tokens,
                            "в_кэш": строка.cache_write_tokens, "цена": строка.cost,
                            "выход": строка.completion_tokens})
        _записать(с)
    письма = с["письма"]

    if ПЛАН == "кэш":
        # Каждое письмо — через проверку 44 с настройками досье ЭТОГО аккаунта
        нарушивших = 0
        for n, п in enumerate(письма, 1):
            р = letter_facts.проверить(п["текст"], полное, резюме, ВАКАНСИЯ, группы,
                                       концовка=концовка, не_упоминать=нельзя)
            нарушивших += bool(р["запреты"])
            with open(os.path.join(ВЫВОД, f"письмо_{n}.txt"), "w", encoding="utf-8") as ф:
                ф.write(п["текст"])
            print(f"ПИСЬМО {n}: вход {п['вход']}, из кэша {п['из_кэша'] or 0}, в кэш {п['в_кэш'] or 0}, "
                  f"выход {п['выход']}, цена {п['цена'] or 0:.4f} $, {п['сек']} с")
            print(f"  проверка 44: {letter_facts.строкой(р)}")
            for раздел, кусок in р["запреты"].items():
                print(f"  НАРУШЕНИЕ «{раздел}»: {кусок!r}")
        всего = sum(п["цена"] or 0 for п in письма) + (с.get("цена_разбора") or 0)
        print(f"СЕРИЯ: писем {len(письма)}, с нарушением запретов досье {нарушивших}; "
              f"разбор {с.get('цена_разбора') or 0:.4f} $; всего {всего:.4f} $")
        print(f"ПИСЬМА: {ВЫВОД}")
        return 0

    # ВСЛЕПУЮ: номера 1–6 в случайном порядке, ключ — отдельным файлом
    порядок = list(range(6))
    random.Random().shuffle(порядок)
    ключ = {}
    for номер, i in enumerate(порядок, 1):
        with open(os.path.join(ВЫВОД, f"письмо_{номер}.txt"), "w", encoding="utf-8") as ф:
            ф.write(письма[i]["текст"])
        ключ[номер] = письма[i]["путь"] + f" #{i % 3 + 1}"
    with open(os.path.join(ВЫВОД, "вакансия.txt"), "w", encoding="utf-8") as ф:
        ф.write(ВАКАНСИЯ)
    with open(os.path.join(ВЫВОД, "ключ.json"), "w", encoding="utf-8") as ф:
        json.dump(ключ, ф, ensure_ascii=False, indent=1)

    print("ТАБЛИЦА (по номеру вслепую; путь — в ключ.json):")
    print("  №  вход   из_кэша  в_кэш   выход  цена $    время с")
    обратно = {i: n for n, i in enumerate(порядок, 1)}
    for i in sorted(range(6), key=lambda k: обратно[k]):
        п = письма[i]
        print(f"  {обратно[i]}  {п['вход']:<6} {п['из_кэша'] or 0:<8} {п['в_кэш'] or 0:<7} "
              f"{п['выход']:<6} {п['цена'] or 0:<9.4f} {п['сек']}")
    ст = [п for п in письма if п["путь"] == "старый"]
    нв = [п for п in письма if п["путь"] == "новый"]
    ср = lambda xs: sum(xs) / len(xs)
    print(f"СРЕДНЯЯ ЦЕНА ПИСЬМА: старый путь {ср([п['цена'] or 0 for п in ст]):.4f} $, "
          f"новый при серии из трёх {ср([п['цена'] or 0 for п in нв]):.4f} $")
    времена = sorted(п["сек"] for п in письма)
    медиана = (времена[2] + времена[3]) / 2
    полное_время = sorted(п["сек"] + сек_разбора for п in письма)
    print(f"ВРЕМЯ ПИСЬМА: медиана {медиана:.1f} с; с разбором {сек_разбора} с — "
          f"медиана {(полное_время[2] + полное_время[3]) / 2:.1f} с")
    всего = sum(п["цена"] or 0 for п in письма)
    print(f"РАЗБОР: вызовов {с.get('вызовов_разбора', '?')}, цена {с.get('цена_разбора') or 0:.4f} $; "
          f"ВСЕГО ЗА СЕРИЮ: {всего + (с.get('цена_разбора') or 0):.4f} $")
    print(f"ПИСЕМ {len(письма)}, сумма по usage.cost писем: {всего:.4f} $ (разбор — строкой [analyze] выше)"
          + ("" if ЖИВЬЁМ else "  (ЗАГЛУШКА — денег нет)"))
    print(f"ПИСЬМА: {ВЫВОД}")
    print(f"КЛЮЧ: {os.path.join(ВЫВОД, 'ключ.json')}")
    return 0


if __name__ == "__main__":
    try:
        код = main_()
    finally:
        if ЗАГЛУШКА:
            ЗАГЛУШКА.__exit__()
    sys.exit(код)
