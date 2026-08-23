# -*- coding: utf-8 -*-
"""ПРОХОД ЭКРАНА УПРАВЛЕНИЯ НАСКВОЗЬ — так, как его проходит человек.

ЗАЧЕМ ОТДЕЛЬНО ОТ `check_ens_admin.py`. Та мерка спрашивает СЕРВЕР:
двадцать пять случаев, у каждого свой код и своя фраза. Она зелёная
и тогда, когда ФОРМА МЕРТВА — отказ при неверных данных можно получить
и от формы, у которой поля выключены, а кнопка не нажимается.

Ровно это и случилось: заход, заведший экран (BACKLOG №137), сдал форму
создания сета с ВЫКЛЮЧЕННЫМИ полями картинки — `disabled` стоял на них
по условию «сет ещё не сохранён». Приёмка была зелёной: сервер отвечал
правильно на всё, о чём его спрашивали, а спросить «можно ли вообще
выбрать файл» было некому. Отсюда правило CLAUDE.md §6.3.

ЧТО СПРАШИВАЕТСЯ ЗДЕСЬ. Каждое действие экрана — от первого нажатия
до НАБЛЮДАЕМОГО результата, и результат берётся не из ответа сервера,
а с экрана и из базы:

    создание сета файлом   · создание сета ссылкой
    правка существующего   · замена картинки
    поиск                  · отбор по категории
    увеличение миниатюры   · удаление: отмена и подтверждение

ОРГАН СЧИТАЕТСЯ ЖИВЫМ, только если до него ДОТЯГИВАЕТСЯ НАЖАТИЕ:
`elementFromPoint` в его центре обязан вернуть его самого или потомка,
и он не `disabled`. Проверка «элемент есть в дереве» этого не заменяет —
выключенное поле в дереве есть.

    py -m uvicorn main:app --port 8899
    py check_ens_admin_ui.py;         echo "код=$?"
    py check_ens_admin_ui.py --следы  # оставить подложенные сеты

Код 1 — хотя бы одно действие не дошло до наблюдаемого результата.
"""
import io
import os
import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import make_local_user as _сид                     # noqa: E402

БАЗА = os.environ.get("ENS_ADMIN_BASE", "http://127.0.0.1:8899")
БД = os.environ.get("DB_PATH") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "app.db")
ФАЙЛОМ = "zz_ui_file"
ССЫЛКОЙ = "zz_ui_url"

# Живой орган: не выключен, виден, и нажатие в его центр попадает
# в него самого или в его потомка. Псевдоэлемент `elementFromPoint`
# отдаёт как самого хозяина, поэтому добранная область считается его.
#
# ЭЛЕМЕНТ СНАЧАЛА ПОДКРУЧИВАЕТСЯ В ВИДИМУЮ ОБЛАСТЬ, и это не удобство:
# `elementFromPoint` отвечает ТОЛЬКО про видимую область и за её
# пределами возвращает null. Без прокрутки проба объявила тремя
# мёртвыми три исправных поля — они просто лежали ниже сгиба внутри
# прокручиваемого окна на ширине 390. Врала проба, а не экран
# (CLAUDE.md §6.0.3): числа сняты на одном и том же коде.
ЖИВОЙ = """(sel) => {
  const e = document.querySelector(sel);
  if (!e) return {есть: false};
  e.scrollIntoView({block: 'center', behavior: 'instant'});
  const r = e.getBoundingClientRect();
  const cs = getComputedStyle(e);
  const виден = r.width > 0 && r.height > 0 && cs.visibility !== 'hidden';
  let попал = null, свой = false;
  if (виден) {
    const t = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
    попал = t ? (t.tagName + (t.id ? '#' + t.id : '')) : null;
    свой = !!(t && (t === e || e.contains(t)));
  }
  return {есть: true, выключен: !!e.disabled, виден: виден,
          размер: [Math.round(r.width), Math.round(r.height)],
          нажатие_попадает: свой, под_курсором: попал};
}"""


def _картинка(w, h, цвет):
    from PIL import Image
    б = io.BytesIO()
    Image.new("RGB", (w, h), цвет).save(б, "JPEG")
    return б.getvalue()


def _из_базы(запрос, *арг):
    c = sqlite3.connect(f"file:{БД}?mode=ro", uri=True)
    try:
        return c.execute(запрос, арг).fetchall()
    finally:
        c.close()


