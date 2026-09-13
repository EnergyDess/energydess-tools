# -*- coding: utf-8 -*-
"""ПРОВЕРКА 37: МЕСТА МЕДИА ГЛАВНОЙ (BACKLOG №325).

ДВА РЕЖИМА, И ВОПРОСЫ У НИХ РАЗНЫЕ.

  py check_landing.py              # ряд §6.0.2: без стенда и браузера
  py check_landing.py --контроль   # подлоги ряда, у каждого доказательство
  py check_landing.py --панель     # стенд, ГОЛОВНОЙ браузер (§6.0.3)

РЯД спрашивает ТЕКСТ И ДИСК:
  · описание мест (`landing_defs`) против СТРУКТУРЫ ВЛАДЕЛЬЦА — она
    записана ЗДЕСЬ, своим словарём, а не взята у проверяемого кода
    (правило захода: мерка не берёт данные у того, что меряет). Лента
    12 роликов, проекты 9 картинок, портрет 1, декор 4 — итого 26;
  · строки `landing_media`, которые указывают на место вне описания;
  · файлы на томе без строки (сироты) и строки без файла.

ПАНЕЛЬ спрашивает ВИДИМОЕ ЧЕЛОВЕКУ:
  · B  — сколько карточек мест ВИДНО в разделе (не сколько в дереве);
  · C  — заглушка не похожа на ошибку, и размер места до загрузки
         равен размеру после, в том числе файлом ДРУГОГО соотношения;
  · D4 — не тот род файла даёт отказ, видимый в карточке;
  · D5 — ролик сверх предела даёт предупреждение С ЧИСЛОМ;
  · D6 — прозрачность декора выжила: пиксель в углу отданного файла
         и пиксель на экране, а не формат файла;
  · D3 — замена удаляет прежний файл с тома;
  · D7 — гость не видит раздела, не-админ получает отказ, в базе
         и на томе ничего не изменилось.

ИСХОДЫ: 0 — всё сошлось, 1 — есть находки, 2 — спросить нечем
(нет стенда либо нет базы), и это говорится словом (§6.0.1).

ПАНЕЛЬ ЗА СОБОЙ УБИРАЕТ: всё, что она загрузила, снимается в `finally`
боевым DELETE, и опись стенда (`check_stand_state`) после неё чиста.
"""

import os
import re
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DB_PATH", "app.db")
import probe_guard  # noqa: E402,F401  ПРОПУСК вместо трассы (§6.0.1)

sys.stdout.reconfigure(encoding="utf-8")

# ── СТРУКТУРА ВЛАДЕЛЬЦА ── своя, НЕ из landing_defs ───────────────────
ОЖИДАНИЕ = {"feed": (12, "video"), "projects": (9, "image"),
            "portrait": (1, "image"), "decor": (4, "image")}
ОЖИДАНИЕ_ВСЕГО = sum(n for n, _ in ОЖИДАНИЕ.values())
# Прозрачность обязана быть у декора и ни у кого больше.
С_ПРОЗРАЧНОСТЬЮ = {"decor"}
# Имя файла на томе — свой разбор, не `landing_store.ИМЯ_ФАЙЛА`.
ИМЯ = re.compile(r"^([a-z0-9-]+)-([0-9a-f]{8})\.(mp4|webp)$")

находок = 0


def шаг(имя, условие, подробность=""):
    global находок
    if not условие:
        находок += 1
    print("  %-4s %s%s" % ("OK" if условие else "ПЛОХО", имя,
                           (" — " + подробность) if подробность else ""))


def сверить_описание(места):
    """Находки описания против структуры владельца. Список строк."""
    плохо = []
    if len(места) != ОЖИДАНИЕ_ВСЕГО:
        плохо.append("мест в описании %d, по структуре владельца %d"
                     % (len(места), ОЖИДАНИЕ_ВСЕГО))
    for секция, (n, род) in ОЖИДАНИЕ.items():
        свои = [м for м in места if м["section"] == секция]
        if len(свои) != n:
            плохо.append("секция %s: мест %d, ожидалось %d" % (секция, len(свои), n))
        чужой_род = [м["id"] for м in свои if м["kind"] != род]
        if чужой_род:
            плохо.append("секция %s: не тот род у %s" % (секция, ", ".join(чужой_род)))
        альфа = [м["id"] for м in свои if bool(м.get("alpha")) != (секция in С_ПРОЗРАЧНОСТЬЮ)]
        if альфа:
            плохо.append("секция %s: признак прозрачности не тот у %s"
                         % (секция, ", ".join(альфа)))
    лишние = sorted({м["section"] for м in места} - set(ОЖИДАНИЕ))
    if лишние:
        плохо.append("секции вне структуры: " + ", ".join(лишние))
    ids = [м["id"] for м in места]
    if len(set(ids)) != len(ids):
        плохо.append("опознаватели повторяются")
    return плохо


