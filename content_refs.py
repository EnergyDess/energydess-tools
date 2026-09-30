"""БИБЛИОТЕКА РОЛИКОВ-ОБРАЗЦОВ ФОРМАТОВ (письмо B, блок 1).

Пакет ролика строит сценарий по структуре НАСТОЯЩИХ удачных роликов
того же формата, а не по пустому шаблону. Здесь эти ролики отбираются
и разбираются: крючок первых 30 с, сегменты с таймкодами, приёмы
удержания, темп, что в кадре, концовка, название и превью.

РОЛИК НЕ СКАЧИВАЕТСЯ — ни байта видео, это правила YouTube. Разбирает
Gemini ПО ССЫЛКЕ на публичный ролик: официальная возможность Gemini API
(`fileData.fileUri` с адресом youtube.com; только публичные ролики,
в бесплатном ярусе не больше 8 часов видео в сутки). Картинка ПРЕВЬЮ —
публичная картинка `i.ytimg.com`, её берём и отдаём модели как есть.

ОТБОР: на формат текущей фазы и фазы any — до `per_format` роликов:
лучший по выстрелу хит археологии на русском, лучший на английском,
свежий ролик радара с аномалией от `radar_min_anomaly` (ролики берутся
из основы идей этого формата — у записей радара формата нет), остаток —
следующие хиты по выстрелу.

ПРОВЕРКА ДО МОДЕЛИ: `videos.list` (1 ед. квоты на 50 роликов) — удалён,
не публичный, возрастное ограничение, длиннее `max_minutes` — пропуск
с причиной без единого вызова модели. Пропуск НАВСЕГДА (`skipped`),
сбой сервиса — `error`, следующий прогон попробует снова (до 3 раз).
Уже разобранное (`ok`) повторно не разбирается.

ДЕНЬГИ: у Gemini в ответе только ТОКЕНЫ, стоимости нет. Цена считается
по прайсу — `ЦЕНЫ` ниже, числом с датой сверки, — и пишется в тот же
`model_usage` операцией `admin-content-refs`: иначе бюджет модуля
(§5.11) образцов бы не видел. Бюджет спрашивается ДО каждого вызова;
у прогона свой потолок `run_usd_cap`, чтобы образцы не съели день идей.
"""
from __future__ import annotations

import base64
import os
import time
import traceback
from datetime import datetime, timedelta

import httpx

import content_collect as cc
import content_db as cdb
import content_engine as ce
from content_db import (ContentArchVideo, ContentFormat, ContentIdea, ContentItem, ContentRef,
                        ContentRun, ContentTheme)

ИНСТРУМЕНТ = "admin-content-refs"
GEMINI_URL = os.getenv("GEMINI_URL", "https://generativelanguage.googleapis.com/v1beta")
REFS_MODEL = os.getenv("CONTENT_REFS_MODEL", "gemini-2.5-flash")
REFS_MAX_TOKENS = int(os.getenv("CONTENT_REFS_MAX_TOKENS", "4000"))
# ЦЕНА ЗА МИЛЛИОН ТОКЕНОВ, $ (вход видео/картинки/текст, выход). Сверено
# с ai.google.dev/gemini-api/docs/pricing 2026-09-30. Модель не из списка —
# стоимость пуста, строка расхода помечена `cost_missing`.
ЦЕНЫ = {"gemini-2.5-flash": (0.30, 2.50), "gemini-2.5-flash-lite": (0.10, 0.40)}
ПОПЫТОК_ПРИ_СБОЕ = 3
ПОТОЛОК_РОЛИКА_СЕК = 240

РОЛИ = ("завязка", "факт", "сравнение", "поворот", "пик", "вывод")

