"""Тесты календарных эндпоинтов агента.

Время заморожено во всех тестах, где оно влияет на ответ: тест, который
проходит только по будням до обеда, — не тест, а ловушка для следующего.

Опорные даты августа 2026 (сверено календарём):
    03 пн · 04 вт · 05 ср · 06 чт · 07 пт · 08 сб · 09 вс · 10 пн · 17 пн

Конкретные ЧАСЫ в ожиданиях не хардкодятся. Занятость слотов считается хешем,
и после правки BUSY_SHARE любой такой тест упал бы на изменении константы,
а не на ошибке — то есть перестал бы что-либо значить. Проверяем свойства:
день, разнесённость, свободен ли слот, совпадение двух ответов подряд.
"""

import re
from datetime import date, time, timedelta

import agent_slots
from conftest import (KEY, auth, час_дня, сказано, свободный_час, занятый_час,
                      первый_день_с_занятым_слотом)


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
    assert all(o["id"].startswith("2026-08-10") for o in данные["options"])
    assert "суббот" not in str(данные["options"]).lower()


def test_2_пятница_утро_тоже_понедельник(client, freeze):
    """Пятница 10:00 — до конца рабочего дня далеко, но сегодня недоступно."""
    freeze("2026-08-07T10:00")
    options = client.get("/api/agent/slots", headers=auth()).json()["options"]
    assert all(o["id"].startswith("2026-08-10") for o in options)


def test_3_среда_утро_даёт_четверг_со_словом_завтра(client, freeze):
    """Среда 08:00 → четверг, и это действительно завтра."""
    freeze("2026-08-05T08:00")
    options = client.get("/api/agent/slots", headers=auth()).json()["options"]
    assert all(o["id"].startswith("2026-08-06") for o in options)
    assert "завтра" in options[0]["human"]
    assert options[0]["human"] == f"завтра, в четверг, {сказано(options[0]['id'])}"


def test_8_варианты_разнесены(client, freeze):
    """Один вариант до 12:00, второй после 14:00 — пока в дне есть оба.

    Если хеш выел одну из половин дня целиком, требование смягчается до
    «два разных часа»: предложить нечего, а молчать хуже.
    """
    for момент in ("2026-08-03T09:00", "2026-08-05T13:00", "2026-08-07T18:00",
                   "2026-08-08T11:00", "2026-08-09T23:59"):
        freeze(момент)
        options = client.get("/api/agent/slots", headers=auth()).json()["options"]
        часы = [час_дня(o["id"]) for o in options]
        день = date.fromisoformat(options[0]["id"][:10])
        свободные = agent_slots.free_hours(день)

        assert часы[0] != часы[1], момент
        assert all(ч in свободные for ч in часы), момент
        есть_обе_половины = (any(ч < 12 for ч in свободные)
                             and any(ч > 14 for ч in свободные))
        if есть_обе_половины:
            assert часы[0] < 12 and часы[1] > 14, момент


def test_обе_половины_дня_бывают_пустыми(client, freeze):
    """Смягчённая ветка в test_8 — не теория: такие дни в календаре есть.

    Если этот тест однажды упадёт, значит хеш стал равномернее и ветку
    «половина дня выпала» больше ничто не проверяет — тогда её надо либо
    покрыть иначе, либо убрать, а не оставлять непроверенной.
    """
    д = date(2026, 8, 1)
    нашлось = 0
    for _ in range(200):
        if agent_slots.is_working_day(д):
            свободные = agent_slots.free_hours(д)
            if not any(ч < 12 for ч in свободные) or not any(ч > 14 for ч in свободные):
                нашлось += 1
        д += timedelta(days=1)
    assert нашлось > 0


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


# ─────────────────── Детерминированность и занятость ────────────────────

def test_повторный_запрос_даёт_те_же_слоты(client, freeze):
    """Собеседник переспрашивает — и слышит то же самое, а не «уже заняли»."""
    freeze("2026-08-06T10:00")
    первый = client.get("/api/agent/slots", headers=auth()).json()["options"]
    второй = client.get("/api/agent/slots", headers=auth()).json()["options"]
    третий = client.get("/api/agent/slots", headers=auth()).json()["options"]
    assert первый == второй == третий


