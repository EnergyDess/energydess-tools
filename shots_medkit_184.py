"""СНИМКИ ЗАХОДА 184 — ДЛЯ ПРИЁМКИ ВЛАДЕЛЬЦЕМ.

НЕ ПРОВЕРКА: кода «правильно» у неё нет, кадры смотрит человек.
Код возврата всегда 0.

Что снимается — ровно то, что просит пункт 5 постановки:

  1. СТРОКА С ПОИСКОМ И КНОПКАМИ (блоки B и C) — на трёх ширинах:
     где стоят органы и сколько между ними места;
  2. ВСЕ ЧЕТЫРЕ ВКЛАДКИ ПАНЕЛИ (блок D) — по кадру на вкладку,
     чтобы разброс высот было видно ГЛАЗОМ, а не только числом;
  3. ОТКАЗ ПРИ ПРИГЛАШЕНИИ ЧЕЛОВЕКА БЕЗ ДОСТУПА (блок A) — та самая
     фраза, которую увидит владелец;
  4. ПАНЕЛЬ, КОГДА ДОСТУП У УЧАСТНИКА ЗАБРАЛИ (блок A.3).

ШИРИНЫ 2560, 1920 И 390 — их назвал владелец; 1440 среди них нет
намеренно, экрана такой ширины у него не существует.

═══════════════════════════════════════════════════════════════════════
КРУГ ЗАВОДИТСЯ НАСТОЯЩИМ ПУТЁМ И УБИРАЕТСЯ ЗА СОБОЙ

Приглашение отправляется и принимается ЧЕРЕЗ ЭНДПОИНТЫ, а не
подставляется строками в базу: подставленный круг показал бы не то,
что увидит владелец, а то, что мы про него думаем.

Съёмка, оставившая за собой круг, сделала бы недостоверными и пиксельный
диф, и следующий прогон `check_medkit_circle` (§6.0.3, шестая причина
неповторимости — чужая проба, пишущая в ту же базу).

═══════════════════════════════════════════════════════════════════════
ЧЕЛОВЕК БЕЗ ДОСТУПА ЗАВОДИТСЯ ТУТ ЖЕ И ТУТ ЖЕ УБИРАЕТСЯ

Кадр 3 нужен на аккаунте, у которого инструмент НЕ открыт, а такого
на стенде по умолчанию нет. Заводить его в `make_local_user.py` значило
бы держать четвёртую фикстуру ради одного кадра; вместо этого доступ
СНИМАЕТСЯ У СОСЕДА и возвращается в `finally` — тем же приёмом, каким
это делает `check_medkit_circle`.
"""
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
КУДА = Path("review_screenshots") / "medkit-184"
ШИРИНЫ = [int(ш) for ш in
          os.environ.get("SHOT_WIDTHS", "2560,1920,390").split(",")]


def _прибрать():
    """Тем же кодом, что у пробы: второй реализации уборки нет."""
    import check_medkit_circle
    check_medkit_circle.прибрать()


