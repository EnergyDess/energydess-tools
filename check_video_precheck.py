"""ПРОВЕРКА 73: ПРЕДВАРИТЕЛЬНАЯ ПРОВЕРКА РОЛИКОВ МОДЕЛЬЮ (№352, письмо «Админка», блок 2).

Зачем. Кнопка «Предварительная проверка» в разделе «Упражнения» гоняет
фоном дешёвую модель по непроверенным роликам справочника и раскладывает
их на «похоже», «не похоже», «не уверена» — подсказку владельцу, а не
решение. Цена ошибки двоякая: метка, засчитанная в «Проверено», соврала
бы о работе, которой никто не делал; прогон без предела — о деньгах.

Модель и YouTube — ЗАГЛУШКИ (`model_stub`, один сервер на POST и GET):
живых вызовов в прогоне нет, денег он не стоит. Упражнения ВЫДУМАННЫЕ:
на КОПИИ базы стенда настоящие непроверенные с роликом помечены
«одобрено» (кандидатами остаются ровно выдуманные), и заведены 22 своих:

  01–06 «похоже», 07–10 «не похоже», 11–14 «не уверена» — ответ заглушки;
  15 — вердикт «да», 16 — текст без JSON: ПОДМЕНЁННЫЙ ОТВЕТ, в базу нельзя;
  17–20 — YouTube о ролике молчит: «нет данных», модель НЕ зовётся;
  21 «одобрено», 22 «неверное» — отмечены владельцем: модели не отдаются.

  А. Прогон в процессе (`TestClient` держит цикл событий — фоновая задача
     живёт между запросами): метки против ожидания, «нет данных» без
     вызова, подмена не легла, один вызов на упражнение, запрос собран
     верно, «Проверено» НЕ выросло, чипы очереди и расход — против SQL.
  Б. Предел: $0.0035 при цене вызова $0.001 — прогон встаёт после трёх
     вызовов и называет, сколько успел.
  В. Стоп и продолжение: остановленный прогон стоит (метки и вызовы
     не растут), «Продолжить» ведёт ТОТ ЖЕ прогон, и каждое упражнение
     спрошено ровно раз.
  Г. Живая страница в невидимом браузере (вопрос логики, §6.0.3) на своём
     стенде по второй копии: кнопка, ход, «Остановить» → «Продолжить» →
     «Завершена», чипы «Модель: …», метка с причиной на карточке.

--контроль — три подлога, у каждого своё ДОКАЗАТЕЛЬСТВО (`доказать_подлог`):
  №1 метка модели засчитана в «Проверено» — шаг «Проверено не выросло» падает;
  №2 вердикт вне трёх слов принят — шаг «подменённый ответ не лёг» падает;
  №3 предел не проверяется — шаг «предел остановил прогон» падает.

--живьём — ОДИН настоящий вызов ключом стенда и настоящим ключом YouTube
из .env, предел $0.05; печатает метку, причину, токены и цену. Без флага
не идёт (`model_stub.живой_замер`).

    py check_video_precheck.py              # код 1 при беде, 2 — нечем проверить
    py check_video_precheck.py --контроль
    py check_video_precheck.py --живьём
"""
import json
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time

import probe_guard  # noqa: F401 — внешний отказ говорится словом (§3)
import model_stub

sys.stdout.reconfigure(encoding="utf-8")
КОРЕНЬ = os.path.dirname(os.path.abspath(__file__))
ПОЧТА = "screenshot@local.dev"
ЦЕНА = 0.001                        # $ за вызов у заглушки
ИМЕНА = {н: "Проба ролика %02d" % н for н in range(1, 23)}
ОТВЕТ = {**{н: "похоже" for н in range(1, 7)}, **{н: "не похоже" for н in range(7, 11)},
         **{н: "не уверена" for н in range(11, 15)}}
ПОДМЕНА = {15: '{"verdict": "да", "reason": "подменённый ответ"}', 16: "Похоже, это оно."}
НЕТ_У_YOUTUBE = {17, 18, 19, 20}
ВЛАДЕЛЕЦ = {21: "approved", 22: "wrong"}
# Id ролика — ОДИННАДЦАТЬ знаков, как у настоящего: короче — кадр карточки
# отвечает 404 по форме id (`PREVIEW_ID_RE`), и консоль страницы краснеет
# не от проверки роликов. Кадры кладутся в кеш стенда (`_кадры`): эндпоинт
# отдаёт файл и к YouTube за ними не ходит
РОЛИК_ИД = "probeVid_%s"
КОД = {"похоже": "match", "не похоже": "mismatch", "не уверена": "unsure"}
ЖДУТ_ВЫЗОВА = sorted(set(ОТВЕТ) | set(ПОДМЕНА))       # 16 упражнений

шаги = []


def шаг(имя, условие, подробно="", собрано=None):
    """Исход шага. `собрано=0` — замер не состоялся: ПРОПУСК, а не OK."""
    if собрано == 0:
        исход = "ПРОПУСК"
    else:
        исход = "OK" if условие else "ПЛОХО"
    шаги.append((имя, исход, подробно))
    print("  %-7s %-40s %s" % (исход, имя, подробно))


