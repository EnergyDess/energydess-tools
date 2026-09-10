# -*- coding: utf-8 -*-
"""ЗА КОГО ЗАПИСАН ПРИЁМ: три места, одна запись (BACKLOG №260).

ПРОВЕРКА, код 1 при беде: здесь спрашивается НАШ код, а не чужой сайт.
Сети не требует вовсе — вопрос «кто записан автором» к доступности
справочника отношения не имеет.

═══════════════════════════════════════════════════════════════════════
ЧЕГО НЕ СПРАШИВАЛ НИКТО

У записи о приёме ДВА лица: кто НАЖАЛ и ЗА КОГО записано. До этой
задачи второго не существовало вовсе, и «Зина — приём: Препарат А»
означало сразу два разных факта — «Зина выпила» и «Зина дала выпить
матери». Ни одна из сорока с лишним проб такого не берёт: они меряют
ОБЛИК, ОТВЕТ СЕРВЕРА и СОДЕРЖИМОЕ БАЗЫ по ОДНОМУ лицу, а вопрос
«не подменилось ли второе» задать было нечем.

РЕЗУЛЬТАТ ЧИТАЕТСЯ ИЗ БАЗЫ, А НЕ ИЗ ОТВЕТА СЕРВЕРА (§6.3). Оба поля
лежат в строке `medkit_events`, и «ответил 200» о том, что именно
в неё легло, не говорит ничего.

ПОДЛОГИ КЛАДУТСЯ В СТРАНИЦУ, кода экрана они не трогают. У КАЖДОГО
СТОИТ ДОКАЗАТЕЛЬСТВО (§6.0.3): независимый замер того, что подлог
СОСТОЯЛСЯ. Без него «проба нашла» неотличимо от «нашла по другой
причине», а «не нашла» — от «подлог не сработал».

ПИШЕТ В БАЗУ и требует поднятого стенда; в ряды §6.0.2 не входит
по обеим причинам.
"""
import argparse
import asyncio
import os
import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8")

БАЗА = os.getenv("HOVER_BASE", "http://127.0.0.1:8899")
ПОЧТА = os.getenv("MEDKIT_EMAIL", "screenshot@local.dev")
ПАРОЛЬ = os.getenv("MEDKIT_PASSWORD", "Screenshot-Local-2026")
ФАЙЛ_БАЗЫ = os.getenv("DB_PATH", "app.db")

ПЛОХО = []
ШАГОВ = [0]
ДОКАЗАНО = {}


def шаг(имя, ок, чем=""):
    ШАГОВ[0] += 1
    if not ок:
        ПЛОХО.append(имя)
    print("  %-5s %-44s %s" % ("OK" if ок else "ПЛОХО", имя, чем))
    return ок


def событие(ид=None):
    """Поля события ИЗ БАЗЫ. Оба лица рядом — иначе не увидеть подмены."""
    c = sqlite3.connect(ФАЙЛ_БАЗЫ)
    try:
        если = "WHERE id = ?" if ид else ""
        арг = (ид,) if ид else ()
        r = c.execute(
            "SELECT id, kind, user_id, for_user_id, name, detail "
            "FROM medkit_events %s ORDER BY id DESC LIMIT 1" % если, арг).fetchone()
    finally:
        c.close()
    if not r:
        return None
    return {"id": r[0], "вид": r[1], "нажал": r[2], "за_кого": r[3],
            "name": r[4], "detail": r[5]}


def остаток(item_id):
    c = sqlite3.connect(ФАЙЛ_БАЗЫ)
    try:
        r = c.execute("SELECT qty_left FROM medkit_items WHERE id = ?",
                      (item_id,)).fetchone()
    finally:
        c.close()
    return r[0] if r else None


async def войти(pg):
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


async def открыть_упаковки(pg):
    """Окно упаковок первой группы. Возвращает id карточки."""
    кид = await pg.evaluate(
        "() => { const s = document.querySelector('.apt-packs-src');"
        "        return s ? s.id.replace('apt-packs-','') : null; }")
    if not кид:
        raise SystemExit("НА СТЕНДЕ НЕТ ГРУППЫ ИЗ НЕСКОЛЬКИХ ПАЧЕК — мерить "
                         "нечего (§8.0). Пересейте: py make_local_user.py --seed")
    await pg.click("[data-packs='%s']" % кид)
    await pg.wait_for_timeout(700)
    return кид


