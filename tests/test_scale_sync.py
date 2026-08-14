"""Запись измерений с весов в дневник: `main._sync_scale`.

Почему тесты именно здесь. Все три проверяемых отказа МОЛЧАЛИ бы —
ни исключения, ни строки в логе, — и все три вылезают ровно на первом
заходе после привязки весов, когда подтягивается вся прежняя история
аккаунта, включая измерения, сделанные ДО покупки весов:

  · два взвешивания за один день давали ДВЕ строки дневника на одну дату
    (сессия открыта с autoflush=False, и добавленная строка не видна
    собственному же запросу);
  · из этих двух в дневник попадало САМОЕ СТАРОЕ — сервис отдаёт записи
    новейшими вперёд, и последним применялось утреннее;
  · пустая история и сбой формата выглядели одинаково — «синхронизировано: 0».

База не поднимается: DB_PATH уводится в tmp ДО импорта main.
"""

import os
import sys
import tempfile
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["DB_PATH"] = str(Path(tempfile.gettempdir()) / "hh_tests_весы.db")

import main            # noqa: E402
import zepp_client     # noqa: E402
from database import (ScaleConnection, SessionLocal, WeightLog,   # noqa: E402
                      init_db)

# Таблицы создаёт обработчик старта приложения, а тесты его не поднимают
init_db()

ПОЛНОЧЬ = int(time.mktime(time.strptime("2026-08-14", "%Y-%m-%d")))
ДАТА = "2026-08-14"
ПУСТО = {k: None for k in ("bmi", "water_pct", "muscle_rate_pct",
                           "bone_mass_kg", "visceral_fat", "bmr", "body_age")}


def измерение(час, вес, жир):
    return {"timestamp": ПОЛНОЧЬ + час * 3600, "weight_kg": вес,
            **{**ПУСТО, "body_fat_pct": жир}}


@pytest.fixture
def сессия(monkeypatch):
    # Шифрование в тестах не настроено, а _sync_scale расшифровывает токен
    # перед выборкой. Подменяем расшифровку, а не заводим ключ: ключ в тестах
    # означал бы, что тест проверяет ещё и crypto
    monkeypatch.setattr(main, "_decrypt_opt", lambda x: x)
    db = SessionLocal()
    conn = ScaleConnection(user_id=999001, encrypted_username="x",
                           encrypted_app_token="ТОКЕН", encrypted_zepp_user_id="1")
    db.add(conn)
    db.commit()
    yield db, conn
    db.query(WeightLog).filter(WeightLog.user_id == 999001).delete()
    db.query(ScaleConnection).filter(ScaleConnection.user_id == 999001).delete()
    db.commit()
    db.close()


def выдать(monkeypatch, записи):
    monkeypatch.setattr(zepp_client, "fetch_weight_records", lambda *a, **k: {
        "records": записи, "total": len(записи), "pages": 1,
        "dropped": {"weightType": 0, "без summary": 0, "без веса": 0},
        "host": "x"})


def строки(db):
    return (db.query(WeightLog).filter(WeightLog.user_id == 999001)
            .filter(WeightLog.log_date == ДАТА).all())


def test_два_взвешивания_за_день_дают_одну_строку(сессия, monkeypatch):
    db, conn = сессия
    выдать(monkeypatch, [измерение(21, 79.0, 19.0), измерение(8, 81.0, 21.0)])
    итог = main._sync_scale(db, conn)
    assert len(строки(db)) == 1, "две строки на одну дату — дубль в дневнике"
    assert итог["synced"] == 1, "счёт по дням, а не по записям"
    assert итог["fetched"] == 2


def test_в_дневник_попадает_последнее_измерение_дня(сессия, monkeypatch):
    """Сервис отдаёт новейшее первым, и без сортировки последним
    применялось утреннее — то есть человек видел не тот вес, который
    видел на весах вечером."""
    db, conn = сессия
    выдать(monkeypatch, [измерение(21, 79.0, 19.0), измерение(8, 81.0, 21.0)])
    main._sync_scale(db, conn)
    assert строки(db)[0].weight_kg == 79.0
    assert строки(db)[0].body_fat_pct == 19.0


def test_итог_не_зависит_от_порядка_прихода(сессия, monkeypatch):
    """Отрицательный контроль к тесту выше: если бы решал порядок в списке,
    обратный порядок дал бы другой вес."""
    db, conn = сессия
    выдать(monkeypatch, [измерение(8, 81.0, 21.0), измерение(21, 79.0, 19.0)])
    main._sync_scale(db, conn)
    assert строки(db)[0].weight_kg == 79.0


def test_ручная_запись_не_перетирается(сессия, monkeypatch):
    db, conn = сессия
    db.add(WeightLog(user_id=999001, log_date=ДАТА, weight_kg=77.7, source="manual"))
    db.commit()
    выдать(monkeypatch, [измерение(21, 79.0, 19.0)])
    итог = main._sync_scale(db, conn)
    assert строки(db)[0].weight_kg == 77.7
    assert строки(db)[0].source == "manual"
    assert итог["synced"] == 0


def test_пустая_история_это_норма_а_не_ошибка(сессия, monkeypatch):
    db, conn = сессия
    выдать(monkeypatch, [])
    итог = main._sync_scale(db, conn)
    assert итог["empty"] is True and итог["synced"] == 0
    assert conn.last_sync_status == "ok", "пустой аккаунт — не сбой"
    assert conn.last_sync_error is None


def test_измерение_до_привязки_без_состава_тела(сессия, monkeypatch):
    """Записи, заведённые в приложении руками до покупки весов, приходят
    без состава тела. Вес из них брать надо, а отсутствие процента жира
    ошибкой не является."""
    db, conn = сессия
    выдать(monkeypatch, [{"timestamp": ПОЛНОЧЬ + 9 * 3600, "weight_kg": 82.5,
                          **ПУСТО, "body_fat_pct": None}])
    итог = main._sync_scale(db, conn)
    assert итог["synced"] == 1
    assert строки(db)[0].weight_kg == 82.5
    assert строки(db)[0].body_fat_pct is None
    assert строки(db)[0].source == "zepp"


def test_изменившийся_формат_не_просит_пароль(сессия, monkeypatch):
    """ZeppProtocolError НЕ превращается в ScaleReauthNeeded: сменившийся
    формат чинится нашей правкой, а предложение ввести пароль заново
    гоняло бы человека по кругу без единого признака, что дело не в нём."""
    db, conn = сессия

    def сломано(*a, **k):
        raise zepp_client.ZeppProtocolError("в ответе нет поля items")

    monkeypatch.setattr(zepp_client, "fetch_weight_records", сломано)
    with pytest.raises(zepp_client.ZeppProtocolError):
        main._sync_scale(db, conn)


def test_протухший_токен_просит_пароль(сессия, monkeypatch):
    """Отрицательный контроль к тесту выше: этот отказ как раз обязан
    привести к повторному вводу пароля."""
    db, conn = сессия

    def протух(*a, **k):
        raise zepp_client.ZeppApiError("токен не принят")

    monkeypatch.setattr(zepp_client, "fetch_weight_records", протух)
    with pytest.raises(main.ScaleReauthNeeded):
        main._sync_scale(db, conn)
