/* Примитивы анимаций залогиненной части — window.Motion (письмо M1,
   BACKLOG №384). Правила — .claude/skills/energydess-motion/SKILL.md.

   Без библиотек, на Web Animations API. Подключается ТОЛЬКО в каркасе
   залогиненной части (templates/_page_end.html, то же условие, что
   у v2-shell.js); лендинг этот файл не грузит.

   Три свойства, на которых держится всё остальное:
   - ВИДНО В ПОКОЕ. Состояние «до» появления задаёт сама анимация
     (`fill: 'backwards'`) и только на время своей задержки; в CSS
     невидимого покоя нет. Не загрузился файл — всё видно.
   - ЧИСЛА ИЗ ТОКЕНОВ. Длительности, кривые и сдвиги читаются
     из `:root` (`static/motion.css`), второго источника чисел нет.
   - МЕНЬШЕ ДВИЖЕНИЯ. При `prefers-reduced-motion: reduce` остаётся только
     проявление opacity не дольше 120 мс, без сдвигов и волны.
   Все функции молча ничего не делают, если элемента нет. */
(function () {
  'use strict';
  if (window.Motion) return;

  const КОРЕНЬ = document.documentElement;
  const МАЛО = 120;                       // потолок движения при reduced-motion
  const запрос = window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)') : null;

  function reduced() { return !!(запрос && запрос.matches); }

  // Токен из :root: «160ms» → 160, «14px» → 14, «.95» → 0.95, кривая — строкой
  function т(имя) { return getComputedStyle(КОРЕНЬ).getPropertyValue('--m-' + имя).trim(); }
  function мс(имя) { const v = parseFloat(т(имя)); return isNaN(v) ? 0 : v; }

  function характер(ch) {
    const c = ch === 'soft' || ch === 'cine' ? ch : 'live';
    return {
      имя: c,
      fast: мс(c + '-fast'), base: мс(c + '-base'), slow: мс(c + '-slow'),
      ease: т(c + '-ease') || 'ease-out',
      stagger: мс(c + '-stagger'),
      shift: мс(c + '-shift'),
      scale: parseFloat(т(c + '-scale')) || 1,
      blur: c === 'live' ? 0 : мс(c + '-blur'),
      pop: т('live-pop'),
      exit: т('exit-ease') || 'ease-in',
    };
  }

  function список(els) {
    if (!els) return [];
    if (els instanceof Element) return [els];
    return Array.prototype.filter.call(els, function (e) { return e instanceof Element; });
  }
  function виден(el) {
    return !!(el && el.getClientRects().length) && getComputedStyle(el).visibility !== 'hidden';
  }
  function конец(анимации) {
    return Promise.all(анимации.map(function (a) { return a.finished.catch(function () {}); }));
  }

  /* enter(els, ch, {pop}) — волна появления. Пружинка (`pop: true`) —
     только объектам: карточка, плашка, тост. Строки и текст — без неё. */
  function enter(els, ch, опц) {
    const все = список(els).filter(виден);
    if (!все.length) return Promise.resolve();
    опц = опц || {};
    if (reduced()) {
      return конец(все.map(function (el) {
        return el.animate([{ opacity: 0 }, { opacity: 1 }], { duration: МАЛО, easing: 'linear', fill: 'backwards' });
      }));
    }
    const х = характер(ch);
    const пружинка = опц.pop && х.имя === 'live';
    return конец(все.map(function (el, i) {
      const из = { opacity: 0, transform: 'translateY(' + х.shift + 'px) scale(' + х.scale + ')' };
      const в = { opacity: 1, transform: 'none' };
      if (х.blur) { из.filter = 'blur(' + х.blur + 'px)'; в.filter = 'blur(0px)'; }
      return el.animate([из, в], {
        duration: х.имя === 'cine' ? х.slow : х.base,
        easing: пружинка ? х.pop : х.ease,
        delay: i * х.stagger,
        fill: 'backwards',
      });
    }));
  }

  // Уход на месте: прозрачность и лёгкий сдвиг вверх, длительность fast
  function уход(els, х, копилка) {
    return конец(список(els).filter(виден).map(function (el) {
      const а = el.animate([{ opacity: 1, transform: 'none' },
                         { opacity: 0, transform: 'translateY(' + (-х.shift / 2) + 'px)' }],
                        { duration: х.fast, easing: х.exit, fill: 'forwards' });
      if (копилка) копилка.push(а);
      return а;
    }));
  }
  /* leave(el, ch, {keep}) — уход, затем схлопывание места без скачка:
     высота, поля и нижняя рамка едут к нулю (единственное законное
     исключение из «только transform/opacity/filter» — схлопывание блока).
     Элемент удаляется, если не передан `keep`. */
  function leave(el, ch, опц) {
    if (!el || !el.isConnected) return Promise.resolve();
    опц = опц || {};
    const убрать = function () { if (!опц.keep) el.remove(); else el.hidden = true; };
    if (reduced()) {
      return el.animate([{ opacity: 1 }, { opacity: 0 }], { duration: МАЛО, fill: 'forwards' })
        .finished.catch(function () {}).then(убрать);
    }
    const х = характер(ch);
    return уход([el], х).then(function () {
      const с = getComputedStyle(el);
      const из = { height: el.offsetHeight + 'px', paddingTop: с.paddingTop, paddingBottom: с.paddingBottom,
                   marginTop: с.marginTop, marginBottom: с.marginBottom, borderBottomWidth: с.borderBottomWidth };
      const в = { height: '0px', paddingTop: '0px', paddingBottom: '0px', marginTop: '0px', marginBottom: '0px', borderBottomWidth: '0px' };
      el.style.overflow = 'hidden';
      // кривая схлопывания плавная в начале, длительность растёт с высотой:
      // за кадр место уходит не больше чем на ~24 px (письмо M1b)
      const длит = Math.max(х.base, Math.round(el.offsetHeight / 24 * 16.7 * 2.4));
      return el.animate([из, в], { duration: длит, easing: т('collapse-ease') || х.ease, fill: 'forwards' }).finished.catch(function () {});
    }).then(убрать);
  }

  /* swap(container, change, ch, {items}) — замена содержимого без скачка
     высоты. `change` — строка HTML (заменит содержимое) либо функция
     `change(корень)`, которая меняет DOM ВНУТРИ переданного корня
     (например, переключает `hidden` у панелей). `items` — селектор пунктов
     волны внутри контейнера (по умолчанию — дети).

     Порядок: целевая высота меряется заранее на невидимом клоне (той же
     ширины) → высота контейнера едет от старой к новой ОДНОВРЕМЕННО
     с уходом старого → вставка → новое появляется волной → явная высота
     снимается. Контейнер не схлопывается в 0 ни в один кадр, а всё
     движение раскладки укладывается в base своего характера. */
  function swap(container, change, ch, опц) {
    if (!container) return Promise.resolve();
    опц = опц || {};
    const применить = function (корень) {
      if (typeof change === 'function') change(корень); else корень.innerHTML = change;
    };
    const пункты = function () {
      return опц.items ? container.querySelectorAll(опц.items) : container.children;
    };
    if (reduced()) { применить(container); return enter(пункты(), ch); }
    const х = характер(ch || 'soft');
    const h0 = container.getBoundingClientRect().height;
    // Мерка: клон той же ширины, невидимый, вне потока; в нём — новое состояние
    const мерка = container.cloneNode(true);
    мерка.removeAttribute('id');
    мерка.setAttribute('aria-hidden', 'true');
    мерка.style.cssText += ';position:absolute;visibility:hidden;pointer-events:none;left:0;top:0;height:auto;width:' +
      container.getBoundingClientRect().width + 'px';
    container.after(мерка);
    применить(мерка);
    const h1 = мерка.getBoundingClientRect().height;
    мерка.remove();
    // ФИКСАЦИЯ ВЫСОТЫ: без неё смена содержимого дала бы скачок
    container.style.height = h1 + 'px';
    container.style.overflow = 'clip';
    const рост = container.animate([{ height: h0 + 'px' }, { height: h1 + 'px' }],
                                   { duration: х.base, easing: х.ease });
    const снять = function () { container.style.height = ''; container.style.overflow = ''; };
    const ушедшие = [];
    return уход(пункты(), х, ушедшие).then(function () {
      применить(container);
      // Заливка ухода держит старые пункты прозрачными; те, что остались
      // в DOM (панель снова покажут), обязаны вернуться видимыми.
      ушедшие.forEach(function (а) { а.cancel(); });
      return Promise.all([рост.finished.catch(function () {}), enter(пункты(), х.имя)]);
    }).then(снять, function (e) { снять(); throw e; });
  }

  /* seg(container, btn) — плашка `.m-seg-pill` едет под выбранную кнопку.
     Конечное положение ставится сразу, а движение — FLIP-ом через transform,
     так что раскладка не пересчитывается на каждом кадре. */
  function seg(container, btn) {
    if (!container || !btn) return;
    let плашка = container.querySelector(':scope > .m-seg-pill');
    if (!плашка) {
      плашка = document.createElement('span');
      плашка.className = 'm-seg-pill';
      плашка.setAttribute('aria-hidden', 'true');
      container.prepend(плашка);
    }
    const было = плашка.dataset.x ? { x: +плашка.dataset.x, w: +плашка.dataset.w } : null;
    const x = btn.offsetLeft, w = btn.offsetWidth;
    плашка.style.top = btn.offsetTop + 'px';
    плашка.style.height = btn.offsetHeight + 'px';
    плашка.style.width = w + 'px';
    плашка.style.transition = 'none';
    плашка.style.transform = 'translateX(' + x + 'px)';
    плашка.dataset.x = x; плашка.dataset.w = w;
    container.classList.add('m-seg-ready');
    if (!было || reduced() || (было.x === x && было.w === w)) return;
    const х = характер('soft');
    плашка.animate([{ transform: 'translateX(' + было.x + 'px) scaleX(' + (было.w / w) + ')' },
                    { transform: 'translateX(' + x + 'px) scaleX(1)' }],
                   { duration: х.base, easing: х.ease });
  }

  /* countUp(el, to, decimals, from) — Мягкий счётчик, easeOutCubic, без перелёта:
     значение ограничено итогом, последний кадр ставит итог точно. */
  function countUp(el, to, decimals, from) {
    if (!el) return Promise.resolve();
    const знаков = decimals || 0;
    const итог = Number(to) || 0;
    // `from` — с какого числа считать (обновление на месте: 3 → 4, а не 0 → 4)
    const нач = Math.min(итог, Number(from) || 0);
    const показать = function (v) {
      el.textContent = v.toLocaleString('ru-RU', { minimumFractionDigits: знаков, maximumFractionDigits: знаков });
    };
    if (reduced()) { показать(итог); return Promise.resolve(); }
    const длит = мс('soft-count') || 950;
    const старт = performance.now();
    return new Promise(function (готово) {
      function кадр(сейчас) {
        const p = Math.min(1, (сейчас - старт) / длит);
        const e = 1 - Math.pow(1 - p, 3);
        if (p < 1) { показать(Math.min(итог, нач + (итог - нач) * e)); requestAnimationFrame(кадр); }
        else { показать(итог); готово(); }
      }
      requestAnimationFrame(кадр);
    });
  }

  /* toast(text) — выезжает снизу с пружинкой, уходит быстро. */
  function toast(text, держать) {
    if (!text) return;
    let хост = document.querySelector('.m-toast-host');
    if (!хост) {
      хост = document.createElement('div');
      хост.className = 'm-toast-host';
      хост.setAttribute('role', 'status');
      хост.setAttribute('aria-live', 'polite');
      document.body.appendChild(хост);
    }
    const т_ = document.createElement('div');
    т_.className = 'm-toast';
    т_.textContent = text;
    хост.appendChild(т_);
    const х = характер('live');
    if (reduced()) т_.animate([{ opacity: 0 }, { opacity: 1 }], { duration: МАЛО });
    else т_.animate([{ opacity: 0, transform: 'translateY(' + (х.shift * 2) + 'px) scale(' + х.scale + ')' },
                     { opacity: 1, transform: 'none' }], { duration: х.base, easing: х.pop });
    setTimeout(function () {
      const ушёл = reduced()
        ? т_.animate([{ opacity: 1 }, { opacity: 0 }], { duration: МАЛО, fill: 'forwards' })
        : т_.animate([{ opacity: 1, transform: 'none' }, { opacity: 0, transform: 'translateY(' + х.shift + 'px)' }],
                     { duration: х.fast, easing: х.exit, fill: 'forwards' });
      ушёл.finished.catch(function () {}).then(function () { т_.remove(); });
    }, держать || 2600);
  }

  /* buildStep(stepEl) — «Кино»: этап зажигается со свечением.
     buildDone(resultEl) — результат проявляется из blur, по нему блик. */
  function buildStep(stepEl) {
    if (!stepEl) return Promise.resolve();
    if (reduced()) return enter([stepEl], 'soft');
    const х = характер('cine');
    stepEl.classList.remove('m-glow'); void stepEl.offsetWidth; stepEl.classList.add('m-glow');
    return stepEl.animate([{ opacity: .35, filter: 'blur(' + (х.blur / 4) + 'px)' }, { opacity: 1, filter: 'blur(0px)' }],
                          { duration: мс('cine-step') || х.base, easing: х.ease, fill: 'backwards' }).finished.catch(function () {});
  }
  function buildDone(resultEl) {
    if (!resultEl) return Promise.resolve();
    if (reduced()) return enter([resultEl], 'soft');
    const х = характер('cine');
    return resultEl.animate([{ opacity: 0, filter: 'blur(' + х.blur + 'px)', transform: 'translateY(' + х.shift + 'px)' },
                             { opacity: 1, filter: 'blur(0px)', transform: 'none' }],
                            { duration: х.slow, easing: х.ease, fill: 'backwards' }).finished.catch(function () {})
      .then(function () {
        resultEl.classList.remove('m-sheen'); void resultEl.offsetWidth; resultEl.classList.add('m-sheen');
      });
  }

  window.Motion = { reduced: reduced, enter: enter, leave: leave, swap: swap, seg: seg,
                    countUp: countUp, toast: toast, buildStep: buildStep, buildDone: buildDone };
})();
