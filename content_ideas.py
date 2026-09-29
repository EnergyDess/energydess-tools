"""ГЕНЕРАТОР ИДЕЙ РОЛИКОВ И КОНВЕЙЕР (BACKLOG №370).

Идея — это ГОТОВЫЙ РОЛИК, а не сюжет: тип (long | shorts), вид
(hot — свежий повод, trend — тема набирает, evergreen — вечный формат
из археологии), название, строка «почему сейчас», формат, сюжет, факты
и флаги риска.

ЦИФРЫ СЧИТАЕТ КОД, А НЕ МОДЕЛЬ. Спрос — просмотры роликов сюжета за 48 ч,
конкуренция — RU-ролики сюжета, выстрел — медиана из археологии, окно —
48 ч минус возраст сюжета. Модель получает факты готовыми и пишет только
название и «почему сейчас» (и выбирает формат ИЗ ПРЕДЛОЖЕННЫХ номером —
как у разбора сюжетов). Число в её тексте, которого нет в фактах, —
текст отклоняется и спрашивается заново; не вышло за `text_tries` —
текст собирает код, и это помечено (`text_by = code`).

ОТКУДА ФАКТЫ — ХРАНИТСЯ (`basis`): номера записей и хитов, из которых
посчитано. Пруф «из каких записей БД» читается оттуда, а не восстанавливается.

ШАГИ ПРОГОНА ПИШУТСЯ В БАЗУ (`ContentRun.summary["шаги"]`) по мере
выполнения: экран показывает реальные шаги, а не анимацию ради анимации.
"""
import asyncio
import re
import time
import traceback
from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func

import content_collect as cc
import content_db as cdb
import content_engine as ce
from content_db import (ContentArchVideo, ContentFormat, ContentIdea, ContentItem,
                        ContentRun, ContentSource, ContentStory, ContentTheme,
                        ContentVideo)

ИНСТРУМЕНТ_ИДЕИ = "admin-content-ideas"
IDEAS_MAX_TOKENS = int(__import__("os").getenv("CONTENT_IDEAS_MAX_TOKENS", "3000"))
МСК = ZoneInfo("Europe/Moscow")

СТАТУСЫ = {"plan": "В плане", "writing": "Пишу и снимаю", "editing": "Монтаж",
           "published": "Вышло"}
ПРИЧИНЫ = {"format": "не мой формат", "done": "уже было", "boring": "скучно"}
ВИДЫ = {"hot": "горячо", "trend": "тренд", "evergreen": "всегда", "user": "от тебя"}
РИСКИ = {"leak": "только рассказ, без кадров утечки", "18+": "ограниченная реклама"}
# Штраф за «Не то»: формат и сюжет весят меньше в следующих прогонах.
# Множитель за КАЖДУЮ отказную идею в окне `reject_days`.
ШТРАФ = {"format": {"format": 0.4}, "done": {"story": 0.0, "format": 0.7},
         "boring": {"story": 0.5, "format": 0.7}}
ШАГИ = [("stories", "Смотрю свежие сюжеты"),
        ("facts", "Считаю спрос и конкуренцию на русском"),
        ("formats", "Сверяю форматы с археологией"),
        ("text", "Пишу названия роликов"),
        ("check", "Проверяю цифры в текстах"),
        ("save", "Раскладываю идеи")]

_ЗАМКИ: dict = {}
_ЗАДАЧА: dict = {}


def SessionLocal():
    """Сессия — та же, что у движка (тесты подменяют `ce.SessionLocal`)."""
    return ce.SessionLocal()


def _замок() -> asyncio.Lock:
    петля = asyncio.get_running_loop()
    пара = _ЗАМКИ.get("идеи")
    if пара is None or пара[0] is not петля:
        пара = (петля, asyncio.Lock())
        _ЗАМКИ["идеи"] = пара
    return пара[1]


def идёт() -> bool:
    з = _ЗАДАЧА.get("идеи")
    return _замок().locked() or (з is not None and not з.done())


# ── ФАКТЫ ─────────────────────────────────────────────────────────────

def _число(n) -> str:
    return "{:,}".format(int(n)).replace(",", " ")


def _просмотры(n: int) -> str:
    """«1,2 млн», «340 тыс.», «870» — так число и попадает в текст модели."""
    if n >= 1_000_000:
        return ("%.1f" % (n / 1_000_000)).replace(".", ",").replace(",0", "") + " млн"
    if n >= 10_000:
        return "%d тыс." % round(n / 1000)
    return _число(n)


