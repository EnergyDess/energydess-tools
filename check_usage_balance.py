"""БЛОК ОСТАТКА НА /admin/usage ПРИ СБОЕ OPENROUTER (задача 346, заход 7).

Живой случай: проверка 20 краснела на стенде без ключа модели. Текст сбоя
занимал три строки вместо одной, карточка росла, подвал съезжал на долю
пикселя — и область ссылки «Cookies» мерилась 80×24 вместо 80×25, то есть
ниже порога площади. Правило: карточка остатка ОДНОЙ высоты во всех
состояниях, текст сбоя не раздвигает вёрстку.

Проба поднимает СВОЙ стенд на копии базы стенда и СВОЮ заглушку запроса
остатка (`OPENROUTER_CREDITS_URL`): состояния «сеть» и «ключ отклонён»
снаружи не воспроизводятся, а проверка, которую нечем прогнать, означает
«проверено рассуждением» (§6.0.1). Живых вызовов нет вовсе.

    py check_usage_balance.py              # 4 состояния × 3 ширины, код 1 при беде
    py check_usage_balance.py --контроль   # подлог: резерв высоты снят — обязан упасть
    py check_usage_balance.py --кадры КАТ  # плюс снимки карточек в каталог

Состояния: получен · сеть (обрыв без ответа) · ключ отклонён (401) ·
ключа нет (стенд без ключа). Признаки на каждой ширине: высота карточки
и верх следующего блока одинаковы во всех состояниях (допуск 0.5 px),
текст сбоя не вылезает из карточки, в тексте сбоя названа причина и
последнее значение.

Головной браузер: вопрос про ширину, и headless без полосы прокрутки
считал бы переносы на 15 px шире (§6.0.3).
"""
import http.server
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time

import probe_guard  # noqa: F401 — внешний отказ говорится словом (§3)

sys.stdout.reconfigure(encoding="utf-8")
КОРЕНЬ = os.path.dirname(os.path.abspath(__file__))
ШИРИНЫ = (390, 1920, 2560)
ПОЧТА, ПАРОЛЬ = "screenshot@local.dev", "Screenshot-Local-2026"
ДОПУСК = 0.5

_режим = {"значение": "ok"}


