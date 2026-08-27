# -*- coding: utf-8 -*-
"""СНИМКИ ЗАХОДА 163 — сканер кода и строка управления списком.

НЕ ПРОВЕРКА, кода «правильно» у неё нет: кадры смотрит человек.
Код возврата всегда 0.

ЧТО СНИМАЕТСЯ И ПОЧЕМУ ИМЕННО ЭТО:

  · СТРОКА УПРАВЛЕНИЯ на трёх ширинах — блок A постановки. Владелец
    просил кнопки у ПРАВОГО края и одну ширину у трёх соседних блоков;
    на кадре видно и то и другое разом, а числа печатает
    `check_medkit_look.py`;
  · ПАНЕЛЬ АССИСТЕНТА со кнопкой сканера — блок B.4: кнопка стоит
    рядом со съёмкой упаковки, а не отдельным экраном;
  · ОКНО СКАНЕРА с живым видоискателем — поддельная камера Chromium
    отдаёт настоящий поток, то есть кадр показывает ровно то, что
    увидит человек, кроме содержимого картинки;
  · ПОДСТАНОВКА ИЗ СВОЕЙ БАЗЫ — главный сценарий B.2: знакомый код,
    ответ ассистента и заполненная карточка С ПОМЕТКАМИ. Именно ради
    этого кадра сканер и делался.

КОД ПОДСТАВЛЯЕТСЯ В `аптСканПрочитан`, а не читается камерой, и это
названо: синтетический поток Chromium не содержит ни одного кода,
подложить его туда нечем. Путь дальше — боевой до последнего шага,
включая запрос к серверу и разбор GTIN. Само чтение DataMatrix
доказано отдельным файловым замером (BACKLOG №163).

    py -m uvicorn main:app --port 8899
    py shots_medkit_163.py
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
КУДА = os.environ.get("SHOTS_DIR", "C:/Temp/claude/shots163")

# ШИРИНЫ НАЗВАЛ ВЛАДЕЛЕЦ: у него два монитора, 1920 и 2560, плюс
# телефон. 1440 среди них нет намеренно — экрана такой ширины
# у него не существует (тот же довод, что у задачи 143).
ШИРИНЫ = [2560, 1920, 390]

# Тот же код, что у пробной позиции стенда: без совпадения кадр
# «подставилось из базы» показывал бы не то.
КОД_ЗНАКОМЫЙ = "010460123456789021ABCD\x1d91EE07"

КЛЮЧИ_КАМЕРЫ = ["--use-fake-ui-for-media-stream",
                "--use-fake-device-for-media-stream"]


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
        raise SystemExit("ВХОД НЕ СОСТОЯЛСЯ — снимать нечего")


async def _кадр(pg, имя):
    путь = os.path.join(КУДА, имя + ".png")
    await pg.screenshot(path=путь)
    print("   " + путь)


async def снять(br, ширина):
    сенсор = ширина < 800
    ctx = await br.new_context(
        viewport={"width": ширина, "height": 1000 if not сенсор else 844},
        has_touch=сенсор, is_mobile=сенсор, device_scale_factor=1,
        permissions=["camera"])
    pg = await ctx.new_page()
    await _войти(pg)
    await pg.goto(БАЗА + "/medkit", wait_until="networkidle")
    await pg.wait_for_timeout(900)

    print("── ширина %d ──" % ширина)
    await _кадр(pg, "строка-управления-%d" % ширина)

    # ПАНЕЛЬ И КНОПКА СКАНЕРА
    await pg.evaluate("() => аптАИОткрыть()")
    await pg.wait_for_timeout(700)
    await _кадр(pg, "панель-со-сканером-%d" % ширина)

    # ОКНО СКАНЕРА С ЖИВЫМ ВИДОИСКАТЕЛЕМ
    await pg.click("#apt-scan-open")
    await pg.wait_for_timeout(4000)
    await _кадр(pg, "окно-сканера-%d" % ширина)
    await pg.evaluate("() => закрыть_модалку('apt-scan')")
    await pg.wait_for_timeout(500)

    # ПОДСТАНОВКА ИЗ СВОЕЙ БАЗЫ — ответ ассистента
    await pg.evaluate("(к) => аптСканПрочитан(к)", КОД_ЗНАКОМЫЙ)
    await pg.wait_for_timeout(1800)
    await _кадр(pg, "код-узнан-%d" % ширина)

    # …и заполненная карточка С ПОМЕТКАМИ
    await pg.evaluate("""() => {
      const кн = [...document.querySelectorAll('#apt-ai-log button')].pop();
      if (кн) кн.click();
    }""")
    await pg.wait_for_timeout(1200)
    await _кадр(pg, "карточка-из-базы-%d" % ширина)
    await ctx.close()


async def main():
    from playwright.async_api import async_playwright
    os.makedirs(КУДА, exist_ok=True)
    print("СНИМКИ ЗАХОДА 163 — сканер кода и строка управления")
    print("стенд: %s" % БАЗА)
    print()
    async with async_playwright() as p:
        br = await p.chromium.launch(args=КЛЮЧИ_КАМЕРЫ)
        for ш in ШИРИНЫ:
            await снять(br, ш)
        await br.close()
    print()
    print("Кадры смотрит человек — кода «правильно» у этой пробы нет.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
