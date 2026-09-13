# -*- coding: utf-8 -*-
"""РАЗБОР И СЖАТИЕ ФАЙЛОВ ДЛЯ МЕСТ ГЛАВНОЙ (BACKLOG №325, блок D4–D6).

ВСЁ ЗДЕСЬ СИНХРОННОЕ И ТЯЖЁЛОЕ, и зовётся только через `_в_потоке`:
сжатие ролика на одном vCPU — это секунды, и цикл событий всё это время
не отвечал бы никому, включая /health, по которому Fly решает, жива ли
машина (§6.0.5, проверка 11).

РОД ФАЙЛА ОПРЕДЕЛЯЕТСЯ СОДЕРЖИМЫМ, А НЕ РАСШИРЕНИЕМ И НЕ ЗАГОЛОВКОМ.
И то и другое пишет клиент. Картинка опознаётся тем, что её открыл
Pillow; ролик — тем, что ffmpeg нашёл в нём видеопоток длительностью
больше одного кадра. Картинку ffmpeg тоже откроет — демультиплексором
`png_pipe`, `image2` и им подобными, — поэтому такие демультиплексоры
роликом НЕ СЧИТАЮТСЯ: иначе PNG, поданный в место под видео, был бы
«сжат» в mp4 из одного кадра и принят молча (§6.0).

FFMPEG — ИЗ КОЛЕСА `imageio-ffmpeg`, а не из системы. В образе
`python:3.12-slim` ffmpeg нет, а `apt-get install ffmpeg` тянет сотни
мегабайт зависимостей; колесо для Linux — 29 МБ со статическим бинарником
и libx264 внутри (замер 2026-09-13). Тот же бинарник у разработчика
и на проде — один путь кода.
"""

import hashlib
import os
import re
import subprocess
import tempfile
import threading
import time

from PIL import Image, ImageOps, UnidentifiedImageError

import landing_defs as ld


class ОтказЗагрузки(Exception):
    """Файл не принят. Текст — для человека, с числом там, где оно есть."""

    def __init__(self, текст, код=400):
        super().__init__(текст)
        self.текст = текст
        self.код = код


def ffmpeg():
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


# Демультиплексоры, которыми ffmpeg открывает НЕПОДВИЖНУЮ картинку.
# Признак — «картинка», а не перечень расширений: `_pipe`-демультиплексоры
# у ffmpeg заведены ровно под одиночные изображения.
_ДЕМУКС_КАРТИНКИ = re.compile(r"(^|,)(image2|[a-z0-9]+_pipe|gif|apng)(,|$)")


def разобрать_ролик(путь):
    """{'format', 'duration', 'width', 'height'} по выводу `ffmpeg -i`.

    ffprobe в колесе нет, поэтому читается ЗАГОЛОВОК, который ffmpeg
    печатает при открытии файла; сам поток при этом не декодируется —
    это миллисекунды, а не прогон всего ролика."""
    п = subprocess.run([ffmpeg(), "-hide_banner", "-nostdin", "-i", путь],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=60)
    вывод = п.stderr
    итог = {"format": None, "duration": None, "width": None, "height": None}
    м = re.search(r"Input #0, ([^ ]+), from", вывод)
    if м:
        итог["format"] = м.group(1).rstrip(",")
    м = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", вывод)
    if м:
        итог["duration"] = (int(м.group(1)) * 3600 + int(м.group(2)) * 60
                            + float(м.group(3)))
    # Первая строка видеопотока. Размер — первая пара «ЧИСЛОxЧИСЛО» после
    # слова Video, не шестнадцатеричный код вида 0x31637661.
    м = re.search(r"Stream #0:\d+[^\n]*?: Video: [^\n]*?(\d{2,5})x(\d{2,5})", вывод)
    if м:
        итог["width"], итог["height"] = int(м.group(1)), int(м.group(2))
    return итог


def _это_ролик(разбор):
    return (разбор["width"] is not None and разбор["format"] is not None
            and not _ДЕМУКС_КАРТИНКИ.search(разбор["format"])
            and (разбор["duration"] or 0) >= 0.3)


def _это_картинка(путь):
    try:
        with Image.open(путь) as im:
            im.verify()
        return True
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError):
        return False


def _версия(путь):
    h = hashlib.sha256()
    with open(путь, "rb") as f:
        for кус in iter(lambda: f.read(1 << 20), b""):
            h.update(кус)
    return h.hexdigest()[:8]


def _мб(n):
    return n / 1024 / 1024


