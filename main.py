import asyncio
import json as _json
import re
import socket
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from fastapi import FastAPI, Request, Depends, Form, UploadFile, File, BackgroundTasks
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
from sqlalchemy import or_, func

from database import (get_db, init_db, migrate_db, SessionLocal, User, Resume, ToolAccess, EnshroudedSlot,
                      HHProfile, CoverLetter, NutritionProfile, FoodLog, CustomFood, CustomRecipe, RecipeIngredient,
                      WaterLog, WeightLog, ChatMessage, Exercise, WorkoutProfile,
                      WorkoutProgram, WorkoutProgramDay, WorkoutProgramExercise,
                      WorkoutSession, SetLog, ProgressionSetting, WorkoutExerciseSwap,
                      ScaleConnection, BodyPhoto, PainZonePatch)
from auth import hash_password, verify_password, create_token, get_current_user, generate_token
from few_shot_examples import build_few_shot_block
import zepp_client

load_dotenv()

# На сервере не работает IPv6 — если у внешнего хоста (например api.groq.com)
# резолвер первым отдаёт AAAA-запись, httpx пытается достучаться по IPv6
# и виснет до таймаута, хотя по IPv4 тот же хост отвечает за миллисекунды.
# Принудительно отдаём только IPv4-адреса для всех исходящих соединений.
_orig_getaddrinfo = socket.getaddrinfo
def _getaddrinfo_ipv4_only(host, *args, **kwargs):
    results = _orig_getaddrinfo(host, *args, **kwargs)
    ipv4 = [r for r in results if r[0] == socket.AF_INET]
    return ipv4 or results
socket.getaddrinfo = _getaddrinfo_ipv4_only

app = FastAPI(title="EnergyDess Tools")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

OPENROUTER_API_KEY  = os.getenv("OPENROUTER_API_KEY", "")
MODEL               = os.getenv("MODEL",         "anthropic/claude-haiku-4-5")
LETTER_MODEL        = os.getenv("LETTER_MODEL",  "anthropic/claude-opus-4-5")   # генерация письма
ANALYZE_MODEL       = os.getenv("ANALYZE_MODEL", "anthropic/claude-sonnet-4-5") # анализ вакансии (JSON)
PARSER_MODEL        = os.getenv("PARSER_MODEL",  "anthropic/claude-sonnet-4-5") # парсер резюме (JSON)
RESEND_API_KEY      = os.getenv("RESEND_API_KEY", "")
BASE_URL            = os.getenv("BASE_URL", "https://energydess.ru")
CREDENTIALS_ENCRYPTION_KEY = os.getenv("CREDENTIALS_ENCRYPTION_KEY", "")


def _get_fernet():
    """Шифрование логина/пароля весов Xiaomi при хранении в БД (см.
    ScaleConnection). Ключ — секрет окружения, не хардкод."""
    from cryptography.fernet import Fernet
    if not CREDENTIALS_ENCRYPTION_KEY:
        raise RuntimeError("CREDENTIALS_ENCRYPTION_KEY не настроен")
    return Fernet(CREDENTIALS_ENCRYPTION_KEY.encode())


def _encrypt(text: str) -> str:
    return _get_fernet().encrypt(text.encode()).decode()


def _decrypt(token: str) -> str:
    return _get_fernet().decrypt(token.encode()).decode()

