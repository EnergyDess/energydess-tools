# -*- coding: utf-8 -*-
"""СНИМКИ ЗАХОДА 207: метка источника у двух справочников.

BACKLOG №207, блок E.4. НЕ проверка — кадры смотрит человек, код
возврата всегда 0.

═══════════════════════════════════════════════════════════════════════
ЧТО СНИМАЕТСЯ И ПОЧЕМУ ИМЕННО ЭТО
═══════════════════════════════════════════════════════════════════════

Три состояния окна способа приёма, отличающиеся РОВНО меткой источника:
схема из wer.ru, схема из Видаля, отказ. Вопрос кадра один — видит ли
человек, ЧЕЙ текст читает (E.1).

═══════════════════════════════════════════════════════════════════════
СОСТОЯНИЕ ПОДСТАВЛЯЕТСЯ В БАЗУ СТЕНДА, И ЭТО НАЗВАНО
═══════════════════════════════════════════════════════════════════════

Обычно проба заводит состояние НАСТОЯЩИМ путём — подставленное
показывало бы не то, что увидит владелец. Здесь исключение, и у него
две причины, обе замеренные:

  1. ВОПРОС КАДРА — ПРО ПОКАЗ, А НЕ ПРО ДОБЫЧУ. Метку рисует сервер
     из колонки `dosage_source`, и путь показа у подставленной записи
     ТОТ ЖЕ САМЫЙ. Что запись туда попадает верно, доказывает боевой
     прогон `check_medkit_all`, а не снимок.

  2. ЖИВОЙ ПУТЬ С МАШИНЫ РАЗРАБОТЧИКА НЕ ВОСПРОИЗВОДИТСЯ. Замер
     2026-09-04: wer.ru отвечает то за 106 с, то не отвечает вовсе,
     а базовая линия при отказе выключает источник целиком — то есть
     кадр «схема из wer.ru» зависел бы от везения.

ТЕКСТ ВЫДЕРЖКИ БЕРЁТСЯ ИЗ ОБРАЗЦА ЖИВОЙ СТРАНИЦЫ, а не выдумывается:
разбирается тот же `tests/fixtures/sources`, которым проверяется
вёрстка. Выдуманный текст показал бы разметку, которой у источника нет.

    py shots_medkit_207.py
"""

import asyncio
import glob
import gzip
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.environ.setdefault("DB_PATH", "app.db")

import medkit_dosage as дозы            # noqa: E402
import medkit_sources as источники      # noqa: E402

БАЗА = os.getenv("HOVER_BASE", "http://127.0.0.1:8899")
ПОЧТА = "screenshot@local.dev"
ПАРОЛЬ = "Screenshot-Local-2026"
КУДА = "review_screenshots"
ШИРИНЫ = (2560, 390)


def _образец(домен, шаблон):
    каталог = os.path.join("tests", "fixtures", "sources",
                           домен.replace(".", "_"))
    для = sorted(glob.glob(os.path.join(каталог, шаблон)))
    if not для:
        return None
    return gzip.open(для[0], "rt", encoding="utf-8", errors="replace").read()