class _Остаток(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        р = _режим["значение"]
        if р == "net":  # обрыв без ответа — у клиента это ошибка сети
            self.close_connection = True
            return
        if р == "401":
            тело, код = {"error": {"code": 401, "message": "No auth"}}, 401
        else:
            тело, код = {"data": {"total_credits": 60.0, "total_usage": 52.3456}}, 200
        b = json.dumps(тело).encode()
        self.send_response(код)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def log_message(self, *a):
        pass


def _порт():
    with socket.socket() as с:
        с.bind(("127.0.0.1", 0))
        return с.getsockname()[1]


def _копия_базы(каталог):
    исх = os.environ.get("STAND_DB") or os.path.join(КОРЕНЬ, "app.db")
    if "/data/" in исх.replace("\\", "/"):
        raise ConnectionError("путь к боевой базе — проба ходит только в копию")
    if not os.path.exists(исх):
        raise ConnectionError("базы стенда нет: %s" % исх)
    куда = os.path.join(каталог, "app.db")
    a, b = sqlite3.connect(исх), sqlite3.connect(куда)
    a.backup(b)
    a.close()
    b.close()
    return куда


def _стенд(база, адрес_остатка, ключ_есть):
    порт = _порт()
    env = dict(os.environ)
    env.update({"DB_PATH": база, "PYTHONIOENCODING": "utf-8",
                "OPENROUTER_CREDITS_URL": адрес_остатка, "USAGE_BALANCE_CACHE_SEC": "0"})
    # Ключ стенда: подставной, в сеть модели проба не ходит ни разу. Пустое
    # значение перекрывает .env — load_dotenv существующее не трогает.
    env["OPENROUTER_STAND_KEY"] = "sk-probe-not-a-real-key" if ключ_есть else ""
    # КЛЮЧ ПОДПИСИ — ТОТ ЖЕ, ЧТО У ПРОЦЕССА, ВЫПУСКАЮЩЕГО ТОКЕН. Стенд читает
    # .env (его грузит `main`), а проба, не импортировавшая `main`, — нет:
    # в CI в .env лежит свой `SECRET_KEY`, и токен пробы 72 стенд не принимал,
    # страница «Пользователи» открывалась гостю, тумблеров было «[]» (прогон
    # 36486120393). Локально ключа в .env нет — обе стороны брали умолчание,
    # и отказ был не виден. Явное значение перекрывает .env: load_dotenv
    # существующее не трогает
    import auth
    env["SECRET_KEY"] = auth.SECRET_KEY
    env.pop("FLY_APP_NAME", None)
    журнал = open(os.path.join(os.path.dirname(база), "stand_%d.log" % порт), "w",
                  encoding="utf-8", errors="replace")
    п = subprocess.Popen([sys.executable, "-X", "utf8", "-m", "uvicorn", "main:app",
                          "--host", "127.0.0.1", "--port", str(порт), "--log-level", "warning"],
                         cwd=КОРЕНЬ, env=env, stdout=журнал, stderr=subprocess.STDOUT)
    for _ in range(120):
        time.sleep(0.5)
        try:
            socket.create_connection(("127.0.0.1", порт), timeout=0.3).close()
            return п, "http://127.0.0.1:%d" % порт
        except OSError:
            if п.poll() is not None:
                break
    п.kill()
    raise ConnectionError("стенд пробы на порту %d не поднялся" % порт)


# ПЕРЕПИСАНО ЗАХОДОМ, КОТОРЫЙ ЧИНИЛ ПРОВЕРЯЕМОЕ (№352, письмо «Расход»),
# ЧЕТЫРЕ ПУНКТА §6.0.3:
#   · было: карточка — предок `.card` у `#usage-balance`; «следующий блок» —
#     строка `.usage-since` под рядом карточек;
#   · стало: плитка — предок `.v2-tile`; «следующий блок» — узел сразу
#     за рядом плиток (`.usage-tiles` + следующий сосед);
#   · почему: страница переведена на v2 — карточек `.card` на ней нет,
#     а строка учёта уехала в строку отбора НАД плитками и о сдвиге
#     под ними не говорит ничего;
#   · контроль на новой формулировке — тот же подлог (резерв высоты
#     примечания снят), прогон в отчёте захода.
# Вторая правка того же захода: перед замером — загрузка шрифтов
# и «дёрганье» окна на пиксель (разбор — у ожидания в `_снять`). Было —
# сразу после `networkidle`; стало — после `document.fonts.ready`
# и пересчёта единиц окна; почему — корневой кегль от `vw` принимал два
# значения в зависимости от порядка прогона, и доля пикселя читалась как
# сдвиг от состояния (шрифт гипотезой был, замером — нет: все грани
# `loaded`); контроль — тот же подлог.
ЗАМЕР = """() => {
  const карта = document.querySelector('#usage-balance').closest('.v2-tile');
  const прим = document.querySelector('#usage-balance-note');
  const r = карта.getBoundingClientRect();
  const след = document.querySelector('.usage-tiles').nextElementSibling.getBoundingClientRect();
  const подвал = document.querySelector('.site-footer');
  return {высота: r.height, верх_следующего: след.top + scrollY,
          подвал: подвал ? подвал.getBoundingClientRect().top + scrollY : null,
          вылезает: карта.scrollWidth > карта.clientWidth + 0.5
                    || прим.getBoundingClientRect().bottom > r.bottom + 0.5,
          обрезан: прим.scrollHeight > прим.clientHeight + 1,
          число: document.querySelector('#usage-balance').innerText.trim(),
          текст: (прим.getAttribute('title') || прим.innerText).trim()};
}"""


def _снять(база_адрес, состояние, подлог_css, кадры):
    import check_hover as ch
    from playwright.sync_api import sync_playwright
    ch.БАЗА = база_адрес
    ch.ПОЧТА, ch.ПАРОЛЬ = ПОЧТА, ПАРОЛЬ
    итог = {}
    with sync_playwright() as p:
        бр = p.chromium.launch(headless=False)
        for ш in ШИРИНЫ:
            к = бр.new_context(viewport={"width": ш, "height": 900}, has_touch=ш < 600)
            с = к.new_page()
            ch._войти(с)
            с.goto(база_адрес + "/admin/usage", wait_until="networkidle", timeout=45000)
            if подлог_css:
                с.add_style_tag(content=подлог_css)
                с.wait_for_timeout(100)
            # ШРИФТ ДОЖИДАЕТСЯ ЗАМЕРА (№352, письмо «Расход»). `networkidle`
            # не обещает применённой гарнитуры: подогнанный запасной шрифт
            # расходится с настоящим на доли пикселя, и замер 2026-09-26
            # на 2560 дал 191.3 против 191.2 px у ОДНОЙ И ТОЙ ЖЕ плитки
            # в двух состояниях — при полном совпадении, когда шрифт
            # загружен. Состояние шрифтов ДО ожидания печатается: это
            # доказательство, а не догадка (тот же урок, что §6.0.16).
            шрифт_до = с.evaluate("() => document.fonts.status")
            с.evaluate("() => document.fonts.ready.then(() => true)")
            # КОРНЕВОЙ КЕГЛЬ СЧИТАЕТСЯ ОТ `vw`, И CHROME ДАЁТ ЕМУ ДВА ЗНАЧЕНИЯ
            # (замер 2026-09-26, 2560): на первой отрисовке `vw` берётся
            # от всей ширины окна — корень 17.000 px, после любого изменения
            # размера — от ширины без резерва полосы (`scrollbar-gutter:
            # stable` у корня) — 16.984 px. 0.016 px в корне дают 0.125 px
            # у плитки и 1.45 px у подвала, и какое из двух значений попадало
            # в замер, решал ПОРЯДОК прогона, а не проверяемое состояние
            # (подтверждено дважды по кругу трёх состояний). Окно дёргается
            # на пиксель и обратно: замер всегда во втором, устойчивом.
            с.set_viewport_size({"width": ш + 1, "height": 900})
            с.set_viewport_size({"width": ш, "height": 900})
            с.wait_for_timeout(50)
            итог[ш] = с.evaluate(ЗАМЕР)
            итог[ш]["шрифт_до"] = шрифт_до
            if кадры:
                с.locator("#usage-balance").locator("xpath=ancestor::div[contains(@class,'v2-tile')][1]") \
                    .screenshot(path=os.path.join(кадры, "balance-%s-%d.png" % (состояние, ш)))
            к.close()
        бр.close()
    return итог


СОСТОЯНИЯ = (("получен", "ok", True), ("сеть", "net", True),
             ("ключ отклонён", "401", True), ("ключа нет", "ok", False))


def прогон(подлог_css="", кадры=None):
    врем = tempfile.mkdtemp(prefix="usage_balance_")
    сервер = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Остаток)
    threading.Thread(target=сервер.serve_forever, daemon=True).start()
    адрес = "http://127.0.0.1:%d/api/v1/credits" % сервер.server_address[1]
    замеры = {}
    стенды = []
    try:
        база = _копия_базы(врем)
        for ключ_есть in (True, False):
            п, база_адрес = _стенд(база, адрес, ключ_есть)
            стенды.append(п)
            for имя, режим, нужен_ключ in СОСТОЯНИЯ:
                if нужен_ключ is not ключ_есть:
                    continue
                _режим["значение"] = режим
                замеры[имя] = _снять(база_адрес, имя, подлог_css, кадры)
            п.terminate()
            п.wait(15)
    finally:
        for п in стенды:
            if п.poll() is None:
                п.kill()
        сервер.shutdown()
        shutil.rmtree(врем, ignore_errors=True)
    return замеры


