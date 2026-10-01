"""ПАКЕТ РОЛИКА (письмо B, блок 2).

По кнопке «Собрать пакет ролика» фоновая задача собирает всё, с чем можно
садиться записывать: названия, превью, крючок, сценарий с таймкодами
по структуре разобранных образцов формата (`content_refs`), список
съёмок, проверку перед публикацией и источники для описания.

ФАКТЫ — ТОЛЬКО ИЗ ИСТОЧНИКОВ. Модель получает записи сюжета под их
номерами в базе и обязана у каждой фразы-факта назвать номера записей.
Номер не из набора либо фраза-факт без номера — подсветка «проверь»
на экране: проверяет КОД, а не просьба в промпте. Идея по слуху — слух:
слова «официально», «подтвердил» у фразы без официального источника —
тоже «проверь».

СТОП-СЛОВА НАЗВАНИЙ (список в базе, `package.stop_words`) — перегенерация
до `title_tries` раз; дальше такие названия выкидываются кодом: в пакете
их нет никогда. Сюжет с утечкой — из списка съёмок кодом убираются кадры
утечки и встаёт предупреждение.

МАТЕРИАЛ — ВОЛНА, А НЕ ОДНА ЗАПИСЬ (письмо B2). К записям сюжета
добавляются записи той же волны из СМИ и официальных источников
(`записи_волны`), и первоисточник волны (Game Informer и др. из
`waves.sources`) идёт в списке ПЕРВЫМ. Ролики YouTube — вторичны: их
утверждения с таймкодами выписывает Gemini по ссылке. Полный текст статьи
не скачивается — правила сайтов (не только robots.txt) это запрещают либо
не проверены; в модель уходит описание из ленты.

ДЛИНА ПО МАТЕРИАЛУ. Уникальные факты источников считаются отдельным
шагом; их число задаёт длительность, а меньше `short_facts` фактов —
предложение Shorts либо ролика до 5 минут с причиной.

ВТОРАЯ ПРОВЕРКА ФАКТОВ — отдельный вызов: модель выписывает ВСЕ
утверждения сценария (включая «впервые», «раньше не было», сравнения
и «в два раза») и для каждого называет запись-источник либо пункт базы
знаний серии (`knowledge` на «Кухне»). Опору сверяет КОД: номер не из набора
и пункт базы, которого нет, — «проверь». Противоречие базе — фраза
переписывается. Галочка «все факты с источником» ставится только по итогам
этой проверки.

МОДЕЛЬ — СИЛЬНАЯ: `CONTENT_PACKAGE_MODEL` (Claude Opus 4.8 через
OpenRouter, политика данных §2.4 — ZDR). Та же, что пишет письма HH:
её владелец уже выбрал за качество живой русской речи, а сценарий под
озвучку — ровно такая задача. Цена пакета и разбора — в бюджет модуля,
строкой «пакеты». Готовый пакет открывается из базы — без вызовов модели.
"""
from __future__ import annotations

import os
import re
import time
import traceback
from datetime import datetime

import content_collect as cc
import content_db as cdb
import content_engine as ce
import content_ideas as ci
import content_refs as cr
from content_db import (ContentFormat, ContentIdea, ContentItem, ContentPackage, ContentStory,
                        ContentVideo)

ИНСТРУМЕНТ = "admin-content-package"
PACKAGE_MODEL = os.getenv("CONTENT_PACKAGE_MODEL", "anthropic/claude-opus-4-8")
PACKAGE_MAX_TOKENS = int(os.getenv("CONTENT_PACKAGE_MAX_TOKENS", "12000"))
PACKAGE_SMALL_TOKENS = int(os.getenv("CONTENT_PACKAGE_SMALL_TOKENS", "2500"))
FACTCHECK_MAX_TOKENS = int(os.getenv("CONTENT_FACTCHECK_MAX_TOKENS", "6000"))

ШАГИ = [("sources", "Читаю источники сюжета и его волны"),
        ("facts", "Считаю факты в источниках"),
        ("refs", "Смотрю разборы образцов формата"),
        ("titles", "Названия и превью"),
        ("script", "Сценарий"),
        ("factcheck", "Вторая проверка фактов"),
        ("shots", "Список съёмок"),
        ("check", "Проверка")]
БЛОКИ = {"titles": "Названия и превью", "hook": "Крючок", "script": "Сценарий",
         "shots": "Список съёмок", "check": "Проверка перед публикацией",
         "sources": "Источники для описания"}
УТЕЧКА = re.compile(r"утечк|слив|leak|insider footage|инсайд", re.I)
СЛУХ_ЯВНО = re.compile(r"слух|по слухам|говорят|якобы|инсайд|утечк|не подтвержд|неофициальн", re.I)
# ГРОМКИЕ УТВЕРЖДЕНИЯ — их вторая проверка не имеет права пропустить: фраза
# с таким оборотом без подтверждённой опоры получает «проверь», даже если
# модель-проверщик её не выписала (пропуск модели не равен опоре).
ГРОМКО = re.compile(r"впервые|раньше[^.!?]{0,40}?не\s+было|никогда\s+раньше|в\s+серии[^.!?]{0,30}?не\s+было"
                    r"|перв(?:ая|ый|ой)\s+(?:в\s+серии|раз)|first\s+time|вдвое|в\s+(?:два|три|\d+)\s+раза?"
                    r"|больше\s+чем\s+в|меньше\s+чем\s+в|никогда\s+не|лучш(?:ая|ий|ее)\s+в\s+истории", re.I)
СЛУХ_ОБОРОТ = re.compile(r"по\s+слухам|якобы", re.I)
СЛОВО_С_ЗАГЛАВНОЙ = re.compile(r"[A-ZА-ЯЁ][a-zа-яё]{3,}(?:-[A-ZА-ЯЁ][a-zа-яё]+)*")
НАСИЛИЕ = re.compile(r"убийств|убива|расстрел|кров|труп|пытк|отрез|казн|gore|kill|blood", re.I)
ПРЕДУПРЕЖДЕНИЕ_УТЕЧКИ = ("Сюжет с утечкой: рассказывать можно, кадры утечки показывать НЕЛЬЗЯ — "
                         "только официальные трейлеры, скриншоты Newswire и свой геймплей GTA 5.")


class Беда(Exception):
    """Шаг сборки не вышел — текст для человека."""


# ── ПОДГОТОВКА ────────────────────────────────────────────────────────

# Слова, которые есть почти в любой записи темы: по ним «та же новость»
# не узнаётся.
ОБЩИЕ_ОСНОВЫ = {"grand", "theft", "rocks", "games", "trail", "relea", "новые", "новый", "детал",
                "details", "detai", "share", "about", "every", "revea", "today", "later", "after",
                "игры", "трейл", "релиз", "свеже", "инфор", "показ", "official", "офици", "подтв"}


def основы(текст: str) -> set[str]:
    """Основы значимых слов (первые 5 букв, от 4 букв, без общих слов темы)."""
    слова = re.findall(r"[a-zа-яё]{4,}", (текст or "").lower())
    return {с[:5] for с in слова} - ОБЩИЕ_ОСНОВЫ


def _момент(и: ContentItem) -> datetime | None:
    return и.published_at or и.first_seen_at


def роль_записи(и: ContentItem, формулировки: dict, волны: dict) -> tuple[int, str]:
    """(порядок, подпись): первоисточник волны → официальный → СМИ → прочее →
    ролик YouTube (вторично)."""
    if и.source_name in set(волны.get("sources") or []):
        return 0, "первоисточник волны"
    if и.official or и.source_name in set(формулировки.get("official_sources") or []):
        return 1, "официально"
    if и.source_name in set(формулировки.get("trusted_media") or []):
        return 2, "СМИ"
    if и.platform == "youtube":
        return 4, "ролик — вторично"
    return 3, "СМИ"


