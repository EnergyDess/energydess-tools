"""ПРИЁМ НАХОДОК ИЗ БОТА ВТОРОГО МОЗГА (письмо D1, задача 383).

Владелец пересылает своему Telegram-боту пост канала, ссылку или идею
(текстом либо голосом), бот шлёт это машинным входом `POST /content/inbox`,
а «Сегодня» показывает карточками «от тебя». Telegram-каналы модуль сам
не читает и читать не будет — ни через t.me/s, ни через Telethon (условия
Telegram, §5.11): пост попадает сюда только тогда, когда владелец сам
переслал его боту.

Вход машинный, не страница: токен в заголовке (`X-Inbox-Token` либо
`Authorization: Bearer …`), сверка в постоянном времени, не больше
`ЛИМИТ_В_ЧАС` запросов в час с одного адреса — счёт в общем журнале
попыток (`login_attempts`), а не в памяти процесса (§8.1).

Дубль — та же `tg_message_id` либо та же ссылка за `ДУБЛЬ_ДНЕЙ`: новой
записи нет, ответ ok с номером существующей. Вызовов моделей здесь нет.
"""
import os
import re
import secrets
from datetime import datetime, timedelta
from urllib.parse import urlsplit

import content_db as cdb
import content_ideas as ci
from content_db import ContentIdea, ContentInbox, ContentItem, ContentLink, ContentStory, ContentTheme

ВИДЫ_ВХОДА = {"forward": "пересланный пост", "link": "ссылка", "idea": "идея"}
ТЕКСТ_МАКС = 8000
ЛИМИТ_В_ЧАС = int(os.getenv("CONTENT_INBOX_PER_HOUR", "60"))
ДУБЛЬ_ДНЕЙ = 7
КОРОТКО = 200
ЗАГОЛОВОК_МАКС = 90


def токен_верен(присланный: str | None) -> bool:
    """Сверка в постоянном времени. Токена в окружении нет — вход закрыт
    для всех: пустая строка против пустой строки совпала бы."""
    настоящий = (os.getenv("CONTENT_INBOX_TOKEN") or "").strip()
    присланный = (присланный or "").strip()
    if not настоящий or not присланный:
        return False
    return secrets.compare_digest(присланный.encode("utf-8"), настоящий.encode("utf-8"))


def токен_из(заголовки) -> str | None:
    т = заголовки.get("x-inbox-token")
    if т:
        return т
    а = заголовки.get("authorization") or ""
    return а[7:] if а.lower().startswith("bearer ") else None


def _строка(v, макс: int) -> str | None:
    if v is None:
        return None
    if not isinstance(v, (str, int, float)):
        return None
    т = str(v).strip()
    return т[:макс] or None


def разобрать(тело) -> tuple[dict | None, str | None]:
    """(поля, ошибка). Длинный текст обрезается до `ТЕКСТ_МАКС`; у идеи
    пустой текст — ошибка; у пересланного поста и ссылки нужен текст
    либо ссылка."""
    if not isinstance(тело, dict):
        return None, "ждём JSON-объект"
    вид = тело.get("kind")
    if вид not in ВИДЫ_ВХОДА:
        return None, "kind: forward | link | idea"
    текст = тело.get("text")
    текст = str(текст).strip()[:ТЕКСТ_МАКС] if isinstance(текст, str) else ""
    ссылка = _строка(тело.get("url"), 2000)
    if ссылка and not re.match(r"^https?://[^\s/]+", ссылка):
        return None, "url: нужна ссылка http(s)://"
    if вид == "idea" and not текст:
        return None, "у идеи пустой текст"
    if вид == "link" and not ссылка:
        return None, "у ссылки нет url"
    if not текст and not ссылка:
        return None, "нет ни текста, ни ссылки"
    слух = тело.get("rumor", False)
    if not isinstance(слух, bool):
        return None, "rumor: true | false"
    return {"kind": вид, "text": текст or None, "url": ссылка,
            "source_name": _строка(тело.get("source_name"), 200),
            "source_date": _строка(тело.get("source_date"), 40),
            "rumor": слух, "tg_message_id": _строка(тело.get("tg_message_id"), 64)}, None


def ключ_ссылки(url: str | None) -> str:
    """Ссылка без схемы, www, хвостового слеша и меток utm — для сверки
    дублей и совпадения с записями радара."""
    if not url:
        return ""
    ч = urlsplit(url.strip())
    хост = (ч.netloc or "").lower()
    хост = хост[4:] if хост.startswith("www.") else хост
    запрос = "&".join(п for п in (ч.query or "").split("&") if п and not п.lower().startswith("utm_"))
    return хост + (ч.path or "").rstrip("/") + ("?" + запрос if запрос else "")


def найти_дубль(db, поля: dict) -> ContentInbox | None:
    порог = datetime.utcnow() - timedelta(days=ДУБЛЬ_ДНЕЙ)
    свежие = db.query(ContentInbox).filter(ContentInbox.created_at >= порог)
    if поля.get("tg_message_id"):
        д = свежие.filter(ContentInbox.tg_message_id == поля["tg_message_id"]).first()
        if д is not None:
            return д
    ключ = ключ_ссылки(поля.get("url"))
    if ключ:
        for з in свежие.filter(ContentInbox.url.isnot(None)):
            if ключ_ссылки(з.url) == ключ:
                return з
    return None


