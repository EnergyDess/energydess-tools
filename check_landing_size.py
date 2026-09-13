"""ЧТО ЛЕГЛО НА ТОМ: СЖАТЫЙ ИЛИ ИСХОДНЫЙ, И КАКОЙ ВЕС (задача 328).

ПРОВЕРКА, код 1 при беде.

ВОПРОС. Пересжатие не всегда уменьшает файл: прозрачный PNG 9 КБ давал
webp 12 КБ, уже сжатый ролик 927 КБ — 1.0 МБ. Правило владельца —
класть меньший из двух, но исходник со звуком не сравнивается (место
беззвучное), а исходник с метаданными не годится (главная публична).

МЕРКА НЕ БЕРЁТ ДАННЫЕ У ПРОВЕРЯЕМОГО КОДА. Файлы собираются здесь же
(Pillow и ffmpeg из колеса), загружаются НАСТОЯЩИМ запросом в панель
стенда, поднятого своим процессом на копии базы. Меряется то, что
ЛЕГЛО НА ТОМ, и то, что ОТДАЁТ адрес места: байты, звук в отданном
ролике, пиксель угла отданной картинки. «Сжатый вес» печатается из
ответа панели — это справка, вердикт по нему не выносится.

СЛУЧАИ И ОЖИДАНИЯ:
  png-прозрачный   маленький уже сжатый PNG декора → на томе исходник,
                   угол прозрачен
  jpeg-фото        крупный JPEG → на томе webp легче исходника
  png-метаданные   тот же PNG с текстовыми метками (автор, координаты) →
                   исходник НЕ годен, на томе webp, даже если он тяжелее
  ролик-сжатый     640 на 360, H.264 crf 30, без звука → на томе не
                   тяжелее исходника
  ролик-со-звуком  тот же со звуком → на томе без звука, даже если тяжелее

КЛЮЧИ:
  --контроль  подлог В ПАМЯТИ стенда: исходник картинки объявлен
              негодным всегда. png-прозрачный обязан лечь webp тяжелее
              исходника. Доказательство — расширение файла на томе.
"""
import io
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile

try:
    import probe_guard  # noqa: F401
except ImportError:
    pass

КОРЕНЬ = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, КОРЕНЬ)


def собрать(каталог):
    from PIL import Image, ImageDraw
    import imageio_ffmpeg
    ф = imageio_ffmpeg.get_ffmpeg_exe()
    файлы = {}

    im = Image.new("RGBA", (220, 220), (0, 0, 0, 0))
    д = ImageDraw.Draw(im)
    д.ellipse((20, 20, 200, 200), fill=(6, 182, 212, 255))
    д.ellipse((70, 70, 150, 150), fill=(0, 0, 0, 0))
    п = os.path.join(каталог, "decor.png")
    im.save(п, "PNG", optimize=True)
    файлы["png-прозрачный"] = п

    фото = Image.effect_mandelbrot((1400, 900), (-2.2, -1.2, 1.0, 1.2), 90).convert("RGB")
    п = os.path.join(каталог, "photo.jpg")
    фото.save(п, "JPEG", quality=95)
    файлы["jpeg-фото"] = п

    from PIL.PngImagePlugin import PngInfo
    метки = PngInfo()
    метки.add_text("Author", "Probe Author")
    метки.add_text("Location", "55.7558 37.6173")
    п = os.path.join(каталог, "decor_meta.png")
    im.save(п, "PNG", optimize=True, pnginfo=метки)
    файлы["png-метаданные"] = п

    п = os.path.join(каталог, "clip.mp4")
    subprocess.run([ф, "-hide_banner", "-y", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30",
                    "-t", "6", "-c:v", "libx264", "-preset", "slow", "-crf", "30",
                    "-pix_fmt", "yuv420p", "-an", "-metadata", "title=ProbeSecretTitle",
                    "-metadata", "location=+55.75+037.61/", п], capture_output=True, check=True)
    файлы["ролик-сжатый"] = п

    п = os.path.join(каталог, "clip_audio.mp4")
    subprocess.run([ф, "-hide_banner", "-y", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30",
                    "-f", "lavfi", "-i", "sine=frequency=440", "-t", "6",
                    "-c:v", "libx264", "-preset", "slow", "-crf", "30", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "12k", "-shortest", п], capture_output=True, check=True)
    файлы["ролик-со-звуком"] = п
    return файлы


def места():
    import landing_defs as ld
    декоры = [м["id"] for м in ld.МЕСТА if м["section"] == "decor"]
    проект = next(м["id"] for м in ld.МЕСТА if м["section"] == "projects")
    лента = [м["id"] for м in ld.МЕСТА if м["kind"] == ld.ВИДЕО]
    return {"png-прозрачный": декоры[0], "jpeg-фото": проект, "png-метаданные": декоры[1],
            "ролик-сжатый": лента[0], "ролик-со-звуком": лента[1]}


def звук_в(путь):
    import imageio_ffmpeg
    п = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-i", путь],
                       capture_output=True, text=True, errors="replace")
    return " Audio:" in п.stderr


def метки_и_начало(путь):
    """(метки исходника дошли до отданного, moov раньше mdat)."""
    import imageio_ffmpeg
    п = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-i", путь],
                       capture_output=True, text=True, errors="replace")
    б = open(путь, "rb").read()
    return ("ProbeSecretTitle" in п.stderr or "location" in п.stderr), б.find(b"moov") < б.find(b"mdat")


def угол_прозрачен(данные):
    from PIL import Image
    im = Image.open(io.BytesIO(данные)).convert("RGBA")
    return im.getpixel((0, 0))[3] == 0 and im.getpixel((110, 110))[3] == 0


