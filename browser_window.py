# -*- coding: utf-8 -*-
"""ВИДИМОЕ ОКНО БРАУЗЕРА ПРОБЫ — НА ВТОРОМ МОНИТОРЕ.

ЗАЧЕМ. У владельца два монитора, и окна головных проб открывались
на ОСНОВНОМ — поверх его работы. Проб с видимым окном два десятка,
и все подключают `probe_guard`; поэтому размещение ставится ОДНИМ
местом — заменой `BrowserType.launch` (синхронной и асинхронной),
а не правкой каждого вызова: двадцатый вызов, написанный завтра,
получил бы окно на основном мониторе молча (§6.0.7).

ЧТО ДЕЛАЕТ. При `headless=False` добавляет Chromium ключ
`--window-position=X,Y` — левый верхний угол ПЕРВОГО НЕ ОСНОВНОГО
монитора. Геометрия берётся у Windows (`EnumDisplayMonitors`),
числом не вписана. Монитор один либо ОС не Windows — не делает ничего
и печатает это строкой.

ПОЧЕМУ ШИРИНА ПРОБЫ ОТ МОНИТОРА НЕ ЗАВИСИТ. Пробы задают `viewport`
в контексте, и Playwright ЭМУЛИРУЕТ его — окно может быть уже, чем
вьюпорт, замер при этом тот же. Проверено `check_browser_window.py
--ширина`: вьюпорт 2560 на втором мониторе шириной 1920 даёт те же
`innerWidth`, ширину полосы прокрутки и `devicePixelRatio`, что на
основном.

ОТКЛЮЧИТЬ: `BROWSER_MONITOR=primary` в окружении — окно откроется
как раньше. Им пользуется отрицательный контроль.

ОДИН ПРОЦЕСС БРАУЗЕРА НА ПРОГОН (задача 346, заход 6, блок 2). Замер:
передним становится ПЕРВОЕ окно НОВОГО процесса Chromium, на 60 мс, —
второе и следующие окна того же процесса фокус не берут. Возврат фокуса
(ниже) эти 60 мс не отменяет, а полноэкранная игра владельца
сворачивается ровно от них. Поэтому прогон из многих проб
(`check_metrics --стенд`, полный `check_portfolio`) поднимает ОДИН
видимый браузер `общий_браузер()` и кладёт его адрес в
`BROWSER_SHARED_CDP`; видимый запуск в пробе при этой переменной
не заводит процесс, а подключается к общему (`connect_over_cdp`).
Контексты и страницы пробы — новые окна того же процесса, передними
они не становятся. `browser.close()` у подключённого браузера закрывает
только свои контексты и отключается — общий живёт до конца прогона.

Модуль без импортов проекта: его читает `probe_guard`, а тот обязан
подключаться одной строкой в любой пробе.
"""
import os
import sys

ОТКЛЮЧИТЬ_ПЕРЕМЕННАЯ = "BROWSER_MONITOR"
# `BROWSER_KEEP_FOCUS=1` — не возвращать фокус (подлог проверки фокуса)
ОТКЛЮЧИТЬ_ФОКУС = "BROWSER_KEEP_FOCUS"


def мониторы():
    """Список (x, y, ширина, высота, основной). Пусто — спросить нечем."""
    if sys.platform != "win32":
        return []
    import ctypes
    from ctypes import wintypes

    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                    ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", RECT),
                    ("rcWork", RECT), ("dwFlags", wintypes.DWORD)]

    user32 = ctypes.windll.user32
    итог = []
    ПРОЦ = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HMONITOR, wintypes.HDC,
                              ctypes.POINTER(RECT), wintypes.LPARAM)

    def _один(hmon, _hdc, _rect, _lp):
        инфо = MONITORINFO()
        инфо.cbSize = ctypes.sizeof(MONITORINFO)
        if user32.GetMonitorInfoW(hmon, ctypes.byref(инфо)):
            р = инфо.rcMonitor
            итог.append((р.left, р.top, р.right - р.left, р.bottom - р.top,
                         bool(инфо.dwFlags & 1)))
        return 1

    user32.EnumDisplayMonitors(None, None, ПРОЦ(_один), 0)
    return итог


def второй_монитор():
    """(x, y, ширина, высота) первого НЕ основного монитора либо None."""
    for x, y, ш, в, основной in мониторы():
        if not основной:
            return x, y, ш, в
    return None


def ключ_позиции():
    """Ключ Chromium для окна на втором мониторе либо None."""
    if os.environ.get(ОТКЛЮЧИТЬ_ПЕРЕМЕННАЯ, "").strip().lower() == "primary":
        return None
    м = второй_монитор()
    if not м:
        return None
    return "--window-position=%d,%d" % (м[0], м[1])


