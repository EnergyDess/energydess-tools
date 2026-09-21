"""ЧЕМ КОНЧАЕТСЯ «НАПИСАТЬ ПИСЬМО»: КАРТОЧКА НЕ ОСТАЁТСЯ ПУСТОЙ (№352, авария 21.09).

ПРОВЕРКА, код 1 при находке, 2 — замерить нечем.

АВАРИЯ, РАДИ КОТОРОЙ ЗАВЕДЕНА. На проде 21.09 после нажатия «Написать
письмо» шла анимация, а потом карточка оставалась ПУСТОЙ — один
заголовок, ни письма, ни ошибки. В журнале вызовов модели — два разбора
вакансии и НИ ОДНОГО вызова письма: сервер вернул предупреждение о низкой
релевантности, а плашка предупреждения на экране НЕВИДИМА — у неё стоит
атрибут `hidden`, а показывали её `style.display`, и правило
`[hidden] { display: none !important }` побеждает.

Проба 49 (`check_hh_ui`) этого не видела по построению: она подделывает
ответ генерации ОДНИМ телом — готовым письмом. Здесь спрашивается КАЖДЫЙ
исход запроса, и вопрос один: после ответа на экране видно ровно одно
из трёх — письмо, предупреждение, ошибка с кнопкой повтора.

ИСХОДОВ ДВА РОДА:
  · НАСТОЯЩИЙ СЕРВЕР в условиях прода — свой стенд на копии базы стенда,
    `LETTER_PROMPT_VARIANT=кэш`, адрес OpenRouter подменён ЗАГЛУШКОЙ
    (`model_stub`), денег ноль. Низкая релевантность, затем «всё равно»;
    обычная генерация на английском — и запрос письма сверяется
    с заглушки: путь кэша, инструкция английского;
  · ПОДДЕЛЬНЫЙ ОТВЕТ в странице: 500 с текстом, 502 страницей прокси,
    обрыв сети, 200 без письма.

ПЕРЕКЛЮЧАТЕЛЬ ЯЗЫКА: у нажатой кнопки фон и цвет ОТЛИЧАЮТСЯ от соседки —
компонент v2 знает класс `.is-active`, а страница ставила `.active`.

КЛЮЧИ:
  --контроль   три подлога в СТРАНИЦУ, у каждого своё доказательство:
                 плашка-невидима     — вернуть `hidden` на предупреждение;
                 ошибка-не-видна     — сбой рисует пустую карточку;
                 язык-класс-active   — переключатель ставит прежний класс.
"""
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time

try:
    import probe_guard  # noqa: F401  ПРОПУСК вместо трассы (§6.0.1)
except ImportError:
    pass

КОРЕНЬ = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, КОРЕНЬ)
import model_stub  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ПОЧТА, ПАРОЛЬ = "screenshot@local.dev", "Screenshot-Local-2026"
# ВЫДУМАННАЯ вакансия и выдуманное письмо (§5.1)
ВАКАНСИЯ = ("Требуется инженер по машинному зрению. Обязанности: конвейер "
            "разметки, дообучение детекторов. Требования: Python, PyTorch.")
ПИСЬМО_EN = ("Hello! Your computer vision role matches my daily work.\n"
             "I built annotation pipelines and shipped detectors to production.")

находок = 0
пропусков = 0
_оценка = {"значение": 8}


def шаг(имя, условие, подробность="", собрано=None, отрицание=None):
    """`собрано` — сколько собрано для замера; ноль — ПРОПУСК (проверка 33)."""
    global находок, пропусков
    if собрано is not None and not собрано:
        пропусков += 1
        print("  %-7s %s — сбор пуст, мерить нечего" % ("ПРОПУСК", имя))
        return
    if not условие:
        находок += 1
    print("  %-4s %s%s" % ("OK" if условие else "ПЛОХО", имя,
                           (" — " + подробность) if подробность else ""))