def кандидаты_волны(db, идея: ContentIdea, свои: list[ContentItem], настройки: dict,
                    формулировки: dict, волны: dict) -> list[ContentItem]:
    """Записи СМИ и официальных источников той же темы рядом по времени
    с записями сюжета — материал, из которого модель выберет ту же волну.
    Ролики сюда не берутся: они вторичны и есть в сюжете сами."""
    моменты = [м for м in (_момент(и) for и in свои) if м]
    if not моменты:
        с = db.get(ContentStory, идея.story_id) if идея.story_id else None
        моменты = [с.first_seen_at] if с and с.first_seen_at else []
    if not моменты:
        return []
    from datetime import timedelta
    часов = int(настройки.get("wave_hours", 72))
    с, по = min(моменты) - timedelta(hours=часов), max(моменты) + timedelta(hours=часов)
    имена = (set(формулировки.get("official_sources") or []) | set(формулировки.get("trusted_media") or [])
             | set(волны.get("sources") or []))
    свои_ид = {и.id for и in свои}
    from sqlalchemy import func, or_
    момент = func.coalesce(ContentItem.published_at, ContentItem.first_seen_at)
    записи = (db.query(ContentItem).filter(ContentItem.theme_id == идея.theme_id,
                                           ContentItem.noise.is_(False),
                                           ContentItem.platform != "youtube",
                                           момент >= с, момент <= по,
                                           or_(ContentItem.official.is_(True),
                                               ContentItem.source_name.in_(имена)))
              .order_by(момент.desc()).limit(int(настройки.get("wave_candidates", 40))).all())
    return [и for и in записи if и.id not in свои_ид]


def волна_по_словам(свои: list[ContentItem], сюжет: ContentStory | None,
                    кандидаты: list[ContentItem]) -> list[int]:
    """Запасной отбор без модели: общая значимая основа слова с записями сюжета."""
    своё = set()
    for и in свои:
        своё |= основы(и.title)
    if сюжет is not None:
        своё |= основы(сюжет.title) | основы(сюжет.summary or "")
    return [и.id for и in кандидаты if основы(и.title + " " + (и.text or "")[:400]) & своё]


def добрать_первоисточник(выбрано: list[ContentItem], кандидаты: list[ContentItem],
                          волны: dict) -> list[int]:
    """Первоисточник волны (`waves.sources`) из кандидатов добирается двумя
    путями, и оба — КОД, а не модель: модель первоисточник часто не узнаёт,
    у него о той же новости другими словами (замер на копии прода, идея №59:
    по словам нашлись Eurogamer и IGN про погоду, Game Informer — нет).
    1. Запись волны его НАЗЫВАЕТ («в обложке Game Informer»).
    2. Его запись лежит в том же сюжете радара, что найденная запись волны
       (IGN про ураганы — сюжет №4, там же статья Game Informer)."""
    имена = set(волны.get("sources") or [])
    названы = {имя for и in выбрано for имя in имена
               if имя.lower() in (и.title + " " + (и.text or "")).lower() or и.source_name == имя}
    сюжеты = {и.story_id for и in выбрано if и.story_id}
    return [и.id for и in кандидаты
            if и.source_name in названы or (и.source_name in имена and и.story_id in сюжеты)]


def _источник(и: ContentItem, роль: tuple[int, str]) -> dict:
    return {"id": и.id, "title": и.title, "text": (и.text or "")[:400], "url": и.url,
            "source": и.source_name, "author": и.author, "platform": и.platform,
            "official": bool(и.official), "rumor": bool(и.rumor), "leak": bool(и.leak),
            "role": роль[1], "order": роль[0], "metric": и.metric or 0, "claims": None,
            "published": _момент(и).strftime("%Y-%m-%d") if _момент(и) else None}


def упорядочить(записи: list[dict]) -> list[dict]:
    return sorted(записи, key=lambda и: (и["order"], -(и["metric"] or 0), и["id"]))


async def источники_волны(клиент, db, идея: ContentIdea, к: dict) -> tuple[list[dict], str]:
    """(источники пакета, заметка шага). Свои записи сюжета плюс та же волна
    из СМИ; первоисточник волны первым."""
    настройки, формулировки = к["настройки"], к["формулировки"]
    волны = cdb.настройка(db, "waves")
    if not идея.story_id:
        return [], "без новостного повода"
    свои = db.query(ContentItem).filter(ContentItem.story_id == идея.story_id,
                                        ContentItem.noise.is_(False)).all()
    сюжет = db.get(ContentStory, идея.story_id)
    кандидаты = кандидаты_волны(db, идея, свои, настройки, формулировки, волны)
    по_ид = {и.id: и for и in кандидаты}
    выбрано_ид: list[int] = []
    как = "без кандидатов"
    if кандидаты:
        вопрос = ("Сюжет: «%s» — %s\nЗаписи сюжета:\n%s\n\nЗаписи СМИ за те же дни:\n%s\n\n"
                  "Какие записи СМИ — о той же новости, что сюжет, либо первоисточник, который сюжет "
                  "пересказывает (журнал, официальный анонс)? Только номера из списка СМИ. "
                  'Ответ JSON: {"same": [номера]}' % (
                      сюжет.title if сюжет else "", (сюжет.summary or "") if сюжет else "",
                      "\n".join(f"- {и.source_name}: {и.title}" for и in свои[:10]),
                      "\n".join(f"[{и.id}] {и.source_name}: {и.title} — {(и.text or '')[:200]}"
                                 for и in кандидаты)))
        текст, беда = await ce._спросить(клиент, ИНСТРУМЕНТ,
                                         "Ты сводишь новости об играх. Отвечай строго JSON.", вопрос, 600)
        данные = ce._json_ответа(текст or "") if not беда else None
        if isinstance(данные, dict) and isinstance(данные.get("same"), list):
            выбрано_ид = [n for n in данные["same"] if isinstance(n, int) and n in по_ид]
            как = "волну отобрала модель"
        else:
            выбрано_ид = волна_по_словам(свои, сюжет, кандидаты)
            как = "волна по словам (модель не ответила: %s)" % (беда or "не JSON")
        выбрано_ид += [n for n in добрать_первоисточник([по_ид[n] for n in выбрано_ид] + свои,
                                                        кандидаты, волны) if n not in выбрано_ид]
    записи = [_источник(и, роль_записи(и, формулировки, волны)) for и in свои]
    записи += [_источник(по_ид[n], роль_записи(по_ид[n], формулировки, волны)) for n in выбрано_ид]
    итог = упорядочить(записи)[:int(настройки.get("sources_per_package", 25))]
    первый = итог[0] if итог else None
    заметка = "записей сюжета: %d, из волны: %d (%s)%s" % (
        len(свои), len(выбрано_ид), как,
        ("; первым — %s «%s»" % (первый["source"], первый["title"][:60])) if первый else "")
    return итог, заметка


async def утверждения_роликов(клиент, db, тема_id: str, источники: list[dict], настройки: dict) -> str:
    """Ролики YouTube среди источников: что в них утверждается, с таймкодами —
    Gemini по ссылке (ролик не скачивается). Нет ключа — заметка, а не сбой."""
    ролики = [и for и in источники if и["platform"] == "youtube"]
    ролики.sort(key=lambda и: -(и["metric"] or 0))
    ролики = ролики[:int(настройки.get("claims_videos", 2))]
    if not ролики:
        return "роликов среди источников нет"
    if not cr.ключ():
        return "утверждения роликов не разобраны: нет ключа Gemini"
    вышло = 0
    for и in ролики:
        м = re.search(r"(?:v=|youtu\.be/|shorts/)([\w-]{11})", и["url"] or "")
        if not м:
            continue
        справка = await cr.справка_ролика(клиент, db, тема_id, м.group(1), "claims", и["title"])
        if справка["state"] == "ok":
            и["claims"] = справка["items"]
            вышло += 1
    return "утверждения роликов: %d из %d" % (вышло, len(ролики))


def _образцы(db, идея: ContentIdea, штук: int) -> list[dict]:
    if not идея.format_id:
        return []
    return [{"id": р.id, "yt_id": р.yt_id, "title": р.title, "channel": р.channel_title,
             "lang": р.lang, "shot": р.shot, "analysis": cdb.из_json(р.analysis, {}) or {}}
            for р in cr.для_формата(db, идея.format_id, штук)]


def контекст(db, идея: ContentIdea) -> dict:
    настройки = cdb.настройка(db, "package")
    ф = db.get(ContentFormat, идея.format_id) if идея.format_id else None
    с = db.get(ContentStory, идея.story_id) if идея.story_id else None
    факты = cdb.из_json(идея.facts, {}) or {}
    риски = cdb.из_json(идея.risks, []) or []
    return {"idea": {"id": идея.id, "title": идея.title, "why": идея.why, "kind": идея.kind,
                     "format": ф.title if ф else None, "format_note": (ф.note if ф else None),
                     "story": с.title if с else None, "summary": с.summary if с else None,
                     "official": bool(факты.get("официально")),
                     "leak": bool(с.leak) if с else ("leak" in риски),
                     "adult": "18+" in риски, "risks": риски},
            "настройки": настройки,
            "стиль": cdb.настройка(db, "style").get("text") or "",
            "база": cdb.настройка(db, "knowledge").get("text") or "",
            "формулировки": cdb.настройка(db, "wording")}