ПРОМПТ = (
    "Ты разбираешь YouTube-ролик про игры как образец формата для автора канала. "
    "Смотри видео и превью. Ответ — строго JSON без пояснений вокруг, по-русски:\n"
    '{"hook": {"said": "что сказано в первые 30 с", "shown": "что показано", '
    '"trick": "каким приёмом цепляют"},\n'
    ' "segments": [{"from": "0:00", "to": "0:45", "role": "завязка|факт|сравнение|поворот|пик|вывод", '
    '"what": "о чём сегмент одной фразой"}],\n'
    ' "retention": ["приёмы удержания: вопросы зрителю, обещания «дальше будет…», смена темпа, повторы — '
    'каждый с таймкодом"],\n'
    ' "pace": {"cuts_per_min": число, "talking_head_share": доля 0..1, "gameplay_share": доля 0..1},\n'
    ' "visuals": ["что показано в кадре: трейлер, геймплей, экран пополам, графика — что встречается"],\n'
    ' "ending": {"what": "чем заканчивается", "cta": "призыв к зрителю"},\n'
    ' "packaging": {"title_trick": "чем цепляет название", "thumbnail": "что на превью и текст на нём"}}\n'
    "Таймкоды — по видео, от 4 до 15 сегментов на весь ролик. Не выдумывай: чего не видно — пиши «не видно»."
)


class Пропуск(Exception):
    """Ролик недоступен навсегда — повтор не поможет."""


class Сбой(Exception):
    """Разбор не вышел сейчас — следующий прогон попробует снова."""


def ключ() -> str:
    return os.getenv("GEMINI_API_KEY", "").strip()


def цена(модель: str, вход: int, выход: int) -> float | None:
    ц = ЦЕНЫ.get(модель)
    if ц is None:
        return None
    return round((вход * ц[0] + выход * ц[1]) / 1_000_000, 6)


def _минут(iso: str | None) -> float | None:
    """ISO 8601 длительность YouTube (PT1H2M3S) → минуты."""
    import re
    м = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not м:
        return None
    д, ч, мин, с = (int(x or 0) for x in м.groups())
    return round(д * 1440 + ч * 60 + мин + с / 60, 2)


# ── ОТБОР ─────────────────────────────────────────────────────────────

def форматы_фазы(db, тема_id: str) -> list[ContentFormat]:
    фаза = cdb.фаза_сейчас(cdb.настройка(db, "phases"))
    return (db.query(ContentFormat).filter(ContentFormat.theme_id == тема_id,
                                           ContentFormat.status == "active",
                                           ContentFormat.phase.in_((фаза, "any")))
            .order_by(ContentFormat.sort, ContentFormat.id).all())


def отобрать(db, тема_id: str, настройки: dict) -> list[dict]:
    """Кандидаты в образцы: [{format_id, yt_id, title, channel_title, lang, origin, shot}]."""
    на_формат = int(настройки.get("per_format", 3))
    порог = float(настройки.get("radar_min_anomaly", 3))
    итог = []
    for ф in форматы_фазы(db, тема_id):
        хиты = (db.query(ContentArchVideo).filter(ContentArchVideo.theme_id == тема_id,
                                                  ContentArchVideo.format_id == ф.id,
                                                  ContentArchVideo.shot.isnot(None))
                .order_by(ContentArchVideo.shot.desc()).all())
        выбрано: list[dict] = []

        def взять(yt, title, канал, язык, откуда, выстрел):
            if len(выбрано) < на_формат and yt and all(в["yt_id"] != yt for в in выбрано):
                выбрано.append({"format_id": ф.id, "yt_id": yt, "title": title,
                                "channel_title": канал, "lang": язык, "origin": откуда,
                                "shot": выстрел})

        for язык in ("ru", "en"):
            х = next((х for х in хиты if х.channel_lang == язык), None)
            if х is not None:
                взять(х.yt_id, х.title, х.channel_title, х.channel_lang, "arch", х.shot)
        ids = set()
        for и in db.query(ContentIdea.basis).filter(ContentIdea.theme_id == тема_id,
                                                    ContentIdea.format_id == ф.id):
            ids.update((cdb.из_json(и.basis, {}) or {}).get("ролики") or [])
        if ids:
            р = (db.query(ContentItem).filter(ContentItem.id.in_(list(ids)[:200]),
                                              ContentItem.platform == "youtube",
                                              ContentItem.anomaly >= порог)
                 .order_by(ContentItem.anomaly.desc()).first())
            if р is not None and (р.ext_id or "").startswith("yt:"):
                взять(р.ext_id[3:], р.title, р.source_name, р.lang, "radar", р.anomaly)
        for х in хиты:
            взять(х.yt_id, х.title, х.channel_title, х.channel_lang, "arch", х.shot)
        итог.extend(выбрано)
    return итог


