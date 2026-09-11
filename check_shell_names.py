# -*- coding: utf-8 -*-
"""ПРОВЕРКА 34: КИРИЛЛИЦА В ИМЕНИ ПЕРЕМЕННОЙ ОБОЛОЧКИ — ДО ЗАПУСКА (заход 298).

Имя переменной bash — только `[A-Za-z_][A-Za-z0-9_]*`. Кириллическое имя
не ошибка разбора, а ДРУГОЙ СМЫСЛ, и отказ немой либо запоздалый (§6.0):

    код=$?          → «код=0: command not found», код возврата ПОТЕРЯН
    echo "$код"     → печатается буквально «$код», ни ошибки, ни пустоты
    ${код}          → «bad substitution», но уже посреди прогона
    for имя in ...  → «not a valid identifier», цикл не выполнен

Правило записано в §6.0 и стоит в каждом письме, и всё равно ТРИ ЗАХОДА
ПОДРЯД рушило прогон: в заходе 280 потерян код двух проверок ряда стенда,
в заходе 296 упала первая цепочка ряда стенда целиком. Текстом это
не лечится — поэтому машина, и в ДВУХ местах:

  · В МОМЕНТ НАПИСАНИЯ КОМАНДЫ — `--hook`: PreToolUse-хук Claude Code
    на инструмент Bash (`.claude/settings.json`). Команда с таким именем
    не запускается вовсе, отказ называет строку и имя. Это и есть ответ
    на вопрос «можно ли поймать до прогона ряда»: можно, потому что
    текст команды виден ДО исполнения.
  · В РЕПОЗИТОРИИ — без ключей: кодовые блоки bash/sh в отслеживаемых
    *.md (там лежат команды ряда §6.0.2), файлы *.sh и шаги `run:`
    в `.github/workflows`. Код 1 при находке, 2 — разбирать было нечего.

ПРИЗНАК — РАЗБОР ОБОЛОЧКИ, А НЕ ГРЕП. Греп по `имя=` поймал бы Python
внутри `py - <<'EOF'` (там присваивания законны), текст внутри кавычек
(`echo "код=$?"` — печать, а не присваивание) и аргументы команды
(`grep -n "имя=" файл`). Разбор знает кавычки, позицию команды,
документ-heredoc (с кавычками у разделителя тело НЕ оболочка вовсе),
подстановку `$(...)`, обратные кавычки и арифметику `$((...))`.

ЧТО СЧИТАЕТСЯ НАХОДКОЙ:
  присваивание   `имя=…` в ПОЗИЦИИ КОМАНДЫ (в том числе приставкой
                 перед командой); кириллица где угодно в имени
  подстановка    `$имя` (первая буква не ASCII), `${…имя…}`
  арифметика     кириллическое имя внутри `$((…))`
  объявление     имя после for/select/read/export/local/declare/
                 typeset/readonly/unset

ГРАНИЦА НАЗВАНА — НЕ ЛОВИТСЯ:
  · `$Nимя` — имя с латинской головы: bash честно берёт `$N` и дописывает
    «имя»; это бывает законным («"$HOME"папка»), и отказ тут стоил бы
    ложной блокировки;
  · имя, собранное в рантайме (`eval "$x=1"`, `declare "$x"`);
  · PowerShell: там `$код` — законное имя, хук на него не ставится.

    py check_shell_names.py                     # репозиторий, код 0/1/2
    py check_shell_names.py --hook              # режим хука (stdin JSON)
    py check_shell_names.py --транскрипты       # мерка по прошлым командам
    py check_shell_names.py --контроль          # подлоги 0 → 1 → 0
"""
import hashlib
import json
import os
import re
import subprocess
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

КОРЕНЬ = os.path.dirname(os.path.abspath(__file__))
ИМЯ = re.compile(r"[^\W\d]\w*")
ПРИСВАИВАНИЕ = re.compile(r"^([^\W\d]\w*)(\[[^\]]*\])?\+?=")
СЛУЖЕБНЫЕ = {"then", "do", "else", "elif", "if", "while", "until", "time",
             "!", "{", "}", "in"}
