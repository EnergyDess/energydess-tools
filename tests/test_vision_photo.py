# -*- coding: utf-8 -*-
"""ФОТО НА ПУТИ В МОДЕЛЬ: уменьшение и потолок размера.

Задача 171. Снимок с камеры Android — 12–108 Мпикс и до десяти
мегабайт; у машины прода 256 МБ (`fly.toml`). Здесь проверяется
то, что можно спросить без браузера и без стенда:

  · `_upright_jpeg` уменьшает кадр ЛЮБОГО разрешения и не раскрывает
    его целиком (иначе 50 Мпикс просят +383 МБ);
  · причина отказа ПЕЧАТАЕТСЯ, а не проглатывается;
  · `_call_vision` не отправляет картинку сверх `VISION_IMAGE_MAX_MB`.

Живой путь целиком — `check_medkit_photo.py` (§6.3): ему нужны
поднятое приложение и потолок памяти, то есть в pytest ему не место.
"""
import asyncio
import io
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DB_PATH", os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app.db"))

import main  # noqa: E402


def _кадр(w, h, формат="JPEG"):
    """Кадр, сжимающийся как фотография: ровная заливка ужалась бы
    в десяток килобайт и не воспроизвела бы стоимости раскодирования."""
    import random
    from PIL import Image
    rnd = random.Random(20260825)
    плитка = Image.new("RGB", (200, 150))
    плитка.putdata([(rnd.randint(60, 210),) * 3 for _ in range(200 * 150)])
    им = плитка.resize((w, h), Image.BILINEAR)
    buf = io.BytesIO()
    им.save(buf, format=формат, **({"quality": 90} if формат == "JPEG" else {}))
    return buf.getvalue()


@pytest.mark.parametrize("w,h", [(4000, 3000), (8160, 6120), (12000, 9000)])
def test_снимок_камеры_ужимается_до_потолка(w, h):
    """Кадр любого разрешения выходит не больше 1920 по длинной стороне."""
    from PIL import Image
    готово = main._upright_jpeg(_кадр(w, h))
    assert готово is not None, "кадр не пересобрался"
    им = Image.open(io.BytesIO(готово))
    assert max(им.width, им.height) <= 1920
    # И ВЕСИТ он не как оригинал: именно вес уезжает в модель
    assert len(готово) < 1024 * 1024, f"вышло {len(готово) // 1024} КБ"


def test_draft_стоит_ДО_раскрытия_кадра():
    """`draft()` обязан стоять ВЫШЕ `convert("RGB")`.

    Это не вкус, а единственное, что отличает +55 МБ от +826 МБ
    на 108 Мпикс: `draft()` умеет только то, что ещё не раскодировано,
    и после `convert()` он пустая операция. Проверяется ПОРЯДОК
    в исходнике, потому что результат у обоих вариантов одинаковый —
    расходится только память, а её в pytest не померить.
    """
    import inspect
    # СТРОКИ КОДА, а не текст целиком: `convert("RGB")` упомянут ещё
    # и в комментарии ВЫШЕ draft(), и сравнение по сырому тексту дало бы
    # ложный провал на исправном коде — поймано первым же прогоном
    строки = [л.split("#")[0].strip()
              for л in inspect.getsource(main._upright_jpeg).splitlines()]
    строки = [л for л in строки if л]
    где_draft = [i for i, л in enumerate(строки) if '.draft("RGB"' in л]
    где_convert = [i for i, л in enumerate(строки) if '.convert("RGB")' in л]
    assert где_draft, "draft() пропал — вернётся +826 МБ на 108 Мпикс"
    assert где_convert, "convert() пропал — кадр не приводится к RGB"
    assert где_draft[0] < где_convert[0], (
        "draft() ниже convert() — то есть не работает вовсе")


