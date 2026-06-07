from datetime import datetime, timedelta
from fastapi import FastAPI, Request, Depends, Form, UploadFile, File
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.exceptions import HTTPException
from bs4 import BeautifulSoup
import httpx
import os
from dotenv import load_dotenv
from sqlalchemy.orm import Session

from database import get_db, init_db, migrate_db, User, Resume, ToolAccess, EnshroudedSlot
from auth import hash_password, verify_password, create_token, get_current_user, generate_token

load_dotenv()

app = FastAPI(title="EnergyDess Tools")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

OPENROUTER_API_KEY  = os.getenv("OPENROUTER_API_KEY", "")
MODEL               = os.getenv("MODEL", "anthropic/claude-haiku-4-5")
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
- Одним предложением — почему именно эта вакансия, не другая. Привяжи к конкретному требованию или задаче из вакансии.
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
- Клише-вступления: "Ваша вакансия — это именно то, что я искал", "вы попали в точку", "эта позиция идеально соответствует", "нашёл то, что искал", "ознакомившись с вакансией, я понял"
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
