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
import os
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


# ЛАТИНИЦА — ЕЩЁ НЕ АНГЛИЙСКИЙ. Замер археологии на проде 2026-09-29:
# в группу англоязычных попали Fernanfloo (испанский, семь хитов из
# первой десятки) и Tauz (португальский) — правило «нет кириллицы, значит
# en» отличало только русский. По ЗАГОЛОВКАМ их не отличить: у Fernanfloo
# половина названий с припиской «(Funny Moments)» и без единого служебного
# слова. Отличает ОПИСАНИЕ КАНАЛА, поэтому язык решается по нему вместе
# с заголовками. Слова взяты только такие, каких в английском нет:
# «no», «do», «a», «per», «em», «sus», «com» сюда не входят нарочно.
ЧУЖИЕ_СЛОВА = frozenset(
    "de la el los las en y con para por una un del al que mi su se "   # es
    "da dos das na um uma pra "                                        # pt
    "le les des du et pour avec sur une "                              # fr
    "der und mit ist ein eine auf nicht "                              # de
    "il di che gli".split())                                           # it
АНГЛ_СЛОВА = frozenset(
    "the and of to in with my on for is it how you we this that are be at "
    "by from your our what when why all new best first".split())
ДИАКРИТИКА = frozenset("áéíóúñãõçâêôàèìòùäöüßœ¿¡")
_ССЫЛКА = re.compile(r"https?://\S+|www\.\S+|\S+\.(?:com|net|org|tv|ru|me|gg|ly|io|br|es)\S*|@\S+")
# Страны, где английский — язык авторов по умолчанию. Страна канала
# решает, только когда текст признаков не дал (правило ниже).
АНГЛ_СТРАНЫ = frozenset("US GB CA AU NZ IE ZA IN PH SG MY NG JM".split())


def латиница_не_английская(текст: str, страна: str | None = None) -> bool:
    """Латинский текст на другом языке — испанском, португальском,
    французском, немецком, итальянском. Ссылки и упоминания снимаются
    до счёта: «youtube.com» дал бы португальское «com». Порог 3 и перевес
    над английскими словами — чтобы одно «Pokémon» в английском описании
    не переворачивало решение.

    КОРОТКОЕ ОПИСАНИЕ ПРИЗНАКОВ НЕ ДАЁТ, и это замер версии 3 на проде:
    у Tauz описание — «Canal do Tauz!», заголовки «Rap do GTA 5», чужих
    признаков один, и он остался в англоязычных. Тогда решает СТРАНА
    канала (у Tauz — BR): не англоязычная и ни одного английского слова
    в тексте — не английский. Англоязычный автор из Бразилии в тексте
    английские слова оставит, и его правило не тронет."""
    чисто = _ССЫЛКА.sub(" ", (текст or "").lower())
    слова = re.findall(r"[a-zà-öø-ÿœß]+", чисто)
    чужие = sum(1 for с in слова if с in ЧУЖИЕ_СЛОВА) + sum(1 for б in чисто if б in ДИАКРИТИКА)
    англ = sum(1 for с in слова if с in АНГЛ_СЛОВА)
    if чужие >= 3 and чужие > англ:
        return True
    return bool(страна) and страна.upper() not in АНГЛ_СТРАНЫ and англ == 0


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
            # СТРОГИЙ ФИЛЬТР СМИ (BACKLOG №367): только заголовок и рубрики —
            # в анонсе обзорной статьи GTA упоминается мимоходом
            "для_строгого": " ".join([заголовок] + рубрики),
        })
    return итог


# ── REDDIT ────────────────────────────────────────────────────────────

REDDIT_ОСТАНОВЛЕН = (
    "Остановлен: нет ключа Reddit Data API (секреты REDDIT_CLIENT_ID "
    "и REDDIT_CLIENT_SECRET). Открытый сайт не годится: robots.txt reddit.com "
    "запрещает автоматический доступ всем, а ленты /r/<sub>/new.json с Fly "
    "отвечают HTTP 403 (замер 2026-09-29). Обходов не делаем. Доступ к API "
    "выдаёт Reddit по заявке — см. BACKLOG №369.")

