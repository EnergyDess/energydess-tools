# -*- coding: utf-8 -*-
"""СНИМКИ ЗАХОДА 248: ответ ассистента со всеми блоками, долги, шторка.

НЕ ПРОВЕРКА — кадры смотрит человек, код возврата всегда 0.

ЧТО СНИМАЕТСЯ И ПОЧЕМУ ИМЕННО ЭТО:

  · ОТВЕТ АССИСТЕНТА СО ВСЕМИ ВИДАМИ БЛОКОВ (блок C). Заход 247 дал
    шапку и подложку ГРУППАМ и не тронул остальные озаглавленные
    куски — «показания есть, но к группам не отнеслись», «показаний
    в справочнике нет», просроченное и рецептурное. Кадр обязан
    показать их РЯДОМ, иначе единообразие не с чем сверить.

    ТЕЛО ОТВЕТА ЗДЕСЬ ПОДСТАВЛЕНО, И ЭТО НАЗВАНО, а не спрятано.
    Живой ответ даёт то, что даёт: на боевой аптечке владельца это
    4–6 групп ОДНОГО вида, а просроченного и рецептурного среди
    найденного может не оказаться ни разу. Собрать все пять видов
    блоков в одном кадре живым вопросом нельзя — их состав зависит
    от данных, а не от нашего кода. Рисует кадр БОЕВАЯ
    `аптАИОтвет` тем телом, какое отдаёт сервер; второго
    построителя ответа в браузере нет (§6.0.7), то есть подставляется
    ВХОД, а не разметка.

  · СПИСОК ДОЛГОВ (блок D). Строки разведены линейкой, имя крупнее
    меток. Плитка фото раскрывается ПОВЕРХ окна — отдельным кадром,
    потому что весь дефект D.1 в том, что она раскрывалась ПОД ним.

  · ШТОРКА С НОВЫМИ ПОДПИСЯМИ (блок B). Состояние опознаётся ПО ФАКТУ —
    по тому, что стоит в окне, — а не по номеру позиции: первая
    карточка сегодня одна, завтра другая.

КАДРЫ ЛОЖАТСЯ В `review_screenshots/`, закрытый `.gitignore`: на них
видно содержимое аптечки, а названия лекарств это сведения о здоровье
(§5.1, §8.0).

    py make_local_user.py --seed
    py -m uvicorn main:app --port 8899
    py shots_medkit_248.py
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

# ── ТЕЛО ОТВЕТА СО ВСЕМИ ПЯТЬЮ ВИДАМИ БЛОКОВ ─────────────────────────
#
# Имена условные: названий из аптечки владельца в пробах не печатается
# и не подставляется (§5.1, проверка 26). Поля — ровно те, что отдаёт
# `_апт_ответ_на_запрос`.
def _поз(ид, имя, группа="", пок="", есть=True):
    return {"id": ид, "name": имя, "группа": группа,
            "показание": пок, "показание_откуда": "справочник",
            "показания_есть": есть, "подпись": "Таблетки · категории: Голова",
            "остаток": "10 из 20", "срок": "годен до 03.2027",
            "место": "полка в ванной", "photo": None, "упаковок": 1}


ТЕЛО = {
    "вид": "запрос", "тип": "поиск", "вопрос": "болит голова",
    "вступление": "Вот что по вашему запросу есть дома.",
    "нашлось": [
        _поз(1, "Проба А", "Головная боль", "головная боль, мигрень"),
        _поз(2, "Проба Б", "Головная боль", "головная боль напряжения"),
        _поз(3, "Проба В", "Температура", "лихорадочный синдром"),
        # СТУПЕНЬ 1: показания есть, но к группам не отнеслись
        _поз(4, "Проба Г", "", "боль в мышцах после нагрузки"),
        # СТУПЕНЬ 2: показаний в справочнике нет вовсе
        _поз(5, "Проба Д", "", "", есть=False),
    ],
    "просрочено": [_поз(6, "Проба Е", "", "головная боль")],
    "рецептурные": [_поз(7, "Проба Ж", "", "мигрень")],
    "группы": [], "разбивка": [], "различия": [], "различия_шапка": "",
    "названо": [], "подложено": [], "нет": "", "группа": "",
    "доза_отброшена": False, "непросмотрено": 0,
    "по_показанию": 3, "без_показаний": 1,
    "оговорка": ("Ответ получился длинным и показан не целиком: групп 2, "
                 "карточек 5. Спросите про одну жалобу за раз — покажу всё."),
    "оборван": True,
}


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


async def кадр(pg, имя, ш, узел=None):
    """Кадр окна, а не страницы.

    `full_page` на 2560 даёт страницу высотой в восемь тысяч пикселей,
    и панель ассистента занимает на ней сотую часть — то есть кадр
    показывает не то, ради чего снят. Узел передаётся там, где предмет
    кадра — ОКНО.
    """
    путь = os.path.join(КУДА, "248-%s-%s.png" % (имя, ш))
    if узел:
        э = await pg.query_selector(узел)
        if э:
            await э.screenshot(path=путь)
            print("   %s" % путь)
            return
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
            await pg.goto(БАЗА + "/medkit", wait_until="networkidle")
            await pg.wait_for_timeout(400)

            # ── ОТВЕТ АССИСТЕНТА СО ВСЕМИ БЛОКАМИ ───────────────────
            await pg.evaluate("() => аптАИОткрыть()")
            await pg.wait_for_timeout(500)
            await pg.evaluate(
                "(т) => { document.getElementById('apt-ai-log').innerHTML = '';"
                " аптАИОтвет(т); }", ТЕЛО)
            await pg.wait_for_timeout(400)
            await кадр(pg, "ответ-все-блоки", ш, "#apt-ai")

            # ── СПИСОК ДОЛГОВ ───────────────────────────────────────
            await pg.evaluate("() => аптАИЗакрыть()")
            await pg.wait_for_timeout(300)
            await pg.evaluate("() => { открыть_модалку('apt-recheck-win');"
                              " аптДолгиЗагрузить(); }")
            await pg.wait_for_timeout(900)
            await кадр(pg, "долги", ш, "#apt-recheck-win .modal-sh")

            # ── ПЛИТКА РАСКРЫВАЕТСЯ ПОВЕРХ ОКНА (D.1) ───────────────
            есть_фото = await pg.evaluate(
                "() => !!document.querySelector('.apt-debt-ph[data-shot]')")
            if есть_фото:
                await pg.click(".apt-debt-ph[data-shot]")
                await pg.wait_for_timeout(450)
                await кадр(pg, "долги-снимок-поверх", ш)
                await pg.keyboard.press("Escape")
                await pg.wait_for_timeout(200)
            else:
                print("   плитки с фото в списке долгов нет — кадра нет")
            await pg.keyboard.press("Escape")
            await pg.wait_for_timeout(250)

            # ── ШТОРКА: ВСЕ ДОСТИЖИМЫЕ СОСТОЯНИЯ ────────────────────
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
                    await кадр(pg, "шторка-" + метка, ш, "#apt-doses .modal-sh")
                await pg.keyboard.press("Escape")
                await pg.wait_for_timeout(120)
            print("   состояний шторки снято: %d" % len(снято))
            await ctx.close()
        await бр.close()


if __name__ == "__main__":
    asyncio.run(прогон())
    print("\nКадры смотрит человек. Каталог: %s" % КУДА)
