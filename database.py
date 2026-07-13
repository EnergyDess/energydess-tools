from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean, Float, JSON
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime
import os
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


class CoverLetter(Base):
    __tablename__ = "cover_letters"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    job_title = Column(String, nullable=True)
    company_name = Column(String, nullable=True)
    job_text = Column(Text, nullable=False)
    letter_text = Column(Text, nullable=False)
    analysis_json = Column(JSON, nullable=True)
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
    image_data = Column(Text, nullable=True)  # миниатюра прикреплённого фото (data URL), если было
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
    (см. zepp_client.py). Логин/пароль хранятся зашифрованными (Fernet,
    ключ — CREDENTIALS_ENCRYPTION_KEY). app_token/zepp_user_id — кеш токена
    сессии, чтобы не логиниться паролем при каждой синхронизации: полный
    логин по паролю разлогинивает пользователя в мобильном приложении
    Zepp Life (особенность их серверной сессии, не наша)."""
    __tablename__ = "scale_connections"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, unique=True, nullable=False, index=True)
    encrypted_username = Column(Text, nullable=False)
    encrypted_password = Column(Text, nullable=False)
    app_token = Column(Text, nullable=True)
    zepp_user_id = Column(String, nullable=True)
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
    image_data = Column(Text, nullable=False)  # data URL, как ChatMessage.image_data
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
    ]:
        try:
            conn.execute(backfill)
        except Exception:
            pass
    conn.commit()
    conn.close()
