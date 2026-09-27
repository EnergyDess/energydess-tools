"""Предупреждение о низком остатке OpenRouter (BACKLOG №346, блок 3).

Проверяется ЦЕПОЧКА, которую ведёт `balance.yml`: запуск скрипта →
решение → (отправка) → `--mark`. Остаток подменяется на месте запроса
к OpenRouter, всё остальное боевое: состояние на диске, расход из базы.
"""
import json
import os
import sqlite3
from datetime import datetime, time as _время, timedelta, timezone

# База тестов, а не рабочая: `database` ниже заводит движок по DB_PATH
os.environ.setdefault("DB_PATH", "./test_model_usage.db")

import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402

import balance_check as бк  # noqa: E402
import database  # noqa: E402


def _завести_таблицы(база):
    """Схема — ТА ЖЕ, что заводит приложение: таблицы создаются моделями
    SQLAlchemy, а не своим CREATE — своя копия разошлась бы молча."""
    движок = create_engine(f"sqlite:///{база}")
    database.Base.metadata.create_all(движок, tables=[
        database.Base.metadata.tables["model_usage"],
        database.Base.metadata.tables["balance_history"]])
    движок.dispose()


@pytest.fixture
def окружение(tmp_path, monkeypatch):
    база = tmp_path / "app.db"
    _завести_таблицы(база)
    conn = sqlite3.connect(база)
    conn.execute("INSERT INTO model_usage (created_at, tool, model, cost, ok, cost_missing) "
                 "VALUES (datetime('now'), 'hh-letter', 'm', 0.25, 1, 0)")
    conn.execute("INSERT INTO model_usage (created_at, tool, model, cost, ok, cost_missing) "
                 "VALUES ('2020-01-01 00:00:00', 'hh-letter', 'm', 9, 1, 0)")
    conn.commit(); conn.close()
    monkeypatch.setattr(бк, "DB_PATH", str(база))
    monkeypatch.setattr(бк, "СОСТОЯНИЕ", str(tmp_path / "balance_alert.json"))
    monkeypatch.setenv("OPENROUTER_API_KEY", "тест")
    остаток = {"usd": 10.0}
    monkeypatch.setattr(бк, "остаток_openrouter", lambda ключ, адрес=None: остаток["usd"])
    # расход_за_7_дней держит путь умолчанием — переподставляем
    monkeypatch.setattr(бк, "расход_за_7_дней",
                        lambda db_path=None, сейчас=None, _f=бк.расход_за_7_дней: _f(str(база)))
    return остаток


def запуск(capsys):
    """Один проход workflow: вывод скрипта и, если решено слать, отметка."""
    assert бк.main([]) == 0
    строка = next(с for с in capsys.readouterr().out.splitlines()
                  if с.startswith("BALANCE_JSON="))
    д = json.loads(строка[len("BALANCE_JSON="):])
    if д["send"]:
        assert бк.main(["--mark"]) == 0
        capsys.readouterr()
    return д


def test_остаток_2_сообщение_уходит(окружение, capsys):
    окружение["usd"] = 2.0
    д = запуск(capsys)
    assert д["send"] is True
    assert "остаток 2.00 $" in д["text"] and "0.25 $" in д["text"]
    assert д["spent7"] == {"usd": 0.25, "calls": 1}


def test_остаток_5_не_уходит(окружение, capsys):
    окружение["usd"] = 5.0
    assert запуск(capsys)["send"] is False


def test_два_запуска_при_2_сообщение_одно(окружение, capsys):
    окружение["usd"] = 2.0
    assert [запуск(capsys)["send"] for _ in range(2)] == [True, False]


def test_после_подъёма_новое_падение_снова_сообщает(окружение, capsys, monkeypatch):
    окружение["usd"] = 2.0
    assert запуск(capsys)["send"] is True
    окружение["usd"] = 12.0
    assert запуск(capsys)["send"] is False
    # новое падение — уже в другие сутки: предел «раз в сутки» не нарушен
    состояние = json.load(open(бк.СОСТОЯНИЕ, encoding="utf-8"))
    состояние["last_alert_day"] = "2000-01-01"
    json.dump(состояние, open(бк.СОСТОЯНИЕ, "w", encoding="utf-8"))
    окружение["usd"] = 1.0
    assert запуск(capsys)["send"] is True


def test_не_дошло_сообщение_завтра_повтор(окружение, capsys):
    """Telegram недоступен: отметки нет, взвод остаётся."""
    окружение["usd"] = 2.0
    assert бк.main([]) == 0
    capsys.readouterr()
    # отправка упала — workflow `--mark` не зовёт
    assert бк.main([]) == 0
    строка = capsys.readouterr().out
    assert '"send": true' in строка


def test_без_ключа_пропуск_кодом_2(окружение, monkeypatch, capsys):
    monkeypatch.delenv("OPENROUTER_API_KEY")
    assert бк.main([]) == 2
    assert "ПРОПУСК" in capsys.readouterr().out


