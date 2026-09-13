"""ЗАГРУЗКА ФАЙЛА: ДОХОДЯТ ЛИ БАЙТЫ ДО ДИСКА РАНЬШЕ ПРОВЕРКИ ПРАВ (задача 327).

ПРОВЕРКА, код 1 при беде: здесь спрашивается НАШ код.

ВОПРОС. `UploadFile` в параметрах обработчика FastAPI разбирает ДО тела
функции, то есть до строки `if not user`. Файл больше мегабайта Starlette
пишет во временный файл машины (`SpooledTemporaryFile`, порог 1 МБ) —
значит гость, приславший гигабайт, получит 401, но уже после того, как
гигабайт лёг на диск. Проба спрашивает ровно это: СКОЛЬКО БАЙТ УВИДЕЛ
ДИСК, пока шёл запрос, которому отказано.

МЕРКА НЕ БЕРЁТ ДАННЫЕ У ПРОВЕРЯЕМОГО КОДА. Стенд поднимается СВОИМ
процессом с отдельным каталогом временных файлов (`TEMP`/`TMP`/`TMPDIR`),
и отдельный поток пробы каждые 5 мс складывает размеры файлов в нём.
Вторая мерка — счётчик записи ПРОЦЕССА у операционной системы
(`psutil.io_counters().write_bytes`): она не знает ни о каталоге,
ни о Starlette. На Windows в счётчик входят и сетевые записи, поэтому
пара сотен байт ответа там законна; мерой служит мегабайтный порядок.

ТЕЛО ШЛЁТСЯ СЫРЫМ СОКЕТОМ, кусками по 256 КБ. httpx на досрочном ответе
сервера роняет запись и теряет сам ответ; сокет читает строку статуса
в тот момент, когда она пришла, и отправку прекращает.

СЛУЧАИ:
  гость      — каждое место приёма файла, 8 МБ с Content-Length;
  нет прав   — сосед (не админ, без дневника) на места, куда ему нельзя;
  вес        — админ сверх предела места: с Content-Length и без него;
  обратное   — законная загрузка админа проходит (200) и не оставляет
               файлов; без обратного «отказ всем» неотличим от «заслон работает»;
  без файла  — маршрут без объявления: форма 5 МБ отвергнута до диска;
  обрыв      — админ рвёт соединение на середине: что осталось во
               временном каталоге и в каталоге тома мест главной.

КЛЮЧИ:
  --контроль  три подлога В ПАМЯТИ стенда (`main.py` на диске не трогается),
              каждый ломает СВОЁ звено: права до тела, предел веса, уборку
              разбора формы на обрыве. Замер 2026-09-13: права 11 -> 1 из 11,
              вес 0 -> 20 МБ на диске, обрыв 0 -> 1 файл 4 МБ; остальные
              звенья в каждом подлоге остаются зелёными.
"""
import ast
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

try:
    import probe_guard  # noqa: F401  (ПРОПУСК вместо трассы)
except ImportError:
    pass

КОРЕНЬ = os.path.dirname(os.path.abspath(__file__))
ПОРТ = None  # назначает поднять()
МБ = 1024 * 1024


