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

ШАГИ = [("sources", "Читаю источники сюжета"),
        ("refs", "Смотрю разборы образцов формата"),
        ("titles", "Названия и превью"),
        ("script", "Сценарий"),
        ("shots", "Список съёмок"),
        ("check", "Проверка")]
БЛОКИ = {"titles": "Названия и превью", "hook": "Крючок", "script": "Сценарий",
         "shots": "Список съёмок", "check": "Проверка перед публикацией",
         "sources": "Источники для описания"}
УТЕЧКА = re.compile(r"утечк|слив|leak|insider footage|инсайд", re.I)
СЛУХ_ЯВНО = re.compile(r"слух|по слухам|говорят|якобы|инсайд|утечк|не подтвержд|неофициальн", re.I)
НАСИЛИЕ = re.compile(r"убийств|убива|расстрел|кров|труп|пытк|отрез|казн|gore|kill|blood", re.I)
ПРЕДУПРЕЖДЕНИЕ_УТЕЧКИ = ("Сюжет с утечкой: рассказывать можно, кадры утечки показывать НЕЛЬЗЯ — "
                         "только официальные трейлеры, скриншоты Newswire и свой геймплей GTA 5.")


class Беда(Exception):
    """Шаг сборки не вышел — текст для человека."""


# ── ПОДГОТОВКА ────────────────────────────────────────────────────────

def _источники(db, идея: ContentIdea, предел: int) -> list[dict]:
    """Записи сюжета — сначала официальные и новости, потом ролики по метрике."""
    if not идея.story_id:
        return []
    записи = db.query(ContentItem).filter(ContentItem.story_id == идея.story_id,
                                          ContentItem.noise.is_(False)).all()
    записи.sort(key=lambda и: (not и.official, и.platform == "youtube", -(и.metric or 0)))
    return [{"id": и.id, "title": и.title, "text": (и.text or "")[:400], "url": и.url,
             "source": и.source_name, "author": и.author, "platform": и.platform,
             "official": bool(и.official), "rumor": bool(и.rumor), "leak": bool(и.leak),
             "published": (и.published_at or и.first_seen_at).strftime("%Y-%m-%d") if (и.published_at or и.first_seen_at) else None}
            for и in записи[:предел]]


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
            + к["стиль"] + "\nОтвечай строго JSON без пояснений вокруг.")


def _метка(к: dict) -> str:
    return ("официально подтверждённый повод" if к["idea"]["official"]
            else "СЛУХ: подавай как слух («по слухам», «говорят»), не называй подтверждённым")


