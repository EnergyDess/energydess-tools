from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean, Float, JSON
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime
import os
import re
import shutil
import sqlite3

# DB_PATH задаётся через .env на Fly.io (volume монтируется в /data),
# по умолчанию — как раньше, файл рядом с кодом
DB_PATH = os.getenv("DB_PATH", "./app.db")
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    # sqlite_autoincrement — чтобы id не переиспользовались после удаления
    # аккаунта: иначе SQLite отдаёт новому пользователю max(id)+1, и тот
    # наследует привязанное к номеру предыдущего (файл аватара, к примеру).
    # Действует на новых базах; существующую переводит
    # _migrate_users_autoincrement()
    __table_args__ = {"sqlite_autoincrement": True}
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    is_admin = Column(Boolean, default=False)
    display_name = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_verified = Column(Boolean, nullable=True)
    verification_token = Column(String, nullable=True)
    verification_token_expires = Column(DateTime, nullable=True)
    reset_token = Column(String, nullable=True)
    reset_token_expires = Column(DateTime, nullable=True)
    # Время последней загрузки аватара. NULL — аватара нет, показывается
    # буква-инициал. Оно же идёт версией в URL картинки: без этого браузер
    # держал бы старое изображение в кэше и после замены
    avatar_updated_at = Column(DateTime, nullable=True)
    # Часовой пояс в формате IANA (Europe/Moscow). NULL — не выбран,
    # интерфейс подставит определённый браузером
    timezone = Column(String, nullable=True)
    # Время последней смены пароля. Попадает в JWT и сверяется при каждом
    # запросе: токен, выданный до смены, перестаёт действовать. Без этого
    # сброс пароля не отбирал доступ у того, кто увёл аккаунт
    password_changed_at = Column(DateTime, nullable=True)


class Resume(Base):
    __tablename__ = "resumes"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, unique=True, nullable=False)
    resume_text = Column(Text, default="")


class ToolAccess(Base):
    __tablename__ = "tool_access"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    tool_id = Column(String, nullable=False)


class EnshroudedSlot(Base):
    __tablename__ = "enshrouded_slots"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    set_id = Column(String, nullable=False)
    slot_id = Column(String, nullable=False)
    owned = Column(Boolean, default=False)
    rarity = Column(String, default="common")
    level = Column(Integer, nullable=True)
    duplicates = Column(Integer, default=0)


class NutritionProfile(Base):
    __tablename__ = "nutrition_profiles"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, unique=True, nullable=False, index=True)
    gender = Column(String, default="male")
    age = Column(Integer, nullable=True)
    weight_kg = Column(Float, nullable=True)
    height_cm = Column(Float, nullable=True)
    goal = Column(String, default="maintain")  # lose/maintain/gain
    activity_level = Column(String, default="moderate")  # sedentary/light/moderate/active/very_active
    calorie_goal = Column(Integer, nullable=True)
    protein_goal = Column(Integer, nullable=True)
    fat_goal = Column(Integer, nullable=True)
    carb_goal = Column(Integer, nullable=True)
    water_goal_ml = Column(Integer, default=2000)
    target_weight_kg = Column(Float, nullable=True)
    start_weight_kg = Column(Float, nullable=True)


class HHProfile(Base):
    __tablename__ = "hh_profiles"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, unique=True, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Раздел 1 — Основная информация
    profession_one_liner = Column(Text, nullable=True)
    location = Column(String, nullable=True)
    timezone = Column(String, nullable=True)
    work_format = Column(String, nullable=True)  # удалёнка / офис / гибрид / любой
    languages = Column(JSON, nullable=False, default=list)  # [{lang, level}]

    # Раздел 2 — Опыт работы (сверх резюме)
    total_years_in_profession = Column(String, nullable=True)
    experience_extra = Column(JSON, nullable=False, default=list)  # [{company, position, period, description, achievements}]

    # Раздел 3 — Проекты и портфолио
    projects = Column(JSON, nullable=False, default=list)  # [{title, type, url, description, tools, tags}]

    # Раздел 4 — Навыки и инструменты
    skills = Column(JSON, nullable=False, default=list)  # [str, ...]

    # Раздел 5 — Методология
    methodology = Column(Text, nullable=True)

    # Раздел 6 — Дополнительный контекст
    extra_context = Column(Text, nullable=True)

    # Раздел 7 — Тон и стиль писем
    tone_preference = Column(String, nullable=True)  # живой / формально-деловой / нейтральный / очень неформальный
    never_mention = Column(Text, nullable=True)
    ending_style = Column(JSON, nullable=True)  # {suggest_call: bool, suggest_test_task: bool, just_farewell: bool}


