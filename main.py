from datetime import datetime, timedelta
from fastapi import FastAPI, Request, Depends, Form, UploadFile, File
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.exceptions import HTTPException
from bs4 import BeautifulSoup
import httpx
import os
import base64
from dotenv import load_dotenv
from sqlalchemy.orm import Session

from database import (get_db, init_db, migrate_db, User, Resume, ToolAccess, EnshroudedSlot,
                      NutritionProfile, FoodLog, CustomFood, CustomRecipe, RecipeIngredient,
                      WaterLog, WeightLog)
from auth import hash_password, verify_password, create_token, get_current_user, generate_token

load_dotenv()

app = FastAPI(title="EnergyDess Tools")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

OPENROUTER_API_KEY  = os.getenv("OPENROUTER_API_KEY", "")
MODEL               = os.getenv("MODEL", "anthropic/claude-haiku-4-5")
LETTER_MODEL        = os.getenv("LETTER_MODEL", "anthropic/claude-sonnet-4-5")
RESEND_API_KEY      = os.getenv("RESEND_API_KEY", "")
BASE_URL            = os.getenv("BASE_URL", "https://energydess.ru")

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
        "id": "enshrouded",
        "name": "Enshrouded",
        "icon": "🛡",
        "color": "orange",
        "url": "/enshrouded",
        "desc": "Трекер доспехов Enshrouded — отмечай собранные сеты, редкость и уровни предметов.",
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
        "name": "Дневник питания",
        "icon": "🥗",
        "color": "green",
        "url": "/nutrition",
        "desc": "Дневник еды, счётчик КБЖУ, штрих-код сканер, трекер веса и AI-анализ рациона.",
        "active": True,
    },
]


def user_has_access(user: User, tool_id: str, db: Session) -> bool:
    if user.is_admin:
        return True
    return db.query(ToolAccess).filter(
        ToolAccess.user_id == user.id,
        ToolAccess.tool_id == tool_id
    ).first() is not None


async def send_email(to: str, subject: str, html: str):
    if not RESEND_API_KEY:
        return
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {RESEND_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": "EnergyDess <noreply@energydess.ru>",
                    "to": [to],
                    "subject": subject,
                    "html": html,
                },
            )
    except Exception:
        pass


@app.exception_handler(404)
async def not_found_handler(request: Request, exc: HTTPException):
    return templates.TemplateResponse(request=request, name="404.html", status_code=404)


@app.api_route("/health", methods=["GET", "HEAD"])
async def health():
    return JSONResponse({"status": "ok"})


@app.post("/deploy-hook")
async def deploy_hook(request: Request):
    token = request.headers.get("X-Deploy-Token", "")
    expected = os.getenv("DEPLOY_SECRET", "")
    if not expected or token != expected:
        return JSONResponse({"error": "Forbidden"}, status_code=403)
    import subprocess
    subprocess.Popen(["bash", "-c", "sleep 2 && cd /var/www/energydess && git pull origin main && systemctl restart energydess"])
    return JSONResponse({"ok": True})


