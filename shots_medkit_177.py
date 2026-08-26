"""СНИМКИ ЗАХОДА 177 — ДЛЯ ПРИЁМКИ ВЛАДЕЛЬЦЕМ.

НЕ ПРОВЕРКА: кода «правильно» у неё нет, кадры смотрит человек.
Код возврата всегда 0.

Что снимается — ровно то, что просила постановка:

  1. окно способа приёма во ВСЕХ ЧЕТЫРЁХ состояниях;
  2. лента переписки со снимком — включая ПОВТОР после сбоя,
     то есть тот путь, где превью и терялось (C.2);
  3. карточка ответа ассистента с кнопкой «Приём» у ВСЕЙ кучи (C.3);
  4. подвал — до и после правки запаса (C.4).

ШИРИНЫ 2560 И 390 — их назвал владелец; 1440 среди них нет намеренно,
экрана такой ширины у него не существует (тот же довод, что у задач
143 и 176).

═══════════════════════════════════════════════════════════════════════
ОТВЕТ АССИСТЕНТА РИСУЕТСЯ ПО ПОДСТАВЛЕННОМУ ТЕЛУ, И ЭТО НАЗВАНО

Живой ответ модели стоит токенов и НЕ ВОСПРОИЗВОДИТСЯ: два прогона
дают разные наборы позиций, а вопрос кадра — «есть ли кнопка у всех
строк», а не «что ответила модель». Рисует кадр НАСТОЯЩАЯ `аптАИОтвет`
тем же путём, что и на бою; подставлено только ТЕЛО ОТВЕТА.

Живьём ответ ассистента снимает `check_medkit_query.py` — там он
и должен сниматься живым.

    py shots_medkit_177.py            # обе ширины
    py shots_medkit_177.py --ширина 390
"""

import argparse
import asyncio
import io
import os
import pathlib
import sys

БАЗА = os.environ.get("HOVER_BASE", "http://127.0.0.1:8899")
ПОЧТА = "screenshot@local.dev"
ПАРОЛЬ = "Screenshot-Local-2026"
КУДА = pathlib.Path(os.environ.get("SHOTS_DIR", "C:/Temp/claude/shots177"))
ШИРИНЫ = [2560, 390]

# Кадр РАЗМЕРА КАМЕРЫ, а не нарисованный маленький: путь уменьшения
# на больших кадрах другой (§5.8, «приёмка ходила не той веткой»)
def _кадр_камеры():
    from PIL import Image
    буфер = io.BytesIO()
    Image.new("RGB", (4000, 3000), (188, 182, 170)).save(буфер, "JPEG", quality=80)
    путь = КУДА / "upakovka.jpg"
    путь.write_bytes(буфер.getvalue())
    return str(путь)


ОТВЕТ_АССИСТЕНТА = {
    "вид": "запрос",
    "вступление": "В вашей аптечке есть несколько средств для ЖКТ.",
    "нашлось": [
        {"id": None, "строка": "Смекта · Диосмектит, 3 г · Порошок · 3 из 10 · до 01.2026"},
        {"id": None, "строка": "Полисорб · Кремния диоксид · Порошок · 25 из 50 · до 07.2028"},
        {"id": None, "строка": "Уголь активированный · 250 мг · Таблетки · 40 из 50 · до 04.2027"},
        {"id": None, "строка": "Регидрон · Декстроза + соли · Пакетики · 11 из 20 · до 09.2028"},
    ],
}


async def _войти(pg):
    await pg.goto(БАЗА + "/login", wait_until="domcontentloaded")
    await pg.fill("input[name=email]", ПОЧТА)
    await pg.fill("input[name=password]", ПАРОЛЬ)
    if await pg.query_selector(".cf-turnstile"):
        for _ in range(60):
            if await pg.evaluate("() => { const t = document.querySelector("
                                 "'[name=\"cf-turnstile-response\"]'); "
                                 "return t && t.value; }"):
                break
            await pg.wait_for_timeout(500)
    await pg.click("button[type=submit]")
    await pg.wait_for_load_state("networkidle")
    if "/login" in pg.url:
        raise SystemExit("ВХОД НЕ СОСТОЯЛСЯ — снимать нечего")


async def _снять(pg, имя, ширина, селектор=None):
    КУДА.mkdir(parents=True, exist_ok=True)
    путь = КУДА / f"{имя}-{ширина}.png"
    цель = await pg.query_selector(селектор) if селектор else None
    if селектор and not цель:
        print("   ПРОПУЩЕН %s — нет %s" % (имя, селектор))
        return
    if цель:
        await цель.screenshot(path=str(путь), animations="disabled")
    else:
        await pg.screenshot(path=str(путь), animations="disabled")
    print("   %s" % путь.name)


