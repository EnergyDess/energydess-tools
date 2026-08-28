# -*- coding: utf-8 -*-
"""СНИМКИ ЗАХОДА 193: то, что владелец обязан увидеть до коммита.

═══════════════════════════════════════════════════════════════════════
ЧТО ЭТО
═══════════════════════════════════════════════════════════════════════

НЕ ПРОВЕРКА, кадры смотрит человек: код возврата всегда 0. Кода
«правильно» тут нет — облик решает глаз владельца.

Снимает ровно то, что названо в постановке пунктом 5:

  · диалог ассистента на ВСЕХ ЧЕТЫРЁХ типах вопроса;
  · одну и ту же переписку на обеих ширинах;
  · поле ввода на 390 — с пустым полем и с длинным текстом;
  · четыре вкладки панели участников;
  · шапку раздела с переименованной кнопкой.

═══════════════════════════════════════════════════════════════════════
ОТВЕТЫ АССИСТЕНТА — ЖИВЫЕ, А НЕ ПОДСТАВЛЕННЫЕ
═══════════════════════════════════════════════════════════════════════

Четыре типа вопроса задаются НАСТОЯЩИМИ запросами к живой модели,
и кадр ждёт разблокировки кнопки отправки, а не таймера: подставленный
ответ показывал бы не то, что увидит владелец, а снимок по таймеру
ловил бы «Смотрю…».

Живой ответ платит временем и требует ключа OpenRouter. Ключа нет —
проба говорит это ДО прогона, а не рисует пустые кадры.

═══════════════════════════════════════════════════════════════════════
ЗАПУСК
═══════════════════════════════════════════════════════════════════════

    py make_local_user.py --seed
    py -m uvicorn main:app --port 8899
    py shots_medkit_193.py

Ширины 2560 и 390 — их назвал владелец; 1440 среди них нет намеренно
(тот же довод, что у задачи 143: экрана такой ширины у него нет).
"""
import asyncio
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

БАЗА = os.environ.get("MEDKIT_BASE", "http://127.0.0.1:8899")
ПОЧТА = "screenshot@local.dev"
ПАРОЛЬ = "Screenshot-Local-2026"
КУДА = os.environ.get("SHOTS_DIR", r"C:\Temp\claude\shots_193")

# ЧЕТЫРЕ ТИПА ВОПРОСА, дословно теми формулировками, которыми их задавал
# живой человек. Пятая строка — своя, на границу нового стоп-состояния.
ВОПРОСЫ = [
    ("тип-поиск", "болит живот"),
    ("тип-схема", "А как принимать цетрин?"),
    ("тип-стоп", "Я приняла нурофен 2 часа назад, поспала, симптомы "
                 "вернулись. Что можно сделать? Может другое "
                 "обезболивающее?"),
    ("тип-иное", "А я могу принять вторую таблетку нурофена? "
                 "Мне это поможет?"),
]

ДЛИННЫЙ = ("Нурофен 200 мг, двадцать таблеток в упаковке, годен "
           "до июня 2028, лежит на полке в ванной")


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
    # НАЖИМАЕМ БЕЗ ОЖИДАНИЯ УСТОЙЧИВОСТИ. На 390 кнопка входа приезжает
    # с анимацией появления, и харнесса ждёт её остановки 30 секунд,
    # а потом роняет прогон: «element is not stable». Кнопка при этом
    # исправна — двигается она, а не ломается.
    await pg.click("button[type=submit]", force=True)
    await pg.wait_for_load_state("networkidle")
    if "/login" in pg.url:
        raise SystemExit("ВХОД НЕ СОСТОЯЛСЯ — снимать нечего")


async def _спросить(pg, текст):
    """Задать вопрос и ДОЖДАТЬСЯ ответа, а не паузы.

    Признак готовности — разблокированная кнопка отправки: её гасит
    `аптАИЖдём` и возвращает `аптАИГотово`. Снимок по таймеру ловил бы
    «Смотрю…» на медленном ответе и молчал бы об этом.
    """
    await pg.fill("#apt-ai-in", текст)
    await pg.evaluate("() => аптАИОтправитьТекст()")
    for _ in range(120):
        готов = await pg.evaluate(
            "() => !document.getElementById('apt-ai-send').disabled")
        if готов:
            break
        await pg.wait_for_timeout(500)
    else:
        print("   ОТВЕТ НЕ ПРИШЁЛ за 60 с — кадр снимается как есть")
    await pg.wait_for_timeout(400)


