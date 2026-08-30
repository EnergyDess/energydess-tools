# -*- coding: utf-8 -*-
"""ЧЕМ ЧУЖИЕ САЙТЫ ДОБИВАЮТСЯ НУЛЯ СДВИГА (BACKLOG №222, блок A).

Владелец проверил руками: на трёх чужих сайтах Ctrl+Shift+R не даёт
ни одного прыжка, на нашем даёт. Значит рецепт существует, и брать
его надо ЗАМЕРОМ, а не подбором наугад — это третий заход подряд
про шрифт, и два предыдущих подбирали.

НЕ ПРОВЕРКА, А МЕРКА: чужие сайты меняются без нашего участия,
кода «правильно» тут нет, код возврата всегда 0 (то же устройство,
что у check_medkit_sources и check_sources_geo).

ДВА ВОПРОСА, И ОНИ РАЗНЫЕ:

  · РЕЦЕПТ (--рецепт) — что вообще скачивается и как объявлено:
    файлы, домены, весь запасной ряд, ВСЕ описатели @font-face,
    предзагрузка, вшивание в CSS, подмножество ли это.
  · СДВИГ (--сдвиг) — сколько элементов переезжает при подмене
    гарнитуры. Мерка ТА ЖЕ, что у нас: снимок запасной гарнитурой,
    затем шрифт подсовывается через FontFace, снимок снова.
    Сравнение идёт `check_font_shift._сравнить` — второй реализации
    диффа в проекте нет (§6.0.7).

ПОЧЕМУ МЕРКА СДВИГА ПЕРЕНОСИМАЯ, А НЕ ПРОСТО «ОТКРЫТЬ И ПОСМОТРЕТЬ».
Наша `check_font_shift` знает адреса НАШИХ файлов и имя семейства
наизусть. Здесь и то и другое СНИМАЕТСЯ с самой страницы первым
проходом: адреса — из ответов сети, описатели — из CSSOM (а для
чужого origin, где `cssRules` бросает, — разбором скачанного текста
таблицы). Сайт без веб-шрифтов при этом честно даёт ноль, и это
не «проба слепа», а ответ: качать нечего.

  py check_font_recipe.py                 # рецепт плюс сдвиг по всем
  py check_font_recipe.py --рецепт        # только рецепт
  py check_font_recipe.py --сдвиг         # только сдвиг
  py check_font_recipe.py --контроль      # проба обязана видеть подмену
  py check_font_recipe.py --сайт URL      # свой адрес
"""
import os, re, sys

from check_font_shift import _сравнить, ЗАМЕР, ПОРОГ

НАШ = os.environ.get("HOVER_BASE", "http://127.0.0.1:8899")
САЙТЫ = [
    ("veyrax.ru", "https://veyrax.ru/"),
    ("shtruzel.ru", "https://shtruzel.ru/"),
    ("github.com", "https://github.com/"),
    ("НАШ /login", НАШ + "/login"),
]
ШРИФТ_РАСШ = (".woff2", ".woff", ".ttf", ".otf", ".eot")

