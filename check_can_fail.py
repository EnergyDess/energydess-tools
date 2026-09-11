"""ПРОВЕРКА 33: ШАГ ПРОБЫ, КОТОРЫЙ НЕ МОЖЕТ ПРОВАЛИТЬСЯ (BACKLOG №281, 285).

ЧТО ЭТО. Пробы проекта печатают шаги вида `шаг(имя, условие, подпись)`,
и итог прохода — «плохих N». Шаг, у которого условие истинно при ЛЮБОМ
входе, занимает место в ряду и создаёт видимость покрытия: он печатает
OK и тогда, когда замер не состоялся вовсе. Это опаснее отсутствующего
шага — отсутствующий хотя бы не выдаёт себя за проверку.

ПОЧЕМУ ПРОВЕРКОЙ, А НЕ ТЕКСТОМ. Правило «пустой результат не равен
успеху» записано в §6.0.1 и §6.0.3 давно — и за один день нашлись
четыре таких шага в двух пробах (задачи 267, 268, 281, 284). Текст его
читают, но не исполняют; ловить надо машиной.

ГДЕ ИЩЕТСЯ. Файлы `check_*.py`, в которых ОБЪЯВЛЕНА функция либо метод
`шаг` с первым параметром `имя` (после `self`). Перечня файлов нет:
новая проба с тем же устройством попадает под проверку сама (§6.0.7).
Условие — второй позиционный аргумент вызова `шаг(...)`/`X.шаг(...)`
либо ключевой с именем второго параметра.

ПРИЗНАКИ «НЕ МОЖЕТ ПРОВАЛИТЬСЯ» — только те, что выводятся из ТЕКСТА:
  · истинная константа (`True`, непустая строка, ненулевое число);
  · `или`, у которого хоть одна ветвь всегда истинна, либо пара
    `X or not X`; `и`, у которого истинны все ветви;
  · сравнение выражения с самим собой (`x == x`, `x >= x`);
  · длина не меньше нуля (`len(...) >= 0`, `0 <= len(...)`);
  · `bool(...)` и тернарный оператор из всегда истинных частей;
  · имя, которому в той же функции присваиваются ТОЛЬКО всегда истинные
    значения;
  · условие шага повторяет условие ОБЪЕМЛЮЩЕГО `if` (или один из его
    сомножителей `and`): внутри ветки оно истинно по построению.

ГРАНИЦА — НАЗВАНА, А НЕ ЗАБЫТА:
  · условие, истинное из-за ДАННЫХ стенда (`было_в_базе == 'approved'`
    при единственной одобренной карточке), текстом не выводится —
    вход, при котором шаг падает, существует, просто стенд его не даёт;
  · `if not x: return` ВЫШЕ шага и затем `шаг(x)` не берётся:
    нужен разбор потока управления, а не дерева;
  · шаг, который ПРОПАДАЕТ целиком в одной из веток, не берётся:
    это другая болезнь — «шага нет», а не «шаг всегда OK».

ДОЛГ И НОВОЕ. Уже известные шаги объявлены `ДОЛГ` — парой «файл, имя»,
с номером задачи и ЧИСЛОМ мест на момент записи. Они печатаются своим
разделом и в код возврата не идут; стало мест больше — это новое место,
и оно уходит в находки с пометкой ВЫРОСЛО (тот же приём, что
`ПРИНЯТЫЕ` у проверки 20).

КОДЫ: 0 — нового нет; 1 — есть новые находки; 2 — не собрано ни одного
вызова шага (пустой сбор не равен чистоте, §6.0.1).

    py check_can_fail.py              опись; код 1 при новом
    py check_can_fail.py --все        плюс ВСЕ вызовы с вердиктом
    py check_can_fail.py --файл X     только один файл
    py check_can_fail.py --контроль   подлоги в памяти, диск не трогается
"""
import ast
import glob
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

КОРЕНЬ = os.path.dirname(os.path.abspath(__file__))

# ── ИЗВЕСТНЫЙ ДОЛГ ─────────────────────────────────────────────────────
# (файл, имя шага) -> (задача, мест на момент записи). Пополняется
# ТОЛЬКО тем же коммитом, что заводит задачу в BACKLOG.md.
ДОЛГ = {
    # мерка обхода справочника печатает число позиций с обеими записями
    # и итогом ставит литерал True — упасть шагу нечем
    ("check_medkit_manual.py", "обе-записи-живут-рядом"): (286, 1),
}


