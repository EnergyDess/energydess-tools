(function () {
  var canvas = document.createElement('canvas');
  canvas.id = 'bg-canvas';
  canvas.style.cssText = 'position:fixed;inset:0;z-index:0;pointer-events:none;';
  document.body.insertBefore(canvas, document.body.firstChild);

  var ctx = canvas.getContext('2d');
  var W, H;
  var mouse = { x: -9999, y: -9999 };
  var particles = [];

  // ── Config ────────────────────────────────────────────────
  var CONNECT   = 160;   // px — connection distance
  var LINE_MAX  = 0.28;  // max line opacity (dark mode)
  var NODE_BASE = 0.60;  // node opacity
  var REPEL_R   = 100;   // mouse repulsion radius
  var REPEL_F   = 2.2;   // repulsion force
  var DAMP      = 0.93;  // velocity damping

  function resize() {
    W = canvas.width  = window.innerWidth;
    H = canvas.height = window.innerHeight;
  }

  function makeParticles() {
    var n = W < 600 ? 30 : 58;
    particles = [];
    for (var i = 0; i < n; i++) {
      // Size tiers: small 72%, medium 22%, anchor 6%
      var t = Math.random();
      var r = t < 0.06 ? Math.random() * 2 + 4      // anchor 4–6 px
            : t < 0.28 ? Math.random() * 1 + 2      // medium 2–3 px
            :             Math.random() * 0.7 + 0.6; // small  0.6–1.3 px

      var a = Math.random() * Math.PI * 2;
      var s = 0.08 + Math.random() * 0.14;

      particles.push({
        x: Math.random() * W,  y: Math.random() * H,
        vx: Math.cos(a) * s,   vy: Math.sin(a) * s,
        bvx: Math.cos(a) * s,  bvy: Math.sin(a) * s,
        r: r
      });
    }
  }

  function draw() {
    ctx.clearRect(0, 0, W, H);
    var C = '0,212,255';  // electric cyan — dark mode only

    // ── Connections ──────────────────────────────────────────
    for (var i = 0; i < particles.length; i++) {
      var a = particles[i];
      for (var j = i + 1; j < particles.length; j++) {
        var b  = particles[j];
        var dx = a.x - b.x,  dy = a.y - b.y;
        var d  = Math.sqrt(dx * dx + dy * dy);
        if (d < CONNECT) {
          // Linear falloff — fully opaque at d=0, 0 at d=CONNECT
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

    // ── Nodes ─────────────────────────────────────────────────
    for (var i = 0; i < particles.length; i++) {
      var p  = particles[i];
      var gr = p.r * 2.4;  // glow radius — small and crisp

      // Glow halo
      var g = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, gr);
      g.addColorStop(0,    'rgba(' + C + ',' + (NODE_BASE * 0.55) + ')');
      g.addColorStop(0.4,  'rgba(' + C + ',' + (NODE_BASE * 0.18) + ')');
      g.addColorStop(1,    'rgba(' + C + ',0)');
      ctx.beginPath();
      ctx.arc(p.x, p.y, gr, 0, Math.PI * 2);
      ctx.fillStyle = g;
      ctx.fill();

      // Solid core
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(' + C + ',' + NODE_BASE + ')';
      ctx.fill();
    }
  }

  function tick() {
    for (var i = 0; i < particles.length; i++) {
      var p = particles[i];

      // Mouse repulsion
      var dx = p.x - mouse.x,  dy = p.y - mouse.y;
      var d  = Math.sqrt(dx * dx + dy * dy);
      if (d < REPEL_R && d > 1) {
        var f = (1 - d / REPEL_R);
        f = f * f * REPEL_F;
        p.vx += (dx / d) * f;
        p.vy += (dy / d) * f;
      }

      // Damp back toward base velocity
      p.vx = p.vx * DAMP + p.bvx * (1 - DAMP);
      p.vy = p.vy * DAMP + p.bvy * (1 - DAMP);

      // Speed cap
      var spd = Math.sqrt(p.vx * p.vx + p.vy * p.vy);
      if (spd > 4) { p.vx = p.vx / spd * 4;  p.vy = p.vy / spd * 4; }

      p.x += p.vx;
      p.y += p.vy;

      // Bounce walls
      if (p.x < 0)  { p.x = 0;  p.vx = Math.abs(p.vx);  p.bvx = Math.abs(p.bvx); }
      if (p.x > W)  { p.x = W;  p.vx = -Math.abs(p.vx); p.bvx = -Math.abs(p.bvx); }
      if (p.y < 0)  { p.y = 0;  p.vy = Math.abs(p.vy);  p.bvy = Math.abs(p.bvy); }
      if (p.y > H)  { p.y = H;  p.vy = -Math.abs(p.vy); p.bvy = -Math.abs(p.bvy); }
    }

    draw();
    requestAnimationFrame(tick);
  }

  resize();
  makeParticles();
  tick();

  window.addEventListener('resize',     function () { resize(); makeParticles(); });
  window.addEventListener('mousemove',  function (e) { mouse.x = e.clientX; mouse.y = e.clientY; });
  window.addEventListener('mouseleave', function ()  { mouse.x = -9999; mouse.y = -9999; });
})();
