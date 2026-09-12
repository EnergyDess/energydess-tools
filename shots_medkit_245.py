# -*- coding: utf-8 -*-
"""СНИМКИ ЗАХОДА 245: группы в ответе, второй ответ, ручные показания.

НЕ ПРОВЕРКА — кадры смотрит человек. Кода «правильно» тут нет.

ЧТО СНИМАЕТСЯ И ПОЧЕМУ ИМЕННО ЭТО:

  1. ОТВЕТ С ГРУППАМИ — то, ради чего заход. Прежний ответ на жалобу
     показывал две карточки из семидесяти семи, а всё остальное
     уезжало в кучу «дословно не сошлись»; теперь найденное разложено
     по смыслу показаний, у каждой группы имя и ДОСЛОВНАЯ цитата.
  2. ВТОРОЙ ОТВЕТ («что из этого выбрать») — прежде приходил тот же
     список второй раз, и владелец сказал про это прямо: «не понимаю,
     что поменялось». Кадр показывает, что карточек в нём НЕТ вовсе,
     а текст идёт двумя частями: сперва честное «выбрать за вас
     нельзя», потом различия.
  3. ОКНО СПОСОБА ПРИЁМА С ПОЛЕМ РУЧНЫХ ПОКАЗАНИЙ — блок D: до этого
     захода вписать «от чего» было нечем, и позиция без показаний
     выпадала из групп по построению.

ОТВЕТЫ МОДЕЛИ ЖИВЫЕ, и кадр ждёт РАЗБЛОКИРОВКИ КНОПКИ ОТПРАВКИ,
а не таймера: снимок по таймеру ловил бы «Смотрю…», а подставленный
ответ показывал бы не то, что увидит владелец.

ПЕРЕПИСКА ЧИСТИТСЯ ПЕРЕД ПРОГОНОМ боевым эндпоинтом: хвост прошлого
разговора уезжает в промпт, и ответ на «что из этого выбрать»
относился бы к чужому списку. Второй вопрос при этом задаётся В ТОЙ ЖЕ
переписке — он ПРО ПРОШЛЫЙ ОТВЕТ и по отдельности не воспроизводит
ничего.

ШИРИНЫ 2560 И 390 — их назвал владелец; 1440 среди них нет намеренно,
экрана такой ширины у него не существует.

    py shots_medkit_245.py
"""
import asyncio
import os
import sys
import probe_guard  # noqa: F401  ПРОПУСК вместо трассы (§6.0.1)

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

БАЗА = os.getenv("HOVER_BASE", "http://127.0.0.1:8899")
КУДА = "review_screenshots"
ПОЧТА = "screenshot@local.dev"
ПАРОЛЬ = "Screenshot-Local-2026"
ШИРИНЫ = [(2560, 1440), (390, 844)]


async def войти(pg):
    await pg.goto(БАЗА + "/login", wait_until="domcontentloaded")
    await pg.fill("input[name=email]", ПОЧТА)
    await pg.fill("input[name=password]", ПАРОЛЬ)
    await pg.click("button[type=submit]")
    await pg.wait_for_timeout(1200)


async def кадр(pg, имя, ш):
    путь = "%s/245-%s-%d.png" % (КУДА, имя, ш)
    await pg.screenshot(path=путь)
    print("   %s" % путь)


async def спросить(pg, текст):
    """Задать вопрос и ДОЖДАТЬСЯ ответа по разблокировке кнопки."""
    await pg.fill("#apt-ai-in", текст)
    await pg.click("#apt-ai-send")
    for _ in range(120):
        await pg.wait_for_timeout(1000)
        занята = await pg.evaluate(
            "() => document.getElementById('apt-ai-send').disabled")
        if not занята:
            break
    await pg.wait_for_timeout(600)


async def снять(pw, ш, в):
    br = await pw.chromium.launch()
    ctx = await br.new_context(viewport={"width": ш, "height": в},
                               has_touch=(ш < 700), is_mobile=(ш < 700))
    pg = await ctx.new_page()
    await войти(pg)
    print("── ширина %d ──" % ш)

    await pg.goto(БАЗА + "/medkit", wait_until="domcontentloaded")
    await pg.wait_for_timeout(900)
    # ЧИСТИМ БОЕВЫМ ЭНДПОИНТОМ — тем же, что у кнопки человека
    await pg.evaluate("() => fetch('/medkit/api/chat', {method: 'DELETE'})")
    await pg.wait_for_timeout(500)

    await pg.click("#apt-ai-open")
    await pg.wait_for_timeout(700)
    await спросить(pg, "болит голова в висках, что выпить")
    await кадр(pg, "ответ-группы", ш)

    await спросить(pg, "что из этого выбрать")
    await кадр(pg, "ответ-выбор", ш)
    await pg.evaluate("() => закрыть_модалку('apt-ai')")
    await pg.wait_for_timeout(400)

    # ── ОКНО СПОСОБА ПРИЁМА: ПОЛЕ РУЧНЫХ ПОКАЗАНИЙ ──────────────────
    #
    # Позиция ищется ПО ФАКТУ (своё «от чего» записано), а не по
    # номеру: порядок карточек меняется от срока годности.
    ид = await pg.evaluate("""() => {
      const п = (АПТ_ПОЗИЦИИ || []).find(п => п['своё_от_чего']);
      return п ? п.id : null;
    }""")
    if ид:
        await pg.evaluate("(id) => аптДозыОткрыть(id)", ид)
        await pg.wait_for_timeout(900)
        await кадр(pg, "окно-своё-от-чего", ш)
        await pg.evaluate("() => закрыть_модалку('apt-doses')")
    else:
        print("   ПРОПУЩЕНО: позиции со своей записью «от чего» на стенде нет")

    # И ОБРАТНОЕ СОСТОЯНИЕ — КНОПКА «ВПИСАТЬ», где записи ещё нет
    await pg.wait_for_timeout(300)
    ид2 = await pg.evaluate("""() => {
      const п = (АПТ_ПОЗИЦИИ || []).find(п => !п['своё_от_чего']
                                              && !п['показания']);
      return п ? п.id : null;
    }""")
    if ид2:
        await pg.evaluate("(id) => аптДозыОткрыть(id)", ид2)
        await pg.wait_for_timeout(900)
        await кадр(pg, "окно-кнопка-вписать", ш)
        await pg.evaluate("() => закрыть_модалку('apt-doses')")
    else:
        print("   ПРОПУЩЕНО: позиции БЕЗ показаний на стенде нет")

    await ctx.close()
    await br.close()


async def main():
    os.makedirs(КУДА, exist_ok=True)
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        for ш, в in ШИРИНЫ:
            await снять(pw, ш, в)


if __name__ == "__main__":
    asyncio.run(main())
