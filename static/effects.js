(function () {
  var canvas = document.createElement('canvas');
  canvas.id = 'bg-canvas';
  // will-change:transform — форсирует отдельный GPU-слой, предотвращает мигание при скролле
  canvas.style.cssText = 'position:fixed;inset:0;z-index:0;pointer-events:none;will-change:transform;';
  document.body.insertBefore(canvas, document.body.firstChild);

  var ctx = canvas.getContext('2d');
  var W, H;
  var mouse = { x: -9999, y: -9999 };
  var particles = [];

  // ── Config ────────────────────────────────────────────────
  var CONNECT   = 160;
  var LINE_MAX  = 0.28;
  var NODE_BASE = 0.60;
  var REPEL_R   = 100;
  var REPEL_F   = 2.2;
  var DAMP      = 0.93;

  // Опциональная переопределяемая тема частиц (window.PARTICLE_THEME),
  // задаётся на конкретных страницах ДО подключения этого скрипта.
  // Если не задана — поведение не меняется (cyan + соединительные линии).
  var THEME         = window.PARTICLE_THEME || {};
  var THEME_COLOR    = THEME.color || '0,212,255';
  var THEME_CONNECT  = THEME.connect !== false;

  var lastW = 0;
  var resizeTimer;

  // Полный сброс canvas (вызываем ТОЛЬКО при реальном ресайзе по ширине)
  function setSize() {
    W = window.innerWidth;
    H = window.innerHeight;
    canvas.width  = W;   // сброс canvas — только здесь!
    canvas.height = H;
    lastW = W;
  }

  function makeParticles() {
    var n = W < 600 ? 30 : 58;
    particles = [];
    for (var i = 0; i < n; i++) {
      var t = Math.random();
      var r = t < 0.06 ? Math.random() * 2 + 4
            : t < 0.28 ? Math.random() * 1 + 2
            :             Math.random() * 0.7 + 0.6;
      var a = Math.random() * Math.PI * 2;
      var s = 0.08 + Math.random() * 0.14;
      particles.push({
        x: Math.random() * W, y: Math.random() * H,
        vx: Math.cos(a) * s,  vy: Math.sin(a) * s,
        bvx: Math.cos(a) * s, bvy: Math.sin(a) * s,
        r: r
      });
    }
  }

  function draw() {
    ctx.clearRect(0, 0, W, H);
    var C = THEME_COLOR;

    if (THEME_CONNECT) {
      for (var i = 0; i < particles.length; i++) {
        var a = particles[i];
        for (var j = i + 1; j < particles.length; j++) {
          var b  = particles[j];
          var dx = a.x - b.x, dy = a.y - b.y;
          var d  = Math.sqrt(dx * dx + dy * dy);
          if (d < CONNECT) {
            var alpha = (1 - d / CONNECT) * LINE_MAX;
            ctx.beginPath();
            ctx.strokeStyle = 'rgba(' + C + ',' + alpha.toFixed(3) + ')';
            ctx.lineWidth   = 0.7;
            ctx.moveTo(a.x, a.y);
            ctx.lineTo(b.x, b.y);
            ctx.stroke();
          }
        }
      }
    }

    for (var i = 0; i < particles.length; i++) {
      var p  = particles[i];
      var gr = p.r * 2.4;
      var g  = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, gr);
      g.addColorStop(0,   'rgba(' + C + ',' + (NODE_BASE * 0.55) + ')');
      g.addColorStop(0.4, 'rgba(' + C + ',' + (NODE_BASE * 0.18) + ')');
      g.addColorStop(1,   'rgba(' + C + ',0)');
      ctx.beginPath();
      ctx.arc(p.x, p.y, gr, 0, Math.PI * 2);
      ctx.fillStyle = g;
      ctx.fill();

      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(' + C + ',' + NODE_BASE + ')';
      ctx.fill();
    }
  }

  function tick() {
    for (var i = 0; i < particles.length; i++) {
      var p = particles[i];

      var dx = p.x - mouse.x, dy = p.y - mouse.y;
      var d  = Math.sqrt(dx * dx + dy * dy);
      if (d < REPEL_R && d > 1) {
        var f = (1 - d / REPEL_R);
        f = f * f * REPEL_F;
        p.vx += (dx / d) * f;
        p.vy += (dy / d) * f;
      }

      p.vx = p.vx * DAMP + p.bvx * (1 - DAMP);
      p.vy = p.vy * DAMP + p.bvy * (1 - DAMP);

      var spd = Math.sqrt(p.vx * p.vx + p.vy * p.vy);
      if (spd > 4) { p.vx = p.vx / spd * 4; p.vy = p.vy / spd * 4; }

      p.x += p.vx;
      p.y += p.vy;

      if (p.x < 0)  { p.x = 0;  p.vx = Math.abs(p.vx);  p.bvx = Math.abs(p.bvx); }
      if (p.x > W)  { p.x = W;  p.vx = -Math.abs(p.vx); p.bvx = -Math.abs(p.bvx); }
      if (p.y < 0)  { p.y = 0;  p.vy = Math.abs(p.vy);  p.bvy = Math.abs(p.bvy); }
      if (p.y > H)  { p.y = H;  p.vy = -Math.abs(p.vy); p.bvy = -Math.abs(p.bvy); }
    }

    draw();
    requestAnimationFrame(tick);
  }

  setSize();
  makeParticles();
  tick();

  window.addEventListener('resize', function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () {
      var newW = window.innerWidth;

      if (Math.abs(newW - lastW) > 50) {
        // Реальный ресайз (поворот телефона, изменение окна) — полный сброс
        setSize();
        makeParticles();
      } else {
        // Только высота изменилась (адресная строка браузера) —
        // НЕ трогаем canvas.width/canvas.height (это сбросит canvas!),
        // просто обновляем H чтобы частицы правильно отбивались от нижней границы
        H = window.innerHeight;
      }
    }, 250);
  });

  window.addEventListener('mousemove',  function (e) { mouse.x = e.clientX; mouse.y = e.clientY; });
  window.addEventListener('mouseleave', function ()  { mouse.x = -9999; mouse.y = -9999; });
})();
