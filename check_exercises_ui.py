# -*- coding: utf-8 -*-
"""СПРАВОЧНИК УПРАЖНЕНИЙ НАСКВОЗЬ: отбор идёт по ВСЕМУ набору.

ЗАЧЕМ ЭТОТ ФАЙЛ. BACKLOG №159 снял со страницы текст техники: он
занимал 79.7% данных списка (0.92 МБ из 1.15) и на экране не виден —
блок закрыт, пока не нажали «Показать технику». Разметка похудела
с 2.89 МБ до 0.29 МБ.

У такой правки есть СВОЙ немой отказ, и он не в весе. Список показывает
30 карточек из 873, а ищет и отбирает по всем 873. Стоит правке задеть
порядок «сперва отобрать, потом нарезать на страницы» — и поиск начнёт
искать ВНУТРИ ВИДИМОЙ СТРАНИЦЫ. Снаружи это выглядит исправно: поле
работает, карточки появляются, число в подписи меняется. Просто
упражнение с 800-й позиции не находится никогда.

Ни один прежний инструмент такого не спросит: пиксельный диф сравнивает
кадры, `check_regress` — свойства дерева, `check_admin_ui` доходит
до наблюдаемого результата, но по ПЕРВОЙ странице, где искомое и так
лежит. Вопрос «а по всему ли набору искали» задаётся только замером
против базы (§6.3).

ЧТО СПРАШИВАЕТСЯ

    набор целиком приехал на клиент, а текста техники в нём НЕТ
    поиск находит упражнение С ПОСЛЕДНЕЙ страницы
    отбор по группе считает по всему набору, а не по видимым 30
    техника дотягивается, совпадает с базой и берётся из кеша повторно
    отказ сервера и пустой ответ ГОВОРЯТ СЛОВАМИ, а не молчат

ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ ОБЯЗАТЕЛЕН И ВСТРОЕН. Три подлога, каждый —
настоящий отказ этой правки; проба обязана назвать каждый своим шагом.
Первая версия подлога «фильтр по странице» НЕ СРАБОТАЛА (резала уже
отфильтрованное) — и подлог, который не сработал, неотличим от слепой
пробы, если не проверить его отдельно.

    py make_local_user.py --seed
    py -m uvicorn main:app --port 8899
    py check_exercises_ui.py;            echo "код=$?"
    py check_exercises_ui.py --контроль; echo "код=$?"

Код 1 — шаг не дошёл до наблюдаемого результата (или подлог не найден).
"""
import json
import os
import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import check_hover as ch     # noqa: E402
from playwright.sync_api import sync_playwright   # noqa: E402

БАЗА_ДАННЫХ = os.environ.get("DB_PATH", "app.db")
ПУТЬ = "/admin/exercises"

# ── ПОДЛОГИ КОНТРОЛЯ ───────────────────────────────────────────────────
# Каждый ложится В СТРАНИЦУ (`evaluate` после загрузки), кода экрана
# не трогает: подлог, правящий исходник, проверял бы другую сборку.
ПОДЛОГ_ФИЛЬТР_ПО_СТРАНИЦЕ = """() => {
    // Сперва берём ВИДИМУЮ СТРАНИЦУ из всего набора и только её
    // фильтруем. Ровно так ломается поиск, когда список переводят
    // на страницы «в лоб».
    window.getFiltered = function () {
        const s = state.q.trim().toLowerCase();
        const н = (state.page - 1) * PAGE_SIZE;
        return EXERCISES.slice(н, н + PAGE_SIZE).filter(e => {
            if (state.muscle !== 'all' && e.muscle_group !== state.muscle) return false;
            if (state.pick !== 'all' && e.video_status !== state.pick) return false;
            if (state.equipment !== 'all' && e.equipment !== state.equipment) return false;
            if (s && !e.name_ru.toLowerCase().includes(s)) return false;
            return true;
        });
    };
}"""

ПОДЛОГ_ТЕХНИКА_ПУСТА = """() => {
    const было = window.fetch;
    window.fetch = async function (u, o) {
        if (String(u).includes('/instructions'))
            return new Response('{"instructions": []}',
                {status: 200, headers: {'Content-Type': 'application/json'}});
        return было(u, o);
    };
}"""

ПОДЛОГ_СЕРВЕР_ОТКАЗАЛ = """() => {
    const было = window.fetch;
    window.fetch = async function (u, o) {
        if (String(u).includes('/instructions'))
            return new Response('сбой', {status: 500});
        return было(u, o);
    };
}"""