class EmailLog(Base):
    """Журнал отправок писем через Resend — по одной записи на каждую попытку.

    Заведён потому, что раньше факт отправки не фиксировался нигде: ответ Resend
    не читался вообще, ошибки глушились, и сбой канала (протухший ключ, лимит,
    слетевшая верификация домена) остался бы незамеченным.

    Отдельной таблицей, а не полем у пользователя: send_email обслуживает три
    сценария, попыток бывает несколько (кнопка «отправить ещё раз»), и поле
    затирало бы ровно ту историю, ради которой заводится. Плюс на этот журнал
    опирается кулдаун повторной отправки, а позже — rate limiting из BACKLOG №1.
    """
    __tablename__ = "email_logs"
    id = Column(Integer, primary_key=True)
    # nullable: письмо может уходить на адрес, за которым нет аккаунта
    user_id = Column(Integer, nullable=True, index=True)
    to_email = Column(String, nullable=False, index=True)
    kind = Column(String, nullable=False)      # verify / resend / reset
    resend_id = Column(String, nullable=True)  # id письма в Resend — сверять с их дашбордом
    # Причина сбоя в формате «<код>: <детали>», коды: no_key / timeout /
    # http_<статус> / network / parse. NULL — письмо принято Resend
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class CoverLetter(Base):
    __tablename__ = "cover_letters"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    job_title = Column(String, nullable=True)
    company_name = Column(String, nullable=True)
    job_text = Column(Text, nullable=False)
    letter_text = Column(Text, nullable=False)
    analysis_json = Column(JSON, nullable=True)
    # Причина, по которой анализ вакансии не отработал. Формат «<код>: <детали>»,
    # коды: timeout / http_<статус> / truncated / parse / empty. NULL — сбоя не было.
    # Отдельным полем, а не внутри analysis_json: то поле означает РЕЗУЛЬТАТ анализа
    # и его читают через .get(...) — подмешивать туда ошибки значит размывать смысл.
    analysis_error = Column(Text, nullable=True)
    custom_context = Column(Text, nullable=True)
    edited = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class FoodLog(Base):
    __tablename__ = "food_logs"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    log_date = Column(String, nullable=False)
    meal_type = Column(String, nullable=False)  # breakfast/lunch/dinner/snack
    food_name = Column(String, nullable=False)
    brand = Column(String, nullable=True)
    grams = Column(Float, nullable=False)
    calories = Column(Float, nullable=False)
    protein = Column(Float, default=0)
    fat = Column(Float, default=0)
    carbs = Column(Float, default=0)
    barcode = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class CustomFood(Base):
    __tablename__ = "custom_foods"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    name = Column(String, nullable=False)
    brand = Column(String, nullable=True)
    barcode = Column(String, nullable=True)
    calories_per_100g = Column(Float, nullable=False)
    protein_per_100g = Column(Float, default=0)
    fat_per_100g = Column(Float, default=0)
    carbs_per_100g = Column(Float, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class CustomRecipe(Base):
    __tablename__ = "custom_recipes"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    name = Column(String, nullable=False)
    total_grams = Column(Float, nullable=False, default=100)
    calories = Column(Float, nullable=False, default=0)
    protein = Column(Float, default=0)
    fat = Column(Float, default=0)
    carbs = Column(Float, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class RecipeIngredient(Base):
    __tablename__ = "recipe_ingredients"
    id = Column(Integer, primary_key=True)
    recipe_id = Column(Integer, nullable=False, index=True)
    food_name = Column(String, nullable=False)
    grams = Column(Float, nullable=False)
    calories = Column(Float, nullable=False)
    protein = Column(Float, default=0)
    fat = Column(Float, default=0)
    carbs = Column(Float, default=0)


class WaterLog(Base):
    __tablename__ = "water_logs"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    log_date = Column(String, nullable=False)
    amount_ml = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    role = Column(String, nullable=False)  # user/assistant
    content = Column(Text, nullable=False)
    # Вложение переписки: токен файла на томе (см. _media_path в main.py).
    # Картинки хранились в base64 прямо здесь, колонка image_data удалена
    # миграцией после переезда — BACKLOG №20
    image_path = Column(String, nullable=True)
    tool = Column(String, nullable=False, default="nutrition")  # nutrition/workout — общая таблица на оба чата
    created_at = Column(DateTime, default=datetime.utcnow)


class WeightLog(Base):
    __tablename__ = "weight_logs"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    log_date = Column(String, nullable=False)
    weight_kg = Column(Float, nullable=True)
    waist_cm = Column(Float, nullable=True)
    hips_cm = Column(Float, nullable=True)
    chest_cm = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    # ── состав тела — вручную или с весов Xiaomi (см. ScaleConnection) ──
    body_fat_pct = Column(Float, nullable=True)
    muscle_rate_pct = Column(Float, nullable=True)
    water_pct = Column(Float, nullable=True)
    visceral_fat = Column(Float, nullable=True)
    bmi = Column(Float, nullable=True)
    bmr = Column(Integer, nullable=True)
    body_age = Column(Integer, nullable=True)
    bone_mass_kg = Column(Float, nullable=True)
    source = Column(String, nullable=False, default="manual")  # manual/zepp


class ScaleConnection(Base):
    """Подключение умных весов Xiaomi через неофициальный API Zepp Life
    (см. zepp_client.py). Все четыре поля с учётными данными зашифрованы
    (Fernet, ключ — CREDENTIALS_ENCRYPTION_KEY), см. crypto.py.

    encrypted_app_token/encrypted_zepp_user_id — кеш токена сессии, чтобы
    не логиниться паролем при каждой синхронизации: полный логин по паролю
    разлогинивает пользователя в мобильном приложении Zepp Life (особенность
    их серверной сессии, не наша).

    Токен раньше лежал открытым рядом с зашифрованным паролем — и это сводило
    шифрование пароля почти на нет: украв базу, чужие измерения можно было
    читать прямо по токену, пароль для этого не нужен."""
    __tablename__ = "scale_connections"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, unique=True, nullable=False, index=True)
    encrypted_username = Column(Text, nullable=False)
    encrypted_password = Column(Text, nullable=False)
    encrypted_app_token = Column(Text, nullable=True)
    encrypted_zepp_user_id = Column(Text, nullable=True)
    last_sync_at = Column(DateTime, nullable=True)
    last_sync_status = Column(String, nullable=True)  # ok/error
    last_sync_error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class BodyPhoto(Base):
    """Фото-дневник прогресса тела — визуальный, без ИИ-анализа."""
    __tablename__ = "body_photos"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    log_date = Column(String, nullable=False)
    angle = Column(String, nullable=False)  # front/side/back
    image_path = Column(String, nullable=True)   # токен файла на томе
    created_at = Column(DateTime, default=datetime.utcnow)


class Exercise(Base):
    __tablename__ = "exercises"
    id = Column(String, primary_key=True)  # исходный id из free-exercise-db, напр. "Barbell_Squat"
    name = Column(String, nullable=False)
    name_ru = Column(String, nullable=False)
    force = Column(String, nullable=True)  # static/pull/push
    level = Column(String, nullable=False)  # beginner/intermediate/expert
    mechanic = Column(String, nullable=True)  # compound/isolation
    equipment = Column(String, nullable=True)  # исходное поле free-exercise-db, null = body only
    equipment_cluster = Column(String, nullable=True, index=True)  # пункт чек-листа "Мой зал", напр. "Гакк-машина / Hack Squat"
    primary_muscles = Column(JSON, nullable=False, default=list)
    secondary_muscles = Column(JSON, nullable=False, default=list)
    instructions = Column(JSON, nullable=False, default=list)
    instructions_ru = Column(JSON, nullable=False, default=list)
    category = Column(String, nullable=False)
    images = Column(JSON, nullable=False, default=list)  # относительные пути внутри static/exercises/
    youtube_id = Column(String, nullable=True)  # id видео техники выполнения, null = не найдено / не импортировано
    video_status = Column(String, nullable=False, default="unchecked")  # unchecked/approved/wrong/no_video — ручная модерация в админке
    video_replaced_at = Column(DateTime, nullable=True)  # когда админ последний раз заменил youtube_id


class WorkoutProfile(Base):
    __tablename__ = "workout_profiles"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, unique=True, nullable=False, index=True)
    goal = Column(String, nullable=True)  # mass/strength/lose/maintain/recomp
    days_per_week = Column(Integer, nullable=True)  # 1-6
    level = Column(String, nullable=True)  # beginner/intermediate/expert
    focus_zones = Column(JSON, nullable=False, default=list)  # arms/shoulders/chest/back/legs/abs/glutes
    pain_zones = Column(JSON, nullable=False, default=list)  # knee/lower_back/shoulder/elbow/neck
    # progression_step_kg убран — шаг прогрессии теперь автоматика по типу
    # оборудования (см. ProgressionSetting), а не один вопрос анкеты
    equipment = Column(JSON, nullable=False, default=list)  # отмеченные equipment_cluster из "Мой зал"
    home_only = Column(Boolean, nullable=False, default=False)  # "Дом без инвентаря"
    onboarded = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # ── Возвращение после перерыва (см. main.py: _last_activity_date и др.) ──
    return_plan_status = Column(String, nullable=True)  # short/long/injury
    return_plan_applied_date = Column(String, nullable=True)  # YYYY-MM-DD выбора варианта
    return_plan_light_days_remaining = Column(Integer, nullable=False, default=0)
    return_plan_weight_factor = Column(Float, nullable=True)  # 0.8 / 0.6 — снижение веса на возврате

    # ── Мезоцикл (см. main.py: MESOCYCLE_*) ──
    mesocycle_started_date = Column(String, nullable=True)  # YYYY-MM-DD начала текущего цикла
    mesocycle_length_weeks = Column(Integer, nullable=False, default=10)

    # ── Интеграция с Дневником питания (см. main.py: workout_nutrition_summary) ──
    # Включена по умолчанию, но если пользователь не ведёт дневник питания
    # активно — подсказки только мешают, поэтому есть простой выключатель
    use_nutrition_data = Column(Boolean, nullable=False, default=True)


