"""Версия статики в адресе и Cache-Control (BACKLOG.md, задача 77).

Почему на это есть тесты. Отказ немой и выглядит как успех: правка CSS
выкачена, файл на сервере новый, замер на сервере чистый — а браузер
рисует старым файлом, консоль пуста. Проверить глазами нельзя вообще:
разница видна только в заголовке ответа и в адресе.

Главное, что здесь проверяется, — не «immutable ставится», а обратное:
что он НЕ ставится там, где адрес своё содержимое не называет. Потолок
в год на неверсированном адресе заморозил бы файл у пользователя
на год, и починить это было бы нечем.
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("AGENT_WEBHOOK_KEY", "test-key-8f3a91")

import main


def test_версия_это_восемь_знаков_от_содержимого():
    в = main.версия_статики("style.css")
    assert len(в) == 8
    assert all(c in "0123456789abcdef" for c in в)


def test_версия_меняется_вместе_с_содержимым(tmp_path):
    файл = Path("static") / "_proba_versii.css"
    файл.write_text("a{color:red}", encoding="utf-8")
    try:
        первая = main.версия_статики("_proba_versii.css")
        файл.write_text("a{color:blue}", encoding="utf-8")
        вторая = main.версия_статики("_proba_versii.css")
        assert первая != вторая
        # и возвращается обратно: отпечаток от СОДЕРЖИМОГО, а не от времени
        файл.write_text("a{color:red}", encoding="utf-8")
        assert main.версия_статики("_proba_versii.css") == первая
    finally:
        файл.unlink(missing_ok=True)


def test_адрес_несёт_версию():
    адрес = main.статика("style.css")
    assert адрес.startswith("/static/style.css?v=")
    assert адрес.endswith(main.версия_статики("style.css"))


def test_пропавший_файл_не_молчит(capsys):
    """Адрес без версии — законный ответ, но о причине должно быть сказано."""
    адрес = main.статика("нет-такого-файла.css")
    assert адрес == "/static/нет-такого-файла.css"
    assert "[static]" in capsys.readouterr().out


def test_верная_версия_кешируется_навсегда():
    в = main.версия_статики("style.css")
    заголовок = main._кеш_статики("/static/style.css", в)
    assert "immutable" in заголовок
    assert f"max-age={main.СТАТИКА_ГОД}" in заголовок


@pytest.mark.parametrize("версия", ["", "deadbeef", "00000000"])
def test_чужая_или_отсутствующая_версия_НЕ_замораживает(версия):
    """Главная защита: адрес, не называющий содержимое, вечным не бывает."""
    for файл in ("/static/style.css", "/static/ui.js", "/static/hh.css"):
        заголовок = main._кеш_статики(файл, версия)
        assert заголовок == "no-cache", (файл, версия, заголовок)
        assert "immutable" not in заголовок


def test_картинки_кешируются_сутками_а_не_годом():
    """Ревалидация 1746 картинок упражнений на каждой странице не нужна,
    но и год им не даём: их правят заменой файла."""
    for файл in ("/static/og.png", "/static/noise.svg", "/static/about-me.jpg"):
        заголовок = main._кеш_статики(файл, "")
        assert заголовок == f"max-age={main.СТАТИКА_СУТКИ}"
        assert "immutable" not in заголовок


def test_шаблоны_видят_помощник():
    assert main.templates.env.globals.get("st") is main.статика


def test_ни_один_шаблон_не_ссылается_на_css_и_js_напрямую():
    """Файл, забытый без версии, попадёт под no-cache и будет ходить
    на сервер каждый раз — не сломается, но и кеша не получит."""
    прямые = []
    for шаблон in sorted(Path("templates").glob("*.html")):
        текст = шаблон.read_text(encoding="utf-8")
        for кусок in текст.split("/static/")[1:]:
            имя = кусок.split('"')[0].split("'")[0].split(" ")[0]
            if имя.endswith((".css", ".js")):
                прямые.append(f"{шаблон.name}: /static/{имя}")
    assert прямые == [], прямые