def _ответ_модели(запрос):
    сообщения = (запрос.get("json") or {}).get("messages") or []
    первое = сообщения[0].get("content") if сообщения else ""
    текст = первое if isinstance(первое, str) else json.dumps(первое, ensure_ascii=False)
    if "Проанализируй соответствие" in текст:
        return model_stub.тело(json.dumps({
            "job_title": "Инженер по машинному зрению", "company_name": "ООО Пример",
            "relevance_score": _оценка["значение"], "relevance_reason": "Проба.",
            "key_matches": ["Python"], "missing_skills": [], "tone_suggestion": "деловой",
            "relevant_portfolio_links": [], "focus_points": ["детекция"]},
            ensure_ascii=False))
    return model_stub.тело(ПИСЬМО_EN)


def _порт():
    with socket.socket() as с:
        с.bind(("127.0.0.1", 0))
        return с.getsockname()[1]


def _стенд(каталог, адрес_модели):
    исх = os.environ.get("STAND_DB") or os.path.join(КОРЕНЬ, "app.db")
    if "/data/" in исх.replace("\\", "/"):
        raise ConnectionError("путь к боевой базе — проба ходит только в копию")
    if not os.path.exists(исх):
        raise ConnectionError("базы стенда нет: %s" % исх)
    база = os.path.join(каталог, "app.db")
    a, b = sqlite3.connect(исх), sqlite3.connect(база)
    a.backup(b)
    a.close()
    b.close()
    порт = _порт()
    env = dict(os.environ)
    env.update({"DB_PATH": база, "PYTHONIOENCODING": "utf-8",
                "OPENROUTER_URL": адрес_модели,
                "OPENROUTER_STAND_KEY": "sk-probe-not-a-real-key",
                # УСЛОВИЯ ПРОДА: путь кэша (замер 21.09 — на проде стоит он)
                "LETTER_PROMPT_VARIANT": "кэш"})
    env.pop("FLY_APP_NAME", None)
    журнал = open(os.path.join(каталог, "stand.log"), "w", encoding="utf-8", errors="replace")
    п = subprocess.Popen([sys.executable, "-X", "utf8", "-m", "uvicorn", "main:app",
                          "--host", "127.0.0.1", "--port", str(порт), "--log-level", "warning"],
                         cwd=КОРЕНЬ, env=env, stdout=журнал, stderr=subprocess.STDOUT)
    for _ in range(120):
        time.sleep(0.5)
        try:
            socket.create_connection(("127.0.0.1", порт), timeout=0.3).close()
            return п, "http://127.0.0.1:%d" % порт
        except OSError:
            if п.poll() is not None:
                break
    п.kill()
    raise ConnectionError("стенд пробы не поднялся")


# Что видно в карточке письма после ответа. «Видно» — дотягивается нажатие.
ИСХОД = """() => {
  function видно(sel) {
    const э = document.querySelector(sel);
    if (!э || !э.checkVisibility({opacityProperty: true, visibilityProperty: true})) return false;
    const r = э.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) return false;
    э.scrollIntoView({block: 'center'});
    const q = э.getBoundingClientRect();
    const т = document.elementFromPoint(q.left + q.width / 2, q.top + q.height / 2);
    return !!т && (т === э || э.contains(т) || т.contains(э));
  }
  const пис = document.getElementById('letter-content');
  return {
    письмо: видно('#letter-content') && (пис.innerText || '').trim().length > 0,
    предупреждение: видно('#warn-state .hh-warn-box'),
    ошибка: видно('#error-state') && (document.getElementById('error-msg').innerText || '').trim().length > 0,
    повтор: видно('#error-retry'),
    текст_ошибки: (document.getElementById('error-msg') || {}).innerText || '',
    загрузка: видно('#loading-state'),
  };
}"""

ЯЗЫК = """() => {
  const к = [...document.querySelectorAll('.letter-lang-seg [data-lang]')];
  return к.map(b => {
    const s = getComputedStyle(b);
    return {язык: b.dataset.lang, фон: s.backgroundColor, цвет: s.color};
  });
}"""

