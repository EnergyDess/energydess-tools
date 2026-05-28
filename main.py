from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from bs4 import BeautifulSoup
import httpx
import os
import re
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="EnergyDess Tools")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
MODEL = os.getenv("MODEL", "anthropic/claude-haiku-4-5")

PORTFOLIO = (
    "AI-портфолио: https://disk.yandex.ru/d/jqvXMaCUNAbvng\n"
    "Портфолио монтажа: https://disk.yandex.ru/d/PFdacTDoN_iwPA"
)

RESUME = """
Кащеев Денис Алексеевич
28 лет | AI Video Creator | Удалённая работа | Балашиха (Московская область)

ОПЫТ РАБОТЫ (11 лет 4 месяца):

Shortly (Армения, shortly.show) — AI Video Creator | Июнь 2025 — Апрель 2026
Полный цикл производства AI-сериалов для международной стриминговой платформы: от концепции до финального ролика.
Генерация персонажей, локаций и раскадровок в Midjourney, Runway ML, Kling AI, Sora.
Написание сценариев и диалогов. Озвучка и lip-sync через ElevenLabs и HeyGen.
Монтаж, саунд-дизайн, цветокоррекция в Adobe Premiere Pro и After Effects.
Ежедневная выдача нормы контента в жёстких дедлайнах. Работа как в команде, так и самостоятельно.

Pulsar Production (Москва) — Режиссер монтажа | Сентябрь 2022 — Май 2025
Монтаж коммерческих роликов: обучающие курсы, корпоративные видео, промо-материалы.
Работа с многослойными проектами в Premiere Pro и After Effects, графика, субтитры, анимация.

RUhub (Москва) — Режиссер монтажа | Июль 2024 — Февраль 2025
Монтаж киберспортивного контента для YouTube и соцсетей: турнирные хайлайты, промо-ролики.
Работа с динамичным монтажом и спортивной графикой.

LanGame (Москва) — Режиссер монтажа | Июнь 2023 — Октябрь 2023
Монтаж роликов для YouTube-канала о киберспорте. Адаптация форматов под YouTube, VK, Telegram.

MedX.pro (Москва) — Режиссер монтажа | Декабрь 2021 — Ноябрь 2022
Монтаж образовательных видеокурсов медицинской тематики. Графика, субтитры, анимация для сложных тем.

Moon video — Режиссер монтажа | Июнь 2021 — Апрель 2022
Съёмка и монтаж рекламных роликов, корпоративных интервью, YouTube-форматов.
Настройка и ведение прямых эфиров. Полный цикл от съёмки до финального рендера.

Россия-1 (Москва) — Режиссер монтажа | Октябрь 2021 — Декабрь 2021
Монтаж сюжетов для федеральной программы «60 минут». Жёсткие эфирные дедлайны.

YouTube канал EnergyDess — Основатель/монтажёр | Январь 2015 — Август 2021
Создание YouTube-канала с нуля: съёмка, монтаж, написание сценариев, SEO-оптимизация.
Настройка рекламных кампаний. 6 лет самостоятельного ведения полного производственного цикла.

Образовательный холдинг «Синергия» (Москва) — Монтажер | Январь 2019 — Январь 2020
Монтаж учебных видеоматериалов для онлайн-платформы. Лекционный и тренинговый контент.

ОБРАЗОВАНИЕ:
Гуманитарный институт телевидения и радиовещания им. М.А. Литовчина, Москва (2021)
Продюсерский факультет — Продюсерство кино и телевидения

НАВЫКИ:
AI-инструменты: Midjourney, Runway ML, Kling AI, ElevenLabs, HeyGen, Sora, ChatGPT, Claude Code, Seedance, VEO, Banana Pro, Grok, SDream
Видеопроизводство: Adobe Premiere Pro, Adobe After Effects, Adobe Photoshop
Специализация: Цветокоррекция, Саунд-дизайн, Видеомонтаж, Моушн-дизайн, Сценаристика, Режиссура
Языки: Русский (родной), Английский

О СЕБЕ:
AI Video Creator с опытом полного цикла производства контента. Последний год работал в международной
продакшн-студии Shortly, где ежедневно создавал AI-сериалы от сценария до финального ролика.
За плечами 10+ лет в видеопроизводстве: монтаж для федерального ТВ, киберспорта, образования и рекламы.
Портфолио — 100+ проектов разных форматов и жанров.
Ищу удалённую работу в команде, где AI — это не эксперимент, а рабочий инструмент.
Желаемая зарплата: 220 000 ₽ на руки.
"""


