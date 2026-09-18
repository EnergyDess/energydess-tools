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

С ЗАХОДА 3 ЗАДАЧИ 346 ЖИВЫХ ВЫЗОВОВ ПО УМОЛЧАНИЮ НЕТ. Прежде два
случая — обрыв по лимиту и несуществующая модель — шли в ЖИВОЙ
OpenRouter и платили с ключа прода. Теперь их тело подаёт заглушка той
же формы (`finish_reason: length`; `error.code: 400`), а живой замер —
только с `--живьём` и ключом стенда: он сверяет, что настоящий сервис
отвечает ТОЙ ЖЕ формой, что заглушка. Шестой случай — закрытый порт,
он и прежде в сеть не ходил.

И ЭТО СТАЛО ПРОВЕРКОЙ. Прежде: «кода „правильно“ у неё нет, код
возврата всегда 0, тексты читает человек». Негодно потому, что на
подделке «прошла» без ожиданий означало бы пустышку. У каждого случая
теперь ожидаемый код HTTP и кусок текста из §2.5, а у двух подделанных —
ещё и сборка запроса (потолок 5 и несуществующая модель обязаны уйти
в заглушку). Код 1 — расхождение. `--контроль`: подлог «потолок не
передан» и подлог «сервис ответил успехом вместо отказа» — оба обязаны
дать расхождение.

ЗАПУСК (приложение поднимается САМО, отдельным портом):

    py check_model_errors.py             # на подделке, код 0/1
    py check_model_errors.py --живьём    # случаи 1–2 в настоящий сервис
    py check_model_errors.py --контроль
