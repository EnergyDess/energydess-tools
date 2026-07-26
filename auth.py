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


def create_token(user_id: int) -> str:
    expire = datetime.utcnow() + timedelta(days=TOKEN_EXPIRE_DAYS)
    return jwt.encode({"sub": str(user_id), "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)


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
        return db.query(User).filter(User.id == user_id).first()
    except (JWTError, Exception):
        return None
