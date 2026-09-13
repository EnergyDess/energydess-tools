"""ОТКАЗ ЗАГРУЗКИ ГЛАВНОЙ НАЗЫВАЕТ ПРИЧИНУ, А НЕ ВЫВОД ffmpeg (задача 330).

ПРОВЕРКА, код 1 при беде, 2 — спросить нечем.

ВОПРОС. Когда ffmpeg не справился со сжатием, человек видел последнюю
строку его вывода: «ffmpeg не смог сжать ролик: frame= 102 fps=0.0 …»
или «Conversion failed!». Из неё не следует ни что случилось, ни что
делать. Отказ обязан сказать причину словами и совет, а технический
текст — лечь в журнал сервера: без него разбирать нечего.

ПАМЯТЬ ОТБИРАЕТСЯ ПО-НАСТОЯЩЕМУ, А НЕ ИЗОБРАЖАЕТСЯ. ffmpeg из колеса
запускается обёрткой в Job Object Windows с жёстким потолком памяти
процесса (`IMAGEIO_FFMPEG_EXE` — штатная ручка `imageio_ffmpeg`, код
приложения не знает, что его ffmpeg обёрнут). При 60 МБ настоящий
ffmpeg на ролике 1920 на 1080 падает с `malloc of size … failed`
и `Conversion failed!` — ровно то, что видел человек.

ГРАНИЦА, И ОНА НАЗВАНА. На проде (Linux) нехватку памяти решает ядро:
ffmpeg получает SIGKILL (код −9), и в выводе нет ни слова о памяти.
Этот путь на Windows-стенде не воспроизводится — его сторожит тест
`tests/test_landing_fail.py` на разборе причины, а не эта проба.

МЕРКА — ВИДИМОЕ ЧЕЛОВЕКУ. Спрашивается текст поля `error` ответа панели
(его и печатает карточка места) и строка `[landing]` журнала стенда.
Признаки технического текста и человеческой причины записаны ЗДЕСЬ,
у `landing_media` не берутся.

СЛУЧАИ:
  память       ролик 1080p, потолок ffmpeg 60 МБ → причина «памяти»
               и совет про разрешение или длительность; в журнале
               технический вывод ffmpeg
  картинка     обрезанный JPEG (признак картинки проходит, сжатие
               падает) → причина словами без имени исключения;
               в журнале имя исключения
  бомба        PNG 30000 на 30000 → отказ с причиной, а не 500
  обратный     тот же ролик, потолок 400 МБ → загрузка проходит

КЛЮЧИ:
  --контроль   два подлога В ПАМЯТИ стенда, по звену на каждое условие:
               отказ снова несёт хвост ffmpeg (человеку); журнал теряет
               технический текст. Каждый обязан быть назван своим случаем.
"""
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile

try:
    import probe_guard  # noqa: F401
except ImportError:
    pass

sys.stdout.reconfigure(encoding="utf-8")
КОРЕНЬ = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, КОРЕНЬ)

# ТЕХНИЧЕСКИЙ ТЕКСТ — то, что человек прочитать не может: вывод ffmpeg,
# код процесса, имя исключения Python
ТЕХНИЧЕСКОЕ = re.compile(
    r"ffmpeg|frame=|fps=|Conversion failed|malloc|get_buffer|"
    r"код \d{2,}|\b[A-Z][A-Za-z]*(Error|Exception)\b|errno", re.I)
# ПРИЧИНА ДЛЯ ЧЕЛОВЕКА: слово причины И совет, что делать
ПРИЧИНА_ПАМЯТЬ = re.compile(r"памят", re.I)
СОВЕТ_ПАМЯТЬ = re.compile(r"разрешени|длительност", re.I)
ПРИЧИНА_КАРТИНКА = re.compile(r"повреждён|не jpg|не картинк|пересохран", re.I)

