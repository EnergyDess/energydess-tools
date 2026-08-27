# -*- coding: utf-8 -*-
"""Раздел тренировок считает «сегодня» в поясе ПОЛЬЗОВАТЕЛЯ (BACKLOG №186).

ЧТО БЫЛО. Шестнадцать мест раздела брали день через `datetime.now()` —
то есть в поясе ПРОЦЕССА. На Fly `TZ=UTC`, и подход, записанный в 01:30
по Москве, ложился ВЧЕРАШНИМ числом: «тренировался сегодня» отвечало
про другой день, график сдвигался, а признака ошибки не было никакого.
Тот же класс, что девять источников в дневнике (§5.0.6), взвешивания
(§5.2) и `/workout/profile` (задача 174).

ЛОКАЛЬНО ДЕФЕКТ НЕ ВОСПРОИЗВОДИТСЯ: на машине разработчика пояс
процесса — Москва, и `datetime.now()` там даёт верный день. Поэтому
часы здесь ПОДМЕНЯЮТСЯ, а пояса перебираются ЯВНО — ровно как
в `test_scale_sync` и `test_nutrition_timezone`. Прогон в три часа дня
о поведении в 00:30 не говорит ничего.

═══════════════════════════════════════════════════════════════════════
ПОЧЕМУ ПРОВЕРОК ДВЕ, И ОДНОЙ НЕ ХВАТАЕТ

  СТРУКТУРНАЯ  закрывает КЛАСС: `datetime.now()` без пояса в `main.py`
               не должно остаться ни одного, а каждое из шестнадцати
               мест обязано брать день у `_сегодня`. Без неё
               семнадцатое место, дописанное завтра, вернуло бы дефект
               молча — перечень мест был бы перечнем, из которого
               однажды выпадет одно (§6.0.7).

  ЖИВАЯ        доказывает, что цепочка РАБОТАЕТ: подход, записанный
               в 00:30 по местному, ложится СЕГОДНЯШНИМ числом,
               а не вчерашним. Структурная этого не говорит: она
               видит имя функции, а не то, что она вернёт.

Обе стороны границы проверяются обязательно. Восточнее Гринвича
местный день ОБГОНЯЕТ UTC (00:30 MSK = 21:30 UTC вчерашних суток),
западнее — ОТСТАЁТ (17:30 в Лос-Анджелесе = 00:30 UTC завтрашних).
Проверь мы одну сторону — правка «прибавить смещение» прошла бы.
"""
import ast
import io
import os
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("AGENT_WEBHOOK_KEY", "test-key-8f3a91")
os.environ.setdefault("DB_PATH",
                      str(Path(tempfile.gettempdir()) / "hh_tests_общая.db"))

import main                                                    # noqa: E402
from auth import create_token, hash_password                   # noqa: E402
from database import (Exercise, SessionLocal, User,            # noqa: E402
                      WorkoutProgram, WorkoutProgramDay,
                      WorkoutProgramExercise, WorkoutSession)
from fastapi.testclient import TestClient                      # noqa: E402

ИСХОДНИК = Path(__file__).resolve().parent.parent / "main.py"

# ШЕСТНАДЦАТЬ МЕСТ. Перечень здесь ЗАКОННЫЙ и закрывает не множество,
# а ИСКЛЮЧЕНИЯ из него: множество «все места, считающие день» ловит
# структурный тест ниже признаком, а этот список отвечает на другой
# вопрос — «а те ли места починены, что назвал замер».
#
# Их 16, а не 12, как стояло в постановке задачи 186: тот замер считал
# только обработчики и пропустил три помощника (`_mesocycle_info`,
# `_determine_today_day_id`, `_serialize_program`) и подсказку тренера
# `_shorten_today_guidance`. Замер главнее постановки.
МЕСТА = [
    "_mesocycle_info", "_determine_today_day_id", "_serialize_program",
    "workout_generate_program", "workout_day_state", "workout_log_set",
    "workout_skip", "workout_complete", "workout_set_light_day",
    "workout_return_check", "workout_return_plan", "workout_swap_exercise",
    "workout_refresh_program", "_workout_nutrition_summary",
    "_shorten_today_guidance", "workout_chat",
]


