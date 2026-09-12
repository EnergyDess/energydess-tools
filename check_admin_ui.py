# -*- coding: utf-8 -*-
"""ПРОХОД АДМИНКИ НАСКВОЗЬ: каждое действие так, как его проходит человек.

ЗАЧЕМ ЭТО ФАЙЛ В РЕПОЗИТОРИИ (§6.3). Экран управления каталогом
Enshrouded уехал на прод с МЁРТВОЙ формой — поля загрузки картинки стояли
`disabled`, — при ЗЕЛЁНОЙ приёмке: мерка спрашивала ответы сервера, все
двадцать пять были верны, и вопроса «а можно ли вообще нажать» среди них
не было. Отсюда правило: у экрана, который заход изменил, проходится
КАЖДОЕ действие от первого нажатия до наблюдаемого результата.

Заход 2026-08-23 (BACKLOG №147, №148) переоформил все четыре раздела
админки целиком — значит, проходить надо все четыре, а не один каталог,
для которого уже есть `check_ens_admin_ui.py`.

ТРИ ТРЕБОВАНИЯ, и каждое отсекает свой вид самообмана:

  · ОРГАН ЖИВОЙ — не `disabled`, виден, и `elementFromPoint` в его центре
    возвращает его самого или потомка. «Есть в дереве» органом не делает;
  · действие идёт ДО НАБЛЮДАЕМОГО РЕЗУЛЬТАТА — не до ответа сервера;
  · результат берётся С ЭКРАНА И ИЗ БАЗЫ, а не из тела ответа: ответ —
    это намерение сервера, а в базе бывает пусто (§6.0.5).

НЕ ПРОВЕРКА РЯДА: нужны браузер, поднятое приложение И ЗАПИСЬ в базу
(заводит и удаляет пробный продукт, переключает доступ, правит статус
упражнения). Ряд обязан быть безопасным для любого прогона — этот нет.
Запускается заходом, который трогал админку; этого требует само правило.

    py make_local_user.py --seed
    py -m uvicorn main:app --port 8899
    py check_admin_ui.py                  # 1440
    py check_admin_ui.py --ширина 390     # сенсорная
    py check_admin_ui.py --контроль       # ПОДЛОГИ, каждый обязан быть
                                          # назван своим шагом (число
                                          # печатает сам прогон, §6.0.4)
    py check_admin_ui.py --контроль-уборки  # обрыв после одобрения
                                          # упражнения: статус обязан
                                          # вернуться (BACKLOG №284)

ПРОБА НЕ МЕНЯЕТ ЧУЖИЕ ДАННЫЕ (BACKLOG №284). Всё, что раздел меняет
в базе, он возвращает в `finally` — в том числе при обрыве посреди
раздела. До этого статус одобренного упражнения возвращался в конце
раздела, и обрыв оставлял `approved` у упражнения без ролика.

ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ ОБЯЗАТЕЛЕН И ЕСТЬ ЗДЕСЬ, А НЕ В ОТЧЁТЕ СЕССИИ.
У соседнего `check_ens_admin_ui.py` он полдня числился существующим,
пока не выяснилось, что прошлый заход проделал подлоги руками и записал
вывод только в отчёт — то есть контроля не было ни строки.
"""
import io
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DB_PATH", "app.db")

import check_hover as ch     # noqa: E402
import probe_guard  # noqa: F401  ПРОПУСК вместо трассы (§6.0.1)

# ВЫВОД В UTF-8: без этого печать знака вне cp1251 роняет пробу
# `UnicodeEncodeError` при ЛЮБОМ перенаправлении (`> файл`,
# конвейер, `capture_output`) — то есть у всякого, кто запустит
# её не в консоль. Найдено проверкой 35 (BACKLOG №307).
sys.stdout.reconfigure(encoding="utf-8")

# ИМЯ ЛАТИНИЦЕЙ — §6.0. Кириллическое `СТЕНД=…` оболочка присвоить
# не может вовсе: это «command not found», а адрес молча остаётся
# умолчанием — то есть проба идёт не на тот стенд и об этом не
# говорит ни словом. Сторожит проверка 34 (BACKLOG №310).
БАЗА = os.environ.get("STAND", "http://127.0.0.1:8899")
ФАЙЛ_БД = os.environ.get("DB_PATH", "app.db")

# Живость органа — тем же способом, каким её видит палец: точка в центре
# обязана принадлежать самому органу или его потомку. Прямоугольник
# на это не отвечает: `disabled` не меняет размера, а перекрытый чужим
# слоем орган измеряется как исправный.
ЖИВ = r"""
  ([сел, последний]) => {
    const все = document.querySelectorAll(сел);
    const el = последний ? все[все.length - 1] : все[0];
    if (!el) return {есть: false};
    const r = el.getBoundingClientRect();
    const st = getComputedStyle(el);
    const о = {есть: true, w: +r.width.toFixed(1), h: +r.height.toFixed(1),
               disabled: !!el.disabled, скрыт: st.display === 'none'
                       || st.visibility === 'hidden' || +st.opacity === 0
                       || el.hasAttribute('hidden')};
    if (r.width < 1 || r.height < 1) { о.дотянулись = false; return о; }
    // ЗА КАДРОМ `elementFromPoint` отдаёт null — точка вне области
    // просмотра ему просто не принадлежит. На 390 таблица прокручивается
    // вбок, и половина органов лежит правее экрана: прежняя версия пробы
    // объявляла их «нажатие ловит None», то есть врала про исправные
    // кнопки. Подводим элемент в кадр и меряем ЗАНОВО — это и есть то,
    // что делает человек пальцем, прежде чем нажать.
    if (r.left < 0 || r.top < 0 || r.right > innerWidth || r.bottom > innerHeight) {
      el.scrollIntoView({block: 'center', inline: 'center'});
      о.подводили = true;
    }
    const r2 = el.getBoundingClientRect();
    о.w = +r2.width.toFixed(1); о.h = +r2.height.toFixed(1);
    const т = document.elementFromPoint(r2.left + r2.width / 2, r2.top + r2.height / 2);
    о.дотянулись = !!(т && (т === el || el.contains(т) || т.contains(el)));
    о.поймал = т ? (т.tagName.toLowerCase()
                    + (т.className && typeof т.className === 'string'
                       ? '.' + т.className.trim().split(/\s+/).join('.') : '')) : null;
    return о;
  }
"""


def _бд(запрос, параметры=()):
    с = sqlite3.connect(ФАЙЛ_БД)
    try:
        return с.execute(запрос, параметры).fetchall()
    finally:
        с.close()


ЧИП_ОДОБРЕНО = ("() => +document.querySelector("
                "'[data-pick=\"approved\"] .chip-n').textContent")


def _вернуть_упражнение(ид, статус):
    """Прежний статус упражнения — ВКЛЮЧАЯ пустой (BACKLOG №284).

    Зовётся из `finally` раздела, то есть и при обрыве. Модульным именем,
    а не строкой внутри раздела: `--контроль-уборки` снимает уборку
    подменой этого имени и раздела не трогает — ровно как `_прибрать`
    у пробы каталога (задача 269)."""
    с = sqlite3.connect(ФАЙЛ_БД)
    try:
        с.execute("UPDATE exercises SET video_status=? WHERE id=?", (статус, ид))
        с.commit()
    finally:
        с.close()


