"""ТАБЛИЦЫ МОДУЛЯ «КОНТЕНТ» (BACKLOG №365, 366).

Модуль — инструмент владельца для YouTube-канала: сайт сам собирает
новости и обсуждения по теме, склеивает их в сюжеты и держит базу
проверенных форматов роликов. Только администратору.

ТАБЛИЦЫ НА ОБЩЕМ `Base`, А НЕ НА СВОЁМ, и это не удобство. Проверка
политики конфиденциальности (`check_privacy.py`), опись стенда
(`check_stand_state.py`) и сверка каскада удаления берут схему
у `database.Base.metadata`: на своём `Base` таблицы модуля выпали бы
из-под всех трёх МОЛЧА. Подключает этот файл одна строка в конце
`database.py`, и `init_db()` заводит таблицы вместе с остальными.

НИ ОДНА ТАБЛИЦА НЕ ПРИВЯЗАНА К ЧЕЛОВЕКУ: темы, источники, публичные
записи чужих площадок, снимки счётчиков, каналы YouTube, сюжеты,
форматы и настройки — данные проекта. Поэтому в каскаде удаления их нет,
а в `PRIVACY_NOT_PERSONAL` они стоят с причиной у каждой. Автора поста
Reddit модуль не хранит вовсе; у YouTube хранится имя КАНАЛА — публичного
автора, а не читателя.

СПИСКИ И ЧИСЛА — В БАЗЕ, А НЕ В КОДЕ (требование письма): ключевые
слова темы, источники, форматы, формула оценки, потолок квоты. Семя
(`content_seed.json`) наполняет ПУСТЫЕ таблицы и больше ни на что
не влияет — тот же приём, что `enshrouded_seed.json`.
"""
import io
import json
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import (Boolean, Column, DateTime, Float, Integer, String, Text,
                        UniqueConstraint)

from database import Base

СЕМЯ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "content_seed.json")

# Сутки квоты YouTube Data API — ТИХООКЕАНСКИЕ: счётчик Google обнуляется
# в полночь по Лос-Анджелесу, а не по UTC и не по Москве. Посчитай мы
# сутки иначе, «потолок на сегодня» расходился бы с настоящим до девяти
# часов в день, и отказ квоты пришёл бы от Google, а не от нас.
ПОЯС_КВОТЫ = ZoneInfo("America/Los_Angeles")

СТАТУСЫ_КАНАЛА = ("candidate", "keep", "removed")


