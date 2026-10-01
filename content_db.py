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
    # РЕКОМЕНДАЦИЯ ЧИСТКИ (письмо A2): по последним 50 названиям — язык,
    # доля роликов про тему и совет. Применяет только владелец кнопкой.
    gta_share = Column(Float, nullable=True)
    titles_checked = Column(Integer, nullable=True)
    rec = Column(String, nullable=True)                  # keep | drop
    rec_reason = Column(Text, nullable=True)
    rec_at = Column(DateTime, nullable=True)
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
    en_videos = Column(Integer, nullable=False, default=0)
    # ОПЕРЕЖЕНИЕ (BACKLOG №367): сюжет впервые появился НЕ на YouTube
    # (СМИ, Rockstar, PlayStation) — и раньше первого ролика либо роликов
    # ещё нет. Первый источник называется на карточке с временем и ссылкой.
    lead = Column(Boolean, nullable=False, default=False)
    first_source = Column(String, nullable=True)
    first_url = Column(String, nullable=True)
    first_platform = Column(String, nullable=True)
    growth = Column(Float, nullable=False, default=0.0)
    score = Column(Integer, nullable=False, default=0)
    score_parts = Column(Text, nullable=True)            # JSON: части оценки
    official = Column(Boolean, nullable=False, default=False)
    rumor = Column(Boolean, nullable=False, default=False)
    leak = Column(Boolean, nullable=False, default=False)
    # ВОЛНА (письмо A2): сюжеты одного первоисточника в пределах 72 ч
    # склеены в этот. `origin` — названный первоисточник, `subtopics` —
    # JSON-список заголовков поглощённых сюжетов (подтемы).
    origin = Column(String, nullable=True)
    subtopics = Column(Text, nullable=True)
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
    note = Column(Text, nullable=True)                   # пометка формата (Content ID и т. п.)
    # ФАЗА (письмо A2): pre — до релиза, launch — первые 4 недели после,
    # post — позже, any — всегда. NULL — фаза не проставлена (досев семени
    # проставит её по названию; до этого формат считается «any»).
    phase = Column(String, nullable=True)
    # СТАТУС: active — в рейтинге и в идеях; review — предложен моделью,
    # ждёт решения владельца; merged — слит в `merged_into` и живёт псевдонимом:
    # модель, назвавшая его снова, попадает в формат-цель.
    status = Column(String, nullable=False, default="active")
    merged_into = Column(Integer, nullable=True)
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
    # ВЫСТРЕЛ (версия 5, BACKLOG №368): просмотры / медиана просмотров
    # роликов того же канала за ±90 дней вокруг ролика. Медианы нет —
    # выстрела нет, и ролик не ранжируется.
    shot = Column(Float, nullable=True)
    channel_median = Column(Integer, nullable=True)
    median_base = Column(Integer, nullable=True)
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
    # ХОД идущего прогона (JSON: этап, сделано, всего, осталось_сек) —
    # пишет `content_worker.ход`, показывает «Кухня» живьём.
    progress = Column(Text, nullable=True)


