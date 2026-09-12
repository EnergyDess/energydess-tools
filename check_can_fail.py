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

ВТОРОЙ И ТРЕТИЙ КЛАСС — С ЗАХОДА 292 (задача 286). Шаг, у которого вход
для падения ЕСТЬ, но который печатает OK, не измерив ничего:
  · ПУСТОЙ СБОР — условие истинно на пустой коллекции (`not X`, `X == 0`,
    `len(X) == 0`, `X == []`, `all(…)`, `not any(…)`), а коллекция —
    сбор: генератор, `len`/`sum`/`filter`, пустой список, пополняемый
    дальше, либо `evaluate` со сбором внутри JS (`querySelectorAll`,
    `.filter(`, `.push(`, `.map(`). Ноль собранного — ноль замера;
  · УСЛОВНЫЙ — `или`, у которого есть ветвь без замера: сравнение одних
    лишь параметров функции и констант (`ширина < 800`) либо `X is None`.
Оба снимаются КЛЮЧОМ у вызова, а не перечнем: `собрано=N` — число
собранного, и при нуле шаг обязан стать ПРОПУСКОМ; `отрицание="причина"`
— шаг проверяет отсутствие, и пустота тут и есть успех. `собрано=`
литералом не засчитывается: `собрано=1` — та же константа True.

ГРАНИЦА — НАЗВАНА, А НЕ ЗАБЫТА:
  · коллекция из поля словаря (`итог["ложных"] == 0`) и из `evaluate`
    с JS в переменной не распознаётся как сбор — берутся только те, что
    видны в тексте вызова;
  · «или» двух замеров, из которых один — отказ («"Сеть" in итог»),
    по тексту неотличим от двух законных формулировок одного исхода;
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
    py check_can_fail.py --пустой-замер   у каждого шага с `собрано=` все
                                      входы пусты: настоящий `шаг` пробы
                                      обязан записать ПРОПУСК

ПУСТОЙ ЗАМЕР — ПОДЛОГ НА ТОЙ САМОЙ СТРОКЕ, А НЕ НА ПРИДУМАННОЙ. Выражения
условия и `собрано=` берутся из дерева файла и вычисляются с ПУСТЫМ
значением каждого имени (длина 0, ложь, ноль, пустой обход); вызывается
НАСТОЯЩИЙ `шаг` пробы (функция модуля либо метод класса), и в его `шаги`
обязан лечь ПРОПУСК. Рядом печатается, чем было бы то же условие без
`собрано=`: OK на пустом — ровно та неправда, которую ключ снимает.
Браузера режим не поднимает: он проверяет проводку строки, а не экран.
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
}
# ДОЛГ ВТОРОГО И ТРЕТЬЕГО КЛАССА — ПО ФАЙЛУ, С ЧИСЛОМ МЕСТ (заход 292).
# Файл -> (задача, мест «пустой сбор», мест «условный»). Стало больше — находка
# ДОЛГА КЛАССОВ БОЛЬШЕ НЕТ. Шесть файлов задачи 293 (16 мест «пустого
# сбора» и 1 «условный») закрыты заходом 307 тем же механизмом, что
# заход 285 дал проходу аптечки: ключи `собрано=` / `отрицание=`
# у вызова шага и ПРОПУСК при нуле собранного.
#
# Пустой словарь оставлен НАМЕРЕННО, а не удалён вместе с чтением:
# следующий известный долг объявляется здесь строкой, и место для него
# должно быть видно.
ДОЛГ_КЛАССОВ = {}


def _как_легло(мод, отчёт_класс, условие, собрано):
    """(исход шага, спросили ли). Складов шагов у проб НЕСКОЛЬКО.

    Первая версия читала только `.шаги` — список, который держит
    `check_medkit_ui`. У соседей склад другой: счётчики (`ПЛОХО`,
    `ПРОПУЩЕНО`), список словарей, а у `check_ens_admin_ui` функция
    `шаг` объявлена ВНУТРИ прогона и на модуле её нет вовсе. Проверка
    падала `AttributeError` — то есть сама страдала болезнью, которую
    ищет (BACKLOG №307).

    Спрашивается по порядку: класс-отчёт со списком, модульный список,
    ВОЗВРАТ самой `шаг` (все починенные пробы отдают `None` при
    пропуске). Ничего не подошло — «спросить нечем», и это НЕ успех.
    """
    if отчёт_класс is not None:
        о = отчёт_класс()
        итог = о.шаг("пустой-замер", условие, "", собрано=собрано)
        шаги = getattr(о, "шаги", None)
        if isinstance(шаги, list):
            return (шаги[-1][1] if шаги else "НИЧЕГО"), True
        return итог, True
    шаг = getattr(мод, "шаг", None)
    if not callable(шаг):
        return None, False
    шаги = getattr(мод, "шаги", None)
    if isinstance(шаги, list):
        шаги.clear()
        шаг("пустой-замер", условие, "", собрано=собрано)
        return (шаги[-1][1] if шаги else "НИЧЕГО"), True
    return шаг("пустой-замер", условие, "", собрано=собрано), True