class ContentTheme(Base):
    """ТЕМА — НАСТРОЙКА, А НЕ КОД. Вторая тема («нейросети») заводится
    строкой: свои ключевые слова, языки, источники и форматы."""
    __tablename__ = "content_themes"
    id = Column(String, primary_key=True)                # gta
    title = Column(String, nullable=False)
    keywords = Column(Text, nullable=False)              # JSON-список
    languages = Column(Text, nullable=False)             # JSON-список
    params = Column(Text, nullable=True)                 # JSON: запросы поиска каналов, археология
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ContentSource(Base):
    """ИСТОЧНИК И ЕГО СОСТОЯНИЕ. Немой отказ запрещён: у каждого источника
    время последнего УДАЧНОГО запуска и текст ПОСЛЕДНЕЙ ошибки, и страница
    красит источник по исходу последнего запуска, а не по наличию записей."""
    __tablename__ = "content_sources"
    id = Column(Integer, primary_key=True)
    theme_id = Column(String, nullable=False, index=True)
    kind = Column(String, nullable=False)                # rockstar | rss | youtube | reddit
    name = Column(String, nullable=False)
    url = Column(String, nullable=True)
    params = Column(Text, nullable=True)                 # JSON
    official = Column(Boolean, nullable=False, default=False)
    filter_keywords = Column(Boolean, nullable=False, default=True)
    enabled = Column(Boolean, nullable=False, default=True)
    note = Column(Text, nullable=True)                   # постоянная пометка (Reddit: почему остановлен)
    last_state = Column(String, nullable=True)           # ok | error | quota
    last_run_at = Column(DateTime, nullable=True)        # UTC
    last_ok_at = Column(DateTime, nullable=True)         # UTC
    last_error = Column(Text, nullable=True)
    last_error_at = Column(DateTime, nullable=True)      # UTC
    last_seen = Column(Integer, nullable=True)           # записей получено за последний запуск
    last_new = Column(Integer, nullable=True)            # из них новых
    last_sec = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ContentChannel(Base):
    """КАНАЛ YOUTUBE В РЕЕСТРЕ. `candidate` — найден поиском, прорежает
    владелец; `keep` — оставлен; `removed` — убран и НЕ ОПРАШИВАЕТСЯ."""
    __tablename__ = "content_channels"
    __table_args__ = (UniqueConstraint("theme_id", "yt_id"),)
    id = Column(Integer, primary_key=True)
    theme_id = Column(String, nullable=False, index=True)
    yt_id = Column(String, nullable=False)               # UC…
    title = Column(String, nullable=False)
    handle = Column(String, nullable=True)
    lang = Column(String, nullable=True)                 # ru | en
    country = Column(String, nullable=True)
    subscribers = Column(Integer, nullable=True)
    videos = Column(Integer, nullable=True)
    views = Column(Integer, nullable=True)
    created_yt = Column(DateTime, nullable=True)         # дата создания канала
    uploads = Column(String, nullable=True)              # плейлист загрузок
    status = Column(String, nullable=False, default="candidate")
    official = Column(Boolean, nullable=False, default=False)
    found_by = Column(String, nullable=True)
    status_at = Column(DateTime, nullable=True)
    last_polled_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ContentItem(Base):
    """ЗАПИСЬ ЧУЖОЙ ПЛОЩАДКИ: новость, ролик, пост. Дубль невозможен
    по построению — `ext_id` (площадка плюс её номер) уникален в теме."""
    __tablename__ = "content_items"
    __table_args__ = (UniqueConstraint("theme_id", "ext_id"),)
    id = Column(Integer, primary_key=True)
    theme_id = Column(String, nullable=False, index=True)
    ext_id = Column(String, nullable=False)
    source_id = Column(Integer, nullable=False, index=True)
    source_key = Column(String, nullable=False)          # rockstar:1 | rss:2 | yt:UC… | reddit:GTA6
    source_name = Column(String, nullable=False)         # подпись источника для экрана
    platform = Column(String, nullable=False)            # rockstar | playstation | youtube | reddit
    channel_id = Column(Integer, nullable=True, index=True)
    url = Column(String, nullable=False)
    title = Column(String, nullable=False)
    text = Column(Text, nullable=True)                   # отрывок, до 1000 знаков
    author = Column(String, nullable=True)               # только имя КАНАЛА YouTube
    flair = Column(String, nullable=True)
    lang = Column(String, nullable=True)
    official = Column(Boolean, nullable=False, default=False)
    published_at = Column(DateTime, nullable=True, index=True)   # UTC
    first_seen_at = Column(DateTime, nullable=False)
    last_seen_at = Column(DateTime, nullable=False)
    metric = Column(Integer, nullable=True)              # просмотры либо счёт
    comments = Column(Integer, nullable=True)
    likes = Column(Integer, nullable=True)
    growth = Column(Float, nullable=True)                # прирост метрики в час
    anomaly = Column(Float, nullable=True)               # просмотры / медиана канала в том же возрасте
    anomaly_base = Column(Integer, nullable=True)        # на скольких роликах медиана
    story_id = Column(Integer, nullable=True, index=True)
    noise = Column(Boolean, nullable=False, default=False)
    leak = Column(Boolean, nullable=False, default=False)
    rumor = Column(Boolean, nullable=False, default=False)
    classify_tries = Column(Integer, nullable=False, default=0)
    classified_at = Column(DateTime, nullable=True)


class ContentSnapshot(Base):
    """СНИМОК СЧЁТЧИКА при каждом опросе — для скорости роста и аномалии."""
    __tablename__ = "content_snapshots"
    id = Column(Integer, primary_key=True)
    item_id = Column(Integer, nullable=False, index=True)
    taken_at = Column(DateTime, nullable=False, index=True)
    age_h = Column(Float, nullable=True)                 # возраст записи в часах
    metric = Column(Integer, nullable=True)
    comments = Column(Integer, nullable=True)
    likes = Column(Integer, nullable=True)


