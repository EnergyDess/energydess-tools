"""ТЯЖЁЛАЯ ЗАДАЧА «КОНТЕНТА» НЕ КЛАДЁТ САЙТ (авария 2026-09-30).

ПРОВЕРКА, код 1 при беде, 2 — стенд не поднялся. Поднимает приложение
СВОИМ процессом на копии базы стенда с включённым планировщиком
и «археологией», которая ведёт себя как настоящая: синхронный счёт
на каждом канале (медиана выстрела) плюс ожидание сети. Внешних вызовов
нет: сбор источников, сюжеты и идеи подменены пустышками, ключ YouTube
выдуманный.

Во время прогона спрашивает:
  · 10 запросов к /health и 10 к /content — каждый быстрее 1 с;
  · повторный запуск — отказ 409 словами, второй прогон НЕ стартовал;
  · ход прогона в базе и в /content/api/state («Идёт: N из M · ~K мин»);
  · память процесса до и во время прогона;
  · `--ошибка`: исключение в середине прогона → «ошибка» с текстом,
    кнопка снова свободна, сайт отвечает.

ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ: `MAIN_DIR=<worktree на коде до правки>` —
тот же сценарий на прежнем коде обязан показать зависание (планировщик
крутится без паузы, /health не отвечает).
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time

import probe_guard  # noqa: F401

import httpx

ЗДЕСЬ = os.path.dirname(os.path.abspath(__file__))
ПРОЕКТ = os.environ.get("MAIN_DIR") or ЗДЕСЬ
ОШИБКА = "--ошибка" in sys.argv
ПОРОГ = 1.0

ЗАПУСК = r'''
import asyncio, os, sys, time, statistics, random
sys.path.insert(0, os.environ["MAIN_DIR"])
os.chdir(os.environ["MAIN_DIR"])
import main, uvicorn
import content_engine as ce, content_collect as cc, content_db as cdb, content_ideas as ci
cw = sys.modules.get("content_worker")

async def _источник(client, тема, и, шаблон, настройки):
    return {"id": и["id"], "state": "ok"}
async def _сюжеты(тема, настройки):
    return {}
ce._собрать_источник = _источник
ce._сюжеты = _сюжеты
ce._археология_нужна = lambda: False
ci.проверить_расписание = lambda: None
_настройка = cdb.настройка
def настройка(db, ключ):
    н = dict(_настройка(db, ключ) or {})
    if ключ == "cycle":
        н["first_delay_sec"], н["minutes"] = 1, 0.05     # цикл «пора» каждые 3 с
    return н
cdb.настройка = настройка

КАНАЛОВ = 40
async def хиты(client, база, ключ, квота, п, метки=None):
    for i in range(КАНАЛОВ):
        if cw: cw.ход("ролики каналов", i, КАНАЛОВ)
        ролики = [random.random() for _ in range(20000)]
        for _ in range(3):                    # синхронный счёт, как медиана выстрела
            statistics.median(ролики)
        if os.environ.get("FAKE_FAIL") and i == 10:
            raise RuntimeError("подложенная ошибка на 11-м канале")
        await asyncio.sleep(0.25)             # сеть YouTube
    return {"каналы_en": [], "каналы_ru": [], "хитов_поиска": 0, "ролики": []}
cc.хиты_выстрела = хиты
uvicorn.run(main.app, host="127.0.0.1", port=int(os.environ["PORT"]), log_level="warning")
'''


def _порт() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    п = s.getsockname()[1]
    s.close()
    return п


def _rss(pid: int) -> float | None:
    try:
        import psutil
        return psutil.Process(pid).memory_info().rss / 1e6
    except Exception:
        return None


def main() -> int:
    база_стенда = os.path.join(ЗДЕСЬ, "app.db")
    if not os.path.exists(база_стенда):
        print("ПРОПУСК: нет базы стенда app.db")
        return 2
    тмп = tempfile.mkdtemp(prefix="cw_")
    база = os.path.join(тмп, "app.db")
    shutil.copy2(база_стенда, база)
    скрипт = os.path.join(тмп, "run.py")
    open(скрипт, "w", encoding="utf-8").write(ЗАПУСК)
    порт = _порт()
    env = dict(os.environ, MAIN_DIR=ПРОЕКТ, DB_PATH=база, PORT=str(порт),
               CONTENT_SCHEDULER="1", CONTENT_YOUTUBE_API_KEY="fake-key",
               TURNSTILE_SECRET_KEY="", OPENROUTER_URL="http://127.0.0.1:9/x",
               PYTHONIOENCODING="utf-8")
    if ОШИБКА:
        env["FAKE_FAIL"] = "1"
    журнал = open(os.path.join(тмп, "log.txt"), "w", encoding="utf-8")
    проц = subprocess.Popen([sys.executable, скрипт], env=env, stdout=журнал, stderr=журнал)
    адрес = f"http://127.0.0.1:{порт}"
    беды: list[str] = []
    строки: list[str] = []
    try:
        c = httpx.Client(base_url=адрес, timeout=5.0)
        for _ in range(60):
            try:
                if c.get("/health").status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.5)
        else:
            print("ПРОПУСК: стенд не поднялся")
            return 2
        r = c.post("/login", data={"email": "screenshot@local.dev",
                                   "password": "Screenshot-Local-2026"})
        if "access_token" not in c.cookies:
            print(f"ПРОПУСК: вход не состоялся ({r.status_code})")
            return 2
        time.sleep(2)                                   # планировщик стартовал
        rss_до = _rss(проц.pid)
        r = c.post("/content/api/run", json={"kind": "archaeology"})
        строки.append(f"запуск археологии: HTTP {r.status_code}")
        if r.status_code != 200:
            беды.append("археология не запустилась")
        time.sleep(4)                                   # «пора» цикла наступила
        времена = []
        for путь in ["/health"] * 10 + ["/content"] * 10:
            t = time.monotonic()
            try:
                код = c.get(путь, timeout=3.0).status_code
            except httpx.HTTPError as e:
                код = type(e).__name__
            dt = time.monotonic() - t
            времена.append((путь, код, dt))
        for путь in ("/health", "/content"):
            мои = [x for x in времена if x[0] == путь]
            худший = max(x[2] for x in мои)
            плохих = sum(1 for x in мои if x[1] != 200 or x[2] >= ПОРОГ)
            print(f"{путь}: худший {худший:.3f} с, плохих {плохих}", flush=True)
            строки.append(f"{путь}: 10 запросов, худший {худший:.3f} с, "
                          f"медиана {sorted(x[2] for x in мои)[5]:.3f} с, плохих {плохих}")
            if плохих:
                беды.append(f"{путь}: {плохих} из 10 не ответили за {ПОРОГ} с")
        rss_во = _rss(проц.pid)
        строки.append(f"память процесса: до {rss_до and round(rss_до)} МБ, "
                      f"во время {rss_во and round(rss_во)} МБ")
        if not ОШИБКА:
            try:
                r2 = c.post("/content/api/run", json={"kind": "archaeology"}, timeout=3.0)
                д = r2.json()
                строки.append(f"повторный запуск: HTTP {r2.status_code} — {д.get('error')}")
                if r2.status_code != 409:
                    беды.append("повторный запуск не отказан")
            except httpx.HTTPError as e:
                беды.append(f"повторный запуск: {type(e).__name__}")
            try:
                ст = c.get("/content/api/state", timeout=3.0).json()
                ход = ((ст.get("running") or {}).get("ход") or {}).get("текст")
                строки.append(f"ход в состоянии: {ход!r}")
                if not ход or " из " not in ход:
                    беды.append("хода «N из M» в состоянии нет")
            except httpx.HTTPError as e:
                беды.append(f"состояние: {type(e).__name__}")
        # ждём конца прогона
        конец = None
        for _ in range(25):
            try:
                ст = c.get("/content/api/state", timeout=3.0).json()
            except httpx.HTTPError:
                time.sleep(1)
                continue
            if not ст.get("busy"):
                конец = ст.get("last")
                break
            time.sleep(1)
        if конец is None:
            беды.append("прогон не кончился за 40 с (либо сайт не отвечает)")
        else:
            строки.append(f"конец: №{конец['id']} {конец['kind']} {конец['state']} — {конец.get('note')}")
            import sqlite3
            арх = sqlite3.connect(база).execute(
                "select id, state, note from content_runs where kind='archaeology' "
                "order by id desc limit 1").fetchone()
            строки.append(f"археология в базе: №{арх[0]} {арх[1]} — {арх[2]}")
            if ОШИБКА and not (арх[1] == "error" and "подложенная" in (арх[2] or "")):
                беды.append("ошибка не записана текстом в прогон")
            r3 = c.post("/content/api/run", json={"kind": "cycle"}, timeout=3.0)
            строки.append(f"после конца кнопка свободна: запуск сбора HTTP {r3.status_code}")
            if r3.status_code != 200:
                беды.append("после конца запуск отказан")
        import sqlite3
        к = sqlite3.connect(база)
        пропусков = к.execute("select count(*) from content_runs where state='skipped'").fetchone()[0]
        строки.append(f"строк «skipped» за прогон: {пропусков}")
        if пропусков > 5:
            беды.append(f"планировщик пишет «skipped» пачками: {пропусков}")
    finally:
        проц.kill()
        журнал.close()
    print(f"код: {ПРОЕКТ}")
    for с in строки:
        print("  " + с)
    print("ИТОГ: " + ("ПЛОХО — " + "; ".join(беды) if беды else "OK"))
    return 1 if беды else 0


if __name__ == "__main__":
    sys.exit(main())
