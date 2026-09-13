"""Заслон тела запроса: объявление приёма у каждого места, где читается
файл, и отказ гостю без прочитанного тела (задача 327).

Живой замер байт на диске — `py check_upload_guard.py`; здесь сторожится
то, что ломается МОЛЧА: новый маршрут с файлом, забывший объявление.
Такой маршрут не станет дырой (заслон даст ему предел ТЕЛО_БЕЗ_ФАЙЛА),
но законная загрузка на нём упадёт 413 у человека, а не в тесте."""
import inspect
import os
import tempfile
from pathlib import Path

os.environ.setdefault("DB_PATH",
                      str(Path(tempfile.gettempdir()) / "hh_tests_общая.db"))

import main  # noqa: E402
from fastapi.routing import APIRoute  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def _места_с_файлом():
    места = []
    for маршрут in main.app.routes:
        if not isinstance(маршрут, APIRoute):
            continue
        ф = маршрут.endpoint
        подпись = inspect.signature(ф)
        файл = any("UploadFile" in str(п.annotation) for п in подпись.parameters.values())
        try:
            форма = ".form()" in inspect.getsource(ф)
        except OSError:
            форма = False
        if файл or форма:
            места.append(маршрут)
    return места


def test_места_с_файлом_найдены():
    # Пустой сбор не равен успеху: без мест тест ниже прошёл бы на всём.
    assert len(_места_с_файлом()) >= 11


def test_каждое_место_с_файлом_объявило_приём():
    без = [м.path for м in _места_с_файлом()
           if getattr(м.endpoint, main.ПРИЁМ_АТРИБУТ, None) is None]
    assert без == [], "маршрут читает файл без @приём_файла: %s" % без


def test_гостю_каждое_объявление_отказывает():
    db = main.SessionLocal()
    try:
        for м in _места_с_файлом():
            права, предел = getattr(м.endpoint, main.ПРИЁМ_АТРИБУТ)
            пп = {"slot_id": "feed-1-1", "set_id": "x", "item_id": "1"}
            assert права(None, db, пп) is not None, м.path
            assert предел(пп) > 0, м.path
    finally:
        db.close()


def test_предел_без_файла_равен_порогу_записи_на_диск():
    import starlette.formparsers as f
    assert main.ТЕЛО_БЕЗ_ФАЙЛА == f.MultiPartParser.spool_max_size


def test_гость_получает_отказ_не_дочитав_тело():
    """Тело — генератор, считающий, сколько из него забрали. Отказ по правам
    обязан наступить раньше, чем приложение возьмёт хоть один кусок."""
    взято = []

    def тело():
        for _ in range(40):
            взято.append(1)
            yield b"\0" * 256 * 1024

    клиент = TestClient(main.app)
    о = клиент.post("/api/avatar", content=тело(),
                    headers={"content-type": "multipart/form-data; boundary=x"})
    assert о.status_code == 401
    assert len(взято) <= 1, "приложение прочло %d кусков тела до отказа" % len(взято)


def test_длина_сверх_предела_без_файла_413():
    клиент = TestClient(main.app)
    о = клиент.post("/api/delete-account", content=b"a" * (main.ТЕЛО_БЕЗ_ФАЙЛА + 10),
                    headers={"content-type": "application/x-www-form-urlencoded"})
    assert о.status_code == 413
