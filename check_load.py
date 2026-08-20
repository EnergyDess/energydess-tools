# -*- coding: utf-8 -*-
"""НАГРУЗОЧНАЯ ПРОБА: отвечает ли /health, пока обработчики заняты базой.

Не проверка, а МЕРКА: понятия «правильно» у неё нет, код возврата всегда 0
(как у check_metrics.py). Числа читает человек и сверяет со ступенями.

═══════════════════════════════════════════════════════════════════════
ПОЧЕМУ /health ОПРАШИВАЕТСЯ НЕЗАВИСИМО, А НЕ ПОДРЯД
═══════════════════════════════════════════════════════════════════════

Последовательный опрос («спросил — дождался — спросил снова») НЕ ВИДИТ
остановки цикла по построению: пока цикл стоит, проба висит на своём же
запросе и вопросов не задаёт. Дождавшись ответа, она запишет одну большую
задержку и десяток нормальных — медиана выйдет здоровой. Ложный зелёный.

Поэтому вопрос задаётся ПО РАСПИСАНИЮ, раз в 20 мс, независимо от того,
пришёл ли ответ на предыдущий.

Две подпорки, без которых врёт уже сама проба:

  • отдельный HTTP-клиент под опрос. Общий с нагрузкой пул соединений
    ставит опрос в очередь ЗА нагрузкой — и проба меряет свою собственную
    очередь, а не приложение;
  • догон расписания сбрасывается. Если цикл встал на 200 с, расписание
    отстаёт на десять тысяч тактов, и проба, честно их догоняя, выпускает
    десять тысяч запросов разом и вешает сама себя. Проверено: первая
    версия так и повисла.

═══════════════════════════════════════════════════════════════════════
ПОЧЕМУ СТУПЕНЕЙ НЕСКОЛЬКО
═══════════════════════════════════════════════════════════════════════

Урок задачи 103: `asyncio.to_thread` без освобождения соединения улучшил
n=10 (967 → 156 мс) и на n=30 сделал ХУЖЕ исходного в 27 раз. Мерка,
снятая на объёме дефекта, подтверждает починку, создавшую худший дефект
рядом. Значит ступени идут ДО ЗАВЕДОМО ИЗБЫТОЧНОЙ.

Запуск (приложение поднимается заранее, база — НЕ рабочая):

    py check_load.py --порт 8801 --куки <access_token> \
        --ступени 10,30,60,120
"""
import argparse
import asyncio
import statistics
import time

import httpx

ШАГ_ОПРОСА = 0.020          # 50 вопросов в секунду
ПОТОЛОК_В_ПОЛЁТЕ = 25       # больше — проба душит сама себя, а не приложение:
                            # при замершем приложении она за минуту откроет
                            # тысячи сокетов, забьёт очередь приёма и утопит
                            # Windows в TIME_WAIT. Проверено — первая версия
                            # уронила ИМЕННО этим. Такт, на который вопрос
                            # задать не удалось, считается пропущенным,
                            # и пропуски — тот же сигнал, что и задержка


async def _опрос(база, стоп, итоги):
    """Опрос /health по расписанию. Свой клиент, свой пул соединений."""
    в_полёте = set()
    async with httpx.AsyncClient(limits=httpx.Limits(
            max_connections=ПОТОЛОК_В_ПОЛЁТЕ)) as c:
        async def один():
            t = time.perf_counter()
            try:
                r = await c.get(база + "/health", timeout=120.0)
                итоги.append(((time.perf_counter() - t) * 1000, r.status_code))
            except Exception as e:
                итоги.append(((time.perf_counter() - t) * 1000, type(e).__name__))

        след = time.perf_counter()
        пропущено = 0
        while not стоп.is_set():
            в_полёте = {t for t in в_полёте if not t.done()}
            if len(в_полёте) < ПОТОЛОК_В_ПОЛЁТЕ:
                в_полёте.add(asyncio.create_task(один()))
            else:
                пропущено += 1
            след += ШАГ_ОПРОСА
            отстали = time.perf_counter() - след
            if отстали > 0.5:
                # Цикл стоял. Догонять расписание нельзя — см. шапку.
                след = time.perf_counter()
            else:
                await asyncio.sleep(max(0.0, -отстали))
        if в_полёте:
            await asyncio.gather(*в_полёте, return_exceptions=True)
    return пропущено