def принять(db, поля: dict) -> tuple[int, bool]:
    """(номер записи, дубль ли)."""
    дубль = найти_дубль(db, поля)
    if дубль is not None:
        return дубль.id, True
    з = ContentInbox(**поля, state="new", created_at=datetime.utcnow())
    db.add(з)
    db.commit()
    return з.id, False


def сюжет_по_ссылке(db, url: str | None) -> dict | None:
    """«Уже в сюжете»: ссылка совпала с записью, собранной радаром, либо со
    ссылкой из её описания (`content_links`). Новых механизмов нет — это
    сверка по уже собранному."""
    ключ = ключ_ссылки(url)
    if not ключ:
        return None
    ядро = ключ.split("?")[0]
    сюжеты = set()
    for и in db.query(ContentItem).filter(ContentItem.url.contains(ядро), ContentItem.story_id.isnot(None)):
        if ключ_ссылки(и.url) == ключ:
            сюжеты.add(и.story_id)
    if not сюжеты:
        записи = [л.item_id for л in db.query(ContentLink).filter(ContentLink.url.contains(ядро))
                  if ключ_ссылки(л.url) == ключ]
        if записи:
            сюжеты |= {и.story_id for и in db.query(ContentItem).filter(ContentItem.id.in_(записи))
                       if и.story_id}
    if not сюжеты:
        return None
    с = db.query(ContentStory).filter(ContentStory.id.in_(сюжеты)).order_by(ContentStory.id.desc()).first()
    return {"id": с.id, "title": с.title} if с else None


def заголовок(з: ContentInbox) -> str:
    """Название идеи из находки: первая строка текста, иначе источник
    и ссылка — модель не зовётся."""
    первая = (з.text or "").strip().split("\n", 1)[0].strip()
    if not первая:
        первая = (з.source_name or "") + (" — " if з.source_name else "") + (з.url or "Находка")
    return первая if len(первая) <= ЗАГОЛОВОК_МАКС else первая[:ЗАГОЛОВОК_МАКС - 1].rstrip() + "…"


def в_работу(db, номер: int) -> dict:
    """«В работу»: находка становится идеей конвейера вида «от тебя»
    (sort=user) и сразу ложится в план — текст стал описанием, ссылка —
    источником. Повторное нажатие не плодит идей."""
    з = db.get(ContentInbox, номер)
    if з is None:
        return {"error": "находки нет", "code": 404}
    if з.state == "work" and з.idea_id:
        return {"ok": True, "idea_id": з.idea_id}
    тема = (db.query(ContentTheme).filter(ContentTheme.active.is_(True)).order_by(ContentTheme.id).first())
    if тема is None:
        return {"error": "темы нет", "code": 409}
    сейчас = datetime.utcnow()
    сюжет = сюжет_по_ссылке(db, з.url)
    идея = ContentIdea(theme_id=тема.id, run_id=None, created_at=сейчас, kind="long", sort="user",
                       title=заголовок(з), why=з.text,
                       story_id=сюжет["id"] if сюжет else None,
                       facts=cdb.в_json({"официально": False} if з.rumor else {}),
                       basis=cdb.в_json({"inbox": з.id, "url": з.url, "source": з.source_name,
                                         "kind": з.kind, "rumor": з.rumor}),
                       risks=cdb.в_json(["rumor"] if з.rumor else []), state="new", text_by="owner")
    db.add(идея)
    db.flush()
    з.state, з.idea_id, з.acted_at = "work", идея.id, сейчас
    итог = ci.реакция(db, идея.id, "plan")
    db.commit()
    return {"ok": True, "idea_id": идея.id, "video_id": итог.get("video_id")}


def убрать(db, номер: int) -> dict:
    """«Убрать» — в архив, не удаление."""
    з = db.get(ContentInbox, номер)
    if з is None:
        return {"error": "находки нет", "code": 404}
    з.state, з.acted_at = "archived", datetime.utcnow()
    db.commit()
    return {"ok": True}


def карточки(db, время) -> list[dict]:
    """Карточки «от тебя» для «Сегодня» — только новые, свежие сверху.
    `время` — функция подписи момента в поясе владельца."""
    итог = []
    for з in db.query(ContentInbox).filter(ContentInbox.state == "new").order_by(ContentInbox.created_at.desc(),
                                                                                  ContentInbox.id.desc()):
        текст = з.text or ""
        итог.append({"id": з.id, "kind": з.kind, "вид": ВИДЫ_ВХОДА.get(з.kind, з.kind),
                     "коротко": текст if len(текст) <= КОРОТКО else текст[:КОРОТКО].rstrip() + "…",
                     "полностью": текст if len(текст) > КОРОТКО else None,
                     "url": з.url, "источник": з.source_name, "дата": з.source_date,
                     "rumor": bool(з.rumor), "когда": время(з.created_at),
                     "сюжет": сюжет_по_ссылке(db, з.url)})
    return итог