def окно_подпись(окно_ч) -> str:
    if окно_ч is None:
        return "в любой день"
    if окно_ч <= 0:
        return "окно закрывается"
    if окно_ч < 20:
        return "окно ~%d ч" % max(1, round(окно_ч))
    дней = max(1, round(окно_ч / 24))
    return "окно ~%d %s" % (дней, "день" if дней == 1 else "дня")


def факты_подписи(ф: dict) -> dict:
    """Готовые строки фактов — ОДНИ на экран и на промпт. Нет данных —
    так и сказано, а не ноль."""
    спрос = ф.get("спрос")
    ролики = ф.get("спрос_роликов") or 0
    выстрел = ф.get("выстрел")
    конк = ф.get("конкуренция")
    return {
        "спрос": ("%s просмотров за 48 ч" % _просмотры(спрос) if спрос is not None
                  else "нет данных"),
        "спрос_коротко": (_просмотры(спрос) if спрос is not None else "нет данных"),
        "спрос_роликов": ролики,
        "конкуренция": ("нет данных" if конк is None else
                        ("0 роликов" if конк == 0 else "%d %s" % (конк, _роликов(конк)))),
        "первый": конк == 0,
        "выстрел": ("×%s" % ("%.1f" % выстрел).replace(".", ",") if выстрел is not None
                    else "нет данных"),
        "окно": окно_подпись(ф.get("окно_ч")),
    }


def _роликов(n: int) -> str:
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return "ролик"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return "ролика"
    return "роликов"


def _веса(db, тема_id: str, настройки: dict) -> tuple[dict, dict]:
    """Веса форматов и сюжетов по отказам «Не то» за `reject_days`."""
    граница = datetime.utcnow() - timedelta(days=int(настройки.get("reject_days", 30)))
    ф_вес, с_вес = defaultdict(lambda: 1.0), defaultdict(lambda: 1.0)
    for и in (db.query(ContentIdea).filter(ContentIdea.theme_id == тема_id,
                                          ContentIdea.state == "rejected",
                                          ContentIdea.reacted_at >= граница).all()):
        правило = ШТРАФ.get(и.reason or "", {})
        if и.format_id is not None and "format" in правило:
            ф_вес[и.format_id] *= правило["format"]
        if и.story_id is not None and "story" in правило:
            с_вес[и.story_id] *= правило["story"]
    return ф_вес, с_вес


def _занятые_пары(db, тема_id: str, настройки: dict) -> set:
    граница = datetime.utcnow() - timedelta(days=int(настройки.get("dedupe_days", 14)))
    return {(и.story_id, и.format_id)
            for и in db.query(ContentIdea).filter(ContentIdea.theme_id == тема_id,
                                                  ContentIdea.created_at >= граница).all()}


def форматы_с_выстрелом(db, тема_id: str) -> dict:
    """{format_id: {title, медиана, хитов, огр, хиты: [id]}} — медиана выстрела
    хитов формата. Нет хитов с выстрелом — медианы нет (None), а не 0."""
    хиты = defaultdict(list)
    for в in (db.query(ContentArchVideo).filter(ContentArchVideo.theme_id == тема_id,
                                                ContentArchVideo.shot.isnot(None),
                                                ContentArchVideo.format_id.isnot(None)).all()):
        хиты[в.format_id].append(в)
    итог = {}
    for ф in (db.query(ContentFormat).filter(ContentFormat.theme_id == тема_id)
              .order_by(ContentFormat.sort, ContentFormat.id).all()):
        свои = sorted(хиты.get(ф.id, []), key=lambda в: -(в.shot or 0))
        м = cc.медиана([в.shot for в in свои])
        итог[ф.id] = {"id": ф.id, "title": ф.title, "note": ф.note,
                      "медиана": round(м, 1) if м is not None else None,
                      "хитов": len(свои), "огр": sum(1 for в in свои if в.limited_ads),
                      "хиты": [в.id for в in свои[:5]]}
    return итог


