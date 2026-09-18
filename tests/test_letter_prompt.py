"""Запрос письма частями и вариант с кэшем (№346, заход 3, блок 3)."""
import os
import sys
import tempfile
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault(
    "DB_PATH", str(Path(tempfile.gettempdir()) / f"hh_letter_prompt_{uuid.uuid4().hex}.db"))

import main  # noqa: E402

ВХОД = dict(resume_text="Резюме-метка", full_dossier="Досье-метка",
            analysis={"relevant_portfolio_links": ["https://ссылка-метка"],
                      "key_matches": ["совпадение-метка"], "focus_points": ["акцент"]},
            job_text="Вакансия-метка", lang="ru")


def test_по_умолчанию_старый_путь():
    assert main.LETTER_PROMPT_VARIANT == "полный"


def test_полный_вариант_одна_строка_в_прежнем_порядке():
    prompt, части = main._промпт_письма(**ВХОД)
    сообщения = main._сообщения_письма(части, "полный")
    assert сообщения == [{"role": "user", "content": prompt}]
    assert prompt.startswith("Напиши сопроводительное письмо.")
    порядок = [prompt.index(м) for м in ("Резюме-метка", "Досье-метка",
                                         "ссылка-метка", "Вакансия-метка",
                                         "ЭТАЛОННЫЕ ПРИМЕРЫ", "КОНЦОВКА ПИСЬМА")]
    assert порядок == sorted(порядок)


def test_кэш_ни_одна_часть_не_потеряна_и_вакансия_целиком():
    _, части = main._промпт_письма(**ВХОД)
    [сообщение] = main._сообщения_письма(части, "кэш")
    блоки = сообщение["content"]
    assert len(блоки) == 2
    assert блоки[0]["cache_control"] == {"type": "ephemeral"}
    assert "cache_control" not in блоки[1]
    постоянное, переменное = блоки[0]["text"], блоки[1]["text"]
    for к in ("инструкция", "примеры", "резюме", "досье"):
        assert части[к] in постоянное, к
    for к in ("ссылки", "подсказки", "вакансия"):
        assert части[к] in переменное, к
    assert "Вакансия-метка" in переменное and "Вакансия-метка" not in постоянное
    # правила — с одной правкой слова «выше» → «ниже»
    assert len(постоянное) + len(переменное) == len("".join(части.values())) + 1


def test_фраза_про_ссылки_выше_существует_иначе_замена_молчит():
    _, части = main._промпт_письма(**ВХОД)
    assert "ТОЛЬКО из блока «РЕЛЕВАНТНЫЕ ССЫЛКИ» выше" in части["правила"]
    [сообщение] = main._сообщения_письма(части, "кэш")
    assert "РЕЛЕВАНТНЫЕ ССЫЛКИ» выше" not in сообщение["content"][0]["text"]
    assert "ТОЛЬКО из блока «РЕЛЕВАНТНЫЕ ССЫЛКИ» ниже" in сообщение["content"][0]["text"]


def test_кэш_из_usage_доезжает_до_учёта():
    class Ответ:
        status_code = 200

        @staticmethod
        def json():
            return {"id": "gen-x", "choices": [], "usage": {
                "prompt_tokens": 100, "completion_tokens": 5, "cost": 0.01,
                "prompt_tokens_details": {"cached_tokens": 80, "cache_write_tokens": 0}}}
    строка = main._разобрать_расход(Ответ())
    assert строка["cached_tokens"] == 80 and строка["cache_write_tokens"] == 0


def test_без_деталей_кэша_поля_пусты():
    class Ответ:
        status_code = 200

        @staticmethod
        def json():
            return {"id": "gen-x", "usage": {"prompt_tokens": 1}}
    строка = main._разобрать_расход(Ответ())
    assert строка["cached_tokens"] is None and строка["cache_write_tokens"] is None


# ── BACKLOG №349: ссылки проекта идут парой, досье не теряет репозиторий ──

ПРОЕКТЫ = [{"title": "energydess.ru", "url": "https://energydess.ru",
            "description": "П" * 200 + " Публичный репозиторий: github.com/EnergyDess/energydess-tools"}]


def test_досье_письма_не_теряет_ссылку_за_обрезкой_описания():
    class Проф:
        projects = ПРОЕКТЫ
        profession_one_liner = location = languages = total_years_in_profession = None
        experience_extra = skills = methodology = tone_preference = None
        never_mention = extra_context = ending_style = None
    досье = main._build_full_dossier(Проф())
    assert "github.com/EnergyDess/energydess-tools" in досье


def test_выбран_сайт_рядом_встаёт_репозиторий():
    группы = main._письмо_факты.ссылки_проектов(ПРОЕКТЫ)
    вход = dict(ВХОД, analysis={"relevant_portfolio_links": ["https://energydess.ru"]},
                группы_ссылок=группы)
    _, части = main._промпт_письма(**вход)
    assert "https://energydess.ru" in части["ссылки"]
    assert "github.com/EnergyDess/energydess-tools" in части["ссылки"]


def test_проект_не_выбран_пара_не_приезжает():
    группы = main._письмо_факты.ссылки_проектов(ПРОЕКТЫ)
    вход = dict(ВХОД, analysis={"relevant_portfolio_links": []}, группы_ссылок=группы)
    _, части = main._промпт_письма(**вход)
    assert "github.com" not in части["ссылки"]


def test_в_правилах_нет_адресов_которых_нет_в_досье():
    _, части = main._промпт_письма(**ВХОД)
    assert "github.com/EnergyDess" not in части["правила"]
    assert "идут ПАРОЙ" in части["правила"]
    assert "Технологии и сервисы." in части["правила"]
