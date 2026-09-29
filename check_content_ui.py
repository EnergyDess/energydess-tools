"""ПРОВЕРКА 74: СТРАНИЦА «КОНТЕНТ» (BACKLOG №365, 366) — три вкладки глазами владельца.

Что спрашивается на 1920 и 2560 (мониторы владельца) и на 390 с касанием:
  · вкладки — нажатие показывает ровно свой раздел, адрес помнит вкладку;
  · ничто не шире окна (законный срез — только своя прокрутка таблицы)
    и строка текста не длиннее 90 знаков (мера проверки 67, импортом);
  · сюжеты — на экране столько, сколько в базе у свежих; у сюжета
    с утечкой ВИДНА заметка «кадры утечки показывать нельзя»; число
    источников в карточке равно числу в базе;
  · источники — у красного источника ВИДЕН текст последней ошибки,
    у каждого — время последнего удачного запуска;
  · реестр каналов — «Убрать» и «Оставить» меняют статус В БАЗЕ
    (копия стенда), а строка перерисовывается по ответу сервера.

Стенд свой — на КОПИИ базы стенда: «Убрать» пишет в базу, а ряд обязан
быть безопасным для любого прогона. Браузер ВИДИМЫЙ (§6.0.3): меряются
ширины. Кадры каждой вкладки ложатся в `review_screenshots/content/`
(в .gitignore) — их смотрит человек, в контекст они не читаются (§6.4 «г»).

ПОДЛОГИ (--контроль), у каждого доказательство независимо от вердикта:
  · заметка утечки спрятана стилем — шаг «сюжеты/утечка» падает;
    доказательство: заметок, видимых по `checkVisibility`, 0;
  · текст ошибки источника спрятан — шаг «источники/ошибка» падает;
  · вкладки не переключаются (обработчики сняты) — шаг «вкладки» падает;
    доказательство: после нажатия раздел «Форматы» остался скрытым.

    py check_content_ui.py              # код 1 при беде, 2 — нечем проверить
    py check_content_ui.py --контроль
"""
import os
import shutil
import sqlite3
import sys
import tempfile

import probe_guard  # noqa: F401 — внешний отказ говорится словом (§3)

sys.stdout.reconfigure(encoding="utf-8")
КОРЕНЬ = os.path.dirname(os.path.abspath(__file__))
ПОЧТА = "screenshot@local.dev"
ШИРИНЫ = ((1920, 1080, False), (2560, 1440, False), (390, 844, True))
КАДРЫ = os.path.join(КОРЕНЬ, "review_screenshots", "content")
ЗАМЕТКА = "кадры утечки показывать нельзя"

ПОДЛОГ_УТЕЧКИ = ".content-leak { display: none !important; }"
ПОДЛОГ_ОШИБКИ = ".content-source-error { display: none !important; }"
ПОДЛОГ_ВКЛАДОК = """() => document.querySelectorAll('.content-page .v2-tab[data-tab]')
  .forEach(к => к.replaceWith(к.cloneNode(true)))"""

шаги = []


def шаг(имя, условие, подробно="", собрано=None):
    """Исход шага. `собрано=0` — замер не состоялся: ПРОПУСК, а не OK."""
    if собрано == 0:
        исход = "ПРОПУСК"
    else:
        исход = "OK" if условие else "ПЛОХО"
    шаги.append((имя, исход, подробно))
    print("  %-7s %-30s %s" % (исход, имя, подробно))


def _копия():
    import check_usage_balance as ч46
    каталог = tempfile.mkdtemp(prefix="content_ui_")
    return ч46._копия_базы(каталог), каталог


def _стенд(база):
    import check_usage_balance as ч46
    return ч46._стенд(база, "http://127.0.0.1:9/api/v1/credits", False)


def _база(база, запрос, *п):
    c = sqlite3.connect(база)
    try:
        return c.execute(запрос, п).fetchall()
    finally:
        c.close()


