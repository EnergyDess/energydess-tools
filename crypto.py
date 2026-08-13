# -*- coding: utf-8 -*-
"""Шифрование чужих учётных данных перед записью в базу.

Пока этим пользуется только привязка умных весов Zepp Life: логин, пароль
и токен сессии стороннего сервиса (см. ScaleConnection). Вынесено из main.py
в отдельный модуль, потому что то же шифрование нужно миграции в database.py,
а импортировать main оттуда нельзя — зависимость развернулась бы наоборот
и потянула за собой весь FastAPI.

Ключ живёт в CREDENTIALS_ENCRYPTION_KEY (секрет Fly), не в коде и не в базе:
лежал бы он рядом с данными — шифрование не значило бы ничего.
"""
import os

CREDENTIALS_ENCRYPTION_KEY = os.getenv("CREDENTIALS_ENCRYPTION_KEY", "")


def is_configured() -> bool:
    return bool(CREDENTIALS_ENCRYPTION_KEY)


def _fernet():
    # Импорт внутри функции: без ключа модуль всё равно бесполезен, а
    # cryptography не нужен для остальных 99% работы приложения
    from cryptography.fernet import Fernet
    if not CREDENTIALS_ENCRYPTION_KEY:
        raise RuntimeError("CREDENTIALS_ENCRYPTION_KEY не настроен")
    return Fernet(CREDENTIALS_ENCRYPTION_KEY.encode())


def encrypt(text: str) -> str:
    return _fernet().encrypt(text.encode()).decode()


def decrypt(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()


def encrypt_optional(text: str | None) -> str | None:
    """Для необязательных полей: None остаётся None, а не превращается в шифр
    от строки «None»."""
    return encrypt(text) if text else None


def decrypt_optional(token: str | None) -> str | None:
    return decrypt(token) if token else None


def ключ_отпечаток() -> str:
    """Отпечаток ключа — для производных, которые должны быть постоянными,
    но не должны раскрывать сам ключ.

    Нужен `zepp_client.устройство`: постоянный `deviceId` считается от связки
    «отпечаток ключа + id пользователя». Сам ключ туда отдавать нельзя —
    производная уходит третьей стороне (Xiaomi) в заголовке Cookie, и брать
    её от секрета напрямую значит выносить материал секрета наружу.

    Пустой ключ даёт пустой отпечаток, а не исключение: вызывающий сам
    решает, что делать без шифрования (эндпоинт весов отказывает раньше)."""
    if not CREDENTIALS_ENCRYPTION_KEY:
        return ""
    import hashlib
    return hashlib.sha256(CREDENTIALS_ENCRYPTION_KEY.encode()).hexdigest()