REDDIT_ТОКЕН_URL = os.getenv("REDDIT_TOKEN_URL", "https://www.reddit.com/api/v1/access_token")
REDDIT_API_URL = os.getenv("REDDIT_API_URL", "https://oauth.reddit.com")
_REDDIT_ТОКЕН: dict = {}                 # {"токен": str, "до": monotonic}


def reddit_ключи() -> tuple[str, str] | None:
    """Пара секретов либо None. Нет хотя бы одного — источник выключен
    и в сеть не ходит вовсе (BACKLOG №369)."""
    cid = (os.getenv("REDDIT_CLIENT_ID") or "").strip()
    сек = (os.getenv("REDDIT_CLIENT_SECRET") or "").strip()
    return (cid, сек) if cid and сек else None


def reddit_ua() -> str:
    """Правила Reddit требуют UA вида «платформа:приложение:версия (by /u/имя)»;
    безликий UA API режет. Имя — из REDDIT_USERNAME, если задано."""
    имя = (os.getenv("REDDIT_USERNAME") or "").strip()
    return "web:energydess-content-radar:v1.0" + (f" (by /u/{имя})" if имя else "")


async def _reddit_токен(client, ключи: tuple[str, str]) -> str:
    """Токен приложения (client_credentials, только чтение публичного).
    Живёт час — держим до истечения с запасом минута, не просим на каждый
    саб: лимит Reddit считается по запросам."""
    сейчас = time.monotonic()
    if _REDDIT_ТОКЕН.get("токен") and _REDDIT_ТОКЕН.get("до", 0) > сейчас:
        return _REDDIT_ТОКЕН["токен"]
    try:
        r = await client.post(REDDIT_ТОКЕН_URL, data={"grant_type": "client_credentials"},
                              auth=ключи, headers={"User-Agent": reddit_ua()})
    except httpx.HTTPError as e:
        raise ОтказИсточника(f"Reddit: выдача токена не ответила ({type(e).__name__})")
    if r.status_code != 200:
        raise ОтказИсточника(f"Reddit: токен не выдан, HTTP {r.status_code} — проверьте "
                             "REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET и одобрение заявки",
                             блок=r.status_code in (401, 403, 429))
    try:
        тело = r.json()
    except ValueError:
        raise ОтказИсточника("Reddit: выдача токена ответила не JSON")
    токен = (тело or {}).get("access_token") if isinstance(тело, dict) else None
    if not токен:
        raise ОтказИсточника("Reddit: в ответе нет access_token"
                             + (f" ({тело.get('error')})" if isinstance(тело, dict) and тело.get("error") else ""))
    _REDDIT_ТОКЕН.update(токен=токен, до=сейчас + max(60, int(тело.get("expires_in") or 3600) - 60))
    return токен


async def собрать_reddit(client, источник: dict) -> list[dict]:
    """REDDIT ЧЕРЕЗ ОФИЦИАЛЬНЫЙ DATA API (BACKLOG №369). Без секретов в сеть
    не ходит вовсе; с №370 движок до сборщика не доходит и ставит источнику
    «выключен, ждёт ключ» (серый, не ошибка), причина — в пометке источника. С секретами — токен приложения и /r/<sub>/new по OAuth
    на oauth.reddit.com; открытый сайт (robots.txt запрещает всё) не трогаем."""
    ключи = reddit_ключи()
    if not ключи:
        raise ОтказИсточника(REDDIT_ОСТАНОВЛЕН, блок=True)
    токен = await _reddit_токен(client, ключи)
    лимит = max(1, min(100, int(источник["params"].get("limit", 50))))
    итог = []
    for саб in источник["params"].get("subs") or []:
        try:
            r = await client.get(f"{REDDIT_API_URL.rstrip('/')}/r/{саб}/new",
                                 params={"limit": лимит, "raw_json": 1},
                                 headers={"Authorization": f"Bearer {токен}",
                                          "User-Agent": reddit_ua()})
        except httpx.HTTPError as e:
            raise ОтказИсточника(f"Reddit r/{саб} не ответил ({type(e).__name__})")
        if r.status_code == 401:
            _REDDIT_ТОКЕН.clear()
        if r.status_code != 200:
            raise _отказ_по_ответу(r, f"Reddit r/{саб}")
        try:
            дети = ((r.json() or {}).get("data") or {}).get("children") or []
        except ValueError:
            raise ОтказИсточника(f"Reddit r/{саб} ответил не JSON")
        for д in дети:
            п = (д or {}).get("data") or {}
            if not п.get("id") or not п.get("title"):
                continue
            текст = " ".join(str(п.get("selftext") or "").split())[:ТЕКСТ_ЗНАКОВ]
            когда = п.get("created_utc")
            итог.append({
                "ext_id": f"reddit:{п['id']}",
                "url": "https://www.reddit.com" + str(п.get("permalink") or ""),
                "title": " ".join(str(п["title"]).split())[:300],
                "text": текст,
                "published_at": (datetime.fromtimestamp(float(когда), timezone.utc).replace(tzinfo=None)
                                 if когда else None),
                "lang": "ru" if есть_кириллица(п["title"]) else "en",
                "platform": "reddit",
                "source_key": f"reddit:{саб}",
                "source_name": f"Reddit r/{саб}",
                "flair": (п.get("link_flair_text") or None),
                "metric": _число(п.get("score")),
                "comments": _число(п.get("num_comments")),
                "для_фильтра": " ".join([п["title"], текст]),
            })
    return итог


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