def каталог_тома(путь_базы):
    return os.path.join(os.path.dirname(os.path.abspath(путь_базы)), "landing")


def сверить_диск(путь_базы, ids):
    """(находки, строк, файлов). Спросить нечем — None вместо находок."""
    if not os.path.exists(путь_базы):
        return None, 0, 0
    c = sqlite3.connect("file:%s?mode=ro" % путь_базы, uri=True)
    try:
        try:
            строки = c.execute("SELECT slot_id, version, ext FROM landing_media").fetchall()
        except sqlite3.OperationalError:
            return None, 0, 0
    finally:
        c.close()
    плохо = []
    вне = [с for с, _, _ in строки if с not in ids]
    if вне:
        плохо.append("строки на места вне описания: " + ", ".join(вне))
    к = каталог_тома(путь_базы)
    файлы = sorted(os.listdir(к)) if os.path.isdir(к) else []
    живые = {"%s-%s.%s" % r for r in строки}
    сироты = [ф for ф in файлы if ф not in живые]
    if сироты:
        плохо.append("файлы без строки (сироты): %d — %s" % (len(сироты), ", ".join(сироты[:3])))
    без_файла = sorted(живые - set(файлы))
    if без_файла:
        плохо.append("строки без файла: %d — %s" % (len(без_файла), ", ".join(без_файла[:3])))
    чужие_имена = [ф for ф in файлы if not ИМЯ.match(ф)]
    if чужие_имена:
        плохо.append("чужие имена в каталоге: " + ", ".join(чужие_имена[:3]))
    return плохо, len(строки), len(файлы)


def ряд(места=None, путь_базы=None, печать=True):
    import landing_defs as ld
    места = ld.МЕСТА if места is None else места
    путь_базы = путь_базы or os.environ["DB_PATH"]
    плохо = сверить_описание(места)
    диск, строк, файлов = сверить_диск(путь_базы, {м["id"] for м in места})
    if печать:
        print("ПРОВЕРКА 37: места медиа главной")
        print("  мест в описании %d, по структуре владельца %d" % (len(места), ОЖИДАНИЕ_ВСЕГО))
        if диск is None:
            print("  база: СПРОСИТЬ НЕЧЕМ — нет базы или таблицы landing_media")
        else:
            print("  база: строк %d, файлов на томе %d" % (строк, файлов))
        for п in плохо + (диск or []):
            print("  НАХОДКА: " + п)
    if плохо or диск:
        return 1, плохо + (диск or [])
    if диск is None:
        return 2, []
    return 0, []


# ── ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ РЯДА ────────────────────────────────────────
#
# ПОДЛОГ ЛОМАЕТ ПРОВЕРЯЕМОЕ ЗВЕНО. Первый — описание мест: одно место
# вынимается В ПАМЯТИ, файл не трогается. Второй — диск: во временный
# каталог рядом с копией базы кладётся файл без строки.
#
# ДОКАЗАТЕЛЬСТВО НЕЗАВИСИМО ОТ ВЕРДИКТА: число мест считается `len` над
# подложенным списком, а сирота — `os.path.exists`, без логики пробы.
ДОКАЗАТЕЛЬСТВА = {
    "одно место вынуто из описания": "len(места) 26 -> 25",
    "файл без строки на томе": "os.path.exists(сирота) False -> True",
    "прозрачность потеряна при сжатии": "режим сохранённого webp RGBA -> RGB",
}


