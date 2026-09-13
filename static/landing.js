/* landing.js — поведение гостевой главной-портфолио (заход 334).

   Всё в одной обёртке: глобальных имён страница не заводит (проверка 30).

   ЛЕНТА РАБОТ (блок C)
   · Ряды едут от ПРОКРУТКИ: сдвиг — функция положения секции в окне,
     а не времени. Остановил прокрутку — лента стоит.
   · Сдвиг пишется переменной `--pf-shift` на дорожку, то есть одним
     `transform`: раскладка при беге не пересчитывается.
   · Дорожка — три одинаковых набора. База сдвига — минус один набор
     (виден средний), размах — не больше трети набора в каждую сторону; при любом
     сдвиге дорожка перекрывает окно целиком, край не показывается.
   · Ролики получают `src` только когда ряд доехал до экрана (C3). Порог
     `rootMargin` на пиксель внутрь: у ряда, стоящего ровно у нижнего
     края окна, пересечение нулевой площади считается пересечением, и без
     этого первый экран мог бы начать качать ленту.
   · «Уменьшить движение» (C5): лента стоит, ролики не играют, но первый
     кадр показан — `preload = auto` и без `play()`. */
(function () {
  'use strict';

  var лента = document.querySelector('.pf-feed');
  if (!лента) return;

  var тихо = window.matchMedia('(prefers-reduced-motion: reduce)');
  var ряды = Array.prototype.slice.call(лента.querySelectorAll('.pf-feed-row'));
  var набор = 0;          // ширина одного набора вместе с зазором после него
  var доехала = false;

  function мерить() {
    var первый = лента.querySelector('.pf-feed-set');
    var дорожка = лента.querySelector('.pf-feed-track');
    if (!первый || !дорожка) return;
    var зазор = parseFloat(getComputedStyle(дорожка).columnGap) || 0;
    набор = первый.getBoundingClientRect().width + зазор;
  }

  function сдвинуть() {
    if (!набор) мерить();
    var доля = 0.5;
    if (!тихо.matches) {
      var к = лента.getBoundingClientRect();
      var ход = window.innerHeight + к.height;
      доля = Math.min(1, Math.max(0, (window.innerHeight - к.top) / ход));
    }
    // СКОРОСТЬ — ДОЛЯ ОТ ПРОКРУТКИ, а не от ширины набора: первая версия
    // брала треть набора, и на 2560 ряд проезжал 1179 px за 1140 px
    // прокрутки, шагом до 66 px за кадр (замер пробы). Правило проекта —
    // лёгкий параллакс, 20–30% скорости прокрутки: 0.3. Треть набора
    // остаётся потолком, чтобы край дорожки не показался никогда.
    var размах = Math.min(набор / 3, 0.3 * (window.innerHeight + лента.offsetHeight) / 2);
    ряды.forEach(function (ряд) {
      var знак = Number(ряд.getAttribute('data-feed-dir')) || 1;
      var сдвиг = -набор + знак * (доля - 0.5) * 2 * размах;
      ряд.firstElementChild.style.setProperty('--pf-shift', сдвиг.toFixed(2) + 'px');
    });
  }

  // СДВИГ ПИШЕТСЯ ПРЯМО В СОБЫТИИ ПРОКРУТКИ, а не в следующем кадре.
  // Событие прокрутки браузер и так шлёт раз в кадр перед отрисовкой;
  // отложенный `requestAnimationFrame` давал отставание ряда от прокрутки
  // на кадр-два — замер пробы: до 4.3 px от прямой и 11–19 кадров, где
  // ряд шевелился при стоящей прокрутке.

  function ролики() {
    return Array.prototype.slice.call(лента.querySelectorAll('video'));
  }

  function запустить() {
    ролики().forEach(function (в) {
      var адрес = в.getAttribute('data-src');
      if (адрес && !в.getAttribute('src')) {
        в.preload = 'auto';
        в.setAttribute('src', адрес);
      }
      if (тихо.matches) {
        в.pause();
      } else {
        var обещание = в.play();
        if (обещание && обещание.catch) обещание.catch(function () {});
      }
    });
  }

  function остановить() {
    ролики().forEach(function (в) { if (в.getAttribute('src')) в.pause(); });
  }

  if ('IntersectionObserver' in window) {
    var видно = new Set();
    var наблюдатель = new IntersectionObserver(function (записи) {
      записи.forEach(function (з) {
        if (з.isIntersecting) видно.add(з.target); else видно.delete(з.target);
      });
      if (видно.size) { доехала = true; запустить(); } else if (доехала) { остановить(); }
    }, { rootMargin: '0px 0px -1px 0px' });
    ряды.forEach(function (ряд) { наблюдатель.observe(ряд); });
  } else {
    запустить();
  }

  мерить();
  сдвинуть();
  window.addEventListener('scroll', сдвинуть, { passive: true });
  window.addEventListener('resize', function () { мерить(); сдвинуть(); });
  var смена = function () { сдвинуть(); if (доехала) запустить(); };
  if (тихо.addEventListener) тихо.addEventListener('change', смена);
})();