async def окно_приёма(pg, ширина):
    """Четыре состояния окна способа приёма."""
    await pg.goto(БАЗА + "/medkit", wait_until="networkidle")
    await pg.wait_for_timeout(500)

    # ── 1/2 · ВЫДЕРЖКА С ВЫДЕЛЕННЫМИ СТРОКАМИ СХЕМЫ ─────────────────
    #
    # ПОЗИЦИЯ ВЫБИРАЕТСЯ ПО ПРИЗНАКУ, а не по номеру: первая карточка
    # сегодня одна, завтра другая, и кадр молча снял бы не то состояние
    id_выд = await pg.evaluate(
        "() => (АПТ_ПОЗИЦИИ.find(x => (x['дозы'] || '').length > 800) || {}).id")
    if id_выд:
        await pg.evaluate("(i) => аптДозыОткрыть(i)", id_выд)
        await pg.wait_for_timeout(500)
        await _снять(pg, "1-выдержка-со-схемой", ширина, "#apt-doses .modal-sh")
        await pg.evaluate("() => { const к = document.querySelector"
                          "('.apt-dose-more'); к && к.click(); }")
        await pg.wait_for_timeout(400)
        await _снять(pg, "2-выдержка-раскрыта", ширина, "#apt-doses .modal-sh")
        await pg.keyboard.press("Escape")
        await pg.wait_for_timeout(300)

    # ── 3 · СПРАВОЧНИК НИЧЕГО НЕ ДАЛ, ПРИЧИНА СРАЗУ ─────────────────
    id_нет = await pg.evaluate(
        "() => (АПТ_ПОЗИЦИИ.find(x => !x['дозы'] && !x['своя_схема']) || {}).id")
    if not id_нет:
        return
    # ПРИЧИНУ ЗАПРАШИВАЕМ БОЕВЫМ ПУТЁМ — кнопкой окна, а не подстановкой
    # в базу: кадр обязан показывать то, что увидит человек
    await pg.evaluate("(i) => аптДозыОткрыть(i)", id_нет)
    await pg.wait_for_timeout(400)
    await pg.evaluate("""() => { const к = [...document.querySelectorAll(
        '#apt-doses-body button')].find(b => /справочник/i.test(b.textContent));
        к && к.click(); }""")
    await pg.wait_for_timeout(9000)
    await _снять(pg, "3-схемы-нет-причина-сразу", ширина, "#apt-doses .modal-sh")

    # ── 4a · ФОРМА СВОЕЙ СХЕМЫ ──────────────────────────────────────
    await pg.evaluate("""() => { const к = [...document.querySelectorAll(
        '#apt-doses-body button')].find(b => /Вписать/i.test(b.textContent));
        к && к.click(); }""")
    await pg.wait_for_timeout(400)
    await pg.evaluate("""() => { const п = document.getElementById('apt-own-in');
        if (п) п.value = 'По 1 капсуле 2 раза в день во время еды, курс 30 дней'; }""")
    await pg.wait_for_timeout(200)
    await _снять(pg, "4a-вписываю-сам", ширина, "#apt-doses .modal-sh")

    # ── 4b · СВОЯ ЗАПИСЬ СОХРАНЕНА ──────────────────────────────────
    await pg.evaluate("""() => { const к = [...document.querySelectorAll(
        '#apt-doses-body button')].find(b => b.textContent.trim() === 'Сохранить');
        к && к.click(); }""")
    await pg.wait_for_timeout(1200)
    await _снять(pg, "4b-своя-схема-сохранена", ширина, "#apt-doses .modal-sh")
    await pg.keyboard.press("Escape")
    await pg.wait_for_timeout(300)

    # ── 4в · СВОЯ ЗАПИСЬ И ВЫДЕРЖКА РЯДОМ (A.2) ─────────────────────
    if id_выд:
        await pg.evaluate("""async (i) => {
          await fetch('/medkit/api/items/' + i + '/own-dosage', {method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({'текст':
              'С пачки: по 1 таблетке вечером, запивая водой'})});
        }""", id_выд)
        await pg.reload(wait_until="networkidle")
        await pg.wait_for_timeout(500)
        await pg.evaluate("(i) => аптДозыОткрыть(i)", id_выд)
        await pg.wait_for_timeout(500)
        await _снять(pg, "4в-своя-и-выдержка-рядом", ширина, "#apt-doses .modal-sh")
        await pg.keyboard.press("Escape")


