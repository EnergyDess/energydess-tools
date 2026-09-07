# -*- coding: utf-8 -*-
"""ЖИВОЙ ЗАМЕР К ПРОВЕРКЕ 27: ЖДЁТ ЛИ СОСЕД, ПОКА АССИСТЕНТ ДУМАЕТ.

Отвечает на ДРУГОЙ вопрос, чем статическая опись `check_db_hold.py`,
и потому вынесен отдельно. Опись говорит «соединение занято» — свойство
ТЕКСТА кода; здесь спрашивается «сколько миллисекунд ждал соседний
запрос и упал ли он» — свойство ПРОГОНА, и замерить его чтением нельзя.

КАК УСТРОЕН. Приложение поднимается своим процессом, а вместо OpenRouter
ему подставляется ЗАГЛУШКА, которая СПИТ заданное число секунд. Живая
модель тут не годится: её длительность гуляет от вызова к вызову,
а замер должен давать одно и то же число на одном и том же коде
(§6.0.3 — пока два прогона одного кода не сошлись, показаниям веры нет).
Путь кода при этом БОЕВОЙ: заглушка отвечает по HTTP на том же адресе.

СОСЕДЕЙ ДВА, И ОНИ РАЗНЫЕ. `GET /medkit` — чтение, которое по дороге
делает ленивую уборку, то есть ПИШЕТ; `POST /nutrition/api/water` —
чистая запись. Один сосед не разделил бы «блокируется всякая запись»
и «блокируется именно аптечка».

ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ (`--контроль`) возвращает дефект: у `_сеть`
временно убирается `db.close()`, то есть соединение снова держится
на время сети. ДОКАЗАТЕЛЬСТВО ПОДЛОГА независимо от вердикта — исходник
перечитывается, и в теле `_сеть` не должно остаться `db.close()`.
Замер обязан назвать соседа упавшим; не назвал — слеп замер, а не код
исправен.

Запуск (приложение и заглушка поднимаются САМИ):

    py check_db_hold.py --живьём
    py check_db_hold.py --живьём --контроль
"""
import http.server
import io
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time

sys.stdout.reconfigure(encoding="utf-8")
КОРЕНЬ = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, КОРЕНЬ)

import make_local_user as _сид                                    # noqa: E402

ПОЧТА, ПАРОЛЬ = _сид.EMAIL, _сид.PASSWORD
ПОРТ_ПРИЛОЖЕНИЯ = 8917
ПОРТ_ЗАГЛУШКИ = 8918
СПАТЬ_СЕК = 12.0
# Порог соседа. Не «сколько не жалко»: у SQLite `busy_timeout` 30 с
# (`database.py`), и всё, что больше секунды, означает ожидание чужой
# транзакции, а не работу.
ПОРОГ_СОСЕДА_МС = 2000
ВЫВОД = os.environ.get("DBHOLD_DIR", "C:/Temp/claude/db_hold")


class Заглушка(http.server.BaseHTTPRequestHandler):
    """Вместо OpenRouter: спит и отдаёт разбираемый ответ."""

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(n)
        time.sleep(СПАТЬ_СЕК)
        тело = json.dumps({
            "choices": [{"message": {"content":
                                     '{"вид":"заведение","поля":{},'
                                     '"вопрос":"Как называется препарат?"}'},
                         "finish_reason": "stop"}],
            "usage": {"completion_tokens": 20}}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(тело)))
        self.end_headers()
        self.wfile.write(тело)

    def log_message(self, *а):
        pass


def _свободен(порт):
    s = socket.socket()
    try:
        s.connect(("127.0.0.1", порт))
        return False
    except OSError:
        return True
    finally:
        s.close()


