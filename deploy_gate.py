"""ЗАМОК ДЕПЛОЯ: ВЫКАТКА ТОЛЬКО НА ЗЕЛЁНОМ ПРОГОНЕ ЭТОГО КОММИТА (№357).

ПРОВЕРКА, код 1 при отказе. Спрашивает у GitHub, чем кончился прогон
`checks.yml` РОВНО для названного коммита, и требует УСПЕХА У КАЖДОЙ
работы: их две (`row` и `stand`), и зелёная одна при красной другой —
это не зелёный ряд.

ПОЧЕМУ ШАГОМ, А НЕ УСЛОВИЕМ `if` У РАБОТЫ. Условие действует только
на том пути запуска, где оно написано: выкатку зовут и по завершении
прогона, и руками (`workflow_dispatch`), и во втором случае про прогон
никто бы не спросил. Скрипт спрашивает одинаково на обоих путях
и — главное — прогоняется МЕСТНО, то есть подлог проверяется без
выкатки на прод.

ПРОГОНА НЕТ — ЭТО ОТКАЗ, А НЕ ПРОПУСК. «Ряд не гоняли» и «ряд зелёный»
обязаны различаться (§6.0.1): молчаливый пропуск означал бы выкатку
кода, которого не проверял никто.

    py deploy_gate.py --sha <коммит>     # обычно ${{ github.sha }}
    py deploy_gate.py                    # текущий HEAD
    py deploy_gate.py --контроль         # подлог: коммит без прогона
"""
import json
import subprocess
import sys

import probe_guard  # noqa: F401 — внешний отказ говорится словом (§3)

РАБОЧИЙ_ПРОЦЕСС = "checks.yml"


def _git(*аргументы):
    п = subprocess.run(["git", *аргументы], capture_output=True, text=True,
                       errors="replace")
    return (п.stdout or "").strip()


def прогоны(sha):
    """[{работа: исход}] по прогонам `checks.yml` для этого коммита.

    Спрашивается `gh`: он есть и на машине разработчика, и на раннере,
    и берёт токен из окружения сам. Пусто — прогона НЕ БЫЛО.
    """
    п = subprocess.run(
        ["gh", "run", "list", "--workflow", РАБОЧИЙ_ПРОЦЕСС,
         "--commit", sha, "--limit", "20", "--json",
         "databaseId,status,conclusion,createdAt"],
        capture_output=True, text=True, errors="replace")
    if п.returncode != 0:
        raise OSError("gh run list: %s" % (п.stderr or "").strip()[:200])
    return json.loads(п.stdout or "[]")


def работы(номер):
    п = subprocess.run(["gh", "run", "view", str(номер), "--json", "jobs"],
                       capture_output=True, text=True, errors="replace")
    if п.returncode != 0:
        raise OSError("gh run view: %s" % (п.stderr or "").strip()[:200])
    return (json.loads(п.stdout or "{}").get("jobs") or [])


def проверить(sha):
    """0 — выкатка можно, 1 — нельзя (с названной причиной)."""
    список = прогоны(sha)
    if not список:
        print("ДЕПЛОЙ НЕЛЬЗЯ: прогона %s для коммита %s НЕТ — ряд этого "
              "кода не гоняли" % (РАБОЧИЙ_ПРОЦЕСС, sha[:7]))
        return 1
    # САМЫЙ СВЕЖИЙ ПРОГОН, а не любой зелёный: перезапуск после правки
    # рабочего процесса должен перекрывать прежний исход.
    свежий = sorted(список, key=lambda п: п.get("createdAt") or "")[-1]
    if свежий.get("status") != "completed":
        print("ДЕПЛОЙ НЕЛЬЗЯ: прогон %s для %s ещё идёт (%s)"
              % (свежий["databaseId"], sha[:7], свежий.get("status")))
        return 1
    if свежий.get("conclusion") != "success":
        print("ДЕПЛОЙ НЕЛЬЗЯ: прогон %s для %s кончился «%s»"
              % (свежий["databaseId"], sha[:7], свежий.get("conclusion")))
        return 1
    плохие = [р for р in работы(свежий["databaseId"])
              if р.get("conclusion") != "success"]
    if плохие:
        print("ДЕПЛОЙ НЕЛЬЗЯ: в прогоне %s работы не зелёные: %s"
              % (свежий["databaseId"],
                 ", ".join("%s → %s" % (р.get("name"), р.get("conclusion"))
                           for р in плохие)))
        return 1
    имена = [р.get("name") for р in работы(свежий["databaseId"])]
    print("ДЕПЛОЙ МОЖНО: прогон %s для %s зелёный, работ %d (%s)"
          % (свежий["databaseId"], sha[:7], len(имена), ", ".join(имена)))
    return 0


def контроль():
    """ПОДЛОГ: коммит, у которого прогона НЕТ, обязан быть отвергнут.

    Доказательство независимо от вердикта: печатается число прогонов,
    найденных для этого коммита, — оно и есть то, что подлог меняет.
    """
    свой = _git("rev-parse", "HEAD")
    без = _git("rev-list", "--max-parents=1", "--skip=60", "-1", "HEAD") or \
        _git("rev-list", "--max-parents=1", "-1", "HEAD~60")
    if not без:
        print("КОНТРОЛЬ: НЕ ПРОГНАН — в истории нет коммита без прогона")
        return 2
    print("  доказательство: прогонов у %s — %d, у подлога %s — %d"
          % (свой[:7], len(прогоны(свой)), без[:7], len(прогоны(без))))
    код = проверить(без)
    print("КОНТРОЛЬ: %s" % ("ЛОВИТ" if код == 1 else "НЕ ЛОВИТ — замок пуст"))
    return 0 if код == 1 else 1


if __name__ == "__main__":
    for _п in (sys.stdout, sys.stderr):
        try:
            _п.reconfigure(encoding="utf-8")
        except AttributeError:
            pass
    if "--контроль" in sys.argv:
        sys.exit(контроль())
    sha = (sys.argv[sys.argv.index("--sha") + 1] if "--sha" in sys.argv
           else _git("rev-parse", "HEAD"))
    sys.exit(проверить(sha))