def _пик_памяти(pid, стоп, итог):
    """Пик резидентной памяти процесса ffmpeg по /proc (только Linux).

    Меряется, а не предполагается: машина прода — 512 МБ на всё,
    и приложение занимает из них больше сотни (§5.8)."""
    файл = "/proc/%d/status" % pid
    while not стоп.is_set():
        try:
            with open(файл) as f:
                for строка in f:
                    if строка.startswith("VmHWM:"):
                        итог[0] = max(итог[0], int(строка.split()[1]) // 1024)
        except OSError:
            return
        time.sleep(0.1)


def сжать_ролик(вход, выход):
    """Беззвучный mp4 H.264, длинная сторона не больше предела, до 30 к/с.

    `-threads 1` и `nice 19`: машина прода — один vCPU, и сжатие не имеет
    права отнять процессор у приложения, отвечающего на запросы."""
    д = ld.ВИДЕО_ДЛИННАЯ_СТОРОНА
    масштаб = ("scale=w=if(gte(iw\\,ih)\\,trunc(min(%d\\,iw)/2)*2\\,-2)"
               ":h=if(gte(iw\\,ih)\\,-2\\,trunc(min(%d\\,ih)/2)*2)" % (д, д))
    команда = [ffmpeg(), "-hide_banner", "-nostdin", "-y", "-i", вход,
               "-map", "0:v:0", "-an", "-sn", "-dn", "-map_metadata", "-1",
               "-vf", масштаб, "-fpsmax", "30",
               "-c:v", "libx264", "-preset", "medium", "-crf", "26",
               "-pix_fmt", "yuv420p", "-profile:v", "high",
               "-movflags", "+faststart", "-threads", "1", выход]
    доп = {}
    if os.name == "posix":
        доп["preexec_fn"] = lambda: os.nice(19)
    п = subprocess.Popen(команда, stdout=subprocess.DEVNULL,
                         stderr=subprocess.PIPE, **доп)
    пик = [0]
    стоп = threading.Event()
    если_linux = os.path.exists("/proc/%d/status" % п.pid)
    if если_linux:
        threading.Thread(target=_пик_памяти, args=(п.pid, стоп, пик),
                         daemon=True).start()
    try:
        _, ошибки = п.communicate(timeout=300)
    except subprocess.TimeoutExpired:
        п.kill()
        п.communicate()
        raise ОтказЗагрузки("Сжатие ролика не уложилось в 300 с — "
                            "ролик слишком длинный или тяжёлый", 413)
    finally:
        стоп.set()
    if п.returncode != 0 or not os.path.exists(выход):
        хвост = (ошибки or b"").decode("utf-8", "replace").strip().splitlines()[-1:]
        raise ОтказЗагрузки("ffmpeg не смог сжать ролик: %s"
                            % (хвост[0] if хвост else "код %d" % п.returncode), 400)
    return пик[0] if если_linux else None


def _есть_прозрачность(im):
    if im.mode not in ("RGBA", "LA"):
        return False
    return im.getchannel("A").getextrema()[0] < 255


def сжать_картинку(вход, выход, место):
    """webp, длинная сторона не больше предела секции, прозрачность цела.

    `draft` ПЕРВЫМ ДЕЙСТВИЕМ: у JPEG он уменьшает при раскодировании,
    а после `convert` уже не работает — ровно на этом порядке прод
    получал 502 от снимка с телефона (§5.8)."""
    предел = ld.КАРТИНКА_ДЛИННАЯ_СТОРОНА[место["section"]]
    with Image.open(вход) as im:
        im.draft("RGB", (предел, предел))
        im = ImageOps.exif_transpose(im)
        if getattr(im, "n_frames", 1) > 1:
            im.seek(0)
        прозрачна = im.mode in ("RGBA", "LA", "PA") or "transparency" in im.info
        im = im.convert("RGBA" if прозрачна else "RGB")
        im.thumbnail((предел, предел), Image.LANCZOS)
        альфа = _есть_прозрачность(im)
        if not альфа and im.mode == "RGBA":
            im = im.convert("RGB")
        параметры = {"quality": 86, "method": 6}
        if альфа:
            # Прозрачность ЛОСЛЕСС при сжатом цвете: край объекта
            # на почти чёрном фоне виден сразу, а цвет прощает 86.
            параметры["alpha_quality"] = 100
            параметры["exact"] = False
        im.save(выход, "WEBP", **параметры)
        return im.width, im.height, альфа


def обработать(место_id, временный, исходное_имя):
    """Готовит файл для места. Возвращает (путь_готового, сведения, предупреждения).

    Бросает `ОтказЗагрузки` — с числом там, где оно есть."""
    место = ld.ПО_ID.get(место_id)
    if место is None:
        raise ОтказЗагрузки("Такого места на странице нет", 404)
    исходный_вес = os.path.getsize(временный)
    предупреждения = []
    каталог = tempfile.mkdtemp(prefix="landing-")

    if место["kind"] == ld.ВИДЕО:
        if исходный_вес > ld.ВИДЕО_ПОТОЛОК_МБ * 1024 * 1024:
            raise ОтказЗагрузки("Ролик весит %.1f МБ при потолке %d МБ — не принят"
                                % (_мб(исходный_вес), ld.ВИДЕО_ПОТОЛОК_МБ), 413)
        разбор = разобрать_ролик(временный)
        if not _это_ролик(разбор):
            if _это_картинка(временный):
                raise ОтказЗагрузки("Это картинка, а место «%s» — под видео"
                                    % место["label"], 400)
            raise ОтказЗагрузки("Файл не распознан как видео — место «%s» "
                                "принимает только ролики" % место["label"], 400)
        if разбор["duration"] > ld.ВИДЕО_ПОТОЛОК_СЕК:
            raise ОтказЗагрузки("Ролик идёт %.1f с при потолке %d с — не принят"
                                % (разбор["duration"], ld.ВИДЕО_ПОТОЛОК_СЕК), 413)
        готовый = os.path.join(каталог, "out.mp4")
        пик = сжать_ролик(временный, готовый)
        итог = разобрать_ролик(готовый)
        сведения = {"kind": ld.ВИДЕО, "ext": "mp4",
                    "width": итог["width"], "height": итог["height"],
                    "duration_sec": round(итог["duration"] or разбор["duration"], 2),
                    "has_alpha": False, "peak_mb": пик}
        if сведения["duration_sec"] > ld.ВИДЕО_ПЕТЛЯ_СЕК:
            предупреждения.append("Петля идёт %.1f с — разумная до %d с"
                                  % (сведения["duration_sec"], ld.ВИДЕО_ПЕТЛЯ_СЕК))
        вес = os.path.getsize(готовый)
        if вес > ld.ВИДЕО_ИТОГ_МБ * 1024 * 1024:
            предупреждения.append("После сжатия %.1f МБ — для ленты разумно до %d МБ"
                                  % (_мб(вес), ld.ВИДЕО_ИТОГ_МБ))
    else:
        if исходный_вес > ld.КАРТИНКА_ПОТОЛОК_МБ * 1024 * 1024:
            raise ОтказЗагрузки("Картинка весит %.1f МБ при потолке %d МБ — не принята"
                                % (_мб(исходный_вес), ld.КАРТИНКА_ПОТОЛОК_МБ), 413)
        if not _это_картинка(временный):
            if _это_ролик(разобрать_ролик(временный)):
                raise ОтказЗагрузки("Это видео, а место «%s» — под картинку"
                                    % место["label"], 400)
            raise ОтказЗагрузки("Файл не распознан как картинка — место «%s» "
                                "принимает jpg, png, webp" % место["label"], 400)
        готовый = os.path.join(каталог, "out.webp")
        try:
            ш, в, альфа = сжать_картинку(временный, готовый, место)
        except (OSError, ValueError, Image.DecompressionBombError) as e:
            raise ОтказЗагрузки("Картинку не удалось разобрать: %s"
                                % type(e).__name__, 400)
        сведения = {"kind": ld.КАРТИНКА, "ext": "webp", "width": ш, "height": в,
                    "duration_sec": None, "has_alpha": альфа, "peak_mb": None}
        if место["alpha"] and not альфа:
            предупреждения.append("У декоративного объекта нет прозрачности — "
                                  "на тёмном фоне будет виден прямоугольник")
        вес = os.path.getsize(готовый)
        if вес > ld.КАРТИНКА_ИТОГ_КБ * 1024:
            предупреждения.append("После сжатия %d КБ — разумно до %d КБ"
                                  % (вес // 1024, ld.КАРТИНКА_ИТОГ_КБ))

    сведения.update({"bytes": os.path.getsize(готовый),
                     "version": _версия(готовый),
                     "original_name": (исходное_имя or "")[:200],
                     "original_bytes": исходный_вес})
    return готовый, сведения, предупреждения
