"""СБОРЩИКИ МОДУЛЯ «КОНТЕНТ» (BACKLOG №365): по одному на вид источника.

СЕТЬ — ЗДЕСЬ, БАЗЫ НЕТ ВОВСЕ. Сборщик получает клиента и описание
источника и возвращает записи; пишет их `content_engine` отдельной
короткой транзакцией. Соединение к базе поэтому не держится на время
похода в сеть (проверка 27, §6.0.5) по построению, а не по памяти.
Единственное исключение — учёт квоты YouTube: он пишется ДО каждого
вызова через `Квота.списать`, и эта функция открывает СВОЮ короткую
сессию, а не держит чужую.

ОТКАЗ — ИСКЛЮЧЕНИЕМ С ТЕКСТОМ ДЛЯ ЧЕЛОВЕКА (`ОтказИсточника`), а не пустым
списком. Пустой список — законный ответ «нового нет», и свести в него
отказ значило бы получить источник, который молчит зелёным (§6.0.1).

ЧУЖОЙ САЙТ ОТКАЗАЛ (403, 429, 451, капча) — СТОП И ОТЧЁТ. Ответ
становится ошибкой источника с кодом; повторов, смены адреса и прочих
обходов нет. `robots.txt` спрашивается перед обращением к САЙТУ (не к API
с ключом) и кешируется на сутки: запрет — ошибка источника, а не тихий
пропуск.

ЧТО ЗАМЕРЕНО 2026-09-29 С МАШИНЫ ПРОДА (Fly, Франкфурт):
  · Reddit: robots.txt — `User-agent: *` / `Disallow: /`; ленты
    `/r/GTA6/new.json` и `hot.json` — HTTP 403. Сборщика у Reddit нет:
    источник красный с причиной, в сеть мы не ходим вовсе.
  · Rockstar Newswire: RSS и карты сайта нет (404), страница — пустая
    оболочка приложения. Новости отдаёт открытый GraphQL
    `graph.rockstargames.com` — ту же точку зовёт сам сайт (запрос взят
    у RSSHub). robots.txt у этого хоста нет (404), у сайта закрыты только
    поимённые ИИ-краулеры. 200 за 0.4 с, 20 новостей.
  · PlayStation Blog: RSS `/feed/` — 200; robots.txt закрывает `/tag/`
    и `/category/`, ленту — нет.
"""
import asyncio
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup

UA = "energydess-content-radar/1.0 (+https://energydess.ru)"
ТЕЛО_МАКС = 5 * 1024 * 1024          # больше — не лента, а что-то другое
ТЕКСТ_ЗНАКОВ = 1000                  # отрывок записи в базе
РОБОТС_СЕК = 86400                   # robots.txt спрашивается раз в сутки на хост
_РОБОТС: dict = {}                   # хост -> (monotonic, RobotFileParser)


class ОтказИсточника(Exception):
    """Источник не отработал. Текст — для человека, его покажет страница."""

    def __init__(self, текст: str, блок: bool = False):
        super().__init__(текст)
        self.блок = блок             # чужой сайт отказал по правам или частоте


class КвотаИсчерпана(ОтказИсточника):
    """Следующий вызов YouTube вышел бы за суточный потолок."""


# ── ОБЩЕЕ ────────────────────────────────────────────────────────────

def _граница(шаблон: str) -> str:
    return r"(?<![0-9a-zа-яё])" + шаблон + r"(?![0-9a-zа-яё])"


def шаблон_ключевых(ключевые) -> re.Pattern | None:
    """Регулярка по ключевым словам темы: регистр не важен, слова внутри
    ключевого разделяются пробелом, дефисом либо ничем («GTA6» = «GTA 6»),
    а по краям — граница слова: «GTA V» не ловит «GTA VI», «GTA 5» —
    «GTA 50». Пустой список — None (фильтровать нечем)."""
    части = []
    for к in ключевые or []:
        слова = [re.escape(с) for с in str(к).lower().split() if с]
        if слова:
            части.append(_граница(r"[\s\-]*".join(слова)))
    if not части:
        return None
    return re.compile("|".join(части), re.IGNORECASE)


def совпало(текст: str, шаблон) -> bool:
    return bool(шаблон and шаблон.search((текст or "").lower()))


