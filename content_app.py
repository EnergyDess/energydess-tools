"""МАРШРУТЫ МОДУЛЯ «КОНТЕНТ» (BACKLOG №365, 366) — только администратору.

    GET  /content                    — «Сегодня»: что снимать (BACKLOG №371)
    GET  /content/kitchen            — «Кухня»: «Сюжеты», «Форматы», «Источники»
    GET  /content/api/ideas/state    — идут ли идеи и их шаги
    POST /content/api/ideas/run      — «Обновить идеи»
    POST /content/api/ideas/{id}     — реакция: plan | reject (с причиной) | later
    POST /content/api/videos/{id}    — статус ролика конвейера (и ссылка у вышедшего)
    POST /content/api/settings/week  — цель роликов в неделю
    GET  /content/api/state          — идёт ли прогон и чем кончился последний
    POST /content/api/run            — запустить: cycle | discover | archaeology
    POST /content/api/channels/{id}  — канал реестра: оставить | убрать | кандидат

НЕ-АДМИНУ — 403, И ГОСТЮ ТОЖЕ (требование письма). Прочие разделы админки
уводят чужого на главную; здесь отказ называется кодом, потому что
модуль целиком служебный и в меню у не-админа его нет вовсе.

`main` ИМПОРТИРУЕТСЯ В МОМЕНТ ВЫЗОВА, а не наверху: этот файл подключает
сам `main`, и прямой импорт замкнул бы круг на полусобранном модуле.

ЧИСЛА СТРАНИЦЫ СОБИРАЕТ СЕРВЕР ИЗ ТЕХ ЖЕ СТРОК, ЧТО ПИШЕТ СБОР, — второго
построителя в браузере нет: браузер только переключает вкладки
и зовёт действия. Время — в поясе владельца (`main._пояс`), как везде.
"""
from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

import content_collect as cc
import content_db as cdb
import content_engine as ce
import content_ideas as ci
import content_package as cp
import content_refs as cr
import content_worker as cw
from auth import get_current_user
from content_db import (ContentArchVideo, ContentChannel, ContentDomain, ContentFormat,
                        ContentIdea, ContentItem, ContentLink, ContentRun, ContentSetting,
                        ContentSnapshot, ContentSource, ContentStory, ContentTheme,
                        ContentVideo)
from database import get_db

router = APIRouter()

СЮЖЕТОВ_НА_СТРАНИЦЕ = 60
СЮЖЕТ_СВЕЖЕСТЬ_ДНЕЙ = 14          # сюжет без новых записей дольше — в архиве, не на экране
ЗАПИСЕЙ_В_СЮЖЕТЕ = 12            # ссылок источников под сюжетом, дальше — «и ещё N»
ХИТОВ_НА_СТРАНИЦЕ = 100
ПРОГОНОВ_В_ЖУРНАЛЕ = 8
ОТКАЗ_НЕ_АДМИНУ = "Нет доступа: раздел «Контент» открыт только администратору."
СТРАНИЦА = {"icon": "activity", "label": "Админ · контент", "title": "Контент"}
ЗАМЕТКА_УТЕЧКИ = "Рассказывать можно, кадры утечки показывать нельзя."
ЦВЕТ_ИСХОДА = {"ok": "ok", "quota": "warn", "error": "danger", "off": "off", None: "idle"}
ВИДЫ_ПРОГОНА = {"cycle": "сбор", "discover": "поиск каналов", "archaeology": "археология",
                "ideas": "идеи", "refs": "образцы", "package": "пакет ролика",
                "channels": "чистка каналов", "domain": "проверка источника"}
СОСТОЯНИЯ_ПРОГОНА = {"running": "идёт", "ok": "готово", "partial": "частично",
                     "error": "ошибка", "skipped": "пропущен"}
СТАТУСЫ_КАНАЛА = {"candidate": "кандидат", "keep": "оставлен", "removed": "убран"}

# ПОДСКАЗКИ ГОРЯЧЕСТИ (письмо A2) — простым языком, при наведении
ПОДСКАЗКИ = {
    "горячесть": "Горячесть 0–100: насколько сюжет стоит снимать прямо сейчас. "
                 "Складывается из четырёх частей ниже — наведите на каждую.",
    "рост": "Рост: как быстро набирают просмотры ролики и посты по сюжету за последние "
            "часы. Чем быстрее, тем больше очков.",
    "площадки": "Площадки: на скольких разных сайтах о сюжете пишут (YouTube, Rockstar, "
                "СМИ, Reddit). Чем шире, тем важнее новость.",
    "окно_ru": "Окно на русском: сколько роликов на русском уже вышло. Меньше роликов — "
               "больше шанс быть первым, больше очков.",
    "опережение": "Опережение: новость сначала вышла не на YouTube (СМИ, Rockstar), "
                  "и роликов по ней ещё мало — можно успеть раньше блогеров.",
}


def _админ(user) -> bool:
    return bool(user and user.is_admin)


def _main():
    import main
    return main


def _время(момент: datetime | None, зона: ZoneInfo, с_годом: bool = False) -> str:
    if not момент:
        return "—"
    местное = момент.replace(tzinfo=ZoneInfo("UTC")).astimezone(зона)
    return местное.strftime("%d.%m.%Y" if с_годом else "%d.%m %H:%M")


