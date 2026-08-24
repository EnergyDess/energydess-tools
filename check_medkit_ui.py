# -*- coding: utf-8 -*-
"""АПТЕЧКА НАСКВОЗЬ — каждое действие так, как его проходит человек (§6.3).

Правило §6.3 прямым текстом: «у экрана, который заход СОЗДАЛ или ИЗМЕНИЛ,
каждое действие проходится насквозь — от первого нажатия до НАБЛЮДАЕМОГО
результата. Проверка отказов при неверных данных этого не заменяет: отказ
можно получить и от мёртвой формы».

Ровно так экран управления каталогом Enshrouded уехал на прод
с `disabled` на полях загрузки картинки: мерка ответов сервера была
зелёной на 25 случаях, и все 25 были верны — вопроса «а можно ли вообще
выбрать файл» среди них не было.

ТРИ ТРЕБОВАНИЯ, и каждое отсекает свой вид самообмана:

  ОРГАН ЖИВОЙ   не `disabled`, виден, и `elementFromPoint` в его центре
                возвращает его самого или потомка. «Есть в дереве» —
                не то же самое, что «до него дотянется палец»;
  ДО РЕЗУЛЬТАТА действие идёт до наблюдаемого исхода, а не до ответа
                сервера: «HTTP 200» не значит, что человек увидел
                картинку;
  ИЗ БАЗЫ ТОЖЕ  результат сверяется и с экраном, и с базой. Ответ
                сервера — это его НАМЕРЕНИЕ; в базе бывает пусто
                (§6.0.5, запись в отцепленный объект).

ЗАПУСК
    py make_local_user.py --seed
    py -m uvicorn main:app --port 8899
    py check_medkit_ui.py                  # 1440
    py check_medkit_ui.py --ширина 390     # сенсорная
    py check_medkit_ui.py --контроль       # ОБЯЗАТЕЛЬНО

В РЯДЫ §6.0.2 НЕ ВХОДИТ по трём причинам сразу: нужен браузер, нужно
поднятое приложение и она ПИШЕТ В БАЗУ (заводит и удаляет пробные
позиции). Ряд обязан быть безопасным для любого прогона.

ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ ОБЯЗАТЕЛЕН И ВСТРОЕН. Подлоги кладутся
В СТРАНИЦУ (`add_init_script`), кода экрана не трогают, и каждый обязан
быть назван СВОИМ шагом. Проба, которая не реагирует на подлог,
не отвечает ни на что.
"""
import argparse
import asyncio
import os
import sqlite3
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

БАЗА = os.environ.get("MEDKIT_BASE", "http://127.0.0.1:8899")
ПОЧТА = "screenshot@local.dev"
ПАРОЛЬ = "Screenshot-Local-2026"
DB = os.environ.get("DB_PATH", "app.db")

# ── ПОДЛОГИ ОТРИЦАТЕЛЬНОГО КОНТРОЛЯ ──────────────────────────────────
#
# Каждый ломает РОВНО ОДНО свойство, и проба обязана назвать именно его.
# Общий подлог доказывал бы, что проба видит хоть что-то, и находка
# от одного шага закрыла бы собой молчание про остальные.
ПОДЛОГИ = {
    "мёртвая-форма": (
        # Поля формы выключены — ровно тот дефект, что уехал на прод
        # у экрана Enshrouded
        "document.addEventListener('DOMContentLoaded', () => {"
        "  ['apt-f-name','apt-f-exp','apt-save'].forEach(id => {"
        "    const el = document.getElementById(id); if (el) el.disabled = true;"
        "  }); });",
        "форма-жива"),
    "молчаливое-удаление": (
        # Удаление без вопроса: окно подтверждения не открывается, позиция
        # уходит сразу.
        #
        # ЗДЕСЬ СТОЯЛО `window.АПТ.удаляем = id; window.аптУдалить()`,
        # и это НЕ РАБОТАЛО: `АПТ` объявлен через `const` на верхнем уровне
        # классического скрипта, а `const` свойства `window` не создаёт
        # вовсе. Подлог падал `TypeError` на первой же строке, окно
        # не открывалось, и шаг «удаление-спрашивает» честно проваливался —
        # но ПО ДРУГОЙ ПРИЧИНЕ. Замер 2026-08-24: карточек было 21, стало
        # 21, то есть подлог не удалял НИЧЕГО, а контроль печатал «НАЙДЕН».
        #
        # Ровно то, о чём §6.3: подлог, который не сработал, неотличим
        # от слепой пробы. Поймано не чтением, а вопросом «а лежит ли
        # `АПТ` на `window`» — и ответом «нет».
        #
        # Теперь подлог УДАЛЯЕТ ПО-НАСТОЯЩЕМУ, тем же адресом, каким это
        # делает экран, и ничего из внутренностей страницы не трогает.
        "window.addEventListener('load', () => {"
        "  window.аптСпросить = function (id) {"
        "    fetch('/medkit/api/items/' + id, {method: 'DELETE'})"
        "      .then(() => location.reload()); }; });",
        "удаление-спрашивает"),
    "регистр-не-приводится": (
        # ПОЛОВИНА ДОГОВОРА О ПОИСКЕ СЛОМАНА: сервер кладёт в `data-find`
        # приведённую строку, браузер обязан привести ЗАПРОС тем же
        # способом. Здесь он этого не делает — и «НУРОФЕН» перестаёт
        # находить «Нурофен», а «нурофен» находит по-прежнему.
        #
        # Дефект немой в чистом виде: поле работает, карточки прячутся
        # и показываются, счётчик «Показано N из M» меняется — просто
        # набранное с большой буквы не находится никогда, и ответ
        # неотличим от «у вас такого нет».
        #
        # Ломается ЗАПРОС, а не строка на сервере: подлог кладётся
        # В СТРАНИЦУ и кода экрана не трогает (§6.3).
        "window.addEventListener('load', () => {"
        "  const дно = String.prototype.toLowerCase;"
        "  String.prototype.toLowerCase = function () {"
        "    const поле = document.getElementById('apt-q');"
        "    if (поле && String(this) === поле.value) return String(this);"
        "    return дно.call(this); }; });",
        "поиск-регистр-и-кириллица"),
    "категория-не-ищется": (
        # Вторая половина: строка поиска собрана без имён категорий —
        # ровно то состояние, в котором раздел уехал в e5e15df. Подпись
        # поля при этом обещает «Название, вещество или категория»
        "window.addEventListener('load', () => {"
        "  document.querySelectorAll('.apt-card').forEach(к => {"
        "    к.dataset.find = (к.dataset.find || '').split(' ')"
        "      .slice(0, 2).join(' '); }); });",
        "поиск-по-категории"),
    "тюбику-дали-кнопку": (
        # Кнопка приёма у формы со ШКАЛОЙ. Точного числа у тюбика
        # не существует по построению (§5.8), значит и снимать нечем:
        # такая кнопка обещала бы действие, которого нет.
        #
        # Подлог держится наблюдателем, а не разовой вставкой: сетка
        # перерисовывается разметкой сервера, и одноразовая правка
        # исчезла бы на первом же обновлении
        "window.addEventListener('load', () => {"
        "  const дорисовать = () => document.querySelectorAll('.apt-scale')"
        "    .forEach(п => {"
        "      const карт = п.closest('.apt-card');"
        "      if (!карт || карт.querySelector('.apt-take')) return;"
        "      const б = document.createElement('button');"
        "      б.className = 'btn btn-secondary apt-take';"
        "      б.textContent = 'Принял 1';"
        "      п.after(б); });"
        "  setInterval(дорисовать, 200); });",
        "кнопка-приёма-по-счёту"),
    "склонение-машинное": (
        # Подпись собрана БЕЗ правил русского счёта — ровно то, что
        # получилось бы, начни браузер строить её вторым экземпляром
        # рядом с серверным (§6.0.7): «Принял 2 шт» вместо «2 таблетки»
        "window.addEventListener('load', () => {"
        "  const испортить = () => document.querySelectorAll('.apt-take')"
        "    .forEach(к => {"
        "      if (к.dataset.испорчено) return;"
        "      к.dataset.испорчено = '1';"
        "      const знак = к.querySelector('svg');"
        "      к.textContent = ' Принял 1 шт';"
        "      if (знак) к.prepend(знак); });"
        "  setInterval(испортить, 200); });",
        "склонение-у-всех-единиц"),
    "чип-врёт-числом": (
        # Число в чипе разошлось с сеткой: человек нажимает «Простуда 5»
        # и видит другое количество, а какое из двух настоящее — понять
        # на экране нечем
        "window.addEventListener('load', () => {"
        "  setInterval(() => document.querySelectorAll('#apt-chips .chip-n')"
        "    .forEach(э => {"
        "      if (э.dataset.n === 'all') return;"
        "      const n = parseInt(э.textContent, 10);"
        "      if (n > 0) э.textContent = String(n + 1); }), 200); });",
        "чип-не-врёт-числом"),
    "отмена-не-возвращает": (
        # Отмена «сработала», а число не вернулось — главный немой отказ
        # этого экрана
        "window.addEventListener('load', () => {"
        "  window.аптОтменитьПриём = function () {"
        "    window.аптЗакрытьПолосу(); }; });",
        "отмена-возвращает-точно"),
}


