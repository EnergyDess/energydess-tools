# -*- coding: utf-8 -*-
"""СНИМКИ ЗАХОДА 247: шторка, ответ ассистента, долги, форма с подвалом.

НЕ ПРОВЕРКА — кадры смотрит человек, код возврата всегда 0.

ЧТО СНИМАЕТСЯ И ПОЧЕМУ ИМЕННО ЭТО:

  · ШТОРКА ВО ВСЕХ ДОСТИЖИМЫХ СОСТОЯНИЯХ (блок B). Подписи кнопок
    называют ПОЛЕ, а не источник, ход наружу понижен до третичного
    уровня и выведен из ряда, отступ под последним рядом уменьшен.
    Состояние опознаётся ПО ФАКТУ — по тому, что стоит в окне, —
    а не по номеру позиции: первая карточка сегодня одна, завтра другая;
  · ОТВЕТ АССИСТЕНТА С ШАПКАМИ ГРУПП (блок C). Ответ ЖИВОЙ, и кадр
    ждёт разблокировки кнопки отправки, а не таймера: подставленный
    показывал бы не то, что увидит владелец, а снимок по таймеру ловил
    бы «Смотрю…». Переписка чистится боевым эндпоинтом ПЕРЕД прогоном —
    иначе на второй ширине в кадр попадёт заслон повтора, потому что
    переписка общая;
  · СПИСОК ДОЛГОВ (блок E) — окно стало шире, плитка фото открывается
    нажатием;
  · ФОРМА ПРАВКИ С ПОДВАЛОМ (блок D), ПРОКРУЧЕННАЯ ВНИЗ: весь дефект
    в том, как выглядит ЛИПКИЙ подвал под содержимым, и кадр
    непрокрученной формы показал бы не его.

КАДРЫ ЛОЖАТСЯ В `review_screenshots/`, закрытый `.gitignore`: на них
видно содержимое аптечки, а названия лекарств это сведения о здоровье
(§5.1, §8.0).

    py make_local_user.py --seed
    py -m uvicorn main:app --port 8899
    py shots_medkit_247.py
"""
import asyncio
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

БАЗА = os.getenv("HOVER_BASE", "http://127.0.0.1:8899")
ПОЧТА = os.getenv("STAND_EMAIL", "screenshot@local.dev")
ПАРОЛЬ = os.getenv("STAND_PASSWORD", "Screenshot-Local-2026")
КУДА = "review_screenshots"
ШИРИНЫ = [2560, 390]
ВОПРОС = "болит голова, что есть дома"


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


async def кадр(pg, имя, ш):
    путь = os.path.join(КУДА, "247-%s-%s.png" % (имя, ш))
    await pg.screenshot(path=путь)
    print("   %s" % путь)


МЕТКА = """() => {
  const т = document.getElementById('apt-doses-body');
  if (!т) return 'окна нет';
  const есть = с => !!т.querySelector(с);
  const подписи = [...т.querySelectorAll('.apt-doses-acts .btn')]
    .map(к => к.textContent.trim());
  const части = [];
  части.push(есть('.apt-doses-text, .apt-doses-blocks') ? 'спр' : 'безспр');
  if (есть('.apt-own')) части.push('своя');
  if (подписи.some(п => /Поискать|Найти в справочнике/.test(п)))
    части.push('повтор');
  if (подписи.some(п => /Вписать вещество/.test(п))) части.push('вещпусто');
  return части.join('-');
}"""


async def прогон():
    from playwright.async_api import async_playwright
    os.makedirs(КУДА, exist_ok=True)
    async with async_playwright() as pw:
        бр = await pw.chromium.launch()
        for ш in ШИРИНЫ:
            ctx = await бр.new_context(
                viewport={"width": ш, "height": 900 if ш > 500 else 780},
                device_scale_factor=1, has_touch=(ш <= 500),
                is_mobile=(ш <= 500))
            pg = await ctx.new_page()
            await _войти(pg)
            print("### %s px" % ш)

            # ── ШТОРКА: ВСЕ ДОСТИЖИМЫЕ СОСТОЯНИЯ ────────────────────
            await pg.goto(БАЗА + "/medkit", wait_until="networkidle")
            await pg.wait_for_timeout(400)
            ид_все = await pg.evaluate(
                "() => [...document.querySelectorAll('[data-doses]')]"
                ".map(к => к.dataset.doses)")
            снято = set()
            for ид in ид_все:
                await pg.evaluate("(id) => аптДозыОткрыть(id)", str(ид))
                await pg.wait_for_timeout(320)
                метка = await pg.evaluate(МЕТКА)
                if метка not in снято:
                    снято.add(метка)
                    await кадр(pg, "шторка-" + метка, ш)
                await pg.keyboard.press("Escape")
                await pg.wait_for_timeout(120)
            print("   состояний шторки снято: %d" % len(снято))

            # ── ФОРМА ПРАВКИ, ПРОКРУЧЕННАЯ ДО ПОДВАЛА ───────────────
            ид = await pg.evaluate(
                "() => {const к = document.querySelector('[data-edit]');"
                " return к ? к.dataset.edit : null;}")
            if ид:
                await pg.evaluate("(id) => аптОткрытьФорму(аптПозиция(+id))",
                                  str(ид))
                await pg.wait_for_timeout(450)
                await pg.evaluate(
                    "() => {const т = document.querySelector('.apt-form')"
                    ".closest('.modal-body'); т.scrollTop = т.scrollHeight;}")
                await pg.wait_for_timeout(250)
                await кадр(pg, "форма-подвал", ш)
                await pg.keyboard.press("Escape")
                await pg.wait_for_timeout(200)

            # ── СПИСОК ДОЛГОВ ───────────────────────────────────────
            await pg.evaluate(
                "() => {открыть_модалку('apt-recheck-win');"
                " аптДолгиЗагрузить();}")
            await pg.wait_for_timeout(700)
            await кадр(pg, "долги", ш)
            await pg.keyboard.press("Escape")
            await pg.wait_for_timeout(200)

            # ── ОТВЕТ АССИСТЕНТА: ЖИВОЙ ВЫЗОВ ───────────────────────
            # ПЕРЕПИСКА ЧИСТИТСЯ БОЕВЫМ ЭНДПОИНТОМ: она общая, и на
            # второй ширине в кадр попал бы заслон повтора
            await pg.evaluate(
                "async () => { await fetch('/medkit/api/chat',"
                " {method: 'DELETE'}); }")
            await pg.wait_for_timeout(300)
            await pg.reload(wait_until="networkidle")
            await pg.wait_for_timeout(400)
            await pg.evaluate("() => аптАИОткрыть()")
            await pg.wait_for_timeout(600)
            await pg.fill("#apt-ai-in", ВОПРОС)
            await pg.evaluate("() => аптАИОтправитьТекст()")
            # ЖДЁМ РАЗБЛОКИРОВКИ КНОПКИ, А НЕ ТАЙМЕРА: по таймеру
            # в кадр попадает «Смотрю…»
            for _ in range(120):
                готово = await pg.evaluate(
                    "() => {const к = document.getElementById('apt-ai-send');"
                    " return к && !к.disabled;}")
                if готово:
                    break
                await pg.wait_for_timeout(500)
            await pg.wait_for_timeout(600)
            await кадр(pg, "ответ-группы", ш)
            await ctx.close()
        await бр.close()
    print("Кадры смотрит человек: это НЕ проверка, код возврата 0.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(прогон()))