def прогон(подлог=None):
    import httpx
    import check_upload_guard as cug
    import make_local_user as сид
    раб = tempfile.mkdtemp(prefix="probe328-")
    база = os.path.join(раб, "app.db")
    исх = sqlite3.connect(os.path.join(КОРЕНЬ, "app.db"))
    цель = sqlite3.connect(база)
    исх.backup(цель)
    исх.close()
    цель.close()
    врем = os.path.join(раб, "tmp")
    os.makedirs(врем)
    файлы = собрать(раб)
    карта = места()
    п = cug.поднять(база, врем, подлог)
    итог, плохо = {}, []
    try:
        кука = cug.войти(сид.EMAIL, сид.PASSWORD)
        with httpx.Client(base_url="http://127.0.0.1:%d" % cug.ПОРТ,
                          cookies={"access_token": кука}, timeout=600) as к:
            for случай, путь in файлы.items():
                место = карта[случай]
                тип = "video/mp4" if путь.endswith(".mp4") else (
                    "image/png" if путь.endswith(".png") else "image/jpeg")
                with open(путь, "rb") as f:
                    о = к.post("/admin/api/landing/%s" % место,
                               files={"file": (os.path.basename(путь), f, тип)})
                тело = о.json()
                с = sqlite3.connect(база)
                стр = с.execute("select version, ext, bytes from landing_media where slot_id=?",
                                (место,)).fetchone()
                с.close()
                if о.status_code != 200 or not стр:
                    плохо.append("%s: код %s %s" % (случай, о.status_code, тело.get("error")))
                    continue
                имя = "%s-%s.%s" % (место, стр[0], стр[1])
                на_томе = os.path.getsize(os.path.join(раб, "landing", имя))
                отдано = к.get("/landing-media/" + имя)
                сохр = os.path.join(раб, "served." + стр[1])
                open(сохр, "wb").write(отдано.content)
                итог[случай] = {"исходный": os.path.getsize(путь), "сжатый": тело.get("compressed"),
                                "ext": стр[1], "на_томе": на_томе, "отдано": len(отдано.content),
                                "тип": отдано.headers.get("content-type"),
                                "звук": звук_в(сохр) if стр[1] == "mp4" else None,
                                "прозрачен": угол_прозрачен(отдано.content)
                                if случай.startswith("png") else None,
                                "метки": метки_и_начало(сохр) if стр[1] == "mp4" else None,
                                "сообщение": тело.get("kept_original")}
    finally:
        п.kill()
        п.wait()
        shutil.rmtree(раб, ignore_errors=True)
    return итог, плохо


def проверить(итог, плохо):
    for случай, з in итог.items():
        print("  %-16s исходный %7.1f КБ  сжатый(панель) %-8s  на томе %-4s %7.1f КБ  "
              "отдано %7.1f КБ %s%s%s" % (
                  случай, з["исходный"] / 1024, з["сжатый"], з["ext"], з["на_томе"] / 1024,
                  з["отдано"] / 1024, з["тип"],
                  "  звук: %s" % з["звук"] if з["звук"] is not None else "",
                  "  угол прозрачен: %s" % з["прозрачен"] if з["прозрачен"] is not None else "")
              + ("  метки дошли: %s, moov в начале: %s" % з["метки"] if з.get("метки") else ""))
    ож = итог.get("png-прозрачный")
    if ож and not (ож["на_томе"] <= ож["исходный"] and ож["прозрачен"]):
        плохо.append("png-прозрачный: на томе %d байт при исходном %d, прозрачен %s"
                     % (ож["на_томе"], ож["исходный"], ож["прозрачен"]))
    ож = итог.get("jpeg-фото")
    if ож and not (ож["ext"] == "webp" and ож["на_томе"] < ож["исходный"]):
        плохо.append("jpeg-фото: на томе %s %d байт" % (ож["ext"], ож["на_томе"]))
    ож = итог.get("png-метаданные")
    if ож and not (ож["ext"] == "webp" and ож["прозрачен"]):
        плохо.append("png-метаданные: лёг %s, прозрачен %s" % (ож["ext"], ож["прозрачен"]))
    ож = итог.get("ролик-сжатый")
    if ож and ож["метки"] and (ож["метки"][0] or not ож["метки"][1]):
        плохо.append("ролик-сжатый: метки исходника дошли %s, moov в начале %s" % ож["метки"])
    if ож and not (ож["на_томе"] <= ож["исходный"] and ож["звук"] is False):
        плохо.append("ролик-сжатый: на томе %d байт при исходном %d" % (ож["на_томе"], ож["исходный"]))
    ож = итог.get("ролик-со-звуком")
    if ож and ож["звук"] is not False:
        плохо.append("ролик-со-звуком: в отданном ролике звук")
    for п in плохо:
        print("  ПЛОХ " + п)
    return плохо


def main():
    if "--контроль" in sys.argv:
        итог, плохо = прогон("import landing_media as _лм; "
                             "_лм.исходник_картинки = lambda *a, **k: (None, 'подлог')")
        плохо = проверить(итог, плохо)
        ext = итог.get("png-прозрачный", {}).get("ext")
        print("доказательство: png-прозрачный лёг как %s" % ext)
        найден = ext == "webp" and any(п.startswith("png-прозрачный") for п in плохо)
        print("КОНТРОЛЬ: %s" % ("НАЙДЕН" if найден else "НЕ НАЙДЕН"))
        return 0 if найден else 1
    итог, плохо = прогон()
    плохо = проверить(итог, плохо)
    print("ИТОГ: %s" % ("чисто" if not плохо else "БЕДА %d" % len(плохо)))
    return 1 if плохо else 0


if __name__ == "__main__":
    sys.exit(main())
