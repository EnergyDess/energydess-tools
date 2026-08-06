"""Календарные эндпоинты для голосового ИИ-агента (ElevenLabs).

Агент записывает посетителя на видеовстречу и НЕ считает даты сам: модель
регулярно ошибается в арифметике («в пятницу, семнадцатого» — а семнадцатое
понедельник). Вся календарная логика здесь, агент только произносит вслух
готовое поле `human` и присылает на проверку то, что назвал.

    GET  /api/agent/slots        — текущее время и два предложения
    POST /api/agent/slots/check  — проверка даты, которую агент посчитал сам

Состояния нет: ни базы, ни внешних вызовов, ни кэша. Это требование
производительности, а не аскеза — вебхук должен ответить меньше чем за
500 мс, иначе агент повиснет в паузе посреди разговора. Всё, что делает
модуль, — арифметика над датами.
"""

import os
import re
import secrets
from datetime import date as _date, datetime, time as _time, timedelta, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel

load_dotenv()

# ───────────────────────────── Ключ вебхука ─────────────────────────────

# Значения по умолчанию нет намеренно. Дефолт означал бы, что приложение
# поднимается с эндпоинтами, открытыми всему интернету, и узнать об этом
# было бы неоткуда: ошибки нет, роуты отвечают. Поэтому падаем на старте.
AGENT_WEBHOOK_KEY = os.getenv("AGENT_WEBHOOK_KEY", "").strip()
if not AGENT_WEBHOOK_KEY:
    raise RuntimeError(
        "AGENT_WEBHOOK_KEY не задан в окружении. По нему проверяется заголовок "
        "X-Agent-Key у вебхуков /api/agent/*; без ключа запускаться нельзя. "
        "Локально — строка в .env, на проде — flyctl secrets set AGENT_WEBHOOK_KEY=…"
    )

# ──────────────────────── Календарные константы ─────────────────────────

TZ = ZoneInfo("Europe/Moscow")   # часовой пояс встреч, не зависит от TZ сервера

WORK_START_HOUR = 9              # первое время начала встречи
WORK_END_HOUR = 17               # последнее время начала, включительно
MORNING_HOUR = 10                # первый предлагаемый вариант
AFTERNOON_HOUR = 15              # второй предлагаемый вариант
EARLY_BEFORE_HOUR = 12           # утренний вариант обязан быть раньше этого часа
LATE_AFTER_HOUR = 14             # дневной — позже этого

# Праздники не учитываем — осознанное упрощение. Производственный календарь
# России меняется постановлением правительства каждый год, и держать его
# в коде значит гарантированно разойтись с реальностью в январе. Правильное
# место для него — справочник с обновлением, а не константа в модуле.
# Следствие: 1 января (если будний) сервер предложит как рабочий день.

WEEKDAYS_NOM = ["понедельник", "вторник", "среда", "четверг",
                "пятница", "суббота", "воскресенье"]
# Винительный падеж вместе с предлогом: «во вторник» — единственная форма,
# где предлог не «в», поэтому храним связку целиком, а не склеиваем на месте.
WEEKDAYS_ACC = ["в понедельник", "во вторник", "в среду", "в четверг",
                "в пятницу", "в субботу", "в воскресенье"]
MONTHS_GEN = ["января", "февраля", "марта", "апреля", "мая", "июня",
              "июля", "августа", "сентября", "октября", "ноября", "декабря"]

# Все формы, которые принимаем в expected_weekday. Агент присылает то, что
# произнёс вслух, а произносит он по-разному: «пятница», «в пятницу».
_WEEKDAY_FORMS: Dict[str, int] = {}
for _i, _nom in enumerate(WEEKDAYS_NOM):
    _acc_word = WEEKDAYS_ACC[_i].split(" ", 1)[1]          # «вторник» из «во вторник»
    for _form in (_nom, WEEKDAYS_ACC[_i], _acc_word,
                  f"в {_acc_word}", f"во {_acc_word}", f"в {_nom}", f"во {_nom}"):
        _WEEKDAY_FORMS[_form] = _i


# ───────────────────────────── Время «сейчас» ───────────────────────────

def now_msk() -> datetime:
    """Текущий момент в московском времени.

    Вынесено отдельной функцией ровно затем, чтобы тесты могли её подменить:
    `datetime.now(TZ)`, вызванный прямо в теле обработчика, заморозить нечем.
    """
    return datetime.now(TZ)


