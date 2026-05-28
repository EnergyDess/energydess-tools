from fastapi import FastAPI, Request, Depends, Form
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, RedirectResponse
from bs4 import BeautifulSoup
import httpx
import os
import re
from dotenv import load_dotenv
from sqlalchemy.orm import Session

from database import get_db, init_db, User, Resume
from auth import hash_password, verify_password, create_token, get_current_user

load_dotenv()

app = FastAPI(title="EnergyDess Tools")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
MODEL = os.getenv("MODEL", "anthropic/claude-haiku-4-5")


@app.on_event("startup")
def startup():
    init_db()


# ── Главная ──────────────────────────────────────────────────────────────────

@app.get("/")
async def index(request: Request, user=Depends(get_current_user)):
    return templates.TemplateResponse(request=request, name="index.html", context={"user": user})


# ── Регистрация ───────────────────────────────────────────────────────────────

@app.get("/register")
async def register_page(request: Request, user=Depends(get_current_user)):
    if user:
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse(request=request, name="register.html", context={"error": None})


@app.post("/register")
async def register(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    password2: str = Form(...),
    db: Session = Depends(get_db),
):
    email = email.strip().lower()

    if password != password2:
        return templates.TemplateResponse(request=request, name="register.html",
                                          context={"error": "Пароли не совпадают"})
    if len(password) < 6:
        return templates.TemplateResponse(request=request, name="register.html",
                                          context={"error": "Пароль минимум 6 символов"})
    if db.query(User).filter(User.email == email).first():
        return templates.TemplateResponse(request=request, name="register.html",
                                          context={"error": "Email уже зарегистрирован"})

    user = User(email=email, password_hash=hash_password(password))
    db.add(user)
    db.commit()
    db.refresh(user)

    resume = Resume(user_id=user.id, resume_text="")
    db.add(resume)
    db.commit()

    token = create_token(user.id)
    response = RedirectResponse("/profile", status_code=302)
    response.set_cookie("access_token", token, httponly=True, max_age=60 * 60 * 24 * 30, samesite="lax")
    return response


# ── Вход ──────────────────────────────────────────────────────────────────────

@app.get("/login")
async def login_page(request: Request, user=Depends(get_current_user)):
    if user:
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse(request=request, name="login.html", context={"error": None})


@app.post("/login")
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    email = email.strip().lower()
    user = db.query(User).filter(User.email == email).first()

    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(request=request, name="login.html",
                                          context={"error": "Неверный email или пароль"})

    token = create_token(user.id)
    response = RedirectResponse("/", status_code=302)
    response.set_cookie("access_token", token, httponly=True, max_age=60 * 60 * 24 * 30, samesite="lax")
    return response


# ── Выход ─────────────────────────────────────────────────────────────────────

@app.get("/logout")
async def logout():
    response = RedirectResponse("/login", status_code=302)
    response.delete_cookie("access_token")
    return response


# ── Профиль ───────────────────────────────────────────────────────────────────

