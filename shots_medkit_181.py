"""СНИМКИ ЗАХОДА 181 — ДЛЯ ПРИЁМКИ ВЛАДЕЛЬЦЕМ.

НЕ ПРОВЕРКА: кода «правильно» у неё нет, кадры смотрит человек.
Код возврата всегда 0.

Что снимается — ровно то, что просил пункт 5 постановки:

  1. ОКНО СПОСОБА ПРИЁМА ДЛЯ ПРЕПАРАТА Б — тот кадр, ради которого
     заведён блок A: схема «по 100-200 мг 3 раза/сут» на карточке
     обычных таблеток 200 мг, которой владелец не мог получить;
  2. ОКНО ДЛЯ ПРЕПАРАТЫ В СИРОПА — исход, где название и форма сошлись,
     а действующее вещество названо в справочнике иначе;
  3. ВСЕ ВОСЕМЬ СОСТОЯНИЙ ОКНА из C.2 — видно, где кнопка повтора
     есть, а где её нет;
  4. ВХОД В СПИСОК ПОКУПОК при ПУСТОМ и при НЕПУСТОМ списке — то,
     чего владелец не нашёл на своём экране (блок D).

ШИРИНЫ 2560 И 390 — их назвал владелец; 1440 среди них нет намеренно,
экрана такой ширины у него не существует.

═══════════════════════════════════════════════════════════════════════
ДАННЫЕ КАДРА ЗАВОДЯТСЯ САМИ И УБИРАЮТСЯ ЗА СОБОЙ

Ни «Препарата Б», ни «Препарата В» в аптечке стенда нет, список
покупок пуст, а восемь состояний окна не воспроизводятся ничем, кроме
подстановки исхода. Поэтому проба заводит своё и убирает в `finally`:
съёмка, оставившая за собой мусор, читается следующим заходом как
находка, а пиксельный диф на ней перестаёт быть повторимым (§6.0.3).

СОСТОЯНИЯ ПОДСТАВЛЯЮТСЯ В БАЗУ, а первые две позиции заводятся ЧЕРЕЗ
ФОРМУ: у них вопрос ровно в том, что ответит НАСТОЯЩИЙ поиск,
и подставленный ответ показывал бы не то, что увидит владелец.
"""
import argparse
import asyncio
import os
import sqlite3
import sys
from pathlib import Path

from playwright.async_api import async_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

БАЗА = os.environ.get("MEDKIT_BASE", "http://127.0.0.1:8899")
DB = os.environ.get("DB_PATH", "app.db")
ПОЧТА = "screenshot@local.dev"
ПАРОЛЬ = "Screenshot-Local-2026"
КУДА = Path("review_screenshots") / "medkit-181"
ШИРИНЫ = [2560, 390]

ПРЕПАРАТ Б = "Препарат Б"
СИРОП = "Препарат В сироп"
МЕТКА_ПОКУПОК = "проба 181"

# Те же восемь состояний, что спрашивает `check_medkit_ui --состояния`.
# Список НЕ КОПИРУЕТСЯ, а берётся оттуда: две копии разошлись бы молча,
# и кадры показывали бы не то, что проверяет проба (§6.0.7).
try:
    from check_medkit_ui import СОСТОЯНИЯ_ДОЗ
except Exception:                                    # pragma: no cover
    СОСТОЯНИЯ_ДОЗ = []

ПОЛЯ_ДОЗ = ("dosage_text", "dosage_source", "dosage_url", "dosage_blocks",
            "dosage_miss", "dosage_miss_at", "dosage_miss_kind")


def _из_базы(запрос, параметры=()):
    conn = sqlite3.connect(DB)
    try:
        return conn.execute(запрос, параметры).fetchall()
    finally:
        conn.close()


def _в_базу(запрос, параметры=()):
    conn = sqlite3.connect(DB)
    try:
        conn.execute(запрос, параметры)
        conn.commit()
    finally:
        conn.close()


def _прибрать():
    for имя in (ПРЕПАРАТ Б, СИРОП):
        _в_базу("DELETE FROM medkit_items WHERE name = ?", (имя,))
    _в_базу("DELETE FROM medkit_buy_items WHERE name LIKE ?",
            ("%" + МЕТКА_ПОКУПОК + "%",))