def доказать_подлог(имя, состоялся, подробно):
    """ДОКАЗАТЕЛЬСТВО ПОДЛОГА — независимо от вердикта шага (§6.0.3)."""
    print("  доказательство «%s»: %s — %s" % (имя, "состоялся" if состоялся else "НЕ СОСТОЯЛСЯ",
                                              подробно))
    return состоялся


# ── ЗАГЛУШКИ: МОДЕЛЬ И YOUTUBE ───────────────────────────────────────

class Поведение:
    """Ответы заглушки. `задержка` — время одного ответа модели: у стопа
    должно быть время успеть."""

    def __init__(self):
        self.задержка = 0.0

    def модель(self, запрос):
        time.sleep(self.задержка)
        н = _номер_в_запросе(запрос)
        if н in ПОДМЕНА:
            текст = ПОДМЕНА[н]
        elif н in ОТВЕТ:
            текст = json.dumps({"verdict": ОТВЕТ[н], "reason": "заглушка: " + ОТВЕТ[н]},
                               ensure_ascii=False)
        else:
            текст = '{"verdict": "не уверена", "reason": "заглушка не знает упражнения"}'
        return model_stub.тело(текст, токены_входа=400, токены_выхода=30, цена=ЦЕНА)

    def get(self, запрос):
        """GET заглушки: YouTube `videos.list` и остаток OpenRouter для
        страницы «Расход» — иначе она сходила бы в настоящий сервис."""
        if запрос["path"].endswith("/credits"):
            return {"data": {"total_credits": 10.0, "total_usage": 1.5}}
        if not запрос["path"].endswith("/youtube/v3/videos"):
            return 404, {"error": "stub: путь не знаком"}
        if not запрос["query"].get("key"):
            return 400, {"error": {"code": 400, "message": "нет ключа"}}
        элементы = []
        for yt in (запрос["query"].get("id") or "").split(","):
            м = re.fullmatch(РОЛИК_ИД % r"(\d\d)", yt)
            if м and int(м.group(1)) not in НЕТ_У_YOUTUBE:
                имя = ИМЕНА[int(м.group(1))]
                элементы.append({"id": yt, "snippet": {
                    "title": "Техника: " + имя, "channelTitle": "Канал пробы",
                    "description": "Пробное описание ролика: " + имя}})
        return {"items": элементы}


def _номер_в_запросе(запрос):
    текст = json.dumps((запрос.get("json") or {}).get("messages") or [], ensure_ascii=False)
    м = re.search(r"Проба ролика (\d\d)", текст)
    return int(м.group(1)) if м else None


def _адрес_ютуба(заглушка):
    return "http://127.0.0.1:%d/youtube/v3/videos" % заглушка.порт


def окружение(заглушка) -> dict:
    """Адреса и ключи стенда пробы: модель, YouTube и остаток — заглушка.
    Ключи выдуманные: `load_dotenv` существующее не перетирает, и настоящие
    из .env в прогон не попадут."""
    return {"OPENROUTER_URL": заглушка.адрес_чата,
            "OPENROUTER_STAND_KEY": "sk-probe-not-a-real-key",
            "OPENROUTER_CREDITS_URL": "http://127.0.0.1:%d/api/v1/credits" % заглушка.порт,
            "YOUTUBE_API_KEY": "probe-youtube-key",
            "YOUTUBE_VIDEOS_URL": _адрес_ютуба(заглушка)}


def ютуб_запросы(заглушка) -> list:
    return [г for г in заглушка.запросы_get if г["path"].endswith("/youtube/v3/videos")]


def спрошено(заглушка) -> dict:
    """{номер выдуманного упражнения: сколько раз модель о нём спросили}.
    Запрос не про выдуманное — ключ None."""
    итог = {}
    for з in list(заглушка.запросы):
        н = _номер_в_запросе(з)
        итог[н] = итог.get(н, 0) + 1
    return итог


# ── БАЗА ─────────────────────────────────────────────────────────────

def _бд(база, запрос, арг=()):
    c = sqlite3.connect(база)
    try:
        return c.execute(запрос, арг).fetchall()
    finally:
        c.close()


def _бд_записать(база, *запросы):
    c = sqlite3.connect(база)
    try:
        for з in запросы:
            c.execute(*з) if isinstance(з, tuple) else c.execute(з)
        c.commit()
    finally:
        c.close()


def _копия(каталог):
    import check_usage_balance as ч46
    return ч46._копия_базы(каталог)


def _засеять(база):
    """Кандидатами прогона остаются ровно выдуманные: настоящие непроверенные
    с роликом — «одобрено». Колонки меток к этому моменту заведены миграцией."""
    c = sqlite3.connect(база)
    try:
        c.execute("UPDATE exercises SET video_status = 'approved' WHERE COALESCE(video_status,"
                  " 'unchecked') = 'unchecked' AND youtube_id IS NOT NULL AND youtube_id != ''")
        for н, имя in ИМЕНА.items():
            c.execute("INSERT OR REPLACE INTO exercises (id, name, name_ru, level, category,"
                      " primary_muscles, secondary_muscles, instructions, instructions_ru, images,"
                      " youtube_id, video_status) VALUES (?, ?, ?, 'beginner', 'strength',"
                      " '[]', '[]', '[]', '[]', '[]', ?, ?)",
                      ("zz_probe_%02d" % н, "Probe video %02d" % н, имя, РОЛИК_ИД % ("%02d" % н),
                       ВЛАДЕЛЕЦ.get(н, "unchecked")))
        c.commit()
    finally:
        c.close()