def угол_прозрачен(путь):
    """Пиксель (0, 0) файла прозрачен. Мерка ОДНА на контроль и панель:
    спрашивает пиксель, а не формат и не признак в базе."""
    from PIL import Image
    with Image.open(путь) as im:
        return im.convert("RGBA").getpixel((0, 0))[3] == 0


def контроль():
    import landing_defs as ld
    import shutil
    print("КОНТРОЛЬ ПРОВЕРКИ 37")
    код0, _ = ряд(печать=False)
    if код0 == 1:
        print("  ОСНОВА ГРЯЗНАЯ: без подлога уже есть находки — контроль недействителен")
        return 2
    итог = 0

    места = [м for м in ld.МЕСТА if м["id"] != "decor-br"]
    print("  подлог 1: вынуто место decor-br; доказательство len %d -> %d"
          % (len(ld.МЕСТА), len(места)))
    код, находки = ряд(места=места, печать=False)
    назвал = any("мест в описании 25" in н for н in находки)
    print("    вердикт: код %d, %s" % (код, "; ".join(находки) or "находок нет"))
    print("    %s" % ("ЛОВИТ" if код == 1 and назвал else "НЕ ЛОВИТ"))
    итог |= 0 if (код == 1 and назвал) else 1

    каталог = tempfile.mkdtemp(prefix="check37-")
    try:
        база = os.path.join(каталог, "app.db")
        shutil.copy2(os.environ["DB_PATH"], база)
        for хвост in ("-wal", "-shm"):
            if os.path.exists(os.environ["DB_PATH"] + хвост):
                shutil.copy2(os.environ["DB_PATH"] + хвост, база + хвост)
        c = sqlite3.connect(база)
        c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        строки = c.execute("SELECT slot_id, version, ext FROM landing_media").fetchall()
        c.close()
        os.makedirs(os.path.join(каталог, "landing"))
        исходный = каталог_тома(os.environ["DB_PATH"])
        for с, в, е in строки:
            имя = "%s-%s.%s" % (с, в, е)
            if os.path.exists(os.path.join(исходный, имя)):
                shutil.copy2(os.path.join(исходный, имя), os.path.join(каталог, "landing", имя))
        код_чист, _ = ряд(путь_базы=база, печать=False)
        сирота = os.path.join(каталог, "landing", "feed-2-6-0badf00d.mp4")
        было = os.path.exists(сирота)
        open(сирота, "wb").write(b"\0" * 16)
        стало = os.path.exists(сирота)
        код, находки = ряд(путь_базы=база, печать=False)
        назвал = any("сироты" in н and "feed-2-6-0badf00d.mp4" in н for н in находки)
        print("  подлог 2: сирота на томе копии; доказательство exists %s -> %s; "
              "копия без подлога — код %d" % (было, стало, код_чист))
        print("    вердикт: код %d, %s" % (код, "; ".join(находки) or "находок нет"))
        print("    %s" % ("ЛОВИТ" if код == 1 and назвал and код_чист != 1 else "НЕ ЛОВИТ"))
        итог |= 0 if (код == 1 and назвал and код_чист != 1) else 1
    finally:
        shutil.rmtree(каталог, ignore_errors=True)

    # ПОДЛОГ 3 — В ЗВЕНО СЖАТИЯ: ветка «сохранить прозрачность» выключена
    # в памяти, картинка уходит в RGB. Мерка — пиксель угла файла.
    import landing_media as лм
    from PIL import Image
    каталог = tempfile.mkdtemp(prefix="check37-alpha-")
    исходный_признак = лм._есть_прозрачность
    try:
        png = os.path.join(каталог, "a.png")
        Image.new("RGBA", (400, 400), (0, 0, 0, 0)).save(png)
        г1, _, _ = лм.обработать("decor-br", png, "a.png")
        чисто = угол_прозрачен(г1)
        режим1 = Image.open(г1).mode
        лм._есть_прозрачность = lambda im: False
        г2, _, _ = лм.обработать("decor-br", png, "a.png")
        режим2 = Image.open(г2).mode
        с_подлогом = угол_прозрачен(г2)
        print("  подлог 3: прозрачность выключена в сжатии; доказательство режим %s -> %s"
              % (режим1, режим2))
        print("    вердикт: угол прозрачен без подлога %s, с подлогом %s" % (чисто, с_подлогом))
        ок = чисто and not с_подлогом and режим2 != режим1
        print("    %s" % ("ЛОВИТ" if ок else "НЕ ЛОВИТ"))
        итог |= 0 if ок else 1
    finally:
        лм._есть_прозрачность = исходный_признак
        shutil.rmtree(каталог, ignore_errors=True)
    print("КОНТРОЛЬ: %s" % ("все подлоги пойманы" if итог == 0 else "ЕСТЬ НЕПОЙМАННЫЕ"))
    return итог


