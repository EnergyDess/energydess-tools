"""ПРОВЕРКА 71: СЧЁТ ПРОВЕРКИ УПРАЖНЕНИЙ (№352, письмо «Админка», блок 1).

Зачем. Полоса «Проверено N из 873» врала: засчитывала проверенным всё,
что вышло из статуса «не проверено», — то есть и записи «без видео».
На проде она показывала 21 при нуле ручных отметок (21 — упражнения без
ролика), на стенде 788 (семя справочника без роликов). Теперь проверено —
ТОЛЬКО «одобрено» и «неверное», «без видео» — отдельное число.

Числа сверяются с ПРЯМЫМ запросом к базе, а не с кодом страницы: сверка
с её же функцией была бы тавтологией.

  А. В процессе приложения, на КОПИИ базы стенда (стенд не трогается):
     · полоса, число в шапке и числа всех пяти чипов — против SQL;
     · «без видео» в проверенные не входит (на копии их обязано быть
       больше нуля, иначе подлог №1 невидим — шаг даёт ПРОПУСК);
     · отметка одного упражнения («Одобрено») — ответ сервера против SQL:
       полоса +1, «Не проверено» −1, «Одобрено» +1. Статус возвращается
       в `finally`.
  Б. Живая страница в невидимом браузере (вопрос логики, а не ширины,
     §6.0.3) на своём стенде по той же копии: те же числа на экране
     до и после нажатия «Одобрено» — против SQL. Браузер больше
     не пересчитывает чипы по своей памяти: подставляет числа ответа.

ПОДЛОГ №1 (--контроль): в проверенные засчитаны записи без видео
(`УПР_ПРОВЕРЕНО` в памяти процесса) — шаг «полоса = база» обязан упасть.
Доказательство независимо от вердикта: число на полосе равно SQL
«одобрено + неверное + без видео».

    py check_admin_exercises.py              # код 1 при беде, 2 — нечем проверить
    py check_admin_exercises.py --контроль   # подлоги письма «Админка»
"""
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile

import probe_guard  # noqa: F401 — внешний отказ говорится словом (§3)

sys.stdout.reconfigure(encoding="utf-8")
КОРЕНЬ = os.path.dirname(os.path.abspath(__file__))
ПОЧТА = "screenshot@local.dev"

шаги = []


def шаг(имя, условие, подробно="", собрано=None):
    """Исход шага. `собрано=0` — замер не состоялся: ПРОПУСК, а не OK."""
    if собрано == 0:
        исход = "ПРОПУСК"
    else:
        исход = "OK" if условие else "ПЛОХО"
    шаги.append((имя, исход, подробно))
    print("  %-7s %-34s %s" % (исход, имя, подробно))


# ── БАЗА — ПРЯМЫМ ЗАПРОСОМ ───────────────────────────────────────────

def _бд(база, запрос, арг=()):
    c = sqlite3.connect(база)
    try:
        return c.execute(запрос, арг).fetchall()
    finally:
        c.close()


def sql_счёт(база):
    """{'all', 'unchecked', 'approved', 'wrong', 'no_video', 'проверено'}.
    Проверено — ТОЛЬКО ручные отметки; определение своё, а не из `main`."""
    с = dict.fromkeys(("unchecked", "approved", "wrong", "no_video"), 0)
    for статус, n in _бд(база, "SELECT COALESCE(video_status, 'unchecked'), COUNT(*)"
                               " FROM exercises GROUP BY 1"):
        с[статус] = с.get(статус, 0) + n
    с["all"] = sum(v for k, v in с.items())
    с["проверено"] = с["approved"] + с["wrong"]
    return с


# ── СТРАНИЦА ─────────────────────────────────────────────────────────

def из_разметки(html):
    """Числа первого кадра: полоса, шапка, чипы."""
    def число(рег):
        м = re.search(рег, html)
        return int(м.group(1)) if м else None
    чипы = {}
    for м in re.finditer(r'data-pick="([a-z_]+)".*?admin-chip-n">(\d+)<', html, re.S):
        чипы.setdefault(м.group(1), int(м.group(2)))
    return {"готово": число(r'id="progress-done">(\d+)<'),
            "всего": число(r'id="progress-total">(\d+)<'),
            "шапка": число(r"Проверка видео для (\d+) упражнений"),
            "чипы": чипы}


def _копия():
    import check_usage_balance as ч46
    каталог = tempfile.mkdtemp(prefix="admin_ex_")
    return ч46._копия_базы(каталог), каталог


