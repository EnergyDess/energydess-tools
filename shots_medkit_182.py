"""СНИМКИ ЗАХОДА 182 — ДЛЯ ПРИЁМКИ ВЛАДЕЛЬЦЕМ.

НЕ ПРОВЕРКА: кода «правильно» у неё нет, кадры смотрит человек.
Код возврата всегда 0.

Что снимается — ровно то, что просит пункт 5 постановки:

  1. ТРИ ВКЛАДКИ ПАНЕЛИ УЧАСТНИКОВ (плюс четвёртая, лента);
  2. КАРТОЧКА СВОЯ И ЧУЖАЯ — с аватаром и без;
  3. ЛЕНТА ИЗМЕНЕНИЙ;
  4. ОКНО ВЫХОДА С ЧИСЛАМИ;
  5. ШАПКА С ТРЕМЯ КНОПКАМИ;
  6. ЛИЧНАЯ АПТЕЧКА БЕЗ ОБЩИХ ЭЛЕМЕНТОВ — тот самый кадр, которым
     проверяется F.4: ни аватаров, ни счётчика участников.

ШИРИНЫ 2560 И 390 — их назвал владелец; 1440 среди них нет намеренно,
экрана такой ширины у него не существует.

═══════════════════════════════════════════════════════════════════════
КРУГ ЗАВОДИТСЯ НАСТОЯЩИМ ПУТЁМ И УБИРАЕТСЯ ЗА СОБОЙ

Приглашение отправляется, принимается и снимается ЧЕРЕЗ ЭНДПОИНТЫ,
а не подставляется строками в базу: подставленный круг показал бы
не то, что увидит владелец, а то, что мы про него думаем. Кадр
«личная аптечка» снимается ДО заведения круга — то есть в состоянии,
в котором стенд и живёт (§8.0: снимок по умолчанию обязан показывать
то, что видит человек без общей аптечки).

Съёмка, оставившая за собой круг, сделала бы недостоверными и пиксельный
диф, и следующий прогон `check_medkit_circle` (§6.0.3, шестая причина
неповторимости — чужая проба, пишущая в ту же базу).
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path

from playwright.async_api import async_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

БАЗА = os.environ.get("MEDKIT_BASE", "http://127.0.0.1:8899")
ПОЧТА = "screenshot@local.dev"
ПАРОЛЬ = "Screenshot-Local-2026"
СОСЕД = "neighbour@local.dev"
ПАРОЛЬ_СОСЕДА = "Neighbour-Local-2026"
КУДА = Path("review_screenshots") / "medkit-182"
ШИРИНЫ = [2560, 390]


def _прибрать():
    """Круг, приглашения, блоки и лента — снимаются.

    Тем же кодом, что у пробы: второй реализации уборки не заводится
    (§6.0.7), и разойдись они, одна оставляла бы то, что другая
    считает мусором.
    """
    import check_medkit_circle
    check_medkit_circle.прибрать()


async def _войти(pg, почта, пароль):
    await pg.goto(БАЗА + "/login", wait_until="domcontentloaded")
    await pg.fill("input[name=email]", почта)
    await pg.fill("input[name=password]", пароль)
    if await pg.query_selector(".cf-turnstile"):
        for _ in range(60):
            есть = await pg.evaluate(
                "() => { const t = document.querySelector("
                "'[name=cf-turnstile-response]'); return t && t.value; }")
            if есть:
                break
            await pg.wait_for_timeout(500)
    await pg.click("button[type=submit]")
    await pg.wait_for_load_state("networkidle")
    if "/login" in pg.url:
        raise SystemExit("ВХОД НЕ СОСТОЯЛСЯ — снимать нечего")


async def _снять(pg, имя, ширина, селектор=None):
    КУДА.mkdir(parents=True, exist_ok=True)
    путь = КУДА / ("%s-%d.png" % (имя, ширина))
    цель = await pg.query_selector(селектор) if селектор else None
    if селектор and not цель:
        print("   ПРОПУЩЕН %s — нет %s" % (имя, селектор))
        return
    if цель:
        await цель.screenshot(path=str(путь), animations="disabled")
    else:
        await pg.screenshot(path=str(путь), animations="disabled")
    print("   %s" % путь.name)


ЗОВ = """async ([путь, метод, тело]) => {
  const н = {method: метод};
  if (тело) { н.headers = {'Content-Type': 'application/json'};
              н.body = JSON.stringify(тело); }
  const о = await fetch(путь, н);
  try { return {код: о.status, тело: await о.json()}; }
  catch (e) { return {код: о.status, тело: null}; }
}"""


async def кадры(ширина, pw):
    br = await pw.chromium.launch()
    ctx = await br.new_context(viewport={"width": ширина, "height": 1400},
                               has_touch=(ширина <= 480),
                               is_mobile=(ширина <= 480))
    ctx2 = await br.new_context(viewport={"width": ширина, "height": 1400},
                                has_touch=(ширина <= 480),
                                is_mobile=(ширина <= 480))
    pg, pg2 = await ctx.new_page(), await ctx2.new_page()
    try:
        await _войти(pg, ПОЧТА, ПАРОЛЬ)
        await _войти(pg2, СОСЕД, ПАРОЛЬ_СОСЕДА)

        # ── 6. ЛИЧНАЯ АПТЕЧКА (F.4) — ДО заведения круга ───────────
        await pg.goto(БАЗА + "/medkit", wait_until="networkidle")
        await pg.wait_for_timeout(600)
        await _снять(pg, "01-личная-аптечка", ширина)
        await _снять(pg, "02-личная-шапка", ширина, ".apt-head")
        await pg.evaluate("() => аптКругОткрыть()")
        await pg.wait_for_timeout(400)
        await _снять(pg, "03-личная-панель", ширина, "#apt-circle .modal-sh")
        await pg.evaluate("() => закрыть_модалку('apt-circle')")

        # ── КРУГ ЗАВОДИТСЯ НАСТОЯЩИМ ПУТЁМ ─────────────────────────
        await pg.evaluate(ЗОВ, ["/medkit/api/circle/invite", "POST",
                                {"кого": СОСЕД}])
        await pg2.goto(БАЗА + "/medkit", wait_until="networkidle")
        о = await pg2.evaluate(ЗОВ, ["/medkit/api/circle", "GET", None])
        пр = (о["тело"] or {}).get("полученные") or []
        if not пр:
            print("   ПРИГЛАШЕНИЕ НЕ ДОШЛО — общие кадры пропущены")
            return
        # Кадр приглашения — У ПОЛУЧАТЕЛЯ: только у него видно, что
        # именно ему прислали и какие три кнопки под этим стоят
        await pg2.evaluate("() => аптКругОткрыть()")
        await pg2.evaluate("() => аптКругВкладка('invites')")
        await pg2.wait_for_timeout(400)
        await _снять(pg2, "04-приглашения-получено", ширина,
                     "#apt-circle .modal-sh")
        await pg2.evaluate(ЗОВ, ["/medkit/api/circle/invite/%d/accept"
                                 % пр[0]["id"], "POST", None])

        # Сосед списывает и правит — чтобы в ленте были ЧУЖИЕ строки,
        # а не только свои: лента с одним именем не показывает того,
        # ради чего она заведена
        о = await pg2.evaluate(ЗОВ, ["/medkit/api/grid", "GET", None])
        мои_чужие = [п for п in ((о["тело"] or {}).get("позиции") or [])
                     if not п.get("группа") and п.get("подпись_приёма")]
        if мои_чужие:
            await pg2.evaluate(ЗОВ, ["/medkit/api/items/%d/take"
                                     % мои_чужие[0]["id"], "POST", None])
        await pg2.evaluate(ЗОВ, ["/medkit/api/buy", "POST",
                                 {"name": "Нурофен", "source": "hand"}])

        # ── 1, 3, 5: ПАНЕЛЬ, ЛЕНТА, ШАПКА ──────────────────────────
        await pg.goto(БАЗА + "/medkit", wait_until="networkidle")
        await pg.wait_for_timeout(700)
        await _снять(pg, "05-общая-аптечка", ширина)
        await _снять(pg, "06-шапка-три-кнопки", ширина, ".apt-head")
        await pg.evaluate("() => аптКругОткрыть()")
        await pg.wait_for_timeout(400)
        await _снять(pg, "07-панель-участники", ширина, "#apt-circle .modal-sh")
        await pg.evaluate("() => аптКругВкладка('invites')")
        await pg.wait_for_timeout(200)
        await _снять(pg, "08-панель-приглашения", ширина, "#apt-circle .modal-sh")
        await pg.evaluate("() => аптКругВкладка('feed')")
        await pg.wait_for_timeout(200)
        await _снять(pg, "09-панель-лента", ширина, "#apt-circle .modal-sh")
        await pg.evaluate("() => аптКругВкладка('block')")
        await pg.wait_for_timeout(200)
        await _снять(pg, "10-панель-блок", ширина, "#apt-circle .modal-sh")

        # ── 4: ОКНО ВЫХОДА С ЧИСЛАМИ ───────────────────────────────
        await pg.evaluate("() => аптКругВкладка('people')")
        await pg.wait_for_timeout(200)
        о = await pg.evaluate(ЗОВ, ["/medkit/api/circle", "GET", None])
        чужой = next((ч for ч in ((о["тело"] or {}).get("участники") or [])
                      if not ч["свой"]), None)
        if чужой:
            await pg.evaluate("(id) => аптКругВыход(id)", чужой["id"])
            await pg.wait_for_timeout(600)
            await _снять(pg, "11-выход-с-числами", ширина,
                         "#apt-leave .modal-sh")
            await pg.evaluate("() => закрыть_модалку('apt-leave')")
        await pg.evaluate("() => закрыть_модалку('apt-circle')")

        # ── 2: КАРТОЧКА СВОЯ И ЧУЖАЯ ───────────────────────────────
        await pg.wait_for_timeout(300)
        карточки = await pg.query_selector_all(".apt-card")
        своя = чужая = None
        for к in карточки:
            имя = await к.eval_on_selector(
                ".apt-who-n", "e => e.textContent.trim()") \
                if await к.query_selector(".apt-who-n") else ""
            if имя == "вы" and своя is None:
                своя = к
            elif имя and имя != "вы" and чужая is None:
                чужая = к
        if своя:
            await своя.screenshot(
                path=str(КУДА / ("12-карточка-своя-%d.png" % ширина)),
                animations="disabled")
            print("   12-карточка-своя-%d.png" % ширина)
        if чужая:
            await чужая.screenshot(
                path=str(КУДА / ("13-карточка-чужая-%d.png" % ширина)),
                animations="disabled")
            print("   13-карточка-чужая-%d.png" % ширина)
        # ГРУППА ИЗ ПАЧЕК РАЗНЫХ ВЛАДЕЛЬЦЕВ (D.6) — раскрытая:
        # ради неё и заведён совпадающий препарат у соседа
        груп = await pg.query_selector(".apt-card details.apt-packs")
        if груп:
            await груп.evaluate("e => e.open = true")
            await pg.wait_for_timeout(200)
            карточка = await груп.evaluate_handle("e => e.closest('.apt-card')")
            await карточка.as_element().screenshot(
                path=str(КУДА / ("14-группа-двух-владельцев-%d.png" % ширина)),
                animations="disabled")
            print("   14-группа-двух-владельцев-%d.png" % ширина)
    finally:
        _прибрать()
        await br.close()


async def прогон(ширина):
    async with async_playwright() as pw:
        await кадры(ширина, pw)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ширина", type=int, default=0)
    a = p.parse_args()
    print("=" * 70)
    print("СНИМКИ ЗАХОДА 182 → %s" % КУДА)
    print("=" * 70)
    _прибрать()
    for ш in ([a.ширина] if a.ширина else ШИРИНЫ):
        print("── ширина %d ──" % ш)
        asyncio.run(прогон(ш))
    print()
    print("готово. Кадры смотрит человек — кода «правильно» тут нет.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