# ══ ПАНЕЛЬ: ГОЛОВНОЙ БРАУЗЕР НА СТЕНДЕ ════════════════════════════════

БАЗА = os.environ.get("STAND", "http://127.0.0.1:8899")
ПОЧТА_АДМИНА = ("screenshot@local.dev", "Screenshot-Local-2026")
ПОЧТА_СОСЕДА = ("neighbour@local.dev", "Neighbour-Local-2026")

# Места, куда панель грузит. НИ ОДНО не из семени стенда: семя остаётся
# нетронутым, а загруженное снимается в `finally`.
М_РОЛИК, М_ВЫСОКАЯ, М_ДЕКОР, М_ОТКАЗ, М_ДЛИННЫЙ = (
    "feed-2-1", "project-2-c", "decor-br", "feed-2-2", "feed-2-3")


def _файлы_пробы(каталог):
    """Входные файлы: у каждого соотношение ДРУГОЕ, чем у места."""
    import subprocess
    from PIL import Image, ImageDraw
    import imageio_ffmpeg
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    п = {}
    п["ролик43"] = os.path.join(каталог, "r43.mp4")      # в место 16:9
    subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                    "-i", "testsrc2=size=1440x1080:rate=30", "-f", "lavfi", "-i",
                    "sine=frequency=300", "-t", "3", "-c:v", "libx264", "-crf", "18",
                    "-c:a", "aac", п["ролик43"]], check=True, timeout=120)
    п["ролик2"] = os.path.join(каталог, "r2.mp4")
    subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                    "-i", "testsrc=size=1280x720:rate=30", "-t", "2", "-c:v", "libx264",
                    п["ролик2"]], check=True, timeout=120)
    п["длинный"] = os.path.join(каталог, "long.mp4")      # 22 с при пределе 15
    subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                    "-i", "testsrc2=size=640x360:rate=24", "-t", "22", "-c:v", "libx264",
                    "-crf", "30", п["длинный"]], check=True, timeout=120)
    п["квадрат"] = os.path.join(каталог, "sq.jpg")        # в место 3:4
    im = Image.new("RGB", (1200, 1200), (60, 150, 90))
    ImageDraw.Draw(im).rectangle((100, 100, 1100, 1100), outline=(250, 250, 250), width=30)
    im.save(п["квадрат"], quality=90)
    п["прозрачный"] = os.path.join(каталог, "alpha.png")  # 16:9 в место 1:1
    im = Image.new("RGBA", (1600, 900), (0, 0, 0, 0))
    ImageDraw.Draw(im).ellipse((500, 150, 1100, 750), fill=(240, 160, 60, 255))
    im.save(п["прозрачный"])
    return п


def _строки_базы():
    c = sqlite3.connect("file:%s?mode=ro" % os.environ["DB_PATH"], uri=True)
    try:
        return {r[0]: "%s-%s.%s" % r for r in
                c.execute("SELECT slot_id, version, ext FROM landing_media")}
    finally:
        c.close()


def _войти(стр, почта, пароль):
    стр.goto(БАЗА + "/login", wait_until="domcontentloaded", timeout=45000)
    стр.fill("input[name=email]", почта)
    стр.fill("input[name=password]", пароль)
    if стр.locator(".cf-turnstile").count():
        стр.wait_for_function("() => { const e = document.querySelector"
                              "('[name=\"cf-turnstile-response\"]'); return e && e.value; }",
                              timeout=20000)
    with стр.expect_navigation(timeout=45000):
        стр.click("button[type=submit]")
    if "/login" in стр.url:
        raise RuntimeError("вход не прошёл: остались на /login")


_КОРОБКА = """(slot) => { const e = document.querySelector(`.media-slot[data-slot="${slot}"]`);
  const r = e.getBoundingClientRect(); return [r.width, r.height]; }"""


