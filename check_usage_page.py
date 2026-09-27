"""ПРОВЕРКА 70: СТРАНИЦА «РАСХОД» `/admin/usage` (№352, письмо «Расход»).

Зачем. Страница считает деньги: сколько потрачено за период, на что
и кем. Сумма, разошедшаяся с базой, выглядит так же уверенно, как верная,
и по ней решают, пополнять ли счёт и сколько брать за подписку. Поэтому
числа сверяются с ПРЯМЫМ запросом к базе, а не с кодом страницы: сверка
с её же функцией была бы тавтологией.

Две части, обе на КОПИИ базы стенда (стенд не трогается вовсе):

  А. В процессе приложения, без браузера:
     · сумма трёх периодов (7 дней, 30 дней, всё время) против SQL —
       разница 0; сумма столбиков графика — сумма периода;
     · отбор по инструменту (HH) против SQL по префиксу имени операции;
     · «активных» против SQL;
     · история остатка ПОПОЛНЯЕТСЯ: суточный запуск `balance_check`
       (остаток — заглушкой) добавляет строку, повтор в те же сутки —
       нет. Перед замером сутки в истории копии очищаются: мерится
       ПРИРОСТ, а не то, что лежало.
  Б. Живая страница в ВИДИМОМ браузере (§6.0.3: вопрос про ширину,
     headless прячет полосу прокрутки без изъятия места) на своём стенде
     по той же копии и со своей заглушкой остатка:
     · ничто не шире окна на 390 / 1280 / 1920 / 2560 и прокрутки вбок
       нет; законный срез — ТОЛЬКО своя прокрутка вбок (`overflow-x:
       auto|scroll`), а не край `clip` каркаса (тот же довод, что у
       проверки 69);
     · на 390 строки таблиц — карточки (`display: block`), шапки таблиц
       на экране нет;
     · моноширинных узлов в содержимом страницы 0 (прежняя страница
       была моноширинной целиком);
     · подсказка графика: сумма её строк равна сумме столбика, и она
       не вылезает за область графика — у крайних столбиков тоже.

Модель не вызывается ни разу; остаток OpenRouter — заглушка (в части А —
подменой функции, в части Б — своим HTTP-сервером, как у проверки 46).

Подлоги (`--контроль`), у каждого ДОКАЗАТЕЛЬСТВО независимо от вердикта:
  №1 цена одной строки подменена В ПАМЯТИ страницы — сумма расходится
     с базой, шаг сверки обязан упасть;
  №2 история остатка не пишется — шаг «пополняется» обязан упасть;
  №3 снято правило «строка таблицы — карточка» на 390 — шаг «ничто
     не шире окна» обязан упасть.

    py check_usage_page.py              # код 1 при беде, 2 — нечем проверить
    py check_usage_page.py --контроль   # три подлога
"""
import collections
import contextlib
import http.server
import io
import os
import re
import sqlite3
import sys
import tempfile
import threading
from datetime import datetime, timedelta, time as _время, timezone
from zoneinfo import ZoneInfo

import probe_guard  # noqa: F401  ПРОПУСК вместо трассы (§6.0.1)

sys.stdout.reconfigure(encoding="utf-8")
КОРЕНЬ = os.path.dirname(os.path.abspath(__file__))
ПОЧТА = "screenshot@local.dev"
МСК = ZoneInfo("Europe/Moscow")
ШИРИНЫ = (390, 1280, 1920, 2560)
ДОПУСК = 1e-9

шаги = []


def шаг(имя, условие, подробно="", собрано=None):
    """Исход шага. `собрано=0` — замер не состоялся: ПРОПУСК, а не OK."""
    if собрано == 0:
        исход = "ПРОПУСК"
    else:
        исход = "OK" if условие else "ПЛОХО"
    шаги.append((имя, исход, подробно))
    print("  %-7s %s%s" % (исход, имя, (" — " + подробно) if подробно else ""))
    return исход


def _граница(дней):
    """Полночь первых московских суток периода → строка UTC для SQLite."""
    if дней is None:
        return None
    день = datetime.now(МСК).date() - timedelta(days=дней - 1)
    м = datetime.combine(день, _время(0), МСК).astimezone(ZoneInfo("UTC"))
    return м.replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S.%f")


