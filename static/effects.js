(function () {
  var canvas = document.createElement('canvas');
  canvas.id = 'bg-canvas';
  canvas.style.cssText = 'position:fixed;inset:0;z-index:0;pointer-events:none;';
  document.body.insertBefore(canvas, document.body.firstChild);

  var ctx = canvas.getContext('2d');
  var W, H;
  var mouse = { x: -9999, y: -9999 };
  var particles = [];

  var CONNECT  = 135;   // connection distance px
  var REPEL_R  = 95;    // mouse repulsion radius px
  var REPEL_F  = 2.0;   // repulsion force strength
  var DAMP     = 0.94;  // velocity damping per frame

  function isLight() {
    return document.documentElement.classList.contains('light');
  }

  function resize() {
    W = canvas.width  = window.innerWidth;
    H = canvas.height = window.innerHeight;
  }

  function makeParticles() {
    var n = W < 600 ? 28 : 52;
    particles = [];
    for (var i = 0; i < n; i++) {
      // 3 size tiers: small (75%), medium (20%), anchor (5%)
      var t = Math.random();
      var r = t < 0.05 ? Math.random() * 1.5 + 3.5   // anchor 3.5–5 px
            : t < 0.25 ? Math.random() * 0.8 + 1.8   // medium 1.8–2.6 px
            :             Math.random() * 0.6 + 0.5;  // small  0.5–1.1 px

      var a = Math.random() * Math.PI * 2;
      var s = 0.07 + Math.random() * 0.16;

      particles.push({
        x: Math.random() * W,
        y: Math.random() * H,
        vx: Math.cos(a) * s,  vy: Math.sin(a) * s,
        bvx: Math.cos(a) * s, bvy: Math.sin(a) * s,  // base velocity
        r: r
      });
    }
  }

  function draw() {
    ctx.clearRect(0, 0, W, H);

    var light = isLight();
    var cr = light ? '80,100,200'  : '0,212,255';
    var lineMax  = light ? 0.055 : 0.13;
    var nodeBase = light ? 0.22  : 0.50;

    // Connections
    for (var i = 0; i < particles.length; i++) {
      var a = particles[i];
      for (var j = i + 1; j < particles.length; j++) {
        var b  = particles[j];
        var dx = a.x - b.x, dy = a.y - b.y;
        var d  = Math.sqrt(dx * dx + dy * dy);
        if (d < CONNECT) {
          ctx.beginPath();
          ctx.strokeStyle = 'rgba(' + cr + ',' + ((1 - d / CONNECT) * lineMax).toFixed(3) + ')';
          ctx.lineWidth   = 0.65;
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
          ctx.stroke();
        }
      }
    }

    // Nodes
    for (var i = 0; i < particles.length; i++) {
      var p  = particles[i];
      var gr = Math.max(p.r * 2.2, 2.5);   // crisp small glow, not blurry blob

      var g = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, gr);
      g.addColorStop(0,   'rgba(' + cr + ',' + (nodeBase + 0.12) + ')');
      g.addColorStop(0.45,'rgba(' + cr + ',' + (nodeBase * 0.35) + ')');
      g.addColorStop(1,   'rgba(' + cr + ',0)');

      ctx.beginPath();
      ctx.arc(p.x, p.y, gr, 0, Math.PI * 2);
      ctx.fillStyle = g;
      ctx.fill();

      // Solid core dot
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(' + cr + ',' + (nodeBase + 0.15) + ')';
      ctx.fill();
    }
  }

  function tick() {
    for (var i = 0; i < particles.length; i++) {
      var p = particles[i];

      // Mouse repulsion
      var dx   = p.x - mouse.x;
      var dy   = p.y - mouse.y;
      var dist = Math.sqrt(dx * dx + dy * dy);
      if (dist < REPEL_R && dist > 1) {
        var f = (1 - dist / REPEL_R);
        f = f * f * REPEL_F;
        p.vx += (dx / dist) * f;
        p.vy += (dy / dist) * f;
      }

      // Damp toward base velocity (particles return to natural drift)
      p.vx = p.vx * DAMP + p.bvx * (1 - DAMP);
      p.vy = p.vy * DAMP + p.bvy * (1 - DAMP);

      // Speed cap
      var spd = Math.sqrt(p.vx * p.vx + p.vy * p.vy);
      if (spd > 3.5) { p.vx = p.vx / spd * 3.5; p.vy = p.vy / spd * 3.5; }

      p.x += p.vx;
      p.y += p.vy;

      // Bounce
      if (p.x < 0 || p.x > W) { p.vx *= -1; p.bvx *= -1; p.x = Math.max(0, Math.min(W, p.x)); }
      if (p.y < 0 || p.y > H) { p.vy *= -1; p.bvy *= -1; p.y = Math.max(0, Math.min(H, p.y)); }
    }

    draw();
    requestAnimationFrame(tick);
  }

  resize();
  makeParticles();
  tick();

  window.addEventListener('resize',    function () { resize(); makeParticles(); });
  window.addEventListener('mousemove', function (e) { mouse.x = e.clientX; mouse.y = e.clientY; });
  window.addEventListener('mouseleave',function ()  { mouse.x = -9999; mouse.y = -9999; });
})();
