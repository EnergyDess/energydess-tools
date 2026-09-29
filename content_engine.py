"""ЦИКЛ СБОРА, ПЛАНИРОВЩИК, СЮЖЕТЫ И АРХЕОЛОГИЯ МОДУЛЯ «КОНТЕНТ».

BACKLOG №365 (источники и хранение) и №366 (сюжеты, оценка, археология).

ЦИКЛ — каждые 30 минут внутри приложения (`cycle.minutes` в базе).
Машина прода не засыпает (`fly.toml`: `auto_stop_machines = false`,
`min_machines_running = 1`), поэтому планировщику внутри процесса есть
где жить. Вне Fly он выключен: стенд, pytest и CI не ходят в чужую сеть
сами — сбор там только по кнопке либо пробой (`CONTENT_SCHEDULER=1`
включает явно, `0` — выключает и на проде).

ПОВТОРНЫЙ ЗАПУСК ВО ВРЕМЯ ИДУЩЕГО СБОРА — ПРОПУСК, и пропуск записывается
строкой прогона: «не запустился, потому что шёл предыдущий» обязано
отличаться от «не запускался вовсе» (§6.0.1). Замок один на все прогоны
модуля — цикл, поиск каналов, археологию: все трое тратят одну квоту
YouTube и одну модель.

СОЕДИНЕНИЕ К БАЗЕ НА ВРЕМЯ СЕТИ НЕ ДЕРЖИТСЯ (проверка 27): база — в коротких
синхронных помощниках со своей сессией, сеть — между ними.

МОДЕЛЬ — ТОЛЬКО ЧЕРЕЗ `main._модель_post` с `**ПОЛИТИКА_ЗАПРОСА` (§2.4, §2.7):
строка расхода ложится в `model_usage` под именем `admin-content-*`
(группа «Админка» на странице «Расход»), политика нулевого удержания
данных — та же, что у всех. Отвечает модель НОМЕРАМИ из присланных
списков; номер вне списка, ответ не той формы — в базу не ложится.
"""
import asyncio
import json
import math
import os
import statistics
import time
import traceback
from collections import defaultdict
from datetime import datetime, timedelta

import httpx
from sqlalchemy import func, text

import content_collect as cc
import content_db as cdb
from content_db import (ContentArchVideo, ContentChannel, ContentFormat, ContentItem,
                        ContentRun, ContentSnapshot, ContentSource, ContentStory,
                        ContentTheme)
from database import ModelUsage, SessionLocal

# ПОТОЛКИ ОТВЕТА МОДЕЛИ — ИМЕНЕМ, С ПЕРЕОПРЕДЕЛЕНИЕМ ИЗ ОКРУЖЕНИЯ (§2.1):
# число на месте вызова нельзя ни грепнуть, ни сверить с расходом.
# Пачка сюжетов — 25 записей по ~15 токенов решения плюс названия новых
# сюжетов (~60 токенов каждое); пачка форматов — 30 роликов по ~35 токенов.
STORIES_MAX_TOKENS = int(os.getenv("CONTENT_STORIES_MAX_TOKENS", "3000"))
FORMATS_MAX_TOKENS = int(os.getenv("CONTENT_FORMATS_MAX_TOKENS", "3000"))
# Префикс `admin-` уводит строки расхода в группу «Админка» (`_РАСХОД_ПРЕФИКСЫ`)
ИНСТРУМЕНТ_СЮЖЕТЫ = "admin-content-stories"
ИНСТРУМЕНТ_ФОРМАТЫ = "admin-content-formats"
ПРОГОН_ЗАВИС_МИН = 40            # «running» старше — прогон прерван перезапуском
ПОТОЛОК_ИСТОЧНИКА_СЕК = 150      # весь сбор одного источника
ПОТОЛОК_YT_СЕК = 600             # YouTube: поиск каналов плюс опрос реестра
ПОТОЛОК_АРХЕОЛОГИИ_СЕК = 900
ЦЕНА_АРХЕОЛОГИИ_ОЦЕНКА = 2000    # единиц YouTube — меньше осталось, автозапуск ждёт
# Цена одного цикла сбора в единицах YouTube — резерв циклам до сброса
# суток Google (`_археология_нужна`). Замер на проде 2026-09-29: 61
# (60 каналов реестра × playlistItems плюс videos). В базе — `cycle_units`.
ЦЕНА_ЦИКЛА_ОЦЕНКА = 70
# ВЕРСИЯ ПРАВИЛ АРХЕОЛОГИИ. Прогон прежней версии планировщик пересобирает
# сам один раз (`_археология_нужна`). 2 — 2026-09-29: только ролики про тему
# (запрос в поиске по каналу и маркеры), язык канала по тексту, таблица
# пересобирается целиком — замер на проде: из 204 хитов первой версии
# большая часть была про другие игры. 3 — 2026-09-29: тема только
# в ЗАГОЛОВКЕ (16 хитов из 158 держались за неё описанием), канал
# на другом языке латиницы в группы не идёт (Fernanfloo и Tauz стояли
# в англоязычных) — замер версии 2 на проде. 4 — 2026-09-29: короткое
# описание канала признаков языка не даёт (Tauz: «Canal do Tauz!»),
# тогда решает страна канала — замер версии 3 на проде.
АРХЕОЛОГИЯ_ВЕРСИЯ = 5
YT_ПО_УМОЛЧАНИЮ = "https://www.googleapis.com/youtube/v3"
ФЛАГИ_МОНЕТИЗАЦИИ = ("18+", "стриптиз-клубы", "шок-насилие")
ФОРМАТОВ_ПАЧКА = 30
# График снимков по возрасту записи: моложе 6 ч — каждый цикл, до суток —
# раз в 2 ч, до трёх суток — раз в 6 ч. Каждый цикл по всем молодым роликам
# дал бы ~144 строки на ролик за трое суток; так — около тридцати.
ГРАФИК_СНИМКОВ = ((6, 0.0), (24, 2.0), (72, 6.0))

_ЗАМКИ: dict = {}                # цикл событий -> замок прогонов
_ЗАДАЧИ: dict = {}               # вид -> задача; ссылка держит её от сборщика мусора
_СТАРТОВАЛ = False


def _замок() -> asyncio.Lock:
    """Замок прогонов СВОЕГО цикла событий. Один `asyncio.Lock` на модуль
    привязался бы к первому циклу и падал бы в следующем (тесты поднимают
    приложение много раз в одном процессе); на проде цикл один."""
    петля = asyncio.get_running_loop()
    пара = _ЗАМКИ.get("текущий")
    if пара is None or пара[0] is not петля:
        пара = (петля, asyncio.Lock())
        _ЗАМКИ["текущий"] = пара
    return пара[1]


def _main():
    """`main` импортируется в момент вызова: модуль подключается из `main`,
    и прямой импорт наверху замкнул бы круг."""
    import main
    return main


def ключ_youtube() -> str:
    """Ключ ОТДЕЛЬНОГО проекта владельца. Прежний `YOUTUBE_API_KEY` (проверка
    роликов справочника) модуль не берёт даже запасным — так решил владелец:
    у проектов раздельные квоты, и один не должен съедать другой."""
    return os.getenv("CONTENT_YOUTUBE_API_KEY", "").strip()


def планировщик_включён() -> bool:
    явно = os.getenv("CONTENT_SCHEDULER", "").strip()
    if явно in ("0", "1"):
        return явно == "1"
    return bool(os.getenv("FLY_APP_NAME"))


def _из(текст, запас):
    return cdb.из_json(текст, запас)


# ── ПРОГОНЫ ───────────────────────────────────────────────────────────

def _начать(вид: str, повод: str, тема_id: str | None = None) -> int:
    db = SessionLocal()
    try:
        # Замок свободен — значит «running» в базе ничей: процесс, который
        # его вёл, перезапущен. Строка называет это, а не висит вечно.
        # Прогоны ИДЕЙ ведёт свой замок (`content_ideas`) — их не трогаем.
        for ст in db.query(ContentRun).filter(ContentRun.state == "running",
                                              ContentRun.kind != "ideas").all():
            ст.state = "error"
            ст.finished_at = datetime.utcnow()
            ст.note = (ст.note or "") + " прерван: процесс перезапущен посреди прогона"
        прогон = ContentRun(kind=вид, theme_id=тема_id, trigger=повод, state="running",
                            started_at=datetime.utcnow())
        db.add(прогон)
        db.commit()
        return прогон.id
    finally:
        db.close()


def _закончить(номер: int, состояние: str, итог: dict, заметка: str | None = None) -> None:
    db = SessionLocal()
    try:
        прогон = db.get(ContentRun, номер)
        if прогон is None:
            return
        прогон.state = состояние
        прогон.finished_at = datetime.utcnow()
        прогон.summary = cdb.в_json(итог)
        if заметка:
            прогон.note = заметка[:2000]
        db.commit()
    finally:
        db.close()


