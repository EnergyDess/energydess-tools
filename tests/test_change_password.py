# -*- coding: utf-8 -*-
"""СМЕНА ПАРОЛЯ В ПРОФИЛЕ (BACKLOG №122).

ЧТО ЗДЕСЬ ГЛАВНОЕ, И ЭТО НЕ «ПАРОЛЬ ПОМЕНЯЛСЯ». Работающая смена —
половина, причём безопасная: сломайся она, человек увидит это сразу
на первом же входе. Опасны три другие, и все три молчат:

  1. СТАРЫЙ ПАРОЛЬ ПРОДОЛЖАЕТ ПОДХОДИТЬ. Экран сказал «готово», письмо
     ушло, а вход по прежней паре работает — то есть смена не сделала
     того единственного, ради чего её делают;

  2. ПРОЧИЕ СЕССИИ ОСТАЛИСЬ ЖИВЫ. Тот, кто увёл куку, сидит в аккаунте
     ещё месяц, и владелец об этом не узнает ничем: у него всё «сменено»;

  3. ОТКАЗ БЕЗ ОТКАЗА. Неверный текущий пароль, короткий новый, тот же
     самый — на всё это ни записи, ни письма быть не должно. Уведомление
     «пароль изменён» о смене, которой не было, — прямая ложь владельцу,
     и вдобавок оно тратит его суточный запас писем.

Приложение поднимается настоящим TestClient на временной базе: половина
проверяемого — это порядок действий внутри обработчика и работа куки,
а подделкой в Python ни то ни другое не проверяется.

ПОЧТУ НЕ ШЛЁМ, А ПЕРЕХВАТЫВАЕМ — по той же причине, что в соседнем файле
про смену адреса: тест обязан видеть не только «письмо ушло», но и куда,
каким видом и с каким флагом лимита.
"""

import os
import sys
import tempfile
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault(
    "DB_PATH", str(Path(tempfile.gettempdir()) / f"hh_chgpwd_{uuid.uuid4().hex}.db"))

import main                                                    # noqa: E402
from database import SessionLocal, User                        # noqa: E402
from fastapi.testclient import TestClient                      # noqa: E402
from auth import hash_password, create_token, verify_password, _pwd_stamp  # noqa: E402

ПАРОЛЬ = "Pa$$w0rd-локальный"
НОВЫЙ = "Novyj-Parol-2026"


class Почта:
    """Перехваченные письма: (кому, тема, вид, флаг лимита)."""

    def __init__(self):
        self.ушло = []
        self.вернуть = None

    async def __call__(self, to, subject, html, text=None, db=None,
                       user_id=None, kind="verify", учитывать_лимит=True):
        self.ушло.append({"кому": to, "тема": subject, "вид": kind,
                          "лимит": учитывать_лимит, "html": html})
        return self.вернуть


def _завести(db, почта, подтверждён=True):
    u = User(email=почта, password_hash=hash_password(ПАРОЛЬ),
             is_verified=подтверждён, timezone="Europe/Moscow")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture()
def стенд(monkeypatch):
    main.init_db()
    почта = Почта()
    monkeypatch.setattr(main, "send_email", почта)

    db = SessionLocal()
    метка = uuid.uuid4().hex[:8]
    свой = _завести(db, f"pwd-{метка}@local.test")
    uid, адрес = свой.id, свой.email
    db.close()

    c = TestClient(main.app)
    c.cookies.set("access_token", create_token(uid))
    c.uid = uid
    c.почта = почта
    c.адрес = адрес
    yield c


def _пользователь(uid):
    db = SessionLocal()
    try:
        return db.query(User).filter(User.id == uid).first()
    finally:
        db.close()


def _кука_из_ответа(r):
    """access_token из Set-Cookie ответа.

    Именно из заголовка, а не из банки клиента: банка TestClient хранит
    ОБЕ куки разом — подложенную нами и выданную сервером, — и `get`
    на ней падает CookieConflict. Читая заголовок, мы проверяем ровно
    то, что сервер прислал браузеру.
    """
    for строка in r.headers.get_list("set-cookie"):
        if строка.startswith("access_token="):
            return строка.split(";")[0].split("=", 1)[1]
    return None