ЖУРНАЛ_ПЕРЕМЕННАЯ = "BROWSER_WINDOW_LOG"
ОБЩИЙ_ПЕРЕМЕННАЯ = "BROWSER_SHARED_CDP"


def окон_нет():
    """Есть ли на этой площадке чем показать окно (задача 357).

    В CI дисплея нет вовсе: `headless=False` там падает «Missing X server
    or $DISPLAY», и первой же пробой валился весь ряд стенда. Спрашивается
    ФАКТ площадки, а не имя площадки: под `xvfb-run` дисплей есть, и окно
    снова поднимается. Общий браузер существует ради ОДНОГО окна
    на прогон (§6.0.3); там, где окон нет, поднимать его нечем и не за чем.
    """
    if os.name == "nt":
        return False
    return not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def _в_журнал(событие):
    """Строка в журнал окон пробы (`BROWSER_WINDOW_LOG`), если он задан.

    Его читает `check_window_focus.py`: сколько раз за прогон запускался
    видимый браузер и сколько видимых окон открылось. Без переменной —
    ничего. Сбой записи печатается строкой, а не глушится (§6.0.1)."""
    путь = os.environ.get(ЖУРНАЛ_ПЕРЕМЕННАЯ)
    if not путь:
        return
    try:
        with open(путь, "a", encoding="utf-8") as ф:
            ф.write("%s pid=%d %s\n" % (событие, os.getpid(), os.path.basename(sys.argv[0])))
    except OSError as e:
        print("[окно] журнал окон не записан: %s" % e)


def _дополнить(kwargs):
    if kwargs.get("headless", True):
        return kwargs
    _в_журнал("launch-headed")
    ключ = ключ_позиции()
    if not ключ:
        return kwargs
    аргументы = list(kwargs.get("args") or [])
    if not any(str(а).startswith("--window-position") for а in аргументы):
        аргументы.append(ключ)
    kwargs["args"] = аргументы
    return kwargs


def _передний():
    """Окно, у которого сейчас клавиатура (hwnd), либо None."""
    if sys.platform != "win32":
        return None
    import ctypes
    return ctypes.windll.user32.GetForegroundWindow() or None


def вернуть_фокус(hwnd):
    """Вернуть клавиатуру окну `hwnd`, если её забрал браузер пробы.

    ЗАЧЕМ — ЗАМЕР 2026-09-18: вход пробы отправил пароль с лишней
    буквой «d» на конце. Новое окно браузера становится ПЕРЕДНИМ, и
    нажатия человека, работающего в своём окне, уходят в поле страницы
    пробы. Окно на втором мониторе этого не отменяет: фокус не зависит
    от монитора. Страница пробы фокус ОС не требует — Playwright
    эмулирует его сам, — поэтому клавиатура возвращается прежнему окну.

    Прямой `SetForegroundWindow` из фонового процесса Windows запрещает;
    `AttachThreadInput` к потоку текущего переднего окна снимает запрет."""
    if sys.platform != "win32" or not hwnd:
        return False
    import ctypes
    u = ctypes.windll.user32
    k = ctypes.windll.kernel32
    import time
    # Новое окно на миг оставляет передний план ПУСТЫМ (замер: класс
    # переднего окна сразу после `new_page` — пустая строка); ждём,
    # пока он определится, иначе возврат уйдёт в никуда.
    сейчас = u.GetForegroundWindow()
    for _ in range(20):
        if сейчас:
            break
        time.sleep(0.05)
        сейчас = u.GetForegroundWindow()
    if сейчас == hwnd or not u.IsWindow(hwnd):
        return сейчас == hwnd
    чужой = u.GetWindowThreadProcessId(сейчас, None)
    свой = k.GetCurrentThreadId()
    u.AttachThreadInput(свой, чужой, True)
    try:
        u.SetForegroundWindow(hwnd)
    finally:
        u.AttachThreadInput(свой, чужой, False)
    return u.GetForegroundWindow() == hwnd


def _с_возвратом(прежний, асинхр):
    """Обёртка: запомнить переднее окно, открыть, вернуть фокус."""
    if асинхр:
        async def обёртка(self, *a, **kw):
            было = _передний()
            итог = await прежний(self, *a, **kw)
            вернуть_фокус(было)
            return итог
    else:
        def обёртка(self, *a, **kw):
            было = _передний()
            итог = прежний(self, *a, **kw)
            вернуть_фокус(было)
            return итог
    обёртка._второй_монитор = True
    return обёртка