def _png_образец() -> bytes:
    """Настоящий PNG, а не подделка байтами: проба обязана проверять
    путь, по которому ходит человек, — Pillow на сервере разберёт
    и пересохранит именно картинку."""
    import io as _io
    from PIL import Image
    буфер = _io.BytesIO()
    Image.new("RGB", (320, 180), (40, 44, 60)).save(буфер, "PNG")
    return буфер.getvalue()


def _в_базе(запрос, параметры=()):
    conn = sqlite3.connect(DB)
    try:
        return conn.execute(запрос, параметры).fetchall()
    finally:
        conn.close()


class Отчёт:
    def __init__(self):
        self.шаги = []

    def шаг(self, имя, ок, что=""):
        self.шаги.append((имя, bool(ок), что))
        print(("   OK   " if ок else "  ПЛОХО ") + имя + (" — " + что if что else ""))

    @property
    def плохих(self):
        return [ш for ш in self.шаги if not ш[1]]


async def _войти(pg):
    await pg.goto(БАЗА + "/login", wait_until="domcontentloaded")
    await pg.fill("input[name=email]", ПОЧТА)
    await pg.fill("input[name=password]", ПАРОЛЬ)
    if await pg.query_selector(".cf-turnstile"):
        for _ in range(60):
            if await pg.evaluate("() => { const t = document.querySelector("
                                 "'[name=\"cf-turnstile-response\"]');"
                                 " return t && t.value; }"):
                break
            await pg.wait_for_timeout(500)
    await pg.click("button[type=submit]")
    await pg.wait_for_load_state("networkidle")
    if "/login" in pg.url:
        raise SystemExit("ВХОД НЕ СОСТОЯЛСЯ — снимать нечего")


ЖИВОЙ = """
(селектор) => {
  const el = document.querySelector(селектор);
  if (!el) return {есть: false, причина: 'элемента нет в дереве'};
  if (el.disabled) return {есть: true, живой: false, причина: 'disabled'};
  // ПОДВЕСТИ К ГЛАЗАМ ПЕРЕД ЗАМЕРОМ. `elementFromPoint` работает
  // в координатах ОКНА и за его пределами возвращает null — то есть
  // орган, лежащий ниже сгиба, объявлялся бы мёртвым. Первая версия
  // пробы так и сделала: три поля формы и кнопка приёма получили
  // «в центре лежит ничто» на исправном экране.
  el.scrollIntoView({block: 'center', behavior: 'instant'});
  const r = el.getBoundingClientRect();
  if (!r.width || !r.height)
    return {есть: true, живой: false, причина: 'нулевой размер'};
  const cs = getComputedStyle(el);
  if (cs.visibility === 'hidden' || cs.display === 'none')
    return {есть: true, живой: false, причина: 'скрыт стилем'};
  // ЖИВОЙ — значит до него ДОТЯГИВАЕТСЯ нажатие, а не «есть в дереве»
  const x = Math.round(r.left + r.width / 2);
  const y = Math.round(r.top + r.height / 2);
  const под = document.elementFromPoint(x, y);
  const свой = под && (под === el || el.contains(под) || под.contains(el));
  return {есть: true, живой: !!свой, размер: [Math.round(r.width),
          Math.round(r.height)],
          причина: свой ? '' : 'в центре лежит ' + (под ? под.className : 'ничто')};
}
"""

ОТКРЫТО = """
(id) => {
  const el = document.getElementById(id);
  // Открытость метит КЛАСС `open`, а не `hidden`: контейнер модалки лежит
  // в дереве всегда, и проверка по `hidden`/`display` отвечала бы «ДА»
  // и при подлоге, который окна не открывает вовсе (поймано контролем
  // у прохода админки)
  return !!el && el.classList.contains('open');
}
"""


async def прогон(ширина, отчёт, подлог=None):
    from playwright.async_api import async_playwright
    сенсор = ширина < 800
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context(
            viewport={"width": ширина, "height": 900 if not сенсор else 844},
            has_touch=сенсор, is_mobile=сенсор, device_scale_factor=1)
        if подлог:
            await ctx.add_init_script(ПОДЛОГИ[подлог][0])
        pg = await ctx.new_page()
        pg.on("pageerror", lambda e: отчёт.шаг(
            "консоль-без-ошибок", False, str(e)[:120]))
        await _войти(pg)
        try:
            await _пройти(pg, отчёт, ширина)
        finally:
            await ctx.close()
            await b.close()


