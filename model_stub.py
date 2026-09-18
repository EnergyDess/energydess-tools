"""ЗАГЛУШКА OPENROUTER: ОТВЕЧАЕТ ЗАДАННЫМ ТЕЛОМ И ЗАПОМИНАЕТ ЗАПРОСЫ.

BACKLOG №346, заход 3, блок 2. Пробы, звавшие живую модель, стоили
денег прода: ключ был общий. Заглушка даёт им ответ модели без сети
и без денег — и при этом не делает их пустышкой: каждый запрос
запоминается ЦЕЛИКОМ, и проба обязана проверить, что он собран верно
(модель, потолок, политика данных, обязательные части), а ответ разобран
и лёг куда надо.

Один модуль на все пробы, а не своя заглушка в каждой (§6.0.7): три
заглушки уже жили порознь (`check_model_errors`, `check_db_hold_live`,
`check_medkit_photo`), и отличались они ровно тем, чего каждая
не умела.

Использование в процессе:

    with Заглушка() as з:
        з.ответ = lambda запрос: з.тело("текст")      # или (код, тело)
        os.environ["OPENROUTER_URL"] = з.адрес_чата
        ...
        з.запросы[-1]["json"]["model"]

Отдельным процессом (для стенда): `py model_stub.py --port 8931
--журнал путь.jsonl` — в журнал пишется ТОЛЬКО устройство запроса
(модель, потолок, политика, число сообщений, размер), без текста.
"""
import argparse
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ПУТЬ_ЧАТА = "/api/v1/chat/completions"
ПУТЬ_РЕЧИ = "/api/v1/audio/transcriptions"


def тело(текст: str, finish: str = "stop", токены_входа: int = 100,
         токены_выхода: int = 20, цена: float = 0.0) -> dict:
    """Тело ответа той же формы, что у OpenRouter."""
    return {"id": "gen-stub", "choices": [{"message": {"role": "assistant",
                                                       "content": текст},
                                           "finish_reason": finish}],
            "usage": {"prompt_tokens": токены_входа,
                      "completion_tokens": токены_выхода, "cost": цена}}


def ошибка(код: int = 500, сообщение: str = "stub error") -> tuple:
    """Отказ сервиса той же формы, что у OpenRouter."""
    return код, {"error": {"code": код, "message": сообщение}}


def устройство(запрос: dict) -> dict:
    """Что про запрос можно писать в журнал: без текста."""
    j = запрос.get("json") or {}
    сообщения = j.get("messages") or []
    знаков = 0
    картинок = 0
    for с in сообщения:
        с_текст = с.get("content")
        if isinstance(с_текст, str):
            знаков += len(с_текст)
        elif isinstance(с_текст, list):
            for ч in с_текст:
                if ч.get("type") == "text":
                    знаков += len(ч.get("text") or "")
                elif ч.get("type") == "image_url":
                    картинок += 1
    return {"path": запрос.get("path"), "model": j.get("model"),
            "max_tokens": j.get("max_tokens"),
            "provider": j.get("provider"), "messages": len(сообщения),
            "chars": знаков, "images": картинок}