def _пропуск(вид: str, повод: str) -> dict:
    """Строка «пропущен: шёл предыдущий» — защита от наложения видна."""
    db = SessionLocal()
    try:
        идёт = (db.query(ContentRun).filter(ContentRun.state == "running",
                                           ContentRun.kind != "ideas")
                .order_by(ContentRun.id.desc()).first())
        заметка = ("пропущен: идёт прогон №%d (%s)" % (идёт.id, идёт.kind) if идёт
                   else "пропущен: идёт другой прогон модуля")
        сейчас = datetime.utcnow()
        db.add(ContentRun(kind=вид, trigger=повод, state="skipped", started_at=сейчас,
                          finished_at=сейчас, note=заметка))
        db.commit()
        print(f"[content] {вид} ({повод}): {заметка}", flush=True)
        return {"state": "skipped", "note": заметка}
    finally:
        db.close()


def занят() -> bool:
    """Идёт ли прогон модуля. Своя задача и планировщик помехой не считаются:
    прогон, запущенный кнопкой, сам себе не помеха, а планировщик ждёт
    внутри себя и замок берёт тем же путём."""
    сама = asyncio.current_task()
    петля = asyncio.get_running_loop()
    return _замок().locked() or any(
        not з.done() and з is not сама and з.get_loop() is петля
        for вид, з in _ЗАДАЧИ.items() if вид != "планировщик")


# ── СОСТОЯНИЕ ИСТОЧНИКА ───────────────────────────────────────────────

def _источник_итог(номер: int, состояние: str, *, получено=None, новых=None, сек=None,
                   ошибка: str | None = None) -> None:
    db = SessionLocal()
    try:
        и = db.get(ContentSource, номер)
        if и is None:
            return
        сейчас = datetime.utcnow()
        и.last_run_at = сейчас
        и.last_state = состояние
        и.last_sec = сек
        if состояние == "ok":
            и.last_ok_at = сейчас
            и.last_seen = получено
            и.last_new = новых
        if ошибка:
            и.last_error = ошибка[:2000]
            и.last_error_at = сейчас
        db.commit()
    finally:
        db.close()


def _списать_квоту(метод: str, единиц: int) -> None:
    """Расход квоты YouTube — ДО вызова, своей короткой сессией."""
    db = SessionLocal()
    try:
        cdb.квота_списать(db, метод, единиц)
    finally:
        db.close()


# ── ЗАПИСЬ ЗАПИСЕЙ ────────────────────────────────────────────────────

def _записать(тема_id: str, источник: dict, записи: list[dict]) -> tuple[int, int]:
    """(новых, всего) — вставка новых по `ext_id`, обновление известных,
    снимок счётчика у тех, у кого он есть. Дубль невозможен: `ext_id`
    уникален в теме, а повтор внутри одной пачки отсеивается здесь."""
    if not записи:
        return 0, 0
    по_ключу = {}
    for з in записи:
        по_ключу.setdefault(з["ext_id"], з)
    сейчас = datetime.utcnow()
    db = SessionLocal()
    try:
        ключи = list(по_ключу)
        есть = {}
        for i in range(0, len(ключи), 400):         # потолок переменных SQLite
            for и in (db.query(ContentItem)
                      .filter(ContentItem.theme_id == тема_id,
                              ContentItem.ext_id.in_(ключи[i:i + 400])).all()):
                есть[и.ext_id] = и
        новых = 0
        for ключ, з in по_ключу.items():
            и = есть.get(ключ)
            if и is None:
                и = ContentItem(
                    theme_id=тема_id, ext_id=ключ, source_id=источник["id"],
                    source_key=з.get("source_key") or f"{источник['kind']}:{источник['id']}",
                    source_name=(з.get("source_name") or источник["name"])[:200],
                    platform=з["platform"], channel_id=з.get("channel_id"),
                    url=з["url"], title=з["title"] or "(без заголовка)",
                    text=(з.get("text") or "")[:cc.ТЕКСТ_ЗНАКОВ] or None,
                    author=з.get("author"), flair=з.get("flair"), lang=з.get("lang"),
                    official=bool(источник.get("official") or з.get("official")),
                    published_at=з.get("published_at"), first_seen_at=сейчас,
                    last_seen_at=сейчас, metric=з.get("metric"),
                    comments=з.get("comments"), likes=з.get("likes"))
                db.add(и)
                новых += 1
            else:
                и.last_seen_at = сейчас
                for поле in ("metric", "comments", "likes"):
                    if з.get(поле) is not None:
                        setattr(и, поле, з[поле])
            if з.get("metric") is not None:
                db.flush()
                возраст = ((сейчас - и.published_at).total_seconds() / 3600
                           if и.published_at else None)
                db.add(ContentSnapshot(item_id=и.id, taken_at=сейчас, age_h=возраст,
                                       metric=з.get("metric"), comments=з.get("comments"),
                                       likes=з.get("likes")))
        db.commit()
        return новых, len(по_ключу)
    finally:
        db.close()


# ── YOUTUBE ───────────────────────────────────────────────────────────

def _каналы_темы(тема_id: str) -> tuple[list[dict], int]:
    """(каналы к опросу, каналов в реестре всего). Убранные не опрашиваются."""
    db = SessionLocal()
    try:
        все = db.query(ContentChannel).filter(ContentChannel.theme_id == тема_id).all()
        к_опросу = [{"id": к.id, "yt_id": к.yt_id, "title": к.title, "uploads": к.uploads,
                     "lang": к.lang, "official": к.official}
                    for к in все if к.status in ("candidate", "keep")]
        return к_опросу, len(все)
    finally:
        db.close()


def _сохранить_каналы(тема_id: str, найдено: list[dict]) -> tuple[int, int]:
    """(новых, обновлено). У известного канала обновляются числа, статус
    владельца НЕ трогается: «убран» остаётся убранным и после поиска."""
    db = SessionLocal()
    try:
        новых = обновлено = 0
        for св in найдено:
            к = (db.query(ContentChannel)
                 .filter(ContentChannel.theme_id == тема_id, ContentChannel.yt_id == св["yt_id"])
                 .first())
            if к is None:
                к = ContentChannel(theme_id=тема_id, yt_id=св["yt_id"], title=св["title"],
                                   status="candidate", found_by=св.get("found_by"),
                                   status_at=datetime.utcnow())
                db.add(к)
                новых += 1
            else:
                обновлено += 1
            к.title = св["title"] or к.title
            for поле in ("handle", "country", "subscribers", "videos", "views",
                         "created_yt", "uploads"):
                if св.get(поле) is not None:
                    setattr(к, поле, св[поле])
            if св.get("lang") and not к.lang:
                к.lang = св["lang"]
        db.commit()
        return новых, обновлено
    finally:
        db.close()


def _отметить_опрос(ошибки: dict, опрошены: list[int]) -> None:
    db = SessionLocal()
    try:
        сейчас = datetime.utcnow()
        for номер in опрошены:
            к = db.get(ContentChannel, номер)
            if к is not None:
                к.last_polled_at = сейчас
                к.last_error = ошибки.get(номер)
        for номер, текст in ошибки.items():
            if номер not in опрошены:
                к = db.get(ContentChannel, номер)
                if к is not None:
                    к.last_error = текст[:500]
        db.commit()
    finally:
        db.close()


def _что_спросить(тема_id: str, ids: list[str], часов_следить: float) -> tuple[set, list]:
    """(известные ролики, молодые ролики, у которых подошёл срок снимка)."""
    сейчас = datetime.utcnow()
    db = SessionLocal()
    try:
        ext = ["yt:" + v for v in ids]
        известные = set()
        for i in range(0, len(ext), 400):
            известные |= {r[0][3:] for r in db.query(ContentItem.ext_id)
                          .filter(ContentItem.theme_id == тема_id,
                                  ContentItem.ext_id.in_(ext[i:i + 400])).all()}
        граница = сейчас - timedelta(hours=часов_следить)
        # Ролики УБРАННОГО канала не снимаются: «убрать» значит, что канал
        # не опрашивается вовсе, и квота на его ролики не тратится
        убраны = {r[0] for r in db.query(ContentChannel.id)
                  .filter(ContentChannel.theme_id == тема_id,
                          ContentChannel.status == "removed").all()}
        молодые = [м for м in (db.query(ContentItem.id, ContentItem.ext_id,
                                        ContentItem.published_at, ContentItem.channel_id)
                               .filter(ContentItem.theme_id == тема_id,
                                       ContentItem.platform == "youtube",
                                       ContentItem.published_at >= граница).all())
                   if м[3] not in убраны]
        последний = dict(db.query(ContentSnapshot.item_id, func.max(ContentSnapshot.taken_at))
                         .filter(ContentSnapshot.item_id.in_([м[0] for м in молодые] or [-1]))
                         .group_by(ContentSnapshot.item_id).all())
        к_снимку = []
        for номер, ext_id, опубл, _канал in молодые:
            возраст = (сейчас - опубл).total_seconds() / 3600
            шаг = next((ш for предел, ш in ГРАФИК_СНИМКОВ if возраст < предел), None)
            if шаг is None:
                continue
            был = последний.get(номер)
            if был is None or (сейчас - был).total_seconds() / 3600 >= шаг - 0.05:
                к_снимку.append(ext_id[3:])
        return известные, к_снимку
    finally:
        db.close()


