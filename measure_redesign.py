"""ЗАМЕР РАЗНОБОЯ СТИЛЕЙ ЗАЛОГИНЕННОЙ ЧАСТИ (задача 352, письмо 1, блок 1).

МЕРКА, код возврата 0 при записанном файле. Только чтение.
    py measure_redesign.py docs/redesign_before.md
Полный вывод — в файл аргументом, сводка — строкой JSON на экран.
Залогиненная часть — все static/*.css, кроме landing.css и botamin.css.
Разделы: переменные, прямые значения мимо переменных, варианты
компонентов, шрифты, цвета инструментов. Прямые значения считаются
по объявлению, вне var(): цвет, кегль, ненулевой отступ, ненулевое
скругление, тень с литералом. Этим же счётом живёт «долг» сторожа v2.
"""
import re, sys, os, glob, collections, json
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
ROOT = os.path.dirname(os.path.abspath(__file__))
АРГ = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else None
os.chdir(ROOT)

# Залогиненная часть: все страничные стили, кроме гостевой главной
# и витрины тестового задания.
ВНЕ = {"static/landing.css", "static/botamin.css"}
CSS = sorted(p.replace("\\", "/") for p in glob.glob("static/*.css"))
CSS = [p for p in CSS if p not in ВНЕ and "@v2" not in open(p, encoding="utf-8").readline()]
TPL = sorted(p.replace("\\", "/") for p in glob.glob("templates/*.html"))
TPL_IN = [p for p in TPL if not os.path.basename(p).startswith(("landing", "demo_", "botamin", "_landing"))]
JS = sorted(p.replace("\\", "/") for p in glob.glob("static/*.js") if not p.endswith("icons.js"))

def без_комм(t):
    return re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), t, flags=re.S)

def читать(p):
    return open(p, encoding="utf-8").read()

ЦВЕТ = re.compile(r"#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)|hsla?\([^)]*\)|\b(white|black)\b")
ЧИСЛО = re.compile(r"(?<![\w-])-?\d*\.?\d+(px|rem|em)\b")
def очистить_var(v):
    # var(--x, запасное) — запасное значение тоже прямое, но считаем только вне var()
    s, d, r = v, 0, ""
    i = 0
    while i < len(s):
        if s.startswith("var(", i):
            d2, j = 1, i + 4
            while j < len(s) and d2:
                d2 += s[j] == "("; d2 -= s[j] == ")"; j += 1
            r += " V "; i = j; continue
        r += s[i]; i += 1
    return r

ВИДЫ = {
    "цвет": (re.compile(r"^(color|background(-color)?|border(-(top|right|bottom|left))?(-color)?|outline(-color)?|fill|stroke|caret-color|text-decoration-color|accent-color)$"), ЦВЕТ),
    "размер шрифта": (re.compile(r"^font-size$"), ЧИСЛО),
    "отступ": (re.compile(r"^(padding|margin|gap|row-gap|column-gap)(-(top|right|bottom|left|inline|block)(-(start|end))?)?$"), ЧИСЛО),
    "скругление": (re.compile(r"^border(-(top|bottom)-(left|right))?-radius$"), ЧИСЛО),
    "тень": (re.compile(r"^(box-shadow|text-shadow)$"), re.compile(r".")),
}

def прямые_значения(путь, текст=None):
    """ПРЯМЫЕ ЗНАЧЕНИЯ МИМО ПЕРЕМЕННЫХ в одном CSS-файле: список
    (вид, строка, свойство, значение, число попаданий). Один счёт на мерку
    блока 1 и на сторож v2 (`check_v2_tokens.py`), второго нет (§6.0.7).
    Объявления `--имя:` не считаются: токен и есть место для значения.
    `текст` — подменённое содержимое файла (подлоги сторожа, без записи на диск)."""
    найдено = []
    t = без_комм(читать(путь) if текст is None else текст)
    for i, line in enumerate(t.split("\n"), 1):
        for m in re.finditer(r"(?<![\w-])([a-z-]+)\s*:\s*([^;{}]+)", line):
            prop, val = m.group(1), m.group(2)
            if prop.startswith("--"):
                continue
            v = очистить_var(val)
            for в, (pp, rx) in ВИДЫ.items():
                if not pp.match(prop):
                    continue
                if в == "тень":
                    vv = v.strip()
                    if vv in ("none", "V", "inherit", "") or re.fullmatch(r"[V ,]+", vv):
                        continue
                    if not (ЦВЕТ.search(vv) or ЧИСЛО.search(vv)):
                        continue
                    hits = 1
                elif в in ("отступ", "скругление"):
                    hits = len([x for x in rx.finditer(v) if float(re.sub(r"[a-z]+", "", x.group(0)) or 0) != 0])
                else:
                    hits = len(rx.findall(v))
                if hits:
                    найдено.append((в, i, prop, val, hits))
    return найдено


