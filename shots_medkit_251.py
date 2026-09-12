# -*- coding: utf-8 -*-
"""СНИМКИ ЗАХОДА 251: обе формы аптечки во всех состояниях.

НЕ проверка, кадры смотрит человек. Ширины 2560, 1920 и 390 — у владельца
два монитора, 1440 среди них нет (тот же довод, что у задачи 143).

СОСТОЯНИЯ СНИМАЮТСЯ ПО ФАКТУ, а не по номеру позиции: первая карточка
сегодня одна, завтра другая. Правка снимается на позиции С ФОТО —
иначе превью в кадр не попадёт вовсе.

ПЕРЕМЕННЫЕ СТЕНДА ЧИТАЮТСЯ БЕЗ `window` (§5.8, блок E задачи 251):
`АПТ_ПОЗИЦИИ` объявлен через `let` и свойства `window` не создаёт.
"""
import asyncio
import os
import pathlib
import sys
import probe_guard  # noqa: F401  ПРОПУСК вместо трассы (§6.0.1)

sys.stdout.reconfigure(encoding="utf-8")

БАЗА = os.getenv("HOVER_BASE", "http://127.0.0.1:8899")
ПОЧТА = os.getenv("MEDKIT_EMAIL", "screenshot@local.dev")
ПАРОЛЬ = os.getenv("MEDKIT_PASSWORD", "Screenshot-Local-2026")
КУДА = pathlib.Path(os.getenv("SHOTS_DIR", "review_screenshots"))
ТЕГ = os.getenv("SHOTS_TAG", "before")
ШИРИНЫ = [int(ш) for ш in os.getenv("SHOT_WIDTHS", "2560,1920,390").split(",")]


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


ЗАВЕДЕНИЕ = "() => аптОткрытьФорму()"
ПРАВКА = r"""() => {
  let ц = null;
  АПТ_ПОЗИЦИИ.forEach(п => {
    (п['группа'] || [п]).forEach(у => { if (!ц && у.photo) ц = у; });
  });
  if (!ц) ц = АПТ_ПОЗИЦИИ[0];
  аптОткрытьФорму(ц);
}"""
ЗАКРЫТЬ = ("() => { document.querySelectorAll('.modal-ov.open')"
           ".forEach(м => м.classList.remove('open')); }")


async def _кадр(pg, имя, ширина):
    КУДА.mkdir(parents=True, exist_ok=True)
    путь = КУДА / ("251-%s-%s-%d.png" % (ТЕГ, имя, ширина))
    лист = await pg.query_selector(".modal-ov.open .modal-sh")
    if лист:
        await лист.screenshot(path=str(путь))
    else:
        await pg.screenshot(path=str(путь), full_page=True)
    print("  %s" % путь)


async def main():
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        br = await p.chromium.launch()
        ctx = await br.new_context(viewport={"width": 1920, "height": 1080})
        pg = await ctx.new_page()
        await _войти(pg)
        await pg.goto(БАЗА + "/medkit", wait_until="networkidle")
        print("СНИМКИ ЗАХОДА 251 (%s)" % ТЕГ)

        for ш in ШИРИНЫ:
            await pg.set_viewport_size({"width": ш, "height": 1200})
            for имя, js in (("зав", ЗАВЕДЕНИЕ), ("прав", ПРАВКА)):
                await pg.evaluate(ЗАКРЫТЬ)
                await pg.wait_for_timeout(150)
                await pg.evaluate(js)
                await pg.wait_for_timeout(600)
                await _кадр(pg, имя, ш)

                # РАСКРЫТЫЕ СОСТОЯНИЯ: категории и «Дополнительно».
                # Снимаются отдельным кадром — свёрнутое и раскрытое
                # это два разных облика, и один за другой не судят.
                раскрыто = await pg.evaluate(r"""() => {
                  let было = false;
                  const к = document.getElementById('apt-cats-more');
                  if (к) { к.click(); было = true; }
                  const д = document.querySelector('.apt-extra');
                  if (д && д.tagName === 'DETAILS') { д.open = true; было = true; }
                  const у = document.querySelector('.apt-url-more');
                  if (у) { у.open = true; было = true; }
                  return было;
                }""")
                if раскрыто:
                    await pg.wait_for_timeout(400)
                    await _кадр(pg, имя + "-раскрыто", ш)
        await br.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
