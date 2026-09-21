"""РЕЕСТР ЗАМЕЧАНИЙ ВЛАДЕЛЬЦА ПО HH-АССИСТЕНТУ (BACKLOG №352, письмо 4).

ПРОВЕРКА, код 1 при находке, 2 — замерить нечем (стенда нет).

ЗАЧЕМ ОТДЕЛЬНЫЙ ФАЙЛ, А НЕ ШАГИ В `check_hh_ui`. Письмо 3 сдали
с зелёными проверками, и владелец за пять минут на проде нашёл больше
десятка дефектов; один из них — немой отказ: переключатель языка
не менял ничего видимого, а загрузка ссылки следом молча возвращала
русский. Сквозной проход (`check_hh_ui`) спрашивает «работает ли
ЭКРАН», и на каждый из этих дефектов он отвечал «да». Здесь каждое
ЗАМЕЧАНИЕ — отдельная строка с номером письма и своим подлогом:
починили — строка зелёная, вернули поломку — она называет себя.

ОДНА КОМАНДА НА ВЕСЬ РЕЕСТР. Замечание, которое негде увидеть
списком, не запускают и о нём не помнят (§6.0.13).

ВЫЗОВОВ МОДЕЛИ НОЛЬ: ответы генерации подделываются В СТРАНИЦЕ —
путь кода при этом тот же. Резюме и письма ВЫДУМАННЫЕ (§5.1).

ПИШЕТ В БАЗУ СТЕНДА: удаляет письмо из истории и правит поля досье —
это и есть проверка действием, «ответил ли сервер» тут не ответ (§6.3).
ПОСЛЕ ПРОГОНА СТЕНД ПЕРЕСЕЯТЬ: `py make_local_user.py --seed`.
В ряды §6.0.2 не входит по этой причине — ряд обязан быть безопасным
для любого прогона.

КЛЮЧИ:
  --контроль     подлоги, по одному на замечание: каждый возвращает
                 СВОЮ поломку и обязан уронить ИМЕННО свою строку;
  --только N,M   часть реестра по номерам замечаний.
"""
import json
import os
import sys

try:
    import probe_guard  # noqa: F401  ПРОПУСК вместо трассы (§6.0.1)
except ImportError:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_hover as ch  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# Выдуманная вакансия: настоящих данных владельца в пробе нет ни строки.
ПИСЬМО = ("Здравствуйте! Увидел вашу вакансию и хочу предложить свою "
          "кандидатуру. Собирал конвейеры разметки и выводил модели "
          "детекции в продакшн.")
АНАЛИЗ = {
    "relevance_score": 8,
    "relevance_reason": "Опыт совпадает с требованиями по ключевым пунктам.",
    "key_matches": ["опыт эксплуатации моделей детекции", "Python и PyTorch"],
    "missing_skills": ["конвейеры разметки в больших командах"],
    "job_title": "Инженер по машинному зрению",
    "company_name": "ООО Пример",
}
ВАКАНСИЯ = ("Требуется инженер по машинному зрению. Обязанности: сборка "
            "конвейера разметки, дообучение моделей детекции. Требования: "
            "Python, PyTorch, опыт эксплуатации моделей в проде.")
ССЫЛКА = "https://example.test/vacancy/1"

находок = 0
пропусков = 0
_строки = []


def шаг(номер, имя, условие, подробность="", собрано=None, отрицание=None):
    """Одно замечание владельца. `собрано=0` — ПРОПУСК, а не зелёный (§6.0.1)."""
    global находок, пропусков
    if собрано is not None and собрано == 0:
        пропусков += 1
        исход = "ПРОПУСК"
    elif условие:
        исход = "ok"
    else:
        находок += 1
        исход = "ПЛОХО"
    _строки.append((номер, имя, исход, подробность))
    print(f"  {исход:8} №{номер:<3} {имя}" + (f" — {подробность}" if подробность else ""))
    return исход == "ok"


# ── Подделка ответов: путь кода в браузере тот же, денег не стоит ─────────
ПОДДЕЛКА = """
window.__ЗАПРОСЫ = [];
window.__ПИСЬМО = %ПИСЬМО%;
window.__АНАЛИЗ = %АНАЛИЗ%;
const исходныйFetch = window.fetch;
window.fetch = async (u, o) => {
  const адрес = typeof u === 'string' ? u : u.url;
  const тело = o && o.body ? o.body : null;
  window.__ЗАПРОСЫ.push({адрес, тело});
  const ответ = (д) => new Response(JSON.stringify(д),
      {status: 200, headers: {'Content-Type': 'application/json'}});
  if (адрес.includes('/api/generate-letter')) {
    if (window.__ЗАДЕРЖКА) await new Promise(r => setTimeout(r, window.__ЗАДЕРЖКА));
    return ответ({letter: window.__ПИСЬМО, letter_id: 424242, analysis: window.__АНАЛИЗ});
  }
  if (адрес.includes('/api/analyze-vacancy')) return ответ(window.__АНАЛИЗ);
  if (адрес.includes('/api/cover-letters/')) return ответ({ok: true});
  if (адрес.includes('/api/fetch-url'))
    return ответ({text: 'Vacancy: computer vision engineer. Duties: pipelines.', chars: 52});
  return исходныйFetch(u, o);
};
"""


# ── ВОЗВРАТ РЕЗЮМЕ СТЕНДА ────────────────────────────────────────────────
# Проба ПРАВИТ резюме (иначе «правка легла в базу» не проверить), и без
# возврата каждый прогон оставляет стенд другим: замер — после нескольких
# прогонов подряд разделов стало 2 вместо 9, и контроль начал падать
# на подлоге, к резюме отношения не имеющем. Инструмент приёмки,
# оставляющий стенд не таким, каким взял, ломает не свой прогон,
# а следующий (§6.0.3, шестая причина неповторимости).
БАЗА_СТЕНДА = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.db")
ПОЧТА_СЪЁМКИ = "screenshot@local.dev"


def _снять_таблицу(запрос):
    """Снимок строки аккаунта съёмки: (колонки, значения) либо None."""
    import sqlite3
    if not os.path.exists(БАЗА_СТЕНДА):
        return None
    с = sqlite3.connect(БАЗА_СТЕНДА)
    try:
        кур = с.execute(запрос, (ПОЧТА_СЪЁМКИ,))
        ряд = кур.fetchone()
        return ([о[0] for о in кур.description], ряд) if ряд else None
    finally:
        с.close()


def _досье_снять():
    """Досье возвращается так же, как резюме: проба ПРАВИТ его поля,
    и без возврата след пробы остаётся на стенде — он попал даже
    в снимок приёмки («Проба03776» в поле профессии)."""
    return _снять_таблицу(
        "SELECT * FROM hh_profiles WHERE user_id ="
        " (SELECT id FROM users WHERE email = ?)")


def _досье_вернуть(снимок):
    import sqlite3
    if not снимок or not os.path.exists(БАЗА_СТЕНДА):
        return
    колонки, значения = снимок
    поля = [к for к in колонки if к not in ("id", "user_id")]
    if not поля:
        return
    зн = [значения[колонки.index(к)] for к in поля]
    с = sqlite3.connect(БАЗА_СТЕНДА)
    try:
        с.execute("UPDATE hh_profiles SET %s WHERE user_id ="
                  " (SELECT id FROM users WHERE email = ?)"
                  % ", ".join("%s = ?" % к for к in поля), зн + [ПОЧТА_СЪЁМКИ])
        с.commit()
    finally:
        с.close()


def _резюме_снять():
    import sqlite3
    if not os.path.exists(БАЗА_СТЕНДА):
        return None
    с = sqlite3.connect(БАЗА_СТЕНДА)
    try:
        ряд = с.execute(
            "SELECT r.resume_text FROM resumes r JOIN users u ON u.id = r.user_id"
            " WHERE u.email = ?", (ПОЧТА_СЪЁМКИ,)).fetchone()
        return ряд[0] if ряд else None
    finally:
        с.close()


def _резюме_вернуть(текст):
    import sqlite3
    if текст is None or not os.path.exists(БАЗА_СТЕНДА):
        return
    с = sqlite3.connect(БАЗА_СТЕНДА)
    try:
        с.execute(
            "UPDATE resumes SET resume_text = ? WHERE user_id ="
            " (SELECT id FROM users WHERE email = ?)", (текст, ПОЧТА_СЪЁМКИ))
        с.commit()
    finally:
        с.close()


def _нажать(стр, селектор, ждать=400):
    """Нажать, если орган ВИДЕН; иначе вернуть False.

    Нажатие по мёртвому органу висит до таймаута и валит прогон
    стектрейсом — то есть подлог ОДНОГО замечания уносит с собой весь
    реестр. Замер: так контроль обрывался дважды (§6.0.3).
    """
    орган = стр.locator(селектор).first
    if not орган.count():
        return False
    if not орган.evaluate("e => e.checkVisibility({checkOpacity: true})"):
        return False
    орган.click()
    стр.wait_for_timeout(ждать)
    return True


def _страница(бр, подлог=None, ширина=1920):
    ctx = бр.new_context(viewport={"width": ширина, "height": 1080})
    стр = ctx.new_page()
    ch._войти(стр)
    стр.add_init_script(ПОДДЕЛКА
                        .replace("%ПИСЬМО%", json.dumps(ПИСЬМО, ensure_ascii=False))
                        .replace("%АНАЛИЗ%", json.dumps(АНАЛИЗ, ensure_ascii=False)))
    if подлог:
        стр.add_init_script(подлог)
    return ctx, стр


