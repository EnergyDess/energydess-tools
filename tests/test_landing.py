# -*- coding: utf-8 -*-
"""МЕСТА МЕДИА ГЛАВНОЙ (BACKLOG №325).

Главное здесь — не «загрузка работает», а три немых отказа:
  1. прозрачность декора потеряна при сжатии — на тёмном фоне будет
     чёрный прямоугольник, а формат файла при этом «webp», как и ждали;
  2. картинка, поданная в место под видео, «сжата» ffmpeg в mp4 из одного
     кадра и принята молча — ffmpeg открывает PNG демультиплексором;
  3. замена оставляет прежний файл на томе — через месяц том полон.
"""

import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault(
    "DB_PATH", str(Path(tempfile.gettempdir()) / f"hh_landing_{uuid.uuid4().hex}.db"))

import main                                                    # noqa: E402
import landing_defs as ld                                      # noqa: E402
import landing_media as лм                                     # noqa: E402
import landing_store as лх                                     # noqa: E402
from auth import hash_password, create_token                   # noqa: E402
from database import SessionLocal, User, LandingMedia          # noqa: E402
from fastapi.testclient import TestClient                      # noqa: E402
from PIL import Image, ImageDraw                               # noqa: E402


def test_мест_28_и_структура_владельца():
    по = {}
    for м in ld.МЕСТА:
        по.setdefault(м["section"], []).append(м)
    assert len(ld.МЕСТА) == 28
    assert {с: len(в) for с, в in по.items()} == {"feed": 12, "projects": 9,
                                                   "portrait": 1, "decor": 4, "bg": 2}
    assert all(м["kind"] == "video" for м in по["feed"])
    # фон страницы — два ролика, верх и финал (заход 342, A1)
    assert [м["id"] for м in по["bg"]] == ["bg-top", "bg-bottom"]
    assert all(м["kind"] == "video" and not м["alpha"] for м in по["bg"])
    # лента остаётся ПЕРВЫМ видео: пробы берут «первое видео» по порядку
    assert next(м for м in ld.МЕСТА if м["kind"] == "video")["section"] == "feed"
    assert all(м["alpha"] for м in по["decor"])
    # портрет с прозрачным фоном налезает на имя (заход 339, A3)
    assert по["portrait"][0]["alpha"] and по["portrait"][0]["ratio"] == "1 / 1"
    assert len({м["id"] for м in ld.МЕСТА}) == 28


def test_путь_и_адрес_собираются_в_одном_месте():
    """Ни main.py, ни шаблоны не склеивают путь к файлу места сами."""
    корень = Path(__file__).resolve().parent.parent
    текст = (корень / "main.py").read_text(encoding="utf-8")
    assert '"/landing-media/" +' not in текст and "'/landing-media/' +" not in текст
    for шаблон in (корень / "templates").glob("*landing*.html"):
        assert "/landing-media/" not in шаблон.read_text(encoding="utf-8")
    assert лх.адрес("feed-1-1", "0123abcd", "mp4") == "/landing-media/feed-1-1-0123abcd.mp4"
    with pytest.raises(ValueError):
        лх.путь("../app.db")


@pytest.fixture()
def файлы(tmp_path):
    ff = лм.ffmpeg()
    ролик = tmp_path / "r.mp4"
    subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                    "-i", "testsrc2=size=640x480:rate=30", "-f", "lavfi", "-i",
                    "sine=frequency=440", "-t", "2", "-c:v", "libx264", "-c:a", "aac",
                    str(ролик)], check=True, timeout=120)
    png = tmp_path / "a.png"
    im = Image.new("RGBA", (800, 400), (0, 0, 0, 0))
    ImageDraw.Draw(im).ellipse((300, 50, 500, 350), fill=(200, 100, 50, 255))
    im.save(png)
    return {"ролик": str(ролик), "png": str(png)}