async def _войти(pg):
    await pg.goto(БАЗА + "/login", wait_until="domcontentloaded")
    await pg.fill("input[name=email]", ПОЧТА)
    await pg.fill("input[name=password]", ПАРОЛЬ)
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


ЗАВЕСТИ = """async (д) => {
  const тело = Object.assign({qty_left: 10, qty_total: 20,
    expires_ym: '2027-09', is_rx: false}, д);
  тело['категории'] = [];
  const т = await fetch('/medkit/api/items', {method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(тело)});
  return await т.json();
}"""


async def _завести(pg, имя, вещество, форма, единица, доза):
    """Позиция ЧЕРЕЗ ФОРМУ — чтобы отработал фоновый поиск схемы.

    Ждёт, пока фон запишет исход; не дождался — ГОВОРИТ ОБ ЭТОМ,
    а не снимает молча кадр другого состояния. Фону нужна СЕТЬ
    (Видаль), и съёмка от неё зависит — это цена того, что кадр
    показывает настоящий ответ, а не подставленный.
    """
    ответ = await pg.evaluate(ЗАВЕСТИ, {
        "name": имя, "substance": вещество, "form": форма,
        "unit": единица, "dose": доза})
    ид = (ответ or {}).get("id")
    if not ид:
        print("   %s не завёлся: %r" % (имя, ответ))
        return None
    for _ in range(40):
        с = _из_базы("SELECT dosage_text, dosage_miss FROM medkit_items"
                     " WHERE id = ?", (ид,))
        if с and (с[0][0] or с[0][1]):
            чем = (("схема, %d знаков" % len(с[0][0])) if с[0][0]
                   else (с[0][1] or "")[:70])
            print("   %s — фон ответил: %s" % (имя, чем))
            return ид
        await pg.wait_for_timeout(500)
    print("   %s — ФОН НЕ ОТВЕТИЛ за 20 с; нужна сеть до Видаля" % имя)
    return ид


async def _окно(pg, ид, имя_кадра, ширина):
    await pg.goto(БАЗА + "/medkit", wait_until="networkidle")
    кн = await pg.query_selector("[data-doses='%d']" % ид)
    if not кн:
        print("   ПРОПУЩЕН %s — кнопки приёма у позиции нет" % имя_кадра)
        return
    await кн.click()
    await pg.wait_for_timeout(500)
    await _снять(pg, имя_кадра, ширина, "#apt-doses .modal-sh")
    await pg.keyboard.press("Escape")


def _поставить_состояние(ид, вид, текст):
    if текст:
        _в_базу("UPDATE medkit_items SET dosage_text=?, dosage_source='Видаль',"
                " dosage_url='https://www.vidal.ru/x', dosage_blocks=NULL,"
                " dosage_miss=NULL, dosage_miss_at=NULL, dosage_miss_kind=NULL"
                " WHERE id=?", (текст, ид))
    elif вид == "":
        _в_базу("UPDATE medkit_items SET dosage_text=NULL, dosage_source=NULL,"
                " dosage_url=NULL, dosage_blocks=NULL, dosage_miss=NULL,"
                " dosage_miss_at=NULL, dosage_miss_kind=NULL WHERE id=?", (ид,))
    else:
        _в_базу("UPDATE medkit_items SET dosage_text=NULL, dosage_source=NULL,"
                " dosage_url=NULL, dosage_blocks=NULL, dosage_miss=?,"
                " dosage_miss_at=datetime('now'), dosage_miss_kind=?"
                " WHERE id=?", ("причина вида «%s»" % вид, вид, ид))