class Проход:
    """Счётчик шагов. Печатает КАЖДЫЙ, а не только упавший."""

    def __init__(self, ширина):
        self.ширина = ширина
        self.плохо = []
        self.пропущено = []
        self.шагов = 0

    def шаг(self, имя, ок, что="", собрано=None, отрицание=""):
        """ПУСТОЙ СБОР — ПРОПУСК, А НЕ OK (задача 293, механизм захода 285).

        `собрано` — сколько собрано для замера: ноль значит, что мерить
        было нечего. `отрицание` — причина, по которой пустота и ЕСТЬ
        успех. Оба ключа читает проверка 33.
        """
        self.шагов += 1
        if собрано is not None and not собрано and not отрицание:
            self.пропущено.append((имя, "сбор пуст — мерить нечего"))
            print("  ПРП %-46s %s" % (имя, "сбор пуст — мерить нечего"))
            return None
        знак = "  ok " if ок else "  !! "
        print("%s%-46s %s" % (знак, имя, что))
        if not ок:
            self.плохо.append((имя, что))
        return ок

    def последний(self, стр, имя, сел):
        """Орган, стоящий ПОСЛЕДНИМ в своём ряду.

        Заведено 2026-08-23 после того, как эту находку принёс ПИКСЕЛЬНЫЙ
        ДИФ, а не проход: на 390 ряд чипов был 643px внутри контейнера
        358, и чипы с четвёртого по шестой оказывались за экраном при
        `body { overflow-x: clip }` — то есть недостижимы ничем. Проба
        при этом печатала «ok», потому что спрашивала ВТОРОЙ чип ряда,
        а второй ещё виден.

        Первый и последний — разные вопросы: первый отвечает «ряд вообще
        живой», последний — «ряд помещается или прокручивается». """
        n = стр.evaluate("(с) => document.querySelectorAll(с).length", сел)
        if not n:
            return self.шаг(имя, False, "ряд пуст: " + сел)
        return self.орган(стр, имя, сел, последний=True)

    def орган(self, стр, имя, сел, последний=False):
        д = стр.evaluate(ЖИВ, [сел, последний])
        if not д.get("есть"):
            return self.шаг(имя, False, "элемента нет в дереве: " + сел)
        беды = []
        if д["disabled"]:
            беды.append("disabled")
        if д["скрыт"]:
            беды.append("скрыт")
        if not д.get("дотянулись"):
            беды.append("нажатие ловит " + str(д.get("поймал")))
        что = "%.0fx%.0f" % (д["w"], д["h"])
        if беды:
            что += " — " + ", ".join(беды)
        # ПУСТОТА ЗДЕСЬ И ЕСТЬ УСПЕХ: `беды` копится из ФИКСИРОВАННОГО
        # набора вопросов к органу (disabled, скрыт, дотянулись), а сам
        # орган уже найден шагом выше — «элемента нет в дереве».
        return self.шаг(имя, not беды, что,
                        отрицание="набор вопросов к органу фиксирован")


# ── ПОДЛОГИ ОТРИЦАТЕЛЬНОГО КОНТРОЛЯ ──────────────────────────────────────
#
# Кладутся В СТРАНИЦУ (`add_init_script`), кода админки не трогают:
# подлог, который правит исходники, чинить потом руками, а забытая правка
# уезжает в коммит.
ПОДЛОГИ = {
    "мёртвый чип": """
        addEventListener('DOMContentLoaded', () => {
          document.querySelectorAll('[data-pick]').forEach(b => b.disabled = true);
        });""",
    "тумблер молчит": """
        addEventListener('DOMContentLoaded', () => {
          window.toggleAccess = function () {};
        });""",
    "удаление без вопроса": """
        addEventListener('DOMContentLoaded', () => {
          window.delFood = function (id, btn) { btn.closest('tr').remove(); };
        });""",
    # Ломает РОВНО проверяемое звено задачи 265 — сокрытие строки отбором
    # каталога — и только на его экране: свойство `hidden` у строки
    # таблицы перестаёт что-либо делать. Отбор при этом отрабатывает
    # целиком: чип подсвечен, число и подпись «Показано 15 из 90» верны.
    "отбор не прячет": """
        if (location.pathname === '/admin/enshrouded') {
          Object.defineProperty(HTMLTableRowElement.prototype, 'hidden',
            {configurable: true, get() { return false; }, set(v) {}});
        }""",
    # ── ТРИ ОТБОРА ЗАДАЧИ 268 ────────────────────────────────────────
    # Слушатель на `document` в фазе ЗАХВАТА срабатывает раньше слушателя
    # самого органа и гасит событие: отбор о действии не узнаёт, а орган
    # при этом жив, виден и нажимается. Ровно этот случай шаг с `>= 0`
    # пропускал — он печатал ok и на пустом, и на несуженном списке.
    "поиск молчит": """
        if (location.pathname === '/admin/users') {
          document.addEventListener('input', e => {
            if (e.target && e.target.id === 'admin-q') e.stopImmediatePropagation();
          }, true);
        }""",
    "отбор статуса молчит": """
        if (location.pathname === '/admin/exercises') {
          document.addEventListener('click', e => {
            if (e.target && e.target.closest && e.target.closest('[data-pick]'))
              e.stopImmediatePropagation();
          }, true);
        }""",
    "группа мышц молчит": """
        if (location.pathname === '/admin/exercises') {
          document.addEventListener('change', e => {
            if (e.target && e.target.id === 'filter-muscle') e.stopImmediatePropagation();
          }, true);
        }""",
    # ── ОТКАЗ ОТ УДАЛЕНИЯ ПРОДУКТА (задача 270, контроль на НОВОЙ
    # формулировке): «Отмена» сама жмёт «Удалить». Подлог настоящий —
    # на стенде уходит продукт; после контроля стенд пересевается.
    "отмена удаляет": """
        if (location.pathname === '/admin/products') {
          addEventListener('DOMContentLoaded', () => {
            const к = document.querySelector('#food-del .btn-secondary[data-modal-close]');
            if (к) к.addEventListener('click',
              () => document.getElementById('food-del-go').click());
          });
        }""",
    # ── ОДОБРЕНИЕ УПРАЖНЕНИЯ (задача 284): нажатие «Одобрено» не доходит
    # до обработчика. На прежних шагах подлог проходил незамеченным, когда
    # первая карточка уже была одобрена; новые обязаны упасть при любом
    # стенде — карточка берётся не одобренная.
    "одобрение молчит": """
        if (location.pathname === '/admin/exercises') {
          document.addEventListener('click', e => {
            if (e.target && e.target.closest && e.target.closest('.ex-btn-approve'))
              e.stopImmediatePropagation();
          }, true);
        }""",
}
ЧЕЙ_ШАГ = {
    "мёртвый чип": ("Пользователи", "чип «Без доступа» — орган живой"),
    "тумблер молчит": ("Пользователи", "доступ записался в базу"),
    "удаление без вопроса": ("Продукты", "окно подтверждения открылось"),
    "отбор не прячет": ("Enshrouded", "отбор по категории сузил каталог"),
    "поиск молчит": ("Пользователи", "поиск по почте отобрал"),
    "отбор статуса молчит": ("Упражнения", "отбор по статусу перерисовал сетку"),
    "группа мышц молчит": ("Упражнения", "список групп мышц отобрал"),
    "отмена удаляет": ("Продукты", "отмена НИЧЕГО не удалила"),
    "одобрение молчит": ("Упражнения", "статус доехал ДО БАЗЫ"),
}


