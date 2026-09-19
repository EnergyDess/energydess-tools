# -*- coding: utf-8 -*-
"""ОКНА ПРОБ ЗА ПРОГОН: СКОЛЬКО ЗАПУСКОВ И СКОЛЬКО РАЗ ОКНО ПРОБЫ СТАЛО ПЕРЕДНИМ.

МЕРКА, код 0 (2 — мерить нечем: не Windows либо команда не запустилась).
Заведена заходом 6 задачи 346, блок 2: владелец играет, пока идут
проверки, и каждое окно браузера пробы, ставшее передним, сворачивает
полноэкранную игру. Окно на втором мониторе этого не отменяет — фокус
от монитора не зависит.

    py check_window_focus.py -- КОМАНДА [АРГУМЕНТЫ]

Гонит команду и параллельно опрашивает переднее окно Windows каждые
10 мс. АКТИВАЦИЯ — переход переднего окна к окну процесса Chromium
из поставки Playwright (путь содержит `ms-playwright`): свой браузер
владельца так не называется и не считается. ЗАПУСКИ — строки
`launch-headed` журнала `BROWSER_WINDOW_LOG`, который пишет
`browser_window` при каждом запуске видимого браузера.

ЗАМЕР ЗАХОДА: активация бывает ОДНА НА ПРОЦЕСС Chromium — первое окно
нового процесса; второе и следующие окна того же процесса передними
не становятся (опыт с тремя контекстами подряд: 1 активация на первом).
Опрос раз в 10 мс видит активацию длиной 60 мс, после которой
`browser_window` возвращает фокус; короче 10 мс — пропустит, и это
граница мерки.
"""
import ctypes
import os
import subprocess
import sys
import tempfile
import threading
import time

import probe_guard  # noqa: F401 — внешний отказ говорится словом (§3)

sys.stdout.reconfigure(encoding="utf-8")


def _процесс(hwnd):
    from ctypes import wintypes
    u, k = ctypes.windll.user32, ctypes.windll.kernel32
    pid = wintypes.DWORD()
    u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    h = k.OpenProcess(0x1000, False, pid.value)
    if not h:
        return ""
    buf = ctypes.create_unicode_buffer(1024)
    n = wintypes.DWORD(1024)
    ок = k.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n))
    k.CloseHandle(h)
    return buf.value if ок else ""


def прогнать(команда, опрос_мс=10):
    """(код команды, активаций, запусков видимого браузера, окон видимого браузера)."""
    журнал = os.path.join(tempfile.mkdtemp(prefix="window_focus_"), "windows.log")
    среда = dict(os.environ, BROWSER_WINDOW_LOG=журнал)
    активаций = [0]
    стоп = threading.Event()

    def опрос():
        u = ctypes.windll.user32
        прежний, был_пробой = None, False
        while not стоп.is_set():
            h = u.GetForegroundWindow()
            if h != прежний:
                проба = bool(h) and "ms-playwright" in _процесс(h).lower()
                if проба and not был_пробой:
                    активаций[0] += 1
                прежний, был_пробой = h, проба
            time.sleep(опрос_мс / 1000)

    нить = threading.Thread(target=опрос, daemon=True)
    нить.start()
    try:
        код = subprocess.run(команда, env=среда).returncode
    finally:
        стоп.set()
        нить.join(1)
    строки = open(журнал, encoding="utf-8").read().splitlines() if os.path.exists(журнал) else []
    return (код, активаций[0], sum(с.startswith("launch-headed") for с in строки),
            sum(с.startswith("launch-shared") for с in строки))


def main():
    if sys.platform != "win32":
        print("ПРОПУСК: переднее окно спрашивается у Windows, здесь не Windows")
        return 2
    if "--" not in sys.argv or sys.argv.index("--") == len(sys.argv) - 1:
        print("ПРОПУСК: не передана команда (py check_window_focus.py -- КОМАНДА)")
        return 2
    команда = sys.argv[sys.argv.index("--") + 1:]
    т = time.monotonic()
    код, акт, запусков, общих = прогнать(команда)
    print("ОКНА ПРОБ: команда %s, код %d, %.0f с" % (" ".join(команда), код, time.monotonic() - т))
    print("  запусков видимого браузера (новый процесс Chromium): %d" % запусков)
    print("  подключений к общему браузеру прогона: %d" % общих)
    print("  активаций окна пробы (стало передним): %d" % акт)
    return 0


if __name__ == "__main__":
    sys.exit(main())
