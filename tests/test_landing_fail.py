"""Причина сбоя ffmpeg на загрузке главной (задача 330).

Живой отказ по памяти на Windows-стенде снимает `check_landing_fail.py`.
Здесь — то, что стенд не воспроизводит: убийство ядром Linux, при котором
в выводе нет ни слова о памяти, а последней стоит строка прогресса.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import landing_media as lm  # noqa: E402

ПРОГРЕСС = "frame=  102 fps=0.0 q=32.0 size=     256KiB time=00:00:03.33 bitrate= 629.5kbits/s"
РАЗБОР = {"width": 1920, "height": 1080, "duration": 5.0}


def test_убит_ядром_это_память_а_не_строка_прогресса():
    текст, журнал = lm.причина_сбоя(-9, ПРОГРЕСС, РАЗБОР)
    assert "памяти" in текст and "разрешение" in текст
    assert "frame=" not in текст and "ffmpeg" not in текст
    assert "frame=" in журнал and "код -9" in журнал


def test_malloc_в_выводе_это_память_хотя_рядом_invalid_data():
    вывод = ("malloc of size 3060037 failed\n"
             "Error submitting packet to decoder: Invalid data found when processing input\n"
             "Conversion failed!")
    текст, _ = lm.причина_сбоя(1, вывод, РАЗБОР)
    assert "памяти" in текст


def test_битый_файл_не_объявлен_памятью():
    текст, _ = lm.причина_сбоя(1, "moov atom not found\nConversion failed!")
    assert "памяти" not in текст and "повреждён" in текст


def test_незнакомое_не_выдумывает_причину():
    текст, журнал = lm.причина_сбоя(1, "что-то совсем другое")
    assert "не распознана" in текст and "журнал" in текст
    assert "что-то совсем другое" in журнал and "что-то" not in текст


def test_обратный_ноль_вывода_тоже_в_журнал():
    _, журнал = lm.причина_сбоя(4294967295, "")
    assert "вывода нет" in журнал