# ── МОДЕЛЬ ────────────────────────────────────────────────────────────

async def _модель(клиент, система: str, вопрос: str, потолок: int) -> dict:
    текст, беда = await ce._спросить(клиент, ИНСТРУМЕНТ, система, вопрос, потолок,
                                     модель=PACKAGE_MODEL, температура=0.7)
    if беда:
        raise Беда(беда)
    данные = ce._json_ответа(текст or "")
    if not isinstance(данные, dict):
        raise Беда("модель ответила не JSON")
    return данные


def _система(к: dict) -> str:
    return ("Ты сценарист YouTube-канала про вселенную GTA на русском. Стиль канала:\n"
            + к["стиль"]
            + ("\n\nБАЗА ЗНАНИЙ СЕРИИ — верные факты, им нельзя противоречить:\n" + к["база"]
               if к.get("база") else "")
            + "\nОтвечай строго JSON без пояснений вокруг.")


def пункты_базы(база: str) -> dict[str, str]:
    """База знаний построчно: K1, K2… — у каждой непустой строки-факта номер."""
    строки = [с.strip(" -•\t") for с in (база or "").splitlines()]
    строки = [с for с in строки if с and not с.endswith(":")]
    return {f"K{n}": с for n, с in enumerate(строки, 1)}


def _метка(к: dict) -> str:
    return ("официально подтверждённый повод" if к["idea"]["official"]
            else "СЛУХ: подавай как слух («по слухам», «говорят»), не называй подтверждённым")


def _список_источников(источники: list[dict]) -> str:
    строки = []
    for и in источники:
        пометки = [п for п, есть in (("официально", и["official"]), ("слух", и["rumor"]),
                                      ("утечка", и["leak"])) if есть]
        роль = и.get("role")
        if и.get("claims"):
            тело = " — утверждения ролика: " + "; ".join(
                f"{у['t']} {у['text']}" + (f" (со слов: {у['from']})" if у.get("from") else "")
                for у in и["claims"])
        elif и.get("platform") == "youtube":
            тело = " — (ролик: содержание не разобрано, только название)"
        else:
            тело = (f" — {и['text']}" if и["text"] else "")
        строки.append(f"[{и['id']}] {и['source']}{' · ' + роль if роль else ''} · {и['published'] or ''} · "
                      f"{и['title']}" + тело + (f" ({', '.join(пометки)})" if пометки else ""))
    return "\n".join(строки) or "(записей сюжета нет — фактов о новостях не приводи)"


# ── ФАКТЫ ИСТОЧНИКОВ И ДЛИНА ──────────────────────────────────────────

def длина_по_фактам(фактов: int, вид: str, настройки: dict) -> dict:
    """Длительность по материалу. Меньше `short_facts` — предложение Shorts
    либо ролика до 5 минут и почему."""
    порог = int(настройки.get("short_facts", 5))
    if вид == "shorts":
        return {"facts": фактов, "minutes": 1, "range": "45–60 секунд", "suggest": None}
    if фактов < порог:
        минут = max(2, min(5, фактов + 1))
        return {"facts": фактов, "minutes": минут, "range": f"до {минут} минут",
                "suggest": (f"Фактов в источниках {фактов} — на 8–12 минут материала нет. "
                            f"Лучше Shorts или ролик до 5 минут: растянутый ролик держится на воде.")}
    минут = max(5, min(12, round(фактов * 0.8) + 2))
    return {"facts": фактов, "minutes": минут, "range": f"около {минут} минут (не больше {минут + 1})",
            "suggest": None}


def свести_факты(сырые, по_id: dict) -> list[dict]:
    """Факты модели: только с номерами записей из набора, без повторов."""
    итог, виденные = [], set()
    for ф in сырые or []:
        if not isinstance(ф, dict):
            continue
        текст = str(ф.get("text") or "").strip()
        src = [n for n in (ф.get("src") or []) if isinstance(n, int) and n in по_id]
        ключ = re.sub(r"\W+", " ", текст.lower()).strip()
        if not текст or not src or ключ in виденные:
            continue
        виденные.add(ключ)
        итог.append({"text": текст, "src": src})
    return итог


async def факты_источников(клиент, к: dict) -> list[dict]:
    if not к["источники"]:
        return []
    вопрос = ("Выпиши УНИКАЛЬНЫЕ факты из источников ниже: что именно сообщается о игре. Один факт — "
              "одна строка; одно и то же из разных источников — один факт с несколькими номерами. "
              "Мнения, реклама, призывы — не факты. Слух помечай словом «слух» в тексте факта.\n"
              f"{_список_источников(к['источники'])}\n"
              'Ответ JSON: {"facts": [{"text": "факт", "src": [номера]}]}')
    данные = await _модель(клиент, _система(к), вопрос, PACKAGE_SMALL_TOKENS)
    return свести_факты(данные.get("facts"), {и["id"]: и for и in к["источники"]})


def _сжатый_образец(о: dict) -> str:
    а = о["analysis"]
    сегм = "; ".join(f"{с.get('from')}–{с.get('to')} {с.get('role')}: {с.get('what')}"
                     for с in (а.get("segments") or [])[:15])
    крючок = а.get("hook") or {}
    return (f"«{о['title']}» ({о['channel']}, выстрел {о['shot']}):\n"
            f"  крючок: {крючок.get('said')} / приём: {крючок.get('trick')}\n"
            f"  сегменты: {сегм}\n"
            f"  удержание: {'; '.join(map(str, (а.get('retention') or [])[:6]))}\n"
            f"  темп: {а.get('pace')}; концовка: {а.get('ending')}")


def стоп_слова_в(текст: str, стоп: list[str]) -> list[str]:
    низ = (текст or "").lower()
    return [с for с in стоп if с.lower() in низ]


async def названия(клиент, к: dict, беды: list) -> tuple[list[str], dict | None]:
    """3 названия (+ превью у long). Стоп-слова — перегенерация, затем выброс."""
    стоп = [str(с) for с in к["настройки"].get("stop_words") or []]
    попыток = int(к["настройки"].get("title_tries", 3))
    long = к["idea"]["kind"] != "shorts"
    отвергнуто: list[str] = []
    годные: list[str] = []
    превью = None
    for попытка in range(1, попыток + 1):
        вопрос = (f"Ролик: «{к['idea']['title']}». Формат: {к['idea']['format']}. "
                  f"Сюжет: {к['idea']['story'] or 'без новостного повода'}. Повод: {_метка(к)}.\n"
                  f"Почему сейчас: {к['idea']['why']}\n"
                  + (f"Приёмы названий и превью у удачных роликов формата:\n"
                     + "\n".join(f"- {о['title']}: {о['analysis'].get('packaging')}" for о in к["образцы"]) + "\n"
                     if к["образцы"] else "")
                  + f"Дай 3 названия {'длинного ролика' if long else 'Shorts'} на русском, до 70 знаков. "
                  f"Нельзя слов: {', '.join(стоп)}.\n"
                  + (f"Уже отвергнуты за стоп-слова: {'; '.join(отвергнуто)}.\n" if отвергнуто else "")
                  + ('Ответ: {"titles": ["", "", ""], "thumbnail": {"frame": "описание кадра", '
                     '"screenshot": "какой скриншот взять и откуда", "text": "текст на превью до 4 слов"}}'
                     if long else 'Ответ: {"titles": ["", "", ""]}'))
        данные = await _модель(клиент, _система(к), вопрос, PACKAGE_SMALL_TOKENS)
        if long and isinstance(данные.get("thumbnail"), dict):
            превью = данные["thumbnail"]
        for т in [str(т).strip() for т in данные.get("titles") or [] if str(т).strip()]:
            if стоп_слова_в(т, стоп):
                отвергнуто.append(т)
            elif т not in годные:
                годные.append(т)
        if len(годные) >= 3:
            break
    if отвергнуто:
        беды.append("названий со стоп-словами отвергнуто: %d" % len(отвергнуто))
    if not годные:
        raise Беда("все названия содержали стоп-слова — переписать блок")
    if превью is not None:
        await текст_превью(клиент, к, превью)
        if стоп_слова_в(превью.get("text"), стоп):
            превью["text"] = ""
    return годные[:3], превью


