"""ПРОВЕРКА 44: ГОТОВОЕ ПИСЬМО HH — ВЫДУМАННЫЕ ТЕХНОЛОГИИ, ПОТЕРЯННЫЙ
РЕПОЗИТОРИЙ, СПИСКИ. BACKLOG №349. Сети и модели не требует.

Правила живут в `letter_facts.py` — ОДИН модуль на сервер и пробу; словарь
технологий — файл `hh_tech_names.txt`. Проба своего признака не держит.

    py check_letter_facts.py                 # самопроверка на поддельных письмах, код 1 при беде
    py check_letter_facts.py --контроль      # подлоги в модуль: каждый обязан уронить свой случай
    py check_letter_facts.py --стенд         # источник допустимых и их число на досье стенда
    py check_letter_facts.py --письма КАТАЛОГ  # проверить настоящие письма (*.txt) против досье стенда

Случаи самопроверки (досье и резюме — поддельные, в духе стенда):
  а) письмо со словом Groq при Whisper в досье   → находка «вне досье»
  б) письмо с сайтом проекта без его репозитория  → находка «нет репозитория»
  в) письмо, где всё в порядке                     → чисто
  г) письмо со списком модулей при вакансии без вопросов → находка «список»
  д) ОБРАТНЫЙ: требование вакансии (PostgreSQL) в письме → НЕ находка, куча «из вакансии»
"""
import os
import sys

import probe_guard  # noqa: F401 — внешний отказ говорится словом (§3)
import letter_facts as lf

sys.stdout.reconfigure(encoding="utf-8")

ДОСЬЕ = """Позиционирование: AI-разработчик
Проекты/портфолио:
  • energydess.ru — https://energydess.ru (Портал из четырёх инструментов) [ссылки проекта: github.com/EnergyDess/energydess-tools] [инструменты: Python, FastAPI, Docker, Fly.io]
Навыки и инструменты: Python, FastAPI, SQLAlchemy, Whisper, Claude API, GitHub Actions"""
РЕЗЮМЕ = "Опыт: Python, FastAPI, SQLite."
ПРОЕКТЫ = [{"title": "energydess.ru", "url": "https://energydess.ru",
            "description": "Портал. Публичный репозиторий: github.com/EnergyDess/energydess-tools"}]
ВАКАНСИЯ = "Python-разработчик. Требования: FastAPI, PostgreSQL. Приложите ссылку на код."

ЧИСТОЕ = """Здравствуйте!

Проект, которым горжусь, — energydess.ru: FastAPI, SQLAlchemy, Whisper для голоса, Claude API через Python.

https://energydess.ru
https://github.com/EnergyDess/energydess-tools

С уважением, Денис"""

СЛУЧАИ = {
    "а-groq": (ЧИСТОЕ.replace("Whisper для голоса", "Whisper и Groq для голоса"),
               lambda и: "Groq" in и["вне_досье"]),
    "б-без-репозитория": (ЧИСТОЕ.replace("https://github.com/EnergyDess/energydess-tools\n", ""),
                          lambda и: bool(и["нет_репозитория"])),
    "в-чисто": (ЧИСТОЕ, lambda и: и["чисто"]),
    "г-список": (ЧИСТОЕ.replace("Проект, которым горжусь",
                                "Внутри:\n— письма\n— дневник\n— тренировки\n\nПроект"),
                 lambda и: и["список_находка"] and и["списков"] == 1),
    "д-обратный-вакансия": (ЧИСТОЕ.replace("Whisper для голоса",
                                           "Whisper; с PostgreSQL в проде не работал"),
                            lambda и: и["чисто"] and "PostgreSQL" in и["из_вакансии"]),
}


def самопроверка(записи=None):
    группы = lf.ссылки_проектов(ПРОЕКТЫ)
    итог = {}
    for имя, (письмо, ожидание) in СЛУЧАИ.items():
        р = lf.проверить(письмо, ДОСЬЕ, РЕЗЮМЕ, ВАКАНСИЯ, группы, записи)
        итог[имя] = (ожидание(р), р)
    return итог


def печать(итог):
    плохих = 0
    for имя, (ок, р) in итог.items():
        плохих += not ок
        print(f"  {'OK   ' if ок else 'ПЛОХО'} {имя:22s} {lf.строкой(р)}")
    return плохих


