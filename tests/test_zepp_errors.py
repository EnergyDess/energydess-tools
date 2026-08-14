"""Родная схема входа Zepp Life: классификация отказов и разбор выборки.

Почему на это есть тесты. Живого аккаунта весов у разработчика нет —
он только у владельца, — и единственный способ увидеть, как поведёт себя
код на том или ином ответе, это подставить ответ. Ошибка здесь того же
класса, что немой сбой из §6.0.1, только повёрнутая к пользователю:
сообщение выглядит осмысленным и потому не вызывает подозрений. Так
успешный ответ Xiaomi (code=0, 成功) полтора месяца выходил наружу
требованием подтвердить вход в приложении, где его нет.

Формы ответов взяты не из головы: все три шага замерены живыми запросами
2026-08-14 (заведомо несуществующий адрес), числа — в шапке zepp_client.

`zepp_client` ничего не тянет, кроме httpx, — импортируется напрямую.
"""

import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import zepp_client as z

ТОКЕН_URL = f"https://{z.ХОСТ_ТОКЕНА}/registrations"
ВХОД_URL = f"https://{z.ХОСТ_ВХОДА}/v2/client/login"


def подменить_сеть(monkeypatch, обработчик):
    """Подсовывает httpx.Client с MockTransport вместо настоящего.

    Клиент создаётся ВНУТРИ функций zepp_client, поэтому подменяется сам
    класс, а не экземпляр: иначе тест проверял бы не тот код, который
    работает на проде."""
    настоящий = httpx.Client

    def подделка(**kwargs):
        kwargs.pop("timeout", None)
        return настоящий(transport=httpx.MockTransport(обработчик), **kwargs)

    monkeypatch.setattr(z.httpx, "Client", подделка)


def ответ_редиректом(запрос_или_параметры):
    """303 с Location — ровно та форма, что отдаёт живой сервис."""
    хвост = "&".join(f"{k}={v}" for k, v in запрос_или_параметры.items())
    return httpx.Response(303, headers={
        "location": f"{z.АДРЕС_ВОЗВРАТА}?{хвост}"})


# ── Шаг 1: почта и пароль ────────────────────────────────────────────────

def test_код_401_это_отказ_по_учётным_данным(monkeypatch):
    """Замер живого сервиса: неверные данные дают ровно error=401."""
    подменить_сеть(monkeypatch, lambda r: ответ_редиректом(
        {"error": "401", "state": "REDIRECTION", "region": "eu-central-1"}))
    with pytest.raises(z.ZeppAuthError) as отказ:
        z.login("kto@to.ru", "ne-tot-parol", "ключ:1")
    assert "401" in str(отказ.value)


def test_незнакомый_код_не_схлопывается_в_неверный_пароль(monkeypatch):
    """Главное правило разбора. Схлопни мы незнакомый код в «проверьте
    пароль» — следующая причина отказа стала бы неотличима от опечатки,
    и разбирать её было бы нечем."""
    подменить_сеть(monkeypatch, lambda r: ответ_редиректом(
        {"error": "0x87", "region": "eu-central-1"}))
    with pytest.raises(z.ZeppProtocolError) as отказ:
        z.login("kto@to.ru", "parol", "ключ:1")
    assert "0x87" in str(отказ.value)
    assert not isinstance(отказ.value, z.ZeppAuthError)


def test_не_303_это_наша_поломка_а_не_пароль(monkeypatch):
    """Замер: так отвечает кривой запрос (без redirect_uri, без client_id) —
    HTTP 400 и тело '"HuaMi Oauth / User Registration 2.0.2"'. Про пароль
    пользователя здесь сказать нечего."""
    подменить_сеть(monkeypatch, lambda r: httpx.Response(
        400, text='"HuaMi Oauth / User Registration 2.0.2"'))
    with pytest.raises(z.ZeppProtocolError) as отказ:
        z.login("kto@to.ru", "parol", "ключ:1")
    assert "400" in str(отказ.value)
    assert not isinstance(отказ.value, z.ZeppAuthError)


def test_ни_кода_доступа_ни_кода_отказа(monkeypatch):
    подменить_сеть(monkeypatch, lambda r: ответ_редиректом({"state": "REDIRECTION"}))
    with pytest.raises(z.ZeppProtocolError):
        z.login("kto@to.ru", "parol", "ключ:1")