# ОПИСАТЕЛИ СНИМАЮТСЯ ИЗ CSSOM, А ГДЕ ОН ЗАКРЫТ — ИЗ ТЕКСТА.
# Для чужого origin `sheet.cssRules` бросает SecurityError, и молча
# пропустить такую таблицу значило бы напечатать «описателей нет»
# про сайт, у которого их полтора десятка, — тот самый немой отказ.
СНЯТЬ_FONTFACE = r"""(async () => {
  const prav = [], zakr = [];
  for (const sh of document.styleSheets) {
    let rules = null;
    try { rules = sh.cssRules; } catch (e) { rules = null; }
    if (rules === null) { if (sh.href) zakr.push(sh.href); continue; }
    for (const r of rules) {
      if (r.constructor.name === 'CSSFontFaceRule' || r.type === 5)
        prav.push({otkuda: sh.href || '<inline>', tekst: r.cssText});
    }
  }
  for (const href of zakr) {
    try {
      const t = await (await fetch(href)).text();
      const m = t.match(/@font-face\s*\{[^}]*\}/g) || [];
      for (const b of m) prav.push({otkuda: href, tekst: b.replace(/\s+/g, ' ')});
    } catch (e) { prav.push({otkuda: href, tekst: '<NE PROCHITAN: ' + e + '>'}); }
  }
  const pred = [...document.querySelectorAll('link[rel=preload][as=font]')]
    .map(l => l.href);
  const sem = new Set();
  document.querySelectorAll('body *').forEach(e => {
    if (e.children.length === 0 && (e.textContent || '').trim().length > 2)
      sem.add(getComputedStyle(e).fontFamily);
  });
  return {pravila: prav, predzagruzka: pred,
          semeystva: [...sem].slice(0, 6),
          body: getComputedStyle(document.body).fontFamily,
          lic: document.fonts.size};
})()"""


def _описатель(текст, имя):
    м = re.search(r"%s\s*:\s*([^;}]+)" % re.escape(имя), текст, re.I)
    return м.group(1).strip() if м else "—"


def _рецепт_сайта(бр, имя, url):
    """Первый проход: что скачивается и как объявлено."""
    кон = бр.new_context(viewport={"width": 1440, "height": 900})
    стр = кон.new_page()
    файлы = []

    def ответ(r):
        u = r.url
        if u.split("?")[0].lower().endswith(ШРИФТ_РАСШ) or \
           (r.request.resource_type == "font"):
            try:
                размер = len(r.body())
            except Exception:
                размер = -1
            файлы.append({"url": u, "байт": размер,
                          "тип": (r.headers or {}).get("content-type", "—"),
                          "домен": re.sub(r"^https?://([^/]+).*", r"\1", u)})

    стр.on("response", ответ)
    try:
        стр.goto(url, wait_until="domcontentloaded", timeout=45000)
        try:
            стр.wait_for_load_state("networkidle", timeout=20000)
        except Exception:
            pass
        стр.wait_for_timeout(1200)
        данные = стр.evaluate(СНЯТЬ_FONTFACE)
    except Exception as e:
        кон.close()
        return {"имя": имя, "url": url, "ошибка": str(e)[:200]}
    кон.close()
    вшито = sum(1 for п in данные["pravila"] if "data:" in п["tekst"])
    return {"имя": имя, "url": url, "файлы": файлы, "вшито": вшито, **данные}


def печать_рецепта(р):
    print("=" * 76)
    print("  %s   %s" % (р["имя"], р["url"]))
    print("=" * 76)
    if "ошибка" in р:
        print("  НЕ ОТКРЫЛСЯ: %s" % р["ошибка"])
        return
    ф = р["файлы"]
    print("  СКАЧАНО ФАЙЛОВ ШРИФТА: %d%s"
          % (len(ф), "" if ф else "   <- КАЧАТЬ НЕЧЕГО"))
    for x in ф:
        print("     %-42s %7d Б  %-20s %s"
              % (x["url"].split("/")[-1][:42], x["байт"],
                 x["тип"].split(";")[0], x["домен"]))
    print("  ВШИТО В CSS (data:font): %d правил" % р["вшито"])
    print("  ПРЕДЗАГРУЗКА: %s"
          % (", ".join(x.split("/")[-1] for x in р["predzagruzka"])
             if р["predzagruzka"] else "нет"))
    print("  font-family У BODY: %s" % р["body"])
    for с in р["semeystva"][:4]:
        if с != р["body"]:
            print("     ещё в тексте: %s" % с[:90])
    print("  ЛИЦ В document.fonts: %d" % р["lic"])
    print("  ПРАВИЛ @font-face: %d" % len(р["pravila"]))
    for п in р["pravila"][:12]:
        т = п["tekst"]
        print("     семья=%-22s display=%-9s size-adjust=%-9s"
              % (_описатель(т, "font-family")[:22],
                 _описатель(т, "font-display"), _описатель(т, "size-adjust")))
        ov = [(k, _описатель(т, k)) for k in
              ("ascent-override", "descent-override", "line-gap-override")]
        ov = ["%s=%s" % (k, v) for k, v in ov if v != "—"]
        ur = _описатель(т, "unicode-range")
        print("        %s | подмножество: %s"
              % (", ".join(ov) if ov else "переопределений метрик НЕТ",
                 ("да, " + ur[:46]) if ur != "—" else "unicode-range НЕ объявлен"))
    if len(р["pravila"]) > 12:
        print("     ... ещё %d правил" % (len(р["pravila"]) - 12))
    print()


