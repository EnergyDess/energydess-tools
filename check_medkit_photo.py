# -*- coding: utf-8 -*-
"""БОЕВОЙ ПУТЬ СНИМКА С ТЕЛЕФОНА — от файла камеры до ответа сервера.

ЗАЧЕМ ОТДЕЛЬНАЯ ПРОБА, ЕСЛИ ЕСТЬ `check_medkit_assist`.

Та подаёт НАРИСОВАННЫЙ кадр 900x560 PNG на 28 КБ. Камера Android отдаёт
12–108 Мпикс и до десяти мегабайт. Разница не в качестве съёмки, а в том,
что это РАЗНЫЕ ВЕТКИ КОДА: маленький кадр ужимается и уезжает в модель
на 670 КБ, большой упирается в память машины, `_upright_jpeg` ловит
MemoryError своим `except` и МОЛЧА отдаёт оригинал — 9898 КБ (замер
2026-08-25). Приёмка при этом печатала «13 из 13, полей неверно 0»,
а владелец на том же экране получал 502.

ЧТО МЕРИТСЯ. Приложение поднимается под ЖЁСТКИМ ПОТОЛКОМ ПАМЯТИ, равным
проду (`fly.toml`, `[[vm]] memory = "256mb"`), и в него уходит файл того
размера, что отдаёт камера. Спрашиваются ДВА числа: пик, который увидел
потолок, и СКОЛЬКО КИЛОБАЙТ РЕАЛЬНО УШЛО В МОДЕЛЬ. Второе важнее —
именно оно отличает «ужали» от «протащили мимо ужатия молча».

ГРАНИЦА, И ОНА НАЗВАНА. Потолок Windows (Job Object) на исчерпании
памяти возвращает процессу MemoryError, а cgroup Linux — УБИВАЕТ его.
То есть здесь дефект виден как «в модель уехал оригинал», а на Fly тот же
дефект виден как «ответа нет вовсе, прокси отдал 502». Проба ловит
ПРИЧИНУ, общую для обеих площадок; воспроизвести само убийство процесса
на этой машине нечем, и выдавать одно за другое нельзя.

Сервис моделей заменён заглушкой НАМЕРЕННО: вопрос пробы — что уходит
в модель, а не что она отвечает.

    py check_medkit_photo.py                # прогон, код 1 при находках
    py check_medkit_photo.py --контроль     # подлог; код 1, если проба слепа

Нужен стенд-аккаунт (`py make_local_user.py`). Браузера не нужно, в базу
проба не пишет. В ряды §6.0.2 не входит: поднимает своё приложение.
"""
import ctypes
import ctypes.wintypes as wt
import io
import json
import os
import random
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

КОРЕНЬ = os.path.dirname(os.path.abspath(__file__))
ПОТОЛОК_МБ = int(os.environ.get("MEDKIT_PHOTO_CAP", "256"))   # как в fly.toml
ПОРТ = int(os.environ.get("MEDKIT_PHOTO_PORT", "8913"))
ПОЧТА = "screenshot@local.dev"
ПАРОЛЬ = "Screenshot-Local-2026"

# РАЗРЕШЕНИЯ КАМЕР — не выдуманы. 12 Мпикс — умолчание Pixel и Galaxy S;
# 50 Мпикс — умолчание Redmi/Xiaomi и режим «высокое разрешение» у Samsung;
# 108 Мпикс — тот же режим у старших Xiaomi. Кадр приёмки стоит ПЕРВЫМ
# намеренно: он показывает, на чём прошлая проба была зелёной.
СЛУЧАИ = [
    ("приёмка (нарисованный кадр)",   900,   560, "PNG"),
    ("камера 12 Мпикс",              4000,  3000, "JPEG"),
    ("камера 50 Мпикс",              8160,  6120, "JPEG"),
    ("камера 108 Мпикс",            12000,  9000, "JPEG"),
]


def _потолок_картинки():
    """Потолок того, что вправе уехать в модель, — ИЗ КОДА, а не вписан
    сюда: второе число разошлось бы с первым молча (§6.0.7)."""
    т = io.open(os.path.join(КОРЕНЬ, "main.py"), encoding="utf-8").read()
    м = re.search(r'VISION_IMAGE_MAX_MB\s*=\s*float\(os\.getenv\([^,]+,\s*"([\d.]+)"', т)
    if not м:
        raise SystemExit("ОСТАНОВЛЕНО: VISION_IMAGE_MAX_MB не найден в main.py")
    return float(м.group(1))