def test_занятость_не_зависит_от_текущего_времени(client, freeze):
    """Занятость — функция от слота, а не от момента запроса.

    Три разных «сейчас» в разные дни, но с одним и тем же after: значит
    и день, и пара слотов обязаны совпасть до символа.
    """
    ответы = []
    for момент in ("2026-08-03T09:00", "2026-08-05T23:30", "2026-08-06T00:01"):
        freeze(момент)
        ответы.append(client.get("/api/agent/slots?after=2026-08-17",
                                 headers=auth()).json()["options"])
    assert ответы[0] == ответы[1] == ответы[2]

    # И то же на уровне функции: свободные часы дня от «сейчас» не зависят.
    день = date(2026, 8, 17)
    assert agent_slots.free_hours(день) == agent_slots.free_hours(день)
    assert agent_slots.pick_two_hours(день) == agent_slots.pick_two_hours(день)


def test_минимум_четыре_свободных_слота_каждый_рабочий_день(client, freeze):
    """Месяц вперёд: дня, в котором агенту нечего предложить, быть не может."""
    д = date(2026, 8, 6)
    проверено = 0
    for _ in range(31):
        if agent_slots.is_working_day(д):
            свободные = agent_slots.free_hours(д)
            assert len(свободные) >= agent_slots.MIN_FREE_SLOTS, (д, свободные)
            assert свободные == sorted(set(свободные)), д
            проверено += 1
        д += timedelta(days=1)
    assert проверено >= 20


def test_доля_занятых_близка_к_константе():
    """Занято примерно BUSY_SHARE — иначе календарь либо пуст, либо забит.

    Точного совпадения не требуем: гарантия минимума свободных слотов
    сдвигает долю вниз, и это осознанно.
    """
    д = date(2026, 1, 1)
    всего = занято = 0
    for _ in range(400):
        if agent_slots.is_working_day(д):
            свободные = agent_slots.free_hours(д)
            всего += len(agent_slots.working_hours())
            занято += len(agent_slots.working_hours()) - len(свободные)
        д += timedelta(days=1)
    доля = занято / всего
    assert agent_slots.BUSY_SHARE - 0.07 < доля <= agent_slots.BUSY_SHARE + 0.02, доля


def test_выходной_не_имеет_свободных_слотов():
    assert agent_slots.free_hours(date(2026, 8, 8)) == []
    assert agent_slots.free_hours(date(2026, 8, 9)) == []


def test_предложенные_слоты_всегда_свободны(client, freeze):
    """Обход месяца: сервер не может предложить то, что сам считает занятым."""
    д = date(2026, 8, 6)
    for _ in range(31):
        freeze(f"{д}T09:00")
        options = client.get("/api/agent/slots", headers=auth()).json()["options"]
        for o in options:
            день = date.fromisoformat(o["id"][:10])
            assert agent_slots.is_free(день, час_дня(o["id"])), o
        д += timedelta(days=1)


# ───────────────────────── Параметр after ───────────────────────────────

def test_after_сдвигает_вперёд(client, freeze):
    freeze("2026-08-06T10:00")
    options = client.get("/api/agent/slots?after=2026-08-17",
                         headers=auth()).json()["options"]
    assert all(o["id"].startswith("2026-08-17") for o in options)


def test_after_дальше_шести_дней_проговаривает_число(client, freeze):
    freeze("2026-08-06T10:00")
    options = client.get("/api/agent/slots?after=2026-08-17",
                         headers=auth()).json()["options"]
    assert options[0]["human"] == (
        f"в понедельник, 17 августа, {сказано(options[0]['id'])}")


def test_after_на_выходной_переносится_на_понедельник(client, freeze):
    freeze("2026-08-06T10:00")
    options = client.get("/api/agent/slots?after=2026-08-08",
                         headers=auth()).json()["options"]
    assert all(o["id"].startswith("2026-08-10") for o in options)


def test_after_в_прошлом_не_приближает_дату(client, freeze):
    """after не может дать дату раньше следующего рабочего дня."""
    freeze("2026-08-06T10:00")
    options = client.get("/api/agent/slots?after=2020-01-01",
                         headers=auth()).json()["options"]
    assert all(o["id"].startswith("2026-08-07") for o in options)


