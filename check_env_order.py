# -*- coding: utf-8 -*-
"""ПРОВЕРКА 18: env-файл прочитан ПОЗЖЕ, чем модуль, который его читает.

ЧТО ЛОВИТ. `database`, `auth`, `crypto`, `zepp_client` берут значения
из окружения НА УРОВНЕ МОДУЛЯ — то есть в момент импорта. Стоял
`load_dotenv()` ниже этих импортов (main.py: импорт database на 32-й
строке, load_dotenv на 47-й), и все они читали ГОЛОЕ окружение процесса,
мимо env-файла.

ПОЧЕМУ ЭТО НЕ ВИДНО. `os.getenv("DB_PATH")` после `load_dotenv()` отдаёт
значение из файла — то есть проверка «а прочитался ли файл» проходит.
А `database.DB_PATH` при этом держит умолчание, и база открыта другая.
Замер до правки, четыре настройки положены в env-файл: разошлись ТРИ
(`DB_PATH`, `SECRET_KEY`, `ZEPP_TRACE`); сошёлся один
`CREDENTIALS_ENCRYPTION_KEY`, и только потому, что `crypto` импортируется
внутри функции, а не в шапке.

Стенд, поднятый с env-файлом, при этом заводит ВТОРУЮ базу рядом с собой
и выглядит рабочим: страницы отдаются, вход не проходит — «аккаунта нет».
Ложный замер из этого получается один раз и стоит захода.

ПОЧЕМУ ПРОВЕРЯЕТСЯ КЛАСС, А НЕ ЭКЗЕМПЛЯР (CLAUDE.md §6.0.7). Перечня
«вот эти четыре модуля» здесь нет: множество открыто — завтра появится
пятый, и в перечне его не будет. Признак выводится из кода:

  · НАШ модуль (лежит рядом, не из site-packages),
  · читает `os.getenv` / `os.environ` НА ВЕРХНЕМ УРОВНЕ (не внутри
    функции и не внутри класса),
  · импортируется в `main.py`.

Такой модуль обязан импортироваться ПОЗЖЕ вызова `load_dotenv()`.

ЧЕГО НЕ ВИДИТ:
  · чтение окружения через переменную-псевдоним;
  · модуль, который читает окружение не сам, а импортом третьего;
  · порядок внутри модулей, которые main.py не импортирует.

Код возврата: 0 — порядок верный, 1 — есть импорт до load_dotenv,
2 — разобрать не удалось.

    py check_env_order.py;            echo "код=$?"
    py check_env_order.py --контроль; echo "код=$?"
"""
import ast
import io
import os
import sys

КОРЕНЬ = os.path.dirname(os.path.abspath(__file__))