# «ИЗ N ПОДОШЕДШИХ» — ЧИСЛО, КОТОРОЕ НАСЧИТАЛ ОТБОР СПРАВОЧНИКА, а не
# число карточек: карточек на странице не больше `PAGE_SIZE`, и «30 из 30»
# неотличимо от «30 из 873»
ПОДОШЛО = ("() => { const м = /из (\\d+) подошедших/.exec("
           "(document.getElementById('note') || {}).textContent || '');"
           " return м ? +м[1] : -1; }")


def _вход(стр, cdp, сенсор):
    ch.БАЗА = БАЗА
    ch._войти(стр)
    if сенсор:
        ch._включить_сенсор(cdp)


def раздел_пользователи(стр, п):
    print("\n== ПОЛЬЗОВАТЕЛИ ==")
    стр.goto(БАЗА + "/admin/users", wait_until="domcontentloaded", timeout=60000)
    стр.wait_for_timeout(2500)

    п.орган(стр, "ряд разделов — вкладка «Продукты» живая",
            '.admin-tabs a[href="/admin/products"]')
    п.орган(стр, "чип «Все» — орган живой", '[data-pick="all"]')
    чип_жив = п.орган(стр, "чип «Без доступа» — орган живой", '[data-pick="no"]')
    п.последний(стр, "ПОСЛЕДНИЙ чип ряда — орган живой", "[data-pick]")
    п.орган(стр, "поле поиска — орган живой", "#admin-q")
    if not чип_жив:
        # Нажимать мёртвый орган незачем: Playwright ждёт его оживления
        # 30 секунд и падает, а падение проглатывает уже НАЙДЕННОЕ.
        п.шаг("отбор «Без доступа» — дальше не идём", False,
              "орган мёртв, нажимать нечего")
        return

    было = стр.evaluate("() => document.querySelectorAll('#rows tr:not([hidden])').length")
    n_чипа = стр.evaluate("() => +document.querySelector('[data-pick=\"no\"] .chip-n').textContent")
    стр.click('[data-pick="no"]')
    стр.wait_for_timeout(400)
    стало = стр.evaluate("() => document.querySelectorAll('#rows tr:not([hidden])').length")
    # СПРАШИВАЕТСЯ «столько ли, сколько обещал чип», а не «стало ли меньше».
    # Первая версия требовала сужения — и упала на стенде, где доступа нет
    # ни у кого: «Без доступа» там законно равно «Все». То есть проба
    # утверждала бы дефект про исправный экран, а на другой базе молчала бы.
    п.шаг("отбор «Без доступа» показал столько, сколько обещал чип",
          стало == n_чипа,
          "строк %d -> %d, чип обещал %d" % (было, стало, n_чипа))

    примечание = стр.evaluate("() => document.getElementById('note').textContent.trim()")
    п.шаг("строка-объяснение под таблицей непуста",
          len(примечание) > 40, примечание[:64] + "...")

    стр.click('[data-pick="all"]')
    стр.wait_for_timeout(300)
    # ПОИСК СВЕРЯЕТСЯ С БАЗОЙ, А НЕ С НУЛЁМ (BACKLOG №268). Здесь стояло
    # `найдено >= 0` по запросу «screenshot» — и это был ноль ПО ПОСТРОЕНИЮ:
    # таблица показывает всех, КРОМЕ вошедшего, а вошёл сам screenshot.
    # Шаг мерил пустоту и печатал ok. Запрос теперь — начало адреса ПЕРВОЙ
    # строки, то есть заведомо непустое подмножество; ожидаемое число — из
    # базы без вошедшего; каждая видимая строка обязана запрос содержать.
    всего_строк = стр.evaluate(
        "() => document.querySelectorAll('#rows tr:not([hidden])').length")
    запрос = стр.evaluate(
        "() => { const r = document.querySelector('#rows tr');"
        " return r ? (r.dataset.email || '').split('@')[0] : ''; }")
    ожидается = _бд(
        "SELECT COUNT(*) FROM users WHERE instr(lower(email), ?) > 0"
        " AND lower(email) <> lower(?)", (запрос.lower(), ch.ПОЧТА))[0][0]
    стр.fill("#admin-q", запрос)
    стр.wait_for_timeout(400)
    почты = стр.evaluate("() => [...document.querySelectorAll("
                         "'#rows tr:not([hidden])')].map(r => r.dataset.email || '')")
    чужие = [а for а in почты if запрос.lower() not in а.lower()]
    п.шаг("поиск по почте отобрал",
          bool(запрос) and 0 < len(почты) == ожидается < всего_строк and not чужие,
          "«%s»: строк %d из %d, в базе подходит %d%s"
          % (запрос, len(почты), всего_строк, ожидается,
             "; не содержат запроса: %s" % чужие if чужие else ""))
    стр.fill("#admin-q", "")
    стр.wait_for_timeout(300)

    # ── ГЛАВНОЕ ДЕЙСТВИЕ РАЗДЕЛА: выдать и отобрать доступ ───────────────
    # ДОСТУП СЧИТАЕТСЯ ПО ПАРЕ «ЧЕЛОВЕК, ИНСТРУМЕНТ» ДО И ПОСЛЕ НАЖАТИЯ
    # (BACKLOG №267). Здесь спрашивалось «есть ли у человека ХОТЬ ОДНА
    # строка доступа» и сравнивалось с нулём: сид общей аптечки выдаёт
    # соседу доступ к аптечке, одна строка у него есть до всякого нажатия,
    # и подлог «тумблер молчит» проходил шаг с «строк 1». А при уже
    # включённом тумблере шаг был `True` без единой сверки.
    д = стр.evaluate(r"""() => {
        const r = document.querySelector('#rows tr:not([hidden])');
        if (!r) return null;
        const c = r.querySelector('input[type=checkbox]');
        const м = /toggleAccess\(\s*\d+\s*,\s*'([^']+)'/.exec(
            c.getAttribute('onchange') || '');
        return {почта: r.dataset.email, был: c.checked, инструмент: м ? м[1] : ''};
    }""")
    if not д:
        return п.шаг("тумблер доступа", False, "в таблице нет ни одной строки")
    uid = _бд("SELECT id FROM users WHERE email=?", (д["почта"],))
    if not uid or not д["инструмент"]:
        return п.шаг("доступ записался в базу", False,
                     "сверять не с чем: человек %s, инструмент %r"
                     % ("есть" if uid else "НЕ НАЙДЕН в базе", д["инструмент"]))
    uid = uid[0][0]

    def строк_доступа():
        return _бд("SELECT COUNT(*) FROM tool_access WHERE user_id=? AND tool_id=?",
                   (uid, д["инструмент"]))[0][0]

    до = строк_доступа()
    # ОРГАН — ПОДПИСЬ `.toggle`, а не сам `<input>`: у системного тумблера
    # флажок спрятан по построению (0x0), нажимают дорожку. Спроси мы
    # про input — проба объявила бы находкой исправный компонент.
    п.орган(стр, "тумблер первого инструмента — орган живой",
            "#rows tr:not([hidden]) .toggle")
    стр.click("#rows tr:not([hidden]) .toggle", timeout=8000)
    стр.wait_for_timeout(900)
    после = строк_доступа()
    ждём = 0 if д["был"] else 1
    п.шаг("доступ записался в базу", после == ждём and после != до,
          "у %s строк доступа к «%s»: до %d, после %d, ждём %d (было отмечено: %s)"
          % (д["почта"], д["инструмент"], до, после, ждём, д["был"]))
    # Вернуть как было — проба не должна оставлять следа, И ЭТО ПРОВЕРЯЕТСЯ
    стр.click("#rows tr:not([hidden]) .toggle", timeout=8000)
    стр.wait_for_timeout(900)
    вернулось = строк_доступа()
    п.шаг("проба вернула доступ как был", вернулось == до,
          "строк доступа к «%s»: было %d, после возврата %d"
          % (д["инструмент"], до, вернулось))


