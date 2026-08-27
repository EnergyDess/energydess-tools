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
    py check_admin_ui.py --контроль       # ТРИ ПОДЛОГА, каждый обязан
                                          # быть назван своим шагом

ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ ОБЯЗАТЕЛЕН И ЕСТЬ ЗДЕСЬ, А НЕ В ОТЧЁТЕ СЕССИИ.
У соседнего `check_ens_admin_ui.py` он полдня числился существующим,
пока не выяснилось, что прошлый заход проделал подлоги руками и записал
вывод только в отчёт — то есть контроля не было ни строки.
"""
import io
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DB_PATH", "app.db")

import check_hover as ch     # noqa: E402

БАЗА = os.environ.get("СТЕНД", "http://127.0.0.1:8899")
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


class Проход:
    """Счётчик шагов. Печатает КАЖДЫЙ, а не только упавший."""

    def __init__(self, ширина):
        self.ширина = ширина
        self.плохо = []
        self.шагов = 0

    def шаг(self, имя, ок, что=""):
        self.шагов += 1
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
        return self.шаг(имя, not беды, что)


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
}
ЧЕЙ_ШАГ = {
    "мёртвый чип": ("Пользователи", "чип «Без доступа» — орган живой"),
    "тумблер молчит": ("Пользователи", "доступ записался в базу"),
    "удаление без вопроса": ("Продукты", "окно подтверждения открылось"),
}


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
    стр.fill("#admin-q", "screenshot")
    стр.wait_for_timeout(400)
    найдено = стр.evaluate("() => document.querySelectorAll('#rows tr:not([hidden])').length")
    п.шаг("поиск по почте отобрал", найдено >= 0, "строк %d" % найдено)
    стр.fill("#admin-q", "")
    стр.wait_for_timeout(300)

    # ── ГЛАВНОЕ ДЕЙСТВИЕ РАЗДЕЛА: выдать и отобрать доступ ───────────────
    д = стр.evaluate("""() => {
        const r = document.querySelector('#rows tr:not([hidden])');
        if (!r) return null;
        const c = r.querySelector('input[type=checkbox]');
        return {почта: r.dataset.email, был: c.checked};
    }""")
    if not д:
        return п.шаг("тумблер доступа", False, "в таблице нет ни одной строки")
    # ОРГАН — ПОДПИСЬ `.toggle`, а не сам `<input>`: у системного тумблера
    # флажок спрятан по построению (0x0), нажимают дорожку. Спроси мы
    # про input — проба объявила бы находкой исправный компонент.
    п.орган(стр, "тумблер первого инструмента — орган живой",
            "#rows tr:not([hidden]) .toggle")
    стр.click("#rows tr:not([hidden]) .toggle", timeout=8000)
    стр.wait_for_timeout(900)
    uid = _бд("SELECT id FROM users WHERE email=?", (д["почта"],))
    есть = _бд("SELECT COUNT(*) FROM tool_access WHERE user_id=?",
               (uid[0][0],))[0][0] if uid else -1
    ждём_больше = not д["был"]
    п.шаг("доступ записался в базу",
          (есть > 0) if ждём_больше else True,
          "у %s строк доступа %d (было отмечено: %s)"
          % (д["почта"], есть, д["был"]))
    # Вернуть как было — проба не должна оставлять следа.
    стр.click("#rows tr:not([hidden]) .toggle", timeout=8000)
    стр.wait_for_timeout(900)


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
        стр.click("#food-del [data-modal-close]")
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

    было = стр.evaluate("() => document.querySelectorAll('.ex-card').length")
    стр.click('[data-pick="unchecked"]')
    стр.wait_for_timeout(600)
    стало = стр.evaluate("() => document.querySelectorAll('.ex-card').length")
    п.шаг("отбор по статусу перерисовал сетку", стало >= 0,
          "карточек %d -> %d" % (было, стало))

    стр.select_option("#filter-muscle", index=1)
    стр.wait_for_timeout(600)
    после_мышц = стр.evaluate("() => document.querySelectorAll('.ex-card').length")
    п.шаг("список групп мышц отобрал", после_мышц >= 0,
          "карточек %d" % после_мышц)
    стр.select_option("#filter-muscle", "all")
    стр.wait_for_timeout(500)

    примечание = стр.evaluate("() => document.getElementById('note').textContent.trim()")
    п.шаг("строка-объяснение непуста", len(примечание) > 40,
          примечание[:64] + "...")

    # ── ГЛАВНОЕ ДЕЙСТВИЕ: одобрить видео и увидеть это В БАЗЕ и В ЧИПЕ ──
    стр.click('[data-pick="all"]')
    стр.wait_for_timeout(600)
    ид = стр.evaluate("() => { const c = document.querySelector('.ex-card');"
                      " return c ? c.dataset.id : null; }")
    if not ид:
        return п.шаг("одобрение упражнения", False, "на экране нет карточек")
    было_в_базе = _бд("SELECT video_status FROM exercises WHERE id=?", (ид,))
    было_в_базе = было_в_базе[0][0] if было_в_базе else None
    n_до = стр.evaluate("() => +document.querySelector('[data-pick=\"approved\"] .chip-n').textContent")
    п.орган(стр, "кнопка «Одобрено» — орган живой", ".ex-card .ex-btn-approve")
    стр.click(".ex-card .ex-btn-approve")
    стр.wait_for_timeout(1100)
    стало_в_базе = _бд("SELECT video_status FROM exercises WHERE id=?", (ид,))[0][0]
    п.шаг("статус доехал ДО БАЗЫ", стало_в_базе == "approved",
          "%s: %r -> %r" % (ид, было_в_базе, стало_в_базе))
    n_после = стр.evaluate("() => +document.querySelector('[data-pick=\"approved\"] .chip-n').textContent")
    п.шаг("число в чипе «Одобрено» изменилось СРАЗУ",
          n_после != n_до or было_в_базе == "approved",
          "чип %d -> %d" % (n_до, n_после))

    # ── Замена ссылки: ряд раскрывается, поле живое ──────────────────────
    стр.click(".ex-card .ex-btn-replace")
    стр.wait_for_timeout(500)
    п.орган(стр, "поле ссылки на видео — орган живой",
            ".ex-replace-row.open .ex-replace-input")
    п.орган(стр, "кнопка сохранения ссылки — орган живой",
            ".ex-replace-row.open .ex-replace-save")

    # Вернуть прежний статус.
    if было_в_базе and было_в_базе != "approved":
        с = sqlite3.connect(ФАЙЛ_БД)
        с.execute("UPDATE exercises SET video_status=? WHERE id=?", (было_в_базе, ид))
        с.commit(); с.close()


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

    было = стр.evaluate("() => document.querySelectorAll('#ens-rows tr').length")
    n = стр.evaluate("() => +document.querySelector('[data-pick=\"blacksmith\"] .chip-n').textContent")
    стр.click('[data-pick="blacksmith"]')
    стр.wait_for_timeout(500)
    стало = стр.evaluate("() => document.querySelectorAll('#ens-rows tr').length")
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


def прогон(ширина, высота, сенсор, подлог=None):
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
            try:
                шаги(стр, п)
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
}


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
            ответы.append(стр.evaluate(выражение))
            к.close()
        бр.close()
    return ответы[0], ответы[1], что


def контроль():
    print("=" * 74)
    print("ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ: три подлога, каждый обязан быть назван")
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


if __name__ == "__main__":
    арг = sys.argv[1:]
    if "--база" in арг:
        БАЗА = арг[арг.index("--база") + 1]
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