async def текст_превью(клиент, к: dict, превью: dict) -> None:
    """Текст превью — до `thumb_words` слов. Длиннее — модель ПЕРЕПИСЫВАЕТ
    (до `rewrite_tries` раз); код не обрезает: «GTA 5 vs GTA» — обрубок,
    а не текст. Не уложилась — текст остаётся и помечен для чек-листа."""
    предел = int(к["настройки"].get("thumb_words", 4))
    for _ in range(int(к["настройки"].get("rewrite_tries", 2))):
        текст = str(превью.get("text") or "").strip()
        if len(текст.split()) <= предел:
            превью.pop("too_long", None)
            return
        try:
            новый = await _модель(клиент, _система(к),
                                  f"Текст на превью «{текст}» длиннее {предел} слов. Перепиши его в {предел} "
                                  f"слова или короче — цельной фразой, не обрубком. Ролик: «{к['idea']['title']}». "
                                  'Ответ JSON: {"text": "текст превью"}', PACKAGE_SMALL_TOKENS)
        except Беда:
            break
        if str(новый.get("text") or "").strip():
            превью["text"] = str(новый["text"]).strip()
    превью["too_long"] = len(str(превью.get("text") or "").split()) > предел


def _таймкод(т) -> float | None:
    м = re.fullmatch(r"\s*(\d+):(\d{1,2})\s*", str(т or ""))
    return int(м.group(1)) * 60 + int(м.group(2)) if м else None


def проверить_сценарий(сегменты: list, источники: list[dict], к: dict) -> list[dict]:
    """Каждая фраза-факт — к записи источника. Нет привязки — «проверь»."""
    по_id = {и["id"]: и for и in источники}
    запрет = [с.lower() for с in к["формулировки"].get("forbidden_when_rumor") or []]
    итог = []
    for с in сегменты:
        if not isinstance(с, dict):
            continue
        строки = []
        for л in с.get("lines") or []:
            if isinstance(л, str):
                л = {"text": л, "fact": False, "src": []}
            if not isinstance(л, dict) or not str(л.get("text") or "").strip():
                continue
            src = [n for n in (л.get("src") or []) if isinstance(n, int) and n in по_id]
            факт = bool(л.get("fact")) or bool(л.get("src"))
            проверь = None
            if факт and not src:
                проверь = "нет источника"
            elif факт:
                офиц = any(по_id[n]["official"] and not по_id[n]["rumor"] for n in src)
                низ = str(л["text"]).lower()
                if not офиц and any(з in низ for з in запрет):
                    проверь = "слух подан как подтверждённый"
                elif all(по_id[n]["rumor"] or по_id[n]["leak"] for n in src) and not СЛУХ_ЯВНО.search(л["text"]):
                    проверь = "источник — слух: скажи, что это слух"
            строки.append({"text": str(л["text"]).strip(), "fact": факт, "src": src, "check": проверь})
        итог.append({"from": str(с.get("from") or ""), "to": str(с.get("to") or ""),
                     "role": str(с.get("role") or ""), "purpose": str(с.get("purpose") or ""),
                     "lines": строки})
    return итог


async def сценарий(клиент, к: dict) -> dict:
    long = к["idea"]["kind"] != "shorts"
    мат = к.get("материал") or {}
    длина = (f"{мат['range']} — ровно столько, сколько даёт материал, не растягивай" if long and мат
             else "45–60 секунд, один пик ближе к концу")
    факты = "\n".join(f"- {ф['text']} [{', '.join(map(str, ф['src']))}]" for ф in мат.get("list") or [])
    образцы = "\n".join(_сжатый_образец(о) for о in к["образцы"]) or "(разборов образцов нет — строй по формату)"
    вопрос = (f"Сценарий ролика «{к['titles'][0] if к.get('titles') else к['idea']['title']}».\n"
              f"Формат: {к['idea']['format']}. Длина: {длина}. Повод: {_метка(к)}.\n"
              f"Сюжет: {к['idea']['story'] or 'без новостного повода'} — {к['idea']['summary'] or ''}\n"
              f"СТРУКТУРА — по разборам удачных роликов этого формата (повтори их ритм, крючок и приёмы удержания, "
              f"не копируй тексты):\n{образцы}\n\n"
              f"ИСТОЧНИКИ — факты только отсюда, у каждой фразы-факта номера в src. Первыми идут "
              f"первоисточник и СМИ, ролики — вторичны:\n{_список_источников(к['источники'])}\n\n"
              + (f"ФАКТЫ, которые в источниках есть (весь материал ролика):\n{факты}\n\n" if факты else "")
              + "Про прошлые части серии — только то, что есть в базе знаний; «впервые в серии», "
              "«раньше такого не было» без опоры не пиши.\n"
              "Интонация — по образцу «Как я говорю» из стиля канала: манера, не слова. "
              "Правила: первые 30 с — крючок, сразу к делу; фраза-факт — fact: true и src с номерами; "
              "мнение, связка, вопрос зрителю — fact: false, src пустой. Слух называй слухом. "
              "Кадры утечек не описывай. Первые 7 секунд — без жёсткого насилия.\n"
              'Ответ: {"hook": {"text": "что сказать в первые 30 с", "shown": "что в кадре"}, '
              '"segments": [{"from": "0:00", "to": "0:30", "role": "крючок|завязка|факт|сравнение|поворот|пик|вывод|призыв", '
              '"purpose": "зачем сегмент", "lines": [{"text": "фраза под озвучку", "fact": true, "src": [123]}]}]}')
    данные = await _модель(клиент, _система(к), вопрос, PACKAGE_MAX_TOKENS)
    сегменты = данные.get("segments")
    if not isinstance(сегменты, list) or len(сегменты) < 2:
        raise Беда("в сценарии нет сегментов")
    хук = данные.get("hook") if isinstance(данные.get("hook"), dict) else {}
    return {"hook": {"text": str(хук.get("text") or ""), "shown": str(хук.get("shown") or "")},
            "script": проверить_сценарий(сегменты, к["источники"], к)}


# ── ЯЗЫК: ЗАПРЕЩЁННЫЕ ФРАЗЫ И «ПО СЛУХАМ» (письмо B2, блок 2) ────────

def нарушения(текст: str, к: dict) -> list[str]:
    """Что в тексте раздела нарушает правила языка. Проверяет КОД: список
    фраз — `package.banned_phrases` на «Кухне», «по слухам»/«якобы» — не
    больше `rumor_per_segment` раз на раздел."""
    н = к["настройки"]
    низ = (текст or "").lower()
    итог = [f"«{ф}»" for ф in н.get("banned_phrases") or [] if str(ф).lower() in низ]
    слухов = len(СЛУХ_ОБОРОТ.findall(текст or ""))
    if слухов > int(н.get("rumor_per_segment", 1)):
        итог.append(f"«по слухам»/«якобы» {слухов} раз")
    return итог


def текст_раздела(с: dict) -> str:
    return " ".join(л["text"] for л in с["lines"])


async def переписать_раздел(клиент, к: dict, с: dict, беды: list[str]) -> dict:
    вопрос = (f"Перепиши раздел сценария {с['from']}–{с['to']} ({с['role']}). Нарушения: {'; '.join(беды)}.\n"
              f"Запрещено: {', '.join(к['настройки'].get('banned_phrases') or [])}. «По слухам» или «якобы» — "
              f"не больше {int(к['настройки'].get('rumor_per_segment', 1))} раза на раздел: один раз скажи, что это "
              "слух и от кого, дальше рассказывай без повторов. Смысл, факты и номера src сохрани, длину не раздувай.\n"
              "Раздел:\n" + "\n".join(f"- {л['text']} (fact: {str(л['fact']).lower()}, src: {л['src']})"
                                        for л in с["lines"])
              + '\nОтвет JSON: {"lines": [{"text": "фраза", "fact": true, "src": [номера]}]}')
    данные = await _модель(клиент, _система(к), вопрос, PACKAGE_SMALL_TOKENS)
    if not isinstance(данные.get("lines"), list) or not данные["lines"]:
        raise Беда("раздел не переписан: модель ответила без строк")
    return проверить_сценарий([{**{к2: с[к2] for к2 in ("from", "to", "role", "purpose")},
                                "lines": данные["lines"]}], к["источники"], к)[0]