def _сменить(c, текущий=ПАРОЛЬ, новый=НОВЫЙ, повтор=None):
    тело = {"current": текущий, "new": новый}
    тело["new2"] = новый if повтор is None else повтор
    return c.post("/api/change-password", json=тело)


# ── 1. Обычный путь ──────────────────────────────────────────────────────

def test_пароль_действительно_меняется(стенд):
    r = _сменить(стенд)
    assert r.status_code == 200, r.text
    u = _пользователь(стенд.uid)
    assert verify_password(НОВЫЙ, u.password_hash), "новый пароль не подошёл"


def test_старый_пароль_перестаёт_подходить(стенд):
    """Главная проверка. «Пароль изменён» при живом старом пароле —
    самый молчаливый из отказов: экран сказал правду о записи и неправду
    о её последствии."""
    _сменить(стенд)
    u = _пользователь(стенд.uid)
    assert not verify_password(ПАРОЛЬ, u.password_hash), (
        "старый пароль всё ещё подходит — смены не произошло")


def test_вход_старым_паролем_НЕ_работает_а_новым_работает(стенд):
    """Проверяется не поле в базе, а сам ВХОД — то, что человек и делает."""
    _сменить(стенд)
    c = TestClient(main.app)
    старым = c.post("/login", data={"email": стенд.адрес, "password": ПАРОЛЬ},
                    follow_redirects=False)
    assert старым.status_code == 200, "вход старым паролем дал редирект — то есть пустил"

    новым = c.post("/login", data={"email": стенд.адрес, "password": НОВЫЙ},
                   follow_redirects=False)
    assert новым.status_code == 302, новым.status_code


def test_дата_смены_записана_и_возвращена(стенд):
    r = _сменить(стенд)
    assert r.json().get("changed_at"), "дата смены не вернулась — экран нечем обновить"
    assert _пользователь(стенд.uid).password_changed_at is not None


# ── 2. Сессии (A.3) ──────────────────────────────────────────────────────

def test_прочие_сессии_отозваны(стенд):
    """Смена пароля обязана отобрать доступ у того, кто увёл куку.

    Иначе она не решает задачи, ради которой её делают: JWT подписан
    ключом и живёт 30 дней независимо от пароля.
    """
    чужая = TestClient(main.app)
    чужая.cookies.set("access_token", create_token(стенд.uid))
    до = чужая.get("/profile", follow_redirects=False)
    assert до.status_code == 200, "контроль: чужая сессия изначально не работала"

    _сменить(стенд)

    после = чужая.get("/profile", follow_redirects=False)
    assert после.status_code == 302, (
        "старая сессия пережила смену пароля — отпечаток в токене не сработал")
    assert "/login" in после.headers["location"]


def test_текущая_сессия_перевыдана_и_остаётся_рабочей(стенд):
    """Отпечаток сменился у ВСЕХ токенов, включая наш собственный.

    Без перевыдачи куки человек выбрасывался бы на вход собственным
    действием — и выглядело бы это как поломка, а не как защита.
    """
    r = _сменить(стенд)
    новая = _кука_из_ответа(r)
    assert новая, "новая кука не выдана — заявитель выброшен собственным действием"

    свежий = TestClient(main.app)
    свежий.cookies.set("access_token", новая)
    assert свежий.get("/profile", follow_redirects=False).status_code == 200, (
        "выданная кука не работает")


def test_отпечаток_в_новой_куке_совпадает_с_базой(стенд):
    """Проверяем не «кука работает», а что в ней зашит ИМЕННО новый
    отпечаток: совпадение по случайности здесь невозможно, а вот выдача
    токена со старым нулём выглядела бы точно так же на первом запросе."""
    from jose import jwt
    from auth import SECRET_KEY, ALGORITHM
    r = _сменить(стенд)
    u = _пользователь(стенд.uid)
    assert _pwd_stamp(u) != 0
    полезное = jwt.decode(_кука_из_ответа(r), SECRET_KEY, algorithms=[ALGORITHM])
    assert полезное["pwd"] == _pwd_stamp(u), (полезное, _pwd_stamp(u))


# ── 3. Отрицательные контроли (A.5) ──────────────────────────────────────

def test_неверный_текущий_пароль_отказ_и_ни_одного_письма(стенд):
    r = _сменить(стенд, текущий="не тот пароль")
    assert r.status_code == 403, r.text
    assert стенд.почта.ушло == [], "ушло письмо о смене, которой не было"
    u = _пользователь(стенд.uid)
    assert verify_password(ПАРОЛЬ, u.password_hash), "пароль всё-таки сменился"