def есть_кириллица(текст: str) -> bool:
    return bool(re.search(r"[а-яё]", (текст or "").lower()))


def чистый_текст(разметка: str, знаков: int = ТЕКСТ_ЗНАКОВ) -> str:
    """HTML описания в текст без тегов, пробелы схлопнуты, длина ограничена."""
    if not разметка:
        return ""
    текст = BeautifulSoup(разметка, "html.parser").get_text(" ")
    return " ".join(текст.split())[:знаков]


def _utc(момент: datetime) -> datetime:
    """Момент с поясом -> UTC без пояса (так хранит весь проект)."""
    if момент.tzinfo is None:
        return момент
    return момент.astimezone(timezone.utc).replace(tzinfo=None)


def _iso(строка: str | None) -> datetime | None:
    if not строка:
        return None
    try:
        return _utc(datetime.fromisoformat(строка.replace("Z", "+00:00")))
    except ValueError:
        return None


def _отказ_по_ответу(r, где: str) -> ОтказИсточника:
    код = r.status_code
    начало = (r.text or "")[:3000].lower() if код >= 400 else ""
    if код in (401, 403, 429, 451) or "captcha" in начало:
        return ОтказИсточника(
            f"{где}: сайт отказал (HTTP {код}) — сбор этого источника остановлен, "
            "обходов не делаем", блок=True)
    return ОтказИсточника(f"{где}: HTTP {код}")


def _проверить_тело(r, где: str) -> None:
    if len(r.content) > ТЕЛО_МАКС:
        raise ОтказИсточника(f"{где}: ответ {len(r.content) // 1024} КБ — больше потолка "
                             f"{ТЕЛО_МАКС // 1024 // 1024} МБ, разбирать не стали")


async def robots_разрешает(client, url: str) -> None:
    """Спросить robots.txt сайта. Запрет — `ОтказИсточника`; файла нет
    (4xx) — ограничений нет; сайт не ответил (5xx, сеть) — тоже отказ:
    не зная правил, к сайту не ходим. Раз в сутки на хост."""
    части = urlsplit(url)
    хост = f"{части.scheme}://{части.netloc}"
    сейчас = time.monotonic()
    запись = _РОБОТС.get(хост)
    if запись is None or сейчас - запись[0] > РОБОТС_СЕК:
        try:
            r = await client.get(хост + "/robots.txt")
        except httpx.HTTPError as e:
            raise ОтказИсточника(f"robots.txt {части.netloc} не получен ({type(e).__name__}) — "
                                 "не зная правил сайта, к нему не обращаемся")
        разбор = RobotFileParser()
        if r.status_code in (401, 403):
            разбор.disallow_all = True
        elif 400 <= r.status_code < 500:
            разбор.allow_all = True
        elif r.status_code >= 500:
            raise ОтказИсточника(f"robots.txt {части.netloc}: HTTP {r.status_code} — "
                                 "не зная правил сайта, к нему не обращаемся")
        else:
            разбор.parse((r.text or "").splitlines())
        разбор.modified()
        _РОБОТС[хост] = (сейчас, разбор)
        запись = _РОБОТС[хост]
    if not запись[1].can_fetch(UA, url):
        raise ОтказИсточника(f"robots.txt {части.netloc} запрещает {части.path or '/'} "
                             "для автоматического доступа — не обращаемся", блок=True)


def новый_клиент() -> httpx.AsyncClient:
    """Один клиент на прогон: keep-alive, чтобы не платить рукопожатием TLS
    за каждый запрос — на одном vCPU прода оно стоит секунды (§5.8)."""
    return httpx.AsyncClient(headers={"User-Agent": UA}, follow_redirects=True,
                             timeout=httpx.Timeout(30.0, connect=15.0))


# ── ROCKSTAR NEWSWIRE ─────────────────────────────────────────────────

ROCKSTAR_ЗАПРОС = """query NewswireList($locale: String!, $page: Int!, $limit: Int, $metaUrl: String!) {
  meta: metaUrl(url: $metaUrl, domain: "www", locale: $locale) { title }
  posts(page: $page, locale: $locale, limit: $limit) { results { ...postFields } }
}
fragment postFields on RockstarGames_Newswire_Model_Entity_Post_o {
  id: id_hash
  url
  title
  created
  primary_tags { name }
  secondary_tags { name }
}"""
ROCKSTAR_ПОЯС = ZoneInfo("America/New_York")   # время новостей — нью-йоркское


