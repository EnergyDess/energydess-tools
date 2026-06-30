# -*- coding: utf-8 -*-
"""Импорт youtube_id для упражнений из exercises (поиск через YouTube Data API v3).

Квота: search.list стоит 100 unit за запрос, бесплатный лимит — 10 000 unit/сутки.
Поэтому скрипт обрабатывает не больше DAILY_LIMIT упражнений за один запуск
(по умолчанию 90 — это 9000 unit, с запасом). Упражнения без видео помечаются
youtube_id = "" (пустая строка, не NULL), чтобы при повторном запуске скрипт
не тратил квоту на повторный поиск того же упражнения. Запускать раз в день,
пока не останется упражнений с youtube_id IS NULL (~10 дней на 873 упражнения).
"""
import os
import sys
import time

import httpx
from dotenv import load_dotenv

load_dotenv()

from database import SessionLocal, Exercise  # noqa: E402

API_KEY = os.getenv("YOUTUBE_API_KEY")
DAILY_LIMIT = 90
SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"


def find_video_id(query: str) -> str:
    """Возвращает videoId первого подходящего результата или '' если ничего не найдено."""
    params = {
        "part": "snippet",
        "q": query,
        "type": "video",
        "maxResults": 1,
        "relevanceLanguage": "ru",
        "videoEmbeddable": "true",
        "safeSearch": "moderate",
        "key": API_KEY,
    }
    resp = httpx.get(SEARCH_URL, params=params, timeout=15)
    if resp.status_code == 403:
        raise RuntimeError(f"Квота исчерпана или ключ невалиден: {resp.text[:300]}")
    resp.raise_for_status()
    items = resp.json().get("items", [])
    if not items:
        return ""
    return items[0]["id"]["videoId"]


def main():
    if not API_KEY:
        print("YOUTUBE_API_KEY не задан в .env")
        sys.exit(1)

    db = SessionLocal()
    try:
        pending = (
            db.query(Exercise)
            .filter(Exercise.youtube_id.is_(None))
            .order_by(Exercise.id)
            .limit(DAILY_LIMIT)
            .all()
        )
        if not pending:
            total = db.query(Exercise).count()
            with_video = db.query(Exercise).filter(Exercise.youtube_id != "").filter(Exercise.youtube_id.isnot(None)).count()
            print(f"Все упражнения обработаны. С видео: {with_video}/{total}")
            return

        print(f"К обработке сегодня: {len(pending)}")
        found = 0
        for i, ex in enumerate(pending, 1):
            query = f"{ex.name_ru} техника выполнения"
            try:
                video_id = find_video_id(query)
            except RuntimeError as e:
                print(f"[{i}/{len(pending)}] ОСТАНОВКА: {e}")
                db.commit()
                return
            ex.youtube_id = video_id
            db.commit()
            if video_id:
                found += 1
                print(f"[{i}/{len(pending)}] {ex.name_ru} -> {video_id}")
            else:
                print(f"[{i}/{len(pending)}] {ex.name_ru} -> не найдено")
            time.sleep(0.2)

        remaining = db.query(Exercise).filter(Exercise.youtube_id.is_(None)).count()
        print(f"Готово. Найдено видео: {found}/{len(pending)}. Осталось необработанных: {remaining}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
