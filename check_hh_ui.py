"""HH-АССИСТЕНТ НАСКВОЗЬ (BACKLOG №352, письмо 3, блок 2).

ПРОВЕРКА, код 1 при находке, 2 — замерить нечем (стенда нет).

ЧТО СПРАШИВАЕТСЯ — путь, которым идёт человек, от первого нажатия
до НАБЛЮДАЕМОГО результата (§6.3):
  1. ОДНО ПОЛЕ. Вставили текст — он уходит в модель; вставили ссылку —
     сама идёт та же загрузка, что раньше шла по кнопке «Загрузить»,
     и статус виден ПОД полем. Отказ загрузки тоже виден.
  2. ПИСЬМО. Сверка с резюме, генерация, копирование, правка,
     перегенерация, «Новое письмо» — всё работает, как до правки.
  3. ИСТОРИЯ. Раскрыть, скопировать, удалить с подтверждением.
  4. ДОСЬЕ. Изменить поле, сохранить, перезагрузить — значение на месте.
  5. ТОЧКИ ЗАПОЛНЕННОСТИ у вкладок «Досье» и «Резюме»: зелёная, когда
     заполнено, и у неё есть имя (`title`), а не только цвет.

ВЫЗОВОВ МОДЕЛИ НОЛЬ. `/api/generate-letter` и `/api/analyze-vacancy`
подменяются в СТРАНИЦЕ (`page.route`): путь кода в браузере при этом
тот же самый, а деньги и разброс живого ответа к вопросу «работает ли
экран» отношения не имеют. Резюме и письма в пробе ВЫДУМАННЫЕ —
настоящие в отчёт и в репозиторий не попадают (§5.1).

ОРГАН СЧИТАЕТСЯ ЖИВЫМ, только если до него дотягивается нажатие
(`elementFromPoint`), а не если он есть в дереве.

КЛЮЧИ:
  --контроль   четыре подлога В СТРАНИЦУ, кода не трогают:
                 ссылка-не-грузится   — вставка ссылки не запускает загрузку;
                 письмо-без-меток     — метки письма не собираются;
                 точка-всегда-серая   — точка заполненности не зеленеет;
                 сверка-таблетками    — пункты сверки не переносятся.
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

находок = 0
пропусков = 0

# ВЫДУМАННАЯ вакансия и выдуманное письмо: настоящих данных владельца
# в пробе нет ни строки.
ВАКАНСИЯ = (
    "Требуется инженер по машинному зрению. Обязанности: сборка конвейера "
    "разметки, дообучение моделей детекции, выкладка сервиса. Требования: "
    "Python, PyTorch, опыт эксплуатации моделей в проде."
)
ССЫЛКА = "https://example.test/vacancy/1"
ЗАГРУЖЕННЫЙ_ТЕКСТ = (
    "Оператор складской техники. Обязанности: приём и отгрузка товара. "
    "Требования: внимательность, готовность к сменному графику."
)
ПИСЬМО = (
    "Здравствуйте! Увидел вашу вакансию и хочу предложить свою кандидатуру. "
    "Собирал конвейеры разметки и выводил модели детекции в продакшн."
)
ОТВЕТ_АНАЛИЗА = {
    "relevance_score": 8,
    "relevance_reason": "Опыт совпадает с требованиями по ключевым пунктам.",
    "key_matches": [
        "опыт промышленной эксплуатации моделей детекции",
        "Python и PyTorch",
    ],
    "missing_skills": ["формальный опыт работы с конвейерами разметки в командах от десяти человек"],
    "job_title": "Инженер по машинному зрению",
    "company_name": "ООО Пример",
}


def шаг(имя, условие, подробность="", собрано=None, отрицание=None):
    """`собрано` — сколько собрано для замера; ноль — ПРОПУСК (проверка 33).

    `отрицание` — причина, по которой пустой сбор ЗАКОНЕН (проверка 33).
    """
    global находок, пропусков
    if собрано is not None and not собрано:
        пропусков += 1
        print("  %-7s %s — сбор пуст, мерить нечего" % ("ПРОПУСК", имя))
        return
    if not условие:
        находок += 1
    print("  %-4s %s%s" % ("OK" if условие else "ПЛОХО", имя,
                           (" — " + подробность) if подробность else ""))


ЖИВОЙ = """(с) => {
  const э = document.querySelector(с);
  if (!э) return {есть: false};
  const r = э.getBoundingClientRect();
  if (!r.width || !r.height) return {есть: true, видно: false};
  const т = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
  return {есть: true, видно: true,
          дотянулись: !!т && (т === э || э.contains(т) || т.contains(э))};
}"""


def живой(стр, селектор):
    стр.locator(селектор).first.scroll_into_view_if_needed(timeout=3000)
    return стр.evaluate(ЖИВОЙ, селектор)


def подделать(стр, ушло, перехвачено, подлог=None):
    """Ответы модели и загрузки страницы — поддельные. Живых вызовов 0."""
    def вакансия(route):
        перехвачено.append(route.request.url)
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps({"text": ЗАГРУЖЕННЫЙ_ТЕКСТ, "source": "hh"},
                                      ensure_ascii=False))

    def анализ(route):
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps(ОТВЕТ_АНАЛИЗА, ensure_ascii=False))

    def письмо(route):
        тело = {"letter": ПИСЬМО, "analysis": ОТВЕТ_АНАЛИЗА, "letter_id": 424242}
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps(тело, ensure_ascii=False))

    # Сохранение правки: письмо поддельное, и в базе стенда его нет —
    # настоящий PATCH честно отвечал бы 404 на выдуманный `letter_id`,
    # то есть проба сама заводила бы находку «ошибка в консоли». Тело
    # запроса ЗАПОМИНАЕТСЯ: «правка сохранена» проверяется тем, что ушло
    # на сервер, а не тем, что экран не ругнулся.
    def правка(route):
        try:
            ушло.append(route.request.post_data or "")
        except Exception:
            ушло.append("")
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps({"ok": True}))

    # ПРАВКА РАЗДЕЛА РЕЗЮМЕ идёт на поддельный ответ, и это решение:
    # настоящий эндпоинт ПИШЕТ в базу стенда, а проба стоит в ряду
    # §6.0.2 — ряд обязан быть безопасным для любого прогона. Что именно
    # ложится в базу, спрашивает `tests/test_resume_sections.py`
    # на голых функциях; здесь спрашивается браузерная половина —
    # уходит ли правка на сервер и подставляется ли ответ.
    def раздел(route):
        try:
            ушло.append(route.request.post_data or "")
        except Exception:
            ушло.append("")
        тело = route.request.post_data_json or {}
        # Сервер отдаёт РАЗМЕТКУ: подделываем её тем же образом, чтобы
        # проверить подстановку, а не выдумываем свой формат ответа
        разметка = ('<span class="hh-chars-src" data-знаков="424242" hidden></span>'
                    '<div class="hh-resume-cols" id="resume-sections">'
                    '<div class="hh-resume-left"><section class="v2-card hh-sec"'
                    ' data-sec="0"><div class="hh-sec-head">'
                    '<h3 class="v2-card-title hh-sec-title">Опыт работы</h3>'
                    '<button class="v2-btn v2-btn-secondary hh-sec-edit" type="button"'
                    ' onclick="правитьРаздел(0)">Изменить</button></div>'
                    '<div class="hh-sec-view"><pre class="hh-sec-text">%s</pre></div>'
                    '<div class="hh-sec-edit-box" hidden>'
                    '<textarea class="v2-input v2-textarea hh-sec-input"></textarea>'
                    '</div></section></div><div class="hh-resume-right"></div></div>'
                    ) % (тело.get("text", "") or "")
        route.fulfill(status=200, content_type="text/html; charset=utf-8",
                      body=разметка)

    стр.route("**/api/resume/section", раздел)
    if подлог != "ссылка-не-грузится":
        стр.route("**/api/fetch-url", вакансия)
    стр.route("**/api/analyze-vacancy", анализ)
    стр.route("**/api/generate-letter", письмо)
    стр.route("**/api/cover-letters/424242", правка)


ПОДЛОГИ_В_СТРАНИЦУ = {
    "письмо-без-меток":
        "addEventListener('DOMContentLoaded', () => {"
        " window.показатьМеткиПисьма = () => {}; });",
    "точка-всегда-серая":
        "addEventListener('DOMContentLoaded', () => {"
        " window.поставитьТочку = (id) => {"
        "   const т = document.getElementById(id);"
        "   if (т) т.className = 'hh-dot'; }; });",
    # Правка раздела — единственное место вкладки, где можно потерять
    # НАБРАННОЕ: «Отмена», не вернувшая исходный текст, оставляет в поле
    # черновик, и следующее «Сохранить» кладёт его в резюме молча.
    "отмена-не-возвращает":
        "addEventListener('DOMContentLoaded', () => {"
        " window.отменитьРаздел = (i) => {"
        "   const к = document.querySelector('.hh-sec[data-sec=\"' + i + '\"]');"
        "   к.querySelector('.hh-sec-edit-box').hidden = true;"
        "   к.querySelector('.hh-sec-view').hidden = false;"
        "   к.querySelector('.hh-sec-edit').hidden = false; }; });",
    # Разметку после правки собирает сервер; собери её скрипт — на экране
    # осталась бы прежняя разбивка при изменившемся тексте
    "разметку-собирает-скрипт":
        "addEventListener('DOMContentLoaded', () => {"
        " const было = window.fetch;"
        " window.fetch = (u, o) => (String(u).includes('/api/resume/section')"
        "   ? было(u, o).then(r => ({ ok: r.ok, status: r.status,"
        "       text: () => Promise.resolve('<div>собрано скриптом</div>'),"
        "       json: () => r.json() }))"
        "   : было(u, o)); });",
    "сверка-таблетками":
        "addEventListener('DOMContentLoaded', () => {"
        " const s = document.createElement('style');"
        " s.textContent = '.hh-points li { white-space: nowrap;"
        " overflow: hidden; text-overflow: ellipsis; }';"
        " document.head.appendChild(s); });",
}


def доказать(стр, подлог, перехвачено=0):
    """Независимый замер того, что подлог ИЗМЕНИЛ (§6.0.3).

    Замер берётся НЕ из вердикта шагов: «находок стало больше» — это тот же
    вердикт, напечатанный дважды. Спрашивается ровно то звено, в которое
    метил подлог, и спрашивается так, чтобы ответ не зависел от того,
    какая вкладка открыта в конце прохода.
    """
    if подлог == "ссылка-не-грузится":
        return {"перехваченных запросов загрузки": перехвачено}
    if подлог == "письмо-без-меток":
        return {"длина показатьМеткиПисьма": стр.evaluate(
            "() => (window.показатьМеткиПисьма || '').toString().length")}
    if подлог == "точка-всегда-серая":
        return {"поставитьТочку знает про is-on": стр.evaluate(
            "() => (window.поставитьТочку || '').toString().includes('is-on')")}
    if подлог == "сверка-таблетками":
        # ВРЕМЕННЫЙ пункт: к концу прохода вкладка письма уже закрыта,
        # и замер по живому пункту отвечал бы `null` — то есть молчал бы
        # и при сработавшем подлоге, и при не сработавшем.
        return {"white-space у пункта": стр.evaluate("""() => {
            const ul = document.createElement('ul');
            ul.className = 'hh-points';
            const li = document.createElement('li');
            li.textContent = 'проба';
            ul.appendChild(li);
            document.body.appendChild(ul);
            const v = getComputedStyle(li).whiteSpace;
            ul.remove();
            return v;
        }""")}
    if подлог == "отмена-не-возвращает":
        # ВРЕМЕННАЯ карточка, а не живая: к концу прохода тело вкладки уже
        # подменено ответом сервера, и живой `data-sec="2"` там нет —
        # замер отвечал бы «карточки нет» и при сработавшем подлоге,
        # и при не сработавшем (§6.0.3).
        return {"поле после Отмены": стр.evaluate("""() => {
            const к = document.createElement('section');
            к.className = 'v2-card hh-sec';
            к.dataset.sec = '777';
            к.innerHTML = '<div class="hh-sec-head">'
              + '<button class="hh-sec-edit"></button></div>'
              + '<div class="hh-sec-view"></div>'
              + '<div class="hh-sec-edit-box" hidden>'
              + '<textarea class="hh-sec-input">ИСХОДНОЕ</textarea></div>';
            document.body.appendChild(к);
            const п = к.querySelector('.hh-sec-input');
            правитьРаздел(777);
            п.value = 'ЧЕРНОВИК';
            отменитьРаздел(777);
            const итог = п.value === 'ИСХОДНОЕ' ? 'вернулось' : 'остался черновик';
            к.remove();
            return итог;
        }""")}
    if подлог == "разметку-собирает-скрипт":
        return {"что подставлено": стр.evaluate(
            "() => (document.getElementById('resume-body') || {}).textContent"
            "        ? document.getElementById('resume-body').textContent.slice(0, 40)"
            "        : 'тела нет'")}
    return {}


def проход(подлог=None):
    from playwright.sync_api import sync_playwright
    global находок
    ошибки = []
    with sync_playwright() as p:
        бр = p.chromium.launch()
        к = бр.new_context(viewport={"width": 1600, "height": 1100})
        if подлог in ПОДЛОГИ_В_СТРАНИЦУ:
            к.add_init_script(ПОДЛОГИ_В_СТРАНИЦУ[подлог])
        стр = к.new_page()
        стр.on("console", lambda m: ошибки.append(m.text) if m.type == "error" else None)
        стр.on("pageerror", lambda e: ошибки.append(str(e)))
        # Отказы сети собираются С АДРЕСОМ: «404 в консоли» без адреса
        # не говорит, что именно не приехало, и чинить его не по чему.
        плохие = []
        стр.on("response", lambda r: плохие.append("%d %s" % (r.status, r.url))
               if r.status >= 400 else None)
        ушло, перехвачено = [], []
        подделать(стр, ушло, перехвачено, подлог)
        ch._войти(стр)
        стр.goto(ch.БАЗА + "/hh", wait_until="domcontentloaded")
        стр.wait_for_timeout(400)

        print("\n1. ОДНО ПОЛЕ: ТЕКСТ И ССЫЛКА")
        шаг("поле-вакансии-живое", живой(стр, "#job-input").get("дотянулись"))
        шаг("переключателя-текст-ссылка-НЕТ",
            стр.locator("#tab-url, #url-input, #fetch-btn").count() == 0,
            "органов прежнего переключателя: %d"
            % стр.locator("#tab-url, #url-input, #fetch-btn").count())

        стр.fill("#job-input", ВАКАНСИЯ)
        стр.wait_for_timeout(300)
        счётчик = стр.inner_text("#char-count")
        шаг("счётчик-символов-считает",
            счётчик.replace(" ", " ").replace(" ", "") == str(len(ВАКАНСИЯ)),
            "на экране %s, в тексте %d" % (счётчик, len(ВАКАНСИЯ)))

        # ССЫЛКА: вставляем и ждём, что загрузка пойдёт САМА
        стр.fill("#job-input", ССЫЛКА)
        стр.wait_for_timeout(1400)
        статус = стр.inner_text("#fetch-status").strip()
        шаг("ссылка-грузится-сама", "Загружено" in статус,
            "статус под полем: %r" % (статус[:60] or "пусто"))
        превью = стр.evaluate(
            "() => { const p = document.getElementById('fetched-preview');"
            " return {видно: p.classList.contains('visible'), длина: p.textContent.length}; }")
        шаг("загруженное-описание-видно",
            превью["видно"] and превью["длина"] > 50, str(превью))

        # ОТКАЗ ЗАГРУЗКИ тоже виден
        стр.unroute("**/api/fetch-url")
        стр.route("**/api/fetch-url", lambda r: r.fulfill(
            status=200, content_type="application/json",
            body=json.dumps({"error": "hh не отдал страницу"}, ensure_ascii=False)))
        стр.fill("#job-input", ССЫЛКА + "?2")
        стр.wait_for_timeout(1400)
        отказ = стр.inner_text("#fetch-status").strip()
        шаг("отказ-загрузки-виден", "не отдал" in отказ, "на экране: %r" % отказ[:60])

        print("\n2. ПИСЬМО")
        стр.fill("#job-input", ВАКАНСИЯ)
        стр.wait_for_timeout(300)
        стр.click("#analyze-btn")
        стр.wait_for_timeout(600)
        сверка = стр.evaluate("""() => {
          const к = document.getElementById('analysis-card');
          const п = [...document.querySelectorAll('#analysis-matches li')];
          const пропуски = [...document.querySelectorAll('#analysis-missing li')];
          const плитка = document.getElementById('analysis-score-tile');
          const самый = п.concat(пропуски).map(li => {
            const cs = getComputedStyle(li);
            return {строк: Math.round(li.getBoundingClientRect().height /
                                      parseFloat(cs.lineHeight)),
                    режется: cs.textOverflow === 'ellipsis' && cs.whiteSpace === 'nowrap'};
          });
          return {видно: к.classList.contains('visible'),
                  оценка: document.getElementById('analysis-score-badge').textContent,
                  класс: плитка ? плитка.className : '',
                  совпадений: п.length, нехваток: пропуски.length,
                  режется: самый.some(x => x.режется),
                  многострочных: самый.filter(x => x.строк > 1).length};
        }""")
        шаг("сверка-показана", сверка["видно"], str(сверка)[:120])
        шаг("оценка-плиткой-и-в-цвете",
            сверка["оценка"] == "8/10" and "score-high" in сверка["класс"],
            "оценка %s, класс %s" % (сверка["оценка"], сверка["класс"]))
        шаг("пункты-сверки-переносятся",
            not сверка["режется"] and сверка["многострочных"] >= 1,
            "режется %s, многострочных %d из %d"
            % (сверка["режется"], сверка["многострочных"],
               сверка["совпадений"] + сверка["нехваток"]),
            собрано=сверка["совпадений"] + сверка["нехваток"])

        стр.click("#generate-btn")
        стр.wait_for_selector("#letter-content", state="visible", timeout=8000)
        стр.wait_for_timeout(400)
        письмо = стр.inner_text("#letter-content")
        шаг("письмо-показано", ПИСЬМО[:30] in письмо, письмо[:40])
        метки = стр.evaluate(
            "() => { const м = document.getElementById('letter-meta');"
            " return {видно: !м.hidden, текст: м.innerText.replace(/\\n/g, ' | ')}; }")
        шаг("метки-письма-из-данных",
            метки["видно"] and "Инженер" in метки["текст"] and "символов" in метки["текст"],
            метки["текст"][:90])

        действия = стр.evaluate("""() => {
          const р = document.getElementById('result-actions');
          const к = [...р.querySelectorAll('button')];
          const главных = к.filter(b => b.classList.contains('v2-btn-primary'));
          return {видно: !р.hidden, кнопок: к.length,
                  главных: главных.map(b => b.textContent.trim()),
                  новое_убрано: !document.getElementById('new-letter-btn')};
        }""")
        # Кнопок ТРИ: «Новое письмо» убрана решением владельца 2026-09-20 —
        # новое письмо это новая вакансия в поле, а под полем уже стоит
        # «Очистить». Что зазоры между тремя равны, спрашивает реестр
        # замечаний (`check_hh_owner.py`, №3).
        шаг("действия-письма-внизу-и-живые",
            действия["видно"] and действия["кнопок"] == 3, str(действия))
        шаг("копировать-главная-новое-убрано",
            действия["главных"] == ["Копировать"] and действия["новое_убрано"],
            str(действия))
        шаг("кнопка-копировать-живая", живой(стр, "#copy-btn").get("дотянулись"))

        # правка письма
        стр.click("#edit-btn")
        стр.wait_for_timeout(200)
        правится = стр.evaluate(
            "() => document.getElementById('letter-content').contentEditable")
        стр.evaluate("() => { const л = document.getElementById('letter-content');"
                     " л.innerText = л.innerText + ' Добавлено правкой.'; }")
        стр.click("#edit-btn")
        стр.wait_for_timeout(400)
        после = стр.inner_text("#letter-content")
        шаг("правка-письма-работает",
            правится == "true" and "Добавлено правкой." in после,
            "contentEditable=%s" % правится)
        шаг("правка-уходит-на-сервер",
            any("Добавлено правкой." in (тело or "") for тело in ушло),
            "запросов сохранения: %d" % len(ушло), собрано=len(ушло))
        метки2 = стр.inner_text("#letter-meta")
        шаг("метки-пересчитаны-после-правки",
            "Инженер" in метки2 and "символов" in метки2, метки2.replace("\n", " | ")[:80])

        стр.click("#generate-btn")
        стр.wait_for_selector("#letter-content", state="visible", timeout=8000)
        стр.wait_for_timeout(300)
        шаг("перегенерация-работает",
            "Добавлено правкой." not in стр.inner_text("#letter-content"))

        # Путь «начать заново» остался ОДИН — «Очистить» под полем вакансии,
        # и он проверяется тем же, чем проверялась убранная кнопка:
        # наблюдаемым состоянием экрана, а не тем, что нажатие прошло.
        стр.click("#clear-text-btn")
        стр.wait_for_timeout(300)
        чисто = стр.evaluate("""() => ({
          поле: document.getElementById('job-input').value,
          превью: document.getElementById('fetched-preview').classList.contains('visible'),
        })""")
        шаг("очистить-чистит-поле-и-превью",
            not чисто["поле"] and not чисто["превью"], str(чисто))

        print("\n3. ИСТОРИЯ ПИСЕМ")
        стр.click('.v2-tab[data-view="history"]')
        стр.wait_for_timeout(900)
        строк = стр.locator(".history-item").count()
        шаг("список-писем-есть", строк > 0, "строк: %d" % строк, собрано=строк)
        счёт = стр.inner_text("#history-count-badge").strip()
        шаг("счётчик-писем-рядом-с-заголовком", bool(счёт), "на экране: %r" % счёт)
        if строк:
            стр.locator(".history-item-head").first.click()
            стр.wait_for_timeout(500)
            раскрыто = стр.evaluate(
                "() => { const т = document.querySelector('.history-item-body');"
                " return {открыт: т.classList.contains('open'),"
                "         высота: Math.round(т.getBoundingClientRect().height)}; }")
            шаг("письмо-раскрывается",
                раскрыто["открыт"] and раскрыто["высота"] > 40, str(раскрыто))
            шаг("кнопка-копировать-в-раскрытом-живая",
                живой(стр, ".history-copy-btn").get("дотянулись"))

            было = стр.locator(".history-item").count()
            стр.locator(".history-item-del").first.click()
            стр.wait_for_timeout(500)
            окно = стр.evaluate(
                "() => { const м = [...document.querySelectorAll('.modal-ov')]"
                ".find(m => m.classList.contains('open'));"
                " return m => 0, м ? м.innerText.slice(0, 120) : null; }")
            шаг("удаление-спрашивает", bool(окно), "окно: %r" % (окно or "нет"))
            # отказ от удаления: письмо остаётся
            стр.keyboard.press("Escape")
            стр.wait_for_timeout(400)
            шаг("отказ-от-удаления-оставляет-письмо",
                стр.locator(".history-item").count() == было,
                "было %d, стало %d" % (было, стр.locator(".history-item").count()))

        print("\n4. ДОСЬЕ")
        стр.click('.v2-tab[data-view="dossier"]')
        стр.wait_for_timeout(500)
        шаг("поле-досье-живое", живой(стр, "#d-profession").get("дотянулись"))
        метка = "Проба %d" % os.getpid()
        стр.fill("#d-profession", метка)
        стр.click("#dosie-save-btn")
        стр.wait_for_timeout(900)
        стр.reload(wait_until="domcontentloaded")
        стр.wait_for_timeout(700)
        стр.click('.v2-tab[data-view="dossier"]')
        стр.wait_for_timeout(500)
        шаг("досье-сохранилось",
            стр.input_value("#d-profession") == метка,
            "в поле после перезагрузки: %r" % стр.input_value("#d-profession"))

        print("\n5. ТОЧКИ ЗАПОЛНЕННОСТИ")
        точки = стр.evaluate("""() => ['dosie-badge', 'resume-badge'].map(id => {
          const т = document.getElementById(id);
          if (!т) return {id, есть: false};
          const cs = getComputedStyle(т);
          return {id, есть: true, зелёная: т.classList.contains('is-on'),
                  имя: т.title, размер: Math.round(parseFloat(cs.width))};
        })""")
        шаг("точки-на-месте-и-названы",
            all(т["есть"] and т["имя"] for т in точки),
            "; ".join("%s: %s %r" % (т["id"], т.get("зелёная"), т.get("имя"))
                      for т in точки),
            собрано=len(точки))
        шаг("точка-зелёная-когда-заполнено",
            all(т.get("зелёная") for т in точки),
            "; ".join("%s=%s" % (т["id"], т.get("зелёная")) for т in точки),
            собрано=len(точки))

        print("\n6. РЕЗЮМЕ ПО РАЗДЕЛАМ")
        стр.click('.v2-tab[data-view="resume"]')
        стр.wait_for_timeout(500)
        # Разделы обязаны быть В ПЕРВОМ КАДРЕ: собери их скрипт, человек
        # увидел бы сплошной текст и его перестройку на глазах (§6.0.15)
        # Спрашивается СЫРОЙ ОТВЕТ СЕРВЕРА, а не дерево: в дереве разделы
        # лежат и тогда, когда их собрал скрипт, — то есть вопрос «кто
        # нарисовал» по нему не задать вовсе (§6.0.15).
        сырой = стр.request.get(ch.БАЗА + "/hh").text()
        первый = сырой.count("hh-sec-head")
        шаг("разделы-нарисовал-сервер", первый > 0,
            "карточек разделов в разметке: %d" % первый,
            отрицание="разделов нет — текст резюме не разобрался")
        слева = стр.locator(".hh-resume-left .hh-sec").count()
        справа = стр.locator(".hh-resume-right .hh-sec").count()
        шаг("опыт-слева-остальное-справа", слева >= 1 and справа >= 1,
            "слева %d, справа %d" % (слева, справа))
        мест = стр.locator(".hh-job").count()
        шаг("места-работы-карточками", мест >= 2, "карточек мест: %d" % мест,
            отрицание="мест нет — признак не сошёлся, раздел показан текстом")
        шаг("кнопка-изменить-живая",
            живой(стр, '.hh-sec[data-sec="2"] .hh-sec-edit').get("дотянулись"))

        # ПРАВКА: поле открывается, «Отмена» возвращает исходный текст
        было = стр.evaluate(
            "() => document.querySelector('.hh-sec[data-sec=\"2\"] .hh-sec-input').value")
        стр.click('.hh-sec[data-sec="2"] .hh-sec-edit')
        стр.wait_for_timeout(300)
        видно = стр.locator('.hh-sec[data-sec="2"] .hh-sec-input').is_visible()
        шаг("изменить-открывает-поле", видно)
        стр.fill('.hh-sec[data-sec="2"] .hh-sec-input', было + "ЧЕРНОВИК\n")
        стр.click('.hh-sec[data-sec="2"] .hh-sec-edit-box .v2-btn-secondary')
        стр.wait_for_timeout(300)
        стало = стр.evaluate(
            "() => document.querySelector('.hh-sec[data-sec=\"2\"] .hh-sec-input').value")
        шаг("отмена-возвращает-исходный-текст", стало == было,
            "знаков было %d, стало %d" % (len(было), len(стало)))

        # СОХРАНЕНИЕ: уходит на сервер и подставляется ЕГО разметка
        ушло_до = len(ушло)
        стр.click('.hh-sec[data-sec="2"] .hh-sec-edit')
        стр.wait_for_timeout(200)
        стр.fill('.hh-sec[data-sec="2"] .hh-sec-input', "ПРАВЛЕНЫЙ РАЗДЕЛ\n")
        стр.click('.hh-sec[data-sec="2"] .hh-sec-save')
        стр.wait_for_timeout(700)
        тела = [т for т in ушло[ушло_до:] if "ПРАВЛЕНЫЙ РАЗДЕЛ" in (т or "")]
        шаг("правка-раздела-ушла-на-сервер", len(тела) == 1,
            "запросов с правкой: %d" % len(тела),
            собрано=len(ушло) - ушло_до,
            отрицание="сохранение не дошло до сервера")
        шаг("разметку-подставил-сервер",
            "ПРАВЛЕНЫЙ РАЗДЕЛ" in стр.inner_text("#resume-body"),
            "в теле вкладки: %s" % ("есть" if "ПРАВЛЕНЫЙ РАЗДЕЛ"
                                    in стр.inner_text("#resume-body") else "нет"))
        знаков = стр.inner_text("#resume-chars")
        шаг("счётчик-знаков-с-сервера", "424" in знаков.replace(" ", ""),
            "на экране %r" % знаков)

        доказательство = доказать(стр, подлог, len(перехвачено)) if подлог else {}
        # Пустой список ошибок — ЗАКОННЫЙ исход, а не «мерить нечего»:
        # страница отработала и не ругнулась. `отрицание` называет это
        # прямо, иначе проверка 33 числит шаг непадающим (он и правда
        # истинен на пустом сборе — но сбор здесь и должен быть пуст).
        шаг("ошибок-в-консоли-нет", not ошибки,
            "; ".join(ошибки[:2]) + (" | сеть: " + "; ".join(плохие[:3]) if плохие else ""),
            отрицание="пустой список ошибок и есть искомый исход")
        бр.close()
    return доказательство


def main():
    print("HH-АССИСТЕНТ НАСКВОЗЬ — задача 352, письмо 3, блок 2")
    print("=" * 70)
    проход()
    print("\nИТОГ: находок %d, пропусков %d" % (находок, пропусков))
    return 1 if находок else 0


def контроль():
    global находок, пропусков
    print("КОНТРОЛЬ — подлоги блока 2 (в СТРАНИЦУ, кода не трогают)")
    print("=" * 70)
    print("\nЧИСТЫЙ ПРОГОН")
    проход()
    чисто = находок
    print("  находок без подлога: %d" % чисто)
    if чисто:
        print("  ОСНОВА ГРЯЗНАЯ: контроль недействителен (§6.0.3)")
        return 2

    итог = []
    for подлог in ["ссылка-не-грузится", "письмо-без-меток",
                   "точка-всегда-серая", "сверка-таблетками",
                   "отмена-не-возвращает", "разметку-собирает-скрипт"]:
        находок, пропусков = 0, 0
        print("\nПОДЛОГ: %s" % подлог)
        док = проход(подлог)
        print("  ДОКАЗАТЕЛЬСТВО: %s" % док)
        print("  находок: %d" % находок)
        итог.append((подлог, находок > 0))

    print("\n" + "=" * 70)
    for имя, поймал in итог:
        print("  %-22s %s" % (имя, "ЛОВИТ" if поймал else "НЕ ЛОВИТ"))
    все = all(п for _, п in итог)
    print("\nКОНТРОЛЬ: %s" % ("все подлоги пойманы" if все else "ЕСТЬ НЕПОЙМАННЫЕ"))
    return 0 if все else 1


def снимки(куда):
    """Кадры всех вкладок в пустом и заполненном состоянии, 390 и 1920.

    НЕ проверка: кадры смотрит человек. Письмо и сверка подделаны — живой
    вызов показал бы не то, что увидит владелец, а разброс модели.
    """
    from playwright.sync_api import sync_playwright
    os.makedirs(куда, exist_ok=True)
    снято = 0
    with sync_playwright() as p:
        бр = p.chromium.launch()
        for ш in (1920, 390):
            к = бр.new_context(viewport={"width": ш, "height": 1300},
                               has_touch=(ш == 390), is_mobile=(ш == 390))
            стр = к.new_page()
            ушло, перехвачено = [], []
            подделать(стр, ушло, перехвачено)
            ch._войти(стр)
            стр.goto(ch.БАЗА + "/hh", wait_until="domcontentloaded")
            стр.wait_for_timeout(500)
            for вкладка in ("write", "history", "dossier", "resume"):
                стр.evaluate("n => switchView(n)", вкладка)
                стр.wait_for_timeout(400)
                стр.screenshot(path=os.path.join(куда, "hh-%s-пусто-%d.png" % (вкладка, ш)),
                               animations="disabled", full_page=(вкладка != "write"))
                снято += 1
            # заполненное состояние вкладки письма: сверка и письмо
            стр.evaluate("n => switchView(n)", "write")
            стр.fill("#job-input", ВАКАНСИЯ)
            стр.wait_for_timeout(250)
            стр.click("#analyze-btn")
            стр.wait_for_timeout(500)
            стр.click("#generate-btn")
            стр.wait_for_selector("#letter-content", state="visible", timeout=8000)
            стр.wait_for_timeout(400)
            стр.screenshot(path=os.path.join(куда, "hh-write-заполнено-%d.png" % ш),
                           animations="disabled", full_page=True)
            снято += 1
            к.close()
        бр.close()
    print("кадров: %d, каталог %s" % (снято, куда))
    return 0 if снято else 2


if __name__ == "__main__":
    if "--контроль" in sys.argv:
        sys.exit(контроль())
    if "--снимки" in sys.argv:
        sys.exit(снимки(sys.argv[sys.argv.index("--снимки") + 1]))
    sys.exit(main())