def _rockstar_время(строка: str | None) -> datetime | None:
    """«9/24/26, 11:00 AM» по Нью-Йорку -> UTC."""
    if not строка:
        return None
    try:
        местн = datetime.strptime(строка.strip(), "%m/%d/%y, %I:%M %p")
    except ValueError:
        return None
    return _utc(местн.replace(tzinfo=ROCKSTAR_ПОЯС))


async def собрать_rockstar(client, источник: dict) -> list[dict]:
    п = источник["params"]
    сайт = (п.get("site") or "https://www.rockstargames.com").rstrip("/")
    await robots_разрешает(client, источник["url"])
    try:
        r = await client.post(источник["url"], json={
            "query": ROCKSTAR_ЗАПРОС,
            "variables": {"locale": п.get("locale", "en_us"), "page": 1,
                          "limit": int(п.get("limit", 20)), "metaUrl": "/newswire"}})
    except httpx.HTTPError as e:
        raise ОтказИсточника(f"Rockstar не ответил ({type(e).__name__})")
    if r.status_code != 200:
        raise _отказ_по_ответу(r, "Rockstar")
    _проверить_тело(r, "Rockstar")
    try:
        тело = r.json()
    except ValueError:
        raise ОтказИсточника("Rockstar ответил не JSON — похоже, точка API сменилась")
    if isinstance(тело, dict) and тело.get("errors"):
        ошибки = "; ".join(str(о.get("message", "?")) for о in тело["errors"][:3]
                           if isinstance(о, dict))
        raise ОтказИсточника(f"Rockstar: GraphQL отказал — {ошибки[:300]}")
    посты = (((тело or {}).get("data") or {}).get("posts") or {}).get("results")
    if not isinstance(посты, list):
        raise ОтказИсточника("Rockstar: в ответе нет списка новостей (data.posts.results)")
    итог = []
    for пост in посты:
        if not isinstance(пост, dict) or not пост.get("id") or not пост.get("title"):
            continue
        теги = [т.get("name") for т in (пост.get("primary_tags") or []) + (пост.get("secondary_tags") or [])
                if isinstance(т, dict) and т.get("name")]
        итог.append({
            "ext_id": "rockstar:" + str(пост["id"]),
            "url": сайт + str(пост.get("url") or "/newswire"),
            "title": " ".join(str(пост["title"]).split())[:300],
            "text": ("Теги: " + ", ".join(теги)) if теги else "",
            "published_at": _rockstar_время(пост.get("created")),
            "lang": "en", "platform": "rockstar",
            "для_фильтра": " ".join([str(пост["title"])] + теги),
        })
    return итог


# ── RSS (PlayStation Blog и любые другие ленты) ───────────────────────

_АТОМ = "{http://www.w3.org/2005/Atom}"


def _rss_время(строка: str | None) -> datetime | None:
    if not строка:
        return None
    try:
        return _utc(parsedate_to_datetime(строка.strip()))
    except (TypeError, ValueError, IndexError):
        return _iso(строка.strip())