def _сколько_назад(момент: datetime | None) -> str:
    if not момент:
        return ""
    минут = int((datetime.utcnow() - момент).total_seconds() // 60)
    if минут < 1:
        return "только что"
    if минут < 60:
        return f"{минут} мин назад"
    часов = минут // 60
    if часов < 48:
        return f"{часов} ч назад"
    return f"{часов // 24} дн назад"


def _число(n) -> str:
    return "—" if n is None else "{:,}".format(int(n)).replace(",", " ")


def _рост(x) -> str:
    if not x:
        return "0 в час"
    return f"{_число(round(x))} в час" if x >= 10 else f"{x:.1f} в час".replace(".", ",")


def _прогон_наружу(п: ContentRun | None, зона: ZoneInfo, user) -> dict | None:
    if п is None:
        return None
    return {"id": п.id, "kind": п.kind, "вид": ВИДЫ_ПРОГОНА.get(п.kind, п.kind),
            "state": п.state, "состояние": СОСТОЯНИЯ_ПРОГОНА.get(п.state, п.state),
            "trigger": п.trigger, "начат": _main()._момент_в_поясе(п.started_at, user),
            "сек": (round((п.finished_at - п.started_at).total_seconds())
                    if п.finished_at else None),
            "note": п.note, "итог": cdb.из_json(п.summary, {}) or {},
            "ход": _ход_наружу(п)}


def _ход_наружу(п: ContentRun) -> dict | None:
    """«Идёт: 340 из 1145 · ~4 мин» — строка собирается здесь, одна на «Кухню»
    и «Сегодня». Только у идущего прогона: у законченного хода нет."""
    if п.state != "running":
        return None
    х = cdb.из_json(getattr(п, "progress", None), {}) or {}
    if not х:
        return {"текст": "Идёт: запуск…"}
    части = [х.get("этап") or "работа"]
    if х.get("всего"):
        части.append("%d из %d" % (х.get("сделано") or 0, х["всего"]))
    ост = х.get("осталось_сек")
    if ост is not None:
        части.append("~%d мин" % max(1, round(ост / 60)) if ост >= 60 else "меньше минуты")
    return {**х, "текст": "Идёт: " + " · ".join(части)}


def _исполнитель() -> dict | None:
    """Что сейчас реально идёт в исполнителе — правда о занятости. Строка
    «running» в базе без живого исполнителя — ничья (процесс падал), и кнопку
    она не держит."""
    т = cw.что_идёт()
    if т is None:
        return None
    return {"kind": т["вид"], "вид": cw.ИМЕНА.get(т["вид"], т["вид"]),
            "текст": cw.отказ_занято()}


def _квота(db) -> dict:
    предел = int(cdb.настройка(db, "youtube").get("daily_cap", 9000))
    день = cdb.сутки_квоты()
    строка = db.get(cdb.ContentQuota, день)
    потрачено = int(строка.units) if строка else 0
    return {"день": день, "потрачено": потрачено, "предел": предел,
            "доля": min(100, round(потрачено * 100 / предел)) if предел else 0,
            "детали": cdb.из_json(строка.detail, {}) if строка else {},
            "сброс_utc": cdb.сброс_квоты_utc()}


def _сюжеты(db, тема_id: str, зона: ZoneInfo) -> list[dict]:
    граница = datetime.utcnow() - timedelta(days=СЮЖЕТ_СВЕЖЕСТЬ_ДНЕЙ)
    сюжеты = (db.query(ContentStory)
              .filter(ContentStory.theme_id == тема_id, ContentStory.items > 0,
                      func.coalesce(ContentStory.last_item_at, ContentStory.created_at) >= граница)
              .order_by(ContentStory.score.desc(), ContentStory.last_item_at.desc())
              .limit(СЮЖЕТОВ_НА_СТРАНИЦЕ).all())
    if not сюжеты:
        return []
    записи = defaultdict(list)
    когда = func.coalesce(ContentItem.published_at, ContentItem.first_seen_at)
    for и in (db.query(ContentItem).filter(ContentItem.story_id.in_([с.id for с in сюжеты]))
              .order_by(ContentItem.official.desc(), когда.asc()).all()):
        записи[и.story_id].append(и)
    итог = []
    for с in сюжеты:
        свои = записи.get(с.id, [])
        итог.append({
            "id": с.id, "title": с.title, "summary": с.summary, "score": с.score,
            "части": cdb.из_json(с.score_parts, {}) or {},
            "первое": _время(с.first_seen_at, зона), "последнее": _время(с.last_item_at, зона),
            "источников": с.sources, "площадок": с.platforms, "записей": с.items,
            "ru_роликов": с.ru_videos, "en_роликов": с.en_videos, "рост": _рост(с.growth),
            # ОПЕРЕЖЕНИЕ (BACKLOG №367): первым пришёл не YouTube
            "опережение": bool(с.lead),
            "первый": {"источник": с.first_source, "url": с.first_url,
                       "platform": с.first_platform, "когда": _время(с.first_seen_at, зона)},
            "official": с.official, "rumor": с.rumor, "leak": с.leak,
            # ВОЛНА (письмо A2): склеенные подтемы одного первоисточника
            "первоисточник": с.origin,
            "подтемы": cdb.из_json(с.subtopics, []) or [],
            "ссылки": [{"title": и.title, "url": и.url, "источник": и.source_name,
                        "когда": _время(и.published_at or и.first_seen_at, зона),
                        "lang": и.lang, "official": и.official, "leak": и.leak,
                        "rumor": и.rumor, "метрика": и.metric, "platform": и.platform}
                       for и in свои[:ЗАПИСЕЙ_В_СЮЖЕТЕ]],
            "ещё": max(0, len(свои) - ЗАПИСЕЙ_В_СЮЖЕТЕ),
        })
    return итог


def _форматы(db, тема_id: str, зона: ZoneInfo) -> dict:
    """ВКЛАДКА «ФОРМАТЫ» ПО ВЫСТРЕЛУ (версия 5, BACKLOG №368). Ранжируются
    только хиты с выстрелом: у ролика без медианы канала (соседей в окне
    мало) планки нет, и ставить его рядом с остальными нечем — он считается
    отдельным числом, а не прячется. Рейтинг форматов — медианный выстрел
    его хитов, а не сумма просмотров: сумма снова поставила бы наверх
    формат большого канала."""
    все = (db.query(ContentFormat).filter(ContentFormat.theme_id == тема_id)
           .order_by(ContentFormat.sort, ContentFormat.id).all())
    # В рейтинг идут только ПРИНЯТЫЕ форматы (письмо A2): предложения модели
    # ждут решения владельца, слитые живут псевдонимами и не показываются.
    форматы = [ф for ф in все if ф.status == "active"]
    хиты = db.query(ContentArchVideo).filter(ContentArchVideo.theme_id == тема_id).all()
    с_выстрелом = sorted((в for в in хиты if в.shot is not None), key=lambda в: -в.shot)
    по_формату = defaultdict(list)
    for в in с_выстрелом:
        по_формату[в.format_id].append(в)
    имена = {ф.id: ф.title for ф in все}
    сводка = []
    for ф in форматы:
        свои = по_формату.get(ф.id, [])
        м = cc.медиана([в.shot for в in свои])
        сводка.append({"id": ф.id, "title": ф.title, "origin": ф.origin, "note": ф.note,
                       "phase": ф.phase or "any", "фаза": cdb.ФАЗЫ.get(ф.phase or "any"),
                       "хитов": len(свои), "медиана": round(м, 1) if м is not None else None,
                       "огр": sum(1 for в in свои if в.limited_ads),
                       "лучший": ({"title": свои[0].title, "url": "https://www.youtube.com/watch?v="
                                   + свои[0].yt_id, "shot": свои[0].shot} if свои else None)})
    сводка.sort(key=lambda ф: (ф["медиана"] is None, -(ф["медиана"] or 0), -ф["хитов"], ф["title"]))

    def строка(в):
        return {"channel": в.channel_title or "—", "lang": в.channel_lang or "",
                "title": в.title, "url": "https://www.youtube.com/watch?v=" + в.yt_id,
                "date": _время(в.published_at, зона, с_годом=True), "views": в.views,
                "median": в.channel_median, "base": в.median_base, "shot": в.shot,
                "format": имена.get(в.format_id), "why": в.format_reason,
                "flags": cdb.из_json(в.flags, []) or [], "limited": в.limited_ads,
                "tries": в.classify_tries}
    return {"сводка": сводка,
            "en": [строка(в) for в in с_выстрелом if в.channel_lang != "ru"][:ХИТОВ_НА_СТРАНИЦЕ],
            "ru": [строка(в) for в in с_выстрелом if в.channel_lang == "ru"][:ХИТОВ_НА_СТРАНИЦЕ],
            "всего": len(хиты), "с_выстрелом": len(с_выстрелом),
            "без_медианы": len(хиты) - len(с_выстрелом),
            "без_формата": sum(1 for в in с_выстрелом if в.format_id is None),
            "каналов_en": len({в.channel_yt_id for в in с_выстрелом if в.channel_lang != "ru"}),
            "каналов_ru": len({в.channel_yt_id for в in с_выстрелом if в.channel_lang == "ru"}),
            "огр": sum(1 for в in с_выстрелом if в.limited_ads),
            "прогноз": ce.цена_археологии(db),
            "на_рассмотрении": [{"id": ф.id, "title": ф.title,
                                 "хитов": sum(1 for в in хиты if в.format_id == ф.id)}
                                for ф in все if ф.status == "review"],
            "слито": sum(1 for ф in все if ф.status == "merged"),
            "принятые": [{"id": ф.id, "title": ф.title} for ф in форматы],
            "фазы": cdb.ФАЗЫ,
            "фаза_сейчас": cdb.фаза_сейчас(cdb.настройка(db, "phases")),
            "первая_неделя": ci.первая_неделя(db, тема_id)}


def _источники(db, тема_id: str, зона: ZoneInfo) -> list[dict]:
    записей = dict(db.query(ContentItem.source_id, func.count(ContentItem.id))
                   .filter(ContentItem.theme_id == тема_id)
                   .group_by(ContentItem.source_id).all())
    итог = []
    for и in (db.query(ContentSource).filter(ContentSource.theme_id == тема_id)
              .order_by(ContentSource.id).all()):
        итог.append({"id": и.id, "name": и.name, "kind": и.kind, "url": и.url,
                     "enabled": и.enabled, "note": и.note,
                     "state": и.last_state, "тон": ЦВЕТ_ИСХОДА.get(и.last_state, "idle"),
                     "запуск": _время(и.last_run_at, зона),
                     "удача": _время(и.last_ok_at, зона) if и.last_ok_at else "ни разу",
                     "удача_назад": _сколько_назад(и.last_ok_at),
                     "ошибка": и.last_error, "ошибка_когда": _время(и.last_error_at, зона),
                     "получено": и.last_seen, "новых": и.last_new, "сек": и.last_sec,
                     "записей": записей.get(и.id, 0)})
    return итог


def _каналы(db, тема_id: str, зона: ZoneInfo) -> list[dict]:
    роликов = dict(db.query(ContentItem.channel_id, func.count(ContentItem.id))
                   .filter(ContentItem.theme_id == тема_id, ContentItem.channel_id.isnot(None))
                   .group_by(ContentItem.channel_id).all())
    порядок = {"keep": 0, "candidate": 1, "removed": 2}
    каналы = db.query(ContentChannel).filter(ContentChannel.theme_id == тема_id).all()
    каналы.sort(key=lambda к: (порядок.get(к.status, 3), -(к.subscribers or 0)))
    return [{"id": к.id, "title": к.title, "handle": к.handle, "lang": к.lang or "",
             "subs": к.subscribers, "status": к.status,
             "статус": СТАТУСЫ_КАНАЛА.get(к.status, к.status),
             "url": "https://www.youtube.com/channel/" + к.yt_id,
             "опрошен": _время(к.last_polled_at, зона) if к.last_polled_at else "ещё нет",
             "ошибка": к.last_error, "роликов": роликов.get(к.id, 0),
             "found_by": к.found_by,
             # РЕКОМЕНДАЦИЯ ЧИСТКИ (письмо A2): совет, статус не меняет
             "rec": к.rec, "rec_reason": к.rec_reason,
             "доля": (round(к.gta_share * 100) if к.gta_share is not None else None),
             "названий": к.titles_checked} for к in каналы]


def _кандидаты(db, тема_id: str, зона: ZoneInfo) -> list[dict]:
    """КАНДИДАТЫ В ПЕРВОИСТОЧНИКИ (BACKLOG №374): домены, на которые ссылаются
    записи по теме, — сколько записей сослалось и сколько разных источников.
    Не показываются: площадки из `candidates.skip` (соцсети, сокращатели,
    магазины — своей ленты новостей у них нет) и сайты, уже заведённые
    источником. Отказ проверки показывается рядом с причиной."""
    нс = cdb.настройка(db, "candidates")
    мин = int(нс.get("min_refs", 2))
    # САМОРЕКЛАМА ОДНОГО КАНАЛА — НЕ ПЕРВОИСТОЧНИК: замер первого цикла
    # на проде — у `darkviper.au` 8 ссылок и ОДИН источник (повторяющееся
    # описание). Кандидат обязан быть процитирован разными источниками.
    мин_ист = int(нс.get("min_sources", 2))
    пропуск = [s.lower() for s in (нс.get("skip") or [])]
    свои = ce.хосты_источников(db.query(ContentSource).all())
    проверки = {д.domain: д for д in db.query(ContentDomain).filter(ContentDomain.theme_id == тема_id)}
    ряды = (db.query(ContentLink.domain,
                     func.count(func.distinct(ContentLink.item_id)),
                     func.count(func.distinct(ContentLink.source_key)),
                     func.max(ContentLink.id))
            .filter(ContentLink.theme_id == тема_id)
            .group_by(ContentLink.domain).all())
    итог = []
    for домен, записей, источников, последняя in ряды:
        if записей < мин or источников < мин_ист or cc.корень_домена(домен) in свои:
            continue
        if any(домен == s or домен.endswith("." + s) for s in пропуск):
            continue
        итог.append({"domain": домен, "refs": записей, "sources": источников, "last": последняя})
    итог.sort(key=lambda к: (-к["sources"], -к["refs"], к["domain"]))
    итог = итог[:int(нс.get("top", 20))]
    примеры = dict(db.query(ContentLink.id, ContentLink.url)
                   .filter(ContentLink.id.in_([к["last"] for к in итог] or [0])).all())
    for к in итог:
        к["url"] = примеры.get(к.pop("last"))
        п = проверки.get(к["domain"])
        к["проверка"] = ({"status": п.status, "reason": п.reason,
                          "когда": _время(п.checked_at, зона)} if п else None)
    return итог


def данные_страницы(db, user) -> dict:
    """Всё, что рисует страница, — одной сессией, без похода в сеть."""
    cdb.засеять(db)
    зона = _main()._пояс(user)
    тема = (db.query(ContentTheme).filter(ContentTheme.active.is_(True))
            .order_by(ContentTheme.id).first())
    формула = cdb.настройка(db, "score_formula")
    # «Пропущен» в журнал не идёт: планировщик их больше не пишет, а 29 046
    # строк аварии 2026-09-30 вытеснили бы из журнала все настоящие прогоны.
    последние = (db.query(ContentRun).filter(ContentRun.state != "skipped")
                 .order_by(ContentRun.id.desc()).limit(ПРОГОНОВ_В_ЖУРНАЛЕ).all())
    # Идёт — только если исполнитель реально занят: строка «running» без
    # живого исполнителя ничья и кнопку не держит.
    исп = cw.что_идёт()
    идёт = (db.query(ContentRun).filter(ContentRun.state == "running",
                                       ContentRun.kind == исп["вид"])
            .order_by(ContentRun.id.desc()).first()) if исп else None
    тема_id = тема.id if тема else ""
    источники = _источники(db, тема_id, зона)
    сейчас = datetime.utcnow()
    return {
        "тема": ({"id": тема.id, "title": тема.title,
                  "keywords": cdb.из_json(тема.keywords, []) or [],
                  "languages": cdb.из_json(тема.languages, []) or []} if тема else None),
        "страница": СТРАНИЦА,
        "сюжеты": _сюжеты(db, тема_id, зона),
        "формула": формула,
        "форматы": _форматы(db, тема_id, зона),
        "источники": источники,
        "красных": sum(1 for и in источники if и["тон"] == "danger"),
        "каналы": _каналы(db, тема_id, зона),
        "кандидаты": _кандидаты(db, тема_id, зона),
        "квота": _квота(db),
        "сброс_квоты": _main()._момент_в_поясе(cdb.сброс_квоты_utc(), user),
        "записей_всего": db.query(func.count(ContentItem.id))
                           .filter(ContentItem.theme_id == тема_id).scalar() or 0,
        "снимков_всего": db.query(func.count(ContentSnapshot.id)).scalar() or 0,
        "ждут_разбора": db.query(func.count(ContentItem.id))
                          .filter(ContentItem.theme_id == тема_id, ContentItem.story_id.is_(None),
                                  ContentItem.noise.is_(False),
                                  ContentItem.classify_tries < 3,
                                  func.coalesce(ContentItem.published_at, ContentItem.first_seen_at)
                                  >= сейчас - timedelta(days=int(
                                      cdb.настройка(db, "stories").get("window_days", 7))))
                          .scalar() or 0,
        "прогоны": [_прогон_наружу(п, зона, user) for п in последние],
        "идёт": _прогон_наружу(идёт, зона, user),
        "ключ_youtube": bool(ce.ключ_youtube()),
        "бюджет": ce.бюджет(db),
        "образцы": cr.сводка(db),
        "стиль": cdb.настройка(db, "style").get("text") or "",
        "база_знаний": cdb.настройка(db, "knowledge").get("text") or "",
        "запрещённые": "\n".join(cdb.настройка(db, "package").get("banned_phrases") or []),
        "подсказки": ПОДСКАЗКИ,
        "расход": ce.расход_по_задачам(db),
        "планировщик": ce.планировщик_включён(),
        "цикл_минут": cdb.настройка(db, "cycle").get("minutes", 30),
        "заметка_утечки": ЗАМЕТКА_УТЕЧКИ,
        "свежесть_дней": СЮЖЕТ_СВЕЖЕСТЬ_ДНЕЙ,
    }


@router.get("/content/kitchen")
async def content_page(request: Request, user=Depends(get_current_user),
                       db: Session = Depends(get_db)):
    if not _админ(user):
        return PlainTextResponse(ОТКАЗ_НЕ_АДМИНУ, status_code=403)
    вкладка = request.query_params.get("tab", "stories")
    if вкладка not in ("stories", "formats", "sources"):
        вкладка = "stories"
    контекст = {"user": user, "вкладка": вкладка, **данные_страницы(db, user)}
    return _main().templates.TemplateResponse(request=request, name="content.html",
                                              context=контекст)


@router.get("/content/api/state")
async def content_state(user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not _админ(user):
        return JSONResponse({"error": ОТКАЗ_НЕ_АДМИНУ}, status_code=403)
    зона = _main()._пояс(user)
    последний = db.query(ContentRun).order_by(ContentRun.id.desc()).first()
    идёт = (db.query(ContentRun).filter(ContentRun.state == "running",
                                       ContentRun.kind != "ideas")
            .order_by(ContentRun.id.desc()).first())
    исп = _исполнитель()
    return {"busy": ce.занят() or исп is not None,
            "work": исп,
            "running": _прогон_наружу(идёт, зона, user) if исп else None,
            "last": _прогон_наружу(последний, зона, user),
            "quota": {к: v for к, v in _квота(db).items() if к != "сброс_utc"}}


class Запуск(BaseModel):
    kind: str


@router.post("/content/api/run")
async def content_run(тело: Запуск, user=Depends(get_current_user)):
    if not _админ(user):
        return JSONResponse({"error": ОТКАЗ_НЕ_АДМИНУ}, status_code=403)
    итог = ce.запустить(тело.kind, "admin")
    if not итог.get("ok"):
        return JSONResponse(итог, status_code=409 if итог.get("busy") else 400)
    return итог


class Домен(BaseModel):
    domain: str


@router.post("/content/api/domains/check")
async def content_domain_check(тело: Домен, user=Depends(get_current_user)):
    """«Проверить и добавить»: фоном, тем же исполнителем, что сбор (§5.11).
    Итог — строка в `content_domains` и, если лента нашлась, новый источник."""
    if not _админ(user):
        return JSONResponse({"error": ОТКАЗ_НЕ_АДМИНУ}, status_code=403)
    итог = ce.запустить_проверку(тело.domain, "admin")
    if not итог.get("ok"):
        return JSONResponse(итог, status_code=409 if итог.get("busy") else 400)
    return итог


class Статус(BaseModel):
    status: str


@router.post("/content/api/channels/{channel_id}")
async def content_channel(channel_id: int, тело: Статус, user=Depends(get_current_user),
                          db: Session = Depends(get_db)):
    """Решение владельца по каналу. «Убран» — канал не опрашивается со следующего
    цикла, и его ролики не снимаются; строки и снимки не стираются."""
    if not _админ(user):
        return JSONResponse({"error": ОТКАЗ_НЕ_АДМИНУ}, status_code=403)
    if тело.status not in СТАТУСЫ_КАНАЛА:
        return JSONResponse({"error": "неизвестный статус"}, status_code=400)
    канал = db.get(ContentChannel, channel_id)
    if канал is None:
        return JSONResponse({"error": "канала нет"}, status_code=404)
    канал.status = тело.status
    канал.status_at = datetime.utcnow()
    db.commit()
    return {"ok": True, "id": канал.id, "status": канал.status,
            "статус": СТАТУСЫ_КАНАЛА[канал.status]}


class Применить(BaseModel):
    ids: list[int]


@router.post("/content/api/channels-apply")
async def content_channels_apply(тело: Применить, user=Depends(get_current_user),
                                 db: Session = Depends(get_db)):
    """РЕКОМЕНДАЦИИ ЧИСТКИ — ТОЛЬКО ОТМЕЧЕННЫЕ владельцем (письмо A2):
    «убрать» → статус «убран», «оставить» → «оставлен». Неотмеченные
    и каналы без совета не трогаются."""
    if not _админ(user):
        return JSONResponse({"error": ОТКАЗ_НЕ_АДМИНУ}, status_code=403)
    изменено = []
    сейчас = datetime.utcnow()
    for к in db.query(ContentChannel).filter(ContentChannel.id.in_(тело.ids or [0])).all():
        новый = {"drop": "removed", "keep": "keep"}.get(к.rec or "")
        if новый is None or новый == к.status:
            continue
        к.status, к.status_at = новый, сейчас
        изменено.append(к.id)
    db.commit()
    return {"ok": True, "изменено": изменено}


class РешениеФормата(BaseModel):
    action: str
    into: int | None = None
    phase: str | None = None


@router.post("/content/api/formats/{format_id}")
async def content_format(format_id: int, тело: РешениеФормата, user=Depends(get_current_user),
                         db: Session = Depends(get_db)):
    """Предложение модели: «Принять» (в рейтинг, с фазой) либо «Слить в…»
    (хиты переезжают, формат остаётся псевдонимом). Фазу можно сменить
    и у принятого."""
    if not _админ(user):
        return JSONResponse({"error": ОТКАЗ_НЕ_АДМИНУ}, status_code=403)
    ф = db.get(ContentFormat, format_id)
    if ф is None:
        return JSONResponse({"error": "формата нет"}, status_code=404)
    if тело.phase is not None and тело.phase not in cdb.ФАЗЫ:
        return JSONResponse({"error": "неизвестная фаза"}, status_code=400)
    if тело.action == "accept":
        ф.status = "active"
        ф.phase = тело.phase or ф.phase or "any"
    elif тело.action == "phase":
        if not тело.phase:
            return JSONResponse({"error": "фаза не указана"}, status_code=400)
        ф.phase = тело.phase
    elif тело.action == "merge":
        цель = db.get(ContentFormat, тело.into or 0)
        if цель is None or цель.id == ф.id or цель.theme_id != ф.theme_id or цель.status != "active":
            return JSONResponse({"error": "слить можно только в принятый формат"}, status_code=400)
        cdb.слить_формат(db, ф, цель)
    else:
        return JSONResponse({"error": "неизвестное действие"}, status_code=400)
    db.commit()
    return {"ok": True, "id": ф.id, "status": ф.status, "phase": ф.phase}


# ── «СЕГОДНЯ» (BACKLOG №371) ─────────────────────────────────────────

def _идея_наружу(и: ContentIdea, форматы: dict, сюжеты: dict) -> dict:
    факты = cdb.из_json(и.facts, {}) or {}
    ф = форматы.get(и.format_id)
    с = сюжеты.get(и.story_id)
    return {"id": и.id, "kind": и.kind, "sort": и.sort, "вид": ci.ВИДЫ.get(и.sort, и.sort),
            "title": и.title, "why": и.why, "main": и.main, "deferred": и.deferred,
            "формат": ф.title if ф else None, "сюжет": с.title if с else None,
            "факты": ci.факты_подписи(факты),
            "риски": [ci.РИСКИ[р] for р in (cdb.из_json(и.risks, []) or []) if р in ci.РИСКИ]}


def данные_сегодня(db, user, тип: str) -> dict:
    """Всё для «Сегодня» — из базы, без сети. Числа — готовыми подписями:
    оценок, роста и формул на этом экране нет (они в «Кухне»)."""
    cdb.засеять(db)
    тема = (db.query(ContentTheme).filter(ContentTheme.active.is_(True))
            .order_by(ContentTheme.id).first())
    тема_id = тема.id if тема else ""
    прогон = ci.последний_прогон(db)
    идеи = []
    if прогон is not None:
        идеи = (db.query(ContentIdea).filter(ContentIdea.run_id == прогон.id,
                                             ContentIdea.theme_id == тема_id,
                                             ContentIdea.state == "new")
                .order_by(ContentIdea.rank.desc(), ContentIdea.id).all())
    форматы = {ф.id: ф for ф in db.query(ContentFormat).filter(ContentFormat.theme_id == тема_id)}
    сюжеты = ({с.id: с for с in db.query(ContentStory).filter(
        ContentStory.id.in_([и.story_id for и in идеи if и.story_id]))} if идеи else {})
    панели = {}
    for т in ("long", "shorts"):
        свои = [_идея_наружу(и, форматы, сюжеты) for и in идеи if и.kind == т]
        if т == "long":
            г = next((и for и in свои if и["main"]), None)
        else:
            г = next((и for и in свои if not и["deferred"]), None)
        панели[т] = {"главная": г, "ещё": [и for и in свои if и is not г]}
    главная, ещё = панели[тип]["главная"], панели[тип]["ещё"]
    ролики = (db.query(ContentVideo).filter(ContentVideo.theme_id == тема_id)
              .order_by(ContentVideo.status_at.desc(), ContentVideo.id.desc()).all())
    зона = _main()._пояс(user)
    пакеты = {}
    for пк in (db.query(cdb.ContentPackage).filter(
            cdb.ContentPackage.idea_id.in_([р.idea_id for р in ролики if р.idea_id]))
            .order_by(cdb.ContentPackage.id)):
        пакеты[пк.idea_id] = пк.id
    радар = ci.радар(db)
    идёт = (db.query(ContentRun).filter(ContentRun.kind == "ideas", ContentRun.state == "running")
            .first()) if ci.идёт() else None
    return {
        "страница": {"icon": "activity", "label": "Контент · GTA", "title": "Сегодня"},
        "тип": тип, "главная": главная, "ещё": ещё, "панели": панели,
        "есть_прогон": прогон is not None,
        "идеи_когда": _время(прогон.finished_at, зона) if прогон else None,
        "до_релиза": ci.до_релиза(db),
        "неделя": ci.неделя(db, тема_id),
        "радар": {"ok": радар["ok"], "причина": радар["причина"], "бюджет": радар.get("бюджет"),
                  "когда": _время(радар["последний"], зона) if радар["последний"] else "ни разу"},
        "ролики": [{"id": р.id, "title": р.title, "kind": р.kind, "status": р.status,
                    "url": р.youtube_url, "когда": _время(р.status_at, зона),
                    "пакет": пакеты.get(р.idea_id)} for р in ролики],
        "статусы": ci.СТАТУСЫ, "причины": ci.ПРИЧИНЫ,
        "счёт": {к: sum(1 for р in ролики if р.status == к) for к in ci.СТАТУСЫ},
        "идёт": идёт is not None,
        "время_генерации": cdb.настройка(db, "ideas").get("generate_at_msk", "08:00"),
    }


@router.get("/content")
async def content_today(request: Request, user=Depends(get_current_user),
                        db: Session = Depends(get_db)):
    if not _админ(user):
        return PlainTextResponse(ОТКАЗ_НЕ_АДМИНУ, status_code=403)
    тип = request.query_params.get("type", "long")
    if тип not in ("long", "shorts"):
        тип = "long"
    контекст = {"user": user, **данные_сегодня(db, user, тип)}
    return _main().templates.TemplateResponse(request=request, name="content_today.html",
                                              context=контекст)


@router.get("/content/api/ideas/state")
async def ideas_state(user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not _админ(user):
        return JSONResponse({"error": ОТКАЗ_НЕ_АДМИНУ}, status_code=403)
    п = (db.query(ContentRun).filter(ContentRun.kind == "ideas")
         .order_by(ContentRun.id.desc()).first())
    итог = (cdb.из_json(п.summary, {}) or {}) if п else {}
    исп = _исполнитель()
    return {"busy": ci.идёт(), "work": исп,
            "ход": _ход_наружу(п) if (п and ci.идёт()) else None,
            "state": п.state if п else None, "steps": итог.get("шаги") or [],
            "ideas": итог.get("идей"), "note": п.note if п else None}


@router.post("/content/api/ideas/run")
async def ideas_run(user=Depends(get_current_user)):
    if not _админ(user):
        return JSONResponse({"error": ОТКАЗ_НЕ_АДМИНУ}, status_code=403)
    итог = ci.запустить("admin")
    return итог if итог.get("ok") else JSONResponse(итог, status_code=409)


class Реакция(BaseModel):
    action: str
    reason: str | None = None


@router.post("/content/api/ideas/{idea_id}")
async def idea_react(idea_id: int, тело: Реакция, user=Depends(get_current_user),
                     db: Session = Depends(get_db)):
    if not _админ(user):
        return JSONResponse({"error": ОТКАЗ_НЕ_АДМИНУ}, status_code=403)
    итог = ci.реакция(db, idea_id, тело.action, тело.reason)
    if итог.get("error"):
        return JSONResponse({"error": итог["error"]}, status_code=итог.get("code", 400))
    return итог


class СтатусРолика(BaseModel):
    status: str
    url: str | None = None


@router.post("/content/api/videos/{video_id}")
async def video_status(video_id: int, тело: СтатусРолика, user=Depends(get_current_user),
                       db: Session = Depends(get_db)):
    if not _админ(user):
        return JSONResponse({"error": ОТКАЗ_НЕ_АДМИНУ}, status_code=403)
    итог = ci.сменить_статус(db, video_id, тело.status, тело.url)
    if итог.get("error"):
        return JSONResponse({"error": итог["error"]}, status_code=итог.get("code", 400))
    return итог


class Цель(BaseModel):
    goal: int


@router.post("/content/api/settings/week")
async def week_goal(тело: Цель, user=Depends(get_current_user), db: Session = Depends(get_db)):
    """Цель роликов в неделю — цель, а не ограничение: от 1 до 21."""
    if not _админ(user):
        return JSONResponse({"error": ОТКАЗ_НЕ_АДМИНУ}, status_code=403)
    if not 1 <= тело.goal <= 21:
        return JSONResponse({"error": "цель — от 1 до 21 ролика в неделю"}, status_code=400)
    н = dict(cdb.настройка(db, "ideas"))
    н["week_goal"] = тело.goal
    строка = db.get(ContentSetting, "ideas")
    if строка is None:
        db.add(ContentSetting(key="ideas", value=cdb.в_json(н), updated_at=datetime.utcnow()))
    else:
        строка.value, строка.updated_at = cdb.в_json(н), datetime.utcnow()
    db.commit()
    return {"ok": True, "goal": тело.goal}


class Стиль(BaseModel):
    text: str


@router.post("/content/api/settings/style")
async def style_save(тело: Стиль, user=Depends(get_current_user), db: Session = Depends(get_db)):
    """Файл-стиль сценариев (письмо B): текст правит владелец на «Кухне»."""
    if not _админ(user):
        return JSONResponse({"error": ОТКАЗ_НЕ_АДМИНУ}, status_code=403)
    текст = (тело.text or "").strip()
    if not 20 <= len(текст) <= 4000:
        return JSONResponse({"error": "стиль — от 20 до 4000 знаков"}, status_code=400)
    строка = db.get(ContentSetting, "style")
    значение = cdb.в_json({"text": текст})
    if строка is None:
        db.add(ContentSetting(key="style", value=значение, updated_at=datetime.utcnow()))
    else:
        строка.value, строка.updated_at = значение, datetime.utcnow()
    db.commit()
    return {"ok": True}


class Бюджет(BaseModel):
    usd: float


@router.post("/content/api/settings/budget")
async def budget_save(тело: Бюджет, user=Depends(get_current_user), db: Session = Depends(get_db)):
    """Дневной бюджет модели модуля (письмо B2), правит владелец на «Кухне»."""
    if not _админ(user):
        return JSONResponse({"error": ОТКАЗ_НЕ_АДМИНУ}, status_code=403)
    if not 0.1 <= тело.usd <= 50:
        return JSONResponse({"error": "бюджет — от 0.1 до 50 $ в сутки"}, status_code=400)
    строка = db.get(ContentSetting, "budget")
    значение = cdb.в_json({**cdb.настройка(db, "budget"), "daily_usd": round(тело.usd, 2), "own": True})
    if строка is None:
        db.add(ContentSetting(key="budget", value=значение, updated_at=datetime.utcnow()))
    else:
        строка.value, строка.updated_at = значение, datetime.utcnow()
    db.commit()
    return {"ok": True, **ce.бюджет(db)}


class Фразы(BaseModel):
    text: str


@router.post("/content/api/settings/banned")
async def banned_save(тело: Фразы, user=Depends(get_current_user), db: Session = Depends(get_db)):
    """Запрещённые фразы сценария (письмо B2): по одной на строку."""
    if not _админ(user):
        return JSONResponse({"error": ОТКАЗ_НЕ_АДМИНУ}, status_code=403)
    фразы = [ф.strip() for ф in (тело.text or "").splitlines() if ф.strip()]
    if len(фразы) > 200 or any(len(ф) > 120 for ф in фразы):
        return JSONResponse({"error": "до 200 фраз, каждая до 120 знаков"}, status_code=400)
    строка = db.get(ContentSetting, "package")
    значение = cdb.в_json({**cdb.настройка(db, "package"), "banned_phrases": фразы})
    if строка is None:
        db.add(ContentSetting(key="package", value=значение, updated_at=datetime.utcnow()))
    else:
        строка.value, строка.updated_at = значение, datetime.utcnow()
    db.commit()
    return {"ok": True, "count": len(фразы)}


@router.post("/content/api/settings/knowledge")
async def knowledge_save(тело: Стиль, user=Depends(get_current_user), db: Session = Depends(get_db)):
    """База знаний серии (письмо B2): уходит в каждую сборку пакета и во
    вторую проверку фактов. Правит владелец на «Кухне»."""
    if not _админ(user):
        return JSONResponse({"error": ОТКАЗ_НЕ_АДМИНУ}, status_code=403)
    текст = (тело.text or "").strip()
    if not 20 <= len(текст) <= 12000:
        return JSONResponse({"error": "база знаний — от 20 до 12000 знаков"}, status_code=400)
    строка = db.get(ContentSetting, "knowledge")
    значение = cdb.в_json({**cdb.настройка(db, "knowledge"), "text": текст})
    if строка is None:
        db.add(ContentSetting(key="knowledge", value=значение, updated_at=datetime.utcnow()))
    else:
        строка.value, строка.updated_at = значение, datetime.utcnow()
    db.commit()
    return {"ok": True}


# ── ПАКЕТ РОЛИКА (письмо B, блок 2) ───────────────────────────────────

class Пакет(BaseModel):
    idea_id: int
    again: bool = False


class Блок(BaseModel):
    block: str


def _ответ(итог: dict):
    if итог.get("error"):
        return JSONResponse({"error": итог["error"]}, status_code=итог.get("code", 400))
    return итог


@router.post("/content/api/package/build")
async def package_build(тело: Пакет, user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not _админ(user):
        return JSONResponse({"error": ОТКАЗ_НЕ_АДМИНУ}, status_code=403)
    return _ответ(cp.начать(db, тело.idea_id, заново=тело.again))


@router.get("/content/api/package/{pid}/state")
async def package_state(pid: int, user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not _админ(user):
        return JSONResponse({"error": ОТКАЗ_НЕ_АДМИНУ}, status_code=403)
    п = db.get(cdb.ContentPackage, pid)
    if п is None:
        return JSONResponse({"error": "пакета нет"}, status_code=404)
    return {"state": п.state, "steps": cdb.из_json(п.steps, []) or [], "note": п.note, "cost": п.cost}


@router.post("/content/api/package/{pid}/rewrite")
async def package_rewrite(pid: int, тело: Блок, user=Depends(get_current_user),
                          db: Session = Depends(get_db)):
    if not _админ(user):
        return JSONResponse({"error": ОТКАЗ_НЕ_АДМИНУ}, status_code=403)
    return _ответ(cp.переписать_блок(db, pid, тело.block))


@router.post("/content/api/package/{pid}/shoot")
async def package_shoot(pid: int, user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not _админ(user):
        return JSONResponse({"error": ОТКАЗ_НЕ_АДМИНУ}, status_code=403)
    return _ответ(cp.отметить_снимаю(db, pid))


@router.get("/content/package/{pid}/download")
async def package_md(pid: int, user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not _админ(user):
        return PlainTextResponse(ОТКАЗ_НЕ_АДМИНУ, status_code=403)
    п = db.get(cdb.ContentPackage, pid)
    if п is None or п.state == "running" or not п.data:
        return PlainTextResponse("пакет не готов", status_code=404)
    return Response(cp.в_markdown(п).encode("utf-8"), media_type="text/markdown; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="package-{pid}.md"'})


def данные_пакета(db, п, user) -> dict:
    зона = _main()._пояс(user)
    д = cdb.из_json(п.data, {}) or {}
    по_id = {}
    for с in д.get("sources") or []:
        по_id[с["id"]] = с
    р = db.get(ContentVideo, п.video_id) if п.video_id else None
    return {"страница": {"icon": "file-text", "label": "Контент · пакет ролика",
                         "title": (д.get("idea") or {}).get("title") or "Пакет ролика"},
            "п": {"id": п.id, "idea_id": п.idea_id, "state": п.state, "note": п.note, "kind": п.kind,
                  "когда": _время(п.finished_at or п.created_at, зона),
                  "cost": п.cost, "steps": cdb.из_json(п.steps, []) or []},
            "д": д, "источник_по_id": по_id, "блоки": cp.БЛОКИ,
            "ролик": ({"status": р.status, "статус": ci.СТАТУСЫ.get(р.status, р.status)} if р else None),
            "проверь": sum(1 for с in д.get("script") or [] for л in с["lines"] if л.get("check"))}


@router.get("/content/package/{pid}")
async def package_page(pid: int, request: Request, user=Depends(get_current_user),
                       db: Session = Depends(get_db)):
    if not _админ(user):
        return PlainTextResponse(ОТКАЗ_НЕ_АДМИНУ, status_code=403)
    п = db.get(cdb.ContentPackage, pid)
    if п is None:
        return PlainTextResponse("Пакета нет", status_code=404)
    контекст = {"user": user, **данные_пакета(db, п, user)}
    return _main().templates.TemplateResponse(request=request, name="content_package.html",
                                              context=контекст)


def _старт():
    ce.старт()


router.add_event_handler("startup", _старт)
