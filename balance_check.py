"""ОСТАТОК НА OPENROUTER И РЕШЕНИЕ, СЛАТЬ ЛИ ПРЕДУПРЕЖДЕНИЕ (BACKLOG №346).

Баланс однажды кончился МОЛЧА, и прод перестал отвечать. Раз в сутки
workflow `balance.yml` зовёт этот скрипт на машине прода (ключ живёт
только там, в секретах GitHub его нет) и по его решению шлёт сообщение
через тот же `telegram.sh`, что и бэкап.

Запрос остатка — `GET /api/v1/credits`, служебный и бесплатный: это не
вызов модели. Ключ не печатается никогда.

РЕШЕНИЕ СРАБАТЫВАЕТ НА ПЕРЕХОД, А НЕ НА УРОВЕНЬ, И НЕ ЧАЩЕ РАЗА В СУТКИ:

  · остаток ниже порога, предупреждение «взведено» и сегодня ещё
    не слали — слать;
  · предупреждение отправлено (`--mark`, зовёт workflow ПОСЛЕ
    удачной отправки) — снять взвод;
  · остаток снова не ниже порога — взвести: следующее падение снова
    даст сообщение.

Отметка ставится ПОСЛЕ отправки, а не при решении: не дошло сообщение
(Telegram недоступен) — взвод остаётся, и завтра попытка повторится.

Импорта `main` здесь нет и быть не должно (§5.8): второй процесс
с полным приложением на машине прода кладёт её по памяти.

Выход — строка `BALANCE_JSON={…}` (ключи латиницей, её разбирает jq),
код 0. Код 2 — остаток спросить нечем (нет ключа, сеть, не та форма
ответа): это «не проверено», а не «всё хорошо».
"""
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

import httpx

ПОРОГ = float(os.getenv("BALANCE_ALERT_USD", "3"))
АДРЕС = os.getenv("OPENROUTER_CREDITS_URL", "https://openrouter.ai/api/v1/credits")
DB_PATH = os.getenv("DB_PATH", "/data/app.db")
# Состояние — на томе рядом с базой: переживает перезапуск и деплой
СОСТОЯНИЕ = os.getenv("BALANCE_STATE",
                      os.path.join(os.path.dirname(DB_PATH) or ".", "balance_alert.json"))


def решить(остаток: float, состояние: dict, сегодня: str, порог: float = ПОРОГ):
    """(слать ли, новое состояние). Чистая функция — её и проверяют тесты."""
    новое = {"armed": состояние.get("armed", True),
             "last_alert_day": состояние.get("last_alert_day")}
    if остаток >= порог:
        новое["armed"] = True
        return False, новое
    слать = bool(новое["armed"]) and новое["last_alert_day"] != сегодня
    return слать, новое


def отметить(состояние: dict, сегодня: str) -> dict:
    return {"armed": False, "last_alert_day": сегодня}


def прочитать_состояние(путь: str = None) -> dict:
    путь = путь or СОСТОЯНИЕ
    try:
        with open(путь, encoding="utf-8") as f:
            д = json.load(f)
        return д if isinstance(д, dict) else {}
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        print(f"[balance] состояние не прочитано ({type(e).__name__}), беру пустое",
              file=sys.stderr)
        return {}


def записать_состояние(д: dict, путь: str = None) -> None:
    путь = путь or СОСТОЯНИЕ
    with open(путь, "w", encoding="utf-8") as f:
        json.dump(д, f)


def остаток_openrouter(ключ: str, адрес: str = АДРЕС) -> float:
    r = httpx.get(адрес, headers={"Authorization": f"Bearer {ключ}"}, timeout=30)
    r.raise_for_status()
    д = (r.json() or {}).get("data") or {}
    return float(д["total_credits"]) - float(д["total_usage"])


def расход_за_7_дней(db_path: str = DB_PATH, сейчас=None):
    """Сумма `model_usage.cost` за 7 суток; None — таблицы ещё нет."""
    сейчас = сейчас or datetime.now(timezone.utc).replace(tzinfo=None)
    с = (сейчас - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            сумма, вызовов = conn.execute(
                "SELECT COALESCE(SUM(cost), 0), COUNT(*) FROM model_usage "
                "WHERE created_at >= ?", (с,)).fetchone()
        finally:
            conn.close()
    except sqlite3.Error as e:
        print(f"[balance] расход из базы не прочитан: {type(e).__name__}: {e}",
              file=sys.stderr)
        return None
    return {"usd": round(float(сумма), 4), "calls": int(вызовов)}


def текст(остаток: float, расход, сегодня: str) -> str:
    строки = [f"OpenRouter: остаток {остаток:.2f} $ — ниже порога {ПОРОГ:.2f} $.",
              f"Дата: {сегодня} (UTC)."]
    if расход is None:
        строки.append("Расход за 7 дней: таблицы учёта нет.")
    else:
        строки.append(f"Расход за 7 дней по учёту: {расход['usd']:.2f} $, "
                      f"вызовов {расход['calls']} (учёт ведётся с 2026-09-18).")
    строки.append("Пополнить: openrouter.ai/settings/credits")
    return "\n".join(строки)


def main(argv):
    сегодня = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if "--mark" in argv:
        записать_состояние(отметить(прочитать_состояние(), сегодня))
        print("BALANCE_MARKED=1")
        return 0
    ключ = os.getenv("OPENROUTER_API_KEY", "")
    if not ключ:
        print("[balance] ПРОПУСК: ключа OpenRouter в окружении нет")
        return 2
    try:
        остаток = остаток_openrouter(ключ)
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as e:
        print(f"[balance] ПРОПУСК: остаток не получен: {type(e).__name__}: {str(e)[:200]}")
        return 2
    слать, новое = решить(остаток, прочитать_состояние(), сегодня)
    записать_состояние(новое)
    расход = расход_за_7_дней()
    print("BALANCE_JSON=" + json.dumps({
        "remaining": round(остаток, 2), "threshold": ПОРОГ, "send": слать,
        "spent7": расход, "text": текст(остаток, расход, сегодня) if слать else ""},
        ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