ЗАМЕР_ЭКРАНА = r"""(заметка) => {
  const вид = (э) => !!э && э.checkVisibility({checkOpacity: true, checkVisibilityCSS: true});
  const ш = document.documentElement.clientWidth;
  // ЗАКОННЫЙ СРЕЗ — ТОЛЬКО СВОЯ ПРОКРУТКА ВБОК (тот же довод, что у
  // проверки 69): элемент внутри контейнера с прокруткой по горизонтали
  // уходит за окно законно — таблица в `.content-scroll`, лента вкладок.
  const в_прокрутке = (э) => {
    for (let п = э.parentElement; п && п !== document.body; п = п.parentElement) {
      const о = getComputedStyle(п).overflowX;
      if (о === 'auto' || о === 'scroll') return true;
    }
    return false;
  };
  const шире = [];
  for (const э of document.querySelectorAll('.content-page *')) {
    if (!вид(э) || в_прокрутке(э)) continue;
    const r = э.getBoundingClientRect();
    if (r.width && (r.right > ш + 1 || r.left < -1))
      шире.push(э.tagName.toLowerCase() + '.' + String(э.className || '').split(' ')[0]
                + ' ' + Math.round(r.left) + '..' + Math.round(r.right));
  }
  const разделы = {};
  for (const в of document.querySelectorAll('.content-view')) разделы[в.dataset.view] = вид(в);
  const активные = [...document.querySelectorAll('.content-page .v2-tab.is-active')].map(к => к.dataset.tab);
  const сюжеты = [...document.querySelectorAll('.content-story')].map(с => ({
    id: с.dataset.story, утечка: с.dataset.leak === 'true', источников: +с.dataset.sources,
    в_карточке: +((с.querySelector('.content-src-n') || {}).textContent || -1),
    заметка: вид(с.querySelector('.content-leak'))
      && (с.querySelector('.content-leak').textContent || '').includes(заметка)}));
  const источники = [...document.querySelectorAll('.content-source')].map(и => ({
    id: и.dataset.source, тон: (и.className.match(/is-(\w+)/) || [])[1],
    строка: вид(и.querySelector('.content-source-line')),
    ошибка: вид(и.querySelector('.content-source-error'))
      && (и.querySelector('.content-source-error').textContent || '').trim().length > 20}));
  return {шире, разделы, активные, адрес: location.search, сюжеты, источники,
          хитов: document.querySelectorAll('#content-arch-table tbody tr').length,
          огр: document.querySelectorAll('#content-arch-table .content-flag.is-limited').length};
}"""


def _ожидание(база):
    """Что СЕРВЕР отдаёт странице — ТОЙ ЖЕ функцией отбора (`content_app`),
    на своей сессии к копии базы. Второй копии фильтра («свежие за 14 дней»,
    «не больше 60 сюжетов») в пробе нет: разошлась бы молча (§6.0.7).
    Числа карточки при этом берутся из базы — вопрос пробы «нарисовано ли
    всё отобранное и теми ли числами», а не «верен ли отбор» (это тесты)."""
    from zoneinfo import ZoneInfo
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    import content_app as ca
    движок = create_engine("sqlite:///" + база.replace("\\", "/"))
    db = sessionmaker(bind=движок)()
    try:
        сюжеты = ca._сюжеты(db, "gta", ZoneInfo("UTC"))
        форматы = ca._форматы(db, "gta", ZoneInfo("UTC"))
    finally:
        db.close()
        движок.dispose()
    return {"сюжеты": {str(с["id"]): {"источников": с["источников"], "утечка": bool(с["leak"])}
                       for с in сюжеты},
            "хитов": len(форматы["строки"]),
            "огр": sum(1 for в in форматы["строки"] if в["limited"])}


def замер(база, подлог=None):
    from auth import create_token
    from playwright.sync_api import sync_playwright
    import check_v2_wide as ч67
    uid = _база(база, "SELECT id FROM users WHERE email = ?", ПОЧТА)
    if not uid:
        raise ConnectionError("на копии стенда нет аккаунта %s — посейте стенд" % ПОЧТА)
    ждём = _ожидание(база)
    п, адрес = _стенд(база)
    итог = []
    os.makedirs(КАДРЫ, exist_ok=True)
    try:
        with sync_playwright() as pw:
            бр = pw.chromium.launch(headless=False)
            for ширина, высота, касание in ШИРИНЫ:
                к = бр.new_context(viewport={"width": ширина, "height": высота},
                                   has_touch=касание, is_mobile=касание)
                к.add_cookies([{"name": "access_token", "value": create_token(uid[0][0]),
                                "url": адрес}])
                с = к.new_page()
                с.goto(адрес + "/content", wait_until="load", timeout=45000)
                if подлог and подлог.startswith("css:"):
                    с.add_style_tag(content=подлог[4:])
                if подлог == "вкладки":
                    с.evaluate(ПОДЛОГ_ВКЛАДОК)
                с.evaluate("() => document.fonts.ready")
                с.mouse.move(0, 0)
                снимки = {}
                for вкладка in ("stories", "formats", "sources"):
                    с.click("#content-tab-" + вкладка)
                    с.wait_for_timeout(250)
                    з = с.evaluate(ЗАМЕР_ЭКРАНА, ЗАМЕТКА)
                    з["строка"] = с.evaluate(ч67.ЗАМЕР_СТРОКИ, ч67.ПОТОЛОК_СТРОКИ)
                    з["прокрутка"] = с.evaluate(ч67.ЗАМЕР_ПРОКРУТКИ)
                    с.screenshot(path=os.path.join(КАДРЫ, "%d-%s.png" % (ширина, вкладка)),
                                 full_page=True)
                    снимки[вкладка] = з
                каналы = None
                if ширина == 1920 and not подлог:
                    каналы = _каналы(с, база)
                итог.append({"ширина": ширина, "вкладки": снимки, "каналы": каналы,
                             "ждём": ждём})
                к.close()
            бр.close()
    finally:
        п.kill()
    return итог