class Заглушка:
    """Сервер в потоке. `ответ(запрос) -> dict | (код, dict)`."""

    def __init__(self, порт: int = 0, журнал: str | None = None):
        self.запросы: list[dict] = []
        self.ответ = lambda запрос: тело("{}")
        self.журнал = журнал
        заглушка = self

        class Обработчик(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                длина = int(self.headers.get("Content-Length") or 0)
                сырое = self.rfile.read(длина)
                запрос = {"path": self.path,
                          "auth": bool(self.headers.get("Authorization")),
                          "title": self.headers.get("X-Title") or "",
                          "json": None}
                if "json" in (self.headers.get("Content-Type") or ""):
                    try:
                        запрос["json"] = json.loads(сырое or b"{}")
                    except ValueError:
                        запрос["json"] = None
                заглушка.запросы.append(запрос)
                if заглушка.журнал:
                    with open(заглушка.журнал, "a", encoding="utf-8") as ф:
                        ф.write(json.dumps(устройство(запрос), ensure_ascii=False) + "\n")
                if self.path.endswith(ПУТЬ_РЕЧИ):
                    код, т = 200, {"text": "проверка связи"}
                else:
                    р = заглушка.ответ(запрос)
                    код, т = р if isinstance(р, tuple) else (200, р)
                данные = json.dumps(т, ensure_ascii=False).encode("utf-8")
                self.send_response(код)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(данные)))
                self.end_headers()
                self.wfile.write(данные)

        self.сервер = ThreadingHTTPServer(("127.0.0.1", порт), Обработчик)
        self.порт = self.сервер.server_address[1]
        self.адрес_чата = f"http://127.0.0.1:{self.порт}{ПУТЬ_ЧАТА}"
        self.адрес_речи = f"http://127.0.0.1:{self.порт}{ПУТЬ_РЕЧИ}"
        self._поток = threading.Thread(target=self.сервер.serve_forever, daemon=True)

    def __enter__(self):
        self._поток.start()
        return self

    def __exit__(self, *a):
        self.сервер.shutdown()
        self.сервер.server_close()
        return False

    тело = staticmethod(тело)
    ошибка = staticmethod(ошибка)


def проверить_запрос(запрос: dict, модель: str, потолок: int,
                     обязательно: tuple = ()) -> list[str]:
    """Беды сборки запроса к модели. Пусто — запрос собран как надо.

    `обязательно` — строки, которые обязаны стоять в тексте сообщений:
    без них модель получит не тот вопрос.
    """
    беды = []
    j = запрос.get("json")
    if not isinstance(j, dict):
        return ["тело запроса не JSON"]
    if not запрос.get("auth"):
        беды.append("нет заголовка Authorization")
    if j.get("model") != модель:
        беды.append(f"модель {j.get('model')!r} вместо {модель!r}")
    if j.get("max_tokens") != потолок:
        беды.append(f"потолок {j.get('max_tokens')!r} вместо {потолок!r}")
    п = j.get("provider") or {}
    if п.get("data_collection") != "deny" or п.get("zdr") is not True:
        беды.append("нет политики данных (§2.4)")
    текст = json.dumps(j.get("messages") or [], ensure_ascii=False)
    for кусок in обязательно:
        if кусок not in текст:
            беды.append(f"в сообщениях нет части «{кусок[:40]}»")
    if not j.get("messages"):
        беды.append("сообщений нет")
    return беды


ФЛАГ_ЖИВЬЁМ = "--живьём"


def живой_замер(режим: str, покрывает: str = "py check_model_paths.py",
                argv=None) -> None:
    """ЗАСЛОН ЖИВОГО РЕЖИМА ПРОБЫ (№346, заход 3, блок 2).

    Режим, который зовёт настоящую модель, без `--живьём` не идёт:
    печатает ПРОПУСК словом и выходит кодом 2 (§6.0.2 — «прогон
    не состоялся»). Живой замер — это вопрос КАЧЕСТВА ответа модели,
    ему место в ручном запуске со своим ключом стенда. Сборку запроса,
    разбор ответа и текст сбоя того же пути проверяет подделка —
    `покрывает` называет, где именно.
    """
    argv = __import__("sys").argv if argv is None else argv
    if ФЛАГ_ЖИВЬЁМ in argv:
        print(f"[живьём] {режим}: вызовы идут в настоящую модель, "
              "платит ключ стенда", flush=True)
        return
    print(f"ПРОПУСК: {режим} — живой замер модели, только с {ФЛАГ_ЖИВЬЁМ} "
          f"(платит ключ стенда). Сборку, разбор и сбой пути без денег "
          f"проверяет {покрывает}", flush=True)
    __import__("sys").exit(2)


def main() -> int:
    р = argparse.ArgumentParser(description="Заглушка OpenRouter")
    р.add_argument("--port", type=int, default=8931)
    р.add_argument("--журнал", default=None)
    а = р.parse_args()
    з = Заглушка(а.port, а.журнал)
    print(f"заглушка OpenRouter на {з.адрес_чата}", flush=True)
    try:
        з.сервер.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