async def выбрать_чужого(pg, кнопка):
    """Раскрыть выбор у названной кнопки и ткнуть НЕ в себя."""
    await pg.click(кнопка)
    await pg.wait_for_timeout(500)
    чужой = await pg.evaluate(
        "() => { const b = [...document.querySelectorAll('#apt-who-list [data-who]')]"
        "        .find(x => (x.textContent||'').trim() !== 'Вы');"
        "        return b ? Number(b.dataset.who) : null; }")
    if not чужой:
        raise SystemExit("В КРУГЕ НЕТ ВТОРОГО УЧАСТНИКА — мерить нечего (§8.0)")
    await pg.click("#apt-who-list [data-who='%d']" % чужой)
    await pg.wait_for_timeout(500)
    return чужой


ВИД_ОКНА = """() => {
  const стр = document.getElementById('apt-packs-for');
  const li = document.querySelectorAll('#apt-packs-body li.apt-pack');
  const кн = li.length ? li[0].querySelector('[data-take]') : null;
  const п = кн ? кн.querySelector('.apt-pack-take-t') : null;
  const к = п ? п.getBoundingClientRect() : null;
  const срок = li.length ? li[0].querySelector('.apt-pack-sub .apt-pack-v') : null;
  return {
    строка: !!стр,
    подпись: стр ? (стр.querySelector('.apt-for-name')||{}).textContent : '',
    видна_подпись: !!(к && к.width > 0 && к.height > 0),
    текст_подписи: п ? (п.textContent||'').trim() : '',
    срок_моно: срок ? /mono/i.test(getComputedStyle(срок).fontFamily) : false,
    гнездо: Math.round(document.getElementById('apt-packs-for-slot')
                       .getBoundingClientRect().height)
  };
}"""

ВИД_ПОЛОСЫ = """() => {
  const b = document.getElementById('undo-bar');
  const after = getComputedStyle(b, '::after');
  return {видна: b.classList.contains('show'),
          значок: !!b.querySelector('.undo-bar-ok svg'),
          отсчёт_высота: after.height,
          отсчёт_есть: after.content !== 'none',
          окно: getComputedStyle(b).getPropertyValue('--undo-window').trim(),
          вернуть: !document.getElementById('undo-bar-undo').hidden,
          другой: !document.getElementById('undo-bar-who').hidden,
          за_кем: document.getElementById('undo-bar-for').hidden ? ''
                  : (document.getElementById('undo-bar-for-name')||{}).textContent};
}"""

ВИД_ЛЕНТЫ = """() => {
  const li = [...document.querySelectorAll('.apt-feed-item')];
  const с = li.map(l => ({карандаш: !!l.querySelector('[data-event-who]'),
                          текст: (l.querySelector('.apt-feed-txt')||{}).textContent||''}));
  const л = document.querySelector('.apt-feed');
  const п = л ? л.parentElement : null;
  let справа = null, прокрутка = false;
  if (л && п) {
    справа = Math.round(п.getBoundingClientRect().right - л.getBoundingClientRect().right);
    прокрутка = л.scrollHeight > л.clientHeight + 1;
  }
  return {всего: li.length,
          с_карандашом: с.filter(x => x.карандаш).length,
          приёмов: с.filter(x => x.текст.indexOf(' — приём') >= 0).length,
          за_кого_в_тексте: с.filter(x => x.текст.indexOf(' — приём за ') >= 0).length,
          справа: справа, прокрутка: прокрутка};
}"""


