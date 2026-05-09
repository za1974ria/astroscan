/**
 * AstroScan-Chohra — Starfield Canvas background (Phase C FIX 1)
 *
 * Cinematic deep-space starfield rendered behind the portail content.
 * Vanilla JS, no dependencies. Respects prefers-reduced-motion.
 *
 * Design:
 *   - 350-500 stars (density scales with viewport)
 *   - 3 parallax layers (far/medium/near) for depth via drift speed
 *   - Twinkle via sin(time * speed + phase)
 *   - 90% white / 7% blue-white / 3% pale yellow stellar variety
 *   - 4-6 shooting stars per minute on diagonal trajectories
 *   - 30 FPS throttle, paused on document.hidden, OffscreenCanvas if available
 *
 * Mounted via #starfield-bg canvas (must exist in DOM at script execution).
 */
(function () {
  'use strict';

  var canvas = document.getElementById('starfield-bg');
  if (!canvas) return;

  var ctx = canvas.getContext('2d', { alpha: true });
  if (!ctx) return;

  var prefersReduce = window.matchMedia &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // ── Sizing ─────────────────────────────────────────────────────────
  var dpr = Math.min(window.devicePixelRatio || 1, 2);
  var W = 0, H = 0;

  function resize() {
    W = window.innerWidth;
    H = window.innerHeight;
    canvas.width = Math.floor(W * dpr);
    canvas.height = Math.floor(H * dpr);
    canvas.style.width = W + 'px';
    canvas.style.height = H + 'px';
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  // ── Star palette ───────────────────────────────────────────────────
  var COLORS = [
    { c: '#ffffff', w: 90 }, // white (90%)
    { c: '#cce4ff', w: 7 },  // blue-white (7%)
    { c: '#fff5e6', w: 3 },  // pale yellow (3%)
  ];
  function pickColor() {
    var r = Math.random() * 100;
    var acc = 0;
    for (var i = 0; i < COLORS.length; i++) {
      acc += COLORS[i].w;
      if (r < acc) return COLORS[i].c;
    }
    return COLORS[0].c;
  }

  // ── Star generation ────────────────────────────────────────────────
  var stars = [];
  function makeStars() {
    var density = Math.min(500, Math.max(350, Math.floor(W * H / 4500)));
    stars = new Array(density);
    for (var i = 0; i < density; i++) {
      var sizeRand = Math.random();
      var radius = sizeRand < 0.85
        ? 0.3 + Math.random() * 0.7   // 85% small
        : 0.9 + Math.random() * 0.9;  // 15% medium
      stars[i] = {
        x: Math.random() * W,
        y: Math.random() * H,
        r: radius,
        baseAlpha: 0.25 + Math.random() * 0.7,
        speed: 0.0008 + Math.random() * 0.0022,  // twinkle freq
        phase: Math.random() * Math.PI * 2,
        layer: 1 + Math.floor(Math.random() * 3), // 1=far .. 3=near
        color: pickColor(),
      };
    }
  }

  // ── Shooting stars ─────────────────────────────────────────────────
  var shootingStars = [];
  var nextShootingAt = 0;

  function spawnShootingStar(now) {
    // diagonal trajectory across 30-60% of the viewport
    var startX = Math.random() * W * 0.6;
    var startY = -10 + Math.random() * H * 0.3;
    var angle = Math.PI / 4 + (Math.random() - 0.5) * 0.4;  // ~45° ± 11°
    var distance = (W * 0.3) + Math.random() * (W * 0.3);
    var duration = 600 + Math.random() * 600;
    shootingStars.push({
      x: startX,
      y: startY,
      vx: Math.cos(angle) * (distance / duration),
      vy: Math.sin(angle) * (distance / duration),
      bornAt: now,
      duration: duration,
    });
  }

  function scheduleNextShootingStar(now) {
    // 4-6 per minute → every 10-15s
    nextShootingAt = now + 10000 + Math.random() * 5000;
  }

  // ── Animation loop (throttled to ~30 FPS) ──────────────────────────
  var FRAME_INTERVAL = 1000 / 30;
  var lastFrame = 0;
  var rafId = null;

  function frame(now) {
    rafId = requestAnimationFrame(frame);
    if (now - lastFrame < FRAME_INTERVAL) return;
    lastFrame = now;

    ctx.clearRect(0, 0, W, H);

    // Stars
    for (var i = 0; i < stars.length; i++) {
      var s = stars[i];
      var twinkle = 0.6 + 0.4 * Math.sin(now * s.speed + s.phase);
      var alpha = s.baseAlpha * twinkle;
      ctx.globalAlpha = alpha;
      ctx.fillStyle = s.color;
      ctx.beginPath();
      ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
      ctx.fill();
      // halo for medium stars
      if (s.r > 1.0) {
        ctx.globalAlpha = alpha * 0.18;
        ctx.beginPath();
        ctx.arc(s.x, s.y, s.r * 2.4, 0, Math.PI * 2);
        ctx.fill();
      }
      // parallax drift (very subtle vertical)
      s.y += s.layer * 0.015;
      if (s.y > H) {
        s.y = -2;
        s.x = Math.random() * W;
      }
    }
    ctx.globalAlpha = 1;

    // Shooting stars
    if (now >= nextShootingAt) {
      spawnShootingStar(now);
      scheduleNextShootingStar(now);
    }
    for (var k = shootingStars.length - 1; k >= 0; k--) {
      var sh = shootingStars[k];
      var t = now - sh.bornAt;
      if (t > sh.duration) {
        shootingStars.splice(k, 1);
        continue;
      }
      var px = sh.x + sh.vx * t;
      var py = sh.y + sh.vy * t;
      var lifeFrac = t / sh.duration;
      var alpha = lifeFrac < 0.2
        ? lifeFrac / 0.2
        : 1 - (lifeFrac - 0.2) / 0.8;
      // tail
      var tailLen = 70;
      var grad = ctx.createLinearGradient(
        px - sh.vx * tailLen, py - sh.vy * tailLen,
        px, py
      );
      grad.addColorStop(0, 'rgba(0, 212, 255, 0)');
      grad.addColorStop(1, 'rgba(204, 240, 255, ' + alpha + ')');
      ctx.strokeStyle = grad;
      ctx.lineWidth = 1.4;
      ctx.beginPath();
      ctx.moveTo(px - sh.vx * tailLen, py - sh.vy * tailLen);
      ctx.lineTo(px, py);
      ctx.stroke();
      // head
      ctx.globalAlpha = alpha;
      ctx.fillStyle = '#e6f5ff';
      ctx.beginPath();
      ctx.arc(px, py, 1.4, 0, Math.PI * 2);
      ctx.fill();
      ctx.globalAlpha = 1;
    }
  }

  // ── Static render (reduced-motion fallback) ────────────────────────
  function renderStatic() {
    ctx.clearRect(0, 0, W, H);
    for (var i = 0; i < stars.length; i++) {
      var s = stars[i];
      ctx.globalAlpha = s.baseAlpha;
      ctx.fillStyle = s.color;
      ctx.beginPath();
      ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
  }

  // ── Page Visibility API: pause when tab hidden ─────────────────────
  function onVisibilityChange() {
    if (document.hidden) {
      if (rafId) {
        cancelAnimationFrame(rafId);
        rafId = null;
      }
    } else if (!prefersReduce && rafId === null) {
      lastFrame = performance.now();
      rafId = requestAnimationFrame(frame);
    }
  }

  // ── Resize handler (debounced) ─────────────────────────────────────
  var resizeTimer = null;
  function onResize() {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () {
      resize();
      makeStars();
      if (prefersReduce) renderStatic();
    }, 120);
  }

  // ── Init ───────────────────────────────────────────────────────────
  resize();
  makeStars();
  if (prefersReduce) {
    renderStatic();
  } else {
    scheduleNextShootingStar(performance.now());
    rafId = requestAnimationFrame(frame);
  }
  window.addEventListener('resize', onResize, { passive: true });
  document.addEventListener('visibilitychange', onVisibilityChange);
})();