async def лента_с_фото(pg, ширина, файл):
    """C.2: превью снимка в ленте, включая ПОВТОР после сбоя."""
    await pg.goto(БАЗА + "/medkit", wait_until="networkidle")
    await pg.click("#apt-ai-open")
    await pg.wait_for_timeout(500)
    await pg.set_input_files("#apt-ai-photo", файл)
    await pg.wait_for_timeout(3500)
    await _снять(pg, "5-лента-снимок", ширина, ".apt-ai")
    # ПОВТОР — тот самый путь, где превью терялось. Сбой подделан
    # отказом сети на эндпоинте: путь кода при этом боевой
    есть = await pg.query_selector(".apt-ai-again button")
    if есть:
        await есть.click()
        await pg.wait_for_timeout(3000)
        await _снять(pg, "6-лента-после-повтора", ширина, ".apt-ai")


async def ответ_ассистента(pg, ширина):
    """C.3: кнопка «Приём» у ВСЕЙ кучи, а не у одной строки."""
    await pg.goto(БАЗА + "/medkit", wait_until="networkidle")
    await pg.click("#apt-ai-open")
    await pg.wait_for_timeout(500)
    await pg.evaluate("""(тело) => {
      // Настоящие id со стенда — чтобы кнопки открывали настоящие окна
      const годные = АПТ_ПОЗИЦИИ.filter(п => п['состояние'] !== 'expired'
                                          && !п['is_rx']).slice(0, 4);
      тело['нашлось'].forEach((с, i) => {
        if (годные[i]) { с['id'] = годные[i].id; с['строка'] = годные[i]['строка_поиска']
          ? с['строка'] : с['строка']; }
      });
      тело['нашлось'] = тело['нашлось'].filter(с => с['id'] != null);
      аптАИОтвет(тело);
    }""", ОТВЕТ_АССИСТЕНТА)
    await pg.wait_for_timeout(600)
    await _снять(pg, "7-ответ-ассистента-кнопки", ширина, ".apt-ai")


async def подвал(pg, ширина, метка):
    """C.4: запас над подвалом. Снимается НА ДВУХ СТЕНДАХ одной командой."""
    await pg.goto(БАЗА + "/medkit", wait_until="networkidle")
    await pg.wait_for_timeout(400)
    # ДО САМОГО НИЗА ДОКУМЕНТА, а не `scrollIntoView` у подвала: страница
    # аптечки длиннее четырёх экранов, и «прокрутить к элементу» ставит
    # его нижний край за границу окна — в кадр попадала сетка карточек,
    # а не то, что снимают
    await pg.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
    await pg.wait_for_timeout(500)
    await _снять(pg, "8-подвал-" + метка, ширина)


async def main():
    from playwright.async_api import async_playwright
    р = argparse.ArgumentParser(description=__doc__)
    р.add_argument("--ширина", type=int, default=None)
    р.add_argument("--метка", default="после",
                   help="подпись кадра подвала: «до» или «после»")
    а = р.parse_args()
    ширины = [а.ширина] if а.ширина else ШИРИНЫ

    КУДА.mkdir(parents=True, exist_ok=True)
    файл = _кадр_камеры()
    print("снимки: %s\nстенд:  %s" % (КУДА, БАЗА))
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for ш in ширины:
            сенсор = ш < 800
            ctx = await b.new_context(
                viewport={"width": ш, "height": 900 if not сенсор else 844},
                has_touch=сенсор, is_mobile=сенсор, device_scale_factor=1)
            pg = await ctx.new_page()
            await _войти(pg)
            print("── ширина %d ──" % ш)
            await подвал(pg, ш, а.метка)
            # Своя схема чистится ПЕРЕД съёмкой: иначе кадр «вписываю
            # сам» снимался бы поверх прошлого прогона
            await pg.evaluate("""async () => {
              for (const п of АПТ_ПОЗИЦИИ)
                if (п['своя_схема'])
                  await fetch('/medkit/api/items/' + п.id + '/own-dosage',
                    {method: 'POST', headers: {'Content-Type': 'application/json'},
                     body: JSON.stringify({'текст': ''})});
            }""")
            await окно_приёма(pg, ш)
            await ctx.route("**/medkit/api/assist", lambda r: r.abort())
            await лента_с_фото(pg, ш, файл)
            await ответ_ассистента(pg, ш)
            await ctx.close()
        await b.close()
    # КОД ВОЗВРАТА ВСЕГДА 0 — кадры смотрит человек
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
