# -*- coding: utf-8 -*-
"""
Перенос вложений из base64 в базе в файлы на томе (BACKLOG №20).

Зачем. `chat_messages.image_data` и `body_photos.image_data` хранят картинку
как data URL прямо в базе. Base64 раздувает объём на треть, а главное —
каждая картинка попадает в КАЖДЫЙ ежедневный архив, уезжающий в Telegram.
Для снимков тела это худший вариант из возможных.

Переносим КАК ЕСТЬ, без пересохранения. Проверка 2026-07-31 показала:
EXIF у всех вложений пуст (их уже обработал `_upright_jpeg` при загрузке),
а 8 из 10 — скриншоты карточек товара с мелким текстом состава и КБЖУ.
Второе поколение JPEG поверх первого испортило бы именно этот текст,
ничего не дав взамен: чистить нечего, уменьшать нечего.

Три шага, между ними жёсткий барьер:

    python migrate_media.py --pass1     # пишет файлы, НИЧЕГО не удаляет
    python migrate_media.py --verify    # четыре проверки, без записи
    python migrate_media.py --pass2     # обнуляет image_data и делает VACUUM

`--pass2` сам вызывает проверку и отказывается работать, если она не прошла.
Это не вежливость к оператору, а условие: между проходами существует ровно
один момент, когда данные есть и в базе, и в файлах, — и именно в нём
проверка имеет смысл.

Идемпотентно: записи с заполненным `image_path` пропускаются, повторный
запуск любого шага безопасен.
"""
import argparse
import base64
import hashlib
import io
import os
import secrets
import sqlite3
import sys

ТАБЛИЦЫ = {"chat": "chat_messages", "body": "body_photos"}


def _db():
    return os.getenv("DB_PATH", "./app.db")


def _корень():
    return os.path.join(os.path.dirname(_db()) or ".", "media")


def _путь(вид, user_id, токен):
    return os.path.join(_корень(), вид, str(int(user_id)), токен + ".jpg")


def _раскодировать(data_url):
    """data URL → байты. None, если строка не похожа на картинку."""
    if not data_url or "," not in data_url:
        return None
    try:
        return base64.b64decode(data_url.split(",", 1)[1])
    except Exception:
        return None


