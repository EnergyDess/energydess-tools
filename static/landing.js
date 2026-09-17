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
  /* ПРОКРУТКА ИДЁТ / ЗАКОНЧИЛАСЬ (заход 343, блок 2). Одно состояние
     на всю страницу: магнит на время прокрутки замирает, кеши геометрии
     перемеряются после её конца. Конец — нет событий прокрутки
     `ТИШИНА_МС`; `scrollend` есть не везде, таймер есть везде. */
  var ТИШИНА_МС = 150;
  var прокрутка_идёт = false, таймер_тишины = 0;
  var после_прокрутки = [];
  window.addEventListener('scroll', function () {
    прокрутка_идёт = true;
    clearTimeout(таймер_тишины);
    таймер_тишины = setTimeout(function () {
      прокрутка_идёт = false;
      после_прокрутки.forEach(function (ф) { ф(); });
    }, ТИШИНА_МС);
  }, { passive: true });

  /* КЕШ ГЕОМЕТРИИ (блок 2). Обработчики прокрутки и указателя не читают
     `getBoundingClientRect`: чтение после записи стиля соседним
     обработчиком заставляло браузер пересчитать раскладку посреди кадра.
     Положения берутся в координатах ДОКУМЕНТА один раз и пересчитываются
     при смене размера окна, изменении высоты страницы (догрузка шрифта,
     картинки) и после конца прокрутки. */
  var сбросы = [];
  var сбросить_кеши = function () { сбросы.forEach(function (ф) { ф(); }); };
  window.addEventListener('resize', сбросить_кеши);
  после_прокрутки.push(сбросить_кеши);
  if (window.ResizeObserver) new ResizeObserver(сбросить_кеши).observe(document.body);
  var в_документе = function (э) {
    var к = э.getBoundingClientRect();
    return {top: к.top + window.scrollY, bottom: к.bottom + window.scrollY,
            left: к.left + window.scrollX, width: к.width, height: к.height};
  };

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
    /* УКАЗАТЕЛЬ — В КАДР, ГЕОМЕТРИЯ — ИЗ КЕША (блок 2). Событие только
       запоминает координаты; цель считается в `requestAnimationFrame`
       не чаще кадра. Центр — по коробке БЕЗ текущего сдвига (родитель
       магнита): иначе портрет убегал бы от курсора собственным смещением.
       Кеш сбрасывается ещё и по концу анимации появления: она двигает
       родителя на 20px. */
    var коробка = null, указано = null, расчёт = 0;
    сбросы.push(function () { коробка = null; });
    магнит.parentElement.addEventListener('animationend', function () { коробка = null; });
    var прицелиться = function () {
      расчёт = 0;
      if (!указано || прокрутка_идёт || !можно()) return;
      if (!коробка) коробка = в_документе(магнит.parentElement);
      var верх = коробка.top - window.scrollY, низ = коробка.bottom - window.scrollY;
      if (низ < 0 || верх > window.innerHeight) { тянуть(0, 0); return; }
      тянуть((указано.x - (коробка.left - window.scrollX + коробка.width / 2)) / КОЭФФИЦИЕНТ,
             (указано.y - (верх + коробка.height / 2)) / КОЭФФИЦИЕНТ);
    };
    window.addEventListener('pointermove', function (e) {
      if (!можно() || e.pointerType === 'touch') return;
      указано = {x: e.clientX, y: e.clientY};
      if (!расчёт && !прокрутка_идёт) расчёт = requestAnimationFrame(прицелиться);
    }, { passive: true });
    /* ЗАМИРАНИЕ НА ВРЕМЯ ПРОКРУТКИ (блок 2). Портрет стоит там, где был:
       новые цели не считаются, бег к цели остановлен. Через `ТИШИНА_МС`
       после последнего события прокрутки магнит оживает сам — цель
       пересчитывается от последнего положения указателя. */
    window.addEventListener('scroll', function () {
      if (кадр) { cancelAnimationFrame(кадр); кадр = 0; }
      if (расчёт) { cancelAnimationFrame(расчёт); расчёт = 0; }
    }, { passive: true });
    после_прокрутки.push(function () {
      if (указано) прицелиться();
      else if (цель.x !== сейчас.x || цель.y !== сейчас.y) тянуть(цель.x, цель.y);
    });
    document.documentElement.addEventListener('pointerleave', function () { тянуть(0, 0); });
    window.addEventListener('blur', function () { тянуть(0, 0); });
    var сбросить = function () { if (!можно()) { цель.x = цель.y = сейчас.x = сейчас.y = 0; записать(); } };
    if (тихо.addEventListener) тихо.addEventListener('change', сбросить);
    if (указатель.addEventListener) указатель.addEventListener('change', сбросить);
  }

  /* ФОН СТРАНИЦЫ (заход 342, блок B)
     · ВЕРХНИЙ получает `src` сразу, НИЖНИЙ — когда до слоя осталось
       полтора экрана (`rootMargin` 150%): при быстрой прокрутке вниз
       ролик успевает, а первый заход не качает его зря (B5).
     · ИГРАЕТ только слой в окне; ушёл из окна — пауза. Два ролика
       на весь экран разом декодировать незачем.
     · СКОРОСТЬ 0.5 (B7): движение читается дыханием, а не роликом.
       Ставится и до, и после загрузки: `play()` в части браузеров
       сбрасывает скорость на `defaultPlaybackRate`.
     · Ролик проявляется поверх кадра только на `playing` — до того
       виден кадр (B6), темноты между ними нет.
     · «Уменьшить движение» (B8): `src` не ставится вовсе — ролик не
       грузится и не играет, виден кадр. Включили настройку на ходу —
       ролик встаёт на паузу и уступает кадру. */
  var СКОРОСТЬ_ФОНА = 0.5;
  Array.prototype.slice.call(document.querySelectorAll('[data-pf-bg]')).forEach(function (слой) {
    var видео = слой.querySelector('.pf-bg-video');
    if (!видео) return;
    var верх = слой.getAttribute('data-pf-bg') === 'top';
    var видно = false;
    var скорость = function () { видео.defaultPlaybackRate = СКОРОСТЬ_ФОНА; видео.playbackRate = СКОРОСТЬ_ФОНА; };
    var загрузить = function () {
      if (тихо.matches || видео.getAttribute('src')) return;
      видео.preload = 'auto';
      скорость();
      видео.setAttribute('src', видео.getAttribute('data-src'));
    };
    var играть = function () {
      if (тихо.matches) return;
      загрузить();
      скорость();
      var о = видео.play();
      if (о && о.catch) о.catch(function () {});
    };
    видео.addEventListener('loadedmetadata', скорость);
    видео.addEventListener('playing', function () { скорость(); видео.classList.add('pf-on'); });
    if (!('IntersectionObserver' in window)) { играть(); return; }
    if (верх) загрузить();
    else {
      var загрузчик = new IntersectionObserver(function (зз) {
        if (зз.some(function (з) { return з.isIntersecting; })) { загрузить(); загрузчик.disconnect(); }
      }, { rootMargin: '150% 0px 150% 0px' });
      загрузчик.observe(слой);
    }
    new IntersectionObserver(function (зз) {
      зз.forEach(function (з) {
        видно = з.isIntersecting;
        if (видно) играть(); else if (видео.getAttribute('src')) видео.pause();
      });
    }).observe(слой);
    if (тихо.addEventListener) тихо.addEventListener('change', function () {
      if (тихо.matches) { if (видео.getAttribute('src')) видео.pause(); видео.classList.remove('pf-on'); }
      else if (видно) играть();
    });
  });

  /* О СЕБЕ (блок D)
     · Знаки абзаца зажигаются от прокрутки (границы — ниже, у
       `доля_проявления`). Функция положения, а не времени: откатил
       прокрутку — знаки гаснут обратно.
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
    /* ГЕОМЕТРИЯ ИЗ КЕША (заход 343, блок 2). Текст и секция стоят в потоке,
       поэтому их положение в окне — положение в документе минус прокрутка:
       читать коробки на каждом событии прокрутки не нужно. */
    var места_о_себе = null;
    сбросы.push(function () { места_о_себе = null; });
    var доля_проявления = function () {
      var vh = window.innerHeight;
      if (!места_о_себе) места_о_себе = {т: в_документе(абзац), с: в_документе(секция_о_себе)};
      var т = {top: места_о_себе.т.top - window.scrollY, bottom: места_о_себе.т.bottom - window.scrollY,
               height: места_о_себе.т.height};
      var пройдено = vh - т.top;                                  // 0 — верх текста у низа окна
      var осталось = Math.min(места_о_себе.с.bottom - window.scrollY - vh,
                              т.bottom - 0.75 * vh);
      var путь = пройдено + осталось;
      return путь > 0 ? Math.min(1, Math.max(0, пройдено / путь)) : 1;
    };
    /* Переключаются только знаки МЕЖДУ прежней и новой границей: проход
       по всему абзацу на каждом кадре трогал бы сотни узлов ради десятка. */
    var зажечь = function () {
      var сколько = знаки.length;
      if (!тихо.matches) {
        сколько = Math.round(доля_проявления() * знаки.length);
      }
      if (сколько === зажжено) return;
      var от = зажжено < 0 ? 0 : Math.min(зажжено, сколько);
      var до = зажжено < 0 ? знаки.length : Math.max(зажжено, сколько);
      for (var i = от; i < до; i++) знаки[i].classList.toggle('pf-on', i < сколько);
      зажжено = сколько;
    };
    зажечь();
    var кадр_о_себе = 0;
    var зажечь_в_кадре = function () {
      if (!кадр_о_себе) кадр_о_себе = requestAnimationFrame(function () { кадр_о_себе = 0; зажечь(); });
    };
    window.addEventListener('scroll', зажечь_в_кадре, { passive: true });
    window.addEventListener('resize', зажечь_в_кадре);
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

  /* ИНСТРУМЕНТЫ (блок E; заход 339, блоки D2–D5)
     · Разметка несёт КОНЕЧНОЕ состояние. В начало (`pf-idle`) отводятся
       только интерфейсы, которых нет в окне: отведи скрипт видимый —
       человек увидел бы готовое, потом пустое (§6.0.15).
     · ОДИН проход за въезд: печать знаков, счётчики, полоски, галочки,
       шаги по очереди (`data-pf-step`) и счёт собранного (`data-pf-tally`).
       Конец отмечается `data-pf-state="done"`, и пока блок в окне, он стоит.
     · ПОВТОР ПРИ ВОЗВРАТЕ (D3). Здесь стояло «один раз за загрузку»: блок
       отыгрывал и больше не двигался никогда. Теперь блок, ЦЕЛИКОМ ушедший
       из окна, возвращается в начало — невидимо, его не видно — и при
       следующем въезде сверху или снизу играет снова. Это не цикл: в окне
       он проигрывает один раз и стоит.
     · Запуск по мере въезда (D5): играют только те, что доехали; таймеры
       и кадры у ушедшего снимаются вместе с возвратом в начало.
     · «Уменьшить движение»: ничего не отводится, всё готово сразу. */
  var макеты = Array.prototype.slice.call(document.querySelectorAll('[data-pf-anim]'));
  if (макеты.length && !тихо.matches && 'IntersectionObserver' in window) {
    var ШАГ_МС = 450;          // шаги подходов и предметов идут через столько
    var СЧЁТ_МС = 900;         // счётчики без шага
    var СЧЁТ_ШАГА_МС = 600;    // счётчик внутри шага
    var в_окне = function (э) {
      var к = э.getBoundingClientRect();
      return к.bottom > 0 && к.top < window.innerHeight;
    };
    var все = function (м, сел) { return Array.prototype.slice.call(м.querySelectorAll(сел)); };
    var от = function (э) { return Number(э.getAttribute('data-count-from')) || 0; };
    var посчитать = function (м, э, длительность, поколение) {
      var цель = Number(э.getAttribute('data-count-to'));
      var с = от(э);
      var начало = null;
      var тик = function (сейчас) {
        if (м.__поколение !== поколение) return;
        if (начало === null) начало = сейчас;
        var доля = Math.min(1, (сейчас - начало) / длительность);
        э.textContent = String(Math.round(с + (цель - с) * (1 - Math.pow(1 - доля, 3))));
        if (доля < 1) requestAnimationFrame(тик);
      };
      requestAnimationFrame(тик);
    };
    var счёт_собранного = function (м) {
      var готовых = все(м, '[data-pf-step]').filter(function (ш) { return !ш.classList.contains('pf-wait'); }).length;
      все(м, '[data-pf-tally]').forEach(function (э) { э.textContent = String(от(э) + готовых); });
    };
    var в_начало = function (м) {
      м.__поколение = (м.__поколение || 0) + 1;
      (м.__таймеры || []).forEach(clearTimeout);
      м.__таймеры = [];
      if (м.__печать) { clearInterval(м.__печать); м.__печать = null; }
      // ВОЗВРАТ МГНОВЕННЫЙ: без переходов полоски и галочки ехали бы назад
      // 400–900 мс, и быстрый возврат в окно застал бы их на полпути.
      м.classList.add('pf-snap');
      м.classList.add('pf-idle');
      все(м, '.pf-t').forEach(function (з) { з.classList.add('pf-t-off'); });
      все(м, '[data-count-to]').forEach(function (э) { э.textContent = String(от(э)); });
      все(м, '[data-pf-step]').forEach(function (ш) { ш.classList.add('pf-wait'); });
      счёт_собранного(м);
      м.setAttribute('data-pf-state', 'idle');
      void м.offsetWidth;   // применить начало без переходов
      м.classList.remove('pf-snap');
    };
    var проиграть = function (м) {
      if (м.getAttribute('data-pf-state') !== 'idle') return;
      м.setAttribute('data-pf-state', 'play');
      м.__прогонов = (м.__прогонов || 0) + 1;
      var поколение = м.__поколение;
      var знаки = м.querySelectorAll('.pf-t');
      var шаг_печати = 22;
      var i = 0;
      if (знаки.length) {
        м.__печать = setInterval(function () {
          if (i < знаки.length) знаки[i++].classList.remove('pf-t-off');
          if (i >= знаки.length) { clearInterval(м.__печать); м.__печать = null; }
        }, шаг_печати);
      }
      requestAnimationFrame(function () {
        if (м.__поколение !== поколение) return;
        м.classList.remove('pf-idle');
      });
      все(м, '[data-count-to]').forEach(function (э) {
        if (!э.closest('[data-pf-step]')) посчитать(м, э, СЧЁТ_МС, поколение);
      });
      var шаги = все(м, '[data-pf-step]');
      var последний = 0;
      шаги.forEach(function (ш) {
        var н = Number(ш.getAttribute('data-pf-step')) || 1;
        последний = Math.max(последний, н);
        м.__таймеры.push(setTimeout(function () {
          ш.classList.remove('pf-wait');
          все(ш, '[data-count-to]').forEach(function (э) { посчитать(м, э, СЧЁТ_ШАГА_МС, поколение); });
          счёт_собранного(м);
        }, н * ШАГ_МС));
      });
      var галочек = м.querySelectorAll('.pf-chk').length;
      var конец = Math.max(знаки.length * шаг_печати, СЧЁТ_МС, галочек * 220 + 400,
                           последний ? последний * ШАГ_МС + СЧЁТ_ШАГА_МС + 400 : 0) + 200;
      м.__таймеры.push(setTimeout(function () { м.setAttribute('data-pf-state', 'done'); }, конец));
    };
    var наблюдатель_макетов = new IntersectionObserver(function (записи) {
      записи.forEach(function (з) {
        var м = з.target;
        if (з.isIntersecting && з.intersectionRatio >= 0.35) {
          проиграть(м);
        } else if (!з.isIntersecting && м.getAttribute('data-pf-state') !== 'idle') {
          в_начало(м);   // ушёл из окна целиком: при возврате сыграет снова
        }
      });
    }, { threshold: [0, 0.35] });
    макеты.forEach(function (м) {
      м.__таймеры = [];
      if (в_окне(м)) м.setAttribute('data-pf-state', 'done');
      else в_начало(м);
      наблюдатель_макетов.observe(м);
    });
  } else {
    макеты.forEach(function (м) { м.setAttribute('data-pf-state', 'done'); });
  }

  /* СВЯЗАТЬСЯ (заход 339, блок F)
     · Здесь стояла ссылка `mailto:`. Она открывает почтовую программу,
       а где программа не настроена — не происходит НИЧЕГО: чужой компьютер,
       рабочий ноутбук, телефон без почтового клиента. Тупик без признака.
     · Теперь кнопка — `<details>`: раскрывается и без скрипта, до неё
       доходит Tab, адрес виден текстом и выделяется руками. Скрипт только
       добавляет копирование и закрытие по Escape и по нажатию мимо.
     · Копирование — `navigator.clipboard`. Нет его либо браузер отказал —
       отказ говорится СЛОВАМИ, а адрес выделяется, чтобы скопировать его
       обычным способом: молчаливого отказа нет (F5).
     · Раскрыт одновременно один блок: открытие второго закрывает первый. */
  var связи = Array.prototype.slice.call(document.querySelectorAll('[data-pf-contact]'));
  связи.forEach(function (блок) {
    var адрес = блок.querySelector('[data-pf-contact-addr]');
    var кнопка = блок.querySelector('[data-pf-contact-copy]');
    var итог = блок.querySelector('[data-pf-contact-status]');
    var таймер = 0;
    var сказать = function (текст, отказ) {
      итог.textContent = текст;
      // успех — галочкой на месте значка (D5), строка остаётся программе
      // чтения; отказ — словами на виду (D7)
      итог.classList.toggle('pf-contact-ok', !!текст && !отказ);
      if (!кнопка) return;
      clearTimeout(таймер);
      кнопка.classList.toggle('pf-done', !!текст && !отказ);
      if (текст && !отказ) таймер = setTimeout(function () { кнопка.classList.remove('pf-done'); }, 1600);
    };
    // Уголок облачка смотрит на центр кнопки (D3): кнопка стоит то у правого
    // края карточки, то под её серединой, и одним числом в стилях это
    // не выражается.
    var карточка = блок.querySelector('.pf-contact-pop');
    var навести = function () {
      var к = блок.querySelector('summary').getBoundingClientRect();
      var п = карточка.getBoundingClientRect();
      if (!п.width) return;
      var x = Math.min(п.width - 20, Math.max(20, к.left + к.width / 2 - п.left));
      карточка.style.setProperty('--pf-tail-x', x.toFixed(1) + 'px');
    };
    var выделить = function () {
      var д = document.createRange();
      д.selectNodeContents(адрес);
      var в = window.getSelection();
      в.removeAllRanges();
      в.addRange(д);
    };
    var не_вышло = function () {
      выделить();
      сказать('Скопировать не удалось — адрес выделен, скопируйте его вручную.', true);
    };
    if (кнопка) {
      кнопка.hidden = false;   // без скрипта кнопки копирования нет вовсе
      кнопка.addEventListener('click', function () {
        var текст = адрес.textContent.trim();
        if (!navigator.clipboard || !navigator.clipboard.writeText) { не_вышло(); return; }
        navigator.clipboard.writeText(текст).then(function () {
          сказать('Скопировано: ' + текст, false);
        }, не_вышло);
      });
    }
    блок.addEventListener('toggle', function () {
      if (!блок.open) { сказать('', false); return; }
      навести();
      связи.forEach(function (другой) { if (другой !== блок) другой.open = false; });
    });
  });
  if (связи.length) {
    document.addEventListener('keydown', function (e) {
      if (e.key !== 'Escape') return;
      связи.forEach(function (блок) {
        if (блок.open) { блок.open = false; блок.querySelector('summary').focus(); }
      });
    });
    document.addEventListener('click', function (e) {
      связи.forEach(function (блок) { if (блок.open && !блок.contains(e.target)) блок.open = false; });
    });
  }

  /* ПРОЕКТЫ (блок F): карточка, на которую наезжает следующая, уменьшается
     до 0.94 — пропорционально тому, какую часть её закрыла следующая.
     Прилипание делает CSS; здесь только масштаб, и пишется он в событии
     прокрутки, как у ленты. «Уменьшить движение» — масштаба нет. */
  var карточки = Array.prototype.slice.call(document.querySelectorAll('.pf-proj'));
  if (карточки.length > 1) {
    /* ЗАХОД 343, БЛОК 2. Карточки прилипают, и их коробки в окне из кеша
       не выводятся — читаются живьём. Но (1) все чтения идут ДО всех
       записей: прежний цикл читал коробку после записи масштаба соседней
       карточки, и раскладка пересчитывалась посреди кадра; (2) пока стопка
       вне окна (положение секции — из кеша), не читается ничего. */
    var стопка = карточки[0].parentElement;
    var место_стопки = null;
    сбросы.push(function () { место_стопки = null; });
    var сжать = function () {
      if (!место_стопки) место_стопки = в_документе(стопка);
      var верх = место_стопки.top - window.scrollY;
      var видна = верх < window.innerHeight && верх + место_стопки.height > 0;
      if (!видна && !тихо.matches) return;
      var доли = [];
      for (var i = 0; i < карточки.length - 1; i++) {
        var к = карточки[i].getBoundingClientRect();
        var след = карточки[i + 1].getBoundingClientRect();
        доли.push(Math.min(1, Math.max(0, (к.bottom - след.top) / к.height)));
      }
      for (var j = 0; j < карточки.length; j++) {
        var коробка = карточки[j].firstElementChild;
        if (тихо.matches || j === карточки.length - 1) коробка.style.removeProperty('--pf-scale');
        else коробка.style.setProperty('--pf-scale', (1 - 0.06 * доли[j]).toFixed(4));
      }
    };
    сжать();
    var кадр_стопки = 0;
    var сжать_в_кадре = function () {
      if (!кадр_стопки) кадр_стопки = requestAnimationFrame(function () { кадр_стопки = 0; сжать(); });
    };
    window.addEventListener('scroll', сжать_в_кадре, { passive: true });
    window.addEventListener('resize', сжать_в_кадре);
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

  /* ПОЛОЖЕНИЕ ЛЕНТЫ ИЗ КЕША (заход 343, блок 2). Лента стоит в потоке:
     её верх в окне — верх в документе минус прокрутка. Прежде обработчик
     читал коробку и `offsetHeight` на каждом событии прокрутки — после
     записей стиля соседних обработчиков это пересчёт раскладки посреди
     кадра. */
  var место_ленты = null;
  // Ширина набора сюда НЕ входит: она мерится, как и прежде, при загрузке
  // и смене размера окна. Перемер после прокрутки ловил появление полосы
  // прокрутки (2560: набор +3.2 px) и сдвигал стоящую ленту.
  сбросы.push(function () { место_ленты = null; });

  function сдвинуть() {
    if (!набор) мерить();
    if (!место_ленты) место_ленты = в_документе(лента);
    var доля = 0.5;
    if (!тихо.matches) {
      var верх = место_ленты.top - window.scrollY;
      var ход = window.innerHeight + место_ленты.height;
      доля = Math.min(1, Math.max(0, (window.innerHeight - верх) / ход));
    }
    // СКОРОСТЬ — ДОЛЯ ОТ ПРОКРУТКИ, а не от ширины набора: первая версия
    // брала треть набора, и на 2560 ряд проезжал 1179 px за 1140 px
    // прокрутки, шагом до 66 px за кадр (замер пробы). Правило проекта —
    // лёгкий параллакс, 20–30% скорости прокрутки: 0.3. Треть набора
    // остаётся потолком, чтобы край дорожки не показался никогда.
    var размах = Math.min(набор / 3, 0.3 * (window.innerHeight + место_ленты.height) / 2);
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

  /* РОЛИКИ ПО ОДНОМУ (заход 343, блок 2). Прежде ряд, доехавший до окна,
     ставил `src` с `preload = auto` и `play()` ВСЕМ 36 роликам разом —
     включая два повтора набора за краем окна. Теперь:
     · ряд доехал — роликам ставится `src` с `preload = metadata`: первый
       кадр есть, поток не качается. У ролика с `poster` (письмо 3а задачи
       343) первый кадр уже нарисован картинкой — `preload = none`, и ролик
       за краем окна не качает даже метаданные;
     · ИГРАЕТ ролик, который сейчас в окне (свой наблюдатель на каждый;
       ролик за краем ряда обрезан `overflow` ленты и в окно не входит);
       ушёл из окна — пауза;
     · «уменьшить движение» — как прежде: первый кадр (`preload = auto`),
       без `play()`. */
  function подготовить() {
    ролики().forEach(function (в) {
      var адрес = в.getAttribute('data-src');
      if (адрес && !в.getAttribute('src')) {
        в.preload = тихо.matches ? 'auto' : (в.hasAttribute('poster') ? 'none' : 'metadata');
        в.setAttribute('src', адрес);
      }
    });
  }

  function решить(в, видим) {
    if (!в.getAttribute('src')) return;
    if (видим && !тихо.matches) {
      в.preload = 'auto';
      var обещание = в.play();
      if (обещание && обещание.catch) обещание.catch(function () {});
    } else {
      в.pause();
    }
  }

  var в_окне_ролики = new Set();
  function запустить() {
    подготовить();
    ролики().forEach(function (в) { решить(в, в_окне_ролики.has(в)); });
  }

  if ('IntersectionObserver' in window) {
    var видно = new Set();
    var наблюдатель = new IntersectionObserver(function (записи) {
      записи.forEach(function (з) {
        if (з.isIntersecting) видно.add(з.target); else видно.delete(з.target);
      });
      if (видно.size && !доехала) { доехала = true; запустить(); }
    }, { rootMargin: '0px 0px -1px 0px' });
    ряды.forEach(function (ряд) { наблюдатель.observe(ряд); });
    var наблюдатель_роликов = new IntersectionObserver(function (записи) {
      записи.forEach(function (з) {
        if (з.isIntersecting) в_окне_ролики.add(з.target); else в_окне_ролики.delete(з.target);
        if (доехала) решить(з.target, з.isIntersecting);
      });
    }, { rootMargin: '0px 0px -1px 0px' });
    ролики().forEach(function (в) { наблюдатель_роликов.observe(в); });
  } else {
    доехала = true;
    ролики().forEach(function (в) { в_окне_ролики.add(в); });
    запустить();
  }

  мерить();
  сдвинуть();
  window.addEventListener('scroll', сдвинуть, { passive: true });
  window.addEventListener('resize', function () { мерить(); сдвинуть(); });
  var смена = function () { сдвинуть(); if (доехала) запустить(); };
  if (тихо.addEventListener) тихо.addEventListener('change', смена);
})();