# ── ЖЁСТКИЙ ПОТОЛОК ПАМЯТИ (Windows Job Object) ──────────────────────
JOB_MEM, JOB_KILL_ON_CLOSE, JOB_EXT_LIMIT = 0x100, 0x2000, 9


class _IO(ctypes.Structure):
    _fields_ = [(n, ctypes.c_ulonglong) for n in
                ("r_op", "w_op", "o_op", "r_tx", "w_tx", "o_tx")]


class _BASIC(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong),
                ("PerJobUserTimeLimit", ctypes.c_longlong),
                ("LimitFlags", wt.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wt.DWORD),
                ("Affinity", ctypes.POINTER(ctypes.c_ulong)),
                ("PriorityClass", wt.DWORD),
                ("SchedulingClass", wt.DWORD)]


class _EXT(ctypes.Structure):
    _fields_ = [("BasicLimitInformation", _BASIC), ("IoInfo", _IO),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t)]


_k = ctypes.WinDLL("kernel32", use_last_error=True)
_k.CreateJobObjectW.restype = wt.HANDLE
_k.CreateJobObjectW.argtypes = [ctypes.c_void_p, wt.LPCWSTR]
_k.SetInformationJobObject.restype = wt.BOOL
_k.SetInformationJobObject.argtypes = [wt.HANDLE, ctypes.c_int, ctypes.c_void_p, wt.DWORD]
_k.QueryInformationJobObject.restype = wt.BOOL
_k.QueryInformationJobObject.argtypes = [wt.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                         wt.DWORD, ctypes.POINTER(wt.DWORD)]
_k.AssignProcessToJobObject.restype = wt.BOOL
_k.AssignProcessToJobObject.argtypes = [wt.HANDLE, wt.HANDLE]
_k.OpenProcess.restype = wt.HANDLE
_k.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]


def _под_потолком(аргументы, мб, **kw):
    """Процесс с жёстким потолком памяти. Каждый вызов ПРОВЕРЯЕТСЯ: молча
    не назначенный потолок дал бы пробу, которая ничего не ограничивает
    и потому всегда зелёная (§6.0.1)."""
    job = _k.CreateJobObjectW(None, None)
    if not job:
        raise OSError(f"CreateJobObject отказал: {ctypes.get_last_error()}")
    инфо = _EXT()
    инфо.BasicLimitInformation.LimitFlags = JOB_MEM | JOB_KILL_ON_CLOSE
    инфо.ProcessMemoryLimit = int(мб) * 1048576
    if not _k.SetInformationJobObject(job, JOB_EXT_LIMIT, ctypes.byref(инфо),
                                      ctypes.sizeof(инфо)):
        raise OSError(f"SetInformationJobObject отказал: {ctypes.get_last_error()}")
    p = subprocess.Popen(аргументы, **kw)
    h = _k.OpenProcess(0x1F0FFF, False, p.pid)
    if not h:
        p.kill()
        raise OSError(f"OpenProcess отказал: {ctypes.get_last_error()}")
    if not _k.AssignProcessToJobObject(job, h):
        p.kill()
        raise OSError(f"AssignProcessToJobObject отказал: {ctypes.get_last_error()}")
    return p, job


def _пик_job(job):
    """Пик, который РЕАЛЬНО увидел потолок, — доказательство того, что он
    применён к нужному процессу, а не к пустому job."""
    инфо = _EXT()
    длина = wt.DWORD(0)
    if not _k.QueryInformationJobObject(job, JOB_EXT_LIMIT, ctypes.byref(инфо),
                                        ctypes.sizeof(инфо), ctypes.byref(длина)):
        raise OSError(f"QueryInformationJobObject отказал: {ctypes.get_last_error()}")
    return инфо.PeakJobMemoryUsed / 1048576, инфо.ProcessMemoryLimit / 1048576