def нужно_разобрать(db, кандидаты: list[dict]) -> list[dict]:
    """Без уже разобранного и навсегда пропущенного. Сбой — до 3 попыток."""
    итог = []
    for к in кандидаты:
        с = (db.query(ContentRef).filter(ContentRef.format_id == к["format_id"],
                                         ContentRef.yt_id == к["yt_id"]).first())
        if с is not None and (с.state in ("ok", "skipped") or с.tries >= ПОПЫТОК_ПРИ_СБОЕ):
            continue
        итог.append(к)
    return итог


# ── ПРОВЕРКА ДО МОДЕЛИ ────────────────────────────────────────────────

async def сведения(client, ids: list[str]) -> dict | None:
    """{yt_id: {минут, публичный, возраст, есть}} через videos.list; ключа
    YouTube нет — None (проверка до модели не делается, решит Gemini)."""
    клю = ce.ключ_youtube()
    if not клю or not ids:
        return None
    db = ce.SessionLocal()
    try:
        осталось = (int(cdb.настройка(db, "youtube").get("daily_cap", 9000))
                    - cdb.квота_израсходовано(db))
    finally:
        db.close()
    квота = cc.Квота(осталось, ce._списать_квоту)
    база = os.getenv("CONTENT_YOUTUBE_URL", ce.YT_ПО_УМОЛЧАНИЮ)
    итог = {}
    for i in range(0, len(ids), 50):
        пачка = ids[i:i + 50]
        тело = await cc._yt(client, база, "videos", {
            "part": "contentDetails,status", "id": ",".join(пачка), "maxResults": 50},
            клю, квота, cc.ЦЕНА_СПИСКА)
        for э in тело.get("items") or []:
            if not isinstance(э, dict) or not э.get("id"):
                continue
            дет, ст = э.get("contentDetails") or {}, э.get("status") or {}
            итог[э["id"]] = {"минут": _минут(дет.get("duration")),
                             "публичный": ст.get("privacyStatus") == "public",
                             "возраст": (дет.get("contentRating") or {}).get("ytRating") == "ytAgeRestricted"}
    return итог


def причина_пропуска(с: dict | None, есть_сведения: bool, предел_мин: float) -> str | None:
    if not есть_сведения:
        return None
    if с is None:
        return "ролик удалён или недоступен (YouTube его не отдаёт)"
    if not с["публичный"]:
        return "ролик не публичный — Gemini разбирает только публичные"
    if с["возраст"]:
        return "18+: у ролика возрастное ограничение"
    if с["минут"] is not None and с["минут"] > предел_мин:
        return "ролик длиннее %d мин (%.0f мин) — разбор дороже пользы" % (предел_мин, с["минут"])
    return None


# ── РАЗБОР ────────────────────────────────────────────────────────────

async def _превью(client, yt_id: str) -> dict | None:
    """Картинка превью inline для модели; не вышло — разбор без неё."""
    try:
        r = await client.get(f"https://i.ytimg.com/vi/{yt_id}/hqdefault.jpg")
    except httpx.HTTPError:
        return None
    if r.status_code != 200 or len(r.content) > 400_000:
        return None
    return {"inlineData": {"mimeType": "image/jpeg",
                           "data": base64.b64encode(r.content).decode("ascii")}}