def _sql(база, дней, префикс=None):
    """(сумма с ценой, строк в периоде, людей) — прямым запросом, без кода страницы."""
    c = sqlite3.connect(база)
    try:
        где, арг = [], []
        г = _граница(дней)
        if г:
            где.append("created_at >= ?")
            арг.append(г)
        if префикс:
            где.append("tool LIKE ?")
            арг.append(префикс + "%")
        w = (" WHERE " + " AND ".join(где)) if где else ""
        строк = c.execute("SELECT COUNT(*) FROM model_usage" + w, арг).fetchone()[0]
        людей = c.execute("SELECT COUNT(DISTINCT user_id) FROM model_usage"
                          + w + (" AND" if где else " WHERE") + " user_id IS NOT NULL",
                          арг).fetchone()[0]
        сумма = c.execute("SELECT COALESCE(SUM(cost), 0) FROM model_usage" + w
                          + (" AND" if где else " WHERE")
                          + " ok = 1 AND cost_missing = 0 AND cost IS NOT NULL",
                          арг).fetchone()[0]
        return сумма, строк, людей
    finally:
        c.close()


def _копия():
    import check_usage_balance as ч46
    каталог = tempfile.mkdtemp(prefix="usage_page_")
    return ч46._копия_базы(каталог), каталог


# ── ЧАСТЬ А: В ПРОЦЕССЕ ПРИЛОЖЕНИЯ ───────────────────────────────────

class _Приложение:
    """`main` импортируется ОДИН раз на копии: движок читает `DB_PATH`
    при импорте. Остаток OpenRouter — подменой: сети нет вовсе."""

    def __init__(self, база, каталог):
        os.environ["DB_PATH"] = база
        os.environ.pop("FLY_APP_NAME", None)
        import main
        import balance_check
        from auth import create_token
        from fastapi.testclient import TestClient
        self.main, self.бк, self.база = main, balance_check, база
        main._расход_остаток_спросить = lambda: {
            "остаток": 11.5, "причина": None, "подробно": "",
            "при": datetime.now(timezone.utc).replace(tzinfo=None), "последний": None}
        balance_check.DB_PATH = база
        balance_check.СОСТОЯНИЕ = os.path.join(каталог, "balance_alert.json")
        balance_check.остаток_openrouter = lambda ключ, адрес=None: 11.5
        c = sqlite3.connect(база)
        строка = c.execute("SELECT id FROM users WHERE email = ?", (ПОЧТА,)).fetchone()
        c.close()
        if not строка:
            raise ConnectionError("на копии стенда нет аккаунта %s — посейте стенд" % ПОЧТА)
        self.клиент = TestClient(main.app)
        self.клиент.cookies.set("access_token", create_token(строка[0]))

    def страница(self, запрос=""):
        r = self.клиент.get("/admin/usage" + запрос)
        if r.status_code != 200:
            raise AssertionError("страница ответила HTTP %d" % r.status_code)
        return r.text

    def суточный_запуск(self):
        """Один проход `balance.yml` без отправки: история и решение."""
        os.environ["OPENROUTER_API_KEY"] = "probe-not-a-real-key"
        with contextlib.redirect_stdout(io.StringIO()):
            код = self.бк.main([])
        return код


def _страничная_сумма(html):
    м = re.search(r'id="usage-spent" data-sum="([^"]+)"', html)
    return float(м.group(1)) if м else None


def _сумма_столбиков(html):
    return sum(float(x) for x in re.findall(r'data-total="([^"]+)"', html))


def _история(база):
    c = sqlite3.connect(база)
    try:
        return c.execute("SELECT COUNT(*) FROM balance_history").fetchone()[0]
    finally:
        c.close()


