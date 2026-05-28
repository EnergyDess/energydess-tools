from fastapi import FastAPI, Request, Depends, Form
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, RedirectResponse
from bs4 import BeautifulSoup
import httpx
import os
from dotenv import load_dotenv
from sqlalchemy.orm import Session

from database import get_db, init_db, User, Resume, ToolAccess
from auth import hash_password, verify_password, create_token, get_current_user

load_dotenv()

app = FastAPI(title="EnergyDess Tools")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
MODEL = os.getenv("MODEL", "anthropic/claude-haiku-4-5")

TOOLS = [
    {
        "id": "hh",
        "name": "HH Помощник",
        "icon": "📝",
        "color": "purple",
        "url": "/hh",
        "desc": "Вставь текст вакансии — получи готовое сопроводительное письмо под твоё резюме за 30 секунд.",
        "active": True,
    },
    {
        "id": "workout",
        "name": "Программа тренировок",
        "icon": "💪",
        "color": "blue",
        "url": "#",
        "desc": "Персональный план тренировок с учётом целей, уровня и расписания.",
        "active": False,
    },
    {
        "id": "nutrition",
        "name": "Калькулятор питания",
        "icon": "🥗",
        "color": "green",
        "url": "#",
        "desc": "Подсчёт калорий и БЖУ, дневник питания, подбор рациона под цели.",
        "active": False,
    },
]


def user_has_access(user: User, tool_id: str, db: Session) -> bool:
    if user.is_admin:
        return True
    return db.query(ToolAccess).filter(
        ToolAccess.user_id == user.id,
        ToolAccess.tool_id == tool_id
    ).first() is not None


@app.on_event("startup")
def startup():
    init_db()


# ── Главная / Landing ─────────────────────────────────────────────────────────

@app.get("/")
async def index(request: Request, user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return templates.TemplateResponse(request=request, name="landing.html")

    tools_with_access = [
        {**t, "has_access": user_has_access(user, t["id"], db)}
        for t in TOOLS
    ]
    return templates.TemplateResponse(request=request, name="index.html",
                                      context={"user": user, "tools": tools_with_access})


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

    is_first = db.query(User).count() == 0
    user = User(email=email, password_hash=hash_password(password), is_admin=is_first)
    db.add(user)
    db.commit()
    db.refresh(user)

    resume = Resume(user_id=user.id, resume_text="")
    db.add(resume)
    db.commit()

    token = create_token(user.id)
    redirect_to = "/profile" if is_first else "/profile"
    response = RedirectResponse(redirect_to, status_code=302)
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
    response = RedirectResponse("/", status_code=302)
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
    resume = db.query(Resume).filter(Resume.user_id == user.id).first()
    return templates.TemplateResponse(request=request, name="profile.html",
                                      context={"user": user, "resume": resume, "saved": True})


# ── Админ панель ──────────────────────────────────────────────────────────────

@app.get("/admin")
async def admin_page(request: Request, user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user or not user.is_admin:
        return RedirectResponse("/", status_code=302)

    users = db.query(User).filter(User.id != user.id).order_by(User.created_at).all()
    accesses = db.query(ToolAccess).all()
    access_set = {(a.user_id, a.tool_id) for a in accesses}

    users_data = []
    for u in users:
        users_data.append({
            "id": u.id,
            "email": u.email,
            "created_at": u.created_at,
            "tools": {t["id"]: (u.id, t["id"]) in access_set for t in TOOLS},
        })

    return templates.TemplateResponse(request=request, name="admin.html",
                                      context={"user": user, "users": users_data, "tools": TOOLS})


@app.post("/admin/toggle")
async def admin_toggle(
    request: Request,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not user or not user.is_admin:
        return JSONResponse({"error": "Forbidden"}, status_code=403)

    data = await request.json()
    target_user_id = int(data["user_id"])
    tool_id = data["tool_id"]

    existing = db.query(ToolAccess).filter(
        ToolAccess.user_id == target_user_id,
        ToolAccess.tool_id == tool_id
    ).first()

    if existing:
        db.delete(existing)
        db.commit()
        return JSONResponse({"access": False})
    else:
        db.add(ToolAccess(user_id=target_user_id, tool_id=tool_id))
        db.commit()
        return JSONResponse({"access": True})


# ── HH Помощник ───────────────────────────────────────────────────────────────

@app.get("/hh")
async def hh_page(request: Request, user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return RedirectResponse("/login", status_code=302)
    if not user_has_access(user, "hh", db):
        return RedirectResponse("/?locked=hh", status_code=302)
    return templates.TemplateResponse(request=request, name="hh.html", context={"user": user})


# ── API: загрузка вакансии ────────────────────────────────────────────────────

@app.post("/api/fetch-url")
async def fetch_url(request: Request, user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user or not user_has_access(user, "hh", db):
        return JSONResponse({"error": "Нет доступа"}, status_code=403)

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
        return JSONResponse({"text": text[:8000]})
    except httpx.TimeoutException:
        return JSONResponse({"error": "Сайт не ответил. Скопируй текст вручную."}, status_code=504)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ── API: генерация письма ─────────────────────────────────────────────────────

@app.post("/api/generate-letter")
async def generate_letter(request: Request, user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user or not user_has_access(user, "hh", db):
        return JSONResponse({"error": "Нет доступа"}, status_code=403)

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

НАЧАЛО — первая строка ВСЕГДА начинается с "Здравствуйте, меня зовут" и имени из резюме.

ОСНОВНОЙ ТЕКСТ:
- После приветствия — живое, цепляющее продолжение, покажи понимание сути вакансии
- Выдели 2-3 конкретных пункта опыта, максимально соответствующих требованиям
- Пиши от первого лица, живым языком, без штампов и клише
- Не используй: синергия, результативный, коммуникабельный, стрессоустойчивый, ответственный
- Тон: уверенный профессионал

КОНЕЦ — если в резюме есть ссылки на портфолио, добавь их.
ЗАПРЕЩЕНО: любая подпись, вводные фразы типа "Вот письмо:"
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
        letter = response.json()["choices"][0]["message"]["content"].strip()
        return JSONResponse({"letter": letter})
    except httpx.TimeoutException:
        return JSONResponse({"error": "Превышено время ожидания. Попробуй ещё раз."}, status_code=504)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


def _extract_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "meta", "noscript"]):
        tag.decompose()
    lines = [l.strip() for l in soup.get_text(separator="\n").splitlines() if l.strip()]
    seen, clean = set(), []
    for line in lines:
        if len(line) >= 3 and line not in seen:
            seen.add(line)
            clean.append(line)
    return "\n".join(clean)