def разобрать_ответ(текст: str) -> dict:
    """JSON разбора; не той формы — Сбой (модель ответит иначе в другой раз)."""
    данные = ce._json_ответа(текст or "")
    if not isinstance(данные, dict):
        raise Сбой("Gemini ответил не JSON")
    сегменты = данные.get("segments")
    if not isinstance(данные.get("hook"), dict) or not isinstance(сегменты, list) or len(сегменты) < 2:
        raise Сбой("в разборе нет крючка или сегментов")
    for с in сегменты:
        if not isinstance(с, dict) or not с.get("from") or not с.get("what"):
            raise Сбой("сегмент без таймкода или описания")
        if с.get("role") not in РОЛИ:
            с["role"] = "факт"
    for поле in ("retention", "visuals"):
        if not isinstance(данные.get(поле), list):
            данные[поле] = []
    for поле in ("pace", "ending", "packaging"):
        if not isinstance(данные.get(поле), dict):
            данные[поле] = {}
    return данные


def _отказ_gemini(r) -> Exception:
    """Отказ Gemini: недоступный ролик — Пропуск, прочее — Сбой."""
    try:
        ошибка = (r.json() or {}).get("error") or {}
    except ValueError:
        ошибка = {}
    текст = str(ошибка.get("message") or "")[:200]
    низ = текст.lower()
    if r.status_code in (400, 403, 404) and any(с in низ for с in (
            "private", "not found", "unavailable", "age", "restricted", "permission",
            "video", "youtube", "cannot be accessed")):
        return Пропуск("Gemini не смог открыть ролик: " + (текст or "HTTP %d" % r.status_code))
    return Сбой("Gemini: HTTP %d%s" % (r.status_code, (" — " + текст) if текст else ""))


async def разобрать(client, yt_id: str, fps: float | None) -> tuple[dict, dict]:
    """(разбор, расход {вход, выход, cost}). Пропуск / Сбой — исключением."""
    клю = ключ()
    if not клю:
        raise Сбой("нет ключа Gemini (GEMINI_API_KEY)")
    видео = {"fileData": {"fileUri": f"https://www.youtube.com/watch?v={yt_id}"}}
    if fps:
        видео["videoMetadata"] = {"fps": fps}
    части = [видео]
    превью = await _превью(client, yt_id)
    if превью:
        части.append(превью)
    части.append({"text": ПРОМПТ})
    тело = {"contents": [{"role": "user", "parts": части}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0,
                                 "maxOutputTokens": REFS_MAX_TOKENS,
                                 "mediaResolution": "MEDIA_RESOLUTION_LOW",
                                 "thinkingConfig": {"thinkingBudget": 0}}}
    м = ce._main()
    try:
        r = await client.post(f"{GEMINI_URL.rstrip('/')}/models/{REFS_MODEL}:generateContent",
                              json=тело, headers={"x-goog-api-key": клю},
                              timeout=httpx.Timeout(ПОТОЛОК_РОЛИКА_СЕК, connect=15.0))
    except httpx.HTTPError as e:
        м._записать_расход(ИНСТРУМЕНТ, REFS_MODEL, None, {"ok": False, "error_code": type(e).__name__})
        raise Сбой(f"Gemini не ответил ({type(e).__name__})")
    try:
        ответ = r.json()
    except ValueError:
        ответ = {}
    уч = ответ.get("usageMetadata") or {} if isinstance(ответ, dict) else {}
    вход = int(уч.get("promptTokenCount") or 0)
    выход = int(уч.get("candidatesTokenCount") or 0) + int(уч.get("thoughtsTokenCount") or 0)
    стоимость = цена(REFS_MODEL, вход, выход) if r.status_code == 200 else None
    м._записать_расход(ИНСТРУМЕНТ, REFS_MODEL, None, {
        "ok": r.status_code == 200, "error_code": None if r.status_code == 200 else f"http_{r.status_code}",
        "prompt_tokens": вход or None, "completion_tokens": выход or None,
        "cost": стоимость if r.status_code == 200 else 0.0})
    if r.status_code != 200:
        raise _отказ_gemini(r)
    блок = (ответ.get("promptFeedback") or {}).get("blockReason")
    if блок:
        raise Пропуск(f"Gemini отказался разбирать ролик ({блок})")
    кандидаты = ответ.get("candidates") or []
    if not кандидаты:
        raise Сбой("Gemini вернул пустой ответ")
    конец = кандидаты[0].get("finishReason")
    if конец in ("SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII"):
        raise Пропуск(f"Gemini отказался разбирать ролик ({конец})")
    текст = "".join(ч.get("text", "") for ч in ((кандидаты[0].get("content") or {}).get("parts") or [])
                    if isinstance(ч, dict))
    if конец == "MAX_TOKENS":
        raise Сбой("разбор не поместился в потолок ответа")
    return разобрать_ответ(текст), {"вход": вход, "выход": выход, "cost": стоимость}


