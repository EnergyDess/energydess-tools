# -*- coding: utf-8 -*-
"""СКОЛЬКО БАЙТ УХОДИТ НА САМОМ ДЕЛЕ — замер живым браузером.

ЧЕМ ЭТО ОТЛИЧАЕТСЯ ОТ `check_upload_paths`. Та читает ТЕКСТ кода
и отвечает «вызов уменьшения на пути есть». Здесь спрашивается другое:
СКОЛЬКО БАЙТ ФАКТИЧЕСКИ УШЛО ПО СЕТИ. Вызов, который стоит на месте
и ничего не уменьшает (формат браузеру незнаком, канвас пуст, потолок
задан больше кадра), статическая опись пропускает по построению.

ЗАЧЕМ ИМЕННО ТАК. Приёмка ассистента аптечки была зелёной на кадре
900x560 в 28 КБ, а владелец с телефона получал 502: камера отдаёт
12–108 Мпикс, и это РАЗНЫЕ ВЕТКИ КОДА. Здесь подаётся файл размера
настоящей камеры и меряется то единственное, что отличает «ужали»
от «протащили мимо ужатия молча».

ПУТИ. Оба, которыми владелец грузит снимок в аптечку:

  панель    `/medkit/api/assist` — снять упаковку в разговоре
            с ассистентом. Уменьшение тут стояло с 2026-08-25;
  форма     `/medkit/api/items/{id}/photo` — приложить фото к карточке.
            Уменьшения НЕ БЫЛО, и владелец получил 502 именно отсюда.

ЗАПУСК
    py -m uvicorn main:app --port 8899
    py check_upload_bytes.py
    py check_upload_bytes.py --контроль

Порог назван числом и выведен из потолка сервиса моделей: картинка
свыше `VISION_IMAGE_MAX_MB` (5 МБ) — гарантированный отказ, а не
«может, повезёт» (§2.1). Берём с запасом: ужатый кадр 1920 по длинной
стороне весит меньше мегабайта.
"""

import asyncio
import io
import os
import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

БАЗА = os.environ.get("MEDKIT_BASE", "http://127.0.0.1:8899")
ПОЧТА = "screenshot@local.dev"
ПАРОЛЬ = "Screenshot-Local-2026"
DB = os.environ.get("DB_PATH", "app.db")

МЕТКА = "ПРОБА-БАЙТЫ"
ПОРОГ_КБ = 2048          # ужатый кадр 1920 не дотягивает и до мегабайта


def _кадр(мпикс=12):
    """Кадр РАЗМЕРА КАМЕРЫ: шум, а не заливка.

    Заливка одним цветом жмётся в килобайты и превращает пробу
    в проверку того, что JPEG умеет сжимать однотонное. Камера отдаёт
    шум, и вес у неё соответствующий.
    """
    import random
    from PIL import Image
    ш = int((мпикс * 1e6 * 4 / 3) ** 0.5)
    в = int(ш * 3 / 4)
    случ = random.Random(20260825)
    img = Image.new("RGB", (ш, в))
    # Пиксельный шум крупными блоками: попиксельно 12 Мпикс рисуются
    # минутами, а JPEG всё равно смотрит на блоки 8x8
    блок = 8
    пикс = img.load()
    for y in range(0, в, блок):
        for x in range(0, ш, блок):
            ц = (случ.randrange(256), случ.randrange(256), случ.randrange(256))
            for dy in range(min(блок, в - y)):
                for dx in range(min(блок, ш - x)):
                    пикс[x + dx, y + dy] = ц
    буфер = io.BytesIO()
    img.save(буфер, "JPEG", quality=92)
    return буфер.getvalue(), ш, в


def _в_базе(запрос, параметры=()):
    conn = sqlite3.connect(DB)
    try:
        return conn.execute(запрос, параметры).fetchall()
    finally:
        conn.close()


def _убрать_пробы():
    conn = sqlite3.connect(DB)
    try:
        ids = [r[0] for r in conn.execute(
            "SELECT id FROM medkit_items WHERE name LIKE ?", (МЕТКА + "%",))]
        for i in ids:
            conn.execute("DELETE FROM medkit_item_categories WHERE item_id=?", (i,))
        conn.execute("DELETE FROM medkit_items WHERE name LIKE ?", (МЕТКА + "%",))
        conn.commit()
        return len(ids)
    finally:
        conn.close()


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