def факты_сюжета(db, с: ContentStory, сейчас: datetime, настройки: dict) -> tuple[dict, dict]:
    """(факты, основа). Спрос — просмотры роликов сюжета, вышедших за 48 ч;
    роликов нет — None. Конкуренция — RU-ролики сюжета. Окно hot —
    `hot_hours` минус возраст сюжета."""
    часов = float(настройки.get("hot_hours", 48))
    граница = сейчас - timedelta(hours=48)
    когда = func.coalesce(ContentItem.published_at, ContentItem.first_seen_at)
    записи = (db.query(ContentItem).filter(ContentItem.story_id == с.id)
              .order_by(когда.asc()).all())
    ролики = [и for и in записи if и.platform == "youtube"
              and (и.published_at or и.first_seen_at) >= граница]
    ru = [и for и in записи if и.platform == "youtube" and и.lang == "ru"]
    новости = [и for и in записи if и.platform != "youtube"]
    возраст = max(0.0, (сейчас - (с.first_seen_at or сейчас)).total_seconds() / 3600)
    факты = {"спрос": (sum(и.metric or 0 for и in ролики) if ролики else None),
             "спрос_роликов": len(ролики),
             "конкуренция": len(ru),
             "возраст_ч": round(возраст, 1),
             "окно_ч": round(часов - возраст, 1),
             "источников": с.sources, "рост": round(с.growth or 0.0, 1)}
    основа = {"ролики": [и.id for и in ролики][:20], "ru": [и.id for и in ru][:20],
              "новости": [и.id for и in новости][:10]}
    return факты, основа


# ── КАНДИДАТЫ ─────────────────────────────────────────────────────────

def подобрать(db, тема_id: str, настройки: dict, сейчас: datetime | None = None) -> dict:
    """Кандидаты без текста: long и shorts, каждый — сюжет (или None),
    список форматов на выбор модели, факты, основа, риски, ранг. Числа —
    здесь, до модели. Пары «сюжет + формат» из окна `dedupe_days` не берутся."""
    сейчас = сейчас or datetime.utcnow()
    форматы = форматы_с_выстрелом(db, тема_id)
    ф_вес, с_вес = _веса(db, тема_id, настройки)
    занято = set(_занятые_пары(db, тема_id, настройки))
    часов = float(настройки.get("hot_hours", 48))
    рост_тренда = float(настройки.get("trend_growth", 300))
    на_выбор = int(настройки.get("formats_per_story", 4))

    def ранг_формата(ф):
        м = ф["медиана"]
        return (м if м is not None else 0.5) * ф_вес[ф["id"]]

    порядок_форматов = sorted(форматы.values(), key=lambda ф: -ранг_формата(ф))
    граница = сейчас - timedelta(days=14)
    сюжеты = (db.query(ContentStory)
              .filter(ContentStory.theme_id == тема_id, ContentStory.items > 0,
                      func.coalesce(ContentStory.last_item_at, ContentStory.created_at) >= граница)
              .order_by(ContentStory.score.desc()).all())
    горячие, тренды = [], []
    for с in сюжеты:
        if с_вес[с.id] <= 0:
            continue
        факты, основа = факты_сюжета(db, с, сейчас, настройки)
        if факты["возраст_ч"] <= часов:
            вид = "hot"
        elif (с.growth or 0) >= рост_тренда:
            вид = "trend"
            факты["окно_ч"] = None
        else:
            continue
        факты["вид"] = вид
        ранг = (с.score or 0) * с_вес[с.id] + (1000 if вид == "hot" else 500)
        (горячие if вид == "hot" else тренды).append(
            {"сюжет": с, "вид": вид, "факты": факты, "основа": основа, "ранг": ранг})

    def риски(с, ф):
        р = []
        if с is not None and с.leak:
            р.append("leak")
        if ф and ф["хитов"] and ф["огр"] * 2 >= ф["хитов"]:
            р.append("18+")
        return р

    def варианты(с):
        свои = [ф for ф in порядок_форматов if (с.id, ф["id"]) not in занято]
        return свои[:на_выбор]

    def собрать(тип: str, предел: int) -> list[dict]:
        итог = []
        for к in горячие + тренды:
            if len(итог) >= предел:
                break
            выбор = варианты(к["сюжет"])
            if not выбор:
                continue
            итог.append({"тип": тип, "вид": к["вид"], "сюжет": к["сюжет"],
                         "форматы": выбор, "факты": dict(к["факты"]),
                         "основа": dict(к["основа"]), "ранг": к["ранг"]})
            # формат для пары выберет модель; до выбора пары не заняты,
            # поэтому второй тип того же сюжета получает ОСТАВШИЕСЯ форматы
            for ф in выбор:
                занято.add((к["сюжет"].id, ф["id"]))
        # вечные форматы: с данными археологии, пара (None, формат) свободна
        for ф in порядок_форматов:
            if len(итог) >= предел:
                break
            if ф["медиана"] is None or (None, ф["id"]) in занято:
                continue
            занято.add((None, ф["id"]))
            факты = {"вид": "evergreen", "спрос": None, "спрос_роликов": 0,
                     "конкуренция": None, "окно_ч": None}
            итог.append({"тип": тип, "вид": "evergreen", "сюжет": None, "форматы": [ф],
                         "факты": факты, "основа": {"хиты": ф["хиты"]},
                         "ранг": ранг_формата(ф) * 10})
        return итог

    long_ = собрать("long", int(настройки.get("long_max", 6)))
    shorts = собрать("shorts", int(настройки.get("shorts_max", 5)))
    for к in long_ + shorts:
        к["риски_по"] = риски
    return {"long": long_, "shorts": shorts, "форматы": форматы}