def test_новый_совпадает_со_старым_отказ(стенд):
    r = _сменить(стенд, новый=ПАРОЛЬ)
    assert r.status_code == 400, r.text
    assert стенд.почта.ушло == []
    assert _пользователь(стенд.uid).password_changed_at is None, (
        "отпечаток сменился — то есть все сессии отозваны ни за чем")


@pytest.mark.parametrize("короткий", ["", "a", "12345"])
def test_короткий_новый_пароль_отказ_с_названным_минимумом(стенд, короткий):
    r = _сменить(стенд, новый=короткий)
    assert r.status_code == 400, (короткий, r.text)
    assert str(main.MIN_PASSWORD_LEN) in r.json()["error"], (
        "минимум не назван — человеку нечем понять, насколько длиннее")
    assert стенд.почта.ушло == []


def test_минимум_объявлен_ОДИН_раз(стенд):
    """Число не должно стоять на месте вызова: их три (регистрация, сброс
    по ссылке, смена в профиле), и разъехались бы они молча."""
    import io
    текст = io.open("main.py", encoding="utf-8").read()
    assert "len(password) < 6" not in текст
    assert "len(новый) < 6" not in текст


def test_повтор_не_совпал_отказ(стенд):
    r = _сменить(стенд, повтор="другое-совсем")
    assert r.status_code == 400, r.text
    assert стенд.почта.ушло == []
    assert _пользователь(стенд.uid).password_changed_at is None


def test_пустой_текущий_пароль_отказ(стенд):
    r = _сменить(стенд, текущий="")
    assert r.status_code == 400
    assert стенд.почта.ушло == []


def test_без_сессии_401(стенд):
    c = TestClient(main.app)
    r = c.post("/api/change-password",
               json={"current": ПАРОЛЬ, "new": НОВЫЙ, "new2": НОВЫЙ})
    assert r.status_code == 401, r.status_code
    assert стенд.почта.ушло == []


# ── 4. Гейт подтверждённой почты и лимит писем (A.4) ─────────────────────

def test_смена_пароля_НЕ_обходит_гейт_подтверждения(стенд):
    """Метод пишущий, значит гейт применяется САМ (§5.3). Исключения ему
    быть не должно: смысл уведомления — чтобы владелец ящика узнал
    о смене, а у неподтверждённого ящика владелец нам неизвестен."""
    assert not main._гейт_путь_исключён("/api/change-password")

    db = SessionLocal()
    неподтв = _завести(db, f"unv-{uuid.uuid4().hex[:8]}@local.test",
                       подтверждён=False)
    uid = неподтв.id
    db.close()

    c = TestClient(main.app)
    c.cookies.set("access_token", create_token(uid))
    r = c.post("/api/change-password",
               json={"current": ПАРОЛЬ, "new": НОВЫЙ, "new2": НОВЫЙ})
    assert r.status_code == main.ГЕЙТ_КОД, r.status_code
    assert стенд.почта.ушло == []
    assert verify_password(ПАРОЛЬ, _пользователь(uid).password_hash)


def test_уведомление_уходит_владельцу_и_называет_что_делать(стенд):
    _сменить(стенд)
    письма = [п for п in стенд.почта.ушло if п["вид"] == "password_changed"]
    assert len(письма) == 1, стенд.почта.ушло
    assert письма[0]["кому"] == стенд.адрес
    assert "forgot-password" in письма[0]["html"], (
        "владельцу не сказано, чем возвращать аккаунт, если это был не он")


def test_уведомление_НЕ_тратит_суточный_запас_адреса(стенд):
    """Тот же довод, что у смены адреса и письма о переборе: запас в 8 писем
    на адрес — ресурс владельца, из которого он берёт письмо сброса."""
    _сменить(стенд)
    письмо = [п for п in стенд.почта.ушло if п["вид"] == "password_changed"][0]
    assert письмо["лимит"] is False