def test_after_кривого_формата_422(client, freeze):
    freeze("2026-08-06T10:00")
    r = client.get("/api/agent/slots?after=06.08.2026", headers=auth())
    assert r.status_code == 422
    assert "ГГГГ-ММ-ДД" in r.json()["detail"]


# ─────────────────────────── Время словами ──────────────────────────────

def test_время_словами():
    """Цифры «16:00» синтез читает как «нуль-наль» — вслух идут слова.

    Ожидания прописаны руками, а не взяты у самой функции: тест, который
    сверяет реализацию с реализацией, проходит всегда и не значит ничего.
    """
    ожидания = {
        9: "в 9 утра", 10: "в 10 утра", 11: "в 11 утра",
        12: "в полдень",
        13: "в час дня", 14: "в 2 часа дня", 15: "в 3 часа дня",
        16: "в 4 часа дня", 17: "в 5 часов дня",
    }
    for час, фраза in ожидания.items():
        assert agent_slots.spoken_time(time(hour=час)) == фраза, час


def test_время_словами_вне_часов_приёма():
    """Границы приёма — константы. Сдвинут их — форма обязана остаться верной."""
    ожидания = {
        0: "в полночь", 1: "в час ночи", 2: "в 2 часа ночи",
        5: "в 5 утра", 8: "в 8 утра",
        18: "в 6 вечера", 22: "в 10 вечера", 23: "в 11 часов ночи",
    }
    for час, фраза in ожидания.items():
        assert agent_slots.spoken_time(time(hour=час)) == фраза, час


def test_не_круглый_час_остаётся_цифрами():
    """Слотов не на круглый час не бывает, но если появятся — лучше цифры,
    чем слова, которые перестанут соответствовать времени."""
    assert agent_slots.spoken_time(time(15, 30)) == "в 15:30"


def test_в_human_нет_цифрового_времени(client, freeze):
    """Ни один произносимый ответ не должен содержать «:00»."""
    freeze("2026-08-06T10:00")
    произносимое = []
    данные = client.get("/api/agent/slots", headers=auth()).json()
    произносимое += [o["human"] for o in данные["options"]]

    отказ = client.post("/api/agent/slots/check", headers=auth(),
                        json={"date": "2026-08-08", "time": "15:00",
                              "expected_weekday": "суббота"}).json()
    произносимое += [a["human"] for a in отказ["alternatives"]]

    час = свободный_час(date(2026, 8, 7))
    успех = client.post("/api/agent/slots/check", headers=auth(),
                        json={"date": "2026-08-07", "time": f"{час:02d}:00",
                              "expected_weekday": "пятница"}).json()
    произносимое.append(успех["slot"]["human"])

    for фраза in произносимое:
        assert ":00" not in фраза, фраза
        assert "0" not in фраза.replace("10", "").replace("11", ""), фраза


def test_ни_в_одном_hint_нет_цифрового_времени(client, freeze):
    """Обход ВСЕХ шести причин отказа: агент произносит hint вслух.

    Тест перебирает причины по списку из самого кода, а не по выписанному
    руками: появится седьмая — она попадёт сюда сама. Проверка, которая
    молчит про новую ветку, хуже отсутствующей: она создаёт уверенность.
    """
    freeze("2026-08-06T09:00")
    день_с_занятым = первый_день_с_занятым_слотом(date(2026, 8, 7))

    запросы = {
        "weekday_mismatch": {"date": "2026-08-07", "time": "15:00",
                             "expected_weekday": "среда"},
        "past": {"date": "2026-08-05", "time": "15:00",
                 "expected_weekday": "среда"},
        "today": {"date": "2026-08-06", "time": "15:00",
                  "expected_weekday": "четверг"},
        "weekend": {"date": "2026-08-08", "time": "15:00",
                    "expected_weekday": "суббота"},
        "outside_hours": {"date": "2026-08-07", "time": "18:00",
                          "expected_weekday": "пятница"},
        "outside_hours_минуты": {"date": "2026-08-07", "time": "15:30",
                                 "expected_weekday": "пятница"},
        "busy": {"date": f"{день_с_занятым}",
                 "time": f"{занятый_час(день_с_занятым):02d}:00",
                 "expected_weekday": agent_slots.WEEKDAYS_NOM[день_с_занятым.weekday()]},
    }

    причины = set()
    for метка, тело in запросы.items():
        данные = client.post("/api/agent/slots/check", headers=auth(),
                             json=тело).json()
        assert данные["ok"] is False, метка
        причины.add(данные["reason"])
        assert not re.search(r"\d{1,2}:\d{2}", данные["hint"]), (метка, данные["hint"])
        for а in данные["alternatives"]:
            assert not re.search(r"\d{1,2}:\d{2}", а["human"]), (метка, а["human"])

    # Все причины из кода должны быть покрыты: иначе тест обходит не всё.
    assert причины == {"weekday_mismatch", "past", "today", "weekend",
                       "outside_hours", "busy"}


