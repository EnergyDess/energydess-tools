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

  function init() {
    initScrollReveal();
    initAvatarDropdown();
    initHints();
    initLucideAutoDraw();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