# ══════════════════════════════════════════════════════════════════════════
# БЛОК 1. НАПИСАНИЕ ПИСЬМА И ШАПКА
# ══════════════════════════════════════════════════════════════════════════


def _подсветка_языка(стр):
    """Какая кнопка языка ВЫДЕЛЕНА НА ЭКРАНЕ: та, чей фон или цвет
    отличается от соседки. Две одинаковые — `None`."""
    вид = стр.eval_on_selector_all(
        ".letter-lang-seg button",
        "e => e.map(b => { const s = getComputedStyle(b);"
        " return [b.dataset.lang, s.backgroundColor + '|' + s.color]; })")
    if len(вид) != 2 or вид[0][1] == вид[1][1]:
        return None
    # выделенная — та, у которой фон не прозрачный
    for язык, в in вид:
        if not в.startswith("rgba(0, 0, 0, 0)"):
            return язык
    return None

def замечания_письма(бр, подлог=None):
    """№1–4: язык, индикатор загрузки, кнопки готового письма, цвет вакансии."""
    ctx, стр = _страница(бр, подлог)
    стр.goto(ch.БАЗА + "/hh", wait_until="domcontentloaded")
    стр.wait_for_timeout(900)

    # ── №1. ЯЗЫК ПИСЬМА ──────────────────────────────────────────────────
    # Немой отказ письма 3: выбор English не менял на экране НИЧЕГО
    # (селектор подсветки искал класс, которого у кнопок нет), а загрузка
    # ссылки следом молча возвращала русский. Спрашиваются ОБЕ половины:
    # видимое состояние И то, что ушло в запрос.
    стр.fill("#job-input", ВАКАНСИЯ)
    стр.wait_for_timeout(900)
    стр.click(".letter-lang-seg button[data-lang=en]")
    # ПОДСВЕТКА СПРАШИВАЕТСЯ У ВЫЧИСЛЕННОГО ВИДА, А НЕ У КЛАССА. Здесь
    # стояло `classList.contains('active')`, а `.v2-seg-btn` класса
    # `.active` не знает вовсе: проба была ЗЕЛЁНОЙ при подсветке, мёртвой
    # на экране, — авария на проде 21.09. Указатель уводится, иначе
    # отличие даёт наведение, а не выбор.
    стр.mouse.move(1, 1)
    стр.wait_for_timeout(350)
    подсветка = _подсветка_языка(стр)
    шаг(1, "язык-английский-подсвечен", подсветка == "en",
        "выделена по виду: %s" % подсветка)

    стр.evaluate("window.__ЗАПРОСЫ = []")
    стр.click("#generate-btn")
    стр.wait_for_selector("#letter-content", state="visible", timeout=9000)
    ушло = стр.evaluate(
        "window.__ЗАПРОСЫ.filter(з => з.адрес.includes('generate-letter'))"
        ".map(з => JSON.parse(з.тело))")
    шаг(1, "язык-английский-ушёл-в-запрос",
        bool(ушло) and ушло[0].get("lang") == "en",
        "lang=%s" % (ушло[0].get("lang") if ушло else "запроса нет"),
        собрано=len(ушло))

    стр.click(".letter-lang-seg button[data-lang=ru]")
    стр.evaluate("window.__ЗАПРОСЫ = []")
    стр.click("#regen-btn")
    стр.wait_for_timeout(900)
    ушло = стр.evaluate(
        "window.__ЗАПРОСЫ.filter(з => з.адрес.includes('generate-letter'))"
        ".map(з => JSON.parse(з.тело))")
    шаг(1, "язык-русский-ушёл-в-запрос",
        bool(ушло) and ушло[0].get("lang") == "ru",
        "lang=%s" % (ушло[0].get("lang") if ушло else "запроса нет"),
        собрано=len(ушло))

    # Главный порядок действий владельца: выбрал язык, ПОТОМ вставил ссылку.
    # Прежде `resetLetterLang()` в загрузке ссылки стирал выбор молча.
    стр.evaluate("clearJobText()")
    стр.click(".letter-lang-seg button[data-lang=en]")
    стр.fill("#job-input", ССЫЛКА)
    стр.wait_for_timeout(1600)
    стр.mouse.move(1, 1)
    стр.wait_for_timeout(350)
    после_ссылки = _подсветка_языка(стр)
    шаг(1, "ссылка-не-стирает-выбор-языка", после_ссылки == "en",
        "выделена по виду после загрузки ссылки: %s" % после_ссылки)

    # ── №2. ОДИН ИНДИКАТОР ЗАГРУЗКИ ──────────────────────────────────────
    стр.evaluate("window.__ЗАДЕРЖКА = 2500")
    стр.evaluate("clearJobText()")
    стр.fill("#job-input", ВАКАНСИЯ)
    стр.wait_for_timeout(700)
    стр.click("#generate-btn")
    стр.wait_for_timeout(900)          # середина генерации
    во_время = стр.evaluate(
        "() => {"
        " const анимы = [];"
        " document.querySelectorAll('*').forEach(e => {"
        "   const s = getComputedStyle(e), r = e.getBoundingClientRect();"
        "   if (r.width < 1 || r.height < 1) return;"
        "   if (!e.checkVisibility({checkOpacity: true, checkVisibilityCSS: true})) return;"
        "   if (s.animationName && s.animationName !== 'none')"
        "     анимы.push(e.className.toString().slice(0, 40));"
        " });"
        " const к = document.getElementById('generate-btn');"
        " return {анимы, выключена: к.disabled,"
        "         текст: document.getElementById('btn-text').textContent.trim(),"
        "         значок: document.getElementById('btn-icon').innerHTML.trim().length,"
        "         этап: document.getElementById('loading-text').textContent.trim()};"
        "}")
    шаг(2, "индикатор-загрузки-один", len(во_время["анимы"]) == 1,
        "анимированных: %d %s" % (len(во_время["анимы"]), во_время["анимы"]))
    шаг(2, "кнопка-выключена-и-без-значка",
        во_время["выключена"] is True and во_время["значок"] == 0
        and "Пишу письмо" in во_время["текст"],
        "disabled=%s значок=%d текст=%r" % (во_время["выключена"], во_время["значок"],
                                            во_время["текст"]))
    # Выдуманных этапов нет: генерация — ОДИН запрос, и границы этапов
    # браузеру не видны вовсе (замер 2026-09-20).
    шаг(2, "этап-не-выдуман", "Анализирую" not in во_время["этап"],
        "текст этапа: %r" % во_время["этап"])
    стр.wait_for_selector("#letter-content", state="visible", timeout=9000)
    стр.evaluate("window.__ЗАДЕРЖКА = 0")

    # ── №3. КНОПКИ ГОТОВОГО ПИСЬМА ───────────────────────────────────────
    действия = стр.evaluate(
        "() => {"
        " const р = document.getElementById('result-actions');"
        " const к = [...р.querySelectorAll('button')].filter(b => b.checkVisibility());"
        " const м = к.map(b => b.getBoundingClientRect());"
        " const зазоры = [];"
        " for (let i = 0; i + 1 < м.length; i++)"
        "   зазоры.push(Math.round((м[i+1].left - м[i].right) * 10) / 10);"
        " return {подписи: к.map(b => b.textContent.trim()), зазоры,"
        "         новое: !!document.getElementById('new-letter-btn'),"
        "         главных: к.filter(b => b.classList.contains('v2-btn-primary')).length};"
        "}")
    шаг(3, "новое-письмо-убрано", действия["новое"] is False)
    шаг(3, "кнопок-письма-три-одна-главная",
        len(действия["подписи"]) == 3 and действия["главных"] == 1,
        "подписи: %s" % действия["подписи"])
    шаг(3, "зазоры-кнопок-равны",
        len(set(действия["зазоры"])) == 1,
        "зазоры: %s" % действия["зазоры"], собрано=len(действия["зазоры"]))

    # Каждое действие проверяется ДЕЙСТВИЕМ, а не видом (§6.3).
    ctx.grant_permissions(["clipboard-read", "clipboard-write"])
    стр.click("#copy-btn")
    стр.wait_for_timeout(400)
    буфер = стр.evaluate("navigator.clipboard.readText()")
    шаг(3, "копирование-кладёт-письмо-в-буфер",
        "Здравствуйте" in (буфер or ""), "в буфере %d знаков" % len(буфер or ""),
        собрано=len(буфер or ""))

    стр.click("#edit-btn")
    стр.wait_for_timeout(300)
    стр.evaluate(
        "() => { const п = document.getElementById('letter-content');"
        " п.textContent = п.innerText + ' Правка владельца.'; }")
    стр.evaluate("window.__ЗАПРОСЫ = []")
    стр.click("#edit-btn")
    стр.wait_for_timeout(700)
    ушедшее = стр.evaluate(
        "window.__ЗАПРОСЫ.filter(з => з.адрес.includes('/api/cover-letters/'))"
        ".map(з => JSON.parse(з.тело))")
    # «Правка сохранена» проверяется ТЕМ, ЧТО УШЛО НА СЕРВЕР, а не тем,
    # что экран не ругнулся: `saveLetter` глотает отказ молча.
    шаг(3, "правка-уходит-на-сервер",
        bool(ушедшее) and "Правка владельца." in ушедшее[0].get("letter_text", ""),
        "запросов правки: %d%s" % (len(ушедшее),
                                   "" if not ушедшее else ", текст дошёл"),
        собрано=len(ушедшее))

    стр.evaluate("window.__ЗАПРОСЫ = []")
    стр.click("#regen-btn")
    стр.wait_for_timeout(900)
    перег = стр.evaluate(
        "window.__ЗАПРОСЫ.filter(з => з.адрес.includes('generate-letter')).length")
    шаг(3, "перегенерация-шлёт-новый-запрос", перег > 0, "запросов: %d" % перег)

    # Путь «начать заново» после решения владельца остался ОДИН —
    # «Очистить» под полем. Он обязан быть достижим ИМЕННО ПОСЛЕ
    # генерации: прежде кнопка пряталась вместе с уборкой черновика,
    # и текст вакансии оставался в поле без единого способа его убрать.
    поле = стр.evaluate(
        "() => ({знаков: document.getElementById('job-input').value.length,"
        " скрыта: document.getElementById('clear-text-btn').hidden})")
    шаг(3, "очистить-доступна-после-генерации",
        поле["знаков"] > 0 and поле["скрыта"] is False,
        "в поле %d знаков, кнопка скрыта: %s" % (поле["знаков"], поле["скрыта"]),
        собрано=поле["знаков"])
    # НАЖАТИЕ ПО МЁРТВОМУ ОРГАНУ НЕ РОНЯЕТ ПРОГОН, а становится ПРОПУСКОМ:
    # первая версия висла на скрытой кнопке 30 секунд и валила контроль
    # стектрейсом — то есть подлог соседнего замечания уносил с собой
    # весь реестр (§6.0.3).
    видна = стр.eval_on_selector("#clear-text-btn",
                                 "e => e.checkVisibility({checkOpacity: true})")
    if видна:
        стр.click("#clear-text-btn")
        стр.wait_for_timeout(300)
    после = стр.evaluate("document.getElementById('job-input').value.length")
    шаг(3, "очистить-чистит-поле", видна and после == 0,
        "осталось знаков: %d" % после, собрано=1 if видна else 0)

    # ── №4. ЦВЕТ ЗАГРУЖЕННОГО ТЕКСТА ВАКАНСИИ ────────────────────────────
    стр.evaluate("clearJobText()")
    стр.fill("#job-input", ССЫЛКА)
    стр.wait_for_timeout(1500)
    цв = стр.evaluate(
        "() => {"
        " const п = document.getElementById('fetched-preview');"
        " const d = document.createElement('div');"
        " d.style.color = 'var(--v2-text)';"
        " document.body.appendChild(d);"
        " const основной = getComputedStyle(d).color;"
        " d.remove();"
        " return {превью: getComputedStyle(п).color, основной, видно: п.checkVisibility()};"
        "}")
    шаг(4, "текст-вакансии-обычным-цветом",
        цв["превью"] == цв["основной"],
        "превью %s, основной %s" % (цв["превью"], цв["основной"]),
        собрано=1 if цв["видно"] else 0)
    ctx.close()


