# -*- coding: utf-8 -*-
"""СНИМКИ ЗАХОДА 187 И 185: общая аптечка в seed и чипы отбора.

НЕ проверка — кадры смотрит человек. Кода «правильно» здесь нет.

ЧТО СНИМАЕТСЯ И ЗАЧЕМ ИМЕННО ЭТО:

  чипы            задача 185 перевела «Просрочено» и «+ Категория»
                  на системные варианты. Пиксельный диф сказал «ноль
                  расхождений», но число — не картинка: владелец
                  смотрит на ряд глазами;
  общая аптечка   задача 187: круг теперь в seed, и это ПЕРВЫЕ кадры
                  общей аптечки, снятые не внутри прогона пробы;
  схлопнутая      главный случай D.6 — две пачки Цетрина от РАЗНЫХ
  группа          владельцев в одной карточке;
  панель          участники, приглашения обеих сторон, лента за три
                  дня от обоих;
  после выхода    та же группа, разделившаяся обратно.

СНИМОК «ПОСЛЕ ВЫХОДА» ПИШЕТ В БАЗУ — иначе его не получить: группа
разделяется настоящим выходом участника. Стенд ВОЗВРАЩАЕТСЯ в
сидированное состояние тем же `вернуть_сид`, что у пробы круга;
без этого следующий инструмент снимал бы личную аптечку вместо общей
(§6.0.3, шестая причина неповторимости).

Ширины 2560 и 390 — их назвал владелец; 1440 среди них нет намеренно
(тот же довод, что у задачи 143: экрана такой ширины у него нет).

    py shots_medkit_187.py                  # стенд из HOVER_BASE
    py shots_medkit_187.py --база http://127.0.0.1:8897 --метка до
"""
import os
import sys

from playwright.sync_api import sync_playwright

БАЗА = os.environ.get("HOVER_BASE", "http://127.0.0.1:8899")
МЕТКА = "после"
КУДА = os.environ.get("SHOTS_DIR", "C:/Temp/claude/shots187")
ПОЧТА, ПАРОЛЬ = "screenshot@local.dev", "Screenshot-Local-2026"
ШИРИНЫ = [2560, 390]


def войти(стр, база):
    стр.goto(база + "/login", wait_until="networkidle", timeout=60000)
    стр.wait_for_timeout(1200)
    стр.fill("input[name=email]", ПОЧТА)
    стр.fill("input[name=password]", ПАРОЛЬ)
    стр.click("button[type=submit]")
    стр.wait_for_timeout(2500)
    if "/login" in стр.url:
        raise SystemExit("ОСТАНОВЛЕНО: вход не прошёл — снимать нечего")


def кадр(стр, имя, ширина, селектор=None):
    os.makedirs(КУДА, exist_ok=True)
    путь = "%s/%s-%s-%d.png" % (КУДА, МЕТКА, имя, ширина)
    if селектор:
        el = стр.query_selector(селектор)
        if not el:
            print("   НЕТ НА ЭКРАНЕ: %s" % селектор)
            return None
        el.screenshot(path=путь)
    else:
        стр.screenshot(path=путь, full_page=True, animations="disabled")
    print("   %s" % путь)
    return путь


def снять(b, ширина, выход):
    ctx = b.new_context(viewport={"width": ширина, "height": 1400})
    стр = ctx.new_page()
    войти(стр, БАЗА)
    стр.goto(БАЗА + "/medkit", wait_until="networkidle", timeout=60000)
    стр.wait_for_timeout(1500)
    стр.mouse.move(3, 3)
    print("── ширина %d ──" % ширина)
    кадр(стр, "чипы", ширина, ".apt-chips")
    кадр(стр, "аптечка", ширина)
    группа = стр.query_selector('.apt-card[data-find*="цетрин"]')
    if группа:
        группа.scroll_into_view_if_needed()
        стр.wait_for_timeout(400)
        кадр(стр, "группа-цетрин", ширина, '.apt-card[data-find*="цетрин"]')
    кн = стр.query_selector("#apt-circle-open")
    if кн:
        кн.click()
        стр.wait_for_timeout(900)
        кадр(стр, "панель-участников", ширина)
        for вкл, имя in (("feed", "панель-лента"),
                         ("invites", "панель-приглашения")):
            т = стр.query_selector('[data-ctab="%s"]' % вкл)
            if т:
                т.click()
                стр.wait_for_timeout(600)
                кадр(стр, имя, ширина)
    ctx.close()


def выйти_и_снять(b, ширина):
    """Кадр ПОСЛЕ выхода участника: та же группа, разделённая обратно.

    КРУГ ВОЗВРАЩАЕТСЯ ПЕРЕД КАЖДОЙ ШИРИНОЙ. Первая версия этого
    не делала, и вторая ширина печатала «круга нет — снимать не с чего»:
    выход на 2560 распустил его, и кадр 390 не получился ВОВСЕ.
    Отказ не молчал только потому, что кадр отсутствовал целиком.
    """
    import check_medkit_circle as пр
    пр.вернуть_сид()
    ctx = b.new_context(viewport={"width": ширина, "height": 1400})
    стр = ctx.new_page()
    войти(стр, БАЗА)
    сосед = стр.evaluate(
        """async () => {
             const r = await fetch('/medkit/api/circle',
                                   {headers: {Accept: 'application/json'}});
             const t = await r.json();
             const ч = (t.участники || []).find(x => !x.свой);
             return ч ? ч.id : null; }""")
    if not сосед:
        print("   круга нет — кадр «после выхода» снимать не с чего")
        ctx.close()
        return
    стр.evaluate(
        """async (id) => { await fetch('/medkit/api/circle/leave',
             {method: 'POST', headers: {'Content-Type': 'application/json'},
              body: JSON.stringify({who: id})}); }""", сосед)
    стр.goto(БАЗА + "/medkit", wait_until="networkidle", timeout=60000)
    стр.wait_for_timeout(1200)
    стр.mouse.move(3, 3)
    print("── ширина %d, ПОСЛЕ ВЫХОДА ──" % ширина)
    кадр(стр, "после-выхода", ширина)
    кадр(стр, "после-выхода-цетрин", ширина,
         '.apt-card[data-find*="цетрин"]')
    ctx.close()


def main():
    global БАЗА, МЕТКА
    if "--база" in sys.argv:
        БАЗА = sys.argv[sys.argv.index("--база") + 1]
    if "--метка" in sys.argv:
        МЕТКА = sys.argv[sys.argv.index("--метка") + 1]
    только_чипы = "--чипы" in sys.argv
    print("стенд: %s · метка: %s" % (БАЗА, МЕТКА))
    with sync_playwright() as p:
        b = p.chromium.launch()
        for ш in ШИРИНЫ:
            снять(b, ш, False)
        if not только_чипы:
            for ш in ШИРИНЫ:
                выйти_и_снять(b, ш)
        b.close()
    if not только_чипы:
        # ВОЗВРАТ СТЕНДА — тем же кодом, что у пробы круга
        import check_medkit_circle as пр
        print("стенд возвращён в сидированное: %s"
              % ("да" if пр.вернуть_сид() else "НЕТ"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
