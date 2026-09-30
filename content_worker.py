"""ФОНОВЫЙ ИСПОЛНИТЕЛЬ ТЯЖЁЛЫХ ЗАДАЧ МОДУЛЯ «КОНТЕНТ».

Авария 2026-09-30: прогон археологии шёл задачей в цикле событий
веб-приложения, а планировщик, наткнувшись на занятый замок, крутился
без единой паузы (`_пропуск` синхронный, `await` не отдавал цикл) —
29 046 строк «skipped» за 6.5 минуты, одно ядро занято целиком,
/health не отвечал, машина считалась живой. Память при этом была
в норме (RSS 163 МБ из 459), то есть это не OOM.

Отсюда устройство:

  · тяжёлая задача (сбор, поиск каналов, археология, идеи) идёт
    в ОТДЕЛЬНОМ ПОТОКЕ со своим циклом событий (`asyncio.run`) и своими
    сессиями базы. Цикл событий веб-приложения ею не занят вовсе:
    синхронный разбор, запись в базу и медиана выстрела уходят в поток,
    GIL отдаётся каждые 5 мс, и запрос к сайту обслуживается между ними;
  · не процесс, и это замер (§5.8): второй процесс с `import main`
    на машине в 512 МБ уже клал прод — одно только приложение держит
    ~110–160 МБ;
  · ЗАМОК ОДИН на все тяжёлые задачи модуля, `threading.Lock`: второй
    запуск, пока идёт первый, — отказ словами, а не очередь и не второй
    прогон;
  · планировщик живёт в своём потоке тем же способом и берёт тот же
    замок; занят — ждёт, а не крутится.
"""
from __future__ import annotations

import asyncio
import contextvars
import threading
import time
import traceback
from datetime import datetime

_ЗАМОК = threading.Lock()
_ТЕКУЩЕЕ: dict = {"вид": None, "поток": None, "с": None}
_ПОТОКИ: dict = {}          # имя -> поток; ссылка для проб и планировщика

ИМЕНА = {"cycle": "сбор источников", "discover": "поиск каналов",
         "archaeology": "археология", "ideas": "генерация идей",
         "channels": "чистка каналов"}


def занят_другим() -> bool:
    """Идёт ли тяжёлая задача в ДРУГОМ потоке. Сама задача себе не помеха:
    внутри прогона `цикл()` спрашивает «занято ли» и не должна увидеть себя."""
    return _ЗАМОК.locked() and _ТЕКУЩЕЕ["поток"] != threading.get_ident()


def что_идёт() -> dict | None:
    if not _ЗАМОК.locked():
        return None
    return {"вид": _ТЕКУЩЕЕ["вид"], "с": _ТЕКУЩЕЕ["с"]}