def _дамп(узел):
    return ast.dump(узел, annotate_fields=False)


def _родители(дерево):
    р = {}
    for у in ast.walk(дерево):
        for ребёнок in ast.iter_child_nodes(у):
            р[ребёнок] = у
    return р


ФОРМЫ_СБОРА_JS = ("querySelectorAll", ".filter(", ".push(", ".map(")
СБОР_ВЫЗОВЫ = ("len", "sum", "list", "set", "sorted", "filter")


def _строка_js(выр):
    if isinstance(выр, ast.Constant) and isinstance(выр.value, str):
        return выр.value
    if isinstance(выр, ast.JoinedStr):
        return "".join(ч.value for ч in выр.values
                       if isinstance(ч, ast.Constant) and isinstance(ч.value, str))
    if isinstance(выр, ast.BinOp) and isinstance(выр.op, (ast.Add, ast.Mod)):
        return _строка_js(выр.left) + _строка_js(выр.right)
    return ""


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

    # ── ВТОРОЙ КЛАСС: ПУСТОЙ СБОР ──
    def сбор(self, у, функция, глубина=0):
        if глубина > 8:
            return False
        if isinstance(у, ast.Await):
            у = у.value
        if isinstance(у, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            return True
        if isinstance(у, ast.List) and not у.elts:
            return True
        if isinstance(у, ast.Call):
            имя = у.func.id if isinstance(у.func, ast.Name) else (
                у.func.attr if isinstance(у.func, ast.Attribute) else "")
            if имя in СБОР_ВЫЗОВЫ:
                return True
            if имя in ("evaluate", "eval_on_selector_all") and у.args and any(
                    ф in _строка_js(у.args[0]) for ф in ФОРМЫ_СБОРА_JS):
                return True
            return False
        if isinstance(у, ast.Name):
            значения = self.присваивания(у.id, функция)
            return bool(значения) and any(
                self.сбор(з, функция, глубина + 1) for з in значения)
        return False

    def пустой_сбор(self, у, функция):
        """Причина, если условие истинно на пустом сборе; иначе пусто."""
        if isinstance(у, ast.UnaryOp) and isinstance(у.op, ast.Not):
            о = у.operand
            if isinstance(о, ast.Call) and isinstance(о.func, ast.Name) \
                    and о.func.id == "any":
                return "not any(…) истинно на пустом"
            if isinstance(о, ast.Call) and isinstance(о.func, ast.Name) \
                    and о.func.id == "len" and о.args:
                о = о.args[0]
            return "not X при пустом сборе" if self.сбор(о, функция) else ""
        if isinstance(у, ast.Call) and isinstance(у.func, ast.Name) \
                and у.func.id == "all":
            return "all(…) истинно на пустом"
        if isinstance(у, ast.Compare) and len(у.ops) == 1:
            л, оп, пр = у.left, у.ops[0], у.comparators[0]
            if isinstance(оп, (ast.Eq, ast.LtE)) and isinstance(пр, ast.Constant) \
                    and пр.value == 0 and not isinstance(пр.value, bool):
                if isinstance(л, ast.Call) and isinstance(л.func, ast.Name) \
                        and л.func.id in ("len", "sum"):
                    return "длина сбора == 0"
                return "X == 0 при пустом сборе" if self.сбор(л, функция) else ""
            if isinstance(оп, ast.Eq) and isinstance(
                    пр, (ast.List, ast.Tuple, ast.Set)) and not пр.elts:
                return "X == [] при пустом сборе" if self.сбор(л, функция) else ""
        return ""

    # ── ТРЕТИЙ КЛАСС: УСЛОВНЫЙ ──
    def условный(self, у, функция):
        if not (isinstance(у, ast.BoolOp) and isinstance(у.op, ast.Or)):
            return ""
        параметры = set()
        if isinstance(функция, (ast.FunctionDef, ast.AsyncFunctionDef)):
            а = функция.args
            параметры = {п.arg for п in а.posonlyargs + а.args + а.kwonlyargs}
        for ветвь in у.values:
            if isinstance(ветвь, ast.Compare) and len(ветвь.ops) == 1 and \
                    isinstance(ветвь.ops[0], ast.Is) and \
                    isinstance(ветвь.comparators[0], ast.Constant) and \
                    ветвь.comparators[0].value is None:
                return "ветвь «%s» засчитывает несостоявшийся замер" % ast.unparse(ветвь)
            if isinstance(ветвь, ast.Compare):
                имена = [н.id for н in ast.walk(ветвь) if isinstance(н, ast.Name)]
                if имена and all(и in параметры for и in имена):
                    return "ветвь «%s» не зависит от замера" % ast.unparse(ветвь)
        return ""

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
    р = Разбор(дерево)
    вызовы = []
    # ВТОРОЙ МЕХАНИЗМ ИСХОДА — ТЕРНАРНИК `"OK" if X else "ПЛОХО"`.
    # Проверка видела только пробы с объявленным `шаг(имя, условие)`,
    # и это ДВЕНАДЦАТЬ файлов из проекта; ещё ДЕВЯТНАДЦАТЬ выражают
    # исход шага тернарником и счётчиком `плохо += 0 if X else 1`,
    # то есть были вне её по построению (задача 293).
    #
    # Условие тут ровно то же самое — «может ли шаг провалиться», —
    # поэтому к нему применяются ТЕ ЖЕ признаки, а не новый разбор.
    for у in ast.walk(дерево):
        if not isinstance(у, ast.IfExp):
            continue
        конст = [n.value for n in (у.body, у.orelse)
                 if isinstance(n, ast.Constant) and isinstance(n.value, str)]
        if not any(c == "OK" or c.startswith("OK") or "ПЛОХО" in c
                   or c == "ok" for c in конст):
            continue
        функция = р.функция(у)
        и, причина = р.всегда(у.test, функция)
        класс = "строгий" if и else ""
        if not и:
            пс = р.пустой_сбор(у.test, функция)
            if пс:
                класс, причина = "пустой сбор", пс
            else:
                ус = р.условный(у.test, функция)
                if ус:
                    класс, причина = "условный", ус
        вызовы.append([у.lineno, "<исход OK/ПЛОХО>", и, причина,
                       ast.unparse(у.test)[:70], False, класс])
    if not вторые and not вызовы:
        return None
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
        ключи = {k.arg: k.value for k in у.keywords}
        класс = "строгий" if и else ""
        if not и:
            собрано = ключи.get("собрано")
            отрицание = ключи.get("отрицание")
            законно = (собрано is not None and not isinstance(собрано, ast.Constant)) \
                or (isinstance(отрицание, ast.Constant) and отрицание.value)
            if not законно:
                п = р.пустой_сбор(условие, функция)
                if п:
                    класс, причина = "пустой сбор", п
                else:
                    п = р.условный(условие, функция)
                    if п:
                        класс, причина = "условный", п
            if собрано is not None and isinstance(собрано, ast.Constant):
                класс, причина = "пустой сбор", "собрано= литералом"
        вызовы.append([у.lineno, имя, и, причина, ast.unparse(условие)[:70], ложь, класс])
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
            в[6] = ""
    return sorted(tuple(в[:5]) + (в[6],) for в in вызовы)


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
        # ФИЛЬТРА ПО СЛОВУ `шаг` БОЛЬШЕ НЕТ: второй механизм исхода
        # (тернарник OK/ПЛОХО) живёт в пробах, где слова `шаг` нет вовсе.
        # Файл без обоих механизмов отсеет сам `разобрать_текст`.
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
        # ЗАХОД 292: здесь стояло `x or w < 800` с `w` ПАРАМЕТРОМ — после
        # заведения третьего класса это ровно «условный» шаг, и контроль
        # объявлял бы находкой то, что признак ловит по делу. Ветвь с
        # замером (`w` присвоен внутри функции) — законная пара исходов
        ("ОБРАТНЫЙ: or без истинной ветви, обе ветви — замер",
         "def ф(x, pg):\n    w = pg.h\n    о.шаг('а', x or w < 800)\n", False),
        ("ОБРАТНЫЙ: условие шага уже условия if",
         "def ф(x):\n    if x:\n        о.шаг('а', x.y)\n", False),
        ("ОБРАТНЫЙ: исход предусловия с парой False",
         "def ф(x):\n    if not x:\n        о.шаг('а', False)\n        return\n"
         "    о.шаг('а', True)\n", False),
        ("ПУСТОЙ СБОР: not X из генератора",
         "def ф(x):\n    плохие = [у for у in x if у]\n    о.шаг('а', not плохие)\n", True),
        ("ПУСТОЙ СБОР: X == 0 из evaluate со сбором",
         "async def ф(pg):\n    н = await pg.evaluate(\"() => document.querySelectorAll('a').length\")\n"
         "    о.шаг('а', н == 0)\n", True),
        ("ПУСТОЙ СБОР: all(…)", "def ф(x):\n    о.шаг('а', all(у for у in x))\n", True),
        ("ПУСТОЙ СБОР: собрано= литералом",
         "def ф(x):\n    п = [у for у in x]\n    о.шаг('а', not п, собрано=1)\n", True),
        ("ОБРАТНЫЙ: собрано= названо",
         "def ф(x):\n    п = [у for у in x if у]\n    о.шаг('а', not п, собрано=len(x))\n", False),
        ("ОБРАТНЫЙ: отрицание с причиной",
         "def ф(x):\n    п = [у for у in x]\n    о.шаг('а', not п, отрицание='окна нет')\n", False),
        ("ОБРАТНЫЙ: not X не из сбора",
         "async def ф(pg):\n    т = await pg.evaluate('() => !!window.а')\n    о.шаг('а', not т)\n", False),
        ("УСЛОВНЫЙ: ветвь по параметру",
         "def ф(x, ширина):\n    о.шаг('а', x.y or ширина < 800)\n", True),
        ("УСЛОВНЫЙ: X is None", "def ф(x):\n    о.шаг('а', x.y is None or x.y > 1)\n", True),
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
        места = [в for в in (вызовы or []) if в[2] or в[5]]
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


class _Пусто:
    """Пустое значение любого вида: длина 0, ложь, ноль, пустой обход."""
    def __len__(self): return 0
    def __iter__(self): return iter(())
    def __bool__(self): return False
    def __int__(self): return 0
    def __index__(self): return 0
    def __float__(self): return 0.0
    def __str__(self): return ""
    def __format__(self, спек): return ""
    def __eq__(self, x): return isinstance(x, _Пусто) or x in (0, "", None) or x == []
    def __ne__(self, x): return not self.__eq__(x)
    def __hash__(self): return 0
    def __lt__(self, x): return False
    __gt__ = __le__ = __ge__ = __lt__
    # АРИФМЕТИКА ДАЁТ НОЛЬ: `собрано=ручных(до) + ручных(после)` уронил
    # первый прогон режима `TypeError` — сумма пустых обязана быть пустой
    def __add__(self, x): return 0
    __radd__ = __sub__ = __rsub__ = __mul__ = __rmul__ = __add__
    def __getitem__(self, к): return self
    def __call__(self, *а, **к): return self
    def __getattr__(self, к):
        if к.startswith("__"):
            raise AttributeError(к)
        return self


class _Имена(dict):
    """Пространство имён, где любое неизвестное имя — пустое."""
    def __missing__(self, к):
        import builtins
        return getattr(builtins, к) if hasattr(builtins, к) else _Пусто()


def _пустой_замер():
    import importlib.util
    плохо, всего = 0, 0
    for путь in файлы_проб():
        файл = os.path.basename(путь)
        текст = open(путь, encoding="utf-8").read()
        if "собрано=" not in текст or файл == "check_can_fail.py":
            continue
        дерево = ast.parse(текст)
        if not _сигнатуры(дерево):
            continue
        спек = importlib.util.spec_from_file_location("_проба_" + файл[:-3], путь)
        мод = importlib.util.module_from_spec(спек)
        спек.loader.exec_module(мод)
        отчёт_класс = next((з for з in vars(мод).values() if isinstance(з, type)
                            and callable(getattr(з, "шаг", None))), None)
        вызовов = пропусков = было_ок = не_спросили = 0
        for у in ast.walk(дерево):
            if not (isinstance(у, ast.Call) and (getattr(у.func, "id", None) == "шаг"
                                                 or getattr(у.func, "attr", None) == "шаг")):
                continue
            ключи = {k.arg: k.value for k in у.keywords}
            if "собрано" not in ключи or len(у.args) < 2:
                continue
            вызовов += 1
            имена = _Имена()
            условие = eval(compile(ast.Expression(у.args[1]), файл, "eval"), {"__builtins__": __import__("builtins")}, имена)
            собрано = eval(compile(ast.Expression(ключи["собрано"]), файл, "eval"), {"__builtins__": __import__("builtins")}, имена)
            было_ок += 1 if условие else 0
            легло, спросили = _как_легло(мод, отчёт_класс, условие, собрано)
            if not спросили:
                # СПРОСИТЬ НЕЧЕМ — И ЭТО НЕ «ПРОПУСК ЛЁГ». У пробы свой
                # склад шагов (счётчики вместо списка, `шаг` внутри
                # функции), и притвориться, что сверка прошла, значило бы
                # печатать зелёное про то, чего не спрашивали (§6.0.1).
                не_спросили += 1
                continue
            if легло is None:
                пропусков += 1
            else:
                плохо += 1
                print("  НЕ ПРОПУСК %s:%d — легло %r" % (файл, у.lineno, легло))
        всего += вызовов
        print("%-26s шагов с собрано= %d: на пустом ПРОПУСК %d · то же условие без "
              "ключа дало бы OK %d%s"
              % (файл, вызовов, пропусков, было_ок,
                 (" · спросить нечем %d" % не_спросили) if не_спросили else ""))
    print("ПУСТОЙ ЗАМЕР: шагов %d, не ПРОПУСК %d" % (всего, плохо))
    return 2 if not всего else (1 if плохо else 0)


def main():
    арг = sys.argv[1:]
    if "--контроль" in арг:
        return _контроль()
    if "--пустой-замер" in арг:
        return _пустой_замер()
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
    классы_всего = {"пустой сбор": 0, "условный": 0}
    for файл, вызовы in итог.items():
        не_могут = [в for в in вызовы if в[2]]
        имён = len({в[1] for в in вызовы})
        пустых = [в for в in вызовы if в[5] == "пустой сбор"]
        условных = [в for в in вызовы if в[5] == "условный"]
        классы_всего["пустой сбор"] += len(пустых)
        классы_всего["условный"] += len(условных)
        print("%-26s вызовов %3d (имён %3d), не могут упасть %d · пустой сбор %d · "
              "условных %d" % (файл, len(вызовы), имён, len(не_могут),
                               len(пустых), len(условных)))
        задача, долг_пустых, долг_условных = ДОЛГ_КЛАССОВ.get(файл, (None, 0, 0))
        for класс, места, предел in (("пустой сбор", пустых, долг_пустых),
                                     ("условный", условных, долг_условных)):
            if not места:
                continue
            if len(места) <= предел:
                долг.append((файл, класс, [(м[0], м[1], True, м[3], м[4]) for м in места],
                             задача))
            else:
                новые.append((файл, класс, [(м[0], м[1], True, м[3], м[4]) for м in места],
                              " ВЫРОСЛО" if предел else ""))
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
            for строка, имя, и, причина, усл, _к in вызовы:
                print("    %5d  %-8s %s  [%s]%s" % (
                    строка, "НЕ МОЖЕТ" if и else "может", имя, усл,
                    ("  — " + причина) if и else ""))
    print()
    print("ВСЕГО вызовов шага %d, не могут упасть %d · пустой сбор %d · условных %d "
          "(новых мест %d, долг %d)" % (
              всего, sum(1 for в in итог.values() for x in в if x[2]),
              классы_всего["пустой сбор"], классы_всего["условный"],
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
            for м in места:
                строка, причина, усл = м[0], м[3], м[4]
                print("  %s:%d  «%s»%s — %s  [%s]" % (
                    файл, строка, имя, метка, причина, усл))
    return 1 if новые else 0


if __name__ == "__main__":
    sys.exit(main())
