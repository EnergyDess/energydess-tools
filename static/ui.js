// ── ui.js — общие микро-механики дизайн-системы ─────────────────────────────
// 1. running-border: вычисляет периметр каждой .btn-signature и пишет его
//    в CSS-переменную --perimeter (design-system.md, раздел 3 — не хардкодим).
// 2. scroll-reveal: элементы .reveal получают .revealed при входе в viewport.
// 3. дорисовка иконок Lucide в разметке, собранной скриптом.

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
  // выбор приёма пищи и результат действия ассистента. Понадобится —
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

  // ── Running-border у .btn-signature ──
  function initSignatureBorders() {
    document.querySelectorAll('.btn-signature').forEach(function (btn) {
      var rect = btn.querySelector('.signature-border rect');
      if (!rect) return;
      // размеры атрибутами — проценты в getTotalLength() не считаются
      var w = btn.offsetWidth, h = btn.offsetHeight;
      if (!w || !h) return;
      rect.setAttribute('width', w - 1);
      rect.setAttribute('height', h - 1);
      var perimeter = Math.ceil(rect.getTotalLength());
      btn.style.setProperty('--perimeter', perimeter);
    });
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

  function init() {
    initSignatureBorders();
    initScrollReveal();
    initAvatarDropdown();
    initLucideAutoDraw();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
  // при ресайзе периметр меняется — пересчитываем
  window.addEventListener('resize', initSignatureBorders);
})();
