"""СНИМКИ ЗАХОДА 209 — ДЛЯ ПРИЁМКИ ВЛАДЕЛЬЦЕМ.

НЕ ПРОВЕРКА: кода «правильно» у неё нет, кадры смотрит человек.
Код возврата всегда 0.

Что снимается — ровно то, что просит пункт 5 постановки:

  1. РЯД КАРТОЧЕК НОВОЙ ФОРМЫ — все одной формы, ниже ряда действий
     ничего нет, метка «N упак.» стоит поверх фото КНОПКОЙ;
  2. ОКНО УПАКОВОК — то, ради чего список и уехал из карточки;
  3. ЧЕТЫРЕ ВКЛАДКИ ОКНА «ОБЩАЯ АПТЕЧКА» В ПУСТОМ СОСТОЯНИИ —
     блок E письма: значки и текст обязаны стоять на одной высоте.

ПУСТОЕ СОСТОЯНИЕ ЗАВОДИТСЯ СЪЁМКОЙ И ВОЗВРАЩАЕТСЯ ЕЮ ЖЕ: seed
наполняет и приглашения, и блок, то есть пустых вкладок на стенде
нет ни одной (§8.0, «состояние, ПРОТИВОПОЛОЖНОЕ другому нужному»).
Тем же приёмом, что у `check_medkit_look --круг`, и тем же кодом —
второй способ опустошить панель разошёлся бы с первым молча.

ШИРИНЫ 2560 И 390 — их назвал владелец; 1440 среди них нет намеренно,
экрана такой ширины у него не существует.
"""
import asyncio
import io
import os
import sys
from pathlib import Path

from playwright.async_api import async_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# `reconfigure`, А НЕ ПОДМЕНА `sys.stdout` НОВОЙ ОБЁРТКОЙ. Импорт
# соседнего инструмента подменяет её у себя, прежняя обёртка уходит
# в сборку мусора и ЗАКРЫВАЕТ общий буфер — печать после импорта
# падает `I/O operation on closed file`. Поймано первым же прогоном.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

БАЗА = os.environ.get("MEDKIT_BASE", "http://127.0.0.1:8899")
ПОЧТА = "screenshot@local.dev"
ПАРОЛЬ = "Screenshot-Local-2026"
КУДА = Path("review_screenshots") / "medkit-209"
ШИРИНЫ = [2560, 390]


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
        print("   ПРОПУЩЕН %s — %s не найден" % (имя, селектор))
        return
    if цель:
        await цель.screenshot(path=str(путь))
    else:
        await pg.screenshot(path=str(путь))
    print("   %s" % путь)


async def кадры(ширина, pw):
    br = await pw.chromium.launch()
    ctx = await br.new_context(viewport={"width": ширина, "height": 1100},
                               has_touch=(ширина <= 640))
    pg = await ctx.new_page()
    await _войти(pg)
    await pg.goto(БАЗА + "/medkit", wait_until="load")
    await pg.wait_for_timeout(1200)

    # 1. РЯД КАРТОЧЕК НОВОЙ ФОРМЫ
    await _снять(pg, "сетка-карточек", ширина, ".apt-grid")

    # 2. ОКНО УПАКОВОК
    открылось = await pg.evaluate("""async () => {
      const м = document.querySelector('.apt-stack[data-packs]');
      if (!м) return false;
      м.scrollIntoView({block: 'center'});
      м.click();
      await new Promise(r => setTimeout(r, 400));
      return document.getElementById('apt-packs-win')
               .classList.contains('open');
    }""")
    if открылось:
        await pg.wait_for_timeout(400)
        await _снять(pg, "окно-упаковок", ширина)
        await pg.evaluate("() => закрыть_модалку('apt-packs-win')")
        await pg.wait_for_timeout(300)
    else:
        print("   ПРОПУЩЕНО окно-упаковок — группы на стенде нет")

    # 3. ЧЕТЫРЕ ВКЛАДКИ ПАНЕЛИ УЧАСТНИКОВ В ПУСТОМ СОСТОЯНИИ
    #
    # Опустошается ТЕМ ЖЕ кодом, что у мерки облика, и возвращается
    # её же сидировщиком: два способа разошлись бы молча
    import check_medkit_look as мерка
    import check_medkit_circle as круг
    мерка._приглашения_и_блок_убрать()
    try:
        await pg.reload(wait_until="load")
        await pg.wait_for_timeout(900)
        открыл = await pg.evaluate("""async () => {
          const к = document.querySelector('[data-circle-open]')
                 || document.getElementById('apt-circle-open');
          if (!к) return false;
          к.click();
          await new Promise(r => setTimeout(r, 500));
          return true;
        }""")
        if not открыл:
            print("   ПРОПУЩЕНЫ вкладки — кнопки участников нет")
        else:
            вкладки = await pg.evaluate(
                "() => [...document.querySelectorAll('.apt-circle-tabs .tab-btn')]"
                "  .map(в => в.textContent.trim())")
            for i, имя in enumerate(вкладки):
                await pg.evaluate(
                    "(i) => document.querySelectorAll("
                    "'.apt-circle-tabs .tab-btn')[i].click()", i)
                await pg.wait_for_timeout(350)
                await _снять(pg, "круг-вкладка-%d" % (i + 1), ширина,
                             "#apt-circle .modal-sh")
            print("   вкладок снято: %d (%s)" % (len(вкладки),
                                                 ", ".join(вкладки)))
    finally:
        # СТЕНД ВОЗВРАЩАЕТСЯ ТЕМ ЖЕ СИДИРОВЩИКОМ, что у мерки облика:
        # оставленная пустая панель превратила бы следующий снимок
        # в снимок не того состояния (§6.0.3, шестая причина)
        print("   стенд возвращён в сидированное: %s"
              % ("да" if круг.вернуть_сид() else "НЕТ"))
    await ctx.close()
    await br.close()


async def main():
    async with async_playwright() as pw:
        for ш in ШИРИНЫ:
            await кадры(ш, pw)
    print("")
    print("Кадры: %s" % КУДА)


if __name__ == "__main__":
    asyncio.run(main())
