"""ПРОВЕРКА 68: НИЖНЯЯ ПАНЕЛЬ РАЗДЕЛОВ НА ТЕЛЕФОНЕ (№352, «мобильный-1», блок 1).

На телефоне разделы инструмента переезжают в нижнюю панель — это ТОТ ЖЕ
ряд вкладок (`.v2-tabs-dock`), закреплённый у низа окна. Спрашивается
на 360, 390 и 430 (эмуляция телефона с сенсором) и на 1600:

  1. ПАНЕЛЬ ЕСТЬ ТАМ, ГДЕ ПОЛОЖЕНА, — HH (4 раздела), питание (4),
     аптечка (3): видна, закреплена, низ совпадает с низом окна ±1,
     верхнего ряда вкладок в шапке нет. И НЕТ там, где не положена:
     Enshrouded, главная, профиль, пять разделов админки, тренировки.
  2. ПОСЛЕДНИЙ ЭЛЕМЕНТ НЕ ПЕРЕКРЫТ — страница прокручена КОЛЕСОМ до
     конца, от низа самого нижнего элемента в потоке до верха панели
     ≥ 0 px (допуск 0.5 px на дробную высоту документа). Мерится содержимое, а не отступ: отступ может стоять,
     а элемент — лечь под панель по другой причине.
  3. ПЕРЕКЛЮЧЕНИЕ НАЖАТИЕМ — каждый раздел панели нажимается как рукой
     (`click` по видимой кнопке): кнопка становится выбранной, её раздел
     виден, остальные скрыты.
  4. НА КОМПЬЮТЕРЕ (1600) ПАНЕЛИ НЕТ — ряд вкладок стоит в шапке
     в потоке, как до письма.

Браузер ВИДИМЫЙ (§6.0.3): меряются положение и перекрытие. В базу
не пишет.

  --замер     таблица чисел без вердикта (код 0)
  --контроль  подлог №1: снят нижний отступ страницы под панель —
              последний элемент уходит под панель, шаг 2 обязан упасть
"""
import os
import sys

try:
    import probe_guard  # noqa: F401  ПРОПУСК вместо трассы (§6.0.1)
except ImportError:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_hover as ch  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ТЕЛЕФОН = (360, 390, 430)
ДЕСКТОП = 1600

# (путь, имя, разделов на панели; 0 — панели быть не должно)
ЭКРАНЫ = [
    ("/hh", "hh", 4),
    ("/nutrition", "питание", 4),
    ("/medkit", "аптечка", 3),
    ("/enshrouded", "enshrouded", 0),
    ("/", "главная", 0),
    ("/profile", "профиль", 0),
    ("/admin/users", "админ · пользователи", 0),
    ("/admin/products", "админ · продукты", 0),
    ("/admin/exercises", "админ · упражнения", 0),
    ("/admin/enshrouded", "админ · enshrouded", 0),
    ("/admin/usage", "админ · расход", 0),
    ("/workout", "тренировки · программа", 0),
    ("/workout/profile", "тренировки · профиль", 0),
]

ГЛУШИТЕЛЬ = """addEventListener('DOMContentLoaded', () => { const s = document.createElement('style');
  s.textContent = '*, *::before, *::after { transition: none !important; animation: none !important; scroll-behavior: auto !important; }';
  document.head.appendChild(s); });"""

ПОДЛОГ_ОТСТУП = """addEventListener('DOMContentLoaded', () => { const s = document.createElement('style');
  s.textContent = 'body { padding-bottom: 0 !important; }';
  document.head.appendChild(s); });"""

ПАНЕЛЬ = r"""() => {
  const R = e => e.getBoundingClientRect();
  const вид = e => e.checkVisibility({opacityProperty: true, visibilityProperty: true})
                 && R(e).width > 0 && R(e).height > 0;
  const H = innerHeight;
  const ряды = [...document.querySelectorAll('.v2-tabs')].filter(вид);
  const закреп = ряды.filter(e => getComputedStyle(e).position === 'fixed');
  const вшапке = ряды.filter(e => getComputedStyle(e).position !== 'fixed' && e.closest('.v2-page-head'));
  const п = закреп[0];
  return {панелей: закреп.length, вшапке: вшапке.length,
          разделов: п ? [...п.querySelectorAll('.v2-tab')].filter(вид).length : 0,
          низ: п ? Math.round((H - R(п).bottom) * 10) / 10 : null,
          верх: п ? R(п).top : null};
}"""