def разобрать(замеры):
    плохо = []
    for ш in ШИРИНЫ:
        строки = {и: замеры[и][ш] for и in замеры}
        высоты = [р["высота"] for р in строки.values()]
        верх = [р["верх_следующего"] for р in строки.values()]
        подвал = [р["подвал"] for р in строки.values()]
        print("  %4d  " % ш + " · ".join("%s: %.1f / %.1f%s" % (
            и, р["высота"], р["верх_следующего"],
            "" if р.get("шрифт_до", "loaded") == "loaded" else " (шрифт догружался)")
            for и, р in строки.items()))
        if max(высоты) - min(высоты) > ДОПУСК:
            плохо.append("%d: высота карточки разная %s" % (ш, [round(в, 1) for в in высоты]))
        if max(верх) - min(верх) > ДОПУСК or max(подвал) - min(подвал) > ДОПУСК:
            плохо.append("%d: следующий блок или подвал сдвинулись" % ш)
        for и, р in строки.items():
            if р["вылезает"]:
                плохо.append("%d, %s: текст вылезает из карточки" % (ш, и))
            if р["обрезан"]:
                плохо.append("%d, %s: текст не влез в три строки" % (ш, и))
            # Последнее удачное значение — либо числом, либо словами «не было»:
            # у стенда, поднятого без ключа, удачного запроса не было ни одного.
            if и != "получен" and not ("Последний:" in р["текст"]
                                       or "Удачных запросов" in р["текст"]):
                плохо.append("%d, %s: не сказано про последнее значение" % (ш, и))
    if "Последний: 7.65" + chr(0xa0) + "$" not in замеры["сеть"][ШИРИНЫ[0]]["текст"]:
        плохо.append("сеть: не показано последнее удачное значение 7.65 $")
    for и, нужно in (("сеть", "сеть"), ("ключ отклонён", "HTTP 401"), ("ключа нет", "Ключа OpenRouter нет")):
        if нужно not in замеры[и][ШИРИНЫ[0]]["текст"]:
            плохо.append("%s: причина не названа" % и)
    return плохо