async def кадры(pg, ширина):
    print(" ── кадры на %d ──" % ширина)

    # ── 1 · ПРЕПАРАТ Б: ТОТ САМЫЙ КАДР БЛОКА A ────────────────────────
    ид_н = await _завести(pg, ПРЕПАРАТ Б, "Тримебутин, 200 мг",
                          "tablet", "tablet", 1)
    if ид_н:
        await _окно(pg, ид_н, "okno-preparat_b", ширина)

    # ── 2 · ПРЕПАРАТЫ В СИРОП ───────────────────────────────────────────
    ид_с = await _завести(pg, СИРОП, "Вещество В густой экстракт, 4 г",
                          "syrup", "ml", 5)
    if ид_с:
        await _окно(pg, ид_с, "okno-solodka", ширина)

    # ── 3 · ВОСЕМЬ СОСТОЯНИЙ ОКНА (C.2) ─────────────────────────────
    #
    # Подставляются В БАЗУ той же позиции: вопрос кадра — какие действия
    # предлагает окно, а не что именно ответил справочник. Исходное
    # состояние возвращается в `finally`.
    if ид_н and СОСТОЯНИЯ_ДОЗ:
        было = _из_базы("SELECT %s FROM medkit_items WHERE id=?"
                        % ",".join(ПОЛЯ_ДОЗ), (ид_н,))[0]
        try:
            for имя, вид, текст, _ждём in СОСТОЯНИЯ_ДОЗ:
                _поставить_состояние(ид_н, вид, текст)
                метка = "sost-" + (вид or ("naideno" if текст else "nikogda"))
                await _окно(pg, ид_н, метка, ширина)
        finally:
            _в_базу("UPDATE medkit_items SET %s WHERE id=?"
                    % ",".join("%s=?" % п for п in ПОЛЯ_ДОЗ),
                    tuple(было) + (ид_н,))

    # ── 4 · ВХОД В СПИСОК ПОКУПОК: ПУСТОЙ И НЕПУСТОЙ ────────────────
    _в_базу("DELETE FROM medkit_buy_items WHERE name LIKE ?",
            ("%" + МЕТКА_ПОКУПОК + "%",))
    await pg.goto(БАЗА + "/medkit", wait_until="networkidle")
    await _снять(pg, "pokupki-pusto-svernut", ширина, "#apt-buy")
    await pg.goto(БАЗА + "/medkit?buy=1", wait_until="networkidle")
    await _снять(pg, "pokupki-pusto-razvernut", ширина, "#apt-buy")

    хозяин = _из_базы("SELECT id FROM users WHERE email = ?", (ПОЧТА,))
    if хозяин:
        for имя, почему in (("Ибупрофен (%s)" % МЕТКА_ПОКУПОК, "кончился"),
                            ("Пластырь (%s)" % МЕТКА_ПОКУПОК, "")):
            # `is_rx` объявлен NOT NULL без умолчания — строка без него
            # не заводится вовсе. Замер: первая версия падала
            # IntegrityError уже ПОСЛЕ двух снятых кадров
            _в_базу("INSERT INTO medkit_buy_items (user_id, name, why,"
                    " source, is_rx, created_at)"
                    " VALUES (?,?,?,?,0,datetime('now'))",
                    (хозяин[0][0], имя, почему, "hand"))
    await pg.goto(БАЗА + "/medkit", wait_until="networkidle")
    await _снять(pg, "pokupki-est-svernut", ширина, "#apt-buy")
    await pg.goto(БАЗА + "/medkit?buy=1", wait_until="networkidle")
    await _снять(pg, "pokupki-est-razvernut", ширина, "#apt-buy")


async def прогон(ширина):
    async with async_playwright() as pw:
        br = await pw.chromium.launch()
        ctx = await br.new_context(viewport={"width": ширина, "height": 1100},
                                   has_touch=(ширина <= 480),
                                   is_mobile=(ширина <= 480))
        pg = await ctx.new_page()
        try:
            await _войти(pg)
            await кадры(pg, ширина)
        finally:
            _прибрать()
            await br.close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ширина", type=int, default=0)
    a = p.parse_args()
    print("=" * 70)
    print("СНИМКИ ЗАХОДА 181 → %s" % КУДА)
    print("=" * 70)
    _прибрать()
    for ш in ([a.ширина] if a.ширина else ШИРИНЫ):
        asyncio.run(прогон(ш))
    print()
    print("готово. Кадры смотрит человек — кода «правильно» тут нет.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