def медиана(числа: list) -> float | None:
    ряд = sorted(числа)
    if not ряд:
        return None
    с = len(ряд) // 2
    return float(ряд[с]) if len(ряд) % 2 else (ряд[с - 1] + ряд[с]) / 2.0


def выстрел(ролик: dict, соседи: list[dict], окно_дней: int = 90,
            мин_соседей: int = 5) -> tuple[float | None, int | None, int]:
    """ВЫСТРЕЛ (BACKLOG №368) = просмотры ролика / медиана просмотров роликов
    ТОГО ЖЕ канала, опубликованных за ±`окно_дней` вокруг него. Сам ролик
    в медиану не входит: иначе у канала с тремя роликами хит тянул бы свою же
    планку вверх. Соседей меньше `мин_соседей` либо медиана ноль — выстрела
    нет (None), и такой ролик не ранжируется: по двум роликам «обычный
    уровень канала» не выводится. Возврат: (выстрел, медиана, соседей)."""
    когда, просмотры = ролик.get("published_at"), ролик.get("views")
    if когда is None or просмотры is None:
        return None, None, 0
    окно = timedelta(days=окно_дней)
    база = [с["views"] for с in соседи
            if с.get("yt_id") != ролик.get("yt_id") and с.get("views") is not None
            and с.get("published_at") is not None and abs(с["published_at"] - когда) <= окно]
    if len(база) < мин_соседей:
        return None, None, len(база)
    м = медиана(база)
    if not м:
        return None, 0, len(база)
    return round(просмотры / м, 2), int(round(м)), len(база)