def _из_базы():
    """Что говорит БАЗА, а не экран. Второго источника чисел нет."""
    c = sqlite3.connect(БАЗА_ДАННЫХ)
    try:
        всего = c.execute("SELECT COUNT(*) FROM exercises").fetchone()[0]
        имена = [r[0] for r in c.execute(
            "SELECT name_ru FROM exercises ORDER BY name_ru")]
        строка = c.execute(
            "SELECT id, name_ru, instructions_ru FROM exercises "
            "WHERE instructions_ru IS NOT NULL AND instructions_ru != '[]' "
            "ORDER BY name_ru").fetchone()
        return {"всего": всего, "последнее": имена[-1], "позиция": len(имена),
                "техника_id": строка[0], "техника_имя": строка[1],
                "техника": json.loads(строка[2])}
    finally:
        c.close()


def _войти(стр):
    стр.goto(ch.БАЗА + "/login", wait_until="domcontentloaded")
    стр.fill("input[name=email]", ch.ПОЧТА)
    стр.fill("input[name=password]", ch.ПАРОЛЬ)
    try:
        стр.wait_for_function(
            "() => !document.querySelector('.cf-turnstile') || "
            "(document.querySelector('[name=cf-turnstile-response]')||{}).value",
            timeout=8000)
    except Exception:
        pass
    стр.click("button[type=submit]")
    стр.wait_for_load_state("domcontentloaded")
    if "/login" in стр.url:
        raise RuntimeError("вход не состоялся — дальше снимался бы экран входа")


class Отчёт:
    def __init__(self):
        self.плохих = 0
        self.шаги = {}

    def шаг(self, имя, ок, подробность=""):
        if not ок:
            self.плохих += 1
        self.шаги[имя] = ок
        print("  %s %-46s%s" % ("ok " if ок else "ПЛОХО", имя, подробность))


ЖИВОЕ_ПОЛЕ = """() => {
    const п = document.querySelector('#admin-q');
    if (!п || п.disabled) return false;
    const r = п.getBoundingClientRect();
    const т = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
    return !!т && (т === п || п.contains(т));
}"""


def _пройти(стр, б, о):
    """Один проход экрана. Возвращает отчёт с итогом каждого шага."""
    print("\n== НАБОР ДАННЫХ ==")
    n = стр.evaluate("() => EXERCISES.length")
    о.шаг("весь набор приехал на клиент", n == б["всего"],
          "%d на клиенте, %d в базе" % (n, б["всего"]))
    есть_текст = стр.evaluate("() => EXERCISES.some(e => 'instructions' in e)")
    о.шаг("текста техники в списке НЕТ", not есть_текст,
          "поле instructions отсутствует" if not есть_текст
          else "поле instructions ЕДЕТ СО СПИСКОМ")
    о.шаг("признак has_instructions у всех",
          стр.evaluate("() => EXERCISES.every(e => 'has_instructions' in e)"))

    print("\n== ПОИСК ПО ВСЕМУ НАБОРУ, А НЕ ПО СТРАНИЦЕ ==")
    видно = стр.evaluate("() => document.querySelectorAll('.ex-card').length")
    о.шаг("на странице показано 30 карточек", видно == 30, "карточек %d" % видно)
    о.шаг("искомое НЕ на первой странице", б["позиция"] > 30,
          "«%s» стоит %d-м из %d" % (б["последнее"], б["позиция"], б["всего"]))

    поле = стр.query_selector("#admin-q")
    о.шаг("поле поиска — орган живой",
          поле is not None and стр.evaluate(ЖИВОЕ_ПОЛЕ))
    if поле:
        поле.fill(б["последнее"])
        стр.wait_for_timeout(700)
        нашлось = стр.evaluate("() => document.querySelectorAll('.ex-card').length")
        текст = стр.evaluate(
            "() => (document.querySelector('.ex-card-name')||{}).textContent || ''")
        о.шаг("НАЙДЕНО упражнение с последней страницы",
              нашлось >= 1 and б["последнее"] in текст,
              "карточек %d, первая — «%s»" % (нашлось, текст.strip()[:38]))
        поле.fill("")
        стр.wait_for_timeout(700)
        вернулось = стр.evaluate("() => document.querySelectorAll('.ex-card').length")
        о.шаг("после очистки вернулись 30", вернулось == 30,
              "карточек %d" % вернулось)

    print("\n== ОТБОР ПО ГРУППЕ СЧИТАЕТ ПО ВСЕМУ НАБОРУ ==")
    свод = стр.evaluate(
        "() => { const g = {}; for (const e of EXERCISES) "
        "g[e.muscle_group || 'нет'] = (g[e.muscle_group || 'нет'] || 0) + 1; "
        "return g; }")
    группа = max((k for k in свод if k != "нет"), key=lambda k: свод[k])
    итог = стр.evaluate(
        "(гр) => { state.muscle = гр; state.q = ''; state.page = 1; renderGrid(); "
        "return {всего: getFiltered().length, "
        "видно: document.querySelectorAll('.ex-card').length}; }", группа)
    о.шаг("отбор «%s» — по всему набору" % группа,
          итог["всего"] == свод[группа],
          "нашлось %d, в наборе %d" % (итог["всего"], свод[группа]))
    о.шаг("на странице всё равно не больше 30", итог["видно"] <= 30,
          "карточек %d" % итог["видно"])
    стр.evaluate("() => { state.muscle = 'all'; state.q = ''; "
                 "state.page = 1; renderGrid(); }")
    стр.wait_for_timeout(300)

    print("\n== ТЕХНИКА ДОТЯГИВАЕТСЯ ==")
    if поле:
        поле.fill(б["техника_имя"])
        стр.wait_for_timeout(700)
    кнопка = стр.query_selector(".ex-btn-howto")
    о.шаг("кнопка «Показать технику» — орган живой", кнопка is not None)
    if кнопка:
        кнопка.click()
        стр.wait_for_timeout(1500)
        пункты = стр.evaluate(
            "() => { const b = document.querySelector('.ex-instructions.open'); "
            "return b ? [...b.querySelectorAll('li')].map(li => li.textContent) : null; }")
        видимое = стр.evaluate(
            "() => { const b = document.querySelector('.ex-instructions.open'); "
            "return b ? b.textContent.trim().slice(0, 70) : ''; }")
        о.шаг("блок раскрылся и текст приехал", bool(пункты),
              "пунктов %d" % len(пункты or []))
        о.шаг("текст СОВПАЛ С БАЗОЙ", пункты == б["техника"],
              "эталон %d пунктов" % len(б["техника"]))
        # Молчания быть не должно НИ В ОДНОМ исходе: блок раскрыт,
        # и пустой прямоугольник неотличим от «ничего не произошло».
        о.шаг("блок НЕ МОЛЧИТ", видимое != "", "«%s»" % видимое)
        кнопка.click()
        стр.wait_for_timeout(300)
        о.шаг("повторное нажатие закрывает",
              стр.evaluate("() => !document.querySelector('.ex-instructions.open')"))
        кнопка.click()
        стр.wait_for_timeout(400)
        из_кеша = стр.evaluate(
            "() => { const b = document.querySelector('.ex-instructions.open'); "
            "return b ? b.querySelectorAll('li').length : 0; }")
        о.шаг("третье нажатие берёт из кеша", из_кеша == len(б["техника"]),
              "пунктов %d" % из_кеша)
    return о


