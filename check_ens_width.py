# -*- coding: utf-8 -*-
"""ЗАМЕР ШИРИНЫ РАЗДЕЛА ENSHROUDED И ЗАЗОРА МЕЖДУ ПОДПИСЯМИ СЛОТОВ.

Не проверка (кода «правильно» у неё нет по половине вопросов) — МЕРКА.
Отвечает числами на три вопроса, которые в постановке владельца слиты
в один:

  · сколько раздел занимает от экрана — полоса шапки и полоса сетки
    ОТДЕЛЬНО: они ограничиваются разными правилами и разъехаться могут
    независимо;
  · сколько карточек в ряду и какой они ширины;
  · ЗАЗОР МЕЖДУ СОСЕДНИМИ ПОДПИСЯМИ СЛОТОВ внутри карточки.

ПРО ЗАЗОР — ГЛАВНОЕ. Меряется не ширина подписи и не ширина слота,
а РАССТОЯНИЕ МЕЖДУ ФАКТИЧЕСКИМИ ПРЯМОУГОЛЬНИКАМИ ТЕКСТА: `.slot-lbl`
шире своего текста (у него text-align: center внутри слота 54px),
и по коробке зазор всегда положителен, тогда как буквы уже слиплись.
Текстовый прямоугольник берётся через Range.getBoundingClientRect —
это то, что видит глаз.

Считаются только пары слотов В ОДНОЙ СТРОКЕ (разница верхних краёв
меньше 4px): у перенесённых на другую строку «зазор» отрицателен
по построению и находкой не является.
"""
import os, sys, json, statistics

БАЗА = os.environ.get("ENSW_BASE", "http://127.0.0.1:8899")
ШИРИНЫ = [(1440, 900, False), (2560, 1400, False), (390, 844, True)]

ЗАМЕР_JS = r"""
() => {
  const прям = el => { const r = el.getBoundingClientRect();
                       return {x:r.x, y:r.y, w:r.width, h:r.height}; };
  // Фактический прямоугольник ТЕКСТА внутри элемента, а не коробки.
  const текстПрям = el => {
    const r = document.createRange(); r.selectNodeContents(el);
    const b = r.getBoundingClientRect(); r.detach && r.detach();
    return {x:b.x, y:b.y, w:b.width, h:b.height, t:(el.textContent||'').trim()};
  };
  const out = {
    экран: window.innerWidth,
    шапка: null, сетка: null, карточки: [], пары: []
  };
  const бар = document.querySelector('.ens-bar-row');
  if (бар) out.шапка = прям(бар);
  const сетки = [...document.querySelectorAll('.sets-grid')];
  if (сетки.length) {
    out.сетка = прям(сетки[0]);
    const cs = getComputedStyle(сетки[0]);
    out.колонок = cs.gridTemplateColumns.split(' ').filter(Boolean).length;
    out.колонка_px = cs.gridTemplateColumns.split(' ')[0];
  }
  const карты = [...document.querySelectorAll('.set-card')];
  out.карточек_всего = карты.length;
  if (карты.length) out.карточка = прям(карты[0]);

  for (const карта of карты) {
    const имя = (карта.querySelector('.card-name')||{}).textContent || '?';
    const lbl = [...карта.querySelectorAll('.slot-lbl')];
    for (let i = 0; i + 1 < lbl.length; i++) {
      const a = текстПрям(lbl[i]), b = текстПрям(lbl[i+1]);
      if (Math.abs(a.y - b.y) > 4) continue;      // разные строки
      out.пары.push({сет: имя.trim(), a: a.t, b: b.t,
                     зазор: +(b.x - (a.x + a.w)).toFixed(2)});
    }
  }
  return out;
}
"""


def _войти(стр):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import make_local_user as _сид
    стр.goto(f"{БАЗА}/login", wait_until="domcontentloaded", timeout=45000)
    стр.fill("input[name=email]", _сид.EMAIL)
    стр.fill("input[name=password]", _сид.PASSWORD)
    if стр.locator(".cf-turnstile").count():
        try:
            стр.wait_for_function(
                "() => { const e = document.querySelector"
                "('[name=\"cf-turnstile-response\"]'); return e && e.value; }",
                timeout=20000)
        except Exception:
            pass
    стр.click("button[type=submit]")
    стр.wait_for_timeout(2500)
    if "/login" in стр.url:
        raise RuntimeError(f"ВХОД НЕ ПРОШЁЛ: остались на {стр.url}")


def прогон():
    from playwright.sync_api import sync_playwright
    итог = {}
    with sync_playwright() as p:
        бр = p.chromium.launch()
        for ш, в, сенсор in ШИРИНЫ:
            к = бр.new_context(viewport={"width": ш, "height": в},
                               has_touch=сенсор, is_mobile=сенсор)
            стр = к.new_page()
            _войти(стр)
            стр.goto(f"{БАЗА}/enshrouded", wait_until="networkidle", timeout=60000)
            стр.wait_for_selector(".set-card", timeout=30000)
            стр.wait_for_timeout(800)
            итог[ш] = стр.evaluate(ЗАМЕР_JS)
            к.close()
        бр.close()
    return итог


def печать(итог):
    for ш, d in итог.items():
        print(f"\n══ ШИРИНА ОКНА {ш} ═══════════════════════════════════")
        э = d["экран"]
        for имя, ключ in (("шапка (.ens-bar-row)", "шапка"),
                          ("сетка (.sets-grid)", "сетка"),
                          ("карточка", "карточка")):
            r = d.get(ключ)
            if not r:
                print(f"  {имя:24} — нет в дереве"); continue
            поле = round(r["x"], 1)
            print(f"  {имя:24} ширина {r['w']:7.1f} из {э} "
                  f"({100*r['w']/э:5.1f}%), левый край {поле}")
        print(f"  колонок в сетке          {d.get('колонок','?')} "
              f"(колонка {d.get('колонка_px','?')})")
        print(f"  карточек всего           {d.get('карточек_всего',0)}")
        пары = d["пары"]
        if not пары:
            print("  пар подписей             НЕТ"); continue
        зазоры = [p["зазор"] for p in пары]
        плохие = [p for p in пары if p["зазор"] <= 0]
        print(f"  пар подписей в строке    {len(пары)}")
        print(f"  зазор мин / медиана / макс   "
              f"{min(зазоры):.2f} / {statistics.median(зазоры):.2f} / {max(зазоры):.2f}")
        print(f"  СЛИПШИХСЯ ПАР (зазор ≤ 0)    {len(плохие)}")
        for p in плохие[:12]:
            print(f"      {p['зазор']:7.2f}  «{p['a']}» + «{p['b']}»   — {p['сет']}")
        if len(плохие) > 12:
            print(f"      … ещё {len(плохие)-12}")


if __name__ == "__main__":
    итог = прогон()
    печать(итог)
    if "--json" in sys.argv:
        путь = sys.argv[sys.argv.index("--json") + 1]
        with open(путь, "w", encoding="utf-8") as f:
            json.dump(итог, f, ensure_ascii=False, indent=1)
        print(f"\nсырые числа: {путь}")
    плохих = sum(1 for d in итог.values() for p in d["пары"] if p["зазор"] <= 0)
    print(f"\nИТОГО СЛИПШИХСЯ ПАР ПО ТРЁМ ШИРИНАМ: {плохих}")
    sys.exit(1 if плохих else 0)