async def _пройти(pg, о, ширина):
    await pg.goto(БАЗА + "/medkit", wait_until="networkidle")
    # ПЛАВНАЯ ПРОКРУТКА ГЛУШИТСЯ. `scroll-behavior: smooth` у `html`
    # означает, что прямоугольник читается ДО конца анимации, и проба
    # мерит положение, которого на экране уже нет. У проверки 20 это
    # дало 23 ложных «перекрытых» органа (§6.0.11)
    await pg.add_style_tag(content="html, * { scroll-behavior: auto !important }")
    await pg.wait_for_timeout(400)

    # ── 1. Экран нарисован СЕРВЕРОМ, а не дорисован скриптом ─────────
    карточек = await pg.evaluate("() => document.querySelectorAll('.apt-card').length")
    о.шаг("список-нарисован", карточек > 0, f"карточек {карточек}")

    в_базе = _в_базе("SELECT COUNT(*) FROM medkit_items WHERE user_id = "
                     "(SELECT id FROM users WHERE email = ?)", (ПОЧТА,))[0][0]
    о.шаг("экран-совпал-с-базой", карточек == в_базе,
          f"на экране {карточек}, в базе {в_базе}")

    # ── 2. Органы отбора и поиска ЖИВЫЕ ──────────────────────────────
    for имя, сел in (("чип-все", "#apt-chips [data-pick='all']"),
                     ("поиск", "#apt-q"),
                     ("кнопка-добавить", ".apt-add")):
        ж = await pg.evaluate(ЖИВОЙ, сел)
        о.шаг(f"живой-{имя}", ж.get("живой"), ж.get("причина", ""))

    # ── 3. ПОИСК ищет по ВЕЩЕСТВУ, а не только по названию ───────────
    # Половина ценности инструмента: Нурофен и Ибупрофен — одно и то же
    await pg.fill("#apt-q", "ибупрофен")
    await pg.wait_for_timeout(250)
    видно = await pg.evaluate(
        "() => [...document.querySelectorAll('.apt-card')]"
        ".filter(к => !к.hidden).map(к => к.querySelector('.apt-name').textContent.trim())")
    # СРАВНЕНИЕ В PYTHON, А НЕ ЧЕРЕЗ `lower()` SQLITE. Первая версия пробы
    # написала `lower(substance) LIKE '%ибупрофен%'` и получила НОЛЬ при
    # двух настоящих совпадениях: SQLite не приводит кириллицу к нижнему
    # регистру, и «Ибупрофен» под этот запрос не подходит. Ровно та ловушка,
    # из-за которой отбор в дневнике питания считает в Python (§5.0.4), —
    # и проба на ней поймалась сама
    вещества = _в_базе("SELECT substance FROM medkit_items WHERE user_id = "
                       "(SELECT id FROM users WHERE email = ?)", (ПОЧТА,))
    по_веществу = sum(1 for (в,) in вещества
                      if в and "ибупрофен" in в.lower())
    о.шаг("поиск-по-веществу", len(видно) == по_веществу and по_веществу > 0,
          f"на экране {len(видно)}, в базе по веществу {по_веществу}: {видно}")

    # ── 3б. РЕГИСТР И КИРИЛЛИЦА ──────────────────────────────────────
    #
    # ЗАЧЕМ ОТДЕЛЬНЫМ ШАГОМ. Постулат постановки был такой: «поиск
    # пользуется тем же `lower()`, что и проба, значит „нурофен“
    # не найдёт „Нурофен“». Замер 2026-08-24 его ОПРОВЕРГ — строку
    # приводит Python на сервере и `toLowerCase` в браузере, оба
    # Unicode-aware, а SQLite в поиске аптечки не участвует вовсе.
    #
    # Шаг всё равно нужен, и не для протокола: договор о приведении
    # регистра держат ДВЕ стороны в разных языках, и разойтись они могут
    # молча. Проверяется он единственным способом, каким это вообще
    # проверяемо, — одним запросом в трёх регистрах: числа обязаны
    # совпасть между собой и с базой.
    async def сколько(запрос):
        await pg.fill("#apt-q", запрос)
        await pg.dispatch_event("#apt-q", "input")
        await pg.wait_for_timeout(200)
        return await pg.evaluate(
            "document.querySelectorAll('.apt-card:not([hidden])').length")

    имена = _в_базе("SELECT name FROM medkit_items WHERE user_id = "
                    "(SELECT id FROM users WHERE email = ?)", (ПОЧТА,))
    в_базе_нурофен = sum(1 for (н,) in имена if "нурофен" in (н or "").lower())
    регистры = {q: await сколько(q)
                for q in ("нурофен", "НУРОФЕН", "Нурофен", "НуРоФеН")}
    о.шаг("поиск-регистр-и-кириллица",
          в_базе_нурофен > 0 and set(регистры.values()) == {в_базе_нурофен},
          f"в базе {в_базе_нурофен}, на экране {регистры}")

    # ── 3в. ПОЛЕ ОБЕЩАЕТ КАТЕГОРИЮ — ЗНАЧИТ ИЩЕТ ПО НЕЙ ──────────────
    #
    # Подпись поля говорит «Название, вещество или категория»: экран
    # объявляет свой договор сам, и не выполнять его — ложь на экране,
    # а не недостающая мелочь. Замер до правки: «простуда» давала
    # 0 находок при трёх позициях этой категории.
    #
    # Ожидание берётся ИЗ БАЗЫ, а не вписывается числом: категорию
    # у позиции завтра поправят, и вписанное число протухло бы молча.
    по_категории = _в_базе(
        "SELECT COUNT(DISTINCT ic.item_id) FROM medkit_item_categories ic "
        "JOIN medkit_categories c ON c.id = ic.category_id "
        "JOIN medkit_items i ON i.id = ic.item_id "
        "WHERE i.user_id = (SELECT id FROM users WHERE email = ?) "
        "AND c.name = ?", (ПОЧТА, "Простуда"))[0][0]
    видно_кат = await сколько("простуда")
    о.шаг("поиск-по-категории",
          по_категории > 0 and видно_кат == по_категории,
          f"«простуда»: на экране {видно_кат}, в базе {по_категории}")

    await pg.fill("#apt-q", "заведомо-такого-нет")
    await pg.wait_for_timeout(250)
    пусто_видно = await pg.evaluate(ОТКРЫТО.replace("classList.contains('open')",
                                                    "true") and
        "() => { const b = document.getElementById('apt-empty-find');"
        " return b && !b.hidden; }")
    о.шаг("пусто-в-отборе-названо", пусто_видно,
          "блок «здесь ничего не нашлось» показан")
    await pg.fill("#apt-q", "")
    await pg.wait_for_timeout(200)

    # ── 4. ФОРМА ЖИВАЯ ЦЕЛИКОМ ───────────────────────────────────────
    await pg.click(".apt-add")
    await pg.wait_for_timeout(400)
    о.шаг("форма-открылась", await pg.evaluate(ОТКРЫТО, "apt-form"))
    поля = ["#apt-f-name", "#apt-f-sub", "#apt-f-form", "#apt-f-left",
            "#apt-f-total", "#apt-f-exp", "#apt-f-open", "#apt-f-dose",
            "#apt-f-code", "#apt-f-url", "#apt-f-note", "#apt-f-photo",
            "#apt-save"]
    мёртвые = []
    for сел in поля:
        ж = await pg.evaluate(ЖИВОЙ, сел)
        if not ж.get("живой"):
            мёртвые.append(f"{сел}: {ж.get('причина')}")
    о.шаг("форма-жива", not мёртвые, "; ".join(мёртвые) or f"полей {len(поля)}")

    # ФОТО ВЫБИРАЕТСЯ СРАЗУ, а не «сначала сохраните»: порядок внутренний,
    # и человеку про него знать незачем
    фото = await pg.evaluate(ЖИВОЙ, "#apt-f-photo")
    о.шаг("фото-выбирается-сразу", фото.get("живой"),
          фото.get("причина", "поле файла живо в НОВОЙ позиции"))

    # ── 5. ОТКАЗ ПРИ ПУСТОМ ОБЯЗАТЕЛЬНОМ ПОЛЕ ────────────────────────
    было_до = _в_базе("SELECT COUNT(*) FROM medkit_items")[0][0]
    await pg.fill("#apt-f-name", "")
    await pg.fill("#apt-f-exp", "")
    await pg.evaluate("() => document.getElementById('apt-save').click()")
    await pg.wait_for_timeout(400)
    стало = _в_базе("SELECT COUNT(*) FROM medkit_items")[0][0]
    о.шаг("пустое-обязательное-не-сохраняется", стало == было_до,
          f"строк было {было_до}, стало {стало}")

    # ── 6. ЗАВЕДЕНИЕ ПОЗИЦИИ НАСКВОЗЬ ────────────────────────────────
    метка = "Проба-%d" % int(time.time())
    await pg.fill("#apt-f-name", метка)
    await pg.fill("#apt-f-sub", "Пробное вещество, 100 мг")
    await pg.select_option("#apt-f-form", "tablet")
    await pg.fill("#apt-f-left", "10")
    await pg.fill("#apt-f-total", "10")
    await pg.fill("#apt-f-dose", "2")
    await pg.fill("#apt-f-exp", "2028-06")
    await pg.evaluate("() => document.getElementById('apt-save').click()")
    await pg.wait_for_timeout(900)

    строки = _в_базе("SELECT id, qty_left, dose, expires_ym FROM medkit_items "
                     "WHERE name = ?", (метка,))
    о.шаг("позиция-в-базе", len(строки) == 1,
          f"строк с именем {метка}: {len(строки)}")
    if not строки:
        return
    новый, остаток, доза, срок = строки[0]
    о.шаг("поля-доехали", остаток == 10 and доза == 2 and срок == "2028-06",
          f"осталось {остаток}, доза {доза}, срок {срок}")
    на_экране = await pg.evaluate(
        "(м) => [...document.querySelectorAll('.apt-name')]"
        ".some(э => э.textContent.trim() === м)", метка)
    о.шаг("позиция-на-экране", на_экране, "карточка появилась без перезагрузки")

    # ── 7. ПОДПИСЬ КНОПКИ ПРИЁМА СКЛОНЕНА ────────────────────────────
    подпись = await pg.evaluate(
        "(id) => { const б = document.querySelector('[data-take=\"' + id + '\"]');"
        " return б ? б.textContent.trim() : null; }", новый)
    о.шаг("подпись-приёма-склонена", подпись == "Принял 2 таблетки",
          f"на кнопке: {подпись!r} (доза 2)")

    # ── 8. СПИСАНИЕ: без подтверждения, с отменой ПОСЛЕ ───────────────
    ж = await pg.evaluate(ЖИВОЙ, f"[data-take='{новый}']")
    о.шаг("живая-кнопка-приёма", ж.get("живой"), ж.get("причина", ""))
    await pg.evaluate("(id) => document.querySelector("
                      "'[data-take=\"' + id + '\"]').click()", новый)
    await pg.wait_for_timeout(700)
    после = _в_базе("SELECT qty_left, opened_on FROM medkit_items WHERE id = ?",
                    (новый,))[0]
    о.шаг("списание-сняло-дозу", после[0] == 8,
          f"в базе осталось {после[0]} (было 10, доза 2)")
    о.шаг("вскрытие-встало-само", bool(после[1]),
          f"opened_on = {после[1]!r} — ставится при первом приёме")
    полоса = await pg.evaluate(
        "() => { const b = document.getElementById('undo-bar');"
        " return {видна: b.classList.contains('show'),"
        "         текст: document.getElementById('undo-bar-text').textContent}; }")
    о.шаг("полоса-отмены-показана", полоса["видна"], полоса["текст"])
    о.шаг("фраза-списания-склонена",
          "2 таблетки" in (полоса["текст"] or ""),
          f"на полосе: {полоса['текст']!r}")

    # ── 9. ОТМЕНА ВОЗВРАЩАЕТ РОВНО ПРЕЖНЕЕ ЧИСЛО ─────────────────────
    # Проверяется ЗАМЕРОМ, а не чтением: «прибавить дозу обратно» дало бы
    # тот же результат здесь и РАЗОШЛОСЬ бы там, где остаток упирался
    # в ноль. Поэтому ниже отдельный случай с нулём
    await pg.evaluate("() => document.querySelector('.undo-bar-btn').click()")
    await pg.wait_for_timeout(700)
    вернулось = _в_базе("SELECT qty_left, opened_on FROM medkit_items "
                        "WHERE id = ?", (новый,))[0]
    о.шаг("отмена-возвращает-точно", вернулось[0] == 10,
          f"в базе {вернулось[0]}, ожидалось 10")
    о.шаг("отмена-снимает-вскрытие", not вернулось[1],
          f"opened_on = {вернулось[1]!r} — пометку ставило само списание")

    # ── 10. ДВА НАЖАТИЯ = ДВЕ ДОЗЫ, отмена возвращает к НАЧАЛУ ───────
    for _ in range(2):
        await pg.evaluate("(id) => document.querySelector("
                          "'[data-take=\"' + id + '\"]').click()", новый)
        await pg.wait_for_timeout(600)
    подряд = _в_базе("SELECT qty_left FROM medkit_items WHERE id = ?",
                     (новый,))[0][0]
    о.шаг("два-нажатия-две-дозы", подряд == 6,
          f"в базе {подряд}, ожидалось 6 (10 − 2 − 2)")
    await pg.evaluate("() => document.querySelector('.undo-bar-btn').click()")
    await pg.wait_for_timeout(700)
    пачкой = _в_базе("SELECT qty_left FROM medkit_items WHERE id = ?",
                     (новый,))[0][0]
    о.шаг("отмена-возвращает-пачку", пачкой == 10,
          f"в базе {пачкой}, ожидалось 10 — к состоянию ДО первого нажатия")

    # ── 11. СПИСАНИЕ ДО НУЛЯ И ОТМЕНА С УПОРОМ В НОЛЬ ────────────────
    # Ровно тот случай, где «прибавить дозу обратно» соврало бы:
    # при остатке 1 и дозе 2 остаток станет 0, а вернуться обязан в 1
    conn = sqlite3.connect(DB)
    conn.execute("UPDATE medkit_items SET qty_left = 1, opened_on = NULL "
                 "WHERE id = ?", (новый,))
    conn.commit()
    conn.close()
    await pg.reload(wait_until="networkidle")
    await pg.wait_for_timeout(400)
    await pg.evaluate("(id) => document.querySelector("
                      "'[data-take=\"' + id + '\"]').click()", новый)
    await pg.wait_for_timeout(700)
    нолём = _в_базе("SELECT qty_left FROM medkit_items WHERE id = ?",
                    (новый,))[0][0]
    о.шаг("остаток-не-уходит-в-минус", нолём == 0,
          f"в базе {нолём} (было 1, доза 2)")
    await pg.evaluate("() => document.querySelector('.undo-bar-btn').click()")
    await pg.wait_for_timeout(700)
    из_нуля = _в_базе("SELECT qty_left FROM medkit_items WHERE id = ?",
                      (новый,))[0][0]
    о.шаг("отмена-от-нуля-точна", из_нуля == 1,
          f"в базе {из_нуля}, ожидалось 1 — «прибавить дозу» дало бы 2")

    # ── 11б. ФОТО УПАКОВКИ НАСКВОЗЬ ──────────────────────────────────
    #
    # Отдельным шагом и с ОТРИЦАТЕЛЬНЫМ КОНТРОЛЕМ: «загрузка вернула 200»
    # и «человек увидел картинку» — разные утверждения, и между ними
    # умещается целый класс отказов. Ровно здесь он и случился: колонка
    # называлась `photo`, общий обработчик отдачи ищет `image_path`,
    # и КАЖДАЯ картинка отдавалась 404 при успешной загрузке
    await pg.evaluate("(id) => document.querySelector("
                      "'[data-edit=\"' + id + '\"]').click()", новый)
    await pg.wait_for_timeout(400)
    await pg.set_input_files("#apt-f-photo", {
        "name": "proba.png", "mimeType": "image/png",
        "buffer": _png_образец()})
    await pg.evaluate("() => document.getElementById('apt-save').click()")
    await pg.wait_for_timeout(1500)
    токен = _в_базе("SELECT image_path FROM medkit_items WHERE id = ?",
                    (новый,))[0][0]
    о.шаг("фото-в-базе", bool(токен), f"токен {токен!r}")
    if токен:
        путь = os.path.join(os.path.dirname(DB) or ".", "media", "medkit",
                            str(_в_базе("SELECT user_id FROM medkit_items "
                                        "WHERE id = ?", (новый,))[0][0]),
                            токен + ".jpg")
        о.шаг("фото-на-томе", os.path.exists(путь), путь)
    # НАБЛЮДАЕМЫЙ результат: картинка не просто «есть в разметке»,
    # а ЗАГРУЗИЛАСЬ. `naturalWidth === 0` у 404 — то есть проверка
    # по наличию тега пропустила бы весь дефект
    видна = await pg.evaluate("""(id) => {
      const к = document.querySelector('.apt-card[data-id="' + id + '"]');
      const i = к && к.querySelector('.apt-ph img');
      return i ? {есть: true, ширина: i.naturalWidth, src: i.getAttribute('src')}
               : {есть: false};
    }""", новый)
    о.шаг("фото-на-экране-загрузилось",
          видна.get("есть") and видна.get("ширина", 0) > 0,
          f"{видна}")

    # ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ ЗАГРУЗКИ: не картинка обязана быть отвергнута,
    # и СТАРАЯ картинка при этом обязана остаться. «Отверг и заодно стёр»
    # было бы тем же немым отказом с другой стороны
    было_фото = токен
    ответ = await pg.evaluate("""async (id) => {
      const ф = new FormData();
      ф.append('file', new Blob(['это не картинка, а текст'],
               {type: 'image/png'}), 'fake.png');
      const r = await fetch('/medkit/api/items/' + id + '/photo',
                            {method: 'POST', body: ф});
      let т = {}; try { т = await r.json(); } catch (e) {}
      return {код: r.status, ошибка: т.error || ''};
    }""", новый)
    о.шаг("не-картинка-отвергнута", ответ["код"] == 400,
          f"HTTP {ответ['код']}: {ответ['ошибка']}")
    осталось_фото = _в_базе("SELECT image_path FROM medkit_items WHERE id = ?",
                            (новый,))[0][0]
    о.шаг("отказ-не-стёр-прежнее-фото", осталось_фото == было_фото,
          f"в базе {осталось_фото!r}, было {было_фото!r}")

    # ── 12. ПРАВКА ───────────────────────────────────────────────────
    await pg.evaluate("(id) => document.querySelector("
                      "'[data-edit=\"' + id + '\"]').click()", новый)
    await pg.wait_for_timeout(400)
    о.шаг("правка-открылась", await pg.evaluate(ОТКРЫТО, "apt-form"))
    имя_в_форме = await pg.evaluate(
        "() => document.getElementById('apt-f-name').value")
    о.шаг("правка-подставила-значения", имя_в_форме == метка,
          f"в поле {имя_в_форме!r}")
    await pg.fill("#apt-f-name", метка + "-правлено")
    await pg.evaluate("() => document.getElementById('apt-save').click()")
    await pg.wait_for_timeout(900)
    правлено = _в_базе("SELECT name FROM medkit_items WHERE id = ?",
                       (новый,))[0][0]
    о.шаг("правка-доехала-до-базы", правлено == метка + "-правлено",
          f"в базе {правлено!r}")

    # ── 13. ФОРМА ОПРЕДЕЛЯЕТ ЕДИНИЦУ: несочетаемое выбрать нельзя ────
    await pg.evaluate("() => аптОткрытьФорму()")
    await pg.wait_for_timeout(300)
    await pg.select_option("#apt-f-form", "ointment")
    await pg.wait_for_timeout(300)
    тюбик = await pg.evaluate("""() => ({
      число_скрыто: [...document.querySelectorAll('.apt-only-exact')]
                      .every(э => э.hidden),
      шкала_видна: [...document.querySelectorAll('.apt-only-scale')]
                      .some(э => !э.hidden),
    })""")
    # СРОК ПОСЛЕ ВСКРЫТИЯ обязан ОСТАТЬСЯ у тюбика: у мази умолчание
    # 90 дней, и поле, пропавшее вместе с дозой, править нечем
    дней_видно = await pg.evaluate(
        "() => !document.getElementById('apt-f-days-box').hidden")
    о.шаг("у-тюбика-есть-срок-после-вскрытия", дней_видно,
          "поле «годен после вскрытия» живо и у формы со шкалой")
    о.шаг("у-тюбика-нет-числа", тюбик["число_скрыто"] and тюбик["шкала_видна"],
          f"поля числа скрыты: {тюбик['число_скрыто']}, "
          f"шкала показана: {тюбик['шкала_видна']}")
    await pg.select_option("#apt-f-form", "powder")
    await pg.wait_for_timeout(250)
    порошок = await pg.evaluate(
        "() => ({выбор: !document.getElementById('apt-f-unit-box').hidden,"
        " единиц: document.getElementById('apt-f-unit').options.length})")
    о.шаг("у-порошка-выбор-единицы", порошок["выбор"] and порошок["единиц"] == 2,
          f"короб единицы виден: {порошок['выбор']}, вариантов {порошок['единиц']}")
    await pg.select_option("#apt-f-form", "tablet")
    await pg.wait_for_timeout(250)
    таблетки = await pg.evaluate(
        "() => document.getElementById('apt-f-unit-box').hidden")
    о.шаг("выбора-из-одного-нет", таблетки,
          "короб единицы спрятан у формы с единственной единицей")
    await pg.evaluate("() => закрыть_модалку('apt-form')")
    await pg.wait_for_timeout(300)

    # ── 14. УДАЛЕНИЕ СПРАШИВАЕТ ВСЕГДА ───────────────────────────────
    await pg.evaluate("(id) => document.querySelector("
                      "'[data-del=\"' + id + '\"]').click()", новый)
    await pg.wait_for_timeout(400)
    спросили = await pg.evaluate(ОТКРЫТО, "apt-del")
    о.шаг("удаление-спрашивает", спросили, "системное окно, а не confirm()")
    ещё_тут = _в_базе("SELECT COUNT(*) FROM medkit_items WHERE id = ?",
                      (новый,))[0][0]
    о.шаг("вопрос-ничего-не-удалил", ещё_тут == 1,
          "позиция на месте, пока не подтвердили")
    # Отмена: «Оставить» обязана оставить
    await pg.evaluate("() => document.querySelector("
                      "'#apt-del [data-modal-close]').click()")
    await pg.wait_for_timeout(400)
    после_отказа = _в_базе("SELECT COUNT(*) FROM medkit_items WHERE id = ?",
                           (новый,))[0][0]
    о.шаг("отказ-от-удаления-оставляет", после_отказа == 1,
          f"строк {после_отказа}")

    await pg.evaluate("(id) => document.querySelector("
                      "'[data-del=\"' + id + '\"]').click()", новый)
    await pg.wait_for_timeout(300)
    await pg.evaluate("() => document.querySelector("
                      "'#apt-del .btn-danger').click()")
    await pg.wait_for_timeout(900)
    удалено = _в_базе("SELECT COUNT(*) FROM medkit_items WHERE id = ?",
                      (новый,))[0][0]
    о.шаг("удаление-доехало", удалено == 0, f"строк осталось {удалено}")
    ушла = await pg.evaluate(
        "(м) => ![...document.querySelectorAll('.apt-name')]"
        ".some(э => э.textContent.trim().startsWith(м))", метка)
    о.шаг("карточка-исчезла-с-экрана", ушла)

    # ── 15. КАТЕГОРИИ: своя заводится и удаляется, базовая нет ───────
    await pg.evaluate("() => открыть_модалку('apt-cats')")
    await pg.wait_for_timeout(400)
    о.шаг("окно-категорий-открылось", await pg.evaluate(ОТКРЫТО, "apt-cats"))
    базовых_с_кнопкой = await pg.evaluate(
        "() => [...document.querySelectorAll('.apt-cat-item')]"
        ".filter(li => li.querySelector('.apt-cat-base')"
        "           && li.querySelector('[data-cat-del]')).length")
    о.шаг("базовую-не-удалить", базовых_с_кнопкой == 0,
          f"базовых с кнопкой удаления: {базовых_с_кнопкой}")

    # ── 15б. ВСЕ ФОРМЫ ВЫПУСКА ───────────────────────────────────────
    #
    # Идёт ПОСЛЕ пробной позиции и её удаления, на данных стенда: своя
    # позиция прохода — всегда таблетка, то есть одна форма из двенадцати
    await pg.evaluate("() => { const о = document.querySelector('.modal-ov.open');"
                      " if (о) о.classList.remove('open'); }")
    await pg.wait_for_timeout(200)
    await pg.goto(БАЗА + "/medkit", wait_until="networkidle")
    await pg.wait_for_timeout(400)
    await _формы_насквозь(pg, о)

    # ── 16. ТАЧ-ТАРГЕТ на сенсорной ширине ───────────────────────────
    #
    # ОКНО ЗАКРЫВАЕТСЯ ПЕРЕД ЗАМЕРОМ. Первая версия пробы мерила область
    # нажатия при ОТКРЫТОЙ модалке категорий: `elementFromPoint` честно
    # возвращал затемнение поверх страницы, и все пятнадцать чипов
    # получили «0x0». Проба объявила бы находкой исправный экран —
    # а «пятнадцать органов меньше 44» читается ровно так же уверенно,
    # как настоящая находка
    await pg.evaluate("() => закрыть_модалку('apt-cats')")
    await pg.wait_for_timeout(400)
    if ширина < 800:
        мелкие = await pg.evaluate("""() => {
          const мал = [];
          document.querySelectorAll('.apt-card [data-edit], .apt-card [data-del],'
            + ' #apt-chips .chip').forEach(э => {
            if (э.hidden) return;
            // ПОДВЕСТИ К ГЛАЗАМ ПЕРЕД ЗАМЕРОМ КАЖДОГО. `elementFromPoint`
            // работает в координатах ОКНА и за его пределами отдаёт null:
            // вторая версия пробы мерила чипы, уехавшие вверх после
            // прокрутки к последней карточке, и объявила «0x0» у всех
            // пятнадцати. Проба, врущая находками, хуже отсутствующей
            э.scrollIntoView({block: 'center', behavior: 'instant'});
            const r = э.getBoundingClientRect();
            // Область НАЖАТИЯ, а не размер элемента: видимый чип 28px
            // ловит 44 невидимым слоем `.tap-44`, и мерка по прямоугольнику
            // объявила бы находкой уже починенное (§6.0.11)
            const cx = Math.round(r.left + r.width / 2);
            const cy = Math.round(r.top + r.height / 2);
            const свой = (x, y) => { const u = document.elementFromPoint(x, y);
              return u && (u === э || э.contains(u) || u.contains(э)); };
            if (!свой(cx, cy)) {
              const u = document.elementFromPoint(cx, cy);
              мал.push('НЕ ДОСТАЁТСЯ ' + э.textContent.trim().slice(0, 14)
                       + ' (под центром: ' + (u ? (u.className || u.tagName)
                                                : 'ничто') + ')');
              return;
            }
            let л = cx, п = cx, в = cy, н = cy;
            for (let i = 1; i <= 30; i++) { if (!свой(cx - i, cy)) break; л = cx - i; }
            for (let i = 1; i <= 30; i++) { if (!свой(cx + i, cy)) break; п = cx + i; }
            for (let i = 1; i <= 30; i++) { if (!свой(cx, cy - i)) break; в = cy - i; }
            for (let i = 1; i <= 30; i++) { if (!свой(cx, cy + i)) break; н = cy + i; }
            // +1: считаем ПИКСЕЛИ, а не разность координат. Область
            // ровно в 44 пикселя даёт крайние точки, отстоящие на 43,
            // и без этого проба объявляла бы находкой добор, сработавший
            // ровно так, как обещано
            const ш = п - л + 1, вы = н - в + 1;
            if (ш < 44 || вы < 44)
              мал.push(э.textContent.trim().slice(0, 14) + ' '
                       + Math.round(ш) + 'x' + Math.round(вы));
          });
          return мал;
        }""")
        о.шаг("тач-таргет-44", not мелкие,
              "; ".join(мелкие[:6]) or "все органы карточки и чипы ≥ 44")


