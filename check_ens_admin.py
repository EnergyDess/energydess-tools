# -*- coding: utf-8 -*-
"""ЭКРАН УПРАВЛЕНИЯ КАТАЛОГОМ ENSHROUDED ЖИВЬЁМ (BACKLOG №137).

НЕ ПРОВЕРКА, а мерка: печатает ФАКТИЧЕСКИЙ ответ сервера на каждый
случай — и на исправный, и на отказной. Кода «правильно» у неё нет
по половине вопросов; ниже стоят ожидания там, где они однозначны,
и код возврата считается по ним.

ЗАЧЕМ ОТДЕЛЬНЫМ ФАЙЛОМ, А НЕ В ОТЧЁТЕ. Вывод, записанный только
в отчёте сессии, не существует: следующий заход не знает, что именно
отвечал сервер, и «отказ с внятным текстом» превращается в утверждение
без предмета. Здесь фраза печатается дословно — ту же, что увидит
владелец.

    py check_ens_admin.py;         echo "код=$?"
    py check_ens_admin.py --следы  # оставить подложенные сеты на месте

Стенд:  py -m uvicorn main:app --port 8899
"""
import io
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import httpx                                       # noqa: E402
import make_local_user as _сид                     # noqa: E402

БАЗА = os.environ.get("ENS_ADMIN_BASE", "http://127.0.0.1:8899")
ПРОБНЫЙ = "zz_proba_137"


def войти():
    кл = httpx.Client(base_url=БАЗА, follow_redirects=False, timeout=30)
    о = кл.post("/login", data={"email": _сид.EMAIL, "password": _сид.PASSWORD})
    if о.status_code not in (302, 303):
        raise RuntimeError(f"вход не прошёл: HTTP {о.status_code}")
    return кл


def _текст(о):
    try:
        д = о.json()
    except Exception:
        return о.text[:90].replace("\n", " ")
    # Порядок: сперва ПОЯСНЕНИЕ, потом код. У отказа 409 в `error` стоит
    # служебное «нужно подтверждение», а фразу для человека — с числом
    # отметок — несёт `text`, и печатать надо её.
    return д.get("text") or д.get("error") or json.dumps(д, ensure_ascii=False)[:110]