# ── №5. СВЕЧЕНИЕ ШАПКИ БЕЗ РЕЗКОГО КРАЯ ──────────────────────────────────
ИНСТРУМЕНТЫ = [("/hh", "hh"), ("/nutrition", "nutrition"), ("/workout", "workout"),
               ("/medkit", "medkit"), ("/enshrouded", "enshrouded")]

# Порог назван владельцем: «соседние столбцы нигде не отличаются больше
# чем на 3 по каналу». Считается на СГЛАЖЕННОЙ строке, и это не поблажка:
# зерно поверх градиента (`v2-grain.svg`) — статичная плитка шума, и разброс
# соседних пикселей ЕСТЬ ОНО САМО (замер: сырой скачок 4–5 при отсутствии
# края вовсе). Без зерна линейный градиент на тёмном фоне ложится полосами
# одного цвета до 1058 px подряд. Окно 9 усредняет зерно; ступенька края,
# которая была 41–55 единиц, его переживает с любым окном.
ПОРОГ_КРАЯ = 3.0
ОКНО = 9

ГЕОМЕТРИЯ = """() => {
  const ш = document.querySelector('.v2-page-head');
  const м = document.querySelector('.v2-shell-main');
  if (!ш || !м) return null;
  const a = ш.getBoundingClientRect(), b = м.getBoundingClientRect();
  return {шапка: {x: a.x, y: a.y, w: a.width}, main: {x: b.x, w: b.width}};
}"""


def _сглаженный_скачок(полоса):
    """Максимальный скачок соседних столбцов после усреднения окном."""
    if len(полоса) < ОКНО + 2:
        return None
    гл = []
    for i in range(len(полоса) - ОКНО + 1):
        окно = полоса[i:i + ОКНО]
        гл.append(tuple(sum(к[j] for к in окно) / ОКНО for j in range(3)))
    return max(max(abs(a - b) for a, b in zip(гл[i], гл[i + 1]))
               for i in range(len(гл) - 1))


def замечание_свечения(бр, подлог=None, ширины=(1920, 2560)):
    """№5: слой свечения во всю главную область, без вертикального обрыва."""
    from PIL import Image
    import io as _io
    худшее = {}
    for ширина in ширины:
        ctx, стр = _страница(бр, подлог, ширина)
        for путь, имя in ИНСТРУМЕНТЫ:
            стр.goto(ch.БАЗА + путь, wait_until="domcontentloaded")
            стр.wait_for_timeout(500)
            г = стр.evaluate(ГЕОМЕТРИЯ)
            if not г:
                continue
            им = Image.open(_io.BytesIO(стр.screenshot(animations="disabled"))).convert("RGB")
            # Строка берётся в ВЕРХНЕМ ПОЛЕ шапки: посередине идут заголовок
            # и кнопки, и каждый их пиксель отличается от фона — замер был бы
            # про текст, а не про свечение.
            y = max(0, min(им.height - 1, int(г["шапка"]["y"] + 6)))
            # И по ВСЕЙ главной области, а не по шапке: край, который ищем,
            # приходится ровно на границу колонки содержимого.
            x0 = max(0, int(г["main"]["x"]))
            x1 = min(им.width, int(г["main"]["x"] + г["main"]["w"]))
            полоса = [им.getpixel((x, y)) for x in range(x0, x1)]
            с = _сглаженный_скачок(полоса)
            if с is None:
                continue
            ключ = "%s@%d" % (имя, ширина)
            худшее[ключ] = round(с, 1)
        ctx.close()
    плохие = {к: в for к, в in худшее.items() if в > ПОРОГ_КРАЯ}
    шаг(5, "свечение-без-резкого-края", not плохие,
        "худший скачок %.1f при пороге %.1f%s"
        % (max(худшее.values()) if худшее else 0, ПОРОГ_КРАЯ,
           ("; выше порога: " + str(плохие)) if плохие else ""),
        собрано=len(худшее))
    return худшее



# ══════════════════════════════════════════════════════════════════════════
# БЛОК 2. ИСТОРИЯ ПИСЕМ И ДОСЬЕ
# ══════════════════════════════════════════════════════════════════════════

# Пороги те же, что до редизайна (`классОценки` в hh.html): 7 и выше —
# зелёный, 4–6 — янтарь, ниже 4 — красный. Здесь они записаны ВТОРОЙ раз
# намеренно: проба, берущая порог у проверяемого кода, подтвердит любое
# его значение — включая то, которое разъехалось с решением владельца.
ПОРОГИ_ОЦЕНКИ = [(9, "ok"), (8, "ok"), (7, "ok"), (6, "warn"),
                 (5, "warn"), (4, "warn"), (3, "danger"), (1, "danger")]