TOOLS = [
    {
        "id": "hh",
        "name": "HH Помощник",
        "icon": "📝",
        "color": "purple",
        "url": "/hh",
        "desc": "Вставь текст вакансии — за 30 секунд получишь готовое сопроводительное письмо, адаптированное под твоё резюме и конкретные требования работодателя.",
        "active": True,
    },
    {
        "id": "enshrouded",
        "name": "Enshrouded",
        "icon": "🛡",
        "color": "orange",
        "url": "/enshrouded",
        "desc": "Трекер доспехов Enshrouded — отмечай собранные сеты, уровни и редкость предметов. Планируй следующий крафт и не теряй прогресс.",
        "active": True,
    },
    {
        "id": "workout",
        "name": "Программа тренировок",
        "icon": "💪",
        "color": "blue",
        "url": "/workout",
        "desc": "Персональный план тренировок под цели, уровень подготовки и доступное оборудование. Автоматическая прогрессия нагрузок, трекинг подходов и весов.",
        "active": True,
    },
    {
        "id": "nutrition",
        "name": "Дневник питания",
        "icon": "🥗",
        "color": "green",
        "url": "/nutrition",
        "desc": "Дневник питания с подсчётом КБЖУ и штрих-код сканером. Трекер веса, AI-анализ рациона и рекомендации под твои цели.",
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


@app.get("/version")
async def version():
    import subprocess
    repo_dir = os.path.dirname(os.path.abspath(__file__))
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=repo_dir,
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except Exception:
        commit = "unknown"
    return JSONResponse({"commit": commit})


@app.post("/deploy-hook")
async def deploy_hook(request: Request):
    token = request.headers.get("X-Deploy-Token", "")
    expected = os.getenv("DEPLOY_SECRET", "")
    if not expected or token != expected:
        return JSONResponse({"error": "Forbidden"}, status_code=403)
    import subprocess
    # git pull с повторами — у VPS периодически рвётся связь с GitHub
    script = (
        "sleep 2 && cd /var/www/energydess && "
        "(git pull origin main || (sleep 5 && git pull origin main) || (sleep 15 && git pull origin main)) && "
        "systemctl restart energydess"
    )
    log = open("/var/log/energydess-deploy.log", "a")
    subprocess.Popen(["bash", "-c", script], stdout=log, stderr=subprocess.STDOUT)
    return JSONResponse({"ok": True})


def _import_exercises_if_empty():
    """База упражнений (с переводом и кластеризацией оборудования, уже
    посчитанными ранее) лежит в exercises_data.json — грузим один раз при
    первом старте, если таблица пустая (напр. свежий volume на проде).
    Идемпотентно: на непустой таблице ничего не делает."""
    db = SessionLocal()
    try:
        if db.query(Exercise).first():
            return
        path = os.path.join(os.path.dirname(__file__), "exercises_data.json")
        if not os.path.exists(path):
            return
        with open(path, encoding="utf-8") as f:
            data = _json.load(f)
        for row in data:
            db.add(Exercise(
                id=row["id"], name=row["name"], name_ru=row["name_ru"],
                force=row["force"], level=row["level"], mechanic=row["mechanic"],
                equipment=row["equipment"], equipment_cluster=row["equipment_cluster"],
                primary_muscles=row["primary_muscles"], secondary_muscles=row["secondary_muscles"],
                instructions=row["instructions"], instructions_ru=row["instructions_ru"],
                category=row["category"], images=row["images"],
            ))
        db.commit()
        print(f"Импортировано упражнений: {len(data)}")
    finally:
        db.close()


@app.on_event("startup")
def startup():
    init_db()
    migrate_db()
    _import_exercises_if_empty()


# ── Демо-страница (тестовое задание, без авторизации) ─────────────────────────

DEMO_PROGRAMS = {
    "metod-usmanovoy": {
        "icon": "🏆", "badge_class": "badge-flagship", "badge_text": "🔥 Флагман",
        "title": "Метод Усмановой",
        "tagline": "Базовая техника упражнений — фундамент всей системы",
        "level": "Для новичков", "duration": "8 недель",
        "feature_chips": ["🔄 Обновлено в 2026", "🎥 Видео в 4K с 3 ракурсов", "♾ Доступ навсегда"],
        "benefits": [
            "Пошаговый разбор техники каждого упражнения",
            "Видео-уроки в высоком качестве с разных ракурсов",
            "Поддержка куратора в закрытом чате",
            "Доступ к программе на 365 дней",
        ],
        "comparison": [
            {"old": "Учишься по случайным видео из интернета — техника вразнобой",
             "new": "Каждое движение разобрано по кадрам тренером с 15-летним стажем"},
            {"old": "Не понимаешь, какие мышцы работают и почему",
             "new": "Понятная анатомия и ощущение «как должно быть» в каждом упражнении"},
            {"old": "Боишься получить травму от неправильной техники",
             "new": "Безопасная прогрессия нагрузки — от простого к сложному без рывков"},
        ],
        "social_proof": "320 000+",
        "testimonials": [
            {"name": "Анна, 29 лет", "text": "Думала, что приседаю правильно 5 лет — оказалось, нет. После 3 недель техника другая, спина не болит вообще.", "stars": 5},
            {"name": "Марина, 34 года", "text": "Очень подробно объясняют. Чувствую, что наконец понимаю, что делаю в зале, а не просто повторяю за кем-то.", "stars": 5},
            {"name": "Ольга, 41 год", "text": "Лучшая база, которую я проходила. Дальше пошла на марафон стройности — и это другой уровень благодаря этой подготовке.", "stars": 5},
        ],
        "goals": ["Освоить технику", "Уверенность в зале", "Безопасные тренировки", "Фундамент для прогресса"],
        "modules": [
            {"title": "Постановка техники", "desc": "Разбираем базовые движения — приседания, выпады, тягу — без травм и ошибок."},
            {"title": "Базовый цикл", "desc": "4 недели на закрепление навыка и первую адаптацию тела к нагрузке."},
            {"title": "Прогрессия нагрузки", "desc": "Постепенно увеличиваем сложность — тело привыкает к новому уровню."},
            {"title": "Закрепление результата", "desc": "Финальный блок для перехода на следующую ступень программ."},
        ],
        "timeline": [
            {"period": "Недели 1–2", "text": "Тело привыкает к правильным траекториям движений, уходит зажатость"},
            {"period": "Недели 3–4", "text": "Техника становится автоматической — не нужно думать о каждом движении"},
            {"period": "Недели 5–6", "text": "Растёт рабочий вес без потери качества движения"},
            {"period": "Недели 7–8", "text": "Готовы к следующей ступени программ — марафонам и силовым циклам"},
        ],
        "bonuses": ["📋 Чек-лист «5 ошибок в технике»", "💬 Чат с куратором", "📱 Доступ с телефона и планшета", "🎯 Разбор вашей техники по видео"],
        "faq": [
            {"q": "У меня вообще нет опыта тренировок — подойдёт?", "a": "Да, программа создана именно для этого. Начинаем с самых базовых движений и постепенно увеличиваем сложность."},
            {"q": "Нужен ли тренажёрный зал или можно дома?", "a": "Лучший результат — в зале со свободными весами, но первые недели можно проходить и дома с минимальным инвентарём."},
            {"q": "Сколько раз в неделю нужно заниматься?", "a": "Оптимально 3 тренировки в неделю по 40–50 минут. Этого достаточно, чтобы закрепить технику без перегрузки."},
            {"q": "Что если я не успею пройти за 8 недель?", "a": "Доступ открыт на 365 дней — двигайтесь в своём темпе, программа никуда не торопит."},
        ],
        "spots_left": 47,
        "price": 2990, "old_price": 5980,
    },
    "marafon-stroynosti": {
        "icon": "🔥", "badge_class": "badge-marathon", "badge_text": "🏃 Марафон",
        "title": "Марафон Стройности",
        "tagline": "21 день интенсивной работы для ощутимых изменений",
        "level": "Средний уровень", "duration": "21 день",
        "feature_chips": ["🔄 Обновлено в 2026", "📅 План на каждый день", "♾ Доступ на 365 дней"],
        "benefits": [
            "Ежедневные тренировки с нарастающей нагрузкой",
            "Дневник питания и трекер прогресса",
            "Чат поддержки с куратором каждый день",
            "Замеры тела до/после с разбором результата",
        ],
        "comparison": [
            {"old": "Случайные интенсивы без системы — эффект быстро уходит",
             "new": "21 день по чёткому плану с нарастающей нагрузкой и контролем результата"},
            {"old": "Тренируешься на пределе без восстановления",
             "new": "Встроенные дни восстановления — прогресс без перегрузки и срывов"},
            {"old": "Не видишь промежуточный результат, бросаешь на середине",
             "new": "Замеры на старте, в середине и в конце — видно реальную динамику"},
        ],
        "social_proof": "145 000+",
        "testimonials": [
            {"name": "Кристина, 27 лет", "text": "21 день — идеальный срок, чтобы не сорваться. Втянулась и продолжила уже на следующую программу.", "stars": 5},
            {"name": "Виктория, 31 год", "text": "Куратор реально следит за прогрессом каждый день, это держит в тонусе лучше любой мотивации.", "stars": 5},
            {"name": "Дарья, 38 лет", "text": "Похудела на 3 кг и подтянулась за 3 недели. Самое важное — не голодала, просто тренировалась по плану.", "stars": 4},
        ],
        "goals": ["Похудение", "Выносливость", "Привычка к спорту", "Видимый результат быстро"],
        "modules": [
            {"title": "Старт и адаптация", "desc": "Дни 1–7: входим в режим, настраиваем питание и сон."},
            {"title": "Ударная неделя", "desc": "Дни 8–14: пик интенсивности — сжигаем максимум калорий."},
            {"title": "Финишная прямая", "desc": "Дни 15–21: закрепляем форму и готовимся к следующему этапу."},
        ],
        "timeline": [
            {"period": "Дни 1–7", "text": "Адаптация: режим, питание, первая лёгкость в теле"},
            {"period": "Дни 8–14", "text": "Пик интенсивности — максимальное жиросжигание"},
            {"period": "Дни 15–21", "text": "Закрепление формы, финальные замеры и явный результат в зеркале"},
        ],
        "bonuses": ["📊 Трекер прогресса и замеров", "🍽 Памятка по питанию на марафон", "💬 Ежедневная поддержка куратора", "🏅 Сертификат за прохождение"],
        "faq": [
            {"q": "21 день — это реально достаточно для результата?", "a": "Для заметных изменений в тонусе и самочувствии — да. Это спринт, который запускает привычку и даёт быстрый старт."},
            {"q": "Что если пропущу день?", "a": "Ничего страшного — план гибкий, можно сдвинуть тренировку на день без потери эффекта."},
            {"q": "Подходит новичкам?", "a": "Да, но рекомендуем сначала пройти «Метод Усмановой», чтобы поставить технику — марафон идёт в высоком темпе."},
        ],
        "spots_left": 31,
        "price": 3490, "old_price": 6980,
    },
    "uprugaya-popa-1": {
        "icon": "🍑", "badge_class": "badge-course", "badge_text": "💫 Курс",
        "title": "Упругая попа 1.0",
        "tagline": "Только собственный вес тела — никакого инвентаря",
        "level": "Для новичков", "duration": "4 недели",
        "feature_chips": ["🏠 Без инвентаря", "⏱ 15–25 минут в день", "♾ Доступ навсегда"],
        "benefits": [
            "Тренировки без инвентаря — нужен только коврик",
            "Прицельная работа над ягодичными мышцами",
            "15–25 минут в день",
            "Подходит для занятий дома в любое время",
        ],
        "comparison": [
            {"old": "Делаешь упражнения, но не чувствуешь нужные мышцы",
             "new": "Сначала учимся включать ягодицы изолированно — потом наращиваем объём"},
            {"old": "Боль в пояснице вместо результата в ягодицах",
             "new": "Правильная техника полностью убирает нагрузку со спины"},
        ],
        "social_proof": "210 000+",
        "testimonials": [
            {"name": "Юлия, 25 лет", "text": "Дома, без зала и инвентаря — реально работает, если делать с вниманием к технике, как показывают.", "stars": 5},
            {"name": "Светлана, 33 года", "text": "Наконец почувствовала ягодицы, а не квадрицепсы. Это просто другое упражнение, хотя выглядит так же.", "stars": 5},
            {"name": "Виолетта, 22 года", "text": "Дома за 4 недели реально стало плотнее. Самое крутое — не пришлось покупать резинки или гантели, я и так сомневалась, нужно ли мне оборудование.", "stars": 5},
            {"name": "Карина, 30 лет", "text": "Понравилось, что объясняют, как именно чувствовать мышцу. Раньше делала похожие упражнения вообще не туда.", "stars": 4},
        ],
        "goals": ["Подтянуть ягодицы", "Без боли в спине", "Тренировки дома", "15 минут в день"],
        "modules": [
            {"title": "Активация ягодиц", "desc": "Учимся включать нужные мышцы в работу, а не перегружать спину."},
            {"title": "Объём и форма", "desc": "Наращиваем количество повторов и усложняем углы движений."},
        ],
        "timeline": [
            {"period": "Неделя 1", "text": "Учимся чувствовать целевые мышцы — самый важный навык программы"},
            {"period": "Неделя 2", "text": "Растёт количество качественных повторений"},
            {"period": "Недели 3–4", "text": "Заметная подтянутость и упругость без дополнительного веса"},
        ],
        "bonuses": ["📋 Чек-лист правильной техники", "🎥 Видео с 3 ракурсов на каждое упражнение", "💬 Чат поддержки"],
        "faq": [
            {"q": "Точно не нужен никакой инвентарь?", "a": "Да, только коврик. Все упражнения построены на работе с собственным весом тела."},
            {"q": "Сколько раз в неделю заниматься?", "a": "4 тренировки в неделю по 15–25 минут — оптимальный баланс для бодрого прогресса без перегрузки."},
        ],
        "spots_left": 58,
        "price": 1990, "old_price": 3980,
    },
    "uprugaya-popa-2": {
        "icon": "💪", "badge_class": "badge-course", "badge_text": "💫 Курс",
        "title": "Упругая попа 2.0",
        "tagline": "Максимальная нагрузка с резинками и гантелями",
        "level": "Продвинутый", "duration": "6 недель",
        "feature_chips": ["🏋️ Резинки + гантели", "📈 Продолжение 1.0", "♾ Доступ навсегда"],
        "benefits": [
            "Работа с резинками и гантелями для роста объёма",
            "Продолжение программы 1.0 — для тех, кто прошёл базу",
            "Видео-разбор техники с разных ракурсов",
            "Гибкий график — 4 тренировки в неделю",
        ],
        "comparison": [
            {"old": "Тело привыкло к нагрузке — собственный вес уже не даёт прогресса",
             "new": "Дополнительное отягощение даёт новый стимул роста для тех, кто прошёл базу"},
            {"old": "Сложно понять, какой вес или резинку выбрать",
             "new": "Чёткие рекомендации по нагрузке на каждую неделю прогрессии"},
        ],
        "social_proof": "98 000+",
        "testimonials": [
            {"name": "Алина, 29 лет", "text": "После 1.0 показалось мало — здесь нагрузка совсем другая. Объём заметно подрос за полтора месяца.", "stars": 5},
            {"name": "Татьяна, 36 лет", "text": "Хорошая прогрессия по неделям, не пришлось гадать с весами — всё расписано.", "stars": 4},
            {"name": "Жанна, 27 лет", "text": "Резинка с гантелями дали ощутимую разницу по сравнению с 1.0 — мышцы реально устают по-другому, в хорошем смысле.", "stars": 5},
            {"name": "Регина, 33 года", "text": "Прогрессия по неделям расписана чётко, не было ощущения, что застряла на месте.", "stars": 5},
        ],
        "goals": ["Рост объёма", "Выраженная форма", "Прогрессия нагрузки", "Силовая выносливость"],
        "modules": [
            {"title": "Усиление базы", "desc": "Добавляем отягощение к проверенным движениям из 1.0."},
            {"title": "Пик объёма", "desc": "Максимальная нагрузка — финальный рывок к выраженной форме."},
        ],
        "timeline": [
            {"period": "Недели 1–2", "text": "Адаптация к новому уровню нагрузки с резинкой и гантелями"},
            {"period": "Недели 3–4", "text": "Рост рабочего веса и количества качественных подходов"},
            {"period": "Недели 5–6", "text": "Пиковая нагрузка — финальный рывок к выраженному объёму"},
        ],
        "bonuses": ["📊 Таблица прогрессии нагрузки", "🎥 Видео-разбор техники", "💬 Чат поддержки куратора"],
        "faq": [
            {"q": "Нужно ли сначала пройти Упругую попу 1.0?", "a": "Рекомендуем — программа построена как продолжение и предполагает базовый навык техники."},
            {"q": "Какой инвентарь нужен?", "a": "Резинка-эспандер (фитнес-петля) и пара гантелей 2–5 кг. Всё компактное, подходит для дома."},
        ],
        "spots_left": 22,
        "price": 2490, "old_price": 4980,
    },
    "ploskiy-zhivot": {
        "icon": "✨", "badge_class": "badge-bestseller", "badge_text": "⭐ Бестселлер",
        "title": "Плоский живот",
        "tagline": "Работа с глубокими мышцами кора без скручиваний",
        "level": "Любой уровень", "duration": "5 недель",
        "feature_chips": ["🫁 Без скручиваний", "⏱ 10–20 минут в день", "♾ Доступ навсегда"],
        "benefits": [
            "Безопасная работа с глубокими мышцами кора",
            "Без изнурительных скручиваний и нагрузки на спину",
            "Дыхательные техники для активации пресса",
            "10–20 минут в день",
        ],
        "comparison": [
            {"old": "Сотни скручиваний без видимого результата и с болью в шее",
             "new": "Работа с глубокими мышцами кора через дыхание — без нагрузки на шею и спину"},
            {"old": "Живот «торчит» даже при невысоком проценте жира",
             "new": "Учимся убирать диастаз и гипертонус — настоящую причину торчащего живота"},
        ],
        "social_proof": "260 000+",
        "testimonials": [
            {"name": "Екатерина, 32 года", "text": "Перепробовала всё для живота — сработала именно работа с дыханием. Через месяц живот плоский без диет.", "stars": 5},
            {"name": "Наталья, 45 лет", "text": "После двух родов наконец-то получилось вернуть форму без боли в спине. Очень бережная программа.", "stars": 5},
            {"name": "Полина, 27 лет", "text": "Бестселлер не зря — 10 минут в день и реально видно разницу через пару недель.", "stars": 5},
        ],
        "goals": ["Плоский живот", "Осанка", "Восстановление после родов", "Без боли в спине"],
        "modules": [
            {"title": "Диафрагмальное дыхание", "desc": "Учимся правильно включать кор через дыхание."},
            {"title": "Глубокий пресс", "desc": "Статика и медленные движения для внутренних мышц живота."},
            {"title": "Видимый результат", "desc": "Сочетаем технику с лёгким кардио для рельефа."},
        ],
        "timeline": [
            {"period": "Неделя 1", "text": "Учимся диафрагмальному дыханию и включению глубокого кора"},
            {"period": "Недели 2–3", "text": "Укрепление поперечных мышц живота, уходит вздутие"},
            {"period": "Недели 4–5", "text": "Видимый результат — живот плоский даже без похудения"},
        ],
        "bonuses": ["🫁 Гайд по дыхательным практикам", "📋 Чек-лист «5 причин торчащего живота»", "💬 Чат поддержки"],
        "faq": [
            {"q": "Подходит после родов?", "a": "Да, это одна из самых частых причин выбора программы. Рекомендуем начинать не раньше 8 недель после родов и без противопоказаний от врача."},
            {"q": "Это похоже на обычный пресс?", "a": "Нет — никаких скручиваний. Работа построена на статике, дыхании и глубоких мышцах кора."},
            {"q": "Сколько нужно заниматься в день?", "a": "10–20 минут. Программа щадящая, подходит даже при низком уровне подготовки."},
        ],
        "spots_left": 64,
        "price": 2290, "old_price": 4580,
    },
    "zhiroszhigatelniy-kurs": {
        "icon": "🫀", "badge_class": "badge-course", "badge_text": "⚡ 6 недель",
        "title": "Жиросжигающий курс",
        "tagline": "6 недель интенсивной кардио и силовой работы",
        "level": "Средний уровень", "duration": "6 недель",
        "feature_chips": ["🔥 Кардио + силовая", "📅 6 недель", "♾ Доступ навсегда"],
        "benefits": [
            "Интервальные кардио-тренировки для ускорения метаболизма",
            "Силовые блоки для сохранения мышечной массы",
            "План питания на каждую неделю",
            "Трекер калорий и активности",
        ],
        "comparison": [
            {"old": "Бесконечное кардио без силовых — теряешь мышцы вместе с жиром",
             "new": "Комбинация интервалов и силовых блоков — жир уходит, мышцы остаются"},
            {"old": "Метаболизм замедляется после первых недель диеты",
             "new": "План питания подстроен под фазы программы, чтобы метаболизм не «засыпал»"},
        ],
        "social_proof": "175 000+",
        "testimonials": [
            {"name": "Ирина, 30 лет", "text": "За 6 недель −4 кг и форма заметно другая. Силовые блоки спасли от обвисшей кожи, которая бывает на одном кардио.", "stars": 5},
            {"name": "Маргарита, 39 лет", "text": "Понравился баланс — не загнали в одно бесконечное кардио, было интересно и разнообразно.", "stars": 4},
            {"name": "Софья, 26 лет", "text": "Кардио и силовые чередуются с умом — не было ощущения, что выгораю на одних интервалах.", "stars": 5},
            {"name": "Людмила, 44 года", "text": "После 6 недель появилась энергия, которой не было даже до начала похудения. Питание реально помогает, не голодала.", "stars": 4},
        ],
        "goals": ["Снижение % жира", "Ускорение метаболизма", "Сохранение мышц", "Выносливость"],
        "modules": [
            {"title": "Разгон метаболизма", "desc": "Недели 1–2: высокоинтенсивные интервалы и базовое питание."},
            {"title": "Жиросжигание", "desc": "Недели 3–4: пик нагрузки, комбинируем кардио и силовые."},
            {"title": "Удержание результата", "desc": "Недели 5–6: закрепляем привычку и готовим план дальше."},
        ],
        "timeline": [
            {"period": "Недели 1–2", "text": "Разгон метаболизма высокоинтенсивными интервалами"},
            {"period": "Недели 3–4", "text": "Пик жиросжигания — комбинация кардио и силовых блоков"},
            {"period": "Недели 5–6", "text": "Удержание результата и переход к поддерживающему режиму"},
        ],
        "bonuses": ["🍽 План питания на 6 недель", "📊 Трекер калорий и активности", "💬 Чат поддержки куратора"],
        "faq": [
            {"q": "Нужен ли зал или можно тренироваться дома?", "a": "Программа адаптирована и под зал, и под дом — нужны лишь гантели и коврик."},
            {"q": "Не уйдут ли мышцы вместе с жиром?", "a": "Нет, силовые блоки специально сохраняют мышечную массу, пока вы теряете жир."},
        ],
        "spots_left": 39,
        "price": 3290, "old_price": 6580,
    },
}


@app.get("/demo")
async def demo_page(request: Request):
    return templates.TemplateResponse(request=request, name="demo_landing.html", context={})


@app.get("/demo/program/{slug}")
async def demo_program_page(request: Request, slug: str):
    program = DEMO_PROGRAMS.get(slug)
    if not program:
        return RedirectResponse("/demo", status_code=302)
    return templates.TemplateResponse(request=request, name="demo_program.html",
                                       context={"program": program, "slug": slug})


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
                                          context={"error": "Неверный email или пароль", "email": email})

    if user.is_verified is False:
        return templates.TemplateResponse(request=request, name="login.html",
                                          context={"error": "Сначала подтвердите email — проверьте почту", "email": email})

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

    # Все продукты, добавленные пользователями в личную базу (CustomFood) —
    # для модерации/правки админом
    all_users = {u.id: u.email for u in db.query(User).all()}
    foods = db.query(CustomFood).order_by(CustomFood.created_at.desc()).all()
    foods_data = [{
        "id": f.id,
        "email": all_users.get(f.user_id, "—"),
        "name": f.name,
        "brand": f.brand or "",
        "barcode": f.barcode or "",
        "calories": f.calories_per_100g,
        "protein": f.protein_per_100g,
        "fat": f.fat_per_100g,
        "carbs": f.carbs_per_100g,
        "created_at": f.created_at,
    } for f in foods]

    return templates.TemplateResponse(request=request, name="admin.html",
                                      context={"user": user, "users": users_data, "tools": TOOLS,
                                               "foods": foods_data})


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


@app.put("/admin/foods/{food_id}")
async def admin_update_food(food_id: int, request: Request, user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user or not user.is_admin:
        return JSONResponse({"error": "Forbidden"}, status_code=403)

    food = db.query(CustomFood).filter(CustomFood.id == food_id).first()
    if not food:
        return JSONResponse({"error": "Не найдено"}, status_code=404)

    data = await request.json()
    food.name = (data.get("name") or food.name).strip()
    food.brand = (data.get("brand") or "").strip() or None
    food.calories_per_100g = float(data.get("calories", food.calories_per_100g))
    food.protein_per_100g = float(data.get("protein", food.protein_per_100g))
    food.fat_per_100g = float(data.get("fat", food.fat_per_100g))
    food.carbs_per_100g = float(data.get("carbs", food.carbs_per_100g))
    db.commit()
    return JSONResponse({"ok": True})


@app.delete("/admin/foods/{food_id}")
async def admin_delete_food(food_id: int, user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user or not user.is_admin:
        return JSONResponse({"error": "Forbidden"}, status_code=403)

    food = db.query(CustomFood).filter(CustomFood.id == food_id).first()
    if not food:
        return JSONResponse({"error": "Не найдено"}, status_code=404)

    db.delete(food)
    db.commit()
    return JSONResponse({"ok": True})


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


# ── Хелперы: сборка досье и анализ вакансии ──────────────────────────────────

def _build_compact_dossier(profile: HHProfile) -> str:
    """Компактное досье для промпта анализа вакансии (только ключевые данные)."""
    if not profile:
        return ""
    parts = []
    if profile.profession_one_liner:
        parts.append(f"Профессия: {profile.profession_one_liner}")
    if profile.skills:
        parts.append(f"Навыки: {', '.join(profile.skills[:20])}")
    if profile.projects:
        parts.append("Проекты/портфолио:")
        for p in profile.projects[:6]:
            title = p.get('title', '')
            if not title:
                continue
            url   = p.get('url', '')
            ptype = (p.get('type') or '').strip()
            tags  = p.get('tags') or []
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(',') if t.strip()]
            tags_str = ', '.join(tags[:5])

            line = f"  - {title}"
            if url:
                line += f" [{url}]"
            if ptype and tags_str:
                line += f": {ptype} · {tags_str}"
            elif ptype:
                line += f": {ptype}"
            elif tags_str:
                line += f": {tags_str}"
            parts.append(line)
    if profile.extra_context:
        parts.append(f"Контекст: {profile.extra_context[:300]}")
    return "\n".join(parts)


def _build_full_dossier(profile: HHProfile) -> str:
    """Полное досье для промпта генерации письма."""
    if not profile:
        return ""
    parts = []
    if profile.profession_one_liner:
        parts.append(f"Позиционирование: {profile.profession_one_liner}")
    if profile.location:
        loc_parts = [profile.location]
        if profile.work_format:
            loc_parts.append(profile.work_format)
        parts.append(f"Локация/формат: {', '.join(loc_parts)}")
    if profile.languages:
        langs = [f"{l.get('lang','')} ({l.get('level','')})" for l in profile.languages if l.get('lang')]
        if langs:
            parts.append(f"Языки: {', '.join(langs)}")
    if profile.total_years_in_profession:
        parts.append(f"Опыт: {profile.total_years_in_profession}")
    if profile.experience_extra:
        for exp in profile.experience_extra[:3]:
            line = f"  — {exp.get('position','')} в {exp.get('company','')} ({exp.get('period','')})"
            if exp.get('achievements'):
                line += f": {exp['achievements'][:200]}"
            parts.append(line)
    if profile.projects:
        parts.append("Проекты/портфолио:")
        for proj in profile.projects[:6]:
            line = f"  • {proj.get('title','')}"
            if proj.get('url'):
                line += f" — {proj['url']}"
            if proj.get('description'):
                line += f" ({proj['description'][:150]})"
            if proj.get('tools'):
                line += f" [инструменты: {proj['tools']}]"
            parts.append(line)
    if profile.skills:
        parts.append(f"Навыки и инструменты: {', '.join(profile.skills)}")
    if profile.methodology:
        parts.append(f"Методология: {profile.methodology}")
    if profile.tone_preference:
        parts.append(f"Тон письма: {profile.tone_preference}")
    if profile.never_mention:
        parts.append(f"Не упоминать: {profile.never_mention}")
    if profile.extra_context:
        parts.append(f"Дополнительный контекст: {profile.extra_context}")
    if profile.ending_style:
        es = profile.ending_style
        if isinstance(es, dict):
            if es.get('just_farewell'):
                parts.append("Концовка письма: без CTA — только подпись (just_farewell=true)")
            else:
                cta = []
                if es.get('suggest_call'):
                    cta.append("предложи созвон")
                if es.get('suggest_test_task'):
                    cta.append("предложи тестовое задание")
                if cta:
                    parts.append(f"Концовка письма: {' и '.join(cta)}")
    return "\n".join(parts)


# ── API: анализ вакансии ──────────────────────────────────────────────────────

@app.post("/api/analyze-vacancy")
async def analyze_vacancy(request: Request, user=Depends(get_current_user), db: Session = Depends(get_db)):
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
    profile = db.query(HHProfile).filter(HHProfile.user_id == user.id).first()
    compact_dossier = _build_compact_dossier(profile)

    dossier_block = f"\nДОСЬЕ КАНДИДАТА:\n{compact_dossier}" if compact_dossier else ""

    prompt = f"""Проанализируй соответствие резюме и вакансии. Ответь ТОЛЬКО JSON без ```json и без пояснений.

РЕЗЮМЕ:
{resume_text}
{dossier_block}

ВАКАНСИЯ:
{job_text}

Верни JSON строго такой структуры:
{{
  "job_title": "название должности из вакансии",
  "company_name": "название компании или пустая строка",
  "relevance_score": 7,
  "relevance_reason": "2-3 предложения: почему этот балл",
  "key_matches": ["совпадение 1", "совпадение 2", "совпадение 3"],
  "missing_skills": ["чего не хватает 1", "чего не хватает 2"],
  "tone_suggestion": "деловой",
  "relevant_portfolio_links": ["https://ссылка1", "https://ссылка2"],
  "focus_points": ["на что делать акцент в письме"]
}}

relevance_score — целое от 1 до 10 (1 = полное несоответствие, 10 = идеальное совпадение).
relevant_portfolio_links — ищи релевантные ссылки в двух источниках: в тексте резюме и в списке проектов из досье (строки вида «Название [URL]»). Возвращай именно URL (строку ссылки), а не названия или описания. Если проект из досье релевантен вакансии — включай его URL. Пустой массив если ничего не подходит.
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
                    "temperature": 0.3,
                    "max_tokens": 700,
                },
                timeout=40.0,
            )
        if response.status_code != 200:
            return JSONResponse({"error": f"Ошибка OpenRouter: {response.text}"}, status_code=500)
        raw = response.json()["choices"][0]["message"]["content"].strip()
        result = _extract_json(raw)
        return JSONResponse(result)
    except httpx.TimeoutException:
        return JSONResponse({"error": "Превышено время ожидания"}, status_code=504)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ── API: генерация письма ─────────────────────────────────────────────────────

@app.post("/api/generate-letter")
async def generate_letter(request: Request, user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user or not user_has_access(user, "hh", db):
        return JSONResponse({"error": "Нет доступа"}, status_code=403)

    data = await request.json()
    job_text = data.get("job_text", "").strip()
    custom_context = data.get("custom_context", "").strip()
    force = data.get("force", False)
    if not job_text:
        return JSONResponse({"error": "Вставь текст вакансии"}, status_code=400)
    if not OPENROUTER_API_KEY:
        return JSONResponse({"error": "API ключ не настроен"}, status_code=500)

    resume_obj = db.query(Resume).filter(Resume.user_id == user.id).first()
    resume_text = resume_obj.resume_text if resume_obj else ""
    if not resume_text.strip():
        return JSONResponse({"error": "Сначала добавь своё резюме в профиле"}, status_code=400)

    profile = db.query(HHProfile).filter(HHProfile.user_id == user.id).first()
    compact_dossier = _build_compact_dossier(profile)
    full_dossier = _build_full_dossier(profile)

    # ── Этап 1: анализ вакансии (temperature 0.3, JSON) ──────────────────────
    dossier_block = f"\nДОСЬЕ КАНДИДАТА:\n{compact_dossier}" if compact_dossier else ""
    analysis_prompt = f"""Проанализируй соответствие резюме и вакансии. Ответь ТОЛЬКО JSON без ```json и без пояснений.

РЕЗЮМЕ:
{resume_text}
{dossier_block}

ВАКАНСИЯ:
{job_text}

Верни JSON строго такой структуры:
{{
  "job_title": "название должности из вакансии",
  "company_name": "название компании или пустая строка",
  "relevance_score": 7,
  "relevance_reason": "2-3 предложения: почему этот балл",
  "key_matches": ["совпадение 1", "совпадение 2"],
  "missing_skills": ["чего не хватает 1"],
  "tone_suggestion": "деловой",
  "relevant_portfolio_links": ["https://ссылка1"],
  "focus_points": ["на что делать акцент в письме"]
}}

relevance_score — целое от 1 до 10.
relevant_portfolio_links — ищи релевантные ссылки в двух источниках: в тексте резюме и в списке проектов из досье (строки вида «Название [URL]»). Возвращай именно URL (строку ссылки), а не названия или описания. Если проект из досье релевантен вакансии — включай его URL. Пустой массив если ничего не подходит.
"""
    analysis = {}
    try:
        async with httpx.AsyncClient() as client:
            ar = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}",
                         "HTTP-Referer": "https://energydess.ru", "X-Title": "EnergyDess HH Helper"},
                json={"model": ANALYZE_MODEL, "messages": [{"role": "user", "content": analysis_prompt}],
                      "temperature": 0.3, "max_tokens": 700},
                timeout=40.0,
            )
        if ar.status_code == 200:
            analysis = _extract_json(ar.json()["choices"][0]["message"]["content"].strip())
    except Exception:
        pass  # анализ упал — продолжаем без него

    relevance_score = int(analysis.get("relevance_score", 10))
    job_title = analysis.get("job_title", "")
    company_name = analysis.get("company_name", "")

    # ── Предупреждение о низкой релевантности ────────────────────────────────
    if relevance_score < 4 and not force:
        return JSONResponse({
            "warning": "low_relevance",
            "score": relevance_score,
            "message": f"Вакансия слабо соответствует резюме (оценка {relevance_score}/10). "
                       f"{analysis.get('relevance_reason', '')} Всё равно сгенерировать письмо?",
        })

    # ── Этап 2: генерация письма (temperature 0.5) ────────────────────────────
    portfolio_links = analysis.get("relevant_portfolio_links", [])
    focus_points = analysis.get("focus_points", [])
    key_matches = analysis.get("key_matches", [])

    dossier_section = f"\nДОСЬЕ КАНДИДАТА:\n{full_dossier}" if full_dossier else ""
    portfolio_section = ""
    if portfolio_links:
        portfolio_section = "\nРЕЛЕВАНТНЫЕ ССЫЛКИ (используй ТОЛЬКО эти, если упоминаешь портфолио):\n" + "\n".join(portfolio_links)
    analysis_hints = ""
    if key_matches:
        analysis_hints += f"\nКлючевые совпадения с вакансией: {', '.join(key_matches)}"
    if focus_points:
        analysis_hints += f"\nНа что делать акцент: {', '.join(focus_points)}"
    custom_block = f"\nИНСТРУКЦИИ ОТ АВТОРА (выполнить обязательно):\n{custom_context}" if custom_context else ""

    few_shot_block = build_few_shot_block()

    prompt = f"""Напиши сопроводительное письмо. Только текст письма — ничего лишнего. Никакого предисловия, никакого «Вот письмо:».

РЕЗЮМЕ:
{resume_text}
{dossier_section}
{portfolio_section}
{analysis_hints}
{custom_block}

ВАКАНСИЯ:
{job_text}

{few_shot_block}
━━━ ЗАПРЕЩЁННЫЕ НАЧАЛА ПИСЬМА ━━━

Никогда не начинай письмо этими фразами или их вариациями:
«Ваша вакансия точно подходит…», «Меня заинтересовала ваша вакансия…», «Откликаюсь на позицию X, потому что…», «Хочу откликнуться…», «Я подходящий кандидат…», «Идеально подхожу…», «Ваша вакансия — это именно то, что я искал», «Нашёл то, что искал», «Ознакомившись с вакансией, я понял», «Эта позиция идеально соответствует», «Именно то место, где», «Это именно та команда», а также любые обороты про «мечта», «интересно», «хочу попробовать себя».

━━━ КАК ПРАВИЛЬНО НАЧИНАТЬ ━━━

После «Здравствуйте!» или «Здравствуйте, меня зовут [имя из резюме].» первый абзац показывает конкретную связь через факт, а не через намерение.

Примеры хороших заходов (используй как вдохновение, не копируй дословно):
— «Ваша вакансия — редкий случай, когда описание совпадает с моей ежедневной работой.»
— «Последний год я делаю именно то, что вы описываете в первом блоке задач.»
— «Формулировка "[точная цитата из вакансии]" — это буквально то, чем я занимаюсь на своих проектах.»

━━━ ПРАВИЛА ПОДАЧИ ━━━

Факты, не намерения. Говори конкретными примерами, цифрами, проектами — не общими фразами и прилагательными. Не признавай академические пробелы без явной необходимости. Не занижай себя — резюме это витрина, а не исповедь.

Портфолио — только из блока «РЕЛЕВАНТНЫЕ ССЫЛКИ». Ссылки в письме бери ТОЛЬКО из блока «РЕЛЕВАНТНЫЕ ССЫЛКИ» выше. Не используй никакие другие URL, даже если они есть в резюме или в досье — анализатор уже отфильтровал нерелевантные. Если блок «РЕЛЕВАНТНЫЕ ССЫЛКИ» пуст — не упоминай портфолио вообще, ни ссылки, ни шоурил. Упоминать портфолио без реального URL — запрещено. Ссылки вставлять дословно, каждую на отдельной строке. Исключение: если в досье указаны ссылки на публичные GitHub-репозитории (github.com/EnergyDess/energydess-tools, github.com/EnergyDess/dom-fon) и вакансия связана с разработкой, vibe coding, AI-инжинирингом или Product Engineer позицией — эти ссылки МОЖНО использовать даже если их нет в блоке «РЕЛЕВАНТНЫЕ ССЫЛКИ». GitHub-репозитории — доказательство активной работы и quality of code, критически важное для технических вакансий.

Инструменты. Не выдумывай инструменты и программы, которых нет в резюме, досье или custom_context. Не заменяй один инструмент на похожий по смыслу.

Детализация проектов. При упоминании собственных проектов из досье НИКОГДА не ограничивайся названием и стеком — раскрывай КОНКРЕТНЫЕ модули, функциональность и решения. Плохо: «energydess.ru — SaaS-хаб на FastAPI с двухэтапными LLM-пайплайнами». Хорошо: «energydess.ru — SaaS-хаб на FastAPI. Внутри четыре модуля: HH-ассистент с двухэтапной LLM-генерацией сопроводительных писем (анализ вакансии + досье пользователя + few-shot примеры), AI-нутрициолог со сканером штрих-кодов и интеграцией с умными весами через Zepp Life API, программа тренировок с AI-подбором из базы 873 упражнений, игровой трекер Enshrouded». Аспекты для раскрытия выбирай под тип вакансии: для LLM/AI-инженерных — LLM-компоненты (двухэтапные пайплайны, промпт-конструкторы, JSON-схемы, интеграции); для Product Manager — продуктовые модули, гипотезы, метрики; для разработческих — стек, архитектура, CI/CD, деплой; для creative/video — рабочий процесс, инструменты, экономика производства. Кейсы продуктовых или технических решений (пивоты, разбор качества, оптимизация) сильнее заявлений.

Разовые инструкции. Если блок «ИНСТРУКЦИИ ОТ АВТОРА» содержит указания, противоречащие tone_preference или never_mention из досье — приоритет у инструкций из этого блока: они уточняют под конкретную вакансию.

Call to action в финале. Тип CTA определяется правилом КОНЦОВКА ПИСЬМА ниже — оно обязательно. Запрещены пустые обороты: «жду вашего ответа», «буду рад», «надеюсь на сотрудничество», «Надеюсь на…», «В заключение хочу». Подпись «С уважением, [имя]» — допустима.

━━━ ЗАПРЕЩЁННЫЕ СЛОВА И ФРАЗЫ ━━━

Слова: ответственный, коммуникабельный, стрессоустойчивый, нацелен на результат, командный игрок, синергия, динамично развивающийся.
Фразы: «готов к сотрудничеству», «рассмотрите мою кандидатуру», «я являюсь», «в данный момент».
ИИ-зачины: «Конечно!», «Безусловно», «Рад помочь», «Вот письмо:». Первый абзац после «Здравствуйте!» не должен начинаться со слова «Я». Начинай с факта, с сути совпадения, с формулировки — но не с местоимения.
Оговорка: все перечисленные слова и фразы запрещены как самохарактеристики или дежурные обороты. Если слово органично встречается в конкретном контексте (например, часть цитаты из вакансии) — это допустимо.

━━━ ФОРМАТ ━━━

Объём: 200–450 слов, ориентируйся на уровень позиции. Для junior/simple ролей — ближе к 200-250. Для middle/senior/PM/Lead позиций — 350-450, чтобы дать место конкретике по проектам и кейсам. Абзацы разделять пустой строкой. Структура: первый абзац — заход + суть совпадения; следующие абзацы — конкретика, факты, проекты в проде, кейсы продуктовых или технических решений; финал — портфолио (если релевантно) + call to action. Для структурированных ответов работодателя (когда вакансия просит ответить на конкретные вопросы) — допустим markdown-болд для навигации по разделам. Без эмодзи. Без маркированных списков из общих слов — только связный текст или структура под запрос работодателя.

━━━ КОНЦОВКА ПИСЬМА — ЖЁСТКОЕ ПРАВИЛО ━━━

Смотри поле «Концовка письма» в ДОСЬЕ КАНДИДАТА:
— just_farewell=true → заканчивай только подписью, без CTA. Никакого созвона, тестового, «готов обсудить».
— «предложи созвон» → созвон в финале, без тестового задания.
— «предложи тестовое задание» → тестовое в финале, без созвона.
— оба → один вариант по контексту вакансии: творческая/продуктовая → тестовое; корпоративная/b2b → созвон.
— поля нет или все false → по умолчанию предлагай созвон.
Это правило приоритетнее любых стилевых соображений.
"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}",
                         "HTTP-Referer": "https://energydess.ru", "X-Title": "EnergyDess HH Helper"},
                json={"model": LETTER_MODEL, "messages": [{"role": "user", "content": prompt}],
                      "temperature": 0.5, "max_tokens": 900},
                timeout=40.0,
            )
        if response.status_code != 200:
            return JSONResponse({"error": f"Ошибка OpenRouter: {response.text}"}, status_code=500)
        letter = response.json()["choices"][0]["message"]["content"].strip()

        # ── Сохраняем в историю писем ─────────────────────────────────────────
        letter_id = None
        try:
            cl = CoverLetter(
                user_id=user.id,
                job_title=job_title or None,
                company_name=company_name or None,
                job_text=job_text,
                letter_text=letter,
                analysis_json=analysis if analysis else None,
                custom_context=custom_context or None,
                edited=False,
            )
            db.add(cl)
            db.commit()
            db.refresh(cl)
            letter_id = cl.id
        except Exception:
            pass  # не ломаем генерацию из-за ошибки записи в историю

        return JSONResponse({"letter": letter, "analysis": analysis, "letter_id": letter_id})
    except httpx.TimeoutException:
        return JSONResponse({"error": "Превышено время ожидания. Попробуй ещё раз."}, status_code=504)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ── API: история писем ────────────────────────────────────────────────────────

@app.get("/api/cover-letters")
async def get_cover_letters(user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user or not user_has_access(user, "hh", db):
        return JSONResponse({"error": "Нет доступа"}, status_code=403)
    letters = (
        db.query(CoverLetter)
        .filter(CoverLetter.user_id == user.id)
        .order_by(CoverLetter.created_at.desc())
        .limit(20)
        .all()
    )
    return JSONResponse([
        {
            "id": cl.id,
            "job_title": cl.job_title or "",
            "company_name": cl.company_name or "",
            "letter_text": cl.letter_text,
            "relevance_score": (cl.analysis_json or {}).get("relevance_score"),
            "edited": cl.edited or False,
            "created_at": cl.created_at.strftime("%d.%m.%Y %H:%M") if cl.created_at else "",
        }
        for cl in letters
    ])


# ── API: редактирование письма ────────────────────────────────────────────────

@app.patch("/api/cover-letters/{letter_id}")
async def patch_cover_letter(letter_id: int, request: Request, user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user or not user_has_access(user, "hh", db):
        return JSONResponse({"error": "Нет доступа"}, status_code=403)
    cl = db.query(CoverLetter).filter(CoverLetter.id == letter_id).first()
    if not cl:
        return JSONResponse({"error": "Письмо не найдено"}, status_code=404)
    if cl.user_id != user.id:
        return JSONResponse({"error": "Нет доступа"}, status_code=403)
    body = await request.json()
    new_text = body.get("letter_text", "").strip()
    if not new_text:
        return JSONResponse({"error": "Текст письма не может быть пустым"}, status_code=400)
    cl.letter_text = new_text
    cl.edited = True
    db.commit()
    return JSONResponse({"ok": True})


# ── API: парсер резюме → заготовка досье ─────────────────────────────────────

@app.post("/api/parse-resume-to-dossier")
async def parse_resume_to_dossier(request: Request, user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user or not user_has_access(user, "hh", db):
        return JSONResponse({"error": "Нет доступа"}, status_code=403)
    if not OPENROUTER_API_KEY:
        return JSONResponse({"error": "API ключ не настроен"}, status_code=500)

    resume_obj = db.query(Resume).filter(Resume.user_id == user.id).first()
    resume_text = resume_obj.resume_text if resume_obj else ""
    if not resume_text.strip():
        return JSONResponse({"error": "Сначала добавь резюме"}, status_code=400)

    prompt = f"""Извлеки структурированные данные из резюме для заполнения профиля кандидата.
Ответь ТОЛЬКО JSON без ```json и без пояснений.

РЕЗЮМЕ:
{resume_text}

Верни JSON строго такой структуры (все поля опциональны — ставь null если данных нет):
{{
  "profession_one_liner": "краткое позиционирование в 1 предложение или null",
  "location": "город или null",
  "work_format": "удалёнка / офис / гибрид / любой или null",
  "total_years_in_profession": "например '5 лет' или null",
  "skills": ["навык1", "навык2"],
  "experience_extra": [
    {{
      "company": "название компании",
      "position": "должность",
      "period": "период, например 2022–2024",
      "description": "чем занимался в 1-2 предложениях",
      "achievements": "ключевые достижения или пустая строка"
    }}
  ],
  "projects": [
    {{
      "title": "название проекта",
      "url": "ссылка или пустая строка",
      "type": "тип проекта в 2-4 слова или пустая строка",
      "tags": ["тег1", "тег2"],
      "description": "описание в 1 предложении или пустая строка",
      "tools": "инструменты через запятую или пустая строка"
    }}
  ],
  "languages": [
    {{"lang": "язык", "level": "уровень"}}
  ]
}}

Правила:
- skills: только конкретные инструменты и технологии, без мягких навыков ("ответственность" и т.п.)
- projects: только реальные проекты с названиями из резюме, не придумывай
- experience_extra: в обратном хронологическом порядке
- Если что-то неочевидно — ставь null/пустую строку, не домысливай
"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}",
                         "HTTP-Referer": "https://energydess.ru", "X-Title": "EnergyDess HH Helper"},
                json={"model": PARSER_MODEL, "messages": [{"role": "user", "content": prompt}],
                      "temperature": 0.1, "max_tokens": 2000},
                timeout=60.0,
            )
        if response.status_code != 200:
            return JSONResponse({"error": f"Ошибка OpenRouter: {response.text}"}, status_code=500)
        raw = response.json()["choices"][0]["message"]["content"].strip()
        result = _extract_json(raw)
        return JSONResponse(result)
    except httpx.TimeoutException:
        return JSONResponse({"error": "Превышено время ожидания"}, status_code=504)
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