class ContentIdea(Base):
    """ИДЕЯ РОЛИКА (BACKLOG №370) — готовый ролик, а не сюжет. Название
    и строку «почему сейчас» пишет модель; ФАКТЫ (`facts`, JSON) считает код
    из записей базы, и `basis` хранит, из каких именно — ролики, новости,
    хиты археологии. Пара «сюжет + формат» не повторяется между прогонами."""
    __tablename__ = "content_ideas"
    id = Column(Integer, primary_key=True)
    theme_id = Column(String, nullable=False, index=True)
    run_id = Column(Integer, nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    kind = Column(String, nullable=False)                # long | shorts
    sort = Column(String, nullable=False)                # hot | trend | evergreen | user
    title = Column(String, nullable=False)
    why = Column(Text, nullable=True)
    format_id = Column(Integer, nullable=True, index=True)
    story_id = Column(Integer, nullable=True, index=True)
    facts = Column(Text, nullable=True)                  # JSON: спрос, конкуренция, выстрел, окно
    basis = Column(Text, nullable=True)                  # JSON: id записей и хитов, из которых факты
    risks = Column(Text, nullable=True)                  # JSON: ["leak", "18+"]
    rank = Column(Float, nullable=False, default=0.0)
    main = Column(Boolean, nullable=False, default=False)
    deferred = Column(Boolean, nullable=False, default=False)   # «Не сегодня» у главной
    state = Column(String, nullable=False, default="new")       # new | planned | rejected
    reason = Column(String, nullable=True)               # format | done | boring
    reacted_at = Column(DateTime, nullable=True)
    text_by = Column(String, nullable=True)              # model | code
    text_tries = Column(Integer, nullable=False, default=0)


class ContentVideo(Base):
    """РОЛИК ВЛАДЕЛЬЦА В КОНВЕЙЕРЕ (BACKLOG №370): plan → writing →
    editing → published. У вышедшего — ссылка на YouTube."""
    __tablename__ = "content_videos"
    id = Column(Integer, primary_key=True)
    theme_id = Column(String, nullable=False, index=True)
    idea_id = Column(Integer, nullable=True, index=True)
    title = Column(String, nullable=False)
    kind = Column(String, nullable=False, default="long")
    status = Column(String, nullable=False, default="plan")
    youtube_url = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    status_at = Column(DateTime, nullable=True)
    published_at = Column(DateTime, nullable=True)


class ContentLink(Base):
    """ВНЕШНЯЯ ССЫЛКА ИЗ ЗАПИСИ (BACKLOG №374): на кого ссылаются описания
    роликов и записи лент. Из них «Кухня» считает кандидатов
    в первоисточники. Повтор ссылки в записи невозможен по построению."""
    __tablename__ = "content_links"
    __table_args__ = (UniqueConstraint("item_id", "url"),)
    id = Column(Integer, primary_key=True)
    theme_id = Column(String, nullable=False, index=True)
    item_id = Column(Integer, nullable=False, index=True)
    source_key = Column(String, nullable=False)          # кто сослался: rss:3 | yt:UC…
    domain = Column(String, nullable=False, index=True)
    url = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class ContentDomain(Base):
    """ИТОГ ПРОВЕРКИ КАНДИДАТА (BACKLOG №374). `added` — лента найдена
    и заведена источником; `refused` — отказ с причиной (robots.txt,
    ленты нет, сайт не ответил). Отказ хранится и показывается рядом
    с кандидатом: иначе его проверяли бы снова и снова."""
    __tablename__ = "content_domains"
    __table_args__ = (UniqueConstraint("theme_id", "domain"),)
    id = Column(Integer, primary_key=True)
    theme_id = Column(String, nullable=False, index=True)
    domain = Column(String, nullable=False)
    status = Column(String, nullable=False)              # added | refused
    reason = Column(Text, nullable=True)
    feed_url = Column(String, nullable=True)
    source_id = Column(Integer, nullable=True)
    checked_at = Column(DateTime, nullable=False)


class ContentRef(Base):
    """РОЛИК-ОБРАЗЕЦ ФОРМАТА и его разбор (письмо B, блок 1). Разбирает
    Gemini ПО ССЫЛКЕ на публичный ролик — сам ролик не скачивается
    (правила YouTube). Ролик одного формата — одна строка; тот же ролик
    у другого формата — своя строка: разбор один, а связь с форматом — нет.
    state: ok — разбор есть; skipped — ролик недоступен НАВСЕГДА (приватный,
    удалён, 18+, слишком длинный), повтор не нужен; error — сбой сервиса,
    следующий прогон попробует снова."""
    __tablename__ = "content_refs"
    __table_args__ = (UniqueConstraint("format_id", "yt_id", name="uq_content_ref"),)
    id = Column(Integer, primary_key=True)
    theme_id = Column(String, nullable=False, index=True)
    format_id = Column(Integer, nullable=False, index=True)
    yt_id = Column(String, nullable=False)
    title = Column(String, nullable=True)
    channel_title = Column(String, nullable=True)
    lang = Column(String, nullable=True)                 # ru | en
    origin = Column(String, nullable=False)              # arch | radar
    shot = Column(Float, nullable=True)                  # выстрел хита либо аномалия радара
    minutes = Column(Float, nullable=True)
    state = Column(String, nullable=False, default="new")   # new | ok | skipped | error
    reason = Column(Text, nullable=True)                 # почему пропущен либо сбой
    analysis = Column(Text, nullable=True)               # JSON разбора
    model = Column(String, nullable=True)
    cost = Column(Float, nullable=True)
    tries = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    analyzed_at = Column(DateTime, nullable=True)


class ContentPackage(Base):
    """ПАКЕТ РОЛИКА (письмо B, блок 2): названия, превью, крючок, сценарий,
    список съёмок, проверка перед публикацией, источники. Собирается ОДИН
    раз фоновой задачей и дальше открывается из базы — без вызовов модели.
    data — JSON блоков; steps — шаги сборки для экрана."""
    __tablename__ = "content_packages"
    id = Column(Integer, primary_key=True)
    theme_id = Column(String, nullable=False, index=True)
    idea_id = Column(Integer, nullable=False, index=True)
    video_id = Column(Integer, nullable=True)
    kind = Column(String, nullable=False, default="long")    # long | shorts
    state = Column(String, nullable=False, default="running")  # running | ok | error
    steps = Column(Text, nullable=True)
    note = Column(Text, nullable=True)
    data = Column(Text, nullable=True)
    refs = Column(Text, nullable=True)                   # JSON: id образцов, по которым строилось
    model = Column(String, nullable=True)
    cost = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)


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
    db.flush()                                   # autoflush выключен: иначе досев не увидит только что заведённое
    догнано = догнать_семя(db, семя)
    if any(итог.values()) or догнано:
        db.commit()
    return итог


