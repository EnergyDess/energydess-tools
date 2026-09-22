"""СТАРТОВЫЕ ПРОВЕРКИ И ЗАМОК КОММИТА (задача 352, «аптечка-1», блок 1).

Правило CLAUDE.md §6.4 («проверки до правок») нарушалось три сессии
подряд: красное, найденное в конце, неотличимо от красного, заведённого
самой сессией. Уговоры не работают — нужен механизм.

    py start_checks.py [--копия ПУТЬ]   — прогнать ВСЁ и снять отметку
    py start_checks.py --hook           — вызывает pre-commit (.githooks)
    py start_checks.py --показать       — напечатать отметку и журнал обходов

ЧТО ГОНЯЕТСЯ. Основной ряд §6.0.2 и ряд стенда (`check_metrics`,
команды берутся из CLAUDE.md — своей копии здесь нет), реестр владельца
(`check_hh_owner.py`), витрина (`check_v2_showcase.py`) и pytest.
Проверки 47–60 входят в ряды. `--копия` — копия боевой базы для
проверки 26: без неё та честно отвечает «НЕ ПРОВЕРЕНО».

СТЕНД. Никто не слушает :8899 — стенд поднимается САМ (seed плюс
uvicorn) и гасится деревом процессов в конце. Слушает — берётся как есть
и не гасится: его поднял человек.

ОТМЕТКА — `.start_checks.json` (в .gitignore): HEAD, id сессии Claude
Code, время и «проверка → код, время». Снимается ДО первой правки.

ЗАМОК (`--hook`). Коммит проходит, только если отметка:
  · есть;
  · снята на коммите, который является ПРЕДКОМ (или равен) текущего HEAD —
    отметка от другой ветки истории не годится;
  · снята В ЭТОЙ ЖЕ СЕССИИ (`CLAUDE_CODE_SESSION_ID`). Без этого
    условия отметка прошлой сессии проходила бы: её коммит — предок
    сегодняшнего HEAD. Вне Claude Code (переменной нет) вместо сессии
    спрашивается возраст отметки: не старше `ВОЗРАСТ_ЧАСОВ`.
После первого коммита следующий опирается на ту же отметку: перепрогон
на каждый коммит не требуется.

ОБХОД — только явной переменной `START_CHECKS_BYPASS=1`, и каждое
использование пишется строкой в `start_checks_bypass.log` (в .gitignore),
который попадает в отчёт.

ГРАНИЦА. Замок проверяет, что проверки ПРОГОНЯЛИСЬ на старте, а не что
они зелёные: красное на старте законно — его обязаны назвать первой
строкой отчёта, а не скрыть.
"""
import datetime as _dt
import io
import json
import os
import socket
import subprocess
import sys
import time

КОРЕНЬ = os.path.dirname(os.path.abspath(__file__))
ОТМЕТКА = os.path.join(КОРЕНЬ, ".start_checks.json")
ЖУРНАЛ_ОБХОДОВ = os.path.join(КОРЕНЬ, "start_checks_bypass.log")
ВОЗРАСТ_ЧАСОВ = 24
ПОРТ = 8899
ПОТОЛОК = int(os.environ.get("START_CHECKS_TIMEOUT", "2400"))
ОШИБКА_ХУКА = "Сначала start_checks на стартовом коммите"


def _git(*аргументы):
    return subprocess.run(["git", *аргументы], cwd=КОРЕНЬ, capture_output=True,
                          text=True, encoding="utf-8", errors="replace")


def _head():
    return _git("rev-parse", "HEAD").stdout.strip()


def _сессия():
    return os.environ.get("CLAUDE_CODE_SESSION_ID", "")


def _слушает(порт):
    with socket.socket() as с:
        с.settimeout(0.5)
        return с.connect_ex(("127.0.0.1", порт)) == 0


# ── ПРОГОН ───────────────────────────────────────────────────────────