def _доступ(uid_почта, дать):
    from database import SessionLocal, ToolAccess, User
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.email == uid_почта).first()
        есть = (db.query(ToolAccess)
                .filter(ToolAccess.user_id == u.id,
                        ToolAccess.tool_id == "medkit").first())
        if дать and not есть:
            db.add(ToolAccess(user_id=u.id, tool_id="medkit"))
        elif not дать and есть:
            db.delete(есть)
        db.commit()
    finally:
        db.close()


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
    сенсор = ширина <= 480
    ctx = await br.new_context(viewport={"width": ширина, "height": 1400},
                               has_touch=сенсор, is_mobile=сенсор)
    ctx2 = await br.new_context(viewport={"width": ширина, "height": 1400},
                                has_touch=сенсор, is_mobile=сенсор)
    pg, pg2 = await ctx.new_page(), await ctx2.new_page()
    try:
        await _войти(pg, ПОЧТА, ПАРОЛЬ)
        await _войти(pg2, СОСЕД, ПАРОЛЬ_СОСЕДА)

        # ── 1. СТРОКА С ПОИСКОМ И КНОПКАМИ (B, C) ──────────────────
        await pg.goto(БАЗА + "/medkit", wait_until="networkidle")
        await pg.wait_for_timeout(600)
        await _снять(pg, "строка-управления", ширина, ".apt-bar")
        # ВЕСЬ ВЕРХ СТРАНИЦЫ — чтобы видно было, что заголовок остался
        # заголовком, а органы уехали к списку
        await _снять(pg, "верх-страницы", ширина, ".apt-wrap")

        # ── 3. ОТКАЗ ПРИ ПРИГЛАШЕНИИ БЕЗ ДОСТУПА (A.2) ─────────────
        _доступ(СОСЕД, дать=False)
        await pg.evaluate("() => аптКругОткрыть()")
        await pg.wait_for_timeout(500)
        await pg.fill("#apt-circle-who", СОСЕД)
        await pg.click(".apt-circle-invite button[type=submit]")
        await pg.wait_for_timeout(900)
        await _снять(pg, "отказ-нет-доступа", ширина, "#apt-circle-body")
        _доступ(СОСЕД, дать=True)

        # ── 2. ЧЕТЫРЕ ВКЛАДКИ ПАНЕЛИ (D) ───────────────────────────
        # Круг заводится НАСТОЯЩИМ путём: иначе три вкладки из четырёх
        # пусты, и «высоты совпали» вышло бы про пустое состояние
        await pg.evaluate(ЗОВ, ["/medkit/api/circle/invite", "POST",
                                {"кого": СОСЕД}])
        о = await pg2.evaluate(ЗОВ, ["/medkit/api/circle", "GET", None])
        пришло = (о["тело"] or {}).get("полученные") or []
        if пришло:
            await pg2.evaluate(
                ЗОВ, ["/medkit/api/circle/invite/%d/accept" % пришло[0]["id"],
                      "POST", None])
        # ВТОРОЕ ПРИГЛАШЕНИЕ — чтобы вкладка «Приглашения» не была пуста
        await pg.evaluate(ЗОВ, ["/medkit/api/circle/invite", "POST",
                                {"кого": "unverified@local.dev"}])
        await pg.reload(wait_until="networkidle")
        await pg.wait_for_timeout(500)
        await pg.evaluate("() => аптКругОткрыть()")
        await pg.wait_for_timeout(600)
        for вкл, подпись in (("people", "участники"), ("invites", "приглашения"),
                             ("feed", "лента"), ("block", "блок")):
            await pg.click('#apt-circle [data-ctab="%s"]' % вкл)
            await pg.wait_for_timeout(350)
            # СНИМАЕТСЯ ОКНО ЦЕЛИКОМ, а не панель: прыгает на глазах
            # именно габарит окна, и по кадру панели этого не видно
            await _снять(pg, "вкладка-" + подпись, ширина,
                         "#apt-circle .modal-sh")

        # ── 4. ПАНЕЛЬ, КОГДА У УЧАСТНИКА ЗАБРАЛИ ДОСТУП (A.3) ──────
        _доступ(СОСЕД, дать=False)
        await pg.reload(wait_until="networkidle")
        await pg.wait_for_timeout(500)
        await pg.evaluate("() => аптКругОткрыть()")
        await pg.wait_for_timeout(600)
        await _снять(pg, "участник-без-доступа", ширина, "#apt-circle .modal-sh")
        _доступ(СОСЕД, дать=True)
    finally:
        await ctx.close()
        await ctx2.close()
        await br.close()


async def главная():
    async with async_playwright() as pw:
        for ш in ШИРИНЫ:
            print("── %d ──" % ш)
            await кадры(ш, pw)


if __name__ == "__main__":
    _прибрать()
    try:
        asyncio.run(главная())
    finally:
        # ДОСТУП ВОЗВРАЩАЕТСЯ ДАЖЕ ПРИ ПАДЕНИИ: съёмка, оставившая
        # соседа без инструмента, сломала бы следующую пробу молча
        _доступ(СОСЕД, дать=True)
        _прибрать()
        print("круг и приглашения убраны, доступ соседа возвращён")
