// ── header-search.js — сквозной поиск в общей шапке ─────────────────────────
//
// Инструменты приходят из _header.html (JSON-скрипт #nav-search-data, источник —
// глобал TOOLS из main.py) и фильтруются ЛОКАЛЬНО: их мало, они стабильны,
// и навигация не должна ждать сеть. Пункт «Админка» попадает в JSON только
// у админа, поэтому здесь никаких проверок прав нет и быть не должно.
//
// Письма и продукты приходят с сервера (/api/search) и только когда человек
// начал печатать. По клику показываются одни инструменты: иначе при сотне
// писем клик по полю вываливал бы лавину, и поиск перестал бы работать как
// быстрая навигация.
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
  if (!input) return;                                    // гость: поля нет в DOM

  // ── Плейсхолдер под ширину экрана ────────────────────────────────────────
  //
  // Содержимое placeholder через CSS не задаётся — свойства с таким смыслом
  // в CSS нет вовсе, ::placeholder красит уже существующий текст. Поэтому
  // подмена скриптом, а не медиазапросом.
  //
  // ПОРОГ 640px ВЗЯТ ЗАМЕРОМ, а не «на глаз». Строка «Найти инструмент,
  // письмо, продукт…» занимает 266px при кегле 15px; поле отдаёт тексту
  // 424px, пока шапка не начала его сжимать, и сужается вместе с окном.
  // Замер по 2px: текст перестаёт помещаться между 574 и 572 CSS-пикселями
  // ширины окна (поле 264 против строки 266). 640 — ближайший порог,
  // который уже используется в проекте, и он даёт 67px запаса: на 640px
  // полю остаётся 332px. Запас нужен не «на всякий случай», а под другой
  // системный шрифт и под увеличенный базовый кегль браузера, при которых
  // строка шире 266px.
  //
  // Скачка вёрстки подмена не даёт по построению: placeholder в раскладке
  // не участвует, ширину поля задаёт flex шапки. Замерено — коробка поля
  // одинакова с обеими строками, до пикселя.
  //
  // НАПРАВЛЕНИЕ ПОДМЕНЫ: в разметке лежит КОРОТКАЯ строка, длинная
  // подставляется на широком экране. До 2026-08-13 было наоборот, и это
  // давало мигание на узком экране: скрипт подключён с defer и выполняется
  // после разбора разметки, то есть первый кадр успевал нарисовать длинную
  // строку в поле шириной 138px, а потом она сменялась на «Поиск».
  // Прошлый замер дефекта дал ложный зелёный, потому что читал значение
  // атрибута после загрузки страницы — то есть уже подменённое. Замер,
  // который его увидел: скрипт отключён совсем (route.abort), и в поле
  // остаётся то, что нарисовал первый кадр.
  //
  // Так подменять нечего именно там, где обрезается. На широком экране
  // подмена осталась, но короткая строка в поле 480px не обрезается,
  // и смена не читается как дефект. Побочно: не отработавший скрипт
  // оставляет узкому экрану ВЕРНЫЙ текст, а не обрезанный.
  //
  // ПЕРВЫЙ ВЫБОР ДЕЛАЕТ НЕ ЭТОТ ФАЙЛ, а встроенный скрипт в `_header.html`:
  // он синхронный и успевает до первой отрисовки, а этот подключён
  // с `defer` и приходит уже к нарисованному экрану — замер до правки
  // давал смену подписи через 304–362 мс после первого кадра.
  // Здесь остаётся РЕАКЦИЯ НА ПЕРЕСЕЧЕНИЕ ПОРОГА: поворот экрана,
  // перетаскивание окна. Первый вызов `применить()` сохранён и вреда
  // не делает — он ставит то же самое значение.
  //
  // matchMedia, а не обработчик resize: событие change приходит один раз
  // на пересечение порога, а не сотнями кадров при перетаскивании окна.
  // Второго поля ввода в разметке нет и не появляется — меняется атрибут
  // у того же самого input.
  (function () {
    var широкий = input.getAttribute('data-placeholder-wide');
    if (!широкий || !window.matchMedia) return;
    // УЗКАЯ СТРОКА БЕРЁТСЯ ИЗ АТРИБУТА, А НЕ ИЗ ТЕКУЩЕГО ЗНАЧЕНИЯ.
    // Встроенный скрипт в шапке к этому моменту уже мог поставить
    // длинную (он выполняется до первой отрисовки), и чтение
    // `placeholder` вернуло бы её — то есть при сужении окна в поле
    // осталась бы длинная строка, обрезанная на 390px.
    var узкий = input.getAttribute('data-placeholder-narrow') || 'Поиск';
    var запрос = input.getAttribute('data-placeholder-mq') || '(max-width: 640px)';
    var mq = window.matchMedia(запрос);
    var применить = function () { input.placeholder = mq.matches ? узкий : широкий; };
    применить();
    // addEventListener у MediaQueryList — не везде; addListener оставлен
    // запасным путём, иначе на старом движке порог перестанет отслеживаться
    // молча: первая установка сработает, реакция на поворот экрана — нет
    if (mq.addEventListener) mq.addEventListener('change', применить);
    else if (mq.addListener) mq.addListener(применить);
  })();

  if (!dropdown || !list || !dataEl) return;             // другая разметка

  var TOOLS = [];
  try {
    TOOLS = JSON.parse(dataEl.textContent) || [];
  } catch (e) {
    return;   // битые данные — поле останется просто инпутом, ничего не ломаем
  }
  if (!TOOLS.length) return;

  var MIN_LEN = 2;        // 1 символ — слишком широкий запрос, сервер его отклонит
  var DEBOUNCE_MS = 250;

  // Плоский список ВСЕХ пунктов всех групп подряд: по нему идёт клавиатура.
  // Заголовки групп сюда не входят и не выделяются
  var flat = [];
  var groups = [];        // [{title, items:[…], more:N}]
  var activeIndex = -1;
  var isOpen = false;
  var timer = null;
  var controller = null;  // отмена предыдущего запроса
  var lastQuery = '';

  // ── Сбор групп ──
  function toolItems(q) {
    var found = q
      ? TOOLS.filter(function (it) { return it.name.toLowerCase().indexOf(q) !== -1; })
      : TOOLS.slice();
    return found.map(function (it) {
      return {url: it.url, name: it.name, icon: it.icon, cls: 'tool-' + it.id};
    });
  }

  function rebuild(q, remote) {
    groups = [];
    var tools = toolItems(q);
    if (tools.length) groups.push({title: 'Инструменты', items: tools, more: 0});

    if (remote) {
      if (remote.letters && remote.letters.length) {
        groups.push({
          title: 'Письма', more: remote.letters_more || 0,
          items: remote.letters.map(function (p) {
            return {url: p.url, name: p.title, sub: p.date, icon: 'mail', cls: 'tool-hh'};
          })
        });
      }
      if (remote.foods && remote.foods.length) {
        groups.push({
          title: 'Продукты', more: remote.foods_more || 0,
          items: remote.foods.map(function (p) {
            return {url: p.url, name: p.title, sub: p.sub, icon: 'apple', cls: 'tool-nutrition'};
          })
        });
      }
    }

    flat = [];
    groups.forEach(function (g) { g.items.forEach(function (it) { flat.push(it); }); });
    activeIndex = flat.length ? 0 : -1;   // первый пункт сразу под Enter
    render();
  }

  // ── Рендер ──
  function render() {
    list.innerHTML = '';
    var i = 0;
    groups.forEach(function (g) {
      var head = document.createElement('li');
      head.className = 'search-group-title';
      head.setAttribute('role', 'presentation');   // не пункт списка, не выделяется
      head.textContent = g.title;
      list.appendChild(head);

      g.items.forEach(function (item) {
        var idx = i++;
        var li = document.createElement('li');
        li.className = 'search-item' + (idx === activeIndex ? ' active' : '');
        li.id = 'nav-search-item-' + idx;
        li.setAttribute('role', 'option');
        li.setAttribute('aria-selected', idx === activeIndex ? 'true' : 'false');
        li.dataset.url = item.url;
        li.dataset.index = idx;

        var ico = document.createElement('i');
        ico.setAttribute('data-lucide', item.icon);
        ico.className = 'search-item-icon ' + item.cls;

        var label = document.createElement('span');
        label.className = 'search-item-name';
        label.textContent = item.name;

        li.appendChild(ico);
        li.appendChild(label);
        if (item.sub) {
          var sub = document.createElement('span');
          sub.className = 'search-item-sub';
          sub.textContent = item.sub;
          li.appendChild(sub);
        }
        list.appendChild(li);
      });

      // «ещё N» без ссылки: смысл в том, чтобы уточнить запрос, а не листать
      if (g.more > 0) {
        var more = document.createElement('li');
        more.className = 'search-group-more';
        more.setAttribute('role', 'presentation');
        more.textContent = 'ещё ' + g.more;
        list.appendChild(more);
      }
    });

    var nothing = flat.length === 0;
    emptyEl.hidden = !nothing;
    list.hidden = nothing;

    // Lucide заменяет <i data-lucide> на <svg> — вызываем после вставки в DOM
    if (window.lucide && typeof window.lucide.createIcons === 'function') {
      window.lucide.createIcons();
    }
    syncActiveDescendant();
  }

  function syncActiveDescendant() {
    if (activeIndex >= 0 && flat[activeIndex]) {
      input.setAttribute('aria-activedescendant', 'nav-search-item-' + activeIndex);
    } else {
      input.removeAttribute('aria-activedescendant');
    }
  }

  function setActive(i) {
    activeIndex = i;
    var items = list.querySelectorAll('.search-item');
    for (var k = 0; k < items.length; k++) {
      var on = k === i;
      items[k].classList.toggle('active', on);
      items[k].setAttribute('aria-selected', on ? 'true' : 'false');
      // держим выделенный пункт в зоне видимости при длинном списке
      if (on && items[k].scrollIntoView) items[k].scrollIntoView({block: 'nearest'});
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

  // ── Запрос к серверу ──
  function fetchRemote(q) {
    // Отменяем предыдущий: иначе ответ по «сб» может прийти после ответа
    // по «сбер» и перезаписать его — гонка выглядит как поломка поиска
    if (controller) controller.abort();
    controller = new AbortController();
    var мой = q;
    fetch('/api/search?q=' + encodeURIComponent(q), {signal: controller.signal})
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        // ещё одна защита от гонки: пришёл ответ на устаревший запрос — игнорируем
        if (!data || мой !== lastQuery) return;
        rebuild(мой, data);
      })
      .catch(function () { /* отменённый или сетевой сбой — инструменты уже видны */ });
  }

  function applyFilter() {
    var q = input.value.trim().toLowerCase();
    lastQuery = q;
    // Инструменты показываем сразу, не дожидаясь сети
    rebuild(q, null);
    if (timer) clearTimeout(timer);
    if (q.length < MIN_LEN) {
      if (controller) controller.abort();
      return;
    }
    timer = setTimeout(function () { fetchRemote(q); }, DEBOUNCE_MS);
  }

  function go(i) {
    var item = flat[i];
    if (item) window.location.href = item.url;
  }

  // ── События ──
  input.addEventListener('focus', function () { applyFilter(); open(); });
  input.addEventListener('input', function () { applyFilter(); open(); });

  input.addEventListener('keydown', function (e) {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      if (!isOpen) { applyFilter(); open(); return; }
      if (!flat.length) return;
      var next = e.key === 'ArrowDown' ? activeIndex + 1 : activeIndex - 1;
      if (next >= flat.length) next = 0;          // зацикливание
      if (next < 0) next = flat.length - 1;
      setActive(next);
    } else if (e.key === 'Enter') {
      if (isOpen && activeIndex >= 0) { e.preventDefault(); go(activeIndex); }
    } else if (e.key === 'Escape') {
      if (isOpen) { e.preventDefault(); close(); }
      else { input.blur(); }                      // повторный Esc — снять фокус
    } else if (e.key === 'Tab') {
      close();                                    // Tab уводит дальше по странице
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