async def чистка_языка(клиент, к: dict, данные: dict) -> dict:
    """Разделы с нарушениями переписываются до `rewrite_tries` раз; не вышло —
    строка раздела помечается «проверь» с названием нарушения."""
    попыток = int(к["настройки"].get("rewrite_tries", 2))
    переписано, осталось = 0, 0
    for i, с in enumerate(данные["script"]):
        for _ in range(попыток):
            беды = нарушения(текст_раздела(с), к)
            if not беды:
                break
            try:
                с = await переписать_раздел(клиент, к, с, беды)
                данные["script"][i] = с
                переписано += 1
            except Беда:
                break
        беды = нарушения(текст_раздела(с), к)
        if беды and с["lines"]:
            осталось += 1
            л = next((л for л in с["lines"] if нарушения(л["text"], к)), с["lines"][0])
            л["check"] = (л.get("check") + "; " if л.get("check") else "") + "язык: " + ", ".join(беды)
    хук = данные.get("hook") or {}
    for _ in range(попыток):
        беды = нарушения(хук.get("text", ""), к)
        if not беды:
            break
        try:
            новый = await _модель(клиент, _система(к),
                                  f"Перепиши крючок без нарушений ({'; '.join(беды)}), смысл сохрани: "
                                  f"«{хук.get('text', '')}». Ответ JSON: {{\"text\": \"крючок\"}}",
                                  PACKAGE_SMALL_TOKENS)
            if str(новый.get("text") or "").strip():
                хук["text"] = str(новый["text"]).strip()
                переписано += 1
        except Беда:
            break
    return {"rewritten": переписано, "left": осталось + (1 if нарушения(хук.get("text", ""), к) else 0)}


def строки_сценария(сценарий: list[dict]) -> dict[str, dict]:
    """Номера строк для проверщика: S1.L2 — сегмент 1, строка 2."""
    return {f"S{i}.L{j}": л for i, с in enumerate(сценарий, 1) for j, л in enumerate(с["lines"], 1)}


def применить_проверку(сценарий: list[dict], ответ, источники: list[dict], база: dict[str, str]) -> dict:
    """Итог второй проверки фактов — решает КОД по ответу модели.
    Опора: номер записи из набора либо пункт базы, который есть. Противоречие
    базе с переписанной фразой — фраза заменяется. Громкое утверждение
    (`ГРОМКО`) без подтверждённой опоры — «проверь», даже если проверщик
    его не выписал. Возвращает сводку для страницы и чек-листа."""
    строки = строки_сценария(сценарий)
    по_id = {и["id"] for и in источники}
    утверждения = ответ.get("claims") if isinstance(ответ, dict) else None
    if not isinstance(утверждения, list):
        raise Беда("проверщик фактов ответил без списка утверждений")
    опора_у: dict[str, bool] = {}
    пункты, с_опорой, переписано = [], 0, 0
    for у in утверждения:
        if not isinstance(у, dict):
            continue
        ключ = str(у.get("line") or "").strip()
        л = строки.get(ключ)
        src = [n for n in (у.get("src") or []) if isinstance(n, int) and n in по_id]
        kb = [k for k in (у.get("kb") or []) if isinstance(k, str) and k in база]
        против = у.get("contradicts") if у.get("contradicts") in база else None
        исправ = str(у.get("fix") or "").strip()
        запись = {"line": ключ, "claim": str(у.get("claim") or (л or {}).get("text") or "")[:300],
                  "src": src, "kb": kb, "status": None}
        if л is None:
            запись["status"] = "строки нет в сценарии"
            пункты.append(запись)
            continue
        if против and исправ:
            запись["was"] = л["text"]
            л["text"], л["fixed"] = исправ, "противоречило базе знаний (%s: %s)" % (против, база[против])
            запись["status"], переписано = "переписано: противоречило базе", переписано + 1
            kb = kb or [против]
            запись["kb"] = kb
        elif против:
            л["check"] = "противоречит базе знаний: " + база[против]
            запись["status"] = "противоречит базе"
            опора_у[ключ] = False
            пункты.append(запись)
            continue
        if src or kb:
            л["src"] = sorted(set(л.get("src") or []) | set(src))
            if kb:
                л["kb"] = sorted(set(л.get("kb") or []) | set(kb))
            л["fact"] = True
            if л.get("check") == "нет источника":
                л["check"] = None
            опора_у[ключ] = опора_у.get(ключ, True)
            с_опорой += 1
            запись["status"] = запись["status"] or "опора есть"
        else:
            л["fact"] = True
            if not л.get("check"):
                л["check"] = "нет опоры в источниках и базе знаний"
            опора_у[ключ] = False
            запись["status"] = "проверь"
        пункты.append(запись)
    громких = 0
    for ключ, л in строки.items():
        if ГРОМКО.search(л["text"]) and not опора_у.get(ключ) and not л.get("check"):
            л["fact"], л["check"] = True, "громкое утверждение без подтверждённой опоры"
            громких += 1
            пункты.append({"line": ключ, "claim": л["text"][:300], "src": [], "kb": [],
                           "status": "проверь (громкое, проверщик не выписал)"})
    проверь = sum(1 for л in строки.values() if л.get("check"))
    return {"done": True, "claims": len(пункты), "supported": с_опорой, "check": проверь,
            "fixed": переписано, "loud": громких, "items": пункты}


async def проверка_фактов(клиент, к: dict, сценарий: list[dict]) -> dict:
    """Отдельный вызов: все утверждения сценария и опора каждого."""
    база = пункты_базы(к.get("база") or "")
    строки = строки_сценария(сценарий)
    вопрос = ("Ты фактчекер. Выпиши ВСЕ утверждения сценария о фактах: о игре, о прошлых частях "
              "серии, сравнения («впервые», «раньше такого не было», «больше чем в GTA 5», «в два раза»), "
              "цифры, даты, имена. Мнения, вопросы зрителю и связки — не утверждения.\n"
              "Для каждого: line — номер строки; src — номера записей-источников, где это сказано; "
              "kb — номера пунктов базы знаний, где это сказано; contradicts — номер пункта базы, "
              "которому утверждение противоречит (иначе null); fix — если противоречит, переписанная "
              "фраза в том же стиле, верная по базе. Нет опоры — src и kb пустые. Не выдумывай опору.\n\n"
              "СЦЕНАРИЙ:\n" + "\n".join(f"{k}: {л['text']}" for k, л in строки.items())
              + "\n\nИСТОЧНИКИ:\n" + _список_источников(к["источники"])
              + "\n\nБАЗА ЗНАНИЙ:\n" + ("\n".join(f"{k}: {т}" for k, т in база.items()) or "(пусто)")
              + '\n\nОтвет JSON: {"claims": [{"line": "S1.L2", "claim": "утверждение", "src": [номера], '
              '"kb": ["K1"], "contradicts": null, "fix": ""}]}')
    данные = await _модель(клиент, "Ты строгий фактчекер. Отвечай строго JSON без пояснений вокруг.",
                           вопрос, FACTCHECK_MAX_TOKENS)
    return применить_проверку(сценарий, данные, к["источники"], база)


async def сцены_трейлеров(клиент, db, тема_id: str, настройки: dict) -> list[dict]:
    """Официальные трейлеры (`package.trailers`) — сцены с таймкодами от Gemini.
    Справка одна на трейлер и хранится. Нет ключа — пусто."""
    if not cr.ключ():
        return []
    итог = []
    for т in настройки.get("trailers") or []:
        if not isinstance(т, dict) or not т.get("yt_id"):
            continue
        справка = await cr.справка_ролика(клиент, db, тема_id, т["yt_id"], "trailer", т.get("title"))
        if справка["state"] == "ok":
            итог.append({"yt_id": т["yt_id"], "title": т.get("title") or т["yt_id"], "scenes": справка["items"]})
    return итог


def корпус_опоры(к: dict) -> set[str]:
    """Всё, на что может опереться список съёмок: база знаний, источники
    (с утверждениями роликов), разборы образцов, сцены трейлеров — основы слов."""
    тексты = [к.get("база") or ""]
    for и in к.get("источники") or []:
        тексты += [и["title"], и.get("text") or ""] + [у["text"] for у in и.get("claims") or []]
    for о in к.get("образцы") or []:
        тексты.append(str(о.get("analysis") or ""))
    for т in к.get("трейлеры") or []:
        тексты += [т["title"]] + [с["what"] for с in т["scenes"]]
    итог = set()
    for т in тексты:
        итог |= {с[:5] for с in re.findall(r"[a-zа-яё]{4,}", т.lower())}
    return итог


def имена_в(текст: str, с_начала: bool = False) -> list[str]:
    """Собственные имена (места, люди) — слова с заглавной. В начале фразы
    заглавная обычна и именем не считается; поле «где» — само название
    места, там считается и первое слово (`с_начала`)."""
    итог = []
    for м in СЛОВО_С_ЗАГЛАВНОЙ.finditer(текст or ""):
        до = (текст or "")[:м.start()].rstrip()
        if not с_начала and (not до or до[-1] in ".!?:;—–•«(\""):
            continue
        итог.append(м.group(0))
    return итог