def _поднять_приложение(порт):
    env = dict(os.environ)
    env["DB_PATH"] = os.path.join(КОРЕНЬ, "app.db")
    env["PYTHONIOENCODING"] = "utf-8"
    env["OPENROUTER_URL"] = "http://127.0.0.1:%d/chat" % ПОРТ_ЗАГЛУШКИ
    os.makedirs(ВЫВОД, exist_ok=True)
    журнал = io.open(os.path.join(ВЫВОД, "app.log"), "w",
                     encoding="utf-8", errors="replace")
    п = subprocess.Popen(
        [sys.executable, "-X", "utf8", "-m", "uvicorn", "main:app",
         "--port", str(порт), "--log-level", "warning"],
        cwd=КОРЕНЬ, env=env, stdout=журнал, stderr=subprocess.STDOUT)
    for _ in range(90):
        time.sleep(1)
        if not _свободен(порт):
            time.sleep(2)
            return п, журнал
    п.kill()
    raise RuntimeError("приложение на порту %d не поднялось" % порт)


def _один_прогон():
    """Возвращает {'ассистент': (код, мс), 'сосед': [(имя, код, мс), …]}."""
    import httpx
    п, журнал = _поднять_приложение(ПОРТ_ПРИЛОЖЕНИЯ)
    итог = {"ассистент": None, "соседи": []}
    try:
        база = "http://127.0.0.1:%d" % ПОРТ_ПРИЛОЖЕНИЯ
        c = httpx.Client(base_url=база, follow_redirects=False, timeout=120)
        r = c.post("/login", data={"email": ПОЧТА, "password": ПАРОЛЬ})
        if r.status_code != 302:
            raise RuntimeError("вход не прошёл: %s" % r.status_code)
        # ПЕРЕПИСКА ЧИСТИТСЯ ПЕРЕД ЗАМЕРОМ, и это не уборка за собой.
        # Заглушка отвечает черновиком С ВОПРОСОМ; оставь его в базе —
        # следующий прогон уйдёт веткой уточнения и сделает ЛИШНИЙ вызов
        # модели. Замер тогда сравнивает 12 с с 35 с не потому, что код
        # другой, а потому, что путь другой. Чистится БОЕВЫМ эндпоинтом,
        # тем же, что у кнопки человека.
        c.delete("/medkit/api/chat")

        def медленный():
            t = time.perf_counter()
            o = c.post("/medkit/api/assist",
                       json={"text": "Проба ассистента, 1 упаковка"})
            итог["ассистент"] = (o.status_code,
                                 round((time.perf_counter() - t) * 1000))

        н = threading.Thread(target=медленный)
        н.start()
        # Дать ассистенту дойти до сети: до неё он успевает сделать
        # запросы к базе, и мерить надо именно окно ожидания модели.
        time.sleep(2.0)
        соседи = [("GET /medkit", "get", "/medkit", None),
                  ("POST вода", "post", "/nutrition/api/water", {"ml": 100})]
        замки = []

        def сосед(имя, метод, путь, тело):
            c2 = httpx.Client(base_url=база, follow_redirects=False,
                              timeout=120, cookies=c.cookies)
            t = time.perf_counter()
            try:
                o = (c2.get(путь) if метод == "get" else c2.post(путь,
                                                                 json=тело))
                код = o.status_code
            except Exception as e:
                код = type(e).__name__
            замки.append((имя, код, round((time.perf_counter() - t) * 1000)))
            c2.close()

        нити = [threading.Thread(target=сосед, args=с) for с in соседи]
        for т in нити:
            т.start()
        for т in нити:
            т.join()
        н.join()
        итог["соседи"] = sorted(замки)
    finally:
        п.kill()
        п.wait()
        журнал.close()
    return итог


