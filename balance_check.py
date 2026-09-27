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

ИСТОРИЯ ОСТАТКА (№352, письмо «Расход», 1.1). Каждый запуск кладёт
остаток в `balance_history` — одна строка на МОСКОВСКИЕ сутки,
повторный запуск в те же сутки строку не добавляет. Итог — поле
`history` в BALANCE_JSON: `added`, `exists` либо `no_table` (база
старше выкатки — таблицу заводит приложение при старте).

ВСПЛЕСК РАСХОДА (1.2). Расход вчерашних суток (МСК) больше ТРЁХ медиан
расхода за четырнадцать суток до них — второе предупреждение тем же
каналом. Считаются только сутки, в которые учёт вёл хоть одну строку:
день без вызовов — не «ноль», а отсутствие данных, и медиана по таким
дням съехала бы к нулю, а за ней сработал бы любой обычный день. Дней
с данными меньше семи — порог МОЛЧИТ: сравнивать не с чем.

ОТМЕТКА «ОТПРАВЛЕНО» ПО КАЖДОМУ ВИДУ СВОЯ. Решение пишет в состояние
`pending` — что именно решено слать; `--mark` отмечает ровно это.
Иначе отметка всплеска сняла бы взвод остатка, которого не слали.
"""
import json
import os
import sqlite3
import statistics
import sys
from datetime import date, datetime, time as _время, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx

ПОРОГ = float(os.getenv("BALANCE_ALERT_USD", "3"))
# Сутки истории и всплеска — московские, как всё время на странице расхода
ПОЯС = ZoneInfo("Europe/Moscow")
ВСПЛЕСК_КРАТНОСТЬ = float(os.getenv("SPIKE_FACTOR", "3"))
ВСПЛЕСК_ОКНО = 14      # суток до проверяемых
ВСПЛЕСК_МИНИМУМ = 7    # суток с данными, без которых порог молчит
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


def день_мск(момент_utc: datetime) -> str:
    """Наивное UTC → московская дата строкой ГГГГ-ММ-ДД."""
    return момент_utc.replace(tzinfo=timezone.utc).astimezone(ПОЯС).strftime("%Y-%m-%d")


def записать_историю(остаток: float, момент_utc: datetime = None,
                     db_path: str = None) -> str:
    """Строка в `balance_history`: `added`, `exists` либо `no_table`.

    Одна на московские сутки: ключ `day` уникален, повтор отбрасывает
    сама база (`INSERT OR IGNORE`), а не проверка перед вставкой — два
    запуска подряд не проскочат в щель между «проверил» и «вставил».
    Формат времени тот же, каким SQLAlchemy пишет DateTime в SQLite,
    иначе страница прочитала бы строку не той датой."""
    момент_utc = момент_utc or datetime.now(timezone.utc).replace(tzinfo=None)
    conn = sqlite3.connect(db_path or DB_PATH, timeout=10)
    try:
        курсор = conn.execute(
            "INSERT OR IGNORE INTO balance_history (day, created_at, remaining) "
            "VALUES (?, ?, ?)",
            (день_мск(момент_utc), момент_utc.strftime("%Y-%m-%d %H:%M:%S.%f"),
             round(float(остаток), 4)))
        conn.commit()
        return "added" if курсор.rowcount == 1 else "exists"
    except sqlite3.OperationalError as e:
        if "no such table" in str(e):
            return "no_table"
        raise
    finally:
        conn.close()


def расход_по_дням(db_path: str = None, до_дня: str = None, дней: int = ВСПЛЕСК_ОКНО + 1):
    """({день: $}, {день: строк}) за `дней` московских суток по `до_дня` включительно.

    None — таблицы учёта нет. Сумма — по тем же строкам, что на странице:
    удачный вызов с ценой; «строк» — все, включая неудачные: по ним
    видно, что учёт в эти сутки вёлся."""
    до = date.fromisoformat(до_дня) if до_дня else datetime.now(ПОЯС).date()
    с_дня = до - timedelta(days=дней - 1)
    с_utc = datetime.combine(с_дня, _время(0), ПОЯС).astimezone(timezone.utc).replace(tzinfo=None)
    try:
        conn = sqlite3.connect(f"file:{db_path or DB_PATH}?mode=ro", uri=True)
        try:
            строки = conn.execute(
                "SELECT created_at, CASE WHEN ok = 1 AND cost IS NOT NULL "
                "AND COALESCE(cost_missing, 0) = 0 THEN cost ELSE 0 END "
                "FROM model_usage WHERE created_at >= ?",
                (с_utc.strftime("%Y-%m-%d %H:%M:%S"),)).fetchall()
        finally:
            conn.close()
    except sqlite3.Error as e:
        print(f"[balance] расход по дням не прочитан: {type(e).__name__}: {e}",
              file=sys.stderr)
        return None
    суммы, строк = {}, {}
    for момент, цена in строки:
        д = день_мск(datetime.fromisoformat(момент))
        if д > до.isoformat():
            continue
        суммы[д] = суммы.get(д, 0.0) + float(цена or 0)
        строк[д] = строк.get(д, 0) + 1
    return суммы, строк


def всплеск(суммы: dict, строк: dict, день: str, кратность: float = ВСПЛЕСК_КРАТНОСТЬ,
            окно: int = ВСПЛЕСК_ОКНО, минимум: int = ВСПЛЕСК_МИНИМУМ) -> dict:
    """Решение о всплеске за `день`. Чистая функция — её зовут и страница,
    и тесты; второй реализации порога в проекте нет.

    Медиана — по суткам окна, в которые учёт вёл хоть одну строку.
    Медиана ноль — сравнивать не с чем: «втрое больше нуля» дал бы
    любой платный день."""
    д0 = date.fromisoformat(день)
    прошлые = [(д0 - timedelta(days=i)).isoformat() for i in range(1, окно + 1)]
    с_данными = [д for д in прошлые if строк.get(д, 0) > 0]
    итог = {"день": день, "сумма": round(суммы.get(день, 0.0), 6), "дней": len(с_данными),
            "нужно": минимум, "медиана": None, "порог": None, "сработал": False}
    if len(с_данными) < минимум:
        итог["причина"] = "мало данных"
        return итог
    медиана = statistics.median(суммы.get(д, 0.0) for д in с_данными)
    итог["медиана"] = round(медиана, 6)
    итог["порог"] = round(кратность * медиана, 6)
    if медиана <= 0:
        итог["причина"] = "медиана ноль"
        return итог
    итог["сработал"] = суммы.get(день, 0.0) > кратность * медиана
    итог["причина"] = "выше порога" if итог["сработал"] else "в норме"
    return итог


def текст_всплеска(в: dict) -> str:
    return (f"OpenRouter: расход за {в['день']} (МСК) {в['сумма']:.2f} $ — больше "
            f"{ВСПЛЕСК_КРАТНОСТЬ:g} медиан за {ВСПЛЕСК_ОКНО} дней "
            f"(медиана {в['медиана']:.2f} $, дней с данными {в['дней']}).\n"
            "Разбор по инструментам: energydess.ru/admin/usage")


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


def отметить_отправленное(состояние: dict, сегодня: str) -> dict:
    """`--mark`: отметить ровно то, что решение положило в `pending`.

    Состояние старше письма «Расход» поля `pending` не знает — тогда
    отмечается остаток, как было: иного вида предупреждений тогда не было."""
    ожидание = состояние.get("pending")
    if ожидание is None:
        ожидание = ["balance"]
    новое = dict(состояние)
    if "balance" in ожидание:
        новое.update(отметить(состояние, сегодня))
    if "spike" in ожидание and состояние.get("spike_day"):
        новое["spike_alert_day"] = состояние["spike_day"]
    новое["pending"] = []
    return новое


def main(argv):
    сейчас_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    сегодня = сейчас_utc.strftime("%Y-%m-%d")
    if "--mark" in argv:
        записать_состояние(отметить_отправленное(прочитать_состояние(), сегодня))
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
    # История пишется ДО решения о предупреждениях: её судьба от порога
    # не зависит, а сбой записи не должен съесть предупреждение
    try:
        история = записать_историю(остаток, сейчас_utc)
    except sqlite3.Error as e:
        print(f"[balance] история не записана: {type(e).__name__}: {e}", file=sys.stderr)
        история = "error"
    состояние = прочитать_состояние()
    слать_остаток, новое = решить(остаток, состояние, сегодня)
    вчера = (datetime.now(ПОЯС).date() - timedelta(days=1)).isoformat()
    по_дням = расход_по_дням(до_дня=вчера)
    всп = (всплеск(*по_дням, вчера) if по_дням is not None
           else {"день": вчера, "сработал": False, "причина": "нет учёта"})
    слать_всплеск = bool(всп["сработал"]) and состояние.get("spike_alert_day") != вчера
    # `решить` отдаёт только поля остатка — поля всплеска переносятся здесь,
    # иначе отметка «уже слали за этот день» терялась бы на каждом запуске
    новое["spike_alert_day"] = состояние.get("spike_alert_day")
    новое["spike_day"] = вчера
    новое["pending"] = [в for в, слать in (("balance", слать_остаток),
                                           ("spike", слать_всплеск)) if слать]
    записать_состояние(новое)
    расход = расход_за_7_дней()
    тексты = []
    if слать_остаток:
        тексты.append(текст(остаток, расход, сегодня))
    if слать_всплеск:
        тексты.append(текст_всплеска(всп))
    # Ключи строки — ЛАТИНИЦЕЙ: её разбирает jq в workflow (§6.0)
    print("BALANCE_JSON=" + json.dumps({
        "remaining": round(остаток, 2), "threshold": ПОРОГ,
        "send": bool(новое["pending"]), "alerts": новое["pending"],
        "history": история,
        "spike": {"day": всп["день"], "usd": всп.get("сумма"), "days": всп.get("дней"),
                  "median": всп.get("медиана"), "fired": bool(всп["сработал"]),
                  "sent": слать_всплеск},
        "spent7": расход, "text": "\n\n".join(тексты)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
