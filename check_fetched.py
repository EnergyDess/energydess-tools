"""ФАЙЛ СЧИТАЕТСЯ ПОЛУЧЕННЫМ ПО РАЗМЕРУ И ЦЕЛОСТНОСТИ, А НЕ ПО КОДУ (№357).

ПРОВЕРКА, код 1 при беде, 2 — спросить нечем (файла нет).

ЗАЧЕМ. `flyctl ssh sftp get` отдал копию боевой базы в 32 КБ вместо
7.7 МБ и ЗАВЕРШИЛСЯ УСПЕХОМ: код 0, файл на месте, открывается. Дальше
на этой «копии» снимались числа — то есть замер шёл по обрубку, и
отличить его от настоящей базы было нечем. Тот же немой отказ, что
`curl` без `-f` (§6.0.1), только про содержимое.

ЧТО СПРАШИВАЕТСЯ. Размер не ниже названного минимума — и, у базы
SQLite, `PRAGMA integrity_check` плюс наличие таблиц: обрубок сплошь
и рядом «открывается», пока не спросишь схему.

    py check_fetched.py <файл> --минимум 5000000
    py check_fetched.py <копия.db> --минимум 5000000 --таблиц 40
    py check_fetched.py --контроль
"""
import os
import sqlite3
import sys

import probe_guard  # noqa: F401 — внешний отказ говорится словом (§3)


def проверить(путь, минимум=0, таблиц=0):
    if not os.path.exists(путь):
        print("НЕ ПРОВЕРЕНО: файла %s нет" % путь)
        return 2
    байт = os.path.getsize(путь)
    print("  %s: %d байт (%.1f МБ)" % (os.path.basename(путь), байт,
                                       байт / 1048576.0))
    беды = []
    if минимум and байт < минимум:
        беды.append("размер %d меньше минимума %d — файл получен НЕ ЦЕЛИКОМ"
                    % (байт, минимум))
    if путь.endswith((".db", ".sqlite", ".sqlite3")):
        с = None
        try:
            с = sqlite3.connect("file:%s?mode=ro" % путь.replace("?", ""),
                                uri=True)
            итог = с.execute("PRAGMA integrity_check").fetchone()[0]
            число = с.execute("SELECT COUNT(*) FROM sqlite_master "
                              "WHERE type='table'").fetchone()[0]
            print("  integrity_check: %s, таблиц %d" % (итог, число))
            if итог != "ok":
                беды.append("integrity_check: %s" % итог)
            if таблиц and число < таблиц:
                беды.append("таблиц %d меньше ожидаемых %d" % (число, таблиц))
        except sqlite3.DatabaseError as e:
            беды.append("SQLite не читает файл: %s" % e)
        finally:
            # ЗАКРЫВАЕТСЯ ВСЕГДА: на обрубке запрос падает, и без этого
            # файл остаётся занят — уборка контроля валилась PermissionError
            if с is not None:
                с.close()
    print("ИТОГ: %s" % ("получен целиком" if not беды else "; ".join(беды)))
    return 1 if беды else 0


def контроль():
    """ПОДЛОГ: обрубок обязан быть отвергнут, целый файл — принят.

    Вторая половина обязательна: проверка, отвергающая всё подряд,
    прошла бы первую и не значила бы ничего (§6.0.3).
    """
    import tempfile
    каталог = tempfile.mkdtemp(prefix="fetched-")
    целый = os.path.join(каталог, "целый.db")
    с = sqlite3.connect(целый)
    с.execute("CREATE TABLE t (a INTEGER)")
    с.executemany("INSERT INTO t VALUES (?)", [(i,) for i in range(20000)])
    с.commit()
    с.close()
    полный = os.path.getsize(целый)
    обрубок = os.path.join(каталог, "обрубок.db")
    with open(целый, "rb") as и, open(обрубок, "wb") as о:
        о.write(и.read(полный // 40))
    print("  доказательство: целый %d байт, обрубок %d"
          % (полный, os.path.getsize(обрубок)))
    к1 = проверить(обрубок, минимум=полный)
    к2 = проверить(целый, минимум=полный, таблиц=1)
    for ф in (целый, обрубок):
        os.remove(ф)
    os.rmdir(каталог)
    print("КОНТРОЛЬ: обрубок → %s, целый → %s"
          % ("ЛОВИТ" if к1 == 1 else "НЕ ЛОВИТ",
             "прошёл" if к2 == 0 else "ОТВЕРГНУТ (ложная находка)"))
    return 0 if (к1 == 1 and к2 == 0) else 1


if __name__ == "__main__":
    for _п in (sys.stdout, sys.stderr):
        try:
            _п.reconfigure(encoding="utf-8")
        except AttributeError:
            pass
    if "--контроль" in sys.argv:
        sys.exit(контроль())
    имена = [а for а in sys.argv[1:] if not а.startswith("--")]
    ключи = {а: sys.argv[sys.argv.index(а) + 1]
             for а in ("--минимум", "--таблиц") if а in sys.argv}
    for а in ключи.values():
        if а in имена:
            имена.remove(а)
    if not имена:
        sys.exit("нужен путь к файлу: py check_fetched.py <файл> --минимум N")
    sys.exit(проверить(имена[0], int(ключи.get("--минимум", 0)),
                       int(ключи.get("--таблиц", 0))))
