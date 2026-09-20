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
    стр.wait_for_timeout(200)
    подсветка = стр.eval_on_selector_all(
        ".letter-lang-seg button",
        "e => Object.fromEntries(e.map(b => [b.dataset.lang, b.classList.contains('active')]))")
    шаг(1, "язык-английский-подсвечен",
        подсветка.get("en") is True and подсветка.get("ru") is False,
        "ru=%s en=%s" % (подсветка.get("ru"), подсветка.get("en")))

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
    после_ссылки = стр.eval_on_selector(
        ".letter-lang-seg button[data-lang=en]", "b => b.classList.contains('active')")
    шаг(1, "ссылка-не-стирает-выбор-языка", после_ссылки is True,
        "English активен после загрузки ссылки: %s" % после_ссылки)

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
    стр.click("#clear-text-btn")
    стр.wait_for_timeout(300)
    после = стр.evaluate("document.getElementById('job-input').value.length")
    шаг(3, "очистить-чистит-поле", после == 0, "осталось знаков: %d" % после)

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
          window.letterLang = lang;
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
