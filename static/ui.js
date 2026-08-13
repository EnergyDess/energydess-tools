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

  function init() {
    initScrollReveal();
    initAvatarDropdown();
    initLucideAutoDraw();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