def замечания_истории(бр, подлог=None):
    """№6–7: цвет оценки в истории, тихие кнопки удаления."""
    ctx, стр = _страница(бр, подлог)
    стр.goto(ch.БАЗА + "/hh", wait_until="domcontentloaded")
    стр.wait_for_timeout(800)
    стр.click('.v2-tab[data-view="history"]')
    стр.wait_for_timeout(900)

    # ── №6. ОЦЕНКА СНОВА ОКРАШЕНА ПО ПОРОГАМ ─────────────────────────────
    # Правила `score-*` при редизайне уехали внутрь `.hh-score` — плитки
    # разбора, — и класс на оценке в истории стоял, не значив ничего.
    # Цвет спрашивается ПОДСТАНОВКОЙ ОЦЕНКИ в живую строку, а не чтением
    # правила из файла: правило может быть перебито соседом при равной
    # специфичности, и проверка 21 ловит ровно это.
    цвета = стр.evaluate(
        "(пороги) => {"
        " const з = document.querySelector('.history-item-score');"
        " if (!з) return null;"
        " const был = з.className;"
        " const цв = т => {"
        "   const d = document.createElement('div');"
        "   d.style.color = 'var(--v2-' + т + ')';"
        "   document.body.appendChild(d);"
        "   const c = getComputedStyle(d).color; d.remove(); return c; };"
        " const класс = о => о >= 7 ? 'score-high' : о >= 4 ? 'score-mid' : 'score-low';"
        " const итог = {};"
        " for (const [о, т] of пороги) {"
        "   з.className = 'history-item-score ' + класс(о);"
        "   итог[о] = {факт: getComputedStyle(з).color, ждём: цв(т)};"
        " }"
        " з.className = был;"
        " return итог;"
        "}", ПОРОГИ_ОЦЕНКИ)
    разошлись = ([] if not цвета else
                 [о for о, д in цвета.items() if д["факт"] != д["ждём"]])
    шаг(6, "оценка-окрашена-по-порогам", not разошлись,
        "проверено оценок %d%s" % (len(цвета or {}),
                                   ("; разошлись: " + str(разошлись)) if разошлись else ""),
        собрано=len(цвета or {}))

    # ── №7. КНОПКИ УДАЛЕНИЯ ТИХИЕ ────────────────────────────────────────
    # Спрашивается ПИКСЕЛЬ И ВЫЧИСЛЕННЫЙ СТИЛЬ: «красной обводки нет» —
    # это про рамку и заливку в ПОКОЕ, а «красная при наведении» — про
    # смену цвета, и по одному покою второе неотличимо от мёртвого
    # правила.
    покой = стр.evaluate(
        "() => {"
        " const к = document.querySelector('.history-item-del');"
        " if (!к) return null;"
        " const s = getComputedStyle(к);"
        " const d = document.createElement('div');"
        " d.style.color = 'var(--v2-danger)';"
        " document.body.appendChild(d);"
        " const красный = getComputedStyle(d).color; d.remove();"
        " const r = к.getBoundingClientRect();"
        " return {рамка: s.borderTopColor, фон: s.backgroundColor, цвет: s.color,"
        "         красный, w: Math.round(r.width), h: Math.round(r.height)};"
        "}")
    прозрачна = lambda ц: ц in ("rgba(0, 0, 0, 0)", "transparent")
    шаг(7, "удаление-в-покое-тихое",
        покой is not None and прозрачна(покой["рамка"])
        and прозрачна(покой["фон"]) and покой["цвет"] != покой["красный"],
        "рамка %s, фон %s, цвет %s" % (покой["рамка"], покой["фон"], покой["цвет"])
        if покой else "кнопки нет",
        собрано=1 if покой else 0)

    # Наведение — НАСТОЯЩИМ указателем: навязанный `:hover` объявляет
    # мёртвой исправную подсветку и наоборот (§6.0.3).
    стр.hover(".history-item-del")
    стр.wait_for_timeout(250)
    ховер = стр.evaluate(
        "() => {"
        " const к = document.querySelector('.history-item-del');"
        " const d = document.createElement('div');"
        " d.style.color = 'var(--v2-danger)';"
        " document.body.appendChild(d);"
        " const красный = getComputedStyle(d).color; d.remove();"
        " return {цвет: getComputedStyle(к).color, красный};"
        "}")
    шаг(7, "удаление-краснеет-при-наведении",
        ховер["цвет"] == ховер["красный"],
        "под курсором %s, красный %s" % (ховер["цвет"], ховер["красный"]))

    # Область нажатия не уменьшилась: снята рамка, а не размер.
    касание = стр.evaluate(
        "() => {"
        " const к = document.querySelector('.history-item-del');"
        " const r = к.getBoundingClientRect();"
        " return {w: Math.round(r.width), h: Math.round(r.height)};"
        "}")
    шаг(7, "область-нажатия-удаления-цела",
        касание["w"] >= 32 and касание["h"] >= 32,
        "%dx%d" % (касание["w"], касание["h"]))

    # Удаление работает как раньше — С ПОДТВЕРЖДЕНИЕМ и ДО БАЗЫ.
    было = стр.locator(".history-item").count()
    стр.click(".history-item-del")
    стр.wait_for_timeout(500)
    окно = стр.evaluate(
        "() => {"
        " const м = [...document.querySelectorAll('.modal-ov')]"
        "   .filter(e => e.checkVisibility({checkOpacity: true}));"
        " return м.length ? м[0].innerText.slice(0, 80) : '';"
        "}")
    шаг(7, "удаление-спрашивает-подтверждение", bool(окно.strip()),
        "в окне: %r" % окно.strip()[:50])
    if окно.strip():
        стр.evaluate(
            "() => {"
            " const м = [...document.querySelectorAll('.modal-ov')]"
            "   .filter(e => e.checkVisibility({checkOpacity: true}))[0];"
            " const к = [...м.querySelectorAll('button')]"
            "   .find(b => /удал/i.test(b.textContent));"
            " if (к) к.click();"
            "}")
        стр.wait_for_timeout(900)
        стало = стр.locator(".history-item").count()
        шаг(7, "удаление-убирает-письмо", стало == было - 1,
            "писем было %d, стало %d" % (было, стало), собрано=было)
    ctx.close()


_КРЕСТ_ПОЛЯ = r"""(к) => {
  const r = к.getBoundingClientRect();
  const о = 2;  // обводка фокуса: 2px вплотную (`outline-offset: 0`)
  const а = {l: r.left - о, t: r.top - о, r: r.right + о, b: r.bottom + о};
  const карт = к.closest('.dosie-item');
  const пер = [];
  for (const п of карт.querySelectorAll('input, textarea, select, label')) {
    if (!п.checkVisibility()) continue;
    const q = п.getBoundingClientRect();
    if (а.l < q.right && а.r > q.left && а.t < q.bottom && а.b > q.top)
      пер.push(п.tagName.toLowerCase() + '.' + (п.className || '').split(' ').pop());
  }
  const cx = (r.left + r.right) / 2, cy = (r.top + r.bottom) / 2;
  const своё = (x, y) => { const э = document.elementFromPoint(x, y);
    return !!э && (э === к || к.contains(э)); };
  const луч = (dx, dy) => { let d = 0; while (d < 40 && своё(cx + dx * (d + 1), cy + dy * (d + 1))) d++; return d; };
  return {пересечения: пер,
          область: [луч(-1, 0) + луч(1, 0) + 1, луч(0, -1) + луч(0, 1) + 1]};
}"""

КРАСНЫЙ_V2 = "rgb(239, 68, 68)"  # --v2-danger

_КРЕСТ_ВИД = r"""(к) => {
  const s = getComputedStyle(к);
  return {рамка_видна: parseFloat(s.borderTopWidth) > 0 && s.borderTopColor !== 'rgba(0, 0, 0, 0)'
                       && s.borderTopColor !== s.backgroundColor,
          рамка: s.borderTopColor, цвет: s.color,
          круг: s.borderTopLeftRadius};
}"""