def _кадр(w, h, формат):
    """Кадр, который сжимается как настоящая фотография.

    Ровная заливка ужалась бы в десяток килобайт и не воспроизвела бы
    ни веса файла, ни стоимости раскодирования, — то есть проба мерила бы
    не то, чем занят прод.
    """
    from PIL import Image, ImageDraw, ImageFont
    rnd = random.Random(20260825)
    плитка = Image.new("RGB", (400, 300))
    плитка.putdata([(rnd.randint(60, 210),) * 3 for _ in range(400 * 300)])
    им = плитка.resize((w, h), Image.BILINEAR)
    d = ImageDraw.Draw(им)
    try:
        ф = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", max(12, h // 12))
    except OSError:
        ф = ImageFont.load_default()
    d.text((w // 10, h // 3), "НУРОФЕН 200", fill=(20, 30, 90), font=ф)
    buf = io.BytesIO()
    им.save(buf, format=формат, **({"quality": 92} if формат == "JPEG" else {}))
    return buf.getvalue()


def _написать_заглушку(путь):
    """Заглушка сервиса моделей. Записывает, ЧТО именно к ней приехало."""
    строки = [
        "# -*- coding: utf-8 -*-",
        "import http.server, json, sys",
        "СОДЕРЖИМОЕ = json.dumps({'name': 'Нурофен', 'form': 'tablet',",
        "    'unit': 'tablet', 'qty_total': 20, 'expires_ym': '2028-06'},",
        "    ensure_ascii=False)",
        "ОТВЕТ = {'choices': [{'finish_reason': 'stop',",
        "         'message': {'content': СОДЕРЖИМОЕ}}],",
        "         'usage': {'completion_tokens': 40}}",
        "class H(http.server.BaseHTTPRequestHandler):",
        "    def do_POST(self):",
        "        n = int(self.headers.get('content-length') or 0)",
        "        сырое = self.rfile.read(n)",
        "        try:",
        "            c = json.loads(сырое)['messages'][0]['content']",
        "            url = c[0]['image_url']['url']",
        "            тело = url.partition(',')[2]",
        "            вышло = {'картинка_КБ': round(len(тело) * 3 / 4 / 1024),",
        "                     'запрос_КБ': round(n / 1024)}",
        "        except Exception as e:",
        "            вышло = {'не_разобрано': str(e)[:100]}",
        "        open(sys.argv[2], 'w', encoding='utf-8').write(json.dumps(вышло))",
        "        т = json.dumps(ОТВЕТ).encode()",
        "        self.send_response(200)",
        "        self.send_header('content-type', 'application/json')",
        "        self.send_header('content-length', str(len(т)))",
        "        self.end_headers()",
        "        self.wfile.write(т)",
        "    def log_message(self, *a): pass",
        "http.server.HTTPServer(('127.0.0.1', int(sys.argv[1])), H).serve_forever()",
    ]
    io.open(путь, "w", encoding="utf-8").write("\n".join(строки))


def _ждать(порт, процесс=None, сек=90):
    т = time.time()
    while time.time() - т < сек:
        if процесс is not None and процесс.poll() is not None:
            return False
        try:
            with socket.create_connection(("127.0.0.1", порт), 0.5):
                return True
        except OSError:
            time.sleep(0.4)
    return False


def прогон():
    """Гонит все случаи через живой эндпоинт. Возвращает (строки, пик, лимит)."""
    врем = tempfile.mkdtemp(prefix="medkit_photo_")
    путь_заглушки = os.path.join(врем, "stub.py")
    отчёт = os.path.join(врем, "got.json")
    _написать_заглушку(путь_заглушки)

    stub = subprocess.Popen([sys.executable, путь_заглушки, str(ПОРТ + 1), отчёт],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not _ждать(ПОРТ + 1, stub, 30):
        stub.kill()
        raise SystemExit("ОСТАНОВЛЕНО: заглушка не поднялась")

    окр = dict(os.environ)
    окр.update({"DB_PATH": os.path.join(КОРЕНЬ, "app.db"),
                "OPENROUTER_URL": f"http://127.0.0.1:{ПОРТ + 1}/v1/chat/completions",
                "OPENROUTER_API_KEY": "stub", "PYTHONIOENCODING": "utf-8"})

    журнал = open(os.path.join(врем, "server.log"), "wb")
    app, job = _под_потолком(
        [sys.executable, "-m", "uvicorn", "main:app", "--port", str(ПОРТ),
         "--log-level", "warning"],
        ПОТОЛОК_МБ, cwd=КОРЕНЬ, env=окр, stdout=журнал, stderr=subprocess.STDOUT)
    строки = []
    try:
        if not _ждать(ПОРТ, app):
            raise SystemExit("ОСТАНОВЛЕНО: стенд не поднялся")
        import http.cookiejar
        cj = http.cookiejar.CookieJar()
        оп = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
        оп.open(urllib.request.Request(
            f"http://127.0.0.1:{ПОРТ}/login",
            f"email={ПОЧТА.replace('@', '%40')}&password={ПАРОЛЬ}".encode(),
            {"Content-Type": "application/x-www-form-urlencoded"}))
        if not any(c.name == "access_token" for c in cj):
            raise SystemExit(f"ОСТАНОВЛЕНО: вход не состоялся ({ПОЧТА}). "
                             "Пересейте: py make_local_user.py --seed")

        for имя, w, h, формат in СЛУЧАИ:
            данные = _кадр(w, h, формат)
            io.open(отчёт, "w", encoding="utf-8").write("{}")
            гр = "----medkitphoto"
            расш = "jpg" if формат == "JPEG" else "png"
            шапка = (f"--{гр}\r\nContent-Disposition: form-data; "
                     f"name=\"file\"; filename=\"IMG_20260825.{расш}\"\r\n"
                     f"Content-Type: image/{формат.lower()}\r\n\r\n")
            м = шапка.encode() + данные + f"\r\n--{гр}--\r\n".encode()
            t = time.perf_counter()
            try:
                r = оп.open(urllib.request.Request(
                    f"http://127.0.0.1:{ПОРТ}/medkit/api/assist", м,
                    {"Content-Type": f"multipart/form-data; boundary={гр}"}),
                    timeout=180)
                код = r.status
            except urllib.error.HTTPError as e:
                код = e.code
            except Exception as e:
                код = f"ОБРЫВ/{type(e).__name__}"
            мс = (time.perf_counter() - t) * 1000
            try:
                ушло = json.load(io.open(отчёт, encoding="utf-8"))
            except Exception:
                ушло = {}
            строки.append({"имя": имя, "wh": f"{w}x{h}", "мп": w * h / 1e6,
                           "файл_КБ": len(данные) / 1024, "код": код, "мс": мс,
                           "ушло_КБ": ушло.get("картинка_КБ"),
                           "жив": app.poll() is None})
            if app.poll() is not None:
                break
        пик, лимит = _пик_job(job)
    finally:
        app.kill()
        stub.kill()
        журнал.close()
        _k.CloseHandle(ctypes.c_void_p(job))
    return строки, пик, лимит


def печать(строки, пик, лимит, потолок_кар):
    print(f"{'случай':<30}{'кадр':>12}{'Мпикс':>7}{'файл КБ':>9}"
          f"{'код':>7}{'в модель КБ':>13}{'мс':>7}  процесс")
    беды = 0
    for с in строки:
        ушло = "—" if с["ушло_КБ"] is None else str(с["ушло_КБ"])
        мимо = с["ушло_КБ"] is not None and с["ушло_КБ"] > потолок_кар * 1024
        плохо = мимо or с["код"] != 200 or not с["жив"]
        беды += 1 if плохо else 0
        print(f"{с['имя']:<30}{с['wh']:>12}{с['мп']:>7.1f}{с['файл_КБ']:>9.0f}"
              f"{str(с['код']):>7}{ушло:>13}{с['мс']:>7.0f}  "
              f"{'ЖИВ' if с['жив'] else 'УМЕР'}"
              f"{'  <- МИМО УЖАТИЯ' if мимо else ''}")
    print(f"\nДОКАЗАТЕЛЬСТВО ПОТОЛКА: job видел пик {пик:.0f} МБ "
          f"при лимите {лимит:.0f} МБ")
    print(f"потолок картинки в модель: {потолок_кар:.0f} МБ "
          f"(VISION_IMAGE_MAX_MB, взят из main.py)")
    return беды


def _пик_разбора():
    """ДОКАЗАТЕЛЬСТВО ПОДЛОГА: независимый замер пика памяти на разборе
    кадра 50 Мпикс, ОТДЕЛЬНЫМ процессом с текущим main.py.

    Вердикт пробы доказательством не является: подлог, который
    не сработал, неотличим от слепой пробы (§6.0.3).
    """
    d = tempfile.mkdtemp(prefix="peak_")
    кадр = os.path.join(d, "k.jpg")
    io.open(кадр, "wb").write(_кадр(8160, 6120, "JPEG"))
    скрипт = os.path.join(d, "p.py")
    строки = [
        "# -*- coding: utf-8 -*-",
        "import sys, io, os, ctypes, ctypes.wintypes as wt",
        "sys.path.insert(0, sys.argv[2])",
        "os.environ.setdefault('DB_PATH', os.path.join(sys.argv[2], 'app.db'))",
        "class P(ctypes.Structure):",
        "    _fields_ = [('cb', wt.DWORD), ('pf', wt.DWORD),",
        "                ('pk', ctypes.c_size_t), ('ws', ctypes.c_size_t)] + [",
        "        (n, ctypes.c_size_t) for n in 'abcdef']",
        "k = ctypes.WinDLL('kernel32'); ps = ctypes.WinDLL('psapi')",
        "k.GetCurrentProcess.restype = wt.HANDLE",
        "ps.GetProcessMemoryInfo.argtypes = [wt.HANDLE, ctypes.POINTER(P), wt.DWORD]",
        "ps.GetProcessMemoryInfo.restype = wt.BOOL",
        "H = k.GetCurrentProcess()",
        "def rss():",
        "    s = P(); s.cb = ctypes.sizeof(P)",
        "    if not ps.GetProcessMemoryInfo(H, ctypes.byref(s), s.cb):",
        "        raise OSError('GetProcessMemoryInfo отказал')",
        "    return s.ws / 1048576, s.pk / 1048576",
        "import main",
        "a, _ = rss()",
        "main._upright_jpeg(io.open(sys.argv[1], 'rb').read())",
        "_, b = rss()",
        "print('PEAK|%.0f' % (b - a))",
    ]
    io.open(скрипт, "w", encoding="utf-8").write("\n".join(строки))
    p = subprocess.run([sys.executable, скрипт, кадр, КОРЕНЬ],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace",
                       env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    for л in (p.stdout or "").splitlines():
        if л.startswith("PEAK|"):
            return float(л.split("|")[1])
    raise SystemExit(f"замер пика не отработал: {(p.stderr or '')[-300:]}")


ПОДЛОГ_ЯКОРЬ = 'img.draft("RGB", (max_dim, max_dim))'

# ── ДОКАЗАТЕЛЬСТВА ПОДЛОГОВ ──────────────────────────────────────────
#
# НЕЗАВИСИМЫЙ замер того, что подлог собирался изменить. Вердикт пробы
# доказательством не является: подлог, который не сработал, неотличим
# от слепой пробы (§6.0.3).
#
# Здесь подлог кладётся в ФАЙЛ, то есть молча провалиться не умеет —
# неудачная запись бросает исключение в самом контроле. Доказательство
# всё равно снимается: «строка заменена» и «пик памяти вырос» —
# разные утверждения, и второе как раз то, ради чего подлог делается.
ДОКАЗАТЕЛЬСТВА = {
    "draft-снят": (_пик_разбора, "пик памяти на разборе кадра 50 Мпикс"),
}


def main():
    потолок_кар = _потолок_картинки()
    контроль = "--контроль" in sys.argv
    print(f"== БОЕВОЙ ПУТЬ СНИМКА · потолок памяти {ПОТОЛОК_МБ} МБ "
          f"(как в fly.toml) ==\n")
    строки, пик, лимит = прогон()
    беды = печать(строки, пик, лимит, потолок_кар)
    print(f"\nнаходок: {беды}")
    if not контроль:
        return 1 if беды else 0

    print("\n== ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ ==")
    print("Подлог: снять draft() из `_upright_jpeg` — ровно тот порядок,\n"
          "что стоял до 2026-08-25. Проба ОБЯЗАНА назвать находку.\n")
    путь = os.path.join(КОРЕНЬ, "main.py")
    было = io.open(путь, encoding="utf-8").read()
    if ПОДЛОГ_ЯКОРЬ not in было:
        print("ПОДЛОГ НЕ СОСТОЯЛСЯ: строки draft() в main.py нет")
        return 1
    чисто = _пик_разбора()
    try:
        io.open(путь, "w", encoding="utf-8").write(
            было.replace(ПОДЛОГ_ЯКОРЬ, "pass  # ПОДЛОГ: draft снят"))
        грязно = _пик_разбора()
        print(f"ДОКАЗАТЕЛЬСТВО ПОДЛОГА: пик разбора 50 Мпикс "
              f"{чисто:.0f} МБ -> {грязно:.0f} МБ")
        if грязно < чисто * 1.5:
            print("ПОДЛОГ НЕ СОСТОЯЛСЯ: пик не вырос — контроль недействителен")
            return 1
        строки2, пик2, лимит2 = прогон()
        print()
        беды2 = печать(строки2, пик2, лимит2, потолок_кар)
        print(f"\nнаходок с подлогом: {беды2}")
    finally:
        io.open(путь, "w", encoding="utf-8").write(было)
        print("main.py возвращён")
    if беды2 <= беды:
        print("\nПРОБА СЛЕПА: подлог не дал новых находок")
        return 1
    print(f"\nконтроль пройден: чисто {беды}, с подлогом {беды2}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