def extract_text_from_html(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "meta", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    # убираем дублирующиеся строки и мусор короче 3 символов
    seen = set()
    clean = []
    for line in lines:
        if len(line) < 3 or line in seen:
            continue
        seen.add(line)
        clean.append(line)
    return "\n".join(clean)


@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.get("/hh")
async def hh_page(request: Request):
    return templates.TemplateResponse(request=request, name="hh.html")


@app.post("/api/fetch-url")
async def fetch_url(request: Request):
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
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    ),
                    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
                },
                timeout=15.0,
            )

        if resp.status_code != 200:
            return JSONResponse(
                {"error": f"Сайт вернул ошибку {resp.status_code}. Попробуй скопировать текст вручную."},
                status_code=400,
            )

        text = extract_text_from_html(resp.text)

        if len(text) < 100:
            return JSONResponse(
                {"error": "Не удалось извлечь текст. Сайт мог заблокировать парсинг — скопируй текст вручную."},
                status_code=400,
            )

        # обрезаем до разумного размера
        if len(text) > 8000:
            text = text[:8000]

        return JSONResponse({"text": text})

    except httpx.TimeoutException:
        return JSONResponse({"error": "Сайт не ответил вовремя. Скопируй текст вручную."}, status_code=504)
    except Exception as e:
        return JSONResponse({"error": f"Не удалось загрузить страницу: {str(e)}"}, status_code=500)


@app.post("/api/generate-letter")
async def generate_letter(request: Request):
    data = await request.json()
    job_text = data.get("job_text", "").strip()

    if not job_text:
        return JSONResponse({"error": "Вставь текст вакансии"}, status_code=400)

    if not OPENROUTER_API_KEY:
        return JSONResponse({"error": "API ключ не настроен. Добавь OPENROUTER_API_KEY в файл .env"}, status_code=500)

    prompt = f"""Ты помогаешь написать сопроводительное письмо для соискателя.

РЕЗЮМЕ СОИСКАТЕЛЯ:
{RESUME}

ТЕКСТ ВАКАНСИИ:
{job_text}

Напиши ТОЛЬКО основной текст письма (100-180 слов). Строгие правила:

НАЧАЛО — первая строка письма ВСЕГДА должна быть точно такой:
"Здравствуйте, меня зовут Денис Кащеев."

ОСНОВНОЙ ТЕКСТ:
- После приветствия — живое, цепляющее продолжение, покажи понимание сути вакансии
- Выдели 2-3 конкретных пункта опыта, максимально соответствующих требованиям
- Если в вакансии есть конкретные вопросы к кандидату — ответь на них
- Пиши от первого лица, живым языком, без штампов и клише
- Не используй слова: синергия, результативный, коммуникабельный, стрессоустойчивый, ответственный
- Тон: уверенный профессионал, не заискивающий

КОНЕЦ — после основного текста, на отдельной строке ВСЕГДА добавляй дословно:
"Вот моё AI-портфолио: https://disk.yandex.ru/d/jqvXMaCUNAbvng и портфолио монтажа: https://disk.yandex.ru/d/PFdacTDoN_iwPA"

ЗАПРЕЩЕНО:
- Любая подпись ("С уважением", "Денис", "Кащеев" и т.п.) — письмо заканчивается ссылками
- Вводные фразы типа "Вот письмо:", "Конечно!", "Здесь письмо:"
- Имя или фамилия в конце письма
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

        # гарантируем правильное начало если модель забыла
        greeting = "Здравствуйте, меня зовут Денис Кащеев."
        if not letter.startswith(greeting):
            # убираем всё до первого "Здравствуйте" если оно есть
            idx = letter.find("Здравствуйте")
            if idx > 0:
                letter = letter[idx:]
            else:
                letter = greeting + "\n\n" + letter

        # гарантируем ссылки на портфолио в конце
        portfolio_url = "https://disk.yandex.ru/d/jqvXMaCUNAbvng"
        if portfolio_url not in letter:
            letter = (
                letter.rstrip()
                + "\n\nВот моё AI-портфолио: https://disk.yandex.ru/d/jqvXMaCUNAbvng"
                + " и портфолио монтажа: https://disk.yandex.ru/d/PFdacTDoN_iwPA"
            )

        # убираем подпись в конце (одиночные строки из 1-3 слов после последней ссылки)
        lines = letter.rstrip().split("\n")
        while lines and re.match(r"^[А-ЯЁA-Z][а-яёa-z\s]{0,30}$", lines[-1].strip()):
            lines.pop()
        letter = "\n".join(lines)

        return JSONResponse({"letter": letter})

    except httpx.TimeoutException:
        return JSONResponse({"error": "Превышено время ожидания. Попробуй ещё раз."}, status_code=504)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
