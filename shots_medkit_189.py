"""СНИМКИ ЗАХОДА 189 — ДЛЯ ПРИЁМКИ ВЛАДЕЛЬЦЕМ.

НЕ ПРОВЕРКА: кода «правильно» у неё нет, кадры смотрит человек.
Код возврата всегда 0.

Что снимается — ровно то, что просит пункт 5 постановки:

  1. ЧЕТЫРЕ ВКЛАДКИ ПАНЕЛИ УЧАСТНИКОВ — с подсвеченной активной
     (блок A.1: до правки активная не отличалась от неактивных
     НИ ОДНИМ вычисленным свойством);
  2. ПАНЕЛЬ В ЛИЧНОЙ АПТЕЧКЕ — то состояние, где A.5 сводил три
     системы координат в одну;
  3. ФОРМА С НОВЫМ ДЕЙСТВИЕМ «Ещё упаковка» (блок B) и она же
     ПОСЛЕ нажатия — с перенесёнными полями и пустым сроком;
  4. ДИАЛОГОВОЕ ОКНО: на 390 без крестика, на десктопе с крестиком
     и без полоски (блок C);
  5. ЗНАЧОК ПОДСКАЗКИ крупным планом (D.1);
  6. РАСКРЫТОЕ ФОТО — кадр, на котором и была рамка вокруг
     страницы (D.2).

ШИРИНЫ 2560 И 390 — их назвал владелец; 1440 среди них нет намеренно,
экрана такой ширины у него не существует (тот же довод, что у задач
143 и 182).

═══════════════════════════════════════════════════════════════════════
КАДР «ЛИЧНАЯ АПТЕЧКА» — РОСПУСКОМ КРУГА, И КРУГ ВОЗВРАЩАЕТСЯ

ПЕРВАЯ ВЕРСИЯ ПОДМЕНЯЛА ОТВЕТ СЕРВЕРА в самой странице — атрибут
общности с единицы на ноль, — и ПОДЛОГ НЕ СОСТОЯЛСЯ: панель рисует
сервер целиком, список участников уже лежит в отданной разметке,
и атрибут на него не влияет. Кадры «участники» и «личная аптечка»
вышли ПОБАЙТОВО ОДИНАКОВЫМИ (md5 7aeb8e8e...) — то есть съёмка
показывала бы общую панель под подписью «личная». Поймано сверкой
размеров файлов, а не чтением: подлог, который не сработал,
неотличим от снятого состояния (§6.0.3).

Поэтому круг РАСПУСКАЕТСЯ по-настоящему и ВОЗВРАЩАЕТСЯ тем же
сидировщиком, каким его сеет seed: второй сборки круга не заводится
(§6.0.7), а стенд после съёмки остаётся ровно сидированным — иначе
следующий пиксельный диф и следующий прогон пробы стали бы
недостоверными (§6.0.3, шестая и седьмая причины неповторимости).

Форма блока B открывается и закрывается БЕЗ сохранения — второй
упаковки в базе после съёмки не остаётся.
"""
import asyncio
import io
import os
import sys
from pathlib import Path

from playwright.async_api import async_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# Консоль Windows — cp1251, и рамки в выводе роняют print целиком (§6.0)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace")

БАЗА = os.environ.get("MEDKIT_BASE", "http://127.0.0.1:8899")
ПОЧТА = "screenshot@local.dev"
ПАРОЛЬ = "Screenshot-Local-2026"
КУДА = Path("review_screenshots") / "medkit-189"
ШИРИНЫ = [2560, 390]


def _круг_распустить():
    """Распустить круг ТЕМ ЖЕ кодом, что у пробы (§6.0.7)."""
    import check_medkit_circle
    check_medkit_circle.прибрать()


def _круг_вернуть():
    """Вернуть стенду сидированный круг — тем же сидировщиком."""
    import check_medkit_circle
    check_medkit_circle.вернуть_сид()


async def _войти(pg):
    await pg.goto(БАЗА + "/login", wait_until="domcontentloaded")
    await pg.fill("input[name=email]", ПОЧТА)
    await pg.fill("input[name=password]", ПАРОЛЬ)
    if await pg.query_selector(".cf-turnstile"):
        for _ in range(60):
            if await pg.evaluate(
                    "() => { const t = document.querySelector("
                    "'[name=cf-turnstile-response]'); return t && t.value; }"):
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