def часть_а(прил):
    print("ЧАСТЬ А: сверка с базой (копия стенда, в процессе приложения)")
    замер = {}
    for код, дней in (("7", 7), ("30", 30), ("all", None)):
        html = прил.страница("?p=" + код)
        база_сумма, строк, _ = _sql(прил.база, дней)
        стр = _страничная_сумма(html)
        столбики = _сумма_столбиков(html)
        разница = None if стр is None else abs(стр - база_сумма)
        замер[код] = (стр, база_сумма)
        шаг("сумма/" + код, разница is not None and разница < ДОПУСК,
            "страница %s, база %.10f, разница %s" % (стр, база_сумма, разница),
            собрано=строк)
        шаг("график/" + код, стр is not None and abs(столбики - стр) < ДОПУСК,
            "столбики %.10f против суммы периода %s" % (столбики, стр), собрано=строк)
    html = прил.страница("?p=30&tool=hh")
    база_сумма, строк, _ = _sql(прил.база, 30, "hh-")
    стр = _страничная_сумма(html)
    шаг("отбор/hh", стр is not None and abs(стр - база_сумма) < ДОПУСК,
        "страница %s, база %.10f" % (стр, база_сумма), собрано=строк)
    html = прил.страница("?p=30")
    _, строк, людей = _sql(прил.база, 30)
    м = re.search(r'id="usage-active">(\d+)<', html)
    шаг("люди/активных", bool(м) and int(м.group(1)) == людей,
        "страница %s, база %d" % (м.group(1) if м else None, людей), собрано=строк)

    # История остатка: сутки очищаются, затем два запуска подряд
    сегодня = datetime.now(МСК).date().isoformat()
    c = sqlite3.connect(прил.база)
    c.execute("DELETE FROM balance_history WHERE day = ?", (сегодня,))
    c.commit()
    c.close()
    было = _история(прил.база)
    прил.суточный_запуск()
    после1 = _история(прил.база)
    прил.суточный_запуск()
    после2 = _история(прил.база)
    м = re.search(r'id="usage-history" data-days="(\d+)"', прил.страница())
    на_странице = int(м.group(1)) if м else None
    замер["история"] = (было, после1, после2, на_странице)
    шаг("история/пополняется", после1 == было + 1 and на_странице == после1,
        "строк %d → %d, на странице %s" % (было, после1, на_странице))
    шаг("история/без-дубля", после2 == после1,
        "повтор в те же сутки: %d → %d" % (после1, после2))
    return замер


# ── ЧАСТЬ Б: ЖИВАЯ СТРАНИЦА В ВИДИМОМ БРАУЗЕРЕ ───────────────────────

ЗАМЕР = r"""() => {
  const W = innerWidth;
  const легально = e => {
    for (let a = e.parentElement; a && a !== document.body; a = a.parentElement) {
      const ox = getComputedStyle(a).overflowX;
      if (ox === 'auto' || ox === 'scroll') return true;
    }
    return false;
  };
  const видно = e => e.checkVisibility({checkOpacity: true, checkVisibilityCSS: true});
  const шире = [];
  let всего = 0;
  for (const e of document.body.querySelectorAll('*')) {
    if (!видно(e)) continue;
    const r = e.getBoundingClientRect();
    if (!r.width || !r.height) continue;
    всего++;
    if ((r.right > W + 1 || r.left < -1) && !легально(e))
      шире.push((e.id ? '#' + e.id : e.tagName.toLowerCase() + '.' +
                 String(e.className).trim().split(/\s+/).slice(0, 2).join('.'))
                + ' ' + Math.round(r.left) + '..' + Math.round(r.right));
  }
  const стр = document.getElementById('usage');
  const моно = [];
  for (const e of стр.querySelectorAll('*')) {
    if (!видно(e)) continue;
    const свой = [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
    if (!свой) continue;
    const ф = getComputedStyle(e).fontFamily.split(',')[0].replace(/["']/g, '').trim();
    if (/mono|courier|consolas/i.test(ф)) моно.push(e.tagName.toLowerCase() + ' ' + ф);
  }
  const строки = [...document.querySelectorAll('.usage-table tbody tr')].filter(видно);
  const шапки = [...document.querySelectorAll('.usage-table thead')];
  const таблицы = [...document.querySelectorAll('.usage-table')].filter(видно);
  return {
    W, всего, шире, моно,
    вбок: document.documentElement.scrollWidth - W,
    строк: строки.length,
    строк_блоком: строки.filter(tr => getComputedStyle(tr).display === 'block').length,
    шапок_видно: шапки.filter(t => t.getBoundingClientRect().height > 1).length,
    таблица_правее: таблицы.length ? Math.round(Math.max(...таблицы.map(t => t.getBoundingClientRect().right))) : null,
  };
}"""

ПОДСКАЗКА = r"""(i) => {
  const ст = document.querySelectorAll('.usage-bar')[i];
  const tip = document.getElementById('usage-tip');
  const поле = document.getElementById('usage-plot').getBoundingClientRect();
  const т = tip.getBoundingClientRect();
  // Точные значения строк (`data-v`), а не округлённый текст: сверка
  // «сумма строк равна столбику» с допуском на округление не отличила бы
  // потерянную долю в полцента от округления
  const числа = [...tip.querySelectorAll('.usage-tip-row')]
    .map(e => parseFloat(e.dataset.v));
  return {видна: !tip.hidden && т.width > 0, всего: parseFloat(ст.dataset.total),
          строк: числа.length, сумма: числа.reduce((a, b) => a + b, 0),
          левее: поле.left - т.left, правее: т.right - поле.right};
}"""

