# -*- coding: utf-8 -*-
"""СЪЁМКА ЭКРАНОВ ВЕСОВ: блок состава со шкалами, кнопка справки, все пять
состояний привязки — на двух ширинах и в четырёх состояниях элемента.

═══════════════════════════════════════════════════════════════════════
ПОЧЕМУ ЭТО ФАЙЛ В РЕПОЗИТОРИИ, А НЕ СКРИПТ В СКРЕТЧПАДЕ
═══════════════════════════════════════════════════════════════════════

Та же причина, что у `check_hover.py`: инструмент съёмки писался заново
каждый заход, и знание о ловушках эмуляции терялось трижды. Здесь оно
не переписано и не скопировано — ИМПОРТИРОВАНО из `check_hover`:
`_включить_сенсор`, `_сверить`, `_снимок`, `_войти`. Вторая копия
разошлась бы с первой молча, и эта разошлась бы в худшую сторону —
у неё нет отрицательного контроля.

ЧЕМ ЭТО НЕ ЯВЛЯЕТСЯ. Это НЕ проверка: у неё нет понятия «правильно»
и код возврата всегда 0 (кроме падения). Она снимает кадры, а смотрит
на них человек. Проверка залипающей подсветки — соседний файл, и она
своя; в ряд девяти §6.0.2 ни та ни эта не входят.

ЧТО СНИМАЕТСЯ

  вкладка «Вес»      блок «Состав тела»: шкалы, числа границ, категории
  вкладка «Профиль»  подсказка закрытая и раскрытая; пять состояний
                     привязки (нет / новое / ok / reauth / ошибка)

СОСТОЯНИЯ ЭЛЕМЕНТА (CLAUDE.md §6.0.3): покой, наведение с ожиданием
конца перехода, фокус НАСТОЯЩИМ Tab, состояние после касания.
Один снимок состоянием не является — дефект живёт ровно там, куда
не посмотрели.

ЗАПУСК

    py -m uvicorn main:app --port 8899
    py make_local_user.py --seed --scale ok
    py check_scale_screens.py
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

import check_hover as ch     # noqa: E402

КУДА = os.environ.get("SHOTS_DIR", "C:/Temp/claude/scale")

# Состояния привязки ставятся скриптом сидирования — четыре из пяти
# снаружи не воспроизводятся вовсе (§8.0). Здесь только имена: сам
# переключатель зовётся отдельным процессом между прогонами.
СОСТОЯНИЯ = ["нет", "новое", "ok", "reauth", "ошибка"]

# Пауза длиннее самого длинного перехода. Та же величина и по той же
# причине, что в check_hover: короче — и снимок поймает середину
# перехода, то есть ещё исходный вид.
ПАУЗА = ch.ПАУЗА_ПЕРЕХОДА


def _вкладка(стр, имя):
    стр.click(f"[data-tab='{имя}']")
    стр.wait_for_timeout(700)


def _есть(стр, селектор):
    return стр.evaluate(
        "(с) => { const э = document.querySelector(с);"
        "  return !!э && э.offsetParent !== null; }", селектор)


def _текст(стр, селектор):
    return стр.evaluate(
        "(с) => { const э = document.querySelector(с);"
        "  return э ? э.innerText.trim().slice(0, 400) : null; }", селектор)


def снять(ширина, высота, сенсор, состояние):
    from playwright.sync_api import sync_playwright

    метка = f"{ширина}-{'touch' if сенсор else 'desk'}-{состояние}"
    отчёт = []
    with sync_playwright() as p:
        бр = p.chromium.launch()
        к = бр.new_context(viewport={"width": ширина, "height": высота},
                           has_touch=сенсор, is_mobile=сенсор)
        стр = к.new_page()
        cdp = к.new_cdp_session(стр)
        if сенсор:
            ch._включить_сенсор(cdp)
        ch._войти(стр)
        if сенсор:
            ch._включить_сенсор(cdp)

        стр.goto(f"{ch.БАЗА}/nutrition", wait_until="domcontentloaded", timeout=45000)
        стр.wait_for_timeout(2000)
        ch._сверить(стр, сенсор, f"{метка}: после загрузки дневника")

        # ── Вкладка «Вес»: блок состава ────────────────────────────────
        _вкладка(стр, "weight")
        стр.wait_for_timeout(900)
        ch._снимок(стр, cdp, сенсор, f"{КУДА}/вес-{метка}.png")
        отчёт.append(("блок состава виден", _есть(стр, "#wt-body")))
        отчёт.append(("карточек показателей",
                      стр.evaluate("() => document.querySelectorAll('#wt-body-grid .wt-bcell').length")))
        отчёт.append(("полос со шкалой",
                      стр.evaluate("() => document.querySelectorAll('#wt-body-grid .scale-bar').length")))
        отчёт.append(("строка про неполную анкету", _текст(стр, "#wt-body-gap")
                      if _есть(стр, "#wt-body-gap") else "нет"))
        отчёт.append(("первая карточка", _текст(стр, "#wt-body-grid .wt-bcell")))
        # Переполнение по горизонтали — главный вопрос на 390
        отчёт.append(("горизонтальная прокрутка страницы",
                      стр.evaluate("() => document.documentElement.scrollWidth > "
                                   "document.documentElement.clientWidth")))
        отчёт.append(("карточка шире своего места",
                      стр.evaluate("""() => {
                        let плохих = 0;
                        for (const к of document.querySelectorAll('#wt-body-grid .wt-bcell'))
                          if (к.scrollWidth > к.clientWidth + 1) плохих++;
                        return плохих; }""")))
        # Кегль подписей — не ниже системной ступени 0.8125rem = 13px
        отчёт.append(("минимальный кегль в блоке, px",
                      стр.evaluate("""() => {
                        let м = 99;
                        for (const э of document.querySelectorAll('#wt-body *'))
                          if (э.innerText && э.innerText.trim())
                            м = Math.min(м, parseFloat(getComputedStyle(э).fontSize));
                        return м; }""")))

        # ── Вкладка «Профиль»: подсказка и состояние привязки ──────────
        _вкладка(стр, "profile")
        стр.wait_for_timeout(900)
        ch._снимок(стр, cdp, сенсор, f"{КУДА}/привязка-покой-{метка}.png")
        отчёт.append(("форма подключения", _есть(стр, "#scale-disconnected")))
        отчёт.append(("блок «подключено»", _есть(стр, "#scale-connected")))
        отчёт.append(("плашка отзыва ключа", _есть(стр, "#scale-reauth")))
        отчёт.append(("кнопка синхронизации", _есть(стр, "#scale-sync-btn")))
        отчёт.append(("блок «стереть привязку»", _есть(стр, "#scale-give-up")))
        # ВЗАИМОИСКЛЮЧЕНИЕ — то самое, ради чего заведено одно состояние
        отчёт.append(("форма И «подключено» одновременно",
                      _есть(стр, "#scale-disconnected") and _есть(стр, "#scale-connected")))

        # подсказка: закрыта → наведение → нажатие
        подсказка = ".p-sec-title-hint .hint"
        отчёт.append(("подсказка раскрыта в покое",
                      стр.evaluate("(с) => { const э = document.querySelector(с + ' .hint-pop');"
                                   "  return э ? getComputedStyle(э).visibility : 'нет'; }",
                                   подсказка)))
        if not сенсор:
            стр.hover(подсказка + " .hint-btn")
            стр.wait_for_timeout(ПАУЗА)
            ch._снимок(стр, cdp, сенсор, f"{КУДА}/справка-наведение-{метка}.png")
            отчёт.append(("подсказка при наведении",
                          стр.evaluate("(с) => getComputedStyle(document.querySelector(с + ' .hint-pop')).visibility",
                                       подсказка)))
            стр.mouse.move(5, 5)
            стр.wait_for_timeout(ПАУЗА)
            отчёт.append(("подсказка после ухода мыши",
                          стр.evaluate("(с) => getComputedStyle(document.querySelector(с + ' .hint-pop')).visibility",
                                       подсказка)))
        стр.click(подсказка + " .hint-btn")
        стр.wait_for_timeout(ПАУЗА)
        ch._снимок(стр, cdp, сенсор, f"{КУДА}/справка-раскрыта-{метка}.png")
        отчёт.append(("подсказка после нажатия",
                      стр.evaluate("(с) => getComputedStyle(document.querySelector(с + ' .hint-pop')).visibility",
                                   подсказка)))
        отчёт.append(("aria-expanded",
                      стр.evaluate("(с) => document.querySelector(с + ' .hint-btn').getAttribute('aria-expanded')",
                                   подсказка)))
        отчёт.append(("текст подсказки", _текст(стр, подсказка + " .hint-pop")))
        # На сенсорной ширине уводим касание в сторону — подсказка обязана
        # закрыться нажатием, а не «уходом мыши», которого там нет
        стр.click("body", position={"x": 5, "y": 5})
        стр.wait_for_timeout(ПАУЗА)
        отчёт.append(("подсказка после касания мимо",
                      стр.evaluate("(с) => getComputedStyle(document.querySelector(с + ' .hint-pop')).visibility",
                                   подсказка)))
        # Фокус НАСТОЯЩИМ Tab, а не .focus(): :focus-visible от программного
        # фокуса не срабатывает, и снимок показал бы отсутствие обводки там,
        # где она есть. Табаем от начала страницы, пока не дойдём до кнопки:
        # «нажать Tab один раз» ничего не гарантирует — порядок обхода
        # задаёт разметка, а не наше предположение о ней
        стр.evaluate("() => document.body.focus()")
        дошли = False
        for _ in range(60):
            стр.keyboard.press("Tab")
            if стр.evaluate("() => !!document.activeElement.closest('.hint')"):
                дошли = True
                break
        стр.wait_for_timeout(ПАУЗА)
        отчёт.append(("Tab дошёл до кнопки справки", дошли))
        ch._снимок(стр, cdp, сенсор, f"{КУДА}/справка-фокус-{метка}.png")
        отчёт.append(("что в фокусе после Tab",
                      стр.evaluate("() => document.activeElement.className || document.activeElement.tagName")))

        ch._сверить(стр, сенсор, f"{метка}: в конце прогона")
        бр.close()
    return отчёт


def главная():
    состояние = sys.argv[1] if len(sys.argv) > 1 else "ok"
    if состояние not in СОСТОЯНИЯ:
        print(f"состояния «{состояние}» нет; есть: {', '.join(СОСТОЯНИЯ)}")
        return 2
    os.makedirs(КУДА, exist_ok=True)
    print("═" * 72)
    print(f"СЪЁМКА ЭКРАНОВ ВЕСОВ — состояние привязки «{состояние}»")
    print("═" * 72)
    for ширина, высота, сенсор in ((1440, 900, False), (390, 844, True)):
        print(f"\n■ {ширина}×{высота}  has_touch={сенсор}")
        for имя, значение in снять(ширина, высота, сенсор, состояние):
            print(f"   {имя:<38} {значение}")
    print(f"\nКадры: {КУДА}")
    return 0


if __name__ == "__main__":
    sys.exit(главная())