def проход1():
    conn = sqlite3.connect(_db())
    всего = перенесено = пропущено = сбоев = 0
    try:
        for вид, таблица in ТАБЛИЦЫ.items():
            строки = conn.execute(
                "SELECT id, user_id, image_data, image_path FROM %s "
                "WHERE image_data IS NOT NULL" % таблица).fetchall()
            for rid, uid, data_url, уже in строки:
                всего += 1
                if уже:
                    пропущено += 1      # идемпотентность: перенос уже был
                    continue
                сырое = _раскодировать(data_url)
                if not сырое:
                    print("  СБОЙ %s id=%s: image_data не раскодировался" % (таблица, rid))
                    сбоев += 1
                    continue
                токен = secrets.token_urlsafe(16)
                путь = _путь(вид, uid, токен)
                os.makedirs(os.path.dirname(путь), exist_ok=True)
                with open(путь, "wb") as f:
                    f.write(сырое)
                # Пишем путь ТОЛЬКО после того, как файл лёг на диск:
                # порядок наоборот дал бы запись, ссылающуюся в пустоту
                conn.execute("UPDATE %s SET image_path = ? WHERE id = ?" % таблица,
                             (токен, rid))
                conn.commit()
                перенесено += 1
                print("  %s id=%s → %s (%d КБ)" % (таблица, rid, токен, len(сырое) // 1024))
    finally:
        conn.close()

    print("")
    print("Проход 1: записей с image_data %d, перенесено %d, пропущено %d, сбоев %d"
          % (всего, перенесено, пропущено, сбоев))
    print("image_data НЕ трогался — откат сводится к удалению файлов")
    return 1 if сбоев else 0


def проверить(тихо=False):
    """Четыре проверки. Возвращает 0, если сошлось всё.

    Существование файла как критерий не годится — оно не доказывает,
    что внутри лежит то самое. Поэтому основная проверка это sha256,
    а остальные ловят ошибки не в данных, а в самой процедуре.
    """
    conn = sqlite3.connect(_db())
    провалов = проверено = 0
    файлов_на_диске = 0
    try:
        for вид, таблица in ТАБЛИЦЫ.items():
            строки = conn.execute(
                "SELECT id, user_id, image_data, image_path FROM %s "
                "WHERE image_data IS NOT NULL" % таблица).fetchall()
            for rid, uid, data_url, токен in строки:
                проверено += 1
                метка = "%s id=%s" % (таблица, rid)
                if not токен:
                    print("  ПРОВАЛ %s: image_path пуст — запись не перенесена" % метка)
                    провалов += 1
                    continue
                путь = _путь(вид, uid, токен)
                if not os.path.exists(путь):
                    print("  ПРОВАЛ %s: файла нет — %s" % (метка, путь))
                    провалов += 1
                    continue
                ожидалось = _раскодировать(data_url)
                на_диске = open(путь, "rb").read()

                # 1. Побайтовое совпадение. Работает именно потому, что мы
                #    ничего не пересохраняем: трансформируй мы файл — хеши
                #    разошлись бы по определению
                if hashlib.sha256(на_диске).hexdigest() != hashlib.sha256(ожидалось).hexdigest():
                    print("  ПРОВАЛ %s: sha256 не совпал" % метка)
                    провалов += 1
                    continue
                # 2. Размер на файловой системе
                if os.path.getsize(путь) != len(ожидалось):
                    print("  ПРОВАЛ %s: размер %d вместо %d"
                          % (метка, os.path.getsize(путь), len(ожидалось)))
                    провалов += 1
                    continue
                # 3. Файл открывается как изображение, и кадр тот же
                try:
                    from PIL import Image
                    было = Image.open(io.BytesIO(ожидалось))
                    стало = Image.open(путь)
                    стало.load()
                    if было.size != стало.size:
                        print("  ПРОВАЛ %s: размер кадра %s вместо %s"
                              % (метка, стало.size, было.size))
                        провалов += 1
                        continue
                except Exception as e:
                    print("  ПРОВАЛ %s: файл не открывается — %s: %s"
                          % (метка, type(e).__name__, e))
                    провалов += 1
                    continue
                if not тихо:
                    print("  OK %s: sha256 совпал, %s, %d КБ"
                          % (метка, стало.size, len(на_диске) // 1024))

            # 4. Лишних файлов на диске быть не должно
            for корень, _, файлы in os.walk(os.path.join(_корень(), вид)):
                файлов_на_диске += len(файлы)

        с_путём = sum(
            conn.execute("SELECT COUNT(*) FROM %s WHERE image_path IS NOT NULL"
                         % т).fetchone()[0] for т in ТАБЛИЦЫ.values())
    finally:
        conn.close()

    print("")
    print("Проверено записей: %d, провалов: %d" % (проверено, провалов))
    print("Файлов на диске: %d, записей с image_path: %d" % (файлов_на_диске, с_путём))
    if файлов_на_диске != с_путём:
        print("  ПРОВАЛ: число файлов не равно числу записей")
        провалов += 1

    if провалов:
        print("")
        print("ПРОВЕРКА НЕ ПРОШЛА. Проход 2 запускать нельзя.")
        return 1
    print("Проверка пройдена полностью.")
    return 0


def проход2():
    # Барьер: сначала проверка, и только если она чистая — запись
    print("Перед очисткой прогоняем проверку.")
    if проверить(тихо=True) != 0:
        print("")
        print("ОСТАНОВЛЕНО: image_data не тронут.")
        return 1

    conn = sqlite3.connect(_db())
    try:
        было = os.path.getsize(_db())
        обнулено = 0
        conn.execute("BEGIN")
        for таблица in ТАБЛИЦЫ.values():
            cur = conn.execute(
                "UPDATE %s SET image_data = NULL "
                "WHERE image_data IS NOT NULL AND image_path IS NOT NULL" % таблица)
            обнулено += cur.rowcount
        conn.commit()
        # VACUUM вне транзакции — SQLite иначе откажет. Без него
        # освободившиеся страницы остались бы в файле, и весь смысл
        # переноса (размер архива) не изменился бы
        conn.execute("VACUUM")
    finally:
        conn.close()

    стало = os.path.getsize(_db())
    print("")
    print("Проход 2: обнулено записей %d" % обнулено)
    print("База: %d → %d байт (−%d, %.1f%%)"
          % (было, стало, было - стало, 100 * (было - стало) / было))
    return 0


def main():
    p = argparse.ArgumentParser(description="Перенос вложений из base64 в файлы")
    p.add_argument("--pass1", action="store_true", help="записать файлы, ничего не удаляя")
    p.add_argument("--verify", action="store_true", help="проверить перенос, без записи")
    p.add_argument("--pass2", action="store_true", help="обнулить image_data и сжать базу")
    a = p.parse_args()
    if a.pass1:
        return проход1()
    if a.verify:
        return проверить()
    if a.pass2:
        return проход2()
    p.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