async def проход(pg):
    await pg.goto(БАЗА + "/medkit", wait_until="networkidle")
    await pg.wait_for_selector(".apt-card", timeout=20000)
    я = await pg.evaluate("() => (АПТ_УЧАСТНИКИ.find(ч => ч.свой)||{}).id")

    print("── B. ОКНО УПАКОВОК: ПРИЁМ И ВЫБОР УЧАСТНИКА ──")
    await открыть_упаковки(pg)
    вид = await pg.evaluate(ВИД_ОКНА)
    шаг("строка-отмечаю-за-есть", вид["строка"])
    шаг("по-умолчанию-за-себя", (вид["подпись"] or "").strip() == "себя",
        "подпись %r" % (вид["подпись"] or "").strip())
    шаг("подпись-кнопки-приёма-видна", вид["видна_подпись"],
        "%r" % вид["текст_подписи"])
    шаг("срок-моноширинным", вид["срок_моно"])
    шаг("выбор-свёрнут-при-открытии", вид["гнездо"] == 0,
        "гнездо %d px" % вид["гнездо"])

    чужой = await выбрать_чужого(pg, "#apt-packs-for-btn")
    после = await pg.evaluate(ВИД_ОКНА)
    шаг("подпись-сменилась-на-соседа",
        (после["подпись"] or "").strip() not in ("", "себя"),
        "подпись %r" % (после["подпись"] or "").strip())
    шаг("выбор-свернулся-после-нажатия", после["гнездо"] == 0)

    пачка2 = await pg.evaluate(
        "() => { const li = document.querySelectorAll('#apt-packs-body li.apt-pack');"
        "        const b = li[1] && li[1].querySelector('[data-take]');"
        "        return b ? Number(b.dataset.take) : null; }")
    ост_до = остаток(пачка2)
    await pg.click("#apt-packs-body li.apt-pack:nth-child(2) [data-take]")
    await pg.wait_for_timeout(1400)
    e = событие()
    шаг("в-базе-приём-ЗА-СОСЕДА",
        bool(e) and e["вид"] == "take" and e["за_кого"] == чужой,
        "нажал=%s заКого=%s" % (e and e["нажал"], e and e["за_кого"]))
    шаг("кто-НАЖАЛ-не-подменён", bool(e) and e["нажал"] == я,
        "нажал=%s, я=%s" % (e and e["нажал"], я))
    шаг("списано-из-ВТОРОЙ-пачки", остаток(пачка2) != ост_до,
        "остаток %s → %s" % (ост_до, остаток(пачка2)))

    сброс = await pg.evaluate(ВИД_ОКНА)
    шаг("выбор-СБРОШЕН-после-приёма",
        (сброс["подпись"] or "").strip() == "себя",
        "подпись %r" % (сброс["подпись"] or "").strip())
    ДОКАЗАНО["сброс"] = (сброс["подпись"] or "").strip()

    # ГЛАВНЫЙ ВОПРОС B.6 — ВТОРОЙ ПРИЁМ ПОДРЯД
    await pg.click("#apt-packs-body li.apt-pack:nth-child(2) [data-take]")
    await pg.wait_for_timeout(1400)
    e2 = событие()
    шаг("второй-приём-ушёл-ЗА-СЕБЯ", bool(e2) and e2["за_кого"] == я,
        "заКого=%s, я=%s" % (e2 and e2["за_кого"], я))

    print()
    print("── C. ПОЛОСА ПОДТВЕРЖДЕНИЯ ──")
    полоса = await pg.evaluate(ВИД_ПОЛОСЫ)
    шаг("значок-успеха", полоса["значок"])
    шаг("ПОЛОСА-ВРЕМЕНИ-НА-МЕСТЕ",
        полоса["отсчёт_есть"] and полоса["отсчёт_высота"] not in ("", "0px", "auto"),
        "линия %s, окно %s" % (полоса["отсчёт_высота"], полоса["окно"]))
    шаг("кнопка-вернуть-на-месте", полоса["вернуть"])
    шаг("кнопка-другой-человек", полоса["другой"])
    ДОКАЗАНО["полоса_время"] = полоса["отсчёт_высота"]

    было = событие()
    # ОСТАТОК СНИМАЕТСЯ ДО ПРАВКИ. Первая версия брала его ПОСЛЕ
    # и сравнивала сама с собой — шаг проходил при любом подлоге,
    # и поймало это ДОКАЗАТЕЛЬСТВО, а не вердикт пробы (§6.0.3)
    ост_до_правки = остаток(пачка2)
    чужой2 = await выбрать_чужого(pg, "#undo-bar-who")
    await pg.wait_for_timeout(1000)
    стало = событие(было["id"])
    шаг("полоса-переписала-ЗА-КОГО",
        стало["за_кого"] == чужой2 and было["за_кого"] != чужой2,
        "%s → %s" % (было["за_кого"], стало["за_кого"]))
    ост_после = остаток(пачка2)
    поля = [к for к in ("вид", "нажал", "name", "detail") if было[к] != стало[к]]
    шаг("НИЧЕГО-КРОМЕ-ЗА-КОГО-не-изменилось", not поля,
        "изменилось ещё: %s" % (поля or "ничего"))
    шаг("остаток-НЕ-пересчитан-правкой", ост_после == ост_до_правки,
        "остаток %s → %s" % (ост_до_правки, ост_после))
    ДОКАЗАНО["остаток"] = "%s→%s" % (ост_до_правки, ост_после)

    print()
    print("── D. ЛЕНТА ──")
    await pg.evaluate("() => закрыть_модалку('apt-packs-win')")
    await pg.wait_for_timeout(500)
    await pg.click("#apt-circle-open")
    await pg.wait_for_timeout(900)
    await pg.click("[data-ctab='feed']")
    await pg.wait_for_timeout(600)
    лента = await pg.evaluate(ВИД_ЛЕНТЫ)
    шаг("карандаш-ТОЛЬКО-у-приёма",
        лента["с_карандашом"] == лента["приёмов"] and лента["приёмов"] > 0,
        "строк %d, приёмов %d, с карандашом %d"
        % (лента["всего"], лента["приёмов"], лента["с_карандашом"]))
    шаг("текст-называет-ОБОИХ", лента["за_кого_в_тексте"] > 0,
        "строк «приём за» %d" % лента["за_кого_в_тексте"])
    ДОКАЗАНО["карандашей"] = лента["с_карандашом"]

    цель_стр = await pg.evaluate(
        "() => { const b = document.querySelector('[data-event-who]');"
        "        return b ? {ид: Number(b.dataset.eventWho),"
        "                    кто: Number(b.dataset.whoNow)} : null; }")
    было_л = событие(цель_стр["ид"])
    await pg.click("[data-event-who='%d']" % цель_стр["ид"])
    await pg.wait_for_timeout(500)
    цель = await pg.evaluate(
        "() => { const b = [...document.querySelectorAll('#apt-who-list [data-who]')]"
        "        .find(x => !x.classList.contains('is-on'));"
        "        return b ? Number(b.dataset.who) : null; }")
    ост_л_до = остаток(пачка2)
    if цель:
        await pg.click("#apt-who-list [data-who='%d']" % цель)
        await pg.wait_for_timeout(1200)
    стало_л = событие(цель_стр["ид"])
    шаг("лента-переписала-ЗА-КОГО", стало_л["за_кого"] == цель,
        "%s → %s (ждали %s)" % (было_л["за_кого"], стало_л["за_кого"], цель))
    поля_л = [к for к in ("вид", "нажал", "name", "detail")
              if было_л[к] != стало_л[к]]
    шаг("из-ленты-меняется-РОВНО-ОДНО-поле", not поля_л,
        "изменилось ещё: %s" % (поля_л or "ничего"))
    шаг("правка-из-ленты-НЕ-трогает-остаток", остаток(пачка2) == ост_л_до,
        "остаток %s" % ост_л_до)
    if лента["справа"] is not None:
        print("     лента: до правого края %s px, прокрутка %s"
              % (лента["справа"], лента["прокрутка"]))