class Ловец:
    """Размер тела запроса, ушедшего на адрес.

    Слушателем, а не перехватом маршрута: перехват сам меняет поведение
    страницы (замерено на переходах между документами, §6.0.16).

    РАЗМЕР БЕРЁТСЯ ИЗ `Content-Length`, А НЕ ИЗ ТЕЛА. Замер 2026-08-25:
    `post_data_buffer` у multipart с файлом отдаёт `None` — Playwright
    такое тело наружу не выносит. Проба, читавшая его, печатала
    «запрос не пойман» на обоих путях и была неотличима от пробы,
    промахнувшейся мимо страницы.
    """

    def __init__(self, pg):
        self.поймано = []
        pg.on("request", self._на_запрос)

    def _на_запрос(self, req):
        if req.method == "POST":
            self.поймано.append(req)

    def clear(self):
        self.поймано.clear()

    async def найти(self, кусок):
        """`all_headers()` асинхронный, и это не придирка: синхронное
        `headers` отдаёт лишь часть заголовков, `content-length` среди
        них нет, и первая версия пробы печатала «запрос не пойман»
        на обоих исправных путях."""
        for req in self.поймано:
            if кусок not in req.url:
                continue
            try:
                h = await req.all_headers()
            except Exception:
                continue
            длина = h.get("content-length")
            if длина and длина.isdigit():
                return int(длина)
        return None


async def замер(pg, ловец, о, кадр, ш, в):
    """Оба пути аптечки одним и тем же файлом."""
    исходный_кб = len(кадр) / 1024
    файл = {"name": "IMG_20260825.jpg", "mimeType": "image/jpeg",
            "buffer": кадр}

    # ── ПУТЬ 1: панель ассистента ────────────────────────────────────
    await pg.goto(БАЗА + "/medkit", wait_until="networkidle")
    ловец.clear()
    await pg.evaluate("() => аптАИОткрыть && аптАИОткрыть()")
    await pg.wait_for_timeout(300)
    поле = await pg.query_selector("#apt-ai-photo")
    if not поле:
        о("панель", исходный_кб, None, "поля выбора файла нет на экране")
    else:
        await поле.set_input_files(файл)
        await pg.wait_for_timeout(6000)
        о("панель", исходный_кб, await ловец.найти("/medkit/api/assist"), "")

    # ── ПУТЬ 2: форма карточки ───────────────────────────────────────
    await pg.goto(БАЗА + "/medkit", wait_until="networkidle")
    ловец.clear()
    имя = МЕТКА + "-форма"
    await pg.evaluate("() => аптОткрытьФорму()")
    await pg.fill("#apt-f-name", имя)
    await pg.select_option("#apt-f-form", "tablet")
    await pg.fill("#apt-f-exp", "2027-06")
    await pg.fill("#apt-f-left", "10")
    await pg.fill("#apt-f-total", "10")
    await pg.fill("#apt-f-dose", "1")
    await pg.set_input_files("#apt-f-photo", файл)
    await pg.wait_for_timeout(500)
    await pg.click("#apt-save")
    await pg.wait_for_timeout(8000)
    о("форма", исходный_кб, await ловец.найти("/photo"), "")


async def прогон(мпикс=12):
    from playwright.async_api import async_playwright

    _убрать_пробы()
    кадр, ш, в = _кадр(мпикс)
    print("Кадр камеры: %dx%d, %.1f Мпикс, %.0f КБ"
          % (ш, в, ш * в / 1e6, len(кадр) / 1024))
    print("Порог: ушедшее тело запроса не больше %d КБ" % ПОРОГ_КБ)
    print()
    строки = []

    def о(путь, было_кб, ушло, что):
        строки.append((путь, было_кб, ушло, что))

    async with async_playwright() as p:
        br = await p.chromium.launch()
        ctx = await br.new_context(viewport={"width": 1440, "height": 900})
        pg = await ctx.new_page()
        ловец = Ловец(pg)
        await _войти(pg)
        await замер(pg, ловец, о, кадр, ш, в)
        await br.close()

    print("%-10s %12s %14s %10s  %s"
          % ("путь", "файл КБ", "ушло КБ", "сжатие", "итог"))
    print("-" * 66)
    беды = 0
    for путь, было_кб, ушло, что in строки:
        if ушло is None:
            вердикт = "НЕ ЗАМЕРЕНО — " + (что or "запрос не пойман")
            беды += 1
            print("%-10s %12.0f %14s %10s  %s"
                  % (путь, было_кб, "—", "—", вердикт))
            continue
        ушло_кб = ушло / 1024
        доля = было_кб / ушло_кб if ушло_кб else 0
        ок = ушло_кб <= ПОРОГ_КБ
        беды += 0 if ок else 1
        print("%-10s %12.0f %14.0f %9.1fx  %s"
              % (путь, было_кб, ушло_кб, доля,
                 "OK" if ок else "ПЛОХО — ушёл оригинал"))
    _убрать_пробы()
    print()
    print("Путей выше порога: %d из %d" % (беды, len(строки)))
    return 1 if беды else 0


