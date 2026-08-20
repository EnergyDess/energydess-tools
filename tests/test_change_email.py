# -*- coding: utf-8 -*-
"""СМЕНА АДРЕСА ВХОДА С ПОДТВЕРЖДЕНИЕМ НА НОВОМ АДРЕСЕ (BACKLOG №3).

ЧТО ЗДЕСЬ ГЛАВНОЕ, И ЭТО НЕ «СМЕНА РАБОТАЕТ». Работающая смена — половина,
причём безопасная: если она сломана, человек это увидит сразу. Опасны
три другие, и каждая молчит:

  1. АДРЕС СМЕНИЛСЯ ДО ПОДТВЕРЖДЕНИЯ. Тогда угнанная сессия отбирает
     аккаунт целиком: владелец теряет вход и заодно возможность сбросить
     пароль — письмо уйдёт уже не ему. Ошибки при этом никакой,
     всё «сработало»;

  2. ССЫЛКА СРАБОТАЛА ДВАЖДЫ или пережила свой срок. Живая ссылка
     в чужом ящике — это отложенный перенос аккаунта, и заметить его
     нечем: она просто лежит и ждёт;

  3. ОТКАЗ БЕЗ ОТКАЗА. Занятый адрес, неверный пароль, кривая форма —
     на всё это письмо уходить НЕ должно. Иначе мы шлём человеку письмо
     на адрес, на который он всё равно не переедет, и тратим чужой
     суточный запас на заведомо бесполезное сообщение.

Приложение поднимается настоящим TestClient на временной базе: половина
проверяемого — это порядок действий внутри обработчика, и подделкой
в Python он не проверяется.

ПОЧТУ НЕ ШЛЁМ, А ПЕРЕХВАТЫВАЕМ. `send_email` подменяется на запись
в список — тест обязан видеть не только «письмо ушло», но и КУДА и КОГДА
ушло, а живой Resend этого не покажет и вдобавок будет стоить денег.
"""

import os
import sys
import tempfile
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault(
    "DB_PATH", str(Path(tempfile.gettempdir()) / f"hh_chgmail_{uuid.uuid4().hex}.db"))

import main                                                    # noqa: E402
from database import SessionLocal, User                        # noqa: E402
from fastapi.testclient import TestClient                      # noqa: E402
from auth import hash_password, create_token, verify_password  # noqa: E402

ПАРОЛЬ = "Pa$$w0rd-локальный"


class Почта:
    """Перехваченные письма: (кому, тема, вид). Плюс подставной сбой."""

    def __init__(self):
        self.ушло = []
        self.вернуть = None          # что вернёт send_email вместо None

    async def __call__(self, to, subject, html, text=None, db=None,
                       user_id=None, kind="verify", учитывать_лимит=True):
        self.ушло.append({"кому": to, "тема": subject, "вид": kind,
                          "лимит": учитывать_лимит, "html": html})
        return self.вернуть

    def кому(self):
        return [п["кому"] for п in self.ушло]


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
    свой = _завести(db, f"vladelec-{метка}@local.test")
    чужой = _завести(db, f"chuzhoy-{метка}@local.test")
    uid, чужой_адрес, свой_адрес = свой.id, чужой.email, свой.email
    db.close()

    c = TestClient(main.app)
    c.cookies.set("access_token", create_token(uid))
    c.uid = uid
    c.почта = почта
    c.свой_адрес = свой_адрес
    c.чужой_адрес = чужой_адрес
    c.новый = f"novy-{метка}@local.test"
    yield c


def _пользователь(uid):
    db = SessionLocal()
    try:
        return db.query(User).filter(User.id == uid).first()
    finally:
        db.close()


def _ссылка_из_письма(письмо):
    """Токен из html — тот же путь, которым пойдёт человек."""
    import re
    m = re.search(r"/change-email/([A-Za-z0-9_-]+)", письмо["html"])
    assert m, "в письме нет ссылки подтверждения"
    return m.group(1)


# ── 1. Обычный путь ──────────────────────────────────────────────────────

def test_заявка_НЕ_меняет_адрес_сразу(стенд):
    """Главная проверка: до перехода по ссылке вход остаётся прежним."""
    r = стенд.post("/api/change-email",
                   json={"email": стенд.новый, "password": ПАРОЛЬ})
    assert r.status_code == 200, r.text
    u = _пользователь(стенд.uid)
    assert u.email == стенд.свой_адрес, "адрес сменился ДО подтверждения"
    assert u.pending_email == стенд.новый
    assert u.pending_email_token


def test_письмо_подтверждения_уходит_на_НОВЫЙ_адрес(стенд):
    стенд.post("/api/change-email",
               json={"email": стенд.новый, "password": ПАРОЛЬ})
    подтверждение = [п for п in стенд.почта.ушло if п["вид"] == "change_email"]
    assert len(подтверждение) == 1
    assert подтверждение[0]["кому"] == стенд.новый, (
        "подтверждение ушло не на новый адрес — тогда смену подтверждает "
        "тот, кто и так уже внутри")