async def _youtube(client, тема: dict, источник: dict, настройки: dict,
                   отчёт: dict) -> tuple[list[dict], str | None]:
    """Опрос реестра каналов. Реестр пуст — сначала поиск каналов
    (100 ед. на запрос). (записи, беда): квота кончилась посреди опроса —
    собранное сохраняется, источник жёлтый с причиной."""
    ключ = ключ_youtube()
    if not ключ:
        raise cc.ОтказИсточника(
            "нет ключа YouTube: секрет CONTENT_YOUTUBE_API_KEY не задан. Это ключ "
            "отдельного проекта владельца; прежний YOUTUBE_API_KEY модуль не берёт")
    нс = настройки["youtube"]
    база = источник["url"] or YT_ПО_УМОЛЧАНИЮ
    db = SessionLocal()
    try:
        израсходовано = cdb.квота_израсходовано(db)
    finally:
        db.close()
    квота = cc.Квота(int(нс.get("daily_cap", 9000)) - израсходовано, _списать_квоту)
    отчёт["квота_до"] = израсходовано
    записи: list[dict] = []
    беда = None
    try:
        каналы, всего = _каналы_темы(тема["id"])
        if всего == 0:
            метки = cc.шаблон_ключевых(тема["params"].get("channel_markers") or тема["keywords"])
            найдено = await cc.найти_каналы(
                client, база, ключ, квота, тема["params"].get("youtube_queries") or [], метки,
                int(нс.get("discover_min_subs", 10000)), int(нс.get("discover_max_channels", 60)))
            новых, _ = _сохранить_каналы(тема["id"], найдено)
            отчёт["поиск_каналов"] = новых
            каналы, всего = _каналы_темы(тема["id"])
            if всего == 0:
                raise cc.ОтказИсточника(
                    "реестр каналов пуст: поиск по запросам темы не нашёл ни одного канала "
                    f"с меткой темы и хотя бы {нс.get('discover_min_subs', 10000)} подписчиков")
        отчёт["каналов"] = len(каналы)
        без_плейлиста = [к["yt_id"] for к in каналы if not к["uploads"]]
        if без_плейлиста:
            св = await cc.каналы_сведения(client, база, ключ, квота, без_плейлиста)
            _сохранить_каналы(тема["id"], list(св.values()))
            каналы, всего = _каналы_темы(тема["id"])
        по_yt = {к["yt_id"]: к for к in каналы}
        ошибки, опрошены, ролик_канал = {}, [], {}
        for к in каналы:
            if not к["uploads"]:
                ошибки[к["id"]] = "у канала нет плейлиста загрузок"
                continue
            try:
                ids = await cc.загрузки_канала(client, база, ключ, квота, к["uploads"],
                                               int(нс.get("uploads_per_channel", 10)))
            except cc.КвотаИсчерпана:
                raise
            except cc.ОтказИсточника as e:
                ошибки[к["id"]] = str(e)[:500]
                continue
            опрошены.append(к["id"])
            for v in ids:
                ролик_канал[v] = к["yt_id"]
        _отметить_опрос(ошибки, опрошены)
        отчёт["каналов_с_ошибкой"] = len(ошибки)
        известные, к_снимку = _что_спросить(тема["id"], list(ролик_канал),
                                            float(нс.get("track_hours", 72)))
        спросить = [v for v in ролик_канал if v not in известные]
        отчёт["новых_роликов"] = len(спросить)
        спросить += [v for v in к_снимку if v not in спросить]
        ролики = await cc.ролики_сведения(client, база, ключ, квота, спросить)
        for р in ролики.values():
            к = по_yt.get(р["channel_yt_id"]) or {}
            язык = к.get("lang") or ("ru" if cc.есть_кириллица(р["title"]) else (р["lang"] or "en"))
            записи.append({
                "ext_id": "yt:" + р["yt_id"],
                "url": "https://www.youtube.com/watch?v=" + р["yt_id"],
                "title": р["title"] or "(без заголовка)",
                "text": " ".join(р["description"].split())[:cc.ТЕКСТ_ЗНАКОВ],
                "published_at": р["published_at"], "lang": язык, "platform": "youtube",
                "source_key": "yt:" + (р["channel_yt_id"] or "?"),
                "source_name": "YouTube · " + (к.get("title") or р["channel_title"] or "канал"),
                "channel_id": к.get("id"), "author": к.get("title") or р["channel_title"],
                "official": bool(к.get("official")),
                "metric": р["views"], "comments": р["comments"], "likes": р["likes"],
                "для_фильтра": р["title"] + " " + р["description"][:500],
            })
    except cc.КвотаИсчерпана as e:
        беда = str(e)
    finally:
        отчёт["единиц"] = квота.потрачено
    return записи, беда


def _рост_по_ряду(ряд: list, окно_ч: float) -> float | None:
    """Прирост счётчика в час по снимкам записи (ряд по возрастанию времени).

    Опора — САМЫЙ РАННИЙ снимок в окне `окно_ч` до последнего (но не ближе
    15 минут: разница двух почти одновременных снимков — шум). В окне
    снимков нет — последний снимок ДО окна, не дальше двух окон: у роликов
    старше суток снимки идут раз в 2–6 часов. Опоры нет — None."""
    if len(ряд) < 2:
        return None
    t_посл, _, м_посл = ряд[-1]
    опора = None
    for t, _, м in ряд[:-1]:
        часов = (t_посл - t).total_seconds() / 3600
        if 0.25 <= часов <= окно_ч:
            опора = (часов, м)
            break
    if опора is None:
        for t, _, м in reversed(ряд[:-1]):
            часов = (t_посл - t).total_seconds() / 3600
            if окно_ч < часов <= 2 * окно_ч:
                опора = (часов, м)
                break
    if опора is None or м_посл is None or опора[1] is None:
        return None
    return round(max(0, м_посл - опора[1]) / опора[0], 1)


def _пересчитать_рост(тема_id: str, настройки: dict) -> dict:
    """Рост в час и аномалия у записей со счётчиком.

    РОСТ — `_рост_по_ряду` по окну `окно_роста_часов` формулы оценки.
    Опоры нет, запись моложе двух суток — средний темп с публикации
    (просмотры / возраст). Старше срока слежения — 0: снимков больше нет,
    и замороженный рост раздувал бы старые сюжеты вечно.

    АНОМАЛИЯ — просмотры ролика в возрасте N часов, делённые на медиану
    просмотров ДРУГИХ роликов того же канала в том же возрасте. Их значение
    в возрасте N берётся линейной интерполяцией по их снимкам — только
    если снимки этот возраст ПОКРЫВАЮТ. Опор меньше `anomaly_min_base` —
    аномалии нет («мало данных»), а не выдумка по экстраполяции: у свежего
    реестра она наступает через сутки-двое."""
    нс = настройки["youtube"]
    следить = float(нс.get("track_hours", 72))
    хранить = int(нс.get("snapshot_keep_days", 14))
    мин_опор = int(нс.get("anomaly_min_base", 3))
    окно = float(настройки["score_formula"].get("окно_роста_часов", 6))
    сейчас = datetime.utcnow()
    db = SessionLocal()
    итог = {"с_ростом": 0, "с_аномалией": 0}
    try:
        ряды = defaultdict(list)
        for номер, когда, возраст, метрика in db.execute(text(
                "SELECT s.item_id, s.taken_at, s.age_h, s.metric FROM content_snapshots s "
                "JOIN content_items i ON i.id = s.item_id "
                "WHERE i.theme_id = :t AND s.taken_at >= :c AND s.metric IS NOT NULL "
                "ORDER BY s.item_id, s.taken_at"),
                {"t": тема_id, "c": сейчас - timedelta(days=хранить)}):
            if isinstance(когда, str):
                когда = datetime.fromisoformat(когда)
            ряды[номер].append((когда, возраст, метрика))
        записи = (db.query(ContentItem)
                  .filter(ContentItem.theme_id == тема_id, ContentItem.metric.isnot(None),
                          ContentItem.published_at >= сейчас - timedelta(days=хранить)).all())
        по_каналу = defaultdict(list)
        for и in записи:
            возраст = (сейчас - и.published_at).total_seconds() / 3600
            if возраст > следить:
                и.growth = 0.0
            else:
                рост = _рост_по_ряду(ряды.get(и.id, []), окно)
                if рост is None and возраст <= 48 and и.metric is not None:
                    рост = round(и.metric / max(возраст, 1.0), 1)
                и.growth = рост or 0.0
            if (и.growth or 0) > 0:
                итог["с_ростом"] += 1
            if и.channel_id:
                по_каналу[и.channel_id].append((и, возраст))
        for список in по_каналу.values():
            for и, возраст in список:
                if возраст > следить or и.metric is None:
                    continue
                опоры = []
                for другой, _ in список:
                    if другой is и:
                        continue
                    точки = [(в, м) for _, в, м in ряды.get(другой.id, []) if в is not None]
                    if not точки or not (точки[0][0] <= возраст <= точки[-1][0]):
                        continue
                    for (в1, м1), (в2, м2) in zip(точки, точки[1:] + [точки[-1]]):
                        if в1 <= возраст <= в2:
                            доля = 0.0 if в2 == в1 else (возраст - в1) / (в2 - в1)
                            опоры.append(м1 + (м2 - м1) * доля)
                            break
                и.anomaly_base = len(опоры)
                медиана = statistics.median(опоры) if len(опоры) >= мин_опор else 0
                и.anomaly = round(и.metric / медиана, 2) if медиана > 0 else None
                if и.anomaly is not None:
                    итог["с_аномалией"] += 1
        db.commit()
        return итог
    finally:
        db.close()