async def собрать_rss(client, источник: dict) -> list[dict]:
    адрес = источник["url"]
    await robots_разрешает(client, адрес)
    try:
        r = await client.get(адрес)
    except httpx.HTTPError as e:
        raise ОтказИсточника(f"{источник['name']} не ответил ({type(e).__name__})")
    if r.status_code != 200:
        raise _отказ_по_ответу(r, источник["name"])
    _проверить_тело(r, источник["name"])
    try:
        корень = ET.fromstring(r.content)
    except ET.ParseError as e:
        raise ОтказИсточника(f"{источник['name']}: лента не разобралась как XML ({e})")
    площадка = источник["params"].get("platform") or urlsplit(адрес).netloc
    итог = []
    элементы = корень.findall("./channel/item")
    атом = not элементы
    if атом:
        элементы = корень.findall(f"{_АТОМ}entry")
    if not элементы and корень.tag not in ("rss", f"{_АТОМ}feed"):
        raise ОтказИсточника(f"{источник['name']}: это не RSS и не Atom (корень <{корень.tag}>)")
    for э in элементы:
        if атом:
            заголовок = (э.findtext(f"{_АТОМ}title") or "").strip()
            ссылка_узел = э.find(f"{_АТОМ}link")
            ссылка = (ссылка_узел.get("href") if ссылка_узел is not None else "") or ""
            метка = (э.findtext(f"{_АТОМ}id") or ссылка).strip()
            когда = _iso((э.findtext(f"{_АТОМ}published") or э.findtext(f"{_АТОМ}updated") or "").strip())
            описание = э.findtext(f"{_АТОМ}summary") or ""
            рубрики = [к.get("term") for к in э.findall(f"{_АТОМ}category") if к.get("term")]
        else:
            заголовок = (э.findtext("title") or "").strip()
            ссылка = (э.findtext("link") or "").strip()
            метка = (э.findtext("guid") or ссылка).strip()
            когда = _rss_время(э.findtext("pubDate"))
            описание = э.findtext("description") or ""
            рубрики = [(к.text or "").strip() for к in э.findall("category") if (к.text or "").strip()]
        if not заголовок or not ссылка:
            continue
        текст = чистый_текст(описание)
        итог.append({
            "ext_id": f"rss:{метка}"[:500],
            "url": ссылка[:1000],
            "title": " ".join(заголовок.split())[:300],
            "text": текст,
            "published_at": когда,
            "lang": "ru" if есть_кириллица(заголовок) else "en",
            "platform": площадка,
            "для_фильтра": " ".join([заголовок, текст] + рубрики),
        })
    return итог


# ── REDDIT ────────────────────────────────────────────────────────────

REDDIT_ОСТАНОВЛЕН = (
    "Остановлен: robots.txt reddit.com запрещает автоматический доступ всем "
    "(User-agent: * — Disallow: /), а открытые ленты /r/<sub>/new.json и hot.json "
    "с сервера Fly отвечают HTTP 403 (замер 2026-09-29). Обходов не делаем. "
    "Нужен одобренный доступ к Reddit Data API — см. BACKLOG №365.")


async def собрать_reddit(client, источник: dict) -> list[dict]:
    """В СЕТЬ НЕ ХОДИТ ВОВСЕ: обращаться к сайту, чей robots.txt запрещает
    всё, мы не вправе, а ключа API нет. Каждый цикл источник красный
    с причиной — молчащий серый был бы немым отказом."""
    raise ОтказИсточника(REDDIT_ОСТАНОВЛЕН, блок=True)


# ── YOUTUBE DATA API ─────────────────────────────────────────────────

ЦЕНА_ПОИСКА = 100                      # search.list — 100 единиц
ЦЕНА_СПИСКА = 1                        # channels / playlistItems / videos.list — 1


class Квота:
    """Потолок единиц YouTube на ПРОГОН, выведенный из суточного.

    `списать(метод, единиц)` пишет расход в базу ДО вызова — своей короткой
    сессией. Следующий вызов вышел бы за потолок — `КвотаИсчерпана`,
    а не вызов «на удачу»: отказ Google посреди прогона оставил бы половину
    работы несделанной и квоту потраченной."""

    def __init__(self, осталось: int, списать):
        self.осталось = max(0, int(осталось))
        self.потрачено = 0
        self._списать = списать

    def взять(self, метод: str, единиц: int) -> None:
        if единиц > self.осталось:
            raise КвотаИсчерпана(
                f"квота YouTube на сегодня исчерпана: осталось {self.осталось} ед., "
                f"а {метод} стоит {единиц} — продолжим после полуночи по Лос-Анджелесу")
        self._списать(метод, единиц)
        self.осталось -= единиц
        self.потрачено += единиц


def _yt_причина(r) -> str:
    try:
        ошибка = (r.json() or {}).get("error") or {}
        причины = [о.get("reason") for о in ошибка.get("errors") or [] if isinstance(о, dict)]
        return ", ".join(п for п in причины if п) or str(ошибка.get("message") or "")[:120]
    except ValueError:
        return ""