def _убрать_пробы():
    """Пробные позиции за собой. Мусор инструмента приёмки читается
    как находка проверки данных и делает кадр дифа недетерминированным —
    ровно на этом споткнулась проба каталога Enshrouded (BACKLOG №152)."""
    conn = sqlite3.connect(DB)
    try:
        n = conn.execute("DELETE FROM medkit_items WHERE name LIKE 'Проба-%'"
                         ).rowcount
        conn.commit()
        return n
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════════════
# ВСЕ ФОРМЫ ВЫПУСКА НАСКВОЗЬ
# ══════════════════════════════════════════════════════════════════════
#
# ЗАЧЕМ ОТДЕЛЬНЫМ РАЗДЕЛОМ. Проход выше заводит СВОЮ пробную позицию,
# и она всегда таблетка: единственная форма, которую он трогает, — одна
# из двенадцати. Замер 2026-08-24 на стенде до правки seed: форм
# в справочнике 12, на стенде 7 — то есть пять форм не показывались
# ни одним снимком и ни одним прогоном.
#
# Цена этого выше обычной: у каждой единицы СВОИ три формы склонения
# («принял 1 свечу», «2 ампулы», «5 пакетиков»), и ошибка в них видна
# только на экране с этой формой. А у форм со шкалой кнопки приёма
# не должно быть вовсе — утверждение, которое до сих пор не проверял
# никто.
#
# СПИСОК ФОРМ БЕРЁТСЯ ИЗ СПРАВОЧНИКА, а не перечисляется здесь:
# форма, заведённая завтра в `medkit_defs`, попадёт под проверку сама,
# а форма, которой нет на стенде, будет НАЗВАНА, а не пропущена молча
# (§6.0.7).