def _скрипт(имя, *аргументы, env=None):
    начало = time.monotonic()
    try:
        п = subprocess.run([sys.executable, имя, *аргументы], cwd=КОРЕНЬ,
                           capture_output=True, text=True, errors="replace",
                           timeout=ПОТОЛОК, env=env)
        код = str(п.returncode)
        if "Traceback (most recent call last)" in (п.stderr or ""):
            код = "УПАЛА: " + (п.stderr.strip().splitlines() or ["трасса"])[-1][:60]
    except subprocess.TimeoutExpired:
        код = "ОБОРВАНА по потолку %d с" % ПОТОЛОК
    return код, time.monotonic() - начало


def _поднять_стенд():
    """(процесс|None). None — стенд уже слушал, его не трогаем."""
    if _слушает(ПОРТ):
        print("  стенд :%d уже слушает — беру как есть" % ПОРТ, flush=True)
        return None
    print("  стенд не поднят — сею и поднимаю :%d" % ПОРТ, flush=True)
    subprocess.run([sys.executable, "make_local_user.py", "--seed"], cwd=КОРЕНЬ,
                   capture_output=True, timeout=600)
    журнал = open(os.path.join(КОРЕНЬ, ".start_checks_stand.log"), "w")
    п = subprocess.Popen([sys.executable, "-m", "uvicorn", "main:app",
                          "--port", str(ПОРТ)], cwd=КОРЕНЬ,
                         stdout=журнал, stderr=subprocess.STDOUT)
    for _ in range(120):
        if _слушает(ПОРТ):
            return п
        time.sleep(0.5)
    raise SystemExit("стенд не поднялся за 60 с — см. .start_checks_stand.log")


def _погасить(п):
    if п is None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(п.pid)],
                       capture_output=True)
    else:
        п.kill()


def прогнать(копия=None):
    sys.path.insert(0, КОРЕНЬ)
    head = _head()
    if копия:
        os.environ["MEDKIT_GUARD_DB"] = os.path.abspath(копия)
    import check_metrics as м
    итог = []           # [(проверка, код, секунды)]
    начало_всего = time.monotonic()

    print("■ основной ряд §6.0.2", flush=True)
    значения, порядок = м.ряд_проверок()
    # ПЕРВОЕ ЧИСЛО — ПО ДОЛГУ, А НЕ ПО ПОЛНОМУ ЧИСЛУ СТРОК (§6.0.2): полное
    # несёт и законную раскладку экземпляра и было бы «красным» всегда
    разбивка = м.первое_число_в_разбивке() or []
    долг1 = sum(1 for р in разбивка if р[3])
    for н in порядок:
        код = значения.get(н, "?")
        if н == "1":
            код = "%s, долг %d" % (код, долг1)
        итог.append(("ряд %s" % н, код, round(м.ВРЕМЕНА.get(н, 0.0), 1)))

    стенд = _поднять_стенд()
    try:
        print("■ ряд стенда", flush=True)
        for н, _к, код in м.ряд_стенда(True):
            итог.append(("стенд %s" % н, str(код), round(м.ВРЕМЕНА.get(н, 0.0), 1)))
        for имя in ("check_hh_owner.py", "check_v2_showcase.py"):
            print("■ " + имя, flush=True)
            код, с = _скрипт(имя)
            итог.append((имя, код, round(с, 1)))
    finally:
        _погасить(стенд)
        # пробы стенда пишут в базу — возвращаем посев (§6.0.18)
        subprocess.run([sys.executable, "make_local_user.py", "--seed"],
                       cwd=КОРЕНЬ, capture_output=True, timeout=600)

    print("■ pytest", flush=True)
    нач = time.monotonic()
    прошло, упало, код = м.тесты()
    итог.append(("pytest (прошло %s, упало %s)" % (прошло, упало), str(код),
                 round(time.monotonic() - нач, 1)))

    отметка = {
        "head": head,
        "session": _сессия(),
        "time": _dt.datetime.now().isoformat(timespec="seconds"),
        "seconds_total": round(time.monotonic() - начало_всего),
        "checks": [{"check": п, "code": к, "seconds": с} for п, к, с in итог],
    }
    io.open(ОТМЕТКА, "w", encoding="utf-8").write(
        json.dumps(отметка, ensure_ascii=False, indent=1))
    _печать(отметка)


def _зелёная(код):
    return код == "0" or код.endswith(", долг 0")