# ── ТЕКСТ МОДЕЛИ И ПРОВЕРКА ЧИСЕЛ ─────────────────────────────────────

_ЧИСЛО = re.compile(r"\d+(?:[.,]\d+)?")


def _числа(текст: str) -> set:
    return {ч.replace(",", ".").rstrip("0").rstrip(".") if "." in ч.replace(",", ".") else ч
            for ч in _ЧИСЛО.findall(текст or "")}


def разрешённые_числа(к: dict, ф: dict | None, тема_title: str = "") -> set:
    """Числа, которые модели можно написать: из фактов (в том виде, в каком
    она их получила), из названий сюжета и формата, из темы."""
    подписи = факты_подписи({**к["факты"], "выстрел": (ф or {}).get("медиана")})
    куски = [подписи["спрос"], подписи["конкуренция"], подписи["выстрел"],
             подписи["окно"], "48", тема_title]
    if к.get("сюжет") is not None:
        куски += [к["сюжет"].title or ""]
    if ф:
        куски.append(ф["title"])
    итог = set()
    for кусок in куски:
        итог |= _числа(кусок)
    return итог


def лишние_числа(текст: str, разрешено: set) -> list[str]:
    return sorted(_числа(текст) - разрешено)


def _вопрос(кандидаты: list[dict], тема_title: str) -> str:
    строки = []
    for n, к in enumerate(кандидаты, 1):
        с = к.get("сюжет")
        строки.append("%d. [%s, %s] %s" % (
            n, "длинный ролик" if к["тип"] == "long" else "Shorts до 60 секунд",
            ВИДЫ[к["вид"]], ("сюжет: " + с.title + (" — " + (с.summary or "")[:200] if с.summary else ""))
            if с else "вечный формат, без новостного повода"))
        for m, ф in enumerate(к["форматы"], 1):
            п = факты_подписи({**к["факты"], "выстрел": ф["медиана"]})
            строки.append("   формат %d: %s (выстрел формата на GTA 5: %s)" % (m, ф["title"], п["выстрел"]))
        п = факты_подписи(к["факты"])
        if с is not None:
            строки.append("   факты: спрос %s; на русском %s; %s" % (
                п["спрос"], п["конкуренция"], п["окно"]))
    return ("Тема канала: %s. Ниже кандидаты в ролики. Для каждого выбери формат "
            "номером из его списка и напиши название ролика на русском (до 90 знаков, "
            "цепляющее, без кликбейтной лжи) и одну строку «почему сейчас» (до 120 знаков). "
            "ЦИФРЫ: пиши только числа, которые есть в фактах, названии сюжета или формата; "
            "своих чисел, дат и процентов не придумывай.\n"
            "Ответ — JSON: {\"ideas\": [{\"n\": 1, \"format\": 1, \"title\": \"…\", \"why\": \"…\"}]}\n\n"
            % тема_title + "\n".join(строки))


_СИСТЕМА = ("Ты редактор YouTube-канала про вселенную GTA на русском. "
            "Пишешь только названия роликов и строку «почему сейчас». "
            "Все числа берёшь из данных, ничего не выдумываешь. Отвечаешь только JSON.")