def _позиции_стенда():
    return _в_базе(
        "SELECT id, name, form, unit, scale, qty_left, dose FROM medkit_items "
        "WHERE user_id = (SELECT id FROM users WHERE email = ?) "
        "ORDER BY id", (ПОЧТА,))


async def _формы_насквозь(pg, о):
    import medkit_defs as опр

    строки = _позиции_стенда()
    по_форме = {}
    for (ид, имя, форма, ед, шкала, осталось, доза) in строки:
        по_форме.setdefault(форма, (ид, имя, ед, шкала, осталось, доза))

    нет = [ф["id"] for ф in опр.ФОРМЫ if ф["id"] not in по_форме]
    о.шаг("все-формы-на-стенде", not нет,
          "нет на стенде: %s" % (", ".join(нет) or "ни одной")
          + " (из %d)" % len(опр.ФОРМЫ))

    # ── КНОПКА ПРИЁМА ЕСТЬ РОВНО ТАМ, ГДЕ ЕСТЬ ЧИСЛО ────────────────
    #
    # У тюбика точного числа не существует по построению (§5.8), значит
    # и снимать кнопкой нечего. «Кнопки нет» — утверждение о КАЖДОЙ форме
    # со шкалой, и проверяется оно по всем сразу, а не на одной
    ошибки = []
    for ф in опр.ФОРМЫ:
        если_есть = по_форме.get(ф["id"])
        if not если_есть:
            continue
        ид = если_есть[0]
        есть_кнопка = await pg.evaluate(
            "(id) => !!document.querySelector('.apt-card[data-id=\"' + id + "
            "'\"] .apt-take')", str(ид))
        ждём = ф["счёт"] != "шкала"
        if есть_кнопка != ждём:
            ошибки.append("%s: кнопка %s, а счёт «%s»"
                          % (ф["id"], "есть" if есть_кнопка else "нет",
                             ф["счёт"]))
    о.шаг("кнопка-приёма-по-счёту", not ошибки,
          "; ".join(ошибки) or "у форм со шкалой кнопки нет, у остальных есть")

    # ── СКЛОНЕНИЕ ПОДПИСИ У КАЖДОЙ ЕДИНИЦЫ ──────────────────────────
    #
    # Ожидание считается ЗДЕСЬ по `medkit_defs`, а не берётся с экрана:
    # сверять экран с экраном значит не сверять ничего
    расхождения = []
    for (ид, имя, форма, ед, шкала, осталось, доза) in строки:
        if опр.ФОРМА_ПО_ID.get(форма, {}).get("счёт") == "шкала" or not доза:
            continue
        слово = опр.склонение(доза, опр.ЕДИНИЦЫ[ед]["слово"])
        ждём = ("Принял %s %s" % (опр.число(доза), слово)).strip()
        на_экране = await pg.evaluate(
            "(id) => { const к = document.querySelector("
            "'.apt-card[data-id=\"' + id + '\"] .apt-take');"
            r" return к ? к.textContent.trim().replace(/\s+/g, ' ') : null; }",
            str(ид))
        if на_экране != ждём:
            расхождения.append("%s: на экране %r, ждали %r"
                               % (имя, на_экране, ждём))
    о.шаг("склонение-у-всех-единиц", not расхождения,
          "; ".join(расхождения) or "подписи совпали у всех форм со счётом")

    # ── ШКАЛА ТЮБИКА: ПОЛОСА ЕСТЬ, ЧИСЛА НЕТ ────────────────────────
    ступени = {}
    for (ид, имя, форма, ед, шкала, осталось, доза) in строки:
        if шкала:
            ступени.setdefault(шкала, ид)
    нет_ступеней = [ш["id"] for ш in опр.ШКАЛА if ш["id"] not in ступени]
    о.шаг("все-ступени-шкалы-на-стенде", not нет_ступеней,
          "нет: %s" % (", ".join(нет_ступеней) or "ни одной"))
    плохо = []
    for ступень, ид in ступени.items():
        доля = await pg.evaluate(
            "(id) => { const п = document.querySelector('.apt-card[data-id=\"'"
            " + id + '\"] .apt-scale .meter-fill');"
            " return п ? п.style.width : null; }", str(ид))
        ждём = "%d%%" % опр.ШКАЛА_ПО_ID[ступень]["доля"]
        if доля != ждём:
            плохо.append("%s: полоса %r, ждали %r" % (ступень, доля, ждём))
    о.шаг("полоса-тюбика-по-ступени", not плохо,
          "; ".join(плохо) or "доли трёх ступеней совпали")

    # ── СПИСАНИЕ У СИРОПА СНИМАЕТ МИЛЛИЛИТРЫ, А НЕ ШТУКУ ────────────
    #
    # Прямой вопрос постановки. Ловушка настоящая: «единица» и «доза» —
    # разные поля, и списание единицы вместо дозы у таблеток (доза 1)
    # выглядело бы исправным, а у сиропа с дозой 10 мл ошибалось бы
    # в десять раз
    сироп = по_форме.get("syrup")
    if сироп:
        ид, имя, ед, шкала, было, доза = сироп
        await pg.evaluate("(id) => document.querySelector('.apt-card[data-id="
                          "\"' + id + '\"] .apt-take').click()", str(ид))
        await pg.wait_for_timeout(900)
        стало = _в_базе("SELECT qty_left FROM medkit_items WHERE id = ?",
                        (ид,))[0][0]
        о.шаг("сироп-списывает-дозу-в-мл", стало == было - доза,
              "%s: было %s мл, доза %s мл, стало %s"
              % (имя, было, доза, стало))
        await pg.evaluate("window.аптОтменитьПриём()")
        await pg.wait_for_timeout(900)
        вернулось = _в_базе("SELECT qty_left, opened_on FROM medkit_items "
                            "WHERE id = ?", (ид,))[0]
        о.шаг("сироп-отмена-возвращает-точно", вернулось[0] == было,
              "в базе %s, ожидалось %s" % (вернулось[0], было))
    else:
        о.шаг("сироп-списывает-дозу-в-мл", False, "сиропа нет на стенде")

    # ── ПОЗИЦИЯ БЕЗ КАТЕГОРИЙ ВИДНА В «ВСЕ» ─────────────────────────
    #
    # Отбор «Все» — не фильтр, а его отсутствие, и позиция без единой
    # категории не имеет права из него выпасть. Отказ был бы немой:
    # карточка просто не показывалась бы, а число в чипе «Все» при этом
    # считается по тому же списку и совпало бы
    без_кат = _в_базе(
        "SELECT i.id, i.name FROM medkit_items i "
        "WHERE i.user_id = (SELECT id FROM users WHERE email = ?) "
        "AND NOT EXISTS (SELECT 1 FROM medkit_item_categories c "
        "                WHERE c.item_id = i.id)", (ПОЧТА,))
    о.шаг("на-стенде-есть-позиция-без-категорий", bool(без_кат),
          ", ".join(н for (_, н) in без_кат) or "нет ни одной")
    if без_кат:
        ид, имя = без_кат[0]
        видна = await pg.evaluate(
            "(id) => { const к = document.querySelector('.apt-card[data-id=\"'"
            " + id + '\"]'); return !!к && !к.hidden; }", str(ид))
        о.шаг("без-категорий-видна-в-все", видна, имя)
        # И ПРОПАДАЕТ ИЗ ЛЮБОГО ДРУГОГО ОТБОРА — вторая половина: попади
        # она в чужую категорию, чип показывал бы одно число, а сетка
        # другое
        чип = await pg.evaluate(
            "() => { const ч = [...document.querySelectorAll("
            "'#apt-chips .chip')].find(c => c.dataset.pick !== 'all'"
            " && !c.hidden && !c.hasAttribute('data-cats-open'));"
            " if (!ч) return null; ч.click(); return ч.dataset.pick; }")
        await pg.wait_for_timeout(250)
        if чип:
            видна2 = await pg.evaluate(
                "(id) => { const к = document.querySelector('.apt-card"
                "[data-id=\"' + id + '\"]'); return !!к && !к.hidden; }",
                str(ид))
            о.шаг("без-категорий-нет-в-чужом-отборе", not видна2,
                  "отбор %r" % чип)
        await pg.evaluate(
            "() => document.querySelector('#apt-chips .chip"
            "[data-pick=\"all\"]').click()")
        await pg.wait_for_timeout(200)

    # ── ЧИСЛО В ЧИПЕ СОВПАДАЕТ С ЧИСЛОМ ВИДИМЫХ КАРТОЧЕК ────────────
    #
    # Чип объявляет, сколько найдётся. Разойдись он с сеткой — человек
    # нажал бы «Простуда 5» и увидел три карточки, а понять, какое число
    # настоящее, было бы нечем
    расхождения = await pg.evaluate("""async () => {
      const плохо = [];
      const чипы = [...document.querySelectorAll('#apt-chips .chip')]
        .filter(ч => !ч.hidden && ч.dataset.pick);
      for (const ч of чипы) {
        const обещано = parseInt(
          (ч.querySelector('.chip-n') || {}).textContent || '0', 10);
        ч.click();
        await new Promise(r => setTimeout(r, 120));
        const видно = document.querySelectorAll(
          '.apt-card:not([hidden])').length;
        if (видно !== обещано)
          плохо.push(ч.dataset.pick + ': чип ' + обещано + ', карточек ' + видно);
      }
      document.querySelector('#apt-chips .chip[data-pick="all"]').click();
      return плохо;
    }""")
    await pg.wait_for_timeout(200)
    о.шаг("чип-не-врёт-числом", not расхождения,
          "; ".join(расхождения) or "все чипы совпали с сеткой")