# ── ЦИКЛ ──────────────────────────────────────────────────────────────

def _загрузить() -> tuple[list[dict], list[dict], dict]:
    """Темы, включённые источники и настройки — одной короткой сессией."""
    db = SessionLocal()
    try:
        cdb.засеять(db)
        темы = [{"id": т.id, "title": т.title, "keywords": _из(т.keywords, []) or [],
                 "languages": _из(т.languages, []) or [], "params": _из(т.params, {}) or {}}
                for т in db.query(ContentTheme).filter(ContentTheme.active.is_(True))
                .order_by(ContentTheme.id).all()]
        источники = [{"id": и.id, "theme_id": и.theme_id, "kind": и.kind, "name": и.name,
                      "url": и.url, "params": _из(и.params, {}) or {}, "official": и.official,
                      "filter_keywords": и.filter_keywords}
                     for и in db.query(ContentSource).filter(ContentSource.enabled.is_(True))
                     .order_by(ContentSource.id).all()]
        настройки = {к: cdb.настройка(db, к) for к in ("youtube", "stories", "score_formula", "cycle")}
        return темы, источники, настройки
    finally:
        db.close()


async def _собрать_источник(client, тема: dict, и: dict, шаблон, настройки: dict) -> dict:
    t0 = time.monotonic()
    отчёт = {"id": и["id"], "имя": и["name"], "вид": и["kind"]}
    беда = None
    try:
        if и["kind"] == "rockstar":
            записи = await cc.с_потолком(cc.собрать_rockstar(client, и), ПОТОЛОК_ИСТОЧНИКА_СЕК, и["name"])
        elif и["kind"] == "rss":
            записи = await cc.с_потолком(cc.собрать_rss(client, и), ПОТОЛОК_ИСТОЧНИКА_СЕК, и["name"])
        elif и["kind"] == "reddit" and not cc.reddit_ключи():
            # ВЫКЛЮЧЕН, ЖДЁТ КЛЮЧ (BACKLOG №370): это не ошибка, и цикл
            # из-за него не «частично». В сеть не ходим вовсе (№369).
            _источник_итог(и["id"], "off", сек=0.0)
            отчёт.update(исход="off", получено=0, новых=0, сек=0.0)
            print(f"[content] источник «{и['name']}»: выключен, ждёт ключ", flush=True)
            return отчёт
        elif и["kind"] == "reddit":
            записи = await cc.с_потолком(cc.собрать_reddit(client, и), ПОТОЛОК_ИСТОЧНИКА_СЕК, и["name"])
        elif и["kind"] == "youtube":
            записи, беда = await cc.с_потолком(_youtube(client, тема, и, настройки, отчёт),
                                               ПОТОЛОК_YT_СЕК, и["name"])
        else:
            raise cc.ОтказИсточника(f"неизвестный вид источника «{и['kind']}» — сборщика нет")
        получено = len(записи)
        if и["filter_keywords"] and и["params"].get("strict"):
            # СМИ пишут обо всех играх: общие слова темы («Rockstar», «Jason»,
            # «Take-Two») пропустили бы новости не про GTA. Строгий список
            # темы и только заголовок с рубриками (BACKLOG №367). Списка нет —
            # записи не пропускаются вовсе: лучше пустая лента, чем чужие новости.
            строгий = cc.шаблон_ключевых(тема["params"].get("strict_keywords") or [])
            записи = [з for з in записи
                      if cc.совпало(з.get("для_строгого") or з["title"], строгий)]
        elif и["filter_keywords"]:
            записи = [з for з in записи if cc.совпало(з.get("для_фильтра") or з["title"], шаблон)]
        новых, по_теме = _записать(тема["id"], и, записи)
        сек = round(time.monotonic() - t0, 1)
        _источник_итог(и["id"], "quota" if беда else "ok", получено=получено, новых=новых,
                       сек=сек, ошибка=беда)
        отчёт.update(исход="quota" if беда else "ok", получено=получено, по_теме=по_теме,
                     новых=новых, сек=сек)
        if беда:
            отчёт["ошибка"] = беда
    except cc.КвотаИсчерпана as e:
        отчёт.update(исход="quota", ошибка=str(e), сек=round(time.monotonic() - t0, 1))
        _источник_итог(и["id"], "quota", сек=отчёт["сек"], ошибка=str(e))
    except cc.ОтказИсточника as e:
        отчёт.update(исход="error", ошибка=str(e), сек=round(time.monotonic() - t0, 1))
        _источник_итог(и["id"], "error", сек=отчёт["сек"], ошибка=str(e))
    except Exception as e:                       # ошибка В НАШЕМ коде: громко, но не валит соседей
        traceback.print_exc()
        текст = f"внутренняя ошибка сборщика: {type(e).__name__}: {e}"
        отчёт.update(исход="error", ошибка=текст, сек=round(time.monotonic() - t0, 1))
        _источник_итог(и["id"], "error", сек=отчёт["сек"], ошибка=текст)
    print(f"[content] источник «{и['name']}»: {отчёт.get('исход')}"
          f" получено={отчёт.get('получено')} новых={отчёт.get('новых')}"
          f" сек={отчёт.get('сек')}" + (f" — {отчёт['ошибка'][:200]}" if отчёт.get("ошибка") else ""),
          flush=True)
    return отчёт


def _уборка(настройки: dict) -> int:
    дней = int(настройки["youtube"].get("snapshot_keep_days", 14))
    db = SessionLocal()
    try:
        убрано = (db.query(ContentSnapshot)
                  .filter(ContentSnapshot.taken_at < datetime.utcnow() - timedelta(days=дней))
                  .delete(synchronize_session=False))
        db.commit()
        return убрано
    finally:
        db.close()


async def цикл(повод: str = "scheduler") -> dict:
    """Один цикл: все включённые источники всех тем, рост и аномалии,
    сюжеты, оценка, уборка старых снимков."""
    if занят():
        return _пропуск("cycle", повод)
    async with _замок():
        номер = _начать("cycle", повод)
        итог = {"источники": [], "сюжеты": {}, "рост": {}}
        состояние, заметка = "ok", None
        t0 = time.monotonic()
        try:
            темы, источники, настройки = _загрузить()
            async with cc.новый_клиент() as client:
                for тема in темы:
                    шаблон = cc.шаблон_ключевых(тема["keywords"])
                    for и in [и for и in источники if и["theme_id"] == тема["id"]]:
                        итог["источники"].append(
                            await _собрать_источник(client, тема, и, шаблон, настройки))
                    итог["рост"][тема["id"]] = _пересчитать_рост(тема["id"], настройки)
            for тема in темы:
                итог["сюжеты"][тема["id"]] = await _сюжеты(тема, настройки)
                _пересчитать_сюжеты(тема["id"], настройки)
            итог["снимков_убрано"] = _уборка(настройки)
            if (any(и.get("исход") not in ("ok", "off") for и in итог["источники"])
                    or any(с.get("беда") for с in итог["сюжеты"].values())):
                состояние = "partial"
        except Exception as e:
            traceback.print_exc()
            состояние, заметка = "error", f"{type(e).__name__}: {e}"
        итог["сек"] = round(time.monotonic() - t0, 1)
        _закончить(номер, состояние, итог, заметка)
        print(f"[content] цикл №{номер}: {состояние} за {итог['сек']} с", flush=True)
        return {"run_id": номер, "state": состояние, **итог}


async def поиск_каналов(повод: str = "admin") -> dict:
    """Поиск каналов по запросам темы заново (100 ед. на запрос). Новые —
    «кандидаты», у известных обновляются числа, статус владельца не трогается."""
    if занят():
        return _пропуск("discover", повод)
    async with _замок():
        номер = _начать("discover", повод)
        итог, состояние, заметка = {}, "ok", None
        try:
            темы, источники, настройки = _загрузить()
            ключ = ключ_youtube()
            if not ключ:
                raise cc.ОтказИсточника("нет ключа YouTube (CONTENT_YOUTUBE_API_KEY)")
            нс = настройки["youtube"]
            async with cc.новый_клиент() as client:
                for тема in темы:
                    запросы = тема["params"].get("youtube_queries") or []
                    if not запросы:
                        continue
                    yt = next((и for и in источники if и["theme_id"] == тема["id"]
                               and и["kind"] == "youtube"), None)
                    db = SessionLocal()
                    try:
                        осталось = int(нс.get("daily_cap", 9000)) - cdb.квота_израсходовано(db)
                    finally:
                        db.close()
                    квота = cc.Квота(осталось, _списать_квоту)
                    метки = cc.шаблон_ключевых(тема["params"].get("channel_markers") or тема["keywords"])
                    найдено = await cc.с_потолком(cc.найти_каналы(
                        client, (yt or {}).get("url") or YT_ПО_УМОЛЧАНИЮ, ключ, квота, запросы, метки,
                        int(нс.get("discover_min_subs", 10000)),
                        int(нс.get("discover_max_channels", 60))), ПОТОЛОК_YT_СЕК, "поиск каналов")
                    новых, обновлено = _сохранить_каналы(тема["id"], найдено)
                    итог[тема["id"]] = {"найдено": len(найдено), "новых": новых,
                                        "обновлено": обновлено, "единиц": квота.потрачено}
        except cc.ОтказИсточника as e:
            состояние, заметка = "error", str(e)
        except Exception as e:
            traceback.print_exc()
            состояние, заметка = "error", f"{type(e).__name__}: {e}"
        _закончить(номер, состояние, итог, заметка)
        return {"run_id": номер, "state": состояние, "note": заметка, **итог}