def разобрать_ответ(текст: str, кандидаты: list[dict], тема_title: str) -> tuple[dict, dict]:
    """({n: (формат, title, why)} годных, {n: причина} отклонённых)."""
    годные, отказы = {}, {}
    тело = ce._json_ответа(текст or "")
    ряды = тело.get("ideas") if isinstance(тело, dict) else None
    if not isinstance(ряды, list):
        return {}, {n: "ответ не JSON" for n in range(1, len(кандидаты) + 1)}
    for р in ряды:
        if not isinstance(р, dict):
            continue
        n = ce._целое(р.get("n"))
        if n is None or not 1 <= n <= len(кандидаты):
            continue
        к = кандидаты[n - 1]
        м = ce._целое(р.get("format")) or 1
        if not 1 <= м <= len(к["форматы"]):
            отказы[n] = "формат вне списка"
            continue
        ф = к["форматы"][м - 1]
        title = str(р.get("title") or "").strip()[:140]
        why = str(р.get("why") or "").strip()[:200]
        if not title:
            отказы[n] = "пустое название"
            continue
        лишние = лишние_числа(title + " " + why, разрешённые_числа(к, ф, тема_title))
        if лишние:
            отказы[n] = "числа не из фактов: " + ", ".join(лишние)
            continue
        годные[n] = (ф, title, why)
    for n in range(1, len(кандидаты) + 1):
        if n not in годные and n not in отказы:
            отказы[n] = "модель пропустила"
    return годные, отказы


def текст_кодом(к: dict) -> tuple[dict, str, str]:
    """Запасной текст без модели: формат — первый из предложенных, название —
    сюжет либо формат, «почему сейчас» — из фактов."""
    ф = к["форматы"][0]
    п = факты_подписи({**к["факты"], "выстрел": ф["медиана"]})
    с = к.get("сюжет")
    if с is not None:
        title = с.title
        why = ("Свежий повод, на русском %s" % п["конкуренция"] if к["вид"] == "hot"
               else "Тема набирает просмотры")
    else:
        title = ф["title"]
        why = "Формат выстреливал на GTA 5: %s" % п["выстрел"]
    return ф, title, why


# ── ПРОГОН ────────────────────────────────────────────────────────────

class Шаги:
    """Шаги прогона в базе. Пишутся по мере выполнения — экран читает их."""

    def __init__(self, номер: int):
        self.номер = номер
        self.шаги = [{"k": к, "t": т, "done": False, "note": None} for к, т in ШАГИ]
        self._записать()

    def готово(self, ключ: str, заметка: str | None = None):
        for ш in self.шаги:
            if ш["k"] == ключ:
                ш["done"] = True
                ш["note"] = заметка
        self._записать()

    def _записать(self, **ещё):
        db = SessionLocal()
        try:
            п = db.get(ContentRun, self.номер)
            if п is not None:
                итог = cdb.из_json(п.summary, {}) or {}
                итог["шаги"] = self.шаги
                итог.update(ещё)
                п.summary = cdb.в_json(итог)
                db.commit()
        finally:
            db.close()


async def _тексты(кандидаты: list[dict], тема_title: str, попыток: int) -> dict:
    """Тексты моделью с перепросом отклонённых. {n: (ф, title, why, by, tries, причина)}."""
    итог, осталось = {}, list(range(1, len(кандидаты) + 1))
    беда = None
    попытка = 0
    async with cc.новый_клиент() as клиент:
        while осталось and попытка < попыток:
            попытка += 1
            часть = [кандидаты[n - 1] for n in осталось]
            текст, беда = await ce._спросить(клиент, ИНСТРУМЕНТ_ИДЕИ, _СИСТЕМА,
                                             _вопрос(часть, тема_title), IDEAS_MAX_TOKENS)
            if беда:
                break
            годные, отказы = разобрать_ответ(текст, часть, тема_title)
            следующие = []
            for i, n in enumerate(осталось, 1):
                if i in годные:
                    ф, t, w = годные[i]
                    итог[n] = (ф, t, w, "model", попытка, None)
                else:
                    следующие.append(n)
                    итог[n] = (None, None, None, None, попытка, отказы.get(i))
            if отказы:
                print("[content] идеи: отклонено %d — %s" % (
                    len(отказы), "; ".join(f"{n}: {п}" for n, п in list(отказы.items())[:5])),
                    flush=True)
            осталось = следующие
    for n in range(1, len(кандидаты) + 1):
        if n not in итог or итог[n][3] is None:
            ф, t, w = текст_кодом(кандидаты[n - 1])
            причина = (итог.get(n) or (None,) * 6)[5] or беда
            итог[n] = (ф, t, w, "code", попытка, причина)
    return {"тексты": итог, "беда": беда}