# №3: правило «строка таблицы — карточка» снято — таблица на 390 снова
# таблица из пяти-шести колонок в одну строку
ПОДЛОГ_3 = """@media (max-width: 640px) {
  .usage-table { display: table !important; width: auto !important; }
  .usage-table thead { display: table-header-group !important; position: static !important;
    width: auto !important; height: auto !important; clip-path: none !important; }
  .usage-table tbody { display: table-row-group !important; width: auto !important; }
  .usage-table tr { display: table-row !important; width: auto !important; }
  .usage-table td, .usage-table th { display: table-cell !important; width: auto !important;
    white-space: nowrap !important; }
  .usage-table td::before { content: none !important; }
}"""


def _стенд_б(база):
    """Свой стенд на копии и своя заглушка остатка — как у проверки 46."""
    import check_usage_balance as ч46
    сервер = http.server.ThreadingHTTPServer(("127.0.0.1", 0), ч46._Остаток)
    threading.Thread(target=сервер.serve_forever, daemon=True).start()
    ч46._режим["значение"] = "ok"
    адрес = "http://127.0.0.1:%d/api/v1/credits" % сервер.server_address[1]
    п, база_адрес = ч46._стенд(база, адрес, True)
    return п, база_адрес, сервер


def часть_б(база, ширины=ШИРИНЫ, подлог_css="", подсказка=True):
    from auth import create_token
    from playwright.sync_api import sync_playwright
    print("ЧАСТЬ Б: живая страница, ширины %s" % ", ".join(map(str, ширины)))
    c = sqlite3.connect(база)
    uid = c.execute("SELECT id FROM users WHERE email = ?", (ПОЧТА,)).fetchone()[0]
    c.close()
    п, адрес, сервер = _стенд_б(база)
    замеры = {}
    try:
        with sync_playwright() as pw:
            бр = pw.chromium.launch(headless=False)
            for ш in ширины:
                к = бр.new_context(viewport={"width": ш, "height": 900}, has_touch=ш < 600)
                к.add_cookies([{"name": "access_token", "value": create_token(uid),
                                "url": адрес}])
                с = к.new_page()
                с.goto(адрес + "/admin/usage?p=30", wait_until="load", timeout=45000)
                if подлог_css:
                    с.add_style_tag(content=подлог_css)
                с.wait_for_timeout(150)
                з = с.evaluate(ЗАМЕР)
                замеры[ш] = з
                шаг("ширина/%d" % ш, not з["шире"] and з["вбок"] <= 0,
                    "шире окна %d из %d%s, прокрутка вбок %d px"
                    % (len(з["шире"]), з["всего"],
                       (": " + "; ".join(з["шире"][:3])) if з["шире"] else "", з["вбок"]),
                    собрано=з["всего"])
                шаг("моно/%d" % ш, not з["моно"],
                    "моноширинных %d%s" % (len(з["моно"]),
                                           (": " + "; ".join(з["моно"][:3])) if з["моно"] else ""),
                    собрано=з["всего"])
                if ш < 600:
                    шаг("карточки/%d" % ш,
                        з["строк_блоком"] == з["строк"] and з["шапок_видно"] == 0,
                        "строк карточкой %d из %d, шапок таблиц видно %d"
                        % (з["строк_блоком"], з["строк"], з["шапок_видно"]),
                        собрано=з["строк"])
                if подсказка and ш == 1920:
                    _подсказка(с)
                к.close()
            бр.close()
    finally:
        п.terminate()
        try:
            п.wait(15)
        except Exception:
            п.kill()
        сервер.shutdown()
    return замеры


def _подсказка(с):
    """Наведение НАСТОЯЩЕЙ мышью на первый и последний непустой столбик."""
    итоги = с.evaluate("() => [...document.querySelectorAll('.usage-bar')]"
                       ".map((b, i) => [i, parseFloat(b.dataset.total)]).filter(x => x[1] > 0)"
                       ".map(x => x[0])")
    for i in ([итоги[0], итоги[-1]] if итоги else []):
        бар = с.locator(".usage-bar").nth(i)
        бар.scroll_into_view_if_needed()
        р = бар.bounding_box()
        с.mouse.move(р["x"] + р["width"] / 2, р["y"] + р["height"] - 2)
        с.wait_for_timeout(120)
        п = с.evaluate(ПОДСКАЗКА, i)
        допуск = 1e-9
        шаг("подсказка/столбик-%d" % i,
            п["видна"] and abs(п["сумма"] - п["всего"]) <= допуск
            and п["левее"] <= 0.5 and п["правее"] <= 0.5,
            "видна %s, строк %d, сумма строк %.4f против %.4f, за край %.1f/%.1f px"
            % (п["видна"], п["строк"], п["сумма"], п["всего"], п["левее"], п["правее"]),
            собрано=п["строк"])
    if not итоги:
        шаг("подсказка/столбики", False, "непустых столбиков нет", собрано=0)
    с.mouse.move(2, 2)