async def _yt(client, база: str, путь: str, параметры: dict, ключ: str, квота: Квота,
              цена: int) -> dict:
    квота.взять(путь, цена)
    try:
        r = await client.get(f"{база.rstrip('/')}/{путь}", params={**параметры, "key": ключ})
    except httpx.HTTPError as e:
        raise ОтказИсточника(f"YouTube {путь} не ответил ({type(e).__name__})")
    if r.status_code != 200:
        причина = _yt_причина(r)
        if "quota" in причина.lower():
            raise КвотаИсчерпана(f"YouTube {путь}: Google сообщил об исчерпанной квоте ({причина})")
        raise ОтказИсточника(f"YouTube {путь}: HTTP {r.status_code}"
                             + (f" ({причина})" if причина else ""),
                             блок=r.status_code in (403, 429))
    try:
        тело = r.json()
    except ValueError:
        raise ОтказИсточника(f"YouTube {путь} ответил не JSON")
    if not isinstance(тело, dict):
        raise ОтказИсточника(f"YouTube {путь} ответил не объектом")
    return тело


def _число(x) -> int | None:
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


def _сведения_канала(э: dict) -> dict:
    с = э.get("snippet") or {}
    ст = э.get("statistics") or {}
    return {
        "yt_id": э.get("id"),
        "title": " ".join(str(с.get("title") or "").split())[:200] or э.get("id"),
        "handle": (с.get("customUrl") or None),
        "country": с.get("country"),
        "description": str(с.get("description") or "")[:600],
        "default_lang": (с.get("defaultLanguage") or "")[:5].lower() or None,
        "subscribers": None if ст.get("hiddenSubscriberCount") else _число(ст.get("subscriberCount")),
        "videos": _число(ст.get("videoCount")),
        "views": _число(ст.get("viewCount")),
        "created_yt": _iso(с.get("publishedAt")),
        "uploads": ((э.get("contentDetails") or {}).get("relatedPlaylists") or {}).get("uploads"),
    }


async def каналы_сведения(client, база, ключ, квота, ids: list[str]) -> dict:
    """{yt_id: сведения} — channels.list пачками по 50 (1 ед. на пачку)."""
    итог = {}
    for i in range(0, len(ids), 50):
        пачка = ids[i:i + 50]
        тело = await _yt(client, база, "channels", {
            "part": "snippet,statistics,contentDetails", "id": ",".join(пачка),
            "maxResults": 50}, ключ, квота, ЦЕНА_СПИСКА)
        for э in тело.get("items") or []:
            if isinstance(э, dict) and э.get("id"):
                итог[э["id"]] = _сведения_канала(э)
    return итог


def _ролик(э: dict) -> dict:
    с = э.get("snippet") or {}
    ст = э.get("statistics") or {}
    return {
        "yt_id": э.get("id"),
        "title": " ".join(str(с.get("title") or "").split())[:300],
        "description": str(с.get("description") or ""),
        "channel_yt_id": с.get("channelId"),
        "channel_title": " ".join(str(с.get("channelTitle") or "").split())[:200],
        "published_at": _iso(с.get("publishedAt")),
        "lang": (с.get("defaultAudioLanguage") or с.get("defaultLanguage") or "")[:2].lower() or None,
        "views": _число(ст.get("viewCount")),
        "likes": _число(ст.get("likeCount")),
        "comments": _число(ст.get("commentCount")),
        "tags": [str(т) for т in (с.get("tags") or [])][:20],
    }


async def ролики_сведения(client, база, ключ, квота, ids: list[str]) -> dict:
    """{yt_id: ролик} — videos.list пачками по 50 (1 ед. на пачку)."""
    итог = {}
    for i in range(0, len(ids), 50):
        пачка = ids[i:i + 50]
        тело = await _yt(client, база, "videos", {
            "part": "snippet,statistics", "id": ",".join(пачка), "maxResults": 50},
            ключ, квота, ЦЕНА_СПИСКА)
        for э in тело.get("items") or []:
            if isinstance(э, dict) and э.get("id"):
                итог[э["id"]] = _ролик(э)
    return итог


async def загрузки_канала(client, база, ключ, квота, плейлист: str, штук: int) -> list[str]:
    """Последние ролики канала через плейлист загрузок (1 ед.)."""
    тело = await _yt(client, база, "playlistItems", {
        "part": "contentDetails", "playlistId": плейлист,
        "maxResults": max(1, min(50, штук))}, ключ, квота, ЦЕНА_СПИСКА)
    return [э["contentDetails"]["videoId"] for э in тело.get("items") or []
            if isinstance(э, dict) and (э.get("contentDetails") or {}).get("videoId")]