def _кадры(база, uid):
    """Файлы страницы рядом с КОПИЕЙ базы: кадры выдуманных роликов
    (`previews`) и аватар аккаунта съёмки (`avatars`). Приложение ищет их
    от `dirname(DB_PATH)`, и без них страница стенда пробы отвечала бы 404
    на файлы, которые у настоящего стенда лежат рядом с его базой."""
    from PIL import Image
    каталог = os.path.join(os.path.dirname(база), "previews")
    os.makedirs(каталог, exist_ok=True)
    for н in ИМЕНА:
        Image.new("RGB", (64, 36), (40, 44, 52)).save(
            os.path.join(каталог, РОЛИК_ИД % ("%02d" % н) + ".jpg"), "JPEG")
    исх = os.path.join(os.path.dirname(os.environ.get("STAND_DB")
                                       or os.path.join(КОРЕНЬ, "app.db")), "avatars")
    куда = os.path.join(os.path.dirname(база), "avatars")
    os.makedirs(куда, exist_ok=True)
    for имя in os.listdir(исх) if os.path.isdir(исх) else []:
        if os.path.splitext(имя)[0] == str(uid):
            shutil.copy2(os.path.join(исх, имя), os.path.join(куда, имя))


def _сбросить(база, заглушка, main=None):
    _бд_записать(база,
                 "UPDATE exercises SET model_verdict = NULL, model_reason = NULL,"
                 " model_checked_at = NULL WHERE id LIKE 'zz_probe_%'",
                 "DELETE FROM video_check_runs",
                 "DELETE FROM model_usage WHERE tool = 'admin-video-check'")
    заглушка.запросы.clear()
    заглушка.запросы_get.clear()
    if main is not None:
        main._видео_задачи.clear()


def sql_метки(база) -> dict:
    return {int(ид[-2:]): м for ид, м in
            _бд(база, "SELECT id, model_verdict FROM exercises WHERE id LIKE 'zz_probe_%'")}


def sql_проверено(база) -> int:
    return _бд(база, "SELECT COUNT(*) FROM exercises WHERE video_status IN ('approved', 'wrong')")[0][0]


def sql_очередь(база) -> dict:
    с = {"m-match": 0, "m-mismatch": 0, "m-unsure": 0}
    for м, n in _бд(база, "SELECT model_verdict, COUNT(*) FROM exercises WHERE"
                           " COALESCE(video_status, 'unchecked') = 'unchecked'"
                           " AND youtube_id IS NOT NULL AND youtube_id != ''"
                           " AND model_verdict IS NOT NULL GROUP BY 1"):
        if "m-" + м in с:
            с["m-" + м] = n
    return с


def sql_прогон(база) -> dict:
    строки = _бд(база, "SELECT id, state, calls, labelled, nodata, rejected, errors, spent_usd,"
                       " limit_usd, note FROM video_check_runs ORDER BY id")
    if not строки:
        return {"всего": 0}
    п = dict(zip(("id", "state", "calls", "labelled", "nodata", "rejected", "errors",
                  "spent", "limit", "note"), строки[-1]))
    п["всего"] = len(строки)
    return п


def sql_расход(база) -> int:
    return _бд(база, "SELECT COUNT(*) FROM model_usage WHERE tool = 'admin-video-check'")[0][0]


# ── СТРАНИЦА В ПРОЦЕССЕ ──────────────────────────────────────────────

def из_разметки(html):
    м = re.search(r'id="progress-done">(\d+)<', html)
    чипы = {}
    for ч in re.finditer(r'data-pick="([a-z_-]+)".*?admin-chip-n">(\d+)<', html, re.S):
        чипы.setdefault(ч.group(1), int(ч.group(2)))
    return {"проверено": int(м.group(1)) if м else None, "чипы": чипы}


def _ждать(к, потолок=60.0) -> dict:
    """Опрос хода, пока прогон идёт. Возвращает последнюю сводку."""
    конец = time.monotonic() + потолок
    с = {}
    while time.monotonic() < конец:
        с = к.get("/admin/api/video-check").json()
        if с.get("состояние") not in ("running", "stopping"):
            return с
        time.sleep(0.15)
    return с


