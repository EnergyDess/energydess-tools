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
        # Удаление без вопроса: окно подтверждения не открывается
        "window.addEventListener('load', () => {"
        "  window.аптСпросить = function (id) {"
        "    window.АПТ.удаляем = id; window.аптУдалить(); }; });",
        "удаление-спрашивает"),
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


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ширина", type=int, default=1440)
    ap.add_argument("--контроль", action="store_true")
    a = ap.parse_args()

    print("=" * 74)
    print("АПТЕЧКА НАСКВОЗЬ — проход §6.3, ширина %d" % a.ширина)
    print("=" * 74)

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
