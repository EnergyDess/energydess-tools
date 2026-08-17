# -*- coding: utf-8 -*-
"""Контрольные числа проекта — ПЕЧАТАЮТСЯ, а не лежат в тексте руками.

ЗАЧЕМ. Числа, вписанные в CLAUDE.md глазами, протухли дважды подряд:
про правила `:hover` там стояло сначала 112, потом 131, а замер не дал
ни того ни другого. Ложная опора хуже отсутствующей — по ней сверяются
и делают вывод «ничего не изменилось» там, где изменилось всё.

Вторая половина той же болезни — СПОСОБ СЧЁТА. У `:hover` три разных
ответа на один вопрос: 123 медиаблока, 129 правил, 134 вхождения. Число
без указания способа не значит ничего, поэтому здесь у каждой метрики
способ назван строкой рядом и записан в самой команде.

    py check_metrics.py          — все метрики
    py check_metrics.py --ряд    — только ряд девяти проверок §6.0.2

Код возврата: 0 всегда. Это СРЕЗ, а не проверка: у него нет понятия
«правильно». Проверки, у которых оно есть, — check_docs, check_ids,
check_backlog, check_endpoints, и их код читается отдельно.
"""
import io
import re
import glob
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8')

СТРАНИЧНЫЕ_CSS = [
    'static/hh.css', 'static/profile.css', 'static/landing.css',
    'static/workout.css', 'static/workout_profile.css',
    'static/nutrition.css', 'static/botamin.css',
]


def _шаблоны_и_страничный_css():
    файлы = sorted(glob.glob('templates/*.html'))
    файлы += [п for п in СТРАНИЧНЫЕ_CSS if glob.glob(п)]
    return файлы


def _прочитать(путь):
    try:
        return io.open(путь, encoding='utf-8').read()
    except OSError:
        return ''


# ── Ряд девяти проверок §6.0.2 ──────────────────────────────────────────────
# Первые шесть — грепы, и здесь они вызываются ТЕМИ ЖЕ командами, что
# записаны в CLAUDE.md. Вторая реализация на Python разошлась бы с первой,
# а это ровно та болезнь, которую весь §6.0.2 и лечит.

КОМАНДЫ_РЯДА = r'''
pages="templates/ static/hh.css static/profile.css static/landing.css static/workout.css static/workout_profile.css static/nutrition.css static/botamin.css"
names='card|btn-primary|btn-secondary|btn-ghost|btn-icon|btn-icon-solid|btn-icon-round|btn-icon-accent|btn-lg|btn-glow|btn-block|input|input-compact|input-nested|input-sm|textarea|textarea-nested|textarea-compact|textarea-grow|select|badge|alert|alert-accent|avatar|chip|chip-wrap|eyebrow|toggle|modal|container|tool-card|page-column|page-fill|tab-bar|tab-btn|segmented|segmented-btn|spinner|breadcrumb|field-label|undo-bar|meter|meter-fill|meter-edge|btn-icon-outline|site-header|site-header-edges|site-footer|site-footer-thin|site-footer-grid|site-footer-grid-guest|site-footer-bottom'
echo "1|$(grep -rnE "\.($names)(:[a-z-]+(\([^)]*\))?|\.[a-zA-Z0-9_-]+|\[[^]]*\])*\s*[,{]" $pages | grep '{' | wc -l)"
tokens=$(grep -oE '^\s*--[a-z0-9-]+\s*:' static/style.css | tr -d ' \t:' | sort -u | paste -sd'|')
echo "2|$(grep -rnE "(^|[;{\"'])\s*($tokens)\s*:" $pages | wc -l)"
echo "2b|$(grep -rnE "setProperty\(\s*['\"]($tokens)['\"]" templates/ static/*.js | wc -l)"
echo "3a|$(grep -rnoE "style='[^']*'" templates/ static/*.js | wc -l)"
echo "3b|$(grep -rnoE 'style="[^"]*"' templates/ static/*.js | grep -vE 'style="\s*(--[a-z0-9_-]+\s*:[^;"]*;?\s*)+"' | grep -vE 'style="\s*display\s*:\s*(none|block|flex|grid|inline-flex)\s*;?\s*"' | grep -vE 'style="\s*[a-z-]+\s*:\s*\{\{[^"]*\}\}[a-z%]*\s*;?\s*"' | grep -vE 'style="\s*[a-z-]+\s*:\s*\$\{[^"]*\}[a-z%]*\s*;?\s*"' | wc -l)"
echo "4|$(grep -LE "_header\.html|_admin_nav\.html" templates/*.html | grep -v '/_' | wc -l)"
echo "4b|$(grep -nE 'class="(nav|site-header)"' templates/*.html | grep -v '/_' | wc -l)"
echo "5|$(grep -L "_page_end\.html" templates/*.html | grep -v '/_' | wc -l)"
echo "6|$(grep -Pni '<[a-z][^>]*\s([a-z][a-z0-9-]*)=("[^"]*"|\x27[^\x27]*\x27)[^>]*\s\1=' templates/*.html | wc -l)"
echo "6b|$(grep -Pzoi '<[a-z][^>]*\s([a-z][a-z0-9-]*)=("[^"]*"|\x27[^\x27]*\x27)[^>]*\s\1=' templates/*.html | tr '\0' '\n' | wc -l)"
'''


