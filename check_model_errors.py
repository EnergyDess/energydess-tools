# -*- coding: utf-8 -*-
"""СБОЙ МОДЕЛИ: КАЖДЫЙ СЛУЧАЙ ВЫЗЫВАЕТСЯ ЖИВЬЁМ И ПОКАЗЫВАЕТ СВОЙ ТЕКСТ.

═══════════════════════════════════════════════════════════════════════
ЗАЧЕМ ЭТО ФАЙЛ В РЕПОЗИТОРИИ
═══════════════════════════════════════════════════════════════════════

BACKLOG №128. До 2026-08-21 в двух местах стояла КОНСТАНТА «Ответ
ассистента оборвался. Попробуйте ещё раз.» — одна на все исходы. Из семи
фактических случаев она описывает ОДИН; в остальных шести она говорит
неправду, а «попробуйте ещё раз» в четырёх не помогает никогда.

Проверить это чтением кода нельзя: разница видна только в том, ЧТО
приезжает от сервиса, а сервис от нас не зависит. Отсюда этот файл —
он поднимает приложение своим процессом с подставленным `OPENROUTER_URL`
(и, где надо, с несуществующей моделью), делает НАСТОЯЩИЙ HTTP-запрос
к чату дневника и печатает фактический текст, который увидит человек.

Три случая идут в ЖИВОЙ OpenRouter (обрыв по лимиту, отказ сервиса, сеть
не отвечает); четыре — через настоящую HTTP-заглушку на том же пути кода.
Заглушка нужна потому, что заставить настоящую модель вернуть пустой
`content` или тело без `choices` по требованию нельзя — и это названо
здесь, а не спрятано.

ЧЕМ ЭТО НЕ ЯВЛЯЕТСЯ. Не проверка: кода «правильно» у неё нет, код
возврата всегда 0. Тексты читает человек — ровно как кадры пиксельного
дифа.

ЗАПУСК (приложение поднимается САМО, отдельным портом):

    py check_model_errors.py
"""

import http.server
import io
import json
import os
import socket
import subprocess
import sys
import threading
import time

sys.stdout.reconfigure(encoding="utf-8")
КОРЕНЬ = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, КОРЕНЬ)

# Учётные данные аккаунта съёмки — ИЗ ОДНОГО ИСТОЧНИКА (§8.0), а не
# переписаны сюда: копия разошлась бы с оригиналом молча.
import make_local_user as _сид                                     # noqa: E402
ПОЧТА = _сид.EMAIL
ПАРОЛЬ = _сид.PASSWORD

# ── Заглушка сервиса: отвечает ровно тем телом, которое нужно случаю ──
ТЕЛО = {"кусок": None}


