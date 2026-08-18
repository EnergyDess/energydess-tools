"""Три строки лога про состав тела и классификатор незнакомого ответа.

BACKLOG.md, задача 97.

ЗАЧЕМ ЭТО ОТДЕЛЬНЫМ ФАЙЛОМ. Живого успешного входа в Zepp Life не было
НИ РАЗУ, и этим заходом его тоже не случилось: учётных данных нет,
а на проде ноль строк в `scale_connections` (проверено 2026-08-18).
Настоящий состав `summary` по-прежнему неизвестен — девять величин
в `РАЗБИРАЕМ` взяты из чужого репозитория и приняты на веру.

Единственное, что напечатает правду, — первый успешный вход владельца.
Три строки лога и есть весь инструмент на этот случай:

    [zepp] поля summary в ответе (N): …
    [zepp] из них мы НЕ разбираем (N): …
    [zepp] мы ждём, а их нет (N): …

И до сегодняшнего дня НИ ОДНА из них не была ничем проверена. То есть
единственная попытка владельца могла пройти впустую: вход удался бы,
измерения записались бы, а строк в логе не оказалось — и мы снова
не узнали бы состава. Отказ был бы молчащим ровно там, где вся задача
про то, чтобы перестать гадать.

Здесь эти строки проверяются на ПОДСТАВЛЕННОМ ответе. Это не замер
живого сервиса и им не притворяется: доказывает не то, что поля такие,
а то, что инструмент их напечатает.
"""

import io
import os
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DB_PATH",
                      str(Path(tempfile.gettempdir()) / "hh_tests_zepp_log.db"))

import zepp_client as z            # noqa: E402


# ── Подставной httpx.Client ─────────────────────────────────────────────────

class Ответ:
    def __init__(с, код=200, json_тело=None, location=None, тело=""):
        с.status_code, с._j, с.text = код, json_тело or {}, тело
        с.headers = {"location": location} if location else {}

    def json(с):
        return с._j

    def raise_for_status(с):
        if с.status_code >= 400:
            raise z.httpx.HTTPStatusError("HTTP %d" % с.status_code,
                                          request=None, response=None)


class Клиент:
    """Отдаёт заготовленные ответы по очереди. Контекстный менеджер —
    `fetch_weight_records` открывает `with httpx.Client(...)`."""

    def __init__(с, ответы):
        с._о = list(ответы)

    def __enter__(с):
        return с

    def __exit__(с, *a):
        return False

    def get(с, *a, **k):
        return с._о.pop(0)

    def post(с, *a, **k):
        return с._о.pop(0)


def _запись(ts, summary):
    return {"timestamp": ts * 1000, "weightType": 0, "weight": 80.5,
            "summary": summary}


def _выборка(monkeypatch, ответы):
    monkeypatch.setattr(z.httpx, "Client", lambda *a, **k: Клиент(ответы))
    поток = io.StringIO()
    with redirect_stdout(поток):
        итог = z.fetch_weight_records("токен", "42", data_host="api-mifit.zepp.com")
    return итог, поток.getvalue()


# ── Три строки ──────────────────────────────────────────────────────────────

def test_состав_тела_печатается_тремя_строками(monkeypatch):
    """ГЛАВНЫЙ тест файла: строки существуют и печатаются."""
    summary = {н: 1 for н in z.РАЗБИРАЕМ.values()}
    _итог, лог = _выборка(monkeypatch, [
        Ответ(json_тело={"items": [_запись(1_700_000_000, summary)]}),
        Ответ(json_тело={"items": []}),
    ])
    assert "[zepp] поля summary в ответе" in лог
    assert "[zepp] из них мы НЕ разбираем" in лог
    assert "[zepp] мы ждём, а их нет" in лог


def test_лишнее_поле_названо_поимённо(monkeypatch):
    """Поле, которого мы не разбираем, обязано быть НАЗВАНО, а не сосчитано:
    по числу «мы не разбираем 4» решить нечего."""
    summary = {н: 1 for н in z.РАЗБИРАЕМ.values()}
    summary["idealWeight"] = 72.0          # его в API, по нашим сведениям, нет
    summary["somethingNew"] = 1
    _итог, лог = _выборка(monkeypatch, [
        Ответ(json_тело={"items": [_запись(1_700_000_000, summary)]}),
        Ответ(json_тело={"items": []}),
    ])
    строка = next(с for с in лог.splitlines() if "НЕ разбираем" in с)
    assert "idealWeight" in строка and "somethingNew" in строка
    assert "(2)" in строка


def test_недостающее_поле_названо_поимённо(monkeypatch):
    """Обратная сторона: величина, которую мы ждём, а её нет. Это и есть
    проверка девяти имён, взятых на веру из чужого репозитория."""
    summary = {н: 1 for н in z.РАЗБИРАЕМ.values()}
    пропало = sorted(z.РАЗБИРАЕМ.values())[0]
    summary.pop(пропало)
    _итог, лог = _выборка(monkeypatch, [
        Ответ(json_тело={"items": [_запись(1_700_000_000, summary)]}),
        Ответ(json_тело={"items": []}),
    ])
    строка = next(с for с in лог.splitlines() if "мы ждём, а их нет" in с)
    assert пропало in строка


def test_запись_без_summary_говорит_об_этом(monkeypatch):
    """Ручной ввод в приложении приходит с summary: null. Тогда состава
    не будет вовсе, и это надо сказать, а не напечатать пустой список."""
    _итог, лог = _выборка(monkeypatch, [
        Ответ(json_тело={"items": [_запись(1_700_000_000, None)]}),
        Ответ(json_тело={"items": []}),
    ])
    assert "ни у одной записи нет summary" in лог


# ── Классификатор: незнакомое остаётся незнакомым ───────────────────────────

class _ОдинОтвет:
    def __init__(с, о):
        с._о = о

    def post(с, *a, **k):
        return с._о


@pytest.mark.parametrize("имя,ответ", [
    ("незнакомый код отказа",
     Ответ(303, location="https://x/?error=90210&state=REDIRECTION")),
    ("429 вместо редиректа",
     Ответ(429, тело='{"error":"rate limited"}')),
    ("303 без access и без error",
     Ответ(303, location="https://x/?state=REDIRECTION&region=eu-central-1")),
    ("200 с JSON вместо редиректа",
     Ответ(200, тело='{"code":0,"message":"ok"}')),
])
def test_чужой_ответ_не_схлопывается_в_неверный_пароль(имя, ответ):
    """Классификатор трижды в истории этого модуля выбирал ближайший
    известный класс вместо «не опознан» — и человек шёл менять пароль,
    который был верным. Ни один из этих ответов не смеет стать
    ZeppAuthError."""
    поток = io.StringIO()
    with redirect_stdout(поток):
        with pytest.raises(z.ZeppProtocolError):
            z._код_доступа(_ОдинОтвет(ответ), "x@y.z", "п")


def test_известный_отказ_остаётся_отказом_по_паролю():
    """Положительный контроль к предыдущему: если бы ZeppAuthError
    не возникал НИКОГДА, тест выше проходил бы и на сломанном коде."""
    ответ = Ответ(303, location="https://x/?error=401&state=REDIRECTION")
    поток = io.StringIO()
    with redirect_stdout(поток):
        with pytest.raises(z.ZeppAuthError):
            z._код_доступа(_ОдинОтвет(ответ), "x@y.z", "п")
