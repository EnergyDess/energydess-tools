"""Классификатор ответов Xiaomi: успех не должен превращаться в отказ входа.

Почему на это есть тесты. Отказ здесь того же класса, что немой сбой
из §6.0.1, только повёрнутый к пользователю: сообщение выглядит
осмысленным и потому не вызывает подозрений. Живой вход 2026-08-14 выдал
«Xiaomi требует подтвердить вход (код 0, 成功)» — код 0 и 成功 означают
успех, а человек пошёл искать в мобильном приложении подтверждение,
которого там нет и быть не могло.

Проверить это глазами нельзя: живого аккаунта весов у разработчика нет,
а единственный способ увидеть классификацию — подставить ответ.

`zepp_client` ничего не тянет, кроме httpx, — импортируется напрямую.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import zepp_client as z


def test_успешный_код_не_даёт_отказа_по_учётным_данным():
    """Главное правило: при code=0 ни одна ветка не говорит про пароль."""
    отказ = z._разобрать_отказ({"code": 0, "description": "成功"})
    assert not isinstance(отказ, z.ZeppAuthError)
    assert isinstance(отказ, z.ZeppStepError)
    assert "принял вход" in str(отказ)


def test_код_ноль_с_notificationurl_называет_вход_принятым():
    """Ровно тот ответ, что пришёл живому пользователю.

    Ветка устанавливается по тексту однозначно: «требует подтвердить вход»
    при коде 0 давало только поле notificationUrl — код 0 в XIAOMI_CODES
    не значится, а ветка captchaUrl пишет про капчу."""
    отказ = z._разобрать_отказ({
        "code": 0, "description": "成功",
        "notificationUrl": "https://account.xiaomi.com/identity/authStart?x=1",
    })
    текст = str(отказ)
    assert isinstance(отказ, z.ZeppVerificationError)
    assert "Логин и пароль Xiaomi принял" in текст      # а не «прервал вход»
    assert "https://account.xiaomi.com/identity/authStart?x=1" in текст
    assert "приложени" not in текст.lower()             # проверка НЕ в приложении


def test_адрес_проверки_показывается_а_не_проглатывается():
    отказ = z._разобрать_отказ({"code": 87001, "captchaUrl": "https://x.mi/cap?id=7"})
    assert "https://x.mi/cap?id=7" in str(отказ)


def test_неверный_пароль_остаётся_ошибкой_учётных_данных():
    """Отрицательный контроль: правка не должна была смягчить настоящий отказ."""
    отказ = z._разобрать_отказ({"code": 70016, "description": "login verification error"})
    assert isinstance(отказ, z.ZeppAuthError)
    assert "70016" in str(отказ)


def test_незнакомый_код_не_схлопывается_в_известный():
    отказ = z._разобрать_отказ({"code": 12345, "description": "нечто новое"})
    assert type(отказ) is z.ZeppProtocolError
    assert "12345" in str(отказ) and "нечто новое" in str(отказ)


def test_ответ_без_кода_вовсе():
    отказ = z._разобрать_отказ({"sid": "x"})
    assert isinstance(отказ, z.ZeppProtocolError)


def test_имя_шага_попадает_в_текст():
    отказ = z._разобрать_отказ({"code": 0}, шаг="serviceLoginAuth2")
    assert "serviceLoginAuth2" in str(отказ)


def test_каждый_класс_остаётся_отдельным():
    """Ловить ZeppLoginError одной строкой можно, различать — обязательно."""
    for кл in (z.ZeppAuthError, z.ZeppVerificationError,
               z.ZeppProtocolError, z.ZeppStepError):
        assert issubclass(кл, z.ZeppLoginError)
    assert not issubclass(z.ZeppStepError, z.ZeppAuthError)
    assert not issubclass(z.ZeppStepError, z.ZeppVerificationError)


def test_в_лог_не_уходят_значения_подписей(capsys):
    """`_след` печатает ИМЕНА полей. Значения — это `_sign`, `pwd`, `qs`."""
    z._разобрать_отказ({"code": 70016, "_sign": "СЕКРЕТНАЯ-ПОДПИСЬ",
                        "pwd": "ХЕШ-ПАРОЛЯ", "qs": "СТРОКА-ЗАПРОСА"})
    напечатано = capsys.readouterr().out
    assert "_sign" in напечатано and "pwd" in напечатано      # имена есть
    assert "СЕКРЕТНАЯ-ПОДПИСЬ" not in напечатано              # значений нет
    assert "ХЕШ-ПАРОЛЯ" not in напечатано
    assert "СТРОКА-ЗАПРОСА" not in напечатано


def test_пустые_поля_не_считаются_признаком():
    """В ответе Xiaomi ключи captchaUrl и notificationUrl приходят ВСЕГДА,
    в неудачном входе — пустыми строками. Признаком является значение."""
    отказ = z._разобрать_отказ({"code": 70016, "captchaUrl": "",
                                "notificationUrl": "", "location": ""})
    assert isinstance(отказ, z.ZeppAuthError)