def test_почта_экранируется_в_пути(monkeypatch):
    """Адрес с плюсом и собакой уезжает в путь URL. Без экранирования
    «a+b@x.ru» стал бы другим адресом, и отказ был бы необъясним."""
    увиденные = []

    def обработчик(r):
        увиденные.append(str(r.url))
        return ответ_редиректом({"error": "401"})

    подменить_сеть(monkeypatch, обработчик)
    with pytest.raises(z.ZeppAuthError):
        z.login("a+b@x.ru", "parol", "ключ:1")
    assert "a%2Bb%40x.ru" in увиденные[0]


# ── Шаг 2: код доступа → токен ───────────────────────────────────────────

def успешный_вход(данные_входа=None, статус=200):
    """Оба шага сразу: tokens отдаёт код, client/login — что попросили."""
    тело = данные_входа if данные_входа is not None else {
        "token_info": {"app_token": "APP-TOKEN", "login_token": "L", "user_id": 4242},
        "domains": {"api-mifit": "api-mifit-de2.zepp.com"},
    }

    def обработчик(r):
        if "registrations" in r.url.path:
            return ответ_редиректом({"access": "ACCESS-CODE", "country_code": "RU",
                                     "region": "eu-central-1"})
        return httpx.Response(статус, json=тело)

    return обработчик


def test_успешный_вход_отдаёт_токен_и_хост(monkeypatch):
    подменить_сеть(monkeypatch, успешный_вход())
    итог = z.login("kto@to.ru", "parol", "ключ:1")
    assert итог["app_token"] == "APP-TOKEN"
    assert итог["zepp_user_id"] == "4242"        # строкой, а не числом
    assert итог["data_host"] == "api-mifit-de2.zepp.com"


def test_без_поля_domains_берётся_хост_по_умолчанию(monkeypatch):
    подменить_сеть(monkeypatch, успешный_вход({
        "token_info": {"app_token": "T", "user_id": 1}}))
    assert z.login("kto@to.ru", "p", "ключ:1")["data_host"] == z.ХОСТ_ДАННЫХ_ПО_УМОЛЧАНИЮ


def test_сбой_после_принятого_пароля_никогда_не_про_пароль(monkeypatch):
    """Замер: негодный код даёт {"error_code":"0104"}. Код доступа к этому
    моменту УЖЕ получен, то есть пароль принят, и ни одна ветка ниже
    не вправе сказать «проверьте пароль»."""
    подменить_сеть(monkeypatch, успешный_вход({"error_code": "0104"}, статус=400))
    with pytest.raises(z.ZeppStepError) as отказ:
        z.login("kto@to.ru", "parol", "ключ:1")
    текст = str(отказ.value)
    assert "0104" in текст
    assert "приняты" in текст
    assert not isinstance(отказ.value, z.ZeppAuthError)


def test_ответ_входа_не_в_json(monkeypatch):
    """Страница-заглушка вместо JSON — тоже сбой ПОСЛЕ принятого пароля."""
    def обработчик(r):
        if "registrations" in r.url.path:
            return ответ_редиректом({"access": "A", "country_code": "RU"})
        return httpx.Response(502, text="<html>502 Bad Gateway</html>")

    подменить_сеть(monkeypatch, обработчик)
    with pytest.raises(z.ZeppStepError):
        z.login("kto@to.ru", "parol", "ключ:1")


def test_страна_подставляется_и_об_этом_говорится(capsys, monkeypatch):
    """Молчаливая подстановка сделала бы отказ входа необъяснимым."""
    def обработчик(r):
        if "registrations" in r.url.path:
            return ответ_редиректом({"access": "A", "region": "eu-central-1"})
        return httpx.Response(200, json={"token_info": {"app_token": "T", "user_id": 1}})

    подменить_сеть(monkeypatch, обработчик)
    z.login("kto@to.ru", "parol", "ключ:1")
    напечатано = capsys.readouterr().out
    assert z.СТРАНА_ПО_УМОЛЧАНИЮ in напечатано
    assert "подставлена" in напечатано