def test_на_старый_адрес_уходит_уведомление(стенд):
    """G.2: владелец ящика узнаёт о попытке, даже если сессию увели."""
    стенд.post("/api/change-email",
               json={"email": стенд.новый, "password": ПАРОЛЬ})
    уведомление = [п for п in стенд.почта.ушло
                   if п["вид"] == "change_email_notice"]
    assert len(уведомление) == 1
    assert уведомление[0]["кому"] == стенд.свой_адрес
    assert стенд.новый in уведомление[0]["html"], (
        "в уведомлении не назван новый адрес — владелец не поймёт, "
        "куда уводят аккаунт")


def test_уведомление_НЕ_тратит_суточный_запас_старого_адреса(стенд):
    """Иначе четырьмя заявками выжигается письмо сброса пароля владельцу.

    Ровно та ошибка, которую §8.1 уже разбирал на письме о переборе,
    и лечится она тем же: свой кулдаун плюс `учитывать_лимит=False`.
    """
    стенд.post("/api/change-email",
               json={"email": стенд.новый, "password": ПАРОЛЬ})
    уведомление = [п for п in стенд.почта.ушло
                   if п["вид"] == "change_email_notice"][0]
    assert уведомление["лимит"] is False


def test_переход_по_ссылке_меняет_адрес(стенд):
    стенд.post("/api/change-email",
               json={"email": стенд.новый, "password": ПАРОЛЬ})
    токен = _ссылка_из_письма(
        [п for п in стенд.почта.ушло if п["вид"] == "change_email"][0])
    r = стенд.get(f"/change-email/{токен}", follow_redirects=False)
    assert r.status_code == 302
    assert "email_changed=1" in r.headers["location"]
    u = _пользователь(стенд.uid)
    assert u.email == стенд.новый
    assert u.pending_email is None and u.pending_email_token is None


# ── 2. Отрицательные контроли (G.5) ──────────────────────────────────────

def test_повторный_переход_по_ссылке_отказ(стенд):
    """Одноразовость. Отказ ВНЯТНЫЙ, а не молчание."""
    стенд.post("/api/change-email",
               json={"email": стенд.новый, "password": ПАРОЛЬ})
    токен = _ссылка_из_письма(
        [п for п in стенд.почта.ушло if п["вид"] == "change_email"][0])
    первый = стенд.get(f"/change-email/{токен}", follow_redirects=False)
    assert "email_changed=1" in первый.headers["location"]

    второй = стенд.get(f"/change-email/{токен}", follow_redirects=False)
    assert второй.status_code == 302
    assert "email_error=bad_token" in второй.headers["location"], (
        "повторный переход не отказал — токен одноразовым не является")
    assert _пользователь(стенд.uid).email == стенд.новый


def test_просроченная_ссылка_отказ_и_заявка_стирается(стенд):
    стенд.post("/api/change-email",
               json={"email": стенд.новый, "password": ПАРОЛЬ})
    токен = _ссылка_из_письма(
        [п for п in стенд.почта.ушло if п["вид"] == "change_email"][0])

    db = SessionLocal()
    u = db.query(User).filter(User.id == стенд.uid).first()
    u.pending_email_expires = datetime.utcnow() - timedelta(minutes=1)
    db.commit()
    db.close()

    r = стенд.get(f"/change-email/{токен}", follow_redirects=False)
    assert "email_error=expired" in r.headers["location"]
    u = _пользователь(стенд.uid)
    assert u.email == стенд.свой_адрес, "просроченная ссылка всё-таки сменила адрес"
    assert u.pending_email is None, (
        "протухшая заявка осталась в базе — она бы всплыла на экране "
        "как «ждёт подтверждения» и ждала бы вечно")


def test_занятый_адрес_отказ_ДО_отправки_письма(стенд):
    """G.5: письма не должно быть вовсе, а не «письмо ушло, потом отказ»."""
    r = стенд.post("/api/change-email",
                   json={"email": стенд.чужой_адрес, "password": ПАРОЛЬ})
    assert r.status_code == 409, r.text
    assert стенд.почта.ушло == [], (
        "ушло письмо по заявке, которая всё равно не могла быть выполнена")
    assert _пользователь(стенд.uid).pending_email is None


def test_неверный_пароль_отказ_и_ни_одного_письма(стенд):
    r = стенд.post("/api/change-email",
                   json={"email": стенд.новый, "password": "не тот пароль"})
    assert r.status_code == 403
    assert стенд.почта.ушло == []
    assert _пользователь(стенд.uid).pending_email is None


@pytest.mark.parametrize("адрес", ["без-собаки", "две@@собаки.рф", "", "a@b",
                                   "пробел в@адресе.ру"])
