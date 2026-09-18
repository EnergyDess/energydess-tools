"""Ключ OpenRouter: прод и стенд разделены, отката на ключ прода нет (№346, заход 3)."""
import os

os.environ.setdefault("DB_PATH", "./test_or_key.db")

import or_key  # noqa: E402

ПРОД = "prod-ключ-для-теста"
СТЕНД = "stand-ключ-для-теста"


def test_на_проде_ключ_прода_и_ключ_стенда_не_нужен():
    ключ, причина = or_key.выбрать_ключ({"FLY_APP_NAME": "x", "OPENROUTER_API_KEY": ПРОД,
                                         "OPENROUTER_STAND_KEY": СТЕНД})
    assert ключ == ПРОД and причина == ""


def test_на_стенде_без_ключа_стенда_ПУСТО_а_не_ключ_прода():
    ключ, причина = or_key.выбрать_ключ({"OPENROUTER_API_KEY": ПРОД})
    assert ключ == ""
    assert "OPENROUTER_STAND_KEY" in причина


def test_ключ_стенда_равный_ключу_прода_не_принимается():
    ключ, причина = or_key.выбрать_ключ({"OPENROUTER_API_KEY": ПРОД,
                                         "OPENROUTER_STAND_KEY": ПРОД})
    assert ключ == "" and "совпадает" in причина


def test_на_стенде_берётся_ключ_стенда():
    ключ, _ = or_key.выбрать_ключ({"OPENROUTER_API_KEY": ПРОД,
                                   "OPENROUTER_STAND_KEY": СТЕНД})
    assert ключ == СТЕНД


def test_отпечаток_не_содержит_ключа():
    assert ПРОД not in or_key.отпечаток(ПРОД) and len(or_key.отпечаток(ПРОД)) == 12


def test_отказ_на_стенде_называет_ключ_стенда(monkeypatch):
    import main
    monkeypatch.delenv("FLY_APP_NAME", raising=False)
    monkeypatch.setattr(main, "КЛЮЧ_НЕТ_ПРИЧИНА", or_key.выбрать_ключ({})[1])
    assert "OPENROUTER_STAND_KEY" in main._без_ключа("API ключ не настроен")


def test_на_проде_текст_отказа_прежний(monkeypatch):
    import main
    monkeypatch.setenv("FLY_APP_NAME", "x")
    monkeypatch.setattr(main, "КЛЮЧ_НЕТ_ПРИЧИНА", "на проде не задан OPENROUTER_API_KEY")
    assert main._без_ключа("API ключ не настроен") == "API ключ не настроен"