def now_utc() -> datetime:
    """Текущий момент в UTC — для отметки времени в логе."""
    return datetime.now(timezone.utc)


# ──────────────────────────────── Логи ──────────────────────────────────

def log_call(endpoint: str, params: Dict[str, Any], result: str) -> None:
    """Строка в лог на каждый вызов: время UTC, эндпоинт, вход, результат.

    Ключ доступа в лог не пишется никогда — ни целиком, ни куском.
    """
    stamp = now_utc().strftime("%Y-%m-%d %H:%M:%S")
    inputs = " ".join(f"{k}={v!r}" for k, v in params.items()) or "—"
    print(f"[agent] {stamp}Z {endpoint} | {inputs} | {result}", flush=True)


# ───────────────────────────── Авторизация ──────────────────────────────

def require_agent_key(
    request: Request,
    x_agent_key: Optional[str] = Header(default=None, alias="X-Agent-Key"),
) -> None:
    """Пускает только вебхуки с верным X-Agent-Key. Иначе 403.

    Сравнение через `secrets.compare_digest`: обычное `==` на строках
    выходит из цикла на первом несовпавшем символе, и по времени ответа
    ключ подбирается посимвольно.
    """
    ok = bool(x_agent_key) and secrets.compare_digest(
        x_agent_key.encode("utf-8"), AGENT_WEBHOOK_KEY.encode("utf-8")
    )
    if not ok:
        причина = "заголовок отсутствует" if not x_agent_key else "ключ не совпал"
        log_call(request.url.path, {"X-Agent-Key": причина}, "403 отказ")
        raise HTTPException(
            status_code=403,
            detail="Доступ запрещён: неверный или отсутствующий заголовок X-Agent-Key",
        )


router = APIRouter(
    prefix="/api/agent",
    tags=["agent"],
    dependencies=[Depends(require_agent_key)],
)


# ──────────────────────── Календарная арифметика ────────────────────────

def is_working_day(d: _date) -> bool:
    """Понедельник-пятница. weekday(): 0 — понедельник, 5 и 6 — выходные."""
    return d.weekday() < 5


def next_working_day(d: _date) -> _date:
    """Ближайший рабочий день СТРОГО после переданного."""
    d += timedelta(days=1)
    while not is_working_day(d):
        d += timedelta(days=1)
    return d


def first_available_day(today: _date, not_before: Optional[_date] = None) -> _date:
    """Ближайший день, на который можно записаться.

    Сегодняшний день недоступен всегда, независимо от текущего времени:
    встречу надо успеть подтвердить и подготовить. Поэтому отсчёт идёт
    со следующего календарного дня, а дальше пропускаются выходные.
    `not_before` (параметр after у эндпоинта) может отодвинуть дату вперёд,
    но не приблизить: минимум — следующий рабочий день.
    """
    d = today + timedelta(days=1)
    if not_before is not None and not_before > d:
        d = not_before
    while not is_working_day(d):
        d += timedelta(days=1)
    return d


def is_working_hour(t: _time) -> bool:
    """Время начала встречи: с 09:00 до 17:00 включительно, шаг ровно час."""
    return WORK_START_HOUR <= t.hour <= WORK_END_HOUR and t.minute == 0


# ───────────────────────── Человеческая фраза ───────────────────────────

def human_phrase(dt: datetime, now: datetime,
                 with_date: bool = False, allow_tomorrow: bool = True) -> str:
    """Фраза, которую агент произнесёт вслух.

    «завтра» подставляется только если дата — действительно следующий
    календарный день относительно now. Слово «сегодня» не используется
    никогда: сегодняшний день недоступен по определению, и произнести его
    значило бы предложить то, чего нет.

    Число и месяц добавляются, когда дата дальше чем через 6 дней (на слух
    «в понедельник» через полторы недели неотличимо от ближайшего) — либо
    когда об этом просит вызывающий: при подтверждении конкретной даты
    её проговаривают полностью, ради этого эндпоинт проверки и существует.
    """
    days = (dt.date() - now.date()).days
    tomorrow = allow_tomorrow and days == 1
    show_date = with_date or days > 6
    weekday = WEEKDAYS_ACC[dt.weekday()]
    clock = f"в {dt:%H:%M}"

    if not tomorrow and not show_date:
        return f"{weekday} {clock}"

    parts: List[str] = []
    if tomorrow:
        parts.append("завтра")
    parts.append(weekday)
    if show_date:
        parts.append(f"{dt.day} {MONTHS_GEN[dt.month - 1]}")
    parts.append(clock)
    return ", ".join(parts)