# ── МОДЕЛЬ ────────────────────────────────────────────────────────────

def _потрачено_сегодня(db) -> float:
    """Деньги модуля на модель за текущие сутки UTC — из учёта `model_usage`."""
    полночь = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    сумма = (db.query(func.sum(ModelUsage.cost))
             .filter(ModelUsage.tool.like("admin-content-%"), ModelUsage.created_at >= полночь)
             .scalar())
    return float(сумма or 0.0)


async def _спросить(клиент, инструмент: str, система: str, вопрос: str,
                    потолок: int) -> tuple[str | None, str | None]:
    """(текст ответа, беда). Беда — причина по-русски; текст — только удачный."""
    м = _main()
    if not м.OPENROUTER_API_KEY:
        return None, м._без_ключа("модель не настроена: API ключ OpenRouter не задан")
    try:
        resp = await м._модель_post(
            клиент, инструмент, None, м.OPENROUTER_URL,
            headers={"Authorization": f"Bearer {м.OPENROUTER_API_KEY}",
                     "HTTP-Referer": "https://energydess.ru",
                     "X-Title": "EnergyDess Content"},
            json={**м.ПОЛИТИКА_ЗАПРОСА, "model": м.MODEL,
                  "messages": [{"role": "system", "content": система},
                               {"role": "user", "content": вопрос}],
                  "temperature": 0, "max_tokens": потолок})
    except httpx.HTTPError as e:
        return None, f"сервис моделей не ответил ({type(e).__name__})"
    try:
        тело = resp.json()
    except ValueError:
        return None, f"сервис моделей ответил не JSON (HTTP {resp.status_code})"
    if not isinstance(тело, dict):
        return None, "сервис моделей ответил не объектом"
    текст, сбой = м._model_output(тело, инструмент, потолок)
    if сбой:
        return None, сбой
    return текст, None


def _json_ответа(текст: str):
    try:
        return _main()._extract_json(текст)
    except (ValueError, TypeError):
        return None


def _целое(x) -> int | None:
    """Целое, но не bool: `True` в Python — тоже int, и «n: true» номером не станет."""
    return x if type(x) is int else None


# ── СЮЖЕТЫ ────────────────────────────────────────────────────────────

ПРОМПТ_СЮЖЕТЫ = (
    "Ты помогаешь автору YouTube-канала вести радар новостей по теме «{тема}». "
    "Тебе дают НОВЫЕ записи (новости, ролики, посты) и список СУЩЕСТВУЮЩИХ сюжетов.\n"
    "Сюжет — одно событие или одна тема обсуждения («Вышел новый трейлер», «Слух "
    "о переносе даты выхода», «Утечка карты»), а не жанр и не вся игра целиком.\n"
    "Для каждой записи выбери ровно одно:\n"
    "- запись про уже существующий сюжет — поле story с его номером из списка;\n"
    "- запись про новое событие или тему — открой новый сюжет ключом-буквой "
    "(поле new) и опиши его в списке new; несколько записей про одно новое событие "
    "относи к ОДНОМУ новому сюжету;\n"
    "- запись не про событие (мем, шутка, вопрос без повода, личная история, "
    "прохождение, стрим, обзор без инфоповода) — noise: true.\n"
    "Флаги записи: leak: true — запись пересказывает или показывает утечку (слитые "
    "кадры, утёкший код, данные из закрытых источников); rumor: true — непроверенный "
    "слух или инсайд без подтверждения. Официальное объявление — ни то, ни другое.\n"
    "Ответ — только JSON без текста вокруг:\n"
    '{{"items":[{{"n":1,"story":3}},{{"n":2,"new":"A","leak":true}},{{"n":3,"noise":true}}],'
    '"new":[{{"key":"A","title":"…","summary":"…"}}]}}\n'
    "title нового сюжета — по-русски, до 80 знаков, называет событие; summary — одна "
    "фраза по-русски до 160 знаков. Номер сюжета — только из присланного списка. "
    "Опирайся только на присланный текст."
)


def _вопрос_сюжетов(сюжеты: list[dict], пачка: list[dict]) -> str:
    строки = ["Существующие сюжеты:"]
    if сюжеты:
        for i, с in enumerate(сюжеты, 1):
            строки.append(f"{i}. {с['title']}" + (f" — {с['summary']}" if с.get("summary") else ""))
    else:
        строки.append("(пока нет ни одного)")
    строки += ["", "Новые записи:"]
    for i, з in enumerate(пачка, 1):
        метка = з["source_name"] + (" · официально" if з["official"] else "") + f" · {з['lang'] or '?'}"
        отрывок = " ".join((з.get("text") or "").split())[:240]
        строки.append(f"{i}. [{метка}] {з['title']}" + (f" — {отрывок}" if отрывок else ""))
    return "\n".join(строки)


def _разобрать_сюжеты(текст: str, записей: int, сюжетов: int) -> tuple[dict | None, str | None]:
    """Решения по номерам. Номер записи вне пачки, номер сюжета вне списка,
    ключ нового без названия — решение отбрасывается, запись ждёт
    следующего цикла (не больше трёх попыток)."""
    д = _json_ответа(текст or "")
    if not isinstance(д, dict) or not isinstance(д.get("items"), list):
        return None, "ответ модели не JSON с полем items"
    новые = {}
    for н in д.get("new") or []:
        if (isinstance(н, dict) and isinstance(н.get("key"), str)
                and isinstance(н.get("title"), str) and н["title"].strip()):
            новые[н["key"].strip()] = {"title": " ".join(н["title"].split())[:120],
                                       "summary": " ".join(str(н.get("summary") or "").split())[:240]}
    решения = {}
    for э in д["items"]:
        if not isinstance(э, dict):
            continue
        n = _целое(э.get("n"))
        if n is None or not 1 <= n <= записей or n in решения:
            continue
        флаги = {"leak": э.get("leak") is True, "rumor": э.get("rumor") is True}
        номер = _целое(э.get("story"))
        ключ = э.get("new").strip() if isinstance(э.get("new"), str) else None
        if э.get("noise") is True and номер is None and ключ is None:
            решения[n] = ("шум", None, флаги)
        elif номер is not None and 1 <= номер <= сюжетов and ключ is None:
            решения[n] = ("сюжет", номер, флаги)
        elif ключ and ключ in новые and номер is None:
            решения[n] = ("новый", ключ, флаги)
    return {"решения": решения, "новые": новые}, None


def _применить_сюжеты(тема_id: str, пачка: list[dict], сюжеты: list[dict],
                      разбор: dict) -> tuple[list[dict], dict]:
    сейчас = datetime.utcnow()
    счёт = {"в_сюжеты": 0, "шум": 0, "новых_сюжетов": 0, "без_решения": 0}
    db = SessionLocal()
    try:
        заведены = {}
        for n, з in enumerate(пачка, 1):
            и = db.get(ContentItem, з["id"])
            if и is None:
                continue
            решение = разбор["решения"].get(n)
            if решение is None:
                и.classify_tries = (и.classify_tries or 0) + 1
                счёт["без_решения"] += 1
                continue
            вид, цель, флаги = решение
            if вид == "шум":
                и.noise = True
                счёт["шум"] += 1
            elif вид == "сюжет":
                и.story_id = сюжеты[цель - 1]["id"]
                счёт["в_сюжеты"] += 1
            else:
                if цель not in заведены:
                    новый = разбор["новые"][цель]
                    с = ContentStory(theme_id=тема_id, title=новый["title"],
                                     summary=новый["summary"] or None,
                                     created_at=сейчас, updated_at=сейчас)
                    db.add(с)
                    db.flush()
                    заведены[цель] = с
                    счёт["новых_сюжетов"] += 1
                и.story_id = заведены[цель].id
                счёт["в_сюжеты"] += 1
            и.leak = bool(флаги["leak"])
            и.rumor = bool(флаги["rumor"])
            и.classified_at = сейчас
        db.commit()
        return ([{"id": с.id, "title": с.title, "summary": с.summary} for с in заведены.values()],
                счёт)
    finally:
        db.close()