def _дамп(узел):
    return ast.dump(узел, annotate_fields=False)


def _родители(дерево):
    р = {}
    for у in ast.walk(дерево):
        for ребёнок in ast.iter_child_nodes(у):
            р[ребёнок] = у
    return р


class Разбор:
    def __init__(self, дерево):
        self.дерево = дерево
        self.родитель = _родители(дерево)

    # ── окружение вызова ──
    def функция(self, узел):
        у = self.родитель.get(узел)
        while у is not None and not isinstance(
                у, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            у = self.родитель.get(у)
        return у

    def присваивания(self, имя, функция):
        """Значения, присваиваемые `имя` в функции. None — есть связывание,
        значение которого неизвестно (параметр, цикл, +=, with, распаковка)."""
        корень = функция if функция is not None else self.дерево
        значения = []
        if isinstance(корень, (ast.FunctionDef, ast.AsyncFunctionDef)):
            а = корень.args
            for п in а.posonlyargs + а.args + а.kwonlyargs + \
                    [x for x in (а.vararg, а.kwarg) if x]:
                if п.arg == имя:
                    return None
        for у in ast.walk(корень):
            if у is not корень and isinstance(
                    у, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                continue
            if isinstance(у, ast.Assign):
                for ц in у.targets:
                    if isinstance(ц, ast.Name) and ц.id == имя:
                        значения.append(у.value)
                    elif any(isinstance(н, ast.Name) and н.id == имя
                             for н in ast.walk(ц)):
                        return None
            elif isinstance(у, ast.AnnAssign) and isinstance(у.target, ast.Name) \
                    and у.target.id == имя:
                if у.value is None:
                    return None
                значения.append(у.value)
            elif isinstance(у, (ast.AugAssign, ast.For, ast.AsyncFor,
                                ast.comprehension, ast.NamedExpr)):
                цель = getattr(у, "target", None)
                if цель is not None and any(
                        isinstance(н, ast.Name) and н.id == имя
                        for н in ast.walk(цель)):
                    return None
            elif isinstance(у, (ast.With, ast.AsyncWith)):
                for эл in у.items:
                    if эл.optional_vars is not None and any(
                            isinstance(н, ast.Name) and н.id == имя
                            for н in ast.walk(эл.optional_vars)):
                        return None
            elif isinstance(у, ast.ExceptHandler) and у.name == имя:
                return None
        return значения or None

    # ── истинность ──
    def всегда(self, у, функция, глубина=0):
        """(истинно ли при любом входе, причина)."""
        if глубина > 12:
            return False, ""
        if isinstance(у, ast.Constant):
            return (bool(у.value), "константа %r" % (у.value,)) if у.value \
                else (False, "")
        if isinstance(у, ast.UnaryOp) and isinstance(у.op, ast.Not):
            л, п = self.никогда(у.operand, функция, глубина + 1)
            return (л, "not " + п) if л else (False, "")
        if isinstance(у, ast.BoolOp):
            if isinstance(у.op, ast.Or):
                for ч in у.values:
                    и, п = self.всегда(ч, функция, глубина + 1)
                    if и:
                        return True, "ветвь «или»: " + п
                дампы = [_дамп(ч) for ч in у.values]
                for ч in у.values:
                    if isinstance(ч, ast.UnaryOp) and isinstance(ч.op, ast.Not) \
                            and _дамп(ч.operand) in дампы:
                        return True, "X or not X"
                return False, ""
            причины = []
            for ч in у.values:
                и, п = self.всегда(ч, функция, глубина + 1)
                if not и:
                    return False, ""
                причины.append(п)
            return True, "все ветви «и»: " + "; ".join(причины)
        if isinstance(у, ast.Compare) and len(у.ops) == 1:
            л, оп, пр = у.left, у.ops[0], у.comparators[0]
            if _дамп(л) == _дамп(пр) and isinstance(
                    оп, (ast.Eq, ast.GtE, ast.LtE, ast.Is)):
                return True, "сравнение с самим собой"

            def длина(x):
                return (isinstance(x, ast.Call) and isinstance(x.func, ast.Name)
                        and x.func.id == "len")

            def ноль(x):
                return isinstance(x, ast.Constant) and x.value == 0 \
                    and not isinstance(x.value, bool)
            if (isinstance(оп, ast.GtE) and длина(л) and ноль(пр)) or \
                    (isinstance(оп, ast.LtE) and ноль(л) and длина(пр)):
                return True, "длина не меньше нуля"
            return False, ""
        if isinstance(у, ast.Call) and isinstance(у.func, ast.Name) \
                and у.func.id == "bool" and len(у.args) == 1:
            return self.всегда(у.args[0], функция, глубина + 1)
        if isinstance(у, ast.IfExp):
            а, па = self.всегда(у.body, функция, глубина + 1)
            б, пб = self.всегда(у.orelse, функция, глубина + 1)
            return (True, "обе ветви тернарного: %s | %s" % (па, пб)) \
                if а and б else (False, "")
        if isinstance(у, ast.Name):
            значения = self.присваивания(у.id, функция)
            if not значения:
                return False, ""
            причины = []
            for з in значения:
                и, п = self.всегда(з, функция, глубина + 1)
                if not и:
                    return False, ""
                причины.append(п)
            return True, "«%s» всегда присваивается истинное (%s)" % (
                у.id, "; ".join(причины))
        return False, ""

    def никогда(self, у, функция, глубина=0):
        if глубина > 12:
            return False, ""
        if isinstance(у, ast.Constant):
            return (True, "константа %r" % (у.value,)) if not у.value \
                else (False, "")
        if isinstance(у, ast.UnaryOp) and isinstance(у.op, ast.Not):
            return self.всегда(у.operand, функция, глубина + 1)
        return False, ""

    def повтор_условия_if(self, вызов, условие):
        """Условие шага повторяет условие объемлющего if."""
        д = _дамп(условие)
        ребёнок, у = вызов, self.родитель.get(вызов)
        while у is not None and not isinstance(
                у, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Module)):
            if isinstance(у, ast.If):
                в_теле = any(ребёнок is x for x in у.body)
                в_иначе = any(ребёнок is x for x in у.orelse)
                т = у.test
                сомножители = т.values if isinstance(т, ast.BoolOp) and \
                    isinstance(т.op, ast.And) else [т]
                if в_теле and д in {_дамп(x) for x in сомножители}:
                    return "повторяет условие if (строка %d)" % у.lineno
                if в_иначе and isinstance(условие, ast.UnaryOp) and \
                        isinstance(условие.op, ast.Not) and \
                        _дамп(условие.operand) == _дамп(т):
                    return "not условия if в ветке else (строка %d)" % у.lineno
                if в_иначе and isinstance(т, ast.UnaryOp) and \
                        isinstance(т.op, ast.Not) and _дамп(т.operand) == д:
                    return "условие if было not X, ветка else (строка %d)" % у.lineno
            ребёнок, у = у, self.родитель.get(у)
        return ""


def _сигнатуры(дерево):
    """Имя второго параметра у объявленных `шаг(имя, условие, ...)`."""
    имена = set()
    for у in ast.walk(дерево):
        if isinstance(у, (ast.FunctionDef, ast.AsyncFunctionDef)) and у.name == "шаг":
            п = [x.arg for x in у.args.args]
            if п and п[0] == "self":
                п = п[1:]
            if len(п) >= 2 and п[0] == "имя":
                имена.add(п[1])
    return имена


def разобрать_текст(текст, файл="<память>"):
    """Список (строка, имя шага, вердикт, причина) и признак «шаг объявлен»."""
    дерево = ast.parse(текст)
    вторые = _сигнатуры(дерево)
    if not вторые:
        return None
    р = Разбор(дерево)
    вызовы = []
    for у in ast.walk(дерево):
        if not isinstance(у, ast.Call):
            continue
        ф = у.func
        имя_ф = ф.id if isinstance(ф, ast.Name) else (
            ф.attr if isinstance(ф, ast.Attribute) else None)
        if имя_ф != "шаг":
            continue
        условие = у.args[1] if len(у.args) >= 2 else next(
            (k.value for k in у.keywords if k.arg in вторые), None)
        if условие is None:
            continue
        первый = у.args[0] if у.args else None
        if isinstance(первый, ast.Constant) and isinstance(первый.value, str):
            имя = первый.value
        elif isinstance(первый, ast.JoinedStr):
            имя = "".join(ч.value if isinstance(ч, ast.Constant) else "{…}"
                          for ч in первый.values)
        else:
            имя = "<выражение: %s>" % ast.unparse(первый)[:50] if первый is not None else "?"
        функция = р.функция(у)
        # вызов внутри самого определения `шаг` (прокладка) не проверяется
        if isinstance(функция, (ast.FunctionDef, ast.AsyncFunctionDef)) and \
                функция.name in ("шаг",):
            continue
        и, причина = р.всегда(условие, функция)
        if not и:
            причина = р.повтор_условия_if(у, условие)
            и = bool(причина)
        ложь = р.никогда(условие, функция)[0]
        вызовы.append([у.lineno, имя, и, причина, ast.unparse(условие)[:70], ложь])
    # ИСХОД ПРОВЕРЕННОГО ПРЕДУСЛОВИЯ — НЕ БОЛЕЗНЬ. Форма
    #   if not поз: шаг(X, False, 'нет'); return
    #   шаг(X, True, 'есть')
    # равна `шаг(X, bool(поз))`: оба исхода перечислены, и шаг X падает.
    # Болезнь — литерал True, у которого пары с False НЕТ: там вторая
    # ветка либо отсутствует, либо это ЗАМЕР, и True стоит на месте
    # «замер не состоялся» (задача 281: `срок-заперт…`, `лента…`).
    с_ложью = {в[1] for в in вызовы if в[5]}
    for в in вызовы:
        if в[2] and в[1] in с_ложью:
            в[2] = False
            в[3] = "исход предусловия: у шага есть пара с False"
    return sorted(tuple(в[:5]) for в in вызовы)


def файлы_проб():
    return sorted(glob.glob(os.path.join(КОРЕНЬ, "check_*.py")))


def опись(только=None):
    итог = {}
    for путь in файлы_проб():
        файл = os.path.basename(путь)
        if только and файл != только:
            continue
        with open(путь, encoding="utf-8") as ф:
            текст = ф.read()
        if "шаг" not in текст:
            continue
        вызовы = разобрать_текст(текст, файл)
        if вызовы is None:
            continue
        итог[файл] = вызовы
    return итог


def _контроль():
    """Подлоги в памяти: каждый обязан быть назван, обратные — пропущены."""
    шапка = ("class О:\n    def шаг(self, имя, ок, что=''):\n        pass\n"
             "о = О()\n")
    случаи = [
        ("литерал True", "о.шаг('а', True, 'x')\n", True),
        ("или с True", "def ф(x):\n    о.шаг('а', x > 1 or True)\n", True),
        ("длина >= 0", "def ф(x):\n    о.шаг('а', len(x) >= 0)\n", True),
        ("имя всегда True", "def ф(x):\n    ок = True\n    о.шаг('а', ок)\n", True),
        ("повтор условия if",
         "def ф(x):\n    if x and x.y:\n        о.шаг('а', x)\n", True),
        ("X or not X", "def ф(x):\n    о.шаг('а', x or not x)\n", True),
        ("ОБРАТНЫЙ: может упасть", "def ф(x):\n    о.шаг('а', x > 1)\n", False),
        ("ОБРАТНЫЙ: имя из двух веток",
         "def ф(x):\n    ок = True\n    if x: ок = x.z\n    о.шаг('а', ок)\n", False),
        ("ОБРАТНЫЙ: or без истинной ветви",
         "def ф(x, w):\n    о.шаг('а', x or w < 800)\n", False),
        ("ОБРАТНЫЙ: условие шага уже условия if",
         "def ф(x):\n    if x:\n        о.шаг('а', x.y)\n", False),
        ("ОБРАТНЫЙ: исход предусловия с парой False",
         "def ф(x):\n    if not x:\n        о.шаг('а', False)\n        return\n"
         "    о.шаг('а', True)\n", False),
        ("True на месте несостоявшегося замера",
         "def ф(x):\n    if x:\n        о.шаг('а', x.y > 1)\n    else:\n"
         "        о.шаг('а', True, 'замер не состоялся')\n", True),
    ]
    плохо = 0
    for что, тело, ждём in случаи:
        вызовы = разобрать_текст(шапка + тело)
        # ЛЮБОЕ место, а не первое по строке: первая версия контроля
        # брала `вызовы[0]` и на случае «True на месте замера» смотрела
        # САМ ЗАМЕР — печатала «может» про место, где True и не стоял
        места = [в for в in (вызовы or []) if в[2]]
        нашёл = bool(места)
        верно = нашёл == ждём
        плохо += 0 if верно else 1
        print("  %s  %-44s ждём %s, вышло %s%s" % (
            "OK   " if верно else "ПЛОХО", что,
            "НЕ МОЖЕТ" if ждём else "МОЖЕТ", "НЕ МОЖЕТ" if нашёл else "МОЖЕТ",
            ("  (" + места[0][3] + ")") if места else ""))
    # файл без объявления `шаг(имя, …)` не собирается вовсе
    чужой = разобрать_текст("def шаг(закр, тег, текст):\n    pass\nшаг(1, True, 2)\n")
    верно = чужой is None
    плохо += 0 if верно else 1
    print("  %s  %-38s ждём не собран, вышло %s" % (
        "OK   " if верно else "ПЛОХО", "ОБРАТНЫЙ: чужая сигнатура шаг",
        "не собран" if чужой is None else "собран"))
    print()
    print("КОНТРОЛЬ: случаев %d, неверных %d" % (len(случаи) + 1, плохо))
    return 1 if плохо else 0


def main():
    арг = sys.argv[1:]
    if "--контроль" in арг:
        return _контроль()
    только = арг[арг.index("--файл") + 1] if "--файл" in арг else None
    все = "--все" in арг

    итог = опись(только)
    всего = sum(len(в) for в in итог.values())
    print("ШАГИ, КОТОРЫЕ НЕ МОГУТ ПРОВАЛИТЬСЯ — разбор дерева, не грепом")
    print("=" * 74)
    if not всего:
        print("СОБРАНО ВЫЗОВОВ ШАГА: 0 — проверять нечего, это НЕ чистота")
        return 2

    новые, долг = [], []
    for файл, вызовы in итог.items():
        не_могут = [в for в in вызовы if в[2]]
        имён = len({в[1] for в in вызовы})
        print("%-26s вызовов %3d (имён %3d), не могут упасть %d" % (
            файл, len(вызовы), имён, len(не_могут)))
        по_имени = {}
        for в in не_могут:
            по_имени.setdefault(в[1], []).append(в)
        for имя, места in по_имени.items():
            ключ = (файл, имя)
            if ключ in ДОЛГ and len(места) <= ДОЛГ[ключ][1]:
                долг.append((файл, имя, места, ДОЛГ[ключ][0]))
            else:
                метка = " ВЫРОСЛО" if ключ in ДОЛГ else ""
                новые.append((файл, имя, места, метка))
        if все:
            for строка, имя, и, причина, усл in вызовы:
                print("    %5d  %-8s %s  [%s]%s" % (
                    строка, "НЕ МОЖЕТ" if и else "может", имя, усл,
                    ("  — " + причина) if и else ""))
    print()
    print("ВСЕГО вызовов шага %d, не могут упасть %d (новых мест %d, долг %d)" % (
        всего, sum(1 for в in итог.values() for x in в if x[2]),
        sum(len(н[2]) for н in новые), sum(len(д[2]) for д in долг)))
    if долг:
        print()
        print("ДОЛГ (известен, заведён задачей — в код возврата не идёт):")
        for файл, имя, места, задача in долг:
            print("  №%s  %s  «%s»  мест %d" % (задача, файл, имя, len(места)))
    if новые:
        print()
        print("НАХОДКИ:")
        for файл, имя, места, метка in новые:
            for строка, _, _, причина, усл in места:
                print("  %s:%d  «%s»%s — %s  [%s]" % (
                    файл, строка, имя, метка, причина, усл))
    return 1 if новые else 0


if __name__ == "__main__":
    sys.exit(main())