class ContentStory(Base):
    """СЮЖЕТ — СКЛЕЙКА ЗАПИСЕЙ ПРО ОДНО СОБЫТИЕ. Числа (источники,
    площадки, рост, оценка) пересчитываются из записей каждым циклом;
    флаги — ИЛИ по записям."""
    __tablename__ = "content_stories"
    id = Column(Integer, primary_key=True)
    theme_id = Column(String, nullable=False, index=True)
    title = Column(String, nullable=False)
    summary = Column(Text, nullable=True)
    first_seen_at = Column(DateTime, nullable=True)
    last_item_at = Column(DateTime, nullable=True)
    items = Column(Integer, nullable=False, default=0)
    sources = Column(Integer, nullable=False, default=0)
    platforms = Column(Integer, nullable=False, default=0)
    ru_videos = Column(Integer, nullable=False, default=0)
    growth = Column(Float, nullable=False, default=0.0)
    score = Column(Integer, nullable=False, default=0)
    score_parts = Column(Text, nullable=True)            # JSON: части оценки
    official = Column(Boolean, nullable=False, default=False)
    rumor = Column(Boolean, nullable=False, default=False)
    leak = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=True)


class ContentFormat(Base):
    """ФОРМАТ РОЛИКА: стартовый список владельца либо предложенный моделью."""
    __tablename__ = "content_formats"
    __table_args__ = (UniqueConstraint("theme_id", "title"),)
    id = Column(Integer, primary_key=True)
    theme_id = Column(String, nullable=False, index=True)
    title = Column(String, nullable=False)
    origin = Column(String, nullable=False, default="start")   # start | model
    sort = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class ContentArchVideo(Base):
    """ХИТ ВРЕМЁН ЗАПУСКА GTA 5 — строка археологии форматов."""
    __tablename__ = "content_arch_videos"
    __table_args__ = (UniqueConstraint("theme_id", "yt_id"),)
    id = Column(Integer, primary_key=True)
    theme_id = Column(String, nullable=False, index=True)
    yt_id = Column(String, nullable=False)
    channel_yt_id = Column(String, nullable=True)
    channel_title = Column(String, nullable=True)
    channel_lang = Column(String, nullable=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)            # начало описания, до 400 знаков
    published_at = Column(DateTime, nullable=True)
    views = Column(Integer, nullable=True)
    likes = Column(Integer, nullable=True)
    comments = Column(Integer, nullable=True)
    format_id = Column(Integer, nullable=True, index=True)
    format_reason = Column(String, nullable=True)
    flags = Column(Text, nullable=True)                  # JSON: 18+ | стриптиз-клубы | шок-насилие
    limited_ads = Column(Boolean, nullable=False, default=False)
    classify_tries = Column(Integer, nullable=False, default=0)
    fetched_at = Column(DateTime, nullable=True)
    classified_at = Column(DateTime, nullable=True)


class ContentSetting(Base):
    """НАСТРОЙКИ МОДУЛЯ: формула оценки, потолок квоты, размеры пачек."""
    __tablename__ = "content_settings"
    key = Column(String, primary_key=True)
    value = Column(Text, nullable=False)                 # JSON
    updated_at = Column(DateTime, nullable=True)


class ContentQuota(Base):
    """РАСХОД КВОТЫ YOUTUBE ЗА ТИХООКЕАНСКИЕ СУТКИ. Пишется ДО вызова
    (резерв), а не после: оборвись процесс посреди вызова, счётчик
    не занизится, и потолок останется жёстким."""
    __tablename__ = "content_quota"
    day = Column(String, primary_key=True)               # ГГГГ-ММ-ДД по Лос-Анджелесу
    units = Column(Integer, nullable=False, default=0)
    detail = Column(Text, nullable=True)                 # JSON: {метод: единиц}
    updated_at = Column(DateTime, nullable=True)


class ContentRun(Base):
    """ПРОГОН: цикл сбора, поиск каналов, археология. Состояние — в базе:
    после перезапуска машины видно, где прогон встал."""
    __tablename__ = "content_runs"
    id = Column(Integer, primary_key=True)
    kind = Column(String, nullable=False)                # cycle | discover | archaeology
    theme_id = Column(String, nullable=True)
    trigger = Column(String, nullable=False)             # scheduler | admin | probe
    state = Column(String, nullable=False)               # running | ok | partial | error | skipped
    started_at = Column(DateTime, nullable=False)
    finished_at = Column(DateTime, nullable=True)
    summary = Column(Text, nullable=True)                # JSON
    note = Column(Text, nullable=True)


# ── ПОМОЩНИКИ ─────────────────────────────────────────────────────────