async def сгенерировать(повод: str = "admin") -> dict:
    """Один прогон генерации идей по всем активным темам."""
    if _замок().locked():
        return {"state": "skipped", "note": "генерация уже идёт"}
    async with _замок():
        номер = _начать(повод)
        шаги = Шаги(номер)
        t0 = time.monotonic()
        состояние, заметка, итог = "ok", None, {"идей": 0}
        try:
            db = SessionLocal()
            try:
                cdb.засеять(db)
                настройки = cdb.настройка(db, "ideas")
                темы = [(т.id, т.title) for т in db.query(ContentTheme)
                        .filter(ContentTheme.active.is_(True)).order_by(ContentTheme.id).all()]
                набор = {т: подобрать(db, т, настройки) for т, _ in темы}
            finally:
                db.close()
            всего = sum(len(н["long"]) + len(н["shorts"]) for н in набор.values())
            свежих = sum(1 for н in набор.values() for к in н["long"] if к["вид"] != "evergreen")
            шаги.готово("stories", "сюжетов с поводом: %d" % свежих)
            шаги.готово("facts", "кандидатов: %d" % всего)
            шаги.готово("formats", "форматов с выстрелом: %d" % sum(
                1 for н in набор.values() for ф in н["форматы"].values() if ф["медиана"] is not None))
            тексты_всех, беды, отклонено = {}, [], 0
            for тема_id, тема_title in темы:
                кандидаты = набор[тема_id]["long"] + набор[тема_id]["shorts"]
                if not кандидаты:
                    continue
                р = await _тексты(кандидаты, тема_title, int(настройки.get("text_tries", 3)))
                тексты_всех[тема_id] = р["тексты"]
                if р["беда"]:
                    беды.append(р["беда"])
                отклонено += sum(1 for в in р["тексты"].values() if в[4] > 1 or в[3] == "code")
            шаги.готово("text", ("модель: " + беды[0]) if беды else None)
            шаги.готово("check", "перепрошено либо собрано кодом: %d" % отклонено)
            db = SessionLocal()
            try:
                for тема_id, _ in темы:
                    кандидаты = набор[тема_id]["long"] + набор[тема_id]["shorts"]
                    тексты = тексты_всех.get(тема_id, {})
                    for n, к in enumerate(кандидаты, 1):
                        ф, title, why, by, tries, _п = тексты[n]
                        с = к.get("сюжет")
                        факты = {**к["факты"], "выстрел": ф["медиана"], "формат_хитов": ф["хитов"]}
                        основа = {**к["основа"], "хиты": ф["хиты"]}
                        db.add(ContentIdea(
                            theme_id=тема_id, run_id=номер, kind=к["тип"], sort=к["вид"],
                            title=title, why=why, format_id=ф["id"],
                            story_id=с.id if с is not None else None,
                            facts=cdb.в_json(факты), basis=cdb.в_json(основа),
                            risks=cdb.в_json(к["риски_по"](с, ф)), rank=к["ранг"],
                            main=False, state="new", text_by=by, text_tries=tries))
                        итог["идей"] += 1
                    db.flush()
                    назначить_главную(db, тема_id, номер)
                db.commit()
            finally:
                db.close()
            шаги.готово("save", "идей: %d" % итог["идей"])
            if беды:
                состояние, заметка = "partial", "тексты собраны кодом: " + беды[0]
        except Exception as e:
            traceback.print_exc()
            состояние, заметка = "error", f"{type(e).__name__}: {e}"
        итог["сек"] = round(time.monotonic() - t0, 1)
        итог["шаги"] = шаги.шаги
        ce._закончить(номер, состояние, итог, заметка)
        print(f"[content] идеи №{номер}: {состояние}, идей {итог['идей']} за {итог['сек']} с", flush=True)
        return {"run_id": номер, "state": состояние, **итог}


def _начать(повод: str) -> int:
    """Строка прогона идей. «running» прежних прогонов ИДЕЙ — ничьи (замок
    свободен), они закрываются; прогоны сбора не трогаются."""
    db = SessionLocal()
    try:
        for ст in db.query(ContentRun).filter(ContentRun.kind == "ideas",
                                              ContentRun.state == "running").all():
            ст.state, ст.finished_at = "error", datetime.utcnow()
            ст.note = (ст.note or "") + " прерван: процесс перезапущен посреди прогона"
        п = ContentRun(kind="ideas", trigger=повод, state="running", started_at=datetime.utcnow())
        db.add(п)
        db.commit()
        return п.id
    finally:
        db.close()


