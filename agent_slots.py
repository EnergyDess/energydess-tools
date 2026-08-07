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

ЗАНЯТОСТЬ СЛОТОВ ЗДЕСЬ СИНТЕТИЧЕСКАЯ. Настоящего календаря встреч у модуля
нет, и появиться ему неоткуда — состояния мы не храним. Занятость считается
хешем от строки «дата час»: функция чистая, один и тот же слот всегда даёт
один и тот же ответ, поэтому два запроса подряд не противоречат друг другу
и агенту не приходится извиняться за передумавший сервер. Когда появится
настоящий календарь, менять придётся ровно две функции — `slot_is_busy`
и `free_hours`; всё остальное про них не знает.
"""

import hashlib
import os
import random
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
EARLY_BEFORE_HOUR = 12           # утренний вариант обязан быть раньше этого часа
LATE_AFTER_HOUR = 14             # дневной — позже этого

# Доля занятых слотов и нижняя граница свободных в дне. Доля вынесена
# константой, а не зашита в условие: это единственная ручка, которой
# настраивается «загруженность календаря», и искать её придётся именно здесь.
BUSY_SHARE = 0.40
MIN_FREE_SLOTS = 4

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


def working_hours() -> List[int]:
    """Все часы, в которые встреча в принципе может начаться."""
    return list(range(WORK_START_HOUR, WORK_END_HOUR + 1))


# ─────────────────────────── Занятость слотов ───────────────────────────

def _digest(ключ: str) -> int:
    """Число из sha256. Ключ — только латиница и цифры (CLAUDE.md, §6.0).

    Хеш взят криптографический, а не встроенный `hash()`: последний солится
    случайным значением на каждый запуск процесса (PYTHONHASHSEED), и «чистая
    функция» разъезжалась бы после каждого рестарта — то есть ровно то, чего
    мы избегаем, только незаметно.
    """
    return int.from_bytes(hashlib.sha256(ключ.encode("ascii")).digest()[:8], "big")


def slot_is_busy(day: _date, hour: int) -> bool:
    """Занят ли слот. Чистая функция от даты и часа, без состояния.

    ВНИМАНИЕ: это не настоящий календарь, а его правдоподобная имитация —
    см. шапку модуля. Здесь только «сырой» ответ хеша; наружу ходить надо
    через `free_hours`, которая ещё и держит минимум свободных слотов в дне.
    """
    return _digest(f"{day:%Y-%m-%d} {hour:02d}") % 10_000 < BUSY_SHARE * 10_000


def free_hours(day: _date) -> List[int]:
    """Свободные часы дня по возрастанию. Для выходного — пустой список.

    Хеш независим по слотам, поэтому день, где занято почти всё, не просто
    возможен, а неизбежен на горизонте месяцев: при доле 0.4 и девяти слотах
    свободных остаётся меньше четырёх примерно в 10% дней (замерено на десяти
    годах календаря: 256 дней из 2607). Это раз в две недели, когда агенту
    почти нечего предложить. Поэтому снизу стоит жёсткая граница: не хватило —
    освобождаем занятые по порядку, с раннего часа, пока не наберётся
    MIN_FREE_SLOTS. Гарантия и съедает разницу между BUSY_SHARE и фактической
    долей занятых (0.40 против 0.39).
    """
    if not is_working_day(day):
        return []
    все = working_hours()
    свободные = [h for h in все if not slot_is_busy(day, h)]
    if len(свободные) < MIN_FREE_SLOTS:
        for h in все:
            if h not in свободные:
                свободные.append(h)
                if len(свободные) >= MIN_FREE_SLOTS:
                    break
        свободные.sort()
    return свободные


def is_free(day: _date, hour: int) -> bool:
    """Занятость с учётом гарантии минимума — то, что видит внешний мир."""
    return hour in free_hours(day)


# ───────────────────────── Человеческая фраза ───────────────────────────

def _hours_word(n: int) -> str:
    """Склонение слова «час» по числу: 1 час, 2 часа, 5 часов."""
    if n % 10 == 1 and n % 100 != 11:
        return "час"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return "часа"
    return "часов"


def spoken_time(t: _time) -> str:
    """Время словами — так, как его должен произнести синтез речи.

    Цифровую запись «16:00» синтез читает как «шестнадцать ноль ноль»,
    и повтор нулей на слух превращается в «нуль-наль». Поэтому вслух идёт
    разговорная форма: «в 4 часа дня», «в 10 утра», «в полдень».

    Это касается ТОЛЬКО поля human. Идентификатор слота остаётся машинным
    (2026-08-10T16:00): его никто не произносит, а разбирает программа,
    и разговорная форма там была бы неразбираемой.

    Часы вне рабочего диапазона тоже разобраны, хотя сейчас недостижимы:
    границы приёма — константы, и в день, когда их подвинут, функция должна
    сказать правильно, а не промолчать неверно.
    """
    if t.minute:
        # Слот не на круглый час невозможен (is_working_hour это проверяет).
        # Если шаг когда-нибудь станет получасовым — лучше цифры, чем слова,
        # которые перестанут соответствовать времени.
        return f"в {t:%H:%M}"

    ч = t.hour
    if ч == 0:
        return "в полночь"
    if ч == 12:
        return "в полдень"

    циферблат = ч % 12 or 12
    if 5 <= ч <= 11:
        # «в 10 утра», а не «в 10 часов утра»: так говорят вслух.
        return f"в {циферблат} утра"
    if 18 <= ч <= 22:
        return f"в {циферблат} вечера"

    часть_суток = "дня" if 13 <= ч <= 17 else "ночи"   # ночь — это 23 и 1-4
    if циферблат == 1:
        return f"в час {часть_суток}"
    return f"в {циферблат} {_hours_word(циферблат)} {часть_суток}"

def human_phrase(dt: datetime, now: datetime,
                 with_date: bool = False, time_only: bool = False) -> str:
    """Фраза, которую агент произнесёт вслух.

    «завтра» подставляется только если дата — действительно следующий
    календарный день относительно now. Слово «сегодня» не используется
    никогда: сегодняшний день недоступен по определению, и произнести его
    значило бы предложить то, чего нет.

    Число и месяц добавляются, когда дата дальше чем через 6 дней (на слух
    «в понедельник» через полторы недели неотличимо от ближайшего) — либо
    когда об этом просит вызывающий: при подтверждении конкретной даты
    её проговаривают полностью, ради этого эндпоинт проверки и существует.

    `time_only` — второй вариант того же дня: одно время без дня недели.
    День, названный дважды подряд («в пятницу в 10:00 или в пятницу в 15:00»),
    звучит как автоответчик; человек в этом месте говорит «…или в 15:00».
    """
    clock = spoken_time(dt.time())
    if time_only:
        return clock

    days = (dt.date() - now.date()).days
    tomorrow = days == 1
    show_date = with_date or days > 6
    weekday = WEEKDAYS_ACC[dt.weekday()]

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
              with_date: bool = False, time_only: bool = False) -> Dict[str, str]:
    return {"id": slot_id(dt),
            "human": human_phrase(dt, now, with_date, time_only)}


def pick_two_hours(day: _date) -> List[int]:
    """Два разных свободных часа дня: сначала утро+день, иначе любые два.

    Выбор случайный, но детерминированный: генератор засеивается хешем даты,
    поэтому повторный запрос в тот же день вернёт те же два времени. Иначе
    собеседник, переспросивший «повторите, пожалуйста», услышал бы другое —
    и решил бы, что первое уже заняли, пока он думал.

    Разнесение обязательно: два соседних часа — это выбор без выбора. Если
    в одной из половин дня свободного часа нет, берём два любых свободных,
    но заведомо разных — минимум в четыре слота на день это позволяет всегда.
    """
    свободные = free_hours(day)
    rnd = random.Random(_digest(f"pick {day:%Y-%m-%d}"))

    утро = [h for h in свободные if h < EARLY_BEFORE_HOUR]
    день = [h for h in свободные if h > LATE_AFTER_HOUR]
    if утро and день:
        return [rnd.choice(утро), rnd.choice(день)]

    # Половина дня выпала целиком. Разносим как можем: два разных часа
    # из того, что осталось. Меньше двух там быть не может — MIN_FREE_SLOTS.
    return sorted(rnd.sample(свободные, 2))


def build_options(now: datetime, not_before: Optional[_date] = None) -> List[Dict[str, str]]:
    """Два предложения времени из свободных слотов ближайшего рабочего дня."""
    day = first_available_day(now.date(), not_before)
    часы = pick_two_hours(day)
    first = datetime.combine(day, _time(hour=часы[0]), tzinfo=TZ)
    second = datetime.combine(day, _time(hour=часы[1]), tzinfo=TZ)

    # Оба варианта в одном дне — день недели называется один раз, второй
    # вариант остаётся одним временем. Подробнее — в docstring human_phrase.
    один_день = first.date() == second.date()
    return [make_slot(first, now),
            make_slot(second, now, time_only=один_день)]


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
    try:
        not_before = parse_date(after, "after") if after is not None else None
    except HTTPException as e:
        # Отказ по формату — тоже вызов, и в логе он нужен: молча отброшенный
        # запрос выглядит как «агент не позвонил», а он звонил и получил 422.
        log_call("GET /api/agent/slots", {"after": after}, f"422 {e.detail}")
        raise
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
    входные = {"date": body.date, "time": body.time,
               "expected_weekday": body.expected_weekday}
    try:
        d = parse_date(body.date, "date")
        t = parse_time(body.time, "time")
    except HTTPException as e:
        log_call("POST /api/agent/slots/check", входные, f"422 {e.detail}")
        raise

    now = now_msk()
    today = now.date()
    dt = datetime.combine(d, t, tzinfo=TZ)

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

    # 6. Занятость — последней. Порядок не косметика: сказать «это время
    # занято» про субботу или про три часа ночи значит соврать и подтолкнуть
    # собеседника переспросить то же самое на час раньше.
    if not is_free(d, t.hour):
        return отказ("busy", "это время уже занято")

    # Дату проговариваем полностью — эндпоинт для того и нужен, чтобы
    # собеседник услышал и день недели, и число, и мог поправить.
    slot = make_slot(dt, now, with_date=True)
    log_call("POST /api/agent/slots/check", входные, f"ok=true slot={slot['id']}")
    return {"ok": True, "slot": slot}