# ── СДВИГ: та же мерка, что у нас, но адреса и описатели СНЯТЫЕ ──────
ПОДСУНУТЬ = """(async (spis) => {
  const dela = [];
  for (const sh of spis) {
    const op = {};
    if (sh.weight) op.weight = sh.weight;
    if (sh.style) op.style = sh.style;
    if (sh.unicodeRange) op.unicodeRange = sh.unicodeRange;
    try {
      const f = new FontFace(sh.family, "url('" + sh.url + "')", op);
      dela.push(f.load().then(x => document.fonts.add(x)).catch(() => null));
    } catch (e) {}
  }
  await Promise.all(dela);
  await document.fonts.ready;
  document.body.offsetHeight;
  return document.fonts.size;
})"""


def _семья_для(url, правила):
    """Какому семейству принадлежит файл — по правилу, где он назван."""
    файл = url.split("/")[-1].split("?")[0]
    for п in правила:
        if файл and файл in п["tekst"]:
            return (_описатель(п["tekst"], "font-family").strip("'\" "),
                    _описатель(п["tekst"], "font-weight"),
                    _описатель(п["tekst"], "font-style"),
                    _описатель(п["tekst"], "unicode-range"))
    return (None, None, None, None)


def _сдвиг_сайта(бр, имя, url, рец, контроль=False):
    if "ошибка" in рец:
        return (имя, 0, 0, 0.0, "", 0.0, "не открылся", 0, 0, 0.0)
    подсунуть = []
    for ф in рец["файлы"]:
        сем, вес, стиль, ur = _семья_для(ф["url"], рец["pravila"])
        if not сем:
            continue
        э = {"family": сем, "url": ф["url"]}
        if вес and вес != "—":
            э["weight"] = вес
        if стиль and стиль != "—":
            э["style"] = стиль
        if ur and ur != "—":
            э["unicodeRange"] = ur
        подсунуть.append(э)
    кон = бр.new_context(viewport={"width": 1440, "height": 900})
    стр = кон.new_page()
    # ШРИФТЫ ОТБИТЫ: снимок «до» обязан быть запасной гарнитурой,
    # иначе подмену мерить не с чем (тот же довод, что в check_font_shift).
    стр.route("**/*", lambda r: r.abort()
              if (r.request.resource_type == "font"
                  or r.request.url.split("?")[0].lower().endswith(ШРИФТ_РАСШ))
              else r.continue_())
    стр.add_init_script(ЗАМЕР)
    try:
        стр.goto(url, wait_until="domcontentloaded", timeout=45000)
        try:
            стр.wait_for_load_state("networkidle", timeout=20000)
        except Exception:
            pass
        стр.wait_for_timeout(1200)
        до = стр.evaluate("window.__snap()")
        if контроль:
            стр.evaluate(
                "document.documentElement.style.setProperty("
                "'font-family', \"'Courier New', monospace\", 'important');"
                "document.body.style.setProperty("
                "'font-family', \"'Courier New', monospace\", 'important')")
            стр.wait_for_timeout(600)
            лиц = -1
        else:
            стр.unroute("**/*")
            лиц = стр.evaluate(ПОДСУНУТЬ, подсунуть) if подсунуть else 0
            стр.wait_for_timeout(700)
        после = стр.evaluate("window.__snap()")
        cls = стр.evaluate("window.__cls") or 0.0
    except Exception as e:
        кон.close()
        return (имя, 0, 0, 0.0, "", 0.0, "сбой: %s" % str(e)[:50], 0, 0, 0.0)
    кон.close()
    дв, макс, имя_макс, гор, вер, макс_в, имя_в = _сравнить(до, после, ПОРОГ)
    прим = ("подсунуто лиц: %d" % лиц) if лиц >= 0 else "подлог Courier"
    if not подсунуть and not контроль:
        прим = "ВЕБ-ШРИФТОВ НЕТ — подменять нечем"
    return (имя, len(до), дв, макс, имя_макс, cls, прим, гор, вер, макс_в)