# ── HH Досье: Pydantic-схема ─────────────────────────────────────────────────

class _LangItem(BaseModel):
    lang: str = ""
    level: str = ""

class _ExperienceItem(BaseModel):
    company: str = ""
    position: str = ""
    period: str = ""
    description: str = ""
    achievements: str = ""

class _ProjectItem(BaseModel):
    title: str = ""
    type: str = ""
    url: str = ""
    description: str = ""
    tools: str = ""
    tags: List[str] = []

class _EndingStyle(BaseModel):
    suggest_call: bool = False
    suggest_test_task: bool = False
    just_farewell: bool = False

class HHProfileSchema(BaseModel):
    profession_one_liner: Optional[str] = None
    location: Optional[str] = None
    timezone: Optional[str] = None
    work_format: Optional[str] = None
    languages: List[_LangItem] = []
    total_years_in_profession: Optional[str] = None
    experience_extra: List[_ExperienceItem] = []
    projects: List[_ProjectItem] = []
    skills: List[str] = []
    methodology: Optional[str] = None
    extra_context: Optional[str] = None
    tone_preference: Optional[str] = None
    never_mention: Optional[str] = None
    ending_style: Optional[_EndingStyle] = None


# ── API: HH-досье ─────────────────────────────────────────────────────────────

@app.get("/api/hh-profile")
async def get_hh_profile(user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    profile = db.query(HHProfile).filter(HHProfile.user_id == user.id).first()
    if not profile:
        return JSONResponse({})
    return JSONResponse({
        "profession_one_liner": profile.profession_one_liner,
        "location": profile.location,
        "timezone": profile.timezone,
        "work_format": profile.work_format,
        "languages": profile.languages or [],
        "total_years_in_profession": profile.total_years_in_profession,
        "experience_extra": profile.experience_extra or [],
        "projects": profile.projects or [],
        "skills": profile.skills or [],
        "methodology": profile.methodology,
        "extra_context": profile.extra_context,
        "tone_preference": profile.tone_preference,
        "never_mention": profile.never_mention,
        "ending_style": profile.ending_style,
        "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
    })


@app.post("/api/hh-profile")
async def save_hh_profile(payload: HHProfileSchema, user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    profile = db.query(HHProfile).filter(HHProfile.user_id == user.id).first()
    data = payload.model_dump()
    # JSON-поля сериализуем в plain dict/list
    data["languages"] = [i.model_dump() for i in (payload.languages or [])]
    data["experience_extra"] = [i.model_dump() for i in (payload.experience_extra or [])]
    data["projects"] = [i.model_dump() for i in (payload.projects or [])]
    data["ending_style"] = payload.ending_style.model_dump() if payload.ending_style else None
    if not profile:
        profile = HHProfile(user_id=user.id, **data)
        db.add(profile)
    else:
        for field, value in data.items():
            setattr(profile, field, value)
        profile.updated_at = datetime.utcnow()
    db.commit()
    return JSONResponse({"ok": True})


@app.delete("/api/hh-profile")
async def delete_hh_profile(user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    profile = db.query(HHProfile).filter(HHProfile.user_id == user.id).first()
    if profile:
        db.delete(profile)
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


def _image_mime(file: UploadFile) -> str:
    """Content-Type из заголовка формы надёжнее имени файла (на телефонах оно часто без расширения)."""
    if file.content_type and file.content_type.startswith("image/"):
        return file.content_type
    ext = (file.filename or "").rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else ""
    return {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
            "webp": "image/webp", "gif": "image/gif", "heic": "image/heic",
            "heif": "image/heif"}.get(ext, "image/jpeg")


def _make_thumbnail(content: bytes, max_dim: int = 1920, quality: int = 85) -> str | None:
    """Копия фото для хранения в истории чата (data URL JPEG) — Full HD,
    чтобы вьюер на весь экран открывал её без замыливания."""
    import io
    from PIL import Image
    try:
        img = Image.open(io.BytesIO(content)).convert("RGB")
        img.thumbnail((max_dim, max_dim))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        return f"data:image/jpeg;base64,{base64.b64encode(buf.getvalue()).decode()}"
    except Exception:
        return None


async def _call_vision(b64: str, mime: str, prompt: str, max_tokens: int = 400) -> str:
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
                  "temperature": 0.2, "max_tokens": max_tokens},
            timeout=45.0,
        )
    if resp.status_code != 200:
        raise RuntimeError(f"Ошибка ИИ ({resp.status_code}): {resp.text[:200]}")
    return resp.json()["choices"][0]["message"]["content"].strip()


_FOOD_BLOCK_RE = re.compile(r"###FOOD_JSON###\s*(\{.*?\})\s*###END_FOOD_JSON###", re.S)


def _extract_food_block(text: str):
    """Достаёт блок ###FOOD_JSON### из ответа ИИ-чата (см. правило добавления еды в system-промпте)."""
    m = _FOOD_BLOCK_RE.search(text)
    if not m:
        return text.strip(), None
    try:
        food = _json.loads(m.group(1))
    except _json.JSONDecodeError:
        food = None
    return _FOOD_BLOCK_RE.sub("", text).strip(), food


def _extract_json(text: str) -> dict:
    """Достаёт JSON-объект из ответа модели, даже если он обёрнут в ```...``` или содержит лишний текст."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        text = text.strip()
    try:
        return _json.loads(text)
    except _json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            raise
        return _json.loads(m.group(0))


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
        text = resp.json()["choices"][0]["message"]["content"].strip()
        d = _extract_json(text)
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

    # Сохраняем блюдо в личную базу продуктов пользователя — чтобы то, что
    # пришло из ИИ-чата/фото, сканера или поиска по OpenFoodFacts, находилось
    # при следующем поиске по названию (CustomFood.name ilike в /api/search)
    name = data.get("name", "").strip()
    barcode = data.get("barcode") or None
    existing = None
    if barcode:
        existing = db.query(CustomFood).filter(
            CustomFood.user_id == user.id, CustomFood.barcode == barcode).first()
    if not existing and name:
        # как и в /api/search — сравниваем в Python, ilike не приводит к
        # нижнему регистру кириллицу в SQLite. Бренд тоже учитываем в сравнении —
        # одно и то же блюдо из разных заведений должно остаться разными записями
        name_lower = name.lower()
        brand_lower = (data.get("brand") or "").strip().lower()
        existing = next((f for f in db.query(CustomFood).filter(CustomFood.user_id == user.id).all()
                          if f.name.lower() == name_lower and (f.brand or "").lower() == brand_lower), None)
    if not existing and name:
        db.add(CustomFood(
            user_id=user.id, name=name, brand=data.get("brand", "") or None, barcode=barcode,
            calories_per_100g=cal_per_100, protein_per_100g=protein_per_100,
            fat_per_100g=fat_per_100, carbs_per_100g=carbs_per_100,
        ))

    db.commit()
    return JSONResponse({"ok": True, "id": log.id})


@app.put("/nutrition/api/log-food/{log_id}")
async def nut_update_food(log_id: int, request: Request, user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    log = db.query(FoodLog).filter(FoodLog.id == log_id, FoodLog.user_id == user.id).first()
    if not log:
        return JSONResponse({"error": "Не найдено"}, status_code=404)
    data = await request.json()
    grams = float(data.get("grams", log.grams))
    cal_per_100 = float(data.get("calories", 0))
    protein_per_100 = float(data.get("protein", 0))
    fat_per_100 = float(data.get("fat", 0))
    carbs_per_100 = float(data.get("carbs", 0))
    log.grams = grams
    log.calories = round(cal_per_100 * grams / 100, 1)
    log.protein = round(protein_per_100 * grams / 100, 1)
    log.fat = round(fat_per_100 * grams / 100, 1)
    log.carbs = round(carbs_per_100 * grams / 100, 1)
    meal_type = data.get("meal_type")
    if meal_type in ("breakfast", "lunch", "dinner", "snack"):
        log.meal_type = meal_type
    db.commit()
    return JSONResponse({"ok": True})


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
    # Регистронезависимый поиск по подстроке делаем на стороне Python: SQL
    # lower()/ilike в SQLite не приводят к нижнему регистру кириллицу, поэтому
    # "Картошка фри" не находилось бы по запросу "картошка фри"
    q_lower = q.strip().lower()
    all_custom = db.query(CustomFood).filter(CustomFood.user_id == user.id).all()
    custom = [f for f in all_custom if q_lower in f.name.lower()][:5]
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
    barcode = data.get("barcode", "").strip() or None
    name = data.get("name", "").strip()
    # Если штрих-код уже сохранён у пользователя — обновляем запись,
    # а не создаём дубликат (например, при повторной правке КБЖУ)
    food = None
    if barcode:
        food = db.query(CustomFood).filter(
            CustomFood.user_id == user.id, CustomFood.barcode == barcode).first()
    if not food:
        food = CustomFood(user_id=user.id, barcode=barcode)
        db.add(food)
    food.name = name
    food.brand = data.get("brand", "").strip() or None
    food.calories_per_100g = float(data.get("calories", 0))
    food.protein_per_100g = float(data.get("protein", 0))
    food.fat_per_100g = float(data.get("fat", 0))
    food.carbs_per_100g = float(data.get("carbs", 0))
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
        "logs": [{
            "date": l.log_date, "weight_kg": l.weight_kg,
            "waist_cm": l.waist_cm, "hips_cm": l.hips_cm, "chest_cm": l.chest_cm,
            "body_fat_pct": l.body_fat_pct, "muscle_rate_pct": l.muscle_rate_pct,
            "water_pct": l.water_pct, "visceral_fat": l.visceral_fat,
            "bmi": l.bmi, "bmr": l.bmr, "body_age": l.body_age, "bone_mass_kg": l.bone_mass_kg,
            "source": l.source,
        } for l in logs],
        "start_weight": profile.start_weight_kg if profile else None,
        "target_weight": profile.target_weight_kg if profile else None,
    })


_WEIGHT_LOG_FLOAT_FIELDS = ["weight_kg", "waist_cm", "hips_cm", "chest_cm",
                            "body_fat_pct", "muscle_rate_pct", "water_pct", "visceral_fat", "bmi", "bone_mass_kg"]
_WEIGHT_LOG_INT_FIELDS = ["bmr", "body_age"]


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
    for field in _WEIGHT_LOG_FLOAT_FIELDS:
        if data.get(field) is not None:
            setattr(existing, field, float(data[field]))
    for field in _WEIGHT_LOG_INT_FIELDS:
        if data.get(field) is not None:
            setattr(existing, field, int(data[field]))
    existing.source = "manual"  # ручная правка всегда переводит запись в "manual"
    db.commit()
    if data.get("weight_kg") is not None:
        profile = db.query(NutritionProfile).filter(NutritionProfile.user_id == user.id).first()
        if profile:
            profile.weight_kg = float(data["weight_kg"])
            db.commit()
    return JSONResponse({"ok": True})


# ── Умные весы Xiaomi (неофициальный API Zepp Life, см. zepp_client.py) ────
# Опциональная интеграция: если не подключено или API недоступен — ручной
# ввод выше продолжает работать как обычно, ничего не блокируется.
#
# Автосинхронизация "раз в день": на Fly.io машина может засыпать при
# отсутствии трафика, поэтому настоящий cron-таймер ненадёжен — он просто не
# выполнится, если в момент срабатывания машина спит. Вместо этого синк
# запускается лениво при первом заходе на страницу с весами (профиль
# тренировок ИЛИ дневника питания) после ~20 часов с последней попытки —
# не блокируя ответ (BackgroundTasks), так что страница не ждёт сетевой запрос
# к Zepp.
SCALE_AUTO_SYNC_INTERVAL_HOURS = 20


def _scale_needs_sync(conn: ScaleConnection) -> bool:
    if not conn.last_sync_at:
        return True
    return datetime.utcnow() - conn.last_sync_at > timedelta(hours=SCALE_AUTO_SYNC_INTERVAL_HOURS)


def _background_sync_scale(user_id: int):
    db = SessionLocal()
    try:
        conn = db.query(ScaleConnection).filter(ScaleConnection.user_id == user_id).first()
        if not conn:
            return
        try:
            _sync_scale(db, conn)
        except Exception as e:
            conn.last_sync_status = "error"
            conn.last_sync_error = str(e)[:300]
            db.commit()
    finally:
        db.close()


def _scale_status(conn: ScaleConnection | None) -> dict:
    if not conn:
        return {"connected": False}
    return {
        "connected": True,
        "last_sync_at": conn.last_sync_at.strftime("%Y-%m-%d %H:%M") if conn.last_sync_at else None,
        "last_sync_status": conn.last_sync_status,
        "last_sync_error": conn.last_sync_error,
    }


def _sync_scale(db: Session, conn: ScaleConnection) -> dict:
    """Логиним по кешированному токену; если он не работает — полный логин
    по паролю (это разлогинит пользователя в приложении Zepp Life, поэтому
    делаем так редко, не на каждую синхронизацию)."""
    username = _decrypt(conn.encrypted_username)
    password = _decrypt(conn.encrypted_password)

    def _do_fetch():
        return zepp_client.fetch_weight_records(conn.app_token, conn.zepp_user_id)

    try:
        if not conn.app_token:
            raise zepp_client.ZeppApiError("нет кешированного токена")
        records = _do_fetch()
    except (zepp_client.ZeppApiError, Exception):
        tokens = zepp_client.login(username, password)
        conn.app_token = tokens["app_token"]
        conn.zepp_user_id = tokens["zepp_user_id"]
        records = _do_fetch()

    saved = 0
    for rec in records:
        if not rec.get("timestamp") or rec.get("weight_kg") is None:
            continue
        log_date = datetime.fromtimestamp(rec["timestamp"]).strftime("%Y-%m-%d")
        row = db.query(WeightLog).filter(WeightLog.user_id == conn.user_id, WeightLog.log_date == log_date).first()
        if not row:
            row = WeightLog(user_id=conn.user_id, log_date=log_date)
            db.add(row)
        elif row.source == "manual":
            continue  # ручная запись на эту дату — не перетираем данными с весов
        row.weight_kg = rec["weight_kg"]
        row.bmi = rec.get("bmi")
        row.body_fat_pct = rec.get("body_fat_pct")
        row.water_pct = rec.get("water_pct")
        row.muscle_rate_pct = rec.get("muscle_rate_pct")
        row.bone_mass_kg = rec.get("bone_mass_kg")
        row.visceral_fat = rec.get("visceral_fat")
        row.bmr = int(rec["bmr"]) if rec.get("bmr") else None
        row.body_age = int(rec["body_age"]) if rec.get("body_age") else None
        row.source = "zepp"
        saved += 1

    conn.last_sync_at = datetime.utcnow()
    conn.last_sync_status = "ok"
    conn.last_sync_error = None
    db.commit()
    return {"ok": True, "synced": saved}


@app.get("/nutrition/api/scale/status")
async def scale_status(background_tasks: BackgroundTasks, user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    conn = db.query(ScaleConnection).filter(ScaleConnection.user_id == user.id).first()
    if conn and _scale_needs_sync(conn):
        background_tasks.add_task(_background_sync_scale, user.id)
    return JSONResponse(_scale_status(conn))


@app.post("/nutrition/api/scale/connect")
async def scale_connect(request: Request, user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    data = await request.json()
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    if not username or not password:
        return JSONResponse({"error": "Укажи логин и пароль Zepp Life"}, status_code=400)
    if not CREDENTIALS_ENCRYPTION_KEY:
        return JSONResponse({"error": "Шифрование не настроено на сервере"}, status_code=500)

    try:
        tokens = zepp_client.login(username, password)
    except zepp_client.ZeppLoginError as e:
        return JSONResponse({"error": f"Не удалось войти: {e}"}, status_code=400)
    except Exception as e:
        return JSONResponse({"error": f"Ошибка соединения с Zepp Life: {e}"}, status_code=502)

    conn = db.query(ScaleConnection).filter(ScaleConnection.user_id == user.id).first()
    if not conn:
        conn = ScaleConnection(user_id=user.id)
        db.add(conn)
    conn.encrypted_username = _encrypt(username)
    conn.encrypted_password = _encrypt(password)
    conn.app_token = tokens["app_token"]
    conn.zepp_user_id = tokens["zepp_user_id"]
    db.commit()

    try:
        result = _sync_scale(db, conn)
    except Exception as e:
        return JSONResponse({"ok": True, "warning": f"Подключено, но первая синхронизация не удалась: {e}"})
    return JSONResponse({"ok": True, "synced": result.get("synced", 0)})


@app.post("/nutrition/api/scale/sync")
async def scale_sync(user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    conn = db.query(ScaleConnection).filter(ScaleConnection.user_id == user.id).first()
    if not conn:
        return JSONResponse({"error": "Весы не подключены"}, status_code=400)
    try:
        result = _sync_scale(db, conn)
    except Exception as e:
        conn.last_sync_status = "error"
        conn.last_sync_error = str(e)[:300]
        db.commit()
        return JSONResponse({"error": f"Синхронизация не удалась: {e}"}, status_code=502)
    return JSONResponse(result)


@app.post("/nutrition/api/scale/disconnect")
async def scale_disconnect(user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    db.query(ScaleConnection).filter(ScaleConnection.user_id == user.id).delete()
    db.commit()
    return JSONResponse({"ok": True})


# ── Фото-дневник прогресса тела (визуальный, без ИИ-анализа) ───────────────

BODY_PHOTO_ANGLES = {"front", "side", "back"}


@app.post("/nutrition/api/body-photo")
async def upload_body_photo(file: UploadFile = File(...), angle: str = Form(...), date: str = Form(...),
                             user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    if angle not in BODY_PHOTO_ANGLES:
        return JSONResponse({"error": "Некорректный ракурс"}, status_code=400)
    content = await file.read()
    if not content:
        return JSONResponse({"error": "Пустой файл"}, status_code=400)
    thumb = _make_thumbnail(content, max_dim=1600, quality=88)
    if not thumb:
        return JSONResponse({"error": "Не удалось обработать фото"}, status_code=400)

    existing = db.query(BodyPhoto).filter(
        BodyPhoto.user_id == user.id, BodyPhoto.log_date == date, BodyPhoto.angle == angle,
    ).first()
    if existing:
        existing.image_data = thumb
    else:
        db.add(BodyPhoto(user_id=user.id, log_date=date, angle=angle, image_data=thumb))
    db.commit()
    return JSONResponse({"ok": True})


@app.get("/nutrition/api/body-photos")
async def list_body_photos(user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    rows = db.query(BodyPhoto).filter(BodyPhoto.user_id == user.id).order_by(BodyPhoto.log_date.desc()).all()
    by_date = {}
    for r in rows:
        by_date.setdefault(r.log_date, {})[r.angle] = r.image_data
    dates = sorted(by_date.keys(), reverse=True)
    return JSONResponse({"dates": dates, "photos": by_date})


# ── Nutrition: history / weekly ───────────────────────────────────────────────

@app.get("/nutrition/api/weekly")
async def nut_weekly(user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    today = datetime.now().date()
    start = (today - timedelta(days=6)).strftime("%Y-%m-%d")
    end = today.strftime("%Y-%m-%d")
    # дни с тренировками за неделю — связка с программой тренировок, чтобы
    # в дневнике питания было видно, в какие дни была нагрузка
    trained_dates = {
        s.log_date for s in db.query(WorkoutSession.log_date).filter(
            WorkoutSession.user_id == user.id, WorkoutSession.log_date >= start,
            WorkoutSession.log_date <= end, WorkoutSession.skipped == False,
        ).all()
    }
    days = []
    for i in range(6, -1, -1):
        d = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        logs = db.query(FoodLog).filter(FoodLog.user_id == user.id, FoodLog.log_date == d).all()
        days.append({
            "date": d,
            "calories": round(sum(l.calories for l in logs), 0),
            "protein": round(sum(l.protein for l in logs), 1),
            "trained": d in trained_dates,
        })
    return JSONResponse({"days": days})


# ── Nutrition: AI chat ───────────────────────────────────────────────────────

@app.get("/nutrition/api/chat-history")
async def nut_chat_history(user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    msgs = db.query(ChatMessage).filter(ChatMessage.user_id == user.id).order_by(
        ChatMessage.created_at).limit(100).all()
    result = []
    for m in msgs:
        item = {"role": m.role, "content": m.content}
        if m.image_data:
            item["image"] = m.image_data
        result.append(item)
    return JSONResponse({"messages": result})


@app.post("/nutrition/api/ai-chat")
async def nut_ai_chat(request: Request, user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user or not user_has_access(user, "nutrition", db):
        return JSONResponse({"error": "Нет доступа"}, status_code=403)
    data = await request.json()
    msg = (data.get("message") or "").strip()
    date = data.get("date", datetime.now().strftime("%Y-%m-%d"))
    if not msg:
        return JSONResponse({"error": "Пустое сообщение"}, status_code=400)

    history = db.query(ChatMessage).filter(ChatMessage.user_id == user.id).order_by(
        ChatMessage.created_at).limit(40).all()

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
{food_list}

ЖЁСТКОЕ ПРАВИЛО про добавление еды в дневник: у тебя НЕТ инструмента, который сам добавляет еду — единственный способ добавить блюдо в дневник пользователя — приложить в конце ответа специальный блок (см. формат ниже), который откроет пользователю выбор приёма пищи (завтрак/обед/ужин/перекус).
Добавляй этот блок, когда:
- пользователь описал блюдо (название + калорийность хотя бы) и попросил добавить/записать его, ИЛИ
- ты сам предложил блюдо с оценкой КБЖУ, и пользователь подтвердил ("да", "верно", "добавь", "ок" и т.п.).
НИКОГДА не пиши "добавил", "записал в дневник", "готово" и т.п. без этого блока — без него ничего не добавится, и пользователь увидит ложь. Если данных о калорийности не хватает — сначала уточни их, не добавляй блок.
ПРО БРЕНД/ЗАВЕДЕНИЕ: если из переписки понятно название кафе, ресторана, сети или производителя — укажи его в поле brand блока. Если блюдо явно ресторанное/готовое (а не домашняя еда вроде "сварил суп") и бренд/заведение НЕ упомянуты — перед добавлением блока спроси одним коротким вопросом, из какого места это блюдо, и не добавляй блок, пока не получишь ответ (или пользователь явно скажет, что не помнит/не важно — тогда добавляй блок с пустым brand).
Формат блока (в конце ответа, отдельным фрагментом):
###FOOD_JSON###
{{"name":"название блюда","brand":"заведение или производитель (пустая строка, если неизвестно/не нужно)","calories":150,"protein":10,"fat":5,"carbs":20,"estimated_grams":100}}
###END_FOOD_JSON###
calories/protein/fat/carbs — на 100г продукта, estimated_grams — вес съеденной порции."""

    api_messages = ([{"role": "system", "content": system}]
                     + [{"role": h.role, "content": h.content} for h in history]
                     + [{"role": "user", "content": msg}])

    db.add(ChatMessage(user_id=user.id, role="user", content=msg))
    db.commit()

    if not OPENROUTER_API_KEY:
        reply = "API ключ не настроен."
    else:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}",
                             "HTTP-Referer": "https://energydess.ru", "X-Title": "EnergyDess Nutrition"},
                    json={"model": LETTER_MODEL, "messages": api_messages,
                          "temperature": 0.4, "max_tokens": 500},
                    timeout=30.0,
                )
            reply = resp.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)

    reply, food = _extract_food_block(reply)
    db.add(ChatMessage(user_id=user.id, role="assistant", content=reply))
    db.commit()
    return JSONResponse({"reply": reply, "food": food} if food else {"reply": reply})