def test_hint_про_часы_приёма_собран_из_констант(client, freeze):
    """Фраза строится из WORK_START_HOUR и WORK_END_HOUR, а не написана руками:
    сдвинут границы — текст обязан поехать следом, а не начать врать."""
    freeze("2026-08-06T09:00")
    данные = client.post("/api/agent/slots/check", headers=auth(),
                         json={"date": "2026-08-07", "time": "18:00",
                               "expected_weekday": "пятница"}).json()
    assert данные["hint"] == "встречи назначаем с 9 утра до 5 часов дня"
    assert agent_slots.spoken_hours_range() == "с 9 утра до 5 часов дня"


def test_hint_про_начало_часа(client, freeze):
    freeze("2026-08-06T09:00")
    данные = client.post("/api/agent/slots/check", headers=auth(),
                         json={"date": "2026-08-07", "time": "15:30",
                               "expected_weekday": "пятница"}).json()
    assert данные["hint"] == ("встречи начинаются в начале часа, "
                              "например, в 3 часа дня")


def test_родительный_падеж_в_обороте_до(client, freeze):
    """«до полудня», а не «до полдень» — если границы приёма сдвинут."""
    assert agent_slots._genitive("полдень") == "полудня"
    assert agent_slots._genitive("полночь") == "полуночи"
    assert agent_slots._genitive("час дня") == "часа дня"
    assert agent_slots._genitive("5 часов дня") == "5 часов дня"


def test_id_остаётся_машинным(client, freeze):
    """Словесная форма — только в human. id разбирает программа."""
    freeze("2026-08-06T10:00")
    данные = client.get("/api/agent/slots", headers=auth()).json()
    for o in данные["options"]:
        assert o["id"].endswith(":00"), o
        assert " " not in o["id"], o


# ──────────────────── День недели произносится один раз ─────────────────

def test_второй_вариант_того_же_дня_без_дня_недели(client, freeze):
    """«завтра, в пятницу, в 10:00» и следом просто «в 15:00»."""
    freeze("2026-08-06T10:00")
    options = client.get("/api/agent/slots", headers=auth()).json()["options"]
    assert options[0]["id"][:10] == options[1]["id"][:10]

    assert options[1]["human"] == сказано(options[1]["id"])
    for день in agent_slots.WEEKDAYS_NOM:
        assert день[:-1] not in options[1]["human"], день
    assert "завтра" not in options[1]["human"]


def test_день_недели_называется_в_первом_варианте(client, freeze):
    freeze("2026-08-06T10:00")
    options = client.get("/api/agent/slots", headers=auth()).json()["options"]
    assert "в пятницу" in options[0]["human"]


def test_второй_вариант_в_другой_день_называет_день(client, freeze):
    """Разные дни — день недели нужен в обоих: иначе «в 15:00» повиснет
    без привязки. Пары в разные дни строит не get_slots, а human_phrase,
    поэтому проверяем её напрямую."""
    from datetime import datetime
    now = datetime(2026, 8, 6, 10, 0, tzinfo=agent_slots.TZ)
    другой_день = datetime(2026, 8, 10, 15, 0, tzinfo=agent_slots.TZ)
    assert agent_slots.human_phrase(другой_день, now) == "в понедельник в 3 часа дня"