class _Приложение:
    """`main` импортируется ОДИН раз на копии: движок читает `DB_PATH`
    при импорте. Модель не вызывается: в сеть проба не ходит."""

    def __init__(self, база):
        os.environ["DB_PATH"] = база
        os.environ.pop("FLY_APP_NAME", None)
        import main
        from auth import create_token
        from fastapi.testclient import TestClient
        self.main, self.база = main, база
        строка = _бд(база, "SELECT id FROM users WHERE email = ?", (ПОЧТА,))
        if not строка:
            raise ConnectionError("на копии стенда нет аккаунта %s — посейте стенд" % ПОЧТА)
        self.uid = строка[0][0]
        self.клиент = TestClient(main.app)
        self.клиент.cookies.set("access_token", create_token(self.uid))

    def страница(self, запрос=""):
        r = self.клиент.get("/admin/exercises" + запрос)
        if r.status_code != 200:
            raise AssertionError("страница ответила HTTP %d" % r.status_code)
        return r.text

    def отметить(self, ид, статус):
        r = self.клиент.post("/admin/exercises/%s/status" % ид, json={"status": статус})
        return r.status_code, (r.json() if r.headers.get("content-type", "").startswith(
            "application/json") else {})


def _сверить(префикс, числа, база_счёт, собрано):
    """Три шага: полоса, шапка, чипы — против прямого запроса."""
    шаг(префикс + "полоса = база",
        числа["готово"] == база_счёт["проверено"] and числа["всего"] == база_счёт["all"],
        "на экране %s из %s, в базе %d из %d (одобрено %d + неверное %d)"
        % (числа["готово"], числа["всего"], база_счёт["проверено"], база_счёт["all"],
           база_счёт["approved"], база_счёт["wrong"]), собрано=собрано)
    шаг(префикс + "шапка = база", числа["шапка"] == база_счёт["all"],
        "в шапке %s, в базе %d" % (числа["шапка"], база_счёт["all"]), собрано=собрано)
    разошлось = {к: (в, база_счёт.get(к)) for к, в in числа["чипы"].items()
                 if в != база_счёт.get(к)}
    шаг(префикс + "чипы = база", len(числа["чипы"]) >= 5 and not разошлось,
        "чипов %d, разошлось %s" % (len(числа["чипы"]), разошлось or "0"), собрано=собрано)


def часть_а(прил):
    print("ЧАСТЬ А: полоса, шапка и чипы против базы (копия стенда, в процессе)")
    база = прил.база
    до = sql_счёт(база)
    числа = из_разметки(прил.страница())
    _сверить("А/", числа, до, до["all"])
    шаг("А/без видео — отдельно", числа["готово"] == до["проверено"],
        "без видео в базе %d; на полосе %s при ручных отметках в базе %d"
        % (до["no_video"], числа["готово"], до["проверено"]), собрано=до["no_video"])

    ид = next((r[0] for r in _бд(база, "SELECT id FROM exercises WHERE COALESCE(video_status,"
                                       " 'unchecked') = 'unchecked' ORDER BY id LIMIT 1")), None)
    if not ид:
        шаг("А/отметка согласована", False, "ЗАМЕР НЕ СОСТОЯЛСЯ: непроверенных 0", собрано=0)
        return {"до": до, "числа": числа}
    было = _бд(база, "SELECT video_status FROM exercises WHERE id = ?", (ид,))[0][0]
    try:
        код, ответ = прил.отметить(ид, "approved")
        после = sql_счёт(база)
        п = ответ.get("проверка") or {}
        с = п.get("счёт") or {}
        согласовано = (код == 200 and п.get("готово") == до["проверено"] + 1 == после["проверено"]
                       and с.get("unchecked") == до["unchecked"] - 1 == после["unchecked"]
                       and с.get("approved") == до["approved"] + 1 == после["approved"])
        шаг("А/отметка согласована", согласовано,
            "HTTP %s; полоса %d → %s (база %d); «Не проверено» %d → %s (база %d); "
            "«Одобрено» %d → %s (база %d)"
            % (код, до["проверено"], п.get("готово"), после["проверено"],
               до["unchecked"], с.get("unchecked"), после["unchecked"],
               до["approved"], с.get("approved"), после["approved"]), собрано=до["all"])
    finally:
        _бд_записать(база, "UPDATE exercises SET video_status = ? WHERE id = ?", (было, ид))
    return {"до": до, "числа": числа}


def _бд_записать(база, запрос, арг=()):
    c = sqlite3.connect(база)
    try:
        c.execute(запрос, арг)
        c.commit()
    finally:
        c.close()


# ── ЧАСТЬ Б: ЖИВАЯ СТРАНИЦА ──────────────────────────────────────────