# ── Nutrition: AI photo ───────────────────────────────────────────────────────

@app.post("/nutrition/api/ai-photo")
async def nut_ai_photo(file: UploadFile = File(...), description: str = Form(""),
                       user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user or not user_has_access(user, "nutrition", db):
        return JSONResponse({"error": "Нет доступа"}, status_code=403)
    content = await file.read()
    if not content:
        return JSONResponse({"error": "Пустой файл"}, status_code=400)
    b64 = base64.b64encode(content).decode()
    mime = _image_mime(file)

    extra = f"\nДополнительное описание от пользователя: {description.strip()}" if description.strip() else ""
    prompt = f"""На фото еда. Определи что изображено и оцени калорийность на 100г.{extra}
Если в описании упомянуто название кафе, ресторана, сети или производителя — укажи его в поле brand. Если не упомянуто — оставь brand пустой строкой.
Ответь ТОЛЬКО JSON без ```json и без пояснений:
{{"name":"название блюда","brand":"заведение или производитель (пустая строка, если неизвестно)","calories":150,"protein":10,"fat":5,"carbs":20,"estimated_grams":300,"note":"краткое пояснение"}}"""

    try:
        text = await _call_vision(b64, mime, prompt)
        result = _extract_json(text)
        return JSONResponse({"ok": True, "food": result})
    except Exception as e:
        return JSONResponse({"error": f"Не удалось распознать: {e}"}, status_code=500)


@app.post("/nutrition/api/ai-chat-photo")
async def nut_ai_chat_photo(file: UploadFile = File(...), message: str = Form(""), date: str = Form(...),
                            user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user or not user_has_access(user, "nutrition", db):
        return JSONResponse({"error": "Нет доступа"}, status_code=403)
    content = await file.read()
    if not content:
        return JSONResponse({"error": "Пустой файл"}, status_code=400)
    b64 = base64.b64encode(content).decode()
    mime = _image_mime(file)
    user_text = message.strip()
    thumb = _make_thumbnail(content)

    comment = f"\nКомментарий пользователя: {user_text}" if user_text else ""
    prompt = f"""На фото еда, которую съел пользователь.{comment}
Определи блюдо, оцени калорийность на 100г и примерный вес порции на фото.
Если в комментарии пользователя упомянуто название кафе, ресторана, сети или производителя — укажи его в поле brand. Если не упомянуто — оставь brand пустой строкой.
Ответь ТОЛЬКО JSON без ```json и без пояснений:
{{"name":"название блюда","brand":"заведение или производитель (пустая строка, если неизвестно)","calories":150,"protein":10,"fat":5,"carbs":20,"estimated_grams":300}}"""

    db.add(ChatMessage(user_id=user.id, role="user", content=user_text or "[фото блюда]", image_data=thumb))

    try:
        text = await _call_vision(b64, mime, prompt)
        food = _extract_json(text)
    except Exception as e:
        reply = f"Не удалось распознать фото: {e}"
        db.add(ChatMessage(user_id=user.id, role="assistant", content=reply))
        db.commit()
        return JSONResponse({"reply": reply})

    grams = food.get("estimated_grams", 100)
    total_cal = round(food.get("calories", 0) * grams / 100)
    total_prot = round(food.get("protein", 0) * grams / 100)
    total_fat = round(food.get("fat", 0) * grams / 100)
    total_carb = round(food.get("carbs", 0) * grams / 100)
    reply = (f"Похоже на «{food.get('name', 'блюдо')}»: примерно {total_cal} ккал на ~{grams:.0f}г "
             f"(Б:{total_prot}г Ж:{total_fat}г У:{total_carb}г). Это какой приём пищи?")
    if not (food.get("brand") or "").strip():
        reply += " И кстати, из какого кафе/ресторана или какой марки этот продукт? Это поможет точнее находить его в поиске."

    db.add(ChatMessage(user_id=user.id, role="assistant", content=reply))
    db.commit()
    return JSONResponse({"reply": reply, "food": food})


# ── Nutrition: распознавание голосовых сообщений (Whisper через OpenRouter) ────

# Прямой аплоад файлов на api.groq.com из РФ блокируется DPI (зависают POST >10-30КБ
# на Cloudflare-хосты). OpenRouter под эту блокировку не попадает, поэтому шлём
# тот же whisper-large-v3-turbo (провайдер Groq) через него, JSON с base64-аудио.
_TRANSCRIBE_FORMATS = {
    "audio/webm": "webm",
    "audio/ogg": "ogg",
    "audio/mp4": "m4a",
    "audio/mpeg": "mp3",
    "audio/wav": "wav",
}

@app.post("/nutrition/api/transcribe")
async def nut_transcribe(file: UploadFile = File(...),
                          user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user or not user_has_access(user, "nutrition", db):
        return JSONResponse({"error": "Нет доступа"}, status_code=403)
    if not OPENROUTER_API_KEY:
        return JSONResponse({"error": "Распознавание речи не настроено"}, status_code=503)
    content = await file.read()
    if not content:
        return JSONResponse({"error": "Пустая запись"}, status_code=400)

    content_type = (file.content_type or "audio/webm").split(";")[0].strip()
    audio_format = _TRANSCRIBE_FORMATS.get(content_type, "webm")

    last_error = None
    timeout = httpx.Timeout(10.0, read=60.0, write=30.0)
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    "https://openrouter.ai/api/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
                    json={
                        "input_audio": {"data": base64.b64encode(content).decode("ascii"), "format": audio_format},
                        "model": "openai/whisper-large-v3-turbo",
                        "language": "ru",
                    },
                )
            resp.raise_for_status()
            text = resp.json().get("text", "").strip()
            return JSONResponse({"text": text})
        except Exception as e:
            last_error = e
            print(f"[transcribe] попытка {attempt+1} не удалась (размер файла {len(content)} байт, "
                  f"content_type={file.content_type}): {type(e).__name__}: {e!r}")
            if isinstance(e, httpx.HTTPStatusError):
                print(f"[transcribe] ответ OpenRouter: {e.response.status_code} {e.response.text[:300]}")
            if attempt == 0:
                await asyncio.sleep(2)

    err_text = f"{type(last_error).__name__}: {last_error}" if last_error else "неизвестная ошибка"
    return JSONResponse({"error": f"Не удалось распознать речь: {err_text}"}, status_code=500)


# ── Workout: программа тренировок ──────────────────────────────────────────

WORKOUT_GOALS = {"mass", "strength", "lose", "maintain", "recomp"}
WORKOUT_LEVELS = {"beginner", "intermediate", "expert"}
WORKOUT_PAIN_ZONES = {"knee", "lower_back", "shoulder", "elbow", "neck"}
WORKOUT_FOCUS_ZONES = {"arms", "shoulders", "chest", "back", "legs", "abs", "glutes"}
SKIP_REASONS = {"tired", "no_time", "sick", "gym_closed"}

# Шаг прогрессии — авто по типу оборудования (kind="weight") или по
# повторам/вариации для bodyweight (kind="reps"), без отдельного вопроса
# в анкете. equipment=None (free-exercise-db) уже трактуется как "body only".
PROGRESSION_DEFAULTS = {
    "barbell":        ("weight", 2.5),
    "e-z curl bar":   ("weight", 2.5),
    "dumbbell":       ("weight", 1.0),
    "kettlebells":    ("weight", 1.0),
    "machine":        ("weight", 5.0),
    "cable":          ("weight", 5.0),
    "body only":      ("reps", None),
    "bands":          ("reps", None),
    "exercise ball":  ("reps", None),
    "medicine ball":  ("reps", None),
    None:             ("reps", None),
}

# Возвращение после перерыва
RETURN_GAP_DAYS = 14
RETURN_PLAN_FACTORS = {"short": 0.8, "long": 0.6, "injury": None}
RETURN_PLAN_LIGHT_DAYS = 2

# Мезоцикл — через сколько недель предлагать обновление программы
MESOCYCLE_DEFAULT_WEEKS = 10

# "Застряло" — 3+ завершённых тренировки одного упражнения с верхом
# диапазона повторов, но без роста веса, в пределах 2+ недель
STUCK_MIN_SESSIONS = 3
STUCK_MIN_SPAN_DAYS = 14


def _workout_equipment_checklist(db: Session):
    """34 кластера оборудования для чек-листа "Мой зал": подпись
    "Русское / English" + картинка первого подходящего упражнения."""
    rows = db.query(Exercise).filter(Exercise.equipment_cluster.isnot(None)).all()
    by_cluster = {}
    for e in rows:
        if e.equipment_cluster not in by_cluster and e.images:
            by_cluster[e.equipment_cluster] = e.images[0]
    items = []
    for label, image in sorted(by_cluster.items()):
        name_ru, _, name_en = label.partition(" / ")
        items.append({"label": label, "name_ru": name_ru, "name_en": name_en, "image": image})
    return items


@app.get("/workout")
async def workout_page(request: Request, user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return RedirectResponse("/login", status_code=302)
    if not user_has_access(user, "workout", db):
        return RedirectResponse("/?locked=workout", status_code=302)
    return templates.TemplateResponse(request=request, name="workout.html", context={
        "user": user,
        "equipment_options": _workout_equipment_checklist(db),
    })


@app.get("/workout/profile")
async def workout_profile_page(request: Request, user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return RedirectResponse("/login", status_code=302)
    if not user_has_access(user, "workout", db):
        return RedirectResponse("/?locked=workout", status_code=302)
    return templates.TemplateResponse(request=request, name="workout_profile.html", context={
        "user": user,
        "equipment_options": _workout_equipment_checklist(db),
    })


@app.get("/workout/api/profile")
async def workout_get_profile(user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    p = db.query(WorkoutProfile).filter(WorkoutProfile.user_id == user.id).first()
    if not p:
        return JSONResponse({"exists": False})
    return JSONResponse({
        "exists": True,
        "goal": p.goal, "days_per_week": p.days_per_week, "level": p.level,
        "focus_zones": p.focus_zones or [], "pain_zones": p.pain_zones,
        "equipment": p.equipment, "home_only": p.home_only, "onboarded": p.onboarded,
        # готовые подписи на русском — чтобы страница профиля не дублировала
        # словари перевода визарда (они живут только в workout.html)
        "labels": {
            "goal": GOAL_LABELS_RU.get(p.goal, p.goal),
            "level": LEVEL_LABELS_RU.get(p.level, p.level),
            "focus_zones": [FOCUS_ZONE_LABELS_RU.get(z, z) for z in (p.focus_zones or [])],
            "pain_zones": [ZONE_LABELS_RU.get(z, z) for z in (p.pain_zones or [])],
        },
    })


@app.post("/workout/api/profile")
async def workout_save_profile(request: Request, user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    data = await request.json()

    goal = data.get("goal")
    if goal not in WORKOUT_GOALS:
        return JSONResponse({"error": "Некорректная цель"}, status_code=400)
    try:
        days_per_week = int(data.get("days_per_week"))
    except (TypeError, ValueError):
        return JSONResponse({"error": "Некорректная частота"}, status_code=400)
    if not 1 <= days_per_week <= 6:
        return JSONResponse({"error": "Частота — от 1 до 6 дней"}, status_code=400)
    level = data.get("level")
    if level not in WORKOUT_LEVELS:
        return JSONResponse({"error": "Некорректный стаж"}, status_code=400)
    # максимум 2 зоны упора — иначе акцент размывается (см. анкету, шаг 2)
    focus_zones = [z for z in data.get("focus_zones", []) if z in WORKOUT_FOCUS_ZONES][:2]
    pain_zones = [z for z in data.get("pain_zones", []) if z in WORKOUT_PAIN_ZONES]
    home_only = bool(data.get("home_only", False))
    equipment = [] if home_only else [str(x) for x in data.get("equipment", [])]

    p = db.query(WorkoutProfile).filter(WorkoutProfile.user_id == user.id).first()
    if not p:
        p = WorkoutProfile(user_id=user.id)
        db.add(p)
        material_change = False  # анкета впервые — генерация и так произойдёт отдельно
    else:
        # значимое изменение — то, что влияет на саму генерацию программы;
        # считаем здесь один раз, а не дублируем сравнение в каждом фронтенде,
        # который умеет сохранять анкету (визард и страница профиля)
        material_change = (
            p.goal != goal or p.days_per_week != days_per_week or p.level != level
            or sorted(p.focus_zones or []) != sorted(focus_zones)
            or sorted(p.pain_zones or []) != sorted(pain_zones)
            or sorted(p.equipment or []) != sorted(equipment)
            or bool(p.home_only) != home_only
        )
    p.goal = goal
    p.days_per_week = days_per_week
    p.level = level
    p.focus_zones = focus_zones
    p.pain_zones = pain_zones
    p.equipment = equipment
    p.home_only = home_only
    p.onboarded = True
    db.commit()
    return JSONResponse({"ok": True, "material_change": material_change})


# ── Workout: ИИ-генерация программы ──────────────────────────────────────────


def _load_trainer_system_prompt() -> str:
    """Системный промпт тренера хранится в TRAINER_PROMPT.md как научно
    обоснованный source of truth (обновляется отдельно от кода) — отсюда
    вытаскивается только тело промпта между ``` ```, без обвязки/ссылок."""
    path = os.path.join(os.path.dirname(__file__), "TRAINER_PROMPT.md")
    with open(path, encoding="utf-8") as f:
        text = f.read()
    start = text.index("```\n", text.index("## Системный промпт")) + 4
    end = text.index("```", start)
    return text[start:end].strip()


TRAINER_SYSTEM_PROMPT = _load_trainer_system_prompt()

GOAL_LABELS_RU = {
    "mass": "набор массы", "strength": "сила", "lose": "похудение",
    "maintain": "поддержание формы", "recomp": "рекомпозиция (набор мышц + жиросжигание)",
}
LEVEL_LABELS_RU = {"beginner": "новичок", "intermediate": "средний уровень", "expert": "опытный"}
FOCUS_ZONE_LABELS_RU = {
    "arms": "руки", "shoulders": "плечи", "chest": "грудь", "back": "спина",
    "legs": "ноги", "abs": "пресс", "glutes": "ягодицы",
}

# Эти типы оборудования считаем доступными всегда (даже без отметок в "Моём
# зале") — штанга/гантели/резинки и т.п. есть почти в любом зале и дома.
# Конкретные тренажёры (machine/other/cable) — только если есть в "Моём зале".
ALWAYS_AVAILABLE_EQUIPMENT = [None, "body only", "barbell", "dumbbell", "bands",
                              "kettlebells", "medicine ball", "exercise ball", "e-z curl bar"]
# Кардио/растяжка — вне скоупа первой версии (см. ТЗ, раздел 9, вторая очередь)
PROGRAM_CATEGORIES = ["strength", "powerlifting", "olympic weightlifting", "strongman"]
LEVEL_INCLUDES = {
    "beginner": ["beginner"],
    "intermediate": ["beginner", "intermediate"],
    "expert": ["beginner", "intermediate", "expert"],
}
PAIN_ZONE_MUSCLES = {
    # hamstrings сюда не входят: TRAINER_PROMPT.md для колена исключает только
    # глубокие приседания/выпады/жим ногами — упражнения на бицепс бедра
    # через тазобедренный шарнир (РДТ, доброе утро) коленный сустав не грузят
    "knee": {"quadriceps"},
    "lower_back": {"lower back"},
    "shoulder": {"shoulders"},
    "elbow": {"triceps", "biceps"},
    "neck": {"neck", "traps"},
}

# Куда смещать нагрузку при замене упражнения, задевающего зону боли — не
# просто "что угодно с той же мышцей" (которой в пуле часто и нет, см.
# PAIN_ZONE_MUSCLES выше), а целевые мышцы безопасного движения для этой
# зоны. Заполнено там, где замена клинически однозначна; для зон без
# явного безопасного редиректа (плечо/локоть/шея) остаётся пусто — для них
# работает обычный _find_alternatives с откатом на честное удаление.
PAIN_ZONE_REDIRECT_MUSCLES = {
    "knee": {"glutes", "hamstrings"},  # тазобедренный шарнир без нагрузки на колено
    "lower_back": {"abdominals"},      # брейсинг кора вместо нагруженной поясницы
    "shoulder": set(),
    "elbow": set(),
    "neck": set(),
}
PAIN_ZONE_REDIRECT_AVOID_NAME_KEYWORDS = {
    # "взятие"/"рывок"/"толчок ядра" — взрывные тяжелоатлетические движения,
    # они попадают в category="strength" в базе, поэтому одной фильтрации
    # по категории недостаточно (не путать с "тазовый толчок" — нужная фраза
    # длиннее и не пересекается с этим списком)
    "knee": ["присед", "выпад", "сгибание ног", "разгибание ног", "жим ногами", "прыж", "гак", "взятие", "рывок", "толчок ядра"],
    "lower_back": ["наклон", "гиперэкстенз", "становая", "доброе утро"],
}
# Канонический, клинически однозначный выбор для зоны — если среди
# кандидатов есть совпадение по названию, берём его первым, а не первое
# попавшееся с подходящей мышцей (иначе можно словить случайный взрывной
# вариант с той же мышцей, см. avoid-лист выше)
PAIN_ZONE_REDIRECT_PREFER_KEYWORDS = {
    "knee": ["ягодичный мост", "тазовый толчок", "хип-трас", "румынск", "гиперэкстенз", "доброе утро", "отведение"],
    "lower_back": ["планка", "скручивани", "вакуум"],
}
# без strongman/olympic weightlifting — взрывные/баллистические движения
# рискованнее при боли в суставе, даже если мышца формально подходящая
PAIN_ZONE_REDIRECT_CATEGORIES = {"strength", "powerlifting"}


def _program_structure(days_per_week: int):
    """Структура программы выводится из частоты, не выбирается произвольно
    (см. ТЗ, раздел 2): 2-3 дня — фулл-боди, 4 — верх/низ, 5-6 — push/pull/legs."""
    if days_per_week <= 3:
        days = [{"index": i, "type": "full_body", "label": f"День {i+1} — Фулл-боди"} for i in range(days_per_week)]
        return "full_body", days
    if days_per_week == 4:
        names = {"upper": "Верх тела", "lower": "Низ тела"}
        types = ["upper", "lower"]
        days = [{"index": i, "type": types[i % 2], "label": f"День {i+1} — {names[types[i % 2]]}"} for i in range(4)]
        return "upper_lower", days
    names = {"push": "Толкающие (грудь, плечи, трицепс)", "pull": "Тянущие (спина, бицепс)", "legs": "Ноги"}
    types = ["push", "pull", "legs"]
    days = [{"index": i, "type": types[i % 3], "label": f"День {i+1} — {names[types[i % 3]]}"} for i in range(days_per_week)]
    return "push_pull_legs", days


def _exercise_pool(db: Session, profile: WorkoutProfile):
    """Пул упражнений-кандидатов: категория силовая, по уровню, по доступному
    оборудованию (всегда доступное + отмеченное в "Моём зале"), без упражнений
    на зоны боли из анкеты (по primary+secondary мышцам)."""
    q = db.query(Exercise).filter(
        Exercise.category.in_(PROGRAM_CATEGORIES),
        Exercise.level.in_(LEVEL_INCLUDES.get(profile.level, ["beginner"])),
    )
    if profile.home_only:
        rows = q.filter(Exercise.equipment.in_(ALWAYS_AVAILABLE_EQUIPMENT)).all()
    else:
        rows = q.filter(
            or_(
                Exercise.equipment.in_(ALWAYS_AVAILABLE_EQUIPMENT),
                Exercise.equipment_cluster.in_(profile.equipment or []),
            )
        ).all()

    excluded_muscles = set()
    for zone in profile.pain_zones or []:
        excluded_muscles |= PAIN_ZONE_MUSCLES.get(zone, set())
    if excluded_muscles:
        rows = [
            e for e in rows
            if not (excluded_muscles & set(e.primary_muscles or []))
            and not (excluded_muscles & set(e.secondary_muscles or []))
        ]
    return rows


_ALT_NAME_STOPWORDS = {
    "barbell", "dumbbell", "cable", "machine", "with", "the", "a", "of", "on", "in",
    "to", "and", "or", "v", "bar", "smith",
}


def _name_overlap(name_a: str, name_b: str) -> int:
    """Тай-брейкер при равном счёте по мышцам/типу движения: совпадающие
    слова в названии (кроме типа оборудования) — "Bench Press" совпадёт
    у штанги и гантелей сильнее, чем у случайной другой груди-изоляции."""
    words_a = set(re.findall(r"[a-zA-Z]+", name_a.lower())) - _ALT_NAME_STOPWORDS
    words_b = set(re.findall(r"[a-zA-Z]+", name_b.lower())) - _ALT_NAME_STOPWORDS
    return len(words_a & words_b)


def _find_alternatives(db: Session, exercise: Exercise, profile: WorkoutProfile, exclude_exercise_ids, limit: int = 2):
    """Альтернативы упражнению: те же primaryMuscles, доступное оборудование
    (тот же пул, что и для генерации), без дублей того, что уже в этом дне.
    Ранжируем не только по основным мышцам, но и по вторичным + совпадению
    типа движения (mechanic/force) — иначе "жим штанги" может предложить
    случайную изоляцию вместо очевидного "жим гантелей" с тем же паттерном."""
    target_primary = set(exercise.primary_muscles or [])
    if not target_primary:
        return []
    target_secondary = set(exercise.secondary_muscles or [])
    pool = _exercise_pool(db, profile)
    candidates = []
    for e in pool:
        if e.id == exercise.id or e.id in exclude_exercise_ids:
            continue
        primary_overlap = len(target_primary & set(e.primary_muscles or []))
        if not primary_overlap:
            continue
        secondary_overlap = len(target_secondary & set(e.secondary_muscles or []))
        score = (
            primary_overlap * 10
            + secondary_overlap * 2
            + (3 if e.mechanic == exercise.mechanic else 0)
            + (2 if e.force == exercise.force else 0)
            + _name_overlap(exercise.name, e.name) * 3
        )
        candidates.append((score, e))
    candidates.sort(key=lambda t: -t[0])
    return [e for _, e in candidates[:limit]]


def _last_activity_date(db: Session, user_id: int):
    """Дата последней тренировки, где реально были залогированы подходы
    (пропуски "не смог сегодня" не считаются активностью)."""
    row = (db.query(WorkoutSession.log_date)
           .join(SetLog, SetLog.session_id == WorkoutSession.id)
           .filter(WorkoutSession.user_id == user_id, WorkoutSession.skipped == False)
           .order_by(WorkoutSession.log_date.desc()).first())
    return row[0] if row else None


def _mesocycle_info(profile: WorkoutProfile):
    length = profile.mesocycle_length_weeks or MESOCYCLE_DEFAULT_WEEKS
    if not profile.mesocycle_started_date:
        return {"week": 1, "length": length, "due": False}
    today = datetime.now().strftime("%Y-%m-%d")
    days = (datetime.strptime(today, "%Y-%m-%d") - datetime.strptime(profile.mesocycle_started_date, "%Y-%m-%d")).days
    week = min(length, max(1, days // 7 + 1))
    return {"week": week, "length": length, "due": week >= length}


def _is_stuck(db: Session, user_id: int, exercise_id: str, pe: WorkoutProgramExercise) -> bool:
    """Прогрессия застряла: 3+ завершённых тренировки этого упражнения подряд
    (не пропущенных, не лёгких), весь диапазон повторов выполнен каждый раз,
    но вес не рос — и это растянуто на 2+ недели (не пачка тренировок за пару
    дней при высокой частоте)."""
    rows = (db.query(WorkoutSession.id, WorkoutSession.log_date)
            .join(SetLog, SetLog.session_id == WorkoutSession.id)
            .filter(WorkoutSession.user_id == user_id, SetLog.exercise_id == exercise_id,
                    WorkoutSession.completed == True, WorkoutSession.skipped == False,
                    WorkoutSession.is_light_day == False)
            .distinct().order_by(WorkoutSession.log_date.desc()).limit(STUCK_MIN_SESSIONS).all())
    if len(rows) < STUCK_MIN_SESSIONS:
        return False
    span_days = (datetime.strptime(rows[0][1], "%Y-%m-%d") - datetime.strptime(rows[-1][1], "%Y-%m-%d")).days
    if span_days < STUCK_MIN_SPAN_DAYS:
        return False
    weights = []
    for sid, _ in rows:
        sets = db.query(SetLog).filter(SetLog.session_id == sid, SetLog.exercise_id == exercise_id).all()
        filled = [s for s in sets if s.reps is not None]
        if len(filled) < pe.target_sets or any(s.reps < pe.rep_high for s in filled):
            return False  # хоть раз не дожал верх — это нормальный прогресс, не застой
        w = [s.weight_kg for s in filled if s.weight_kg is not None]
        if not w:
            return False
        weights.append(max(w))
    return len(set(weights)) == 1


def _build_program_user_message(profile: WorkoutProfile, days, pool):
    """User message — только факты профиля и доступные данные. Все правила
    по объёму/диапазонам/балансу групп/порядку — в системном промпте
    (TRAINER_SYSTEM_PROMPT), сюда не дублируются, чтобы не разойтись с ним."""
    pool_compact = [
        {"id": e.id, "name": e.name_ru, "primary": e.primary_muscles, "equipment": e.equipment, "mechanic": e.mechanic}
        for e in pool
    ]
    days_desc = "\n".join(f'- day_index={d["index"]}, тип "{d["type"]}": {d["label"]}' for d in days)
    focus_desc = (
        ", ".join(FOCUS_ZONE_LABELS_RU.get(z, z) for z in (profile.focus_zones or []))
        or "нет особого акцента"
    )
    example = _json.dumps(
        {"days": [{
            "day_index": 0,
            "exercises": [{"exercise_id": "...", "sets": 3, "rep_low": 8, "rep_high": 12}],
            "bonus_exercises": [{"exercise_id": "...", "sets": 2, "rep_low": 10, "rep_high": 15}],
        }]},
        ensure_ascii=False,
    )
    return f"""Составь программу тренировок для клиента.

Профиль клиента:
- Цель: {GOAL_LABELS_RU.get(profile.goal, profile.goal)}
- Уровень: {LEVEL_LABELS_RU.get(profile.level, profile.level)}
- Дней в неделю: {profile.days_per_week}
- Зоны упора (см. раздел "ЗОНЫ УПОРА" в твоих знаниях — это ЗАМЕНА упражнения, не добавка сверху лимита): {focus_desc}

Дни программы (структура уже задана по правилу от частоты, не меняй её — заполни упражнениями каждый день под его тип/фокус):
{days_desc}

Доступные упражнения (выбирай ТОЛЬКО из этого списка, по полю id, ничего не придумывай — ограничения и оборудование клиента уже учтены при формировании списка):
{_json.dumps(pool_compact, ensure_ascii=False)}

Для каждого упражнения укажи sets (целое число подходов) и rep_low/rep_high (целые числа, диапазон повторов) — по правилам из твоих знаний для этой цели и типа упражнения.

"exercises" — основные упражнения дня, строго в пределах лимита из раздела "КОЛИЧЕСТВО УПРАЖНЕНИЙ НА ТРЕНИРОВКУ" (НИКОГДА 7+, зоны упора заменяют, а не добавляют). "bonus_exercises" — отдельно, 1-2 опциональных упражнения "если остались силы" (см. раздел "ОПЦИОНАЛЬНЫЙ БЛОК"), вне основного лимита.

Ответ — ТОЛЬКО JSON без markdown-обёртки, формат:
{example}
"""


def _progression_scope_for(equipment, equipment_cluster):
    if equipment in ("machine", "cable") and equipment_cluster:
        return f"cluster:{equipment_cluster}"
    return f"equipment:{equipment}"


def _resolve_progression(db: Session, user_id: int, equipment, equipment_cluster):
    scope = _progression_scope_for(equipment, equipment_cluster)
    kind, default_step = PROGRESSION_DEFAULTS.get(equipment, ("reps", None))
    if kind != "weight":
        return {"kind": kind, "step_kg": None, "fixed_values": None, "status": None, "scope": scope}
    setting = db.query(ProgressionSetting).filter(
        ProgressionSetting.user_id == user_id, ProgressionSetting.scope == scope
    ).first()
    is_machine = equipment in ("machine", "cable")
    if not setting:
        # "unset" — только для тренажёров с кластером: фронт спросит про
        # фиксированную шкалу при первом логировании веса (см. ТЗ Этапа 4)
        status = "unset" if (is_machine and equipment_cluster) else "standard"
        return {"kind": kind, "step_kg": default_step, "fixed_values": None, "status": status, "scope": scope}
    if setting.status == "custom_fixed":
        return {"kind": kind, "step_kg": None, "fixed_values": setting.fixed_values, "status": "custom_fixed", "scope": scope}
    return {"kind": kind, "step_kg": setting.step_kg or default_step, "fixed_values": None, "status": setting.status, "scope": scope}


PAIN_ZONE_RETURN_NOTICE_DAYS = 21  # сколько показывать подсказку "входи через сниженный вес" после возврата зоны


def _recent_pain_zone_returns(db: Session, user_id: int):
    """program_exercise_id -> {zone, suggested_weight} для недавних возвратов
    после снятия ограничения по зоне боли. Используется и для карточки
    (баннер), и для прайфилла полей подходов — без него поля показывали бы
    прежний рабочий вес, который баннер тут же советует не брать."""
    return_cutoff = datetime.utcnow() - timedelta(days=PAIN_ZONE_RETURN_NOTICE_DAYS)
    recent_returns = (db.query(PainZonePatch)
                       .filter(PainZonePatch.user_id == user_id, PainZonePatch.active == False,
                               PainZonePatch.reverted_at.isnot(None), PainZonePatch.reverted_at >= return_cutoff,
                               PainZonePatch.program_exercise_id.isnot(None))
                       .all())
    return {
        patch.program_exercise_id: {
            "zone": ZONE_LABELS_RU.get(patch.zone, patch.zone),
            "suggested_weight": patch.suggested_return_weight,
        }
        for patch in recent_returns
    }


def _determine_today_day_id(db: Session, user_id: int, days: list):
    """Программа не привязана к конкретным дням недели — пользователь сам
    решает, когда какой день делать. "Сегодняшний" день для авто-раскрытия
    аккордеона определяем так: если сегодня уже начали какой-то день — он и
    есть; иначе берём следующий по очереди после последнего ЗАВЕРШЁННОГО
    (с переходом в начало цикла), а если истории вообще нет — первый день."""
    if not days:
        return None
    today = datetime.now().strftime("%Y-%m-%d")
    day_ids = [d.id for d in days]
    today_session = (db.query(WorkoutSession)
                      .filter(WorkoutSession.user_id == user_id, WorkoutSession.log_date == today,
                              WorkoutSession.program_day_id.in_(day_ids))
                      .first())
    if today_session:
        return today_session.program_day_id
    last_completed = (db.query(WorkoutSession)
                       .filter(WorkoutSession.user_id == user_id, WorkoutSession.completed == True,
                               WorkoutSession.program_day_id.in_(day_ids))
                       .order_by(WorkoutSession.log_date.desc(), WorkoutSession.id.desc()).first())
    if not last_completed:
        return days[0].id
    by_id = {d.id: d for d in days}
    last_day = by_id.get(last_completed.program_day_id)
    if not last_day:
        return days[0].id
    next_index = (last_day.day_index + 1) % len(days)
    next_day = next((d for d in days if d.day_index == next_index), days[0])
    return next_day.id


def _serialize_program(db: Session, program: WorkoutProgram, user_id: int):
    # недавние возвраты после снятия ограничения по зоне — подсказка на
    # карточке "входи через сниженный вес", а не сразу прежний рабочий
    return_notice_by_pe = _recent_pain_zone_returns(db, user_id)

    days = (db.query(WorkoutProgramDay)
            .filter(WorkoutProgramDay.program_id == program.id)
            .order_by(WorkoutProgramDay.day_index).all())
    today_day_id = _determine_today_day_id(db, user_id, days)
    today = datetime.now().strftime("%Y-%m-%d")
    today_sessions = {
        s.program_day_id: s for s in db.query(WorkoutSession).filter(
            WorkoutSession.user_id == user_id, WorkoutSession.log_date == today,
            WorkoutSession.program_day_id.in_([d.id for d in days]),
        ).all()
    }
    result_days = []
    for day in days:
        pes = (db.query(WorkoutProgramExercise)
               .filter(WorkoutProgramExercise.day_id == day.id)
               .order_by(WorkoutProgramExercise.order).all())
        ex_by_id = {e.id: e for e in db.query(Exercise).filter(
            Exercise.id.in_([pe.exercise_id for pe in pes])
        ).all()}
        ex_list = []
        for pe in pes:
            e = ex_by_id.get(pe.exercise_id)
            if not e:
                continue
            progression = _resolve_progression(db, user_id, e.equipment, e.equipment_cluster)
            ex_list.append({
                "program_exercise_id": pe.id,
                "exercise_id": e.id, "name_ru": e.name_ru,
                "primary_muscles": e.primary_muscles, "secondary_muscles": e.secondary_muscles,
                "equipment_cluster": e.equipment_cluster,
                "equipment": e.equipment, "image": e.images[0] if e.images else None,
                "instructions_ru": e.instructions_ru, "youtube_id": e.youtube_id or None,
                "force": e.force,
                "sets": pe.target_sets, "rep_low": pe.rep_low, "rep_high": pe.rep_high,
                # специфическая разминка (TRAINER_PROMPT.md, блок "РАЗМИНКА") —
                # 1-2 разминочных подхода нужны для тяжёлых базовых движений со
                # штангой, не для тренажёров/гантель на изоляцию/bodyweight
                "needs_warmup": e.equipment == "barbell" and e.mechanic == "compound",
                "is_bonus": pe.is_bonus,
                "progression": progression,
                "return_notice": return_notice_by_pe.get(pe.id),
            })
        session = today_sessions.get(day.id)
        if session and session.completed:
            today_status = "completed"
        elif session and session.skipped:
            today_status = "skipped"
        else:
            today_status = None
        result_days.append({
            "id": day.id, "day_index": day.day_index, "day_type": day.day_type, "label": day.label,
            "exercises": ex_list, "is_today": day.id == today_day_id, "today_status": today_status,
        })

    profile = db.query(WorkoutProfile).filter(WorkoutProfile.user_id == user_id).first()
    mesocycle = _mesocycle_info(profile) if profile else {"week": 1, "length": MESOCYCLE_DEFAULT_WEEKS, "due": False}
    pain_zones = [{"zone": z, "label": ZONE_LABELS_RU.get(z, z)} for z in (profile.pain_zones or [])] if profile else []
    return {
        "id": program.id, "structure": program.structure, "days_per_week": program.days_per_week,
        "days": result_days, "mesocycle": mesocycle, "pain_zones": pain_zones,
    }


@app.get("/workout/api/program")
async def workout_get_program(user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    program = (db.query(WorkoutProgram)
               .filter(WorkoutProgram.user_id == user.id, WorkoutProgram.active == True)
               .first())
    if not program:
        return JSONResponse({"exists": False})
    data = _serialize_program(db, program, user.id)
    data["exists"] = True
    return JSONResponse(data)


@app.post("/workout/api/generate-program")
async def workout_generate_program(user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    profile = db.query(WorkoutProfile).filter(WorkoutProfile.user_id == user.id).first()
    if not profile or not profile.onboarded:
        return JSONResponse({"error": "Сначала заполни анкету"}, status_code=400)
    if not OPENROUTER_API_KEY:
        return JSONResponse({"error": "API ключ не настроен"}, status_code=500)

    structure, days = _program_structure(profile.days_per_week)
    pool = _exercise_pool(db, profile)
    if len(pool) < 10:
        return JSONResponse(
            {"error": "Недостаточно доступных упражнений — отметь больше оборудования в «Моём зале»"},
            status_code=400,
        )
    pool_ids = {e.id for e in pool}
    user_message = _build_program_user_message(profile, days, pool)

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "HTTP-Referer": "https://energydess.ru",
                    "X-Title": "EnergyDess Workout",
                },
                json={
                    "model": LETTER_MODEL,
                    "messages": [
                        {"role": "system", "content": TRAINER_SYSTEM_PROMPT},
                        {"role": "user", "content": user_message},
                    ],
                    "temperature": 0.4,
                    "max_tokens": 4000,
                },
                timeout=60.0,
            )
        if response.status_code != 200:
            return JSONResponse({"error": f"Ошибка OpenRouter: {response.text[:300]}"}, status_code=500)
        text = response.json()["choices"][0]["message"]["content"].strip()
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end == -1:
            return JSONResponse({"error": "ИИ вернул не JSON"}, status_code=500)
        parsed = _json.loads(text[start:end + 1])
    except httpx.TimeoutException:
        return JSONResponse({"error": "Превышено время ожидания. Попробуй ещё раз."}, status_code=504)
    except Exception as e:
        return JSONResponse({"error": f"Ошибка генерации: {e}"}, status_code=500)

    def _parse_exercise_entries(raw_list, seen, max_count):
        valid = []
        for ex in raw_list:
            eid = ex.get("exercise_id")
            if eid not in pool_ids or eid in seen:
                continue
            seen.add(eid)
            try:
                sets = max(2, min(5, int(ex.get("sets", 3))))
                rep_low = max(1, min(30, int(ex.get("rep_low", 8))))
                rep_high = max(rep_low, min(30, int(ex.get("rep_high", 12))))
            except (TypeError, ValueError):
                continue
            valid.append({"exercise_id": eid, "sets": sets, "rep_low": rep_low, "rep_high": rep_high})
            if len(valid) >= max_count:
                break
        return valid

    by_index = {d.get("day_index"): d for d in parsed.get("days", [])}
    built_days = []
    for d in days:
        day_data = by_index.get(d["index"]) or {}
        seen = set()
        # safety cap 6 — независимо от того, как ИИ интерпретировал лимит из
        # промпта, программа не должна разъехаться по объёму (см. ревью: была
        # утечка зон упора сверх лимита, чинится и тут, и в самом промпте)
        main_exercises = _parse_exercise_entries(day_data.get("exercises", []), seen, max_count=6)
        if len(main_exercises) < 3:
            return JSONResponse(
                {"error": f"ИИ собрал слишком мало упражнений для дня «{d['label']}» — попробуй сгенерировать ещё раз"},
                status_code=500,
            )
        bonus_exercises = _parse_exercise_entries(day_data.get("bonus_exercises", []), seen, max_count=2)
        built_days.append({**d, "exercises": main_exercises, "bonus_exercises": bonus_exercises})

    db.query(WorkoutProgram).filter(
        WorkoutProgram.user_id == user.id, WorkoutProgram.active == True
    ).update({"active": False})
    program = WorkoutProgram(user_id=user.id, structure=structure, days_per_week=profile.days_per_week, active=True)
    db.add(program)
    # новая программа — новый мезоцикл, счётчик недель с нуля
    profile.mesocycle_started_date = datetime.now().strftime("%Y-%m-%d")
    db.flush()
    for d in built_days:
        day_row = WorkoutProgramDay(program_id=program.id, day_index=d["index"], day_type=d["type"], label=d["label"])
        db.add(day_row)
        db.flush()
        order = 0
        for ex in d["exercises"]:
            db.add(WorkoutProgramExercise(
                day_id=day_row.id, exercise_id=ex["exercise_id"], order=order,
                target_sets=ex["sets"], rep_low=ex["rep_low"], rep_high=ex["rep_high"], is_bonus=False,
            ))
            order += 1
        for ex in d["bonus_exercises"]:
            db.add(WorkoutProgramExercise(
                day_id=day_row.id, exercise_id=ex["exercise_id"], order=order,
                target_sets=ex["sets"], rep_low=ex["rep_low"], rep_high=ex["rep_high"], is_bonus=True,
            ))
            order += 1
    db.commit()

    return JSONResponse(_serialize_program(db, program, user.id))


# ── Workout: логирование (подход / упражнение / тренировка) ─────────────────

def _progression_suggestion(db: Session, user_id: int, exercise_id: str,
                             pe: WorkoutProgramExercise, progression: dict, today: str):
    """Двойная прогрессия (TRAINER_PROMPT.md, ТЗ Этапа 5): если в последней
    ЗАВЕРШЁННОЙ тренировке (completed=True, не пропущена, не лёгкий день, и
    точно не сегодняшняя текущая открытая сессия) все подходы этого
    упражнения достигли верха диапазона повторов — предлагаем поднять вес.
    Чистая арифметика по set_log, без ИИ."""
    if progression["kind"] != "weight":
        return None

    last_session = (db.query(WorkoutSession)
                     .join(SetLog, SetLog.session_id == WorkoutSession.id)
                     .filter(WorkoutSession.user_id == user_id, SetLog.exercise_id == exercise_id,
                             WorkoutSession.skipped == False, WorkoutSession.is_light_day == False,
                             WorkoutSession.completed == True, WorkoutSession.log_date != today)
                     .order_by(WorkoutSession.log_date.desc()).first())
    if not last_session:
        return None

    sets = db.query(SetLog).filter(SetLog.session_id == last_session.id, SetLog.exercise_id == exercise_id).all()
    filled = [s for s in sets if s.reps is not None]
    if len(filled) < pe.target_sets or any(s.reps < pe.rep_high for s in filled):
        return None
    weights = [s.weight_kg for s in filled if s.weight_kg is not None]
    if not weights:
        return None
    last_weight = max(weights)

    if progression["status"] == "custom_fixed" and progression["fixed_values"]:
        higher = sorted(v for v in progression["fixed_values"] if v > last_weight)
        suggested = higher[0] if higher else None
    else:
        suggested = round(last_weight + (progression["step_kg"] or 0), 2)
    if not suggested:
        return None
    return {"ready": True, "last_weight": last_weight, "suggested_weight": suggested, "rep_low": pe.rep_low}


@app.get("/workout/api/day-state")
async def workout_day_state(program_day_id: int, log_date: str = None,
                             user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    today = log_date or datetime.now().strftime("%Y-%m-%d")

    day = db.query(WorkoutProgramDay).filter(WorkoutProgramDay.id == program_day_id).first()
    if not day:
        return JSONResponse({"error": "День программы не найден"}, status_code=404)
    pes = db.query(WorkoutProgramExercise).filter(WorkoutProgramExercise.day_id == program_day_id).all()
    profile = db.query(WorkoutProfile).filter(WorkoutProfile.user_id == user.id).first()

    swaps = {s.program_exercise_id: s.swapped_to_exercise_id for s in db.query(WorkoutExerciseSwap).filter(
        WorkoutExerciseSwap.user_id == user.id, WorkoutExerciseSwap.log_date == today,
        WorkoutExerciseSwap.program_exercise_id.in_([pe.id for pe in pes]),
    ).all()}
    all_needed_ids = {pe.exercise_id for pe in pes} | set(swaps.values())
    exercises_by_id = {e.id: e for e in db.query(Exercise).filter(Exercise.id.in_(all_needed_ids)).all()}
    return_notices = _recent_pain_zone_returns(db, user.id)

    today_session = db.query(WorkoutSession).filter(
        WorkoutSession.user_id == user.id, WorkoutSession.program_day_id == program_day_id,
        WorkoutSession.log_date == today,
    ).first()

    return_factor = None
    return_skip_reps = False
    if profile and (profile.return_plan_light_days_remaining or 0) > 0:
        return_factor = profile.return_plan_weight_factor
        return_skip_reps = profile.return_plan_status == "long"

    result = {}
    for pe in pes:
        default_eid = pe.exercise_id
        eid = swaps.get(pe.id, default_eid)  # активное упражнение на эту дату (с учётом замены)
        active_exercise = exercises_by_id.get(eid)

        today_sets, last_sets, last_date = [], [], None
        if today_session:
            rows = (db.query(SetLog)
                    .filter(SetLog.session_id == today_session.id, SetLog.exercise_id == eid)
                    .order_by(SetLog.set_index).all())
            today_sets = [{"set_index": r.set_index, "reps": r.reps, "weight_kg": r.weight_kg} for r in rows]

        # последняя ПРЕДЫДУЩАЯ тренировка с этим упражнением (не сегодняшняя)
        prev_session = (db.query(WorkoutSession)
                         .join(SetLog, SetLog.session_id == WorkoutSession.id)
                         .filter(WorkoutSession.user_id == user.id, SetLog.exercise_id == eid,
                                 WorkoutSession.log_date != today)
                         .order_by(WorkoutSession.log_date.desc()).first())
        if prev_session:
            rows = (db.query(SetLog)
                    .filter(SetLog.session_id == prev_session.id, SetLog.exercise_id == eid)
                    .order_by(SetLog.set_index).all())
            last_sets = [{"set_index": r.set_index, "reps": r.reps, "weight_kg": r.weight_kg} for r in rows]
            last_date = prev_session.log_date
            if return_factor is not None:
                # возвращение после перерыва — снижаем подсказанный вес, и для
                # долгого перерыва не тащим старые повторы (начать с низа диапазона)
                last_sets = [
                    {"set_index": s["set_index"],
                     "reps": None if return_skip_reps else s["reps"],
                     "weight_kg": round(s["weight_kg"] * return_factor, 1) if s["weight_kg"] is not None else None}
                    for s in last_sets
                ]

        return_notice = return_notices.get(pe.id)
        if return_notice and return_notice["suggested_weight"] is not None and last_sets:
            # поля должны показывать то, с чего реально начинать сегодня
            # (вес возврата), а не прежний рабочий — личный максимум при этом
            # остаётся отдельной справкой (personal_best_kg ниже), не пропадает
            last_sets = [
                {"set_index": s["set_index"], "reps": s["reps"], "weight_kg": return_notice["suggested_weight"]}
                for s in last_sets
            ]

        best = (db.query(SetLog.weight_kg)
                .filter(SetLog.user_id == user.id, SetLog.exercise_id == eid, SetLog.weight_kg.isnot(None))
                .order_by(SetLog.weight_kg.desc()).first())

        suggestion = None
        stuck = False
        active_display = None
        if active_exercise:
            progression = _resolve_progression(db, user.id, active_exercise.equipment, active_exercise.equipment_cluster)
            suggestion = _progression_suggestion(db, user.id, eid, pe, progression, today)
            stuck = _is_stuck(db, user.id, eid, pe)
            if eid != default_eid:
                active_display = {
                    "exercise_id": active_exercise.id, "name_ru": active_exercise.name_ru,
                    "primary_muscles": active_exercise.primary_muscles,
                    "secondary_muscles": active_exercise.secondary_muscles,
                    "equipment": active_exercise.equipment, "equipment_cluster": active_exercise.equipment_cluster,
                    "image": active_exercise.images[0] if active_exercise.images else None,
                    "instructions_ru": active_exercise.instructions_ru,
                    "youtube_id": active_exercise.youtube_id or None,
                    "force": active_exercise.force,
                    "needs_warmup": active_exercise.equipment == "barbell" and active_exercise.mechanic == "compound",
                    "progression": progression,
                }

        result[pe.id] = {
            "active_exercise_id": eid, "swapped": eid != default_eid, "active_display": active_display,
            "today_sets": today_sets, "last_sets": last_sets, "last_date": last_date,
            "personal_best_kg": best[0] if best else None,
            "progression_suggestion": suggestion, "stuck": stuck,
        }

    return JSONResponse({
        "log_date": today, "exercises": result,
        "skipped": bool(today_session and today_session.skipped),
        "skip_reason": today_session.skip_reason if today_session else None,
        "completed": bool(today_session and today_session.completed),
        "is_light_day": bool(today_session and today_session.is_light_day),
    })


def _get_or_create_session(db: Session, user_id: int, program_day_id: int, log_date: str) -> WorkoutSession:
    session = db.query(WorkoutSession).filter(
        WorkoutSession.user_id == user_id, WorkoutSession.program_day_id == program_day_id,
        WorkoutSession.log_date == log_date,
    ).first()
    if not session:
        session = WorkoutSession(user_id=user_id, program_day_id=program_day_id, log_date=log_date)
        # первые N тренировок после возвращения после перерыва — автоматически
        # лёгкие, прогрессия их игнорирует (см. блок "Возвращение после перерыва")
        profile = db.query(WorkoutProfile).filter(WorkoutProfile.user_id == user_id).first()
        if profile and (profile.return_plan_light_days_remaining or 0) > 0:
            session.is_light_day = True
            profile.return_plan_light_days_remaining -= 1
        db.add(session)
        db.flush()
    return session


@app.get("/workout/api/exercise-progress")
async def workout_exercise_progress(exercise_id: str, user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    # лучший вес за сессию (максимум среди подходов), не последний подход —
    # иначе график "пилит" вниз-вверх в рамках одной тренировки без смысла
    rows = (db.query(WorkoutSession.log_date, func.max(SetLog.weight_kg).label("best_weight"))
            .join(SetLog, SetLog.session_id == WorkoutSession.id)
            .filter(WorkoutSession.user_id == user.id, SetLog.exercise_id == exercise_id, SetLog.weight_kg.isnot(None))
            .group_by(WorkoutSession.log_date)
            .order_by(WorkoutSession.log_date)
            .all())
    points = [{"date": r.log_date, "weight_kg": r.best_weight} for r in rows]
    personal_best = max((p["weight_kg"] for p in points), default=None)
    return JSONResponse({"points": points, "personal_best_kg": personal_best})


@app.post("/workout/api/log-set")
async def workout_log_set(request: Request, user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    data = await request.json()
    program_day_id = data.get("program_day_id")
    exercise_id = data.get("exercise_id")
    log_date = data.get("log_date") or datetime.now().strftime("%Y-%m-%d")
    sets = data.get("sets", [])
    if not program_day_id or not exercise_id:
        return JSONResponse({"error": "Не указано упражнение"}, status_code=400)

    exercise = db.query(Exercise).filter(Exercise.id == exercise_id).first()
    if not exercise:
        return JSONResponse({"error": "Упражнение не найдено"}, status_code=404)

    session = _get_or_create_session(db, user.id, program_day_id, log_date)
    # незаполненный подход = не сделан, без валидации — просто не сохраняем
    # пустые строки (reps и weight оба пустые), но сохраняем, если хоть одно есть
    any_weight_logged = False
    for s in sets:
        reps = s.get("reps")
        weight_kg = s.get("weight_kg")
        if reps is None and weight_kg is None:
            continue
        set_index = s.get("set_index", 0)
        row = db.query(SetLog).filter(
            SetLog.session_id == session.id, SetLog.exercise_id == exercise_id, SetLog.set_index == set_index,
        ).first()
        if not row:
            row = SetLog(user_id=user.id, session_id=session.id, exercise_id=exercise_id, set_index=set_index)
            db.add(row)
        row.reps = reps
        row.weight_kg = weight_kg
        if weight_kg is not None:
            any_weight_logged = True
    db.commit()

    # "Это тренажёр с фиксированными блоками?" — спрашиваем один раз на
    # equipment_cluster, только при первом логировании ВЕСА на тренажёре
    ask_progression_setup = False
    if any_weight_logged and exercise.equipment in ("machine", "cable") and exercise.equipment_cluster:
        scope = _progression_scope_for(exercise.equipment, exercise.equipment_cluster)
        existing = db.query(ProgressionSetting).filter(
            ProgressionSetting.user_id == user.id, ProgressionSetting.scope == scope,
        ).first()
        ask_progression_setup = existing is None

    return JSONResponse({"ok": True, "ask_progression_setup": ask_progression_setup})


@app.post("/workout/api/skip-workout")
async def workout_skip(request: Request, user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    data = await request.json()
    program_day_id = data.get("program_day_id")
    log_date = data.get("log_date") or datetime.now().strftime("%Y-%m-%d")
    skip_reason = data.get("skip_reason")
    if skip_reason not in SKIP_REASONS:
        return JSONResponse({"error": "Некорректная причина"}, status_code=400)

    session = _get_or_create_session(db, user.id, program_day_id, log_date)
    session.skipped = True
    session.skip_reason = skip_reason
    db.commit()
    return JSONResponse({"ok": True})


@app.post("/workout/api/complete-workout")
async def workout_complete(request: Request, user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    data = await request.json()
    program_day_id = data.get("program_day_id")
    log_date = data.get("log_date") or datetime.now().strftime("%Y-%m-%d")

    session = _get_or_create_session(db, user.id, program_day_id, log_date)
    session.completed = True
    db.commit()
    return JSONResponse({"ok": True})


@app.post("/workout/api/set-light-day")
async def workout_set_light_day(request: Request, user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    data = await request.json()
    program_day_id = data.get("program_day_id")
    log_date = data.get("log_date") or datetime.now().strftime("%Y-%m-%d")
    is_light_day = bool(data.get("is_light_day", True))

    session = _get_or_create_session(db, user.id, program_day_id, log_date)
    session.is_light_day = is_light_day
    db.commit()
    return JSONResponse({"ok": True})


@app.get("/workout/api/progression-setting")
async def workout_get_progression(scope: str, user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    setting = db.query(ProgressionSetting).filter(
        ProgressionSetting.user_id == user.id, ProgressionSetting.scope == scope,
    ).first()
    if not setting:
        return JSONResponse({"exists": False, "scope": scope})
    return JSONResponse({
        "exists": True, "scope": scope, "status": setting.status,
        "step_kg": setting.step_kg, "fixed_values": setting.fixed_values,
    })


@app.post("/workout/api/progression-setting")
async def workout_save_progression(request: Request, user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    data = await request.json()
    scope = data.get("scope")
    status = data.get("status")
    if not scope or status not in ("standard", "custom_step", "custom_fixed", "pending_at_gym"):
        return JSONResponse({"error": "Некорректные данные"}, status_code=400)

    step_kg = None
    fixed_values = None
    if status == "custom_step":
        try:
            step_kg = float(data.get("step_kg"))
            if step_kg <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return JSONResponse({"error": "Некорректный шаг"}, status_code=400)
    elif status == "custom_fixed":
        try:
            fixed_values = sorted({float(v) for v in data.get("fixed_values", [])})
        except (TypeError, ValueError):
            return JSONResponse({"error": "Некорректный список значений"}, status_code=400)
        if len(fixed_values) < 2:
            return JSONResponse({"error": "Укажи хотя бы 2 значения шкалы"}, status_code=400)

    setting = db.query(ProgressionSetting).filter(
        ProgressionSetting.user_id == user.id, ProgressionSetting.scope == scope,
    ).first()
    if not setting:
        setting = ProgressionSetting(user_id=user.id, scope=scope)
        db.add(setting)
    setting.status = status
    setting.step_kg = step_kg
    setting.fixed_values = fixed_values
    db.commit()
    return JSONResponse({"ok": True})


# ── Workout: возвращение после перерыва ──────────────────────────────────────

@app.get("/workout/api/return-check")
async def workout_return_check(user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    profile = db.query(WorkoutProfile).filter(WorkoutProfile.user_id == user.id).first()
    if not profile or not profile.onboarded:
        return JSONResponse({"show": False})

    last_date = _last_activity_date(db, user.id)
    if not last_date:
        return JSONResponse({"show": False})
    today = datetime.now().strftime("%Y-%m-%d")
    gap_days = (datetime.strptime(today, "%Y-%m-%d") - datetime.strptime(last_date, "%Y-%m-%d")).days
    if gap_days < RETURN_GAP_DAYS:
        return JSONResponse({"show": False})
    # уже отвечали на этот конкретный перерыв?
    if profile.return_plan_applied_date and profile.return_plan_applied_date > last_date:
        return JSONResponse({"show": False})
    return JSONResponse({"show": True, "gap_days": gap_days, "last_activity_date": last_date})


@app.post("/workout/api/return-plan")
async def workout_return_plan(request: Request, user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    data = await request.json()
    choice = data.get("choice")
    if choice not in RETURN_PLAN_FACTORS:
        return JSONResponse({"error": "Некорректный выбор"}, status_code=400)
    profile = db.query(WorkoutProfile).filter(WorkoutProfile.user_id == user.id).first()
    if not profile:
        return JSONResponse({"error": "Сначала заполни анкету"}, status_code=400)

    profile.return_plan_status = choice
    profile.return_plan_applied_date = datetime.now().strftime("%Y-%m-%d")
    profile.return_plan_light_days_remaining = RETURN_PLAN_LIGHT_DAYS
    profile.return_plan_weight_factor = RETURN_PLAN_FACTORS[choice]
    db.commit()
    return JSONResponse({
        "ok": True, "weight_factor": profile.return_plan_weight_factor,
        "light_days": RETURN_PLAN_LIGHT_DAYS,
    })


# ── Workout: альтернативы и замена упражнения ────────────────────────────────

@app.get("/workout/api/alternatives")
async def workout_alternatives(program_exercise_id: int, user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    pe = db.query(WorkoutProgramExercise).filter(WorkoutProgramExercise.id == program_exercise_id).first()
    if not pe:
        return JSONResponse({"error": "Упражнение не найдено"}, status_code=404)
    exercise = db.query(Exercise).filter(Exercise.id == pe.exercise_id).first()
    profile = db.query(WorkoutProfile).filter(WorkoutProfile.user_id == user.id).first()
    if not exercise or not profile:
        return JSONResponse({"alternatives": []})

    day_exercise_ids = {row.exercise_id for row in db.query(WorkoutProgramExercise).filter(
        WorkoutProgramExercise.day_id == pe.day_id
    ).all()}
    alts = _find_alternatives(db, exercise, profile, day_exercise_ids)
    return JSONResponse({"alternatives": [
        {
            "exercise_id": a.id, "name_ru": a.name_ru, "image": a.images[0] if a.images else None,
            "equipment": a.equipment, "equipment_cluster": a.equipment_cluster, "primary_muscles": a.primary_muscles,
        }
        for a in alts
    ]})


@app.post("/workout/api/swap-exercise")
async def workout_swap_exercise(request: Request, user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    data = await request.json()
    program_exercise_id = data.get("program_exercise_id")
    log_date = data.get("log_date") or datetime.now().strftime("%Y-%m-%d")
    swapped_to = data.get("swapped_to_exercise_id")

    existing = db.query(WorkoutExerciseSwap).filter(
        WorkoutExerciseSwap.user_id == user.id, WorkoutExerciseSwap.program_exercise_id == program_exercise_id,
        WorkoutExerciseSwap.log_date == log_date,
    ).first()
    if not swapped_to:
        if existing:
            db.delete(existing)
            db.commit()
        return JSONResponse({"ok": True})

    if existing:
        existing.swapped_to_exercise_id = swapped_to
    else:
        db.add(WorkoutExerciseSwap(
            user_id=user.id, program_exercise_id=program_exercise_id,
            log_date=log_date, swapped_to_exercise_id=swapped_to,
        ))
    db.commit()
    return JSONResponse({"ok": True})


# ── Workout: мезоцикл — обновление программы (вариация, не пересборка) ──────

@app.post("/workout/api/refresh-program")
async def workout_refresh_program(user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    profile = db.query(WorkoutProfile).filter(WorkoutProfile.user_id == user.id).first()
    program = db.query(WorkoutProgram).filter(
        WorkoutProgram.user_id == user.id, WorkoutProgram.active == True
    ).first()
    if not profile or not program:
        return JSONResponse({"error": "Сначала сгенерируй программу"}, status_code=400)

    days = db.query(WorkoutProgramDay).filter(WorkoutProgramDay.program_id == program.id).all()
    changed = []
    for day in days:
        pes = (db.query(WorkoutProgramExercise)
               .filter(WorkoutProgramExercise.day_id == day.id, WorkoutProgramExercise.is_bonus == False)
               .all())
        if not pes:
            continue
        # предпочитаем заменить застрявшее упражнение; если такого нет — первое
        candidate = next((pe for pe in pes if _is_stuck(db, user.id, pe.exercise_id, pe)), pes[0])
        exercise = db.query(Exercise).filter(Exercise.id == candidate.exercise_id).first()
        if not exercise:
            continue
        day_exercise_ids = {p.exercise_id for p in pes}
        alts = _find_alternatives(db, exercise, profile, day_exercise_ids)
        if not alts:
            continue
        changed.append({"day_label": day.label, "from": exercise.name_ru, "to": alts[0].name_ru})
        candidate.exercise_id = alts[0].id

    profile.mesocycle_started_date = datetime.now().strftime("%Y-%m-%d")
    db.commit()
    data = _serialize_program(db, program, user.id)
    data["changes"] = changed
    return JSONResponse(data)


# ── Workout: чат-ассистент (Этап 6) ──────────────────────────────────────────
# Работает поверх базы упражнений — выбирает из неё, не выдумывает (см.
# контекст в системном промпте). Алгоритмически точные вещи (замена
# упражнения, исключение по зоне боли) считаются кодом, не ИИ — модель
# только определяет НАМЕРЕНИЕ пользователя и формирует action-блок,
# дальше работает та же детерминированная логика, что в Этапах 4-5.

_WORKOUT_ACTION_RE = re.compile(r"###WORKOUT_ACTION###\s*(\{.*?\})\s*###END_WORKOUT_ACTION###", re.S)

EQUIPMENT_LABELS_RU = {
    "barbell": "штанга", "e-z curl bar": "EZ-гриф", "dumbbell": "гантели", "kettlebells": "гири",
    "machine": "тренажёр", "cable": "тренажёр", "body only": "без инвентаря",
}
ZONE_LABELS_RU = {
    "knee": "колено", "lower_back": "поясница", "shoulder": "плечо", "elbow": "локоть", "neck": "шея",
}
DOCTOR_DISCLAIMER = ("Это фитнес-помощник, не медицинский сервис. Если боль сильная, не проходит "
                      "несколько дней или появилась резко после травмы — обратись к врачу, не жди улучшения от тренировок.")


def _extract_workout_action(text: str):
    m = _WORKOUT_ACTION_RE.search(text)
    if not m:
        return text.strip(), None
    try:
        action = _json.loads(m.group(1))
    except Exception:
        action = None
    return _WORKOUT_ACTION_RE.sub("", text).strip(), action


# ── Workout × Дневник питания (Этап 8) ──────────────────────────────────────
# Не дублируем данные — только читаем из существующих источников: WeightLog
# и NutritionProfile/FoodLog уже ведёт Дневник питания. Включено по умолчанию
# (use_nutrition_data), но никаких напоминаний "включи" — выключил и забыл.

WORKOUT_PROTEIN_FACTOR_HIGH = 1.8  # масса/рекомпозиция
WORKOUT_PROTEIN_FACTOR_STANDARD = 1.6  # остальные цели
WORKOUT_RECOMP_DEFICIT_WARNING_KCAL = 500


def _current_weight_kg(db: Session, user_id: int):
    """Текущий вес — последнее измерение из WeightLog (ручной ввод или умные
    весы), с откатом на статический вес из анкеты питания, если измерений
    ещё не было вообще."""
    latest = (db.query(WeightLog)
              .filter(WeightLog.user_id == user_id, WeightLog.weight_kg.isnot(None))
              .order_by(WeightLog.log_date.desc()).first())
    if latest:
        return latest.weight_kg
    nut_profile = db.query(NutritionProfile).filter(NutritionProfile.user_id == user_id).first()
    if nut_profile and nut_profile.weight_kg:
        return nut_profile.weight_kg
    return None


def _workout_nutrition_summary(db: Session, user: User, profile: WorkoutProfile):
    """Белок/калории на сегодня для индикатора на странице программы и для
    контекста чата. None — если интеграция выключена или нечем считать
    (нет ни одного измерения веса)."""
    if not profile.use_nutrition_data:
        return None
    weight = _current_weight_kg(db, user.id)
    if not weight:
        return None
    today = datetime.now().strftime("%Y-%m-%d")
    logs = db.query(FoodLog).filter(FoodLog.user_id == user.id, FoodLog.log_date == today).all()
    totals = _diary_totals(logs)["totals"]
    factor = WORKOUT_PROTEIN_FACTOR_HIGH if profile.goal in ("mass", "recomp") else WORKOUT_PROTEIN_FACTOR_STANDARD
    protein_target = round(weight * factor)
    trained_today = db.query(WorkoutSession).filter(
        WorkoutSession.user_id == user.id, WorkoutSession.log_date == today).first() is not None
    result = {
        "protein_eaten": totals["protein"], "protein_target": protein_target,
        "trained_today": trained_today, "calorie_deficit_warning": False,
    }
    nut_profile = db.query(NutritionProfile).filter(NutritionProfile.user_id == user.id).first()
    # дефицит считаем только если что-то уже залогировано сегодня — иначе
    # утром, пока человек ещё не открывал дневник, "дефицит" будет равен
    # всей дневной норме и предупреждение будет ложным
    if profile.goal == "recomp" and nut_profile and nut_profile.calorie_goal and logs:
        deficit = nut_profile.calorie_goal - totals["calories"]
        if deficit > WORKOUT_RECOMP_DEFICIT_WARNING_KCAL:
            result["calorie_deficit_warning"] = True
            result["deficit_kcal"] = round(deficit)
    return result


@app.get("/workout/api/nutrition-summary")
async def workout_nutrition_summary_api(user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    profile = db.query(WorkoutProfile).filter(WorkoutProfile.user_id == user.id).first()
    if not profile or not profile.onboarded:
        return JSONResponse({"enabled": False})
    summary = _workout_nutrition_summary(db, user, profile)
    if not summary:
        return JSONResponse({"enabled": False})
    summary["enabled"] = True
    return JSONResponse(summary)


@app.get("/workout/api/settings")
async def workout_get_settings(user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    profile = db.query(WorkoutProfile).filter(WorkoutProfile.user_id == user.id).first()
    return JSONResponse({"use_nutrition_data": profile.use_nutrition_data if profile else True})


@app.post("/workout/api/settings")
async def workout_save_settings(request: Request, user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    data = await request.json()
    profile = db.query(WorkoutProfile).filter(WorkoutProfile.user_id == user.id).first()
    if not profile:
        return JSONResponse({"error": "Сначала заполни анкету"}, status_code=400)
    if "use_nutrition_data" in data:
        profile.use_nutrition_data = bool(data["use_nutrition_data"])
    db.commit()
    return JSONResponse({"ok": True})


def _workout_chat_context(db: Session, user: User, focus_program_exercise_id=None) -> str:
    profile = db.query(WorkoutProfile).filter(WorkoutProfile.user_id == user.id).first()
    if not profile or not profile.onboarded:
        return "У пользователя пока нет заполненной анкеты тренировок."

    lines = [
        f"Цель: {GOAL_LABELS_RU.get(profile.goal, profile.goal)}",
        f"Уровень: {LEVEL_LABELS_RU.get(profile.level, profile.level)}",
        f"Дней в неделю: {profile.days_per_week}",
        f"Зоны упора: {', '.join(FOCUS_ZONE_LABELS_RU.get(z, z) for z in (profile.focus_zones or [])) or 'нет'}",
        f"Зоны боли/ограничения: {', '.join(ZONE_LABELS_RU.get(z, z) for z in (profile.pain_zones or [])) or 'нет'}",
        f"Мой зал (доступные тренажёры): {', '.join(profile.equipment or []) or ('дом без инвентаря' if profile.home_only else 'только базовое оборудование (штанга/гантели/турник)')}",
    ]

    program = db.query(WorkoutProgram).filter(WorkoutProgram.user_id == user.id, WorkoutProgram.active == True).first()
    if program:
        days = db.query(WorkoutProgramDay).filter(WorkoutProgramDay.program_id == program.id).order_by(WorkoutProgramDay.day_index).all()
        lines.append("\nТекущая программа:")
        for day in days:
            pes = db.query(WorkoutProgramExercise).filter(WorkoutProgramExercise.day_id == day.id).order_by(WorkoutProgramExercise.order).all()
            ex_by_id = {e.id: e for e in db.query(Exercise).filter(Exercise.id.in_([pe.exercise_id for pe in pes])).all()}
            lines.append(f"  {day.label}:")
            for pe in pes:
                e = ex_by_id.get(pe.exercise_id)
                if not e:
                    continue
                tag = " [program_exercise_id=" + str(pe.id) + "]"
                bonus = " (опционально)" if pe.is_bonus else ""
                lines.append(f"    - {e.name_ru}{bonus} — {pe.target_sets}x{pe.rep_low}-{pe.rep_high}{tag}")
        if focus_program_exercise_id:
            pe = db.query(WorkoutProgramExercise).filter(WorkoutProgramExercise.id == focus_program_exercise_id).first()
            if pe:
                e = db.query(Exercise).filter(Exercise.id == pe.exercise_id).first()
                if e:
                    lines.append(f"\nПользователь открыл чат из карточки упражнения «{e.name_ru}» (program_exercise_id={pe.id}) — если просит заменить/убрать «это» упражнение, имеет в виду именно его.")
    else:
        lines.append("\nПрограмма ещё не сгенерирована.")

    last_weight = db.query(WeightLog).filter(WeightLog.user_id == user.id).order_by(WeightLog.log_date.desc()).first()
    if last_weight and last_weight.source == "zepp":
        parts = [f"{last_weight.weight_kg} кг"]
        if last_weight.body_fat_pct:
            parts.append(f"жир {last_weight.body_fat_pct}%")
        if last_weight.muscle_rate_pct:
            parts.append(f"мышцы {last_weight.muscle_rate_pct}%")
        lines.append(f"\nПоследнее измерение с умных весов ({last_weight.log_date}): {', '.join(parts)}")

    nutrition_summary = _workout_nutrition_summary(db, user, profile)
    if nutrition_summary:
        lines.append(f"\nБелок сегодня (Дневник питания): {nutrition_summary['protein_eaten']} г из {nutrition_summary['protein_target']} г нужных")
        if nutrition_summary["calorie_deficit_warning"]:
            lines.append(f"Внимание: сегодня дефицит калорий ~{nutrition_summary['deficit_kcal']} ккал — для цели «рекомпозиция» это много, мышцам может не хватить энергии на восстановление. Если уместно, мягко посоветуй добрать белок.")
    elif not profile.use_nutrition_data:
        lines.append("\n(Пользователь СОЗНАТЕЛЬНО выключил интеграцию с Дневником питания в настройках — это его осознанный выбор, не ошибка и не то, что надо исправить. НЕ упоминай белок/калории/дефицит. Если спросят про питание — ответь только, что не видишь данных по питанию, БЕЗ единого слова про включение/настройки/функцию — никаких 'можешь включить', 'если хочешь, включи' и т.п. Просто переведи разговор на тренировки.)")

    return "\n".join(lines)


WORKOUT_CHAT_SYSTEM = """Ты — AI-ассистент персонального тренера в фитнес-приложении. Отвечай кратко (2-5 предложений), просто, без терминов вроде "прогрессивная перегрузка", "гипертрофия", "мезоцикл" — объясняй как тренер другу, не как учебник.

ЕСЛИ в контексте ниже сказано, что интеграция с Дневником питания выключена — это жёсткое правило без исключений: ни слова про включение/настройку этой функции, даже если пользователь сам спрашивает про питание или явно просит совета по калориям/белку. Просто скажи, что не видишь данных, и переведи на тренировки.

Контекст пользователя:
{context}

У ТЕБЯ ЕСТЬ ДЕЙСТВИЯ — выбирай упражнения ТОЛЬКО из программы в контексте выше, никогда не выдумывай. Чтобы выполнить действие, добавь в конце ответа блок (пользователь его не увидит как текст, увидит результат):
###WORKOUT_ACTION###
{{"action": "...", ...параметры...}}
###END_WORKOUT_ACTION###

ВАЖНО про слова "это"/"это упражнение"/"оно": если в контексте выше есть строка "Пользователь открыл чат из карточки упражнения «...» (program_exercise_id=X)" — это и есть то, что имеется в виду под "это", СЕЙЧАС, в этом сообщении. Не путай с упражнениями, которые обсуждались РАНЕЕ в истории этой переписки (другая карточка, другая сессия) — ориентируйся только на актуальный контекст выше, а не на прошлые сообщения.

Доступные действия:
1. swap_exercise — заменить конкретное упражнение на аналог с теми же мышцами. {{"action":"swap_exercise","program_exercise_id":<id из контекста, см. правило про "это" выше>}}. Используй, когда просят заменить/убрать/не любят конкретное упражнение.
2. set_pain_zone — отметить зону как ограничение; система САМА сместит нагрузку на безопасные альтернативы для этой зоны (не убирает тренировку, а заменяет упражнения — например, при боли в колене заменяет присед/выпады на ягодичный мостик/RDL/гиперэкстензию, день ног не пропадает). {{"action":"set_pain_zone","zone":"knee|lower_back|shoulder|elbow|neck"}}. Когда вызываешь это действие, НЕ выдумывай сам, что на что заменится — просто скажи, что подбираешь замену, конкретику возьми из structured-результата, который вернёт система (он придёт отдельно и пользователь увидит точный список).
3. set_focus_zones — сделать акцент на зоне (не более 2 одновременно, заменяет старый список). {{"action":"set_focus_zones","zones":["arms|shoulders|chest|back|legs|abs|glutes", ...]}}. Используй для "хочу упор на руки/ноги/пресс" и т.п.
4. remove_equipment — убрать тренажёр из доступного оборудования (точная подпись из "Мой зал" в контексте) и заменить упражнения на нём. {{"action":"remove_equipment","cluster_label":"<точная строка из контекста>"}}. Используй для "у меня нет такого тренажёра".
5. none — без действия, просто разговор (в том числе для технических советов при острой боли, см. ниже — это НЕ ошибка, а намеренное поведение). Используй это же действие, если пользователь спрашивает "какие у меня сейчас ограничения/зоны боли" — просто перечисли зоны из контекста выше, ничего не меняя.
6. clear_pain_zone — снять ограничение по зоне и аккуратно вернуть упражнения, которые были заменены/убраны из-за неё (не сразу с прежней нагрузкой — см. раздел Г ниже). {{"action":"clear_pain_zone","zone":"knee|lower_back|shoulder|elbow|neck"}}. Используй, когда пользователь говорит, что зона прошла/восстановилась — и только если эта зона сейчас реально в списке ограничений в контексте (если её там нет — нечего снимать, скажи об этом).

=== БОЛЬ — СНАЧАЛА ОПРЕДЕЛИ ТИП, ПОТОМ РЕШАЙ, КАКОЕ ACTION ВЫЗЫВАТЬ ===
Ты не диагностируешь и не лечишь — только базовая техника и решение "продолжать с поправками / заменить / к врачу". При любой неуверенности или повторе боли — направляй к врачу, а не углубляйся в догадки о причине.

А) КРАСНЫЕ ФЛАГИ — переводи сюда ТОЛЬКО если пользователь явно описал хотя бы один из конкретных признаков: боль отдаёт/простреливает в руку или ногу, онемение/покалывание/слабость в конечности, не может разогнуться или согнуть сустав совсем. Просто "резко", "сильно", "остро", "кольнуло" — это НЕ красный флаг сами по себе, это пункт Б ниже. Не повышай тревожность без явного указания на один из перечисленных признаков.
   → action: "none" (или дополнительно "set_pain_zone" как мера предосторожности, на твой выбор, но это не обязательно). В ТЕКСТЕ — только "стоп, прекрати упражнение и обратись к врачу/травматологу как можно скорее". БЕЗ технических советов, БЕЗ попыток "поправить" упражнение — это не та ситуация, где помогает техника.

Б) ОСТРАЯ БОЛЬ ВО ВРЕМЯ ПОДХОДА — это ДЕФОЛТНАЯ ветка для любой боли "прямо сейчас/только что", если нет признаков из пункта А выше (резко, сильно, кольнуло, потянул, заболело на конкретном подходе — без признаков пункта А). Не заявленное ранее ограничение, а случившееся прямо на тренировке. По умолчанию action: "none" — НЕ вызывай set_pain_zone сразу, чаще всего дело в технике или весе, а не в противопоказании к упражнению. Вместо этого:
   - скажи остановить текущий подход, не продолжать через боль;
   - задай 1-2 уточняющих вопроса (на каком движении/в какой фазе стрельнуло, с каким весом работал);
   - дай 2-3 коротких чек-поинта по технике под конкретное упражнение (поясница: нейтральная спина, брейсинг кора, без рывка, таз не подворачивается; колено: колено не уходит далеко вперёд за носок, без рывка вниз; плечо: лопатки сведены и слегка опущены, локоть не заводится за линию корпуса) — адаптируй под движение, которое называет пользователь;
   - предложи снизить вес и заново проверить технику на лёгком;
   - обязательно добавь: "если боль повторится даже на лёгком весе с правильной техникой — напиши, тогда заменим упражнение, и если не пройдёт — обратись к врачу".
   Вызывай set_pain_zone в этой ветке ТОЛЬКО если из истории переписки видно, что это уже повторное сообщение о той же боли после твоего совета про технику/лёгкий вес — то есть боль не разовая, а повторяющаяся.

В) ЗАЯВЛЕННОЕ ОГРАНИЧЕНИЕ/ХРОНИКА ("у меня больное колено", "грыжа в пояснице", "старая травма плеча" — жалоба не привязана к конкретному текущему подходу): → action: "set_pain_zone" сразу. В тексте скажи, что подбираешь замену (без выдумывания конкретики, см. пункт 2 выше), и добавь: "если и новый вариант будет отдавать болью — убери его и обратись к врачу".

=== ЗОНА ВОССТАНОВИЛАСЬ — ВОЗВРАТ ДОЛЖЕН БЫТЬ ОСТОРОЖНЫМ, НЕ ОДНОМОМЕНТНЫМ ===
Г) Пользователь говорит, что зона прошла ("колено больше не болит", "поясница прошла", "плечо восстановилось") — ПЕРЕД вызовом clear_pain_zone уточни через текст ответа, что зона ПОЛНОСТЬЮ без боли, а не "вроде получше" (если из сообщения уже однозначно ясно, что полностью прошло и давно — можно не переспрашивать и сразу действовать). Когда вызываешь clear_pain_zone:
   - не обещай возврат к прежнему рабочему весу — конкретную сниженную цифру даст structured-результат (если есть история весов), не выдумывай её сам;
   - словами объясни идею: возвращаемся осторожно, первые тренировки — сниженный вес (заметно меньше прежнего), затем поднимаем обратно за несколько тренировок, а не сразу на максимум;
   - добавь: на первых подходах внимательно следи за зоной; если боль вернётся даже на сниженном весе — сразу стоп, и если повторится — обратись к врачу. Это не "забыли и снова всё как было", а контролируемый возврат под наблюдением за симптомом.

Если пользователь прислал фото тренажёра, его описание придёт отдельным сообщением — прокомментируй что это и для чего используется, БЕЗ action-блока (добавление в "Мой зал" по фото — отдельная кнопка, не твоя забота)."""


def _find_pain_zone_redirect(db: Session, profile: WorkoutProfile, zone: str, exclude_exercise_ids, limit: int = 1):
    """Целевой поиск безопасной замены для конкретной зоны боли (например,
    для колена — тазобедренный шарнир: ягодицы/бицепс бедра без сгибания и
    осевой нагрузки на сустав), а не общий "та же мышца", которой в пуле
    часто и нет. См. PAIN_ZONE_REDIRECT_MUSCLES."""
    redirect_muscles = PAIN_ZONE_REDIRECT_MUSCLES.get(zone, set())
    if not redirect_muscles:
        return []
    avoid_muscles = PAIN_ZONE_MUSCLES.get(zone, set()) - redirect_muscles
    avoid_keywords = PAIN_ZONE_REDIRECT_AVOID_NAME_KEYWORDS.get(zone, [])
    q = db.query(Exercise).filter(
        Exercise.category.in_(PAIN_ZONE_REDIRECT_CATEGORIES),
        Exercise.level.in_(LEVEL_INCLUDES.get(profile.level, ["beginner"])),
    )
    if profile.home_only:
        rows = q.filter(Exercise.equipment.in_(ALWAYS_AVAILABLE_EQUIPMENT)).all()
    else:
        rows = q.filter(or_(
            Exercise.equipment.in_(ALWAYS_AVAILABLE_EQUIPMENT),
            Exercise.equipment_cluster.in_(profile.equipment or []),
        )).all()

    prefer_keywords = PAIN_ZONE_REDIRECT_PREFER_KEYWORDS.get(zone, [])
    candidates = []
    for e in rows:
        if e.id in exclude_exercise_ids:
            continue
        if not (redirect_muscles & set(e.primary_muscles or [])):
            continue
        muscles_all = set(e.primary_muscles or []) | set(e.secondary_muscles or [])
        if avoid_muscles & muscles_all:
            continue  # замена не должна сама грузить проблемный сустав
        name_lower = (e.name_ru or "").lower()
        if any(kw in name_lower for kw in avoid_keywords):
            continue
        is_preferred = any(kw in name_lower for kw in prefer_keywords)
        candidates.append((is_preferred, e))
    # сначала канонические безопасные движения (ягодичный мост, РДТ и т.п.),
    # иначе можно словить случайный вариант с подходящей мышцей, но рискованной
    # механикой (взрывной/баллистический и т.п.), который не попал в avoid-лист
    candidates.sort(key=lambda t: t[0], reverse=True)
    return [e for _, e in candidates[:limit]]


def _patch_program_for_pain_zone(db: Session, user: User, profile: WorkoutProfile, zone: str):
    program = db.query(WorkoutProgram).filter(WorkoutProgram.user_id == user.id, WorkoutProgram.active == True).first()
    if not program:
        return [], {}
    excluded_muscles = PAIN_ZONE_MUSCLES.get(zone, set())
    if not excluded_muscles:
        return [], {}
    changes = []
    days = db.query(WorkoutProgramDay).filter(WorkoutProgramDay.program_id == program.id).all()
    for day in days:
        pes = db.query(WorkoutProgramExercise).filter(WorkoutProgramExercise.day_id == day.id).all()
        existing_ids = {pe.exercise_id for pe in pes}
        for pe in pes:
            exercise = db.query(Exercise).filter(Exercise.id == pe.exercise_id).first()
            if not exercise:
                continue
            hits = excluded_muscles & (set(exercise.primary_muscles or []) | set(exercise.secondary_muscles or []))
            if not hits:
                continue
            # 1. сначала пробуем целевой редирект (сместить нагрузку на
            #    безопасное движение для этой зоны — например, тазобедренный
            #    шарнир вместо приседа при боли в колене)
            redirect = _find_pain_zone_redirect(db, profile, zone, existing_ids)
            replacement = redirect[0] if redirect else None
            # 2. иначе — обычный поиск аналога с той же основной мышцей
            if not replacement:
                alts = _find_alternatives(db, exercise, profile, existing_ids)
                replacement = alts[0] if alts else None
            # сохраняем оригинал ДО мутации — иначе при выздоровлении
            # (clear_pain_zone) нечем будет вернуть исходное упражнение
            patch = PainZonePatch(
                user_id=user.id, zone=zone, program_id=program.id, day_id=day.id,
                order_in_day=pe.order, original_exercise_id=exercise.id,
                original_target_sets=pe.target_sets, original_rep_low=pe.rep_low,
                original_rep_high=pe.rep_high, original_is_bonus=pe.is_bonus,
            )
            if replacement:
                changes.append({"day": day.label, "from": exercise.name_ru, "to": replacement.name_ru})
                existing_ids.discard(pe.exercise_id)
                existing_ids.add(replacement.id)
                patch.program_exercise_id = pe.id
                patch.applied_exercise_id = replacement.id
                pe.exercise_id = replacement.id
            else:
                # основная мышца упражнения сама входит в зону боли, и для
                # неё нет ни редиректа, ни обычного аналога — убираем совсем,
                # а не оставляем нагружающее упражнение в программе молча
                changes.append({"day": day.label, "from": exercise.name_ru, "removed": True})
                db.delete(pe)
            db.add(patch)
    db.commit()
    day_counts = {day.label: db.query(WorkoutProgramExercise).filter(WorkoutProgramExercise.day_id == day.id).count() for day in days}
    return changes, day_counts


def _suggested_return_weight(db: Session, user: User, original_exercise_id: str):
    """После снятия ограничения возвращаем упражнение не с прежним рабочим
    весом, а с ~55% от последнего залогированного — резкий возврат к
    нагрузке после боли сам по себе риск повторной травмы."""
    logs = (db.query(SetLog)
            .filter(SetLog.user_id == user.id, SetLog.exercise_id == original_exercise_id, SetLog.weight_kg.isnot(None))
            .order_by(SetLog.created_at.desc()).limit(15).all())
    weights = [l.weight_kg for l in logs if l.weight_kg]
    if not weights:
        return None
    last_working_weight = max(weights)
    if last_working_weight <= 0:
        return None
    return round(last_working_weight * 0.55, 1)


def _revert_pain_zone_patches(db: Session, user: User, profile: WorkoutProfile, zone: str):
    """Снятие ограничения по зоне — возвращает исходные упражнения, убранные
    или заменённые из-за этой зоны (см. _patch_program_for_pain_zone), с
    подсказкой по сниженному весу на вход (а не сразу прежний рабочий)."""
    patches = (db.query(PainZonePatch)
               .filter(PainZonePatch.user_id == user.id, PainZonePatch.zone == zone, PainZonePatch.active == True)
               .all())
    if not patches:
        return [], {}
    days_cache = {}
    changes = []
    touched_day_ids = set()
    now = datetime.utcnow()
    for patch in patches:
        original = db.query(Exercise).filter(Exercise.id == patch.original_exercise_id).first()
        if not original:
            patch.active = False
            patch.reverted_at = now
            continue
        day = days_cache.get(patch.day_id)
        if day is None:
            day = db.query(WorkoutProgramDay).filter(WorkoutProgramDay.id == patch.day_id).first()
            days_cache[patch.day_id] = day
        day_label = day.label if day else "?"
        suggested_weight = _suggested_return_weight(db, user, patch.original_exercise_id)

        if patch.program_exercise_id:
            pe = db.query(WorkoutProgramExercise).filter(WorkoutProgramExercise.id == patch.program_exercise_id).first()
            if pe:
                applied = db.query(Exercise).filter(Exercise.id == pe.exercise_id).first()
                changes.append({
                    "day": day_label, "from": applied.name_ru if applied else "?", "to": original.name_ru,
                    "restored": True, "suggested_weight": suggested_weight,
                })
                pe.exercise_id = patch.original_exercise_id
                touched_day_ids.add(patch.day_id)
        else:
            new_pe = WorkoutProgramExercise(
                day_id=patch.day_id, exercise_id=patch.original_exercise_id, order=patch.order_in_day,
                target_sets=patch.original_target_sets, rep_low=patch.original_rep_low,
                rep_high=patch.original_rep_high, is_bonus=patch.original_is_bonus,
            )
            db.add(new_pe)
            db.flush()
            changes.append({
                "day": day_label, "from": "убрано ранее", "to": original.name_ru,
                "restored": True, "suggested_weight": suggested_weight,
            })
            patch.program_exercise_id = new_pe.id
            touched_day_ids.add(patch.day_id)
        patch.active = False
        patch.reverted_at = now
        patch.suggested_return_weight = suggested_weight
    db.commit()
    day_counts = {}
    for day_id in touched_day_ids:
        day = days_cache.get(day_id)
        if day:
            day_counts[day.label] = db.query(WorkoutProgramExercise).filter(WorkoutProgramExercise.day_id == day_id).count()
    return changes, day_counts


def _patch_program_remove_equipment(db: Session, user: User, profile: WorkoutProfile, cluster_label: str):
    program = db.query(WorkoutProgram).filter(WorkoutProgram.user_id == user.id, WorkoutProgram.active == True).first()
    if not program:
        return [], {}
    changes = []
    days = db.query(WorkoutProgramDay).filter(WorkoutProgramDay.program_id == program.id).all()
    for day in days:
        pes = db.query(WorkoutProgramExercise).filter(WorkoutProgramExercise.day_id == day.id).all()
        existing_ids = {pe.exercise_id for pe in pes}
        for pe in pes:
            exercise = db.query(Exercise).filter(Exercise.id == pe.exercise_id).first()
            if not exercise or exercise.equipment_cluster != cluster_label:
                continue
            alts = _find_alternatives(db, exercise, profile, existing_ids)
            if alts:
                changes.append({"day": day.label, "from": exercise.name_ru, "to": alts[0].name_ru})
                existing_ids.discard(pe.exercise_id)
                existing_ids.add(alts[0].id)
                pe.exercise_id = alts[0].id
            else:
                changes.append({"day": day.label, "from": exercise.name_ru, "removed": True})
                db.delete(pe)
    db.commit()
    day_counts = {day.label: db.query(WorkoutProgramExercise).filter(WorkoutProgramExercise.day_id == day.id).count() for day in days}
    return changes, day_counts


def _shorten_today_guidance(db: Session, user: User) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    program = db.query(WorkoutProgram).filter(WorkoutProgram.user_id == user.id, WorkoutProgram.active == True).first()
    if not program:
        return "Программа ещё не сгенерирована."
    # без привязки к конкретному дню недели берём первый день программы как пример
    day = db.query(WorkoutProgramDay).filter(WorkoutProgramDay.program_id == program.id).order_by(WorkoutProgramDay.day_index).first()
    if not day:
        return "В программе нет дней."
    pes = db.query(WorkoutProgramExercise).filter(WorkoutProgramExercise.day_id == day.id, WorkoutProgramExercise.is_bonus == False).order_by(WorkoutProgramExercise.order).all()
    ex_by_id = {e.id: e for e in db.query(Exercise).filter(Exercise.id.in_([pe.exercise_id for pe in pes])).all()}
    keep, skip = [], []
    for pe in pes:
        e = ex_by_id.get(pe.exercise_id)
        if not e:
            continue
        (keep if e.mechanic == "compound" else skip).append(e.name_ru)
    return f"Если мало времени — сделай только базовые: {', '.join(keep) or 'нет базовых в этом дне'}. Изоляцию можно пропустить сегодня: {', '.join(skip) or 'её и нет'}. Это не повредит прогрессу."


@app.get("/workout/api/chat-history")
async def workout_chat_history(user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    msgs = db.query(ChatMessage).filter(ChatMessage.user_id == user.id, ChatMessage.tool == "workout").order_by(
        ChatMessage.created_at).limit(100).all()
    return JSONResponse({"messages": [{"role": m.role, "content": m.content, "image": m.image_data} for m in msgs]})


@app.post("/workout/api/chat")
async def workout_chat(request: Request, user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    data = await request.json()
    msg = (data.get("message") or "").strip()
    focus_pe_id = data.get("program_exercise_id")
    if not msg:
        return JSONResponse({"error": "Пустое сообщение"}, status_code=400)
    if not OPENROUTER_API_KEY:
        return JSONResponse({"error": "API ключ не настроен"}, status_code=500)

    history = db.query(ChatMessage).filter(ChatMessage.user_id == user.id, ChatMessage.tool == "workout").order_by(
        ChatMessage.created_at).limit(30).all()
    context = _workout_chat_context(db, user, focus_pe_id)
    system = WORKOUT_CHAT_SYSTEM.format(context=context)

    api_messages = ([{"role": "system", "content": system}]
                     + [{"role": h.role, "content": h.content} for h in history]
                     + [{"role": "user", "content": msg}])

    db.add(ChatMessage(user_id=user.id, role="user", content=msg, tool="workout"))
    db.commit()

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}",
                         "HTTP-Referer": "https://energydess.ru", "X-Title": "EnergyDess Workout"},
                json={"model": LETTER_MODEL, "messages": api_messages, "temperature": 0.4, "max_tokens": 500},
                timeout=30.0,
            )
        reply = resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

    reply, action = _extract_workout_action(reply)
    result = None
    profile = db.query(WorkoutProfile).filter(WorkoutProfile.user_id == user.id).first()

    if action and profile:
        act = action.get("action")
        try:
            if act == "swap_exercise":
                # если чат открыт из конкретной карточки — это и есть "это
                # упражнение", независимо от того, что модель вернула в
                # action (история переписки может содержать другое
                # упражнение из прошлой сессии, и модель иногда путает)
                target_pe_id = focus_pe_id or action.get("program_exercise_id")
                pe = db.query(WorkoutProgramExercise).filter(WorkoutProgramExercise.id == target_pe_id).first()
                if pe:
                    day = db.query(WorkoutProgramDay).filter(WorkoutProgramDay.id == pe.day_id).first()
                    program = db.query(WorkoutProgram).filter(WorkoutProgram.id == day.program_id).first() if day else None
                    if program and program.user_id == user.id:
                        exercise = db.query(Exercise).filter(Exercise.id == pe.exercise_id).first()
                        day_ids = {p.exercise_id for p in db.query(WorkoutProgramExercise).filter(WorkoutProgramExercise.day_id == pe.day_id).all()}
                        alts = _find_alternatives(db, exercise, profile, day_ids) if exercise else []
                        if alts:
                            today = datetime.now().strftime("%Y-%m-%d")
                            existing = db.query(WorkoutExerciseSwap).filter(
                                WorkoutExerciseSwap.user_id == user.id, WorkoutExerciseSwap.program_exercise_id == pe.id,
                                WorkoutExerciseSwap.log_date == today,
                            ).first()
                            if existing:
                                existing.swapped_to_exercise_id = alts[0].id
                            else:
                                db.add(WorkoutExerciseSwap(user_id=user.id, program_exercise_id=pe.id, log_date=today, swapped_to_exercise_id=alts[0].id))
                            db.commit()
                            result = {"type": "swap_exercise", "from": exercise.name_ru, "to": alts[0].name_ru}

            elif act == "set_pain_zone":
                zone = action.get("zone")
                if zone in WORKOUT_PAIN_ZONES:
                    zones = list(profile.pain_zones or [])
                    if zone not in zones:
                        zones.append(zone)
                        profile.pain_zones = zones
                        db.commit()
                    changes, day_counts = _patch_program_for_pain_zone(db, user, profile, zone)
                    result = {"type": "set_pain_zone", "zone": ZONE_LABELS_RU.get(zone, zone), "changes": changes, "day_counts": day_counts}

            elif act == "clear_pain_zone":
                zone = action.get("zone")
                if zone in WORKOUT_PAIN_ZONES and zone in (profile.pain_zones or []):
                    profile.pain_zones = [z for z in profile.pain_zones if z != zone]
                    db.commit()
                    changes, day_counts = _revert_pain_zone_patches(db, user, profile, zone)
                    # восстановленные упражнения могут конфликтовать с ДРУГИМИ
                    # зонами, которые всё ещё активны — пере-патчим их же
                    # логикой, а не оставляем нагружающее упражнение молча
                    for other_zone in (profile.pain_zones or []):
                        more_changes, more_counts = _patch_program_for_pain_zone(db, user, profile, other_zone)
                        changes += more_changes
                        day_counts.update(more_counts)
                    result = {"type": "clear_pain_zone", "zone": ZONE_LABELS_RU.get(zone, zone), "changes": changes, "day_counts": day_counts}
                elif zone in WORKOUT_PAIN_ZONES:
                    # зона уже не в ограничениях (например, повторный вызов в
                    # той же беседе) — явно сообщаем, а не молчим result=None,
                    # иначе модель решит, что действие не выполнилось вообще
                    result = {"type": "clear_pain_zone", "zone": ZONE_LABELS_RU.get(zone, zone), "already_cleared": True}

            elif act == "set_focus_zones":
                zones = [z for z in (action.get("zones") or []) if z in WORKOUT_FOCUS_ZONES][:2]
                if zones:
                    profile.focus_zones = zones
                    db.commit()
                    result = {"type": "set_focus_zones", "zones": [FOCUS_ZONE_LABELS_RU.get(z, z) for z in zones]}

            elif act == "remove_equipment":
                cluster = action.get("cluster_label")
                if cluster and cluster in (profile.equipment or []):
                    profile.equipment = [c for c in profile.equipment if c != cluster]
                    db.commit()
                    changes, day_counts = _patch_program_remove_equipment(db, user, profile, cluster)
                    result = {"type": "remove_equipment", "cluster": cluster, "changes": changes, "day_counts": day_counts}

            elif act == "shorten_today":
                result = {"type": "shorten_today", "guidance": _shorten_today_guidance(db, user)}
        except Exception as e:
            result = {"type": "error", "error": str(e)}

    db.add(ChatMessage(user_id=user.id, role="assistant", content=reply, tool="workout"))
    db.commit()
    return JSONResponse({"reply": reply, "result": result})


@app.post("/workout/api/chat-photo")
async def workout_chat_photo(file: UploadFile = File(...), message: str = Form(""),
                              user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    if not OPENROUTER_API_KEY:
        return JSONResponse({"error": "API ключ не настроен"}, status_code=500)
    content = await file.read()
    if not content:
        return JSONResponse({"error": "Пустой файл"}, status_code=400)
    b64 = base64.b64encode(content).decode()
    mime = _image_mime(file)
    thumb = _make_thumbnail(content)

    db.add(ChatMessage(user_id=user.id, role="user", content=message or "[фото тренажёра]", image_data=thumb, tool="workout"))
    db.commit()

    cluster_labels = {item["label"] for item in _workout_equipment_checklist(db)}
    cluster_list = "\n".join(f"- {label}" for label in sorted(cluster_labels))
    prompt = (
        "Это фото тренажёра в зале. Определи, какой из списка ниже это тренажёр (выбери максимально похожий, "
        "даже если фото не идеальное). Если это вообще не тренажёр или ничего похожего нет в списке — скажи, что не уверен.\n\n"
        f"Список тренажёров:\n{cluster_list}\n\n"
        "Ответь по-русски: 1-2 предложения, что это за тренажёр и для чего используется. "
        "В конце ОБЯЗАТЕЛЬНО на отдельной строке укажи точную подпись из списка в формате: МЕТКА: <точная строка из списка>. "
        "Если не уверен — МЕТКА: нет."
    )
    try:
        reply = await _call_vision(b64, mime, prompt, max_tokens=300)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

    label_match = re.search(r"МЕТКА:\s*(.+)", reply)
    cluster_label = None
    if label_match:
        candidate = label_match.group(1).strip()
        if candidate in cluster_labels:
            cluster_label = candidate
    reply_text = re.sub(r"МЕТКА:\s*.+", "", reply).strip()

    db.add(ChatMessage(user_id=user.id, role="assistant", content=reply_text, tool="workout"))
    db.commit()
    return JSONResponse({"reply": reply_text, "cluster_label": cluster_label})


@app.post("/workout/api/add-equipment")
async def workout_add_equipment(request: Request, user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return JSONResponse({"error": "Не авторизован"}, status_code=401)
    data = await request.json()
    cluster_label = data.get("cluster_label")
    cluster_labels = {item["label"] for item in _workout_equipment_checklist(db)}
    if cluster_label not in cluster_labels:
        return JSONResponse({"error": "Неизвестный тренажёр"}, status_code=400)
    profile = db.query(WorkoutProfile).filter(WorkoutProfile.user_id == user.id).first()
    if not profile:
        return JSONResponse({"error": "Сначала заполни анкету"}, status_code=400)
    equipment = list(profile.equipment or [])
    if cluster_label not in equipment:
        equipment.append(cluster_label)
        profile.equipment = equipment
        profile.home_only = False
        db.commit()
    return JSONResponse({"ok": True, "equipment": equipment})