ОБЪЯВЛЕНИЯ = {"export", "local", "declare", "typeset", "readonly", "unset"}
READ_С_АРГУМЕНТОМ = {"-p", "-d", "-t", "-n", "-N", "-u", "-i"}
КОНЕЦ_СЛОВА = set(" \t\n;&|()<>")


def _не_ascii(с):
    return any(ord(б) > 127 for б in с)


class _Разбор:
    """Состояние одного прохода по тексту оболочки."""

    def __init__(self, т):
        self.т = т
        self.н = len(т)
        self.находки = []
        self.ожидают = []          # [(разделитель, в кавычках, срезать табы)]

    def _строка(self, i):
        return self.т.count("\n", 0, i) + 1

    def _найдено(self, вид, имя, i):
        self.находки.append({"вид": вид, "имя": имя, "строка": self._строка(i)})

    # ── подстановки ────────────────────────────────────────────────────
    def доллар(self, i):
        т, н = self.т, self.н
        сл = т[i + 1:i + 2]
        if сл == "{":
            м = re.compile(r"[#!]?([^\W\d]\w*)").match(т, i + 2)
            if м and _не_ascii(м.group(1)):
                self._найдено("подстановка", м.group(1), i)
            j = т.find("}", i)
            return н if j == -1 else j + 1
        if т.startswith("((", i + 1):
            return self.арифметика(i + 3)
        if сл == "(":
            return self.команды(i + 2, до_скобки=True)
        if сл == "'":
            j = i + 2
            while j < н and т[j] != "'":
                j += 2 if т[j] == "\\" else 1
            return min(н, j + 1)
        if сл == '"':
            return self.двойные(i + 2)
        м = ИМЯ.match(т, i + 1)
        if м:
            if _не_ascii(м.group(0)[0]):
                self._найдено("подстановка", м.group(0), i)
            return м.end()
        return i + 1

    def арифметика(self, i):
        """Тело `$((…))`: голое имя — переменная. Вложенная `$(…)`, кавычки
        и `$имя` разбираются своими путями — первая версия искала имена
        сплошняком до `))` и объявила находкой текст внутри
        `$(( $(grep -n 'СТОП_СИМПТОМЫ' …) + 40 ))`: 8 ложных из 36."""
        т, н = self.т, self.н
        глубина = 0
        while i < н:
            с = т[i]
            if т.startswith("))", i) and глубина == 0:
                return i + 2
            if с == "(":
                глубина += 1
                i += 1
            elif с == ")":
                глубина = max(0, глубина - 1)
                i += 1
            elif с == "$":
                i = self.доллар(i)
            elif с == "'":
                j = т.find("'", i + 1)
                i = н if j == -1 else j + 1
            elif с == '"':
                i = self.двойные(i + 1)
            elif с == "`":
                i = self.обратные(i)
            else:
                м = ИМЯ.match(т, i)
                if м:
                    if _не_ascii(м.group(0)):
                        self._найдено("арифметика", м.group(0), i)
                    i = м.end()
                else:
                    i += 1
        return н

    def обратные(self, i):
        """`…` — внутренность разбирается как команды."""
        т, н = self.т, self.н
        j = i + 1
        while j < н and т[j] != "`":
            j += 2 if т[j] == "\\" else 1
        вложенный = _Разбор(т[i + 1:j])
        вложенный.команды(0)
        сдвиг = self.т.count("\n", 0, i + 1)
        for ф in вложенный.находки:
            ф["строка"] += сдвиг
            self.находки.append(ф)
        return min(н, j + 1)

    def двойные(self, i):
        т, н = self.т, self.н
        while i < н:
            с = т[i]
            if с == "\\":
                i += 2
            elif с == '"':
                return i + 1
            elif с == "$":
                i = self.доллар(i)
            elif с == "`":
                i = self.обратные(i)
            else:
                i += 1
        return н

    def слово(self, i):
        """(конец, видимое без кавычек: закавыченное заменено нулём)."""
        т, н = self.т, self.н
        чистое = []
        while i < н:
            с = т[i]
            if с in КОНЕЦ_СЛОВА:
                break
            if с == "\\":
                чистое.append("\0")
                i += 2
            elif с == "'":
                j = т.find("'", i + 1)
                i = н if j == -1 else j + 1
                чистое.append("\0")
            elif с == '"':
                i = self.двойные(i + 1)
                чистое.append("\0")
            elif с == "`":
                i = self.обратные(i)
                чистое.append("\0")
            elif с == "$":
                i = self.доллар(i)
                чистое.append("\0")
            else:
                чистое.append(с)
                i += 1
        return i, "".join(чистое)

    # ── документы-heredoc ──────────────────────────────────────────────
    def тела(self, i):
        т, н = self.т, self.н
        for разделитель, в_кавычках, срезать in self.ожидают:
            while i < н:
                j = т.find("\n", i)
                j = н if j == -1 else j
                строка = т[i:j]
                сравнить = строка.lstrip("\t") if срезать else строка
                if not в_кавычках:
                    к = i
                    while к < j:
                        if т[к] == "\\":
                            к += 2
                        elif т[к] == "$":
                            к = min(j, self.доллар(к))
                        elif т[к] == "`":
                            к = min(j, self.обратные(к))
                        else:
                            к += 1
                i = min(н, j + 1)
                if сравнить == разделитель:
                    break
        self.ожидают = []
        return i

    # ── команды ────────────────────────────────────────────────────────
    def команды(self, i, до_скобки=False):
        т, н = self.т, self.н
        позиция = True
        ждём = None               # "for" | "объявление" | "read"
        пропустить = False
        глубина = 0
        while i < н:
            с = т[i]
            if с == "\n":
                i = self.тела(i + 1)
                позиция, ждём = True, None
                continue
            if с in " \t":
                i += 1
                continue
            if с == "\\" and т[i + 1:i + 2] == "\n":
                i += 2
                continue
            if с == "#":
                j = т.find("\n", i)
                i = н if j == -1 else j
                continue
            if т.startswith(("&&", "||", ";;", "|&"), i):
                i += 2
                позиция, ждём = True, None
                continue
            if с in ";&|":
                i += 1
                позиция, ждём = True, None
                continue
            if с == "(":
                глубина += 1
                i += 1
                позиция, ждём = True, None
                continue
            if с == ")":
                i += 1
                if до_скобки and глубина == 0:
                    return i
                глубина = max(0, глубина - 1)
                позиция, ждём = True, None
                continue
            м = re.compile(r"\d*(<<<|<<-|<<|>>|>&|<&|>\||&>|<|>)").match(т, i)
            if м:
                оп = м.group(1)
                i = м.end()
                while i < н and т[i] in " \t":
                    i += 1
                if оп in ("<<", "<<-"):
                    нач = i
                    i, чистое = self.слово(i)
                    сырое = т[нач:i]
                    в_кав = any(к in сырое for к in "'\"\\")
                    разделитель = re.sub(r"['\"\\]", "", сырое)
                    self.ожидают.append((разделитель, в_кав, оп == "<<-"))
                else:
                    i, _ = self.слово(i)
                continue
            нач = i
            i, чистое = self.слово(i)
            if i == нач:
                i += 1
                continue
            if пропустить:
                пропустить = False
                continue
            if ждём == "for":
                if ИМЯ.fullmatch(чистое) and _не_ascii(чистое):
                    self._найдено("объявление", чистое, нач)
                ждём = None
                continue
            if ждём in ("объявление", "read"):
                if чистое.startswith(("-", "+")):
                    if ждём == "read" and чистое in READ_С_АРГУМЕНТОМ:
                        пропустить = True
                    continue
                мм = re.match(r"^([^\W\d]\w*)(?:=|$)", чистое)
                if мм and _не_ascii(мм.group(1)):
                    self._найдено("объявление", мм.group(1), нач)
                continue
            if позиция:
                мм = ПРИСВАИВАНИЕ.match(чистое)
                if мм:
                    if _не_ascii(мм.group(1)):
                        self._найдено("присваивание", мм.group(1), нач)
                        позиция = False
                    continue
                if чистое in СЛУЖЕБНЫЕ:
                    continue
                if чистое in ("for", "select"):
                    ждём = "for"
                elif чистое in ОБЪЯВЛЕНИЯ:
                    ждём = "объявление"
                elif чистое == "read":
                    ждём = "read"
                позиция = False
        return i


