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

  var тихо = window.matchMedia('(prefers-reduced-motion: reduce)');

  /* МАГНИТНЫЙ ПОРТРЕТ (заход 339, блок A4)
     · Цель сдвига — расстояние от курсора до ЦЕНТРА портрета, делённое
       на КОЭФФИЦИЕНТ: курсор в углу окна двигает портрет заметно,
       курсор на портрете — почти никак.
     · Плавность — приближение к цели на долю разницы в кадр, а не
       переход CSS: переход перезапускался бы на каждое движение мыши
       и дёргал. Кадры идут, только пока портрет не пришёл к цели.
     · Вход и выход плавные: курсор ушёл из окна либо первый экран уехал
       из вида — цель ноль, портрет спокойно возвращается.
     · Только настоящий указатель (`hover: hover` и `pointer: fine`)
       и без «уменьшить движение»: на сенсорном нет курсора, и сдвиг
       от последнего касания читался бы залипшим. */
  var магнит = document.querySelector('[data-pf-magnet]');
  var указатель = window.matchMedia('(hover: hover) and (pointer: fine)');
  if (магнит) {
    var КОЭФФИЦИЕНТ = 12;
    var ДОЛЯ_КАДРА = 0.12;
    var цель = {x: 0, y: 0}, сейчас = {x: 0, y: 0}, кадр = 0;
    var записать = function () {
      магнит.style.setProperty('--pf-mx', сейчас.x.toFixed(2) + 'px');
      магнит.style.setProperty('--pf-my', сейчас.y.toFixed(2) + 'px');
    };
    var шагнуть = function () {
      сейчас.x += (цель.x - сейчас.x) * ДОЛЯ_КАДРА;
      сейчас.y += (цель.y - сейчас.y) * ДОЛЯ_КАДРА;
      if (Math.abs(цель.x - сейчас.x) < 0.05 && Math.abs(цель.y - сейчас.y) < 0.05) {
        сейчас.x = цель.x; сейчас.y = цель.y; кадр = 0;
      } else {
        кадр = requestAnimationFrame(шагнуть);
      }
      записать();
    };
    var тянуть = function (x, y) {
      цель.x = x; цель.y = y;
      if (!кадр) кадр = requestAnimationFrame(шагнуть);
    };
    var можно = function () { return указатель.matches && !тихо.matches; };
    window.addEventListener('pointermove', function (e) {
      if (!можно() || e.pointerType === 'touch') return;
      // центр — по коробке БЕЗ текущего сдвига: иначе портрет убегал бы
      // от курсора собственным смещением
      var к = магнит.parentElement.getBoundingClientRect();
      if (к.bottom < 0 || к.top > window.innerHeight) { тянуть(0, 0); return; }
      тянуть((e.clientX - (к.left + к.width / 2)) / КОЭФФИЦИЕНТ,
             (e.clientY - (к.top + к.height / 2)) / КОЭФФИЦИЕНТ);
    }, { passive: true });
    document.documentElement.addEventListener('pointerleave', function () { тянуть(0, 0); });
    window.addEventListener('blur', function () { тянуть(0, 0); });
    var сбросить = function () { if (!можно()) { цель.x = цель.y = сейчас.x = сейчас.y = 0; записать(); } };
    if (тихо.addEventListener) тихо.addEventListener('change', сбросить);
    if (указатель.addEventListener) указатель.addEventListener('change', сбросить);
  }

  /* О СЕБЕ (блок D)
     · Знаки абзаца зажигаются от прокрутки: начинается, когда верх текста
       дошёл до 85% окна, кончается, когда низ дошёл до 40%. Функция
       положения, а не времени: откатил прокрутку — знаки гаснут обратно.
     · Декор выезжает с боков при доезде секции, один раз.
     · «Уменьшить движение»: всё зажжено и на месте сразу. */
  var абзац = document.querySelector('.pf-about-text');
  if (абзац) {
    var знаки = Array.prototype.slice.call(абзац.querySelectorAll('.pf-ch'));
    var зажжено = -1;
    var секция_о_себе = абзац.closest('.pf-about') || абзац;
    /* ДОЛЯ ПРОЯВЛЕННОГО (заход 339, блок B). Здесь стояло: начало — верх
       текста на 85% окна, конец — НИЗ ТЕКСТА на 40% окна. Замер: когда
       секция целиком в окне, проявлено 35% (2560) и 47% (1920), и граница
       стояла посреди слова — до конца текст доходил, только уехав в верх
       экрана. Теперь начало — верх текста показался у низа окна, конец —
       НИЗ СЕКЦИИ дошёл до низа окна, то есть секция целиком видна. У секции
       выше окна (телефон: декор над текстом и под ним) это наступает, когда
       верх уже уехал, — там конец раньше: низ текста поднялся на 75% окна.
       Берётся то, что наступит РАНЬШЕ. Оба расстояния меняются с прокруткой
       одинаково, поэтому знаменатель постоянен и граница идёт ровно. */
    var доля_проявления = function () {
      var vh = window.innerHeight;
      var т = абзац.getBoundingClientRect();
      var пройдено = vh - т.top;                                  // 0 — верх текста у низа окна
      var осталось = Math.min(секция_о_себе.getBoundingClientRect().bottom - vh,
                              т.bottom - 0.75 * vh);
      var путь = пройдено + осталось;
      return путь > 0 ? Math.min(1, Math.max(0, пройдено / путь)) : 1;
    };
    var зажечь = function () {
      var сколько = знаки.length;
      if (!тихо.matches) {
        сколько = Math.round(доля_проявления() * знаки.length);
      }
      if (сколько === зажжено) return;
      for (var i = 0; i < знаки.length; i++) знаки[i].classList.toggle('pf-on', i < сколько);
      зажжено = сколько;
    };
    зажечь();
    window.addEventListener('scroll', зажечь, { passive: true });
    window.addEventListener('resize', зажечь);
    if (тихо.addEventListener) тихо.addEventListener('change', зажечь);
  }
  var бока = Array.prototype.slice.call(document.querySelectorAll('.pf-side'));
  if (бока.length) {
    if (тихо.matches || !('IntersectionObserver' in window)) {
      бока.forEach(function (э) { э.classList.add('pf-in'); });
    } else {
      var наблюдатель_боков = new IntersectionObserver(function (записи) {
        записи.forEach(function (з) {
          if (з.isIntersecting) { з.target.classList.add('pf-in'); наблюдатель_боков.unobserve(з.target); }
        });
      }, { threshold: 0.2 });
      бока.forEach(function (э) { наблюдатель_боков.observe(э); });
    }
  }

  /* ИНСТРУМЕНТЫ (блок E)
     · Разметка несёт КОНЕЧНОЕ состояние. В начало (`pf-idle`) отводятся
       только интерфейсы, которых нет в окне при загрузке: отведи скрипт
       видимый — человек увидел бы готовое, потом пустое (§6.0.15).
     · Проигрыш ОДИН раз при доезде: печать знаков, счётчики, полоски,
       галочки. Конец отмечается `data-pf-state="done"`, и больше
       интерфейс не двигается.
     · «Уменьшить движение»: ничего не отводится, всё готово сразу. */
  var макеты = Array.prototype.slice.call(document.querySelectorAll('[data-pf-anim]'));
  if (макеты.length && !тихо.matches && 'IntersectionObserver' in window) {
    var в_окне = function (э) {
      var к = э.getBoundingClientRect();
      return к.bottom > 0 && к.top < window.innerHeight;
    };
    var счётчики = function (м) {
      return Array.prototype.slice.call(м.querySelectorAll('[data-count-to]'));
    };
    var проиграть = function (м) {
      if (м.getAttribute('data-pf-state') !== 'idle') return;
      м.setAttribute('data-pf-state', 'play');
      var знаки = м.querySelectorAll('.pf-t');
      var шаг_печати = 22;
      var i = 0;
      var печать = знаки.length ? setInterval(function () {
        if (i < знаки.length) знаки[i++].classList.remove('pf-t-off');
        if (i >= знаки.length) clearInterval(печать);
      }, шаг_печати) : null;
      var цели = счётчики(м);
      var начало = performance.now();
      var длительность = 900;
      var тик = function (сейчас) {
        var доля = Math.min(1, (сейчас - начало) / длительность);
        var плавно = 1 - Math.pow(1 - доля, 3);
        цели.forEach(function (э) {
          э.textContent = String(Math.round(Number(э.getAttribute('data-count-to')) * плавно));
        });
        if (доля < 1) requestAnimationFrame(тик);
      };
      requestAnimationFrame(function (сейчас) {
        начало = сейчас;
        м.classList.remove('pf-idle');
        тик(сейчас);
      });
      var галочек = м.querySelectorAll('.pf-chk').length;
      var конец = Math.max(знаки.length * шаг_печати, длительность, галочек * 220 + 400) + 200;
      setTimeout(function () { м.setAttribute('data-pf-state', 'done'); }, конец);
    };
    var наблюдатель_макетов = new IntersectionObserver(function (записи) {
      записи.forEach(function (з) {
        if (з.isIntersecting) { наблюдатель_макетов.unobserve(з.target); проиграть(з.target); }
      });
    }, { threshold: 0.35 });
    макеты.forEach(function (м) {
      if (в_окне(м)) { м.setAttribute('data-pf-state', 'done'); return; }
      м.classList.add('pf-idle');
      Array.prototype.forEach.call(м.querySelectorAll('.pf-t'), function (з) { з.classList.add('pf-t-off'); });
      счётчики(м).forEach(function (э) { э.textContent = '0'; });
      м.setAttribute('data-pf-state', 'idle');
      наблюдатель_макетов.observe(м);
    });
  } else {
    макеты.forEach(function (м) { м.setAttribute('data-pf-state', 'done'); });
  }

  /* ПРОЕКТЫ (блок F): карточка, на которую наезжает следующая, уменьшается
     до 0.94 — пропорционально тому, какую часть её закрыла следующая.
     Прилипание делает CSS; здесь только масштаб, и пишется он в событии
     прокрутки, как у ленты. «Уменьшить движение» — масштаба нет. */
  var карточки = Array.prototype.slice.call(document.querySelectorAll('.pf-proj'));
  if (карточки.length > 1) {
    var сжать = function () {
      for (var i = 0; i < карточки.length; i++) {
        var коробка = карточки[i].firstElementChild;
        if (тихо.matches || i === карточки.length - 1) {
          коробка.style.removeProperty('--pf-scale');
          continue;
        }
        var к = карточки[i].getBoundingClientRect();
        var след = карточки[i + 1].getBoundingClientRect();
        var доля = Math.min(1, Math.max(0, (к.bottom - след.top) / к.height));
        коробка.style.setProperty('--pf-scale', (1 - 0.06 * доля).toFixed(4));
      }
    };
    сжать();
    window.addEventListener('scroll', сжать, { passive: true });
    window.addEventListener('resize', сжать);
    if (тихо.addEventListener) тихо.addEventListener('change', сжать);
  }

  var лента = document.querySelector('.pf-feed');
  if (!лента) return;

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