class WorkoutProgram(Base):
    __tablename__ = "workout_programs"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    structure = Column(String, nullable=False)  # full_body/upper_lower/push_pull_legs
    days_per_week = Column(Integer, nullable=False)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class WorkoutProgramDay(Base):
    __tablename__ = "workout_program_days"
    id = Column(Integer, primary_key=True)
    program_id = Column(Integer, nullable=False, index=True)
    day_index = Column(Integer, nullable=False)
    day_type = Column(String, nullable=False)  # full_body/upper/lower/push/pull/legs
    label = Column(String, nullable=False)


class WorkoutProgramExercise(Base):
    __tablename__ = "workout_program_exercises"
    id = Column(Integer, primary_key=True)
    day_id = Column(Integer, nullable=False, index=True)
    exercise_id = Column(String, nullable=False, index=True)
    order = Column(Integer, nullable=False)
    target_sets = Column(Integer, nullable=False)
    rep_low = Column(Integer, nullable=False)
    rep_high = Column(Integer, nullable=False)
    is_bonus = Column(Boolean, nullable=False, default=False)  # "если остались силы" — вне основного лимита


class WorkoutSession(Base):
    """Уровень 3 логирования — тренировка: попытка дня программы в дату."""
    __tablename__ = "workout_sessions"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    program_day_id = Column(Integer, nullable=False, index=True)
    log_date = Column(String, nullable=False)  # YYYY-MM-DD
    skipped = Column(Boolean, nullable=False, default=False)
    skip_reason = Column(String, nullable=True)  # tired/no_time/sick/gym_closed
    # completed — тренировка финализирована явным тапом "Завершить тренировку"
    # ИЛИ дата уже не сегодня (см. PROGRESSION в main.py). Авто-прогрессия
    # анализирует только завершённые тренировки — никогда текущую открытую
    # сессию, чтобы не предлагать поднять вес посреди незавершённых данных.
    completed = Column(Boolean, nullable=False, default=False)
    is_light_day = Column(Boolean, nullable=False, default=False)  # исключается из расчёта прогрессии
    created_at = Column(DateTime, default=datetime.utcnow)


class SetLog(Base):
    """Уровень 1 логирования — подход: повторы × вес. Привязан к exercise_id
    (не к program_exercise_id), чтобы пересборка программы не теряла историю."""
    __tablename__ = "set_logs"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    session_id = Column(Integer, nullable=False, index=True)
    exercise_id = Column(String, nullable=False, index=True)
    set_index = Column(Integer, nullable=False)
    reps = Column(Integer, nullable=True)
    weight_kg = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ProgressionSetting(Base):
    """Шаг прогрессии — авто по типу оборудования (см. PROGRESSION_DEFAULTS
    в main.py), с возможностью переопределить для типа снаряда (штанга,
    гантели) или конкретного тренажёра (cluster:<equipment_cluster> — общая
    шкала для всех упражнений на нём, не на уровне отдельного упражнения)."""
    __tablename__ = "progression_settings"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    scope = Column(String, nullable=False)  # "equipment:barbell" / "cluster:<label>"
    status = Column(String, nullable=False, default="standard")  # standard/custom/pending_at_gym
    step_kg = Column(Float, nullable=True)
    fixed_values = Column(JSON, nullable=True)  # неровная шкала блочного тренажёра, напр. [40, 45, 49.5]
    created_at = Column(DateTime, default=datetime.utcnow)