ЭКРАН = """() => {
  const т = id => { const e = document.getElementById(id); return e ? +e.textContent : null; };
  const м = (document.querySelector('.v2-head-desc') || {}).textContent || '';
  const н = м.match(/Проверка видео для (\\d+)/);
  const чипы = {};
  document.querySelectorAll('[data-pick]').forEach(ч => {
    const n = ч.querySelector('.admin-chip-n'); if (n) чипы[ч.dataset.pick] = +n.textContent; });
  return {готово: т('progress-done'), всего: т('progress-total'),
          шапка: н ? +н[1] : null, чипы,
          карточки: [...document.querySelectorAll('.ex-card')].map(к => к.dataset.id)};
}"""


def _стенд(база):
    import check_usage_balance as ч46
    return ч46._стенд(база, "http://127.0.0.1:9/api/v1/credits", False)


def часть_б(база):
    from auth import create_token
    from playwright.sync_api import sync_playwright
    print("ЧАСТЬ Б: живая страница, отметка одного упражнения")
    uid = _бд(база, "SELECT id FROM users WHERE email = ?", (ПОЧТА,))[0][0]
    п, адрес = _стенд(база)
    ид, было = None, None
    try:
        with sync_playwright() as pw:
            бр = pw.chromium.launch(headless=True)
            к = бр.new_context(viewport={"width": 1600, "height": 1000})
            к.add_cookies([{"name": "access_token", "value": create_token(uid), "url": адрес}])
            с = к.new_page()
            с.goto(адрес + "/admin/exercises", wait_until="load", timeout=45000)
            с.wait_for_timeout(600)
            до = sql_счёт(база)
            нач = с.evaluate(ЭКРАН)
            _сверить("Б/до/", нач, до, до["all"])
            if not нач["карточки"]:
                шаг("Б/после отметки", False, "ЗАМЕР НЕ СОСТОЯЛСЯ: карточек 0", собрано=0)
                return
            ид = нач["карточки"][0]
            было = _бд(база, "SELECT video_status FROM exercises WHERE id = ?", (ид,))[0][0]
            с.click(".ex-card[data-id=%s] .ex-btn-approve" % json.dumps(ид))
            с.wait_for_timeout(1200)
            после = sql_счёт(база)
            кон = с.evaluate(ЭКРАН)
            _сверить("Б/после/", кон, после, после["all"])
            шаг("Б/три числа сдвинулись вместе",
                кон["готово"] == нач["готово"] + 1
                and кон["чипы"].get("unchecked") == нач["чипы"].get("unchecked", 0) - 1
                and кон["чипы"].get("approved") == нач["чипы"].get("approved", 0) + 1
                and после["проверено"] == до["проверено"] + 1,
                "полоса %s → %s, «Не проверено» %s → %s, «Одобрено» %s → %s, база %d → %d"
                % (нач["готово"], кон["готово"], нач["чипы"].get("unchecked"),
                   кон["чипы"].get("unchecked"), нач["чипы"].get("approved"),
                   кон["чипы"].get("approved"), до["проверено"], после["проверено"]),
                собрано=до["all"])
            бр.close()
    finally:
        if ид is not None:
            _бд_записать(база, "UPDATE exercises SET video_status = ? WHERE id = ?", (было, ид))
        п.kill()


# ── КОНТРОЛЬ ─────────────────────────────────────────────────────────

def _упал(имя):
    return any(и == имя and исход == "ПЛОХО" for и, исход, _ in шаги)


def контроль(прил):
    main = прил.main
    ловит, всего = 0, 0

    print("ПОДЛОГ №1: в проверенные засчитаны записи без видео")
    всего += 1
    шаги.clear()
    настоящее = main.УПР_ПРОВЕРЕНО
    main.УПР_ПРОВЕРЕНО = ("approved", "wrong", "no_video")
    try:
        замер = часть_а(прил)
    finally:
        main.УПР_ПРОВЕРЕНО = настоящее
    до = замер["до"]
    док = замер["числа"]["готово"] == до["проверено"] + до["no_video"] and до["no_video"] > 0
    упал = _упал("А/полоса = база")
    print("  доказательство: полоса = одобрено + неверное + без видео (%s = %d) → %s; "
          "шаг упал: %s" % (замер["числа"]["готово"], до["проверено"] + до["no_video"], док, упал))
    ловит += док and упал

    print("КОНТРОЛЬ: ловит %d из %d" % (ловит, всего))
    return 0 if ловит == всего else 1


def main_():
    база, каталог = _копия()
    try:
        прил = _Приложение(база)
        if "--контроль" in sys.argv:
            return контроль(прил)
        часть_а(прил)
        часть_б(база)
        плохо = [ш for ш in шаги if ш[1] == "ПЛОХО"]
        пропуск = [ш for ш in шаги if ш[1] == "ПРОПУСК"]
        print("ИТОГ: шагов %d, плохих %d, пропусков %d" % (len(шаги), len(плохо), len(пропуск)))
        if плохо:
            return 1
        return 2 if пропуск else 0
    finally:
        shutil.rmtree(каталог, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main_())