def назначить_главную(db, тема_id: str, номер: int | None = None) -> ContentIdea | None:
    """Главная — лучшая long последнего прогона: new, не отложенная."""
    if номер is None:
        последний = последний_прогон(db)
        номер = последний.id if последний else None
    if номер is None:
        return None
    for и in db.query(ContentIdea).filter(ContentIdea.run_id == номер,
                                          ContentIdea.theme_id == тема_id,
                                          ContentIdea.main.is_(True)).all():
        if и.state == "new" and not и.deferred:
            return и
        и.main = False
    лучшая = (db.query(ContentIdea).filter(ContentIdea.run_id == номер,
                                           ContentIdea.theme_id == тема_id,
                                           ContentIdea.kind == "long",
                                           ContentIdea.state == "new",
                                           ContentIdea.deferred.is_(False))
              .order_by(ContentIdea.rank.desc(), ContentIdea.id).first())
    if лучшая is not None:
        лучшая.main = True
    return лучшая


def последний_прогон(db) -> ContentRun | None:
    return (db.query(ContentRun).filter(ContentRun.kind == "ideas",
                                        ContentRun.state.in_(("ok", "partial")))
            .order_by(ContentRun.id.desc()).first())


def запустить(повод: str = "admin") -> dict:
    if идёт():
        return {"ok": False, "busy": True, "error": "Идеи уже собираются — дождитесь конца."}
    _ЗАДАЧА["идеи"] = asyncio.create_task(сгенерировать(повод))
    return {"ok": True}


# ── РЕАКЦИИ ───────────────────────────────────────────────────────────

def реакция(db, idea_id: int, действие: str, причина: str | None = None) -> dict:
    и = db.get(ContentIdea, idea_id)
    if и is None:
        return {"error": "идеи нет", "code": 404}
    сейчас = datetime.utcnow()
    if действие == "plan":
        if и.state == "planned":
            return {"ok": True, "video_id": None}
        и.state, и.reacted_at, и.main = "planned", сейчас, False
        р = ContentVideo(theme_id=и.theme_id, idea_id=и.id, title=и.title, kind=и.kind,
                         status="plan", created_at=сейчас, status_at=сейчас)
        db.add(р)
        db.flush()
        назначить_главную(db, и.theme_id, и.run_id)
        db.commit()
        return {"ok": True, "video_id": р.id}
    if действие == "reject":
        if причина not in ПРИЧИНЫ:
            return {"error": "причина: format | done | boring", "code": 400}
        и.state, и.reason, и.reacted_at, и.main = "rejected", причина, сейчас, False
        назначить_главную(db, и.theme_id, и.run_id)
        db.commit()
        return {"ok": True}
    if действие == "later":
        и.deferred, и.main, и.reacted_at = True, False, сейчас
        db.flush()
        назначить_главную(db, и.theme_id, и.run_id)
        db.commit()
        return {"ok": True}
    return {"error": "действие: plan | reject | later", "code": 400}


def сменить_статус(db, video_id: int, статус: str, ссылка: str | None = None) -> dict:
    р = db.get(ContentVideo, video_id)
    if р is None:
        return {"error": "ролика нет", "code": 404}
    if статус not in СТАТУСЫ:
        return {"error": "статус: " + " | ".join(СТАТУСЫ), "code": 400}
    ссылка = (ссылка or "").strip() or None
    if ссылка and not re.match(r"^https://(www\.|m\.)?(youtube\.com|youtu\.be)/", ссылка):
        return {"error": "ссылка должна вести на YouTube", "code": 400}
    р.status, р.status_at = статус, datetime.utcnow()
    if статус == "published":
        р.published_at = р.published_at or datetime.utcnow()
        if ссылка:
            р.youtube_url = ссылка
    db.commit()
    return {"ok": True, "status": р.status, "статус": СТАТУСЫ[р.status]}


# ── РАДАР, НЕДЕЛЯ, РЕЛИЗ ──────────────────────────────────────────────