def _читает_окружение_на_верхнем_уровне(путь):
    """Имена настроек, которые модуль читает В МОМЕНТ ИМПОРТА.

    Обходом дерева, а не грепом: `os.getenv("X")` внутри функции читается
    при вызове, а не при импорте, и находкой не является. Греп эти два
    случая не различает вовсе — а в `main.py` вызовов внутри функций
    десятки."""
    try:
        дерево = ast.parse(io.open(путь, encoding="utf-8").read(), путь)
    except (OSError, SyntaxError):
        return []
    имена = []

    def подходит(узел):
        if isinstance(узел, ast.Call) and isinstance(узел.func, ast.Attribute):
            ф = узел.func
            if ф.attr == "getenv" and isinstance(ф.value, ast.Name) and ф.value.id == "os":
                return True
            if (ф.attr == "get" and isinstance(ф.value, ast.Attribute)
                    and ф.value.attr == "environ"):
                return True
        return False

    def имя_настройки(узел):
        if узел.args and isinstance(узел.args[0], ast.Constant):
            return str(узел.args[0].value)
        return "?"

    # Только верхний уровень: тело модуля и тела `if`/`try` на нём.
    # Внутрь def/class не спускаемся — там чтение отложено до вызова.
    for узел in дерево.body:
        if isinstance(узел, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        for под in ast.walk(узел):
            if isinstance(под, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if подходит(под):
                имена.append(имя_настройки(под))
            elif (isinstance(под, ast.Subscript)
                  and isinstance(под.value, ast.Attribute)
                  and под.value.attr == "environ"
                  and isinstance(под.slice, ast.Constant)):
                имена.append(str(под.slice.value))
    return sorted(set(str(и) for и in имена))


def разобрать(путь_main, корень):
    """(строка load_dotenv, [(строка, модуль, [настройки])]) по одному файлу."""
    исходник = io.open(путь_main, encoding="utf-8").read()
    дерево = ast.parse(исходник, путь_main)

    строка_dotenv = None
    for узел in ast.walk(дерево):
        if (isinstance(узел, ast.Call) and isinstance(узел.func, ast.Name)
                and узел.func.id == "load_dotenv"):
            if строка_dotenv is None or узел.lineno < строка_dotenv:
                строка_dotenv = узел.lineno

    импорты = []
    for узел in дерево.body:
        модули = []
        if isinstance(узел, ast.Import):
            модули = [а.name for а in узел.names]
        elif isinstance(узел, ast.ImportFrom) and узел.level == 0 and узел.module:
            модули = [узел.module]
        for м in модули:
            верх = м.split(".")[0]
            файл = os.path.join(корень, верх + ".py")
            if not os.path.exists(файл):
                continue                      # чужой пакет — его порядок не наш
            настройки = _читает_окружение_на_верхнем_уровне(файл)
            if настройки:
                импорты.append((узел.lineno, верх, настройки))
    return строка_dotenv, импорты


def проверить(путь_main, корень, тихо=False):
    try:
        строка_dotenv, импорты = разобрать(путь_main, корень)
    except (OSError, SyntaxError) as e:
        print("РАЗОБРАТЬ НЕ УДАЛОСЬ: %s" % e)
        return 2
    имя = os.path.basename(путь_main)
    if строка_dotenv is None:
        if not тихо:
            print("%s: load_dotenv() не вызывается вовсе — проверять нечего" % имя)
        return 0
    if not тихо:
        print("%s: load_dotenv() на строке %d" % (имя, строка_dotenv))
        print("наших модулей, читающих окружение при импорте: %d" % len(импорты))
    находки = []
    for строка, модуль, настройки in импорты:
        поздно = строка < строка_dotenv
        if поздно:
            находки.append((строка, модуль, настройки))
        if not тихо:
            print("  строка %-5d %-16s %-52s %s"
                  % (строка, модуль, ",".join(настройки), "ПОЗДНО" if поздно else "ок"))
    if находки:
        print("НАХОДОК: %d — импорт стоит ДО load_dotenv(), "
              "настройки из env-файла до модуля не доедут" % len(находки))
        return 1
    if not тихо:
        print("НАХОДОК: 0")
    return 0


def контроль():
    """Подлог: тот же разбор на файле, где load_dotenv стоит НИЖЕ импорта.

    Без него «находок 0» ничего не значит — ровно ноль печатала бы
    и проверка, которая смотрит не туда."""
    import tempfile
    with tempfile.TemporaryDirectory() as кат:
        io.open(os.path.join(кат, "poddelny.py"), "w", encoding="utf-8").write(
            "import os\nВАЖНОЕ = os.getenv('ВАЖНОЕ', 'умолчание')\n")
        io.open(os.path.join(кат, "bezobidny.py"), "w", encoding="utf-8").write(
            "import os\ndef взять():\n    return os.getenv('ПОЗЖЕ')\n")
        плохой = os.path.join(кат, "плохой.py")
        io.open(плохой, "w", encoding="utf-8").write(
            "from poddelny import ВАЖНОЕ\n"
            "from bezobidny import взять\n"
            "from dotenv import load_dotenv\n"
            "load_dotenv()\n")
        хороший = os.path.join(кат, "хороший.py")
        io.open(хороший, "w", encoding="utf-8").write(
            "from dotenv import load_dotenv\n"
            "load_dotenv()\n"
            "from poddelny import ВАЖНОЕ\n"
            "from bezobidny import взять\n")

        плохо = проверить(плохой, кат, тихо=True)
        хорошо = проверить(хороший, кат, тихо=True)
        _, импорты = разобрать(хороший, кат)
        видит_отложенное = any(м == "bezobidny" for _, м, _ in импорты)

        ок = (плохо == 1 and хорошо == 0 and not видит_отложенное)
        print("подлог (load_dotenv ниже импорта): код %d  (обязан быть 1)" % плохо)
        print("верный порядок:                    код %d  (обязан быть 0)" % хорошо)
        print("чтение окружения ВНУТРИ функции:   %s  (обязан пропускать)"
              % ("считает находкой" if видит_отложенное else "пропускает"))
        print("КОНТРОЛЬ ПРОЙДЕН" if ок else "КОНТРОЛЬ ПРОВАЛЕН")
        return 0 if ок else 1


if __name__ == "__main__":
    if "--контроль" in sys.argv:
        sys.exit(контроль())
    sys.exit(проверить(os.path.join(КОРЕНЬ, "main.py"), КОРЕНЬ))
