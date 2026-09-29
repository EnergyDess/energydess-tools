"""ФАЙЛЫ ПРИЛОЖЕНИЯ: `main.py` и модули проекта, которые он подключает.

Сторожа вызовов модели (политика данных — `test_openrouter_policy.py`,
учёт расхода — `test_model_usage.py`) до 2026-09-29 читали ОДИН `main.py`.
Модуль «Контент» (BACKLOG №365, 366) зовёт модель из своего файла —
и прошёл бы мимо обоих сторожей МОЛЧА: «политика в каждом вызове»
печаталась бы про список, в котором его нет (§6.0.7).

ВЫВОДИТСЯ ГРАФОМ ИМПОРТОВ ОТ `main.py`, а не перечнем и не по
`sys.modules`. Перечень отстал бы на следующем модуле, а `sys.modules`
зависел бы от порядка тестов: пробы и мерки (`measure_letter_*`,
`check_search_api`) тоже зовут модель, и загрузи их соседний тест —
число мест вызова поплыло бы от прогона к прогону.
"""
import ast
import io
import pathlib

КОРЕНЬ = pathlib.Path(__file__).resolve().parent.parent


def модули_приложения() -> list:
    """Пути файлов проекта, достижимых импортом из `main.py` (включая
    импорты внутри функций — `import main` в модуле, подключённом из
    `main`, тоже ребро графа)."""
    очередь, видели = ["main"], set()
    while очередь:
        имя = очередь.pop()
        if имя in видели:
            continue
        путь = КОРЕНЬ / f"{имя}.py"
        if not путь.exists():
            continue
        видели.add(имя)
        for узел in ast.walk(ast.parse(io.open(путь, encoding="utf-8").read())):
            if isinstance(узел, ast.Import):
                очередь += [а.name.split(".")[0] for а in узел.names]
            elif isinstance(узел, ast.ImportFrom) and узел.module and not узел.level:
                очередь.append(узел.module.split(".")[0])
    return sorted(КОРЕНЬ / f"{и}.py" for и in видели)


def исходники_приложения() -> dict:
    """{имя файла: текст} по всем файлам приложения."""
    return {п.name: io.open(п, encoding="utf-8").read() for п in модули_приложения()}
