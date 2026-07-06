(function () {
  var THEME = window.PARTICLE_THEME || {};

  // Aurora-фон — создаём если страница явно не отключила эффект
  if (THEME.disabled !== true && THEME.aurora !== false) {
    if (!document.querySelector('.aurora-bg')) {
      var aurora = document.createElement('div');
      aurora.className = 'aurora-bg';
      aurora.innerHTML = '<span></span>';
      document.body.insertBefore(aurora, document.body.firstChild);
    }
  }

  // Умная навигация: прячем при скролле вниз, показываем при скролле вверх
  var nav = document.querySelector('.nav');
  if (nav) {
    var lastScrollY = 0;
    window.addEventListener('scroll', function () {
      var currentScrollY = window.scrollY;
      if (currentScrollY < 10) {
        nav.classList.remove('nav-hidden');
        nav.classList.remove('nav-glass');
      } else if (currentScrollY > lastScrollY + 5) {
        nav.classList.add('nav-hidden');
        nav.classList.add('nav-glass');
      } else if (currentScrollY < lastScrollY - 5) {
        nav.classList.remove('nav-hidden');
      }
      lastScrollY = currentScrollY;
    }, { passive: true });
  }
})();