def часть_а(к, база, заглушка, main):
    print("ЧАСТЬ А: прогон на заглушках — метки, «нет данных», подмена, «Проверено», расход")
    _сбросить(база, заглушка, main)
    до = из_разметки(к.get("/admin/exercises").text)
    проверено_до = sql_проверено(база)
    к.post("/admin/api/video-check/start")
    с = _ждать(к)
    п = sql_прогон(база)
    метки = sql_метки(база)
    вопросы = спрошено(заглушка)
    шаг("А/прогон завершился", п.get("state") == "done",
        "состояние %s, заметка %r" % (п.get("state"), (п.get("note") or "")[:120]),
        собрано=п["всего"])
    ждали = {н: КОД[ОТВЕТ[н]] for н in ОТВЕТ}
    мимо = {н: (метки.get(н), в) for н, в in ждали.items() if метки.get(н) != в}
    шаг("А/метки — как ответила заглушка", not мимо,
        "проставлено %d из %d, мимо %s" % (len(ждали) - len(мимо), len(ждали), мимо or "0"),
        собрано=len(ждали))
    нет_данных = [н for н in НЕТ_У_YOUTUBE if метки.get(н) == "nodata"]
    спрошены_зря = [н for н in НЕТ_У_YOUTUBE if вопросы.get(н)]
    шаг("А/«нет данных» — без вызова модели",
        len(нет_данных) == len(НЕТ_У_YOUTUBE) and not спрошены_зря,
        "«нет данных» у %d из %d, модель о них спрошена %s"
        % (len(нет_данных), len(НЕТ_У_YOUTUBE), спрошены_зря or "ни разу"),
        собрано=len(НЕТ_У_YOUTUBE))
    легло = {н: метки.get(н) for н in ПОДМЕНА if метки.get(н)}
    шаг("А/подменённый ответ не лёг", not легло and п.get("rejected") == len(ПОДМЕНА),
        "метка у подменённых %s, отвергнуто прогоном %s"
        % (легло or "нет", п.get("rejected")), собрано=len(ПОДМЕНА))
    по_разу = {н: вопросы.get(н, 0) for н in ЖДУТ_ВЫЗОВА}
    шаг("А/один вызов на упражнение",
        all(в == 1 for в in по_разу.values()) and п.get("calls") == len(ЖДУТ_ВЫЗОВА)
        == sum(вопросы.values()),
        "вызовов %s (прогон %s), не по разу %s"
        % (sum(вопросы.values()), п.get("calls"),
           {н: в for н, в in по_разу.items() if в != 1} or "0"), собрано=len(по_разу))
    чужие = {н: в for н, в in вопросы.items() if н not in ЖДУТ_ВЫЗОВА}
    шаг("А/отмеченные владельцем модели не отданы", not чужие,
        "запросов не про кандидатов: %s" % (чужие or "0"), собрано=len(ВЛАДЕЛЕЦ))
    беды = []
    for з in list(заглушка.запросы):
        н = _номер_в_запросе(з)
        беды += model_stub.проверить_запрос(
            з, main.MODEL, main.VIDEO_CHECK_MAX_TOKENS,
            обязательно=(ИМЕНА.get(н, "?"), "Техника: " + ИМЕНА.get(н, "?")))
    шаг("А/запрос собран верно", not беды,
        "запросов %d, беды %s" % (len(заглушка.запросы), беды[:3] or "0"),
        собрано=len(заглушка.запросы))
    пачки = ютуб_запросы(заглушка)
    ролики = (пачки[0]["query"].get("id") or "").split(",") if пачки else []
    шаг("А/YouTube спрошен одной пачкой с ключом",
        len(пачки) == 1 and bool(пачки[0]["query"].get("key")) and len(ролики) == 20,
        "запросов к YouTube %d, роликов в пачке %d" % (len(пачки), len(ролики)),
        собрано=len(пачки))
    после = из_разметки(к.get("/admin/exercises").text)
    проверено_после = sql_проверено(база)
    шаг("А/«Проверено» не выросло",
        до["проверено"] == после["проверено"] == проверено_до == проверено_после,
        "на экране %s → %s, в базе «одобрено + неверное» %d → %d, меток модели %d"
        % (до["проверено"], после["проверено"], проверено_до, проверено_после,
           sum(1 for м in метки.values() if м)), собрано=len(метки))
    очередь = sql_очередь(база)
    на_экране = {к_: в for к_, в in после["чипы"].items() if к_.startswith("m-")}
    шаг("А/чипы очереди = база", на_экране == очередь and sum(очередь.values()) > 0,
        "на экране %s, в базе %s" % (на_экране, очередь), собрано=len(на_экране))
    строк = sql_расход(база)
    стр_расход = к.get("/admin/usage?p=7")
    шаг("А/расход — отдельной операцией",
        строк == п.get("calls") and стр_расход.status_code == 200
        and "Админка: проверка роликов" in стр_расход.text,
        "строк учёта admin-video-check %d при вызовах %s; «Расход» HTTP %d, называет "
        "операцию: %s" % (строк, п.get("calls"), стр_расход.status_code,
                          "Админка: проверка роликов" in стр_расход.text),
        собрано=п.get("calls") or 0)
    шаг("А/сводка страницы = база",
        с.get("размечено") == sum(1 for н, м in метки.items() if м and н not in ВЛАДЕЛЕЦ)
        and с.get("к_разбору") == 20,
        "размечено %s из %s; в базе с меткой %d из 20"
        % (с.get("размечено"), с.get("к_разбору"),
           sum(1 for н, м in метки.items() if м and н not in ВЛАДЕЛЕЦ)), собрано=len(метки))
    return {"до": до, "после": после, "метки": метки, "проверено": проверено_после}


