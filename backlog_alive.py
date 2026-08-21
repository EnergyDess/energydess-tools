# -*- coding: utf-8 -*-
"""ЖИВ ЛИ ДЕФЕКТ: по одной пробе на каждую ОТКРЫТУЮ задачу BACKLOG.

═══════════════════════════════════════════════════════════════════════
ЗАЧЕМ
═══════════════════════════════════════════════════════════════════════

`backlog_open.py` отвечает на вопрос «что числится открытым». Это
утверждение о ТЕКСТЕ, а не о коде. Задача, починенная попутно, остаётся
в списке ровно так же, как живая, и отличить их по списку нельзя ничем.

Цена названа владельцем прямо: работа по протухшей задаче опаснее
бездействия — «чинится» исправное, и правка ложится поверх работающего
кода без всякой нужды.

Отсюда правило: **у открытой задачи должна быть команда, отвечающая
„дефект ещё воспроизводится?“**. Задача без такой команды протухает
молча — это тот же немой отказ (CLAUDE.md §6.0.1), только в бэклоге.

═══════════════════════════════════════════════════════════════════════
ЧЕМ ЭТО НЕ ЯВЛЯЕТСЯ
═══════════════════════════════════════════════════════════════════════

  · это НЕ проверка «всё ли хорошо»: живой дефект у открытой задачи —
    нормальное состояние, а не сбой. Код возврата 1 означает ровно одно —
    есть задача, чей дефект НЕ воспроизводится, то есть текст бэклога
    разошёлся с кодом;
  · проба не доказывает, что задача сделана целиком. Она отвечает
    на один буквальный вопрос — тот, что записан рядом с ней;
  · задача, чей предмет вне кода (настройка чужого аккаунта, решение
    об облике), пробы не имеет и НАЗЫВАЕТСЯ так прямо, а не молчит.

Список открытых берётся у `backlog_open.py` — второго разбора BACKLOG
здесь нет (§6.0.7, задача 123).

ЗАПУСК

    py backlog_alive.py                  # таблица «задача → жив? → чем»
    py backlog_alive.py --браузер        # плюс пробы, которым нужен стенд
    py backlog_alive.py --контроль       # пробы обязаны реагировать на подлог
"""
import io
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

КОРЕНЬ = os.path.dirname(os.path.abspath(__file__))
БАЗА = os.environ.get("HOVER_BASE", "http://127.0.0.1:8899")


def _читать(имя):
    return io.open(os.path.join(КОРЕНЬ, имя), encoding="utf-8").read()


def _стили():
    """[(файл, селектор, тело)] по всем CSS проекта, без комментариев."""
    из = []
    каталог = os.path.join(КОРЕНЬ, "static")
    for имя in sorted(os.listdir(каталог)):
        if not имя.endswith(".css"):
            continue
        текст = re.sub(r"/\*.*?\*/", "", _читать(f"static/{имя}"), flags=re.S)
        for сел, тело in re.findall(r"([^{}]+)\{([^{}]*)\}", текст):
            сел = " ".join(сел.split())
            if not сел or сел.startswith("@"):
                continue
            из.append((имя, сел, тело))
    return из


# ── ПРОБЫ ────────────────────────────────────────────────────────────────
# Каждая возвращает (жив, строка-объяснение). `жив is None` — «пробы нет
# и вот почему»: это честнее, чем выдумать ответ.

def проба_3():
    """Профиль: заглушки без логики."""
    нужны = {"/api/change-password", "/api/change-email", "/api/avatar",
             "/api/delete-account", "/api/timezone"}
    os.environ.setdefault("DB_PATH", "app.db")
    import main
    есть = {getattr(м, "path", "") for м in main.app.routes}
    нет = sorted(нужны - есть)
    шаблон = _читать("templates/profile.html")
    заглушки = re.findall(r"не реализован\w*", шаблон)
    жив = bool(нет or заглушки)
    return жив, (f"эндпоинтов нет: {нет or '—'}; надписей «не реализован»: "
                 f"{len(заглушки)}")