def контроль():
    """Подлоги в модуль: каждый ломает ОДНО звено и обязан уронить свой случай.
    Доказательство независимо от вердикта — печатается само сломанное звено."""
    подлоги = {
        "а-groq": ("словарь без Groq", lambda: setattr(lf, "словарь",
                   (lambda _исх: (lambda путь=None: [з for з in _исх(путь) if з[0] != "Groq"]))(lf.словарь))),
        "б-без-репозитория": ("пары ссылок не собираются", lambda: setattr(lf, "ссылки_проектов",
                              lambda проекты: [])),
        "в-чисто": ("допустимые пусты", lambda: setattr(lf, "допустимые",
                    lambda досье, резюме, записи=None: set())),
        "г-список": ("списки не считаются", lambda: setattr(lf, "списков", lambda письмо: 0)),
    }
    найдено = 0
    for случай, (что, наложить) in подлоги.items():
        сохр = dict(vars(lf))
        try:
            наложить()
            ок, р = самопроверка()[случай]
            доказ = {"а-groq": lambda: "Groq" in {з[0] for з in lf.словарь()},
                     "б-без-репозитория": lambda: len(lf.ссылки_проектов(ПРОЕКТЫ)),
                     "в-чисто": lambda: len(lf.допустимые(ДОСЬЕ, РЕЗЮМЕ)),
                     "г-список": lambda: lf.списков("— а\n— б")}[случай]()
        finally:
            for к, в in сохр.items():
                setattr(lf, к, в)
        упал = not ок
        найдено += упал
        print(f"  {'НАЙДЕН    ' if упал else 'НЕ НАЙДЕН '} {случай:20s} подлог: {что}; "
              f"доказательство: {доказ}; итог случая: {lf.строкой(р)}")
    print(f"КОНТРОЛЬ: подлогов {len(подлоги)}, найдено {найдено}")
    return 0 if найдено == len(подлоги) else 1


def _стенд():
    import sqlite3
    import tempfile
    исх = os.environ.get("STAND_DB") or os.path.join(lf.КОРЕНЬ, "app.db")
    if "/data/" in исх.replace("\\", "/"):
        print("ПРОПУСК: путь к боевой базе")
        sys.exit(2)
    if not os.path.exists(исх):
        print(f"ПРОПУСК: базы стенда нет ({исх})")
        sys.exit(2)
    копия = os.path.join(tempfile.mkdtemp(prefix="letter_facts_"), "app.db")
    a, b = sqlite3.connect(исх), sqlite3.connect(копия)
    a.backup(b)
    a.close()
    b.close()
    os.environ["DB_PATH"] = копия
    import main
    from database import SessionLocal, User, Resume, HHProfile
    db = SessionLocal()
    u = db.query(User).filter(User.email == os.environ.get("STAND_EMAIL", "screenshot@local.dev")).first()
    if not u:
        print("ПРОПУСК: на стенде нет аккаунта съёмки")
        sys.exit(2)
    проф = db.query(HHProfile).filter(HHProfile.user_id == u.id).first()
    рез = db.query(Resume).filter(Resume.user_id == u.id).first()
    досье = main._build_full_dossier(проф)
    резюме = рез.resume_text if рез else ""
    группы = lf.ссылки_проектов(проф.projects if проф else [])
    db.close()
    return досье, резюме, группы


def main_():
    if "--контроль" in sys.argv:
        return контроль()
    if "--стенд" in sys.argv or "--письма" in sys.argv:
        досье, резюме, группы = _стенд()
        можно = sorted(lf.допустимые(досье, резюме))
        print(f"ИСТОЧНИК ДОПУСТИМЫХ: полное досье (_build_full_dossier) + резюме аккаунта стенда; "
              f"словарь {len(lf.словарь())} названий ({os.path.basename(lf.СЛОВАРЬ_ФАЙЛ)})")
        print(f"ДОПУСТИМЫХ: {len(можно)} — {', '.join(можно)}")
        print(f"ГРУППЫ ССЫЛОК ПРОЕКТОВ: {группы}")
        if "--письма" in sys.argv:
            каталог = sys.argv[sys.argv.index("--письма") + 1]
            вакансия = ""
            пв = os.path.join(каталог, "вакансия.txt")
            if os.path.exists(пв):
                вакансия = open(пв, encoding="utf-8").read()
            файлы = sorted(ф for ф in os.listdir(каталог)
                           if ф.endswith(".txt") and ф != "вакансия.txt")
            if not файлы:
                print("ПРОПУСК: писем в каталоге нет")
                return 2
            выдумки = без_репо = со_списком = 0
            for ф in файлы:
                р = lf.проверить(open(os.path.join(каталог, ф), encoding="utf-8").read(),
                                 досье, резюме, вакансия, группы)
                выдумки += bool(р["вне_досье"])
                без_репо += bool(р["нет_репозитория"])
                со_списком += р["список_находка"]
                print(f"  {ф}: {lf.строкой(р)}")
            print(f"ПИСЕМ {len(файлы)}: с выдуманными технологиями {выдумки}, "
                  f"без ссылки на репозиторий {без_репо}, со списком {со_списком}")
        return 0
    print(f"САМОПРОВЕРКА НА ПОДДЕЛЬНЫХ ПИСЬМАХ (словарь {len(lf.словарь())} названий):")
    плохих = печать(самопроверка())
    print(f"ИТОГ: случаев {len(СЛУЧАИ)}, плохих {плохих}")
    return 1 if плохих else 0


if __name__ == "__main__":
    sys.exit(main_())