def раздел_продукты(стр, п):
    print("\n== ПРОДУКТЫ ==")
    стр.goto(БАЗА + "/admin/products", wait_until="domcontentloaded", timeout=60000)
    стр.wait_for_timeout(2200)

    п.орган(стр, "чип «Без бренда» — орган живой", '[data-pick="nobrand"]')
    п.последний(стр, "ПОСЛЕДНИЙ чип ряда — орган живой", "[data-pick]")
    п.орган(стр, "поле поиска — орган живой", "#admin-q")
    п.орган(стр, "поле «Название» первой строки — орган живой",
            "#rows tr:not([hidden]) .food-name")

    было = стр.evaluate("() => document.querySelectorAll('#rows tr:not([hidden])').length")
    n = стр.evaluate("() => +document.querySelector('[data-pick=\"nobrand\"] .chip-n').textContent")
    стр.click('[data-pick="nobrand"]')
    стр.wait_for_timeout(400)
    стало = стр.evaluate("() => document.querySelectorAll('#rows tr:not([hidden])').length")
    п.шаг("отбор «Без бренда» сузил таблицу", стало == n,
          "строк %d -> %d, чип обещал %d" % (было, стало, n))
    стр.click('[data-pick="all"]')
    стр.wait_for_timeout(300)

    # ── ПРАВКА СТРОКИ: кнопка появляется только после изменения ──────────
    видна = стр.evaluate("""() => {
        const b = document.querySelector('#rows tr:not([hidden]) .food-save-btn');
        return getComputedStyle(b).visibility;
    }""")
    п.шаг("кнопка сохранения спрятана, пока строку не тронули",
          видна == "hidden", "visibility=" + видна)

    ид = стр.evaluate("() => +document.querySelector('#rows tr:not([hidden])').dataset.foodId")
    старое = _бд("SELECT name FROM custom_foods WHERE id=?", (ид,))[0][0]
    новое = (старое or "") + " (проба)"
    стр.fill("#rows tr:not([hidden]) .food-name", новое)
    стр.wait_for_timeout(300)
    видна = стр.evaluate("""() => {
        const b = document.querySelector('#rows tr:not([hidden]) .food-save-btn');
        return getComputedStyle(b).visibility;
    }""")
    п.шаг("кнопка сохранения показалась после правки", видна == "visible",
          "visibility=" + видна)
    п.орган(стр, "кнопка сохранения — орган живой",
            "#rows tr:not([hidden]) .food-save-btn")
    стр.click("#rows tr:not([hidden]) .food-save-btn")
    стр.wait_for_timeout(900)
    в_базе = _бд("SELECT name FROM custom_foods WHERE id=?", (ид,))[0][0]
    п.шаг("правка доехала ДО БАЗЫ", в_базе == новое,
          "в базе: %r" % в_базе)
    стр.fill("#rows tr:not([hidden]) .food-name", старое or "")
    стр.wait_for_timeout(200)
    стр.click("#rows tr:not([hidden]) .food-save-btn")
    стр.wait_for_timeout(700)

    # ── УДАЛЕНИЕ: вопрос обязателен, отмена обязана отменять ─────────────
    всего_до = _бд("SELECT COUNT(*) FROM custom_foods")[0][0]
    п.орган(стр, "кнопка удаления — орган живой",
            "#rows tr:not([hidden]) .btn-icon-danger")
    стр.click("#rows tr:not([hidden]) .btn-icon-danger")
    стр.wait_for_timeout(700)
    открыто = стр.evaluate(
        "() => { const m = document.getElementById('food-del');"
        " return !!m && m.classList.contains('open'); }")
    п.шаг("окно подтверждения открылось", открыто,
          "" if открыто else "удаление прошло БЕЗ вопроса")
    текст = стр.evaluate("() => (document.getElementById('food-del-text')||{}).textContent || ''")
    п.шаг("вопрос называет, ЧТО удаляется", len(текст.strip()) > 10,
          текст.strip()[:60])
    if открыто:
        # «ОТМЕНА», А НЕ ПЕРВЫЙ ОРГАН ЗАКРЫТИЯ (§6.0.3, четыре пункта; BACKLOG №270).
        #   ПРЕЖНЯЯ ФОРМУЛИРОВКА: `#food-del [data-modal-close]` — первым
        #     таким органом стоит крестик шапки.
        #   НОВАЯ: `#food-del .btn-secondary[data-modal-close]` — «Отмена»,
        #     тот же селектор, что у соседней пробы каталога (задача 266).
        #   ПОЧЕМУ ПРЕЖНЯЯ СТАЛА НЕГОДНОЙ: крестик шапки на сенсорной ширине
        #     скрыт с задачи 189 (окно закрывают жестом), клик ждал 30 с
        #     и ронял раздел — отказ от удаления на 390 не проверялся ни разу.
        #   ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ НА НОВОЙ: подлог «отмена удаляет».
        стр.click("#food-del .btn-secondary[data-modal-close]")
        стр.wait_for_timeout(600)
    всего_после = _бд("SELECT COUNT(*) FROM custom_foods")[0][0]
    п.шаг("отмена НИЧЕГО не удалила", всего_до == всего_после,
          "записей %d -> %d" % (всего_до, всего_после))


