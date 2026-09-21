"""СОБИРАЕТСЯ ЛИ ЗАПРОС ПИСЬМА НА ПРОДЕ — после каждой выкладки, без денег.

ПРОВЕРКА, код 1 при сбое сборки, 2 — спросить нечем (прод не ответил
либо на нём не тот коммит).

АВАРИЯ 21.09 (№352). Письма на проде не писались, а стенд, на котором
всё было зелёным, собирал запрос письма не тем путём: на проде стоит
`LETTER_PROMPT_VARIANT=кэш`. Условие прода было невидимо стенду.

ЧТО СПРАШИВАЕТСЯ. Приложение прода САМО собирает запрос письма
(`GET /version/letter-build`, функция `main._сборка_письма_проверка`):
оба пути (полный и кэш) × оба языка × выдуманный профиль, со СВОИМИ
переменными окружения. Модель не зовётся, база не читается. Второго
процесса с `import main` на машине прода проба НЕ ЗАВОДИТ (§5.8: он
клал прод) — вопрос задаётся по HTTP.

Стоит шагом в `deploy.yml` сразу после выкладки: сборка упала — прогон
Actions красный, и это видно явно.

КЛЮЧИ:
  --база URL     чей адрес спрашивать (по умолчанию прод);
  --коммит SHA   дождаться этого коммита на `/version` (до 180 с);
  --контроль-подписи  английскому письму возвращается русская подпись —
                 падают ровно два случая en (№352, «питание-1»);
  --контроль     в процессе ломается путь кэша — проба обязана упасть
                 ИМЕННО на двух случаях кэша, полный путь остаётся зелёным.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

try:
    import probe_guard  # noqa: F401
except ImportError:
    pass

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

АДРЕС = "https://energydess.ru"


def _get(url, таймаут=30):
    try:
        with urllib.request.urlopen(url, timeout=таймаут) as r:
            return r.status, r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def разобрать(итог):
    """Печать случаев; возвращает число сбойных."""
    плохих = 0
    print("вариант на машине: %s" % итог.get("вариант_прода"))
    for с in итог.get("случаи", []):
        хорошо = с.get("ok")
        плохих += 0 if хорошо else 1
        print("  %-5s путь %-6s язык %s%s" % (
            "OK" if хорошо else "ПЛОХО", с.get("вариант"), с.get("язык"),
            "" if хорошо else " — " + json.dumps(
                {к: с.get(к) for к in ("сбой", "язык_в_запросе", "подпись_в_запросе", "пустые_части", "форма")
                 if к in с}, ensure_ascii=False)))
    if not итог.get("случаи"):
        плохих += 1
        print("  ПЛОХО случаев в ответе НОЛЬ — сборка не спрошена")
    return плохих


def прод(база, коммит):
    if коммит:
        до = time.time() + 180
        while True:
            код, тело = _get(база + "/version", 20)
            есть = (json.loads(тело).get("commit") or "") if код == 200 else ""
            if есть and коммит.startswith(есть):
                print("на %s коммит %s" % (база, есть))
                break
            if time.time() > до:
                print("ПРОПУСК: на %s коммит %r, ждали %s" % (база, есть, коммит[:7]))
                return 2
            time.sleep(10)
    код, тело = _get(база + "/version/letter-build", 60)
    try:
        итог = json.loads(тело)
    except ValueError:
        print("ПЛОХО: %s ответил %d не JSON" % (база, код))
        return 1
    плохих = разобрать(итог)
    print("ИТОГ: HTTP %d, случаев %d, сбойных %d" % (код, len(итог.get("случаи", [])), плохих))
    return 1 if (плохих or код != 200) else 0


def контроль():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import main
    from fastapi.testclient import TestClient
    чисто = main._сборка_письма_проверка()
    настоящий = main._сообщения_письма

    def сломанный(части, вариант):
        if вариант == "кэш":
            return [{"role": "user", "content": "".join(части.values())}]  # кэш потерян
        return настоящий(части, вариант)
    main._сообщения_письма = сломанный
    try:
        # ДОКАЗАТЕЛЬСТВО независимо от вердикта: сам путь кэша больше
        # не ставит `cache_control`
        док = "cache_control" in json.dumps(сломанный({"а": "б"}, "кэш"))
        ответ = TestClient(main.app).get("/version/letter-build")
        итог = ответ.json()
    finally:
        main._сообщения_письма = настоящий
    упали = sorted((с["вариант"], с["язык"]) for с in итог["случаи"] if not с["ok"])
    print("чисто: ok=%s; ДОКАЗАТЕЛЬСТВО подлога: cache_control в пути кэша %s → %s"
          % (чисто["ok"], True, док))
    print("с подлогом: HTTP %d, упали %s" % (ответ.status_code, упали))
    ждём = [("кэш", "en"), ("кэш", "ru")]
    годен = чисто["ok"] and not док and ответ.status_code == 500 and упали == ждём
    print("КОНТРОЛЬ: %s" % ("проба НАШЛА сломанный путь кэша и только его" if годен
                            else "НЕ ДОКАЗАН"))
    return 0 if годен else 1


def контроль_подписи():
    """Подлог: английскому письму возвращается русская подпись.

    Проба обязана упасть ИМЕННО на двух английских случаях (оба пути),
    русские остаются зелёными (№352, «питание-1», 1.4)."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import main
    чисто = main._сборка_письма_проверка()
    настоящая = main.ПОДПИСЬ_ПИСЬМА["en"]
    main.ПОДПИСЬ_ПИСЬМА["en"] = main.ПОДПИСЬ_ПИСЬМА["ru"]
    try:
        # ДОКАЗАТЕЛЬСТВО независимо от вердикта: в правиле en больше нет
        # английской подписи
        док = main.СБОРКА_ПОДПИСЬ["en"] in main.ПОДПИСЬ_ПИСЬМА["en"]
        итог = main._сборка_письма_проверка()
    finally:
        main.ПОДПИСЬ_ПИСЬМА["en"] = настоящая
    упали = sorted((с["вариант"], с["язык"]) for с in итог["случаи"] if not с["ok"])
    print("чисто: ok=%s; ДОКАЗАТЕЛЬСТВО подлога: «Best regards» в правиле en True → %s"
          % (чисто["ok"], док))
    print("с подлогом: упали %s" % упали)
    годен = чисто["ok"] and not док and упали == [("кэш", "en"), ("полный", "en")]
    print("КОНТРОЛЬ ПОДПИСИ: %s" % ("проба НАШЛА русскую подпись в английском письме"
                                    if годен else "НЕ ДОКАЗАН"))
    return 0 if годен else 1


def main_():
    if "--контроль-подписи" in sys.argv:
        return контроль_подписи()
    if "--контроль" in sys.argv:
        return контроль()
    база = sys.argv[sys.argv.index("--база") + 1] if "--база" in sys.argv else АДРЕС
    коммит = sys.argv[sys.argv.index("--коммит") + 1] if "--коммит" in sys.argv else ""
    try:
        return прод(база.rstrip("/"), коммит)
    except (urllib.error.URLError, OSError) as e:
        print("ПРОПУСК: %s не ответил: %s" % (база, e))
        return 2


if __name__ == "__main__":
    sys.exit(main_())