async def доказать_подлог(pg):
    """НЕЗАВИСИМЫЙ ЗАМЕР ТОГО, ЧТО ПОДЛОГ СОБИРАЛСЯ ИЗМЕНИТЬ (§6.0.3).

    Подмена `уменьшитьФото` обязана вернуть ОРИГИНАЛ. Без этого замера
    «ушёл оригинал» неотличимо от «проба промахнулась мимо страницы»:
    вердикт был бы один и тот же.
    """
    return await pg.evaluate("""async () => {
      const б = new Blob([new Uint8Array(1000)], {type: 'image/jpeg'});
      const ф = new File([б], 'x.jpg', {type: 'image/jpeg'});
      const и = await уменьшитьФото(ф, 1920, 0.85);
      return и['какОригинал'] === true && и.сталоБайт === ф.size;
    }""")


async def контроль():
    """ПОДЛОГ ДОКАЗЫВАЕТСЯ ОТДЕЛЬНЫМ ЗАМЕРОМ (§6.0.3).

    Снимаем уменьшение с пути ФОРМЫ прямо в странице и требуем, чтобы
    замер это увидел. Доказательство подлога — независимая проверка
    того, что подмена встала: `уменьшитьФото` возвращает оригинал.
    """
    from playwright.async_api import async_playwright

    _убрать_пробы()
    кадр, ш, в = _кадр(12)
    ПОДЛОГ = """
    () => {
      window.уменьшитьФото = (файл) => Promise.resolve(
        {blob: файл, dataUrl: null, 'какОригинал': true,
         былоБайт: файл.size, сталоБайт: файл.size});
    }
    """
    async with async_playwright() as p:
        br = await p.chromium.launch()
        ctx = await br.new_context(viewport={"width": 1440, "height": 900})
        pg = await ctx.new_page()
        ловец = Ловец(pg)
        await _войти(pg)
        await pg.goto(БАЗА + "/medkit", wait_until="networkidle")
        await pg.evaluate(ПОДЛОГ)

        # ДОКАЗАТЕЛЬСТВО: подмена действительно встала и возвращает
        # оригинал. Без него «ушёл оригинал» неотличимо от «проба
        # промахнулась мимо страницы»
        доказано = await доказать_подлог(pg)
        print("ДОКАЗАТЕЛЬСТВО подлога: уменьшение возвращает оригинал — %s"
              % ("да" if доказано else "НЕТ"))
        if not доказано:
            await br.close()
            print("ПОДЛОГ НЕ СОСТОЯЛСЯ — ломать было нечего")
            return 1

        ловец.clear()
        имя = МЕТКА + "-контроль"
        await pg.evaluate("() => аптОткрытьФорму()")
        await pg.fill("#apt-f-name", имя)
        await pg.select_option("#apt-f-form", "tablet")
        await pg.fill("#apt-f-exp", "2027-06")
        await pg.fill("#apt-f-left", "10")
        await pg.fill("#apt-f-total", "10")
        await pg.fill("#apt-f-dose", "1")
        await pg.set_input_files("#apt-f-photo",
                                 {"name": "IMG.jpg", "mimeType": "image/jpeg",
                                  "buffer": кадр})
        await pg.wait_for_timeout(500)
        await pg.click("#apt-save")
        await pg.wait_for_timeout(8000)
        ушло = await ловец.найти("/photo")
        await br.close()

    _убрать_пробы()
    if ушло is None:
        print("  ПЛОХО  запрос не пойман — проба не отвечает ни на что")
        return 1
    ушло_кб = ушло / 1024
    нашла = ушло_кб > ПОРОГ_КБ
    print(("   OK   " if нашла else "  ПЛОХО ")
          + "подлог «форма шлёт оригинал»: ушло %.0f КБ при пороге %d"
          % (ушло_кб, ПОРОГ_КБ))
    return 0 if нашла else 1


def main():
    if "--контроль" in sys.argv:
        return asyncio.run(контроль())
    мпикс = 12
    for i, а in enumerate(sys.argv):
        if а == "--мпикс" and i + 1 < len(sys.argv):
            мпикс = float(sys.argv[i + 1])
    return asyncio.run(прогон(мпикс))


if __name__ == "__main__":
    sys.exit(main())