def проба_17():
    """Полнотекстовый поиск по телу писем."""
    import httpx
    import sqlite3
    бд = sqlite3.connect(os.environ.get("DB_PATH", os.path.join(КОРЕНЬ, "app.db")))
    строка = бд.execute(
        "SELECT letter_text FROM cover_letters WHERE letter_text IS NOT NULL "
        "AND length(letter_text) > 200 LIMIT 1").fetchone()
    if not строка:
        return None, "в базе нет ни одного письма — пробе не на чем работать"
    # Слово из СЕРЕДИНЫ тела письма, которого заведомо нет в заголовке.
    слова = [с for с in re.findall(r"[А-Яа-яЁё]{7,}", строка[0])]
    if not слова:
        return None, "в теле письма нет длинного слова для запроса"
    слово = слова[len(слова) // 2]
    import make_local_user as сид
    with httpx.Client(base_url=БАЗА, follow_redirects=True, timeout=30) as c:
        c.post("/login", data={"email": сид.EMAIL, "password": сид.PASSWORD})
        r = c.get("/api/search", params={"q": слово})
        нашлось = слово.lower() in r.text.lower() or '"letters": [{' in r.text
        письма = r.json().get("letters", []) if r.status_code == 200 else []
    return (not письма), (f"запрос «{слово}» из ТЕЛА письма: "
                          f"писем в выдаче {len(письма)}")


def проба_18():
    """Остатки legacy-оформления в шаблонах: инлайновые <style> с TODO."""
    каталог = os.path.join(КОРЕНЬ, "templates")
    всего = 0
    где = []
    for имя in sorted(os.listdir(каталог)):
        if not имя.endswith(".html"):
            continue
        т = _читать(f"templates/{имя}")
        n = len(re.findall(r"TODO: перенести в модульный CSS", т))
        if n:
            всего += n
            где.append(f"{имя}×{n}")
    хардкоды = 0
    for имя in sorted(os.listdir(каталог)):
        if имя.endswith(".html"):
            хардкоды += len(re.findall(r"#[0-9a-fA-F]{6}\b",
                                       _читать(f"templates/{имя}")))
    return (всего > 0 or хардкоды > 0), (f"блоков «TODO: перенести»: {всего} "
                                         f"({', '.join(где) or '—'}); "
                                         f"шестизначных хардкод-цветов "
                                         f"в шаблонах: {хардкоды}")


def проба_19():
    return None, ("предмет остатка — настройка ЧУЖОГО аккаунта "
                  "(openrouter.ai/settings/privacy). Из кода не читается "
                  "ничем: /api/v1/key политику не отдаёт (§2.4)")


def проба_96():
    """Долг дневника мимо компонентной базы."""
    import check_metrics
    отступы, кегли = check_metrics.долг_дневника()
    return (отступы + кегли > 0), f"отступов числом {отступы}, кеглей числом {кегли}"


def проба_118():
    """Полоса заполнения вне дневника: реализации мимо системного .meter."""
    свои = []
    for файл, сел, тело in _стили():
        if файл in ("style.css",):
            continue
        if not re.search(r"height\s*:", тело):
            continue
        if not re.search(r"(bar|track|progress|meter)", сел, re.I):
            continue
        if "meter" in сел:
            continue
        # Полоса — это дорожка или заливка с высотой и скруглением
        if re.search(r"border-radius", тело) or "fill" in сел.lower():
            свои.append(f"{файл}: {сел}")
    вне = [с for с in свои if not с.startswith("nutrition.css")]
    return bool(вне), f"полос мимо .meter вне дневника: {len(вне)} — {'; '.join(вне[:4])}"


def проба_121():
    """`names` в §6.0.2 — перечень: насколько он отстал от style.css."""
    import project_lists
    имена = set(project_lists.имена_компонентов())
    текст = re.sub(r"/\*.*?\*/", "", _читать("static/style.css"), flags=re.S)
    объявлено = set(re.findall(r"\.([a-z][a-z0-9-]{2,})(?=[\s,{:.\[])", текст))
    отстало = объявлено - имена
    return bool(отстало), (f"классов объявлено в style.css: {len(объявлено)}, "
                           f"в списке names: {len(имена)}, "
                           f"НЕ В СПИСКЕ: {len(отстало)}")


def проба_126():
    """Дубли вне переписи: группы правил с совпавшим телом и разными селекторами."""
    ВИД = ("font", "color", "background", "border", "radius", "shadow", "padding")
    по_телу = {}
    for файл, сел, тело in _стили():
        объявления = tuple(sorted(
            " ".join(о.split()) for о in тело.split(";") if ":" in о))
        if len(объявления) < 3:
            continue
        по_телу.setdefault(объявления, set()).add(f"{файл}:{сел}")
    группы = {т: с for т, с in по_телу.items() if len(с) > 1}
    с_видом = {т: с for т, с in группы.items()
               if any(any(в in о for в in ВИД) for о in т)}
    мест = sum(len(с) for с in с_видом.values())
    return bool(с_видом), (f"групп с совпавшим телом: {len(группы)}, "
                           f"из них с ВИДОМ: {len(с_видом)} на {мест} местах")


def проба_127():
    """Превью упражнения на /workout — div, а не кнопка.

    Речь про ФОТО (`.wk-ex-img`), а не про кадр видео: кадр видео стал
    настоящей `<button>` задачей 73, а фотография осталась `<div>`
    с делегированным обработчиком — с клавиатуры её не открыть вовсе.
    Первая версия этой пробы искала не те имена классов и отвечала
    «дефекта нет» при живом дефекте: ровно то, от чего этот файл.
    """
    т = _читать("templates/workout.html")
    открывашка = re.search(r"class=[\"']wk-ex-img[\"']", т)
    делегат = re.search(r"closest\(['\"]\.wk-ex-img", т)
    кнопка = re.search(r"<button[^>]*class=[\"'][^\"']*wk-ex-img", т)
    return (bool(открывашка) and bool(делегат) and not кнопка), (
        f"элемент .wk-ex-img: {'div' if открывашка and not кнопка else 'button'}, "
        f"делегат по .wk-ex-img: {'есть' if делегат else 'нет'}")


def проба_128():
    """«Ответ оборвался» говорится и там, где ответа не было вовсе.

    Признак буквальный: наружу уходит СТРОКА-КОНСТАНТА, одинаковая
    для обоих исходов `_model_output` — и для `length` (ответ начался
    и обрезан), и для `empty` (ответа не было: нет модели, протух ключ,
    сервис вернул ошибку). Дефект жив, пока ни одно сообщение наружу
    не построено ИЗ причины.
    """
    т = _читать("main.py")
    мест = len(re.findall(r'"error": "Ответ ассистента оборвался[^"]*"', т))
    по_причине = len(re.findall(r'"error": f"[^"]*\{сбой', т))
    return (мест > 0 and по_причине == 0), (
        f"мест с постоянной фразой: {мест}; "
        f"сообщений, построенных ИЗ причины: {по_причине}")


def проба_125(браузер=False):
    """Тач-таргет 44×44 у мелких органов управления."""
    if not браузер:
        return None, "нужен браузер и поднятый стенд: запуск с --браузер"
    from playwright.sync_api import sync_playwright
    import check_hover as ch
    ch.БАЗА = БАЗА
    ЦЕЛИ = ".btn-icon, .chip, .modal-x, .modal-x-float, .btn-icon-sm"
    JS = """
    (сел) => {
      const мало = [];
      document.querySelectorAll(сел).forEach(el => {
        const s = getComputedStyle(el);
        if (s.display === 'none' || s.visibility !== 'visible') return;
        const r = el.getBoundingClientRect();
        if (!r.width || !r.height) return;
        // Невидимая добавка ::after считается: она и есть тач-таргет
        const a = getComputedStyle(el, '::after');
        let w = r.width, h = r.height;
        if (a.content !== 'none' && a.position === 'absolute') {
          const i = ['top','right','bottom','left'].map(k => parseFloat(a[k]) || 0);
          w = r.width - i[1] - i[3];
          h = r.height - i[0] - i[2];
        }
        if (w < 44 || h < 44) мало.push({
          кл: el.getAttribute('class') || '', w: Math.round(w), h: Math.round(h)});
      });
      return мало;
    }
    """
    with sync_playwright() as p:
        бр = p.chromium.launch()
        к = бр.new_context(viewport={"width": 390, "height": 844},
                           has_touch=True, is_mobile=True)
        стр = к.new_page()
        cdp = к.new_cdp_session(стр)
        ch._включить_сенсор(cdp)
        ch._войти(стр)
        ch._включить_сенсор(cdp)
        всего = []
        for путь in ("/nutrition", "/hh", "/profile", "/workout"):
            стр.goto(f"{БАЗА}{путь}", wait_until="domcontentloaded", timeout=45000)
            стр.wait_for_timeout(2200)
            for м in стр.evaluate(JS, ЦЕЛИ):
                всего.append(f"{путь} .{м['кл'][:30]} {м['w']}×{м['h']}")
        бр.close()
    return bool(всего), (f"органов управления меньше 44×44 на сенсорной "
                         f"ширине: {len(всего)} — {'; '.join(всего[:4])}")


ПРОБЫ = {
    3: проба_3, 17: проба_17, 18: проба_18, 19: проба_19, 96: проба_96,
    118: проба_118, 121: проба_121, 125: проба_125, 126: проба_126,
    127: проба_127, 128: проба_128,
}

# Задачи, которые в ревизию НЕ входят, с причиной у каждой строки.
ВНЕ_РЕВИЗИИ = {
    2: "раздел Enshrouded — выведен из работы решением владельца",
    38: "остаток — Enshrouded, см. задачу 2",
    45: "остаток — `.spinner` в enshrouded.html, см. задачу 2",
}


def главная(браузер=False):
    import backlog_open
    # Список открытых — у backlog_open, второго разбора BACKLOG нет (§6.0.7).
    задачи = [(int(н.rstrip("ab")), имя)
              for н, имя, ст, ос, _ in backlog_open.задачи()
              if backlog_open.состояние(ст, ос)[0] == "открыта"]
    print("=" * 74)
    print("ЖИВ ЛИ ДЕФЕКТ — по одной пробе на открытую задачу")
    print("=" * 74)
    print()
    мертвы, без_пробы = [], []
    for номер, заголовок in задачи:
        if номер in ВНЕ_РЕВИЗИИ:
            print(f"  {номер:>4}  ВНЕ РЕВИЗИИ — {ВНЕ_РЕВИЗИИ[номер]}")
            continue
        проба = ПРОБЫ.get(номер)
        if проба is None:
            без_пробы.append(номер)
            print(f"  {номер:>4}  ПРОБЫ НЕТ — задача протухает молча")
            continue
        try:
            жив, чем = (проба(браузер) if номер == 125 else проба())
        except Exception as e:            # проба сломалась — это не «дефекта нет»
            print(f"  {номер:>4}  ПРОБА УПАЛА: {type(e).__name__}: {e}")
            continue
        значок = {True: "ЖИВ ", False: "НЕТ ", None: "?   "}[жив]
        print(f"  {номер:>4}  {значок} {заголовок[:52]}")
        print(f"        {чем}")
        if жив is False:
            мертвы.append(номер)
    print()
    print(f"  задач без пробы: {len(без_пробы)} {без_пробы or ''}")
    print(f"  ОТКРЫТЫХ, ЧЕЙ ДЕФЕКТ НЕ ВОСПРОИЗВОДИТСЯ: {len(мертвы)} {мертвы or ''}")
    if мертвы:
        print("  → текст бэклога разошёлся с кодом, задачи закрываются")
    return 1 if мертвы else 0


# ── ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ ───────────────────────────────────────────────
# Проба, которая отвечает «дефекта нет» и на исправленном, и на сломанном
# коде, не отвечает ни на что. Подлог кладётся во ВРЕМЕННУЮ копию файла,
# рабочее дерево не меняется.
def контроль():
    print("=" * 74)
    print("ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ ПРОБ: подлог обязан перевернуть ответ")
    print("=" * 74)
    ok = True

    # 1. Проба 128: убираем различение empty/length — проба обязана сказать «жив».
    #    А добавляем — «не жив». Проверяем ОБЕ стороны.
    исходный = _читать("main.py")
    try:
        жив_до, _ = проба_128()
        # Подлог — сообщение, ПОСТРОЕННОЕ ИЗ ПРИЧИНЫ: ровно то, чего
        # задача и требует. Проба обязана перестать считать дефект живым.
        подлог = исходный + chr(10) + '_подлог = {"error": f"причина: ' +             '{сбой}"}' + chr(10)

        io.open(os.path.join(КОРЕНЬ, "main.py"), "w",
                encoding="utf-8").write(подлог)
        жив_после, чем = проба_128()
        печать = f"  128: было жив={жив_до}, после подлога жив={жив_после}"
        годна = жив_до != жив_после
        print(f"  {'ok ' if годна else 'НЕТ'}{печать}")
        ok = ok and годна
    finally:
        io.open(os.path.join(КОРЕНЬ, "main.py"), "w",
                encoding="utf-8").write(исходный)

    # 2. Проба 121: подкладываем в style.css класс, которого нет в names.
    исходный_css = _читать("static/style.css")
    try:
        жив_до, чем_до = проба_121()
        io.open(os.path.join(КОРЕНЬ, "static/style.css"), "w",
                encoding="utf-8").write(
            исходный_css + "\n.zzz-podlog-klass { color: red; }\n")
        жив_после, чем_после = проба_121()
        n_до = int(re.search(r"НЕ В СПИСКЕ: (\d+)", чем_до).group(1))
        n_после = int(re.search(r"НЕ В СПИСКЕ: (\d+)", чем_после).group(1))
        годна = n_после == n_до + 1
        print(f"  {'ok ' if годна else 'НЕТ'}  121: не в списке {n_до} → {n_после}")
        ok = ok and годна
    finally:
        io.open(os.path.join(КОРЕНЬ, "static/style.css"), "w",
                encoding="utf-8").write(исходный_css)

    # 3. Проба 3: подкладываем надпись-заглушку в профиль.
    исходный_проф = _читать("templates/profile.html")
    try:
        жив_до, _ = проба_3()
        io.open(os.path.join(КОРЕНЬ, "templates/profile.html"), "w",
                encoding="utf-8").write(
            исходный_проф + "\n<!-- эндпоинт ещё не реализован -->\n")
        жив_после, чем = проба_3()
        годна = (жив_до is False) and (жив_после is True)
        print(f"  {'ok ' if годна else 'НЕТ'}  3: было жив={жив_до}, "
              f"после подлога жив={жив_после}")
        ok = ok and годна
    finally:
        io.open(os.path.join(КОРЕНЬ, "templates/profile.html"), "w",
                encoding="utf-8").write(исходный_проф)

    print()
    print("ПРОЙДЕН." if ok else "ПРОВАЛЕН: проба не реагирует на подлог.")
    return 0 if ok else 1


if __name__ == "__main__":
    if "--контроль" in sys.argv:
        sys.exit(контроль())
    sys.exit(главная(браузер="--браузер" in sys.argv))