ПОДЛОГИ = {
    "плашка-невидима":
        "addEventListener('DOMContentLoaded', () => {"
        " const w = document.getElementById('warn-state');"
        " const s = window.setState;"
        " window.setState = (st) => { s(st); if (w) w.hidden = true; }; });",
    "ошибка-не-видна":
        "addEventListener('DOMContentLoaded', () => {"
        " const s = window.setState;"
        " window.setState = (st) => s(st === 'error' ? 'none' : st); });",
    "язык-класс-active":
        "addEventListener('DOMContentLoaded', () => {"
        # `letterLang` объявлен через `let` и в окне не живёт: язык запроса
        # подлог не трогает, он ломает РОВНО подсветку (проверка 30)
        " window.setLetterLang = (lang) => {"
        "   document.querySelectorAll('.letter-lang-seg [data-lang]').forEach(b => {"
        "     b.classList.remove('is-active');"
        "     b.classList.toggle('active', b.dataset.lang === lang); }); }; });",
}


def доказать(стр, подлог):
    """Независимый замер звена, в которое метил подлог (§6.0.3)."""
    if подлог == "плашка-невидима":
        return {"setState прячет плашку": стр.evaluate(
            "() => (window.setState||'').toString().includes('w.hidden = true')")}
    if подлог == "ошибка-не-видна":
        return {"setState подменён": стр.evaluate(
            "() => (window.setState||'').toString().includes(\"'none'\")")}
    if подлог == "язык-класс-active":
        return {"ставит .active": стр.evaluate(
            "() => (window.setLetterLang||'').toString().includes(\"'active'\")")}
    return {}


def _генерация(стр):
    стр.click("#generate-btn")
    стр.wait_for_function(
        "() => !document.getElementById('generate-btn').disabled", timeout=30000)
    стр.wait_for_timeout(300)
    return стр.evaluate(ИСХОД)


def _один_исход(имя, исх, ждём):
    видно = [к for к in ("письмо", "предупреждение", "ошибка") if исх[к]]
    шаг(имя, видно == [ждём] and (ждём != "ошибка" or исх["повтор"]),
        "видно: %s%s" % (", ".join(видно) or "НИЧЕГО — пустая карточка",
                         "" if ждём != "ошибка" else "; кнопка повтора: %s" % исх["повтор"]))