async def _отобрать_каналы(client, база, ключ, квота, параметры: dict, метки=None) -> dict:
    """Каналы, которые снимали тему В ПЕРИОД: поиск роликов периода по запросам
    (100 ед. на запрос), сведения хитов (1 ед. на 50), каналы — суммой
    просмотров своих хитов ПРО ТЕМУ; `channels_en` англоязычных
    и `channels_ru` русскоязычных.

    ПРО ТЕМУ — МАРКЕРЫ В ЗАГОЛОВКЕ (версия 3, замер на проде 2026-09-29:
    16 хитов из 158 держались за тему только описанием — Gmod, WATCH DOGS,
    Metro 2033). ЯЗЫК — ПО ТЕКСТУ (версия 2), И ЛАТИНИЦА — ЕЩЁ НЕ АНГЛИЙСКИЙ
    (версии 3–4): канал на другом языке в группы не идёт и называется
    в `другой_язык`; короткое описание — решает страна канала."""
    с, по = _rfc3339(параметры["from"]), _rfc3339(параметры["to"], конец=True)
    по_теме = (lambda р: метки is None or совпало(р.get("title") or "", метки))
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
                                        "title": р["channel_title"], "заголовки": []})
        к["просмотры"] += р["views"] or 0
        к["всего"] += 1
        к["заголовки"].append(р["title"] or "")
        if есть_кириллица(р["title"]):
            к["ru"] += 1
    ранжир = sorted(по_каналам.items(), key=lambda кв: -кв[1]["просмотры"])
    сведения = await каналы_сведения(client, база, ключ, квота, [cid for cid, _ in ранжир])
    выбрано_en, выбрано_ru, другой_язык = [], [], []
    for cid, к in ранжир:
        ru = есть_кириллица(к["title"]) or к["ru"] * 2 > к["всего"]
        св = сведения.get(cid) or {}
        язык_сведений = (св.get("default_lang") or "")[:2]
        if not ru and (язык_сведений not in ("", "en") or латиница_не_английская(
                " ".join([св.get("title") or к["title"], св.get("description") or "",
                          *к["заголовки"]]), св.get("country"))):
            другой_язык.append(к["title"])
            continue
        if ru and len(выбрано_ru) < int(параметры.get("channels_ru", 5)):
            выбрано_ru.append(cid)
        elif not ru and len(выбрано_en) < int(параметры.get("channels_en", 10)):
            выбрано_en.append(cid)
    return {"en": выбрано_en, "ru": выбрано_ru, "сведения": сведения, "хиты": хиты,
            "названия": {cid: к["title"] for cid, к in по_каналам.items()},
            "другой_язык": другой_язык}


async def окно_загрузок(client, база, ключ, квота, плейлист: str, с: datetime,
                        по: datetime, макс_страниц: int) -> tuple[list[str], int, bool]:
    """Ролики канала, опубликованные в [с, по), через ПЛЕЙЛИСТ ЗАГРУЗОК —
    1 единица на 50 роликов вместо 100 за поиск. Дата публикации лежит
    в `contentDetails.videoPublishedAt`, поэтому окно режется без
    `videos.list`. Плейлист идёт от новых к старым: страница, где ВСЕ
    ролики старше `с`, — конец. Возврат: (ids, страниц, дошли_до_начала)."""
    ids, страниц, токен = [], 0, None
    while страниц < макс_страниц:
        п = {"part": "contentDetails", "playlistId": плейлист, "maxResults": 50}
        if токен:
            п["pageToken"] = токен
        тело = await _yt(client, база, "playlistItems", п, ключ, квота, ЦЕНА_СПИСКА)
        страниц += 1
        элементы = [э for э in тело.get("items") or [] if isinstance(э, dict)]
        старше = 0
        for э in элементы:
            cd = э.get("contentDetails") or {}
            vid, когда = cd.get("videoId"), _iso(cd.get("videoPublishedAt"))
            if not vid or когда is None:
                continue
            if когда < с:
                старше += 1
            elif когда < по:
                ids.append(vid)
        токен = тело.get("nextPageToken")
        if not токен or (элементы and старше == len(элементы)):
            return ids, страниц, True
    return ids, страниц, False


def цена_выстрела(параметры: dict) -> int:
    """ПРОГНОЗ ЕДИНИЦ ПРОГОНА ДО ЗАПУСКА: поиск по запросам (100 за запрос),
    бюджет страниц плейлистов (1 за страницу) и запас на `channels.list`
    и `videos.list` роликов окна. Прогон сам не выйдет за бюджет страниц."""
    запросов = len(параметры.get("queries") or [])
    return запросов * ЦЕНА_ПОИСКА + int(параметры.get("page_budget", 1600)) + 200


