/* Подсказка при опечатке в домене почты.
 *
 * Человек пишет gmial.com вместо gmail.com, письмо уходит в никуда,
 * подтвердить регистрацию он не может и уходит. На входе та же опечатка
 * даёт «неверный email или пароль», и он думает, что забыл пароль.
 *
 * Это ПОДСКАЗКА, а не запрет: форма отправляется в любом случае. Человек
 * с почтой на редком домене не должен упираться в стену из-за того, что
 * его адрес похож на популярный.
 *
 * MX-проверку не делаем намеренно: домены-опечатки популярных провайдеров
 * (gmai.com, yandx.ru, mial.ru) зарегистрированы и принимают почту — это
 * тайпсквоттинг, их скупают ради чужих писем. MX там есть, и проверка
 * сказала бы «всё в порядке». Проверено замером, см. BACKLOG №12.
 */
(function () {
  'use strict';

  // На этих молчим — они настоящие, даже если похожи на популярные
  var ИЗВЕСТНЫЕ = ['gmail.com', 'mail.ru', 'yandex.ru', 'ya.ru', 'outlook.com',
    'hotmail.com', 'icloud.com', 'bk.ru', 'list.ru', 'inbox.ru', 'rambler.ru',
    'proton.me', 'mail.com', 'gmx.com', 'email.ru', 'vk.ru', 'ok.ru', 'aol.com',
    'yahoo.com', 'live.com', 'me.com', 'msn.com', 'qip.ru', 'internet.ru',
    'protonmail.com', 'yandex.com', 'ya.com', 'mail.ua', 'ukr.net', 'tut.by'];

  // Что предлагаем как исправление. Двухбуквенных имён здесь нет намеренно:
  // расстояние 1 от ya.ru или bk.ru накрывает пол-интернета, и подсказка
  // начинает предлагать bk.ru вместо vk.ru
  var ЦЕЛИ = ['gmail.com', 'mail.ru', 'yandex.ru', 'outlook.com', 'hotmail.com',
    'icloud.com', 'list.ru', 'inbox.ru', 'rambler.ru', 'proton.me'];

  /* Дамерау-Левенштейн: перестановка соседних букв стоит 1, а не 2.
     Это самая частая опечатка при быстром наборе — gmial вместо gmail. */
  function расстояние(a, b) {
    if (a === b) return 0;
    var la = a.length, lb = b.length, i, j, d = [];
    for (i = 0; i <= la; i++) { d[i] = [i]; }
    for (j = 0; j <= lb; j++) { d[0][j] = j; }
    for (i = 1; i <= la; i++) {
      for (j = 1; j <= lb; j++) {
        var цена = a.charAt(i - 1) === b.charAt(j - 1) ? 0 : 1;
        d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + цена);
        if (i > 1 && j > 1 &&
            a.charAt(i - 1) === b.charAt(j - 2) && a.charAt(i - 2) === b.charAt(j - 1)) {
          d[i][j] = Math.min(d[i][j], d[i - 2][j - 2] + 1);
        }
      }
    }
    return d[la][lb];
  }

  function подсказать(адрес) {
    var части = String(адрес || '').toLowerCase().trim().split('@');
    if (части.length !== 2 || !части[1]) return null;
    var домен = части[1];
    if (ИЗВЕСТНЫЕ.indexOf(домен) !== -1) return null;
    var лучший = null, лучшее = 99;
    for (var k = 0; k < ЦЕЛИ.length; k++) {
      var цель = ЦЕЛИ[k];
      // Короткие цели строже: одна ошибка. Длинные — до двух
      var порог = цель.length <= 7 ? 1 : 2;
      var р = расстояние(домен, цель);
      if (р <= порог && р < лучшее) { лучший = цель; лучшее = р; }
    }
    return лучший;
  }

  function подключить(поле) {
    if (!поле || поле.dataset.typoOn) return;
    поле.dataset.typoOn = '1';

    var блок = document.createElement('div');
    блок.className = 'email-typo-hint';
    блок.hidden = true;
    поле.parentNode.insertBefore(блок, поле.nextSibling);

    function показать() {
      var домен = подсказать(поле.value);
      if (!домен) { блок.hidden = true; return; }
      блок.innerHTML = '';
      блок.appendChild(document.createTextNode('Возможно, вы имели в виду '));
      var кнопка = document.createElement('button');
      кнопка.type = 'button';                 // иначе отправит форму
      кнопка.className = 'email-typo-fix';
      кнопка.textContent = домен;
      кнопка.addEventListener('click', function () {
        поле.value = поле.value.split('@')[0] + '@' + домен;
        блок.hidden = true;
        поле.focus();
      });
      блок.appendChild(кнопка);
      блок.appendChild(document.createTextNode('?'));
      блок.hidden = false;
    }

    // По потере фокуса, а не по отправке: после отправки страница
    // перезагружается, и исправлять уже поздно
    поле.addEventListener('blur', показать);
    поле.addEventListener('input', function () { блок.hidden = true; });
  }

  document.addEventListener('DOMContentLoaded', function () {
    var поля = document.querySelectorAll('input[type="email"], input[name="email"]');
    for (var i = 0; i < поля.length; i++) подключить(поля[i]);
  });
})();
