/* УВЕЛИЧЕНИЕ КАРТИНКИ ПО НАВЕДЕНИЮ (на сенсорном — по касанию).

   СИСТЕМНЫЙ КОМПОНЕНТ, а не приём одной страницы. Потребителей два:
   баннер карточки в разделе Enshrouded и миниатюра в таблице экрана
   управления. До 2026-08-23 механика жила ~90 строками ВНУТРИ
   `templates/enshrouded.html`, и таблица экрана управления показывала
   картинки 64x40 без всякого способа их разглядеть: переписать те же
   90 строк во второй шаблон значило бы завести дубль, который разойдётся
   молча (CLAUDE.md §6.0.7).

   РАЗМЕТКИ ОТ ПОТРЕБИТЕЛЯ НЕ ТРЕБУЕТСЯ. Окно скрипт заводит сам:
   иначе страница, забывшая вписать <div class="img-zoom">, получала бы
   немой отказ — наведение работает, показывать нечего, консоль чиста.

   ПОДКЛЮЧЕНИЕ: элемент-якорь помечается `data-zoom` и содержит <img>.
   Ничего больше — ни класса, ни обработчика.
*/
(function () {
  'use strict';

  var ЖЕЛАЕМЫЙ_W = 700, ЖЕЛАЕМЫЙ_H = 500, ПОЛЕ = 8, ЗАЗОР = 14;
  // Ниже этой ширины окно перестаёт быть увеличением — тогда лучше
  // поставить его по центру экрана, чем ужимать до значка.
  var МИНИМУМ_W = 300;

  var окно = null, картинка = null, якорь = null;
  var естьНаведение = window.matchMedia('(hover: hover)').matches;

  function завести() {
    if (окно) return;
    окно = document.createElement('div');
    окно.className = 'img-zoom';
    окно.setAttribute('aria-hidden', 'true');
    картинка = document.createElement('img');
    картинка.alt = '';
    окно.appendChild(картинка);
    document.body.appendChild(окно);
  }

  function закрыть() {
    якорь = null;
    if (окно) окно.classList.remove('is-open');
  }

  /* Готова ли картинка якоря: у незагруженной naturalWidth равен нулю,
     и окно показало бы пустую коробку. Прежний код раздела гонялся
     за этим классом `.loaded`; вопрос к самой картинке честнее — он
     верен и для той, что пришла из кеша без события load. */
  function источник(эл) {
    var i = эл.querySelector('img');
    return (i && i.complete && i.naturalWidth > 0) ? i.currentSrc || i.src : null;
  }

  function показать(эл) {
    var src = источник(эл);
    if (!src) return;
    завести();
    якорь = эл;
    var нарисовать = function () {
      if (якорь !== эл) return;      // навели уже на другое, пока грузилось
      разместить(эл);
      окно.classList.add('is-open');
    };
    if (картинка.src === src && картинка.complete && картинка.naturalWidth > 0) {
      нарисовать(); return;
    }
    окно.classList.remove('is-open');
    картинка.onload = function () { requestAnimationFrame(нарисовать); };
    картинка.onerror = function () {};
    картинка.src = src;
    if (картинка.complete && картинка.naturalWidth > 0) requestAnimationFrame(нарисовать);
  }

  function переключить(эл) {
    if (якорь === эл && окно && окно.classList.contains('is-open')) закрыть();
    else показать(эл);
  }

  function разместить(эл) {
    var vw = document.documentElement.clientWidth, vh = window.innerHeight;
    var r = эл.getBoundingClientRect();
    // ЧЕТЫРЕ СТОРОНЫ ОТ ЯКОРЯ. Выбирается та, где помещается САМОЕ
    // КРУПНОЕ окно с сохранением пропорции; окно ставится ВНУТРИ
    // выбранной стороны, то есть якоря не задевает по построению.
    var стороны = [
      {x0: r.right + ЗАЗОР, x1: vw - ПОЛЕ,      y0: ПОЛЕ,             y1: vh - ПОЛЕ},
      {x0: ПОЛЕ,            x1: r.left - ЗАЗОР, y0: ПОЛЕ,             y1: vh - ПОЛЕ},
      {x0: ПОЛЕ,            x1: vw - ПОЛЕ,      y0: r.bottom + ЗАЗОР, y1: vh - ПОЛЕ},
      {x0: ПОЛЕ,            x1: vw - ПОЛЕ,      y0: ПОЛЕ,             y1: r.top - ЗАЗОР}
    ];
    var лучшая = null, лучшийK = 0;
    for (var i = 0; i < стороны.length; i++) {
      var б = стороны[i];
      var k = Math.min(1, (б.x1 - б.x0) / ЖЕЛАЕМЫЙ_W, (б.y1 - б.y0) / ЖЕЛАЕМЫЙ_H);
      if (k > лучшийK) { лучшийK = k; лучшая = б; }
    }
    var зажать = function (v, мин, макс) {
      return Math.max(мин, Math.min(v, Math.max(мин, макс)));
    };
    var w, h, left, top;
    if (лучшая && ЖЕЛАЕМЫЙ_W * лучшийK >= МИНИМУМ_W) {
      w = Math.round(ЖЕЛАЕМЫЙ_W * лучшийK); h = Math.round(ЖЕЛАЕМЫЙ_H * лучшийK);
      left = Math.round(зажать(r.left + r.width / 2 - w / 2, лучшая.x0, лучшая.x1 - w));
      top  = Math.round(зажать(r.top  + r.height / 2 - h / 2, лучшая.y0, лучшая.y1 - h));
    } else {
      // Ни с одной стороны не помещается ничего годного — окно встаёт
      // по центру экрана. Якорь оно закроет, и это меньшее зло:
      // окно в 200px увеличением уже не является.
      var k2 = Math.min(1, (vw - ПОЛЕ * 2) / ЖЕЛАЕМЫЙ_W, (vh - ПОЛЕ * 2) / ЖЕЛАЕМЫЙ_H);
      w = Math.round(ЖЕЛАЕМЫЙ_W * k2); h = Math.round(ЖЕЛАЕМЫЙ_H * k2);
      left = Math.round((vw - w) / 2); top = Math.round((vh - h) / 2);
    }
    окно.style.width = w + 'px';  окно.style.height = h + 'px';
    окно.style.left = left + 'px'; окно.style.top = top + 'px';
  }

  if (естьНаведение) {
    document.addEventListener('mousemove', function (e) {
      var эл = e.target.closest && e.target.closest('[data-zoom]');
      if (эл === якорь) return;
      if (!эл) { закрыть(); return; }
      показать(эл);
    });
  }
  // Нажатие мимо картинки закрывает увеличение — единственный способ
  // закрыть его пальцем, кроме повторного нажатия по той же картинке.
  document.addEventListener('click', function (e) {
    var эл = e.target.closest && e.target.closest('[data-zoom]');
    if (эл) { if (!естьНаведение) переключить(эл); return; }
    if (якорь) закрыть();
  }, true);
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') закрыть(); });
  window.addEventListener('resize', function () { if (якорь) разместить(якорь); });
  window.addEventListener('scroll', закрыть, {passive: true});

  window.закрыть_увеличение = закрыть;
})();