def язык_канала(сведения: dict, подсказка: str | None) -> str:
    """ru | en: кириллица в названии либо описании сильнее подсказки запроса."""
    if есть_кириллица(сведения.get("title", "")) or есть_кириллица(сведения.get("description", "")):
        return "ru"
    if сведения.get("default_lang") in ("ru", "uk", "be", "kk"):
        return "ru"
    if сведения.get("default_lang", "") and сведения["default_lang"].startswith("en"):
        return "en"
    return подсказка or "en"


async def найти_каналы(client, база, ключ, квота, запросы: list[dict], метки,
                       мин_подписчиков: int, максимум: int) -> list[dict]:
    """Поиск каналов по запросам темы (100 ед. на запрос) плюс сведения
    (1 ед. на 50). Остаются каналы, в названии или описании которых есть
    метка темы, и не меньше `мин_подписчиков`; самые крупные — первыми."""
    найдено: dict[str, dict] = {}
    for з in запросы:
        параметры = {"part": "snippet", "type": "channel", "q": з["q"], "maxResults": 50}
        if з.get("lang"):
            параметры["relevanceLanguage"] = з["lang"]
        if з.get("lang") == "ru":
            параметры["regionCode"] = "RU"
        тело = await _yt(client, база, "search", параметры, ключ, квота, ЦЕНА_ПОИСКА)
        for э in тело.get("items") or []:
            cid = ((э.get("id") or {}).get("channelId") if isinstance(э, dict) else None)
            if cid and cid not in найдено:
                найдено[cid] = {"подсказка": з.get("lang"), "запрос": з["q"]}
    сведения = await каналы_сведения(client, база, ключ, квота, list(найдено))
    итог = []
    for cid, св in сведения.items():
        if not совпало(св["title"] + " " + св["description"], метки):
            continue
        if (св["subscribers"] or 0) < мин_подписчиков:
            continue
        св["lang"] = язык_канала(св, найдено[cid]["подсказка"])
        св["found_by"] = "поиск: " + найдено[cid]["запрос"]
        итог.append(св)
    итог.sort(key=lambda к: -(к["subscribers"] or 0))
    return итог[:максимум]


def _rfc3339(дата: str, конец: bool = False) -> str:
    д = datetime.fromisoformat(дата)
    if конец:
        д = д + timedelta(days=1)
    return д.strftime("%Y-%m-%dT00:00:00Z")