def замечания_досье(бр, подлог=None):
    """№8: досье на всю ширину, системные подписи, правка сохраняется.
    №15: круг удаления строки не заходит на поля."""
    ctx, стр = _страница(бр, подлог)
    стр.goto(ch.БАЗА + "/hh", wait_until="domcontentloaded")
    стр.wait_for_timeout(800)
    стр.click('.v2-tab[data-view="dossier"]')
    стр.wait_for_timeout(800)

    вид = стр.evaluate(
        "() => {"
        " const в = document.getElementById('view-dossier');"
        " const ф = в.querySelector('.dosie-view-card') || в.firstElementChild;"
        " const л = document.querySelector('.dosie-label');"
        " const мон = document.createElement('div');"
        " мон.style.fontFamily = 'var(--v2-font-mono)';"
        " document.body.appendChild(мон);"
        " const моно = getComputedStyle(мон).fontFamily; мон.remove();"
        " const ш = e => Math.round(e.getBoundingClientRect().width);"
        " return {вкладка: ш(в), форма: ш(ф),"
        "         подпись: л ? getComputedStyle(л).fontFamily : null, моно,"
        "         рядов: document.querySelectorAll('.dosie-row').length,"
        "         колонки: document.querySelector('.dosie-row')"
        "                  ? getComputedStyle(document.querySelector('.dosie-row'))"
        "                    .gridTemplateColumns : null};"
        "}")
    шаг(8, "досье-во-всю-ширину-колонки",
        вид["форма"] >= вид["вкладка"] - 2,
        "форма %d из %d" % (вид["форма"], вид["вкладка"]))
    шаг(8, "подписи-досье-системные",
        вид["подпись"] != вид["моно"],
        "подпись %s, моно %s" % (вид["подпись"], вид["моно"]),
        собрано=1 if вид["подпись"] else 0)
    шаг(8, "короткие-поля-по-два-в-ряд",
        bool(вид["колонки"]) and len(вид["колонки"].split()) == 2,
        "колонки ряда: %s" % вид["колонки"], собрано=вид["рядов"])

    # ПРАВКА ДОХОДИТ ДО БАЗЫ, А НЕ ДО ЭКРАНА: поле меняется, сохраняется,
    # страница перезагружается, значение спрашивается заново.
    метка = "Проба " + str(id(стр))[-5:]
    поле = стр.locator("#d-profession")
    шаг(8, "поле-досье-на-месте", поле.count() > 0, собрано=поле.count())
    if поле.count():
        поле.fill(метка)
        стр.evaluate("window.__ЗАПРОСЫ = []")
        стр.click("#dosie-save-btn")
        стр.wait_for_timeout(1200)
        стр.reload(wait_until="domcontentloaded")
        стр.wait_for_timeout(900)
        стр.click('.v2-tab[data-view="dossier"]')
        стр.wait_for_timeout(700)
        стало = стр.eval_on_selector("#d-profession", "e => e.value")
        шаг(8, "правка-досье-пережила-перезагрузку", стало == метка,
            "в поле %r, ждали %r" % (стало[:40], метка))

    # РАЗДЕЛЫ 1–7 не тронуты правкой ширины и подписей: каждый
    # раскрывается, и поле в КАЖДОМ сохраняется. Спрашивается перезагрузкой,
    # а не тем, что экран не ругнулся.
    разделов = стр.locator(".ds").count()
    шаг(8, "разделов-досье-семь", разделов == 7, "разделов: %d" % разделов,
        собрано=разделов)
    # ПОЛЕ БЕРЁТСЯ ЛЮБОЕ ИМЕНОВАННОЕ, а не `input.v2-input`: в разделе
    # «Как я работаю» первым идёт `textarea`, в «Тоне писем» — `select`,
    # и первая версия пробы находила поле лишь в трёх разделах из семи,
    # печатая это НАХОДКОЙ. Ограничение было у пробы, а не у экрана.
    # Раздел, где именованных полей нет вовсе (проекты — динамический
    # список, поля там без `id`), это ПРОПУСК с причиной: спросить
    # перезагрузкой нечем, и выдать это за находку нельзя (§6.0.1).
    метки, без_имени = {}, []
    for i in range(разделов):
        раздел = стр.locator(".ds").nth(i)
        if раздел.locator(".ds-body.open").count() == 0:
            раздел.locator(".ds-toggle").click()
            стр.wait_for_timeout(250)
        поля = раздел.locator(".ds-body :is(input, textarea)[id]:visible")
        имя = раздел.locator(".ds-toggle span").inner_text().strip()[:22]
        if поля.count() == 0:
            без_имени.append(имя)
            continue
        орган = поля.first
        ид = орган.get_attribute("id")
        if орган.get_attribute("type") == "checkbox":
            орган.check()
            метки[i] = (ид, True, имя, "значение")
            continue
        м = "Проба%d%s" % (i, str(id(стр))[-4:])
        # ПОЛЕ ВВОДА ЧИПОВ ХРАНИМЫМ НЕ ЯВЛЯЕТСЯ: набранное уходит в чип
        # по Enter, а само поле очищается. Требовать от него переживания
        # перезагрузки — мерить не то; спрашивается ЧИП.
        чипы = раздел.locator(".tag-wrap")
        if чипы.count() and орган.get_attribute("class") == "tag-text-input":
            орган.fill(м)
            орган.press("Enter")
            стр.wait_for_timeout(200)
            метки[i] = (ид, м, имя, "чип")
            continue
        орган.fill(м)
        метки[i] = (ид, м, имя, "значение")
    шаг(8, "в-разделах-есть-именованное-поле",
        len(метки) + len(без_имени) == разделов and len(метки) >= 5,
        "полей нашлось в %d разделах из %d%s"
        % (len(метки), разделов,
           ("; только списки: " + str(без_имени)) if без_имени else ""),
        собрано=разделов)
    стр.click("#dosie-save-btn")
    стр.wait_for_timeout(1400)
    стр.reload(wait_until="domcontentloaded")
    стр.wait_for_timeout(900)
    стр.click('.v2-tab[data-view="dossier"]')
    стр.wait_for_timeout(700)
    не_сошлись = []
    for i, (ид, м, имя, как) in метки.items():
        if как == "чип":
            есть = стр.evaluate(
                "(м) => [...document.querySelectorAll('.tag-wrap .tag-chip,"
                " .tag-wrap .v2-chip')].some(э => э.textContent.includes(м))", м)
            if not есть:
                не_сошлись.append((имя, "чип не найден"))
            continue
        если = стр.eval_on_selector(
            "#" + ид, "e => e.type === 'checkbox' ? e.checked : e.value")
        if если != м:
            не_сошлись.append((имя, если))
    шаг(8, "правка-каждого-раздела-пережила-перезагрузку", not не_сошлись,
        "проверено разделов %d%s" % (len(метки),
                                     ("; разошлись: " + str(не_сошлись)) if не_сошлись else ""),
        собрано=len(метки))
    # ── №15. КРУГ УДАЛЕНИЯ СТРОКИ НЕ ЗАХОДИТ НА ПОЛЯ ─────────────────────
    # Замечание владельца (письмо 5): крестик строки досье стоял поверх
    # полей. Спрашивается ПРЯМОУГОЛЬНИК круга ВМЕСТЕ С ОБВОДКОЙ фокуса
    # против каждого поля своей карточки — в покое, при наведении и при
    # фокусе, — плюс область нажатия. Строки заводятся в странице и НЕ
    # сохраняются: база стенда не трогается.
    стр.evaluate("() => { addLanguage('Проба', 'B2'); addExperience({}); }")
    стр.wait_for_timeout(300)
    пересечений, замеров, мелких, не_красный = [], 0, [], []
    кресты = стр.locator(".dosie-item .dosie-item-del:visible")
    всего = кресты.count()
    for i in range(всего):
        кр = кресты.nth(i)
        # Раздел досье, где лежит строка, раскрывается: в свёрнутом круг
        # есть в дереве, но нажатие до него не доходит
        кр.evaluate("e => { const б = e.closest('.ds-body');"
                    " if (б && !б.classList.contains('open'))"
                    "   б.previousElementSibling.click(); }")
        стр.wait_for_timeout(350)
        кр.scroll_into_view_if_needed()
        for состояние in ("покой", "наведение", "фокус"):
            стр.mouse.move(1, 1)
            if состояние == "наведение":
                б = кр.bounding_box()
                стр.mouse.move(б["x"] + б["width"] / 2, б["y"] + б["height"] / 2)
            elif состояние == "фокус":
                кр.evaluate("e => e.classList.add('is-focus')")
            стр.wait_for_timeout(220)
            итог = кр.evaluate(_КРЕСТ_ПОЛЯ)
            if состояние != "покой":
                в = кр.evaluate(_КРЕСТ_ВИД)
                if not (в["рамка"] == КРАСНЫЙ_V2 and в["цвет"] == КРАСНЫЙ_V2):
                    не_красный.append((i, состояние, в["рамка"], в["цвет"]))
            кр.evaluate("e => e.classList.remove('is-focus')")
            замеров += 1
            if итог["пересечения"]:
                пересечений.append((i, состояние, итог["пересечения"][:2]))
            if состояние == "покой" and min(итог["область"]) < 44:
                мелких.append((i, итог["область"]))
    шаг(15, "круг-удаления-не-заходит-на-поля", not пересечений,
        "крестиков %d, замеров %d, пересечений %d%s" % (
            всего, замеров, len(пересечений),
            ("; " + str(пересечений[:2])) if пересечений else ""),
        собрано=всего)
    шаг(15, "круг-удаления-виден-в-покое-серым",
        всего > 0 and кресты.first.evaluate(_КРЕСТ_ВИД)["рамка_видна"],
        str(кресты.first.evaluate(_КРЕСТ_ВИД)) if всего else "крестиков нет",
        собрано=всего)
    шаг(15, "круг-удаления-красный-при-наведении-и-фокусе", not не_красный,
        "не красный: %s" % не_красный[:2] if не_красный
        else "красный во всех %d замерах" % (2 * всего), собрано=всего)
    шаг(15, "круг-удаления-область-нажатия-не-меньше-44", not мелких,
        "меньше 44: %s" % мелких if мелких else "у всех %d не меньше 44" % всего,
        собрано=всего)
    ctx.close()


# ══════════════════════════════════════════════════════════════════════════
# БЛОК 3. РЕЗЮМЕ
# ══════════════════════════════════════════════════════════════════════════