class WorkoutExerciseSwap(Base):
    """Замена упражнения на альтернативу — действует только на одну дату
    (program_exercise_id остаётся тот же слот программы), не меняет программу
    навсегда. История/прогрессия по обоим вариантам считаются независимо,
    так как set_log привязан к exercise_id, а не к program_exercise_id."""
    __tablename__ = "workout_exercise_swaps"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    program_exercise_id = Column(Integer, nullable=False, index=True)
    log_date = Column(String, nullable=False)
    swapped_to_exercise_id = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class PainZonePatch(Base):
    """Запись о замене/удалении упражнения из-за зоны боли (см.
    _patch_program_for_pain_zone в main.py) — без неё снятие ограничения
    (clear_pain_zone) не может вернуть исходное упражнение, оно было бы
    потеряно безвозвратно. SetLog привязан к exercise_id напрямую, поэтому
    историю весов по original_exercise_id можно поднять независимо от
    того, жива ли строка WorkoutProgramExercise."""
    __tablename__ = "pain_zone_patches"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    zone = Column(String, nullable=False, index=True)
    program_id = Column(Integer, nullable=False)
    day_id = Column(Integer, nullable=False, index=True)
    order_in_day = Column(Integer, nullable=False)
    original_exercise_id = Column(String, nullable=False)
    original_target_sets = Column(Integer, nullable=False)
    original_rep_low = Column(Integer, nullable=False)
    original_rep_high = Column(Integer, nullable=False)
    original_is_bonus = Column(Boolean, nullable=False, default=False)
    # текущий живой pe.id, если строка не удалялась (замена); NULL — строка
    # была удалена совсем (нет безопасного аналога), при возврате пересоздаём
    program_exercise_id = Column(Integer, nullable=True, index=True)
    applied_exercise_id = Column(String, nullable=True)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    reverted_at = Column(DateTime, nullable=True)
    # ~55% от последнего рабочего веса на момент возврата — фиксируем именно
    # тогда, чтобы при повторном чтении карточки не пересчитывалось от уже
    # новых (сниженных) логов после возврата
    suggested_return_weight = Column(Float, nullable=True)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    Base.metadata.create_all(bind=engine)


def migrate_db():
    conn = sqlite3.connect(DB_PATH)
    for col in [
        "ALTER TABLE users ADD COLUMN is_verified BOOLEAN",
        "ALTER TABLE users ADD COLUMN verification_token VARCHAR",
        "ALTER TABLE users ADD COLUMN verification_token_expires DATETIME",
        "ALTER TABLE users ADD COLUMN reset_token VARCHAR",
        "ALTER TABLE users ADD COLUMN reset_token_expires DATETIME",
        "ALTER TABLE chat_messages ADD COLUMN image_data TEXT",
        "ALTER TABLE workout_profiles ADD COLUMN focus_zones JSON",
        "ALTER TABLE workout_program_exercises ADD COLUMN is_bonus BOOLEAN",
        "ALTER TABLE workout_sessions ADD COLUMN completed BOOLEAN",
        "ALTER TABLE workout_sessions ADD COLUMN is_light_day BOOLEAN",
        "ALTER TABLE workout_profiles ADD COLUMN return_plan_status VARCHAR",
        "ALTER TABLE workout_profiles ADD COLUMN return_plan_applied_date VARCHAR",
        "ALTER TABLE workout_profiles ADD COLUMN return_plan_light_days_remaining INTEGER",
        "ALTER TABLE workout_profiles ADD COLUMN return_plan_weight_factor FLOAT",
        "ALTER TABLE workout_profiles ADD COLUMN mesocycle_started_date VARCHAR",
        "ALTER TABLE workout_profiles ADD COLUMN mesocycle_length_weeks INTEGER",
        "ALTER TABLE chat_messages ADD COLUMN tool VARCHAR",
        "ALTER TABLE weight_logs ADD COLUMN body_fat_pct FLOAT",
        "ALTER TABLE weight_logs ADD COLUMN muscle_rate_pct FLOAT",
        "ALTER TABLE weight_logs ADD COLUMN water_pct FLOAT",
        "ALTER TABLE weight_logs ADD COLUMN visceral_fat FLOAT",
        "ALTER TABLE weight_logs ADD COLUMN bmi FLOAT",
        "ALTER TABLE weight_logs ADD COLUMN bmr INTEGER",
        "ALTER TABLE weight_logs ADD COLUMN body_age INTEGER",
        "ALTER TABLE weight_logs ADD COLUMN source VARCHAR",
        "ALTER TABLE workout_profiles ADD COLUMN use_nutrition_data BOOLEAN",
        "ALTER TABLE weight_logs ADD COLUMN bone_mass_kg FLOAT",
        "ALTER TABLE exercises ADD COLUMN youtube_id VARCHAR",
        "ALTER TABLE cover_letters ADD COLUMN edited BOOLEAN DEFAULT 0",
        "ALTER TABLE exercises ADD COLUMN video_status VARCHAR",
        "ALTER TABLE exercises ADD COLUMN video_replaced_at DATETIME",
        "ALTER TABLE cover_letters ADD COLUMN analysis_error TEXT",
        "ALTER TABLE users ADD COLUMN avatar_updated_at DATETIME",
        "ALTER TABLE users ADD COLUMN timezone VARCHAR",
        "ALTER TABLE users ADD COLUMN password_changed_at DATETIME",
        "ALTER TABLE scale_connections ADD COLUMN encrypted_app_token TEXT",
        "ALTER TABLE scale_connections ADD COLUMN encrypted_zepp_user_id TEXT",
        "ALTER TABLE chat_messages ADD COLUMN image_path VARCHAR",
        "ALTER TABLE body_photos ADD COLUMN image_path VARCHAR",
    ]:
        try:
            conn.execute(col)
        except Exception:
            pass
    # бэкфилл новых колонок со значением по умолчанию — ALTER TABLE в SQLite
    # не применяет Python-дефолт к уже существующим строкам, оставляет NULL
    for backfill in [
        "UPDATE chat_messages SET tool = 'nutrition' WHERE tool IS NULL",
        "UPDATE weight_logs SET source = 'manual' WHERE source IS NULL",
        "UPDATE workout_sessions SET completed = 0 WHERE completed IS NULL",
        "UPDATE workout_sessions SET is_light_day = 0 WHERE is_light_day IS NULL",
        "UPDATE workout_profiles SET return_plan_light_days_remaining = 0 WHERE return_plan_light_days_remaining IS NULL",
        "UPDATE workout_profiles SET mesocycle_length_weeks = 10 WHERE mesocycle_length_weeks IS NULL",
        "UPDATE workout_profiles SET use_nutrition_data = 1 WHERE use_nutrition_data IS NULL",
        "UPDATE cover_letters SET edited = 0 WHERE edited IS NULL",
        "UPDATE exercises SET video_status = 'no_video' WHERE video_status IS NULL AND (youtube_id IS NULL OR youtube_id = '')",
        "UPDATE exercises SET video_status = 'unchecked' WHERE video_status IS NULL",
        # Ретроактивная верификация: is_verified раньше не проставлялся всем строкам при
        # добавлении колонки (NULL). Помечаем как подтверждённых только те аккаунты, у
        # которых NULL — это существующие пользователи "из прошлого", не бот-волна.
        # Явные False (реальные неподтверждённые/бот-регистрации) НЕ трогаем.
        "UPDATE users SET is_verified = 1 WHERE is_verified IS NULL",
    ]:
        try:
            conn.execute(backfill)
        except Exception:
            pass
    conn.commit()
    _migrate_users_autoincrement(conn)
    _migrate_zepp_token_encryption(conn)
    _migrate_drop_image_data(conn)
    conn.close()