def часть_б(к, база, заглушка, main):
    print("ЧАСТЬ Б: предел расхода")
    _сбросить(база, заглушка, main)
    было = (main.ВИДЕО_ПРЕДЕЛ_USD, main.ВИДЕО_ОЦЕНКА_ВЫЗОВА_USD)
    main.ВИДЕО_ПРЕДЕЛ_USD, main.ВИДЕО_ОЦЕНКА_ВЫЗОВА_USD = 0.0035, ЦЕНА
    try:
        к.post("/admin/api/video-check/start")
        с = _ждать(к)
    finally:
        main.ВИДЕО_ПРЕДЕЛ_USD, main.ВИДЕО_ОЦЕНКА_ВЫЗОВА_USD = было
    п = sql_прогон(база)
    шаг("Б/предел остановил прогон",
        п.get("state") == "limit" and п.get("calls") == 3 and (п.get("spent") or 0) <= 0.0035 + 1e-9,
        "состояние %s, вызовов %s, потрачено $%.4f при пределе $%.4f"
        % (п.get("state"), п.get("calls"), п.get("spent") or 0, п.get("limit") or 0),
        собрано=п["всего"])
    шаг("Б/сообщает, сколько успел",
        "Успела" in (п.get("note") or "") and "вызовов модели 3" in (п.get("note") or "")
        and "по пределу" in (с.get("строка") or "") + (с.get("подпись") or ""),
        "заметка %r; на странице «%s»" % ((п.get("note") or "")[:160], с.get("подпись")),
        собрано=п["всего"])
    return п


def часть_в(к, база, заглушка, поведение, main):
    print("ЧАСТЬ В: остановить и продолжить")
    _сбросить(база, заглушка, main)
    поведение.задержка = 0.3
    try:
        к.post("/admin/api/video-check/start")
        конец = time.monotonic() + 20
        while time.monotonic() < конец and len(заглушка.запросы) < 3:
            time.sleep(0.05)
        к.post("/admin/api/video-check/stop")
        с = _ждать(к, 20)
        метки1, вопросов1 = sum(1 for м in sql_метки(база).values() if м), len(заглушка.запросы)
        time.sleep(1.5)
        метки2, вопросов2 = sum(1 for м in sql_метки(база).values() if м), len(заглушка.запросы)
        шаг("В/остановленный прогон стоит",
            с.get("состояние") == "stopped" and метки1 == метки2 and вопросов1 == вопросов2
            and 0 < вопросов1 < len(ЖДУТ_ВЫЗОВА),
            "состояние %s; меток %d → %d, вызовов %d → %d за 1.5 с"
            % (с.get("состояние"), метки1, метки2, вопросов1, вопросов2), собрано=вопросов1)
        к.post("/admin/api/video-check/start")
        с = _ждать(к, 30)
    finally:
        поведение.задержка = 0.0
    п = sql_прогон(база)
    вопросы = спрошено(заглушка)
    по_разу = {н: вопросы.get(н, 0) for н in ЖДУТ_ВЫЗОВА}
    шаг("В/«Продолжить» ведёт тот же прогон",
        п["всего"] == 1 and п.get("state") == "done" and с.get("состояние") == "done",
        "прогонов в базе %d, состояние %s" % (п["всего"], п.get("state")), собрано=п["всего"])
    шаг("В/после продолжения — по одному вызову",
        all(в == 1 for в in по_разу.values()) and п.get("calls") == len(ЖДУТ_ВЫЗОВА),
        "вызовов %d, не по разу %s" % (sum(по_разу.values()),
                                       {н: в for н, в in по_разу.items() if в != 1} or "0"),
        собрано=len(по_разу))


# ── ЧАСТЬ Г: ЖИВАЯ СТРАНИЦА ──────────────────────────────────────────

ЭКРАН = """() => {
  const т = id => { const e = document.getElementById(id); return e ? e.textContent.trim() : ''; };
  const чипы = {};
  document.querySelectorAll('[data-pick]').forEach(ч => {
    const n = ч.querySelector('.admin-chip-n'); if (n) чипы[ч.dataset.pick] = +n.textContent; });
  const кн = document.getElementById('pc-btn');
  return {готово: +т('pc-done'), всего: +т('pc-total'), кнопка: т('pc-btn'),
          кнопка_вкл: кн ? !кн.disabled : false, строка: т('pc-line'),
          проверено: +т('progress-done'), чипы,
          карточки: [...document.querySelectorAll('.ex-card')].map(к => ({id: к.dataset.id,
            метка: ((к.querySelector('.ex-card-model:not([hidden])') || {}).textContent || '').trim()}))};
}"""


def _порт():
    с = socket.socket()
    с.bind(("127.0.0.1", 0))
    п = с.getsockname()[1]
    с.close()
    return п