def найти(текст):
    """Находки в тексте оболочки: [{вид, имя, строка}]."""
    р = _Разбор(текст or "")
    р.команды(0)
    return р.находки


# ── источники в репозитории ─────────────────────────────────────────────
ОГРАДА = re.compile(r"^```(?:bash|sh|shell)[ \t]*\n(.*?)^```", re.S | re.M)


def _отслеживаемые():
    вывод = subprocess.run(["git", "ls-files", "-z"], cwd=КОРЕНЬ,
                           capture_output=True, check=True).stdout
    return [п for п in вывод.decode("utf-8").split("\0") if п]


def _узлы_run(узел):
    """[(ключ, узел значения)] — все `run:` в дереве узлов YAML."""
    import yaml
    итог = []
    if isinstance(узел, yaml.MappingNode):
        for к, з in узел.value:
            if isinstance(к, yaml.ScalarNode) and к.value == "run" \
                    and isinstance(з, yaml.ScalarNode):
                итог.append((к, з))
            else:
                итог += _узлы_run(з)
    elif isinstance(узел, yaml.SequenceNode):
        for з in узел.value:
            итог += _узлы_run(з)
    return итог


def куски_репозитория():
    """[(путь, строка начала, текст)] — всё, что в репозитории исполняет bash."""
    куски = []
    for п in _отслеживаемые():
        полный = os.path.join(КОРЕНЬ, п)
        if not os.path.isfile(полный):
            continue
        if п.endswith(".md"):
            т = open(полный, encoding="utf-8").read()
            for м in ОГРАДА.finditer(т):
                куски.append((п, т.count("\n", 0, м.start(1)) + 1, м.group(1)))
        elif п.endswith(".sh"):
            куски.append((п, 1, open(полный, encoding="utf-8").read()))
        elif п.startswith(".github/workflows/") and п.endswith((".yml", ".yaml")):
            # НОМЕР СТРОКИ — ИЗ УЗЛА YAML, А НЕ ПОИСКОМ ПЕРВОЙ СТРОКИ КОДА:
            # первая версия искала её текстом и назвала строку 72 вместо
            # 198 — одинаковая первая строка стояла у ДВУХ шагов.
            import yaml
            for к, у in _узлы_run(yaml.compose(open(полный, encoding="utf-8"))):
                сдвиг = 2 if у.style in ("|", ">") else 1
                куски.append((п, у.start_mark.line + сдвиг, у.value))
    return куски