# ══════════════════════════════════════════════════════════════════════
# ПУСТОЙ ЭКРАН И ОБРАТНЫЙ ПЕРЕХОД (§6.3)
# ══════════════════════════════════════════════════════════════════════
#
# ОТДЕЛЬНЫМ РЕЖИМОМ, А НЕ ШАГОМ ОБЩЕГО ПРОХОДА, потому что он ОПУСТОШАЕТ
# аптечку: другого способа увидеть пустой экран нет. Общий проход обязан
# оставаться повторяемым, поэтому режим называется вслух и в конце сам
# говорит, что стенд надо пересеять.
#
# ЗАЧЕМ ВООБЩЕ. Пустое состояние — единственный экран, который человек
# видит ПЕРВЫМ, и единственный, которого нет ни на одном снимке приёмки,
# пока в базе есть хоть одна позиция. До этого режима оно проверялось
# ровно тем, что кто-то однажды посмотрел на него глазами.
#
# ОБРАТНЫЙ ПЕРЕХОД — половина ценности режима. Правка «спрятать лишнее
# на пустом экране» ломается не там, где прячет, а там, где ВОЗВРАЩАЕТ:
# поле поиска уходит вместе с набранным в нём текстом, а текст в нём
# остаётся. Заведи человек первую позицию — поле вернётся с прежним
# запросом и, скорее всего, скроет ровно ту карточку, которую он только
# что завёл. Ни ошибки, ни признака на экране.