async def прогон(подлог=None):
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        br = await p.chromium.launch(headless=True)
        pg = await br.new_page(viewport={"width": 1920, "height": 1080})
        if подлог:
            await pg.add_init_script(подлог)
        await войти(pg)
        try:
            await проход(pg)
        finally:
            await pg.close()
            await br.close()


# ═══════════════════════════════════════════════════════════════════
# ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ
# ═══════════════════════════════════════════════════════════════════
#
# ПЕРЕМЕННЫЕ СТЕНДА ЧИТАЮТСЯ БЕЗ `window` (проверка 30): `АПТ_ЗА_КОГО`
# объявлена через `let`, свойством `window` она не становится вовсе.
# Поэтому подлог подменяет ФУНКЦИЮ, а не переменную: функции верхнего
# уровня классического скрипта на `window` лежат.
#
# ЧЕТВЁРТЫЙ ПОДЛОГ ОБРАТНЫЙ: законная правка обязана ПРОЙТИ. Без него
# «заслон ловит всё» неотличимо от «путь не работает вовсе» (§6.0.3).

ПОДЛОГИ = {
    # B.6 наизнанку: выбор переживает приём, и ВТОРОЕ нажатие уходит
    # тому же человеку — ровно то, ради чего сброс и заведён
    "сброс-выбора-выключен": (
        # ПОДМЕНЯЕТСЯ ТА ЖЕ ФУНКЦИЯ, ЧТО ЗОВЁТ ПРИЁМ. Первая версия
        # била по `аптЗаКогоСброс`, когда приём обнулял переменную
        # двумя строками у себя, — подлог не состоялся, и показало
        # это ДОКАЗАТЕЛЬСТВО («сброс: себя»), а не вердикт пробы
        "window.addEventListener('load', () => {"
        "  window.аптЗаКогоСброс = function () { аптЗаКогоПодпись(); };"
        "});",
        "второй-приём-ушёл-ЗА-СЕБЯ"),
    # C.2/D.2 наизнанку: путь правки трогает количество
    "правка-меняет-остаток": (
        "window.addEventListener('load', () => {"
        "  const было = window.аптСобытиеЗаКого;"
        "  window.аптСобытиеЗаКого = async function (с, ч, потом) {"
        "    await было(с, ч, потом);"
        "    const п = АПТ.пачка;"
        "    if (п) await аптЗапрос('/medkit/api/items/' + п.id + '/take',"
        "      {method: 'POST', headers: {'Content-Type': 'application/json'},"
        "       body: '{}'});"
        "  }; });",
        "остаток-НЕ-пересчитан-правкой"),
    # D.1 наизнанку: карандаш у всех строк, включая правку карточки
    "карандаш-у-всех-строк": (
        # Вешается на `аптКругПрименить` — единственную дверь, через
        # которую панель попадает на экран. Наблюдатель за мутациями
        # в первой версии не срабатывал вовсе (панель уже в разметке),
        # и подлог не состоялся МОЛЧА
        "window.addEventListener('load', () => {"
        "  const было = window.аптКругПрименить;"
        "  window.аптКругПрименить = function (т) {"
        "    const r = было(т);"
        "    document.querySelectorAll('.apt-feed-item').forEach(l => {"
        "      if (l.querySelector('[data-event-who]')) return;"
        "      const b = document.createElement('button');"
        "      b.setAttribute('data-event-who', l.dataset.event || '1');"
        "      b.setAttribute('data-who-now', '0');"
        "      l.appendChild(b); });"
        "    return r; }; });",
        "карандаш-ТОЛЬКО-у-приёма"),
    # ОБРАТНЫЙ: подлог ничего не ломает, и проба обязана СМОЛЧАТЬ
    "обратный-ничего-не-сломано": (
        "window.__пустойПодлог = true;",
        None),
}


