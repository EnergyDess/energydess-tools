(function () {
  var THEME = window.PARTICLE_THEME || {};

  // Aurora-фон — создаём если страница явно не отключила эффект
  if (THEME.disabled !== true) {
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
    var lastY = 0, ticking = false;
    window.addEventListener('scroll', function () {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(function () {
        var y = window.scrollY;
        if (y < 10) {
          nav.classList.remove('nav-hidden', 'nav-glass');
        } else {
          nav.classList.add('nav-glass');
          if (y > 80) {
            if (y > lastY + 5)      nav.classList.add('nav-hidden');
            else if (y < lastY - 5) nav.classList.remove('nav-hidden');
          }
        }
        lastY = y;
        ticking = false;
      });
    }, { passive: true });
  }
})();
