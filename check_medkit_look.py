# -*- coding: utf-8 -*-
"""ОБЛИК АПТЕЧКИ И ЛАУНЧЕРА — числа, по которым принимают решения.

═══════════════════════════════════════════════════════════════════════
ЧТО ЭТО
═══════════════════════════════════════════════════════════════════════

МЕРКА, а не проверка: кода «правильно» у неё нет, код возврата всегда 0.
Сколько пикселей должна занимать плитка фото и сколько колонок держать
лаунчер — решение об ОБЛИКЕ, и порога тут назначать нечему (то же
устройство, что у `check_ens_width.py` и `check_metrics.py`).

Отвечает на четыре вопроса, и все четыре завела постановка задачи 166:

  D.5  сколько пикселей до первой карточки на 390 — ряд чипов там
       занимал семь строк, и на телефоне были видны одни фильтры;
  D.6  какую долю карточки занимает плитка фото;
  D.7  сколько колонок у лаунчера на 2560 — пятая карточка стояла одна;
  B.1  видна ли кнопка панели ассистента и открывается ли панель.

═══════════════════════════════════════════════════════════════════════
ШИРИНЫ — 1920, 2560 И 390
═══════════════════════════════════════════════════════════════════════

У владельца ДВА монитора, 1920 и 2560. Мерить 1440 значит мерить
ширину, которой никто не видит: ровно эту ошибку разбирала задача 143,
и повторять её здесь незачем.

═══════════════════════════════════════════════════════════════════════
ЗАПУСК
═══════════════════════════════════════════════════════════════════════

    py make_local_user.py --seed
    py -m uvicorn main:app --port 8899
    py check_medkit_look.py

Браузер и поднятое приложение. В ряды §6.0.2 НЕ входит.
"""
import asyncio
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

БАЗА = os.environ.get("MEDKIT_BASE", "http://127.0.0.1:8899")
ПОЧТА = "screenshot@local.dev"
ПАРОЛЬ = "Screenshot-Local-2026"
ШИРИНЫ = [int(ш) for ш in
          os.environ.get("LOOK_WIDTHS", "2560,1920,390").split(",")]


async def _войти(pg):
    await pg.goto(БАЗА + "/login", wait_until="domcontentloaded")
    await pg.fill("input[name=email]", ПОЧТА)
    await pg.fill("input[name=password]", ПАРОЛЬ)
    if await pg.query_selector(".cf-turnstile"):
        for _ in range(60):
            if await pg.evaluate(
                    "() => { const t = document.querySelector("
                    "'[name=\"cf-turnstile-response\"]'); return t && t.value; }"):
                break
            await pg.wait_for_timeout(500)
    await pg.click("button[type=submit]")
    await pg.wait_for_load_state("networkidle")
    if "/login" in pg.url:
        raise SystemExit("ВХОД НЕ СОСТОЯЛСЯ — мерить нечего")


ЗАМЕР = """() => {
  const п = (с) => document.querySelector(с);
  const кор = (э) => э ? э.getBoundingClientRect() : null;
  const карт = п('.apt-card');
  const плитка = карт ? карт.querySelector('.apt-ph') : null;
  const ккор = кор(карт), пкор = кор(плитка);
  /* ДО ПЕРВОЙ КАРТОЧКИ — от верха документа, а не от верха окна:
     окно можно прокрутить, а вопрос про то, сколько занимает всё,
     что стоит ВЫШЕ карточек */
  const доКарточки = карт
    ? Math.round(карт.getBoundingClientRect().top + window.scrollY) : null;
  const сетка = п('.apt-grid');
  let колонок = null;
  if (сетка) {

    колонок = getComputedStyle(сетка).gridTemplateColumns.split(' ').length;
  }
  const кнопка = п('#apt-ai-open');
  return {
    доКарточки,
    карточка: ккор ? Math.round(ккор.width) : null,
    карточкаВысота: ккор ? Math.round(ккор.height) : null,
    плитка: пкор ? Math.round(пкор.height) : null,
    доляПлитки: (пкор && ккор) ? +(пкор.height / ккор.height).toFixed(3) : null,
    колонок,
    чиповРядов: (() => {
      const ч = [...document.querySelectorAll('#apt-chips .chip')]
        .filter(э => !э.hidden);
      const верх = new Set(ч.map(э => Math.round(э.getBoundingClientRect().top)));
      return {штук: ч.length, рядов: верх.size};
    })(),
    кнопкаАссистента: кнопка ? {
      есть: true,
      видна: !!(кнопка.offsetWidth || кнопка.offsetHeight),
      ширина: Math.round(кнопка.getBoundingClientRect().width),
    } : {есть: false},
    высотаСтраницы: Math.round(document.body.scrollHeight),
  };
}"""

ЛАУНЧЕР = """() => {
  const сетка = document.querySelector('.tools-grid, .tool-grid, .cards-grid');
  if (!сетка) return {найдено: false};
  const карточки = [...сетка.querySelectorAll('.tool-card')];
  const верх = new Map();
  карточки.forEach(к => {
    const t = Math.round(к.getBoundingClientRect().top);
    верх.set(t, (верх.get(t) || 0) + 1);
  });
  return {
    найдено: true,
    карточек: карточки.length,
    ряды: [...верх.values()],
    ширинаКарточки: карточки.length
      ? Math.round(карточки[0].getBoundingClientRect().width) : null,
    колонок: getComputedStyle(сетка).gridTemplateColumns.split(' ').length,
  };
}"""


