/* ПОВЕДЕНИЕ КАРКАСА v2 (BACKLOG №352, письмо 2). Разметка — `_header.html`.

   1. «Инструменты» — всплывающий список по наведению (только там, где
      наведение есть) и по клику. Esc закрывает и возвращает фокус
      на кнопку, стрелки ходят по пунктам. Ниже десктопа — раскрывающийся
      список на месте (CSS), наведения нет.
   2. «Свернуть» — меню в полосу иконок; состояние в `localStorage['v2-rail']`,
      класс ставит встроенный скрипт шапки ДО первой отрисовки.
   3. Ниже десктопа меню открывается кнопкой в верхней строке поверх
      страницы; закрывается кнопкой, тапом мимо и Esc.
   Хранилище недоступно — каркас работает, просто ничего не помнит.

   Глобальных имён не заводит. */
(function () {
  var каркас = document.getElementById('v2-shell');
  if (!каркас) return;
  var меню = document.getElementById('v2-side');
  var кнопка = document.getElementById('v2-tools-btn');
  var список = document.getElementById('v2-tools-pop');
  var свернуть = document.getElementById('v2-side-fold');
  var бургер = document.getElementById('v2-burger');
  var крестик = document.getElementById('v2-side-close');
  var подложка = document.getElementById('v2-side-scrim');
  var десктоп = window.matchMedia('(min-width: 1024px)');
  var наведение = window.matchMedia('(hover: hover)');
  var таймер = null;

  function пункты() { return Array.prototype.slice.call(список.querySelectorAll('[role="menuitem"]')); }

  function поставить() {
    if (!десктоп.matches) { список.style.top = ''; список.style.left = ''; return; }
    var r = кнопка.getBoundingClientRect();
    var м = меню.getBoundingClientRect();
    список.style.left = (м.right + 8) + 'px';
    var верх = Math.min(r.top, window.innerHeight - список.offsetHeight - 8);
    список.style.top = Math.max(8, верх) + 'px';
  }
  function открыт() { return !список.hidden; }
  function открыть(фокус) {
    clearTimeout(таймер);
    if (!открыт()) {
      список.hidden = false;
      кнопка.setAttribute('aria-expanded', 'true');
      поставить();
    }
    if (фокус) { var п = пункты(); if (п.length) п[0].focus(); }
  }
  function закрыть(вернуть) {
    clearTimeout(таймер);
    if (!открыт()) return;
    список.hidden = true;
    кнопка.setAttribute('aria-expanded', 'false');
    if (вернуть) кнопка.focus();
  }
  function закрытьПозже() {
    clearTimeout(таймер);
    таймер = setTimeout(function () { закрыть(false); }, 200);
  }

  кнопка.addEventListener('click', function () {
    if (открыт()) закрыть(false); else открыть(false);
  });
  кнопка.addEventListener('keydown', function (e) {
    if (e.key === 'ArrowDown' || e.key === 'ArrowRight') { e.preventDefault(); открыть(true); }
  });
  [кнопка, список].forEach(function (эл) {
    эл.addEventListener('mouseenter', function () {
      if (наведение.matches && десктоп.matches) открыть(false);
    });
    эл.addEventListener('mouseleave', function () {
      if (наведение.matches && десктоп.matches) закрытьПозже();
    });
  });
  список.addEventListener('keydown', function (e) {
    var п = пункты(), i = п.indexOf(document.activeElement);
    if (e.key === 'ArrowDown') { e.preventDefault(); п[(i + 1) % п.length].focus(); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); п[(i - 1 + п.length) % п.length].focus(); }
    else if (e.key === 'Home') { e.preventDefault(); п[0].focus(); }
    else if (e.key === 'End') { e.preventDefault(); п[п.length - 1].focus(); }
  });
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape') return;
    if (открыт()) { закрыть(true); e.stopPropagation(); return; }
    if (каркас.classList.contains('is-side-open')) { закрытьМеню(true); }
  });
  document.addEventListener('click', function (e) {
    if (открыт() && !список.contains(e.target) && !кнопка.contains(e.target)) закрыть(false);
  });
  window.addEventListener('resize', function () { if (открыт()) поставить(); });
  меню.addEventListener('scroll', function () { if (открыт()) поставить(); });

  // 2. Полоса иконок
  function отметитьПолосу() {
    var полоса = document.documentElement.classList.contains('v2-rail');
    свернуть.setAttribute('aria-pressed', полоса ? 'true' : 'false');
    свернуть.title = полоса ? 'Развернуть меню' : 'Свернуть меню';
    var подпись = свернуть.querySelector('.v2-side-label');
    if (подпись) подпись.textContent = полоса ? 'Развернуть' : 'Свернуть';
  }
  свернуть.addEventListener('click', function () {
    var полоса = document.documentElement.classList.toggle('v2-rail');
    try { localStorage.setItem('v2-rail', полоса ? '1' : '0'); } catch (e) { /* хранилище недоступно */ }
    отметитьПолосу();
    закрыть(false);
  });
  отметитьПолосу();

  // 3. Меню поверх страницы ниже десктопа
  var прежнийФокус = null;
  function открытьМеню() {
    прежнийФокус = document.activeElement;
    каркас.classList.add('is-side-open');
    бургер.setAttribute('aria-expanded', 'true');
    крестик.focus();
  }
  function закрытьМеню(вернуть) {
    каркас.classList.remove('is-side-open');
    бургер.setAttribute('aria-expanded', 'false');
    закрыть(false);
    if (вернуть) (прежнийФокус && прежнийФокус.focus ? прежнийФокус : бургер).focus();
  }
  бургер.addEventListener('click', открытьМеню);
  крестик.addEventListener('click', function () { закрытьМеню(true); });
  подложка.addEventListener('click', function () { закрытьМеню(true); });
  десктоп.addEventListener('change', function () { if (десктоп.matches) закрытьМеню(false); });
})();
