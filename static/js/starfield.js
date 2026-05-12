/**
 * AstroScan-Chohra — Starfield Canvas (Day 1.18 — Parallax 3 layers)
 *
 * 3 depth layers réactives au scroll Y (slow / medium / fast)
 * Vanilla JS, requestAnimationFrame, no deps.
 */
(function () {
  'use strict';

  var canvas = document.getElementById('starfield-bg');
  if (!canvas) return;
  var ctx = canvas.getContext('2d');
  if (!ctx) return;

  var W = 0, H = 0, DPR = Math.max(1, window.devicePixelRatio || 1);
  var scrollY = 0;

  var layers = [
    { count: 80, opacity: 0.30, sizeMin: 0.5, sizeMax: 1.0, parallax: 0.10, stars: [] },
    { count: 60, opacity: 0.60, sizeMin: 1.0, sizeMax: 1.8, parallax: 0.30, stars: [] },
    { count: 40, opacity: 0.90, sizeMin: 1.5, sizeMax: 2.5, parallax: 0.60, stars: [] }
  ];

  function resize() {
    W = window.innerWidth;
    H = window.innerHeight;
    canvas.width = W * DPR;
    canvas.height = H * DPR;
    canvas.style.width = W + 'px';
    canvas.style.height = H + 'px';
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
    seed();
  }

  function rand(a, b) { return a + Math.random() * (b - a); }

  function seed() {
    layers.forEach(function (L) {
      L.stars = [];
      for (var i = 0; i < L.count; i++) {
        L.stars.push({
          x: Math.random() * W,
          y: Math.random() * H * 2.5,
          r: rand(L.sizeMin, L.sizeMax),
          twinklePhase: Math.random() * Math.PI * 2,
          twinkleSpeed: rand(0.0008, 0.002)
        });
      }
    });
  }

  function draw(t) {
    ctx.clearRect(0, 0, W, H);

    var g = ctx.createRadialGradient(W / 2, H / 2, 0, W / 2, H / 2, Math.max(W, H));
    g.addColorStop(0, 'rgba(8, 15, 28, 1)');
    g.addColorStop(1, 'rgba(0, 0, 0, 1)');
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, W, H);

    layers.forEach(function (L) {
      var offsetY = -scrollY * L.parallax;
      for (var i = 0; i < L.stars.length; i++) {
        var s = L.stars[i];
        var twinkle = 0.5 + 0.5 * Math.sin(t * s.twinkleSpeed + s.twinklePhase);
        var alpha = L.opacity * (0.5 + 0.5 * twinkle);
        var y = ((s.y + offsetY) % (H * 2.5) + H * 2.5) % (H * 2.5);
        if (y < -5 || y > H + 5) continue;
        ctx.beginPath();
        ctx.arc(s.x, y, s.r, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(220, 230, 255,' + alpha + ')';
        ctx.fill();
      }
    });

    requestAnimationFrame(draw);
  }

  var scrollPending = false;
  function onScroll() {
    if (scrollPending) return;
    scrollPending = true;
    requestAnimationFrame(function () {
      scrollY = window.scrollY || window.pageYOffset || 0;
      scrollPending = false;
    });
  }

  window.addEventListener('resize', resize, { passive: true });
  window.addEventListener('scroll', onScroll, { passive: true });

  resize();
  requestAnimationFrame(draw);
})();