# ── ПРОГОН ────────────────────────────────────────────────────────────

def _сохранить(к: dict, состояние: str, причина: str | None, разбор: dict | None,
               стоимость: float | None, минут: float | None, тема_id: str) -> None:
    db = ce.SessionLocal()
    try:
        с = (db.query(ContentRef).filter(ContentRef.format_id == к["format_id"],
                                         ContentRef.yt_id == к["yt_id"]).first())
        if с is None:
            с = ContentRef(theme_id=тема_id, format_id=к["format_id"], yt_id=к["yt_id"],
                           origin=к["origin"], tries=0)
            db.add(с)
        с.title, с.channel_title, с.lang, с.shot = к.get("title"), к.get("channel_title"), к.get("lang"), к.get("shot")
        с.state, с.reason, с.minutes = состояние, (причина or None), минут
        с.tries = (с.tries or 0) + (1 if состояние == "error" else 0)
        if разбор is not None:
            с.analysis, с.model, с.analyzed_at = cdb.в_json(разбор), REFS_MODEL, datetime.utcnow()
        if стоимость is not None:
            с.cost = round((с.cost or 0) + стоимость, 6)
        db.commit()
    finally:
        db.close()


async def прогон(повод: str = "admin") -> dict:
    """Один прогон библиотеки образцов по всем активным темам."""
    номер = ce._начать("refs", повод)
    t0 = time.monotonic()
    итог = {"кандидатов": 0, "разобрано": 0, "пропущено": 0, "сбоев": 0, "usd": 0.0,
            "пропуски": [], "стоп": None}
    состояние, заметка = "ok", None
    import content_worker as cw
    try:
        if not ключ():
            raise Сбой("нет ключа Gemini (GEMINI_API_KEY) — образцы не разбираются")
        db = ce.SessionLocal()
        try:
            cdb.засеять(db)
            настройки = cdb.настройка(db, "refs")
            темы = [т.id for т in db.query(ContentTheme).filter(ContentTheme.active.is_(True))]
            очередь = []
            for т in темы:
                очередь += [(т, к) for к in нужно_разобрать(db, отобрать(db, т, настройки))]
        finally:
            db.close()
        итог["кандидатов"] = len(очередь)
        предел_прогона = float(настройки.get("run_usd_cap", 0.6))
        предел_мин = float(настройки.get("max_minutes", 30))
        fps = настройки.get("fps")
        async with cc.новый_клиент() as client:
            try:
                св = await сведения(client, sorted({к["yt_id"] for _, к in очередь}))
            except (cc.ОтказИсточника, cc.КвотаИсчерпана) as e:
                print(f"[content] образцы: проверка до модели не вышла: {e}", flush=True)
                св = None
            for n, (тема_id, к) in enumerate(очередь, 1):
                cw.ход("образцы", n - 1, len(очередь))
                с = (св or {}).get(к["yt_id"])
                минут = с["минут"] if с else None
                причина = причина_пропуска(с, св is not None, предел_мин)
                if причина:
                    _сохранить(к, "skipped", причина, None, None, минут, тема_id)
                    итог["пропущено"] += 1
                    итог["пропуски"].append({"yt": к["yt_id"], "причина": причина})
                    continue
                db = ce.SessionLocal()
                try:
                    б = ce.бюджет(db)
                finally:
                    db.close()
                if б["исчерпан"]:
                    итог["стоп"] = "бюджет"
                    заметка = б["текст"]
                    break
                if итог["usd"] >= предел_прогона:
                    итог["стоп"] = "потолок прогона"
                    заметка = ("Потолок прогона образцов %.2f $ достигнут — остальное "
                               "разберёт следующий прогон" % предел_прогона)
                    break
                try:
                    разбор, расход = await разобрать(client, к["yt_id"], fps)
                except Пропуск as e:
                    _сохранить(к, "skipped", str(e), None, None, минут, тема_id)
                    итог["пропущено"] += 1
                    итог["пропуски"].append({"yt": к["yt_id"], "причина": str(e)})
                    continue
                except Сбой as e:
                    _сохранить(к, "error", str(e), None, None, минут, тема_id)
                    итог["сбоев"] += 1
                    print(f"[content] образец {к['yt_id']}: {e}", flush=True)
                    continue
                итог["usd"] = round(итог["usd"] + (расход["cost"] or 0), 6)
                _сохранить(к, "ok", None, разбор, расход["cost"], минут, тема_id)
                итог["разобрано"] += 1
            cw.ход("образцы", len(очередь), len(очередь), сразу=True)
        if итог["стоп"] or итог["сбоев"]:
            состояние = "partial"
            заметка = заметка or "сбоев разбора: %d" % итог["сбоев"]
    except Сбой as e:
        состояние, заметка = "error", str(e)
    except Exception as e:
        traceback.print_exc()
        состояние, заметка = "error", f"{type(e).__name__}: {e}"
    итог["сек"] = round(time.monotonic() - t0, 1)
    итог["пропуски"] = итог["пропуски"][:30]
    ce._закончить(номер, состояние, итог, заметка)
    print(f"[content] образцы №{номер}: {состояние}, разобрано {итог['разобрано']}, "
          f"пропущено {итог['пропущено']}, {итог['usd']} $", flush=True)
    return {"run_id": номер, "state": состояние, "note": заметка, **итог}