class Заглушка(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        длина = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(длина)
        код, тело, тип = ТЕЛО["кусок"]
        if тело == "__СПАТЬ__":
            time.sleep(40)
        данные = тело.encode("utf-8")
        self.send_response(код)
        self.send_header("Content-Type", тип)
        self.send_header("Content-Length", str(len(данные)))
        self.end_headers()
        self.wfile.write(данные)

    def log_message(self, *а):
        pass


def поднять_заглушку(порт):
    с = http.server.HTTPServer(("127.0.0.1", порт), Заглушка)
    threading.Thread(target=с.serve_forever, daemon=True).start()
    return с


def свободен(порт):
    s = socket.socket()
    try:
        s.connect(("127.0.0.1", порт))
        return False
    except OSError:
        return True
    finally:
        s.close()


def поднять_приложение(порт, доп_env):
    env = dict(os.environ)
    env["DB_PATH"] = os.path.join(КОРЕНЬ, "app.db")
    env["PYTHONIOENCODING"] = "utf-8"
    env.update(доп_env)
    журнал = io.open(os.path.join(ВЫВОД, "app_%d.log") % порт, "w",
                     encoding="utf-8", errors="replace")
    п = subprocess.Popen(
        [sys.executable, "-X", "utf8", "-m", "uvicorn", "main:app",
         "--port", str(порт), "--log-level", "warning"],
        cwd=КОРЕНЬ, env=env, stdout=журнал, stderr=subprocess.STDOUT)
    for _ in range(90):
        time.sleep(1)
        if not свободен(порт):
            time.sleep(2)
            return п, журнал
    п.kill()
    raise RuntimeError("приложение на порту %d не поднялось" % порт)


def спросить(порт):
    import httpx
    with httpx.Client(base_url="http://127.0.0.1:%d" % порт,
                      follow_redirects=False, timeout=90) as c:
        r = c.post("/login", data={"email": ПОЧТА, "password": ПАРОЛЬ})
        if r.status_code != 302:
            return ("ВХОД НЕ ПРОШЁЛ (%s)" % r.status_code, r.status_code)
        o = c.post("/nutrition/api/ai-chat",
                   json={"message": "Съел 100 г гречки"})
        try:
            текст = o.json().get("error") or ("ОТВЕТ БЕЗ ОШИБКИ: "
                                              + str(o.json())[:120])
        except Exception:
            текст = "тело не JSON: " + o.text[:120]
        return (текст, o.status_code)


СЛУЧАИ = [
    # (имя, доп_env, тело заглушки или None — тогда идём в живой OpenRouter)
    ("1. ОБРЫВ ПО ЛИМИТУ (живой OpenRouter, потолок 5 токенов)",
     {"CHAT_MAX_TOKENS": "5"}, None),
    ("2. ОТКАЗ СЕРВИСА (живой OpenRouter, несуществующая модель)",
     {"LETTER_MODEL": "нет-такой/модели-2026"}, None),
    ("3. ПУСТОЙ ОТВЕТ (заглушка: choices есть, content пуст)",
     {}, (200, json.dumps({"choices": [{"message": {"content": "  "},
                                        "finish_reason": "stop"}],
                           "usage": {"completion_tokens": 0}}),
          "application/json")),
    ("4. ОТВЕТ НЕ ТОЙ ФОРМЫ (заглушка: тела без choices и без error)",
     {}, (200, json.dumps({"ok": True, "id": "abc"}), "application/json")),
    ("5. ТЕЛО НЕ JSON (заглушка: страница ошибки шлюза)",
     {}, (502, "<html><body>502 Bad Gateway</body></html>", "text/html")),
    ("6. СЕТЬ НЕ ОТВЕЧАЕТ (адрес на закрытый порт)",
     {"OPENROUTER_URL": "http://127.0.0.1:9/chat"}, None),
    ("7. СЕРВИС МОЛЧИТ ДОЛЬШЕ ТАЙМАУТА (заглушка спит 40 с при timeout=30)",
     {}, (200, "__СПАТЬ__", "application/json")),
]

ВЫВОД = os.environ.get("MODEL_ERR_DIR", "C:/Temp/claude/model_errors")
os.makedirs(ВЫВОД, exist_ok=True)

ПОРТ_ПРИЛОЖЕНИЯ = 8907
ПОРТ_ЗАГЛУШКИ = 8908

if __name__ == "__main__":
    поднять_заглушку(ПОРТ_ЗАГЛУШКИ)
    for имя, доп, тело in СЛУЧАИ:
        env = dict(доп)
        if тело is not None:
            ТЕЛО["кусок"] = тело
            env["OPENROUTER_URL"] = "http://127.0.0.1:%d/chat" % ПОРТ_ЗАГЛУШКИ
        п = журнал = None
        try:
            п, журнал = поднять_приложение(ПОРТ_ПРИЛОЖЕНИЯ, env)
            текст, код = спросить(ПОРТ_ПРИЛОЖЕНИЯ)
            print("─" * 74)
            print(имя)
            print("   HTTP %s" % код)
            print("   ТЕКСТ ЧЕЛОВЕКУ: %s" % текст)
        except Exception as e:
            print("─" * 74)
            print(имя)
            print("   НЕ ВЫШЛО: %s: %s" % (type(e).__name__, str(e)[:200]))
        finally:
            if п:
                п.kill()
                п.wait()
            if журнал:
                журнал.close()
            time.sleep(1)
        # строка журнала приложения — она же говорит причину
        try:
            лог = io.open(os.path.join(ВЫВОД, "app_%d.log") % ПОРТ_ПРИЛОЖЕНИЯ,
                          encoding="utf-8", errors="replace").read()
            для_печати = [с for с in лог.splitlines()
                          if "nut-chat" in с or "[letter]" in с]
            for с in для_печати[-3:]:
                print("   ЖУРНАЛ: %s" % с.strip()[:150])
        except OSError:
            pass