НИЗ = r"""() => {
  const R = e => e.getBoundingClientRect();
  const п = [...document.querySelectorAll('.v2-tabs')].find(e => getComputedStyle(e).position === 'fixed');
  if (!п) return null;
  let низ = -1e9, кто = '';
  for (const e of document.body.querySelectorAll('*')) {
    if (п.contains(e)) continue;
    if (!e.checkVisibility({opacityProperty: true, visibilityProperty: true})) continue;
    const c = getComputedStyle(e);
    if (c.position === 'fixed' || e.closest('[hidden], .modal-ov:not(.open)')) continue;
    // внутри фиксированного предка — не содержимое страницы
    let ф = e.parentElement, в_фикс = false;
    while (ф) { if (getComputedStyle(ф).position === 'fixed') { в_фикс = true; break; } ф = ф.parentElement; }
    if (в_фикс) continue;
    const b = R(e); if (b.height < 1 || b.width < 1) continue;
    if (b.bottom > низ) { низ = b.bottom; кто = (e.className || e.tagName).toString().slice(0, 40); }
  }
  return {зазор: Math.round((R(п).top - низ) * 10) / 10, кто,
          прокручено: Math.round(scrollY), максимум: Math.round(document.documentElement.scrollHeight - innerHeight)};
}"""

ВЫБОР = r"""(кн) => {
  const R = e => e.getBoundingClientRect();
  const вид = e => !!e && e.checkVisibility({opacityProperty: true, visibilityProperty: true}) && R(e).height > 0;
  const п = [...document.querySelectorAll('.v2-tabs')].find(e => getComputedStyle(e).position === 'fixed');
  const все = [...п.querySelectorAll('.v2-tab')];
  const к = все[кн];
  const ключ = к.dataset.view || к.dataset.tab;
  const раздел = document.getElementById('view-' + ключ) || document.getElementById('tab-' + ключ);
  const выбран = к.classList.contains('active') || к.classList.contains('is-active');
  const другие = все.filter((x, i) => i !== кн && (x.classList.contains('active') || x.classList.contains('is-active'))).length;
  const чужие = все.filter((x, i) => i !== кн).map(x => x.dataset.view || x.dataset.tab)
    .map(k => document.getElementById('view-' + k) || document.getElementById('tab-' + k)).filter(вид).length;
  return {ключ, выбран, другие, раздел_виден: вид(раздел), чужие_видны: чужие};
}"""

_шаги = []


def шаг(имя, ок, подробно="", собрано=None):
    if собрано is not None and собрано == 0:
        исход = "ПРОПУСК"
    else:
        исход = "OK" if ок else "ПЛОХО"
    _шаги.append((имя, исход))
    print("  %-6s %-44s %s" % (исход, имя, подробно))