def test_в_лог_не_уходят_ключи_доступа(capsys, monkeypatch):
    """`_след` печатает ИМЕНА полей. Значения — это access и app_token,
    то есть ключи к чужому аккаунту."""
    подменить_сеть(monkeypatch, успешный_вход())
    z.login("kto@to.ru", "parol", "ключ:1")
    напечатано = capsys.readouterr().out
    assert "token_info" in напечатано          # имена есть
    assert "ACCESS-CODE" not in напечатано     # значений нет
    assert "APP-TOKEN" not in напечатано


def test_китайский_ответ_не_роняет_лог(capsys, monkeypatch):
    """Сервис отвечает и по-китайски. Обычный !r на консоли cp1251 роняет
    print с UnicodeEncodeError — и валит им весь вход, потому что строка
    стоит в его цепочке. Диагностика, ломающая то, что она диагностирует, —
    это §6.0.1 наизнанку."""
    подменить_сеть(monkeypatch, успешный_вход({"error_code": "成功"}, статус=400))
    with pytest.raises(z.ZeppStepError):
        z.login("kto@to.ru", "parol", "ключ:1")
    напечатано = capsys.readouterr().out
    assert "\\u6210\\u529f" in напечатано       # экранировано, а не сырьём
    напечатано.encode("cp1251")                # не должно бросить


# ── Устройство ───────────────────────────────────────────────────────────

def test_устройство_постоянно_и_в_форме_mac():
    assert z.устройство("ключ:12") == z.устройство("ключ:12")
    assert z.устройство("ключ:12") != z.устройство("ключ:13")
    части = z.устройство("ключ:12").split(":")
    assert len(части) == 6 and all(len(ч) == 2 for ч in части)
    assert "ключ" not in z.устройство("ключ:12")   # ключ не восстанавливается


# ── Шаг 3: выборка измерений ─────────────────────────────────────────────

def выборка(items, статус=200, тело=None):
    def обработчик(r):
        return httpx.Response(статус, json=тело if тело is not None
                              else {"items": items, "next": 0})
    return обработчик


def test_пустая_история_это_не_сбой(monkeypatch, capsys):
    """Главное различие, ради которого выборка возвращает словарь.
    Пустой список отвечал сразу на два вопроса — «измерений нет»
    и «всё сломалось», — и в интерфейсе они выглядели одинаково."""
    подменить_сеть(monkeypatch, выборка([]))
    итог = z.fetch_weight_records("T", "1")
    assert итог["records"] == [] and итог["total"] == 0
    assert "НЕ сбой" in capsys.readouterr().out


def test_нет_поля_items_это_сбой_а_не_пустота(monkeypatch):
    """Отрицательный контроль к тесту выше: изменившийся формат обязан
    отличаться от пустой истории, иначе поломка показывается как норма."""
    подменить_сеть(monkeypatch, выборка(None, тело={"code": 0, "message": "ok"}))
    with pytest.raises(z.ZeppProtocolError):
        z.fetch_weight_records("T", "1")


def test_запись_без_summary_не_роняет_выборку(monkeypatch):
    """Записи, заведённые в приложении РУКАМИ (а такие есть у всех, кто
    вводил вес до покупки весов), приходят с summary = null. Прежний код
    брал .get('summary', {}) — значение по умолчанию не применяется, когда
    ключ есть и равен null, — и падал AttributeError на первой же такой
    записи, роняя синхронизацию целиком."""
    подменить_сеть(monkeypatch, выборка([
        {"weightType": 0, "generatedTime": 100, "summary": None},
        {"weightType": 0, "generatedTime": 200,
         "summary": {"weight": 80.5, "fatRate": 20.0, "muscleAge": 33}},
    ]))
    итог = z.fetch_weight_records("T", "1")
    assert итог["total"] == 2
    assert len(итог["records"]) == 1              # запись без веса отброшена
    assert итог["dropped"]["без summary"] == 1
    assert итог["records"][0]["weight_kg"] == 80.5
    assert итог["records"][0]["body_age"] == 33   # muscleAge — это «возраст тела»