async def прогон():
    from playwright.async_api import async_playwright
    итог = {}
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for ширина in ШИРИНЫ:
            сенсор = ширина < 800
            ctx = await b.new_context(
                viewport={"width": ширина, "height": 900 if not сенсор else 844},
                has_touch=сенсор, is_mobile=сенсор, device_scale_factor=1)
            pg = await ctx.new_page()
            await _войти(pg)
            await pg.goto(БАЗА + "/medkit", wait_until="networkidle")
            await pg.add_style_tag(
                content="html, * { scroll-behavior: auto !important }")
            await pg.wait_for_timeout(500)
            медкит = await pg.evaluate(ЗАМЕР)
            # ПАНЕЛЬ ОТКРЫВАЕТСЯ — вопрос не «есть ли класс», а видно ли
            await pg.evaluate("() => аптАИОткрыть()")
            await pg.wait_for_timeout(500)
            медкит["панель"] = await pg.evaluate("""() => {
              const п = document.getElementById('apt-ai');
              const к = п.getBoundingClientRect();
              const в = document.getElementById('apt-ai-in');
              /* ЖИВОСТЬ ОРГАНА, а не наличие в дереве: `elementFromPoint`
                 в центре поля обязан вернуть его самого (§6.3) */
              const вк = в.getBoundingClientRect();
              const т = document.elementFromPoint(
                вк.left + вк.width / 2, вк.top + вк.height / 2);
              return {
                ширина: Math.round(к.width),
                внутриЭкрана: к.right <= window.innerWidth + 1 && к.left >= -1,
                полеЖивое: !!(т && (т === в || в.contains(т))),
                реплик: document.querySelectorAll('.apt-ai-msg').length,
              };
            }""")
            await pg.evaluate("() => аптАИЗакрыть()")

            await pg.goto(БАЗА + "/", wait_until="networkidle")
            # АНИМАЦИЯ ПОЯВЛЕНИЯ ГЛУШИТСЯ, И ЭТО НЕ ПЕРЕСТРАХОВКА.
            # Карточки лаунчера появляются `.stagger-in` с разной
            # задержкой и со сдвигом по вертикали. Меря через 400 мс,
            # проба видела их НА РАЗНОЙ ВЫСОТЕ и печатала ряды
            # [3, 1, 1] там, где фактически [3, 2], — то есть объявляла
            # находкой собственную торопливость. Поймано сверкой
            # с прямым замером координат, а не чтением.
            #
            # Тот же класс, что недосчитанный переход у пиксельного
            # дифа (§6.0.3): врёт харнесса, а не код.
            await pg.add_style_tag(content=(
                # НЕ `animation: none`, А МГНОВЕННЫЙ ПРОИГРЫШ ДО КОНЦА.
                # `.stagger-in` объявляет `opacity: 0` У САМОГО ЭЛЕМЕНТА,
                # а видимость даёт анимация: выключив её, кадр получаешь
                # с НЕВИДИМЫМИ карточками. Замер геометрии при этом верен
                # (положение не смещается), а снимок — нет, и на первом
                # же кадре лаунчер вышел пустым.
                #
                # `duration: 1ms` доигрывает до конечного кадра, то есть
                # снимает и дрожание, и невидимость разом.
                "*, *::before, *::after { animation-duration: 1ms !important;"
                " animation-delay: 0s !important;"
                " transition-duration: 1ms !important;"
                " transition-delay: 0s !important }"))
            await pg.wait_for_timeout(400)
            лаунчер = await pg.evaluate(ЛАУНЧЕР)
            итог[ширина] = {"медкит": медкит, "лаунчер": лаунчер}
            await ctx.close()
        await b.close()
    return итог


def печать(итог):
    print("ОБЛИК АПТЕЧКИ И ЛАУНЧЕРА")
    print("=" * 72)
    for ширина, д in итог.items():
        м, л = д["медкит"], д["лаунчер"]
        print()
        print("── %d ──" % ширина)
        print("  D.5  до первой карточки: %s px   чипов %s в %s рядов"
              % (м["доКарточки"], м["чиповРядов"]["штук"],
                 м["чиповРядов"]["рядов"]))
        print("  D.6  карточка %sx%s, плитка фото %s px (%s от высоты)"
              % (м["карточка"], м["карточкаВысота"], м["плитка"],
                 м["доляПлитки"]))
        print("       колонок сетки аптечки: %s" % м["колонок"])
        print("  D.7  лаунчер: карточек %s, ряды %s, колонок %s, ширина %s"
              % (л.get("карточек"), л.get("ряды"), л.get("колонок"),
                 л.get("ширинаКарточки")))
        к = м["кнопкаАссистента"]
        print("  B.1  кнопка ассистента: %s"
              % ("видна, %s px" % к["ширина"] if к.get("видна")
                 else "НЕ ВИДНА" if к.get("есть") else "НЕТ В РАЗМЕТКЕ"))
        п = м["панель"]
        print("       панель: %s px, внутри экрана %s, поле живое %s, реплик %s"
              % (п["ширина"], п["внутриЭкрана"], п["полеЖивое"], п["реплик"]))
        print("       высота страницы: %s px" % м["высотаСтраницы"])
    print()
    print("Код возврата 0 всегда: это МЕРКА, а не проверка (§6.0.4).")


def main():
    печать(asyncio.run(прогон()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