def _секунды(т: str) -> float | None:
    return _таймкод(т)


def обосновать_съёмки(съём: list[dict], к: dict) -> list[dict]:
    """Место или сцена — только если есть в базе знаний, источниках, разборе
    роликов или сценах трейлера. Иначе пункт становится «найди в трейлере: …».
    Решает КОД по ответу модели (`basis`): трейлер — таймкод обязан быть среди
    сцен этого трейлера; имя места — среди основ корпуса опоры."""
    корпус = корпус_опоры(к)
    трейлеры = {т["yt_id"]: т for т in к.get("трейлеры") or []}
    итог = []
    for с in съём:
        что, где, источник = с.get("what", ""), с.get("where", ""), с.get("source", "")
        основа = str(с.get("basis") or "")
        выдумка = None
        м = re.fullmatch(r"trailer:([\w-]{11})@(\d+:\d{2})", основа.strip())
        if "трейлер" in источник.lower() or основа.startswith("trailer"):
            т = трейлеры.get(м.group(1)) if м else None
            сек = _секунды(м.group(2)) if м else None
            сцена = None
            if т and сек is not None:
                сцена = min((с2 for с2 in т["scenes"] if _секунды(с2["t"]) is not None),
                            key=lambda с2: abs(_секунды(с2["t"]) - сек), default=None)
                if сцена and abs(_секунды(сцена["t"]) - сек) > 3:
                    сцена = None
            if сцена is None:
                выдумка = "сцены нет в разборе трейлера"
            else:
                где = f"{т['title']}, {сцена['t']} — {сцена['what']}"
        if выдумка is None:
            чужие = [и for и in имена_в(что) + имена_в(где, с_начала=True)
                     if not ({ч[:5] for ч in re.findall(r"[a-zа-яё]{4,}", и.lower())} & корпус)]
            if чужие:
                выдумка = "нет в источниках: " + ", ".join(чужие)
        if выдумка:
            итог.append({"what": "найди в трейлере: " + что, "source": "трейлер", "where": "",
                         "for": с.get("for", ""), "note": выдумка})
        else:
            итог.append({"what": что, "source": источник, "where": где, "for": с.get("for", ""), "note": ""})
    return итог


async def съёмки(клиент, к: dict) -> tuple[list[dict], str | None]:
    long = к["idea"]["kind"] != "shorts"
    план = "\n".join(f"{с['from']}–{с['to']} {с['role']}: {с['purpose']}" for с in к["script"])
    сцены = "\n".join(f"[trailer:{т['yt_id']}] {т['title']}: " + "; ".join(f"{с['t']} {с['what']}" for с in т["scenes"])
                      for т in к.get("трейлеры") or []) or "(разбора трейлеров нет)"
    вопрос = (f"Список съёмок для ролика «{к['idea']['title']}» по плану:\n{план}\n"
              f"Источники: {_список_источников(к['источники'][:10])}\n"
              f"Сцены официальных трейлеров (таймкоды настоящие):\n{сцены}\n"
              "Материал: запись своего геймплея GTA 5 (что именно снять), официальные трейлеры "
              "Rockstar, скриншоты Rockstar Newswire. Места и сцены — ТОЛЬКО из базы знаний, источников "
              "и сцен трейлеров выше; не выдумывай названий мест и сцен. Кадр трейлера — с таймкодом "
              "из списка сцен. "
              + ("ЭТО СЮЖЕТ С УТЕЧКОЙ: ни одного кадра утечки, только официальное и свой геймплей. "
                 if к["idea"]["leak"] else "")
              + (f"Дай 1–2 кадра." if not long else "Дай 6–12 пунктов по порядку сценария.")
              + ' Ответ: {"shots": [{"what": "что записать", "source": "GTA 5 | трейлер | Newswire", '
              '"where": "место в игре либо что в кадре", "basis": "trailer:<id>@<таймкод> | src:<номер> | kb | gameplay", '
              '"for": "к какому сегменту (таймкод)"}]}')
    данные = await _модель(клиент, _система(к), вопрос, PACKAGE_SMALL_TOKENS)
    съём = [{к2: str(с.get(к2) or "") for к2 in ("what", "source", "where", "basis", "for")}
            for с in данные.get("shots") or [] if isinstance(с, dict) and с.get("what")]
    предупреждение = None
    if к["idea"]["leak"]:
        съём = [с for с in съём if not УТЕЧКА.search(" ".join(str(v) for v in с.values()))]
        предупреждение = ПРЕДУПРЕЖДЕНИЕ_УТЕЧКИ
    if not long:
        съём = съём[:2]
    return обосновать_съёмки(съём, к), предупреждение


def проверка(данные: dict, к: dict) -> list[dict]:
    """Чек-лист перед публикацией — считает КОД по готовому пакету."""
    стоп = [str(с) for с in к["настройки"].get("stop_words") or []]
    long = к["idea"]["kind"] != "shorts"
    пункты = []
    найдено = [с for т in данные.get("titles") or [] for с in стоп_слова_в(т, стоп)]
    пункты.append({"item": "Стоп-слова в названиях", "ok": not найдено,
                   "note": ", ".join(найдено) if найдено else "нет"})
    язык = данные.get("language") or {}
    if язык:
        пункты.append({"item": "Запрещённые фразы и «по слухам»", "ok": не_ноль(язык.get("left", 0)),
                       "note": (("переписано разделов: %d" % язык.get("rewritten", 0)) if not язык.get("left")
                                else "осталось нарушений: %d — поправь руками" % язык["left"])})
    т = данные.get("thumbnail") or {}
    if т:
        пункты.append({"item": "Текст превью до %d слов" % int(к["настройки"].get("thumb_words", 4)),
                       "ok": None if т.get("too_long") else True,
                       "note": "длиннее — перепиши: «%s»" % т.get("text") if т.get("too_long") else "«%s»" % т.get("text", "")})
    выдумок = sum(1 for с in данные.get("shots") or [] if с.get("note"))
    if выдумок:
        пункты.append({"item": "Список съёмок без выдумок", "ok": None,
                       "note": "заменено на «найди в трейлере»: %d" % выдумок})
    первые = (данные.get("hook") or {}).get("text", "") + " " + (данные.get("hook") or {}).get("shown", "")
    насилие = НАСИЛИЕ.search(первые)
    пункты.append({"item": "Первые 7 с без жёсткого насилия", "ok": None if насилие else True,
                   "note": ("в крючке есть «%s» — проверь кадр" % насилие.group(0)) if насилие else "в крючке не найдено"})
    утечки = [с for с in данные.get("shots") or [] if УТЕЧКА.search(" ".join(str(v) for v in с.values()))]
    пункты.append({"item": "Нет кадров утечек", "ok": not утечки,
                   "note": ("сюжет с утечкой — только рассказ" if к["idea"]["leak"] else "утечек в сюжете нет")})
    заметка = (к["idea"].get("format_note") or "") + " " + (к["idea"]["format"] or "")
    if re.search(r"content id|катсцен", заметка, re.I):
        пункты.append({"item": "Катсцены: проверь музыку на Content ID", "ok": None,
                       "note": "фоновая музыка игры ловится Content ID"})
    if к["idea"]["adult"]:
        пункты.append({"item": "18+: ограниченная реклама", "ok": None,
                       "note": "в YouTube Studio отметь, реклама будет урезана"})
    без = sum(1 for с in данные.get("script") or [] for л in с["lines"] if л.get("check"))
    фп = данные.get("factcheck") or {}
    if not фп.get("done"):
        пункты.append({"item": "Утверждения без подтверждения", "ok": None,
                       "note": "вторая проверка фактов не прошла%s — факты не сверены" % (
                           (": " + фп["error"]) if фп.get("error") else "")})
    else:
        пункты.append({"item": "Утверждения без подтверждения", "ok": не_ноль(без),
                       "note": ("подсвечено «проверь»: %d из %d утверждений" % (без, фп.get("claims", 0))) if без
                       else "все факты с источником: утверждений %d, с опорой %d" % (
                           фп.get("claims", 0), фп.get("supported", 0))})
    конец = max((_таймкод(с["to"]) or 0 for с in данные.get("script") or []), default=0)
    мат = данные.get("material") or {}
    if long and мат.get("minutes"):
        цель = мат["minutes"] * 60
        if конец > (мат["minutes"] + 1.5) * 60 or конец < max(60, цель * 0.5):
            пункты.append({"item": "Длина по материалу (%s)" % мат["range"], "ok": None,
                           "note": "по таймкодам %d:%02d" % divmod(int(конец), 60)})
    elif long and not 7.5 * 60 <= конец <= 12.5 * 60:
        пункты.append({"item": "Длина 8–12 мин", "ok": None, "note": "по таймкодам %d:%02d" % divmod(int(конец), 60)})
    if not long and not 40 <= конец <= 65:
        пункты.append({"item": "Длина 45–60 с", "ok": None, "note": "по таймкодам %d с" % конец})
    return пункты