@app.on_event("startup")
def startup():
    init_db()
    migrate_db()


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
                                          context={"error": "Пароли не совпадают", "email": email})
    if len(password) < 6:
        return templates.TemplateResponse(request=request, name="register.html",
                                          context={"error": "Пароль минимум 6 символов", "email": email})
    if db.query(User).filter(User.email == email).first():
        return templates.TemplateResponse(request=request, name="register.html",
                                          context={"error": "Email уже зарегистрирован", "email": email})

    is_first = db.query(User).count() == 0
    vtok = generate_token()
    vexp = datetime.utcnow() + timedelta(hours=24)
    user = User(
        email=email,
        password_hash=hash_password(password),
        is_admin=is_first,
        is_verified=True if is_first else False,
        verification_token=None if is_first else vtok,
        verification_token_expires=None if is_first else vexp,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    resume = Resume(user_id=user.id, resume_text="")
    db.add(resume)
    db.commit()

    if not is_first:
        link = f"{BASE_URL}/verify/{vtok}"
        await send_email(
            to=email,
            subject="Подтвердите регистрацию на EnergyDess",
            html=f"""
<div style="font-family:sans-serif;max-width:480px;margin:0 auto;padding:32px 24px;background:#07070f;border-radius:16px;border:1px solid rgba(255,255,255,0.08)">
  <div style="font-size:1.5rem;font-weight:800;margin-bottom:8px;color:#dde2f0">⚡ EnergyDess</div>
  <div style="color:#5a6888;font-size:0.875rem;margin-bottom:24px">Подтверждение регистрации</div>
  <p style="color:#dde2f0;line-height:1.6;margin-bottom:24px">
    Для завершения регистрации перейдите по ссылке ниже. Ссылка действует 24 часа.
  </p>
  <a href="{link}"
     style="display:inline-block;padding:13px 28px;background:linear-gradient(135deg,#7c4dff,#00d4ff);color:#fff;text-decoration:none;border-radius:10px;font-weight:700;font-size:0.95rem">
    Подтвердить email →
  </a>
  <p style="color:#2a3050;font-size:0.78rem;margin-top:24px">
    Если вы не регистрировались на EnergyDess — просто проигнорируйте это письмо.
  </p>
</div>""",
        )
        return RedirectResponse("/verify-pending", status_code=302)

    token = create_token(user.id)
    response = RedirectResponse("/profile", status_code=302)
    response.set_cookie("access_token", token, httponly=True, max_age=60 * 60 * 24 * 30, samesite="lax")
    return response


# ── Вход ──────────────────────────────────────────────────────────────────────

@app.get("/login")
async def login_page(request: Request, user=Depends(get_current_user),
                     verified: str = None, error: str = None):
    if user:
        return RedirectResponse("/", status_code=302)
    msg = None
    if verified:
        msg = "✓ Email подтверждён — теперь можно войти"
    elif error == "bad_token":
        msg = "Неверная ссылка подтверждения"
    elif error == "expired_token":
        msg = "Ссылка устарела — зарегистрируйтесь заново"
    return templates.TemplateResponse(request=request, name="login.html",
                                      context={"error": None, "info": msg})


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

    if user.is_verified is False:
        return templates.TemplateResponse(request=request, name="login.html",
                                          context={"error": "Сначала подтвердите email — проверьте почту"})

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


# ── Email verification ────────────────────────────────────────────────────────

@app.get("/verify-pending")
async def verify_pending(request: Request):
    return templates.TemplateResponse(request=request, name="verify_pending.html")


@app.get("/verify/{token}")
async def verify_email(token: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.verification_token == token).first()
    if not user:
        return RedirectResponse("/login?error=bad_token", status_code=302)
    if user.verification_token_expires and user.verification_token_expires < datetime.utcnow():
        return RedirectResponse("/login?error=expired_token", status_code=302)
    user.is_verified = True
    user.verification_token = None
    user.verification_token_expires = None
    db.commit()
    return RedirectResponse("/login?verified=1", status_code=302)


# ── Forgot / Reset password ───────────────────────────────────────────────────

@app.get("/forgot-password")
async def forgot_page(request: Request):
    return templates.TemplateResponse(request=request, name="forgot_password.html",
                                      context={"sent": False, "error": None})


@app.post("/forgot-password")
async def forgot_post(request: Request, email: str = Form(...), db: Session = Depends(get_db)):
    email = email.strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if user:
        rtok = generate_token()
        user.reset_token = rtok
        user.reset_token_expires = datetime.utcnow() + timedelta(hours=1)
        db.commit()
        link = f"{BASE_URL}/reset-password/{rtok}"
        await send_email(
            to=email,
            subject="Сброс пароля EnergyDess",
            html=f"""
<div style="font-family:sans-serif;max-width:480px;margin:0 auto;padding:32px 24px;background:#07070f;border-radius:16px;border:1px solid rgba(255,255,255,0.08)">
  <div style="font-size:1.5rem;font-weight:800;margin-bottom:8px;color:#dde2f0">⚡ EnergyDess</div>
  <div style="color:#5a6888;font-size:0.875rem;margin-bottom:24px">Сброс пароля</div>
  <p style="color:#dde2f0;line-height:1.6;margin-bottom:24px">
    Для установки нового пароля перейдите по ссылке. Ссылка действует 1 час.
  </p>
  <a href="{link}"
     style="display:inline-block;padding:13px 28px;background:linear-gradient(135deg,#7c4dff,#00d4ff);color:#fff;text-decoration:none;border-radius:10px;font-weight:700;font-size:0.95rem">
    Сбросить пароль →
  </a>
  <p style="color:#2a3050;font-size:0.78rem;margin-top:24px">
    Если вы не запрашивали сброс — просто проигнорируйте это письмо.
  </p>
</div>""",
        )
    return templates.TemplateResponse(request=request, name="forgot_password.html",
                                      context={"sent": True, "error": None})


@app.get("/reset-password/{token}")
async def reset_page(token: str, request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.reset_token == token).first()
    if not user or (user.reset_token_expires and user.reset_token_expires < datetime.utcnow()):
        return templates.TemplateResponse(request=request, name="reset_password.html",
                                          context={"token": token, "error": "Ссылка недействительна или устарела", "done": False})
    return templates.TemplateResponse(request=request, name="reset_password.html",
                                      context={"token": token, "error": None, "done": False})


@app.post("/reset-password/{token}")
async def reset_post(
    token: str, request: Request,
    password: str = Form(...), password2: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.reset_token == token).first()
    if not user or (user.reset_token_expires and user.reset_token_expires < datetime.utcnow()):
        return templates.TemplateResponse(request=request, name="reset_password.html",
                                          context={"token": token, "error": "Ссылка недействительна", "done": False})
    if password != password2:
        return templates.TemplateResponse(request=request, name="reset_password.html",
                                          context={"token": token, "error": "Пароли не совпадают", "done": False})
    if len(password) < 6:
        return templates.TemplateResponse(request=request, name="reset_password.html",
                                          context={"token": token, "error": "Минимум 6 символов", "done": False})
    user.password_hash = hash_password(password)
    user.reset_token = None
    user.reset_token_expires = None
    db.commit()
    return templates.TemplateResponse(request=request, name="reset_password.html",
                                      context={"token": token, "error": None, "done": True})


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


# ── Enshrouded Трекер ─────────────────────────────────────────────────────────

@app.get("/enshrouded")
async def enshrouded_page(request: Request, user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return RedirectResponse("/login", status_code=302)
    if not user_has_access(user, "enshrouded", db):
        return RedirectResponse("/?locked=enshrouded", status_code=302)
    return templates.TemplateResponse(request=request, name="enshrouded.html", context={"user": user})


@app.get("/api/enshrouded/state")
async def get_enshrouded_state(user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    slots = db.query(EnshroudedSlot).filter(EnshroudedSlot.user_id == user.id).all()
    result = {}
    for s in slots:
        if s.set_id not in result:
            result[s.set_id] = {}
        result[s.set_id][s.slot_id] = {
            "owned": s.owned,
            "rarity": s.rarity,
            "level": s.level,
            "duplicates": s.duplicates,
        }
    return JSONResponse(result)


@app.post("/api/enshrouded/slot")
async def update_enshrouded_slot(request: Request, user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    data = await request.json()
    set_id = data.get("set_id")
    slot_id = data.get("slot_id")
    if not set_id or not slot_id:
        return JSONResponse({"error": "Нет set_id или slot_id"}, status_code=400)
    slot = db.query(EnshroudedSlot).filter(
        EnshroudedSlot.user_id == user.id,
        EnshroudedSlot.set_id == set_id,
        EnshroudedSlot.slot_id == slot_id,
    ).first()
    if not slot:
        slot = EnshroudedSlot(user_id=user.id, set_id=set_id, slot_id=slot_id)
        db.add(slot)
    slot.owned = data.get("owned", False)
    slot.rarity = data.get("rarity", "common")
    slot.level = data.get("level") or None
    slot.duplicates = data.get("duplicates", 0)
    db.commit()
    return JSONResponse({"ok": True})


@app.post("/api/enshrouded/import")
async def import_enshrouded_state(request: Request, user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    data = await request.json()
    for set_id, slots in data.items():
        for slot_id, slot_data in slots.items():
            slot = db.query(EnshroudedSlot).filter(
                EnshroudedSlot.user_id == user.id,
                EnshroudedSlot.set_id == set_id,
                EnshroudedSlot.slot_id == slot_id,
            ).first()
            if not slot:
                slot = EnshroudedSlot(user_id=user.id, set_id=set_id, slot_id=slot_id)
                db.add(slot)
            slot.owned = slot_data.get("owned", False)
            slot.rarity = slot_data.get("rarity", "common")
            slot.level = slot_data.get("level") or None
            slot.duplicates = slot_data.get("duplicates", 0)
    db.commit()
    return JSONResponse({"ok": True, "imported": sum(len(v) for v in data.values())})


# ── HH Помощник ───────────────────────────────────────────────────────────────

@app.get("/hh")
async def hh_page(request: Request, user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return RedirectResponse("/login", status_code=302)
    if not user_has_access(user, "hh", db):
        return RedirectResponse("/?locked=hh", status_code=302)
    resume = db.query(Resume).filter(Resume.user_id == user.id).first()
    return templates.TemplateResponse(request=request, name="hh.html",
                                      context={"user": user, "resume": resume})


# ── API: сохранение отображаемого имени ──────────────────────────────────────

@app.post("/api/save-display-name")
async def save_display_name(request: Request, user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    data = await request.json()
    name = data.get("name", "").strip()
    user_obj = db.query(User).filter(User.id == user.id).first()
    user_obj.display_name = name or None
    db.commit()
    return JSONResponse({"ok": True})


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

    prompt = f"""Напиши сопроводительное письмо. Только текст письма — ничего лишнего.

РЕЗЮМЕ:
{resume_text}

ВАКАНСИЯ:
{job_text}

ПРАВИЛА ТЕКСТА (строго):

Объём: 90–160 слов. Плотно, без воды.

Первая строка: "Здравствуйте, меня зовут [имя из резюме]." — и сразу к делу.

Что писать:
- Одним предложением — почему именно эта вакансия, не другая. Конкретная причина из текста вакансии: задача, формат, продукт. Не абстракции про "AI-стандарты" или "экспериментальные фишки".
- 2–3 факта из опыта, которые напрямую закрывают требования. Цифры, проекты, результаты — не прилагательные.
- Последние строки: если в резюме есть URL шоурила или портфолио — вставь ОБА адреса дословно из текста резюме, каждый на отдельной строке. Пропускать ссылки из резюме нельзя. Упоминать шоурил или портфолио без реального URL — запрещено.

Инструменты и программы:
- Упоминай ТОЛЬКО те инструменты, программы и сервисы, которые явно названы в резюме.
- Никогда не добавляй и не заменяй инструменты от себя — если что-то не упомянуто в резюме, не пиши это.

Запрещено:
- Слова: ответственный, коммуникабельный, стрессоустойчивый, нацелен на результат, командный игрок, синергия, динамично развивающийся
- Фразы: "буду рад", "жду вашего ответа", "готов к сотрудничеству", "рассмотрите мою кандидатуру", "я являюсь", "в данный момент"
- Итоговые фразы: "Надеюсь на...", "С уважением", "В заключение хочу"
- ИИ-зачины: "Конечно!", "Безусловно", "Рад помочь", "Вот письмо:"
- Клише-вступления: "Ваша вакансия — это именно то, что я искал", "вы попали в точку", "эта позиция идеально соответствует", "нашёл то, что искал", "ознакомившись с вакансией, я понял", "ищу позицию, где", "именно то место, где", "это именно та команда"
- Любое повторение сказанного выше

Пиши как человек, который уверен в себе и ценит чужое время. Не продавай себя — показывай факты.
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
                    "model": LETTER_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.5,
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


# ── API: сохранение резюме ────────────────────────────────────────────────────

@app.post("/api/save-resume")
async def save_resume_api(request: Request, user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    data = await request.json()
    text = data.get("text", "")
    resume = db.query(Resume).filter(Resume.user_id == user.id).first()
    if not resume:
        resume = Resume(user_id=user.id, resume_text=text)
        db.add(resume)
    else:
        resume.resume_text = text
    db.commit()
    return JSONResponse({"ok": True})


# ── API: загрузка файла резюме ────────────────────────────────────────────────

@app.post("/api/upload-resume")
async def upload_resume_file(
    file: UploadFile = File(...),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)

    name = (file.filename or "").lower()
    content = await file.read()

    try:
        if name.endswith(".pdf"):
            text = _extract_pdf(content)
        elif name.endswith((".docx", ".doc")):
            text = _extract_docx(content)
        else:
            return JSONResponse({"error": "Поддерживаются только PDF и DOCX"}, status_code=400)

        if not text.strip():
            return JSONResponse({"error": "Не удалось извлечь текст. Попробуй PDF."}, status_code=400)

        return JSONResponse({"text": text})
    except Exception as e:
        return JSONResponse({"error": f"Ошибка чтения файла: {str(e)}"}, status_code=500)


def _extract_pdf(content: bytes) -> str:
    import io
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(content))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _extract_docx(content: bytes) -> str:
    import io
    from docx import Document
    doc = Document(io.BytesIO(content))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


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


# ── Nutrition: helpers ────────────────────────────────────────────────────────

def _calc_tdee(gender: str, age: int, weight_kg: float, height_cm: float,
               activity_level: str, goal: str) -> dict:
    if gender == "female":
        bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age - 161
    else:
        bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age + 5
    multipliers = {
        "sedentary": 1.2, "light": 1.375, "moderate": 1.55,
        "active": 1.725, "very_active": 1.9,
    }
    tdee = bmr * multipliers.get(activity_level, 1.55)
    if goal == "lose":
        cal = int(tdee * 0.82)
    elif goal == "gain":
        cal = int(tdee * 1.15)
    else:
        cal = int(tdee)
    protein = int(weight_kg * 2.0)
    fat = int(cal * 0.25 / 9)
    carbs = max(0, int((cal - protein * 4 - fat * 9) / 4))
    water = int(weight_kg * 35)
    return {"calories": cal, "protein": protein, "fat": fat, "carbs": carbs, "water_ml": water}


_OFF_HEADERS = {"User-Agent": "EnergyDess-Nutrition/1.0 (https://energydess.ru)"}


async def _off_search(query: str) -> list:
    url = "https://search.openfoodfacts.org/search"
    params = {
        "q": query, "page_size": 25, "langs": "ru,en",
        "fields": "product_name,product_name_ru,brands,nutriments",
    }
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(url, params=params, headers=_OFF_HEADERS)
        products = r.json().get("hits", [])
    except Exception:
        return []
    results = []
    for p in products:
        name = p.get("product_name_ru") or p.get("product_name", "")
        if not name:
            continue
        n = p.get("nutriments", {})
        kcal = n.get("energy-kcal_100g") or n.get("energy-kcal") or 0
        if not kcal:
            continue
        brands = p.get("brands") or []
        if isinstance(brands, str):
            brands = brands.split(",")
        results.append({
            "name": name.strip(),
            "brand": (brands[0] if brands else "").strip(),
            "calories": round(float(kcal), 1),
            "protein": round(float(n.get("proteins_100g", 0)), 1),
            "fat": round(float(n.get("fat_100g", 0)), 1),
            "carbs": round(float(n.get("carbohydrates_100g", 0)), 1),
        })
    return results


async def _ai_food_estimate(query: str) -> list:
    if not OPENROUTER_API_KEY:
        return []
    prompt = f"""Оцени пищевую ценность блюда "{query}" на 100 грамм продукта.
Ответь ТОЛЬКО JSON без ```json и без пояснений:
{{"name":"уточнённое название блюда","calories":150,"protein":10,"fat":5,"carbs":20}}"""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}",
                         "HTTP-Referer": "https://energydess.ru", "X-Title": "EnergyDess Nutrition"},
                json={"model": MODEL, "messages": [{"role": "user", "content": prompt}],
                      "temperature": 0.2, "max_tokens": 150},
            )
        import json as _json
        text = resp.json()["choices"][0]["message"]["content"].strip()
        d = _json.loads(text)
        return [{
            "name": str(d.get("name", query)).strip(),
            "brand": "", "source": "ai",
            "calories": round(float(d["calories"]), 1),
            "protein": round(float(d["protein"]), 1),
            "fat": round(float(d["fat"]), 1),
            "carbs": round(float(d["carbs"]), 1),
        }]
    except Exception:
        return []


async def _off_barcode(code: str) -> dict | None:
    url = f"https://world.openfoodfacts.org/api/v0/product/{code}.json"
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(url, headers=_OFF_HEADERS)
        data = r.json()
    except Exception:
        return None
    if data.get("status") != 1:
        return None
    p = data.get("product", {})
    n = p.get("nutriments", {})
    name = p.get("product_name_ru") or p.get("product_name", "")
    kcal = n.get("energy-kcal_100g") or n.get("energy-kcal") or 0
    if not name or not kcal:
        return None
    return {
        "name": name.strip(),
        "brand": (p.get("brands") or "").split(",")[0].strip(),
        "calories": round(float(kcal), 1),
        "protein": round(float(n.get("proteins_100g", 0)), 1),
        "fat": round(float(n.get("fat_100g", 0)), 1),
        "carbs": round(float(n.get("carbohydrates_100g", 0)), 1),
        "barcode": code,
    }


def _diary_totals(logs: list) -> dict:
    meals = {"breakfast": [], "lunch": [], "dinner": [], "snack": []}
    for lg in logs:
        meals.get(lg.meal_type, meals["snack"]).append({
            "id": lg.id, "name": lg.food_name, "brand": lg.brand or "",
            "grams": lg.grams, "calories": round(lg.calories, 1),
            "protein": round(lg.protein, 1), "fat": round(lg.fat, 1),
            "carbs": round(lg.carbs, 1),
        })
    totals = {
        "calories": round(sum(l.calories for l in logs), 1),
        "protein": round(sum(l.protein for l in logs), 1),
        "fat": round(sum(l.fat for l in logs), 1),
        "carbs": round(sum(l.carbs for l in logs), 1),
    }
    return {"meals": meals, "totals": totals}


# ── Nutrition: page ───────────────────────────────────────────────────────────

@app.get("/nutrition")
async def nutrition_page(request: Request, user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return RedirectResponse("/login", status_code=302)
    if not user_has_access(user, "nutrition", db):
        return RedirectResponse("/?locked=nutrition", status_code=302)
    return templates.TemplateResponse(request=request, name="nutrition.html", context={"user": user})


# ── Nutrition: profile ────────────────────────────────────────────────────────

@app.get("/nutrition/api/profile")
async def nut_get_profile(user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    p = db.query(NutritionProfile).filter(NutritionProfile.user_id == user.id).first()
    if not p:
        return JSONResponse({"exists": False})
    return JSONResponse({
        "exists": True,
        "gender": p.gender, "age": p.age, "weight_kg": p.weight_kg,
        "height_cm": p.height_cm, "goal": p.goal, "activity_level": p.activity_level,
        "calorie_goal": p.calorie_goal, "protein_goal": p.protein_goal,
        "fat_goal": p.fat_goal, "carb_goal": p.carb_goal,
        "water_goal_ml": p.water_goal_ml,
        "target_weight_kg": p.target_weight_kg, "start_weight_kg": p.start_weight_kg,
    })


@app.post("/nutrition/api/profile")
async def nut_save_profile(request: Request, user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    data = await request.json()
    gender = data.get("gender", "male")
    age = int(data.get("age", 25))
    weight_kg = float(data.get("weight_kg", 70))
    height_cm = float(data.get("height_cm", 170))
    goal = data.get("goal", "maintain")
    activity_level = data.get("activity_level", "moderate")
    target_weight = data.get("target_weight_kg")

    targets = _calc_tdee(gender, age, weight_kg, height_cm, activity_level, goal)

    p = db.query(NutritionProfile).filter(NutritionProfile.user_id == user.id).first()
    if not p:
        p = NutritionProfile(user_id=user.id)
        db.add(p)
    p.gender = gender
    p.age = age
    p.weight_kg = weight_kg
    p.height_cm = height_cm
    p.goal = goal
    p.activity_level = activity_level
    p.calorie_goal = targets["calories"]
    p.protein_goal = targets["protein"]
    p.fat_goal = targets["fat"]
    p.carb_goal = targets["carbs"]
    p.water_goal_ml = targets["water_ml"]
    if target_weight:
        p.target_weight_kg = float(target_weight)
    if not p.start_weight_kg:
        p.start_weight_kg = weight_kg
    db.commit()
    return JSONResponse({"ok": True, "targets": targets})


# ── Nutrition: diary ──────────────────────────────────────────────────────────

@app.get("/nutrition/api/diary")
async def nut_diary(date: str = None, user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    d = date or datetime.now().strftime("%Y-%m-%d")
    logs = db.query(FoodLog).filter(FoodLog.user_id == user.id, FoodLog.log_date == d).order_by(FoodLog.created_at).all()
    water_logs = db.query(WaterLog).filter(WaterLog.user_id == user.id, WaterLog.log_date == d).all()
    water_ml = sum(w.amount_ml for w in water_logs)

    profile = db.query(NutritionProfile).filter(NutritionProfile.user_id == user.id).first()
    diary = _diary_totals(logs)
    diary["water_ml"] = water_ml
    diary["water_logs"] = [{"id": w.id, "amount_ml": w.amount_ml} for w in water_logs]
    diary["goals"] = {
        "calories": profile.calorie_goal if profile else 2000,
        "protein": profile.protein_goal if profile else 100,
        "fat": profile.fat_goal if profile else 65,
        "carbs": profile.carb_goal if profile else 250,
        "water_ml": profile.water_goal_ml if profile else 2000,
    }
    return JSONResponse(diary)


@app.post("/nutrition/api/log-food")
async def nut_log_food(request: Request, user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    data = await request.json()
    grams = float(data.get("grams", 100))
    cal_per_100 = float(data.get("calories", 0))
    protein_per_100 = float(data.get("protein", 0))
    fat_per_100 = float(data.get("fat", 0))
    carbs_per_100 = float(data.get("carbs", 0))
    log = FoodLog(
        user_id=user.id,
        log_date=data.get("date", datetime.now().strftime("%Y-%m-%d")),
        meal_type=data.get("meal_type", "breakfast"),
        food_name=data.get("name", ""),
        brand=data.get("brand", "") or None,
        grams=grams,
        calories=round(cal_per_100 * grams / 100, 1),
        protein=round(protein_per_100 * grams / 100, 1),
        fat=round(fat_per_100 * grams / 100, 1),
        carbs=round(carbs_per_100 * grams / 100, 1),
        barcode=data.get("barcode") or None,
    )
    db.add(log)
    db.commit()
    return JSONResponse({"ok": True, "id": log.id})


@app.delete("/nutrition/api/log-food/{log_id}")
async def nut_delete_food(log_id: int, user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    log = db.query(FoodLog).filter(FoodLog.id == log_id, FoodLog.user_id == user.id).first()
    if log:
        db.delete(log)
        db.commit()
    return JSONResponse({"ok": True})


# ── Nutrition: water ──────────────────────────────────────────────────────────

@app.post("/nutrition/api/water")
async def nut_log_water(request: Request, user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    data = await request.json()
    amount = int(data.get("amount_ml", 200))
    date = data.get("date", datetime.now().strftime("%Y-%m-%d"))
    entry = WaterLog(user_id=user.id, log_date=date, amount_ml=amount)
    db.add(entry)
    db.commit()
    total = sum(w.amount_ml for w in db.query(WaterLog).filter(
        WaterLog.user_id == user.id, WaterLog.log_date == date).all())
    return JSONResponse({"ok": True, "total_ml": total})


@app.delete("/nutrition/api/water/{log_id}")
async def nut_delete_water(log_id: int, user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    entry = db.query(WaterLog).filter(WaterLog.id == log_id, WaterLog.user_id == user.id).first()
    if entry:
        db.delete(entry)
        db.commit()
    return JSONResponse({"ok": True})


# ── Nutrition: food search ────────────────────────────────────────────────────

@app.get("/nutrition/api/search")
async def nut_search(q: str = "", user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    if not q.strip():
        return JSONResponse({"results": []})
    custom = db.query(CustomFood).filter(
        CustomFood.user_id == user.id,
        CustomFood.name.ilike(f"%{q}%")
    ).limit(5).all()
    custom_results = [{
        "name": f.name, "brand": f.brand or "", "source": "custom",
        "calories": f.calories_per_100g, "protein": f.protein_per_100g,
        "fat": f.fat_per_100g, "carbs": f.carbs_per_100g,
    } for f in custom]
    off_results = await _off_search(q)
    results = custom_results + off_results[:20]
    if not results:
        results += await _ai_food_estimate(q)
    return JSONResponse({"results": results})


@app.get("/nutrition/api/barcode/{code}")
async def nut_barcode(code: str, user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    custom = db.query(CustomFood).filter(
        CustomFood.user_id == user.id, CustomFood.barcode == code).first()
    if custom:
        return JSONResponse({
            "found": True, "source": "custom",
            "name": custom.name, "brand": custom.brand or "",
            "calories": custom.calories_per_100g, "protein": custom.protein_per_100g,
            "fat": custom.fat_per_100g, "carbs": custom.carbs_per_100g, "barcode": code,
        })
    result = await _off_barcode(code)
    if result:
        return JSONResponse({"found": True, "source": "off", **result})
    return JSONResponse({"found": False, "barcode": code})


@app.get("/nutrition/api/recent-foods")
async def nut_recent(user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    logs = db.query(FoodLog).filter(FoodLog.user_id == user.id).order_by(
        FoodLog.created_at.desc()).limit(200).all()
    seen, results = set(), []
    for lg in logs:
        key = lg.food_name.lower()
        if key not in seen:
            seen.add(key)
            results.append({
                "name": lg.food_name, "brand": lg.brand or "",
                "calories": round(lg.calories / lg.grams * 100, 1),
                "protein": round(lg.protein / lg.grams * 100, 1),
                "fat": round(lg.fat / lg.grams * 100, 1),
                "carbs": round(lg.carbs / lg.grams * 100, 1),
            })
        if len(results) >= 20:
            break
    return JSONResponse({"results": results})


@app.get("/nutrition/api/frequent-foods")
async def nut_frequent(user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    from collections import Counter
    logs = db.query(FoodLog).filter(FoodLog.user_id == user.id).all()
    counts = Counter(lg.food_name for lg in logs)
    top_names = [name for name, _ in counts.most_common(20)]
    results = []
    for name in top_names:
        lg = next((l for l in logs if l.food_name == name), None)
        if lg:
            results.append({
                "name": lg.food_name, "brand": lg.brand or "",
                "calories": round(lg.calories / lg.grams * 100, 1),
                "protein": round(lg.protein / lg.grams * 100, 1),
                "fat": round(lg.fat / lg.grams * 100, 1),
                "carbs": round(lg.carbs / lg.grams * 100, 1),
                "count": counts[name],
            })
    return JSONResponse({"results": results})


# ── Nutrition: custom foods ───────────────────────────────────────────────────

@app.post("/nutrition/api/custom-food")
async def nut_create_custom_food(request: Request, user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    data = await request.json()
    food = CustomFood(
        user_id=user.id,
        name=data.get("name", "").strip(),
        brand=data.get("brand", "").strip() or None,
        barcode=data.get("barcode", "").strip() or None,
        calories_per_100g=float(data.get("calories", 0)),
        protein_per_100g=float(data.get("protein", 0)),
        fat_per_100g=float(data.get("fat", 0)),
        carbs_per_100g=float(data.get("carbs", 0)),
    )
    db.add(food)
    db.commit()
    return JSONResponse({"ok": True, "id": food.id,
                         "name": food.name, "brand": food.brand or "",
                         "calories": food.calories_per_100g, "protein": food.protein_per_100g,
                         "fat": food.fat_per_100g, "carbs": food.carbs_per_100g})


# ── Nutrition: recipes ────────────────────────────────────────────────────────

@app.get("/nutrition/api/recipes")
async def nut_recipes(user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    recipes = db.query(CustomRecipe).filter(CustomRecipe.user_id == user.id).order_by(
        CustomRecipe.created_at.desc()).all()
    result = []
    for r in recipes:
        ingredients = db.query(RecipeIngredient).filter(RecipeIngredient.recipe_id == r.id).all()
        result.append({
            "id": r.id, "name": r.name, "total_grams": r.total_grams,
            "calories": r.calories, "protein": r.protein, "fat": r.fat, "carbs": r.carbs,
            "ingredients": [{"name": i.food_name, "grams": i.grams, "calories": i.calories,
                              "protein": i.protein, "fat": i.fat, "carbs": i.carbs}
                             for i in ingredients],
        })
    return JSONResponse({"recipes": result})


@app.post("/nutrition/api/recipes")
async def nut_create_recipe(request: Request, user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    data = await request.json()
    ingredients = data.get("ingredients", [])
    total_g = sum(float(i.get("grams", 0)) for i in ingredients)
    total_cal = sum(float(i.get("calories", 0)) for i in ingredients)
    total_prot = sum(float(i.get("protein", 0)) for i in ingredients)
    total_fat = sum(float(i.get("fat", 0)) for i in ingredients)
    total_carbs = sum(float(i.get("carbs", 0)) for i in ingredients)
    recipe = CustomRecipe(
        user_id=user.id, name=data.get("name", "Рецепт"),
        total_grams=total_g, calories=round(total_cal, 1),
        protein=round(total_prot, 1), fat=round(total_fat, 1), carbs=round(total_carbs, 1),
    )
    db.add(recipe)
    db.commit()
    db.refresh(recipe)
    for ing in ingredients:
        g = float(ing.get("grams", 0))
        cal100 = float(ing.get("calories", 0))
        db.add(RecipeIngredient(
            recipe_id=recipe.id, food_name=ing.get("name", ""),
            grams=g, calories=round(cal100 * g / 100, 1),
            protein=round(float(ing.get("protein", 0)) * g / 100, 1),
            fat=round(float(ing.get("fat", 0)) * g / 100, 1),
            carbs=round(float(ing.get("carbs", 0)) * g / 100, 1),
        ))
    db.commit()
    return JSONResponse({"ok": True, "id": recipe.id})


@app.delete("/nutrition/api/recipes/{recipe_id}")
async def nut_delete_recipe(recipe_id: int, user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    recipe = db.query(CustomRecipe).filter(
        CustomRecipe.id == recipe_id, CustomRecipe.user_id == user.id).first()
    if recipe:
        db.query(RecipeIngredient).filter(RecipeIngredient.recipe_id == recipe_id).delete()
        db.delete(recipe)
        db.commit()
    return JSONResponse({"ok": True})


# ── Nutrition: weight & measurements ─────────────────────────────────────────

@app.get("/nutrition/api/weight")
async def nut_weight(user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    logs = db.query(WeightLog).filter(WeightLog.user_id == user.id).order_by(
        WeightLog.log_date.desc()).limit(60).all()
    profile = db.query(NutritionProfile).filter(NutritionProfile.user_id == user.id).first()
    return JSONResponse({
        "logs": [{"date": l.log_date, "weight_kg": l.weight_kg,
                  "waist_cm": l.waist_cm, "hips_cm": l.hips_cm, "chest_cm": l.chest_cm}
                 for l in logs],
        "start_weight": profile.start_weight_kg if profile else None,
        "target_weight": profile.target_weight_kg if profile else None,
    })


@app.post("/nutrition/api/weight")
async def nut_log_weight(request: Request, user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    data = await request.json()
    date = data.get("date", datetime.now().strftime("%Y-%m-%d"))
    existing = db.query(WeightLog).filter(WeightLog.user_id == user.id,
                                           WeightLog.log_date == date).first()
    if not existing:
        existing = WeightLog(user_id=user.id, log_date=date)
        db.add(existing)
    if data.get("weight_kg") is not None:
        existing.weight_kg = float(data["weight_kg"])
    if data.get("waist_cm") is not None:
        existing.waist_cm = float(data["waist_cm"])
    if data.get("hips_cm") is not None:
        existing.hips_cm = float(data["hips_cm"])
    if data.get("chest_cm") is not None:
        existing.chest_cm = float(data["chest_cm"])
    db.commit()
    if data.get("weight_kg") is not None:
        profile = db.query(NutritionProfile).filter(NutritionProfile.user_id == user.id).first()
        if profile:
            profile.weight_kg = float(data["weight_kg"])
            db.commit()
    return JSONResponse({"ok": True})


# ── Nutrition: history / weekly ───────────────────────────────────────────────

@app.get("/nutrition/api/weekly")
async def nut_weekly(user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    today = datetime.now().date()
    days = []
    for i in range(6, -1, -1):
        d = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        logs = db.query(FoodLog).filter(FoodLog.user_id == user.id, FoodLog.log_date == d).all()
        days.append({
            "date": d,
            "calories": round(sum(l.calories for l in logs), 0),
            "protein": round(sum(l.protein for l in logs), 1),
        })
    return JSONResponse({"days": days})


# ── Nutrition: AI chat ───────────────────────────────────────────────────────

@app.post("/nutrition/api/ai-chat")
async def nut_ai_chat(request: Request, user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user or not user_has_access(user, "nutrition", db):
        return JSONResponse({"error": "Нет доступа"}, status_code=403)
    data = await request.json()
    messages = data.get("messages", [])
    date = data.get("date", datetime.now().strftime("%Y-%m-%d"))

    logs = db.query(FoodLog).filter(FoodLog.user_id == user.id, FoodLog.log_date == date).all()
    water = sum(w.amount_ml for w in db.query(WaterLog).filter(
        WaterLog.user_id == user.id, WaterLog.log_date == date).all())
    profile = db.query(NutritionProfile).filter(NutritionProfile.user_id == user.id).first()

    total_cal = sum(l.calories for l in logs)
    total_prot = sum(l.protein for l in logs)
    total_fat = sum(l.fat for l in logs)
    total_carbs = sum(l.carbs for l in logs)
    goal_cal = profile.calorie_goal if profile else 2000
    goal_name = {"lose": "похудение", "gain": "набор массы", "maintain": "поддержание"}.get(
        profile.goal if profile else "maintain", "поддержание")
    food_list = "\n".join(f"- {l.food_name}: {l.calories:.0f} ккал" for l in logs) or "Ничего не записано"

    system = f"""Ты AI-нутрициолог в мобильном приложении. Отвечай кратко и конкретно (2-4 предложения). Без списков — просто текст.

Контекст пользователя сегодня ({date}):
- Цель: {goal_name}, норма {goal_cal} ккал/день
- Съедено: {total_cal:.0f} ккал | Б:{total_prot:.0f}г Ж:{total_fat:.0f}г У:{total_carbs:.0f}г
- Вода: {water} мл
- Приёмы пищи:
{food_list}"""

    api_messages = [{"role": "system", "content": system}] + messages

    if not OPENROUTER_API_KEY:
        return JSONResponse({"reply": "API ключ не настроен."})

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}",
                         "HTTP-Referer": "https://energydess.ru", "X-Title": "EnergyDess Nutrition"},
                json={"model": LETTER_MODEL, "messages": api_messages,
                      "temperature": 0.4, "max_tokens": 350},
                timeout=30.0,
            )
        reply = resp.json()["choices"][0]["message"]["content"].strip()
        return JSONResponse({"reply": reply})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ── Nutrition: AI photo ───────────────────────────────────────────────────────

@app.post("/nutrition/api/ai-photo")
async def nut_ai_photo(file: UploadFile = File(...), user=Depends(get_current_user),
                       db: Session = Depends(get_db)):
    if not user or not user_has_access(user, "nutrition", db):
        return JSONResponse({"error": "Нет доступа"}, status_code=403)
    content = await file.read()
    b64 = base64.b64encode(content).decode()
    ext = (file.filename or "photo.jpg").rsplit(".", 1)[-1].lower()
    mime = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}"

    prompt = """На фото еда. Определи что изображено и оцени калорийность на 100г.
Ответь ТОЛЬКО JSON без ```json и без пояснений:
{"name":"название блюда","calories":150,"protein":10,"fat":5,"carbs":20,"estimated_grams":300,"note":"краткое пояснение"}"""

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}",
                         "HTTP-Referer": "https://energydess.ru", "X-Title": "EnergyDess Nutrition"},
                json={"model": LETTER_MODEL,
                      "messages": [{"role": "user", "content": [
                          {"type": "image_url",
                           "image_url": {"url": f"data:{mime};base64,{b64}"}},
                          {"type": "text", "text": prompt}
                      ]}],
                      "temperature": 0.2, "max_tokens": 200},
                timeout=30.0,
            )
        import json as _json
        text = resp.json()["choices"][0]["message"]["content"].strip()
        result = _json.loads(text)
        return JSONResponse({"ok": True, "food": result})
    except Exception as e:
        return JSONResponse({"error": f"Не удалось распознать: {e}"}, status_code=500)
