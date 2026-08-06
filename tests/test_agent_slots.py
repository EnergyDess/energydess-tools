"""Тесты календарных эндпоинтов агента.

Время заморожено во всех тестах, где оно влияет на ответ: тест, который
проходит только по будням до обеда, — не тест, а ловушка для следующего.

Опорные даты августа 2026 (сверено календарём):
    03 пн · 04 вт · 05 ср · 06 чт · 07 пт · 08 сб · 09 вс · 10 пн · 17 пн
"""

from conftest import KEY, auth


# ─────────────────────────── 9-10. Авторизация ──────────────────────────

def test_неверный_ключ_403(client):
    # Значение заголовка — латиницей: в HTTP заголовки байтовые, кириллица
    # в них не проходит ещё на стороне клиента (см. CLAUDE.md, §6.0).
    r = client.get("/api/agent/slots", headers={"X-Agent-Key": "wrong-key"})
    assert r.status_code == 403

    r = client.post("/api/agent/slots/check",
                    headers={"X-Agent-Key": "wrong-key"},
                    json={"date": "2026-08-07", "time": "15:00",
                          "expected_weekday": "пятница"})
    assert r.status_code == 403


def test_без_заголовка_403(client):
    assert client.get("/api/agent/slots").status_code == 403
    assert client.post("/api/agent/slots/check",
                       json={"date": "2026-08-07", "time": "15:00",
                             "expected_weekday": "пятница"}).status_code == 403


def test_ключ_отличается_длиной_403(client):
    """compare_digest не должен спотыкаться на строках разной длины."""
    assert client.get("/api/agent/slots",
                      headers={"X-Agent-Key": KEY + "x"}).status_code == 403
    assert client.get("/api/agent/slots",
                      headers={"X-Agent-Key": KEY[:-1]}).status_code == 403


def test_пустой_заголовок_403(client):
    assert client.get("/api/agent/slots",
                      headers={"X-Agent-Key": ""}).status_code == 403


# ──────────────────── 1-3, 8. Выбор ближайшего дня ──────────────────────

def test_1_пятница_вечер_даёт_понедельник(client, freeze):
    """Пятница 18:00 → понедельник. Суббота и воскресенье пропускаются."""
    freeze("2026-08-07T18:00")
    r = client.get("/api/agent/slots", headers=auth())
    assert r.status_code == 200
    данные = r.json()
    assert [o["id"] for o in данные["options"]] == ["2026-08-10T10:00",
                                                    "2026-08-10T15:00"]
    assert "суббот" not in str(данные["options"]).lower()


def test_2_пятница_утро_тоже_понедельник(client, freeze):
    """Пятница 10:00 — до конца рабочего дня далеко, но сегодня недоступно."""
    freeze("2026-08-07T10:00")
    r = client.get("/api/agent/slots", headers=auth())
    assert [o["id"] for o in r.json()["options"]] == ["2026-08-10T10:00",
                                                      "2026-08-10T15:00"]


def test_3_среда_утро_даёт_четверг_со_словом_завтра(client, freeze):
    """Среда 08:00 → четверг, и это действительно завтра."""
    freeze("2026-08-05T08:00")
    данные = client.get("/api/agent/slots", headers=auth()).json()
    assert [o["id"] for o in данные["options"]] == ["2026-08-06T10:00",
                                                    "2026-08-06T15:00"]
    assert "завтра" in данные["options"][0]["human"]
    assert данные["options"][0]["human"] == "завтра, в четверг, в 10:00"
    assert данные["options"][1]["human"] == "в четверг в 15:00"


def test_8_варианты_разнесены(client, freeze):
    """Один вариант до 12:00, второй после 14:00 — в любой день недели."""
    for момент in ("2026-08-03T09:00", "2026-08-05T13:00", "2026-08-07T18:00",
                   "2026-08-08T11:00", "2026-08-09T23:59"):
        freeze(момент)
        options = client.get("/api/agent/slots", headers=auth()).json()["options"]
        часы = [int(o["id"][11:13]) for o in options]
        assert часы[0] < 12, момент
        assert часы[1] > 14, момент


def test_сегодня_недоступно_никогда(client, freeze):
    """В 00:01 впереди целый рабочий день — и он всё равно недоступен."""
    freeze("2026-08-05T00:01")
    options = client.get("/api/agent/slots", headers=auth()).json()["options"]
    assert all(o["id"].startswith("2026-08-06") for o in options)


def test_блок_now(client, freeze):
    freeze("2026-08-06T15:42")
    now = client.get("/api/agent/slots", headers=auth()).json()["now"]
    assert now == {"date": "2026-08-06", "weekday": "четверг",
                   "time": "15:42", "tz": "Europe/Moscow"}


def test_слово_сегодня_не_произносится(client, freeze):
    freeze("2026-08-05T09:00")
    assert "сегодня" not in str(client.get("/api/agent/slots",
                                           headers=auth()).json()).lower()


