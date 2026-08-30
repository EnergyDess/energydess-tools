// ── ui.js — общие микро-механики дизайн-системы ─────────────────────────────
// 1. scroll-reveal: элементы .reveal получают .revealed при входе в viewport.
// 2. дорисовка иконок Lucide в разметке, собранной скриптом.
//
// Здесь был третий пункт — running-border: расчёт периметра .btn-signature
// через getTotalLength(). Ушёл вместе с самой рамкой 2026-08-11 (BACKLOG №54).

(function () {
  'use strict';

  // ── Иконки Lucide в динамической разметке ────────────────────────────────
  //
  // lucide.createIcons() вызывается страницей ОДИН раз, последней строкой.
  // Всё, что скрипт вставит позже, этим вызовом не покрыто: <i data-lucide>
  // останется пустым тегом. Отказ немой — ни ошибки, ни следа в консоли,
  // просто пустое место там, где ждали значок.
  //
  // Раньше это никого не задевало: динамическая разметка была на эмодзи,
  // а эмодзи — символ шрифта, ему дорисовка не нужна. Как только эмодзи
  // уехали на Lucide (BACKLOG.md, задача 31), точек вставки стало
  // 48 в одном только workout.html — и каждая из них место, где следующий
  // забудет позвать createIcons.
  //
  // Поэтому не 48 вызовов, а один наблюдатель: он ждёт появления
  // недорисованного значка и дорисовывает.
  //
  // СЕЛЕКТОР ИМЕННО `i[data-lucide]`, И ЭТО НЕ ПРИДИРКА. Первая версия
  // искала `[data-lucide]` без имени тега — и получилась вечная петля:
  // createIcons копирует атрибуты исходного элемента на созданный <svg>,
  // то есть data-lucide после дорисовки НИКУДА НЕ ДЕВАЕТСЯ. Условие
  // «искать нечего» не наступало никогда, каждая дорисовка меняла дерево,
  // мутация будила наблюдателя — и так кадр за кадром.
  //
  // Отказ был бы тихий: страница рисуется правильно, ошибок нет, просто
  // вентилятор. Поймал замер: 21 нарисованный значок и ровно 21 «ещё
  // не нарисованный» — числа совпали, потому что это одни и те же элементы.
  // Тег в селекторе различает их однозначно: до дорисовки <i>, после <svg>.
  //
  // ЧТО ЭТО СТОИТ, замерено 2026-08-08 на ленте чата дневника.
  // Обычное сообщение без значка: сторож ниже — 2 мкс, и он НЕ растёт
  // с длиной ленты (0 → 600 сообщений: 1.8–2.3 мкс). createIcons при этом
  // не зовётся вовсе, разницы во времени отправки нет.
  //
  // Сообщение СО значком: 1.5 мс на отправку при 120 значках в ленте,
  // 2.75 мс при 320, 6.8 мс при 826 — линейно. Причина в том же, из-за чего
  // была петля: data-lucide остаётся на нарисованном svg, отличить готовые
  // от новых createIcons не может и перерисовывает всю страницу.
  // Работа идёт в rAF после перерисовки ленты, ввод не блокирует.
  //
  // Порог, за которым это станет заметно, — около 2000 значков в одной
  // ленте (кадр 16 мс). Сегодня столько не набирается: значок несут только
  // карточки блюд от ассистента и кнопки удаления в сравнении фото
  // (выбор приёма пищи, стоявший здесь раньше, удалён вместе
  // с .meal-picker-btns 2026-08-13). Понадобится —
  // дорисовывать не через createIcons, а поштучно по собранным узлам:
  // стоимость станет от числа НОВЫХ значков, а не от числа всех.
  function initLucideAutoDraw() {
    if (!('MutationObserver' in window)) return;
    var ждём = false;
    var наблюдатель = new MutationObserver(function () {
      if (ждём) return;
      // Один проход на кадр: рендер списка даёт десятки мутаций подряд,
      // и звать createIcons на каждую значит перебирать дерево заново.
      ждём = true;
      requestAnimationFrame(function () {
        ждём = false;
        if (!window.lucide) return;
        if (!document.querySelector('i[data-lucide]')) return;
        window.lucide.createIcons();
      });
    });
    наблюдатель.observe(document.body, { childList: true, subtree: true });
  }

  // ── Появление секций при скролле ──
  function initScrollReveal() {
    var els = document.querySelectorAll('.reveal');
    if (!els.length || !('IntersectionObserver' in window)) {
      els.forEach(function (el) { el.classList.add('revealed'); });
      return;
    }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add('revealed');
          io.unobserve(entry.target);
        }
      });
    }, { threshold: 0.12 });
    els.forEach(function (el) { io.observe(el); });
  }

  // ── Дропдаун аватара в шапке ──
  function initAvatarDropdown() {
    var wrap = document.getElementById('avatar-wrap');
    if (!wrap) return;
    var btn = wrap.querySelector('.avatar-btn');
    btn.addEventListener('click', function (e) {
      e.stopPropagation();
      var open = wrap.classList.toggle('open');
      btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
    document.addEventListener('click', function () {
      wrap.classList.remove('open');
      btn.setAttribute('aria-expanded', 'false');
    });
  }

  // ── Показать/скрыть пароль ──────────────────────────────────────────────
  //
  // Вид кнопки — .btn-icon .eye-btn в style.css, а поведение до 2026-08-13
  // лежало ТРЕМЯ одинаковыми копиями в login.html, register.html
  // и reset_password.html. Копии — не стилистика: дневнику питания глазок
  // понадобился четвёртым, и без общей функции появилась бы четвёртая.
  //
  // Глобал, а не делегат на document: вызов идёт из onclick в разметке,
  // как у остальных кнопок этих страниц. Переписывать разметку четырёх
  // шаблонов ради формы подписки — работа не этого захода.
  var ГЛАЗ_ОТКРЫТ = '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>';
  var ГЛАЗ_ЗАКРЫТ = '<path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/>';

  window.toggleEye = function (inputId, btn) {
    var input = document.getElementById(inputId);
    var svg = btn.querySelector('svg');
    if (!input || !svg) return;
    var показать = input.type === 'password';
    input.type = показать ? 'text' : 'password';
    svg.innerHTML = показать ? ГЛАЗ_ЗАКРЫТ : ГЛАЗ_ОТКРЫТ;
    // Кнопка сообщает СВОЁ действие, а не текущее состояние поля:
    // иначе программа чтения объявляет «скрыть пароль» ровно тогда,
    // когда пароль скрыт
    btn.setAttribute('aria-label', показать ? 'Скрыть пароль' : 'Показать пароль');
  };

  // ── Подсказка `.hint`: наведение И нажатие ──────────────────────────────
  //
  // ДВА СПОСОБА ОТКРЫТЬ, И ВТОРОЙ ОБЯЗАТЕЛЕН. Наведения на сенсорном
  // экране не существует: `:hover` там залипает на последнем тронутом
  // элементе и не уходит сам (CLAUDE.md §6.0.3). Подсказка,
  // открывающаяся только по наведению, на телефоне либо не открывается,
  // либо не закрывается — оба исхода немые.
  //
  // ОБА СПОСОБА ЖИВУТ ЗДЕСЬ, А НЕ ПОЛОВИНА В CSS. Причина — замер
  // 2026-08-19: подсказка высотой 380px, поставленная `absolute`,
  // обрезалась ПЯТЬЮ предками сразу (`.d-left` с `overflow-y: auto`
  // и четыре блока раскладки дневника), и невидимым оказывался
  // последний абзац. Лечится `position: fixed` с посчитанными
  // координатами — а посчитать их может только скрипт. Оставь мы
  // наведение в CSS, оно показывало бы неразмещённую, то есть
  // обрезанную подсказку.
  //
  // Сенсорную ширину это не задевает: `matchMedia('(hover: hover)')` —
  // тот же признак, что и `@media (hover: hover)`, и на сенсоре
  // наведение не подписывается вовсе.
  var ОТСТУП = 8;

  function естьНаведение() {
    return window.matchMedia && window.matchMedia('(hover: hover)').matches;
  }

  // Координаты считаются от кнопки, а не от края экрана, и упираются
  // в границы окна с обеих сторон: подсказка у правого края уезжала бы
  // за него, у нижнего — под него
  function разместить(hint) {
    var поп = hint.querySelector('.hint-pop');
    if (!поп) return;
    var к = hint.getBoundingClientRect();
    поп.style.position = 'fixed';
    поп.style.left = '0px';
    поп.style.top = '0px';
    var ш = поп.offsetWidth, в = поп.offsetHeight;
    var x = Math.min(к.left, window.innerWidth - ш - ОТСТУП);
    поп.style.left = Math.max(ОТСТУП, x) + 'px';
    var y = к.bottom + ОТСТУП;
    // Снизу не помещается — ставим НАД кнопкой. Не помещается и там
    // (подсказка выше окна) — прижимаем к верхнему краю: обрезанный
    // низ лучше обрезанного верха, потому что читают сверху вниз
    if (y + в > window.innerHeight - ОТСТУП) {
      y = к.top - в - ОТСТУП;
      if (y < ОТСТУП) y = ОТСТУП;
    }
    поп.style.top = y + 'px';
  }

  function открыть(hint, закрепить) {
    hint.classList.add('is-open');
    if (закрепить) hint.dataset.pin = '1';
    var b = hint.querySelector('.hint-btn');
    if (b) b.setAttribute('aria-expanded', 'true');
    разместить(hint);
  }

  function закрыть(hint) {
    hint.classList.remove('is-open');
    delete hint.dataset.pin;
    var b = hint.querySelector('.hint-btn');
    if (b) b.setAttribute('aria-expanded', 'false');
    // ЗАКРЫТИЕ ОТМЕНЯЕТ РОВНО ТО, ЧТО СДЕЛАЛО ОТКРЫТИЕ (BACKLOG №197,
    // D.3). `разместить` вешает инлайновые `position: fixed`, `left`
    // и `top`; без этой уборки они переживали закрытие и оставались
    // на элементе до конца жизни страницы.
    //
    // ЧТО ЭТО ЛОМАЛО НА САМОМ ДЕЛЕ — назовём честно: НИЧЕГО ВИДИМОГО,
    // потому что задача 196 закрыла подсказку `display: none`, и блок
    // вне раскладки в любом положении. Убирается не признак беды,
    // а РАСХОЖДЕНИЕ ОТКРЫТИЯ С ЗАКРЫТИЕМ: инлайновый `position` бьёт
    // любое правило файла, и следующий, кто задаст `.hint-pop`
    // положение в CSS, получил бы его на всех подсказках, кроме
    // однажды открытых. Отказ при этом немой — правило написано,
    // на экране ничего.
    // УБИРАЮТСЯ ОНИ ПОСЛЕ ПЕРЕХОДА, А НЕ СРАЗУ — BACKLOG №218.
    //
    // АБЗАЦ ВЫШЕ («ничего видимого») НЕВЕРЕН, и неверен ровно на длину
    // перехода: `display` у `.hint-pop` анимируется через
    // `allow-discrete`, то есть остаётся `block` все `--dur-base`, —
    // а `position` снимался ПЕРВЫМ КАДРОМ. На эти доли секунды
    // подсказка становилась абсолютным потомком шириной 24rem внутри
    // `.hint` шириной 23 px и входила в `scrollWidth` панели.
    //
    // Это и есть «горизонтальная прокрутка появляется на мгновение,
    // когда мышь отводится с подсказки» — жалоба владельца, четыре
    // раза объявленная невоспроизводимой. Замер
    // `py check_medkit_look.py --ход`: во время закрытия 346 px
    // на 1920 и 266 px на 390.
    //
    // СОБЫТИЕМ, А НЕ ТАЙМЕРОМ С ЧИСЛОМ: длительность живёт в CSS,
    // и вписанное сюда число разошлось бы с ней молча. Таймер стоит
    // ЗАПАСНЫМ — при `prefers-reduced-motion` перехода нет вовсе,
    // и `transitionend` не придёт никогда.
    var поп = hint.querySelector('.hint-pop');
    if (!поп) return;
    var убрать = function () {
      // Подсказку успели открыть заново — уборка отменяется: иначе она
      // сорвала бы размещение уже ОТКРЫТОЙ
      if (hint.classList.contains('is-open')) return;
      поп.style.position = ''; поп.style.left = ''; поп.style.top = '';
    };
    поп.addEventListener('transitionend', убрать, { once: true });
    var мс = parseFloat(getComputedStyle(поп).transitionDuration) * 1000;
    setTimeout(убрать, (мс || 0) + 60);
  }

  function закрытьВсе(кроме) {
    document.querySelectorAll('.hint.is-open').forEach(function (el) {
      if (el !== кроме) закрыть(el);
    });
  }

  function initHints() {
    // Делегаты на document, а не обработчики на каждой кнопке:
    // подсказки появляются в разметке, собранной скриптом, и навешивание
    // при инициализации до них не доехало бы. Тот же довод, что
    // у дорисовки иконок Lucide выше
    document.addEventListener('click', function (e) {
      var btn = e.target.closest ? e.target.closest('.hint-btn') : null;
      var hint = btn ? btn.closest('.hint') : null;
      закрытьВсе(hint);
      if (!hint) return;
      // Переключаем по ЗАКРЕПЛЕНИЮ, а не по видимости, и это не мелочь.
      // К моменту `click` подсказка уже открыта — её открыл `focusin`
      // (нажатие даёт фокус) или `mouseover` на десктопе. Проверяй мы
      // видимость, первое же нажатие ЗАКРЫВАЛО бы её: замер 2026-08-19
      // дал «после нажатия: hidden» на обеих ширинах, то есть кнопка
      // справки на телефоне не работала вовсе
      if (hint.dataset.pin) закрыть(hint);
      else открыть(hint, true);
    });
    // Наведение НЕ закрепляет: подсказка уходит вместе с курсором.
    // Открытую нажатием курсор не гасит — её закрывает второе нажатие
    document.addEventListener('mouseover', function (e) {
      if (!естьНаведение() || !e.target.closest) return;
      var hint = e.target.closest('.hint');
      if (hint && !hint.classList.contains('is-open')) открыть(hint, false);
    });
    document.addEventListener('mouseout', function (e) {
      if (!естьНаведение() || !e.target.closest) return;
      var hint = e.target.closest('.hint');
      if (!hint || hint.dataset.pin) return;
      // Уход ВНУТРЬ той же подсказки уходом не считается
      if (e.relatedTarget && hint.contains(e.relatedTarget)) return;
      закрыть(hint);
    });
    // Клавиатура: фокус открывает, уход фокуса закрывает
    document.addEventListener('focusin', function (e) {
      if (!e.target.closest) return;
      var hint = e.target.closest('.hint');
      if (hint) открыть(hint, false);
    });
    document.addEventListener('focusout', function (e) {
      if (!e.target.closest) return;
      var hint = e.target.closest('.hint');
      if (hint && !hint.dataset.pin) закрыть(hint);
    });
    // Escape закрывает — иначе на клавиатуре подсказку нечем убрать,
    // не уводя фокус
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') закрытьВсе(null);
    });
    // Прокрутка и смена размера окна уводят кнопку, а подсказка стоит
    // `fixed` — то есть осталась бы висеть на прежнем месте. Пересчёт,
    // а не закрытие: закрытие на скролле выглядит как сбой
    var пересчитать = function () {
      document.querySelectorAll('.hint.is-open').forEach(разместить);
    };
    window.addEventListener('scroll', пересчитать, true);
    window.addEventListener('resize', пересчитать);
  }

  /* КОРОТКАЯ ПОДСКАЗКА ПОЛЯ НА УЗКОМ ЭКРАНЕ — `data-narrow-hint`.
     Механика жила внутри одного шаблона (экран управления каталогом,
     BACKLOG №64/№137). С 2026-08-23 поле поиска приезжает из общего
     макроса шапки раздела админки, то есть потребителей стало четыре, —
     и четыре копии разошлись бы МОЛЧА: подсказка просто осталась бы
     длинной там, где её забыли скопировать (§6.0.7).

     Подменяется АТРИБУТ, а не текст в разметке: на широком окне подсказка
     обязана называть все способы поиска, и укоротить её насовсем значило
     бы спрятать от всех то, что не помещается у одного.

     Имя атрибута ЛАТИНИЦЕЙ: `dataset` убирает дефис только перед
     ASCII-буквой, у кириллического имени ключ не собирается вовсе,
     чтение даёт undefined, и правка выглядит несработавшей (§6.0). */
  function initNarrowHints() {
    var поля = document.querySelectorAll('[data-narrow-hint]');
    if (!поля.length) return;
    var узко = window.matchMedia('(max-width: 640px)');
    var выбрать = function () {
      поля.forEach(function (поле) {
        if (!поле.dataset.wideHint) поле.dataset.wideHint = поле.placeholder || '';
        поле.placeholder = узко.matches ? поле.dataset.narrowHint : поле.dataset.wideHint;
      });
    };
    выбрать();
    узко.addEventListener('change', выбрать);
  }

  function init() {
    initScrollReveal();
    initAvatarDropdown();
    initHints();
    initNarrowHints();
    initLucideAutoDraw();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