def помечен_v2(путь):
    """Файл, написанный по v2: метка `@v2` в первой строке."""
    with open(путь, encoding="utf-8") as ф:
        return "@v2" in ф.readline()

def main():
    global out
    out = ["# Замер «до» редизайна залогиненной части", "", "Собрано командой `py measure_redesign.py docs/redesign_before.md` (задача 352, письмо 1, блок 1). Руками не правится.", ""]
    def P(*a):
        out.append(" ".join(str(x) for x in a))

    # ---------- 1. Переменные ----------
    decl = collections.OrderedDict()   # имя -> (файл, строка, значение)
    for p in CSS + ["static/landing.css"]:
        t = без_комм(читать(p))
        for i, line in enumerate(t.split("\n"), 1):
            for m in re.finditer(r"(?<![\w-])(--[a-zA-Z0-9_-]+)\s*:\s*([^;{}]+)", line):
                if m.group(1) not in decl:
                    decl[m.group(1)] = (p, i, m.group(2).strip())

    все_тексты = "\n".join(без_комм(читать(p)) for p in CSS + ["static/landing.css", "static/botamin.css"]) + \
        "\n".join(читать(p) for p in TPL + JS)
    исп = collections.Counter(re.findall(r"var\(\s*(--[a-zA-Z0-9_-]+)", все_тексты))
    исп_js = set(re.findall(r"['\"](--[a-zA-Z0-9_-]+)['\"]", все_тексты))

    def вид(имя, знач):
        n = имя.lower()
        if n.startswith("--font") or "font-family" in n: return "шрифт"
        if n.startswith("--text-") and re.search(r"(rem|px|clamp|em)\b", знач): return "размер шрифта"
        if n.startswith(("--space", "--gap", "--pad")): return "отступ"
        if n.startswith("--radius"): return "скругление"
        if n.startswith("--shadow"): return "тень"
        if re.search(r"#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(|color-mix", знач): return "цвет"
        if n.startswith(("--dur", "--ease")): return "анимация"
        return "прочее"

    по_виду = collections.defaultdict(list)
    for имя, (f, i, v) in decl.items():
        по_виду[вид(имя, v)].append((имя, f, i, v))

    P("## 1. CSS-переменные")
    P("")
    P("| вид | объявлено | не используется | где (файл:строка первой) |")
    P("|---|---:|---:|---|")
    неисп_все = []
    for в in ["цвет", "шрифт", "размер шрифта", "отступ", "скругление", "тень", "анимация", "прочее"]:
        L = по_виду.get(в, [])
        неисп = [x for x in L if исп[x[0]] == 0 and x[0] not in исп_js]
        неисп_все += [(в,) + x for x in неисп]
        файлы = collections.Counter(f for _, f, _, _ in L)
        где = ", ".join(f"{f}×{n}" for f, n in файлы.most_common(4))
        P(f"| {в} | {len(L)} | {len(неисп)} | {где} |")
    P("")
    P("Не используются (ни `var()`, ни строкой в скрипте):")
    for в, имя, f, i, v in неисп_все:
        P(f"- {в}: `{имя}` — {f}:{i} = `{v[:50]}`")
    P("")
    P("Полный список объявлений:")
    for имя, (f, i, v) in decl.items():
        P(f"- `{имя}` [{вид(имя, v)}] {f}:{i} = `{v[:60]}` (var: {исп[имя]})")

    # ---------- 2. Прямые значения ----------
    счёт = collections.defaultdict(collections.Counter)  # вид -> файл -> n
    примеры = collections.defaultdict(list)
    for p in CSS:
        for в, i, prop, val, hits in прямые_значения(p):
            счёт[в][p] += hits
            if len(примеры[(в, p)]) < 3:
                примеры[(в, p)].append(f"{i}: {prop}: {val.strip()[:50]}")
    # инлайновые style= в залогиненных шаблонах
    инлайн = collections.Counter()
    for p in TPL_IN:
        t = читать(p)
        for m in re.finditer(r'style="([^"]*)"', t):
            s = очистить_var(m.group(1))
            if ЦВЕТ.search(s) or ЧИСЛО.search(s): инлайн[p] += 1

    P("")
    P("## 2. Прямые значения мимо переменных (залогиненные стили)")
    P("")
    P("| вид | всего | файлов |")
    P("|---|---:|---:|")
    итог = {}
    for в in ВИДЫ:
        итог[в] = sum(счёт[в].values())
        P(f"| {в} | {итог[в]} | {len(счёт[в])} |")
    P(f"| (инлайновый style= с числом/цветом в шаблонах) | {sum(инлайн.values())} | {len(инлайн)} |")
    P("")
    по_файлам = collections.Counter()
    for в in ВИДЫ:
        for f, n in счёт[в].items(): по_файлам[f] += n
    P("Топ-10 файлов (сумма по всем видам):")
    P("")
    P("| файл | всего | цвет | кегль | отступ | скругл. | тень |")
    P("|---|---:|---:|---:|---:|---:|---:|")
    for f, n in по_файлам.most_common(10):
        P(f"| {f} | {n} | " + " | ".join(str(счёт[в][f]) for в in ВИДЫ) + " |")
    P("")
    P("Примеры (до трёх на вид и файл):")
    for (в, f), L in sorted(примеры.items()):
        P(f"- {в} · {f}: " + " ‖ ".join(L))

    # ---------- 3. Варианты компонентов ----------
    КОМП = {
        "кнопки": r"btn|button",
        "карточки": r"card|panel|box|tile",
        "поля ввода": r"input|field|textarea|select",
        "вкладки": r"tab(?!le)",
        "чипы": r"chip|pill|tag|badge",
        "пустые состояния": r"empty",
    }
    классы_css = collections.defaultdict(set)  # класс -> файлы, где у него есть правило субъектом
    for p in CSS:
        t = без_комм(читать(p))
        for sel in re.findall(r"([^{}]+)\{", t):
            for part in sel.split(","):
                part = part.strip()
                if part.startswith("@") or not part: continue
                последн = re.split(r"[\s>+~]+", part)[-1]
                m = re.match(r"[a-z]*\.([a-zA-Z0-9_-]+)", последн)
                if m: классы_css[m.group(1)].add(p)
    шабл_текст = {p: читать(p) for p in TPL + JS}
    def где(кл):
        return sorted(os.path.basename(p) for p, t in шабл_текст.items()
                      if re.search(r"(class=\"(?:[^\"]*\s)?|classList\.\w+\(\s*['\"]|['\" ])" + re.escape(кл) + r"(?![\w-])", t))
    P("")
    P("## 3. Варианты компонентов (класс — субъект правила в залогиненных стилях)")
    P("")
    P("| вид | классов | из них в style.css | страничных |")
    P("|---|---:|---:|---:|")
    комп_спис = {}
    for в, rx in КОМП.items():
        L = sorted(k for k in классы_css if re.search(rx, k))
        комп_спис[в] = L
        sys_ = [k for k in L if "static/style.css" in классы_css[k]]
        P(f"| {в} | {len(L)} | {len(sys_)} | {len(L) - len(sys_)} |")
    for в, L in комп_спис.items():
        P("")
        P(f"### {в}: {len(L)}")
        for k in L:
            P(f"- `.{k}` — css: {', '.join(os.path.basename(x) for x in sorted(классы_css[k]))}; разметка: {', '.join(где(k)) or '—'}")

    # ---------- 4. Шрифты ----------
    семейства = collections.Counter(); веса = collections.Counter(); где_сем = collections.defaultdict(set)
    for p in CSS:
        t = без_комм(читать(p))
        for m in re.finditer(r"font-family\s*:\s*([^;{}]+)", t):
            v = m.group(1).strip(); семейства[v] += 1; где_сем[v].add(os.path.basename(p))
        for m in re.finditer(r"font-weight\s*:\s*([^;{}]+)", t):
            веса[m.group(1).strip()] += 1
        for m in re.finditer(r"(?<![\w-])font\s*:\s*([^;{}]+)", t):
            семейства["font: " + m.group(1).strip()[:40]] += 1; где_сем["font: " + m.group(1).strip()[:40]].add(os.path.basename(p))
    P("")
    P("## 4. Шрифты в залогиненных стилях")
    P("")
    P("| font-family | объявлений | файлы |")
    P("|---|---:|---|")
    for v, n in семейства.most_common():
        P(f"| `{v[:60]}` | {n} | {', '.join(sorted(где_сем[v]))} |")
    P("")
    P("| font-weight | объявлений |")
    P("|---|---:|")
    for v, n in веса.most_common():
        P(f"| `{v}` | {n} |")
    ff = []
    for p in CSS:
        t = без_комм(читать(p))
        for m in re.finditer(r"@font-face\s*\{([^}]*)\}", t, re.S):
            fam = re.search(r"font-family:\s*([^;]+)", m.group(1)); w = re.search(r"font-weight:\s*([^;]+)", m.group(1))
            ff.append((os.path.basename(p), fam.group(1).strip() if fam else "?", w.group(1).strip() if w else "?"))
    P("")
    P("@font-face в залогиненных стилях: " + "; ".join(f"{a}: {b} {c}" for a, b, c in ff))

    # ---------- 5. Цвета инструментов ----------
    def lum(h):
        h = h.lstrip("#"); r, g, b = (int(h[i:i+2], 16) / 255 for i in (0, 2, 4))
        f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
        return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)
    def кр(a, b):
        la, lb = sorted([lum(a), lum(b)], reverse=True); return (la + 0.05) / (lb + 0.05)
    фон = decl["--surface-0"][2]
    P("")
    P(f"## 5. Цвета инструментов (фон страницы `--surface-0` = {фон})")
    P("")
    P("| инструмент | переменная | значение | к фону | наведение | тусклый | где |")
    P("|---|---|---|---:|---|---|---|")
    for t in ["hh", "nutrition", "medkit", "enshrouded", "workout"]:
        имя = f"--accent-{t}"; f, i, v = decl[имя]
        P(f"| {t} | `{имя}` | {v} | {кр(v, фон):.2f} | {decl[имя+'-hover'][2]} | `{decl[имя+'-dim'][2]}` | {f}:{i} |")
    P("")
    P("Классы тем объявляют `--tool-accent`, `--tool-accent-dim`, `--tool-accent-hover`, `--tool-accent-ink` (style.css, блоки `.theme-*`).")

    # ---------- 6. Светлая тема ----------
    ПРИЗНАКИ_ТЕМЫ = [r"html\.light", r"\.theme-light", r"data-theme=\"light", r"prefers-color-scheme\s*:\s*light",
                     r"theme\.js", r"localStorage\.\w+\(\s*['\"][^'\"]*them"]
    P("")
    P("## 6. Светлая тема")
    P("")
    P("| признак | совпадений в static/*.css, static/*.js, templates, main.py, database.py |")
    P("|---|---:|")
    тексты6 = {p: читать(p) for p in glob.glob("static/*.css") + glob.glob("static/*.js") + TPL + ["main.py", "database.py"]}
    for rx in ПРИЗНАКИ_ТЕМЫ:
        n = sum(len(re.findall(rx, т)) for т in тексты6.values())
        P(f"| `{rx}` | {n} |")
    cs = collections.Counter()
    for p, т in тексты6.items():
        for m in re.finditer(r"color-scheme\s*:\s*([a-z ]+)", т):
            cs[(os.path.basename(p), m.group(1).strip())] += 1
    P("")
    P("`color-scheme` в коде: " + (", ".join(f"{a}: {b}×{n}" for (a, b), n in cs.items()) or "нет"))

    # ---------- 7. Документ дизайн-системы против кода ----------
    d = читать("design-system.md")
    s13 = d[d.index("## 13."):d.index("## 14.")]
    ск = dict(re.findall(r"(--[a-z0-9-]+)\s*:\s*([^;]+);", s13))
    css_s = без_комм(читать("static/style.css"))
    кор = css_s[css_s.index(":root {"):]; кор = кор[:кор.index("\n}")]
    рт = {k: v.strip() for k, v in re.findall(r"(--[a-z0-9-]+)\s*:\s*([^;]+);", кор)}
    P("")
    P("## 7. design-system.md §13 (скелет :root) против static/style.css")
    P("")
    P(f"- токенов в скелете §13: {len(ск)}; в `:root` кода: {len(рт)}")
    P(f"- есть в коде, нет в скелете: {sorted(set(рт) - set(ск)) or 'нет'}")
    P(f"- есть в скелете, нет в коде: {sorted(set(ск) - set(рт)) or 'нет'}")
    разн = [k for k in ск if k in рт and re.sub(r'\s+', '', ск[k]) != re.sub(r'\s+', '', рт[k])]
    P(f"- значение расходится: {разн or 'нет'}")
    P(f"- строк в design-system.md: {d.count(chr(10))}; разделов верхнего уровня: {len(re.findall(r'^## ', d, re.M))}")

    # ---------- 8. Скриншоты «до» ----------
    кадры = sorted(os.path.basename(p) for p in glob.glob("review_screenshots/redesign-before/*.png"))
    P("")
    P("## 8. Скриншоты «до» (review_screenshots/redesign-before/, в git не входят — §8.0)")
    P("")
    P(f"Кадров: {len(кадры)} — " + ", ".join(кадры))

    open(АРГ, "w", encoding="utf-8", newline="\n").write("\n".join(out) + "\n")
    json.dump({"итог_прямых": итог, "инлайн": sum(инлайн.values()), "перем": {k: len(v) for k, v in по_виду.items()},
               "неисп": len(неисп_все), "комп": {k: len(v) for k, v in комп_спис.items()}},
              open(АРГ + ".json", "w", encoding="utf-8"), ensure_ascii=False)
    print(open(АРГ + ".json", encoding="utf-8").read())
    os.remove(АРГ + ".json")
    print("файлы стилей:", len(CSS), CSS)


if __name__ == "__main__":
    main()