def _грузить(стр, место, файл, ждать_заполнения=True):
    стр.set_input_files('[data-upload="%s"]' % место, файл)
    if ждать_заполнения:
        стр.wait_for_function(
            "(s) => { const к = document.querySelector(`[data-card=\"${s}\"]`);"
            " return к && к.dataset.filled === 'yes'; }", arg=место, timeout=240000)
    else:
        стр.wait_for_function(
            "(s) => { const м = document.querySelector(`[data-card=\"${s}\"] [data-msg]`);"
            " return м && !м.hidden && м.textContent.trim(); }", arg=место, timeout=240000)
    стр.wait_for_timeout(600)
    return стр.evaluate("""(s) => { const м = document.querySelector(`[data-card="${s}"] [data-msg]`);
      return {текст: м ? м.textContent.trim() : '', тон: м ? м.dataset.tone : '',
              видно: м ? м.checkVisibility() : false,
              заполнено: document.querySelector(`[data-card="${s}"]`).dataset.filled}; }""", место)


def панель():
    import urllib.request
    from io import BytesIO
    from PIL import Image
    try:
        urllib.request.urlopen(БАЗА + "/health", timeout=5)
    except OSError as e:
        print("ПРОПУСК: стенд %s не отвечает (%s) — спросить нечем" % (БАЗА, type(e).__name__))
        return 2
    from playwright.sync_api import sync_playwright
    каталог = tempfile.mkdtemp(prefix="check37-panel-")
    файлы = _файлы_пробы(каталог)
    загружено = set()
    print("ПРОВЕРКА 37, ПАНЕЛЬ: %s, головной браузер" % БАЗА)
    with sync_playwright() as p:
        бр = p.chromium.launch(headless=False)
        ктх = бр.new_context(viewport={"width": 1920, "height": 1080})
        стр = ктх.new_page()
        try:
            _войти(стр, *ПОЧТА_АДМИНА)
            стр.goto(БАЗА + "/admin/landing", wait_until="load", timeout=45000)
            стр.wait_for_timeout(800)
            строки_до = _строки_базы()

            # ── B: сколько мест ВИДНО ────────────────────────────────────
            видно = стр.evaluate("""() => [...document.querySelectorAll('[data-card]')]
                .filter(к => к.checkVisibility({opacityProperty: true, visibilityProperty: true})).length""")
            слотов = стр.evaluate("() => document.querySelectorAll('.media-slot').length")
            шаг("B: карточек мест видно в панели", видно == ОЖИДАНИЕ_ВСЕГО,
                "%d из %d" % (видно, ОЖИДАНИЕ_ВСЕГО))
            шаг("B: коробок мест в разделе", слотов == ОЖИДАНИЕ_ВСЕГО,
                "%d из %d" % (слотов, ОЖИДАНИЕ_ВСЕГО))
            полоса = стр.evaluate("() => !!document.querySelector('.admin-wrap .admin-bar .chip')")
            подвал = стр.evaluate("() => { const п = document.querySelector('.admin-foot #note');"
                                  " return п ? п.textContent.trim().length : 0; }")
            шаг("D: полоса отбора из общего макроса", полоса, "чипы в .admin-bar")
            шаг("D: подвал из общего макроса", подвал > 0, "знаков подписи %d" % подвал)

            # ── C1/C2: заглушка не похожа на ошибку ─────────────────────
            заглушки = стр.evaluate("""() => [...document.querySelectorAll('.media-slot[data-filled="no"]')].map(e => {
                const п = e.querySelector('.media-slot-empty');
                const цвета = [...e.querySelectorAll('*')].map(x => getComputedStyle(x).color);
                return {подпись: п ? п.innerText.trim() : '', красный: цвета.some(ц => ц === 'rgb(239, 68, 68)'),
                        битых: [...e.querySelectorAll('img')].filter(i => !i.naturalWidth).length}; })""")
            без_подписи = sum(1 for з in заглушки if not з["подпись"])
            красных = sum(1 for з in заглушки if з["красный"])
            битых = sum(з["битых"] for з in заглушки)
            шаг("C1: у пустого места подпись", len(заглушки) > 0 and без_подписи == 0,
                "пустых %d, без подписи %d" % (len(заглушки), без_подписи))
            шаг("C2: у заглушки нет цвета ошибки и битой картинки",
                len(заглушки) > 0 and красных == 0 and битых == 0,
                "красных %d, битых картинок %d из %d" % (красных, битых, len(заглушки)))

            # ── C3 + подлог «другое соотношение» ────────────────────────
            до = {м: стр.evaluate(_КОРОБКА, м) for м in (М_РОЛИК, М_ВЫСОКАЯ, М_ДЕКОР)}
            ответы = {}
            for место, файл in ((М_РОЛИК, "ролик43"), (М_ВЫСОКАЯ, "квадрат"), (М_ДЕКОР, "прозрачный")):
                ответы[место] = _грузить(стр, место, файлы[файл])
                загружено.add(место)
            for место in (М_РОЛИК, М_ВЫСОКАЯ, М_ДЕКОР):
                после = стр.evaluate(_КОРОБКА, место)
                сдвиг = max(abs(после[0] - до[место][0]), abs(после[1] - до[место][1]))
                шаг("C3: %s с заглушкой и с файлом другого соотношения" % место,
                    ответы[место]["заполнено"] == "yes" and сдвиг <= 0.5,
                    "до %.1fx%.1f, после %.1fx%.1f, сдвиг %.2f px"
                    % (до[место][0], до[место][1], после[0], после[1], сдвиг))
            for место in (М_РОЛИК, М_ВЫСОКАЯ, М_ДЕКОР):
                print("       вес %s: %s" % (место, ответы[место]["текст"]))
            меты = стр.evaluate("""(ss) => ss.map(s => document.querySelector(`[data-card="${s}"] .landing-card-meta`).innerText)""",
                                [М_РОЛИК, М_ВЫСОКАЯ, М_ДЕКОР])
            for место, мета in zip((М_РОЛИК, М_ВЫСОКАЯ, М_ДЕКОР), меты):
                print("       размеры %s: %s" % (место, " ".join(мета.split())))

            # ── D6: прозрачность — пиксель файла и пиксель экрана ───────
            исходник = Image.open(файлы["прозрачный"]).getpixel((0, 0))
            адрес = стр.evaluate("(s) => document.querySelector(`.media-slot[data-slot=\"${s}\"] img`).getAttribute('src')", М_ДЕКОР)
            тело = стр.request.get(БАЗА + адрес).body()
            отданный = Image.open(BytesIO(тело))
            угол = отданный.convert("RGBA").getpixel((0, 0))
            файл_угла = os.path.join(каталог, "served.webp")
            open(файл_угла, "wb").write(тело)
            шаг("D6: угол отданного webp прозрачен", угол_прозрачен(файл_угла),
                "исходник %s, отдано режим %s угол %s" % (исходник, отданный.mode, угол))
            стр.evaluate("(s) => document.querySelector(`.media-slot[data-slot=\"${s}\"]`).scrollIntoView({block:'center'})", М_ДЕКОР)
            стр.wait_for_timeout(400)
            снимок = Image.open(BytesIO(стр.locator('.media-slot[data-slot="%s"]' % М_ДЕКОР).screenshot()))
            экран = снимок.convert("RGB").getpixel((3, 3))
            фон = стр.evaluate("(s) => getComputedStyle(document.querySelector(`[data-card=\"${s}\"]`)).backgroundColor", М_ДЕКОР)
            чёрный = sum(экран) < 20
            шаг("D6: на экране в углу фон карточки, не чёрный прямоугольник", not чёрный,
                "пиксель %s, фон карточки %s" % (экран, фон))

            # ── D4: не тот род ───────────────────────────────────────────
            о = _грузить(стр, М_ОТКАЗ, файлы["прозрачный"], ждать_заполнения=False)
            шаг("D4: картинка в место под видео — видимый отказ",
                о["видно"] and о["тон"] == "error" and "видео" in о["текст"] and о["заполнено"] == "no",
                "«%s», тон %s" % (о["текст"], о["тон"]))
            о = _грузить(стр, М_ВЫСОКАЯ, файлы["ролик2"], ждать_заполнения=False)
            шаг("D4: ролик в место под картинку — видимый отказ",
                о["видно"] and о["тон"] == "error" and "картинк" in о["текст"],
                "«%s», тон %s" % (о["текст"], о["тон"]))

            # ── D5: сверх предела — предупреждение числом ───────────────
            о = _грузить(стр, М_ДЛИННЫЙ, файлы["длинный"])
            загружено.add(М_ДЛИННЫЙ)
            шаг("D5: ролик 22 с — предупреждение с числом",
                о["видно"] and о["тон"] == "warning" and re.search(r"22[.,]\d", о["текст"]) is not None,
                "«%s»" % о["текст"])

            # ── D3: замена удаляет прежний файл ──────────────────────────
            прежний = _строки_базы()[М_РОЛИК]
            к_тома = каталог_тома(os.environ["DB_PATH"])
            _грузить(стр, М_РОЛИК, файлы["ролик2"])
            новый = _строки_базы()[М_РОЛИК]
            шаг("D3: замена удалила прежний файл с тома",
                новый != прежний and not os.path.exists(os.path.join(к_тома, прежний))
                and os.path.exists(os.path.join(к_тома, новый)),
                "%s -> %s" % (прежний, новый))

            # ── D7: посторонние ──────────────────────────────────────────
            строки_перед = _строки_базы()
            файлов_перед = sorted(os.listdir(к_тома))
            гость = бр.new_context().new_page()
            гость.goto(БАЗА + "/admin/landing", wait_until="domcontentloaded", timeout=45000)
            шаг("D7: гость не видит раздела", "/admin/landing" not in гость.url
                and гость.locator("[data-card]").count() == 0, "оказался на %s" % гость.url)
            ответ_гостя = гость.request.post(БАЗА + "/admin/api/landing/feed-2-4",
                                             multipart={"file": {"name": "x.mp4", "mimeType": "video/mp4",
                                                                 "buffer": open(файлы["ролик2"], "rb").read()}})
            шаг("D7: гость не загружает", ответ_гостя.status in (401, 403), "HTTP %d" % ответ_гостя.status)
            сосед = бр.new_context().new_page()
            _войти(сосед, *ПОЧТА_СОСЕДА)
            сосед.goto(БАЗА + "/admin/landing", wait_until="domcontentloaded", timeout=45000)
            шаг("D7: не-админ не видит раздела", "/admin/landing" not in сосед.url,
                "оказался на %s" % сосед.url)
            ответ = сосед.request.post(БАЗА + "/admin/api/landing/feed-2-4",
                                       multipart={"file": {"name": "x.mp4", "mimeType": "video/mp4",
                                                           "buffer": open(файлы["ролик2"], "rb").read()}})
            удал = сосед.request.delete(БАЗА + "/admin/api/landing/" + М_ДЕКОР)
            шаг("D7: не-админ не загружает и не удаляет", ответ.status == 403 and удал.status == 403,
                "загрузка HTTP %d, удаление HTTP %d" % (ответ.status, удал.status))
            шаг("D7: в базе и на томе ничего не изменилось",
                _строки_базы() == строки_перед and sorted(os.listdir(к_тома)) == файлов_перед,
                "строк %d, файлов %d" % (len(строки_перед), len(файлов_перед)))
            print("       строк в базе до пробы %d" % len(строки_до))
        finally:
            for место in sorted(загружено):
                if место in _строки_базы():
                    стр.request.delete(БАЗА + "/admin/api/landing/" + место)
            остаток = sorted(set(_строки_базы()) & загружено)
            print("  уборка: снято %d мест, осталось загруженного %d" % (len(загружено), len(остаток)))
            бр.close()
            import shutil
            shutil.rmtree(каталог, ignore_errors=True)
    print("ПАНЕЛЬ: находок %d" % находок)
    return 1 if находок else 0


def main():
    if "--контроль" in sys.argv:
        return контроль()
    if "--панель" in sys.argv:
        return панель()
    код, _ = ряд()
    print("ИТОГ: %s" % {0: "ПРОВЕРЕНО, ЧИСТО", 1: "ЕСТЬ НАХОДКИ", 2: "НЕ ПРОВЕРЕНО"}[код])
    return код


if __name__ == "__main__":
    sys.exit(main())