def test_прозрачность_декора_выживает_по_пикселю(файлы):
    готовый, св, _ = лм.обработать("decor-tl", файлы["png"], "a.png")
    with Image.open(готовый) as im:
        assert im.format == "WEBP"
        assert im.convert("RGBA").getpixel((0, 0))[3] == 0
        assert im.convert("RGBA").getpixel((im.width // 2, im.height // 2))[3] == 255
    assert св["has_alpha"] is True


def test_картинка_в_место_под_видео_отказ(файлы):
    with pytest.raises(лм.ОтказЗагрузки) as e:
        лм.обработать("feed-1-1", файлы["png"], "a.png")
    assert e.value.код == 400 and "под видео" in e.value.текст


def test_ролик_в_место_под_картинку_отказ(файлы):
    with pytest.raises(лм.ОтказЗагрузки) as e:
        лм.обработать("portrait", файлы["ролик"], "r.mp4")
    assert "под картинку" in e.value.текст


def test_ролик_без_звука_и_в_пределах(файлы):
    готовый, св, пред = лм.обработать("feed-1-1", файлы["ролик"], "r.mp4")
    вывод = subprocess.run([лм.ffmpeg(), "-hide_banner", "-i", готовый],
                           capture_output=True, text=True, errors="replace").stderr
    assert "Audio:" not in вывод and "Video: h264" in вывод
    assert св["width"] == 640 and св["height"] == 480 and пред == []


def test_предупреждение_сверх_петли_числом(файлы, monkeypatch):
    monkeypatch.setattr(ld, "ВИДЕО_ПЕТЛЯ_СЕК", 1)
    _, _, пред = лм.обработать("feed-1-1", файлы["ролик"], "r.mp4")
    assert any("2.0 с" in п and "до 1 с" in п for п in пред)


@pytest.fixture()
def клиенты(tmp_path, monkeypatch):
    # МИГРАЦИИ ОБЯЗАТЕЛЬНЫ: база общая на прогон, и файл, импортировавший
    # `main` первым, мог завести таблицы без колонок, добавленных позже.
    main.init_db()
    main.migrate_db()
    monkeypatch.setattr(лх, "КАТАЛОГ", str(tmp_path / "landing"))
    db = SessionLocal()
    м = uuid.uuid4().hex[:8]
    админ = User(email=f"adm-{м}@local.test", password_hash=hash_password("x-123456"),
                 is_verified=True, is_admin=True)
    простой = User(email=f"usr-{м}@local.test", password_hash=hash_password("x-123456"),
                   is_verified=True, is_admin=False)
    db.add_all([админ, простой])
    db.commit()
    а, п = TestClient(main.app), TestClient(main.app)
    а.cookies.set("access_token", create_token(админ.id))
    п.cookies.set("access_token", create_token(простой.id))
    db.query(LandingMedia).filter(LandingMedia.slot_id == "decor-bl").delete()
    db.commit()
    db.close()
    return а, п


def test_замена_удаляет_прежний_файл_и_посторонний_не_пишет(клиенты, файлы, tmp_path):
    админ, простой = клиенты
    о = простой.post("/admin/api/landing/decor-bl",
                     files={"file": ("a.png", open(файлы["png"], "rb"))})
    assert о.status_code == 403
    assert not os.path.isdir(лх.КАТАЛОГ) or not os.listdir(лх.КАТАЛОГ)

    о = админ.post("/admin/api/landing/decor-bl", files={"file": ("a.png", open(файлы["png"], "rb"))})
    assert о.status_code == 200, о.text
    первый = os.listdir(лх.КАТАЛОГ)
    assert len(первый) == 1

    другой = tmp_path / "b.png"
    Image.new("RGBA", (300, 300), (0, 0, 0, 0)).save(другой)
    о = админ.post("/admin/api/landing/decor-bl", files={"file": ("b.png", open(другой, "rb"))})
    assert о.status_code == 200
    второй = os.listdir(лх.КАТАЛОГ)
    assert len(второй) == 1 and второй != первый

    файл = админ.get("/landing-media/" + второй[0])
    assert файл.status_code == 200 and "immutable" in файл.headers["cache-control"]
    assert админ.get("/landing-media/" + первый[0]).status_code == 404

    assert простой.delete("/admin/api/landing/decor-bl").status_code == 403
    assert админ.delete("/admin/api/landing/decor-bl").status_code == 200
    assert os.listdir(лх.КАТАЛОГ) == []


def test_ролик_сверх_потолка_разрешения_отказ_с_числом(файлы, monkeypatch):
    """Потолок 1920 — замер памяти на машине прода (landing_defs). Здесь
    он занижен до 320, чтобы не гнать 4K в тесте: звено то же самое."""
    monkeypatch.setattr(ld, "ВИДЕО_ПОТОЛОК_СТОРОНА", 320)
    with pytest.raises(лм.ОтказЗагрузки) as e:
        лм.обработать("feed-1-1", файлы["ролик"], "r.mp4")
    assert e.value.код == 413 and "640x480" in e.value.текст and "320" in e.value.текст


def test_фон_жмётся_в_1920_лёгким_режимом_а_лента_прежним(tmp_path):
    """Параметры сжатия — по секции (заход 342, A2). Ролик 1920 в ленте
    уменьшается до 1280, в фоне остаётся 1920; команда фона несёт лёгкий
    режим кодера (пик памяти 136 МБ против 239 — замер в landing_defs)."""
    ролик = tmp_path / "wide.mp4"
    subprocess.run([лм.ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                    "-i", "testsrc2=size=1920x1080:rate=24", "-t", "1", "-c:v", "libx264",
                    "-pix_fmt", "yuv444p", str(ролик)], check=True, timeout=120)
    _, лента, _ = лм.обработать("feed-1-1", str(ролик), "wide.mp4")
    _, фон, _ = лм.обработать("bg-top", str(ролик), "wide.mp4")
    assert (лента["width"], лента["height"]) == (1280, 720)
    assert (фон["width"], фон["height"]) == (1920, 1080)
    команды = []
    настоящий = subprocess.Popen

    class Перехват(настоящий):
        def __init__(self, cmd, *a, **k):
            команды.append(list(cmd))
            super().__init__(cmd, *a, **k)
    subprocess.Popen = Перехват
    try:
        лм.сжать_ролик(str(ролик), str(tmp_path / "o1.mp4"), None, ld.ПО_ID["bg-top"])
        лм.сжать_ролик(str(ролик), str(tmp_path / "o2.mp4"), None, ld.ПО_ID["feed-1-1"])
    finally:
        subprocess.Popen = настоящий
    фон_к, лента_к = команды[0], команды[1]
    assert "rc-lookahead=0:sync-lookahead=0:bframes=0" in фон_к
    assert фон_к[фон_к.index("-crf") + 1] == "30"
    assert "-x264-params" not in лента_к and лента_к[лента_к.index("-crf") + 1] == "26"


def test_первый_кадр_ролика_снимается_отдаётся_и_уходит_с_заменой(клиенты, файлы):
    """B6: кадр из ГОТОВОГО ролика лежит рядом, отдаётся при живой строке,
    старая версия кадра после замены — 404 и на томе её нет."""
    админ, _ = клиенты
    о = админ.post("/admin/api/landing/bg-bottom",
                   files={"file": ("r.mp4", open(файлы["ролик"], "rb"))})
    assert о.status_code == 200, о.text
    первые = sorted(os.listdir(лх.КАТАЛОГ))
    кадр = [ф for ф in первые if ф.endswith(".poster.webp")]
    assert len(первые) == 2 and len(кадр) == 1
    отдан = админ.get("/landing-media/" + кадр[0])
    assert отдан.status_code == 200 and отдан.headers["content-type"] == "image/webp"
    import io
    with Image.open(io.BytesIO(отдан.content)) as im:
        assert im.size == (640, 480)
    места = {м["id"]: м for м in main.лнд_места(SessionLocal())}
    assert места["bg-bottom"]["file"]["poster"] == "/landing-media/" + кадр[0]

    другой = файлы["ролик"].replace("r.mp4", "r2.mp4")
    subprocess.run([лм.ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                    "-i", "testsrc=size=320x240:rate=25", "-t", "1", "-c:v", "libx264",
                    другой], check=True, timeout=120)
    о = админ.post("/admin/api/landing/bg-bottom", files={"file": ("r2.mp4", open(другой, "rb"))})
    assert о.status_code == 200
    вторые = sorted(os.listdir(лх.КАТАЛОГ))
    assert len(вторые) == 2 and not set(вторые) & set(первые)
    assert админ.get("/landing-media/" + кадр[0]).status_code == 404
    assert админ.delete("/admin/api/landing/bg-bottom").status_code == 200
    assert os.listdir(лх.КАТАЛОГ) == []