def _стенд(база, заглушка):
    порт = _порт()
    env = dict(os.environ)
    env.update({"DB_PATH": база, "PYTHONIOENCODING": "utf-8", **окружение(заглушка)})
    # ключ подписи — тот же, что у процесса пробы, выпускающего токен
    # (разбор — `check_usage_balance._стенд`, прогон 36486120393)
    import auth
    env["SECRET_KEY"] = auth.SECRET_KEY
    env.pop("FLY_APP_NAME", None)
    журнал = open(os.path.join(os.path.dirname(база), "stand_%d.log" % порт), "w",
                  encoding="utf-8", errors="replace")
    п = subprocess.Popen([sys.executable, "-X", "utf8", "-m", "uvicorn", "main:app",
                          "--host", "127.0.0.1", "--port", str(порт), "--log-level", "warning"],
                         cwd=КОРЕНЬ, env=env, stdout=журнал, stderr=subprocess.STDOUT)
    for _ in range(120):
        time.sleep(0.5)
        try:
            socket.create_connection(("127.0.0.1", порт), timeout=0.3).close()
            return п, "http://127.0.0.1:%d" % порт, журнал
        except OSError:
            if п.poll() is not None:
                break
    п.kill()
    журнал.close()
    raise ConnectionError("стенд пробы на порту %d не поднялся" % порт)


def _ждать_экран(стр, условие, потолок):
    конец = time.monotonic() + потолок
    э = стр.evaluate(ЭКРАН)
    while time.monotonic() < конец and not условие(э):
        стр.wait_for_timeout(200)
        э = стр.evaluate(ЭКРАН)
    return э


def часть_г(база, заглушка, поведение):
    from auth import create_token
    from playwright.sync_api import sync_playwright
    print("ЧАСТЬ Г: живая страница — кнопка, ход, стоп, продолжение, чипы, метки")
    uid = _бд(база, "SELECT id FROM users WHERE email = ?", (ПОЧТА,))[0][0]
    п, адрес, журнал = _стенд(база, заглушка)
    try:
        _засеять(база)
        _кадры(база, uid)
        заглушка.запросы.clear()
        заглушка.запросы_get.clear()
        поведение.задержка = 0.4
        with sync_playwright() as pw:
            бр = pw.chromium.launch(headless=True)
            к = бр.new_context(viewport={"width": 1600, "height": 1000})
            к.add_cookies([{"name": "access_token", "value": create_token(uid), "url": адрес}])
            с = к.new_page()
            ошибки, отказы = [], []
            с.on("pageerror", lambda e: ошибки.append(str(e)))
            с.on("console", lambda m: ошибки.append(m.text) if m.type == "error" else None)
            # отказ сети — С АДРЕСОМ: «404 в консоли» не говорит, что не приехало
            с.on("response", lambda r: отказы.append("%d %s" % (r.status, r.url))
                 if r.status >= 400 else None)
            с.goto(адрес + "/admin/exercises", wait_until="load", timeout=45000)
            нач = с.evaluate(ЭКРАН)
            шаг("Г/кнопка на месте",
                нач["кнопка"] == "Предварительная проверка" and нач["кнопка_вкл"]
                and нач["всего"] == 20 and нач["готово"] == 0,
                "кнопка «%s», размечено %s из %s" % (нач["кнопка"], нач["готово"], нач["всего"]),
                собрано=нач["всего"])
            с.click("#pc-btn")
            ход = _ждать_экран(с, lambda э: э["готово"] >= 3, 30)
            с.click("#pc-btn")                                   # «Остановить»
            стоп = _ждать_экран(с, lambda э: э["кнопка"] == "Продолжить", 20)
            метки1, вопросов1 = sum(1 for м in sql_метки(база).values() if м), len(заглушка.запросы)
            с.wait_for_timeout(1500)
            стоп2 = с.evaluate(ЭКРАН)
            метки2, вопросов2 = sum(1 for м in sql_метки(база).values() if м), len(заглушка.запросы)
            шаг("Г/«Остановить» останавливает",
                стоп["кнопка"] == "Продолжить" and стоп["строка"].startswith("Остановлена")
                and стоп["готово"] == стоп2["готово"] and метки1 == метки2
                and вопросов1 == вопросов2 and 0 < ход["готово"] < 18,
                "ход %s из %s; кнопка «%s», строка «%s…»; меток %d → %d, вызовов %d → %d"
                % (ход["готово"], ход["всего"], стоп["кнопка"], стоп["строка"][:24],
                   метки1, метки2, вопросов1, вопросов2), собрано=вопросов1)
            с.click("#pc-btn")                                   # «Продолжить»
            кон = _ждать_экран(с, lambda э: э["строка"].startswith("Завершена"), 45)
            шаг("Г/«Продолжить» доводит до конца",
                кон["строка"].startswith("Завершена") and кон["готово"] == 18
                and кон["кнопка"] == "Предварительная проверка",
                "строка «%s…», размечено %s из %s" % (кон["строка"][:24], кон["готово"],
                                                      кон["всего"]), собрано=кон["всего"])
            вопросы = спрошено(заглушка)
            шаг("Г/каждое упражнение спрошено раз",
                all(вопросы.get(н, 0) == 1 for н in ЖДУТ_ВЫЗОВА)
                and not any(н not in ЖДУТ_ВЫЗОВА for н in вопросы),
                "вызовов %d, не по разу %s" % (sum(вопросы.values()),
                                               {н: вопросы.get(н, 0) for н in ЖДУТ_ВЫЗОВА
                                                if вопросы.get(н, 0) != 1} or "0"),
                собрано=len(ЖДУТ_ВЫЗОВА))
            проверено = sql_проверено(база)
            шаг("Г/«Проверено» на экране не выросло",
                нач["проверено"] == кон["проверено"] == проверено,
                "на экране %s → %s, в базе %d" % (нач["проверено"], кон["проверено"], проверено),
                собрано=кон["всего"])
            очередь = sql_очередь(база)
            на_экране = {к_: в for к_, в in кон["чипы"].items() if к_.startswith("m-")}
            шаг("Г/чипы очереди = база", на_экране == очередь and sum(очередь.values()) > 0,
                "на экране %s, в базе %s" % (на_экране, очередь), собрано=len(на_экране))
            с.click('[data-pick="m-mismatch"]')
            с.wait_for_timeout(300)
            отбор = с.evaluate(ЭКРАН)["карточки"]
            шаг("Г/чип «Модель: не похоже» отбирает очередь",
                len(отбор) == очередь["m-mismatch"]
                and all(к_["метка"].startswith("Модель: не похоже") for к_ in отбор),
                "карточек %d при очереди %d; метки %s"
                % (len(отбор), очередь["m-mismatch"], sorted({к_["метка"][:17] for к_ in отбор})),
                собрано=len(отбор))
            с.click('[data-pick="m-match"]')
            с.wait_for_timeout(300)
            похожие = с.evaluate(ЭКРАН)["карточки"]
            шаг("Г/метка с причиной на карточке",
                bool(похожие) and all(к_["метка"] == "Модель: похоже — заглушка: похоже"
                                      for к_ in похожие),
                "карточек %d, пример «%s»" % (len(похожие), похожие[0]["метка"] if похожие else ""),
                собрано=len(похожие))
            шаг("Г/ошибок в консоли и отказов сети нет", not ошибки and not отказы,
                "; ".join((ошибки + отказы)[:4]) or "0", собрано=len(нач["карточки"]))
            бр.close()
    finally:
        поведение.задержка = 0.0
        п.kill()
        журнал.close()