def _войти(стр):
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


def прогон(следы=False, ширина=1440, сенсор=False, кадры=None):
    from playwright.sync_api import sync_playwright
    шаги, ошибки_страницы = [], []

    def шаг(имя, вышло, факт):
        шаги.append((имя, bool(вышло), факт))

    with sync_playwright() as p:
        бр = p.chromium.launch()
        к = бр.new_context(viewport={"width": ширина, "height": 1000},
                           has_touch=сенсор, is_mobile=сенсор)
        стр = к.new_page()
        стр.on("pageerror", lambda e: ошибки_страницы.append(str(e)[:160]))
        _войти(стр)
        стр.goto(f"{БАЗА}/admin/enshrouded", wait_until="networkidle", timeout=60000)
        стр.wait_for_selector("#ens-rows tr", timeout=20000)

        # ── 0. Таблица нарисовалась, и подписи В НЕЙ по-русски ──────
        было_строк = стр.locator("#ens-rows tr").count()
        первая = стр.locator("#ens-rows tr").first.locator("td").all_inner_texts()
        кат, состав = первая[3].strip(), первая[5].strip()
        латиница = [т for т in (кат, состав)
                    if any("a" <= с.lower() <= "z" for с in т)]
        шаг("таблица нарисована", было_строк > 0, f"строк {было_строк}")
        шаг("категория и состав по-русски", not латиница,
            f"категория «{кат}», состав «{состав}»"
            + (f" ← ЛАТИНИЦА: {латиница}" if латиница else ""))

        # ── 1. Увеличение миниатюры ─────────────────────────────────
        якорь = стр.locator(".ens-a-thumbwrap").first
        if якорь.count():
            якорь.scroll_into_view_if_needed()
            if сенсор:
                якорь.click()
            else:
                якорь.hover()
            стр.wait_for_timeout(700)
            зум = стр.evaluate("""() => {
              const о = document.querySelector('.img-zoom');
              if (!о) return null;
              const r = о.getBoundingClientRect();
              return {открыто: о.classList.contains('is-open'),
                      размер: [Math.round(r.width), Math.round(r.height)],
                      за_экраном: r.x < 0 || r.y < 0
                                  || r.right > innerWidth || r.bottom > innerHeight};
            }""")
            шаг("увеличение миниатюры открылось",
                зум and зум["открыто"] and not зум["за_экраном"],
                f"{зум}")
            стр.mouse.move(2, 2)
            стр.mouse.click(2, 2)
            стр.wait_for_timeout(400)
        else:
            шаг("увеличение миниатюры открылось", False, "миниатюр на экране нет")

        # ── 2. ФОРМА СОЗДАНИЯ: живы ли органы ───────────────────────
        стр.click(".ens-a-add")
        стр.wait_for_selector("#f-id", timeout=8000)
        стр.wait_for_timeout(400)
        мёртвые = []
        for sel, имя in [("#f-id", "идентификатор"), ("#f-ru", "название ru"),
                         ("#f-en", "название en"), ("#f-cat", "категория"),
                         ("#f-lvl", "уровень"), ("#f-file", "файл картинки"),
                         ("#f-url", "ссылка на картинку"), ("#f-up", "кнопка «Загрузить»")]:
            с = стр.evaluate(ЖИВОЙ, sel)
            жив = с.get("есть") and not с.get("выключен") and с.get("нажатие_попадает")
            if not жив:
                мёртвые.append((имя, с))
        шаг("в форме создания живы ВСЕ органы", not мёртвые,
            "мертвы: " + "; ".join(f"{и} {с}" for и, с in мёртвые) if мёртвые
            else "все восемь живы")

        # подсказки не обрезаны
        обрез = стр.evaluate("""() => {
          const беды = [];
          for (const e of document.querySelectorAll('#ens-body input, #ens-body select, #ens-q')) {
            const cs = getComputedStyle(e);
            const внутри = e.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
            const п = e.placeholder;
            if (!п) continue;
            const к = document.createElement('canvas').getContext('2d');
            к.font = `${cs.fontStyle} ${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`;
            const w = к.measureText(п).width;
            if (w > внутри) беды.push({поле: e.id, текст: п,
                                       нужно: Math.round(w), есть: Math.round(внутри)});
          }
          return беды;
        }""")
        шаг("подсказки полей помещаются", not обрез,
            "обрезаны: " + str(обрез) if обрез else "все помещаются")

        if кадры:
            стр.screenshot(path=os.path.join(кадры, f"форма-создания-{ширина}.png"))

        # ── 3. СОЗДАНИЕ СЕТА ФАЙЛОМ, насквозь ───────────────────────
        стр.fill("#f-id", ФАЙЛОМ)
        стр.fill("#f-ru", "Проба файлом")
        стр.fill("#f-en", "Probe File")
        стр.select_option("#f-cat", label="Охотница")
        стр.fill("#f-lvl", "17")
        стр.set_input_files("#f-file", {"name": "proba.jpg", "mimeType": "image/jpeg",
                                        "buffer": _картинка(1800, 1000, (40, 90, 60))})
        стр.wait_for_timeout(400)
        видно_превью = стр.evaluate(
            "() => { const e = document.getElementById('f-prev');"
            " return !!(e && e.tagName === 'IMG' && e.src); }")
        шаг("выбранный файл показан ДО сохранения", видно_превью,
            "превью подставлено" if видно_превью else "превью не изменилось")
        стр.click("#ens-body .btn-primary")
        стр.wait_for_timeout(2500)
        сказано = стр.inner_text("#ens-msg").strip()
        в_базе = _из_базы("SELECT id, name_ru, crafter, lvl, img_ext FROM enshrouded_sets"
                          " WHERE id = ?", ФАЙЛОМ)
        в_таблице = стр.evaluate("""(id) => {
          const tr = document.querySelector(`#ens-rows tr[data-id="${id}"]`);
          if (!tr) return null;
          const td = [...tr.querySelectorAll('td')].map(e => e.textContent.trim());
          const img = tr.querySelector('.ens-a-thumb');
          return {ячейки: td.slice(1, 6), картинка: img ? img.src.split('/').pop() : null};
        }""", ФАЙЛОМ)
        шаг("сет создан ФАЙЛОМ и картинка легла",
            bool(в_базе) and в_базе[0][4] and в_таблице and в_таблице["картинка"],
            f"база {в_базе} | таблица {в_таблице} | экран сказал: {сказано[:90]}")

        # ── 4. СОЗДАНИЕ СЕТА ССЫЛКОЙ ────────────────────────────────
        стр.evaluate("window.закрыть_модалку('ens-edit')")
        стр.wait_for_timeout(300)
        стр.click(".ens-a-add")
        стр.wait_for_selector("#f-id", timeout=8000)
        стр.fill("#f-id", ССЫЛКОЙ)
        стр.fill("#f-ru", "Проба ссылкой")
        стр.fill("#f-en", "Probe Url")
        стр.select_option("#f-cat", label="Алхимик")
        стр.fill("#f-url", f"{БАЗА}/enshrouded-img/bs_fur.png")
        стр.click("#ens-body .btn-primary")
        стр.wait_for_timeout(3000)
        сказано2 = стр.inner_text("#ens-msg").strip()
        в_базе2 = _из_базы("SELECT id, img_ext, img_ver FROM enshrouded_sets WHERE id = ?",
                           ССЫЛКОЙ)
        шаг("сет создан ССЫЛКОЙ и картинка легла",
            bool(в_базе2) and в_базе2[0][1] and в_базе2[0][2],
            f"база {в_базе2} | экран сказал: {сказано2[:90]}")

        # ── 5. ПРАВКА СУЩЕСТВУЮЩЕГО ─────────────────────────────────
        стр.evaluate("window.закрыть_модалку('ens-edit')")
        стр.wait_for_timeout(300)
        стр.evaluate(f"открыть('{ФАЙЛОМ}')")
        стр.wait_for_selector("#f-ru", timeout=8000)
        заблокирован = стр.evaluate("() => document.getElementById('f-id').disabled")
        стр.fill("#f-ru", "Проба правленая")
        стр.fill("#f-lvl", "42")
        стр.click("#ens-body .btn-primary")
        стр.wait_for_timeout(1500)
        после = _из_базы("SELECT name_ru, lvl FROM enshrouded_sets WHERE id = ?", ФАЙЛОМ)
        имя_в_таблице = стр.evaluate("""(id) => {
          const tr = document.querySelector(`#ens-rows tr[data-id="${id}"]`);
          return tr ? tr.querySelectorAll('td')[2].textContent.trim() : null;
        }""", ФАЙЛОМ)
        шаг("правка доехала до базы И до таблицы",
            after_ok := (bool(после) and после[0][0] == "Проба правленая"
                         and после[0][1] == 42 and "правленая" in (имя_в_таблице or "")),
            f"база {после} | в таблице «{имя_в_таблице}» | id заблокирован: {заблокирован}")

        # ── 6. ЗАМЕНА КАРТИНКИ у существующего ──────────────────────
        было_ver = _из_базы("SELECT img_ver FROM enshrouded_sets WHERE id = ?", ФАЙЛОМ)[0][0]
        стр.set_input_files("#f-file", {"name": "vtoraya.jpg", "mimeType": "image/jpeg",
                                        "buffer": _картинка(900, 620, (150, 40, 40))})
        стр.click("#f-up")
        стр.wait_for_timeout(2500)
        стало_ver = _из_базы("SELECT img_ver FROM enshrouded_sets WHERE id = ?", ФАЙЛОМ)[0][0]
        шаг("картинка заменена, версия адреса сменилась",
            было_ver != стало_ver,
            f"было v={было_ver}, стало v={стало_ver} | {стр.inner_text('#ens-msg').strip()[:70]}")

        if кадры:
            стр.screenshot(path=os.path.join(кадры, f"форма-правки-{ширина}.png"))

        # ── 7. УДАЛЕНИЕ: вопрос, ОТМЕНА, подтверждение ──────────────
        # Отметка, чтобы число в вопросе было не нулём.
        стр.evaluate("""(id) => fetch('/api/enshrouded/slot', {method:'POST',
            headers:{'Content-Type':'application/json'},
            body: JSON.stringify({set_id:id, slot_id:'head', owned:true,
                                  rarity:'epic', level:9, duplicates:0})})""", ФАЙЛОМ)
        стр.wait_for_timeout(900)
        отметок_до = _из_базы("SELECT COUNT(*) FROM enshrouded_slots WHERE set_id = ?",
                              ФАЙЛОМ)[0][0]
        стр.click("#ens-body .btn-danger")
        стр.wait_for_timeout(1200)
        вопрос = стр.inner_text("#ens-del-text").strip()
        видно_окно = стр.evaluate(
            "() => !document.getElementById('ens-del').hasAttribute('inert')")
        шаг("удаление СПРАШИВАЕТ и называет число",
            видно_окно and str(отметок_до) in вопрос,
            f"отметок в базе {отметок_до} | вопрос: «{вопрос}»"
            + ("" if видно_окно else " | ОКНО ВОПРОСА НЕ ОТКРЫЛОСЬ, экран сказал: "
                                    + стр.inner_text("#ens-msg").strip()[:80]))

        # НЕ СПРОСИЛИ — дальше идти НЕЛЬЗЯ, и молчать об этом тоже.
        # Прежняя версия шла дальше и висела 30 секунд на клике по кнопке
        # в неоткрытом окне: находка была, но приезжала стектрейсом
        # вместо строки. Проба, которая падает вместо ответа, отвечает
        # хуже той, которая называет.
        if not видно_окно:
            шаг("отказ НИЧЕГО не тронул", False, "пропущено: вопроса не было")
            шаг("подтверждение убрало сет, отметки и не оставило сирот", False,
                "пропущено: вопроса не было")
            шаг("поиск отбирает, пустое говорит и сбрасывается", False, "пропущено")
            шаг("отбор по категории совпал с базой", False, "пропущено")
            бр.close()
            return _печать(шаги, ошибки_страницы, ширина, сенсор)

        # отказ
        стр.click("#ens-del [data-modal-close]")
        стр.wait_for_timeout(700)
        жив = _из_базы("SELECT COUNT(*) FROM enshrouded_sets WHERE id = ?", ФАЙЛОМ)[0][0]
        отметок_после_отказа = _из_базы(
            "SELECT COUNT(*) FROM enshrouded_slots WHERE set_id = ?", ФАЙЛОМ)[0][0]
        шаг("отказ НИЧЕГО не тронул",
            жив == 1 and отметок_после_отказа == отметок_до,
            f"сетов {жив}, отметок {отметок_после_отказа} (было {отметок_до})")

        # подтверждение
        стр.click("#ens-body .btn-danger")
        стр.wait_for_timeout(900)
        стр.click("#ens-del-go")
        стр.wait_for_timeout(1500)
        нет_сета = _из_базы("SELECT COUNT(*) FROM enshrouded_sets WHERE id = ?", ФАЙЛОМ)[0][0]
        нет_отметок = _из_базы("SELECT COUNT(*) FROM enshrouded_slots WHERE set_id = ?",
                               ФАЙЛОМ)[0][0]
        сирот = _из_базы(
            "SELECT COUNT(*) FROM enshrouded_slots WHERE set_id NOT IN"
            " (SELECT id FROM enshrouded_sets)")[0][0]
        в_таблице_ли = стр.evaluate(
            "(id) => !!document.querySelector(`#ens-rows tr[data-id=\"${id}\"]`)", ФАЙЛОМ)
        шаг("подтверждение убрало сет, отметки и не оставило сирот",
            нет_сета == 0 and нет_отметок == 0 and сирот == 0 and not в_таблице_ли,
            f"сетов {нет_сета}, отметок {нет_отметок}, СИРОТ ВСЕГО {сирот},"
            f" в таблице {в_таблице_ли}")

        # ── 8. ПОИСК ────────────────────────────────────────────────
        всего = стр.evaluate("() => СЕТЫ.length")
        стр.fill("#ens-q", "меховой")
        стр.wait_for_timeout(400)
        нашлось = стр.locator("#ens-rows tr").count()
        видно_счёт = стр.inner_text("#ens-count").strip()
        стр.fill("#ens-q", "заведомо-нет-такого")
        стр.wait_for_timeout(400)
        пусто = стр.locator("#ens-rows tr").count()
        пусто_видно = стр.evaluate(
            "() => !document.getElementById('ens-empty').hidden")
        стр.fill("#ens-q", "")
        стр.wait_for_timeout(300)
        вернулось = стр.locator("#ens-rows tr").count()
        шаг("поиск отбирает, пустое говорит и сбрасывается",
            0 < нашлось < всего and пусто == 0 and пусто_видно and вернулось == всего,
            f"«меховой» → {нашлось} (счётчик {видно_счёт}), небыль → {пусто}"
            f" и плашка {пусто_видно}, сброс → {вернулось} из {всего}")

        # ── 9. ОТБОР ПО КАТЕГОРИИ ───────────────────────────────────
        стр.select_option("#ens-cat", label="Охотница")
        стр.wait_for_timeout(400)
        охотница = стр.locator("#ens-rows tr").count()
        в_базе_охотниц = _из_базы(
            "SELECT COUNT(*) FROM enshrouded_sets WHERE crafter = 'huntress'")[0][0]
        стр.select_option("#ens-cat", value="")
        стр.wait_for_timeout(300)
        снова = стр.locator("#ens-rows tr").count()
        шаг("отбор по категории совпал с базой",
            охотница == в_базе_охотниц and снова == всего,
            f"«Охотница» → {охотница}, в базе huntress {в_базе_охотниц}, сброс → {снова}")

        if not следы:
            стр.evaluate("""(id) => fetch(`/admin/api/enshrouded/set/${id}?confirm=1`,
                             {method:'DELETE'})""", ССЫЛКОЙ)
            стр.wait_for_timeout(900)
        бр.close()

    return _печать(шаги, ошибки_страницы, ширина, сенсор)


def _печать(шаги, ошибки_страницы, ширина, сенсор):
    print("=" * 100)
    print(f"ПРОХОД ЭКРАНА /admin/enshrouded НАСКВОЗЬ — ширина {ширина}"
          f"{', сенсор' if сенсор else ''}")
    print("=" * 100)
    плохих = 0
    for имя, вышло, факт in шаги:
        знак = "OK  " if вышло else "МИМО"
        плохих += not вышло
        print(f"  [{знак}] {имя}")
        print(f"         {факт}")
    print(f"\n  ошибок страницы: {len(ошибки_страницы)}"
          + (f" — {ошибки_страницы[:3]}" if ошибки_страницы else ""))
    print(f"  действий не дошло до результата: {плохих} из {len(шаги)}")
    return 1 if (плохих or ошибки_страницы) else 0


if __name__ == "__main__":
    арг = sys.argv[1:]
    кадры = None
    if "--кадры" in арг:
        кадры = арг[арг.index("--кадры") + 1]
        os.makedirs(кадры, exist_ok=True)
    ш = 390 if "--узко" in арг else 1440
    sys.exit(прогон(следы="--следы" in арг, ширина=ш,
                    сенсор="--узко" in арг, кадры=кадры))