ОБЁРТКА = r'''import ctypes, ctypes.wintypes as wt, os, subprocess, sys
os.environ.pop("IMAGEIO_FFMPEG_EXE", None)
import imageio_ffmpeg
здесь = os.path.dirname(os.path.abspath(__file__))
мб = int(open(os.path.join(здесь, "limit.txt")).read().strip())
class IO(ctypes.Structure):
    _fields_ = [(n, ctypes.c_ulonglong) for n in "abcdef"]
class BASIC(ctypes.Structure):
    _fields_ = [("a", ctypes.c_longlong), ("b", ctypes.c_longlong), ("LimitFlags", wt.DWORD),
                ("c", ctypes.c_size_t), ("d", ctypes.c_size_t), ("e", wt.DWORD),
                ("f", ctypes.POINTER(ctypes.c_ulong)), ("g", wt.DWORD), ("h", wt.DWORD)]
class EXT(ctypes.Structure):
    _fields_ = [("B", BASIC), ("I", IO), ("ProcessMemoryLimit", ctypes.c_size_t),
                ("j", ctypes.c_size_t), ("k", ctypes.c_size_t), ("l", ctypes.c_size_t)]
k = ctypes.WinDLL("kernel32", use_last_error=True)
k.CreateJobObjectW.restype = wt.HANDLE
k.CreateJobObjectW.argtypes = [ctypes.c_void_p, wt.LPCWSTR]
k.SetInformationJobObject.argtypes = [wt.HANDLE, ctypes.c_int, ctypes.c_void_p, wt.DWORD]
k.AssignProcessToJobObject.argtypes = [wt.HANDLE, wt.HANDLE]
k.OpenProcess.restype = wt.HANDLE
k.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
job = k.CreateJobObjectW(None, None)
e = EXT()
e.B.LimitFlags = 0x100 | 0x2000
e.ProcessMemoryLimit = мб * 1048576
if not k.SetInformationJobObject(job, 9, ctypes.byref(e), ctypes.sizeof(e)):
    sys.exit(97)
p = subprocess.Popen([imageio_ffmpeg.get_ffmpeg_exe()] + sys.argv[1:])
h = k.OpenProcess(0x1F0FFF, False, p.pid)
if not (h and k.AssignProcessToJobObject(job, h)):
    p.kill()
    sys.exit(98)
sys.exit(p.wait())
'''