# ── КОНТРОЛЬ ─────────────────────────────────────────────────────────

def _упал(имя):
    return any(и == имя and исход == "ПЛОХО" for и, исход, _ in шаги)


def контроль(к, база, заглушка, main):
    ловит, всего = 0, 0

    print("ПОДЛОГ №1: метка модели засчитана в «Проверено»")
    всего += 1
    шаги.clear()
    исх = main._упр_проверка

    def с_метками(db):
        п = исх(db)
        п["готово"] += п["модель"]["метки"]["match"]
        return п
    main._упр_проверка = с_метками
    try:
        замер = часть_а(к, база, заглушка, main)
    finally:
        main._упр_проверка = исх
    похоже = sum(1 for м in замер["метки"].values() if м == "match")
    док = доказать_подлог("метка в «Проверено»",
                          замер["после"]["проверено"] == замер["проверено"] + похоже and похоже > 0,
                          "на полосе %s = в базе %d + «похоже» %d"
                          % (замер["после"]["проверено"], замер["проверено"], похоже))
    упал = _упал("А/«Проверено» не выросло")
    print("  шаг «Проверено не выросло» упал: %s" % упал)
    ловит += док and упал

    print("ПОДЛОГ №2: вердикт вне трёх слов принят")
    всего += 1
    шаги.clear()
    исх_р = main._видео_разобрать

    def всё_принять(текст):
        код, причина, беда = исх_р(текст)
        return (код, причина, None) if код else ("match", "принято подлогом", None)
    main._видео_разобрать = всё_принять
    try:
        замер = часть_а(к, база, заглушка, main)
    finally:
        main._видео_разобрать = исх_р
    легло = {н: замер["метки"].get(н) for н in ПОДМЕНА}
    док = доказать_подлог("вердикт вне трёх слов", all(легло.values()),
                          "у подменённых в базе метки %s" % легло)
    упал = _упал("А/подменённый ответ не лёг")
    print("  шаг «подменённый ответ не лёг» упал: %s" % упал)
    ловит += док and упал

    print("ПОДЛОГ №3: предел не проверяется")
    всего += 1
    шаги.clear()
    исх_ш = main._видео_шаг

    def без_предела(run_id, у, без_вызова):
        return исх_ш(run_id, у, без_вызова=True)
    main._видео_шаг = без_предела
    try:
        п = часть_б(к, база, заглушка, main)
    finally:
        main._видео_шаг = исх_ш
    док = доказать_подлог("предел не проверяется", (п.get("calls") or 0) > 3,
                          "вызовов %s при пределе на 3" % п.get("calls"))
    упал = _упал("Б/предел остановил прогон")
    print("  шаг «предел остановил прогон» упал: %s" % упал)
    ловит += док and упал

    print("КОНТРОЛЬ: ловит %d из %d" % (ловит, всего))
    return 0 if ловит == всего else 1