async def _сюжеты(тема: dict, настройки: dict) -> dict:
    нс = настройки["stories"]
    итог = {"разобрано": 0, "в_сюжеты": 0, "новых_сюжетов": 0, "шум": 0,
            "без_решения": 0, "вызовов": 0, "ждут": 0, "беда": None}
    сейчас = datetime.utcnow()
    когда = func.coalesce(ContentItem.published_at, ContentItem.first_seen_at)
    db = SessionLocal()
    try:
        потрачено = _потрачено_сегодня(db)
        предел = float(нс.get("daily_usd_cap", 1.0))
        выборка = (db.query(ContentItem)
                   .filter(ContentItem.theme_id == тема["id"], ContentItem.story_id.is_(None),
                           ContentItem.noise.is_(False), ContentItem.classify_tries < 3,
                           когда >= сейчас - timedelta(days=int(нс.get("window_days", 7)))))
        всего = выборка.count()
        if потрачено >= предел:
            итог["ждут"] = всего
            итог["беда"] = (f"предел денег на модель за сутки: потрачено {потрачено:.2f} $ "
                            f"из {предел:.2f} $ — разбор по сюжетам продолжится после полуночи UTC")
            return итог
        записи = [{"id": и.id, "title": и.title, "text": и.text, "source_name": и.source_name,
                   "lang": и.lang, "official": и.official}
                  for и in выборка.order_by(когда.desc())
                  .limit(int(нс.get("max_items_per_cycle", 100))).all()]
        итог["ждут"] = всего - len(записи)
        сюжеты = [{"id": с.id, "title": с.title, "summary": с.summary}
                  for с in (db.query(ContentStory)
                            .filter(ContentStory.theme_id == тема["id"],
                                    func.coalesce(ContentStory.last_item_at, ContentStory.created_at)
                                    >= сейчас - timedelta(days=int(нс.get("active_days", 10))))
                            .order_by(ContentStory.score.desc(), ContentStory.id.desc())
                            .limit(int(нс.get("max_stories_in_prompt", 80))).all())]
    finally:
        db.close()
    if not записи:
        return итог
    система = ПРОМПТ_СЮЖЕТЫ.format(тема=тема["title"])
    пачка_н = max(1, int(нс.get("batch", 25)))
    async with httpx.AsyncClient(timeout=httpx.Timeout(90.0, connect=15.0)) as клиент:
        for i in range(0, len(записи), пачка_н):
            пачка = записи[i:i + пачка_н]
            текст, беда = await _спросить(клиент, ИНСТРУМЕНТ_СЮЖЕТЫ, система,
                                          _вопрос_сюжетов(сюжеты, пачка), STORIES_MAX_TOKENS)
            итог["вызовов"] += 1
            if беда:
                # Сервис не ответил — записи не тронуты и попыток не теряют:
                # иначе суточная авария OpenRouter за полтора часа навсегда
                # выводила бы записи из разбора (три попытки)
                итог["беда"] = беда
                итог["без_решения"] += len(пачка)
                break
            разбор, отказ = _разобрать_сюжеты(текст, len(пачка), len(сюжеты))
            if отказ:
                итог["беда"] = отказ
                разбор = {"решения": {}, "новые": {}}
            заведены, счёт = _применить_сюжеты(тема["id"], пачка, сюжеты, разбор)
            сюжеты.extend(заведены)
            итог["разобрано"] += len(пачка)
            for к, v in счёт.items():
                итог[к] += v
    return итог


def оценка(формула: dict, рост: float, площадок: int, ru_роликов: int,
           опережение: bool = False, роликов: int = 0) -> tuple[int, dict]:
    """Оценка 0–100 по формуле ИЗ БАЗЫ (`score_formula`). Описание — там же.

    ОПЕРЕЖЕНИЕ (BACKLOG №367) — четвёртая часть: сюжет впервые появился
    не на YouTube. Полный вес при нуле роликов, дальше каждый ролик (любого
    языка) отнимает долю до `опережение_насыщение`. Веса «опережение»
    в базе нет — части нет: формула до правки считается как прежде."""
    в = формула.get("веса") or {}
    w_р, w_п, w_о = (float(в.get("рост", 45)), float(в.get("площадки", 30)),
                     float(в.get("окно_ru", 25)))
    нас_р = max(1.0, float(формула.get("рост_насыщение", 5000)))
    нас_п = max(1.0, float(формула.get("площадки_насыщение", 3)))
    нас_ru = max(1.0, float(формула.get("ru_насыщение", 3)))
    части = {
        "рост": w_р * min(1.0, math.log1p(max(0.0, рост)) / math.log1p(нас_р)),
        "площадки": w_п * min(1.0, площадок / нас_п),
        "окно_ru": w_о * (1.0 - min(1.0, ru_роликов / нас_ru)),
    }
    w_оп = float(в.get("опережение", 0))
    if w_оп > 0:
        нас_оп = max(1.0, float(формула.get("опережение_насыщение", 5)))
        части["опережение"] = (w_оп * (1.0 - min(1.0, роликов / нас_оп))) if опережение else 0.0
    return max(0, min(100, round(sum(части.values())))), {к: round(v, 1) for к, v in части.items()}


def _пересчитать_сюжеты(тема_id: str, настройки: dict) -> int:
    """Числа сюжета — из его записей: источники (разные `source_key`),
    площадки (разные сайты), ролики на русском, рост, флаги ИЛИ по записям."""
    формула = настройки["score_formula"]
    множитель = float(формула.get("реддит_множитель", 20))
    сейчас = datetime.utcnow()
    db = SessionLocal()
    try:
        сюжеты = (db.query(ContentStory)
                  .filter(ContentStory.theme_id == тема_id,
                          func.coalesce(ContentStory.last_item_at, ContentStory.created_at)
                          >= сейчас - timedelta(days=30)).all())
        if not сюжеты:
            return 0
        по_сюжету = defaultdict(list)
        for и in (db.query(ContentItem)
                  .filter(ContentItem.story_id.in_([с.id for с in сюжеты])).all()):
            по_сюжету[и.story_id].append(и)
        for с in сюжеты:
            записи = по_сюжету.get(с.id, [])
            if not записи:
                continue
            моменты = [и.published_at or и.first_seen_at for и in записи]
            с.items = len(записи)
            с.sources = len({и.source_key for и in записи})
            с.platforms = len({и.platform for и in записи})
            ролики = [и for и in записи if и.platform == "youtube"]
            с.ru_videos = sum(1 for и in ролики if и.lang == "ru")
            с.en_videos = len(ролики) - с.ru_videos
            с.first_seen_at = min(моменты)
            # ПЕРВЫЙ ИСТОЧНИК и ОПЕРЕЖЕНИЕ (BACKLOG №367): самый ранний по времени
            # публикации. Опережение — первым пришёл не YouTube, а до первого
            # ролика (либо роликов нет вовсе) — окно «успеть первым».
            первый = min(записи, key=lambda и: и.published_at or и.first_seen_at)
            с.first_source, с.first_url = первый.source_name, первый.url
            с.first_platform = первый.platform
            первый_ролик = min((и.published_at or и.first_seen_at for и in ролики), default=None)
            с.lead = (первый.platform != "youtube"
                      and (первый_ролик is None
                           or (первый.published_at or первый.first_seen_at) < первый_ролик))
            с.last_item_at = max(моменты)
            с.growth = round(sum((и.growth or 0.0) * (множитель if и.platform == "reddit" else 1.0)
                                 for и in записи), 1)
            с.official = any(и.official for и in записи)
            с.leak = any(и.leak for и in записи)
            с.rumor = any(и.rumor for и in записи)
            с.score, части = оценка(формула, с.growth, с.platforms, с.ru_videos,
                                    с.lead, len(ролики))
            с.score_parts = cdb.в_json(части)
            с.updated_at = сейчас
        db.commit()
        return len(сюжеты)
    finally:
        db.close()


# ── АРХЕОЛОГИЯ ФОРМАТОВ ───────────────────────────────────────────────

ПРОМПТ_ФОРМАТЫ = (
    "Ты раскладываешь популярные ролики YouTube про GTA 5 времён её запуска "
    "(2013–2014) по ФОРМАТАМ. Формат — тип ролика по подаче и приёму, а не тема игры.\n"
    "Для каждого ролика выбери номер формата из списка (поле format). Если ни один "
    "не подходит по смыслу — предложи новый формат ключом-буквой (поле new) "
    "и опиши его в списке new: короткое название по-русски до 60 знаков; похожие "
    "ролики относи к одному новому формату.\n"
    "Формат из списка бери, только если его название прямо называет приём "
    "ролика; похожая тема — не повод. Нарезка смешных моментов, прохождение, "
    "стрим, обзор, для которых в списке нет своего формата, — новый формат.\n"
    "Ролик не про GTA (другая игра, рэп, влог) не относи никуда: ни format, ни new.\n"
    "flags — флаги монетизации, только из трёх: «18+» (эротика, откровенные сцены, "
    "мат в заголовке), «стриптиз-клубы» (стриптиз, клубы, проститутки в игре), "
    "«шок-насилие» (жестокие убийства, кровь, пытки, шок в заголовке). Нет признаков — [].\n"
    "why — короткая причина выбора по-русски, до 60 знаков.\n"
    "Ответ — только JSON без текста вокруг:\n"
    '{"videos":[{"n":1,"format":3,"flags":[],"why":"…"},'
    '{"n":2,"new":"A","flags":["18+"],"why":"…"}],"new":[{"key":"A","title":"…"}]}\n'
    "Номер формата — только из присланного списка. Опирайся только на заголовок "
    "и описание."
)