def _общий(kwargs):
    """Адрес общего браузера прогона для ВИДИМОГО запуска либо None.

    Невидимый запуск идёт как прежде: активаций у него нет. Ключи запуска
    при подключении не применяются — видимые пробы проекта их не передают
    (замер захода 6: особых `args` у видимых запусков ноль); переданные
    называются строкой, а не глушатся."""
    адрес = os.environ.get(ОБЩИЙ_ПЕРЕМЕННАЯ, "").strip()
    if not адрес or kwargs.get("headless", True):
        return None
    if kwargs.get("args"):
        print("[окно] общий браузер прогона: ключи запуска пробы не применены: %s"
              % kwargs.get("args"))
    _в_журнал("launch-shared")
    return адрес


def _свободный_порт():
    import socket
    с = socket.socket()
    с.bind(("127.0.0.1", 0))
    порт = с.getsockname()[1]
    с.close()
    return порт


class общий_браузер:
    """Один видимый браузер на прогон: `with общий_браузер(): …`.

    Уже задан (вложенный прогон) либо видимого окна не бывает (не Windows,
    второго монитора нет) — ничего не заводит. Первое окно процесса
    открывается СРАЗУ и держится до конца: это и есть единственная
    активация прогона, после неё фокус возвращается прежнему окну."""

    def __enter__(self):
        self._свой = None
        if os.environ.get(ОБЩИЙ_ПЕРЕМЕННАЯ):
            return os.environ[ОБЩИЙ_ПЕРЕМЕННАЯ]
        if окон_нет():
            print("[окно] дисплея нет — пробы идут невидимым браузером")
            return None
        from playwright.sync_api import sync_playwright
        порт = _свободный_порт()
        self._пв = sync_playwright().start()
        self._бр = self._пв.chromium.launch(
            headless=False, args=["--remote-debugging-port=%d" % порт])
        стр = self._бр.new_page()
        стр.set_content("<title>Окно проверок</title><p>Окно проверок прогона. "
                        "Пробы открывают здесь свои окна; закроется само.</p>")
        адрес = "http://127.0.0.1:%d" % порт
        os.environ[ОБЩИЙ_ПЕРЕМЕННАЯ] = адрес
        self._свой = адрес
        print("[окно] общий браузер прогона: %s" % адрес)
        return адрес

    def __exit__(self, *_):
        if not self._свой:
            return False
        os.environ.pop(ОБЩИЙ_ПЕРЕМЕННАЯ, None)
        try:
            self._бр.close()
        finally:
            self._пв.stop()
        return False


def поставить():
    """Заменяет launch у Playwright. Идемпотентно; нет Playwright — ничего."""
    try:
        from playwright.sync_api import BrowserType as Синхр
        from playwright.async_api import BrowserType as Асинхр
    except ImportError:
        return False
    if getattr(Синхр.launch, "_второй_монитор", False):
        return False
    прежний_с = Синхр.launch
    прежний_а = Асинхр.launch

    def launch_с(self, *a, **kw):
        адрес = _общий(kw)
        if адрес:
            return self.connect_over_cdp(адрес)
        return прежний_с(self, *a, **_дополнить(kw))

    async def launch_а(self, *a, **kw):
        адрес = _общий(kw)
        if адрес:
            return await self.connect_over_cdp(адрес)
        return await прежний_а(self, *a, **_дополнить(kw))

    launch_с._второй_монитор = True
    launch_а._второй_монитор = True
    Синхр.launch = _с_возвратом(launch_с, False)
    Асинхр.launch = _с_возвратом(launch_а, True)
    # Каждая новая страница и контекст в головном режиме — НОВОЕ ОКНО,
    # и оно тоже забирает фокус; возврат ставится и на них.
    if os.environ.get(ОТКЛЮЧИТЬ_ФОКУС, "") != "1":
        from playwright.sync_api import Browser as Бс, BrowserContext as Кс
        from playwright.async_api import Browser as Ба, BrowserContext as Ка
        for класс, асинхр in ((Бс, False), (Кс, False), (Ба, True), (Ка, True)):
            класс.new_page = _с_возвратом(класс.new_page, асинхр)
    else:
        Синхр.launch, Асинхр.launch = launch_с, launch_а
    return True


# ── ОСТАНОВКА КАДРОВ ОКНА ПРОБЫ (задача 344) ────────────────────────────
# Корень не найден, и догадка «фоновое торможение» опровергнута (заход 6
# задачи 346). Дальше не угадываем, а КОПИМ ДАННЫЕ: каждый случай, когда
# окно пробы дало меньше КАДРОВ_ПОРОГ кадров за 500 мс, пишется строкой
# JSON в файл, который живёт между заходами (каталог закрыт .gitignore).
КАДРОВ_ПОРОГ = 10
ОСТАНОВКИ_ПЕРЕМЕННАЯ = "FRAME_STALL_LOG"
ОСТАНОВКИ_ФАЙЛ = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "review_screenshots", "frame_stalls.jsonl")

