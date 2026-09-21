"""ПРОВЕРКА 58: ВЕС ОДИН НА ВЕСЬ ИНСТРУМЕНТ (№352, «питание-3», 2.2).

ПРОВЕРКА, код 1 при находке, 2 — спросить нечем (базы стенда нет либо
аккаунта съёмки нет).

Решение владельца: вес один. Источник правды — ЖУРНАЛ ЗАМЕРОВ; вес
в профиле — последний по дате замер, ручной или с весов; замер задним
числом профиль не меняет; смена веса в профиле пишет замер за сегодня
(дубля нет); нормы пересчитываются от нового веса.

КАК: настоящее приложение В ПРОЦЕССЕ (`TestClient`) на КОПИИ базы стенда,
тот же приём, что у проверки 42. Весы Zepp НЕ вызываются: выборку отдаёт
заглушка на месте `zepp_client.fetch_weight_records`. Модель не зовётся.
База стенда не меняется.

ШАГИ (профиль выдуманный — аккаунт съёмки стенда):
  подстановка — вес профиля разошёлся с журналом → подстановка на старте
      приводит его к последнему замеру;
  весы       — заглушка приносит замер за сегодня → профиль и нормы
      следуют за ним;
  задним числом — ручной замер 30 дней назад → профиль НЕ меняется;
  ручной     — ручной замер за сегодня → профиль, нормы, строка за сегодня одна;
  профиль    — смена веса в анкете → замер за сегодня обновлён, дубля нет,
      точка на графике есть;
  тот же вес — сохранение анкеты без смены веса новых замеров не даёт.

КЛЮЧИ:
  --контроль  подлог: обновление профиля при замере отключено (функция
              синхронизации ничего не делает) — обязаны упасть «весы»
              и «ручной».
"""
import datetime as dt
import os
import sqlite3
import sys
import tempfile

try:
    import probe_guard  # noqa: F401  ПРОПУСК вместо трассы (§6.0.1)
except ImportError:
    pass

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

КОРЕНЬ = os.path.dirname(os.path.abspath(__file__))
ИСХОДНАЯ = os.environ.get("STAND_DB") or os.path.join(КОРЕНЬ, "app.db")
ПОЧТА = os.environ.get("STAND_EMAIL", "screenshot@local.dev")


def _пропуск(причина):
    print("ПРОПУСК: " + причина)
    sys.exit(2)


def _копия_базы():
    if "/data/" in ИСХОДНАЯ.replace("\\", "/"):
        _пропуск("путь к боевой базе — проверка ходит только по стенду")
    if not os.path.exists(ИСХОДНАЯ):
        _пропуск("базы стенда нет — посейте: py make_local_user.py --seed")
    путь = os.path.join(tempfile.mkdtemp(prefix="single_weight_"), "app.db")
    исх, нов = sqlite3.connect(ИСХОДНАЯ), sqlite3.connect(путь)
    исх.backup(нов)
    исх.close()
    нов.close()
    return путь


os.environ["DB_PATH"] = _копия_базы()
os.environ.pop("FLY_APP_NAME", None)
sys.path.insert(0, КОРЕНЬ)

import main                                            # noqa: E402
from auth import create_token                          # noqa: E402
from database import (SessionLocal, User, WeightLog,   # noqa: E402
                      NutritionProfile, ScaleConnection)
from fastapi.testclient import TestClient              # noqa: E402

находок = 0
_строки = {}


def шаг(имя, условие, подробность=""):
    global находок
    исход = "ok" if условие else "ПЛОХО"
    находок += not условие
    _строки[имя] = исход
    print("  %-6s %s%s" % (исход, имя, (" — " + подробность) if подробность else ""))


def _состояние(uid):
    db = SessionLocal()
    try:
        п = db.query(NutritionProfile).filter(NutritionProfile.user_id == uid).first()
        логи = db.query(WeightLog).filter(WeightLog.user_id == uid, WeightLog.weight_kg.isnot(None)).all()
        сегодня = main._сегодня(db.query(User).get(uid)).strftime("%Y-%m-%d")
        return {"вес": п.weight_kg, "ккал": п.calorie_goal, "белок": п.protein_goal,
                "замеров": len(логи), "за_сегодня": [л.weight_kg for л in логи if л.log_date == сегодня],
                "последний": max(логи, key=lambda л: л.log_date).weight_kg if логи else None,
                "сегодня": сегодня}
    finally:
        db.close()