# ──────────────────────────── check: отказы ─────────────────────────────

def test_4_суббота_weekend_с_альтернативами(client, freeze):
    freeze("2026-08-06T10:00")
    данные = client.post("/api/agent/slots/check", headers=auth(),
                         json={"date": "2026-08-08", "time": "15:00",
                               "expected_weekday": "суббота"}).json()
    assert данные["ok"] is False
    assert данные["reason"] == "weekend"
    assert данные["hint"] == "суббота — нерабочий день"
    assert len(данные["alternatives"]) == 2
    assert all(a["id"].startswith("2026-08-10") for a in данные["alternatives"])
    assert "в понедельник" in данные["alternatives"][0]["human"]


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
    assert all(a["id"].startswith("2026-08-07") for a in данные["alternatives"])


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
    час = свободный_час(date(2026, 8, 7))
    for форма in ("пятница", "в пятницу", "Пятница", "  В ПЯТНИЦУ  ", "пятницу"):
        данные = client.post("/api/agent/slots/check", headers=auth(),
                             json={"date": "2026-08-07", "time": f"{час:02d}:00",
                                   "expected_weekday": форма}).json()
        assert данные["ok"] is True, форма


def test_день_недели_вторник_с_предлогом_во(client, freeze):
    freeze("2026-08-06T09:00")
    час = свободный_час(date(2026, 8, 11))
    for форма in ("вторник", "во вторник"):
        данные = client.post("/api/agent/slots/check", headers=auth(),
                             json={"date": "2026-08-11", "time": f"{час:02d}:00",
                                   "expected_weekday": форма}).json()
        assert данные["ok"] is True, форма


def test_нераспознанный_день_недели(client, freeze):
    freeze("2026-08-06T09:00")
    данные = client.post("/api/agent/slots/check", headers=auth(),
                         json={"date": "2026-08-07", "time": "15:00",
                               "expected_weekday": "послезавтра"}).json()
    assert данные["reason"] == "weekday_mismatch"
    assert данные["hint"] == "7 августа — это пятница"


# ─────────────────────────── check: занятость ───────────────────────────

def test_занятый_слот_даёт_busy_и_альтернативы(client, freeze):
    freeze("2026-08-06T09:00")
    день = первый_день_с_занятым_слотом(date(2026, 8, 7))
    час = занятый_час(день)

    данные = client.post("/api/agent/slots/check", headers=auth(),
                         json={"date": f"{день}", "time": f"{час:02d}:00",
                               "expected_weekday": agent_slots.WEEKDAYS_NOM[день.weekday()]}).json()
    assert данные["ok"] is False
    assert данные["reason"] == "busy"
    assert данные["hint"] == "это время уже занято"
    assert len(данные["alternatives"]) == 2
    # Альтернатива не может совпасть с тем, что только что назвали занятым.
    assert all(a["id"] != f"{день}T{час:02d}:00" for a in данные["alternatives"])


def test_свободный_слот_проходит(client, freeze):
    freeze("2026-08-06T09:00")
    день = date(2026, 8, 7)
    час = свободный_час(день)
    данные = client.post("/api/agent/slots/check", headers=auth(),
                         json={"date": f"{день}", "time": f"{час:02d}:00",
                               "expected_weekday": "пятница"}).json()
    assert данные["ok"] is True
    assert данные["slot"]["id"] == f"2026-08-07T{час:02d}:00"


def test_занятость_проверяется_последней(client, freeze):
    """Занятый час в субботу — это weekend, а не busy.

    Сказать «занято» про выходной значит соврать: собеседник переспросит
    то же самое на час раньше и получит тот же отказ другими словами.
    """
    freeze("2026-08-06T09:00")
    суббота = date(2026, 8, 8)
    # У выходного свободных часов нет вовсе, то есть формально «занят» любой.
    assert agent_slots.free_hours(суббота) == []
    данные = client.post("/api/agent/slots/check", headers=auth(),
                         json={"date": "2026-08-08", "time": "15:00",
                               "expected_weekday": "суббота"}).json()
    assert данные["reason"] == "weekend"