def test_у_уведомления_свой_кулдаун(стенд):
    """Вторая смена подряд письма не шлёт: окно своё, а не общий запас."""
    _сменить(стенд)
    assert len([п for п in стенд.почта.ушло if п["вид"] == "password_changed"]) == 1
    r = _сменить(стенд, текущий=НОВЫЙ, новый="Tretij-Parol-2026")
    assert r.status_code == 200, r.text
    assert len([п for п in стенд.почта.ушло if п["вид"] == "password_changed"]) == 1, (
        "кулдаун уведомления не сработал")
    # И сама смена при этом прошла — кулдаун письма её не блокирует
    assert verify_password("Tretij-Parol-2026",
                           _пользователь(стенд.uid).password_hash)


def test_сбой_отправки_уведомления_НЕ_отменяет_смену(стенд):
    """Пароль уже сменён — откатывать нечего. Но молчать нельзя: причина
    печатается строкой (§6.0.1), а человеку смена подтверждается честно."""
    стенд.почта.вернуть = "http_500: Resend прилёг"
    r = _сменить(стенд)
    assert r.status_code == 200, r.text
    assert verify_password(НОВЫЙ, _пользователь(стенд.uid).password_hash)


# ── 5. Пересечение с незавершённой сменой адреса (A.5, последний пункт) ──

def test_смена_пароля_ГАСИТ_заявку_на_смену_адреса(стенд):
    """ЗАМЕРЕННЫЙ ЗАХВАТ АККАУНТА, а не гигиена.

    Письмо владельцу про начатую смену адреса говорит: «Смените пароль,
    и заявка станет недействительной». До 2026-08-20 это было НЕПРАВДОЙ —
    и владелец, выполнив нашу же инструкцию, терял аккаунт.
    """
    стенд.post("/api/change-email",
               json={"email": f"chuzhoy-{uuid.uuid4().hex[:6]}@local.test",
                     "password": ПАРОЛЬ})
    assert _пользователь(стенд.uid).pending_email, "контроль: заявки не было"

    _сменить(стенд)

    u = _пользователь(стенд.uid)
    assert u.pending_email is None and u.pending_email_token is None, (
        "заявка пережила смену пароля — письмо владельцу врёт")


def test_ссылка_смены_адреса_ПОСЛЕ_смены_пароля_не_работает(стенд):
    """Тот самый шаг 3 замера: ссылке сессия не нужна, она проверяется
    по токену. Проверять надо ПЕРЕХОД, а не поле в базе — поле могли
    очистить, а токен оставить живым во второй колонке."""
    import re
    стенд.post("/api/change-email",
               json={"email": f"chuzhoy2-{uuid.uuid4().hex[:6]}@local.test",
                     "password": ПАРОЛЬ})
    письмо = [п for п in стенд.почта.ушло if п["вид"] == "change_email"][0]
    токен = re.search(r"/change-email/([A-Za-z0-9_-]+)", письмо["html"]).group(1)
    свой = _пользователь(стенд.uid).email

    _сменить(стенд)

    # Без сессии — именно так пойдёт посторонний из своего ящика
    чистый = TestClient(main.app)
    r = чистый.get(f"/change-email/{токен}", follow_redirects=False)
    assert "email_error=bad_token" in r.headers["location"], r.headers["location"]
    assert _пользователь(стенд.uid).email == свой, (
        "адрес входа уехал по ссылке, которую смена пароля обязана была погасить")


def test_смена_пароля_гасит_и_ссылку_сброса(стенд):
    """Та же природа: ссылка сброса равна доступу к аккаунту и на сессию
    не смотрит."""
    db = SessionLocal()
    u = db.query(User).filter(User.id == стенд.uid).first()
    u.reset_token = "живой-токен-сброса"
    db.commit()
    db.close()

    _сменить(стенд)
    assert _пользователь(стенд.uid).reset_token is None


def test_смена_адреса_требует_УЖЕ_НОВОГО_пароля(стенд):
    """Обратная сторона: после смены пароля заявка на адрес подаётся
    новым паролем, а старый там отказывает. Иначе старый пароль остался бы
    рабочим ключом хотя бы к одному действию."""
    _сменить(стенд)
    старым = стенд.post("/api/change-email",
                        json={"email": "kuda@local.test", "password": ПАРОЛЬ})
    assert старым.status_code == 403, старым.text
    новым = стенд.post("/api/change-email",
                       json={"email": f"kuda-{uuid.uuid4().hex[:6]}@local.test",
                             "password": НОВЫЙ})
    assert новым.status_code == 200, новым.text
