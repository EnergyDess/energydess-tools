import bcrypt
import secrets
from jose import JWTError, jwt
from datetime import datetime, timedelta
from fastapi import Cookie, Depends
from sqlalchemy.orm import Session
from database import get_db, User
import os

SECRET_KEY = os.getenv("SECRET_KEY", "energydess-secret-change-in-prod-2026")
ALGORITHM = "HS256"
TOKEN_EXPIRE_DAYS = 30


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def _pwd_stamp(user) -> int:
    """Отпечаток пароля для токена: секунды из password_changed_at, 0 если
    пароль ни разу не меняли."""
    ts = getattr(user, "password_changed_at", None)
    return int(ts.timestamp()) if ts else 0


def create_token(user_id: int, pwd_stamp: int = 0) -> str:
    """Токен сессии.

    pwd — отпечаток последней смены пароля. Без него смена пароля не
    отбирала доступ у того, кто увёл аккаунт: JWT подписан ключом и живёт
    30 дней независимо от пароля, то есть сброс пароля не выполнял своего
    единственного назначения.
    """
    expire = datetime.utcnow() + timedelta(days=TOKEN_EXPIRE_DAYS)
    return jwt.encode({"sub": str(user_id), "pwd": pwd_stamp, "exp": expire},
                      SECRET_KEY, algorithm=ALGORITHM)


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def decode_token_user_id(token: str) -> int | None:
    """user_id из подписанного токена, или None если токен битый/просрочен.
    Нужна там, где сессии ещё нет: например кука pending_verify на /verify-pending,
    выдаваемая при регистрации до входа. Работа с ключом подписи остаётся здесь,
    а не расползается по main.py."""
    if not token:
        return None
    try:
        return int(jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])["sub"])
    except (JWTError, ValueError, KeyError):
        return None


def get_current_user(access_token: str = Cookie(default=None), db: Session = Depends(get_db)):
    if not access_token:
        return None
    try:
        payload = jwt.decode(access_token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload["sub"])
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return None
        # Токен, выданный до последней смены пароля, недействителен.
        # Токены, выпущенные раньше этой правки, поля pwd не содержат — для них
        # подставляется 0, и они остаются рабочими, пока пароль не меняли.
        # Разлогинивать всех разом незачем: старая сессия опасна ровно тогда,
        # когда пароль сменили, а её не отозвали
        if payload.get("pwd", 0) != _pwd_stamp(user):
            return None
        return user
    except (JWTError, KeyError, ValueError, TypeError):
        # Битый или просроченный токен — это «не авторизован», нормальный
        # ход событий, а не сбой (CLAUDE.md §6.0.1, список осознанных).
        # KeyError/ValueError/TypeError — то же самое: подпись сошлась,
        # а `sub` отсутствует или не число, то есть токен всё равно негодный.
        return None
    except Exception as e:
        # ЛЮБАЯ другая беда — не «не авторизован», и раньше было именно так.
        # Стояло `except (JWTError, Exception)`, то есть сбой базы возвращал
        # None, и обработчик отвечал 401 «Не авторизован». Замер 2026-08-20:
        # при исчерпанном пуле соединений `TimeoutError` из SQLAlchemy
        # приезжал сюда, и пять запросов подряд получили 401 — человеку
        # сообщили, что он не вошёл, тогда как сессия была рабочая,
        # а кончились соединения. Немой отказ, который вдобавок ВРЁТ
        # о причине.
        #
        # Пробрасываем: 500 говорит правду («у нас сломалось»), 401 —
        # неправду («это вы не представились»).
        print(f"[auth] сессия НЕ разобрана из-за сбоя, не из-за токена: "
              f"{type(e).__name__}: {e}", flush=True)
        raise