def замечания_резюме(бр, подлог=None):
    """№9–14: сохранение раздела, правка на месте, карточки мест,
    разбор места, колонтитул PDF, навыки и языки."""
    ctx, стр = _страница(бр, подлог)
    стр.goto(ch.БАЗА + "/hh", wait_until="domcontentloaded")
    стр.wait_for_timeout(800)
    стр.click('.v2-tab[data-view="resume"]')
    стр.wait_for_timeout(900)

    # ── №9. ЛОЖНАЯ ОШИБКА ПРИ СОХРАНЕНИИ РАЗДЕЛА ─────────────────────────
    # Правка сохранялась, а экран говорил «Не удалось сохранить раздел»:
    # `_резюме_разметка` звала `TemplateResponse` СТАРОЙ позиционной
    # формой, Starlette 1.1 читал словарь как имя шаблона и падал —
    # уже ПОСЛЕ `db.commit()`. Спрашивается И ответ сервера, И тост,
    # И база: «ответил 200» о том, что легло в базу, не говорит (§6.3).
    ответы = []
    стр.on("response", lambda r: ответы.append(r.status)
           if "/api/resume/section" in r.url else None)
    разделов = стр.locator(".hh-sec").count()
    шаг(9, "разделы-резюме-на-экране", разделов >= 5,
        "разделов: %d" % разделов, собрано=разделов)
    правимый = None
    for i in range(разделов):
        с = стр.locator(".hh-sec").nth(i)
        if с.locator(".hh-sec-edit").count() and с.locator(".hh-sec-input").count():
            правимый = с.get_attribute("data-sec")
            break
    if правимый is None:
        шаг(9, "есть-раздел-с-правкой", False, "ни одного", собрано=0)
        ctx.close()
        return

    метка = "Проба раздела %s." % str(id(стр))[-4:]
    карточка = '.hh-sec[data-sec="%s"]' % правимый
    нажалось = _нажать(стр, карточка + " .hh-sec-edit", 350)
    поле = стр.locator(карточка + " .hh-sec-input")
    поле.fill(поле.input_value() + "\n" + метка)
    _нажать(стр, карточка + " .hh-sec-save", 1500)
    тост = стр.evaluate(
        "() => [...document.querySelectorAll('.toast, #toast, .v2-toast')]"
        ".filter(e => e.checkVisibility()).map(e => e.textContent.trim()).join(' ')")
    шаг(9, "сохранение-раздела-отвечает-успехом",
        bool(ответы) and ответы[-1] == 200 and "Не удалось" not in тост,
        "ответ %s, тост %r" % (ответы[-1] if ответы else "нет", тост[:40]),
        собрано=len(ответы))
    стр.reload(wait_until="domcontentloaded")
    стр.wait_for_timeout(900)
    стр.click('.v2-tab[data-view="resume"]')
    стр.wait_for_timeout(700)
    в_базе = стр.evaluate(
        "(м) => document.getElementById('resume-body').innerText.includes(м)", метка)
    шаг(9, "правка-раздела-легла-в-базу", в_базе is True)

    # ── №10. ПРАВКА НА МЕСТЕ: КНОПКИ В ШАПКЕ ─────────────────────────────
    до = стр.evaluate(
        "(с) => {"
        " const к = document.querySelector(с);"
        " const и = к.querySelector('.hh-sec-edit');"
        " return {изменить: и.checkVisibility(),"
        "         отмена: к.querySelector('.hh-sec-cancel').checkVisibility(),"
        "         сохранить: к.querySelector('.hh-sec-save').checkVisibility(),"
        "         шапка: Math.round(и.getBoundingClientRect().top)};"
        "}", карточка)
    _нажать(стр, карточка + " .hh-sec-edit")
    после = стр.evaluate(
        "(с) => {"
        " const к = document.querySelector(с);"
        " const о = к.querySelector('.hh-sec-cancel');"
        " const х = к.querySelector('.hh-sec-save');"
        " return {изменить: к.querySelector('.hh-sec-edit').checkVisibility(),"
        "         отмена: о.checkVisibility(), сохранить: х.checkVisibility(),"
        "         верх_отмены: Math.round(о.getBoundingClientRect().top),"
        "         верх_сохранить: Math.round(х.getBoundingClientRect().top)};"
        "}", карточка)
    шаг(10, "кнопки-правки-встали-на-место-изменить",
        нажалось and до["изменить"] and not до["отмена"] and not до["сохранить"]
        and не_видно(после["изменить"]) and после["отмена"] and после["сохранить"]
        and abs(после["верх_отмены"] - до["шапка"]) <= 2
        and abs(после["верх_сохранить"] - до["шапка"]) <= 2,
        "шапка была y=%d, «Отмена» y=%d, «Сохранить» y=%d"
        % (до["шапка"], после["верх_отмены"], после["верх_сохранить"]))

    # ПОЛЕ ПРАВКИ БЕЗ СВОЕЙ ПРОКРУТКИ: высота следует за текстом.
    прокрутка = стр.evaluate(
        "(с) => {"
        " const п = document.querySelector(с + ' .hh-sec-input');"
        " return {лишнее: п.scrollHeight - п.clientHeight,"
        "         высота: Math.round(п.getBoundingClientRect().height)};"
        "}", карточка)
    шаг(10, "поле-правки-без-внутренней-прокрутки",
        прокрутка["лишнее"] <= 2,
        "невидимого текста %d px при высоте %d" % (прокрутка["лишнее"],
                                                   прокрутка["высота"]))

    # «ОТМЕНА» ВОЗВРАЩАЕТ ПРЕЖНИЙ ВИД И ПРЕЖНИЙ ТЕКСТ.
    было = стр.locator(карточка + " .hh-sec-input").input_value()
    стр.locator(карточка + " .hh-sec-input").fill(было + "\nЭто не должно сохраниться.")
    _нажать(стр, карточка + " .hh-sec-cancel", 500)
    отмена = стр.evaluate(
        "(с) => {"
        " const к = document.querySelector(с);"
        " return {изменить: к.querySelector('.hh-sec-edit').checkVisibility(),"
        "         поле: к.querySelector('.hh-sec-input').value,"
        "         вид: к.querySelector('.hh-sec-view').checkVisibility()};"
        "}", карточка)
    шаг(10, "отмена-возвращает-прежний-вид",
        отмена["изменить"] and отмена["вид"] and отмена["поле"] == было,
        "текст вернулся: %s" % (отмена["поле"] == было))

    # ПЛАВНОСТЬ РАСКРЫТИЯ спрашивается ПОКАДРОВО, а не по объявлению
    # в стилях: правило может быть написано и не применяться (§6.0.15,
    # «между двумя готовыми кадрами»). Сэмплер считает высоту короба
    # в каждом кадре, пока карточка раскрывается.
    ход = стр.evaluate(
        "async (с) => {"
        " const к = document.querySelector(с + ' .hh-sec-edit-box');"
        " const кадры = [];"
        " let идём = true;"
        " const тик = () => { if (!идём) return;"
        "   кадры.push(Math.round(к.getBoundingClientRect().height));"
        "   requestAnimationFrame(тик); };"
        " requestAnimationFrame(тик);"
        " document.querySelector(с + ' .hh-sec-edit').click();"
        " await new Promise(r => setTimeout(r, 700));"
        " идём = false;"
        " const разных = [...new Set(кадры)];"
        " return {кадров: кадры.length, ступеней: разных.length,"
        "         начало: кадры[0], конец: кадры[кадры.length - 1]};"
        "}", карточка)
    шаг(10, "раскрытие-плавное",
        ход["ступеней"] >= 5 and ход["конец"] > ход["начало"],
        "ступеней высоты %d за %d кадров, %d → %d px"
        % (ход["ступеней"], ход["кадров"], ход["начало"], ход["конец"]),
        собрано=ход["кадров"])
    _нажать(стр, карточка + " .hh-sec-cancel")

    # «УМЕНЬШИТЬ ДВИЖЕНИЕ» — БЕЗ АНИМАЦИИ. Спрашивается у БРАУЗЕРА
    # (эмуляция признака), а не у нашего правила: правило могло бы
    # стоять и не применяться.
    стр.emulate_media(reduced_motion="reduce")
    стр.wait_for_timeout(200)
    без_движения = стр.evaluate(
        "async (с) => {"
        " const к = document.querySelector(с + ' .hh-sec-edit-box');"
        " const кадры = [];"
        " let идём = true;"
        " const тик = () => { if (!идём) return;"
        "   кадры.push(Math.round(к.getBoundingClientRect().height));"
        "   requestAnimationFrame(тик); };"
        " requestAnimationFrame(тик);"
        " document.querySelector(с + ' .hh-sec-edit').click();"
        " await new Promise(r => setTimeout(r, 600));"
        " идём = false;"
        " return {ступеней: [...new Set(кадры)].length,"
        "         длительность: getComputedStyle(к).transitionDuration};"
        "}", карточка)
    шаг(10, "при-уменьшить-движение-без-анимации",
        без_движения["ступеней"] <= 2,
        "ступеней %d, длительность перехода %s"
        % (без_движения["ступеней"], без_движения["длительность"]))
    стр.emulate_media(reduced_motion="no-preference")
    _нажать(стр, карточка + " .hh-sec-cancel", 300)

    # ── №11. ОПЫТ РАБОТЫ ПРАВИТСЯ ПО КАРТОЧКАМ МЕСТ ──────────────────────
    мест = стр.locator(".hh-job").count()
    шаг(11, "места-работы-карточками", мест >= 2, "мест: %d" % мест, собрано=мест)
    кнопок = стр.locator(".hh-place-edit").count()
    шаг(11, "у-каждого-места-своё-изменить", кнопок == мест,
        "кнопок %d при %d местах" % (кнопок, мест), собрано=мест)
    if мест >= 2:
        весь_до = стр.evaluate(
            "() => document.getElementById('resume-body').innerText")
        метка2 = "Правка места %s." % str(id(стр))[-4:]
        _нажать(стр, ".hh-place-edit")
        поле2 = стр.locator(".hh-place-input").first
        поле2.fill(поле2.input_value().rstrip("\n") + "\n" + метка2 + "\n")
        _нажать(стр, ".hh-place-save", 1500)
        стр.reload(wait_until="domcontentloaded")
        стр.wait_for_timeout(900)
        стр.click('.v2-tab[data-view="resume"]')
        стр.wait_for_timeout(700)
        легло = стр.evaluate(
            "(м) => document.getElementById('resume-body').innerText.includes(м)", метка2)
        шаг(11, "правка-места-легла-в-базу", легло is True)
        # ОСТАЛЬНЫЕ МЕСТА НЕ ТРОНУТЫ: сверяем текст ВТОРОЙ карточки.
        второе_до = _текст_места(весь_до, 1)
        второе_после = _текст_места(
            стр.evaluate("() => document.getElementById('resume-body').innerText"), 1)
        шаг(11, "соседнее-место-не-тронуто", второе_до == второе_после,
            "длина %d → %d" % (len(второе_до), len(второе_после)),
            собрано=len(второе_до))

    # ── №12. РАЗБОР МЕСТА: ПЕРИОД, ГОРОД, ДОЛЖНОСТЬ ──────────────────────
    разбор = стр.evaluate(
        "() => [...document.querySelectorAll('.hh-job')].map(к => ({"
        " компания: (к.querySelector('.hh-job-name')||{}).textContent,"
        " период: (к.querySelector('.hh-job-period')||{}).textContent,"
        " должность: (к.querySelector('.hh-job-role')||{}).textContent,"
        " город: (к.querySelector('.hh-job-place')||{}).textContent || '',"
        " отрасль: (к.querySelector('.hh-job-branch')||{}).textContent || '',"
        "}))")
    полные = [м for м in разбор if " — " in (м["период"] or "")
              and "·" in (м["период"] or "")]
    шаг(12, "период-целиком-начало-конец-длительность",
        len(полные) == len(разбор) and разбор,
        "полных периодов %d из %d: %s"
        % (len(полные), len(разбор),
           [м["период"].strip()[:38] for м in разбор][:2]),
        собрано=len(разбор))
    # Должность НЕ должна совпадать с отраслью или городом того же места:
    # ровно так прежний разбор их и путал.
    путаница = [м["компания"] for м in разбор
                if м["должность"] and
                (м["должность"].strip() == м["отрасль"].strip()
                 or м["должность"].strip() in (м["город"] or "").strip())]
    шаг(12, "должность-не-подменена-городом-или-отраслью", not путаница,
        "спутано у: %s" % путаница if путаница else "спутанных нет",
        собрано=len(разбор))

    # ── №13. КОЛОНТИТУЛ PDF ──────────────────────────────────────────────
    # Спрашивается ВИДИМЫЙ текст, а не атрибут: дата, лежащая в `data-`,
    # человеку не видна вовсе — ровно так первая версия правки её
    # и «вывела».
    кол = стр.evaluate(
        "() => {"
        " const п = document.getElementById('resume-updated');"
        " return {видно: (document.getElementById('resume-body').innerText"
        "   .match(/Резюме обновлено/g) || []).length,"
        "  дата: п && п.checkVisibility() ? п.textContent.trim() : '',"
        "  мест_даты: [...document.querySelectorAll('#resume-updated')]"
        "   .filter(э => э.checkVisibility()).length};"
        "}")
    шаг(13, "колонтитул-pdf-не-показывается", кол["видно"] == 0,
        "строк «Резюме обновлено» на экране: %d" % кол["видно"])
    шаг(13, "дата-обновления-видна-один-раз",
        bool(кол["дата"]) and кол["мест_даты"] == 1,
        "на экране %r, мест %d" % (кол["дата"], кол["мест_даты"]))

    # ── №14. НАВЫКИ И ЯЗЫКИ ──────────────────────────────────────────────
    нав = стр.evaluate(
        "() => {"
        " const ч = [...document.querySelectorAll('.hh-skills .v2-chip')];"
        " const я = [...document.querySelectorAll('.hh-lang-row')];"
        " const выс = ч.map(э => Math.round(э.getBoundingClientRect().height));"
        " return {чипов: ч.length, классы: [...new Set(ч.map(э => э.className))],"
        "         высоты: [...new Set(выс)],"
        "         тексты: ч.map(э => э.textContent.trim()),"
        "         языков: я.length,"
        "         имена: я.map(э => (э.querySelector('dt')||{}).textContent"
        "                    ? э.querySelector('dt').textContent.trim() : ''),"
        "         языки: я.map(э => э.textContent.trim())};"
        "}")
    шаг(14, "навыки-одинаковыми-чипами",
        нав["чипов"] > 0 and len(нав["классы"]) == 1 and len(нав["высоты"]) == 1,
        "чипов %d, классов %d, высот %d" % (нав["чипов"], len(нав["классы"]),
                                            len(нав["высоты"])),
        собрано=нав["чипов"])
    шаг(14, "языки-отдельным-списком", нав["языков"] > 0,
        "пар «язык — уровень»: %d %s" % (нав["языков"], нав["языки"][:2]),
        собрано=нав["языков"])
    # Ни один язык не уехал в чипы навыков — ровно то, чем болел показ.
    # Имя языка берётся у `dt`, а не у строки целиком: `dt` и `dd` стоят
    # вплотную, и `textContent` строки даёт «РусскийРодной» — признак
    # не опознал бы НИ ОДИН язык в чипах (поймано контролем).
    # КАЖДЫЙ НАВЫК ИЗ ТЕКСТА — В ЧИПЕ (№352, письмо 5). Прежние строки
    # сверяли классы только у того, что УЖЕ чип, и были слепы к навыкам,
    # ушедшим простым текстом: hh.ru переносит список на несколько строк,
    # а разбор брал одну. Навыки считаются ПО СЫРОМУ ТЕКСТУ раздела
    # (поле правки), своим разбором пробы: строка с подписью «Навыки»
    # и её продолжения до пустой строки, делёж по набегам пробелов.
    сыр = стр.evaluate(_СЫРЫЕ_НАВЫКИ)
    из_текста = сыр["навыки"]
    не_в_чипе = [н for н in из_текста if н not in нав["тексты"]]
    шаг(14, "каждый-навык-из-текста-в-чипе",
        not не_в_чипе and len(из_текста) == нав["чипов"] and not сыр["текстом"],
        "в тексте %d, чипов %d, не в чипе %d, видно простым текстом %d"
        % (len(из_текста), нав["чипов"], len(не_в_чипе), len(сыр["текстом"])),
        собрано=len(из_текста))
    в_чипах = [имя for имя in нав["имена"] if имя and имя in нав["тексты"]]
    шаг(14, "язык-не-попал-в-чипы-навыков", not в_чипах,
        "в чипах оказались: %s" % в_чипах if в_чипах else "ни одного",
        собрано=нав["языков"])
    ctx.close()