ПРЯЧЕТСЯ_НА_ПУСТОМ = [
    (".apt-bar", "ряд поиска и кнопки"),
    (".apt-chips", "чипы отбора и «+ Категория»"),
    (".apt-legend", "легенда цветов срока"),
]
ОСТАЁТСЯ_НА_ПУСТОМ = [
    (".apt-title", "заголовок раздела"),
    (".apt-sub", "подзаголовок"),
    (".apt-empty .empty-state-icon", "иллюстрация"),
    (".apt-empty .empty-state-title", "заголовок приглашения"),
    (".apt-empty .empty-state-sub", "текст приглашения"),
    (".apt-empty .btn-primary", "кнопка «Добавить лекарство»"),
]

ВИДЕН = """
(селектор) => {
  const el = document.querySelector(селектор);
  if (!el) return {есть: false, виден: false};
  const r = el.getBoundingClientRect();
  const cs = getComputedStyle(el);
  return {есть: true,
          виден: !!(r.width && r.height) && cs.visibility !== 'hidden'
                 && cs.display !== 'none' && !el.hidden};
}
"""


# ПОДЛОГИ РЕЖИМА ПУСТОГО ЭКРАНА. Свои, а не общие: подлог «мёртвая форма»
# на пустом экране ничего не говорит, а «класс пустоты не ставится» —
# ровно то состояние, в котором раздел уехал в e5e15df.
ПОДЛОГИ_ПУСТОГО = {
    "пустота-не-объявляется": (
        # ДОРЕФОРМЕННОЕ СОСТОЯНИЕ ЦЕЛИКОМ: класс не ставит ни сервер,
        # ни скрипт. На пустом экране остаются поиск, чипы «Все 0»
        # и «+ Категория» и легенда цветов, которых ни у одной карточки
        # нет — четыре органа, которым нечего делать.
        #
        # Возвращать надо ВСЕ условия прежнего состояния, а не одно
        # (§6.0.16): сними только скрипт — сервер всё равно пометил бы
        # первый кадр, и половина шагов осталась бы зелёной
        "window.addEventListener('load', () => {"
        "  const о = document.querySelector('.apt-wrap');"
        "  if (о) о.classList.remove('apt-blank');"
        "  window.аптПустота = function () {}; });",
        "после-удаления-спрятан-apt-bar"),
    "запрос-переживает-опустошение": (
        # Класс ставится, а состояние не чистится — типовой недоделок
        # такой правки: поле спряталось вместе с текстом, текст остался.
        # Заведённая следом первая позиция окажется скрыта прежним
        # запросом, и экран покажет пустоту при непустой аптечке
        "window.addEventListener('load', () => {"
        "  const было = window.аптПустота;"
        "  window.аптПустота = function (пусто) {"
        "    const поле = document.getElementById('apt-q');"
        "    const текст = поле ? поле.value : '';"
        "    было(пусто);"
        "    if (поле) поле.value = текст; }; });",
        "запрос-сброшен"),
}


async def _опустошить(pg, о):
    """Убрать всё, КРОМЕ последней позиции: последнюю удаляем через экран.

    Именно переход «была одна — стало ноль» и есть предмет замера:
    экран обязан прийти в пустое состояние ЦЕЛИКОМ, не перезагружаясь.
    """
    было = await pg.evaluate("document.querySelectorAll('.apt-card').length")
    ушло = await pg.evaluate("""async () => {
      const ид = [...document.querySelectorAll('.apt-card')]
        .map(к => к.dataset.id).slice(0, -1);
      let n = 0;
      for (const id of ид) {
        const о = await fetch('/medkit/api/items/' + id, {method: 'DELETE'});
        if (о.ok) n++;
      }
      return n;
    }""")
    await pg.reload(wait_until="networkidle")
    await pg.wait_for_timeout(300)
    осталось = await pg.evaluate("document.querySelectorAll('.apt-card').length")
    о.шаг("осталась-одна-позиция", осталось == 1,
          "было %d, убрано %d, осталось %d" % (было, ушло, осталось))
    return осталось == 1


async def _пустой_экран(pg, о, метка):
    for сел, имя in ПРЯЧЕТСЯ_НА_ПУСТОМ:
        в = await pg.evaluate(ВИДЕН, сел)
        о.шаг("%s-спрятан-%s" % (метка, сел.lstrip(".")), not в["виден"],
              "%s: есть в дереве %s, виден %s" % (имя, в["есть"], в["виден"]))
    for сел, имя in ОСТАЁТСЯ_НА_ПУСТОМ:
        о.шаг("%s-остался-%s" % (метка, сел.split()[-1].lstrip(".")),
              (await pg.evaluate(ВИДЕН, сел))["виден"], имя)


