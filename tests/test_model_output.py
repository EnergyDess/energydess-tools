"""Разбор ответа модели: обрыв по лимиту обязан быть виден как обрыв.

Почему на это есть тесты, а на соседний код нет. Отказ, который здесь
ловится, немой по своей природе: оборванный JSON приезжал в except как
JSONDecodeError с текстом «Unterminated string at line 22 column 5», и
по этому сообщению никто не догадывался, что дело в потолке токенов.
Проверка «сообщение названо правильно» глазами не делается — она делается
подстановкой ответа, у которого finish_reason == length.

main.py тянет базу, миграции и шаблоны, поэтому импортируется он один раз
и только ради одной функции; сама функция чистая и ничего не трогает.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("AGENT_WEBHOOK_KEY", "test-key-8f3a91")

from main import _model_output   # noqa: E402


def ответ(текст="ответ модели", finish="stop", токенов=100, **лишнее):
    """Ответ OpenRouter в том виде, в каком он приходит на самом деле."""
    payload = {
        "choices": [{"finish_reason": finish, "message": {"content": текст}}],
        "usage": {"completion_tokens": токенов},
    }
    payload.update(лишнее)
    return payload


def test_обычный_ответ_проходит():
    текст, сбой = _model_output(ответ(), "тест", 2000)
    assert текст == "ответ модели"
    assert сбой is None


def test_обрыв_по_лимиту_назван_обрывом():
    текст, сбой = _model_output(ответ('{"job_title": "Разрабо', finish="length", токенов=2000),
                                "тест", 2000)
    assert сбой is not None
    assert сбой.startswith("truncated"), сбой
    # Числа в сообщении обязательны: без них «не поместилось» не отличить
    # от «поместилось, но модель замолчала», и непонятно, куда поднимать
    assert "2000" in сбой


def test_обрыв_важнее_непустого_текста():
    """Оборванный ответ НЕ пустой — в нём есть начало. Раньше проверка шла
    по пустоте, и оборванный JSON проходил дальше как годный."""
    текст, сбой = _model_output(ответ("Здравствуйте! Меня зов", finish="length"), "тест", 1500)
    assert сбой and сбой.startswith("truncated")
    assert текст, "текст всё равно возвращается — он нужен для лога"


def test_пустой_ответ_отличается_от_обрыва():
    текст, сбой = _model_output(ответ("   "), "тест", 2000)
    assert сбой and сбой.startswith("empty"), сбой
    assert текст == ""


def test_native_finish_reason_когда_обычного_нет():
    """OpenRouter у части провайдеров кладёт причину только в native_*.
    Без запасного чтения обрыв выглядел бы как обычная остановка."""
    payload = {"choices": [{"native_finish_reason": "length",
                            "message": {"content": "обрыв"}}],
               "usage": {"completion_tokens": 700}}
    _, сбой = _model_output(payload, "тест", 700)
    assert сбой and сбой.startswith("truncated")


def test_без_usage_не_падает():
    """usage приходит не всегда. Отсутствие счётчика — не повод уронить
    запрос: расход в лог уедет как None, а решение принимается по finish."""
    payload = {"choices": [{"finish_reason": "stop", "message": {"content": "ок"}}]}
    текст, сбой = _model_output(payload, "тест", 2000)
    assert (текст, сбой) == ("ок", None)


def test_пустой_payload_не_падает():
    """Ответ без choices — это сбой провайдера, а не исключение в нашем коде."""
    текст, сбой = _model_output({}, "тест", 2000)
    assert текст == ""
    assert сбой and сбой.startswith("empty")


def test_запас_у_потолка_не_считается_сбоем(capsys):
    """80% потолка — повод предупредить в логе, но не повод отказать."""
    текст, сбой = _model_output(ответ(токенов=1900), "тест", 2000)
    assert сбой is None
    assert "ЗАПАС КОНЧАЕТСЯ" in capsys.readouterr().out


def test_расход_печатается_всегда(capsys):
    """Строка расхода — единственный способ узнать фактическое потребление
    на проде: usage больше нигде не сохраняется."""
    _model_output(ответ(токенов=793), "letter", 3000)
    вывод = capsys.readouterr().out
    assert "[letter]" in вывод and "793" in вывод and "3000" in вывод