def _migrate_drop_image_data(conn) -> int:
    """Убирает колонки image_data после переезда картинок в файлы.

    Две причины делать это, а не оставлять колонку пустой.

    Первая — она сломана. У body_photos.image_data стоит NOT NULL,
    и ALTER TABLE его не снимает: модель поменяли на nullable, а схема
    осталась прежней. Первая же загрузка фото тела падала на INSERT
    с IntegrityError. Записей там не было ни одной, поэтому дефект
    и не проявлялся — он ждал первого пользователя.

    Вторая — пока колонка жива, жив и фолбэк «пустой путь, читаем
    image_data», а он маскирует поломку записи: сломанный путь записи
    обслуживался бы исправным чтением, и база тихо росла бы обратно.

    Удаляем ТОЛЬКО если непустых значений не осталось. Есть хоть одно —
    значит миграция не доделана, и колонка нужна.
    """
    удалено = 0
    for таблица in ("chat_messages", "body_photos"):
        колонки = {r[1] for r in conn.execute("PRAGMA table_info(%s)" % таблица)}
        if "image_data" not in колонки:
            continue
        осталось = conn.execute(
            "SELECT COUNT(*) FROM %s WHERE image_data IS NOT NULL "
            "AND image_data <> ''" % таблица).fetchone()[0]
        if осталось:
            print(f"[migrate] {таблица}.image_data не удалена: непустых записей "
                  f"{осталось}, сначала migrate_media.py")
            continue
        try:
            conn.execute("ALTER TABLE %s DROP COLUMN image_data" % таблица)
            conn.commit()
            удалено += 1
            print(f"[migrate] {таблица}.image_data удалена")
        except Exception as e:
            print(f"[migrate] {таблица}.image_data не удалена: {type(e).__name__}: {e}")
    return удалено


def _migrate_zepp_token_encryption(conn) -> int:
    """Зашифровывает токены Zepp, лежавшие открытыми, и стирает исходные.

    Старые колонки app_token/zepp_user_id удаляются: обнулить значение
    недостаточно — колонка осталась бы в схеме, и первая же невнимательная
    правка снова начала бы писать в неё plaintext.

    После удаления делаем VACUUM. Без него страницы с прежним открытым
    токеном остаются в файле как свободное место и уезжают в ежедневный
    бэкап — то есть смысл шифрования теряется ровно там, где он важнее всего.

    Возвращает число перенесённых записей.
    """
    колонки = {r[1] for r in conn.execute("PRAGMA table_info(scale_connections)")}
    if "app_token" not in колонки:
        return 0        # миграция уже прошла

    import crypto
    if not crypto.is_configured():
        # Без ключа шифровать нечем. Стереть открытые токены всё равно можно —
        # но это разорвало бы работающие подключения, поэтому решает человек
        print("[migrate] токены Zepp остались открытыми: "
              "CREDENTIALS_ENCRYPTION_KEY не задан")
        return 0

    строки = conn.execute(
        "SELECT id, app_token, zepp_user_id FROM scale_connections "
        "WHERE app_token IS NOT NULL OR zepp_user_id IS NOT NULL"
    ).fetchall()

    перенесено = 0
    try:
        conn.execute("BEGIN")
        for id_, токен, zepp_id in строки:
            conn.execute(
                "UPDATE scale_connections SET encrypted_app_token = ?, "
                "encrypted_zepp_user_id = ? WHERE id = ?",
                (crypto.encrypt_optional(токен), crypto.encrypt_optional(zepp_id), id_),
            )
            перенесено += 1
        conn.execute("ALTER TABLE scale_connections DROP COLUMN app_token")
        conn.execute("ALTER TABLE scale_connections DROP COLUMN zepp_user_id")
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"[migrate] токены Zepp не зашифрованы: {type(e).__name__}: {e}")
        return 0

    conn.execute("VACUUM")      # вне транзакции — SQLite иначе откажет
    print(f"[migrate] токены Zepp зашифрованы, записей: {перенесено}, файл сжат")
    return перенесено