async def хиты_выстрела(client, база, ключ, квота, параметры: dict, метки=None) -> dict:
    """АРХЕОЛОГИЯ ВЕРСИИ 5 (BACKLOG №368): хиты периода по ВЫСТРЕЛУ.

    Сырые просмотры ставили наверх большие каналы, а не удачные ролики:
    рядовой ролик канала на 10 млн подписчиков обгонял лучший ролик канала
    на 100 тысяч. Выстрел меряет ролик планкой ЕГО канала.

    1. Каналы периода — `_отобрать_каналы` (поиск — единственное место, где
       он нужен: иначе каналов 2013–2014 не узнать).
    2. У каждого канала — ВСЕ ролики за период ±окно через плейлист
       загрузок (1 ед. на 50) и `videos.list` (1 ед. на 50). Поиска по каналу
       нет: версия 4 тратила на это 100 ед. на канал и видела только топ.
    3. Хит — ролик ПРО ТЕМУ периода не ниже `min_views`; выстрел — по всем
       роликам канала в окне, любой темы: это и есть обычный уровень канала.

    Канал, у которого роликов на страниц больше `max_pages_per_channel`,
    либо не влезающий в остаток `page_budget`, пропускается СО СЛОВАМИ
    в `пропущено`, а не молча."""
    import content_worker as cw
    cw.ход("поиск каналов периода", 0, None, сразу=True)
    отбор = await _отобрать_каналы(client, база, ключ, квота, параметры, метки)
    всего_каналов = len(отбор["en"]) + len(отбор["ru"])
    пройдено = 0
    cw.ход("ролики каналов", 0, всего_каналов, сразу=True)
    по_теме = (lambda р: метки is None or совпало(р.get("title") or "", метки))
    окно = int(параметры.get("window_days", 90))
    мин_просмотров = int(параметры.get("min_views", 100000))
    мин_соседей = int(параметры.get("min_neighbors", 5))
    нач = datetime.fromisoformat(параметры["from"])
    кон = datetime.fromisoformat(параметры["to"]) + timedelta(days=1)
    потолок = int(параметры.get("max_pages_per_channel", 160))
    бюджет = int(параметры.get("page_budget", 1600))
    хиты, каналы, пропущено, страниц_всего = [], [], [], 0
    for язык, группа in (("en", отбор["en"]), ("ru", отбор["ru"])):
        for cid in группа:
            cw.ход("ролики каналов", пройдено, всего_каналов)
            пройдено += 1
            св = отбор["сведения"].get(cid) or {}
            название = св.get("title") or отбор["названия"].get(cid) or cid
            плейлист = св.get("uploads")
            страниц_оценка = max(1, -(-int(св.get("videos") or 0) // 50))
            if not плейлист:
                пропущено.append(f"{название}: нет плейлиста загрузок")
                continue
            if страниц_оценка > потолок:
                пропущено.append(f"{название}: роликов {св.get('videos')} — {страниц_оценка} "
                                 f"страниц плейлиста, больше потолка {потолок} на канал")
                continue
            if страниц_оценка > бюджет:
                пропущено.append(f"{название}: не влез в остаток бюджета страниц ({бюджет})")
                continue
            ids, страниц, дошли = await окно_загрузок(
                client, база, ключ, квота, плейлист, нач - timedelta(days=окно),
                кон + timedelta(days=окно), min(потолок, бюджет))
            бюджет -= страниц
            страниц_всего += страниц
            ролики = list((await ролики_сведения(client, база, ключ, квота, ids)).values())
            n = 0
            for р in ролики:
                когда = р.get("published_at")
                if (когда is None or not (нач <= когда < кон) or not по_теме(р)
                        or (р.get("views") or 0) < мин_просмотров):
                    continue
                р["shot"], р["channel_median"], р["median_base"] = выстрел(
                    р, ролики, окно, мин_соседей)
                р["channel_lang"] = язык
                хиты.append(р)
                n += 1
            каналы.append({"канал": название, "язык": язык, "страниц": страниц,
                           "роликов_окна": len(ролики), "хитов": n, "дошли": дошли})
    return {"каналы_en": отбор["en"], "каналы_ru": отбор["ru"],
            "хитов_поиска": len(отбор["хиты"]), "ролики": хиты,
            "другой_язык": отбор["другой_язык"][:20], "каналы": каналы,
            "пропущено": пропущено, "страниц": страниц_всего}


async def с_потолком(корутина, секунд: float, что: str):
    """Потолок времени на весь сбор источника: запрос висит — источник
    красный с причиной, остальные идут дальше."""
    try:
        return await asyncio.wait_for(корутина, timeout=секунд)
    except asyncio.TimeoutError:
        raise ОтказИсточника(f"{что}: не уложился в {int(секунд)} с — прерван")