def проход(подлог=None):
    import check_hover as ch
    from playwright.sync_api import sync_playwright
    каталог = tempfile.mkdtemp(prefix="hh_letter_")
    п = None
    доказательство = {}
    try:
        with model_stub.Заглушка() as з:
            з.ответ = _ответ_модели
            п, база = _стенд(каталог, з.адрес_чата)
            ch.БАЗА, ch.ПОЧТА, ch.ПАРОЛЬ = база, ПОЧТА, ПАРОЛЬ
            with sync_playwright() as pw:
                бр = pw.chromium.launch()
                к = бр.new_context(viewport={"width": 1600, "height": 1100})
                if подлог:
                    к.add_init_script(ПОДЛОГИ[подлог])
                стр = к.new_page()
                ch._войти(стр)
                стр.goto(база + "/hh", wait_until="domcontentloaded")
                стр.wait_for_timeout(400)
                стр.fill("#job-input", ВАКАНСИЯ)
                стр.wait_for_timeout(900)  # автоопределение языка отработало

                print("\n1. ПЕРЕКЛЮЧАТЕЛЬ ЯЗЫКА")
                стр.click(".letter-lang-seg [data-lang=en]")
                # Указатель уводится: иначе у нажатой кнопки фон и цвет
                # от НАВЕДЕНИЯ, и «подсвечена» выходит при мёртвом классе
                # (первый прогон так и соврал — §6.0.3, физический указатель)
                стр.mouse.move(1, 1)
                стр.wait_for_timeout(350)
                кн = стр.evaluate(ЯЗЫК)
                en = next((x for x in кн if x["язык"] == "en"), {})
                ru = next((x for x in кн if x["язык"] == "ru"), {})
                шаг("нажатая-English-подсвечена",
                    bool(en) and (en["фон"] != ru.get("фон") or en["цвет"] != ru.get("цвет")),
                    "en фон %s цвет %s / ru фон %s цвет %s" % (
                        en.get("фон"), en.get("цвет"), ru.get("фон"), ru.get("цвет")),
                    собрано=len(кн))

                print("\n2. НАСТОЯЩИЙ СЕРВЕР, УСЛОВИЯ ПРОДА (кэш, заглушка модели)")
                _оценка["значение"] = 2
                исх = _генерация(стр)
                _один_исход("низкая-релевантность-видна", исх, "предупреждение")
                if исх["предупреждение"]:
                    стр.click("#warn-state .hh-warn-box button")
                    стр.wait_for_function(
                        "() => !document.getElementById('generate-btn').disabled", timeout=30000)
                    стр.wait_for_timeout(300)
                    _один_исход("после-«всё-равно»-письмо", стр.evaluate(ИСХОД), "письмо")
                _оценка["значение"] = 8
                до = len(з.запросы)
                исх = _генерация(стр)
                _один_исход("обычная-генерация-письмо", исх, "письмо")
                письма = [з_ for з_ in з.запросы[до:]
                          if "Проанализируй соответствие" not in json.dumps(
                              з_.get("json") or {}, ensure_ascii=False)]
                if письма:
                    сооб = письма[-1]["json"]["messages"][0]["content"]
                    кэш = isinstance(сооб, list) and any("cache_control" in ч for ч in сооб)
                    текст = json.dumps(сооб, ensure_ascii=False)
                    шаг("запрос-письма-по-пути-кэша", кэш, "блоков %s" % (
                        len(сооб) if isinstance(сооб, list) else "строка"))
                    шаг("в-запросе-инструкция-английского",
                        "ENTIRELY IN ENGLISH" in текст)
                else:
                    шаг("запрос-письма-дошёл-до-модели", False, "вызовов письма 0")

                print("\n3. ПОДДЕЛЬНЫЕ ОТВЕТЫ: СБОЙ НЕ ДАЁТ ПУСТОЙ КАРТОЧКИ")
                случаи = [
                    ("500-с-текстом", lambda r: r.fulfill(
                        status=500, content_type="application/json",
                        body=json.dumps({"error": "Сбой на сервере"}, ensure_ascii=False))),
                    ("502-страница-прокси", lambda r: r.fulfill(
                        status=502, content_type="text/html", body="<html>Bad gateway</html>")),
                    ("обрыв-сети", lambda r: r.abort("connectionreset")),
                    ("200-без-письма", lambda r: r.fulfill(
                        status=200, content_type="application/json", body="{}")),
                ]
                for имя, ответ in случаи:
                    стр.route("**/api/generate-letter", ответ)
                    исх = _генерация(стр)
                    _один_исход(имя, исх, "ошибка")
                    стр.unroute("**/api/generate-letter")
                if подлог:
                    доказательство = доказать(стр, подлог)
                бр.close()
    finally:
        if п and п.poll() is None:
            п.terminate()
            try:
                п.wait(15)
            except subprocess.TimeoutExpired:
                п.kill()
        shutil.rmtree(каталог, ignore_errors=True)
    return доказательство


def контроль():
    global находок, пропусков
    не_найдено = 0
    for подлог in ПОДЛОГИ:
        находок = пропусков = 0
        print("\n═══ ПОДЛОГ: %s" % подлог)
        док = проход(подлог)
        print("  ДОКАЗАТЕЛЬСТВО:", док)
        состоялся = all(bool(v) for v in док.values()) and bool(док)
        найден = находок > 0
        print("  ИТОГ: подлог %s, проба %s" % ("СОСТОЯЛСЯ" if состоялся else "НЕ СОСТОЯЛСЯ",
                                              "НАШЛА" if найден else "НЕ НАШЛА"))
        if not (состоялся and найден):
            не_найдено += 1
    print("\nКОНТРОЛЬ: подлогов %d, не найдено %d" % (len(ПОДЛОГИ), не_найдено))
    return 1 if не_найдено else 0


def main():
    if "--контроль" in sys.argv:
        return контроль()
    проход()
    print("\nИТОГ: находок %d, пропусков %d" % (находок, пропусков))
    if находок:
        return 1
    return 2 if пропусков else 0


if __name__ == "__main__":
    sys.exit(main())