def test_занятость_не_мешает_отказу_по_часам(client, freeze):
    freeze("2026-08-06T09:00")
    данные = client.post("/api/agent/slots/check", headers=auth(),
                         json={"date": "2026-08-07", "time": "18:00",
                               "expected_weekday": "пятница"}).json()
    assert данные["reason"] == "outside_hours"


# ─────────────────────── 7. Часы приёма ─────────────────────────────────

def test_7_границы_рабочего_дня(client, freeze):
    """08:00 и 18:00 — вне диапазона; 09:00 и 17:00 — внутри.

    День берём такой, где обе границы свободны: иначе внутрь диапазона
    прилетит busy, и тест проверял бы занятость вместо часов приёма.
    """
    freeze("2026-08-06T09:00")

    for время in ("08:00", "18:00"):
        данные = client.post("/api/agent/slots/check", headers=auth(),
                             json={"date": "2026-08-07", "time": время,
                                   "expected_weekday": "пятница"}).json()
        assert данные["ok"] is False, время
        assert данные["reason"] == "outside_hours", время
        assert данные["alternatives"], время

    день = date(2026, 8, 7)
    for _ in range(30):
        свободные = agent_slots.free_hours(день)
        if agent_slots.WORK_START_HOUR in свободные and agent_slots.WORK_END_HOUR in свободные:
            break
        день += timedelta(days=1)
    else:
        raise AssertionError("за месяц не нашлось дня, где свободны и 09:00, и 17:00")

    for время in ("09:00", "17:00"):
        данные = client.post("/api/agent/slots/check", headers=auth(),
                             json={"date": f"{день}", "time": время,
                                   "expected_weekday": agent_slots.WEEKDAYS_NOM[день.weekday()]}).json()
        assert данные["ok"] is True, (день, время)
        assert данные["slot"]["id"] == f"{день}T{время}"


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
    час = свободный_час(date(2026, 8, 7))
    данные = client.post("/api/agent/slots/check", headers=auth(),
                         json={"date": "2026-08-07", "time": f"{час:02d}:00",
                               "expected_weekday": "пятница"}).json()
    вслух = agent_slots.spoken_time(time(hour=час))
    assert данные == {"ok": True,
                      "slot": {"id": f"2026-08-07T{час:02d}:00",
                               "human": f"в пятницу, 7 августа, {вслух}"}}


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


def test_отказ_по_формату_тоже_в_логе(client, freeze, capsys):
    """422 — это тоже вызов. Без записи он выглядит как «агент не позвонил»."""
    freeze("2026-08-06T09:00")
    client.get("/api/agent/slots?after=06.08.2026", headers=auth())
    client.post("/api/agent/slots/check", headers=auth(),
                json={"date": "не дата", "time": "15:00",
                      "expected_weekday": "пятница"})

    строки = [s for s in capsys.readouterr().out.splitlines() if "[agent]" in s]
    assert len(строки) == 2
    assert all("422" in s for s in строки)


def test_busy_попадает_в_лог(client, freeze, capsys):
    freeze("2026-08-06T09:00")
    день = первый_день_с_занятым_слотом(date(2026, 8, 7))
    час = занятый_час(день)
    client.post("/api/agent/slots/check", headers=auth(),
                json={"date": f"{день}", "time": f"{час:02d}:00",
                      "expected_weekday": agent_slots.WEEKDAYS_NOM[день.weekday()]})
    строки = [s for s in capsys.readouterr().out.splitlines() if "[agent]" in s]
    assert "ok=false reason=busy" in строки[0]


# ────────────────────────── Производительность ──────────────────────────

def test_ответ_быстрее_500мс(client, freeze):
    """Вебхук обязан уложиться в 500 мс, иначе агент повиснет в паузе.

    Хеширование добавилось к арифметике — девять sha256 на день, — поэтому
    порог теперь проверяется не для проформы.
    """
    import time as _t
    freeze("2026-08-06T09:00")
    старт = _t.perf_counter()
    for _ in range(20):
        client.get("/api/agent/slots", headers=auth())
    среднее = (_t.perf_counter() - старт) / 20
    assert среднее < 0.5, среднее
