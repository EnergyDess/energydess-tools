# -*- coding: utf-8 -*-
"""РЯД ДЕЙСТВИЙ НА КАРТОЧКЕ АПТЕЧКИ: ГАБАРИТЫ И ОБЛАСТЬ НАЖАТИЯ.

Спрашивает то, чего не спрашивала ни одна проба: КАКОГО РАЗМЕРА
кнопки ряда друг относительно друга.

`check_medkit_row.py` мерит выравнивание соседних карточек ПО Y —
«стоят ли одноимённые элементы вровень». `check_touch.py` мерит
область нажатия — «дотянется ли палец». Вопрос «корзина квадратная
или прямоугольная и делят ли соседи остаток поровну» не задавал
никто: ответа на него нет ни в одной из двух мерок, потому что обе
смотрят на ДРУГУЮ ось.

═══════════════════════════════════════════════════════════════════════
ГОЛОВНОЙ БРАУЗЕР ОБЯЗАТЕЛЕН
═══════════════════════════════════════════════════════════════════════

Headless Chromium прячет полосу прокрутки БЕЗ ИЗЪЯТИЯ МЕСТА
(`clientWidth === offsetWidth` при живой прокрутке) — находка захода
255, блок C. Страница `/medkit` прокручивается всегда, полоса
отнимает у контейнера 15 px, и ширина карточки в сетке считается
от него. То есть в headless все ширины ряда выходят завышенными,
и мерка отвечает про раскладку, которой на экране нет.

═══════════════════════════════════════════════════════════════════════
ОБЛАСТЬ НАЖАТИЯ МЕРИТСЯ `elementFromPoint`, А НЕ ПРЯМОУГОЛЬНИКОМ
═══════════════════════════════════════════════════════════════════════

Тот же довод, что у проверки 20 (§6.0.11): видимая кнопка бывает
меньше своей области — доборный слой `::after` не входит
в `getBoundingClientRect`. Меряется от центра в четыре стороны,
пока точка ещё принадлежит кнопке или её потомку.

═══════════════════════════════════════════════════════════════════════
КОРЗИНА ОПОЗНАЁТСЯ ПО ОТСУТСТВИЮ ПОДПИСИ, А НЕ ПО МЕСТУ В РЯДУ
═══════════════════════════════════════════════════════════════════════

У просроченной карточки третья кнопка ПОДПИСАНА («Выбросить»),
и квадратить её нечего: это другое действие, а не то же самое
красным. Отбор по номеру в ряду смешал бы два случая и напечатал
бы находку про исправное.

МЕРКА, код возврата всегда 0 (кроме `--контроль`): «сколько
пикселей расхождения» — число для решения, а не порог.

    py check_medkit_acts.py              # габариты ряда, три ширины
    py check_medkit_acts.py --контроль   # подлог: ширины соседей разные
"""
import asyncio
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace")

БАЗА = os.environ.get("MEDKIT_BASE", "http://127.0.0.1:8899")
ПОЧТА = "screenshot@local.dev"
ПАРОЛЬ = "Screenshot-Local-2026"
ШИРИНЫ = [int(ш) for ш in
          os.environ.get("ACTS_WIDTHS", "2560,1920,390").split(",")]
КОНТРОЛЬ = "--контроль" in sys.argv

# ПОДЛОГ РАЗВОДИТ ШИРИНЫ СОСЕДЕЙ, как просит письмо. Мерка обязана
# назвать это расхождением; молчание означало бы, что она сравнивает
# не то, что печатает.
ПОДЛОГ = """
  .apt-card .apt-acts > .apt-act:first-child { flex-grow: 1.02 !important; }
"""

ЗАМЕР = """() => {
  const из = [];
  for (const к of document.querySelectorAll('.apt-card')) {
    const ряд = к.querySelector('.apt-acts');
    if (!ряд) continue;
    const кнопки = [...ряд.querySelectorAll('.apt-act')];
    if (кнопки.length < 3) continue;
    const описать = (э) => {
      const r = э.getBoundingClientRect();
      const зн = э.querySelector('svg');
      const зр = зн ? зн.getBoundingClientRect() : null;
      return {
        подпись: э.textContent.trim(),
        ш: Math.round(r.width * 10) / 10,
        в: Math.round(r.height * 10) / 10,
        значок: зр ? Math.round(зр.width * 10) / 10 : null
      };
    };
    из.push({ кнопки: кнопки.map(описать) });
  }
  return из;
}"""

# ОБЛАСТЬ НАЖАТИЯ — от центра в четыре стороны, пока точка
# принадлежит самой кнопке либо её потомку.
ОБЛАСТЬ = """(сел) => {
  const э = document.querySelector(сел);
  if (!э) return null;
  э.scrollIntoView({block: 'center'});
  const r = э.getBoundingClientRect();
  const cx = Math.round(r.left + r.width / 2);
  const cy = Math.round(r.top + r.height / 2);
  const свой = (t) => t && (t === э || э.contains(t));
  if (!свой(document.elementFromPoint(cx, cy))) return {перекрыт: true};
  const шаг = (dx, dy) => {
    let n = 0;
    for (let i = 1; i <= 60; i++) {
      if (!свой(document.elementFromPoint(cx + dx * i, cy + dy * i))) break;
      n = i;
    }
    return n;
  };
  return {
    ширина: шаг(1, 0) + шаг(-1, 0) + 1,
    высота: шаг(0, 1) + шаг(0, -1) + 1,
    видимая_ш: Math.round(r.width * 10) / 10,
    видимая_в: Math.round(r.height * 10) / 10
  };
}"""


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