ПОДЛОГ = ".usage-balance-note { height: auto !important; -webkit-line-clamp: unset !important; }"


def доказать_подлог(замеры):
    """Независимо от вердикта: разброс высоты карточки по состояниям на
    каждой ширине. Подлог состоялся, только если разброс стал больше нуля —
    иначе «ЛОВИТ» значило бы находку не про резерв высоты."""
    return {ш: round(max(р[ш]["высота"] for р in замеры.values())
                     - min(р[ш]["высота"] for р in замеры.values()), 1) for ш in ШИРИНЫ}


def main_():
    кадры = None
    if "--кадры" in sys.argv:
        кадры = sys.argv[sys.argv.index("--кадры") + 1]
        os.makedirs(кадры, exist_ok=True)
    if "--контроль" in sys.argv:
        print("КОНТРОЛЬ: резерв высоты у примечания снят (%s)" % ПОДЛОГ)
        замеры = прогон(ПОДЛОГ)
        доказ = доказать_подлог(замеры)
        плохо = разобрать(замеры)
        for п in плохо:
            print("  находка:", п)
        print("  доказательство: разброс высоты карточки по ширинам %s px" % доказ)
        if not any(доказ.values()):
            print("КОНТРОЛЬ: ПОДЛОГ НЕ СОСТОЯЛСЯ — высота не изменилась, вердикт не значит ничего")
            return 2
        print("КОНТРОЛЬ: %s" % ("ЛОВИТ" if плохо else "НЕ ЛОВИТ — проба слепа"))
        return 0 if плохо else 1
    плохо = разобрать(прогон("", кадры))
    for п in плохо:
        print("  ПЛОХО:", п)
    print("ИТОГ: состояний %d, ширин %d, находок %d" % (len(СОСТОЯНИЯ), len(ШИРИНЫ), len(плохо)))
    return 1 if плохо else 0


if __name__ == "__main__":
    sys.exit(main_())
