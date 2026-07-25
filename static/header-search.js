// ── header-search.js — поиск-навигация по инструментам в общей шапке ────────
//
// Данные приходят из _header.html (JSON-скрипт #nav-search-data), источник —
// глобал TOOLS из main.py. Пункт «Админка» попадает в JSON только у админа,
// поэтому здесь никаких проверок прав нет и быть не должно.
//
// Клавиатура — паттерн WAI-ARIA combobox с ВИРТУАЛЬНЫМ фокусом: фокус физически
// остаётся в поле ввода (можно продолжать печатать), выделение пункта передаётся
// через aria-activedescendant. Жёсткая фокус-ловушка здесь была бы ошибкой —
// она не даёт уйти с поля клавиатурой.
//
// У гостя поля нет в DOM (см. _header.html) — скрипт молча выходит.

(function () {
  'use strict';

  var input = document.getElementById('nav-search-input');
  var dropdown = document.getElementById('nav-search-dropdown');
  var list = document.getElementById('nav-search-list');
  var emptyEl = document.getElementById('nav-search-empty');
  var dataEl = document.getElementById('nav-search-data');
  if (!input || !dropdown || !list || !dataEl) return;   // гость или другая разметка

  var ITEMS = [];
  try {
    ITEMS = JSON.parse(dataEl.textContent) || [];
  } catch (e) {
    return;   // битые данные — поле останется просто инпутом, ничего не ломаем
  }
  if (!ITEMS.length) return;

  var filtered = ITEMS.slice();
  var activeIndex = -1;
  var isOpen = false;

  // ── Рендер ──
  function render() {
    list.innerHTML = '';
    filtered.forEach(function (item, i) {
      var li = document.createElement('li');
      li.className = 'search-item' + (i === activeIndex ? ' active' : '');
      li.id = 'nav-search-item-' + i;
      li.setAttribute('role', 'option');
      li.setAttribute('aria-selected', i === activeIndex ? 'true' : 'false');
      li.dataset.url = item.url;
      li.dataset.index = i;

      var ico = document.createElement('i');
      ico.setAttribute('data-lucide', item.icon);
      ico.className = 'search-item-icon tool-' + item.id;

      var label = document.createElement('span');
      label.className = 'search-item-name';
      label.textContent = item.name;

      li.appendChild(ico);
      li.appendChild(label);
      list.appendChild(li);
    });

    var nothing = filtered.length === 0;
    emptyEl.hidden = !nothing;
    list.hidden = nothing;

    // Lucide заменяет <i data-lucide> на <svg> — вызываем после вставки в DOM
    if (window.lucide && typeof window.lucide.createIcons === 'function') {
      window.lucide.createIcons();
    }
    syncActiveDescendant();
  }

  function syncActiveDescendant() {
    if (activeIndex >= 0 && filtered[activeIndex]) {
      input.setAttribute('aria-activedescendant', 'nav-search-item-' + activeIndex);
    } else {
      input.removeAttribute('aria-activedescendant');
    }
  }

  function setActive(i) {
    var items = list.querySelectorAll('.search-item');
    if (activeIndex >= 0 && items[activeIndex]) {
      items[activeIndex].classList.remove('active');
      items[activeIndex].setAttribute('aria-selected', 'false');
    }
    activeIndex = i;
    if (activeIndex >= 0 && items[activeIndex]) {
      items[activeIndex].classList.add('active');
      items[activeIndex].setAttribute('aria-selected', 'true');
      // держим выделенный пункт в зоне видимости при длинном списке
      items[activeIndex].scrollIntoView({ block: 'nearest' });
    }
    syncActiveDescendant();
  }

  // ── Открытие / закрытие ──
  function open() {
    if (isOpen) return;
    isOpen = true;
    dropdown.hidden = false;
    input.setAttribute('aria-expanded', 'true');
  }

  function close() {
    if (!isOpen) return;
    isOpen = false;
    dropdown.hidden = true;
    input.setAttribute('aria-expanded', 'false');
    setActive(-1);
  }

  function applyFilter() {
    var q = input.value.trim().toLowerCase();
    filtered = q
      ? ITEMS.filter(function (it) { return it.name.toLowerCase().indexOf(q) !== -1; })
      : ITEMS.slice();
    activeIndex = filtered.length ? 0 : -1;   // первый пункт сразу под Enter
    render();
  }

  function go(i) {
    var item = filtered[i];
    if (item) window.location.href = item.url;
  }

  // ── События ──
  input.addEventListener('focus', function () { applyFilter(); open(); });
  input.addEventListener('input', function () { applyFilter(); open(); });

  input.addEventListener('keydown', function (e) {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      if (!isOpen) { applyFilter(); open(); return; }
      if (!filtered.length) return;
      var next = e.key === 'ArrowDown' ? activeIndex + 1 : activeIndex - 1;
      if (next >= filtered.length) next = 0;          // зацикливание
      if (next < 0) next = filtered.length - 1;
      setActive(next);
    } else if (e.key === 'Enter') {
      if (isOpen && activeIndex >= 0) { e.preventDefault(); go(activeIndex); }
    } else if (e.key === 'Escape') {
      if (isOpen) { e.preventDefault(); close(); }
      else { input.blur(); }                          // повторный Esc — снять фокус
    } else if (e.key === 'Tab') {
      close();                                        // Tab уводит дальше по странице
    }
  });

  // mousedown, а не click: blur поля не должен успеть закрыть список до перехода
  list.addEventListener('mousedown', function (e) {
    var li = e.target.closest('.search-item');
    if (!li) return;
    e.preventDefault();
    go(parseInt(li.dataset.index, 10));
  });

  list.addEventListener('mousemove', function (e) {
    var li = e.target.closest('.search-item');
    if (li) {
      var i = parseInt(li.dataset.index, 10);
      if (i !== activeIndex) setActive(i);
    }
  });

  document.addEventListener('click', function (e) {
    if (!e.target.closest('#header-search')) close();
  });
})();
