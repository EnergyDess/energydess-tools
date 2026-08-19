"""Критерий «досье хватает, чтобы написать письмо».

Почему на это есть тесты. Условие решает, что человек видит на вкладке:
галочку или «нет». Прежнее жило в браузере, было ИЛИ по трём полям
и загоралось от одного заполненного поля из четырнадцати — то есть
показывало готовность там, где её нет. Ошибка такого рода немая: экран
не ломается, консоль чистая, врёт только смысл.

Проверяется ровно граница — какие поля обязательны и какие нет, включая
пары «одно из двух». Разбор с обоснованием по каждому полю — в докстроке
самой dossier_ready и в BACKLOG.md, задача 58.

main.py тянет базу, миграции и шаблоны, поэтому импортируется один раз
и ради одной функции; сама она чистая и в базу не ходит.

DB_PATH УВОДИТСЯ В tmp — хотя этому файлу база не нужна вовсе.

Причина в том, КОГДА он импортирует main. Файлы собираются по алфавиту,
и `test_dossier_ready` — первый, кто тянет main; путь к базе `database`
читает один раз при импорте, а значит выбор, сделанный здесь, действует
НА ВЕСЬ ПРОГОН. Без этой строки выбором становилось умолчание `./app.db`,
то есть локальная рабочая база разработчика: все остальные модули
выставляли свой DB_PATH уже впустую.

Что это давало (замер 2026-08-19, чистый прогон на нетронутом дереве):
восемь ошибок `UNIQUE constraint failed: scale_connections.user_id` —
строки, оставшиеся в app.db от прошлых оборванных прогонов. Плюс отказ
другого вида: новая колонка `weight_logs` в app.db не появлялась, потому
что ALTER-миграции живут в `migrate_db()`, а тесты зовут только
`init_db()` с `create_all` — а тот к СУЩЕСТВУЮЩЕЙ таблице колонку
не добавляет. То есть прогон падал на схеме, которой в коде уже нет.

`setdefault`, а не присваивание: если DB_PATH задан снаружи, решение
принимает тот, кто его задал.
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("AGENT_WEBHOOK_KEY", "test-key-8f3a91")
os.environ.setdefault("DB_PATH",
                      str(Path(tempfile.gettempdir()) / "hh_tests_общая.db"))

from main import dossier_ready   # noqa: E402


class Досье:
    """Профиль с любым набором полей. Отдельный класс, а не HHProfile:
    настоящая модель потребовала бы сессии SQLAlchemy, а функция читает
    только атрибуты."""

    ПОЛЯ = ("profession_one_liner", "location", "timezone", "work_format",
            "languages", "total_years_in_profession", "experience_extra",
            "projects", "skills", "methodology", "extra_context",
            "tone_preference", "never_mention", "ending_style")

    def __init__(self, **значения):
        for имя in self.ПОЛЯ:
            setattr(self, имя, None)
        self.languages = []
        self.experience_extra = []
        self.projects = []
        self.skills = []
        for имя, зн in значения.items():
            assert имя in self.ПОЛЯ, f"нет такого поля: {имя}"
            setattr(self, имя, зн)


ПРОЕКТ = {"title": "energydess.ru", "url": "https://energydess.ru"}
РАБОТА = {"company": "Фриланс", "position": "AI-разработчик"}
ПОЛНОЕ = dict(profession_one_liner="AI Video Creator",
              skills=["Python", "FastAPI"],
              projects=[ПРОЕКТ])


def test_профиля_нет_вовсе():
    """Досье не заведено — не «пусто», а именно None. Так приходит
    пользователь, который ни разу не открывал вкладку."""
    assert dossier_ready(None) is False


def test_пустое_досье():
    assert dossier_ready(Досье()) is False


def test_полное_досье():
    assert dossier_ready(Досье(**ПОЛНОЕ)) is True


# ── Каждое из трёх обязательных — по отдельности ─────────────────────────────

def test_без_позиционирования():
    поля = dict(ПОЛНОЕ, profession_one_liner=None)
    assert dossier_ready(Досье(**поля)) is False


def test_позиционирование_из_пробелов():
    """Строка из пробелов — не заполненное поле. Проверяется отдельно:
    `bool(" ")` истинно, и без .strip() пробел давал бы галочку."""
    поля = dict(ПОЛНОЕ, profession_one_liner="   ")
    assert dossier_ready(Досье(**поля)) is False


def test_без_навыков():
    поля = dict(ПОЛНОЕ, skills=[])
    assert dossier_ready(Досье(**поля)) is False


def test_без_фактуры_вовсе():
    """Ни проектов, ни опыта — модели нечего рассказать сверх резюме."""
    поля = dict(ПОЛНОЕ, projects=[], experience_extra=[])
    assert dossier_ready(Досье(**поля)) is False


# ── Пара «одно из двух»: проекты ИЛИ опыт ────────────────────────────────────

def test_только_проекты():
    поля = dict(ПОЛНОЕ, projects=[ПРОЕКТ], experience_extra=[])
    assert dossier_ready(Досье(**поля)) is True


def test_только_опыт():
    поля = dict(ПОЛНОЕ, projects=[], experience_extra=[РАБОТА])
    assert dossier_ready(Досье(**поля)) is True


def test_проект_без_названия_не_считается():
    """Строку проекта заводит кнопка «добавить», и пустая заготовка
    остаётся в JSON, если её не заполнили. Заготовка — не фактура."""
    поля = dict(ПОЛНОЕ, projects=[{"title": "", "url": ""}], experience_extra=[])
    assert dossier_ready(Досье(**поля)) is False


def test_опыт_без_компании_и_должности_не_считается():
    поля = dict(ПОЛНОЕ, projects=[],
                experience_extra=[{"company": "", "position": "", "period": "2024"}])
    assert dossier_ready(Досье(**поля)) is False


def test_опыт_только_с_должностью_считается():
    """Достаточно одного из двух: фриланс без названия компании — обычный
    случай, и требовать оба поля значило бы держать галочку выключенной."""
    поля = dict(ПОЛНОЕ, projects=[],
                experience_extra=[{"company": "", "position": "AI-разработчик"}])
    assert dossier_ready(Досье(**поля)) is True


# ── Одиннадцать необязательных: их отсутствие галочку не гасит ───────────────

def test_необязательные_поля_не_влияют():
    """Полное досье минус ВСЕ поля, объявленные необязательными, — галочка
    остаётся. Проверяется одним тестом на весь список, а не по одному:
    важно именно то, что ни одно из них не попало в условие по недосмотру."""
    необязательные = ("location", "timezone", "work_format", "languages",
                      "total_years_in_profession", "methodology",
                      "extra_context", "tone_preference", "never_mention",
                      "ending_style")
    д = Досье(**ПОЛНОЕ)
    for имя in необязательные:
        setattr(д, имя, [] if имя == "languages" else None)
    assert dossier_ready(д) is True


def test_старое_условие_не_вернулось():
    """Одно заполненное поле из четырнадцати — это НЕ готовое досье.
    Ровно так вело себя условие до 2026-08-11 (ИЛИ по трём полям),
    и тест стоит здесь, чтобы возврат к нему был виден сразу."""
    assert dossier_ready(Досье(profession_one_liner="AI Video Creator")) is False
    assert dossier_ready(Досье(skills=["Python"])) is False
    assert dossier_ready(Досье(projects=[ПРОЕКТ])) is False