def не_ноль(n: int) -> bool | None:
    return True if n == 0 else None


def источники_описания(данные: dict, к: dict) -> list[dict]:
    """Ссылки для описания: записи, на которые опирается сценарий, плюс официальные."""
    нужные = {n for с in данные.get("script") or [] for л in с["lines"] for n in л["src"]}
    итог = []
    for и in к["источники"]:
        if и["id"] in нужные or и["official"] or и.get("order") == 0:
            итог.append({"id": и["id"], "title": и["title"], "url": и["url"], "source": и["source"],
                         "author": и["author"] or и["source"], "role": и.get("role")})
    return итог


# ── ПРОГОН ────────────────────────────────────────────────────────────

class Шаги:
    def __init__(self, номер: int, ключи=ШАГИ):
        self.номер = номер
        self.шаги = [{"k": к, "t": т, "done": False, "note": None} for к, т in ключи]
        self.записать()

    def готово(self, ключ: str, заметка: str | None = None):
        for ш in self.шаги:
            if ш["k"] == ключ:
                ш["done"], ш["note"] = True, заметка
        self.записать()

    def записать(self):
        db = ce.SessionLocal()
        try:
            п = db.get(ContentPackage, self.номер)
            if п is not None:
                п.steps = cdb.в_json(self.шаги)
                db.commit()
        finally:
            db.close()


def _закончить(номер: int, состояние: str, заметка: str | None, данные: dict | None = None,
               стоимость: float | None = None) -> None:
    db = ce.SessionLocal()
    try:
        п = db.get(ContentPackage, номер)
        if п is None:
            return
        п.state, п.note, п.finished_at = состояние, заметка, datetime.utcnow()
        if данные is not None:
            п.data = cdb.в_json(данные)
            п.refs = cdb.в_json([о["id"] for о in данные.get("refs") or []])
            п.model = PACKAGE_MODEL
        if стоимость is not None:
            п.cost = round((п.cost or 0) + стоимость, 6)
        db.commit()
    finally:
        db.close()


def _потрачено_с(с: datetime) -> float:
    """Цена пакета: вызовы пакета плюс Gemini по роликам-источникам и трейлерам
    за время сборки (исполнитель один — чужих вызовов модуля в это время нет)."""
    from sqlalchemy import func
    from database import ModelUsage
    db = ce.SessionLocal()
    try:
        return float(db.query(func.sum(ModelUsage.cost)).filter(
            ModelUsage.tool.in_((ИНСТРУМЕНТ, cr.ИНСТРУМЕНТ)), ModelUsage.created_at >= с).scalar() or 0.0)
    finally:
        db.close()


async def _проверить_факты(клиент, к: dict, данные: dict) -> dict:
    """Вторая проверка; сбой — не падение пакета, а «не прошла» в чек-листе."""
    try:
        return await проверка_фактов(клиент, к, данные["script"])
    except Беда as e:
        return {"done": False, "error": str(e)}


async def собрать(номер: int) -> dict:
    """Сборка пакета по шагам. Ошибка шага — пакет «ошибка» с текстом."""
    начало = datetime.utcnow()
    t0 = time.monotonic()
    шаги = Шаги(номер)
    беды: list[str] = []
    try:
        async with cc.новый_клиент() as клиент:
            db = ce.SessionLocal()
            try:
                п = db.get(ContentPackage, номер)
                идея = db.get(ContentIdea, п.idea_id) if п else None
                if идея is None:
                    raise Беда("идеи пакета нет")
                к = контекст(db, идея)
                к["источники"], заметка = await источники_волны(клиент, db, идея, к)
                заметка += "; " + await утверждения_роликов(клиент, db, идея.theme_id,
                                                           к["источники"], к["настройки"])
                шаги.готово("sources", заметка)
                к["образцы"] = _образцы(db, идея, int(к["настройки"].get("refs_per_package", 3)))
                к["трейлеры"] = await сцены_трейлеров(клиент, db, идея.theme_id, к["настройки"])
            finally:
                db.close()
            try:
                факты = await факты_источников(клиент, к)
                к["материал"] = {**длина_по_фактам(len(факты), к["idea"]["kind"], к["настройки"]),
                                 "list": факты}
                шаги.готово("facts", "фактов: %d → %s" % (len(факты), к["материал"]["range"]))
            except Беда as e:
                # Не посчитали — длина по формату, и это сказано, а не подставлено молча
                к["материал"] = {"facts": None, "minutes": None, "list": [], "suggest": None,
                                 "range": "8–12 минут" if к["idea"]["kind"] != "shorts" else "45–60 секунд",
                                 "error": str(e)}
                шаги.готово("facts", "факты не посчитаны: %s — длина по формату" % e)
            шаги.готово("refs", "разборов образцов: %d" % len(к["образцы"])
                        if к["образцы"] else "разобранных образцов формата нет — по формату")
            данные = {"kind": к["idea"]["kind"], "idea": к["idea"], "material": к["материал"],
                      "src": к["источники"],
                      "refs": [{"id": о["id"], "yt_id": о["yt_id"], "title": о["title"], "channel": о["channel"]}
                               for о in к["образцы"]]}
            данные["titles"], данные["thumbnail"] = await названия(клиент, к, беды)
            к["titles"] = данные["titles"]
            шаги.готово("titles", "; ".join(беды) or None)
            сц = await сценарий(клиент, к)
            данные.update(сц)
            к["script"] = сц["script"]
            данные["language"] = await чистка_языка(клиент, к, данные)
            шаги.готово("script", "сегментов: %d; язык: переписано %d, осталось %d" % (
                len(данные["script"]), данные["language"]["rewritten"], данные["language"]["left"]))
            данные["factcheck"] = await _проверить_факты(клиент, к, данные)
            шаги.готово("factcheck", "утверждений %d, с опорой %d, «проверь» %d, переписано %d" % (
                данные["factcheck"].get("claims", 0), данные["factcheck"].get("supported", 0),
                данные["factcheck"].get("check", 0), данные["factcheck"].get("fixed", 0))
                if данные["factcheck"].get("done") else "не прошла: " + str(данные["factcheck"].get("error")))
            данные["shots"], данные["shots_warning"] = await съёмки(клиент, к)
            шаги.готово("shots", "пунктов: %d, заменено на «найди в трейлере»: %d; трейлеров разобрано: %d" % (
                len(данные["shots"]), sum(1 for с in данные["shots"] if с.get("note")), len(к["трейлеры"])))
        данные["check"] = проверка(данные, к)
        данные["sources"] = источники_описания(данные, к) if к["idea"]["kind"] != "shorts" else []
        шаги.готово("check", None)
        _закончить(номер, "ok", "; ".join(беды) or None, данные, _потрачено_с(начало))
        print(f"[content] пакет №{номер}: ok за {time.monotonic() - t0:.1f} с", flush=True)
        return {"state": "ok"}
    except Беда as e:
        _закончить(номер, "error", str(e), None, _потрачено_с(начало))
        return {"state": "error", "note": str(e)}
    except Exception as e:
        traceback.print_exc()
        _закончить(номер, "error", f"{type(e).__name__}: {e}", None, _потрачено_с(начало))
        return {"state": "error"}