def раздел_упражнения(стр, п):
    print("\n== УПРАЖНЕНИЯ ==")
    стр.goto(БАЗА + "/admin/exercises", wait_until="domcontentloaded", timeout=60000)
    стр.wait_for_timeout(2500)

    п.орган(стр, "чип «Не проверено» — орган живой", '[data-pick="unchecked"]')
    п.последний(стр, "ПОСЛЕДНИЙ чип ряда — орган живой", "[data-pick]")
    п.орган(стр, "список групп мышц — орган живой", "#filter-muscle")
    п.орган(стр, "список оборудования — орган живой", "#filter-equipment")
    п.орган(стр, "поле поиска — орган живой", "#admin-q")

    # ДВА ОТБОРА СВЕРЯЮТСЯ С ЧИСЛОМ, А НЕ С НУЛЁМ (BACKLOG №268): здесь
    # стояло `стало >= 0` и `после_мышц >= 0`, истинное и на пустой сетке,
    # и на НЕСУЖЕННОЙ. Карточек на странице не больше `PAGE_SIZE`, поэтому
    # спрашивается ещё и «из N подошедших» подписи — иначе 30 из 873
    # неотличимо от 30 из 85.
    стр_размер = стр.evaluate("() => PAGE_SIZE")
    было = стр.evaluate("() => document.querySelectorAll('.ex-card').length")
    стр.click('[data-pick="unchecked"]')
    стр.wait_for_timeout(600)
    стало = стр.evaluate("() => document.querySelectorAll('.ex-card').length")
    подошло = стр.evaluate(ПОДОШЛО)
    значков = стр.evaluate(
        "() => document.querySelectorAll('.ex-card .ex-card-badge').length")
    в_базе = _бд("SELECT COUNT(*) FROM exercises"
                 " WHERE COALESCE(video_status, 'unchecked') = 'unchecked'")[0][0]
    п.шаг("отбор по статусу перерисовал сетку",
          в_базе > 0 and подошло == в_базе and стало == min(стр_размер, в_базе)
          and значков == 0,
          "карточек %d -> %d, подошло по подписи %d, в базе «не проверено» %d,"
          " со значком другого статуса %d" % (было, стало, подошло, в_базе, значков))

    # ГРУППА — ТА, ГДЕ «НЕ ПРОВЕРЕННЫХ» БОЛЬШЕ ВСЕГО: первая по списку бывает
    # пустой, и «0 из 0» выглядело бы как работающий отбор. Число считается
    # по данным страницы мимо отбора — вопрос про отбор, а не про выгрузку
    группа = стр.evaluate("""() => {
        const счёт = {};
        EXERCISES.forEach(e => {
          if ((e.video_status || 'unchecked') === 'unchecked' && e.muscle_group)
            счёт[e.muscle_group] = (счёт[e.muscle_group] || 0) + 1; });
        const лучшая = Object.entries(счёт).sort((a, b) => b[1] - a[1])[0];
        if (!лучшая) return null;
        const о = [...document.querySelectorAll('#filter-muscle option')]
          .find(o => o.value === лучшая[0]);
        return {ключ: лучшая[0], ждём: лучшая[1], подпись: о ? о.textContent.trim() : ''};
    }""")
    if not группа:
        п.шаг("список групп мышц отобрал", False,
              "ни одной группы с «не проверенными» — отбирать нечем")
    else:
        стр.select_option("#filter-muscle", группа["ключ"])
        стр.wait_for_timeout(600)
        после_мышц = стр.evaluate("() => document.querySelectorAll('.ex-card').length")
        подошло_м = стр.evaluate(ПОДОШЛО)
        чужих = стр.evaluate(
            "(м) => [...document.querySelectorAll('.ex-card-meta')]"
            ".filter(e => !e.textContent.trim().startsWith(м)).length",
            группа["подпись"])
        п.шаг("список групп мышц отобрал",
              подошло_м == группа["ждём"] > 0
              and после_мышц == min(стр_размер, группа["ждём"]) and чужих == 0,
              "«%s»: карточек %d, подошло по подписи %d, ждём %d, из чужой группы %d"
              % (группа["подпись"], после_мышц, подошло_м, группа["ждём"], чужих))
        стр.select_option("#filter-muscle", "all")
        стр.wait_for_timeout(500)

    примечание = стр.evaluate("() => document.getElementById('note').textContent.trim()")
    п.шаг("строка-объяснение непуста", len(примечание) > 40,
          примечание[:64] + "...")

    # ── ГЛАВНОЕ ДЕЙСТВИЕ: одобрить видео и увидеть это В БАЗЕ и В ЧИПЕ ──
    #
    # КАРТОЧКА НЕ В СТАТУСЕ `approved`, СТАТУС ВОЗВРАЩАЕТСЯ В `finally`
    # (BACKLOG №284; §6.0.3, четыре пункта).
    #   ПРЕЖНЯЯ ФОРМУЛИРОВКА: первая карточка «Все»; шаги «стало approved»
    #     и «чип изменился ИЛИ было approved»; возврат UPDATE-ом в конце
    #     раздела — только на нормальном пути и только при непустом прежнем.
    #   НОВАЯ: первая карточка страницы, чей статус В БАЗЕ не `approved`;
    #     шаги «было не approved И стало approved» и «чип вырос ровно на один
    #     и равен числу одобренных в базе»; возврат в `finally`, пустой
    #     прежний статус тоже.
    #   ПОЧЕМУ ПРЕЖНЯЯ НЕГОДНА: обрыв между нажатием и возвратом оставлял
    #     карточку `approved` (копия пробы из HEAD: статусов не как в снимке
    #     0 → 1, `Mountain_Climbers` no_video → approved), и на таком стенде
    #     оба шага проходят при кнопке, не делающей ничего: `'approved' ->
    #     'approved'`, `чип 1 -> 1`.
    #   ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ НА НОВОЙ: подлог «одобрение молчит» и
    #     `--контроль-уборки` (обрыв после смены статуса: с `finally`
    #     изменённых статусов 0, без него 1).
    стр.click('[data-pick="all"]')
    стр.wait_for_timeout(600)
    на_экране = стр.evaluate(
        "() => [...document.querySelectorAll('.ex-card')].map(c => c.dataset.id)")
    статусы = dict(_бд("SELECT id, video_status FROM exercises"))
    ид = next((и for и in на_экране
               if и in статусы and статусы[и] != "approved"), None)
    if not ид:
        return п.шаг("одобрение упражнения", False,
                     "ЗАМЕР НЕ СОСТОЯЛСЯ: карточек на экране %d, не одобренных"
                     " среди них 0" % len(на_экране))
    было_в_базе = статусы[ид]
    карточка = ".ex-card[data-id=%s]" % json.dumps(ид)
    n_до = стр.evaluate(ЧИП_ОДОБРЕНО)
    try:
        п.орган(стр, "кнопка «Одобрено» — орган живой",
                карточка + " .ex-btn-approve")
        стр.click(карточка + " .ex-btn-approve")
        стр.wait_for_timeout(1100)
        стало_в_базе = _бд("SELECT video_status FROM exercises WHERE id=?",
                           (ид,))[0][0]
        п.шаг("статус доехал ДО БАЗЫ",
              было_в_базе != "approved" and стало_в_базе == "approved",
              "%s: %r -> %r" % (ид, было_в_базе, стало_в_базе))
        n_после = стр.evaluate(ЧИП_ОДОБРЕНО)
        одобрено = _бд("SELECT COUNT(*) FROM exercises"
                       " WHERE video_status = 'approved'")[0][0]
        п.шаг("число в чипе «Одобрено» выросло на один СРАЗУ",
              n_после == n_до + 1 and n_после == одобрено,
              "чип %d -> %d, одобренных в базе %d" % (n_до, n_после, одобрено))

        # ── Замена ссылки: ряд раскрывается, поле живое ──────────────────
        стр.click(карточка + " .ex-btn-replace")
        стр.wait_for_timeout(500)
        п.орган(стр, "поле ссылки на видео — орган живой",
                ".ex-replace-row.open .ex-replace-input")
        п.орган(стр, "кнопка сохранения ссылки — орган живой",
                ".ex-replace-row.open .ex-replace-save")
    finally:
        _вернуть_упражнение(ид, было_в_базе)
        вернулось = _бд("SELECT video_status FROM exercises WHERE id=?",
                        (ид,))[0][0]
        п.шаг("статус упражнения возвращён", вернулось == было_в_базе,
              "%s: %r" % (ид, вернулось))