def _функции():
    дерево = ast.parse(io.open(ИСХОДНИК, encoding="utf-8").read())
    из = {}
    for узел in ast.walk(дерево):
        if isinstance(узел, (ast.FunctionDef, ast.AsyncFunctionDef)):
            из.setdefault(узел.name, []).append(узел)
    return из


def _вызовы_без_пояса(узел):
    """`datetime.now()` / `.today()` БЕЗ аргумента — день процесса.

    Обходом дерева, а не грепом: греп посчитал бы вызовом и строку
    в комментарии, и цитату в docstring (§6.0.2, довод проверки 7).
    """
    из = []
    for n in ast.walk(узел):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr in ("now", "today")
                and getattr(n.func.value, "id", None) == "datetime"
                and not n.args and not n.keywords):
            из.append(n.lineno)
    return из


# ── СТРУКТУРНАЯ ПОЛОВИНА: КЛАСС, А НЕ ЭКЗЕМПЛЯР ─────────────────────

def test_во_всём_main_нет_дня_процесса():
    """Ни одного `datetime.now()` без пояса — во ВСЁМ файле.

    Не только в тренировках: класс закрывается целиком, иначе
    следующий обработчик заведёт его заново в другом разделе.
    `datetime.utcnow()` под запрет НЕ ПОПАДАЕТ — это метка времени
    в колонке, законный ход.
    """
    дерево = ast.parse(io.open(ИСХОДНИК, encoding="utf-8").read())
    плохие = _вызовы_без_пояса(дерево)
    assert not плохие, ("день процесса в main.py, строки: %s" % плохие)


@pytest.mark.parametrize("имя", МЕСТА)
def test_место_берёт_день_у_сегодня(имя):
    """Каждое из шестнадцати мест ходит через `_сегодня`.

    Либо зовёт её само, либо получает уже посчитанный день параметром
    (`log_date` у обработчиков, `today` у помощников) — и тогда день
    считает вызывающий. Второго способа узнать «сегодня» в разделе
    быть не должно (§5.0.6).
    """
    функции = _функции()
    assert имя in функции, "функция %s исчезла из main.py" % имя
    for узел in функции[имя]:
        текст = ast.unparse(узел)
        assert "_сегодня(" in текст, (
            "%s не берёт день у `_сегодня` — второй источник дня" % имя)
        assert not _вызовы_без_пояса(узел), (
            "%s считает день в поясе процесса" % имя)


# ── ЖИВАЯ ПОЛОВИНА: ПОДХОД ЛОЖИТСЯ В МЕСТНЫЙ ДЕНЬ ───────────────────

class ЧасыСтоят:
    """Подменённый `datetime` main-а: `now` отдаёт назначенный момент.

    Подменяется ИМЕННО `main.datetime`, потому что `_сегодня` берёт
    момент через него. Остальное поведение класса наследуется — иначе
    сломались бы `strptime`, `timedelta` и запись меток.
    """

    def __init__(self, момент_utc):
        self.момент = момент_utc

    def __getattr__(self, имя):
        return getattr(datetime, имя)

    def now(self, tz=None):
        return self.момент.astimezone(tz) if tz else self.момент.replace(
            tzinfo=None)

    def utcnow(self):
        return self.момент.replace(tzinfo=None)