def проверить(тихо=False):
    куски = куски_репозитория()
    файлов = len({к[0] for к in куски})
    находки = []
    for путь, строка, текст in куски:
        for ф in найти(текст):
            находки.append((путь, строка + ф["строка"] - 1, ф["вид"], ф["имя"]))
    if not тихо:
        print("ПРОВЕРКА 34: кириллица в именах переменных оболочки")
        print("  кусков оболочки %d в %d файлах" % (len(куски), файлов))
        for путь, стр, вид, имя in находки:
            print("  %s:%d  %s «%s»" % (путь, стр, вид, имя))
        print("  находок %d" % len(находки))
    if not куски:
        if not тихо:
            print("  НЕ ПРОВЕРЕНО: разбирать нечего — пустой сбор не равен чистоте")
        return 2, находки
    return (1 if находки else 0), находки


# ── режим хука Claude Code ──────────────────────────────────────────────
def хук():
    """PreToolUse: код 2 — команда не запускается, stderr уходит модели."""
    try:
        данные = json.loads(sys.stdin.buffer.read().decode("utf-8") or "{}")
        if данные.get("tool_name") not in (None, "Bash"):
            return 0
        команда = (данные.get("tool_input") or {}).get("command") or ""
        находки = найти(команда)
    except Exception as e:                           # noqa: BLE001
        print("[check_shell_names] разбор не удался, команда не проверена: %s"
              % e, file=sys.stderr)
        return 1
    if not находки:
        return 0
    print("ОСТАНОВЛЕНО проверкой 34 (§6.0): имя переменной оболочки не латиницей.",
          file=sys.stderr)
    for ф in находки:
        print("  строка %d: %s «%s»" % (ф["строка"], ф["вид"], ф["имя"]),
              file=sys.stderr)
    print("bash понимает только [A-Za-z_][A-Za-z0-9_]* — «код=$?» даёт "
          "«command not found», «$код» печатается буквально. Переименуйте "
          "латиницей и запустите снова.", file=sys.stderr)
    return 2