def отказ_занято() -> str:
    т = что_идёт() or {}
    имя = ИМЕНА.get(т.get("вид"), т.get("вид") or "другой прогон")
    с = т.get("с")
    когда = (" (идёт %d мин)" % max(0, int((datetime.utcnow() - с).total_seconds() // 60))
             if с else "")
    return f"Сейчас идёт {имя}{когда} — дождитесь конца, второй прогон не запущен."


def _взять(вид: str, поток: int | None) -> bool:
    if not _ЗАМОК.acquire(blocking=False):
        return False
    _ТЕКУЩЕЕ.update(вид=вид, поток=поток, с=datetime.utcnow())
    return True


def _отдать() -> None:
    _ТЕКУЩЕЕ.update(вид=None, поток=None, с=None)
    _ЗАМОК.release()


def запустить(вид: str, фабрика, повод: str) -> dict:
    """Прогон кнопкой: отдельный поток, свой цикл событий. Ответ сразу."""
    if not _взять(вид, None):
        return {"ok": False, "busy": True, "error": отказ_занято()}

    def тело():
        _ТЕКУЩЕЕ["поток"] = threading.get_ident()
        начало = datetime.utcnow()
        try:
            asyncio.run(фабрика(повод))
        except BaseException as e:
            traceback.print_exc()
            _закрыть_брошенные(начало, f"{type(e).__name__}: {e}")
        finally:
            _отдать()

    поток = threading.Thread(target=тело, name=f"content-{вид}", daemon=True)
    _ПОТОКИ[вид] = поток
    поток.start()
    return {"ok": True}


def _закрыть_брошенные(начало: datetime, причина: str) -> None:
    """Прогон упал мимо своего `try` — строка «running» не должна остаться
    висеть: закрывается ошибкой с текстом."""
    try:
        import content_db as cdb
        from database import SessionLocal
        db = SessionLocal()
        try:
            for п in (db.query(cdb.ContentRun)
                      .filter(cdb.ContentRun.state == "running",
                              cdb.ContentRun.started_at >= начало).all()):
                п.state, п.finished_at = "error", datetime.utcnow()
                п.note = ((п.note or "") + " прерван: " + причина)[:2000]
            db.commit()
        finally:
            db.close()
    except Exception:
        traceback.print_exc()


async def выполнить(вид: str, фабрика, повод: str):
    """Прогон изнутри планировщика (он уже в своём потоке). Занято — None
    без строки в базе: планировщик подождёт и спросит снова."""
    if not _взять(вид, threading.get_ident()):
        return None
    try:
        return await фабрика(повод)
    finally:
        _отдать()


# ── ХОД ПРОГОНА В БАЗЕ ────────────────────────────────────────────────
# Номер прогона — переменная контекста: её ставит `_начать` движка, и она
# доезжает до сборщика в `content_collect`, не протаскиваясь аргументом.
ПРОГОН: contextvars.ContextVar = contextvars.ContextVar("content_run", default=None)
_ЭТАПЫ: dict = {}           # (прогон, этап) -> (момент начала этапа, последняя запись)
ЗАПИСЬ_НЕ_ЧАЩЕ_СЕК = 2.0


def ход(этап: str, сделано: int, всего: int | None = None, *, сразу: bool = False) -> None:
    """Этап, сделано из всего и оценка остатка — в `content_runs.progress`.
    Пишется не чаще раза в 2 с: частая запись сама стала бы нагрузкой.
    Сбой записи прогон не роняет — это показ, а не работа."""
    номер = ПРОГОН.get()
    if номер is None:
        return
    сейчас = time.monotonic()
    ключ = (номер, этап)
    начало, последняя = _ЭТАПЫ.get(ключ, (сейчас, 0.0))
    if ключ not in _ЭТАПЫ:
        for к in [к for к in _ЭТАПЫ if к[0] == номер]:
            _ЭТАПЫ.pop(к, None)
    конец = всего is not None and сделано >= всего
    if not (сразу or конец) and сейчас - последняя < ЗАПИСЬ_НЕ_ЧАЩЕ_СЕК:
        _ЭТАПЫ[ключ] = (начало, последняя)
        return
    _ЭТАПЫ[ключ] = (начало, сейчас)
    прошло = сейчас - начало
    осталось = (int(прошло / сделано * (всего - сделано))
                if всего and сделано and прошло > 1 and сделано < всего else None)
    данные = {"этап": этап, "сделано": int(сделано), "всего": всего,
              "осталось_сек": осталось, "обновлено": datetime.utcnow().isoformat()}
    try:
        import content_db as cdb
        from database import SessionLocal
        db = SessionLocal()
        try:
            прогон = db.get(cdb.ContentRun, номер)
            if прогон is not None and прогон.state == "running":
                прогон.progress = cdb.в_json(данные)
                db.commit()
        finally:
            db.close()
    except Exception as e:
        print(f"[content] ход прогона №{номер} не записан: {type(e).__name__}: {e}", flush=True)


def поток_планировщика(корутина_фабрика) -> threading.Thread:
    def тело():
        try:
            asyncio.run(корутина_фабрика())
        except BaseException:
            traceback.print_exc()
    поток = threading.Thread(target=тело, name="content-scheduler", daemon=True)
    _ПОТОКИ["планировщик"] = поток
    поток.start()
    return поток
