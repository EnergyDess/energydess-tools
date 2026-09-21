"""ПРОВЕРКА 52: `TemplateResponse` ТОЛЬКО С `request` ПЕРВЫМ АРГУМЕНТОМ.

ПРОВЕРКА, код 1 при находке, 2 — вызовов не найдено (пустой сбор
не равен чистоте).

ЗАЧЕМ (№352, письмо 5). Старая позиционная форма
`TemplateResponse(имя, контекст)` на Starlette 1.1 читает первый
аргумент как `request`, второй как имя шаблона — словарь уходит на место
имени и падает `TypeError`. Отказ был НЕМОЙ И ОБРАТНЫЙ: правка раздела
резюме уже лежала в базе, а человек видел «Не удалось сохранить».
Поймал это владелец, а не проверка.

ПРИЗНАК — РАЗБОР ДЕРЕВА, а не греп: вызов, разорванный переносом строки
(`TemplateResponse(` и аргументы ниже), грепом по строке не виден,
а таких в проекте большинство. Годен вызов, у которого первым
позиционным стоит имя `request` либо передан ключ `request=`.
Файлы — все отслеживаемые `*.py` (`git ls-files`), перечня нет.

    py check_render_calls.py              # проверка
    py check_render_calls.py --контроль   # подлог: одна старая форма
"""
import ast
import subprocess
import sys

try:
    import probe_guard  # noqa: F401
except ImportError:
    pass

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def файлы():
    вывод = subprocess.run(["git", "ls-files", "-z", "*.py"], capture_output=True, check=True)
    return [f for f in вывод.stdout.decode("utf-8").split("\0") if f]


def разобрать(путь, текст=None):
    """(вызовов, [(строка, первый аргумент)] старой формы)."""
    if текст is None:
        with open(путь, encoding="utf-8") as ф:
            текст = ф.read()
    try:
        дерево = ast.parse(текст)
    except SyntaxError:
        return 0, []
    вызовов, плохие = 0, []
    for у in ast.walk(дерево):
        if (isinstance(у, ast.Call) and isinstance(у.func, ast.Attribute)
                and у.func.attr == "TemplateResponse"):
            вызовов += 1
            первый = у.args[0] if у.args else None
            годен = ((isinstance(первый, ast.Name) and первый.id == "request")
                     or any(к.arg == "request" for к in у.keywords))
            if not годен:
                плохие.append((у.lineno, ast.unparse(первый)[:50] if первый else "—"))
    return вызовов, плохие


def прогон(подмена=None, печать=True):
    всего, находки = 0, []
    for f in файлы():
        n, п = разобрать(f, (подмена or {}).get(f))
        всего += n
        находки += [(f, с, а) for с, а in п]
    if печать:
        print("вызовов TemplateResponse: %d, старой формы: %d" % (всего, len(находки)))
        for f, с, а in находки:
            print("   %s:%d  первым аргументом %s" % (f, с, а))
    if not всего:
        if печать:
            print("ПРОПУСК: вызовов не найдено — проверять нечего")
        return 2, находки
    return (1 if находки else 0), находки


ПОДЛОГ = ('\n\ndef _подлог_шаблона(request):\n'
          '    return templates.TemplateResponse(\n'
          '        "hh.html", {"request": request})\n')


def контроль():
    код0, _ = прогон(печать=False)
    if код0 != 0:
        print("ГРЯЗНАЯ ОСНОВА: чистый прогон дал код %d" % код0)
        return 2
    with open("main.py", encoding="utf-8") as ф:
        до = ф.read()
    после = до + ПОДЛОГ
    строка = после.count("\n", 0, после.index("templates.TemplateResponse(\n        \"hh.html\"")) + 1
    # ДОКАЗАТЕЛЬСТВО независимо от вердикта: старая форма в тексте 0 → 1
    док = (до.count('TemplateResponse(\n        "hh.html"'), после.count('TemplateResponse(\n        "hh.html"'))
    код, н = прогон({"main.py": после}, печать=False)
    назван = ("main.py", строка) in [(f, с) for f, с, _ in н]
    print("доказательство: старая форма в тексте %d → %d" % док)
    print("подлог main.py:%d — код %d → %d, находка названа: %s" % (строка, код0, код, назван))
    годен = док == (0, 1) and код == 1 and назван
    print("КОНТРОЛЬ:", "подлог найден по файлу и строке" if годен else "НЕ ДОКАЗАН")
    return 0 if годен else 1


if __name__ == "__main__":
    if "--контроль" in sys.argv:
        sys.exit(контроль())
    sys.exit(прогон()[0])