def _каналы(с, база):
    """«Убрать» и «Оставить» — по-настоящему нажатием, результат ИЗ БАЗЫ."""
    строка = _база(база, "SELECT id FROM content_channels WHERE status = 'candidate' "
                         "ORDER BY id LIMIT 1")
    if not строка:
        return {"собрано": 0}
    cid = строка[0][0]
    ряд = "#content-channels tr[data-channel='%d']" % cid
    итог = {"собрано": 1, "id": cid}
    for действие, ждём, слово in (("removed", "removed", "убран"), ("keep", "keep", "оставлен")):
        с.click(ряд + " [data-channel-set='%s']" % действие)
        с.wait_for_function("(с) => document.querySelector(с).dataset.status === %r" % ждём,
                            arg=ряд, timeout=10000)
        итог[действие] = {
            "база": _база(база, "SELECT status FROM content_channels WHERE id = ?", cid)[0][0],
            "слово": с.inner_text(ряд + " .content-status-word").strip(),
            "ждём": (ждём, слово)}
    return итог


def оценить(замеры):
    for з in замеры:
        ш = з["ширина"]
        сюж, форм, ист = з["вкладки"]["stories"], з["вкладки"]["formats"], з["вкладки"]["sources"]
        for имя, снимок in з["вкладки"].items():
            видно = [в for в, да in снимок["разделы"].items() if да]
            шаг("%d/вкладка %s" % (ш, имя), видно == [имя] and снимок["активные"] == [имя]
                and ("tab=" + имя) in снимок["адрес"],
                "видно %s, активна %s, адрес %s" % (видно, снимок["активные"], снимок["адрес"]))
            шаг("%d/шире окна %s" % (ш, имя),
                not снимок["шире"] and снимок["прокрутка"]["док"] <= 1
                and снимок["прокрутка"]["тело"] <= 1,
                "за краем %s, прокрутка вбок %s" % (снимок["шире"][:3] or "нет",
                                                   снимок["прокрутка"]))
            худший = снимок["строка"]["худший"]
            шаг("%d/строка %s" % (ш, имя), худший["знаков"] <= снимок["строка"]["потолок"],
                "самая длинная строка %d знаков (%s), узлов текста %d"
                % (худший["знаков"], худший["кто"], снимок["строка"]["узлов"]),
                собрано=снимок["строка"]["узлов"])
        сюжеты = сюж["сюжеты"]
        ждём = з["ждём"]["сюжеты"]
        на_экране = {с["id"] for с in сюжеты}
        шаг("%d/сюжеты из базы" % ш, на_экране == set(ждём),
            "на экране %d, отбор сервера %d, лишних %d, потерянных %d"
            % (len(на_экране), len(ждём), len(на_экране - set(ждём)), len(set(ждём) - на_экране)),
            собрано=len(ждём))
        с_утечкой = [с for с in сюжеты if ждём.get(с["id"], {}).get("утечка")]
        шаг("%d/сюжеты/утечка" % ш, all(с["заметка"] for с in с_утечкой),
            "сюжетов с утечкой в базе %d, с видимой заметкой на экране %d"
            % (len(с_утечкой), sum(1 for с in с_утечкой if с["заметка"])), собрано=len(с_утечкой))
        врут = [с["id"] for с in сюжеты
                if с["в_карточке"] != ждём.get(с["id"], {}).get("источников")]
        шаг("%d/сюжеты/источники" % ш, not врут,
            "число источников в карточке расходится с базой у %d: %s" % (len(врут), врут[:5]),
            собрано=len(сюжеты))
        красные = [и for и in ист["источники"] if и["тон"] == "danger"]
        шаг("%d/источники/ошибка" % ш, all(и["ошибка"] for и in красные),
            "красных %d, с видимым текстом ошибки %d"
            % (len(красные), sum(1 for и in красные if и["ошибка"])), собрано=len(красные))
        шаг("%d/источники/строка" % ш, all(и["строка"] for и in ист["источники"]),
            "источников %d" % len(ист["источники"]), собрано=len(ист["источники"]))
        хиты = з["ждём"]
        шаг("%d/форматы/хиты" % ш, форм["хитов"] == хиты["хитов"] and форм["огр"] == хиты["огр"],
            "строк археологии %d из %d, «Ограниченная» %d из %d"
            % (форм["хитов"], хиты["хитов"], форм["огр"], хиты["огр"]), собрано=хиты["хитов"])
        к = з["каналы"]
        if к is not None:
            есть = к.get("собрано", 0)
            шаг("%d/каналы/убрать" % ш, есть and к["removed"]["база"] == "removed"
                and к["removed"]["слово"] == "убран",
                "в базе %s, на экране %s" % (к.get("removed", {}).get("база"),
                                             к.get("removed", {}).get("слово")), собрано=есть)
            шаг("%d/каналы/оставить" % ш, есть and к["keep"]["база"] == "keep"
                and к["keep"]["слово"] == "оставлен",
                "в базе %s, на экране %s" % (к.get("keep", {}).get("база"),
                                             к.get("keep", {}).get("слово")), собрано=есть)