def из_json(текст, запас=None):
    """Разбор JSON-поля. Битое поле — запасное значение И СТРОКА в журнале:
    молча подставленный запас выглядел бы как настоящая настройка."""
    if текст is None or текст == "":
        return запас
    try:
        return json.loads(текст)
    except (ValueError, TypeError) as e:
        print(f"[content] битое JSON-поле ({type(e).__name__}): {str(текст)[:80]!r}", flush=True)
        return запас


def в_json(значение) -> str:
    return json.dumps(значение, ensure_ascii=False)


def прочитать_семя() -> dict:
    with io.open(СЕМЯ, encoding="utf-8") as ф:
        return json.load(ф)


def засеять(db) -> dict:
    """Наполнить ПУСТЫЕ таблицы из семени. Идемпотентно: вторая тема,
    источник или формат, заведённые владельцем, не трогаются; настройка
    добавляется по ключу, если её нет, и НЕ перезаписывается."""
    семя = прочитать_семя()
    итог = {"тем": 0, "источников": 0, "форматов": 0, "настроек": 0}
    for т in семя.get("темы", []):
        if db.query(ContentTheme).filter(ContentTheme.id == т["id"]).first():
            continue
        db.add(ContentTheme(id=т["id"], title=т["title"], keywords=в_json(т["keywords"]),
                            languages=в_json(т["languages"]),
                            params=в_json(т.get("params") or {}), active=True))
        итог["тем"] += 1
        for и in т.get("sources", []):
            db.add(ContentSource(theme_id=т["id"], kind=и["kind"], name=и["name"],
                                 url=и.get("url"), params=в_json(и.get("params") or {}),
                                 official=bool(и.get("official")),
                                 filter_keywords=bool(и.get("filter_keywords", True)),
                                 enabled=bool(и.get("enabled", True)), note=и.get("note")))
            итог["источников"] += 1
        for порядок, название in enumerate(т.get("formats", []), 1):
            db.add(ContentFormat(theme_id=т["id"], title=название, origin="start", sort=порядок))
            итог["форматов"] += 1
    for ключ, значение in (семя.get("settings") or {}).items():
        if db.query(ContentSetting).filter(ContentSetting.key == ключ).first():
            continue
        db.add(ContentSetting(key=ключ, value=в_json(значение), updated_at=datetime.utcnow()))
        итог["настроек"] += 1
    if any(итог.values()):
        db.commit()
    return итог


def настройка(db, ключ: str) -> dict:
    """Настройка из базы. Нет в базе — из семени (и строка в журнале):
    иначе код молча жил бы без предела, а на экране стояло бы «из базы»."""
    строка = db.query(ContentSetting).filter(ContentSetting.key == ключ).first()
    if строка is not None:
        значение = из_json(строка.value, None)
        if isinstance(значение, dict):
            return значение
    запас = (прочитать_семя().get("settings") or {}).get(ключ) or {}
    print(f"[content] настройки {ключ!r} в базе нет — взято из семени", flush=True)
    return запас


def сутки_квоты(момент: datetime | None = None) -> str:
    """Тихоокеанские сутки квоты для момента UTC."""
    момент = момент or datetime.utcnow()
    return момент.replace(tzinfo=ZoneInfo("UTC")).astimezone(ПОЯС_КВОТЫ).date().isoformat()


def сброс_квоты_utc(момент: datetime | None = None) -> datetime:
    """Когда квота обнулится (UTC, без пояса) — для подписи на экране."""
    момент = (момент or datetime.utcnow()).replace(tzinfo=ZoneInfo("UTC"))
    местн = момент.astimezone(ПОЯС_КВОТЫ)
    полночь = (местн + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return полночь.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)


def квота_израсходовано(db, день: str | None = None) -> int:
    строка = db.query(ContentQuota).filter(ContentQuota.day == (день or сутки_квоты())).first()
    return int(строка.units) if строка else 0


def квота_списать(db, метод: str, единиц: int) -> int:
    """Прибавить расход и вернуть итог суток. Коммит — здесь же."""
    день = сутки_квоты()
    строка = db.query(ContentQuota).filter(ContentQuota.day == день).first()
    if строка is None:
        строка = ContentQuota(day=день, units=0, detail="{}")
        db.add(строка)
    строка.units = int(строка.units or 0) + int(единиц)
    детали = из_json(строка.detail, {}) or {}
    детали[метод] = int(детали.get(метод, 0)) + int(единиц)
    строка.detail = в_json(детали)
    строка.updated_at = datetime.utcnow()
    db.commit()
    return строка.units