def _завести(db, пояс):
    u = User(email="wk-tz-%s@local.test" % uuid.uuid4().hex[:8],
             password_hash=hash_password("Pa$$w0rd-локальный"),
             is_verified=True, timezone=пояс)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _программа(db, uid):
    """Минимальная связка «программа → день → упражнение».

    Меньше не бывает: `workout_log_set` ищет день программы и
    упражнение в справочнике, и без них не дойдёт до записи дня.
    """
    прог = WorkoutProgram(user_id=uid, active=True, structure="full_body",
                          days_per_week=3)
    db.add(прог)
    db.flush()
    день = WorkoutProgramDay(program_id=прог.id, day_index=0,
                             day_type="full_body", label="День A")
    db.add(день)
    db.flush()
    упр = db.query(Exercise).first()
    if not упр:
        упр = Exercise(id="tz-test-ex", name="Squat", name_ru="Приседания",
                       level="beginner", category="strength",
                       equipment="barbell")
        db.add(упр)
        db.flush()
    db.add(WorkoutProgramExercise(day_id=день.id, exercise_id=упр.id,
                                  order=0, target_sets=3,
                                  rep_low=8, rep_high=12))
    db.commit()
    return день.id, упр.id


@pytest.mark.parametrize("момент_utc, пояс, ожидание, что", [
    # ВОСТОЧНЕЕ ГРИНВИЧА: местный день ОБГОНЯЕТ UTC.
    # Ровно тот час, в который дефект и жил, — 00:30 по Москве
    ("2026-08-26 21:30", "Europe/Moscow", "2026-08-27", "00:30 по Москве"),
    ("2026-08-26 20:30", "Europe/Moscow", "2026-08-26", "23:30 по Москве"),
    # ЗАПАДНЕЕ: местный день ОТСТАЁТ. Без этой стороны правка
    # «прибавить смещение» прошла бы
    ("2026-08-27 00:30", "America/Los_Angeles", "2026-08-26",
     "17:30 в Лос-Анджелесе"),
    ("2026-08-27 07:30", "America/Los_Angeles", "2026-08-27",
     "00:30 в Лос-Анджелесе"),
])
def test_подход_ложится_в_местный_день(monkeypatch, момент_utc, пояс,
                                       ожидание, что):
    main.init_db()
    # СХЕМА ДОГОНЯЕТСЯ, а не предполагается готовой: временная база общая
    # у всех тестов и переживает заходы, а ALTER-миграции живут в
    # `migrate_db`, которую зовёт старт приложения (тесты его не поднимают)
    main.migrate_db()
    db = SessionLocal()
    try:
        u = _завести(db, пояс)
        день_id, упр_id = _программа(db, u.id)
        uid = u.id
    finally:
        db.close()

    момент = datetime.strptime(момент_utc, "%Y-%m-%d %H:%M").replace(
        tzinfo=timezone.utc)
    monkeypatch.setattr(main, "datetime", ЧасыСтоят(момент))

    c = TestClient(main.app)
    c.cookies.set("access_token", create_token(uid))
    r = c.post("/workout/api/log-set",
               json={"program_day_id": день_id, "exercise_id": упр_id,
                     "sets": [{"reps": 10, "weight_kg": 50}]})
    assert r.status_code == 200, r.text

    db = SessionLocal()
    try:
        строки = [s.log_date for s in db.query(WorkoutSession)
                  .filter(WorkoutSession.user_id == uid).all()]
    finally:
        db.close()
    assert строки == [ожидание], (
        "%s: подход лёг в %s, а должен в %s" % (что, строки, ожидание))


def test_день_процесса_дал_бы_ДРУГОЙ_ответ():
    """ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ САМОЙ ПРОВЕРКИ (§6.0.3).

    Без него «подход лёг в 27-е» ничего не доказывает: 27-е мог бы
    дать и день процесса. Здесь замеряется, что на выбранном моменте
    два ответа РАЗНЫЕ, — то есть проверка вообще способна различить
    исправный код и прежний.
    """
    момент = datetime(2026, 8, 26, 21, 30, tzinfo=timezone.utc)
    часы = ЧасыСтоят(момент)

    class Человек:
        id = 1
        timezone = "Europe/Moscow"

    было = часы.now().strftime("%Y-%m-%d")          # день ПРОЦЕССА
    стало = main._день_в_поясе(момент, ZoneInfo("Europe/Moscow")).isoformat()
    assert было != стало, ("на этом моменте два способа совпадают — "
                           "проверка не различает")
    assert (было, стало) == ("2026-08-26", "2026-08-27")