def главная(следы=False):
    кл = войти()
    строки, беды = [], 0

    def случай(имя, о, ждём):
        nonlocal беды
        плохо = о.status_code != ждём
        беды += плохо
        строки.append((имя, о.status_code, ждём, _текст(о), плохо))

    # ── D.8: доступ ─────────────────────────────────────────────────
    гость = httpx.Client(base_url=БАЗА, follow_redirects=False, timeout=30)
    случай("экран без сессии", гость.get("/admin/enshrouded"), 302)
    случай("правка без сессии",
           гость.post("/admin/api/enshrouded/set", json={"id": "x"}), 403)
    случай("удаление без сессии",
           гость.request("DELETE", f"/admin/api/enshrouded/set/{ПРОБНЫЙ}"), 403)
    случай("картинка без сессии",
           гость.post(f"/admin/api/enshrouded/set/{ПРОБНЫЙ}/image",
                      data={"url": "http://example.invalid/a.png"}), 403)
    случай("экран админом", кл.get("/admin/enshrouded"), 200)

    # ── D.7: отказы по полям ────────────────────────────────────────
    полный = {"id": ПРОБНЫЙ, "name_ru": "Проба", "name_en": "Probe",
              "crafter": "blacksmith", "lvl": 12}
    for имя, правка in [
        ("без русского названия", {"name_ru": ""}),
        ("без английского названия", {"name_en": ""}),
        ("без идентификатора", {"id": ""}),
        ("идентификатор кириллицей", {"id": "проба"}),
        ("категории не существует", {"crafter": "нет_такой"}),
        ("уровень не число", {"lvl": "много"}),
        ("уровень вне разумного", {"lvl": 9999}),
        ("вид слота не существует", {"pieces": ["head", "wings"]}),
        ("свой состав без подписи", {"custom": [{"id": "a", "label": ""}]}),
        ("свой и обычный состав вместе",
         {"custom": [{"id": "a", "label": "А"}], "pieces": ["head"]}),
    ]:
        случай(имя, кл.post("/admin/api/enshrouded/set", json={**полный, **правка}), 400)

    # ── исправный ход ───────────────────────────────────────────────
    случай("сохранение исправного", кл.post("/admin/api/enshrouded/set", json=полный), 200)

    # ── D.7: картинки ───────────────────────────────────────────────
    # §6.0: bytes-литерал с кириллицей — SyntaxError, только ASCII.
    не_картинка = "не картинка, а текст".encode("utf-8")
    случай("файл не-картинка",
           кл.post(f"/admin/api/enshrouded/set/{ПРОБНЫЙ}/image",
                   files={"file": ("a.png", не_картинка, "image/png")}), 400)
    случай("ссылка битая",
           кл.post(f"/admin/api/enshrouded/set/{ПРОБНЫЙ}/image",
                   data={"url": "http://127.0.0.1:9/нет.png"}), 400)
    случай("ссылка не на http",
           кл.post(f"/admin/api/enshrouded/set/{ПРОБНЫЙ}/image",
                   data={"url": "file:///etc/passwd"}), 400)
    случай("ни файла, ни ссылки",
           кл.post(f"/admin/api/enshrouded/set/{ПРОБНЫЙ}/image", data={}), 400)
    случай("картинка у несуществующего сета",
           кл.post("/admin/api/enshrouded/set/нет_такого/image",
                   data={"url": "http://example.com/a.png"}), 404)

    # НАСТОЯЩАЯ картинка, заведомо КРУПНЕЕ потолка: ужатие обязано
    # случиться на сервере, иначе проверку 24 уронит первый же файл.
    from PIL import Image
    б = io.BytesIO()
    Image.new("RGB", (1920, 1080), (30, 60, 90)).save(б, "JPEG")
    о = кл.post(f"/admin/api/enshrouded/set/{ПРОБНЫЙ}/image",
                files={"file": ("big.jpg", б.getvalue(), "image/jpeg")})
    случай("картинка 1920x1080 файлом", о, 200)
    ужато = о.json().get("now") if о.status_code == 200 else None

    # ── D.7: удаление ───────────────────────────────────────────────
    случай("удаление несуществующего",
           кл.request("DELETE", "/admin/api/enshrouded/set/нет_такого"), 404)
    # Отметка на пробном сете, чтобы удаление СПРОСИЛО
    кл.post("/api/enshrouded/slot", json={"set_id": ПРОБНЫЙ, "slot_id": "head",
                                          "owned": True, "rarity": "rare",
                                          "level": 3, "duplicates": 0})
    случай("удаление с отметками без подтверждения",
           кл.request("DELETE", f"/admin/api/enshrouded/set/{ПРОБНЫЙ}"), 409)
    if not следы:
        случай("удаление с подтверждением",
               кл.request("DELETE", f"/admin/api/enshrouded/set/{ПРОБНЫЙ}?confirm=1"), 200)

    # ── печать ──────────────────────────────────────────────────────
    print("=" * 96)
    print("ЭКРАН УПРАВЛЕНИЯ КАТАЛОГОМ ENSHROUDED — ЖИВЫЕ ОТВЕТЫ")
    print("=" * 96)
    print(f"  {'случай':38} {'HTTP':>5} {'ждём':>5}  что сказал сервер")
    for имя, код, ждём, текст, плохо in строки:
        знак = " ← НЕ ТО" if плохо else ""
        print(f"  {имя:38} {код:>5} {ждём:>5}  {текст[:64]}{знак}")
    if ужато:
        print(f"\n  УЖАТИЕ: 1920x1080 -> {ужато[0]}x{ужато[1]} "
              f"(потолок проверки 24 — 1396x994)")
    print(f"\nрасхождений с ожиданием: {беды}")
    return 1 if беды else 0


if __name__ == "__main__":
    sys.exit(главная("--следы" in sys.argv))