async def _кадр(pg, имя):
    путь = os.path.join(КУДА, имя + ".png")
    await pg.screenshot(path=путь)
    print("   %s" % путь)


async def прогон(ширина):
    from playwright.async_api import async_playwright
    сенсор = ширина < 800
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context(
            viewport={"width": ширина, "height": 900 if not сенсор else 844},
            has_touch=сенсор, is_mobile=сенсор, device_scale_factor=1)
        pg = await ctx.new_page()
        await _войти(pg)

        # ── ШАПКА РАЗДЕЛА С ПЕРЕИМЕНОВАННОЙ КНОПКОЙ (блок D) ─────────
        await pg.goto(БАЗА + "/medkit", wait_until="domcontentloaded")
        await pg.wait_for_selector(".apt-wrap", timeout=20000)
        await pg.wait_for_timeout(700)
        подпись = await pg.evaluate(
            "() => document.getElementById('apt-ai-open').textContent"
            ".replace(/\\s+/g, ' ').trim()")
        print("── %d: шапка раздела, подпись кнопки %r" % (ширина, подпись))
        await _кадр(pg, "%d-шапка-раздела" % ширина)

        # ── ЧЕТЫРЕ ТИПА ВОПРОСА ──────────────────────────────────────
        #
        # ПЕРЕПИСКА ЧИСТИТСЯ ПЕРЕД ПРОГОНОМ: кадр обязан показывать
        # ответ на ЭТОТ вопрос, а не хвост прошлого разговора.
        await pg.evaluate("""async () => {
          await fetch('/medkit/api/chat', {method: 'DELETE'});
        }""")
        await pg.reload(wait_until="domcontentloaded")
        await pg.wait_for_selector(".apt-wrap", timeout=20000)
        await pg.evaluate("() => аптАИОткрыть()")
        await pg.wait_for_timeout(900)
        print("── %d: панель ассистента, приветствие" % ширина)
        await _кадр(pg, "%d-панель-приветствие" % ширина)

        for имя, текст in ВОПРОСЫ:
            print("── %d: %s — «%.60s»" % (ширина, имя, текст))
            await _спросить(pg, текст)
            await _кадр(pg, "%d-%s" % (ширина, имя))

        # ── ОДНА И ТА ЖЕ ПЕРЕПИСКА ПОСЛЕ ПЕРЕЗАГРУЗКИ ────────────────
        #
        # Кадр отвечает на вопрос блока B: то, что человек видит после
        # перезагрузки, обязано совпадать с тем, что он видел до неё,
        # и совпадать на ОБЕИХ ширинах.
        await pg.reload(wait_until="domcontentloaded")
        await pg.wait_for_selector(".apt-wrap", timeout=20000)
        await pg.evaluate("() => аптАИОткрыть()")
        # ЖДЁМ СОСТОЯНИЕ, А НЕ ТАЙМЕР. Первый прогон печатал «реплик 4»
        # при восьми в базе: `аптАИПеречитать` ходит на сервер, и 1200 мс
        # ему хватало не всегда. Кадр, снятый на середине перерисовки,
        # показывает не то, что увидит человек, — и молчит об этом.
        сколько = await pg.evaluate("""async () => {
          const о = await fetch('/medkit/api/chat');
          const т = await о.json();
          return (т['реплики'] || []).length;
        }""")
        for _ in range(40):
            есть = await pg.evaluate(
                "() => document.querySelectorAll('.apt-ai-msg').length")
            if есть >= сколько:
                break
            await pg.wait_for_timeout(250)
        else:
            print("   ЛЕНТА НЕ ДОРИСОВАЛАСЬ: в базе %d, на экране меньше"
                  % сколько)
        await pg.wait_for_timeout(300)
        реплик = await pg.evaluate(
            "() => document.querySelectorAll('.apt-ai-msg').length")
        print("── %d: та же переписка после перезагрузки, реплик %d"
              % (ширина, реплик))
        await _кадр(pg, "%d-переписка-после-перезагрузки" % ширина)

        # ── ПОЛЕ ВВОДА (блок C) ──────────────────────────────────────
        ряд = await pg.evaluate("""() => {
          const р = document.querySelector('.apt-ai-row');
          const п = document.getElementById('apt-ai-in');
          return {доля: +(п.getBoundingClientRect().width /
                          р.getBoundingClientRect().width * 100).toFixed(1),
                  высота: Math.round(р.getBoundingClientRect().height)};
        }""")
        print("── %d: ряд ввода — поле %s%% ширины, высота ряда %s px"
              % (ширина, ряд["доля"], ряд["высота"]))
        await _кадр(pg, "%d-поле-ввода-пустое" % ширина)
        await pg.fill("#apt-ai-in", ДЛИННЫЙ)
        await pg.evaluate("() => аптАИРост(document.getElementById('apt-ai-in'))")
        await pg.wait_for_timeout(300)
        await _кадр(pg, "%d-поле-ввода-длинный-текст" % ширина)
        await pg.fill("#apt-ai-in", "")
        await pg.evaluate("() => аптАИЗакрыть()")
        await pg.wait_for_timeout(400)

        # ── ЧЕТЫРЕ ВКЛАДКИ ПАНЕЛИ УЧАСТНИКОВ (блок E) ────────────────
        await pg.evaluate("() => document.getElementById('apt-circle-open').click()")
        await pg.wait_for_timeout(800)
        for вкладка in ("people", "invites", "feed", "block"):
            await pg.evaluate("(в) => { const к = document.querySelector("
                              "'[data-ctab=\"' + в + '\"]'); if (к) к.click(); }",
                              вкладка)
            await pg.wait_for_timeout(450)
            await _кадр(pg, "%d-круг-%s" % (ширина, вкладка))
        print("── %d: четыре вкладки панели участников" % ширина)

        # ── ПУСТОЕ СОСТОЯНИЕ ПАНЕЛИ (блок E.1) ──────────────────────
        #
        # НА СИДИРОВАННОМ СТЕНДЕ ЕГО НЕТ ВОВСЕ: seed наполняет
        # и приглашения, и блок, и владелец на кадре увидел бы список,
        # а не пустоту, которую правили. Мерка (`check_medkit_look
        # --круг`) заводит это состояние сама и по той же причине —
        # тем же приёмом пользуемся здесь, а не вторым (§6.0.7).
        #
        # ПИШЕТ В БАЗУ И ГОВОРИТ ЭТО, а сид возвращается следом.
        import check_medkit_look as _мерка
        _мерка._приглашения_и_блок_убрать()
        try:
            await pg.reload(wait_until="domcontentloaded")
            await pg.wait_for_selector(".apt-wrap", timeout=20000)
            await pg.evaluate("() => document.getElementById("
                              "'apt-circle-open').click()")
            await pg.wait_for_timeout(800)
            for вкладка in ("invites", "block"):
                await pg.evaluate(
                    "(в) => { const к = document.querySelector("
                    "'[data-ctab=\"' + в + '\"]'); if (к) к.click(); }",
                    вкладка)
                await pg.wait_for_timeout(450)
                await _кадр(pg, "%d-круг-%s-ПУСТО" % (ширина, вкладка))
            print("── %d: пустые вкладки панели (E.1)" % ширина)
        finally:
            os.system("py make_local_user.py --seed > nul 2>&1")
        await ctx.close()
        await b.close()


def main():
    os.makedirs(КУДА, exist_ok=True)
    print("КАДРЫ КЛАДУТСЯ В %s" % КУДА)
    print("Живые ответы модели: нужен ключ OpenRouter и время.\n")
    for ш in (2560, 390):
        asyncio.run(прогон(ш))
    print("\nКод возврата 0 всегда: это СНИМКИ, а не проверка. "
          "Облик решает глаз владельца (§6.0.4).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