def _печать(отметка):
    красные = [c for c in отметка["checks"] if not _зелёная(c["code"])
               and not c["code"].startswith(("НЕ ПРОВЕРЕНО", "ОБОРВАНА",
                                             "не запустился", "не скрипт"))]
    непрогнанные = [c for c in отметка["checks"]
                    if c["code"].startswith(("НЕ ПРОВЕРЕНО", "ОБОРВАНА",
                                             "не запустился", "не скрипт"))]
    print("\nОТМЕТКА: HEAD %s, %s, проверок %d, %d с"
          % (отметка["head"][:7], отметка["time"], len(отметка["checks"]),
             отметка.get("seconds_total", 0)))
    print("  КРАСНЫЕ: %s" % ("нет" if not красные else "; ".join(
        "%s → %s" % (c["check"], c["code"]) for c in красные)))
    print("  НЕ ПРОГНАНЫ: %s" % ("нет" if not непрогнанные else "; ".join(
        "%s → %s" % (c["check"], c["code"]) for c in непрогнанные)))


# ── ЗАМОК ────────────────────────────────────────────────────────────

def _отказ(причина):
    sys.stderr.write("pre-commit: %s. %s.\n" % (ОШИБКА_ХУКА, причина))
    return 1


def хук():
    if os.environ.get("START_CHECKS_BYPASS") == "1":
        with io.open(ЖУРНАЛ_ОБХОДОВ, "a", encoding="utf-8") as ж:
            ж.write("%s\tHEAD %s\tсессия %s\tОБХОД ЗАМКА\n" % (
                _dt.datetime.now().isoformat(timespec="seconds"),
                _head()[:12], _сессия() or "-"))
        sys.stderr.write("pre-commit: ОБХОД START_CHECKS_BYPASS=1 — записан "
                         "в start_checks_bypass.log\n")
        return 0
    if not os.path.exists(ОТМЕТКА):
        return _отказ("Отметки .start_checks.json нет")
    try:
        отметка = json.loads(io.open(ОТМЕТКА, encoding="utf-8").read())
    except ValueError:
        return _отказ("Отметка не читается")
    head = _head()
    if head and отметка.get("head") != head and _git(
            "merge-base", "--is-ancestor", отметка.get("head", ""), head
    ).returncode != 0:
        return _отказ("Отметка снята на %s, это не предок HEAD %s"
                      % (отметка.get("head", "?")[:7], head[:7]))
    сессия = _сессия()
    if сессия:
        if отметка.get("session") != сессия:
            return _отказ("Отметка снята в другой сессии")
    else:
        try:
            возраст = _dt.datetime.now() - _dt.datetime.fromisoformat(отметка["time"])
        except (KeyError, ValueError):
            return _отказ("В отметке нет времени")
        if возраст.total_seconds() > ВОЗРАСТ_ЧАСОВ * 3600:
            return _отказ("Отметка старше %d ч" % ВОЗРАСТ_ЧАСОВ)
    return 0


def показать():
    if os.path.exists(ОТМЕТКА):
        _печать(json.loads(io.open(ОТМЕТКА, encoding="utf-8").read()))
    else:
        print("отметки нет")
    print("\nЖУРНАЛ ОБХОДОВ:")
    print(io.open(ЖУРНАЛ_ОБХОДОВ, encoding="utf-8").read().rstrip()
          if os.path.exists(ЖУРНАЛ_ОБХОДОВ) else "  пусто")


if __name__ == "__main__":
    for _п in (sys.stdout, sys.stderr):
        try:
            _п.reconfigure(encoding="utf-8")
        except AttributeError:
            pass
    if "--hook" in sys.argv:
        sys.exit(хук())
    if "--показать" in sys.argv:
        показать()
        sys.exit(0)
    копия = sys.argv[sys.argv.index("--копия") + 1] if "--копия" in sys.argv else None
    # ОДИН видимый браузер на весь прогон (§6.0.3): основной ряд тоже
    # гоняет пробы (`check_probe_start --быстро`)
    import browser_window
    with browser_window.общий_браузер():
        прогнать(копия)