def _с_утечкой(з):
    return [с for x in з for с in x["вкладки"]["stories"]["сюжеты"] if с["утечка"]]


def _красные(з):
    return [и for x in з for и in x["вкладки"]["sources"]["источники"] if и["тон"] == "danger"]


# ДОКАЗАТЕЛЬСТВО ПОДЛОГА — независимый замер того, что подлог собирался
# изменить (§6.0.3), и НЕ ПУСТОЙ: на пустом списке `all` истинно само,
# и «заметок не видно» читалось бы как «подлог сработал» про страницу,
# где сюжета с утечкой нет вовсе.
ДОКАЗАТЕЛЬСТВА = {
    "утечка": lambda з: bool(_с_утечкой(з)) and not any(с["заметка"] for с in _с_утечкой(з)),
    "ошибка": lambda з: bool(_красные(з)) and not any(и["ошибка"] for и in _красные(з)),
    "вкладки": lambda з: bool(з) and not any(x["вкладки"]["formats"]["разделы"].get("formats")
                                             for x in з),
}
ПОДЛОГИ = {"утечка": ("css:" + ПОДЛОГ_УТЕЧКИ, "сюжеты/утечка"),
           "ошибка": ("css:" + ПОДЛОГ_ОШИБКИ, "источники/ошибка"),
           "вкладки": ("вкладки", "вкладка formats")}


def main_():
    база, каталог = _копия()
    try:
        if "--контроль" in sys.argv:
            ловит = 0
            for имя, (подлог, звено) in ПОДЛОГИ.items():
                шаги.clear()
                print("ПОДЛОГ «%s»" % имя)
                з = замер(база, подлог)
                оценить(з)
                док = ДОКАЗАТЕЛЬСТВА[имя](з)
                упал = any(звено in и and исход == "ПЛОХО" for и, исход, _ in шаги)
                print("  доказательство %s; шаг «%s» упал: %s" % (док, звено, упал))
                ловит += int(док and упал)
            print("КОНТРОЛЬ: ловит %d из %d" % (ловит, len(ПОДЛОГИ)))
            return 0 if ловит == len(ПОДЛОГИ) else 1
        з = замер(база)
        оценить(з)
        if not шаги:
            # Ни одного шага — замер не состоялся; ноль шагов не равен
            # «плохих ноль» (§6.0.1, класс проверки 33)
            print("ЗАМЕР НЕ СОСТОЯЛСЯ: шагов 0")
            return 2
        плохо = [ш for ш in шаги if ш[1] == "ПЛОХО"]
        пропуск = [ш for ш in шаги if ш[1] == "ПРОПУСК"]
        print("ИТОГ: шагов %d, плохих %d, пропусков %d · кадры: %s"
              % (len(шаги), len(плохо), len(пропуск), КАДРЫ))
        if плохо:
            return 1
        return 2 if пропуск else 0
    finally:
        shutil.rmtree(каталог, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main_())