_ЗАМЕР_КАДРОВ = """() => new Promise(r => { let n = 0; const t0 = performance.now();
    const f = () => { n++; if (performance.now() - t0 < 500) requestAnimationFrame(f); };
    requestAnimationFrame(f); setTimeout(() => r(n), 520); })"""


def _окна_хрома():
    """[{title, exe, rect, visible, iconic}] всех окон верхнего уровня
    процессов Chromium. По заголовку окно пробы не найти: при стоящей
    отрисовке новый заголовок до окна может не доехать — ровно в нужный
    момент. Окно пробы опознаётся по `page.sx/sy/ow/oh` той же записи."""
    import ctypes
    from ctypes import wintypes
    import psutil
    u = ctypes.windll.user32
    найдено = []
    ПРОЦ = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def _одно(hwnd, _lp):
        pid = wintypes.DWORD()
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        try:
            exe = psutil.Process(pid.value).name()
        except psutil.Error:
            return True
        if not exe.lower().startswith("chrom") or not u.IsWindowVisible(hwnd):
            return True
        б = ctypes.create_unicode_buffer(256)
        u.GetWindowTextW(hwnd, б, 256)
        р = wintypes.RECT()
        u.GetWindowRect(hwnd, ctypes.byref(р))
        найдено.append({"title": б.value[:80], "exe": exe,
                        "rect": [р.left, р.top, р.right - р.left, р.bottom - р.top],
                        "iconic": bool(u.IsIconic(hwnd))})
        return True
    u.EnumWindows(ПРОЦ(_одно), 0)
    return найдено


def _переднее_окно():
    import ctypes
    from ctypes import wintypes
    u = ctypes.windll.user32
    hwnd = u.GetForegroundWindow()
    if not hwnd:
        return None
    б = ctypes.create_unicode_buffer(256)
    u.GetWindowTextW(hwnd, б, 256)
    к = ctypes.create_unicode_buffer(128)
    u.GetClassNameW(hwnd, к, 128)
    pid = wintypes.DWORD()
    u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    имя = None
    try:
        import psutil
        имя = psutil.Process(pid.value).name()
    except Exception as e:  # процесс мог завершиться между вызовами
        имя = "?" + type(e).__name__
    р = wintypes.RECT()
    u.GetWindowRect(hwnd, ctypes.byref(р))
    return {"title": б.value[:120], "class": к.value, "exe": имя,
            "rect": [р.left, р.top, р.right - р.left, р.bottom - р.top]}


def записать_остановку(страница, кадров, где):
    """Строка JSON про одну остановку. Сбой записи печатается (§6.0.1)."""
    import json
    import time
    запись = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "probe": os.path.basename(sys.argv[0]),
              "where": где, "frames_500ms": кадров, "threshold": КАДРОВ_ПОРОГ}
    try:
        запись["page"] = страница.evaluate(
            "() => ({visibility: document.visibilityState, focus: document.hasFocus(),"
            " title: document.title, w: innerWidth, h: innerHeight,"
            " sx: screenX, sy: screenY, ow: outerWidth, oh: outerHeight})")
    except Exception as e:  # страница могла закрыться — остановка всё равно пишется
        запись["page"] = {"error": type(e).__name__}
    if sys.platform == "win32":
        try:
            запись["chrome_windows"] = _окна_хрома()
        except Exception as e:  # данные — не повод ронять пробу
            запись["chrome_windows"] = {"error": type(e).__name__}
        запись["foreground"] = _переднее_окно()
    try:
        import psutil
        запись["cpu_percent"] = psutil.cpu_percent(interval=0.3)
        запись["cpu_per_core"] = psutil.cpu_percent(interval=None, percpu=True)
        запись["chrome_processes"] = sum(1 for п in psutil.process_iter(["name"])
                                         if (п.info.get("name") or "").lower().startswith("chrom"))
    except Exception as e:
        запись["cpu_error"] = type(e).__name__
    путь = os.environ.get(ОСТАНОВКИ_ПЕРЕМЕННАЯ) or ОСТАНОВКИ_ФАЙЛ
    try:
        os.makedirs(os.path.dirname(путь), exist_ok=True)
        with open(путь, "a", encoding="utf-8") as ф:
            ф.write(json.dumps(запись, ensure_ascii=False) + "\n")
    except OSError as e:
        print("[окно] остановка кадров не записана: %s" % e)
    return путь


def кадров_окна(страница, где=""):
    """Кадров requestAnimationFrame за 500 мс. Меньше порога — строка в файл
    остановок (`FRAME_STALL_LOG` либо review_screenshots/frame_stalls.jsonl)."""
    n = страница.evaluate(_ЗАМЕР_КАДРОВ)
    if n < КАДРОВ_ПОРОГ:
        записать_остановку(страница, n, где)
    return n