def нужны(сейчас: datetime | None = None) -> bool:
    """Автозапуск: ключ есть и удачного прогона не было `every_days` дней,
    либо прошлый остановил бюджет, а московские сутки с тех пор сменились."""
    if not ключ():
        return False
    сейчас = сейчас or datetime.utcnow()
    db = ce.SessionLocal()
    try:
        дней = float(cdb.настройка(db, "refs").get("every_days", 7))
        п = (db.query(ContentRun).filter(ContentRun.kind == "refs",
                                         ContentRun.state.in_(("ok", "partial")))
             .order_by(ContentRun.id.desc()).first())
    finally:
        db.close()
    if п is None:
        return True
    стоп = (cdb.из_json(п.summary, {}) or {}).get("стоп")
    if стоп and п.started_at < ce._полночь_мск_utc(сейчас):
        return True
    return п.started_at < сейчас - timedelta(days=дней)


def сводка(db) -> dict:
    """Для «Кухни»: сколько разобрано, пропущено и во что обошлось."""
    from sqlalchemy import func
    по = dict(db.query(ContentRef.state, func.count(ContentRef.id)).group_by(ContentRef.state).all())
    usd = db.query(func.sum(ContentRef.cost)).scalar() or 0.0
    п = (db.query(ContentRun).filter(ContentRun.kind == "refs").order_by(ContentRun.id.desc()).first())
    return {"разобрано": по.get("ok", 0), "пропущено": по.get("skipped", 0),
            "сбоев": по.get("error", 0), "usd": round(float(usd), 4),
            "ключ": bool(ключ()),
            "последний": ({"state": п.state, "note": п.note, "когда": п.finished_at or п.started_at}
                          if п else None)}


def для_формата(db, format_id: int, штук: int = 3) -> list[ContentRef]:
    """Разобранные образцы формата — лучшие по выстрелу."""
    return (db.query(ContentRef).filter(ContentRef.format_id == format_id, ContentRef.state == "ok")
            .order_by(ContentRef.shot.desc().nullslast(), ContentRef.id).limit(штук).all())


def запустить(повод: str = "admin") -> dict:
    import content_worker as cw
    return cw.запустить("refs", прогон, повод)
