# -*- coding: utf-8 -*-
"""СНИМКИ ЗАХОДА 197 — кадры смотрит человек, не проверка.

ЧТО СНИМАЕТСЯ И ПОЧЕМУ ИМЕННО ЭТО:

  A. РЯД ВВОДА ПАНЕЛИ на 2560 и 390, пустым и с настоящей фразой
     владельца. Главный кадр захода: до правки поле на 1920 прятало
     целую строку, и увидеть это можно только с текстом внутри.
  B. ДИАЛОГ «не понял» — та же невнятная фраза ДВАЖДЫ ПОДРЯД.
     Один кадр показал бы только первую половину, а вся суть B.4
     в том, что второй ответ ДРУГОЙ.

ФРАЗЫ НАСТОЯЩИЕ, ВЛАДЕЛЬЦА. Ответы модели ЖИВЫЕ, и кадр ждёт
разблокировки кнопки отправки, а не таймера: снимок по таймеру ловил
бы «Смотрю…».

ПЕРЕПИСКА ЧИСТИТСЯ ПЕРЕД ПРОГОНОМ — кадр обязан показывать ответ
на ЭТОТ вопрос, а не хвост прошлого разговора.

    py make_local_user.py --seed
    py -m uvicorn main:app --port 8899
    py shots_medkit_197.py
"""
import asyncio
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

БАЗА = os.environ.get("MEDKIT_BASE", "http://127.0.0.1:8899")
ПОЧТА, ПАРОЛЬ = "screenshot@local.dev", "Screenshot-Local-2026"
КУДА = os.environ.get("SHOTS_DIR", "C:/Temp/claude/shots197")
# ШИРИНЫ НАЗВАЛ ВЛАДЕЛЕЦ: у него два монитора, 2560 и 1920, плюс
# телефон. 1440 среди них нет — экрана такой ширины не существует
ШИРИНЫ = [2560, 1920, 390]

ФРАЗА = "Привет, у меня вздулся живот, болит. Что мне можно принять?"
НЕВНЯТНАЯ = "ну там это, с той пачкой как"


async def _войти(pg):
    await pg.goto(БАЗА + "/login", wait_until="domcontentloaded")
    await pg.fill("input[name=email]", ПОЧТА)
    await pg.fill("input[name=password]", ПАРОЛЬ)
    await pg.click("button[type=submit]")
    await pg.wait_for_load_state("networkidle")
    if "/login" in pg.url:
        raise SystemExit("ВХОД НЕ СОСТОЯЛСЯ — снимать нечего")


async def _ответ_пришёл(pg, было):
    """Ждём разблокировки кнопки отправки, а не таймера."""
    for _ in range(150):
        await pg.wait_for_timeout(400)
        готово = await pg.evaluate(
            "(было) => { const к = document.getElementById('apt-ai-send');"
            "  const м = document.querySelectorAll('.apt-ai-msg').length;"
            "  return !к.disabled && м > было; }", было)
        if готово:
            return True
    return False


async def прогон():
    from playwright.async_api import async_playwright
    os.makedirs(КУДА, exist_ok=True)
    async with async_playwright() as pw:
        бр = await pw.chromium.launch()
        for ш in ШИРИНЫ:
            сенсор = ш < 800
            ctx = await бр.new_context(
                viewport={"width": ш, "height": 900 if not сенсор else 844},
                has_touch=сенсор, is_mobile=сенсор, device_scale_factor=1)
            pg = await ctx.new_page()
            await _войти(pg)
            await pg.goto(БАЗА + "/medkit", wait_until="networkidle")
            # ПЕРЕПИСКА ЧИСТИТСЯ ЧЕРЕЗ ТОТ ЖЕ ЭНДПОИНТ, что у кнопки
            # человека: подстановка в базу показала бы не то состояние,
            # которое рисует сервер
            await pg.evaluate(
                "() => fetch('/medkit/api/chat', {method: 'DELETE'})")
            await pg.wait_for_timeout(400)
            await pg.reload(wait_until="networkidle")
            await pg.evaluate("() => аптАИОткрыть()")
            await pg.wait_for_timeout(600)

            # ── A: РЯД ВВОДА ────────────────────────────────────────
            панель = await pg.query_selector("#apt-ai")
            await панель.screenshot(path="%s/A-панель-пустая-%d.png" % (КУДА, ш))
            await pg.fill("#apt-ai-in", ФРАЗА)
            await pg.dispatch_event("#apt-ai-in", "input")
            await pg.wait_for_timeout(350)
            await панель.screenshot(path="%s/A-панель-с-фразой-%d.png" % (КУДА, ш))
            ряд = await pg.query_selector(".apt-ai-bar")
            await ряд.screenshot(path="%s/A-ряд-ввода-%d.png" % (КУДА, ш))
            print("  %d: A — три кадра" % ш)

            # ── B: «НЕ ПОНЯЛ» ДВАЖДЫ ПОДРЯД ─────────────────────────
            await pg.fill("#apt-ai-in", "")
            await pg.dispatch_event("#apt-ai-in", "input")
            for заход in (1, 2):
                было = await pg.evaluate(
                    "() => document.querySelectorAll('.apt-ai-msg').length")
                await pg.fill("#apt-ai-in", НЕВНЯТНАЯ)
                await pg.dispatch_event("#apt-ai-in", "input")
                await pg.click("#apt-ai-send")
                пришёл = await _ответ_пришёл(pg, было)
                await pg.wait_for_timeout(400)
                await панель.screenshot(
                    path="%s/B-непонял-%d-%d.png" % (КУДА, заход, ш))
                текст = await pg.evaluate(
                    "() => { const м = document.querySelectorAll('.apt-ai-msg');"
                    "  return м.length ? м[м.length-1].textContent.trim() : ''; }")
                print("  %d: B заход %d — ответ %s: %s"
                      % (ш, заход, "пришёл" if пришёл else "НЕ ПРИШЁЛ",
                         текст[:90]))
            await ctx.close()
        await бр.close()
    print("\nкадры: %s" % КУДА)


if __name__ == "__main__":
    asyncio.run(прогон())
