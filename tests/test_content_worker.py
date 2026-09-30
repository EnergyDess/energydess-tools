"""Исполнитель тяжёлых задач «Контента» (авария 2026-09-30)."""
import asyncio
import threading

import content_worker as cw


def test_второй_запуск_отказан_словами_и_не_стартует():
    идёт = threading.Event()
    отпустить = threading.Event()
    запусков = []

    async def долгий(повод):
        запусков.append(повод)
        идёт.set()
        await asyncio.to_thread(отпустить.wait, 5)

    assert cw.запустить("archaeology", долгий, "a")["ok"]
    assert идёт.wait(5)
    второй = cw.запустить("ideas", долгий, "b")
    assert второй["busy"] and "археология" in второй["error"]
    assert cw.занят_другим()
    отпустить.set()
    cw._ПОТОКИ["archaeology"].join(5)
    assert запусков == ["a"]                      # второй не стартовал
    assert not cw.занят_другим()


def test_исключение_в_прогоне_отпускает_замок():
    async def падает(повод):
        raise RuntimeError("подлог")

    assert cw.запустить("cycle", падает, "x")["ok"]
    cw._ПОТОКИ["cycle"].join(5)
    assert cw.что_идёт() is None


def test_задача_сама_себе_не_помеха():
    видела = []

    async def смотрит(повод):
        видела.append(cw.занят_другим())

    cw.запустить("cycle", смотрит, "x")
    cw._ПОТОКИ["cycle"].join(5)
    assert видела == [False]


def test_планировщик_не_крутится_без_паузы():
    """Подлог аварии: замок занят, «пора» цикла наступила — оборотов
    планировщика за секунду не больше двух (было ~75 в секунду)."""
    import content_engine as ce
    исходник = open(ce.__file__, encoding="utf-8").read()
    тело = исходник[исходник.index("async def _планировщик"):
                    исходник.index("async def _идеи_по_расписанию")]
    assert "await asyncio.sleep(пауза)" in тело
    assert "ПАУЗА_ЕСЛИ_ЗАНЯТО_СЕК" in тело
    assert ce.ПАУЗА_ПЛАНИРОВЩИКА_МИН_СЕК >= 1