def _migrate_users_autoincrement(conn) -> bool:
    """Переводит users на AUTOINCREMENT, чтобы id не переиспользовались.

    Зачем. Без AUTOINCREMENT SQLite выдаёт новой строке max(id)+1. Удалили
    последнего пользователя — следующий зарегистрировавшийся получает его
    номер. Каскад чистит базу, но аватар лежит файлом /data/avatars/<id>.png,
    и новый человек увидел бы в шапке чужое лицо. Мы как раз собирались
    удалять 67 ботовых аккаунтов, что уронило бы max(id) сразу на десятки.

    Файл аватара теперь удаляется в delete_user_cascade — это первый рубеж.
    AUTOINCREMENT — второй: он закрывает не конкретно аватары, а сам приём
    «привязать что-то внешнее к id пользователя». Любая будущая привязка
    (файл, кеш, запись у стороннего сервиса) наследования уже не получит.

    AUTOINCREMENT в SQLite задаётся только при CREATE TABLE, поэтому таблицу
    приходится пересоздавать: скопировать, подменить, вернуть индексы. Делаем
    один раз и идемпотентно — признаком служит наличие users в sqlite_sequence.

    Возвращает True, если миграция выполнена сейчас.
    """
    есть = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='sqlite_sequence'"
    ).fetchone()
    if есть and conn.execute(
        "SELECT 1 FROM sqlite_sequence WHERE name='users'"
    ).fetchone():
        return False        # уже переведена

    ddl = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='users'"
    ).fetchone()
    if not ddl:
        return False        # базы ещё нет — таблицу создаст SQLAlchemy, уже с AUTOINCREMENT

    # Колонки берём из самой базы, а не из модели: они добавлялись миграциями
    # выше, и перечислять их здесь руками значит однажды разойтись со схемой
    колонки = [r[1] for r in conn.execute("PRAGMA table_info(users)")]
    список = ", ".join(f'"{c}"' for c in колонки)

    # Переносим тело исходного DDL, заменив объявление ключа. Всё, кроме
    # первичного ключа, остаётся как было — типы, NOT NULL, порядок колонок
    тело = ddl[0]
    тело = re.sub(r"\bid\s+INTEGER\s+NOT\s+NULL\s*,", "", тело, count=1, flags=re.I)
    тело = re.sub(r"PRIMARY\s+KEY\s*\(\s*id\s*\)",
                  "id INTEGER PRIMARY KEY AUTOINCREMENT", тело, count=1, flags=re.I)
    тело = тело.replace("CREATE TABLE users", "CREATE TABLE users_ai_new", 1)
    if "AUTOINCREMENT" not in тело:
        # DDL оказался не той формы, что мы ожидали. Молча продолжать нельзя:
        # без пересоздания id продолжат переиспользоваться
        print("[migrate] AUTOINCREMENT для users не применён: неожидаемый DDL")
        return False

    индексы = [r[0] for r in conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name='users' "
        "AND sql IS NOT NULL")]

    try:
        conn.execute("BEGIN")
        conn.execute(тело)
        conn.execute(f"INSERT INTO users_ai_new ({список}) SELECT {список} FROM users")
        conn.execute("DROP TABLE users")
        conn.execute("ALTER TABLE users_ai_new RENAME TO users")
        for sql in индексы:
            conn.execute(sql)      # UNIQUE на email в том числе — снялся вместе с таблицей
        # Ставим планку вручную: sqlite_sequence заполняется при вставке, а мы
        # копировали строки в новую таблицу. Без этого seq остался бы от
        # последней вставки, а не от максимума
        conn.execute("DELETE FROM sqlite_sequence WHERE name='users'")
        conn.execute("INSERT INTO sqlite_sequence(name, seq) "
                     "SELECT 'users', COALESCE(MAX(id), 0) FROM users")
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"[migrate] AUTOINCREMENT для users не применён: {type(e).__name__}: {e}")
        return False

    целостность = conn.execute("PRAGMA integrity_check").fetchone()[0]
    print(f"[migrate] users переведена на AUTOINCREMENT, integrity_check: {целостность}")
    return True


# ── Полное удаление пользователя ──────────────────────────────────────────────
#
# Раньше удаление чистило только users и resumes. Данные оставались в двух
# десятках таблиц, а SQLite переиспользует освободившиеся id — новый
# пользователь мог унаследовать чужие письма и дневник. Это утечка данных
# между людьми, а не косметика, поэтому кнопка «Удалить аккаунт» была
# заблокирована до появления этой функции (BACKLOG №11).
#
# Каскад сделан кодом, а не внешними ключами: в схеме их нет вовсе, добавить
# ретроспективно в SQLite нельзя без пересоздания всех таблиц, а PRAGMA
# foreign_keys там по умолчанию выключен.

# Таблицы с прямой привязкой по user_id. Порядок значения не имеет —
# они независимы друг от друга.
USER_TABLES = [
    "resumes", "tool_access", "enshrouded_slots", "nutrition_profiles",
    "hh_profiles", "cover_letters", "food_logs", "custom_foods", "custom_recipes",
    "water_logs", "chat_messages", "weight_logs", "scale_connections", "body_photos",
    "workout_profiles", "workout_programs", "workout_sessions", "set_logs",
    "progression_settings", "workout_exercise_swaps", "pain_zone_patches",
]

# Таблицы, привязанные к пользователю ЧЕРЕЗ родителя: поиском по user_id их
# не найти. Удалять строго до родителей, глубина — три уровня.
CHILD_TABLES = [
    ("workout_program_exercises", "day_id", "workout_program_days", "program_id",
     "workout_programs"),
    ("workout_program_days", "program_id", "workout_programs", None, None),
    ("recipe_ingredients", "recipe_id", "custom_recipes", None, None),
]

# email_logs намеренно НЕ удаляется, а обезличивается — см. _anonymize_email_logs
EXCLUDED_TABLES = {"email_logs", "users", "exercises"}


def check_user_tables_complete():
    """Сверяет список USER_TABLES с реальными моделями.

    Список в коде устареет в тот день, когда добавится новая модель с user_id,
    и про неё просто забудут. Проверка берёт таблицы из метаданных SQLAlchemy
    и возвращает те, что не учтены. Пустой список — всё в порядке.
    """
    с_user_id = {
        имя for имя, т in Base.metadata.tables.items()
        if "user_id" in т.columns
    }
    учтено = set(USER_TABLES) | EXCLUDED_TABLES
    return sorted(с_user_id - учтено)