def test_кривой_адрес_отказ_до_письма(стенд, адрес):
    r = стенд.post("/api/change-email",
                   json={"email": адрес, "password": ПАРОЛЬ})
    assert r.status_code == 400, (адрес, r.text)
    assert стенд.почта.ушло == []


def test_свой_же_адрес_отказ(стенд):
    r = стенд.post("/api/change-email",
                   json={"email": стенд.свой_адрес, "password": ПАРОЛЬ})
    assert r.status_code == 400
    assert стенд.почта.ушло == []


def test_отмена_бездействием_вход_по_старому_адресу_работает(стенд):
    """G.5, последний: не перешли по ссылке — ничего не изменилось.

    Проверяется не поле в базе, а ВХОД: именно он и есть то, что человек
    теряет, если смена применилась раньше времени.
    """
    стенд.post("/api/change-email",
               json={"email": стенд.новый, "password": ПАРОЛЬ})
    u = _пользователь(стенд.uid)
    assert u.email == стенд.свой_адрес
    assert verify_password(ПАРОЛЬ, u.password_hash), (
        "пароль перестал подходить к старому адресу")

    db = SessionLocal()
    нет_такого = db.query(User).filter(User.email == стенд.новый).count()
    db.close()
    assert нет_такого == 0, "новый адрес уже числится адресом входа"


# ── 3. Взаимодействие с гейтом и с лимитом писем (G.4) ───────────────────

def test_смена_адреса_НЕ_обходит_гейт_подтверждения(стенд):
    """Непроверенный аккаунт не меняет адрес — POST закрыт middleware.

    И исключения ему быть не должно: смена адреса — это запись, а гейт
    объявлен «непроверенный не записывает ничего» (§5.3). Заодно
    проверяем, что список исключений его действительно не содержит:
    лишняя строка в этом списке — дыра, которую никто не заметит.
    """
    assert not main._гейт_путь_исключён("/api/change-email")

    db = SessionLocal()
    неподтв = _завести(db, f"unv-{uuid.uuid4().hex[:8]}@local.test",
                       подтверждён=False)
    uid = неподтв.id
    db.close()

    c = TestClient(main.app)
    c.cookies.set("access_token", create_token(uid))
    r = c.post("/api/change-email", json={"email": "kuda@local.test",
                                          "password": ПАРОЛЬ})
    assert r.status_code == main.ГЕЙТ_КОД, r.status_code
    assert стенд.почта.ушло == []


def test_ссылка_подтверждения_гейтом_НЕ_закрыта(стенд):
    """Первое, что ломается у неаккуратного гейта, — путь подтверждения.

    Здесь он не в списке исключений и не должен быть: гейт держит только
    методы записи, а это GET. Тест сторожит именно это рассуждение —
    добавят GET в ГЕЙТ_МЕТОДЫ, и ссылка из письма перестанет работать
    молча.
    """
    assert "GET" not in main.ГЕЙТ_МЕТОДЫ


def test_сбой_отправки_НЕ_выдаётся_за_успех(стенд):
    """Письмо не ушло — говорим об этом. Заявка при этом остаётся."""
    стенд.почта.вернуть = "http_500: Resend прилёг"
    r = стенд.post("/api/change-email",
                   json={"email": стенд.новый, "password": ПАРОЛЬ})
    assert r.status_code == 502, r.text
    assert "Письмо не отправилось" in r.json()["error"]
    assert _пользователь(стенд.uid).pending_email == стенд.новый


def test_исчерпанный_запас_адреса_назван_своим_текстом(стенд):
    """`limit:` — не сбой канала, и говорить «попробуйте через минуту» здесь
    было бы неправдой: через минуту ничего не изменится."""
    стенд.почта.вернуть = "limit: за сутки на этот адрес уже ушло 8 писем"
    r = стенд.post("/api/change-email",
                   json={"email": стенд.новый, "password": ПАРОЛЬ})
    assert r.status_code == 502
    assert "завтра" in r.json()["error"].lower()


def test_без_сессии_отказ(стенд):
    c = TestClient(main.app)
    r = c.post("/api/change-email", json={"email": "x@local.test",
                                          "password": ПАРОЛЬ})
    assert r.status_code == 401


# ── 4. Контроль самой проверки ───────────────────────────────────────────

def test_перехват_писем_работает(стенд):
    """Отрицательный контроль обвязки: без него «письма не было» неотличимо
    от «перехватчик не подключился», и половина тестов выше проходила бы
    на любом коде."""
    assert стенд.почта.ушло == []
    стенд.post("/api/change-email",
               json={"email": стенд.новый, "password": ПАРОЛЬ})
    assert len(стенд.почта.ушло) == 2, (
        "перехвачено %d писем вместо двух" % len(стенд.почта.ушло))
