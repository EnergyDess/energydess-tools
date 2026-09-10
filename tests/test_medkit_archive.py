# -*- coding: utf-8 -*-
"""АРХИВ УДАЛЁННЫХ УПАКОВОК: ПРАВА И СТРОГОСТЬ (заход 249, блок G).

Что здесь и чего нет. Сквозной путь «завели → удалили → нашли»
проверяет `check_medkit_archive.py` — он ходит боевыми эндпоинтами
и читает результат ИЗ БАЗЫ. Здесь спрашивается то, что пробе стоило
бы второго аккаунта и поднятого стенда: ВИДИМОСТЬ (G5) и СТРОГОСТЬ
сопоставления (G3) — на голых функциях, без сети.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DB_PATH", "test_medkit.db")

import main                                                  # noqa: E402
from database import MedkitArchive                           # noqa: E402


class ФейкЗапрос:
    """Минимальный `query(...).filter(...)` — сети и базы не требует."""

    def __init__(с, строки):
        с.строки = строки

    def filter(с, условие):
        # Условие SQLAlchemy тут не исполняется: видимость проверяется
        # ОТДЕЛЬНО (тест ниже), а строгость — на уже отобранных строках
        return с

    def all(с):
        return с.строки


class ФейкБаза:
    def __init__(с, строки):
        с.строки = строки
        с.спрошено = []

    def query(с, модель):
        с.спрошено.append(модель)
        return ФейкЗапрос(с.строки)


def _зп(**кв):
    з = MedkitArchive()
    for к, в in кв.items():
        setattr(з, к, в)
    return з


def _подмена_круга(monkeypatch, кто_видит):
    monkeypatch.setattr(main, "_апт_круг",
                        lambda db, user: (None, кто_видит))


def test_совпадение_по_полной_связке(monkeypatch):
    _подмена_круга(monkeypatch, [1])
    db = ФейкБаза([_зп(id=1, user_id=1, name="Проба", form="tablet", dose=2)])
    з = main._апт_архив_совпало(db, object(), name="Проба",
                                form="tablet", dose=2)
    assert з is not None and з.id == 1


def test_ДРУГАЯ_разовая_доза_не_совпадает(monkeypatch):
    """G3: «подставить схему от других миллиграммов — это чужая схема
    хуже её отсутствия, только чужая от самого владельца».

    ИМЯ ТЕСТА УТОЧНЕНО (задача 255): здесь сравнивается `dose` —
    РАЗОВАЯ доза приёма («по 1 таблетке»), а не миллиграммы вещества.
    Обе проверки нужны и не заменяют друг друга — эта про разовую дозу,
    `test_ДРУГАЯ_сила_вещества_не_совпадает` ниже про миллиграммы."""
    _подмена_круга(monkeypatch, [1])
    db = ФейкБаза([_зп(id=1, user_id=1, name="Проба", form="tablet", dose=2)])
    assert main._апт_архив_совпало(db, object(), name="Проба",
                                   form="tablet", dose=4) is None


def test_ДРУГАЯ_форма_не_совпадает(monkeypatch):
    _подмена_круга(monkeypatch, [1])
    db = ФейкБаза([_зп(id=1, user_id=1, name="Проба", form="tablet", dose=2)])
    assert main._апт_архив_совпало(db, object(), name="Проба",
                                   form="syrup", dose=2) is None


def test_доза_сравнивается_числом_а_не_строкой(monkeypatch):
    """«10» и «10.0» — одна доза. Разводить их значило бы отказывать
    по форме записи, а не по существу."""
    _подмена_круга(monkeypatch, [1])
    db = ФейкБаза([_зп(id=1, user_id=1, name="Проба", form="tablet",
                       dose=10.0)])
    assert main._апт_архив_совпало(db, object(), name="Проба",
                                   form="tablet", dose=10) is not None


def test_обе_дозы_пусты_это_совпадение(monkeypatch):
    """Дозировка — поле необязательное, и её отсутствие с обеих сторон
    совпадением быть обязано: иначе архив не сработал бы у всего,
    что заведено без дозы."""
    _подмена_круга(monkeypatch, [1])
    db = ФейкБаза([_зп(id=1, user_id=1, name="Проба", form="tablet",
                       dose=None)])
    assert main._апт_архив_совпало(db, object(), name="Проба",
                                   form="tablet", dose=None) is not None


def test_неоднозначность_это_ОТКАЗ(monkeypatch):
    """Две записи под одну связку — выбрать за человека нечем,
    а показать «одну из» значило бы выдать догадку за его же запись."""
    _подмена_круга(monkeypatch, [1])
    db = ФейкБаза([
        _зп(id=1, user_id=1, name="Проба", form="tablet", dose=2),
        _зп(id=2, user_id=1, name="Проба", form="tablet", dose=2),
    ])
    assert main._апт_архив_совпало(db, object(), name="Проба",
                                   form="tablet", dose=2) is None


def test_ДРУГАЯ_сила_вещества_не_совпадает(monkeypatch):
    """BACKLOG №255, блок E. G3 говорит про «другие миллиграммы»,
    а миллиграммы — это СИЛА ВЕЩЕСТВА («Ибупрофен, 200 мг»), которая
    лежит в `substance`, а не в `dose` (dose — РАЗОВАЯ доза приёма,
    «по 1 таблетке», она одна и та же что у 200, что у 400 мг).

    До правки `substance` в сравнении не участвовал ВООБЩЕ: связка
    «имя+форма+dose» совпадала у «Нурофен 200 мг» и «Нурофен 400 мг»,
    если разовая доза приёма у обеих была «1 таблетка» — ровно то,
    от чего предостерегает G3."""
    _подмена_круга(monkeypatch, [1])
    db = ФейкБаза([_зп(id=1, user_id=1, name="Проба", form="tablet",
                       dose=1, substance="Действующее, 200 мг")])
    assert main._апт_архив_совпало(
        db, object(), name="Проба", form="tablet", dose=1,
        substance="Действующее, 400 мг") is None


def test_ТА_ЖЕ_сила_вещества_совпадает(monkeypatch):
    _подмена_круга(monkeypatch, [1])
    db = ФейкБаза([_зп(id=1, user_id=1, name="Проба", form="tablet",
                       dose=1, substance="Действующее, 200 мг")])
    з = main._апт_архив_совпало(
        db, object(), name="Проба", form="tablet", dose=1,
        substance="Действующее, 200 мг")
    assert з is not None and з.id == 1


def test_вещество_неизвестно_с_одной_стороны_не_блокирует(monkeypatch):
    """«Не знаем» — не то же самое, что «не подходит». Архивный поиск
    срабатывает на `blur` полей ДО того, как substance обязательно
    заполнен (§5.8: поле необязательное), и пустое поле в запросе
    не должно гасить предложение, которое иначе законно найдётся."""
    _подмена_круга(monkeypatch, [1])
    db = ФейкБаза([_зп(id=1, user_id=1, name="Проба", form="tablet",
                       dose=1, substance="Действующее, 200 мг")])
    assert main._апт_архив_совпало(
        db, object(), name="Проба", form="tablet", dose=1,
        substance="") is not None
    # И ОБРАТНО: архивная запись сама может быть без вещества
    # (заведена до BACKLOG №234) — запрос с веществом её не отвергает
    db2 = ФейкБаза([_зп(id=2, user_id=1, name="Проба", form="tablet",
                        dose=1, substance=None)])
    assert main._апт_архив_совпало(
        db2, object(), name="Проба", form="tablet", dose=1,
        substance="Действующее, 200 мг") is not None


def test_пустое_имя_и_пустой_код_дают_ОТКАЗ(monkeypatch):
    """Иначе первое же открытие формы предлагало бы случайную запись."""
    _подмена_круга(monkeypatch, [1])
    db = ФейкБаза([_зп(id=1, user_id=1, name="Проба", form="tablet", dose=2)])
    assert main._апт_архив_совпало(db, object(), name="", form="tablet",
                                   dose=2) is None


def test_видимость_ограничена_кругом(monkeypatch):
    """G5: архив принадлежит владельцу позиции, видимость — в пределах
    круга, как у активных позиций.

    Спрашивается ИМЕННО ТО, что уходит в `filter`: множество id,
    по которому идёт отбор. Второго правила видимости не заводится —
    берётся тот же `_апт_круг`, что у списка позиций (§6.0.7).
    """
    поймано = {}

    class Ловушка(ФейкЗапрос):
        def filter(с, условие):
            # `in_` кладёт список в правую часть — достаём его оттуда
            поймано["условие"] = условие
            return с

    class База(ФейкБаза):
        def query(с, модель):
            return Ловушка(с.строки)

    _подмена_круга(monkeypatch, [7, 9])
    main._апт_архив_совпало(База([]), object(), name="Проба",
                            form="tablet", dose=1)
    выражение = поймано.get("условие")
    assert выражение is not None, "отбор по кругу не выполнялся вовсе"
    текст = str(выражение.compile(compile_kwargs={"literal_binds": True}))
    assert "7" in текст and "9" in текст, текст
    assert "medkit_archive.user_id IN" in текст, текст


def test_выдержек_справочника_в_архиве_НЕТ():
    """Они не запись человека, а снимок чужой страницы на дату.
    Новая карточка возьмёт свежий сама (§5.8, фоновый поиск)."""
    колонки = {c.name for c in MedkitArchive.__table__.columns}
    assert "dosage_text" not in колонки
    assert "indications_text" not in колонки


def test_срока_количества_и_фото_в_архиве_НЕТ():
    """Ими пачки и отличаются — тот же список, что не переносит
    действие «Ещё упаковка» (§5.8, задача 175)."""
    колонки = {c.name for c in MedkitArchive.__table__.columns}
    for поле in ("expires_ym", "qty_left", "qty_total", "opened_on",
                 "image_path", "place_id"):
        assert поле not in колонки, поле
