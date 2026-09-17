"""ПЕРВЫЕ КАДРЫ РОЛИКОВ ЛЕНТЫ, ЗАГРУЖЕННЫХ ДО КАДРОВ (письмо 3а задачи 343).

Разовая команда. С захода 342 кадр снимается при загрузке ролика
(`landing_media.обработать`); ролики ленты на проде загружены раньше,
и кадра у них нет, а страница без кадра показывает в рамке пустоту,
пока ролик не приехал.

ТОЛЬКО МЕСТА ЛЕНТЫ (`section == "feed"`, их двенадцать). Кадр уже лежит —
не трогается: версия в имени та же, что у ролика, значит кадр от него.

`main` НЕ ИМПОРТИРУЕТСЯ (§5.8): второй процесс с `import main` на машине
прода кладёт её по памяти. Строки мест читаются голым sqlite3.

    py landing_posters.py              # снять недостающие кадры
    py landing_posters.py --проверка   # только посчитать, без записи

Код 1 — хотя бы один кадр снять не вышло; 0 — иначе."""

import os
import sqlite3
import sys
import tempfile

import landing_defs as ld
import landing_media as lm
import landing_store as хран
from database import DB_PATH

sys.stdout.reconfigure(encoding="utf-8")


def main():
    только_счёт = "--проверка" in sys.argv[1:]
    места_ленты = {м["id"] for м in ld.МЕСТА if м["section"] == "feed"}
    with sqlite3.connect(DB_PATH) as c:
        строки = c.execute("SELECT slot_id, version, ext FROM landing_media "
                           "WHERE kind = ?", (ld.ВИДЕО,)).fetchall()
    ролики = [(с, в, е) for с, в, е in строки if с in места_ленты]
    ширина = ld.ВИДЕО_СЖАТИЕ["feed"]["постер_ширина"]
    было = создано = не_вышло = нет_ролика = 0
    for slot_id, версия, ext in sorted(ролики):
        имя_кадра = хран.имя_постера(slot_id, версия)
        if os.path.exists(хран.путь(имя_кадра)):
            было += 1
            continue
        ролик = хран.путь(хран.имя_файла(slot_id, версия, ext))
        if not os.path.exists(ролик):
            нет_ролика += 1
            print("  НЕТ ФАЙЛА РОЛИКА %s — кадр снимать не с чего" % os.path.basename(ролик))
            continue
        if только_счёт:
            print("  без кадра: %s" % slot_id)
            continue
        with tempfile.TemporaryDirectory(prefix="landing-poster-") as каталог:
            готовый = lm.снять_постер(ролик, os.path.join(каталог, "poster.webp"), ширина)
            if готовый is None:
                не_вышло += 1
                print("  НЕ ВЫШЛО: %s — ffmpeg не отдал кадр" % slot_id)
                continue
            хран.положить(готовый, имя_кадра)
        создано += 1
        print("  создан: %s (%d КБ)" % (имя_кадра, os.path.getsize(хран.путь(имя_кадра)) // 1024))
    print("РОЛИКОВ ЛЕНТЫ %d: кадр уже был %d, создано %d, не вышло %d, нет файла ролика %d%s" % (
        len(ролики), было, создано, не_вышло, нет_ролика, " (только счёт)" if только_счёт else ""))
    return 1 if (не_вышло or нет_ролика) else 0


if __name__ == "__main__":
    sys.exit(main())
