/* ВЫБРАННЫЙ ЭЛЕМЕНТ ПРОКРУЧИВАЕМОЙ ЛЕНТЫ ВИДЕН (BACKLOG №326).

   Ряд вкладок или чипов на узкой ширине листается вбок и открывается
   с нулевой прокрутки. Выбранный элемент правее окна человек не видит —
   и не видит, в каком разделе стоит. Замер 2026-09-13 на 390: у ряда
   разделов админки выбранная вкладка не видна в 3 разделах из 5
   (Enshrouded 0 %, Главная 0 %, Упражнения 33 %), у вкладок «Общей
   аптечки» — после перерисовки окна.

   ЛЕНТА ВЫВОДИТСЯ, А НЕ ПЕРЕЧИСЛЯЕТСЯ. От каждого видимого элемента
   с признаком выбора вверх ищется ближайший предок с горизонтальной
   прокруткой, которому есть что прокручивать. Признаки выбора — те, что
   объявляет компонентная база и ARIA: `.active`, `aria-current`,
   `aria-selected="true"`. Новая лента попадает сюда сама.

   ПОДКЛЮЧЁН В <head>, А НЕ В ХВОСТЕ, И ЭТО ПРО ПЕРВЫЙ КАДР (§6.0.15).
   Наблюдатель ставится до разбора разметки; поправка идёт в
   `requestAnimationFrame`, то есть до отрисовки того кадра, в котором
   лента появилась. В хвосте страницы первый кадр мог бы нарисоваться
   с нулевой прокруткой и дёрнуться следом.

   РУЧНУЮ ПРОКРУТКУ НЕ ОТБИРАЕТ. Лента двигается, только когда в ней
   СМЕНИЛСЯ выбранный элемент либо сама лента новая (перерисовка окна
   даёт новый узел с нулевой прокруткой). Листнул человек ряд вбок —
   выбор тот же, и ряд остаётся там, куда его увели. */
(function () {
  'use strict';
  var МАРКЕРЫ = '.active, [aria-current="page"], [aria-current="true"], [aria-selected="true"]';
  var ЗАПАС = 16;
  var поправлено = new WeakMap();
  var запланировано = false;

  function ленты(эл) {
    var п = эл.parentElement;
    while (п && п !== document.documentElement) {
      var s = getComputedStyle(п);
      if ((s.overflowX === 'auto' || s.overflowX === 'scroll') &&
          п.scrollWidth > п.clientWidth + 1) return п;
      п = п.parentElement;
    }
    return null;
  }

  function прокрутитьКВыбранному() {
    запланировано = false;
    var выбранные = document.querySelectorAll(МАРКЕРЫ);
    for (var i = 0; i < выбранные.length; i++) {
      var эл = выбранные[i];
      if (эл.checkVisibility && !эл.checkVisibility()) continue;
      var лента = ленты(эл);
      if (!лента || поправлено.get(лента) === эл) continue;
      var r = эл.getBoundingClientRect(), л = лента.getBoundingClientRect();
      if (r.left < л.left + ЗАПАС || r.right > л.right - ЗАПАС) {
        лента.scrollLeft += (r.width + 2 * ЗАПАС > л.width)
          ? r.left - л.left - ЗАПАС
          : (r.left - л.left) - (л.width - r.width) / 2;
      }
      поправлено.set(лента, эл);
    }
  }
  window.прокрутитьКВыбранному = прокрутитьКВыбранному;

  function запланировать() {
    if (запланировано) return;
    запланировано = true;
    requestAnimationFrame(function () { window.прокрутитьКВыбранному(); });
  }

  new MutationObserver(запланировать).observe(document.documentElement, {
    childList: true, subtree: true, attributes: true,
    attributeFilter: ['class', 'hidden', 'open', 'aria-selected', 'aria-current', 'style']
  });
  addEventListener('resize', запланировать);
  addEventListener('pageshow', запланировать);
  запланировать();
})();