@pytest.mark.parametrize("остаток,состояние,ждём", [
    (2.0, {}, True), (5.0, {}, False), (3.0, {}, False),
    (2.0, {"armed": False, "last_alert_day": "2026-09-17"}, False),
    (2.0, {"armed": True, "last_alert_day": "2026-09-18"}, False),
])
def test_решение(остаток, состояние, ждём):
    assert бк.решить(остаток, состояние, "2026-09-18", 3.0)[0] is ждём


# ── ИСТОРИЯ ОСТАТКА И ВСПЛЕСК РАСХОДА (№352, письмо «Расход», 1.1–1.2) ──

def _строк_истории():
    conn = sqlite3.connect(бк.DB_PATH)
    try:
        return conn.execute("SELECT COUNT(*) FROM balance_history").fetchone()[0]
    finally:
        conn.close()


def test_история_пополняется_и_дубля_в_те_же_сутки_нет(окружение, capsys):
    """1.1: запуск — строк в истории на одну больше; повтор в те же
    сутки дубля не создаёт. Поле `history` называет исход словом."""
    assert _строк_истории() == 0
    д1 = запуск(capsys)
    assert д1["history"] == "added" and _строк_истории() == 1
    д2 = запуск(capsys)
    assert д2["history"] == "exists" and _строк_истории() == 1


def test_история_без_таблицы_называет_это_а_не_падает(tmp_path, monkeypatch, capsys):
    база = tmp_path / "old.db"
    sqlite3.connect(база).close()
    assert бк.записать_историю(5.0, db_path=str(база)) == "no_table"


def _дни_расхода(база, суммы_по_смещению):
    """Строки учёта на полдень МСК суток `сегодня − смещение`."""
    сегодня = datetime.now(бк.ПОЯС).date()
    conn = sqlite3.connect(база)
    conn.execute("DELETE FROM model_usage")
    for смещение, сумма in суммы_по_смещению.items():
        д = сегодня - timedelta(days=смещение)
        момент = datetime.combine(д, _время(12), бк.ПОЯС).astimezone(timezone.utc)
        conn.execute("INSERT INTO model_usage (created_at, tool, model, cost, ok, cost_missing) "
                     "VALUES (?, 'hh-letter', 'm', ?, 1, 0)",
                     (момент.replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S.%f"), сумма))
    conn.commit()
    conn.close()


def test_всплеск_один_тяжёлый_день_оповещение_одно(окружение, capsys):
    """1.2: ряд обычных дней плюс вчерашний тяжёлый — оповещение ОДНО:
    второй запуск в те же сутки после отметки молчит."""
    окружение["usd"] = 10.0                    # остаток выше порога — только всплеск
    обычные = {i: 0.5 + 0.01 * i for i in range(2, 16)}   # 14 суток до вчера
    _дни_расхода(бк.DB_PATH, {**обычные, 1: 2.5})         # вчера: > 3 × медиана
    д1 = запуск(capsys)
    assert д1["alerts"] == ["spike"] and д1["send"] is True
    assert "расход за" in д1["text"] and "медиан" in д1["text"]
    д2 = запуск(capsys)
    assert д2["send"] is False and д2["spike"]["fired"] is True
    assert [д1["send"], д2["send"]].count(True) == 1


def test_ровный_ряд_оповещений_ноль(окружение, capsys):
    окружение["usd"] = 10.0
    _дни_расхода(бк.DB_PATH, {i: 0.5 for i in range(1, 16)})
    д = запуск(capsys)
    assert д["alerts"] == [] and д["spike"]["fired"] is False


def test_мало_дней_порог_молчит(окружение, capsys):
    """Шесть суток данных при нужных семи — молчит даже на тяжёлом дне."""
    окружение["usd"] = 10.0
    _дни_расхода(бк.DB_PATH, {**{i: 0.5 for i in range(2, 8)}, 1: 50.0})
    д = запуск(capsys)
    assert д["alerts"] == [] and д["spike"]["days"] == 6


def test_отметка_всплеска_не_снимает_взвод_остатка(окружение, capsys):
    """Слали только всплеск — взвод остатка остаётся: следующее падение
    остатка ниже порога даст своё сообщение."""
    окружение["usd"] = 10.0
    _дни_расхода(бк.DB_PATH, {**{i: 0.5 for i in range(2, 16)}, 1: 2.5})
    запуск(capsys)
    состояние = json.load(open(бк.СОСТОЯНИЕ, encoding="utf-8"))
    assert состояние["armed"] is True and состояние["spike_alert_day"]
    окружение["usd"] = 2.0
    д = запуск(capsys)
    assert д["alerts"] == ["balance"]


@pytest.mark.parametrize("суммы,ждём", [
    ({**{f"2026-09-{d:02d}": 1.0 for d in range(1, 15)}, "2026-09-15": 3.5}, True),
    ({**{f"2026-09-{d:02d}": 1.0 for d in range(1, 15)}, "2026-09-15": 3.0}, False),
    ({**{f"2026-09-{d:02d}": 0.0 for d in range(1, 15)}, "2026-09-15": 3.0}, False),
])
def test_всплеск_чистая_функция(суммы, ждём):
    строк = {д: 1 for д in суммы}
    assert бк.всплеск(суммы, строк, "2026-09-15")["сработал"] is ждём