# Чем каждая таблица должна быть названа в политике конфиденциальности.
# Достаточно одного совпадения из списка: формулировка может меняться,
# а вот исчезнуть категория целиком не должна.
#
# Список ведётся руками намеренно — автоматически «человеческое название»
# из имени таблицы не выведешь. Зато забыть таблицу нельзя: проверка ниже
# сверяется с метаданными SQLAlchemy и ругается на любую, которой здесь нет.
PRIVACY_MENTIONS = {
    "users":                     ["адрес электронной почты", "отображаемое имя"],
    "tool_access":               ["какие инструменты вам открыты"],
    "resumes":                   ["текст резюме"],
    "hh_profiles":               ["досье"],
    "cover_letters":             ["текст вакансии"],
    "nutrition_profiles":        ["уровень активности", "нормы калорий"],
    "food_logs":                 ["записи о съеденном"],
    "custom_foods":              ["добавленные вами продукты"],
    "custom_recipes":            ["рецепты"],
    "recipe_ingredients":        ["рецепты"],
    "water_logs":                ["вода"],
    "chat_messages":             ["переписка с ассистентами"],
    "weight_logs":               ["измерения тела"],
    "body_photos":               ["фотографии тела"],
    "scale_connections":         ["zepp life"],
    "workout_profiles":          ["зоны упора", "зоны боли"],
    "workout_programs":          ["программа"],
    "workout_program_days":      ["программа"],
    "workout_program_exercises": ["программа"],
    "workout_sessions":          ["журнал тренировок"],
    "set_logs":                  ["каждый подход"],
    "progression_settings":      ["шаг веса"],
    "workout_exercise_swaps":    ["замены упражнений"],
    "pain_zone_patches":         ["правки программы"],
    "enshrouded_slots":          ["enshrouded"],
    "email_logs":                ["факте отправки"],
}

# Таблицы без персональных данных: их в перечне категорий быть и не должно
PRIVACY_NOT_PERSONAL = {
    "exercises": "общий справочник упражнений, одинаковый для всех",
}


def check_privacy_coverage(текст_политики: str) -> list:
    """Сверяет перечень категорий в политике конфиденциальности со схемой базы.

    Полный перечень обрабатываемых данных — требование закона, а не
    стилистика, но забыть таблицу при этом легко: она добавляется в одном
    файле, а называть её нужно в другом. Так однажды и выпал целый
    инструмент — трекер Enshrouded не упоминался в политике вовсе,
    хотя данные по нему хранились.

    Проверка не судит формулировки, только наличие: для каждой таблицы
    ищет в тексте хотя бы одно из закреплённых за ней слов. Возвращает
    список расхождений, пустой список — всё названо.

    Текст передаётся аргументом, а не берётся из main: обратный импорт
    развернул бы зависимость и потянул сюда весь FastAPI. Запуск —
    check_privacy.py в корне.
    """
    текст = (текст_политики or "").lower()
    расхождения = []

    for имя in sorted(Base.metadata.tables):
        if имя in PRIVACY_NOT_PERSONAL:
            continue
        слова = PRIVACY_MENTIONS.get(имя)
        if слова is None:
            расхождения.append(
                f"{имя}: таблица не учтена в PRIVACY_MENTIONS — добавьте её "
                f"туда и назовите категорию в политике")
            continue
        if not any(с.lower() in текст for с in слова):
            расхождения.append(
                f"{имя}: в политике не найдено ни одного из "
                f"{слова} — категория выпала из перечня либо формулировка "
                f"изменилась (тогда поправьте PRIVACY_MENTIONS)")

    # Список не должен отставать от схемы и в обратную сторону: строка
    # про удалённую таблицу молча проходила бы проверку годами
    лишние = (set(PRIVACY_MENTIONS) | set(PRIVACY_NOT_PERSONAL)) - set(Base.metadata.tables)
    for имя in sorted(лишние):
        расхождения.append(f"{имя}: есть в списке, но таблицы в схеме нет — удалите строку")

    return расхождения


# Таблицы, где строка появляется САМА при регистрации и данными не является,
# пока пуста. Условие описывает, что считать пустотой.
#
# Сейчас такая одна: при регистрации каждому заводится пустое резюме
# (main.py, регистрация). На копии боевой базы 91 запись из 93 — пустые
# болванки ботов. Без этого исключения проверка «аккаунт пуст» считала бы
# данными всех подряд, и очистка перестала бы удалять ботов вовсе:
# в прогоне 2026-07-31 она пропустила 60 аккаунтов вместо одного.
ПУСТЫЕ_ПО_УМОЛЧАНИЮ = {
    "resumes": "resume_text IS NULL OR TRIM(resume_text) = ''",
}


def user_data_counts(user_id: int) -> dict:
    """Что аккаунт накопил. Пустой словарь — аккаунт пуст.

    Считает ровно то, что удалил бы каскад: вызывает его же в режиме
    dry_run и берёт непустые строки отчёта. Это не оптимизация, а способ
    сделать расхождение невозможным — списки таблиц одни и те же,
    и добавление новой модели попадает в обе стороны сразу
    (см. CLAUDE.md §6.1).

    Из подсчёта исключены:
      users       — сама учётная запись, она есть у всех и данными не является;
      email_logs  — письмо о верификации приходит каждому боту, наличие
                    записи о нём ничего не говорит о содержимом аккаунта;
      строки из ПУСТЫЕ_ПО_УМОЛЧАНИЮ — заготовки, созданные при регистрации.
    """
    отчёт = delete_user_cascade(user_id, dry_run=True)
    пропустить = {"users", "email_logs (обезличено)"}
    итог = {т: n for т, n in отчёт.items() if n and т not in пропустить}

    # Таблицы-заготовки пересчитываем по содержимому, а не по факту строки
    if any(т in ПУСТЫЕ_ПО_УМОЛЧАНИЮ for т in итог):
        conn = sqlite3.connect(DB_PATH)
        try:
            for таблица, условие_пустоты in ПУСТЫЕ_ПО_УМОЛЧАНИЮ.items():
                if таблица not in итог:
                    continue
                n = conn.execute(
                    "SELECT COUNT(*) FROM %s WHERE user_id = ? AND NOT (%s)"
                    % (таблица, условие_пустоты), (user_id,)).fetchone()[0]
                if n:
                    итог[таблица] = n
                else:
                    итог.pop(таблица)
        finally:
            conn.close()
    return итог