def раздел_каталог(стр, п):
    print("\n== ENSHROUDED ==")
    стр.goto(БАЗА + "/admin/enshrouded", wait_until="domcontentloaded", timeout=60000)
    стр.wait_for_timeout(2500)

    п.орган(стр, "чип «Кузнец» — орган живой", '[data-pick="blacksmith"]')
    п.последний(стр, "ПОСЛЕДНИЙ чип ряда — орган живой", "[data-pick]")
    п.последний(стр, "ПОСЛЕДНЯЯ вкладка ряда — орган живая",
                ".admin-tabs .tab-btn")
    п.орган(стр, "поле поиска — орган живой", "#admin-q")
    п.орган(стр, "кнопка «Добавить сет» — орган живая", ".ens-a-add")

    # СЧИТАЮТСЯ ВИДИМЫЕ СТРОКИ, А НЕ СТРОКИ В ДЕРЕВЕ (BACKLOG №265, §6.0.3).
    #
    #   ПРЕЖНЯЯ ФОРМУЛИРОВКА: `querySelectorAll('#ens-rows tr').length`.
    #   НОВАЯ: строк, для которых `checkVisibility()` отвечает «видно».
    #   ПОЧЕМУ ПРЕЖНЯЯ НЕГОДНА: с задачи 161 строки рисует сервер ОДИН раз,
    #     а отбор их ПРЯЧЕТ (`tr.hidden`), — в дереве всегда 90. Проба
    #     печатала «90 -> 90» на ИСПРАВНОМ отборе и то же самое на сломанном,
    #     то есть не различала их вовсе. Соседняя `check_ens_admin_ui.py`
    #     перешла на видимые строки тогда же; сюда починка не доехала.
    #     Три других раздела этого файла считают `tr:not([hidden])` —
    #     дефект был ровно в одном месте из четырёх.
    #   Видимость спрашивается `checkVisibility`, а не атрибутом: подлог
    #     контроля «отбор-не-прячет» ломает именно атрибут, и проба,
    #     спрашивающая его же, мерила бы подлог самим подлогом.
    #   ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ НА НОВОЙ: `--контроль`, подлог «отбор не прячет».
    ВИДНО = ("() => [...document.querySelectorAll('#ens-rows tr')]"
             ".filter(tr => tr.checkVisibility()).length")
    было = стр.evaluate(ВИДНО)
    n = стр.evaluate("() => +document.querySelector('[data-pick=\"blacksmith\"] .chip-n').textContent")
    стр.click('[data-pick="blacksmith"]')
    стр.wait_for_timeout(900)
    стало = стр.evaluate(ВИДНО)
    п.шаг("отбор по категории сузил каталог", стало == n,
          "строк %d -> %d, чип обещал %d" % (было, стало, n))
    в_базе = _бд("SELECT COUNT(*) FROM enshrouded_sets WHERE crafter='blacksmith'")[0][0]
    п.шаг("число чипа сходится С БАЗОЙ", n == в_базе,
          "чип %d, в базе %d" % (n, в_базе))
    стр.click('[data-pick="all"]')
    стр.wait_for_timeout(400)

    примечание = стр.evaluate("() => document.getElementById('note').textContent.trim()")
    п.шаг("строка-объяснение непуста", len(примечание) > 40,
          примечание[:64] + "...")

    п.орган(стр, "миниатюра сета — орган живой", "#ens-rows .ens-a-thumbwrap")
    п.орган(стр, "кнопка «Править» — орган живая", "#ens-rows .ens-a-edit")
    стр.click("#ens-rows .ens-a-edit")
    стр.wait_for_timeout(800)
    открыто = стр.evaluate(
        "() => { const m = document.getElementById('ens-edit');"
        " return !!m && m.classList.contains('open'); }")
    п.шаг("окно правки открылось", открыто)
    if открыто:
        п.орган(стр, "поле «Название по-русски» — орган живое", "#f-ru")
        п.орган(стр, "выбор файла картинки — орган живой", "#f-file")
        стр.keyboard.press("Escape")
        стр.wait_for_timeout(600)


class _Обрыв:
    """Страница, обрывающая раздел «Упражнения» СРАЗУ ПОСЛЕ смены статуса.

    Обрыв кладётся на первый клик после одобрения — раскрытие замены
    ссылки, — то есть ровно туда, где без `finally` статус остался бы
    `approved`. Остальное делегируется странице как есть."""

    def __init__(self, стр):
        self._стр = стр

    def __getattr__(self, имя):
        return getattr(self._стр, имя)

    def click(self, сел, *а, **к):
        if "ex-btn-replace" in сел:
            raise RuntimeError("ПОДЛОГ 284: обрыв после смены статуса")
        return self._стр.click(сел, *а, **к)


def прогон(ширина, высота, сенсор, подлог=None, только=None, сорвать=False):
    from playwright.sync_api import sync_playwright
    п = Проход(ширина)
    with sync_playwright() as pw:
        бр = pw.chromium.launch()
        к = бр.new_context(viewport={"width": ширина, "height": высота},
                           has_touch=сенсор, is_mobile=сенсор)
        if подлог:
            к.add_init_script(ПОДЛОГИ[подлог])
        стр = к.new_page()
        cdp = к.new_cdp_session(стр)
        if сенсор:
            ch._включить_сенсор(cdp)
        _вход(стр, cdp, сенсор)
        for имя, шаги in (("Пользователи", раздел_пользователи),
                          ("Продукты", раздел_продукты),
                          ("Упражнения", раздел_упражнения),
                          ("Enshrouded", раздел_каталог)):
            if только and имя not in только:
                continue
            try:
                шаги(_Обрыв(стр) if сорвать else стр, п)
            except Exception as e:
                # Падение раздела — ШАГ, а не конец прогона. Иначе подлог,
                # который проба уже честно назвала строкой выше, пропадал бы
                # вместе с ней: «упало» неотличимо от «не нашло».
                п.шаг("раздел «%s» доигран до конца" % имя, False,
                      "%s: %s" % (type(e).__name__, str(e).split(chr(10))[0][:70]))
        к.close()
        бр.close()
    return п