async def кадры(ширина, pw):
    сенсор = ширина <= 480
    br = await pw.chromium.launch()
    ctx = await br.new_context(
        viewport={"width": ширина, "height": 1200 if not сенсор else 844},
        has_touch=сенсор, is_mobile=сенсор, device_scale_factor=1)
    pg = await ctx.new_page()
    await _войти(pg)
    await pg.goto(БАЗА + "/medkit", wait_until="networkidle")
    await pg.wait_for_timeout(400)
    print("-- %d --" % ширина)

    # 1. ЧЕТЫРЕ ВКЛАДКИ ПАНЕЛИ (A.1, A.2)
    await pg.evaluate("() => аптКругОткрыть()")
    await pg.wait_for_timeout(700)
    for вкл, имя in (("people", "участники"), ("invites", "приглашения"),
                     ("feed", "лента"), ("block", "блок")):
        await pg.evaluate(
            "(в) => document.querySelector('[data-ctab=\"' + в + '\"]').click()",
            вкл)
        await pg.wait_for_timeout(350)
        await _снять(pg, "панель-" + имя, ширина, "#apt-circle .modal-sh")
    await pg.evaluate("() => закрыть_модалку('apt-circle')")
    await pg.wait_for_timeout(300)

    # 2. ПАНЕЛЬ В ЛИЧНОЙ АПТЕЧКЕ (A.5).
    #
    # Возврат круга стоит в `finally`: упади съёмка посередине, стенд
    # остался бы личным, и следующий инструмент снимал бы не ту аптечку.
    _круг_распустить()
    try:
        pg2 = await ctx.new_page()
        await pg2.goto(БАЗА + "/medkit", wait_until="networkidle")
        await pg2.evaluate("() => аптКругОткрыть()")
        await pg2.wait_for_timeout(700)
        # ЧТО СНЯЛОСЬ — НАЗЫВАЕТСЯ ЧИСЛОМ, а не подразумевается
        общая = await pg2.evaluate(
            "() => { const п = document.querySelector('.apt-circle');"
            "        return п ? п.dataset.common : 'панели нет'; }")
        print("   [A.5] панель считает аптечку общей: %s (ждём 0)" % общая)
        await _снять(pg2, "панель-личная-аптечка", ширина,
                     "#apt-circle .modal-sh")
        await pg2.close()
    finally:
        _круг_вернуть()

    # 3. ФОРМА С «ЕЩЁ УПАКОВКА» (блок B)
    await pg.reload(wait_until="networkidle")
    await pg.wait_for_timeout(400)
    await pg.evaluate("() => аптОткрытьФорму((АПТ_ПОЗИЦИИ || [])[0] || null)")
    await pg.wait_for_timeout(500)
    await pg.evaluate(
        "() => document.getElementById('apt-more-pack')"
        ".scrollIntoView({block: 'center'})")
    await pg.wait_for_timeout(250)
    await _снять(pg, "форма-ещё-упаковка", ширина, "#apt-form .modal-sh")
    await pg.evaluate(
        "() => document.getElementById('apt-more-pack-btn').click()")
    await pg.wait_for_timeout(450)
    await _снять(pg, "форма-после-переноса", ширина, "#apt-form .modal-sh")
    # ЗАКРЫВАЕМ БЕЗ СОХРАНЕНИЯ: съёмка в базу не пишет
    await pg.evaluate("() => закрыть_модалку('apt-form')")
    await pg.wait_for_timeout(300)

    # 4. ОКНО НА ЭТОЙ ШИРИНЕ: крестик против полоски (блок C)
    await pg.evaluate("() => аптОткрытьФорму()")
    await pg.wait_for_timeout(450)
    await _снять(pg, "окно-шапка", ширина, "#apt-form .modal-sh")
    состояние = await pg.evaluate("""() => {
      const в = (с) => { const э = document.querySelector('#apt-form ' + с);
        return э ? getComputedStyle(э).display : 'нет'; };
      return {полоска: в('.modal-drag'), крестик: в('.modal-hdr .modal-x')};
    }""")
    print("   [C] полоска=%s крестик=%s"
          % (состояние["полоска"], состояние["крестик"]))
    await pg.evaluate("() => закрыть_модалку('apt-form')")
    await pg.wait_for_timeout(250)

    # 5. ЗНАЧОК ПОДСКАЗКИ (D.1)
    await pg.evaluate("() => аптАИОткрыть && аптАИОткрыть()")
    await pg.wait_for_timeout(500)
    await _снять(pg, "подсказка-шапка", ширина, ".apt-ai-head")
    await pg.evaluate("() => аптАИЗакрыть && аптАИЗакрыть()")
    await pg.wait_for_timeout(300)

    # 6. РАСКРЫТОЕ ФОТО (D.2)
    открылось = await pg.evaluate("""async () => {
      /* ОТКРЫВАЕТ КНОПКА УВЕЛИЧЕНИЯ, А НЕ САМА КАРТИНКА: у плитки
         обработчика нажатия нет. Первая версия щёлкала по картинке
         и печатала «на стенде нет карточки со снимком» при трёх
         снимках на стенде — то есть сообщала о СВОЁМ промахе как
         о свойстве данных */
      const к = document.querySelector('.apt-ph-zoom');
      if (!к) return false;
      к.scrollIntoView({block: 'center'});
      к.click();
      await new Promise(r => setTimeout(r, 400));
      return document.getElementById('apt-img-viewer')
               .classList.contains('open');
    }""")
    if открылось:
        await pg.wait_for_timeout(400)
        await _снять(pg, "фото-раскрыто", ширина)
    else:
        print("   ПРОПУЩЕН фото-раскрыто — на стенде нет карточки со снимком")
    await ctx.close()
    await br.close()


async def main():
    async with async_playwright() as pw:
        for ш in ШИРИНЫ:
            await кадры(ш, pw)
    print("\nКадры: %s" % КУДА)


if __name__ == "__main__":
    asyncio.run(main())