def ряд_проверок():
    """Первые шесть — теми же грепами, что в CLAUDE.md. Скрипты — по коду."""
    из_грепов = {}
    try:
        вывод = subprocess.run(['bash', '-c', КОМАНДЫ_РЯДА],
                               capture_output=True, text=True, timeout=180)
        for строка in вывод.stdout.splitlines():
            if '|' in строка:
                имя, число = строка.split('|', 1)
                из_грепов[имя.strip()] = число.strip()
    except (OSError, subprocess.SubprocessError) as e:
        print(f'  !! грепы не отработали: {e}')

    коды = {}
    for имя, скрипт in [('7', 'check_docs.py'), ('8', 'check_ids.py'),
                        ('9', 'check_backlog.py')]:
        try:
            коды[имя] = subprocess.run([sys.executable, скрипт],
                                       capture_output=True, timeout=180).returncode
        except (OSError, subprocess.SubprocessError) as e:
            коды[имя] = f'не запустился: {e}'
    return из_грепов, коды


# ── Прочие метрики ──────────────────────────────────────────────────────────

def hover_метрика():
    """ТРИ ЧИСЛА, а не одно, и это не избыточность.

    Опорным считается СРЕДНЕЕ — «правил»: селекторов с `:hover` внутри
    медиазоны. Блоки считают обёртки (в одной может лежать несколько
    правил), вхождения считают `:hover` в списках селекторов через запятую.
    Три ответа на один вопрос — ровно та причина, по которой число в тексте
    без указания способа ничего не значило.
    """
    файлы = sorted(glob.glob('static/*.css')) + sorted(glob.glob('templates/*.html'))
    блоков = правил = вхождений = 0
    по_файлам = {}
    for путь in файлы:
        текст = _прочитать(путь)
        б = пр = вх = 0
        for m in re.finditer(r'@media\s*\(\s*hover\s*:\s*hover\s*\)\s*\{', текст):
            б += 1
            i, глубина = m.end(), 1
            while i < len(текст) and глубина:
                if текст[i] == '{':
                    глубина += 1
                elif текст[i] == '}':
                    глубина -= 1
                i += 1
            for sm in re.finditer(r'([^{}]+)\{', текст[m.end():i - 1]):
                if ':hover' in sm.group(1):
                    пр += 1
                    вх += sm.group(1).count(':hover')
        if б:
            по_файлам[путь] = (б, пр, вх)
            блоков += б
            правил += пр
            вхождений += вх
    return блоков, правил, вхождений, по_файлам


def долг_дневника():
    """Задача 96. Способ — ГРЕП, потому что грепом его и проверяют.

    Разбор CSS даёт число на единицу меньше (комментарии), и однажды это
    уже стоило расхождения: в таблице задачи стояло число разбора,
    а в мерке готовности под ней — команда грепа.
    """
    текст = _прочитать('static/nutrition.css')
    отступы = len(re.findall(
        r'(^|[;{ ])(margin|padding|gap|row-gap|column-gap)'
        r'(-(top|bottom|left|right))?:\s*[0-9.]', текст, re.M))
    кегли = len(re.findall(r'font-size:\s*[0-9.]', текст))
    return отступы, кегли