# ───────────────────────── Параметр after ───────────────────────────────

def test_after_сдвигает_вперёд(client, freeze):
    freeze("2026-08-06T10:00")
    данные = client.get("/api/agent/slots?after=2026-08-17", headers=auth()).json()
    assert [o["id"] for o in данные["options"]] == ["2026-08-17T10:00",
                                                    "2026-08-17T15:00"]


def test_after_дальше_шести_дней_проговаривает_число(client, freeze):
    freeze("2026-08-06T10:00")
    данные = client.get("/api/agent/slots?after=2026-08-17", headers=auth()).json()
    assert данные["options"][0]["human"] == "в понедельник, 17 августа, в 10:00"


def test_after_на_выходной_переносится_на_понедельник(client, freeze):
    freeze("2026-08-06T10:00")
    данные = client.get("/api/agent/slots?after=2026-08-08", headers=auth()).json()
    assert all(o["id"].startswith("2026-08-10") for o in данные["options"])


def test_after_в_прошлом_не_приближает_дату(client, freeze):
    """after не может дать дату раньше следующего рабочего дня."""
    freeze("2026-08-06T10:00")
    данные = client.get("/api/agent/slots?after=2020-01-01", headers=auth()).json()
    assert all(o["id"].startswith("2026-08-07") for o in данные["options"])


def test_after_кривого_формата_422(client, freeze):
    freeze("2026-08-06T10:00")
    r = client.get("/api/agent/slots?after=06.08.2026", headers=auth())
    assert r.status_code == 422
    assert "ГГГГ-ММ-ДД" in r.json()["detail"]


# ──────────────────────────── check: отказы ─────────────────────────────

def test_4_суббота_weekend_с_альтернативами(client, freeze):
    freeze("2026-08-06T10:00")
    r = client.post("/api/agent/slots/check", headers=auth(),
                    json={"date": "2026-08-08", "time": "15:00",
                          "expected_weekday": "суббота"})
    данные = r.json()
    assert данные["ok"] is False
    assert данные["reason"] == "weekend"
    assert данные["hint"] == "суббота — нерабочий день"
    assert [a["id"] for a in данные["alternatives"]] == ["2026-08-10T10:00",
                                                         "2026-08-10T15:00"]
    assert данные["alternatives"][0]["human"] == "в понедельник в 10:00"


def test_5_сегодня(client, freeze):
    freeze("2026-08-06T09:00")
    данные = client.post("/api/agent/slots/check", headers=auth(),
                         json={"date": "2026-08-06", "time": "15:00",
                               "expected_weekday": "четверг"}).json()
    assert данные["reason"] == "today"
    assert данные["alternatives"]


def test_прошедшая_дата(client, freeze):
    freeze("2026-08-06T09:00")
    данные = client.post("/api/agent/slots/check", headers=auth(),
                         json={"date": "2026-08-05", "time": "15:00",
                               "expected_weekday": "среда"}).json()
    assert данные["reason"] == "past"
    # Альтернативы считаются от сегодня, а не от прошедшей даты.
    assert [a["id"] for a in данные["alternatives"]] == ["2026-08-07T10:00",
                                                         "2026-08-07T15:00"]


def test_6_день_недели_не_совпал(client, freeze):
    """Дата рабочая и будущая, но агент назвал её другим днём."""
    freeze("2026-08-06T09:00")
    данные = client.post("/api/agent/slots/check", headers=auth(),
                         json={"date": "2026-08-07", "time": "15:00",
                               "expected_weekday": "среда"}).json()
    assert данные["ok"] is False
    assert данные["reason"] == "weekday_mismatch"
    assert данные["hint"] == "7 августа — это пятница, а не среда"
    assert данные["alternatives"]


def test_день_недели_проверяется_раньше_остальных(client, freeze):
    """Суббота, названная пятницей: первой срабатывает weekday_mismatch."""
    freeze("2026-08-06T09:00")
    данные = client.post("/api/agent/slots/check", headers=auth(),
                         json={"date": "2026-08-08", "time": "15:00",
                               "expected_weekday": "пятница"}).json()
    assert данные["reason"] == "weekday_mismatch"


def test_день_недели_принимает_обе_формы_и_регистр(client, freeze):
    freeze("2026-08-06T09:00")
    for форма in ("пятница", "в пятницу", "Пятница", "  В ПЯТНИЦУ  ", "пятницу"):
        данные = client.post("/api/agent/slots/check", headers=auth(),
                             json={"date": "2026-08-07", "time": "15:00",
                                   "expected_weekday": форма}).json()
        assert данные["ok"] is True, форма


def test_день_недели_вторник_с_предлогом_во(client, freeze):
    freeze("2026-08-06T09:00")
    for форма in ("вторник", "во вторник"):
        данные = client.post("/api/agent/slots/check", headers=auth(),
                             json={"date": "2026-08-11", "time": "10:00",
                                   "expected_weekday": форма}).json()
        assert данные["ok"] is True, форма