# ── ЖИВЬЁМ ───────────────────────────────────────────────────────────

def живьём():
    model_stub.живой_замер("проверка 73: живой вызов предварительной проверки",
                           покрывает="py check_video_precheck.py")
    каталог = tempfile.mkdtemp(prefix="video_live_")
    try:
        база = _копия(каталог)
        os.environ["DB_PATH"] = база
        os.environ.pop("FLY_APP_NAME", None)
        import main
        from auth import create_token
        from fastapi.testclient import TestClient
        uid = _бд(база, "SELECT id FROM users WHERE email = ?", (ПОЧТА,))
        if not uid:
            raise ConnectionError("на копии стенда нет аккаунта %s — посейте стенд" % ПОЧТА)
        кандидаты = [r[0] for r in _бд(база, "SELECT id FROM exercises WHERE COALESCE(video_status,"
                                             " 'unchecked') = 'unchecked' AND youtube_id IS NOT NULL"
                                             " AND youtube_id != '' ORDER BY id")]
        if not кандидаты:
            print("ПРОПУСК: на копии стенда нет непроверенных упражнений с роликом")
            return 2
        main.ВИДЕО_ПРЕДЕЛ_USD = 0.05
        with TestClient(main.app) as к:
            к.cookies.set("access_token", create_token(uid[0][0]))
            for ид in кандидаты[:3]:
                # КАНДИДАТ РОВНО ОДИН: остальные непроверенные — «одобрено» на копии.
                # Первой строкой он возвращается в «не проверено»: прошлая попытка
                # цикла пометила его «одобрено» вместе со всеми
                _бд_записать(база,
                             ("UPDATE exercises SET video_status = 'unchecked' WHERE id = ?", (ид,)),
                             ("UPDATE exercises SET video_status = 'approved' WHERE"
                              " COALESCE(video_status, 'unchecked') = 'unchecked' AND id != ?",
                              (ид,)))
                к.post("/admin/api/video-check/start")
                с = _ждать(к, 120)
                п = sql_прогон(база)
                if п.get("state") == "error" and not п.get("calls"):
                    print("ПРОПУСК: %s" % (п.get("note") or "прогон упал без вызова"))
                    return 2
                if п.get("calls"):
                    break
                print("  %s: «нет данных», вызова не было — беру следующее" % ид)
            строка = _бд(база, "SELECT model, prompt_tokens, completion_tokens, cost, ok, error_code"
                               " FROM model_usage WHERE tool = 'admin-video-check'"
                               " ORDER BY id DESC LIMIT 1")
            метка = _бд(база, "SELECT model_verdict, model_reason FROM exercises WHERE id = ?", (ид,))
        print("  упражнение %s; прогон %s; «%s»" % (ид, п.get("state"), с.get("строка")))
        print("  метка %s, причина «%s»" % (метка[0] if метка else ("—", "—")))
        if строка:
            print("  модель %s, токенов %s → %s, цена $%s, ok %s, код %s" % строка[0])
        цена = строка[0][3] if строка else None
        шаг("живьём/один вызов в пределах $0.05",
            п.get("calls") == 1 and цена is not None and цена <= 0.05,
            "вызовов %s, цена $%s" % (п.get("calls"), цена), собрано=п.get("calls") or 0)
        шаг("живьём/метка легла", bool(метка and метка[0][0]),
            "метка %s" % (метка[0][0] if метка else None), собрано=п.get("calls") or 0)
        return 1 if any(ш[1] == "ПЛОХО" for ш in шаги) else 0
    finally:
        shutil.rmtree(каталог, ignore_errors=True)


def main_():
    if model_stub.ФЛАГ_ЖИВЬЁМ in sys.argv:
        return живьём()
    каталог = tempfile.mkdtemp(prefix="video_check_")
    поведение = Поведение()
    try:
        база = _копия(каталог)
        with model_stub.Заглушка() as заглушка:
            заглушка.ответ = поведение.модель
            заглушка.ответ_get = поведение.get
            os.environ.update({"DB_PATH": база, **окружение(заглушка)})
            os.environ.pop("FLY_APP_NAME", None)
            import main
            from auth import create_token
            from fastapi.testclient import TestClient
            uid = _бд(база, "SELECT id FROM users WHERE email = ?", (ПОЧТА,))
            if not uid:
                raise ConnectionError("на копии стенда нет аккаунта %s — посейте стенд" % ПОЧТА)
            with TestClient(main.app) as к:            # старт: миграции копии
                к.cookies.set("access_token", create_token(uid[0][0]))
                _засеять(база)
                if "--контроль" in sys.argv:
                    return контроль(к, база, заглушка, main)
                часть_а(к, база, заглушка, main)
                часть_б(к, база, заглушка, main)
                часть_в(к, база, заглушка, поведение, main)
            база_г = _копия(tempfile.mkdtemp(prefix="g_", dir=каталог))
            часть_г(база_г, заглушка, поведение)
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