@app.get("/profile")
async def profile_page(request: Request, user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return RedirectResponse("/login", status_code=302)
    resume = db.query(Resume).filter(Resume.user_id == user.id).first()
    return templates.TemplateResponse(request=request, name="profile.html",
                                      context={"user": user, "resume": resume, "saved": False})


@app.post("/profile")
async def profile_save(
    request: Request,
    resume_text: str = Form(...),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not user:
        return RedirectResponse("/login", status_code=302)
    resume = db.query(Resume).filter(Resume.user_id == user.id).first()
    if not resume:
        resume = Resume(user_id=user.id, resume_text=resume_text)
        db.add(resume)
    else:
        resume.resume_text = resume_text
    db.commit()
    resume_obj = db.query(Resume).filter(Resume.user_id == user.id).first()
    return templates.TemplateResponse(request=request, name="profile.html",
                                      context={"user": user, "resume": resume_obj, "saved": True})


# ── HH Помощник ───────────────────────────────────────────────────────────────

@app.get("/hh")
async def hh_page(request: Request, user=Depends(get_current_user)):
    if not user:
        return RedirectResponse("/login", status_code=302)
    return templates.TemplateResponse(request=request, name="hh.html", context={"user": user})


# ── API: загрузка вакансии ────────────────────────────────────────────────────

@app.post("/api/fetch-url")
async def fetch_url(request: Request, user=Depends(get_current_user)):
    if not user:
        return JSONResponse({"error": "Необходима авторизация"}, status_code=401)

    data = await request.json()
    url = data.get("url", "").strip()

    if not url:
        return JSONResponse({"error": "Вставь ссылку на вакансию"}, status_code=400)
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
                },
                timeout=15.0,
            )
        if resp.status_code != 200:
            return JSONResponse({"error": f"Сайт вернул ошибку {resp.status_code}. Скопируй текст вручную."}, status_code=400)

        text = _extract_text(resp.text)
        if len(text) < 100:
            return JSONResponse({"error": "Не удалось извлечь текст. Скопируй вручную."}, status_code=400)
        if len(text) > 8000:
            text = text[:8000]
        return JSONResponse({"text": text})

    except httpx.TimeoutException:
        return JSONResponse({"error": "Сайт не ответил вовремя. Скопируй текст вручную."}, status_code=504)
    except Exception as e:
        return JSONResponse({"error": f"Не удалось загрузить страницу: {str(e)}"}, status_code=500)


# ── API: генерация письма ─────────────────────────────────────────────────────

@app.post("/api/generate-letter")
async def generate_letter(request: Request, user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return JSONResponse({"error": "Необходима авторизация"}, status_code=401)

    data = await request.json()
    job_text = data.get("job_text", "").strip()

    if not job_text:
        return JSONResponse({"error": "Вставь текст вакансии"}, status_code=400)
    if not OPENROUTER_API_KEY:
        return JSONResponse({"error": "API ключ не настроен"}, status_code=500)

    resume_obj = db.query(Resume).filter(Resume.user_id == user.id).first()
    resume_text = resume_obj.resume_text if resume_obj else ""

    if not resume_text.strip():
        return JSONResponse({"error": "Сначала добавь своё резюме в профиле"}, status_code=400)

    prompt = f"""Ты помогаешь написать сопроводительное письмо для соискателя.

РЕЗЮМЕ СОИСКАТЕЛЯ:
{resume_text}

ТЕКСТ ВАКАНСИИ:
{job_text}

Напиши ТОЛЬКО основной текст письма (100-180 слов). Строгие правила:

НАЧАЛО — первая строка письма ВСЕГДА должна начинаться с "Здравствуйте, меня зовут" и имени из резюме.

ОСНОВНОЙ ТЕКСТ:
- После приветствия — живое, цепляющее продолжение, покажи понимание сути вакансии
- Выдели 2-3 конкретных пункта опыта, максимально соответствующих требованиям
- Если в вакансии есть конкретные вопросы к кандидату — ответь на них
- Пиши от первого лица, живым языком, без штампов и клише
- Не используй слова: синергия, результативный, коммуникабельный, стрессоустойчивый, ответственный
- Тон: уверенный профессионал, не заискивающий

КОНЕЦ — если в резюме есть ссылки на портфолио, добавь их в конце.

ЗАПРЕЩЕНО:
- Любая подпись ("С уважением" и т.п.)
- Вводные фразы типа "Вот письмо:", "Конечно!"
"""

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "HTTP-Referer": "https://energydess.ru",
                    "X-Title": "EnergyDess HH Helper",
                },
                json={
                    "model": MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.8,
                    "max_tokens": 900,
                },
                timeout=40.0,
            )
        if response.status_code != 200:
            return JSONResponse({"error": f"Ошибка OpenRouter: {response.text}"}, status_code=500)

        result = response.json()
        letter = result["choices"][0]["message"]["content"].strip()
        return JSONResponse({"letter": letter})

    except httpx.TimeoutException:
        return JSONResponse({"error": "Превышено время ожидания. Попробуй ещё раз."}, status_code=504)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ── Утилиты ───────────────────────────────────────────────────────────────────

def _extract_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "meta", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    seen = set()
    clean = []
    for line in lines:
        if len(line) < 3 or line in seen:
            continue
        seen.add(line)
        clean.append(line)
    return "\n".join(clean)