def прогон(подлог=False):
    global находок
    находок = 0
    _строки.clear()
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.email == ПОЧТА).first()
        if not u:
            _пропуск("на стенде нет аккаунта %s" % ПОЧТА)
        uid = u.id
        п = db.query(NutritionProfile).filter(NutritionProfile.user_id == uid).first()
        if not п or not п.age or not п.height_cm:
            _пропуск("у аккаунта нет анкеты питания — посейте стенд")
        анкета = {"gender": п.gender, "age": п.age, "height_cm": п.height_cm,
                  "goal": п.goal, "activity_level": п.activity_level}
        сегодня = main._сегодня(u).strftime("%Y-%m-%d")
        # чистый лист: замера за сегодня нет, привязка весов есть
        db.query(WeightLog).filter(WeightLog.user_id == uid, WeightLog.log_date == сегодня).delete()
        if not db.query(ScaleConnection).filter(ScaleConnection.user_id == uid).first():
            db.add(ScaleConnection(user_id=uid, encrypted_username="stub"))
        db.commit()
    finally:
        db.close()

    исходные = (main._вес_профиля_из_журнала, main.zepp_client.fetch_weight_records, main._decrypt_opt)
    if подлог:
        main._вес_профиля_из_журнала = lambda db, user: False
    try:
        c = TestClient(main.app)
        c.cookies.set("access_token", create_token(uid))
        база = _состояние(uid)

        # подстановка: вес профиля разошёлся с журналом
        db = SessionLocal()
        db.query(NutritionProfile).filter(NutritionProfile.user_id == uid).update(
            {"weight_kg": база["последний"] + 5})
        db.commit()
        db.close()
        main._вес_профилей_из_журнала_все()
        с = _состояние(uid)
        шаг("подстановка-к-последнему-замеру", с["вес"] == с["последний"],
            "совпадает" if с["вес"] == с["последний"] else "не совпадает")

        # весы: заглушка приносит замер за сегодня
        до = _состояние(uid)
        wz = round(до["последний"] - 1.7, 1)
        ts = int(dt.datetime.now(dt.timezone.utc).timestamp())
        main._decrypt_opt = lambda v: "stub"
        main.zepp_client.fetch_weight_records = lambda *a, **k: {
            "records": [{"timestamp": ts, "weight_kg": wz}], "total": 1, "with_body": 0, "dropped": {}}
        r = c.post("/nutrition/api/scale/sync")
        с = _состояние(uid)
        шаг("весы-свежий-замер-в-профиле", r.status_code == 200 and с["вес"] == wz and с["ккал"] != до["ккал"],
            "HTTP %d; вес %s → %s; ккал %s → %s" % (r.status_code, до["вес"], с["вес"], до["ккал"], с["ккал"]))

        # задним числом: 30 дней назад — профиль не меняется
        до = _состояние(uid)
        давно = (dt.date.fromisoformat(до["сегодня"]) - dt.timedelta(days=30)).isoformat()
        r = c.post("/nutrition/api/weight", json={"date": давно, "weight_kg": 55.5})
        с = _состояние(uid)
        шаг("задним-числом-профиль-не-меняется", r.status_code == 200 and с["вес"] == до["вес"] and с["ккал"] == до["ккал"],
            "вес %s → %s" % (до["вес"], с["вес"]))

        # ручной за сегодня: профиль и нормы, строка одна
        до = _состояние(uid)
        w1 = round(до["вес"] + 2.4, 1)
        r = c.post("/nutrition/api/weight", json={"weight_kg": w1})
        с = _состояние(uid)
        шаг("ручной-замер-в-профиле-и-нормах",
            r.status_code == 200 and с["вес"] == w1 and с["ккал"] != до["ккал"] and len(с["за_сегодня"]) == 1,
            "вес %s → %s; ккал %s → %s; белок %s → %s; замеров за сегодня %d"
            % (до["вес"], с["вес"], до["ккал"], с["ккал"], до["белок"], с["белок"], len(с["за_сегодня"])))

        # смена веса в профиле → замер за сегодня обновлён, дубля нет
        до = _состояние(uid)
        wp = round(до["вес"] - 0.9, 1)
        r = c.post("/nutrition/api/profile", json=dict(анкета, weight_kg=wp))
        с = _состояние(uid)
        точки = [л for л in c.get("/nutrition/api/weight").json().get("logs", []) if л.get("date") == с["сегодня"]]
        шаг("профиль-пишет-замер-за-сегодня",
            r.status_code == 200 and с["за_сегодня"] == [wp] and с["замеров"] == до["замеров"]
            and с["вес"] == wp and точки and точки[0]["weight_kg"] == wp,
            "за сегодня %s → %s; замеров %d → %d; точка графика %s"
            % (до["за_сегодня"], с["за_сегодня"], до["замеров"], с["замеров"], [т["weight_kg"] for т in точки]))

        # тот же вес — новых замеров нет
        до = _состояние(uid)
        r = c.post("/nutrition/api/profile", json=dict(анкета, weight_kg=до["вес"]))
        с = _состояние(uid)
        шаг("тот-же-вес-без-нового-замера", r.status_code == 200 and с["замеров"] == до["замеров"],
            "замеров %d → %d" % (до["замеров"], с["замеров"]))
    finally:
        main._вес_профиля_из_журнала, main.zepp_client.fetch_weight_records, main._decrypt_opt = исходные
    return находок


def main_():
    if "--контроль" in sys.argv:
        print("ЧИСТЫЙ ПРОГОН")
        if прогон():
            print("КОНТРОЛЬ НЕДЕЙСТВИТЕЛЕН: грязная основа")
            sys.exit(2)
        print("ПОДЛОГ: обновление профиля при замере отключено")
        прогон(подлог=True)
        упали = [к for к in ("весы-свежий-замер-в-профиле", "ручной-замер-в-профиле-и-нормах") if _строки.get(к) == "ПЛОХО"]
        print("КОНТРОЛЬ: %s" % ("НАЙДЕН, упали %s" % ", ".join(упали) if len(упали) == 2 else "НЕ НАЙДЕН"))
        sys.exit(0 if len(упали) == 2 else 1)
    print("ВЕС ОДИН НА ИНСТРУМЕНТ (копия базы стенда, весы — заглушка)")
    н = прогон()
    print("ИТОГ: находок %d" % н)
    sys.exit(1 if н else 0)


if __name__ == "__main__":
    main_()