def радар(db, сейчас: datetime | None = None) -> dict:
    """Зелёный — был успешный цикл за `radar_hours` и ни один ВКЛЮЧЁННЫЙ
    источник не падает дольше `radar_hours`. Квота и «выключен, ждёт ключ»
    падением не считаются. Иначе красный с причиной."""
    сейчас = сейчас or datetime.utcnow()
    часов = float(cdb.настройка(db, "ideas").get("radar_hours", 2))
    граница = сейчас - timedelta(hours=часов)
    цикл = (db.query(ContentRun).filter(ContentRun.kind == "cycle",
                                        ContentRun.state.in_(("ok", "partial")),
                                        ContentRun.finished_at.isnot(None))
            .order_by(ContentRun.finished_at.desc()).first())
    причины = []
    if цикл is None or цикл.finished_at < граница:
        причины.append("успешного сбора не было %d ч" % часов)
    for и in db.query(ContentSource).filter(ContentSource.enabled.is_(True)).all():
        if и.last_state in ("error",) and (и.last_ok_at is None or и.last_ok_at < граница):
            причины.append("«%s» падает дольше %d ч" % (и.name, часов))
    return {"ok": not причины, "причина": "; ".join(причины) or None,
            "последний": цикл.finished_at if цикл else None}


def неделя(db, тема_id: str, сейчас: datetime | None = None) -> dict:
    """Вышло роликов на этой неделе (пн–вс по Москве) против цели."""
    сейчас = сейчас or datetime.utcnow()
    м = сейчас.replace(tzinfo=ZoneInfo("UTC")).astimezone(МСК)
    пн = (м - timedelta(days=м.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    с = пн.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    вышло = (db.query(func.count(ContentVideo.id))
             .filter(ContentVideo.theme_id == тема_id, ContentVideo.status == "published",
                     ContentVideo.published_at >= с).scalar() or 0)
    return {"вышло": вышло, "цель": int(cdb.настройка(db, "ideas").get("week_goal", 3))}


def до_релиза(db, сейчас: datetime | None = None) -> int | None:
    дата = cdb.настройка(db, "ideas").get("release_date")
    if not дата:
        return None
    сейчас = сейчас or datetime.utcnow()
    сегодня = сейчас.replace(tzinfo=ZoneInfo("UTC")).astimezone(МСК).date()
    try:
        return (datetime.strptime(дата, "%Y-%m-%d").date() - сегодня).days
    except ValueError:
        return None


# ── КОГДА ГЕНЕРИРОВАТЬ ────────────────────────────────────────────────

def пора_утром(db, сейчас: datetime | None = None) -> bool:
    """Утренний прогон: после `generate_at_msk` по Москве, и сегодня после
    этого часа удачного прогона ещё не было."""
    сейчас = сейчас or datetime.utcnow()
    ч, мин = (cdb.настройка(db, "ideas").get("generate_at_msk") or "08:00").split(":")
    м = сейчас.replace(tzinfo=ZoneInfo("UTC")).astimezone(МСК)
    рубеж = м.replace(hour=int(ч), minute=int(мин), second=0, microsecond=0)
    if м < рубеж:
        return False
    рубеж_utc = рубеж.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    return (db.query(ContentRun).filter(ContentRun.kind == "ideas",
                                        ContentRun.state.in_(("ok", "partial", "running")),
                                        ContentRun.started_at >= рубеж_utc).first()) is None


def горячий_без_идеи(db, сейчас: datetime | None = None) -> bool:
    """Сюжет пересёк порог «горячо» (`hot_score`), свежий, и идеи по нему
    ещё не было — пора генерировать, не дожидаясь утра."""
    сейчас = сейчас or datetime.utcnow()
    н = cdb.настройка(db, "ideas")
    граница = сейчас - timedelta(hours=float(н.get("hot_hours", 48)))
    горячие = [с.id for с in db.query(ContentStory).filter(
        ContentStory.score >= int(н.get("hot_score", 60)),
        ContentStory.first_seen_at >= граница).all()]
    if not горячие:
        return False
    с_идеями = {r[0] for r in db.query(ContentIdea.story_id)
               .filter(ContentIdea.story_id.in_(горячие)).all()}
    return any(с not in с_идеями for с in горячие)


def проверить_расписание() -> str | None:
    """Зовётся планировщиком: вернёт повод, если пора генерировать."""
    db = SessionLocal()
    try:
        cdb.засеять(db)
        if пора_утром(db):
            return "morning"
        if горячий_без_идеи(db):
            return "hot"
        return None
    finally:
        db.close()