"""

import http.server
import probe_guard  # noqa: F401  ПРОПУСК вместо трассы (§6.0.1)
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
ПОСЛЕДНИЙ = {"json": None}     # что пришло в заглушку — сверка сборки


class Заглушка(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        длина = int(self.headers.get("Content-Length") or 0)
        try:
            ПОСЛЕДНИЙ["json"] = json.loads(self.rfile.read(длина) or b"{}")
        except ValueError:
            ПОСЛЕДНИЙ["json"] = None
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
    # Адрес сервиса подменён на нашу петлю — ключ стенда фиктивный. Ключ прода
    # на стенде не используется вовсе (№346, заход 3), и без ключа стенда
    # приложение отказало бы раньше заглушки
    if env.get("OPENROUTER_URL", "").startswith("http://127.0.0.1"):
        env["OPENROUTER_STAND_KEY"] = "stub"
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


ЖИВЬЁМ = "--живьём" in sys.argv
КОНТРОЛЬ = "--контроль" in sys.argv


def _ответ(код, тело):
    return (код, json.dumps(тело, ensure_ascii=False), "application/json")


# (имя, доп_env, тело заглушки или None — тогда живой OpenRouter,
#  ожидание: (код HTTP, кусок текста), сборка: {поле: значение} или {})
СЛУЧАИ = [
    ("1. ОБРЫВ ПО ЛИМИТУ (потолок 5 токенов)",
     {"CHAT_MAX_TOKENS": "5"},
     None if ЖИВЬЁМ else _ответ(200, {"choices": [{"message": {"content": "Недопис"},
                                                    "finish_reason": "length"}],
                                      "usage": {"completion_tokens": 5}}),
     (502, "не поместился в лимит"), {"max_tokens": 5}),
    ("2. ОТКАЗ СЕРВИСА (несуществующая модель)",
     {"LETTER_MODEL": "нет-такой/модели-2026"},
     None if ЖИВЬЁМ else _ответ(400, {"error": {"code": 400, "message":
                                               "нет-такой/модели-2026 is not a valid model ID"}}),
     (502, "Сервис моделей вернул ошибку"), {"model": "нет-такой/модели-2026"}),
    ("3. ПУСТОЙ ОТВЕТ (заглушка: choices есть, content пуст)",
     {}, (200, json.dumps({"choices": [{"message": {"content": "  "},
                                        "finish_reason": "stop"}],
                           "usage": {"completion_tokens": 0}}),
          "application/json"), (502, "пустой ответ"), {}),
    ("4. ОТВЕТ НЕ ТОЙ ФОРМЫ (заглушка: тела без choices и без error)",
     {}, (200, json.dumps({"ok": True, "id": "abc"}), "application/json"),
     (502, "не так, как мы ожидаем"), {}),
    ("5. ТЕЛО НЕ JSON (заглушка: страница ошибки шлюза)",
     {}, (502, "<html><body>502 Bad Gateway</body></html>", "text/html"),
     (502, "не так, как мы ожидаем"), {}),
    ("6. СЕТЬ НЕ ОТВЕЧАЕТ (адрес на закрытый порт)",
     {"OPENROUTER_URL": "http://127.0.0.1:9/chat"}, None,
     (503, "Не удалось связаться"), {}),
    ("7. СЕРВИС МОЛЧИТ ДОЛЬШЕ ТАЙМАУТА (заглушка спит 40 с при timeout=30)",
     {}, (200, "__СПАТЬ__", "application/json"), (504, "не ответил за 30"), {}),
]

# ПОДЛОГИ КОНТРОЛЯ — каждый ломает одно звено, и проверка обязана дать
# расхождение ровно у своего случая
ПОДЛОГИ = {
    # сборка: потолок не передан — в заглушку уходит обычный CHAT_MAX_TOKENS
    "потолок-не-передан": (0, {"CHAT_MAX_TOKENS": None}),
    # ошибка: сервис ответил УСПЕХОМ вместо отказа
    "успех-вместо-отказа": (1, _ответ(200, {"choices": [{"message": {"content": "ок"},
                                                           "finish_reason": "stop"}],
                                            "usage": {}})),
}


def прогнать(случаи):
    """Каждый случай — своё приложение. Список расхождений."""
    расхождения = []
    for имя, доп, тело, (ждём_код, ждём_текст), сборка in случаи:
        env = {к: в for к, в in доп.items() if в is not None}
        if тело is not None:
            ТЕЛО["кусок"] = тело
            env["OPENROUTER_URL"] = "http://127.0.0.1:%d/chat" % ПОРТ_ЗАГЛУШКИ
        ПОСЛЕДНИЙ["json"] = None
        п = журнал = None
        try:
            п, журнал = поднять_приложение(ПОРТ_ПРИЛОЖЕНИЯ, env)
            текст, код = спросить(ПОРТ_ПРИЛОЖЕНИЯ)
            беды = []
            if код != ждём_код:
                беды.append("HTTP %s вместо %s" % (код, ждём_код))
            if ждём_текст not in str(текст):
                беды.append("нет «%s»" % ждём_текст)
            if тело is not None:
                j = ПОСЛЕДНИЙ["json"] or {}
                for поле, значение in сборка.items():
                    if j.get(поле) != значение:
                        беды.append("в запросе %s=%r вместо %r" % (поле, j.get(поле), значение))
            print("─" * 74)
            print(имя)
            print("   HTTP %s" % код)
            print("   ТЕКСТ ЧЕЛОВЕКУ: %s" % текст)
            сверено = 2 + (len(сборка) if тело is not None else 0)
            print("   %s" % (("РАСХОЖДЕНИЕ: " + "; ".join(беды)) if беды
                              else "СОВПАЛО (сверено %d)" % сверено))
            if беды:
                расхождения.append(имя)
        except Exception as e:
            print("─" * 74)
            print(имя)
            print("   НЕ ВЫШЛО: %s: %s" % (type(e).__name__, str(e)[:200]))
            расхождения.append(имя)
        finally:
            if п:
                п.kill()
                п.wait()
            if журнал:
                журнал.close()
            time.sleep(1)
    return расхождения


ВЫВОД = os.environ.get("MODEL_ERR_DIR", "C:/Temp/claude/model_errors")
os.makedirs(ВЫВОД, exist_ok=True)

ПОРТ_ПРИЛОЖЕНИЯ = 8907
ПОРТ_ЗАГЛУШКИ = 8908

if __name__ == "__main__":
    if ЖИВЬЁМ:
        import model_stub
        model_stub.живой_замер("check_model_errors, случаи 1–2")
    поднять_заглушку(ПОРТ_ЗАГЛУШКИ)
    if not КОНТРОЛЬ:
        р = прогнать(СЛУЧАИ)
        print("═" * 74)
        print("ИТОГ: случаев %d, расхождений %d%s" % (len(СЛУЧАИ), len(р),
              (" — " + ", ".join(р)) if р else ""))
        sys.exit(1 if р else 0)
    беды = 0
    for имя, (номер, подмена) in ПОДЛОГИ.items():
        случай = list(СЛУЧАИ[номер])
        if isinstance(подмена, dict):
            случай[1] = {**случай[1], **подмена}
        else:
            случай[2] = подмена
        print("═ подлог %s" % имя)
        р = прогнать([tuple(случай)])
        беды += 0 if р else 1
        print("  подлог %s: %s" % (имя, "НАЙДЕН" if р else "НЕ НАЙДЕН — проверка слепа"))
    print("КОНТРОЛЬ: " + ("подлоги найдены" if not беды else "БЕДА"))
    sys.exit(1 if беды else 0)