_СЫРЫЕ_НАВЫКИ = r"""() => {
  const кар = document.querySelector('.hh-skills') && document.querySelector('.hh-skills').closest('.hh-sec');
  if (!кар) return {навыки: [], текстом: []};
  const тело = (кар.querySelector('.hh-sec-input') || {}).value || '';
  const дели = (с) => с.split(/\s{2,}|\t/).map(x => x.trim()).filter(Boolean);
  const навыки = [];
  let внутри = false;
  for (const с of тело.split('\n')) {
    const ст = с.trim();
    const м = ст.match(/^(Ключевые навыки|Навыки)(\s{2,}.*)$/);
    if (м) { внутри = true; навыки.push(...дели(м[2])); continue; }
    if (!внутри) continue;
    if (!ст || /^знание языков/i.test(ст)) { внутри = false; continue; }
    навыки.push(...дели(ст));
  }
  const вид = [...кар.querySelectorAll('.hh-sec-text')].filter(э => э.checkVisibility())
    .map(э => э.innerText).join('\n');
  const куски = вид.split('\n').flatMap(дели);
  const текстом = навыки.filter(н => куски.includes(н));
  return {навыки, текстом};
}"""


def не_видно(значение):
    """`checkVisibility()` у скрытой кнопки — False; читаем это словом."""
    return значение is False


def _текст_места(весь, номер):
    """Кусок текста экрана, принадлежащий карточке места с этим номером.

    Берётся по разметке, а не по содержимому: проба сравнивает СОСЕДНЕЕ
    место до и после правки первого, и делить надо ровно там же.
    """
    куски = весь.split("\n\n")
    return куски[номер] if номер < len(куски) else ""

