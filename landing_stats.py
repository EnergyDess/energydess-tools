"""ЧИСЛА КАРТОЧКИ 03 ГОСТЕВОЙ ГЛАВНОЙ — «масштаб работы» (письмо 4 задачи 343).

Каждое число считается КОМАНДОЙ, а не вписывается руками: вписанное
протухает молча (§6.0.4). Считаются ПРИ ВЫКЛАДКЕ — шагом deploy.yml
перед сборкой образа, — а не на каждый запрос: в образе нет ни `.git/`,
ни `*.md` (.dockerignore), считать там нечем. Результат — файл
`landing_stats.json` в корне сборки; в git он не лежит (.gitignore),
иначе число коммитов в нём отставало бы на коммит, который его записал.

    py landing_stats.py              — напечатать числа и способ счёта
    py landing_stats.py --записать   — записать landing_stats.json

ЧИСЛА И СПОСОБ:
  · инструменты — пунктов списка раздела «Инструменты» гостевой главной
    (`class="pf-tool"` в templates/landing.html): ровно то, что видит гость;
  · рабочие заходы — различные номера задачи в области темы коммита
    (`feat(343,…)` → 343), а у писем одной задачи (`п2`, `п3а`, `п4`…) —
    каждое письмо отдельно. Коммиты ранней истории номера не носят,
    поэтому число — нижняя граница;
  · коммиты — `git rev-list --count HEAD`;
  · автопроверки — проверок обоих рядов §6.0.2 (основной и ряд стенда,
    `project_lists`) плюс режимов пробы главной (`РЕЖИМЫ` в
    check_portfolio.py, разбором дерева — без импорта Playwright).

Любое число, которое посчитать не удалось, останавливает запись кодом 2:
карточка с выдуманным или пустым числом хуже карточки без выкладки.
"""
import ast
import io
import json
import pathlib
import re
import subprocess
import sys

КОРЕНЬ = pathlib.Path(__file__).resolve().parent
ФАЙЛ = КОРЕНЬ / "landing_stats.json"


def _git(*арг):
    return subprocess.run(["git", *арг], cwd=КОРЕНЬ, capture_output=True, text=True,
                          encoding="utf-8", check=True).stdout


def инструменты():
    текст = io.open(КОРЕНЬ / "templates" / "landing.html", encoding="utf-8").read()
    return len(re.findall(r'<li class="pf-tool"', текст))


ТЕМА = re.compile(r"^[a-z]+\((\d{2,3})(?:\s*,\s*(п\d+[а-я]?))?")


def заходы():
    ключи = set()
    for строка in _git("log", "--format=%s").splitlines():
        м = ТЕМА.match(строка)
        if м:
            ключи.add((м.group(1), м.group(2) or ""))
    return len(ключи)


def коммиты():
    return int(_git("rev-list", "--count", "HEAD").strip())


def автопроверки():
    sys.path.insert(0, str(КОРЕНЬ))
    import project_lists as пл
    ряд = len(пл.разобрать()[1]) + len(пл.команды_стенда())
    дерево = ast.parse(io.open(КОРЕНЬ / "check_portfolio.py", encoding="utf-8").read())
    режимов = 0
    for узел in дерево.body:
        if isinstance(узел, ast.Assign) and any(getattr(ц, "id", "") == "РЕЖИМЫ" for ц in узел.targets):
            режимов = len(узел.value.elts)
    return ряд, режимов


def посчитать():
    ряд, режимов = автопроверки()
    return {"tools": инструменты(), "sessions": заходы(), "commits": коммиты(),
            "checks": ряд + режимов, "checks_row": ряд, "checks_portfolio": режимов,
            "commit": _git("rev-parse", "--short", "HEAD").strip()}


def main():
    ч = посчитать()
    print("инструменты %(tools)d · заходы %(sessions)d · коммиты %(commits)d · "
          "автопроверки %(checks)d (ряды §6.0.2 %(checks_row)d + режимы пробы главной "
          "%(checks_portfolio)d) · коммит %(commit)s" % ч)
    нули = [к for к in ("tools", "sessions", "commits", "checks_row", "checks_portfolio") if not ч[к]]
    if нули:
        print("НЕ ПОСЧИТАНО: %s — файл не записан" % ", ".join(нули))
        return 2
    if "--записать" in sys.argv[1:]:
        ФАЙЛ.write_text(json.dumps(ч, ensure_ascii=False), encoding="utf-8")
        print("записано: %s" % ФАЙЛ.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