def _вопрос_форматов(форматы: list[dict], пачка: list[dict]) -> str:
    строки = ["Форматы:"] + [f"{i}. {ф['title']}" for i, ф in enumerate(форматы, 1)]
    строки += ["", "Ролики:"]
    for i, р in enumerate(пачка, 1):
        описание = " ".join((р.get("description") or "").split())[:150]
        строки.append(f"{i}. [{р.get('channel_title') or 'канал'} · {р.get('channel_lang') or '?'}] "
                      f"{р['title']}" + (f" — {описание}" if описание else "")
                      + f" (просмотров {р.get('views') or 0})")
    return "\n".join(строки)


def _разобрать_форматы(текст: str, роликов: int, форматов: int) -> tuple[dict | None, str | None]:
    д = _json_ответа(текст or "")
    if not isinstance(д, dict) or not isinstance(д.get("videos"), list):
        return None, "ответ модели не JSON с полем videos"
    новые = {}
    for н in д.get("new") or []:
        if (isinstance(н, dict) and isinstance(н.get("key"), str)
                and isinstance(н.get("title"), str) and н["title"].strip()):
            новые[н["key"].strip()] = " ".join(н["title"].split())[:80]
    решения = {}
    for э in д["videos"]:
        if not isinstance(э, dict):
            continue
        n = _целое(э.get("n"))
        if n is None or not 1 <= n <= роликов or n in решения:
            continue
        флаги = sorted({ф for ф in (э.get("flags") or []) if ф in ФЛАГИ_МОНЕТИЗАЦИИ},
                       key=ФЛАГИ_МОНЕТИЗАЦИИ.index)
        почему = " ".join(str(э.get("why") or "").split())[:100]
        номер = _целое(э.get("format"))
        ключ = э.get("new").strip() if isinstance(э.get("new"), str) else None
        if номер is not None and 1 <= номер <= форматов and ключ is None:
            решения[n] = ("формат", номер, флаги, почему)
        elif ключ and ключ in новые and номер is None:
            решения[n] = ("новый", ключ, флаги, почему)
    return {"решения": решения, "новые": новые}, None


def _пересобрать_археологию(тема_id: str, ролики: list[dict]) -> dict:
    """Археология — СНИМОК ПРОШЛОГО, и каждый прогон пересобирает его
    целиком: хиты, которых нет в новой выдаче, уходят, раскладка по форматам
    считается заново, форматы, предложенные моделью, заводятся заново.
    Иначе правка отбора оставила бы в таблице хиты про другие игры и форматы
    под них навсегда. Стартовые форматы владельца не трогаются.

    Зовётся только ПОСЛЕ удачного сбора с непустой выдачей: сбой YouTube
    либо пустой ответ прежнюю таблицу не стирают."""
    новые = {р["yt_id"] for р in ролики if р.get("yt_id")}
    db = SessionLocal()
    try:
        убрано = 0
        for в in db.query(ContentArchVideo).filter(ContentArchVideo.theme_id == тема_id).all():
            if в.yt_id not in новые:
                db.delete(в)
                убрано += 1
                continue
            в.format_id = в.format_reason = в.flags = в.classified_at = None
            в.limited_ads = False
            в.classify_tries = 0
        форматов = (db.query(ContentFormat)
                    .filter(ContentFormat.theme_id == тема_id, ContentFormat.origin == "model")
                    .delete(synchronize_session=False))
        db.commit()
        return {"убрано_хитов": убрано, "убрано_форматов_модели": форматов}
    finally:
        db.close()


def _сохранить_хиты(тема_id: str, ролики: list[dict]) -> tuple[int, int]:
    сейчас = datetime.utcnow()
    db = SessionLocal()
    try:
        новых = обновлено = 0
        for р in ролики:
            if not р.get("yt_id") or not р.get("title"):
                continue
            в = (db.query(ContentArchVideo)
                 .filter(ContentArchVideo.theme_id == тема_id, ContentArchVideo.yt_id == р["yt_id"])
                 .first())
            if в is None:
                в = ContentArchVideo(theme_id=тема_id, yt_id=р["yt_id"], title=р["title"])
                db.add(в)
                новых += 1
            else:
                обновлено += 1
            в.title = р["title"]
            в.description = " ".join((р.get("description") or "").split())[:400] or None
            в.channel_yt_id = р.get("channel_yt_id")
            в.channel_title = р.get("channel_title")
            в.channel_lang = р.get("channel_lang") or в.channel_lang
            в.published_at = р.get("published_at")
            в.views, в.likes, в.comments = р.get("views"), р.get("likes"), р.get("comments")
            в.shot = р.get("shot")
            в.channel_median = р.get("channel_median")
            в.median_base = р.get("median_base")
            в.fetched_at = сейчас
        db.commit()
        return новых, обновлено
    finally:
        db.close()


async def _форматы(тема_id: str) -> dict:
    итог = {"разобрано": 0, "с_форматом": 0, "новых_форматов": 0, "вызовов": 0,
            "ограниченная_реклама": 0, "беда": None}
    db = SessionLocal()
    try:
        ролики = [{"id": в.id, "title": в.title, "channel_title": в.channel_title,
                   "channel_lang": в.channel_lang, "views": в.views,
                   "description": в.description or ""}
                  for в in (db.query(ContentArchVideo)
                            .filter(ContentArchVideo.theme_id == тема_id,
                                    ContentArchVideo.format_id.is_(None),
                                    ContentArchVideo.classify_tries < 3)
                            .order_by(ContentArchVideo.views.desc()).all())]
        форматы = [{"id": ф.id, "title": ф.title}
                   for ф in (db.query(ContentFormat).filter(ContentFormat.theme_id == тема_id)
                             .order_by(ContentFormat.sort, ContentFormat.id).all())]
    finally:
        db.close()
    if not ролики:
        return итог
    async with httpx.AsyncClient(timeout=httpx.Timeout(90.0, connect=15.0)) as клиент:
        for i in range(0, len(ролики), ФОРМАТОВ_ПАЧКА):
            пачка = ролики[i:i + ФОРМАТОВ_ПАЧКА]
            текст, беда = await _спросить(клиент, ИНСТРУМЕНТ_ФОРМАТЫ, ПРОМПТ_ФОРМАТЫ,
                                          _вопрос_форматов(форматы, пачка), FORMATS_MAX_TOKENS)
            итог["вызовов"] += 1
            if беда:
                # Сервис не ответил — ролики попыток не теряют (как у сюжетов)
                итог["беда"] = беда
                break
            разбор, отказ = _разобрать_форматы(текст, len(пачка), len(форматы))
            if отказ:
                итог["беда"] = отказ
                разбор = {"решения": {}, "новые": {}}
            сейчас = datetime.utcnow()
            db = SessionLocal()
            try:
                заведены = {}
                for n, р in enumerate(пачка, 1):
                    в = db.get(ContentArchVideo, р["id"])
                    if в is None:
                        continue
                    решение = разбор["решения"].get(n)
                    if решение is None:
                        в.classify_tries = (в.classify_tries or 0) + 1
                        continue
                    вид, цель, флаги, почему = решение
                    if вид == "формат":
                        в.format_id = форматы[цель - 1]["id"]
                    else:
                        if цель not in заведены:
                            название = разбор["новые"][цель]
                            ф = (db.query(ContentFormat)
                                 .filter(ContentFormat.theme_id == тема_id,
                                         ContentFormat.title == название).first())
                            if ф is None:
                                ф = ContentFormat(theme_id=тема_id, title=название,
                                                  origin="model", sort=1000 + len(форматы))
                                db.add(ф)
                                db.flush()
                                итог["новых_форматов"] += 1
                            заведены[цель] = ф
                        в.format_id = заведены[цель].id
                    в.flags = cdb.в_json(флаги)
                    в.limited_ads = bool(флаги)
                    в.format_reason = почему or None
                    в.classified_at = сейчас
                    итог["с_форматом"] += 1
                    итог["ограниченная_реклама"] += 1 if флаги else 0
                db.commit()
                форматы += [{"id": ф.id, "title": ф.title} for ф in заведены.values()
                            if all(ф.id != x["id"] for x in форматы)]
            finally:
                db.close()
            итог["разобрано"] += len(пачка)
    return итог