def места_из_кода():
    """Обработчики, принимающие файл: параметр `UploadFile` либо
    `request.form()` в теле. Разбором дерева, а не грепом."""
    дерево = ast.parse(open(os.path.join(КОРЕНЬ, "main.py"), encoding="utf-8").read())
    итог = []
    for узел in дерево.body:
        if not isinstance(узел, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        путь = метод = None
        for д in узел.decorator_list:
            if (isinstance(д, ast.Call) and isinstance(д.func, ast.Attribute)
                    and isinstance(д.func.value, ast.Name) and д.func.value.id == "app"
                    and д.func.attr in ("post", "put", "patch") and д.args
                    and isinstance(д.args[0], ast.Constant)):
                путь, метод = д.args[0].value, д.func.attr.upper()
        if not путь:
            continue
        файл = any("UploadFile" in ast.unparse(а.annotation)
                   for а in узел.args.args + узел.args.kwonlyargs if а.annotation)
        форма = any(isinstance(н, ast.Call) and isinstance(н.func, ast.Attribute)
                    and н.func.attr == "form" for н in ast.walk(узел))
        if файл or форма:
            итог.append((метод, путь, узел.name, "UploadFile" if файл else "request.form()"))
    return итог


def подставить(путь, база):
    с = sqlite3.connect(база)
    try:
        # Номер в пути нужен ТОЛЬКО чтобы маршрут совпал: права спрашиваются
        # до поиска записи. Стенд без сетов или позиций (его опустошают пробы
        # режима --пустое) не повод падать трассой — берётся заведомый номер.
        сет = (с.execute("select id from enshrouded_sets limit 1").fetchone() or ["x"])[0]
        поз = (с.execute("select m.id from medkit_items m join users u on u.id=m.user_id "
                         "where u.email='screenshot@local.dev' limit 1").fetchone() or [1])[0]
    finally:
        с.close()
    return (путь.replace("{slot_id}", "feed-1-1").replace("{set_id}", str(сет))
            .replace("{item_id}", str(поз)))


class Весы(threading.Thread):
    """Максимум байт во временном каталоге, пока идёт запрос."""

    def __init__(self, каталог):
        super().__init__(daemon=True)
        self.каталог, self.пик, self.файлов, self.стоп = каталог, 0, 0, False

    def снять(self):
        всего, n = 0, 0
        for корень, _, имена in os.walk(self.каталог):
            for и in имена:
                try:
                    всего += os.stat(os.path.join(корень, и)).st_size
                    n += 1
                except OSError:
                    pass
        return всего, n

    def run(self):
        while not self.стоп:
            в, n = self.снять()
            self.пик = max(self.пик, в)
            self.файлов = max(self.файлов, n)
            time.sleep(0.005)


def поднять(база, врем, подлог=None):
    # ПОРТ СВОБОДНЫЙ, А НЕ ВПИСАННЫЙ: две копии пробы (прогон и контроль
    # в `check_probe_start`) иначе делили бы один порт, и вторая падала бы
    # «стенд не поднялся» на исправном коде.
    global ПОРТ
    with socket.socket() as с:
        с.bind(("127.0.0.1", 0))
        ПОРТ = с.getsockname()[1]
    env = dict(os.environ)
    env.update({"DB_PATH": база, "PYTHONIOENCODING": "utf-8",
                "TEMP": врем, "TMP": врем, "TMPDIR": врем})
    код = ("import sys; sys.path.insert(0, %r); import main\n" % КОРЕНЬ
           + (подлог or "") +
           "\nimport uvicorn; uvicorn.run(main.app, host='127.0.0.1', port=%d, "
           "log_level='warning')" % ПОРТ)
    журнал = open(os.path.join(os.path.dirname(база), "stand_%d.log" % ПОРТ), "w",
                  encoding="utf-8", errors="replace")
    п = subprocess.Popen([sys.executable, "-X", "utf8", "-c", код], cwd=КОРЕНЬ,
                         env=env, stdout=журнал, stderr=subprocess.STDOUT)
    for _ in range(120):
        time.sleep(0.5)
        try:
            socket.create_connection(("127.0.0.1", ПОРТ), timeout=0.3).close()
            return п
        except OSError:
            if п.poll() is not None:
                break
    п.kill()
    raise ConnectionError("стенд пробы на порту %d не поднялся" % ПОРТ)


def войти(почта, пароль):
    import httpx
    with httpx.Client(base_url="http://127.0.0.1:%d" % ПОРТ, follow_redirects=False,
                      timeout=30) as к:
        о = к.post("/login", data={"email": почта, "password": пароль})
        кука = к.cookies.get("access_token")
        if not кука:
            raise ConnectionError("вход %s не прошёл: %s" % (почта, о.status_code))
        return кука


def загрузить(путь, кука, байт, длина=True, оборвать_на=None, врем=None, pid=None,
              поле="file", имя="big.mp4", тип="video/mp4"):
    """Шлёт multipart сырым сокетом. Отдаёт (статус|None, пик_во_врем, файлов,
    запись_процесса, отправлено)."""
    import psutil
    граница = "----probe327"
    голова = ("--%s\r\nContent-Disposition: form-data; name=\"%s\"; filename=\"%s\"\r\n"
              "Content-Type: %s\r\n\r\n" % (граница, поле, имя, тип)).encode()
    хвост = ("\r\n--%s--\r\n" % граница).encode()
    заголовки = ["POST %s HTTP/1.1" % путь, "Host: 127.0.0.1:%d" % ПОРТ,
                 "Content-Type: multipart/form-data; boundary=%s" % граница,
                 "Accept: application/json"]
    if кука:
        заголовки.append("Cookie: access_token=%s" % кука)
    if длина:
        заголовки.append("Content-Length: %d" % (len(голова) + байт + len(хвост)))
    else:
        заголовки.append("Transfer-Encoding: chunked")
    весы = Весы(врем)
    проц = psutil.Process(pid)
    до = проц.io_counters().write_bytes
    весы.start()
    с = socket.create_connection(("127.0.0.1", ПОРТ))
    с.settimeout(0.001)
    статус, отправлено, ответ = None, 0, b""

    def послать(данные):
        if длина:
            с.sendall(данные)
        else:
            с.sendall(b"%x\r\n" % len(данные) + данные + b"\r\n")

    def прочесть():
        nonlocal ответ, статус
        try:
            кус = с.recv(65536)
            if кус:
                ответ += кус
                if статус is None and b"\r\n" in ответ:
                    статус = int(ответ.split(b" ", 2)[1])
            return кус
        except (socket.timeout, BlockingIOError):
            return None
        except OSError:
            return b""

    try:
        с.settimeout(10)
        с.sendall(("\r\n".join(заголовки) + "\r\n\r\n").encode())
        послать(голова)
        # ДОСРОЧНЫЙ ОТВЕТ ЖДЁТСЯ ДО ТЕЛА. Сервер, отказавший по правам,
        # отвечает и закрывает соединение; кусок, досланный следом, получает
        # сброс, а сброс на Windows стирает непрочитанный ответ — проба
        # печатала «код None» при исправном отказе (прогон ряда 2026-09-13).
        с.settimeout(0.05)
        конец_ожидания = time.time() + 0.5
        while статус is None and time.time() < конец_ожидания:
            if прочесть() == b"":
                break
        с.settimeout(0.001)
        кусок = b"\0" * (256 * 1024)
        while отправлено < байт:
            if оборвать_на is not None and отправлено >= оборвать_на:
                break
            if прочесть() is not None and статус is not None:
                break
            n = min(len(кусок), байт - отправлено)
            try:
                с.settimeout(10)
                послать(кусок[:n])
                с.settimeout(0.001)
            except OSError:
                break
            отправлено += n
            time.sleep(0.004)
        if оборвать_на is None and отправлено >= байт and статус is None:
            try:
                с.settimeout(10)
                послать(хвост)
                if not длина:
                    с.sendall(b"0\r\n\r\n")
            except OSError:
                pass
        if оборвать_на is None:
            конец = time.time() + 60
            while статус is None and time.time() < конец:
                с.settimeout(1)
                if прочесть() == b"":
                    break
        else:
            time.sleep(0.5)
    finally:
        с.close()
    time.sleep(0.4)
    весы.стоп = True
    весы.join()
    return статус, весы.пик, весы.файлов, проц.io_counters().write_bytes - до, отправлено


def законная_картинка():
    """Настоящий PNG больше мегабайта: меньше порога Starlette держит
    в памяти, и вопрос «убрано ли за собой» не задался бы."""
    import io
    from PIL import Image
    img = Image.frombytes("RGB", (900, 700), os.urandom(900 * 700 * 3))
    буфер = io.BytesIO()
    img.save(буфер, "PNG")
    return буфер.getvalue()


def загрузить_байты(путь, кука, данные, врем, pid):
    import httpx
    import psutil
    весы = Весы(врем)
    до = psutil.Process(pid).io_counters().write_bytes
    весы.start()
    try:
        о = httpx.post("http://127.0.0.1:%d%s" % (ПОРТ, путь),
                       cookies={"access_token": кука}, timeout=60,
                       files={"file": ("ok.png", данные, "image/png")})
        ст = о.status_code
    finally:
        time.sleep(0.4)
        весы.стоп = True
        весы.join()
    return ст, весы.пик, весы.файлов, psutil.Process(pid).io_counters().write_bytes - до, len(данные)


def остатки(врем, том):
    н, б = 0, 0
    for кат in (врем, том):
        for корень, _, имена in os.walk(кат):
            for и in имена:
                try:
                    б += os.stat(os.path.join(корень, и)).st_size
                    н += 1
                except OSError:
                    pass
    return н, б


def мб(б):
    return "%.2f МБ" % (б / МБ)


def прогон(подлог=None, метка=""):
    import make_local_user as сид
    раб = tempfile.mkdtemp(prefix="probe327-")
    база = os.path.join(раб, "app.db")
    исх = sqlite3.connect(os.path.join(КОРЕНЬ, "app.db"))
    цель = sqlite3.connect(база)
    исх.backup(цель)
    исх.close()
    цель.close()
    врем = os.path.join(раб, "tmp")
    os.makedirs(врем)
    том = os.path.join(раб, "landing")
    os.makedirs(том, exist_ok=True)
    п = поднять(база, врем, подлог)
    плохо, строки = [], []
    try:
        админ = войти(сид.EMAIL, сид.PASSWORD)
        сосед = войти(сид.EMAIL_СОСЕД, сид.PASSWORD_СОСЕД)
        места = места_из_кода()
        print("%sМЕСТ ПРИЁМА ФАЙЛА в main.py: %d" % (метка, len(места)))

        print("\n-- ГОСТЬ, 8 МБ на каждое место --")
        защищено = 0
        for метод, путь, имя, как in места:
            адрес = подставить(путь, база)
            ст, пик, файлов, запись, посл = загрузить(адрес, None, 8 * МБ, врем=врем, pid=п.pid)
            ок = пик == 0 and ст in (401, 403)
            защищено += ок
            print("  %-4s %-44s код %s  на диске %-9s запись процесса %-9s отправлено %s"
                  % ("OK" if ок else "ПЛОХ", путь, ст, мб(пик), мб(запись), мб(посл)))
            if not ок:
                плохо.append("гость: %s — на диске %s, код %s" % (путь, мб(пик), ст))
        print("  проверяют права ДО тела: %d из %d" % (защищено, len(места)))
        строки.append(("гость", защищено, len(места)))

        print("\n-- НЕТ ПРАВ: сосед (не админ, без дневника), 8 МБ --")
        for путь in ("/admin/api/landing/{slot_id}", "/admin/api/enshrouded/set/{set_id}/image",
                     "/nutrition/api/ai-photo", "/nutrition/api/ai-chat-photo"):
            ст, пик, файлов, запись, посл = загрузить(подставить(путь, база), сосед, 8 * МБ,
                                                      врем=врем, pid=п.pid)
            ок = пик == 0 and ст == 403
            print("  %-4s %-44s код %s  на диске %s" % ("OK" if ок else "ПЛОХ", путь, ст, мб(пик)))
            if not ок:
                плохо.append("сосед: %s — на диске %s, код %s" % (путь, мб(пик), ст))

        print("\n-- ВЕС: админ сверх предела (картинка сета, предел 12 МБ) --")
        путь = подставить("/admin/api/enshrouded/set/{set_id}/image", база)
        ст, пик, _, _, посл = загрузить(путь, админ, 20 * МБ, врем=врем, pid=п.pid,
                                        имя="big.png", тип="image/png")
        ок = пик == 0 and ст == 413
        print("  %-4s с Content-Length 20 МБ: код %s  на диске %s  отправлено %s"
              % ("OK" if ок else "ПЛОХ", ст, мб(пик), мб(посл)))
        if not ок:
            плохо.append("вес с длиной: на диске %s, код %s" % (мб(пик), ст))
        ст, пик, _, _, посл = загрузить(путь, админ, 20 * МБ, длина=False, врем=врем,
                                        pid=п.pid, имя="big.png", тип="image/png")
        # Без длины заранее знать нечего: мерой служит то, что поток
        # остановлен у предела, а не дочитан до конца.
        ок = ст == 413 and пик <= 13 * МБ
        print("  %-4s без длины 20 МБ:        код %s  на диске %s  отправлено %s"
              % ("OK" if ок else "ПЛОХ", ст, мб(пик), мб(посл)))
        if not ок:
            плохо.append("вес без длины: на диске %s, код %s" % (мб(пик), ст))

        print("\n-- ОБРАТНОЕ: законная загрузка админа проходит, за собой не мусорит --")
        png = законная_картинка()
        ст, пик, _, _, посл = загрузить_байты(подставить("/admin/api/enshrouded/set/{set_id}/image",
                                                         база), админ, png, врем, п.pid)
        н, б = остатки(врем, os.path.join(раб, "нет"))
        ок = ст == 200 and н == 0
        print("  %-4s картинка %s: код %s, во временном каталоге пик %s, после %d файлов"
              % ("OK" if ок else "ПЛОХ", мб(len(png)), ст, мб(пик), н))
        if not ок:
            плохо.append("законная загрузка: код %s, остатков %d" % (ст, н))

        print("\n-- БЕЗ ОБЪЯВЛЕНИЯ: тело больше порога записи на диск --")
        ст, пик, _, _, посл = загрузить("/api/delete-account", админ, 5 * МБ, врем=врем, pid=п.pid)
        ок = ст == 413 and пик == 0
        print("  %-4s /api/delete-account 5 МБ формой: код %s, на диске %s"
              % ("OK" if ок else "ПЛОХ", ст, мб(пик)))
        if not ок:
            плохо.append("без объявления: код %s, на диске %s" % (ст, мб(пик)))

        print("\n-- ОБРЫВ: админ рвёт загрузку ролика на 4 МБ из 8 --")
        до = остатки(врем, том)
        загрузить(подставить("/admin/api/landing/{slot_id}", база), админ, 8 * МБ,
                  оборвать_на=4 * МБ, врем=врем, pid=п.pid)
        time.sleep(3)
        после = остатки(врем, том)
        ок = после[0] <= до[0] and после[1] <= до[1]
        print("  %-4s файлов во временном каталоге и на томе: до %d (%s), после %d (%s)"
              % ("OK" if ок else "ПЛОХ", до[0], мб(до[1]), после[0], мб(после[1])))
        if not ок:
            плохо.append("обрыв оставил %d файлов, %s" % (после[0] - до[0], мб(после[1] - до[1])))
    finally:
        п.kill()
        п.wait()
        time.sleep(0.5)
        shutil.rmtree(раб, ignore_errors=True)
    return плохо


def main():
    if "--контроль" in sys.argv:
        доказано = 0
        print("ПОДЛОГ 1: заслон прав до тела отключён в памяти стенда")
        плохо = прогон(подлог="main._права_до_тела = lambda *a, **k: None", метка="[подлог 1] ")
        найден = any(с.startswith("гость") for с in плохо)
        print("  => %s" % ("НАЙДЕН" if найден else "НЕ НАЙДЕН"))
        доказано += найден
        print("\nПОДЛОГ 2: предел веса до тела отключён в памяти стенда")
        плохо = прогон(подлог="main._предел_тела = lambda *a, **k: None", метка="[подлог 2] ")
        найден = any(с.startswith("вес") for с in плохо)
        print("  => %s" % ("НАЙДЕН" if найден else "НЕ НАЙДЕН"))
        доказано += найден
        print("\nПОДЛОГ 3: разбору формы возвращена исходная уборка Starlette")
        плохо = прогон(подлог="import starlette.formparsers as _ф; "
                              "_ф.MultiPartParser.parse = main._исходный_разбор_формы",
                       метка="[подлог 3] ")
        найден = any(с.startswith("обрыв") for с in плохо)
        print("  => %s" % ("НАЙДЕН" if найден else "НЕ НАЙДЕН"))
        доказано += найден
        print("\nКОНТРОЛЬ: найдено %d из 3" % доказано)
        return 0 if доказано == 3 else 1
    плохо = прогон()
    print("\nИТОГ: %s" % ("чисто" if not плохо else "БЕДА %d:\n  " % len(плохо)
                          + "\n  ".join(плохо)))
    return 1 if плохо else 0


if __name__ == "__main__":
    sys.exit(main())
