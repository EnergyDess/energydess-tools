# -*- coding: utf-8 -*-
"""СКОЛЬКО МЕСТ ЧИТАЕТ «Во флаконе» (задача 253).

МЕРКА, код возврата всегда 0: «сколько мест осталось» — число,
а не приговор.

СЧИТАЮТСЯ МЕСТА ЧТЕНИЯ, А НЕ СТРОКИ С ПОДСТРОКОЙ. Разница
не педантизм: объявление колонки, строка миграции и упоминание
в комментарии — это не чтение, и свалив их в одно число, мерка
печатала бы «мест 42» там, где убрать надо шесть.

ПРИЗНАК РАЗНЫЙ У РАЗНЫХ ЯЗЫКОВ, и поэтому разбор тоже разный:
в Python — синтаксическое дерево (обращение к атрибуту либо ключ
словаря), в шаблоне — идентификаторы органов и имена полей в JS.
Греп по подстроке считал бы прозой код и кодом прозу (§6.0, урок
задачи 99).
"""
import ast
import io
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

ИМЕНА = ("volume", "volume_unit")
# ОБЪЯВЛЕНИЕ И МИГРАЦИЯ — НЕ ЧТЕНИЕ. Они уйдут вместе с колонкой,
# и числить их местами чтения значило бы считать одно дважды
НЕ_ЧТЕНИЕ = ("database.py",)


def _питон(путь):
    """Места чтения в Python: `x.volume`, `d["volume"]`, `volume=`."""
    исх = io.open(путь, encoding="utf-8").read()
    из_ = []
    try:
        дер = ast.parse(исх)
    except SyntaxError as e:
        print("  %s: РАЗБОР НЕ УДАЛСЯ (%s) — молчание было бы неотличимо "
              "от чистоты" % (путь, e))
        return из_
    строки = исх.split("\n")
    for узел in ast.walk(дер):
        стр = None
        if isinstance(узел, ast.Attribute) and узел.attr in ИМЕНА:
            стр = узел.lineno
        elif (isinstance(узел, ast.Constant) and isinstance(узел.value, str)
              and узел.value in ИМЕНА):
            стр = узел.lineno
        elif isinstance(узел, ast.keyword) and узел.arg in ИМЕНА:
            стр = узел.lineno
        elif isinstance(узел, ast.Name) and узел.id in (
                "ЕДИНИЦЫ_ОБЪЁМА", "ЕДИНИЦА_ОБЪЁМА_ПО_ID", "объём_словами"):
            стр = узел.lineno
        if стр:
            из_.append((стр, строки[стр - 1].strip()[:72]))
    return sorted(set(из_))


def _шаблон(путь):
    """Места в разметке и скрипте страницы."""
    исх = io.open(путь, encoding="utf-8").read()
    из_ = []
    признак = re.compile(
        r"volume|apt-f-vol|apt-only-volume|apt-vol-unit|единицы_объёма"
        r"|объём_словами|ЕДИНИЦЫ_ОБЪЁМА")
    for н, с in enumerate(исх.split("\n"), 1):
        # ПРОЗА СНИМАЕТСЯ: комментарий Jinja и JS-комментарий
        голая = re.sub(r"\{#.*?#\}", "", с)
        голая = re.sub(r"/\*.*?\*/", "", голая)
        if голая.strip().startswith(("{#", "*", "/*", "//")):
            continue
        if признак.search(голая):
            из_.append((н, с.strip()[:72]))
    return из_


ФАЙЛЫ = [("main.py", _питон), ("medkit_defs.py", _питон),
         ("make_local_user.py", _питон),
         ("templates/medkit.html", _шаблон)]


def main():
    всего = 0
    print("МЕСТА ЧТЕНИЯ «Во флаконе» (volume / volume_unit)")
    print("=" * 72)
    for путь, разбор in ФАЙЛЫ:
        места = разбор(путь)
        всего += len(места)
        print("  %-24s мест: %d" % (путь, len(места)))
        for н, с in места:
            print("     %5d | %s" % (н, с))
    print("")
    print("  ВСЕГО МЕСТ ЧТЕНИЯ: %d" % всего)
    print("  (объявление колонки и миграция в database.py не считаются:"
          " они уйдут вместе с полем)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