# ── мерка по прошлым командам ───────────────────────────────────────────
ПРИЗНАКИ_ОТКАЗА = ("command not found", "bad substitution", "not a valid identifier")


def транскрипты():
    """МЕРКА, код 0: сколько прошлых команд Bash проверка остановила бы,
    и у скольких из них оболочка действительно ответила ошибкой."""
    корень = os.path.join(os.path.expanduser("~"), ".claude", "projects",
                          "e--------------------Ai-HH---------")
    import glob
    команды, итоги = {}, {}
    for ф in glob.glob(os.path.join(корень, "**", "*.jsonl"), recursive=True):
        for строка in open(ф, encoding="utf-8", errors="replace"):
            try:
                д = json.loads(строка)
            except ValueError:
                continue
            содерж = (д.get("message") or {}).get("content")
            if not isinstance(содерж, list):
                continue
            for х in содерж:
                if not isinstance(х, dict):
                    continue
                if х.get("type") == "tool_use" and х.get("name") == "Bash":
                    к = (х.get("input") or {}).get("command")
                    if к:
                        команды[х.get("id")] = к
                elif х.get("type") == "tool_result":
                    т = х.get("content")
                    if isinstance(т, list):
                        т = " ".join(ч.get("text", "") for ч in т if isinstance(ч, dict))
                    итоги[х.get("tool_use_id")] = т or ""
    с_находкой = {к: найти(т) for к, т in команды.items()}
    с_находкой = {к: н for к, н in с_находкой.items() if н}
    виды = {}
    for н in с_находкой.values():
        for ф in н:
            виды[ф["вид"]] = виды.get(ф["вид"], 0) + 1
    с_отказом = sum(1 for к in с_находкой
                    if any(п in итоги.get(к, "") for п in ПРИЗНАКИ_ОТКАЗА))
    с_кириллицей_отказ = sum(
        1 for к, т in команды.items() if к not in с_находкой
        and re.search(r"[^\x00-\x7f]+[^\s]*: command not found", итоги.get(к, "")))
    print("команд Bash в транскриптах проекта: %d" % len(команды))
    print("остановила бы проверка: %d (мест %d: %s)" % (
        len(с_находкой), sum(виды.values()),
        ", ".join("%s %d" % (в, ч) for в, ч in sorted(виды.items()))))
    print("  из них оболочка ответила ошибкой имени: %d; без ошибки: %d "
          "(подстановка печаталась буквально — либо ложная находка)"
          % (с_отказом, len(с_находкой) - с_отказом))
    # Подпись нарочно без буквального текста ошибки bash: иначе следующий
    # прогон находит ЭТУ СТРОКУ в итоге прошлого прогона и числит пропуском
    print("пропущено (ошибка оболочки на не-ASCII слове при нуле находок): %d"
          % с_кириллицей_отказ)
    if "--примеры" in sys.argv:
        for к, н in list(с_находкой.items())[:int(sys.argv[sys.argv.index("--примеры") + 1])]:
            print("---", н)
            print(команды[к][:400])
    return 0