# Веса формулы до версии с опережением: пока в базе ровно они, владелец
# формулу не правил, и её можно заменить новой целиком. Иначе добавляется
# только новый вес — чужая правка не перезаписывается.
_ВЕСА_ДО_ОПЕРЕЖЕНИЯ = {"рост": 45, "площадки": 30, "окно_ru": 25}


ДОСЕВ_КЛЮЧЕЙ_ИСТОЧНИКА = ("site",)


def догнать_семя(db, семя: dict) -> int:
    """ДОСЕВ УЖЕ ЗАВЕДЁННОЙ ТЕМЫ (BACKLOG №367, 368). `засеять` трогает
    только пустые таблицы, а источники, параметры археологии и формат,
    добавленные в семя позже, до прода иначе не доехали бы никогда.
    Добавляется ТОЛЬКО недостающее: источник — по имени, формат — по названию,
    ключ параметров темы — по ключу; археология — по номеру версии `v`.
    Возвращает, сколько изменений внесено (0 — база уже догнана)."""
    изменений = 0
    for т in семя.get("темы", []):
        тема = db.query(ContentTheme).filter(ContentTheme.id == т["id"]).first()
        if тема is None:
            continue
        имена = {и.name: и for и in db.query(ContentSource).filter(ContentSource.theme_id == т["id"])}
        for и in т.get("sources", []):
            if и["name"] in имена:
                # КЛЮЧ `site` (№374, у IGN лента на чужом хосте) доезжает, если
                # его нет. ТОЛЬКО ОН: он называет, чей это сайт, а не поведение.
                # Общий досев ключей вернул бы `strict`, снятый владельцем, —
                # «ключа нет» и «ключ убрали» неразличимы (поймал тест подлога
                # фильтра СМИ).
                есть = имена[и["name"]]
                пар = из_json(есть.params, {}) or {}
                новые = {к: з for к, з in (и.get("params") or {}).items()
                         if к in ДОСЕВ_КЛЮЧЕЙ_ИСТОЧНИКА and к not in пар}
                if новые:
                    есть.params = в_json({**пар, **новые})
                    изменений += 1
                continue
            db.add(ContentSource(theme_id=т["id"], kind=и["kind"], name=и["name"],
                                 url=и.get("url"), params=в_json(и.get("params") or {}),
                                 official=bool(и.get("official")),
                                 filter_keywords=bool(и.get("filter_keywords", True)),
                                 enabled=bool(и.get("enabled", True)), note=и.get("note")))
            изменений += 1
        параметры = из_json(тема.params, {}) or {}
        было = в_json(параметры)
        for ключ, значение in (т.get("params") or {}).items():
            if ключ == "archaeology":
                старая = параметры.get("archaeology") or {}
                if int(старая.get("v", 1)) < int(значение.get("v", 1)):
                    параметры["archaeology"] = значение
            elif ключ not in параметры:
                параметры[ключ] = значение
        if в_json(параметры) != было:
            тема.params = в_json(параметры)
            изменений += 1
        заметки = т.get("format_notes") or {}
        есть = {ф.title: ф for ф in db.query(ContentFormat).filter(ContentFormat.theme_id == т["id"])}
        порядок = max([ф.sort for ф in есть.values()] or [0])
        for название in т.get("formats", []):
            ф = есть.get(название)
            if ф is None:
                порядок += 1
                ф = ContentFormat(theme_id=т["id"], title=название, origin="start", sort=порядок)
                db.add(ф)
                изменений += 1
            if заметки.get(название) and not ф.note:
                ф.note = заметки[название]
                изменений += 1
        # ФАЗЫ и СЛИЯНИЯ (письмо A2) — по названию, в том числе у форматов,
        # заведённых моделью. Фаза ставится только непроставленной: правка
        # владельца не перезаписывается.
        db.flush()
        есть = {ф.title: ф for ф in db.query(ContentFormat).filter(ContentFormat.theme_id == т["id"])}
        for название, фаза in (т.get("format_phases") or {}).items():
            ф = есть.get(название)
            if ф is not None and ф.phase is None and фаза in ФАЗЫ:
                ф.phase = фаза
                изменений += 1
        for откуда, куда in (т.get("format_merges") or {}).items():
            ф, цель = есть.get(откуда), есть.get(куда)
            if ф is not None and цель is not None and ф.status != "merged" and ф.id != цель.id:
                слить_формат(db, ф, цель)
                изменений += 1
    # БЮДЖЕТ ПО УМОЛЧАНИЮ $2 (письмо B2). Прежнее умолчание 1.0 в базе
    # меняется, только пока владелец его не правил (значение ровно 1.0
    # при версии ниже 2); своё значение владельца не трогается.
    запись = db.query(ContentSetting).filter(ContentSetting.key == "budget").first()
    б_семя = (семя.get("settings") or {}).get("budget") or {}
    if запись is not None and б_семя.get("v"):
        текущее = из_json(запись.value, {}) or {}
        if int(текущее.get("v", 1)) < int(б_семя["v"]) and float(текущее.get("daily_usd", 1.0)) == 1.0:
            текущее["daily_usd"] = б_семя["daily_usd"]
            запись.value = в_json(текущее)
            запись.updated_at = datetime.utcnow()
            изменений += 1
    # СПИСКИ НАСТРОЕК С ВЕРСИЕЙ (№374: Game Informer в доверенных СМИ).
    # Настройка без изменений не перезаписывается (`засеять`), а новый член
    # списка в семени до прода иначе не доехал бы. У настройки с `v` в семени
    # списки ОБЪЕДИНЯЮТСЯ, когда версия в базе ниже: добавляется недостающее,
    # чужое не удаляется.
    for ключ, значение in (семя.get("settings") or {}).items():
        if not isinstance(значение, dict) or "v" not in значение:
            continue
        запись = db.query(ContentSetting).filter(ContentSetting.key == ключ).first()
        if запись is None:
            continue
        текущее = из_json(запись.value, {}) or {}
        if int(текущее.get("v", 1)) >= int(значение["v"]):
            continue
        for к, з in значение.items():
            if isinstance(з, list) and isinstance(текущее.get(к), list):
                текущее[к] = текущее[к] + [x for x in з if x not in текущее[к]]
            elif к not in текущее or к == "v":
                текущее[к] = з
        запись.value = в_json(текущее)
        запись.updated_at = datetime.utcnow()
        изменений += 1
    формула_семени = (семя.get("settings") or {}).get("score_formula")
    запись = db.query(ContentSetting).filter(ContentSetting.key == "score_formula").first()
    if формула_семени and запись is not None:
        формула = из_json(запись.value, {}) or {}
        веса = формула.get("веса") or {}
        if "опережение" not in веса:
            if веса == _ВЕСА_ДО_ОПЕРЕЖЕНИЯ:
                формула = dict(формула_семени)
            else:
                веса["опережение"] = формула_семени["веса"]["опережение"]
                формула["веса"] = веса
                формула.setdefault("опережение_насыщение", формула_семени.get("опережение_насыщение", 5))
            запись.value = в_json(формула)
            запись.updated_at = datetime.utcnow()
            изменений += 1
    return изменений