def собрать(раб):
    import imageio_ffmpeg
    from PIL import Image
    ф = imageio_ffmpeg.get_ffmpeg_exe()
    ролик = os.path.join(раб, "big1080.mp4")
    subprocess.run([ф, "-hide_banner", "-y", "-f", "lavfi", "-i",
                    "testsrc2=size=1920x1080:rate=30", "-t", "5", "-c:v", "libx264",
                    "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-an", ролик],
                   capture_output=True, check=True)
    # ОБРЕЗАННЫЙ JPEG, А НЕ PNG: у PNG `verify()` проверяет суммы кусков
    # и отсекает обрезку ещё признаком «это картинка» (человеческий текст),
    # а JPEG признак проходит и падает уже на сжатии — ровно та ветка,
    # где человеку уходило имя исключения
    полный = os.path.join(раб, "full.jpg")
    Image.effect_mandelbrot((900, 600), (-2.2, -1.2, 1.0, 1.2), 60).convert("RGB").save(
        полный, "JPEG", quality=95)
    данные = open(полный, "rb").read()
    битый = os.path.join(раб, "broken.jpg")
    open(битый, "wb").write(данные[:len(данные) // 2])
    # PNG-БОМБА: заголовок 30000 на 30000 при крошечных данных. Pillow
    # отказывает `DecompressionBombError` уже при открытии
    import struct
    import zlib

    def кусок(тип, тело):
        return (struct.pack(">I", len(тело)) + тип + тело
                + struct.pack(">I", zlib.crc32(тип + тело) & 0xffffffff))
    бомба = os.path.join(раб, "bomb.png")
    сигнатура = bytes([0x89]) + b"PNG" + bytes([13, 10, 26, 10])
    open(бомба, "wb").write(сигнатура
                           + кусок(b"IHDR", struct.pack(">IIBBBBB", 30000, 30000, 8, 2, 0, 0, 0))
                           + кусок(b"IDAT", zlib.compress(bytes(100))) + кусок(b"IEND", b""))
    обёртка = os.path.join(раб, "ffwrap.py")
    open(обёртка, "w", encoding="utf-8").write(ОБЁРТКА)
    cmd = os.path.join(раб, "ff.cmd")
    open(cmd, "w", encoding="ascii").write('@"%s" "%s" %%*\r\n' % (sys.executable, обёртка))
    return ролик, битый, бомба, cmd


def места():
    import landing_defs as ld
    видео = next(м["id"] for м in ld.МЕСТА if м["kind"] == ld.ВИДЕО)
    картинка = next(м["id"] for м in ld.МЕСТА if м["kind"] == ld.КАРТИНКА)
    return видео, картинка


def прогон(подлог=None):
    if os.name != "nt":
        print("ПРОПУСК: потолок памяти ffmpeg ставится Job Object Windows")
        sys.exit(2)
    import httpx
    import check_upload_guard as cug
    import make_local_user as сид
    раб = tempfile.mkdtemp(prefix="probe330-")
    if not re.fullmatch(r"[\x20-\x7e]+", раб):
        print("ПРОПУСК: каталог временных файлов с не-ASCII путём (%r) — "
              "cmd-обёртка его не прочтёт" % раб)
        sys.exit(2)
    база = os.path.join(раб, "app.db")
    исх = sqlite3.connect(os.path.join(КОРЕНЬ, "app.db"))
    цель = sqlite3.connect(база)
    исх.backup(цель)
    исх.close()
    цель.close()
    врем = os.path.join(раб, "tmp")
    os.makedirs(врем)
    ролик, битый, бомба, cmd = собрать(раб)
    видео, картинка = места()
    прежний = os.environ.get("IMAGEIO_FFMPEG_EXE")
    os.environ["IMAGEIO_FFMPEG_EXE"] = cmd
    итог = {}
    try:
        п = cug.поднять(база, врем, подлог)
    finally:
        if прежний is None:
            os.environ.pop("IMAGEIO_FFMPEG_EXE", None)
        else:
            os.environ["IMAGEIO_FFMPEG_EXE"] = прежний
    журнал_путь = os.path.join(раб, "stand_%d.log" % cug.ПОРТ)
    try:
        кука = cug.войти(сид.EMAIL, сид.PASSWORD)
        with httpx.Client(base_url="http://127.0.0.1:%d" % cug.ПОРТ,
                          cookies={"access_token": кука}, timeout=600) as к:
            for случай, место, путь, тип, мб in (
                    ("память", видео, ролик, "video/mp4", 60),
                    ("картинка", картинка, битый, "image/jpeg", 400),
                    ("бомба", картинка, бомба, "image/png", 400),
                    ("обратный", видео, ролик, "video/mp4", 400)):
                open(os.path.join(раб, "limit.txt"), "w").write(str(мб))
                было = os.path.getsize(журнал_путь) if os.path.exists(журнал_путь) else 0
                with open(путь, "rb") as f:
                    о = к.post("/admin/api/landing/%s" % место,
                               files={"file": (os.path.basename(путь), f, тип)})
                try:
                    тело = о.json()
                except ValueError:
                    тело = {}
                with open(журнал_путь, encoding="utf-8", errors="replace") as ж:
                    ж.seek(было)
                    новое = ж.read()
                строка = next((с for с in новое.splitlines()
                               if с.startswith("[landing] %s" % место)), "")
                итог[случай] = {"код": о.status_code, "текст": тело.get("error") or "",
                                "журнал": строка}
    finally:
        п.kill()
        п.wait()
        shutil.rmtree(раб, ignore_errors=True)
    return итог


def проверить(итог):
    плохо = []
    for случай, з in итог.items():
        print("  %-9s код %s  человеку: %s" % (случай, з["код"], з["текст"] or "(отказа нет)"))
        print("  %-9s журнал: %s" % ("", (з["журнал"] or "(строки нет)")[:220]))
    техн = sum(1 for з in итог.values() if з["текст"] and ТЕХНИЧЕСКОЕ.search(з["текст"]))
    print("  отказов с техническим текстом: %d из %d"
          % (техн, sum(1 for з in итог.values() if з["текст"])))
    з = итог.get("память", {})
    if з.get("код") == 200:
        плохо.append("память: загрузка прошла — потолок ffmpeg не сработал, замер не состоялся")
    else:
        if ТЕХНИЧЕСКОЕ.search(з.get("текст", "")):
            плохо.append("память: человеку ушёл технический текст")
        if not (ПРИЧИНА_ПАМЯТЬ.search(з.get("текст", "")) and СОВЕТ_ПАМЯТЬ.search(з.get("текст", ""))):
            плохо.append("память: причина или совет не названы")
        if not ТЕХНИЧЕСКОЕ.search(з.get("журнал", "")):
            плохо.append("память: в журнале нет технической строки")
    з = итог.get("картинка", {})
    if ТЕХНИЧЕСКОЕ.search(з.get("текст", "")):
        плохо.append("картинка: человеку ушёл технический текст")
    if not ПРИЧИНА_КАРТИНКА.search(з.get("текст", "")):
        плохо.append("картинка: причина не названа")
    if not ТЕХНИЧЕСКОЕ.search(з.get("журнал", "")):
        плохо.append("картинка: в журнале нет технической строки")
    з = итог.get("бомба", {})
    if з.get("код", 500) >= 500 or not з.get("текст"):
        плохо.append("бомба: сервер ответил %s без причины" % з.get("код"))
    elif ТЕХНИЧЕСКОЕ.search(з["текст"]):
        плохо.append("бомба: человеку ушёл технический текст")
    if итог.get("обратный", {}).get("код") != 200:
        плохо.append("обратный: законная загрузка не прошла (%s)"
                     % итог.get("обратный", {}).get("текст"))
    for п in плохо:
        print("  ПЛОХО " + п)
    return плохо


ПОДЛОГИ = (
    ("хвост-человеку",
     "import landing_media as _лм\n"
     "_прежн = _лм.ОтказЗагрузки.__init__\n"
     "def _init(self, текст, код=400, журнал=None):\n"
     "    _прежн(self, текст + ((' ' + журнал) if журнал else ''), код)\n"
     "_лм.ОтказЗагрузки.__init__ = _init\n",
     "память: человеку ушёл технический текст"),
    ("журнал-пуст",
     "import landing_media as _лм\n"
     "_прежн = _лм.ОтказЗагрузки.__init__\n"
     "def _init(self, текст, код=400, журнал=None):\n"
     "    _прежн(self, текст, код)\n"
     "    self.журнал = None\n"
     "_лм.ОтказЗагрузки.__init__ = _init\n",
     "память: в журнале нет технической строки"),
)


def main():
    if "--контроль" in sys.argv:
        найдено = 0
        for имя, код, ждём in ПОДЛОГИ:
            print("ПОДЛОГ %s" % имя)
            итог = прогон(код)
            плохо = проверить(итог)
            есть = ждём in плохо
            найдено += есть
            print("  -> %s" % ("НАЙДЕН" if есть else "НЕ НАЙДЕН"))
        print("КОНТРОЛЬ: найдено %d из %d" % (найдено, len(ПОДЛОГИ)))
        return 0 if найдено == len(ПОДЛОГИ) else 1
    итог = прогон()
    плохо = проверить(итог)
    print("ИТОГ: %s" % ("чисто" if not плохо else "БЕДА %d" % len(плохо)))
    return 1 if плохо else 0


if __name__ == "__main__":
    sys.exit(main())