# ── отрицательный контроль ──────────────────────────────────────────────
ПОДЛОГ = "\n```bash\npy check_docs.py; zz_контроль_код=$?\n```\n"
# Имя кириллическое, но с латинской приставкой: хвост «контроль» делает
# имя недопустимым, и находка обязана назвать его ЦЕЛИКОМ.
ОБРАТНЫЕ = (
    ("heredoc в кавычках с Python", "py - <<'EOF'\nимя = 1\nprint(имя)\nEOF\n"),
    ("печать в кавычках", 'py check_docs.py; echo "код=$?"\n'),
    ("аргумент команды", 'grep -n "имя=" CLAUDE.md\n'),
    ("кириллица в значении", 'KOD="значение"; echo "$KOD"\n'),
)
ПРЯМЫЕ = (
    ("присваивание", "py x.py; код=$?\n", "код"),
    ("подстановка в кавычках", 'echo "$код"\n', "код"),
    ("фигурная подстановка", "echo ${код}\n", "код"),
    ("имя цикла", "for имя in a b; do echo $имя; done\n", "имя"),
    ("heredoc без кавычек", "cat <<EOF\nитог $итог\nEOF\n", "итог"),
    ("внутри $(...)", 'x=$(код=1; echo 2)\n', "код"),
)


def контроль():
    ок = True
    путь = os.path.join(КОРЕНЬ, "CLAUDE.md")
    исходник = open(путь, "rb").read()
    отпечаток = hashlib.sha256(исходник).hexdigest()
    к0, н0 = проверить(тихо=True)
    try:
        with open(путь, "ab") as ф:
            ф.write(ПОДЛОГ.encode("utf-8"))
        к1, н1 = проверить(тихо=True)
    finally:
        with open(путь, "wb") as ф:
            ф.write(исходник)
    к2, н2 = проверить(тихо=True)
    вернулся = hashlib.sha256(open(путь, "rb").read()).hexdigest() == отпечаток
    названо = [н for н in н1 if н[0] == "CLAUDE.md" and н[3] == "zz_контроль_код"]
    print("РЕПОЗИТОРИЙ: находок %d → %d → %d, код %d → %d → %d; подлог назван "
          "поимённо: %s; CLAUDE.md побайтно возвращён: %s"
          % (len(н0), len(н1), len(н2), к0, к1, к2,
             "%s:%d" % названо[0][:2] if названо else "НЕТ", вернулся))
    ок &= (len(н0) == 0 and len(н1) == 1 and len(н2) == 0 and bool(названо)
           and к1 == 1 and к2 == 0 and вернулся)

    def хук_код(команда):
        п = subprocess.run([sys.executable, os.path.abspath(__file__), "--hook"],
                           input=json.dumps({"tool_name": "Bash",
                                             "tool_input": {"command": команда}},
                                            ensure_ascii=False).encode("utf-8"),
                           capture_output=True)
        return п.returncode, п.stderr.decode("utf-8", "replace")
    кч, _ = хук_код("py check_docs.py; KOD=$?; echo $KOD")
    кп, текст = хук_код("py check_docs.py; код=$?; echo $код")
    print("ХУК: латинское имя — код %d; кириллическое — код %d, имя в отказе: %s"
          % (кч, кп, "«код»" in текст))
    ок &= кч == 0 and кп == 2 and "«код»" in текст

    for подпись, текст, имя in ПРЯМЫЕ:
        н = найти(текст)
        попал = any(ф["имя"] == имя for ф in н)
        print("  прямой  %-24s находок %d — %s" % (подпись, len(н),
                                                     "НАЗВАН" if попал else "НЕ НАЗВАН"))
        ок &= попал
    for подпись, текст in ОБРАТНЫЕ:
        н = найти(текст)
        print("  обратный %-23s находок %d — %s" % (подпись, len(н),
                                                      "ЧИСТО" if not н else "ЛОЖНАЯ"))
        ок &= not н
    print("КОНТРОЛЬ ПРОВЕРКИ 34: %s" % ("ПРОЙДЕН" if ок else "ПРОВАЛЕН"))
    return 0 if ок else 1


if __name__ == "__main__":
    if "--hook" in sys.argv:
        sys.exit(хук())
    if "--транскрипты" in sys.argv:
        sys.exit(транскрипты())
    if "--контроль" in sys.argv:
        sys.exit(контроль())
    sys.exit(проверить()[0])
