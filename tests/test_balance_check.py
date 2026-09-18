"""Предупреждение о низком остатке OpenRouter (BACKLOG №346, блок 3).

Проверяется ЦЕПОЧКА, которую ведёт `balance.yml`: запуск скрипта →
решение → (отправка) → `--mark`. Остаток подменяется на месте запроса
к OpenRouter, всё остальное боевое: состояние на диске, расход из базы.
"""
import json
import sqlite3

import pytest

import balance_check as бк


@pytest.fixture
def окружение(tmp_path, monkeypatch):
    база = tmp_path / "app.db"
    conn = sqlite3.connect(база)
    conn.execute("CREATE TABLE model_usage (id INTEGER PRIMARY KEY, created_at TEXT, cost REAL)")
    conn.execute("INSERT INTO model_usage (created_at, cost) VALUES (datetime('now'), 0.25)")
    conn.execute("INSERT INTO model_usage (created_at, cost) VALUES ('2020-01-01 00:00:00', 9)")
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
