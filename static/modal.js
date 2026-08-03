// ── modal.js — поведение модальных окон (design-system.md, раздел 2.5) ───────
//
// Каркас — в templates/_modal.html, оформление — в style.css, поведение здесь.
// Страница не подключает ни onclick, ни свой обработчик клавиш: разметке
// достаточно `.modal-ov` с id и `[data-modal-close]` на кнопке закрытия.
//
// Что закрывает этот файл (замерено на дневнике питания до его появления):
//   • Escape не работал ни в одной из двенадцати модалок — обработчика
//     не существовало вовсе;
//   • фокус после закрытия оставался на невидимом поле ВНУТРИ закрытой
//     модалки: она не display:none, а opacity:0, и элемент остаётся живым;
//   • 73 фокусируемых элемента из 142 на странице лежали в закрытых
//     модалках и всегда были в порядке табуляции — четырнадцать нажатий
//     Tab с начала страницы попадали в них все четырнадцать;
//   • фон прокручивался под открытой модалкой и оставался на новом месте
//     после закрытия (390px: 292 → 1000).
//
// Публичный API — те же два имени, что были: openModal(id) / closeModal(id).

(function () {
  'use strict';

  // Порядок открытия. Модалка над модалкой в дневнике — норма (поиск
  // ингредиента → порция, штрих-код → добавить вручную), поэтому Escape
  // обязан закрывать верхнюю, а не первую попавшуюся.
  var стек = [];
  // id → элемент, с которого модалку открыли. Сюда возвращается фокус.
  var фокус_до = {};

  function лист(м) { return м.querySelector('.modal-sh'); }

  // Блокировка прокрутки фона. Классом на <html>, тем же приёмом, что уже
  // применён для вкладки ассистента (html.assistant-mode) — не position:fixed
  // на body: тот сбрасывает scrollY, и страница прыгает при закрытии, а
  // в дневнике вдобавок поехала бы sticky-панель внизу.
  // Ширину скроллбара компенсировать не нужно: scrollbar-gutter: stable
  // в style.css резервирует место всегда, поэтому исчезновение полосы
  // не сдвигает вёрстку.
  function блокировать(нужно) {
    document.documentElement.classList.toggle('modal-open', !!нужно);
  }

  window.openModal = function (id) {
    var м = document.getElementById(id);
    if (!м || м.classList.contains('open')) return;

    фокус_до[id] = document.activeElement;
    // inert снимаем ДО показа: пока он висит, фокус внутрь не поставить
    м.removeAttribute('inert');
    м.classList.add('open');
    стек.push(id);
    блокировать(true);

    // Фокус — на сам лист, а не на первую кнопку: программа чтения с экрана
    // объявляет диалог с начала, а не с «Закрыть». Страницы, которым нужно
    // конкретное поле, ставят фокус сами через setTimeout после openModal —
    // их вызов идёт позже и перебивает этот, что и требуется.
    var л = лист(м);
    if (л) л.focus({ preventScroll: true });
  };

  window.closeModal = function (id) {
    var м = document.getElementById(id);
    if (!м || !м.classList.contains('open')) return;

    м.classList.remove('open');
    стек = стек.filter(function (x) { return x !== id; });

    // Порядок важен: фокус возвращаем ДО inert. Наоборот — inert снимет
    // фокус с потомка в никуда (на <body>), и возвращать станет неоткуда.
    var назад = фокус_до[id];
    delete фокус_до[id];
    if (назад && document.contains(назад) && !назад.closest('.modal-ov')) {
      назад.focus({ preventScroll: true });
    } else if (м.contains(document.activeElement)) {
      // Открывшего элемента больше нет (список перерисовали) — уводим фокус
      // хотя бы наружу, иначе он останется на невидимом поле
      document.activeElement.blur();
    }
    м.setAttribute('inert', '');

    if (!стек.length) блокировать(false);

    // Своя уборка страницы (остановить камеру сканера, сбросить состояние)
    // вешается сюда, а не подменяет closeModal: выход из окна должен быть
    // один на все три способа закрытия.
    м.dispatchEvent(new CustomEvent('modal:close', { bubbles: true }));
  };

  // ── Escape закрывает верхнюю открытую ──
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape' || !стек.length) return;
    window.closeModal(стек[стек.length - 1]);
  });

  // ── Клик вне окна и кнопка закрытия — одним делегатом ──
  // Делегат, а не onclick в разметке: обработчик перестаёт быть тем, что
  // можно забыть скопировать в тринадцатую модалку.
  document.addEventListener('click', function (e) {
    var кнопка = e.target.closest('[data-modal-close]');
    if (кнопка) {
      var свой = кнопка.closest('.modal-ov');
      if (свой) { window.closeModal(свой.id); return; }
    }
    // Именно сам оверлей, а не что-то внутри листа
    if (e.target.classList && e.target.classList.contains('modal-ov')) {
      window.closeModal(e.target.id);
    }
  });

  // ── Закрытые модалки — вне порядка табуляции ──
  // inert стоит в разметке макроса, но страницы, собранные до компонента,
  // и любая динамика подстрахованы здесь.
  function расставить_inert() {
    document.querySelectorAll('.modal-ov').forEach(function (м) {
      if (!м.classList.contains('open')) м.setAttribute('inert', '');
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', расставить_inert);
  } else {
    расставить_inert();
  }
})();