# ── ДОКАЗАТЕЛЬСТВА ПОДЛОГОВ (§6.0.3) ────────────────────────────────
#
# «Нужный шаг назван» доказательством НЕ является: провалиться шаг мог
# по другой причине — раздел не открылся, строка не нашлась. А подлог
# кладётся В СТРАНИЦУ через `add_init_script`, и он умеет провалиться
# МОЛЧА: исключение внутри страницы наружу не выходит. Ровно так
# в проекте однажды пришёл «НАЙДЕН» про подлог, не сделавший ничего.
#
# Каждое доказательство — НЕЗАВИСИМЫЙ замер того, что подлог собирался
# изменить: открывается нужный раздел и читается одно значение мимо
# всей машинерии прохода.
ДОКАЗАТЕЛЬСТВА = {
    "мёртвый чип": ("/admin/users", """
      () => {
        const ч = [...document.querySelectorAll('[data-pick]')];
        if (!ч.length) return 'чипов [data-pick] на экране нет';
        return 'выключенных чипов: ' + ч.filter(b => b.disabled).length
             + ' из ' + ч.length;
      }""", "сколько чипов отбора выключено"),
    "тумблер молчит": ("/admin/users", r"""
      () => 'toggleAccess: ' + (typeof toggleAccess === 'function'
              ? String(toggleAccess).replace(/\s+/g, ' ').slice(0, 60)
              : 'НЕТ')""", "тело обработчика тумблера доступа"),
    "удаление без вопроса": ("/admin/products", r"""
      () => 'delFood: ' + (typeof delFood === 'function'
              ? String(delFood).replace(/\s+/g, ' ').slice(0, 60)
              : 'НЕТ')""", "тело обработчика удаления продукта"),
    # Спрашивается ВИДИМОСТЬ после нажатия чипа «Кузнец», а не атрибут:
    # подлог ломает атрибут, и мерить его атрибутом значило бы спросить
    # у подлога, состоялся ли он.
    "отбор не прячет": ("/admin/enshrouded", """
      async () => {
        const ч = document.querySelector('[data-pick="blacksmith"]');
        if (!ч) return 'чипа «Кузнец» на экране нет';
        ч.click();
        await new Promise(r => setTimeout(r, 1200));
        const trs = [...document.querySelectorAll('#ens-rows tr')];
        return 'после «Кузнец» видно строк: '
             + trs.filter(tr => tr.checkVisibility()).length + ' из ' + trs.length;
      }""", "сколько строк каталога видно после чипа «Кузнец»"),
    # ТРИ ОТБОРА 268: мерится ТО, ЧТО ОТБОР ДЕЛАЕТ С ЭКРАНОМ, мимо шага
    "поиск молчит": ("/admin/users", """
      async () => {
        const r = document.querySelector('#rows tr');
        const запрос = r ? (r.dataset.email || '').split('@')[0] : '';
        const q = document.getElementById('admin-q');
        q.value = запрос;
        q.dispatchEvent(new Event('input', {bubbles: true}));
        await new Promise(r => setTimeout(r, 300));
        return 'видно строк после «' + запрос + '»: '
             + document.querySelectorAll('#rows tr:not([hidden])').length;
      }""", "сколько строк видно после ввода в поиск"),
    "отбор статуса молчит": ("/admin/exercises", """
      async () => {
        const ч = document.querySelector('[data-pick="unchecked"]');
        if (!ч) return 'чипа «Не проверено» нет';
        ч.click();
        await new Promise(r => setTimeout(r, 400));
        return 'чип «Не проверено» выбран: ' + ч.classList.contains('active');
      }""", "стал ли чип «Не проверено» выбранным после нажатия"),
    "группа мышц молчит": ("/admin/exercises", """
      async () => {
        const с = document.getElementById('filter-muscle');
        с.value = с.options[1].value;
        с.dispatchEvent(new Event('change', {bubbles: true}));
        await new Promise(r => setTimeout(r, 400));
        return 'подпись называет группу мышц: '
             + document.getElementById('note').textContent.includes('группа мышц');
      }""", "назвала ли подпись выбранную группу мышц"),
    # ОБРАБОТЧИК СО СТОРОНЫ СТРАНИЦЫ НЕ ВИДЕН: `addEventListener` не заводит
    # ни атрибута, ни свойства, и выражение ответило бы одинаково до подлога
    # и после. Число спрашивается у CDP — тот же приём, что у соседней пробы
    "отмена удаляет": ("/admin/products",
                       "CDP:#food-del .btn-secondary[data-modal-close]",
                       "сколько обработчиков click висит на «Отмене»"),
    # ДОКАЗАТЕЛЬСТВО НЕ МЕНЯЕТ БАЗУ (правило 6 письма захода 285): `fetch`
    # подменяется счётчиком, отвечающим без сервера, и мерится, дошло ли
    # нажатие «Одобрено» до запроса смены статуса. Чистое нажатие обязано
    # дать один запрос, под подлогом — ноль.
    "одобрение молчит": ("/admin/exercises", """
      async () => {
        const b = document.querySelector('.ex-card .ex-btn-approve');
        if (!b) return 'кнопок «Одобрено» на экране нет';
        let звонков = 0;
        const прежний = window.fetch;
        window.fetch = (u, o) => {
          if (String(u).includes('/status')) {
            звонков++;
            return Promise.resolve(new Response(
              '{"ok": true, "video_status": "approved"}',
              {status: 200, headers: {'Content-Type': 'application/json'}}));
          }
          return прежний(u, o);
        };
        b.click();
        await new Promise(r => setTimeout(r, 400));
        window.fetch = прежний;
        return 'запросов смены статуса после нажатия: ' + звонков;
      }""", "дошло ли нажатие «Одобрено» до запроса смены статуса"),
}


def _обработчиков(стр, кон, селектор):
    """Обработчики click на элементе — у CDP (изнутри страницы их не видно)."""
    cdp = кон.new_cdp_session(стр)
    cdp.send("DOM.enable")
    cdp.send("Runtime.enable")
    итог = cdp.send("Runtime.evaluate",
                    {"expression": "document.querySelector('%s')" % селектор})
    объект = итог.get("result", {}).get("objectId")
    if not объект:
        return "элемента %s в дереве нет" % селектор
    сп = cdp.send("DOMDebugger.getEventListeners", {"objectId": объект})
    return "обработчиков click: %d" % len(
        [л for л in сп.get("listeners", []) if л.get("type") == "click"])