# ══════════════════════════════════════════════════════════════════════════
# ПОДЛОГИ: каждый возвращает СВОЮ поломку и обязан уронить ИМЕННО свою
# строку. Общий подлог доказывал бы, что реестр видит хоть что-то, —
# и молчание про остальные замечания осталось бы непроверенным (§6.0.3).
# ══════════════════════════════════════════════════════════════════════════
ПОДЛОГИ = {
    # Ровно тот немой отказ, что нашёл владелец: подсветка ищет класс,
    # которого у кнопок нет.
    "подсветка-языка-мертва": """
      addEventListener('DOMContentLoaded', () => {
        const прежний = window.setLetterLang;
        window.setLetterLang = (lang, вручную) => {
          document.querySelectorAll('.letter-lang-seg .segmented-btn').forEach(b =>
            b.classList.toggle('active', b.dataset.lang === lang));
        };
      });""",
    # Вторая половина того же отказа: загрузка ссылки стирает выбор.
    "ссылка-стирает-язык": """
      addEventListener('DOMContentLoaded', () => {
        const п = window.fetchJobUrl || null;
        const прежний = window.fetch;
        window.fetch = async (u, o) => {
          const адрес = typeof u === 'string' ? u : u.url;
          if (адрес.includes('/api/fetch-url') && window.resetLetterLang)
            window.resetLetterLang();
          return прежний(u, o);
        };
      });""",
    # Прежний вид: круг и полоса разом.
    "два-индикатора": """
      addEventListener('DOMContentLoaded', () => {
        const б = document.getElementById('loading-state');
        if (!б) return;
        const к = document.createElement('div');
        к.className = 'spinner spinner-lg';
        б.prepend(к);
      });""",
    # Кнопка «Новое письмо» вернулась в ряд.
    "новое-письмо-вернулось": """
      addEventListener('DOMContentLoaded', () => {
        const р = document.getElementById('result-actions');
        if (!р) return;
        const b = document.createElement('button');
        b.className = 'v2-btn v2-btn-secondary';
        b.id = 'new-letter-btn';
        b.textContent = 'Новое письмо';
        b.style.marginLeft = 'auto';
        р.appendChild(b);
      });""",
    # Текст вакансии снова приглушён.
    "вакансия-другим-цветом": """
      addEventListener('DOMContentLoaded', () => {
        const s = document.createElement('style');
        s.textContent = '.hh-preview { color: var(--v2-text-2) !important; }';
        document.head.appendChild(s);
      });""",
    # Кнопка «Очистить» снова прячется после генерации.
    "очистить-прячется": """
      addEventListener('DOMContentLoaded', () => {
        const к = document.getElementById('clear-text-btn');
        new MutationObserver(() => {
          const письмо = document.getElementById('letter-content');
          if (письмо && письмо.textContent.trim() && !к.hidden) к.hidden = true;
        }).observe(document.body, {subtree: true, childList: true, attributes: true});
      });""",
    # Оценка в истории снова без единого цветового правила.
    "оценка-без-цвета": """
      addEventListener('DOMContentLoaded', () => {
        const s = document.createElement('style');
        s.textContent = '.history-item-score.score-high, .history-item-score.score-mid,'
          + ' .history-item-score.score-low { color: var(--v2-text-2) !important; }';
        document.head.appendChild(s);
      });""",
    # Кнопки удаления снова с красной обводкой в покое.
    "удаление-обведено": """
      addEventListener('DOMContentLoaded', () => {
        const s = document.createElement('style');
        s.textContent = '.history-item-del { border-color: var(--v2-danger) !important;'
          + ' color: var(--v2-danger) !important; }';
        document.head.appendChild(s);
      });""",
    # Досье снова у́же колонки.
    "досье-узкое": """
      addEventListener('DOMContentLoaded', () => {
        const s = document.createElement('style');
        s.textContent = '.dosie-view-card { max-width: 860px !important; }';
        document.head.appendChild(s);
      });""",
    # Разметка резюме снова рисуется старой позиционной формой
    # `TemplateResponse` — сервер отвечает 500 при сохранённой правке.
    "ложная-ошибка-сохранения": """
      addEventListener('DOMContentLoaded', () => {
        const исходный = window.fetch;
        window.fetch = async (u, o) => {
          const адрес = typeof u === 'string' ? u : u.url;
          if (адрес.includes('/api/resume/section')) {
            await исходный(u, o);            // правка всё равно сохраняется
            return new Response('{}', {status: 500,
              headers: {'Content-Type': 'application/json'}});
          }
          return исходный(u, o);
        };
      });""",
    # Кнопки правки снова внизу поля, а не в шапке карточки.
    "кнопки-правки-внизу": """
      addEventListener('DOMContentLoaded', () => {
        const s = document.createElement('style');
        s.textContent = '.hh-sec-cancel, .hh-sec-save { display: none !important; }';
        document.head.appendChild(s);
      });""",
    # Раскрытие снова мгновенное: короб прячется `hidden`.
    "раскрытие-мгновенное": """
      addEventListener('DOMContentLoaded', () => {
        const s = document.createElement('style');
        s.textContent = '.hh-sec-edit-box { transition: none !important; }';
        document.head.appendChild(s);
      });""",
    # Колонтитул PDF снова показывается между разделами.
    "колонтитул-виден": r"""
      addEventListener('DOMContentLoaded', () => {
        setTimeout(() => {
          const т = document.querySelector('.hh-sec-text');
          if (т) т.textContent = 'Пётр Иванов  •  Резюме обновлено 27 мая 2026\n' + т.textContent;
        }, 600);
      });""",
    # Язык снова уехал в чипы навыков.
    # Один навык выводится ТЕКСТОМ: чип убран, его имя строкой над чипами.
    # Резерв места под круг удаления снят: круг ложится на поля.
    "крестик-без-резерва": r"""
      addEventListener('DOMContentLoaded', () => {
        const s = document.createElement('style');
        s.textContent = '.dosie-item { padding-right: 12px !important; }';
        document.head.appendChild(s);
      });""",
    "навык-текстом": r"""
      addEventListener('DOMContentLoaded', () => {
        const ч = document.querySelectorAll('.hh-skills .v2-chip');
        const п = ч[ч.length - 1];
        if (!п) return;
        const pre = document.createElement('pre');
        pre.className = 'hh-sec-text';
        pre.textContent = п.textContent;
        п.closest('.hh-skills').before(pre);
        п.remove();
      });""",
    "язык-в-чипах": r"""
      addEventListener('DOMContentLoaded', () => {
        setTimeout(() => {
          const ч = document.querySelector('.hh-skills');
          const я = document.querySelector('.hh-lang-row dt');
          if (ч && я) {
            const э = document.createElement('span');
            э.className = 'v2-chip hh-skill';
            э.textContent = я.textContent.replace(/\s*—\s*$/, '');
            ч.appendChild(э);
          }
        }, 600);
      });""",
    # Слой свечения снова обрывается по колонке содержимого.
    "свечение-в-колонке": """
      addEventListener('DOMContentLoaded', () => {
        const s = document.createElement('style');
        s.textContent = '.v2-page-head::after, .v2-page-head::before'
          + ' { left: 0 !important; right: 0 !important; }';
        document.head.appendChild(s);
      });""",
}

# Какая строка реестра обязана упасть от какого подлога.
ЧЬЯ_СТРОКА = {
    "подсветка-языка-мертва":  "язык-английский-подсвечен",
    "ссылка-стирает-язык":     "ссылка-не-стирает-выбор-языка",
    "два-индикатора":          "индикатор-загрузки-один",
    "новое-письмо-вернулось":  "новое-письмо-убрано",
    "вакансия-другим-цветом":  "текст-вакансии-обычным-цветом",
    "очистить-прячется":       "очистить-доступна-после-генерации",
    "оценка-без-цвета":        "оценка-окрашена-по-порогам",
    "удаление-обведено":       "удаление-в-покое-тихое",
    "досье-узкое":             "досье-во-всю-ширину-колонки",
    "ложная-ошибка-сохранения": "сохранение-раздела-отвечает-успехом",
    "кнопки-правки-внизу":     "кнопки-правки-встали-на-место-изменить",
    "раскрытие-мгновенное":    "раскрытие-плавное",
    "колонтитул-виден":        "колонтитул-pdf-не-показывается",
    "язык-в-чипах":            "язык-не-попал-в-чипы-навыков",
    "навык-текстом":           "каждый-навык-из-текста-в-чипе",
    "крестик-без-резерва":     "круг-удаления-не-заходит-на-поля",
    "свечение-в-колонке":      "свечение-без-резкого-края",
}


def прогон(подлог=None, только=None):
    """Весь реестр одним заходом. `только` — номера замечаний через запятую."""
    global находок, пропусков, _строки
    находок = пропусков = 0
    _строки = []
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        # Браузер НЕВИДИМЫЙ: вопросы здесь про логику и про цвет пикселя
        # на снимке, а не про вёрстку с полосой прокрутки (§6.0.3).
        бр = p.chromium.launch(headless=True)
        try:
            if только is None or {1, 2, 3, 4} & только:
                замечания_письма(бр, подлог)
            if только is None or 5 in только:
                замечание_свечения(бр, подлог)
            if только is None or {6, 7} & только:
                замечания_истории(бр, подлог)
            if только is None or {8, 15} & только:
                снимок_досье = _досье_снять()
                try:
                    замечания_досье(бр, подлог)
                finally:
                    _досье_вернуть(снимок_досье)
            if только is None or {9, 10, 11, 12, 13, 14} & только:
                # Резюме возвращается ТЕМ ЖЕ, каким взято: правка —
                # часть проверки, а не след, который остаётся на стенде.
                снимок = _резюме_снять()
                try:
                    замечания_резюме(бр, подлог)
                finally:
                    _резюме_вернуть(снимок)
        finally:
            бр.close()
    return находок, пропусков


def main():
    только = None
    if "--только" in sys.argv:
        только = {int(н) for н in sys.argv[sys.argv.index("--только") + 1].split(",")}
    print("РЕЕСТР ЗАМЕЧАНИЙ ВЛАДЕЛЬЦА — HH-ассистент (письмо 4)")
    print("=" * 74)
    н, п = прогон(только=только)
    print("-" * 74)
    print("замечаний проверено: %d · плохих: %d · пропусков: %d"
          % (len(_строки), н, п))
    if п and not н:
        sys.exit(2)
    sys.exit(1 if н else 0)


def контроль():
    """Каждый подлог обязан уронить ИМЕННО свою строку, остальные — нет."""
    print("КОНТРОЛЬ РЕЕСТРА: по подлогу на замечание")
    print("=" * 74)
    print("\n— чистый прогон —")
    чисто_н, _ = прогон()
    чисто = {имя for _, имя, исход, _ in _строки if исход == "ПЛОХО"}
    if чисто_н:
        print("ГРЯЗНАЯ ОСНОВА: на чистом коде уже %d находок — контроль "
              "недействителен (§6.0.3)" % чисто_н)
        sys.exit(2)
    беда = 0
    for имя, скрипт in ПОДЛОГИ.items():
        print("\n— подлог: %s —" % имя)
        прогон(подлог=скрипт)
        упали = {и for _, и, исход, _ in _строки if исход == "ПЛОХО"}
        своя = ЧЬЯ_СТРОКА[имя]
        if своя in упали:
            лишние = упали - {своя}
            print("   НАЙДЕН: упала своя строка «%s»%s" %
                  (своя, ("; заодно " + str(sorted(лишние))) if лишние else ""))
        else:
            print("   НЕ НАЙДЕН: строка «%s» осталась зелёной — проба слепа "
                  "либо подлог не состоялся" % своя)
            беда += 1
    print("\n" + "=" * 74)
    print("подлогов: %d · не найдено: %d" % (len(ПОДЛОГИ), беда))
    sys.exit(1 if беда else 0)


if __name__ == "__main__":
    if "--контроль" in sys.argv:
        контроль()
    main()