def test_нераспознанный_день_недели(client, freeze):
    freeze("2026-08-06T09:00")
    данные = client.post("/api/agent/slots/check", headers=auth(),
                         json={"date": "2026-08-07", "time": "15:00",
                               "expected_weekday": "послезавтра"}).json()
    assert данные["reason"] == "weekday_mismatch"
    assert данные["hint"] == "7 августа — это пятница"


# ─────────────────────── 7. Часы приёма ─────────────────────────────────

def test_7_границы_рабочего_дня(client, freeze):
    freeze("2026-08-06T09:00")

    for время in ("08:00", "18:00"):
        данные = client.post("/api/agent/slots/check", headers=auth(),
                             json={"date": "2026-08-07", "time": время,
                                   "expected_weekday": "пятница"}).json()
        assert данные["ok"] is False, время
        assert данные["reason"] == "outside_hours", время
        assert данные["alternatives"], время

    for время in ("09:00", "17:00"):
        данные = client.post("/api/agent/slots/check", headers=auth(),
                             json={"date": "2026-08-07", "time": время,
                                   "expected_weekday": "пятница"}).json()
        assert данные["ok"] is True, время
        assert данные["slot"]["id"] == f"2026-08-07T{время}"


def test_получас_не_время_начала(client, freeze):
    """Шаг ровно час: 15:30 — не слот, хотя и внутри рабочего дня."""
    freeze("2026-08-06T09:00")
    данные = client.post("/api/agent/slots/check", headers=auth(),
                         json={"date": "2026-08-07", "time": "15:30",
                               "expected_weekday": "пятница"}).json()
    assert данные["reason"] == "outside_hours"
    assert "начале часа" in данные["hint"]


# ──────────────────────────── check: успех ──────────────────────────────

def test_успех_проговаривает_число_и_месяц(client, freeze):
    freeze("2026-08-05T09:00")
    данные = client.post("/api/agent/slots/check", headers=auth(),
                         json={"date": "2026-08-07", "time": "15:00",
                               "expected_weekday": "пятница"}).json()
    assert данные == {"ok": True,
                      "slot": {"id": "2026-08-07T15:00",
                               "human": "в пятницу, 7 августа, в 15:00"}}


# ───────────────────────── Разбор входных данных ────────────────────────

def test_кривая_дата_422(client, freeze):
    freeze("2026-08-06T09:00")
    for плохая in ("07.08.2026", "2026-8-7", "завтра", "2026-02-30", ""):
        r = client.post("/api/agent/slots/check", headers=auth(),
                        json={"date": плохая, "time": "15:00",
                              "expected_weekday": "пятница"})
        assert r.status_code == 422, плохая
        assert "date" in r.json()["detail"], плохая


def test_кривое_время_422(client, freeze):
    freeze("2026-08-06T09:00")
    for плохое in ("15-00", "три часа", "25:00", ""):
        r = client.post("/api/agent/slots/check", headers=auth(),
                        json={"date": "2026-08-07", "time": плохое,
                              "expected_weekday": "пятница"})
        assert r.status_code == 422, плохое
        assert "time" in r.json()["detail"], плохое


def test_пропущенное_поле_422_по_русски(client, freeze):
    freeze("2026-08-06T09:00")
    r = client.post("/api/agent/slots/check", headers=auth(),
                    json={"time": "15:00", "expected_weekday": "пятница"})
    assert r.status_code == 422
    assert "ГГГГ-ММ-ДД" in r.json()["detail"]


# ─────────────────────────── Логирование ────────────────────────────────

def test_вызовы_попадают_в_лог(client, freeze, capsys):
    freeze("2026-08-06T09:00")
    client.get("/api/agent/slots", headers=auth())
    client.post("/api/agent/slots/check", headers=auth(),
                json={"date": "2026-08-08", "time": "15:00",
                      "expected_weekday": "суббота"})
    client.get("/api/agent/slots", headers={"X-Agent-Key": "wrong-key"})

    строки = [s for s in capsys.readouterr().out.splitlines() if "[agent]" in s]
    assert len(строки) == 3
    assert "GET /api/agent/slots" in строки[0]
    assert "ok=false reason=weekend" in строки[1]
    assert "403" in строки[2]
    assert KEY not in "\n".join(строки)   # ключ в лог не попадает никогда


# ────────────────────────── Производительность ──────────────────────────

def test_ответ_быстрее_500мс(client, freeze):
    """Вебхук обязан уложиться в 500 мс, иначе агент повиснет в паузе."""
    import time as _t
    freeze("2026-08-06T09:00")
    старт = _t.perf_counter()
    for _ in range(20):
        client.get("/api/agent/slots", headers=auth())
    среднее = (_t.perf_counter() - старт) / 20
    assert среднее < 0.5, среднее