def test_причина_отказа_печатается(capsys):
    """Голое `return None` отправляло вызывающего на запасной путь
    «шлём оригинал», и отличить «не картинка» от «не хватило памяти»
    было нечем (§6.0.1)."""
    # §6.0: в bytes-литерале только ASCII. Кириллица здесь —
    # SyntaxError, и правило поймало само себя при написании теста
    assert main._upright_jpeg(b"\x00\x01\x02 not an image") is None
    напечатано = capsys.readouterr().out
    assert "[image]" in напечатано
    assert "пересобрать не вышло" in напечатано


def test_картинка_сверх_потолка_НЕ_уходит_в_модель():
    """Единственная точка отправки отказывает ДО обращения к сервису.

    Сюда картинка попадает запасным путём `_for_vision`: пересобрать
    не вышло — шлём оригинал как есть. Замер 2026-08-25: 108 Мпикс
    уходили в модель оригиналом на 9898 КБ, и сервис отвечал отказом,
    которого человек объяснить не мог.
    """
    import base64
    великан = base64.b64encode(
        b"x" * int((main.VISION_IMAGE_MAX_MB + 1) * 1048576)).decode()
    with pytest.raises(RuntimeError) as беда:
        asyncio.run(main._call_vision(великан, "image/jpeg", "разбери"))
    текст = str(беда.value)
    assert "слишком большой" in текст
    # ТЕКСТ ГОВОРИТ, ЧТО ДЕЛАТЬ. «Ошибка ИИ (400)» не говорит ничего
    assert "заново" in текст or "руками" in текст


def test_картинка_в_пределах_потолка_проверку_проходит(monkeypatch):
    """Отрицательная половина: заслон не должен резать нормальный кадр.

    Без неё «отказывает всегда» выглядело бы как «отказывает верно».

    АДРЕС ПОДМЕНЁН НА ЗАВЕДОМО ЗАКРЫТЫЙ ПОРТ, и это не удобство.
    Первая версия звала настоящий OpenRouter — ключ в окружении есть —
    и падала с «DID NOT RAISE»: вызов УСПЕВАЛ, то есть тест ходил
    в чужой сервис за деньги и зависел от его настроения. Теперь
    признаком «заслон пропустил» служит ошибка СЕТИ: до неё доходит
    только то, что заслон не остановил.
    """
    import base64
    monkeypatch.setattr(main, "OPENROUTER_URL",
                        "http://127.0.0.1:9/v1/chat/completions")
    обычная = base64.b64encode(_кадр(1920, 1440)).decode()
    assert len(обычная) * 3 / 4 < main.VISION_IMAGE_MAX_MB * 1048576
    with pytest.raises(Exception) as беда:
        asyncio.run(main._call_vision(обычная, "image/jpeg", "разбери"))
    assert "слишком большой" not in str(беда.value)


def test_потолок_объявлен_ИМЕНЕМ_а_не_числом_на_месте():
    """Число на месте вызова нельзя ни грепнуть, ни поменять
    окружением — то же правило, что у потолков ответа (§2.1)."""
    import inspect
    текст = inspect.getsource(main._call_vision)
    assert "VISION_IMAGE_MAX_MB" in текст
    assert isinstance(main.VISION_IMAGE_MAX_MB, float)


def test_потолок_загрузки_объявлен_и_применён():
    """Эндпоинт разбора фото не принимает произвольный объём.

    У загрузки картинки Enshrouded такой потолок был с самого начала
    (`ENS_MAX_UPLOAD`), у разбора фото — ни одного, при том что дальше
    кадр раскрывается в память машины на 256 МБ.
    """
    import inspect
    assert isinstance(main.PHOTO_MAX_UPLOAD_MB, float)
    текст = inspect.getsource(main.medkit_assist)
    assert "PHOTO_MAX_UPLOAD_MB" in текст, "потолок объявлен, но не применён"
    assert "413" in текст, "отказ по размеру обязан быть 413, а не 400"
    # ЗАПАС НАЗВАН: потолок не должен резать настоящую фотографию.
    # Самый тяжёлый реальный случай — 108 Мпикс, это ~10 МБ
    assert main.PHOTO_MAX_UPLOAD_MB >= 15