def slot_id(dt: datetime) -> str:
    """Машинный идентификатор варианта: 2026-08-07T10:00."""
    return f"{dt:%Y-%m-%dT%H:%M}"


def make_slot(dt: datetime, now: datetime,
              with_date: bool = False, allow_tomorrow: bool = True) -> Dict[str, str]:
    return {"id": slot_id(dt),
            "human": human_phrase(dt, now, with_date, allow_tomorrow)}


def build_options(now: datetime, not_before: Optional[_date] = None) -> List[Dict[str, str]]:
    """Два предложения времени: утро и день ближайшего доступного дня."""
    day = first_available_day(now.date(), not_before)
    first = datetime.combine(day, _time(hour=MORNING_HOUR), tzinfo=TZ)
    second = datetime.combine(day, _time(hour=AFTERNOON_HOUR), tzinfo=TZ)

    # Варианты обязаны быть разнесены: один до 12:00, другой после 14:00 —
    # иначе человеку предлагается выбор без выбора. При нынешних константах
    # (10 и 15) условие выполняется всегда; проверка стоит на случай, если
    # часы поменяют, и тогда второй вариант уезжает на следующий рабочий день,
    # а не молча превращается в дубль первого.
    разнесены = (first.hour < EARLY_BEFORE_HOUR
                 and second.hour > LATE_AFTER_HOUR
                 and is_working_hour(first.time())
                 and is_working_hour(second.time()))
    if not разнесены:
        second = datetime.combine(next_working_day(day),
                                  _time(hour=AFTERNOON_HOUR), tzinfo=TZ)

    # «завтра» произносится один раз. Обе фразы идут подряд в одной реплике
    # («завтра, в пятницу, в 10:00 или в пятницу в 15:00»), и повтор звучит
    # как речь робота — которым агент как раз старается не звучать.
    один_день = first.date() == second.date()
    return [make_slot(first, now),
            make_slot(second, now, allow_tomorrow=not один_день)]


# ──────────────────────────── Разбор ввода ──────────────────────────────

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME_RE = re.compile(r"^\d{1,2}:\d{2}$")


def parse_date(raw: Optional[str], field: str) -> _date:
    """YYYY-MM-DD или 422 с внятным объяснением, что именно не так."""
    if raw is None or not str(raw).strip():
        raise HTTPException(status_code=422,
                            detail=f"Не передано поле {field}: нужна дата в формате ГГГГ-ММ-ДД, например 2026-08-07")
    raw = str(raw).strip()
    if not _DATE_RE.match(raw):
        raise HTTPException(status_code=422,
                            detail=f"Поле {field}: дата должна быть в формате ГГГГ-ММ-ДД, например 2026-08-07. Получено: {raw}")
    try:
        return _date.fromisoformat(raw)
    except ValueError:
        raise HTTPException(status_code=422,
                            detail=f"Поле {field}: такой даты не существует. Получено: {raw}")


def parse_time(raw: Optional[str], field: str) -> _time:
    """ЧЧ:ММ или 422. Диапазон часов проверяется отдельно, это только формат."""
    if raw is None or not str(raw).strip():
        raise HTTPException(status_code=422,
                            detail=f"Не передано поле {field}: нужно время в формате ЧЧ:ММ, например 15:00")
    raw = str(raw).strip()
    if not _TIME_RE.match(raw):
        raise HTTPException(status_code=422,
                            detail=f"Поле {field}: время должно быть в формате ЧЧ:ММ, например 15:00. Получено: {raw}")
    try:
        return _time.fromisoformat(raw if len(raw) == 5 else f"0{raw}")
    except ValueError:
        raise HTTPException(status_code=422,
                            detail=f"Поле {field}: такого времени не существует. Получено: {raw}")


def parse_weekday(raw: Optional[str]) -> Optional[int]:
    """Индекс дня недели из того, что произнёс агент. None — не опознали.

    Регистр не важен, «ё» приравнивается к «е», хвостовая пунктуация
    отбрасывается: агент присылает кусок собственной реплики.
    """
    if raw is None:
        return None
    s = str(raw).strip().lower().replace("ё", "е").strip(".,!?;:«»\"'")
    s = re.sub(r"\s+", " ", s)
    return _WEEKDAY_FORMS.get(s)


# ────────────────────────────── Эндпоинт 1 ──────────────────────────────