async def переписать(номер: int, блок: str) -> dict:
    """Один блок заново. Остальные не трогаются; не вышло — блок прежний
    и заметка с причиной."""
    начало = datetime.utcnow()
    db = ce.SessionLocal()
    try:
        п = db.get(ContentPackage, номер)
        идея = db.get(ContentIdea, п.idea_id)
        данные = cdb.из_json(п.data, {}) or {}
        к = контекст(db, идея)
        к["источники"] = данные.get("src") or []
        к["материал"] = данные.get("material") or {}
        к["образцы"] = _образцы(db, идея, int(к["настройки"].get("refs_per_package", 3)))
    finally:
        db.close()
    к["titles"] = данные.get("titles")
    к["script"] = данные.get("script") or []
    Шаги(номер, [("rewrite", "Переписываю блок «%s»" % БЛОКИ.get(блок, блок))])
    try:
        async with cc.новый_клиент() as клиент:
            if блок == "titles":
                данные["titles"], данные["thumbnail"] = await названия(клиент, к, [])
            elif блок in ("hook", "script"):
                сц = await сценарий(клиент, к)
                if блок == "hook":
                    данные["hook"] = сц["hook"]
                else:
                    данные.update(сц)
                    данные["language"] = await чистка_языка(клиент, к, данные)
                    данные["factcheck"] = await _проверить_факты(клиент, к, данные)
            elif блок == "shots":
                db = ce.SessionLocal()
                try:
                    к["трейлеры"] = await сцены_трейлеров(клиент, db, идея.theme_id, к["настройки"])
                finally:
                    db.close()
                данные["shots"], данные["shots_warning"] = await съёмки(клиент, к)
        данные["check"] = проверка(данные, к)
        if к["idea"]["kind"] != "shorts":
            данные["sources"] = источники_описания(данные, к)
        _закончить(номер, "ok", None, данные, _потрачено_с(начало))
        return {"state": "ok"}
    except Exception as e:
        if not isinstance(e, Беда):
            traceback.print_exc()
        _закончить(номер, "ok", "Блок «%s» не переписан: %s" % (БЛОКИ.get(блок, блок), e),
                   None, _потрачено_с(начало))
        return {"state": "error", "note": str(e)}


# ── ВХОДЫ ─────────────────────────────────────────────────────────────

def начать(db, idea_id: int, заново: bool = False) -> dict:
    """Кнопка «Собрать пакет». Готовый пакет — сразу он, без модели;
    `заново` (кнопка «Собрать заново» у готового пакета, письмо B2) — тот же
    пакет собирается с нуля. Идёт — он же. Бюджет исчерпан или исполнитель
    занят — текст, не сборка."""
    import content_worker as cw
    идея = db.get(ContentIdea, idea_id)
    if идея is None:
        return {"error": "идеи нет", "code": 404}
    п = (db.query(ContentPackage).filter(ContentPackage.idea_id == idea_id)
         .order_by(ContentPackage.id.desc()).first())
    if п is not None and (п.state == "running" or (п.state == "ok" and not заново)):
        return {"ok": True, "id": п.id, "ready": п.state == "ok"}
    б = ce.бюджет(db)
    if б["исчерпан"]:
        return {"error": б["текст"] + ". Пакет не собирается.", "code": 409}
    if cw.занят_другим() or cw.что_идёт():
        return {"error": cw.отказ_занято(), "code": 409}
    if п is None:
        п = ContentPackage(theme_id=идея.theme_id, idea_id=идея.id, kind=идея.kind)
        db.add(п)
    п.state, п.note, п.data, п.created_at, п.finished_at = "running", None, None, datetime.utcnow(), None
    п.cost = None
    if идея.state != "planned":
        итог = ci.реакция(db, идея.id, "plan")
        п.video_id = итог.get("video_id")
    elif п.video_id is None:
        р = db.query(ContentVideo).filter(ContentVideo.idea_id == идея.id).first()
        п.video_id = р.id if р else None
    db.commit()
    номер = п.id
    Шаги(номер)
    старт = cw.запустить("package", lambda повод: собрать(номер), "admin")
    if not старт.get("ok"):
        _закончить(номер, "error", старт.get("error"))
        return {"error": старт.get("error"), "code": 409}
    return {"ok": True, "id": номер, "ready": False}


def переписать_блок(db, номер: int, блок: str) -> dict:
    import content_worker as cw
    п = db.get(ContentPackage, номер)
    if п is None:
        return {"error": "пакета нет", "code": 404}
    if блок not in БЛОКИ:
        return {"error": "блок: " + " | ".join(БЛОКИ), "code": 400}
    if п.state != "ok":
        return {"error": "пакет ещё собирается либо не собрался", "code": 409}
    if блок in ("check", "sources"):
        # Их считает код — модель не нужна, фоновая задача тоже
        данные = cdb.из_json(п.data, {}) or {}
        идея = db.get(ContentIdea, п.idea_id)
        к = контекст(db, идея)
        к["источники"] = данные.get("src") or []
        данные["check"] = проверка(данные, к)
        if п.kind != "shorts":
            данные["sources"] = источники_описания(данные, к)
        п.data = cdb.в_json(данные)
        db.commit()
        return {"ok": True, "ready": True}
    б = ce.бюджет(db)
    if б["исчерпан"]:
        return {"error": б["текст"], "code": 409}
    if cw.что_идёт():
        return {"error": cw.отказ_занято(), "code": 409}
    п.state = "running"
    db.commit()
    старт = cw.запустить("package", lambda повод: переписать(номер, блок), "admin")
    if not старт.get("ok"):
        п.state = "ok"
        db.commit()
        return {"error": старт.get("error"), "code": 409}
    return {"ok": True, "ready": False}


def отметить_снимаю(db, номер: int) -> dict:
    п = db.get(ContentPackage, номер)
    if п is None:
        return {"error": "пакета нет", "code": 404}
    р = db.get(ContentVideo, п.video_id) if п.video_id else None
    if р is None:
        р = db.query(ContentVideo).filter(ContentVideo.idea_id == п.idea_id).first()
    if р is None:
        идея = db.get(ContentIdea, п.idea_id)
        р = ContentVideo(theme_id=п.theme_id, idea_id=п.idea_id, title=идея.title if идея else "Ролик",
                         kind=п.kind, status="plan", created_at=datetime.utcnow())
        db.add(р)
        db.flush()
        п.video_id = р.id
    db.commit()
    return ci.сменить_статус(db, р.id, "writing")


def в_markdown(п: ContentPackage) -> str:
    д = cdb.из_json(п.data, {}) or {}
    и = д.get("idea") or {}
    строки = [f"# {и.get('title', 'Пакет ролика')}", "",
              f"Формат: {и.get('format') or '—'} · {'Shorts' if д.get('kind') == 'shorts' else 'длинный'} · "
              f"{'официально' if и.get('official') else 'слух'}", ""]
    строки += ["## Названия", ""] + [f"{n}. {т}" for n, т in enumerate(д.get("titles") or [], 1)] + [""]
    if д.get("thumbnail"):
        т = д["thumbnail"]
        строки += ["## Превью", "", f"- Кадр: {т.get('frame', '')}", f"- Скриншот: {т.get('screenshot', '')}",
                   f"- Текст: {т.get('text', '')}", ""]
    мат = д.get("material") or {}
    if мат:
        строки += ["## Материал", "", f"Фактов в источниках: {мат.get('facts')} → длительность {мат.get('range')}"]
        if мат.get("suggest"):
            строки.append(f"> {мат['suggest']}")
        строки.append("")
    х = д.get("hook") or {}
    строки += ["## Крючок (первые 30 с)", "", х.get("text", ""), "", f"В кадре: {х.get('shown', '')}", ""]
    строки += ["## Сценарий", ""]
    for с in д.get("script") or []:
        строки.append(f"### {с['from']}–{с['to']} · {с['role']}" + (f" — {с['purpose']}" if с.get("purpose") else ""))
        for л in с["lines"]:
            метка = (f" [ист. {', '.join(map(str, л['src']))}]" if л["src"] else "") + (
                f" [база {', '.join(л['kb'])}]" if л.get("kb") else "")
            строки.append(f"- {л['text']}{метка}" + (f" **ПРОВЕРЬ: {л["check"]}**" if л.get("check") else ""))
        строки.append("")
    строки += ["## Список съёмок", ""]
    if д.get("shots_warning"):
        строки += [f"> ВНИМАНИЕ: {д["shots_warning"]}", ""]
    строки += [f"- {с['what']} ({с['source']}{', ' + с['where'] if с['where'] else ''})"
               + (f" — {с['note']}" if с.get("note") else "") for с in д.get("shots") or []] + [""]
    строки += ["## Проверка перед публикацией", ""]
    строки += [f"- [{'x' if п2['ok'] else ' '}] {п2['item']} — {п2['note']}" for п2 in д.get("check") or []] + [""]
    if д.get("sources"):
        строки += ["## Источники для описания", ""]
        строки += [f"- {с['title']} — {с['url']} (находка: {с['author']})" for с in д["sources"]] + [""]
    return "\n".join(строки)