def _прогон(подлог=None):
    б = _из_базы()
    о = Отчёт()
    with sync_playwright() as p:
        бр = p.chromium.launch()
        ctx = бр.new_context(viewport={"width": 1440, "height": 900})
        стр = ctx.new_page()
        ошибки = []
        стр.on("pageerror", lambda e: ошибки.append(str(e)))
        _войти(стр)
        стр.goto(ch.БАЗА + ПУТЬ, wait_until="networkidle")
        стр.wait_for_timeout(500)
        if подлог:
            # Подлог живёт в УЖЕ ОТКРЫТОЙ странице; перезагружать её после
            # этого нельзя — он исчезнет вместе с окружением, и контроль
            # печатал бы «проба слепа» про исправную пробу.
            стр.evaluate(подлог)
            стр.wait_for_timeout(200)
        _пройти(стр, б, о)
        if not подлог:
            о.шаг("ошибок в консоли нет", not ошибки,
                  "; ".join(ошибки[:2]) if ошибки else "")
        бр.close()
    return о


# ── ДОКАЗАТЕЛЬСТВА ПОДЛОГОВ (§6.0.3) ────────────────────────────────
#
# «Шаг провалился» доказательством НЕ является: провалиться он мог
# по другой причине — страница не догрузилась, кнопка не нажалась.
# А подлог кладётся В СТРАНИЦУ через `evaluate`: он бывает ПУСТОЙ
# ОПЕРАЦИЕЙ — отработал без ошибки и не изменил ничего. Ровно это
# и случилось с первой версией первого подлога: он резал уже
# отфильтрованное, то есть не менял выдачу вовсе.
#
# Каждое доказательство — НЕЗАВИСИМЫЙ замер того, что подлог собирался
# изменить, и машинерией прохода он не пользуется.
ДОКАЗАТЕЛЬСТВА = {
    # Отбор идёт по ВСЕЙ базе или по видимой странице: спрашиваем, сколько
    # находок даёт заведомо редкое имя с последней страницы
    "фильтр ищет ТОЛЬКО по видимой странице": ("""
      () => {
        const б = EXERCISES.map(e => e.name_ru).sort();
        state.q = б[б.length - 1]; state.page = 1;
        state.muscle = 'all'; state.pick = 'all'; state.equipment = 'all';
        return 'находок по имени с последней страницы: '
             + getFiltered().length;
      }""", "сколько находит отбор по имени с последней страницы"),
    # Что отдаёт сервер техники — спрашиваем НАПРЯМУЮ тем же fetch,
    # который подлог и подменяет
    "техника приезжает ПУСТОЙ": ("""
      async () => {
        const о = await fetch('/admin/api/exercise/1/instructions');
        const т = await о.text();
        return 'ответ техники: ' + о.status + ' ' + т.slice(0, 40);
      }""", "что отвечает эндпоинт техники"),
    "сервер отказывает 500": ("""
      async () => {
        const о = await fetch('/admin/api/exercise/1/instructions');
        return 'код ответа техники: ' + о.status;
      }""", "код ответа эндпоинта техники"),
}