async def _пройти_пустое(pg, о, ширина):
    await pg.goto(БАЗА + "/medkit", wait_until="networkidle")
    await pg.add_style_tag(content="html, * { scroll-behavior: auto !important }")
    await pg.wait_for_timeout(300)
    if not await _опустошить(pg, о):
        return

    # НАБРАННЫЙ ЗАПРОС ДО УДАЛЕНИЯ — он и есть ловушка обратного хода:
    # поле спрячется вместе с текстом, а текст в нём останется
    await pg.fill("#apt-q", "нурофен")
    await pg.dispatch_event("#apt-q", "input")
    await pg.wait_for_timeout(200)
    остался_запрос = await pg.evaluate("document.getElementById('apt-q').value")

    ид = await pg.evaluate(
        "() => { const к = document.querySelector('.apt-card');"
        " return к ? к.dataset.id : null; }")
    await pg.evaluate("(id) => window.аптСпросить(id)", ид)
    await pg.wait_for_timeout(300)
    await pg.evaluate("window.аптУдалить()")
    await pg.wait_for_timeout(900)

    карточек = await pg.evaluate("document.querySelectorAll('.apt-card').length")
    о.шаг("последняя-удалилась", карточек == 0, "карточек %d" % карточек)
    о.шаг("приглашение-показано",
          (await pg.evaluate(ВИДЕН, "#apt-empty-all"))["виден"],
          "без перезагрузки страницы")
    await _пустой_экран(pg, о, "после-удаления")

    поле = await pg.evaluate("document.getElementById('apt-q').value")
    # ОТБОР ЧИТАЕТСЯ С ЭКРАНА, а не из переменной скрипта: `АПТ` объявлен
    # через `const` и на `window` не лежит (замер выше, у подлога
    # удаления). Подсвеченный чип — это к тому же то, что ВИДИТ человек,
    # а внутреннее поле могло бы с ним разойтись
    отбор = await pg.evaluate(
        "() => { const ч = document.querySelector('#apt-chips .chip.active');"
        " return ч ? ч.dataset.pick : null; }")
    о.шаг("запрос-сброшен", поле == "",
          "до удаления в поле было %r, стало %r" % (остался_запрос, поле))
    о.шаг("отбор-сброшен", отбор == "all", "отбор %r" % отбор)

    # ПЕРЕЗАГРУЗКА ДАЁТ ТО ЖЕ САМОЕ. Иначе «пусто» жило бы только
    # в скрипте, первый кадр приезжал бы с поиском и чипами
    # и перерисовывался на глазах (§6.0.15)
    await pg.reload(wait_until="networkidle")
    await pg.wait_for_timeout(300)
    await _пустой_экран(pg, о, "первый-кадр")

    # ── ОБРАТНЫЙ ХОД: завели первую позицию ──────────────────────────
    ж = await pg.evaluate(ЖИВОЙ, ".apt-empty .btn-primary")
    о.шаг("кнопка-приглашения-живая", ж.get("живой"), ж.get("причина", ""))
    await pg.click(".apt-empty .btn-primary")
    await pg.wait_for_timeout(400)
    о.шаг("форма-открылась-с-пустого", await pg.evaluate(ОТКРЫТО, "apt-form"))
    имя = "Первая-%d" % int(time.time())
    await pg.fill("#apt-f-name", имя)
    await pg.fill("#apt-f-exp", "2028-06")
    await pg.fill("#apt-f-left", "10")
    await pg.fill("#apt-f-total", "20")
    await pg.fill("#apt-f-dose", "1")
    await pg.click("#apt-save")
    await pg.wait_for_timeout(1100)

    карточек = await pg.evaluate("document.querySelectorAll('.apt-card').length")
    видно = await pg.evaluate(
        "document.querySelectorAll('.apt-card:not([hidden])').length")
    о.шаг("первая-позиция-появилась", карточек == 1, "карточек %d" % карточек)
    # ГЛАВНОЕ: она ВИДНА. Переживи запрос опустошение — карточка была бы
    # в дереве и спрятана поиском, то есть экран показывал бы пустоту
    # при заведённой позиции
    о.шаг("первая-позиция-видна", видно == 1,
          "видно %d из %d — не скрыта прежним запросом" % (видно, карточек))
    for сел, имя_ч in ПРЯЧЕТСЯ_НА_ПУСТОМ:
        о.шаг("вернулся-%s" % сел.lstrip("."),
              (await pg.evaluate(ВИДЕН, сел))["виден"], имя_ч)


async def прогон_пустого(ширина, отчёт, подлог=None):
    from playwright.async_api import async_playwright
    сенсор = ширина < 800
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context(
            viewport={"width": ширина, "height": 900 if not сенсор else 844},
            has_touch=сенсор, is_mobile=сенсор, device_scale_factor=1)
        if подлог:
            await ctx.add_init_script(ПОДЛОГИ_ПУСТОГО[подлог][0])
        pg = await ctx.new_page()
        pg.on("pageerror", lambda e: отчёт.шаг(
            "консоль-без-ошибок", False, str(e)[:120]))
        await _войти(pg)
        try:
            await _пройти_пустое(pg, отчёт, ширина)
        finally:
            await ctx.close()
            await b.close()


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ширина", type=int, default=1440)
    ap.add_argument("--контроль", action="store_true")
    ap.add_argument("--пустое", action="store_true",
                    help="проход ПУСТОГО экрана и обратного перехода. "
                         "ОПУСТОШАЕТ аптечку — после него пересейте стенд")
    a = ap.parse_args()

    print("=" * 74)
    print("АПТЕЧКА НАСКВОЗЬ — проход §6.3, ширина %d" % a.ширина)
    print("=" * 74)

    if a.пустое:
        # РЕЖИМ ОПУСТОШАЕТ АПТЕЧКУ. Говорится ДО прогона, а не после:
        # прочитанное после того, как данные уже стёрты, предупреждением
        # не является
        print()
        print("ВНИМАНИЕ: режим ОПУСТОШАЕТ аптечку стенда — иначе пустой")
        print("экран не увидеть. После прогона: py make_local_user.py --seed")
        if not a.контроль:
            о = Отчёт()
            await прогон_пустого(a.ширина, о)
            убрано = _убрать_пробы()
            print()
            print("шагов %d, плохих %d; пробных позиций убрано %d"
                  % (len(о.шаги), len(о.плохих), убрано))
            print("СТЕНД ОПУСТОШЁН — пересейте: py make_local_user.py --seed")
            return 1 if о.плохих else 0

        # ЧИСТЫЙ ПРОГОН ПЕРЕД ПОДЛОГАМИ — то же требование, что у общего
        # прохода: находка, бывшая и до подлога, засчиталась бы как
        # находка подлога
        print()
        print("ЧИСТЫЙ ПРОГОН — обязателен ПЕРЕД подлогами.")
        чисто = Отчёт()
        await прогон_пустого(a.ширина, чисто)
        _убрать_пробы()
        if чисто.плохих:
            print()
            print("ОСТАНОВЛЕНО: на чистом коде уже есть находки — "
                  "контроль на грязной основе недействителен")
            return 2
        нашли = 0
        for имя, (_, ждём) in ПОДЛОГИ_ПУСТОГО.items():
            print()
            print("── ПОДЛОГ «%s»: ждём находку на шаге «%s» ──" % (имя, ждём))
            о = Отчёт()
            try:
                await прогон_пустого(a.ширина, о, подлог=имя)
            except Exception as e:
                print("   прогон оборвался: %s: %s"
                      % (type(e).__name__, str(e)[:120]))
            _убрать_пробы()
            плохие = {ш[0] for ш in о.плохих}
            if ждём in плохие:
                print("   НАЙДЕН: шаг «%s» назвал подлог" % ждём)
                нашли += 1
            else:
                print("   НЕ НАЙДЕН: шаг «%s» промолчал. Плохих шагов: %s"
                      % (ждём, sorted(плохие) or "ни одного"))
        print()
        print("КОНТРОЛЬ ПУСТОГО: найдено %d из %d"
              % (нашли, len(ПОДЛОГИ_ПУСТОГО)))
        print("СТЕНД ОПУСТОШЁН — пересейте: py make_local_user.py --seed")
        return 0 if нашли == len(ПОДЛОГИ_ПУСТОГО) else 1

    if not a.контроль:
        о = Отчёт()
        await прогон(a.ширина, о)
        убрано = _убрать_пробы()
        print()
        print(f"шагов {len(о.шаги)}, плохих {len(о.плохих)}; "
              f"пробных позиций убрано {убрано}")
        return 1 if о.плохих else 0

    # ── ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ ───────────────────────────────────────
    print()
    print("ЧИСТЫЙ ПРОГОН — обязателен ПЕРЕД подлогами: находка, бывшая")
    print("и до подлога, засчиталась бы как находка подлога.")
    чисто = Отчёт()
    await прогон(a.ширина, чисто)
    _убрать_пробы()
    if чисто.плохих:
        print()
        print("ОСТАНОВЛЕНО: на чистом коде уже есть находки — "
              "контроль на грязной основе недействителен")
        return 2

    нашли = 0
    for имя, (_, ждём) in ПОДЛОГИ.items():
        print()
        print(f"── ПОДЛОГ «{имя}»: ждём находку на шаге «{ждём}» ──")
        о = Отчёт()
        try:
            await прогон(a.ширина, о, подлог=имя)
        except Exception as e:
            print(f"   прогон оборвался: {type(e).__name__}: {str(e)[:120]}")
        _убрать_пробы()
        плохие = {ш[0] for ш in о.плохих}
        if ждём in плохие:
            print(f"   НАЙДЕН: шаг «{ждём}» назвал подлог")
            нашли += 1
        else:
            print(f"   НЕ НАЙДЕН: шаг «{ждём}» промолчал. "
                  f"Плохих шагов: {sorted(плохие) or 'ни одного'}")
    print()
    print(f"КОНТРОЛЬ: найдено {нашли} из {len(ПОДЛОГИ)}")
    return 0 if нашли == len(ПОДЛОГИ) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