async def археология(повод: str = "admin") -> dict:
    """Хиты 17.09.2013–31.12.2014 по ВЫСТРЕЛУ (версия 5, BACKLOG №368) плюс
    раскладка по форматам. Цена прогона — `цена_археологии`, резерв циклам
    сбора до сброса суток Google прогон не трогает."""
    if занят():
        return _пропуск("archaeology", повод)
    async with _замок():
        номер = _начать("archaeology", повод)
        итог, состояние, заметка = {}, "ok", None
        try:
            темы, источники, настройки = _загрузить()
            ключ = ключ_youtube()
            for тема in темы:
                п = тема["params"].get("archaeology")
                if not п:
                    continue
                if not ключ:
                    raise cc.ОтказИсточника("нет ключа YouTube (CONTENT_YOUTUBE_API_KEY)")
                yt = next((и for и in источники if и["theme_id"] == тема["id"]
                           and и["kind"] == "youtube"), None)
                db = SessionLocal()
                try:
                    осталось = (int(настройки["youtube"].get("daily_cap", 9000))
                                - cdb.квота_израсходовано(db) - _резерв_циклам(db))
                finally:
                    db.close()
                квота = cc.Квота(осталось, _списать_квоту)
                # МАРКЕРЫ ТЕМЫ: свои у археологии (`markers` в базе), иначе
                # маркеры каналов плюс ключевые слова темы. Одних маркеров
                # каналов мало, и это замер: «GTA» по границе слова не ловит
                # «GTA5» и «GTAV», а ключевое «GTA 5» ловит оба написания.
                метки = cc.шаблон_ключевых(
                    п.get("markers") or ((тема["params"].get("channel_markers") or [])
                                         + (тема["keywords"] or [])))
                async with cc.новый_клиент() as client:
                    try:
                        хиты = await cc.с_потолком(cc.хиты_выстрела(
                            client, (yt or {}).get("url") or YT_ПО_УМОЛЧАНИЮ, ключ, квота, п,
                            метки), ПОТОЛОК_АРХЕОЛОГИИ_СЕК, "археология")
                    finally:
                        итог.setdefault(тема["id"], {})["единиц"] = квота.потрачено
                итог[тема["id"]].update({"каналы_en": len(хиты["каналы_en"]),
                                         "каналы_ru": len(хиты["каналы_ru"]),
                                         "хитов_поиска": хиты["хитов_поиска"],
                                         "роликов": len(хиты["ролики"]),
                                         "другой_язык": хиты.get("другой_язык") or [],
                                         "прогноз_единиц": cc.цена_выстрела(п),
                                         "страниц": хиты.get("страниц"),
                                         "каналы": хиты.get("каналы") or [],
                                         "пропущено": хиты.get("пропущено") or []})
                if not хиты["ролики"]:
                    # Пустая выдача — не повод стирать собранное прежде
                    состояние = "partial"
                    заметка = "по теме не нашлось ни одного хита — прежняя таблица не тронута"
                    continue
                итог[тема["id"]].update(_пересобрать_археологию(тема["id"], хиты["ролики"]))
                новых, обновлено = _сохранить_хиты(тема["id"], хиты["ролики"])
                итог[тема["id"]].update({"новых": новых, "обновлено": обновлено})
                форм = await _форматы(тема["id"])
                итог[тема["id"]]["форматы"] = форм
                if форм.get("беда"):
                    состояние = "partial"
                    заметка = "форматы: " + форм["беда"]
        except cc.ОтказИсточника as e:
            состояние, заметка = "error", str(e)
        except Exception as e:
            traceback.print_exc()
            состояние, заметка = "error", f"{type(e).__name__}: {e}"
        итог["версия"] = АРХЕОЛОГИЯ_ВЕРСИЯ
        _закончить(номер, состояние, итог, заметка)
        print(f"[content] археология №{номер}: {состояние}" + (f" — {заметка}" if заметка else ""),
              flush=True)
        return {"run_id": номер, "state": состояние, "note": заметка, **итог}


# ── ЗАПУСК ИЗ ЭКРАНА И ПЛАНИРОВЩИК ────────────────────────────────────

ВИДЫ = {"cycle": цикл, "discover": поиск_каналов, "archaeology": археология}


def запустить(вид: str, повод: str = "admin") -> dict:
    """Прогон фоном. Идёт другой — отказ словами, а не молчаливая очередь."""
    if вид not in ВИДЫ:
        return {"ok": False, "error": "неизвестный вид прогона"}
    if занят():
        return {"ok": False, "busy": True,
                "error": "Уже идёт прогон — дождитесь его конца, повтор его не ускорит."}
    _ЗАДАЧИ[вид] = asyncio.create_task(ВИДЫ[вид](повод))
    return {"ok": True}


def _до_следующего(минут: float) -> float:
    db = SessionLocal()
    try:
        последний = (db.query(ContentRun).filter(ContentRun.kind == "cycle",
                                                 ContentRun.state != "skipped")
                     .order_by(ContentRun.started_at.desc()).first())
    finally:
        db.close()
    if последний is None:
        return 0.0
    return max(0.0, (последний.started_at + timedelta(minutes=минут)
                     - datetime.utcnow()).total_seconds())


def _резерв_циклам(db) -> int:
    """Единиц YouTube, которые нужны циклам сбора до сброса суток Google.
    Замер на проде 2026-09-29: к 15:00 UTC израсходовано 6465 из 9000,
    прогон археологии в 16:00 съел бы ~1800, и сбор YouTube встал бы на всю
    ночь. Этот резерв археология не трогает НИ при автозапуске, НИ при ручном
    нажатии: ручной прогон упрётся в потолок `Квота`, а не съест циклы."""
    ют = cdb.настройка(db, "youtube")
    до_сброса = (cdb.сброс_квоты_utc() - datetime.utcnow()).total_seconds()
    циклов = math.ceil(max(0.0, до_сброса)
                       / (60 * float(cdb.настройка(db, "cycle").get("minutes", 30))))
    return циклов * int(ют.get("cycle_units", ЦЕНА_ЦИКЛА_ОЦЕНКА))


def цена_археологии(db) -> int:
    """Прогноз единиц прогона ДО запуска — по параметрам тем в базе
    (`content_collect.цена_выстрела`). Нет параметров — прежняя оценка."""
    цены = [cc.цена_выстрела((_из(т.params, {}) or {}).get("archaeology") or {})
            for т in db.query(ContentTheme).filter(ContentTheme.active.is_(True)).all()
            if ((_из(т.params, {}) or {}).get("archaeology"))]
    return sum(цены) or ЦЕНА_АРХЕОЛОГИИ_ОЦЕНКА


def _археология_нужна() -> bool:
    """Автозапуск один раз НА ВЕРСИЮ: ключ есть, удачного прогона текущей
    версии правил ещё не было (`АРХЕОЛОГИЯ_ВЕРСИЯ` в итоге прогона),
    квоты хватает на весь прогон (иначе ждём следующего цикла). Прогон
    прежней версии пересобирается сам один раз после выкатки — иначе
    правка отбора не дошла бы до уже собранной таблицы без нажатия."""
    if not ключ_youtube():
        return False
    db = SessionLocal()
    try:
        была = (db.query(ContentRun).filter(ContentRun.kind == "archaeology",
                                            ContentRun.state.in_(("ok", "partial")))
                .order_by(ContentRun.id.desc()).first())
        if была is not None:
            версия = int((cdb.из_json(была.summary, {}) or {}).get("версия", 1))
            if версия >= АРХЕОЛОГИЯ_ВЕРСИЯ:
                return False
        # РЕЗЕРВ ЦИКЛАМ ДО СБРОСА СУТОК GOOGLE: прогон ждёт суток, где после
        # него циклам ещё хватит квоты (`_резерв_циклам`). Цена — ПРОГНОЗ по
        # параметрам прогона, а не константа: версия 5 стоит иначе, чем 4.
        предел = int(cdb.настройка(db, "youtube").get("daily_cap", 9000))
        return предел - cdb.квота_израсходовано(db) - _резерв_циклам(db) >= цена_археологии(db)
    finally:
        db.close()


async def _планировщик() -> None:
    try:
        db = SessionLocal()
        try:
            cdb.засеять(db)
            нц = cdb.настройка(db, "cycle")
        finally:
            db.close()
        await asyncio.sleep(float(нц.get("first_delay_sec", 120)))
    except asyncio.CancelledError:
        raise
    except Exception:
        traceback.print_exc()
    while True:
        try:
            db = SessionLocal()
            try:
                минут = float(cdb.настройка(db, "cycle").get("minutes", 30))
            finally:
                db.close()
            ждать = _до_следующего(минут)
            if ждать > 0:
                await _идеи_по_расписанию()
                await asyncio.sleep(min(ждать, 300))
                continue
            await цикл("scheduler")
            if _археология_нужна():
                await археология("scheduler")
            await _идеи_по_расписанию()
        except asyncio.CancelledError:
            raise
        except Exception:
            traceback.print_exc()
            await asyncio.sleep(60)


async def _идеи_по_расписанию() -> None:
    """Идеи роликов (BACKLOG №370): утром в `generate_at_msk` и когда сюжет
    пересёк порог «горячо». Импорт в момент вызова: `content_ideas`
    сам импортирует этот модуль."""
    import content_ideas as ci
    повод = ci.проверить_расписание()
    if повод and not ci.идёт():
        await ci.сгенерировать(повод)


def старт() -> None:
    """Зовётся из обработчика старта приложения (цикл событий уже идёт).
    Обработчик FastAPI переносит в приложение дважды (список старта
    и склейка lifespan) — второй вызов ничего не делает."""
    global _СТАРТОВАЛ
    задача = _ЗАДАЧИ.get("планировщик")
    if задача is not None and not задача.done() and задача.get_loop() is asyncio.get_running_loop():
        return
    if _СТАРТОВАЛ and not планировщик_включён():
        return
    _СТАРТОВАЛ = True
    if not планировщик_включён():
        print("[content] планировщик выключен (вне Fly либо CONTENT_SCHEDULER=0) — "
              "сбор только по кнопке", flush=True)
        return
    _ЗАДАЧИ["планировщик"] = asyncio.create_task(_планировщик())
    print("[content] планировщик запущен", flush=True)