async def _дождаться_покоя(база, предел=180.0):
    """Ступень начинается с приложения в покое, иначе она мерит хвост
    предыдущей. Возвращает, сколько секунд ушло на восстановление —
    это тоже число: приложение, которому нужны минуты, чтобы перестать
    отвечать таймаутами, здоровым не является."""
    t0 = time.perf_counter()
    async with httpx.AsyncClient() as c:
        подряд = 0
        while time.perf_counter() - t0 < предел:
            try:
                r = await c.get(база + "/health", timeout=3.0)
                подряд = подряд + 1 if r.status_code == 200 else 0
                if подряд >= 5:
                    return time.perf_counter() - t0
            except Exception:
                подряд = 0
            await asyncio.sleep(0.3)
    return time.perf_counter() - t0


async def ступень(база, n, куки, путь, метод, тело, потолок):
    итоги_h = []
    стоп = asyncio.Event()
    покой = await _дождаться_покоя(база)
    async with httpx.AsyncClient(cookies=куки, limits=httpx.Limits(
            max_connections=n + 10)) as c:
        фон = []
        for _ in range(15):
            t = time.perf_counter()
            try:
                await c.get(база + "/health", timeout=10.0)
                фон.append((time.perf_counter() - t) * 1000)
            except Exception:
                фон.append(float("nan"))
        фон = [м for м in фон if м == м] or [float("nan")]

        опрос = asyncio.create_task(_опрос(база, стоп, итоги_h))
        await asyncio.sleep(0.4)
        итоги_h.clear()

        async def нагрузка():
            t = time.perf_counter()
            try:
                r = (await c.post(база + путь, json=тело, timeout=потолок)
                     if метод == "POST" else
                     await c.get(база + путь, timeout=потолок))
                return (time.perf_counter() - t) * 1000, r.status_code
            except Exception as e:
                return (time.perf_counter() - t) * 1000, type(e).__name__

        t0 = time.perf_counter()
        нагр = await asyncio.gather(*[нагрузка() for _ in range(n)])
        пачка = (time.perf_counter() - t0) * 1000
        await asyncio.sleep(0.3)
        стоп.set()
        пропущено = await опрос

    хор = sorted(м for м, к in итоги_h if к == 200)
    сбои = {}
    for _, к in итоги_h:
        if к != 200:
            сбои[к] = сбои.get(к, 0) + 1
    коды = {}
    for _, к in нагр:
        коды[к] = коды.get(к, 0) + 1
    def кв(доля):
        return хор[min(len(хор) - 1, int(len(хор) * доля))] if хор else None
    return {"n": n, "покой": покой, "фон": statistics.median(фон), "пачка": пачка,
            "проб": len(итоги_h), "пропущено": пропущено,
            "мед": statistics.median(хор) if хор else None,
            "p95": кв(0.95), "макс": max(хор) if хор else None,
            "сбои": сбои, "коды": коды}


async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--порт", type=int, required=True)
    p.add_argument("--куки", required=True)
    p.add_argument("--ступени", default="10,30,60,120")
    p.add_argument("--путь", default="/nutrition/api/water")
    p.add_argument("--метод", default="POST")
    p.add_argument("--потолок", type=float, default=120.0,
                   help="таймаут запроса нагрузки, с")
    p.add_argument("--метка", default="")
    a = p.parse_args()
    база = f"http://127.0.0.1:{a.порт}"

    print(f"═══ {a.метка}  {a.метод} {a.путь}  (опрос /health раз в "
          f"{ШАГ_ОПРОСА * 1000:.0f} мс, независимо)", flush=True)
    print("{:>5} {:>9} {:>11} {:>9} {:>9} {:>9} {:>6}  {}".format(
        "n", "фон,мс", "пачка,мс", "h мед", "h p95", "h макс", "проб",
        "исходы нагрузки"), flush=True)
    for n in [int(x) for x in a.ступени.split(",")]:
        r = await ступень(база, n, a.куки and {"access_token": a.куки},
                          a.путь, a.метод, {"amount_ml": 200}, a.потолок)
        ф = lambda v: "—" if v is None else f"{v:.2f}"
        хвост = f"{r['коды']}"
        if r["сбои"]:
            хвост += f"  СБОИ /health: {r['сбои']}"
        if r["пропущено"]:
            хвост += f"  (тактов пропущено: {r['пропущено']})"
        if r["покой"] > 1.5:
            хвост += f"  [восстановление до ступени: {r['покой']:.1f} с]"
        print("{:>5} {:>9.2f} {:>11.1f} {:>9} {:>9} {:>9} {:>6}  {}".format(
            r["n"], r["фон"], r["пачка"], ф(r["мед"]), ф(r["p95"]),
            ф(r["макс"]), r["проб"], хвост), flush=True)
        await asyncio.sleep(1.5)


asyncio.run(main())