def тесты():
    """Сколько тестов проходит. Способ — ПРОГОН pytest, а не подсчёт
    функций `def test_` грепом.

    Разница не косметическая: параметризованный тест — одна функция
    и десять прогонов, и два способа дают два разных числа. Опорным
    считается то, что печатает сам pytest, потому что именно оно
    называется в отчётах.
    """
    try:
        r = subprocess.run([sys.executable, '-m', 'pytest', 'tests/', '-q',
                            '--no-header', '-p', 'no:warnings'],
                           capture_output=True, text=True, encoding='utf-8',
                           errors='replace', timeout=900)
        m = re.search(r'(\d+) passed', r.stdout or '')
        f = re.search(r'(\d+) failed', r.stdout or '')
        return (m.group(1) if m else '?'), (f.group(1) if f else '0'), r.returncode
    except (OSError, subprocess.SubprocessError) as e:
        return f'не запустился: {e}', '?', '?'


def эндпоинты():
    """Опись — из check_endpoints, чтобы число было одно на весь проект."""
    try:
        import check_endpoints
        строки = check_endpoints.собрать()
        служебных = sum(1 for с in строки
                        if с['служебный'] or с['метод'] == '(mount)')
        под_гейтом = sum(1 for с in строки if с.get('под_гейтом'))
        return len(строки), служебных, check_endpoints.грепом(), под_гейтом
    except Exception as e:
        return None, None, None, f'не собралось: {e}'


def главное():
    только_ряд = '--ряд' in sys.argv or '--row' in sys.argv

    print('═' * 74)
    print('КОНТРОЛЬНЫЕ ЧИСЛА ПРОЕКТА — срез на сейчас')
    print('═' * 74)

    print('\n■ РЯД ДЕВЯТИ ПРОВЕРОК (CLAUDE.md §6.0.2)')
    print('  способ: проверки 1-6 — те же грепы, что записаны в §6.0.2;')
    print('          проверки 7-9 — КОД ВОЗВРАТА скриптов, не число строк')
    гр, коды = ряд_проверок()
    ряд = [гр.get(и, '?') for и in ('1', '2', '3b', '4', '5', '6')]
    ряд += [str(коды.get(и, '?')) for и in ('7', '8', '9')]
    print(f'\n  РЯД: {" / ".join(ряд)}')
    print(f'  подпроходы: 2b={гр.get("2b", "?")}  3a={гр.get("3a", "?")}  '
          f'4b={гр.get("4b", "?")}  6b={гр.get("6b", "?")}')
    print('\n  ВНИМАНИЕ: первое и пятое числа — НЕ РАВНЫ ДОЛГУ. В выводе')
    print('  обоих есть законные строки; читать по таблицам в §6.0.2.')

    print('\n■ PYTEST')
    print('  способ: прогон py -m pytest tests/ -q; ОПОРНОЕ — число, которое')
    print('          печатает сам pytest (греп по `def test_` даст меньше:')
    print('          параметризованный тест — одна функция и много прогонов)')
    прошло, упало, код = тесты()
    print(f'\n  прошло: {прошло}   упало: {упало}   код возврата: {код}')

    if только_ряд:
        return 0

    print('\n■ ПРАВИЛА :hover В @media (hover: hover)')
    print('  способ: разбор CSS и <style> в шаблонах; ОПОРНОЕ — «правил»')
    б, пр, вх, по_файлам = hover_метрика()
    print(f'\n  блоков @media : {б}')
    print(f'  ПРАВИЛ        : {пр}   ← опорное')
    print(f'  вхождений     : {вх}')
    print(f'  в nutrition.css: правил {по_файлам.get("static\\nutrition.css", по_файлам.get("static/nutrition.css", (0, 0, 0)))[1]}')

    print('\n■ ДОЛГ ДНЕВНИКА МИМО КОМПОНЕНТНОЙ БАЗЫ (BACKLOG №96)')
    print('  способ: греп по static/nutrition.css — тот же, что в мерке задачи')
    о, к = долг_дневника()
    print(f'\n  отступы числом: {о}')
    print(f'  кегли числом  : {к}')

    print('\n■ ЭНДПОИНТЫ (check_endpoints.py)')
    print('  способ: обход app.routes; греп по декораторам — второе число')
    всего, служ, греп, гейт = эндпоинты()
    print(f'\n  всего строк описи : {всего}  (служебных и статики: {служ})')
    print(f'  греп по @app.<метод>: {греп}')
    print(f'  закрыто гейтом is_verified: {гейт}')

    print('\n' + '═' * 74)
    print('Числа выше в текст руками НЕ ПЕРЕПИСЫВАТЬ. В документации стоит')
    print('ссылка на эту команду — она и есть источник (CLAUDE.md §6.0.4).')
    return 0


if __name__ == '__main__':
    sys.exit(главное())