@router.get("/slots")
def get_slots(request: Request, after: Optional[str] = Query(default=None)) -> Dict[str, Any]:
    """Текущее время и два предложения для встречи.

    `after` (ГГГГ-ММ-ДД) сдвигает поиск вперёд — например, когда собеседник
    сказал «не раньше следующей недели». Приблизить дату он не может.
    """
    not_before = parse_date(after, "after") if after is not None else None
    now = now_msk()
    options = build_options(now, not_before)

    log_call("GET /api/agent/slots", {"after": after},
             "варианты: " + ", ".join(o["id"] for o in options))

    return {
        "now": {
            "date": f"{now:%Y-%m-%d}",
            "weekday": WEEKDAYS_NOM[now.weekday()],
            "time": f"{now:%H:%M}",
            "tz": "Europe/Moscow",
        },
        "options": options,
    }


# ────────────────────────────── Эндпоинт 2 ──────────────────────────────

class CheckRequest(BaseModel):
    """Тело POST /api/agent/slots/check.

    Все три поля объявлены необязательными нарочно: пропущенное поле должно
    получить такой же понятный русский 422, как и поле кривого формата,
    а не служебный текст pydantic на английском.
    """
    date: Optional[str] = None
    time: Optional[str] = None
    expected_weekday: Optional[str] = None


@router.post("/slots/check")
def check_slot(request: Request, body: CheckRequest) -> Dict[str, Any]:
    """Сверяет дату, которую агент посчитал сам, с календарём.

    Смысл эндпоинта: агент называет собеседнику день словами («в пятницу»)
    и присылает дату, которую под этим словом имел в виду. Расхождение между
    произнесённым и посчитанным — самая частая ошибка модели, и ловится она
    только так. Причина возвращается первая сработавшая, в порядке проверок.
    """
    d = parse_date(body.date, "date")
    t = parse_time(body.time, "time")
    now = now_msk()
    today = now.date()
    dt = datetime.combine(d, t, tzinfo=TZ)

    входные = {"date": body.date, "time": body.time,
               "expected_weekday": body.expected_weekday}

    def отказ(reason: str, hint: str) -> Dict[str, Any]:
        # Альтернативы отдаём ВСЕГДА: агент, оставшийся без вариантов,
        # начинает их выдумывать — ровно то, ради чего сервер и считает даты.
        # Ищем от запрошенной даты, а не от сегодня: человек уже назвал,
        # когда ему удобно, и предлагать более ранний день нет смысла.
        alternatives = build_options(now, d)
        log_call("POST /api/agent/slots/check", входные,
                 f"ok=false reason={reason}")
        return {"ok": False, "reason": reason, "hint": hint,
                "alternatives": alternatives}

    # 1. День недели, произнесённый вслух, против реального дня этой даты.
    expected = parse_weekday(body.expected_weekday)
    real = d.weekday()
    if expected != real:
        дата_словами = f"{d.day} {MONTHS_GEN[d.month - 1]}"
        if expected is None:
            hint = f"{дата_словами} — это {WEEKDAYS_NOM[real]}"
        else:
            hint = (f"{дата_словами} — это {WEEKDAYS_NOM[real]}, "
                    f"а не {WEEKDAYS_NOM[expected]}")
        return отказ("weekday_mismatch", hint)

    # 2-3. Прошедшая и сегодняшняя дата. Сегодня недоступно всегда,
    # даже в девять утра: это правило записи, а не нехватка времени.
    if d < today:
        return отказ("past", "эта дата уже прошла")
    if d == today:
        return отказ("today", "на сегодня записаться нельзя, ближайшая встреча — со следующего рабочего дня")

    # 4. Выходные.
    if not is_working_day(d):
        return отказ("weekend", f"{WEEKDAYS_NOM[real]} — нерабочий день")

    # 5. Часы приёма.
    if not is_working_hour(t):
        if t.minute != 0:
            hint = "встречи начинаются в начале часа, например в 15:00"
        else:
            hint = f"встречи назначаем с {WORK_START_HOUR}:00 до {WORK_END_HOUR}:00"
        return отказ("outside_hours", hint)

    # Дату проговариваем полностью — эндпоинт для того и нужен, чтобы
    # собеседник услышал и день недели, и число, и мог поправить.
    slot = make_slot(dt, now, with_date=True)
    log_call("POST /api/agent/slots/check", входные, f"ok=true slot={slot['id']}")
    return {"ok": True, "slot": slot}
