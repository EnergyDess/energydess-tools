# -*- coding: utf-8 -*-
"""ДУБЛЬ ПРИ ПОВТОРНОМ СОХРАНЕНИИ — четыре пути, каждый насквозь (§6.3).

ЗАЧЕМ. Владелец завёл позицию с телефона: карточка сохранилась, фото
упало с 502, он убрал фото и нажал «Сохранить» ещё раз — и получил ДВЕ
записи. Подтверждено его же замером: списание на одной карточке дало
12 из 20, на второй осталось 13 из 20. Это две строки в базе, а не одна
карточка, нарисованная дважды.

ЧТО СПРАШИВАЕТСЯ. Не «ответил ли сервер 200», а СКОЛЬКО СТРОК ПОЯВИЛОСЬ
В БАЗЕ. Ответ сервера — его намерение; строки считает SELECT (§6.3,
«результат берётся С ЭКРАНА И ИЗ БАЗЫ»).

ЧЕТЫРЕ ПУТИ — они РАЗНЫЕ, и общего у них только исход:

  сбой-фото     сохранение, фото упало, «Сохранить» ещё раз. Ровно путь
                владельца: форма остаётся открытой, и второе нажатие
                обязано ОБНОВИТЬ созданную позицию;
  правка-поля   то же, но между нажатиями человек поправил поле:
                проверяем, что правка ДОЕХАЛА, а не только что дубля нет;
  двойной-тап   три нажатия подряд без ожидания ответа. Здесь лечит
                не режим правки, а блокировка кнопки: к моменту второго
                нажатия id ещё не существует;
  назад-вперёд  сохранение, «назад» в браузере, возврат на страницу,
                форма, «Сохранить». Состояние вкладки СТЁРТО, и режим
                правки помочь не может по построению — две записи здесь
                ЗАКОННЫ, человек заполнил форму заново.

ПАДЕНИЕ ФОТО ПОДДЕЛЫВАЕТСЯ, И ЭТО НАЗВАНО. Заставить сервер отдать
настоящий 502 по требованию нечем, поэтому отправка фото перехватывается
В СТРАНИЦЕ: fetch на адрес /photo отвечает отказом. Путь кода при этом
тот же самый — аптСохранить получает отказ ровно в той точке, где
получил бы его от прода.

ЗАПУСК
    py -m uvicorn main:app --port 8899
    py check_medkit_dupe.py

НЕ ПРОВЕРКА РЯДА: нужен браузер, нужно поднятое приложение, и она ПИШЕТ
в базу. Пробные позиции убирает за собой сама — мусор инструмента
приёмки читается как находка (§6.0.3, шестая причина неповторимости).
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

МЕТКА = "ПРОБА-ДУБЛЬ"


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


def _счёт(имя):
    return _в_базе("SELECT COUNT(*) FROM medkit_items WHERE name=?", (имя,))[0][0]


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


# Перехват отправки фото ВНУТРИ страницы: путь кода аптСохранить остаётся
# тем же, меняется только ответ на один адрес
СЛОМАТЬ_ФОТО = """
() => {
  const родной = window.fetch;
  window.fetch = function (адрес, наст) {
    const s = String(адрес || '');
    if (s.indexOf('/photo') >= 0 && (наст || {}).method === 'POST') {
      return Promise.resolve(new Response(
        JSON.stringify({error: 'подложенный отказ выгрузки'}),
        {status: 502, headers: {'Content-Type': 'application/json'}}));
    }
    return родной.apply(this, arguments);
  };
}
"""


async def _заполнить(pg, имя, срок="2027-06"):
    await pg.evaluate("() => аптОткрытьФорму()")
    await pg.fill("#apt-f-name", имя)
    await pg.select_option("#apt-f-form", "tablet")
    await pg.fill("#apt-f-exp", срок)
    await pg.fill("#apt-f-left", "20")
    await pg.fill("#apt-f-total", "20")
    await pg.fill("#apt-f-dose", "1")


async def _подложить_файл(pg):
    """Настоящий выбор файла: аптВыбралиФото кладёт его в АПТ.файл."""
    from PIL import Image
    буфер = io.BytesIO()
    Image.new("RGB", (320, 180), (40, 44, 60)).save(буфер, "PNG")
    await pg.set_input_files("#apt-f-photo",
                             {"name": "proba.png", "mimeType": "image/png",
                              "buffer": буфер.getvalue()})


class Отчёт:
    def __init__(self):
        self.строки = []

    def путь(self, имя, записей, ожидалось, что=""):
        ок = записей == ожидалось
        self.строки.append((имя, записей, ожидалось, ок, что))
        print(("   OK   " if ок else "  ПЛОХО ")
              + "%-14s записей в базе: %d (ожидалось %d)%s"
              % (имя, записей, ожидалось, ("  — " + что) if что else ""))

    @property
    def плохих(self):
        return [с for с in self.строки if not с[3]]


async def путь_сбой_фото(pg, о):
    """Сохранение, фото упало, «Сохранить» ещё раз."""
    имя = МЕТКА + "-сбой-фото"
    await pg.goto(БАЗА + "/medkit", wait_until="networkidle")
    await pg.evaluate(СЛОМАТЬ_ФОТО)
    await _заполнить(pg, имя)
    await _подложить_файл(pg)
    await pg.click("#apt-save")
    await pg.wait_for_timeout(1500)
    ошибка = await pg.evaluate(
        "() => { const e = document.getElementById('apt-form-err');"
        " return e.hidden ? '' : e.textContent; }")
    после_первого = _счёт(имя)
    # Второе нажатие — то самое, что владелец сделал вручную
    await pg.evaluate("() => аптУбратьФото()")
    await pg.wait_for_timeout(400)
    await pg.click("#apt-save")
    await pg.wait_for_timeout(1500)
    о.путь("сбой-фото", _счёт(имя), 1,
           "после 1-го сохранения было %d; текст ошибки: %s"
           % (после_первого, (ошибка or "НЕТ")[:70]))


async def путь_правка_поля(pg, о):
    """Сохранение, фото упало, правка поля, «Сохранить»."""
    имя = МЕТКА + "-правка"
    await pg.goto(БАЗА + "/medkit", wait_until="networkidle")
    await pg.evaluate(СЛОМАТЬ_ФОТО)
    await _заполнить(pg, имя)
    await _подложить_файл(pg)
    await pg.click("#apt-save")
    await pg.wait_for_timeout(1500)
    await pg.evaluate("() => аптУбратьФото()")
    await pg.wait_for_timeout(300)
    await pg.fill("#apt-f-left", "7")          # правка ПОСЛЕ первого сохранения
    await pg.click("#apt-save")
    await pg.wait_for_timeout(1500)
    строки = _в_базе("SELECT qty_left FROM medkit_items WHERE name=?", (имя,))
    остатки = ", ".join(str(r[0]) for r in строки)
    о.путь("правка-поля", len(строки), 1,
           "остаток в базе: [%s], ожидался 7" % остатки)


async def путь_двойной_тап(pg, о):
    """Три нажатия подряд без ожидания ответа."""
    имя = МЕТКА + "-двойной"
    await pg.goto(БАЗА + "/medkit", wait_until="networkidle")
    await _заполнить(pg, имя)
    # Все нажатия шлём ДО того, как первый запрос успеет вернуться
    await pg.evaluate("""() => {
      const b = document.getElementById('apt-save');
      b.click(); b.click(); b.click();
    }""")
    await pg.wait_for_timeout(2500)
    о.путь("двойной-тап", _счёт(имя), 1, "три нажатия подряд")


async def путь_назад_вперёд(pg, о):
    """Сохранение, «назад» в браузере, форма, «Сохранить»."""
    имя = МЕТКА + "-назад"
    await pg.goto(БАЗА + "/medkit", wait_until="networkidle")
    await _заполнить(pg, имя)
    await pg.click("#apt-save")
    await pg.wait_for_timeout(1500)
    после = _счёт(имя)
    await pg.goto(БАЗА + "/", wait_until="networkidle")
    await pg.go_back()
    await pg.wait_for_load_state("networkidle")
    await pg.wait_for_timeout(500)
    # На перезагруженной странице форма пуста — заполняем те же данные
    await _заполнить(pg, имя)
    await pg.click("#apt-save")
    await pg.wait_for_timeout(1500)
    о.путь("назад-вперёд", _счёт(имя), 2,
           "после первого было %d; ДВЕ записи здесь ЗАКОННЫ — состояние "
           "вкладки стёрто, человек заполнил форму заново" % после)


async def main():
    from playwright.async_api import async_playwright

    убрано = _убрать_пробы()
    if убрано:
        print("Убрано пробных позиций с прошлого прогона: %d" % убрано)

    о = Отчёт()
    async with async_playwright() as p:
        br = await p.chromium.launch()
        ctx = await br.new_context(viewport={"width": 1440, "height": 900})
        pg = await ctx.new_page()
        await _войти(pg)
        for проба in (путь_сбой_фото, путь_правка_поля,
                      путь_двойной_тап, путь_назад_вперёд):
            try:
                await проба(pg, о)
            except Exception as e:
                о.путь(проба.__name__, -1, -2, "проба упала: %r" % (e,))
        await br.close()

    print()
    осталось = _убрать_пробы()
    print("Пробные позиции убраны: %d" % осталось)
    print("Путей с неверным числом записей: %d из %d"
          % (len(о.плохих), len(о.строки)))
    return 1 if о.плохих else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