def _доказать_подлог(имя, скрипт):
    """Состояние страницы БЕЗ подлога и С ним — своим замером, мимо
    прохода. Возвращает пару сравнимых значений и подпись."""
    from playwright.sync_api import sync_playwright

    выражение, что = ДОКАЗАТЕЛЬСТВА[имя]
    ответы = []
    with sync_playwright() as p:
        бр = p.chromium.launch()
        for класть in (False, True):
            ctx = бр.new_context(viewport={"width": 1440, "height": 900})
            стр = ctx.new_page()
            _войти(стр)
            стр.goto(ch.БАЗА + ПУТЬ, wait_until="networkidle")
            стр.wait_for_timeout(500)
            if класть:
                стр.evaluate(скрипт)
                стр.wait_for_timeout(200)
            ответы.append(стр.evaluate(выражение))
            ctx.close()
        бр.close()
    return ответы[0], ответы[1], что


def _контроль():
    """Три подлога; каждый обязан быть назван СВОИМ шагом."""
    print("=" * 74)
    print("ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ: три подлога кладутся В СТРАНИЦУ")
    print("=" * 74)
    чисто = _прогон()
    if чисто.плохих:
        print("\nОСТАНОВЛЕНО: чистый прогон уже даёт %d плохих шагов. "
              "На грязной основе контроль недействителен — «нашла» "
              "и «нашла подлог» неотличимы." % чисто.плохих)
        return 1

    случаи = [
        ("фильтр ищет ТОЛЬКО по видимой странице",
         ПОДЛОГ_ФИЛЬТР_ПО_СТРАНИЦЕ, "НАЙДЕНО упражнение с последней страницы"),
        ("техника приезжает ПУСТОЙ",
         ПОДЛОГ_ТЕХНИКА_ПУСТА, "текст СОВПАЛ С БАЗОЙ"),
        ("сервер отказывает 500",
         ПОДЛОГ_СЕРВЕР_ОТКАЗАЛ, "блок раскрылся и текст приехал"),
    ]
    найдено, несостоявшихся = 0, 0
    for имя, скрипт, ждём in случаи:
        print("\nПОДЛОГ — %s" % имя)
        # ШАГ ПЕРВЫЙ — ДОКАЗАТЬ, ЧТО ПОДЛОГ СОСТОЯЛСЯ (§6.0.3)
        д_ч, д_п, что = _доказать_подлог(имя, скрипт)
        состоялся = д_ч != д_п
        print("  доказательство (%s): чисто=%r с подлогом=%r → %s"
              % (что, д_ч, д_п,
                 "ПОДЛОГ СОСТОЯЛСЯ" if состоялся else "ПОДЛОГ НЕ СОСТОЯЛСЯ"))
        if not состоялся:
            несостоявшихся += 1
            print("  -> ПРОПУЩЕН: ломать нечего, вердикт пробы про него "
                  "не значит ничего")
            continue
        о = _прогон(скрипт)
        поймал = о.шаги.get(ждём) is False
        найдено += 1 if поймал else 0
        print("  -> шаг «%s»: %s"
              % (ждём, "НАЙДЕН ПОДЛОГ" if поймал else "ПРОБА НЕ ВИДИТ"))
    print("\n" + "=" * 74)
    print("НАЙДЕНО ПОДЛОГОВ: %d из %d; НЕ СОСТОЯЛОСЬ: %d"
          % (найдено, len(случаи), несостоявшихся))
    if несостоявшихся:
        print("ПОДЛОГ, КОТОРЫЙ НЕ СОСТОЯЛСЯ, не проверяет ничего.")
        return 1
    if найдено != len(случаи):
        print("ПРОБА СЛЕПА — её зелёный результат недействителен.")
        return 1
    print("ПРОЙДЕН: проба видит каждый из трёх отказов.")
    return 0


def main():
    if "--контроль" in sys.argv:
        return _контроль()
    о = _прогон()
    print("\n" + "=" * 74)
    print("ШАГОВ %d, ПЛОХИХ %d" % (len(о.шаги), о.плохих))
    print("\nОтдельно: этот ноль стоит чего-то только вместе "
          "с `py check_exercises_ui.py --контроль`.")
    return 1 if о.плохих else 0


if __name__ == "__main__":
    sys.exit(main())