async def прогон(подлог=False):
    from playwright.async_api import async_playwright
    итог = {}
    async with async_playwright() as p:
        # headless=False — разбор в шапке файла
        бр = await p.chromium.launch(headless=False)
        for ш in ШИРИНЫ:
            ктх = await бр.new_context(viewport={"width": ш, "height": 1100},
                                       has_touch=(ш <= 640))
            if подлог:
                await ктх.add_init_script(
                    "document.addEventListener('DOMContentLoaded', () => {"
                    "const s=document.createElement('style');"
                    "s.textContent=" + repr(ПОДЛОГ) + ";"
                    "document.head.appendChild(s); });")
            pg = await ктх.new_page()
            await _войти(pg)
            await pg.goto(БАЗА + "/medkit", wait_until="networkidle")
            await pg.wait_for_timeout(400)
            карточки = await pg.evaluate(ЗАМЕР)
            обл = await pg.evaluate(
                ОБЛАСТЬ, ".apt-card .apt-acts .apt-act-dead")
            итог[ш] = {"карточки": карточки, "область": обл}
            await ктх.close()
        await бр.close()
    return итог


def разбор(итог, метка):
    находок = 0
    print("=" * 68)
    print(метка)
    print("=" * 68)
    for ш, д in итог.items():
        карточки = д["карточки"]
        рабочие = [к for к in карточки if к["кнопки"][2]["подпись"] == ""]
        просроч = [к for к in карточки if к["кнопки"][2]["подпись"] != ""]
        print("")
        print(f"── ширина {ш} ── карточек {len(карточки)}"
              f" (рабочих {len(рабочие)}, с подписью у третьей {len(просроч)})")
        if not рабочие:
            print("   РАБОЧИХ КАРТОЧЕК НЕТ — мерить нечего")
            continue
        к = рабочие[0]
        for i, б in enumerate(к["кнопки"]):
            имя = б["подпись"] or "(корзина, без подписи)"
            print(f"   {i+1}. {имя:<26} {б['ш']:>6} x {б['в']:<6}"
                  f"  значок {б['значок']}")
        корз = к["кнопки"][2]
        разн_кв = round(abs(корз["ш"] - корз["в"]), 1)
        квадрат = разн_кв <= 1.5
        print(f"   корзина КВАДРАТ: {'да' if квадрат else 'НЕТ'}"
              f"  (|{корз['ш']} - {корз['в']}| = {разн_кв})")
        if not квадрат:
            находок += 1
        разн = []
        for кк in рабочие:
            a, b = кк["кнопки"][0]["ш"], кк["кнопки"][1]["ш"]
            разн.append(round(abs(a - b), 1))
        худш = max(разн) if разн else 0
        print(f"   «Изменить» vs «Инструкция»: худшее расхождение"
              f" {худш} px по {len(рабочие)} карточкам")
        if худш > 0.5:
            находок += 1
        о = д["область"]
        # МИНИМУМ 44 СПРАШИВАЕТСЯ ТОЛЬКО НА СЕНСОРНОЙ ШИРИНЕ.
        # Доборный слой `.tap-44` объявлен под `pointer: coarse`
        # НАМЕРЕННО (§6.0.11): на мыши курсор точен, а лишняя область
        # крала бы соседей. Спрашивать 44 у десктопа значило бы
        # печатать находку про исправное — проверка, которая врёт,
        # перестаёт читаться (§6.0.2, довод проверки 4).
        сенсор = ш <= 640
        if о and not о.get("перекрыт"):
            мало = о["ширина"] < 44 or о["высота"] < 44
            вердикт = ("МЕНЬШЕ 44" if мало else "ok") if сенсор else \
                      "(мышь: минимум не спрашивается)"
            print(f"   область нажатия корзины: {о['ширина']}x{о['высота']}"
                  f"  (видимая {о['видимая_ш']}x{о['видимая_в']})"
                  f"  {вердикт}")
            if мало and сенсор:
                находок += 1
        else:
            print(f"   область нажатия: {о}")
    print("")
    print(f"НАХОДОК: {находок}")
    return находок


async def main():
    if КОНТРОЛЬ:
        чисто = разбор(await прогон(False), "КОНТРОЛЬ, ОСНОВА (без подлога)")
        сподл = разбор(await прогон(True),
                       "КОНТРОЛЬ, ПОДЛОГ: ширины соседей разведены")
        print("")
        print("=" * 68)
        print(f"ДОКАЗАТЕЛЬСТВО: находок без подлога {чисто},"
              f" с подлогом {сподл}")
        print("КОНТРОЛЬ: подлог " +
              ("НАЙДЕН" if сподл > чисто else "НЕ НАЙДЕН — проба слепа"))
        return 0 if сподл > чисто else 1
    разбор(await прогон(False), "РЯД ДЕЙСТВИЙ КАРТОЧКИ АПТЕЧКИ")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