# ── ПОДЛОГИ ──────────────────────────────────────────────────────────

ДОКАЗАТЕЛЬСТВА = {
    "№1 цена в памяти": "сумма страницы минус сумма базы — ровно подложенная добавка",
    "№2 история не пишется": "строк в истории до и после суточного запуска — равны",
    "№3 таблица на 390": "правый край таблиц на 390 правее окна",
}


def доказать_подлог(имя, замер):
    """Независимо от вердикта: подлог изменил ровно то, что собирался."""
    if имя == "№1":
        стр, база = замер["30"]
        return стр is not None and abs(стр - база - 0.5) < 1e-6
    if имя == "№2":
        было, после1, _, _ = замер["история"]
        return после1 == было
    if имя == "№3":
        з = замер[390]
        return з["таблица_правее"] is not None and з["таблица_правее"] > з["W"]
    return False


def _провалено(префикс):
    return any(и.startswith(префикс) and исход == "ПЛОХО" for и, исход, _ in шаги)


def контроль(прил, база):
    import main
    ловит = 0
    # №1 — одна строка периода с подменённой ценой, В ПАМЯТИ страницы
    настоящие = main._расход_строки

    def подложные(db, с_utc=None, инструмент=""):
        # Строка запроса SQLAlchemy `_replace` не умеет — подменяется
        # копией с теми же полями: страница читает их по имени
        строки = list(настоящие(db, с_utc, инструмент))
        for i, с in enumerate(строки):
            if с.ok and not с.cost_missing and с.cost is not None:
                Р = collections.namedtuple("Р", с._fields)
                строки[i] = Р(*с)._replace(cost=с.cost + 0.5)
                break
        return строки

    print("ПОДЛОГ №1: цена одной строки подменена в памяти (+0.5 $)")
    шаги.clear()
    main._расход_строки = подложные
    try:
        замер = часть_а(прил)
    finally:
        main._расход_строки = настоящие
    док = доказать_подлог("№1", замер)
    упал = _провалено("сумма/")
    print("  доказательство: страница − база = +0.5 → %s; шаг сверки упал: %s" % (док, упал))
    ловит += док and упал

    print("ПОДЛОГ №2: история остатка не пишется")
    шаги.clear()
    настоящая = прил.бк.записать_историю
    прил.бк.записать_историю = lambda *a, **k: "added"
    try:
        замер = часть_а(прил)
    finally:
        прил.бк.записать_историю = настоящая
    док = доказать_подлог("№2", замер)
    упал = _провалено("история/пополняется")
    print("  доказательство: строк до и после запуска равны → %s; шаг упал: %s" % (док, упал))
    ловит += док and упал

    print("ПОДЛОГ №3: снято правило «строка таблицы — карточка» на 390")
    шаги.clear()
    замер = часть_б(база, ширины=(390,), подлог_css=ПОДЛОГ_3, подсказка=False)
    док = доказать_подлог("№3", замер)
    упал = _провалено("ширина/390")
    print("  доказательство: правый край таблиц %s при окне %d → %s; шаг упал: %s"
          % (замер[390]["таблица_правее"], замер[390]["W"], док, упал))
    ловит += док and упал
    print("КОНТРОЛЬ: ловит %d из 3" % ловит)
    return 0 if ловит == 3 else 1


def main_():
    база, каталог = _копия()
    прил = _Приложение(база, каталог)
    if "--контроль" in sys.argv:
        return контроль(прил, база)
    часть_а(прил)
    часть_б(база)
    плохо = [ш for ш in шаги if ш[1] == "ПЛОХО"]
    пропуск = [ш for ш in шаги if ш[1] == "ПРОПУСК"]
    print("ИТОГ: шагов %d, плохих %d, пропусков %d" % (len(шаги), len(плохо), len(пропуск)))
    if плохо:
        return 1
    return 2 if пропуск else 0


if __name__ == "__main__":
    sys.exit(main_())
