(function () {
  var canvas = document.createElement('canvas');
  canvas.id = 'bg-canvas';
  canvas.style.cssText = 'position:fixed;inset:0;z-index:0;pointer-events:none;';
  document.body.insertBefore(canvas, document.body.firstChild);

  var ctx = canvas.getContext('2d');
  var particles = [];
  var raf;
  var W, H;

  var COLORS = {
    dark:  { r: 0,   g: 212, b: 255 },
    light: { r: 80,  g: 120, b: 220 }
  };

  function getTheme() {
    return document.documentElement.classList.contains('light') ? 'light' : 'dark';
  }

  function resize() {
    W = canvas.width  = window.innerWidth;
    H = canvas.height = window.innerHeight;
  }

  function makeParticles() {
    var n = W < 600 ? 28 : 55;
    particles = [];
    for (var i = 0; i < n; i++) {
      particles.push({
        x:  Math.random() * W,
        y:  Math.random() * H,
        vx: (Math.random() - 0.5) * 0.25,
        vy: (Math.random() - 0.5) * 0.25,
        r:  Math.random() * 1.2 + 0.4
      });
    }
  }

  function draw() {
    ctx.clearRect(0, 0, W, H);
    var c   = COLORS[getTheme()];
    var rs  = c.r + ',' + c.g + ',' + c.b;
    var dim = getTheme() === 'light' ? 0.06 : 0.12;

    for (var i = 0; i < particles.length; i++) {
      var a = particles[i];
      for (var j = i + 1; j < particles.length; j++) {
        var b  = particles[j];
        var dx = a.x - b.x, dy = a.y - b.y;
        var d  = Math.sqrt(dx * dx + dy * dy);
        if (d < 130) {
          ctx.beginPath();
          ctx.strokeStyle = 'rgba(' + rs + ',' + ((1 - d / 130) * dim) + ')';
          ctx.lineWidth   = 0.6;
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
          ctx.stroke();
        }
      }
    }

    var alpha = getTheme() === 'light' ? 0.25 : 0.45;
    for (var i = 0; i < particles.length; i++) {
      var p   = particles[i];
      var grad = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, p.r * 5);
      grad.addColorStop(0, 'rgba(' + rs + ',' + alpha + ')');
      grad.addColorStop(1, 'rgba(' + rs + ',0)');
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r * 5, 0, Math.PI * 2);
      ctx.fillStyle = grad;
      ctx.fill();
    }
  }

  function tick() {
    for (var i = 0; i < particles.length; i++) {
      var p = particles[i];
      p.x += p.vx;
      p.y += p.vy;
      if (p.x < 0 || p.x > W) p.vx *= -1;
      if (p.y < 0 || p.y > H) p.vy *= -1;
    }
    draw();
    raf = requestAnimationFrame(tick);
  }

  resize();
  makeParticles();
  tick();

  window.addEventListener('resize', function () {
    resize();
    makeParticles();
  });
})();