def прогон(подлог=None, печать=True):
    from playwright.sync_api import sync_playwright
    import browser_window  # noqa: F401  окно — на втором мониторе
    _шаги.clear()
    with sync_playwright() as p:
        бр = p.chromium.launch(headless=False)
        try:
            for ш in ТЕЛЕФОН + (ДЕСКТОП,):
                тел = ш < 800
                ctx = бр.new_context(viewport={"width": ш, "height": 800}, has_touch=тел, is_mobile=False)
                стр = ctx.new_page()
                стр.add_init_script(ГЛУШИТЕЛЬ)
                if подлог:
                    стр.add_init_script(подлог)
                ch._войти(стр)
                print("\n── ширина %d ──" % ш)
                for путь, имя, разделов in ЭКРАНЫ:
                    стр.goto(ch.БАЗА + путь, wait_until="networkidle", timeout=45000)
                    стр.wait_for_timeout(400)
                    з = стр.evaluate(ПАНЕЛЬ)
                    if not тел:
                        if разделов:
                            шаг("%d %s: панели нет, вкладки в шапке" % (ш, имя),
                                з["панелей"] == 0 and з["вшапке"] == 1,
                                "панелей %d, рядов в шапке %d" % (з["панелей"], з["вшапке"]))
                        continue
                    if not разделов:
                        шаг("%d %s: панели нет" % (ш, имя), з["панелей"] == 0,
                            "панелей %d" % з["панелей"])
                        continue
                    шаг("%d %s: панель у низа, %d раздела" % (ш, имя, разделов),
                        з["панелей"] == 1 and з["вшапке"] == 0 and з["разделов"] == разделов
                        and з["низ"] is not None and abs(з["низ"]) <= 1,
                        "панелей %d, в шапке %d, разделов %d, до низа окна %s"
                        % (з["панелей"], з["вшапке"], з["разделов"], з["низ"]))
                    if з["панелей"] != 1:
                        continue
                    # 1б. до кнопок панели дотягивается нажатие на середине
                    # прокрутки: содержимое с `z-index` не ложится поверх
                    стр.mouse.move(ш / 2, 300)
                    стр.mouse.wheel(0, 600)
                    стр.wait_for_timeout(200)
                    сверху = стр.evaluate("""() => { const п = [...document.querySelectorAll('.v2-tabs')]
                        .find(e => getComputedStyle(e).position === 'fixed');
                      return [...п.querySelectorAll('.v2-tab')].map(к => { const b = к.getBoundingClientRect();
                        const т = document.elementFromPoint(b.left + b.width / 2, b.top + b.height / 2);
                        return !!т && к.contains(т); }); }""")
                    шаг("%d %s: панель поверх содержимого" % (ш, имя), all(сверху),
                        "дотягивается %d из %d" % (sum(сверху), len(сверху)), собрано=len(сверху))
                    # 2. прокрутка колесом до конца
                    стр.mouse.move(ш / 2, 300)
                    for _ in range(60):
                        стр.mouse.wheel(0, 1500)
                        стр.wait_for_timeout(30)
                        if стр.evaluate("scrollY + innerHeight >= document.documentElement.scrollHeight - 1"):
                            break
                    стр.wait_for_timeout(200)
                    н = стр.evaluate(НИЗ)
                    шаг("%d %s: последний элемент над панелью" % (ш, имя),
                        # допуск полпикселя: высота документа дробная, а прокрутка
                        # целая — у низа остаётся до 0.4 px (замер). Настоящее
                        # перекрытие — высота панели, 56 px (подлог №1)
                        н is not None and н["зазор"] >= -0.5 and н["прокручено"] >= н["максимум"] - 1,
                        "зазор %s px (%s), прокручено %s из %s" % (н["зазор"], н["кто"], н["прокручено"], н["максимум"]) if н else "нет замера")
                    # 3. переключение нажатием — обратным порядком, чтобы первый
                    # раздел (открытый по умолчанию) тоже был выбран нажатием
                    кнопки = стр.locator(".v2-tabs.v2-tabs-dock .v2-tab")
                    всего = кнопки.count()
                    плохо = []
                    for i in list(range(всего - 1, -1, -1)):
                        к = кнопки.nth(i)
                        if not к.is_visible():
                            плохо.append("%d не видна" % i)
                            continue
                        try:
                            к.click(timeout=3000)
                        except Exception:
                            плохо.append("%d: нажатие не дошло" % i)
                            continue
                        стр.wait_for_timeout(300)
                        в = стр.evaluate(ВЫБОР, i)
                        if not (в["выбран"] and в["раздел_виден"] and в["другие"] == 0 and в["чужие_видны"] == 0):
                            плохо.append("%s %s" % (в["ключ"], в))
                    шаг("%d %s: разделы переключаются нажатием" % (ш, имя), not плохо,
                        "нажато %d, ошибок %d %s" % (всего, len(плохо), "; ".join(плохо)[:160]), собрано=всего)
                ctx.close()
        finally:
            бр.close()
    плохих = sum(1 for _, и in _шаги if и == "ПЛОХО")
    пропусков = sum(1 for _, и in _шаги if и == "ПРОПУСК")
    if печать:
        print("\nИТОГ: шагов %d, плохих %d, пропусков %d" % (len(_шаги), плохих, пропусков))
    return плохих, пропусков


def контроль():
    print("ЧИСТЫЙ ПРОГОН")
    плохих, _ = прогон(печать=False)
    if плохих:
        print("КОНТРОЛЬ НЕДЕЙСТВИТЕЛЕН: грязная основа (%d плохих)" % плохих)
        return 2
    print("\nПОДЛОГ №1: снят нижний отступ страницы под панель")
    прогон(ПОДЛОГ_ОТСТУП, печать=False)
    упали = [и for и, х in _шаги if х == "ПЛОХО" and "последний элемент" in и]
    print("  упало шагов «последний элемент над панелью»: %d из 9" % len(упали))
    ок = len(упали) == 9
    print("КОНТРОЛЬ: %s" % ("ПОДЛОГ НАЙДЕН" if ок else "ПОДЛОГ НЕ НАЙДЕН"))
    return 0 if ок else 1


def main():
    if "--контроль" in sys.argv:
        sys.exit(контроль())
    print("НИЖНЯЯ ПАНЕЛЬ РАЗДЕЛОВ НА ТЕЛЕФОНЕ")
    плохих, пропусков = прогон()
    if "--замер" in sys.argv:
        sys.exit(0)
    sys.exit(1 if плохих else (2 if пропусков and not плохих and пропусков == len(_шаги) else 0))


if __name__ == "__main__":
    main()