def _список_источников(источники: list[dict]) -> str:
    строки = []
    for и in источники:
        пометки = [п for п, есть in (("официально", и["official"]), ("слух", и["rumor"]),
                                      ("утечка", и["leak"])) if есть]
        строки.append(f"[{и['id']}] {и['source']} · {и['published'] or ''} · {и['title']}"
                      + (f" — {и['text']}" if и["text"] else "")
                      + (f" ({', '.join(пометки)})" if пометки else ""))
    return "\n".join(строки) or "(записей сюжета нет — фактов о новостях не приводи)"


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
        слова = str(превью.get("text") or "").split()
        if len(слова) > 4:
            превью["text"] = " ".join(слова[:4])
        if стоп_слова_в(превью.get("text"), стоп):
            превью["text"] = ""
    return годные[:3], превью


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
    длина = ("8–12 минут, пики удержания примерно на 3–4-й и 8–9-й минутах" if long
             else "45–60 секунд, один пик ближе к концу")
    образцы = "\n".join(_сжатый_образец(о) for о in к["образцы"]) or "(разборов образцов нет — строй по формату)"
    вопрос = (f"Сценарий ролика «{к['titles'][0] if к.get('titles') else к['idea']['title']}».\n"
              f"Формат: {к['idea']['format']}. Длина: {длина}. Повод: {_метка(к)}.\n"
              f"Сюжет: {к['idea']['story'] or 'без новостного повода'} — {к['idea']['summary'] or ''}\n"
              f"СТРУКТУРА — по разборам удачных роликов этого формата (повтори их ритм, крючок и приёмы удержания, "
              f"не копируй тексты):\n{образцы}\n\n"
              f"ИСТОЧНИКИ — факты только отсюда, у каждой фразы-факта номера в src:\n"
              f"{_список_источников(к['источники'])}\n\n"
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


async def съёмки(клиент, к: dict) -> tuple[list[dict], str | None]:
    long = к["idea"]["kind"] != "shorts"
    план = "\n".join(f"{с['from']}–{с['to']} {с['role']}: {с['purpose']}" for с in к["script"])
    вопрос = (f"Список съёмок для ролика «{к['idea']['title']}» по плану:\n{план}\n"
              f"Источники: {_список_источников(к['источники'][:10])}\n"
              "Материал: запись своего геймплея GTA 5 (что именно снять), официальные трейлеры "
              "Rockstar с таймкодами, скриншоты Rockstar Newswire. "
              + ("ЭТО СЮЖЕТ С УТЕЧКОЙ: ни одного кадра утечки, только официальное и свой геймплей. "
                 if к["idea"]["leak"] else "")
              + (f"Дай 1–2 кадра." if not long else "Дай 6–12 пунктов по порядку сценария.")
              + ' Ответ: {"shots": [{"what": "что записать", "source": "GTA 5 | трейлер | Newswire", '
              '"where": "таймкод трейлера или место в игре", "for": "к какому сегменту (таймкод)"}]}')
    данные = await _модель(клиент, _система(к), вопрос, PACKAGE_SMALL_TOKENS)
    съём = [с for с in данные.get("shots") or [] if isinstance(с, dict) and с.get("what")]
    предупреждение = None
    if к["idea"]["leak"]:
        съём = [с for с in съём if not УТЕЧКА.search(" ".join(str(v) for v in с.values()))]
        предупреждение = ПРЕДУПРЕЖДЕНИЕ_УТЕЧКИ
    if not long:
        съём = съём[:2]
    return [{к2: str(с.get(к2) or "") for к2 in ("what", "source", "where", "for")} for с in съём], предупреждение


def проверка(данные: dict, к: dict) -> list[dict]:
    """Чек-лист перед публикацией — считает КОД по готовому пакету."""
    стоп = [str(с) for с in к["настройки"].get("stop_words") or []]
    long = к["idea"]["kind"] != "shorts"
    пункты = []
    найдено = [с for т in данные.get("titles") or [] for с in стоп_слова_в(т, стоп)]
    пункты.append({"item": "Стоп-слова в названиях", "ok": not найдено,
                   "note": ", ".join(найдено) if найдено else "нет"})
    первые = (данные.get("hook") or {}).get("text", "") + " " + (данные.get("hook") or {}).get("shown", "")
    насилие = НАСИЛИЕ.search(первые)
    пункты.append({"item": "Первые 7 с без жёсткого насилия", "ok": None if насилие else True,
                   "note": ("в крючке есть «%s» — проверь кадр" % насилие.group(0)) if насилие else "в крючке не найдено"})
    утечки = [с for с in данные.get("shots") or [] if УТЕЧКА.search(" ".join(с.values()))]
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
    пункты.append({"item": "Утверждения без подтверждения", "ok": не_ноль(без),
                   "note": ("подсвечено «проверь»: %d" % без) if без else "все факты с источником"})
    конец = max((_таймкод(с["to"]) or 0 for с in данные.get("script") or []), default=0)
    if long and not 7.5 * 60 <= конец <= 12.5 * 60:
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
        if и["id"] in нужные or и["official"]:
            итог.append({"id": и["id"], "title": и["title"], "url": и["url"], "source": и["source"],
                         "author": и["author"] or и["source"]})
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
    from sqlalchemy import func
    from database import ModelUsage
    db = ce.SessionLocal()
    try:
        return float(db.query(func.sum(ModelUsage.cost)).filter(
            ModelUsage.tool == ИНСТРУМЕНТ, ModelUsage.created_at >= с).scalar() or 0.0)
    finally:
        db.close()


async def собрать(номер: int) -> dict:
    """Сборка пакета по шагам. Ошибка шага — пакет «ошибка» с текстом."""
    начало = datetime.utcnow()
    t0 = time.monotonic()
    шаги = Шаги(номер)
    беды: list[str] = []
    try:
        db = ce.SessionLocal()
        try:
            п = db.get(ContentPackage, номер)
            идея = db.get(ContentIdea, п.idea_id) if п else None
            if идея is None:
                raise Беда("идеи пакета нет")
            к = контекст(db, идея)
            к["источники"] = _источники(db, идея, int(к["настройки"].get("sources_per_package", 25)))
            шаги.готово("sources", "записей сюжета: %d" % len(к["источники"])
                        if идея.story_id else "без новостного повода")
            к["образцы"] = _образцы(db, идея, int(к["настройки"].get("refs_per_package", 3)))
        finally:
            db.close()
        шаги.готово("refs", "разборов образцов: %d" % len(к["образцы"])
                    if к["образцы"] else "разобранных образцов формата нет — по формату")
        данные = {"kind": к["idea"]["kind"], "idea": к["idea"],
                  "refs": [{"id": о["id"], "yt_id": о["yt_id"], "title": о["title"], "channel": о["channel"]}
                           for о in к["образцы"]]}
        async with cc.новый_клиент() as клиент:
            данные["titles"], данные["thumbnail"] = await названия(клиент, к, беды)
            к["titles"] = данные["titles"]
            шаги.готово("titles", "; ".join(беды) or None)
            сц = await сценарий(клиент, к)
            данные.update(сц)
            к["script"] = сц["script"]
            шаги.готово("script", "фраз «проверь»: %d" % sum(
                1 for с in сц["script"] for л in с["lines"] if л["check"]))
            данные["shots"], данные["shots_warning"] = await съёмки(клиент, к)
            шаги.готово("shots", "пунктов: %d" % len(данные["shots"]))
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
        к["источники"] = _источники(db, идея, int(к["настройки"].get("sources_per_package", 25)))
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
            elif блок == "shots":
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

def начать(db, idea_id: int) -> dict:
    """Кнопка «Собрать пакет». Готовый пакет — сразу он, без модели.
    Идёт — он же. Бюджет исчерпан или исполнитель занят — текст, не сборка."""
    import content_worker as cw
    идея = db.get(ContentIdea, idea_id)
    if идея is None:
        return {"error": "идеи нет", "code": 404}
    п = (db.query(ContentPackage).filter(ContentPackage.idea_id == idea_id)
         .order_by(ContentPackage.id.desc()).first())
    if п is not None and п.state in ("ok", "running"):
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
        к["источники"] = _источники(db, идея, int(к["настройки"].get("sources_per_package", 25)))
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
    х = д.get("hook") or {}
    строки += ["## Крючок (первые 30 с)", "", х.get("text", ""), "", f"В кадре: {х.get('shown', '')}", ""]
    строки += ["## Сценарий", ""]
    for с in д.get("script") or []:
        строки.append(f"### {с['from']}–{с['to']} · {с['role']}" + (f" — {с['purpose']}" if с.get("purpose") else ""))
        for л in с["lines"]:
            метка = f" [ист. {', '.join(map(str, л['src']))}]" if л["src"] else ""
            строки.append(f"- {л['text']}{метка}" + (f" **ПРОВЕРЬ: {л["check"]}**" if л.get("check") else ""))
        строки.append("")
    строки += ["## Список съёмок", ""]
    if д.get("shots_warning"):
        строки += [f"> ВНИМАНИЕ: {д["shots_warning"]}", ""]
    строки += [f"- {с['what']} ({с['source']}{', ' + с['where'] if с['where'] else ''})" for с in д.get("shots") or []] + [""]
    строки += ["## Проверка перед публикацией", ""]
    строки += [f"- [{'x' if п2['ok'] else ' '}] {п2['item']} — {п2['note']}" for п2 in д.get("check") or []] + [""]
    if д.get("sources"):
        строки += ["## Источники для описания", ""]
        строки += [f"- {с['title']} — {с['url']} (находка: {с['author']})" for с in д["sources"]] + [""]
    return "\n".join(строки)