def доказать_подлог(чисто, с_подлогом):
    """ПОДЛОГ СОСТОЯЛСЯ — доказательство отдельно от вердикта (§6.0.3).

    Вердикт «сдвинулось N элементов» доказательством не является:
    столько же могло сдвинуться и от подмены настоящим шрифтом.
    Доказательство — МАКСИМУМ смещения при подмене на Courier обязан
    быть ЗАМЕТНО больше, чем при подмене настоящей гарнитурой: Courier
    моноширинный и по метрикам далёк от любой из измеряемых. Не вырос —
    подлог до страницы не доехал, и её ноль ничего не значит.
    """
    return с_подлогом[3] > чисто[3] + 5 or (с_подлогом[2] > чисто[2] > 0)


def печать_сдвига(строки, заголовок):
    print(заголовок)
    print("  %-14s %7s %8s %6s %6s %9s %9s %8s  %s"
          % ("сайт", "элем.", "СДВИНУЛ", "ГОРИЗ", "ВЕРТ", "макс,px",
             "макс-В", "CLS", "примечание"))
    for с in строки:
        имя, всего, дв, макс, им, cls, прим, гор, вер, макс_в = с
        print("  %-14s %7d %8d %6d %6d %9.1f %9.1f %8.4f  %s"
              % (имя, всего, дв, гор, вер, макс, макс_в, cls, прим))
    print()


def main():
    from playwright.sync_api import sync_playwright
    свой = None
    if "--сайт" in sys.argv:
        свой = sys.argv[sys.argv.index("--сайт") + 1]
    сайты = [("свой", свой)] if свой else САЙТЫ
    только_рецепт = "--рецепт" in sys.argv
    только_сдвиг = "--сдвиг" in sys.argv
    контроль = "--контроль" in sys.argv
    with sync_playwright() as p:
        бр = p.chromium.launch()
        рецепты = {}
        for имя, url in сайты:
            рецепты[имя] = _рецепт_сайта(бр, имя, url)
        if not только_сдвиг:
            print("\nРЕЦЕПТ ШРИФТА — ЧТО СКАЧИВАЕТСЯ И КАК ОБЪЯВЛЕНО\n")
            for имя, _ in сайты:
                печать_рецепта(рецепты[имя])
        if not только_рецепт:
            строки = [_сдвиг_сайта(бр, имя, url, рецепты[имя])
                      for имя, url in сайты]
            печать_сдвига(строки, "СДВИГ ПРИ ПОДМЕНЕ ГАРНИТУРЫ "
                                  "(снимок запасной -> шрифт подсунут)")
            if контроль:
                к = [_сдвиг_сайта(бр, имя, url, рецепты[имя], контроль=True)
                     for имя, url in сайты]
                печать_сдвига(к, "КОНТРОЛЬ: гарнитура подменена на Courier")
                видит = sum(1 for а, б in zip(строки, к)
                            if доказать_подлог(а, б))
                print("ДОКАЗАТЕЛЬСТВО ПОДЛОГА: подлог увидели %d сайтов из %d."
                      % (видит, len(к)))
                print("Сайт, на котором проба слепа, не вправе утверждать ноль.")
        бр.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