def _anonymize_email_logs(conn, user_id: int) -> int:
    """Обезличивает журнал отправок вместо удаления.

    Журнал нужен, чтобы разбирать проблемы с доставкой уже после того, как
    аккаунт удалён: коды сбоев, resend_id и время — не персональные данные.
    Но адрес почты — персональные, и оставлять его после удаления аккаунта
    нельзя. Плюс переиспользование id: новый пользователь унаследовал бы чужие
    записи, а по ним считается кулдаун повторной отправки письма.

    Поэтому: user_id обнуляется, адрес заменяется маской с сохранением домена —
    статистика доставки по провайдерам остаётся, личность уходит.
    """
    строки = conn.execute(
        "SELECT id, to_email FROM email_logs WHERE user_id = ?", (user_id,)
    ).fetchall()
    for id_, адрес in строки:
        домен = адрес.split("@")[-1] if адрес and "@" in адрес else "неизвестно"
        conn.execute(
            "UPDATE email_logs SET user_id = NULL, to_email = ? WHERE id = ?",
            (f"удалённый@{домен}", id_),
        )
    return len(строки)


def delete_user_cascade(user_id: int, dry_run: bool = False) -> dict:
    """Удаляет пользователя со всеми его данными. Возвращает отчёт по таблицам.

    dry_run=True только считает, ничего не трогая, — отчёт нужен как последняя
    проверка перед необратимым действием.

    Всё в одной транзакции: либо удаляется целиком, либо не удаляется ничего.
    Половинчатое удаление хуже неудалённого — оно и есть та самая сирота.
    """
    отчёт = {}
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("BEGIN")

        # 1. Внуки и дети — строго до родителей, иначе связь потеряется
        for таблица, поле, родитель, поле_р, дед in CHILD_TABLES:
            if дед:
                условие = (f"{поле} IN (SELECT id FROM {родитель} WHERE {поле_р} IN "
                           f"(SELECT id FROM {дед} WHERE user_id = ?))")
            else:
                условие = f"{поле} IN (SELECT id FROM {родитель} WHERE user_id = ?)"
            n = conn.execute(f"SELECT COUNT(*) FROM {таблица} WHERE {условие}",
                             (user_id,)).fetchone()[0]
            if n and not dry_run:
                conn.execute(f"DELETE FROM {таблица} WHERE {условие}", (user_id,))
            отчёт[таблица] = n

        # 2. Всё с прямой привязкой
        for таблица in USER_TABLES:
            n = conn.execute(f"SELECT COUNT(*) FROM {таблица} WHERE user_id = ?",
                             (user_id,)).fetchone()[0]
            if n and not dry_run:
                conn.execute(f"DELETE FROM {таблица} WHERE user_id = ?", (user_id,))
            отчёт[таблица] = n

        # 3. Журнал писем — обезличивание, а не удаление.
        #    Записи с user_id IS NULL (отправки на адрес без аккаунта) не
        #    затрагиваются: сравнение с NULL в SQL никогда не истинно
        n = conn.execute("SELECT COUNT(*) FROM email_logs WHERE user_id = ?",
                         (user_id,)).fetchone()[0]
        if n and not dry_run:
            _anonymize_email_logs(conn, user_id)
        отчёт["email_logs (обезличено)"] = n

        # 4. Сам пользователь — последним
        n = conn.execute("SELECT COUNT(*) FROM users WHERE id = ?", (user_id,)).fetchone()[0]
        if n and not dry_run:
            conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        отчёт["users"] = n

        if dry_run:
            conn.rollback()
        else:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    # 5. Файлы вне базы — аватар и приватные медиа. Строго после commit:
    #    упади транзакция, файлы остались бы удалёнными у живого аккаунта.
    #    В обратную сторону ошибка дешевле — осиротевший файл никому
    #    не показывается, потому что показывать его больше некому
    отчёт["файл аватара"] = _delete_avatar_file(user_id, dry_run=dry_run)
    отчёт["медиафайлы"] = _delete_media_dirs(user_id, dry_run=dry_run)
    return отчёт


def _delete_media_dirs(user_id: int, dry_run: bool = False) -> int:
    """Удаляет каталоги приватных медиа: вложения переписки и фото тела.
    Возвращает число удалённых файлов.

    Каталогом целиком, а не по одному файлу: список файлов в базе может
    разойтись с диском (запись удалили, файл остался), и тогда перебор
    по записям оставил бы мусор. Каталог пользователя не содержит ничего,
    кроме его же файлов, поэтому удалять его безопасно.
    """
    корень = os.path.join(os.path.dirname(DB_PATH) or ".", "media")
    удалено = 0
    for вид in ("chat", "body"):
        каталог = os.path.join(корень, вид, str(int(user_id)))
        if not os.path.isdir(каталог):
            continue
        try:
            файлы = os.listdir(каталог)
        except OSError as e:
            print(f"[delete] каталог {каталог} не прочитан: {type(e).__name__}: {e}")
            continue
        удалено += len(файлы)
        if dry_run:
            continue
        try:
            shutil.rmtree(каталог)
        except OSError as e:
            # Не рушим удаление аккаунта из-за файлов: база уже вычищена,
            # вернуться к прежнему состоянию невозможно. Но и молчать нельзя
            print(f"[delete] каталог {каталог} не удалён: {type(e).__name__}: {e}")
            удалено -= len(файлы)
    return удалено


def _delete_avatar_file(user_id: int, dry_run: bool = False) -> int:
    """Удаляет /data/avatars/<id>.png. Возвращает 1, если файл был.

    Каскад чистил только базу, и аватар оставался на диске. Сам по себе
    осиротевший файл безвреден, но имя ему даёт id пользователя, а id в SQLite
    переиспользуются — новый человек получал бы в шапке чужое лицо. Второй
    рубеж против этого — AUTOINCREMENT, см. _migrate_users_autoincrement.

    Путь собирается здесь, а не берётся из main.py: импорт из main в database
    развернул бы зависимость наоборот и потянул за собой весь FastAPI.
    """
    каталог = os.path.join(os.path.dirname(DB_PATH) or ".", "avatars")
    путь = os.path.join(каталог, f"{user_id}.png")
    if not os.path.exists(путь):
        return 0
    if dry_run:
        return 1
    try:
        os.remove(путь)
    except OSError as e:
        # Не рушим удаление аккаунта из-за файла: база уже вычищена, и
        # возврат к прежнему состоянию невозможен. Но и молчать нельзя
        print(f"[delete] аватар {путь} не удалён: {type(e).__name__}: {e}")
        return 0
    return 1