async def хиты_периода(client, база, ключ, квота, параметры: dict, метки=None) -> dict:
    """АРХЕОЛОГИЯ: самые просматриваемые ролики ПРО ТЕМУ периода запуска GTA 5.

    1. Поиск роликов периода по запросам, по просмотрам (100 ед. на запрос):
       отсюда — каналы, которые снимали эту тему ТОГДА (в том числе
       существовавшие в 2013–2014 по построению).
    2. Сведения хитов (1 ед. на 50) — просмотры сейчас.
    3. Каналы ранжируются суммой просмотров своих хитов ПО ТЕМЕ; берутся
       `channels_en` англоязычных и `channels_ru` русскоязычных.
    4. У каждого канала — его ролики того же периода ПО ЗАПРОСУ ТЕМЫ
       (`channel_q`, по умолчанию — запросы шага 1 через «|»), по просмотрам
       (100 ед. на канал), затем сведения (1 ед. на 50).

    ПРО ТЕМУ — ДВАЖДЫ, И ОБА ЗАМЕРЕНЫ НА ПРОДЕ 2026-09-29. Без запроса
    в шаге 4 топ канала периода — всё подряд: у Tauz рэп про Minecraft
    и Naruto, у Fernanfloo Five Nights at Freddy's и Goat Simulator
    (из 204 хитов первой археологии модель завела под них форматы «Кинематики
    и сюжеты других игр» — 37 и «Рэп и музыка про игры» — 34). Запрос
    сужает выдачу, а `метки` (маркеры темы по заголовку и описанию)
    отбрасывают то, что поиск всё же пропустил.

    ЯЗЫК КАНАЛА — ПО ТЕКСТУ, А НЕ ПО ПОДСКАЗКЕ ЗАПРОСА. Прежде ролик,
    найденный русским запросом, засчитывался русским: SquidPhysics
    и XpertThief (англоязычные) заняли места русских каналов."""
    с, по = _rfc3339(параметры["from"]), _rfc3339(параметры["to"], конец=True)
    по_теме = (lambda р: метки is None
               or совпало(f"{р.get('title') or ''} {р.get('description') or ''}", метки))
    запросы = [з["q"] for з in параметры.get("queries") or [] if з.get("q")]
    запрос_канала = параметры.get("channel_q") or "|".join(dict.fromkeys(запросы))
    кандидаты: dict[str, dict] = {}
    for з in параметры.get("queries") or []:
        п = {"part": "snippet", "type": "video", "q": з["q"], "maxResults": 50,
             "order": "viewCount", "publishedAfter": с, "publishedBefore": по}
        if з.get("lang"):
            п["relevanceLanguage"] = з["lang"]
        if з.get("lang") == "ru":
            п["regionCode"] = "RU"
        тело = await _yt(client, база, "search", п, ключ, квота, ЦЕНА_ПОИСКА)
        for э in тело.get("items") or []:
            vid = ((э.get("id") or {}).get("videoId") if isinstance(э, dict) else None)
            if vid and vid not in кандидаты:
                кандидаты[vid] = {"подсказка": з.get("lang")}
    хиты = {vid: р for vid, р in
            (await ролики_сведения(client, база, ключ, квота, list(кандидаты))).items()
            if по_теме(р)}
    по_каналам: dict[str, dict] = {}
    for vid, р in хиты.items():
        cid = р["channel_yt_id"]
        if not cid:
            continue
        к = по_каналам.setdefault(cid, {"просмотры": 0, "ru": 0, "всего": 0,
                                        "title": р["channel_title"]})
        к["просмотры"] += р["views"] or 0
        к["всего"] += 1
        if есть_кириллица(р["title"]):
            к["ru"] += 1
    ранжир = sorted(по_каналам.items(), key=lambda кв: -кв[1]["просмотры"])
    выбрано_en, выбрано_ru = [], []
    for cid, к in ранжир:
        ru = есть_кириллица(к["title"]) or к["ru"] * 2 > к["всего"]
        if ru and len(выбрано_ru) < int(параметры.get("channels_ru", 5)):
            выбрано_ru.append(cid)
        elif not ru and len(выбрано_en) < int(параметры.get("channels_en", 10)):
            выбрано_en.append(cid)
    ролики_ids: set[str] = set()
    for cid in выбрано_en + выбрано_ru:
        п = {"part": "snippet", "type": "video", "channelId": cid, "order": "viewCount",
             "publishedAfter": с, "publishedBefore": по,
             "maxResults": max(1, min(50, int(параметры.get("per_channel", 20))))}
        if запрос_канала:
            п["q"] = запрос_канала
        тело = await _yt(client, база, "search", п, ключ, квота, ЦЕНА_ПОИСКА)
        for э in тело.get("items") or []:
            vid = ((э.get("id") or {}).get("videoId") if isinstance(э, dict) else None)
            if vid:
                ролики_ids.add(vid)
    ролики = {vid: р for vid, р in
              (await ролики_сведения(client, база, ключ, квота, sorted(ролики_ids))).items()
              if по_теме(р)}
    языки = {cid: "ru" for cid in выбрано_ru}
    языки.update({cid: "en" for cid in выбрано_en})
    for р in ролики.values():
        р["channel_lang"] = языки.get(р["channel_yt_id"])
    return {"каналы_en": выбрано_en, "каналы_ru": выбрано_ru,
            "хитов_поиска": len(хиты), "ролики": list(ролики.values())}


async def с_потолком(корутина, секунд: float, что: str):
    """Потолок времени на весь сбор источника: запрос висит — источник
    красный с причиной, остальные идут дальше."""
    try:
        return await asyncio.wait_for(корутина, timeout=секунд)
    except asyncio.TimeoutError:
        raise ОтказИсточника(f"{что}: не уложился в {int(секунд)} с — прерван")
