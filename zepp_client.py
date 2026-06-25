# -*- coding: utf-8 -*-
"""
Неофициальный клиент Zepp Life / аккаунта Xiaomi для получения измерений
с умных весов (Mi Body Composition Scale) без официального API — его не
существует. Флоу подтверждён по актуальному (2026) опенсорсному проекту
AlexxIT/SmartScaleConnect (pkg/xiaomi, pkg/zepp): account.xiaomi.com OAuth2
→ обмен кода на токен Zepp (account.zepp.com) → api-mifit.zepp.com/.../weightRecords.

ВАЖНО — известные риски (см. README/чат с пользователем перед реализацией):
- Это реверс-инжиниринг, не официальный API. Xiaomi/Huami может изменить
  флоу без предупреждения — тогда понадобится обновлять этот файл.
- Полный логин по паролю (login()) разлогинивает пользователя в мобильном
  приложении Zepp Life — это особенность серверной сессии Xiaomi, не наша.
  Поэтому app_token/zepp_user_id кешируются в БД (см. ScaleConnection) и
  повторный логин по паролю выполняется только когда кеш не работает —
  не при каждой синхронизации.
"""
import hashlib
import json
import time
import uuid

import httpx

OAUTH2_PARAMS = (
    "_json=true&"
    "client_id=428135909242707968&"
    "pt=1&"
    "redirect_uri=https://api-mifit-cn.huami.com/huami.health.loginview.do&"
    "response_type=code"
)
LOGIN_PREFIX = "&&&START&&&"


class ZeppLoginError(Exception):
    """Логин не удался — неверный пароль либо изменился флоу Xiaomi/Zepp."""


class ZeppApiError(Exception):
    """Логин прошёл, но запрос данных не удался (истёк токен и т.п.)."""


def _strip_prefix(text: str) -> dict:
    if not text.startswith(LOGIN_PREFIX):
        raise ZeppLoginError("неожиданный формат ответа Xiaomi — возможно, изменился флоу")
    return json.loads(text[len(LOGIN_PREFIX):])


def _get_code(client: httpx.Client, start_url: str) -> str:
    """Воспроизводит CheckRedirect-логику оригинала: 2 редиректа проходим
    автоматически, на третьем — не идём дальше, код берём из его Location."""
    url = start_url
    for hop in range(3):
        resp = client.get(url, follow_redirects=False)
        location = resp.headers.get("location")
        if not location:
            raise ZeppLoginError("ожидался редирект от Xiaomi, не получили (изменился флоу?)")
        if hop == 2:
            _, _, code = location.partition("=")
            if not code:
                raise ZeppLoginError("не нашли код авторизации в финальном редиректе")
            return code
        url = httpx.URL(url).join(location)
    raise ZeppLoginError("не удалось получить код авторизации")


def _xiaomi_oauth2_code(client: httpx.Client, username: str, password: str) -> str:
    r = client.get(f"https://account.xiaomi.com/oauth2/authorize?{OAUTH2_PARAMS}")
    r.raise_for_status()
    data1 = _strip_prefix(r.text)
    oauth_login_url = data1.get("data", {}).get("oauthLoginUrl")
    if not oauth_login_url:
        raise ZeppLoginError("Xiaomi не вернул oauthLoginUrl")

    r = client.get(oauth_login_url)
    r.raise_for_status()
    res1 = _strip_prefix(r.text)
    sid, callback, sign, qs = res1.get("sid"), res1.get("callback"), res1.get("_sign"), res1.get("qs")
    if not sid:
        raise ZeppLoginError("Xiaomi не вернул sid — проверь логин")

    password_hash = hashlib.md5(password.encode()).hexdigest().upper()
    device_id = uuid.uuid4().hex[:16]
    r = client.post(
        "https://account.xiaomi.com/pass/serviceLoginAuth2",
        data={"_json": "true", "hash": password_hash, "sid": sid,
              "callback": callback, "_sign": sign, "qs": qs, "user": username},
        headers={"Cookie": f"deviceId={device_id}"},
    )
    r.raise_for_status()
    res2 = _strip_prefix(r.text)
    location = res2.get("location")
    if not location:
        raise ZeppLoginError("неверный логин или пароль Xiaomi")

    return _get_code(client, location)


def login(username: str, password: str) -> dict:
    """Полный логин по паролю — использовать только при первом подключении
    или когда кешированный токен перестал работать. Возвращает
    {"app_token": ..., "zepp_user_id": ...}."""
    with httpx.Client(timeout=30.0) as client:
        code = _xiaomi_oauth2_code(client, username, password)
        r = client.post(
            "https://account.zepp.com/v2/client/login",
            data={
                "app_name": "com.xiaomi.hm.health",
                "app_version": "6.14.0",
                "code": code,
                "country_code": "CN",
                "device_id": str(uuid.uuid4()),
                "device_model": "phone",
                "dn": "api-mifit.zepp.com",
                "grant_type": "request_token",
                "third_name": "xiaomi-hm-mifit",
            },
        )
        r.raise_for_status()
        data = r.json()
        token_info = data.get("token_info", {})
        app_token, zepp_user_id = token_info.get("app_token"), token_info.get("user_id")
        if not app_token or not zepp_user_id:
            raise ZeppLoginError(f"Zepp не вернул токен сессии: {data}")
        return {"app_token": app_token, "zepp_user_id": zepp_user_id}


def fetch_weight_records(app_token: str, zepp_user_id: str, limit: int = 30) -> list:
    """Измерения с весов главного пользователя аккаунта (member -1 —
    без привязки к "членам семьи" в Zepp, см. GetFamilyID("") в оригинале).
    Поля совпадают с тем, что показывает сам Zepp Life: вес, ИМТ, % жира,
    % воды, % мышц (как названо в самом API — точная семантика не
    задокументирована официально), костная масса, висцеральный жир,
    базальный метаболизм, "возраст тела" (в API называется muscleAge)."""
    records = []
    to_time = int(time.time())
    headers = {"apptoken": app_token}
    with httpx.Client(timeout=30.0, headers=headers) as client:
        while len(records) < limit:
            r = client.get(
                f"https://api-mifit.zepp.com/users/{zepp_user_id}/members/-1/weightRecords",
                params={"limit": 200, "toTime": to_time},
            )
            if r.status_code == 401:
                raise ZeppApiError("токен истёк или недействителен — нужен повторный логин")
            r.raise_for_status()
            data = r.json()
            items = data.get("items", [])
            if not items:
                break
            for item in items:
                if item.get("weightType") != 0:
                    continue  # см. оригинал: weightType != 0 — повреждённые значения
                s = item.get("summary", {})
                records.append({
                    "timestamp": item.get("generatedTime"),
                    "weight_kg": s.get("weight"),
                    "bmi": s.get("bmi"),
                    "body_fat_pct": s.get("fatRate"),
                    "water_pct": s.get("bodyWaterRate"),
                    "muscle_rate_pct": s.get("muscleRate"),
                    "bone_mass_kg": s.get("boneMass"),
                    "visceral_fat": s.get("visceralFat"),
                    "bmr": s.get("metabolism"),
                    "body_age": s.get("muscleAge"),
                })
            next_ts = data.get("next", 0)
            if not next_ts or next_ts >= to_time:
                break
            to_time = next_ts
    return records[:limit]