def доказать_подлог(имя):
    """Состояние страницы БЕЗ подлога и С ним. Возвращает пару значений
    и подпись того, что мерилось."""
    from playwright.sync_api import sync_playwright

    путь, выражение, что = ДОКАЗАТЕЛЬСТВА[имя]
    ответы = []
    with sync_playwright() as pw:
        бр = pw.chromium.launch()
        for класть in (False, True):
            к = бр.new_context(viewport={"width": 1440, "height": 900})
            if класть:
                к.add_init_script(ПОДЛОГИ[имя])
            стр = к.new_page()
            cdp = к.new_cdp_session(стр)
            _вход(стр, cdp, False)
            стр.goto(БАЗА + путь, wait_until="domcontentloaded", timeout=60000)
            стр.wait_for_timeout(2500)
            if выражение.startswith("CDP:"):
                ответы.append(_обработчиков(стр, к, выражение[4:]))
            else:
                ответы.append(стр.evaluate(выражение))
            к.close()
        бр.close()
    return ответы[0], ответы[1], что


def контроль():
    print("=" * 74)
    print("ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ: %d подлога, каждый обязан быть назван"
          % len(ПОДЛОГИ))
    print("=" * 74)
    print("\nСНАЧАЛА ЧИСТЫЙ ПРОГОН — иначе беда, бывшая и до подлога,")
    print("засчиталась бы за находку контроля.\n")
    чисто = прогон(1440, 900, False)
    print("\n  чистый прогон: шагов %d, плохих %d" % (чисто.шагов, len(чисто.плохо)))
    if чисто.плохо:
        print("  !! КОНТРОЛЬ НЕ ЗАСЧИТАН: чистый прогон уже с находками.")
        return 1

    промах = несостоявшихся = 0
    for имя in ПОДЛОГИ:
        раздел, шаг_имя = ЧЕЙ_ШАГ[имя]
        print("\n" + "-" * 74)
        print("ПОДЛОГ: %s   (ждём находку на шаге «%s»)" % (имя, шаг_имя))
        print("-" * 74)
        # ШАГ ПЕРВЫЙ — ДОКАЗАТЬ, ЧТО ПОДЛОГ СОСТОЯЛСЯ (§6.0.3)
        д_ч, д_п, что = доказать_подлог(имя)
        состоялся = д_ч != д_п
        print("  доказательство (%s):" % что)
        print("     чисто      = %s" % д_ч)
        print("     с подлогом = %s" % д_п)
        print("     → %s" % ("ПОДЛОГ СОСТОЯЛСЯ" if состоялся
                             else "ПОДЛОГ НЕ СОСТОЯЛСЯ"))
        if not состоялся:
            промах += 1
            несостоявшихся += 1
            print("  -> ПРОПУЩЕН: ломать нечего, вердикт прохода про этот "
                  "подлог не значит ничего")
            continue
        p = прогон(1440, 900, False, подлог=имя)
        назван = any(шаг_имя in н for н, _ in p.плохо)
        плохих = len(p.плохо)
        print("  -> плохих %d, нужный шаг назван: %s" % (плохих, назван))
        if not назван:
            промах += 1

    print("\n" + "=" * 74)
    if промах:
        print("ПРОВАЛЕН: не найдено %d из %d подлогов "
              "(из них НЕ СОСТОЯЛОСЬ %d)."
              % (промах, len(ПОДЛОГИ), несостоявшихся))
        return 1
    print("ПРОЙДЕН: все %d подлога названы своими шагами, чистый прогон чист."
          % len(ПОДЛОГИ))
    return 0


# ── КОНТРОЛЬ УБОРКИ: `--контроль-уборки` (BACKLOG №284) ─────────────
#
# ПОДЛОГ ЛОМАЕТ ПРОВЕРЯЕМОЕ ЗВЕНО — НОРМАЛЬНЫЙ ХОД РАЗДЕЛА: он обрывается
# исключением сразу после смены статуса, то есть там, где без `finally`
# статус остался бы `approved`. Прогона три, числа — ПО БАЗЕ, против
# снимка статусов до первого прогона:
#   обычный прогон        — изменённых статусов 0;
#   обрыв, уборка на месте — 0;
#   обрыв, уборка снята    — ДОКАЗАТЕЛЬСТВО: 1, то есть статус к моменту
#                            обрыва действительно сменился, и первый ноль
#                            дала именно уборка, а не несостоявшееся
#                            одобрение.
# Оставленное снятой уборкой добирается той же функцией, и хвост после
# контроля обязан быть пустым.
def _статусы():
    return dict(_бд("SELECT id, video_status FROM exercises"))


def контроль_уборки():
    global _вернуть_упражнение
    база = _статусы()
    итог = {}
    for имя, сорвать, снять in (("обычный прогон", False, False),
                                ("обрыв, уборка на месте", True, False),
                                ("обрыв, уборка снята", True, True)):
        прежняя = _вернуть_упражнение
        if снять:
            _вернуть_упражнение = lambda ид, статус: None          # noqa: E731
        try:
            p = прогон(1440, 900, False, только=("Упражнения",), сорвать=сорвать)
        finally:
            _вернуть_упражнение = прежняя
        оборвался = any("ПОДЛОГ 284" in что for _, что in p.плохо)
        изменено = sorted((ид, база[ид], ст) for ид, ст in _статусы().items()
                          if база.get(ид) != ст)
        итог[имя] = (оборвался, len(изменено))
        print("  %-24s обрыв состоялся: %-5s изменённых статусов после: %d %s"
              % (имя, оборвался, len(изменено), изменено))
        for ид, было, _ in изменено:
            _вернуть_упражнение(ид, было)
    хвост = [ид for ид, ст in _статусы().items() if база.get(ид) != ст]
    print("  после добора изменённых статусов: %d" % len(хвост))
    верно = (итог["обычный прогон"] == (False, 0)
             and итог["обрыв, уборка на месте"] == (True, 0)
             and итог["обрыв, уборка снята"] == (True, 1)
             and not хвост)
    print("КОНТРОЛЬ УБОРКИ: %s" % (
        "ПОДЛОГ ПОЙМАН ЧИСЛОМ (%d → %d)" % (итог["обрыв, уборка на месте"][1],
                                          итог["обрыв, уборка снята"][1])
        if верно else "НЕ ДОКАЗАНО — разобрать числа выше"))
    return 0 if верно else 1


if __name__ == "__main__":
    арг = sys.argv[1:]
    if "--база" in арг:
        БАЗА = арг[арг.index("--база") + 1]
    if "--контроль-уборки" in арг:
        sys.exit(контроль_уборки())
    if "--контроль" in арг:
        sys.exit(контроль())
    ш = int(арг[арг.index("--ширина") + 1]) if "--ширина" in арг else 1440
    в, сенсор = (844, True) if ш <= 640 else (900, False)
    print("=" * 74)
    print("ПРОХОД АДМИНКИ НАСКВОЗЬ — ширина %d%s"
          % (ш, " (сенсор)" if сенсор else ""))
    print("=" * 74)
    p = прогон(ш, в, сенсор)
    print("\n" + "=" * 74)
    print("ШАГОВ %d, ПЛОХИХ %d" % (p.шагов, len(p.плохо)))
    for имя, что in p.плохо:
        print("   !! %s   %s" % (имя, что))
    print("\nОтдельно: этот ноль стоит чего-то только вместе с "
          "`py check_admin_ui.py --контроль`.")
    sys.exit(1 if p.плохо else 0)