def test_повреждённые_записи_отброшены_и_посчитаны(monkeypatch):
    подменить_сеть(monkeypatch, выборка([
        {"weightType": 1, "generatedTime": 1, "summary": {"weight": 70}},
        {"weightType": 0, "generatedTime": 2, "summary": {"weight": 71}},
    ]))
    итог = z.fetch_weight_records("T", "1")
    assert итог["dropped"]["weightType"] == 1
    assert len(итог["records"]) == 1


def test_401_на_выборке_это_повторный_вход_а_не_протокол(monkeypatch):
    """Замер: {"code":0,"message":"invalid token","data":{"code":"0102"}}.
    Тело печатается в сообщение — если однажды придёт другое, будет видно,
    что 401 не про токен."""
    подменить_сеть(monkeypatch, выборка(None, статус=401, тело={
        "code": 0, "message": "invalid token", "data": {"code": "0102"}}))
    with pytest.raises(z.ZeppApiError) as отказ:
        z.fetch_weight_records("T", "1")
    assert "0102" in str(отказ.value)


def test_хост_данных_берётся_из_подключения(monkeypatch):
    """Без этого европейский аккаунт получал бы 401 на ЖИВОМ токене,
    а 401 у нас означает «протух» — то есть просьбу вводить пароль
    по кругу без единого признака, что дело не в пароле."""
    адреса = []

    def обработчик(r):
        адреса.append(r.url.host)
        return httpx.Response(200, json={"items": [], "next": 0})

    подменить_сеть(monkeypatch, обработчик)
    z.fetch_weight_records("T", "1", data_host="api-mifit-de2.zepp.com")
    assert адреса == ["api-mifit-de2.zepp.com"]
    адреса.clear()
    z.fetch_weight_records("T", "1")
    assert адреса == [z.ХОСТ_ДАННЫХ_ПО_УМОЛЧАНИЮ]


def test_печатает_поля_состава_и_чего_не_хватает(monkeypatch, capsys):
    """Ради этой строки в логе всё и затевалось: живого ответа у нас нет,
    и список показателей до неё брался из чужого репозитория на веру."""
    подменить_сеть(monkeypatch, выборка([
        {"weightType": 0, "generatedTime": 1,
         "summary": {"weight": 80, "bmi": 24, "неведомоеПоле": 1}},
    ]))
    z.fetch_weight_records("T", "1")
    напечатано = capsys.readouterr().out
    assert "неведомоеПоле" in напечатано        # чего мы не разбираем
    assert "fatRate" in напечатано              # чего ждём, но не пришло


# ── Классы ───────────────────────────────────────────────────────────────

def test_каждый_класс_остаётся_отдельным():
    """Ловить ZeppLoginError одной строкой можно, различать — обязательно."""
    for кл in (z.ZeppAuthError, z.ZeppProtocolError, z.ZeppStepError):
        assert issubclass(кл, z.ZeppLoginError)
    assert not issubclass(z.ZeppStepError, z.ZeppAuthError)
    assert not issubclass(z.ZeppProtocolError, z.ZeppAuthError)


def test_схемы_xiaomi_в_модуле_не_осталось():
    """Не косметика: пока имя живо, его можно позвать. Схема Xiaomi упиралась
    в проверку личности, недоступную стороннему приложению, и оставлять
    её запасной было нельзя — почта на обоих аккаунтах одна и та же,
    то есть отличить «не та схема» от «что-то ещё» стало бы невозможно."""
    for имя in ("ZeppVerificationError", "OAUTH2_PARAMS", "LOGIN_PREFIX",
                "XIAOMI_CODES", "_xiaomi_oauth2_code", "_get_code",
                "_strip_prefix", "_разобрать_отказ"):
        assert not hasattr(z, имя), f"{имя} осталось от схемы Xiaomi"
    # Адреса мёртвой схемы не должны остаться В КОДЕ. В шапке модуля они
    # названы намеренно — там объяснено, почему схема удалена, и вычистить
    # оттуда имена значило бы стереть разбор вместе с долгом. Поэтому
    # docstring из проверки исключается, а не текст в нём подгоняется
    исходник = Path(z.__file__).read_text(encoding="utf-8")
    код = исходник.split('"""', 2)[2]
    for адрес in ("account.xiaomi.com", "api-mifit-cn.huami.com",
                  "huami.health.loginview.do", "&&&START&&&"):
        assert адрес not in код, f"{адрес} остался в коде"