ФАЗЫ = {"pre": "до релиза", "launch": "первые 4 недели", "post": "после запуска",
        "any": "всегда"}


def слить_формат(db, ф, цель) -> int:
    """Формат `ф` сливается в `цель`: хиты и идеи переезжают, сам формат
    остаётся ПСЕВДОНИМОМ (status merged) — модель, назвавшая его снова
    при следующей археологии, попадёт в цель, а не заведёт дубль заново.
    Возвращает, сколько хитов переехало."""
    хитов = (db.query(ContentArchVideo).filter(ContentArchVideo.format_id == ф.id)
             .update({ContentArchVideo.format_id: цель.id}, synchronize_session=False))
    db.query(ContentIdea).filter(ContentIdea.format_id == ф.id).update(
        {ContentIdea.format_id: цель.id}, synchronize_session=False)
    # цепочка псевдонимов не растёт: то, что было слито в `ф`, теперь смотрит в цель
    db.query(ContentFormat).filter(ContentFormat.merged_into == ф.id).update(
        {ContentFormat.merged_into: цель.id}, synchronize_session=False)
    ф.status, ф.merged_into = "merged", цель.id
    if цель.status == "review":
        цель.status = "active"
    return хитов


def фаза_сейчас(настройки_фаз: dict, сейчас: datetime | None = None) -> str:
    """pre | launch | post по дате релиза (сутки — по Москве)."""
    from zoneinfo import ZoneInfo
    сейчас = сейчас or datetime.utcnow()
    день = сейчас.replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo("Europe/Moscow")).date()
    try:
        релиз = datetime.strptime(str(настройки_фаз.get("release_date") or "2026-11-19"),
                                  "%Y-%m-%d").date()
    except ValueError:
        return "pre"
    if день < релиз:
        return "pre"
    if (день - релиз).days < int(настройки_фаз.get("launch_days", 28)):
        return "launch"
    return "post"


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