def главная():
    р = argparse.ArgumentParser()
    р.add_argument("--контроль", action="store_true",
                   help="подлоги: каждый обязан быть назван своим шагом")
    р.add_argument("--только", default="",
                   help="имена подлогов через запятую")
    а = р.parse_args()

    print("=" * 70)
    print("ЗА КОГО ЗАПИСАН ПРИЁМ — BACKLOG №260")
    print("=" * 70)

    if not а.контроль:
        asyncio.run(прогон())
        print()
        print("шагов %d, плохих %d %s" % (ШАГОВ[0], len(ПЛОХО), ПЛОХО or ""))
        print("ДОКАЗАТЕЛЬСТВА: %s" % ДОКАЗАНО)
        sys.exit(1 if ПЛОХО else 0)

    # ── чистый прогон обязателен: находка, бывшая ДО подлога,
    #    засчиталась бы как находка подлога, и контроль не доказал бы
    #    ничего (§6.0.3)
    asyncio.run(прогон())
    чисто = list(ПЛОХО)
    print()
    print("ЧИСТЫЙ ПРОГОН: плохих %d %s" % (len(чисто), чисто or ""))
    if чисто:
        print("ОСТАНОВЛЕНО: основа грязная, контроль недействителен")
        sys.exit(2)

    отбор = [и.strip() for и in а.только.split(",") if и.strip()]
    итог = []
    for имя, (скрипт, ждём) in ПОДЛОГИ.items():
        if отбор and имя not in отбор:
            continue
        ПЛОХО.clear()
        ШАГОВ[0] = 0
        ДОКАЗАНО.clear()
        print()
        print("── ПОДЛОГ: %s ──" % имя)
        asyncio.run(прогон(скрипт))
        нашли = (ждём in ПЛОХО) if ждём else (not ПЛОХО)
        итог.append((имя, нашли, list(ПЛОХО), dict(ДОКАЗАНО)))
        print("  %s (плохих: %s)"
              % ("НАЙДЕН" if нашли else "НЕ НАЙДЕН", ПЛОХО or "нет"))

    print()
    print("=" * 70)
    for имя, нашли, плохо, док in итог:
        print("  %-9s %-28s доказательство: %s"
              % ("НАЙДЕН" if нашли else "НЕ НАЙДЕН", имя, док or "—"))
    не = [и for и, н, _п, _д in итог if not н]
    print("КОНТРОЛЬ: %d из %d" % (len(итог) - len(не), len(итог)))
    sys.exit(1 if не else 0)


if __name__ == "__main__":
    главная()