def подставить():
    """Три позиции с разными источниками. Возвращает их id.

    ВОЗВРАЩАЕТ И ПРЕЖНЕЕ СОСТОЯНИЕ: снимок, оставляющий стенд не таким,
    каким взял, ломает не свой прогон, а следующий (§6.0.3).
    """
    import database
    from datetime import datetime
    db = database.SessionLocal()
    try:
        поз = (db.query(database.MedkitItem)
               .order_by(database.MedkitItem.id).limit(3).all())
        if len(поз) < 3:
            print("СПРОСИТЬ НЕЧЕМ: на стенде меньше трёх позиций.")
            print("Пересейте: py make_local_user.py --seed")
            return None, None
        было = [(п.id, п.dosage_text, п.dosage_blocks, п.dosage_source,
                 п.dosage_url, п.dosage_fetched_at, п.dosage_miss,
                 п.dosage_miss_kind, п.indications_text,
                 п.indications_blocks) for п in поз]
        # ── 1. СХЕМА ИЗ WER.RU ──────────────────────────────────────
        стр = _образец("wer.ru", "citramon*.html.gz")
        _з, кусок = источники.WER.раздел_доз(стр or "")
        текст, блоки = дозы.разметить(кусок) if кусок else ("", None)
        _зп, кусокп = источники.WER.раздел_показаний(стр or "")
        птекст, пблоки = дозы.разметить(кусокп) if кусокп else ("", None)
        поз[0].dosage_text = текст
        поз[0].dosage_blocks = (json.dumps(блоки, ensure_ascii=False)
                                if блоки else None)
        поз[0].dosage_source = источники.WER.имя
        поз[0].dosage_url = источники.WER.база + "/catalog/obrazec/"
        поз[0].dosage_fetched_at = datetime.utcnow()
        поз[0].dosage_miss = None
        поз[0].dosage_miss_kind = None
        поз[0].indications_text = птекст
        поз[0].indications_blocks = (json.dumps(пблоки, ensure_ascii=False)
                                     if пблоки else None)
        # ── 2. СХЕМА ИЗ ВИДАЛЯ ──────────────────────────────────────
        стрв = _образец("vidal.ru", "[0-9a-f]*.html.gz")
        _з2, кусок2 = источники.ВИДАЛЬ.раздел_доз(стрв or "")
        текст2, блоки2 = дозы.разметить(кусок2) if кусок2 else ("", None)
        поз[1].dosage_text = текст2
        поз[1].dosage_blocks = (json.dumps(блоки2, ensure_ascii=False)
                                if блоки2 else None)
        поз[1].dosage_source = источники.ВИДАЛЬ.имя
        поз[1].dosage_url = источники.ВИДАЛЬ.база + "/drugs/obrazec"
        поз[1].dosage_fetched_at = datetime.utcnow()
        поз[1].dosage_miss = None
        поз[1].dosage_miss_kind = None
        поз[1].indications_text = None
        поз[1].indications_blocks = None
        # ── 3. ОТКАЗ ────────────────────────────────────────────────
        поз[2].dosage_text = None
        поз[2].dosage_blocks = None
        поз[2].dosage_source = None
        поз[2].dosage_url = None
        поз[2].indications_text = None
        поз[2].indications_blocks = None
        поз[2].dosage_miss = ("под описание подошло несколько препаратов "
                              "с РАЗНЫМИ схемами приёма — какой именно "
                              "у вас в руках, решать не нам")
        поз[2].dosage_miss_at = datetime.utcnow()
        поз[2].dosage_miss_kind = "неоднозначно"
        db.commit()
        print("подставлено: id %d (wer.ru, %d зн), id %d (Видаль, %d зн), "
              "id %d (отказ)" % (поз[0].id, len(текст or ""),
                                 поз[1].id, len(текст2 or ""), поз[2].id))
        return [п.id for п in поз], было
    finally:
        db.close()


def вернуть(было):
    if not было:
        return
    import database
    db = database.SessionLocal()
    try:
        for (ид, т, б, и, у, д, м, мк, пт, пб) in было:
            п = db.query(database.MedkitItem).get(ид)
            if not п:
                continue
            (п.dosage_text, п.dosage_blocks, п.dosage_source, п.dosage_url,
             п.dosage_fetched_at, п.dosage_miss, п.dosage_miss_kind,
             п.indications_text, п.indications_blocks) = (т, б, и, у, д, м,
                                                          мк, пт, пб)
        db.commit()
        print("стенд возвращён в прежнее состояние")
    finally:
        db.close()


async def снять(ид):
    from playwright.async_api import async_playwright
    os.makedirs(КУДА, exist_ok=True)
    async with async_playwright() as pw:
        бр = await pw.chromium.launch()
        for ширина in ШИРИНЫ:
            ctx = await бр.new_context(
                viewport={"width": ширина, "height": 900},
                device_scale_factor=1,
                has_touch=(ширина <= 640), is_mobile=(ширина <= 640))
            стр = await ctx.new_page()
            await стр.goto(БАЗА + "/login")
            await стр.fill("input[name=email]", ПОЧТА)
            await стр.fill("input[name=password]", ПАРОЛЬ)
            await стр.click("button[type=submit]")
            await стр.wait_for_load_state("networkidle")
            await стр.goto(БАЗА + "/medkit")
            await стр.wait_for_load_state("networkidle")
            await стр.wait_for_timeout(700)
            for подпись, поз_ид in (("wer", ид[0]), ("vidal", ид[1]),
                                    ("otkaz", ид[2])):
                кнопка = стр.locator('[data-doses="%d"]' % поз_ид)
                try:
                    await кнопка.first.click(timeout=4000)
                except Exception:
                    # ЗАПАСНОЙ ПУТЬ НАЗЫВАЕТСЯ, а не молчит: разметка
                    # кнопки могла смениться, и кадр без окна лучше
                    # кадра, выданного за окно
                    print("   %s: кнопку окна найти не удалось" % подпись)
                    continue
                await стр.wait_for_timeout(900)
                имя = "%s/207_%s_%d.png" % (КУДА, подпись, ширина)
                await стр.screenshot(path=имя)
                print("   снят %s" % имя)
                await стр.keyboard.press("Escape")
                await стр.wait_for_timeout(400)
            await ctx.close()
        await бр.close()


def главное():
    ид, было = подставить()
    if not ид:
        return 0
    try:
        asyncio.run(снять(ид))
    finally:
        вернуть(было)
    return 0


if __name__ == "__main__":
    sys.exit(главное())
