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


def _дополнить(kwargs):
    if kwargs.get("headless", True):
        return kwargs
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
        return прежний_с(self, *a, **_дополнить(kw))

    async def launch_а(self, *a, **kw):
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