def доказать_подлог(путь):
    """НЕЗАВИСИМЫЙ ЗАМЕР ТОГО, ЧТО ПОДЛОГ СОСТОЯЛСЯ (§6.0.3).

    Вердикт замера доказательством не является: «соседей задело»
    выходит и тогда, когда их задело по другой причине. Здесь
    читается ИСХОДНИК: исполняемой строки `db.close()` в теле `_сеть`
    остаться не должно.

    ПЕРЕВОДЫ СТРОК ПРИВОДЯТСЯ, а ищется ИСПОЛНЯЕМАЯ строка, а не
    упоминание, — обе оговорки поймал сам контроль, а не чтение:
    файл на этой машине CRLF, а docstring `_сеть` разбирает
    `db.close()` словами.
    """
    # ПЕРЕВОД СТРОКИ ОБЪЯВЛЕН КОДОМ, А НЕ ЭКРАНИРОВАНИЕМ (§6.0, §2.6).
    # Эта самая строка уже уезжала в файл НАСТОЯЩИМ переводом строки
    # внутри литерала — файл переставал разбираться вовсе. Где знак
    # не виден глазом, он объявляется так, чтобы его было видно.
    пв = chr(10)
    новый = io.open(путь, encoding="utf-8",
                    newline="").read().replace(chr(13) + пв, пв)
    тело = re.search("async def _сеть" + re.escape("(db, корутина):")
                     + "(.*?)" + пв * 3, новый, re.S)
    return bool(тело) and (пв + "    db.close()" + пв) not in тело.group(1)


def _подложить_удержание():
    """Убрать `db.close()` из тела `_сеть` — вернуть дефект.

    Возвращает (было, доказано): доказательство читается ИЗ ФАЙЛА
    после правки и от вердикта замера не зависит.
    """
    путь = os.path.join(КОРЕНЬ, "main.py")
    было = io.open(путь, "rb").read()
    текст = было.decode("utf-8")
    перевод = "\r\n" if b"\r\n" in было else "\n"
    цель = ("    db.close()%s    return await корутина" % перевод)
    if текст.count(цель) != 1:
        return было, False
    текст = текст.replace(
        цель,
        "    # ПОДЛОГ КОНТРОЛЯ: соединение НЕ отпускаем%s"
        "    return await корутина" % перевод)
    io.open(путь, "wb").write(текст.encode("utf-8"))
    # ДОКАЗАТЕЛЬСТВО ОБЪЯВЛЕНО ИМЕНЕМ И ЖИВЁТ ОТДЕЛЬНО (§6.0.3):
    # его считает `доказать_подлог`, и опись контролей видит его
    # разбором дерева, а не по слову в комментарии.
    return было, доказать_подлог(путь)


def замер():
    контроль = "--контроль" in sys.argv
    threading.Thread(
        target=http.server.HTTPServer(("127.0.0.1", ПОРТ_ЗАГЛУШКИ),
                                      Заглушка).serve_forever,
        daemon=True).start()
    путь = os.path.join(КОРЕНЬ, "main.py")
    было = None
    try:
        if контроль:
            было, доказано = _подложить_удержание()
            print("ДОКАЗАТЕЛЬСТВО ПОДЛОГА: `db.close()` убран из тела "
                  "`_сеть` — %s" % ("ДА" if доказано else "НЕТ"))
            if not доказано:
                return 2
        print("ЗАГЛУШКА ВМЕСТО МОДЕЛИ СПИТ %.0f с; сосед идёт на 2-й секунде"
              % СПАТЬ_СЕК)
        итог = _один_прогон()
    finally:
        if было is not None:
            io.open(путь, "wb").write(было)
    код_а, мс_а = итог["ассистент"] or ("нет ответа", -1)
    print("─" * 70)
    print("  ассистент  %s за %d мс" % (код_а, мс_а))
    плохих = 0
    for имя, код, мс in итог["соседи"]:
        беда = (not isinstance(код, int)) or код >= 500 or мс > ПОРОГ_СОСЕДА_МС
        плохих += 1 if беда else 0
        print("  %-12s %s за %5d мс   %s"
              % (имя, код, мс, "← ЖДАЛ/УПАЛ" if беда else "ok"))
    print("─" * 70)
    if контроль:
        if плохих:
            print("КОНТРОЛЬ ПРОЙДЕН: с удержанием соседей задело — %d" % плохих)
            return 0
        print("КОНТРОЛЬ НЕ ПРОЙДЕН: подлог состоялся, а замер молчит — "
              "замер слеп")
        return 1
    if плохих:
        print("НАХОДКА: соседний запрос ждёт либо падает, пока идёт сеть")
        return 1
    print("СОСЕДЕЙ НЕ ЗАДЕЛО")
    return 0


if __name__ == "__main__":
    sys.exit(замер())
