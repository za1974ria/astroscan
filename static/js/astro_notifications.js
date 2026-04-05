/* AstroScan Notification Bell — ISS passes + space weather alerts */
(function () {
  'use strict';
  if (window.__astroNotifLoaded) return;
  window.__astroNotifLoaded = true;

  /* ── CSS ── */
  var style = document.createElement('style');
  style.textContent = `
    #astro-notif-bell {
      position: relative;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      margin-left: 8px;
      vertical-align: middle;
    }
    #astro-notif-bell-btn {
      background: rgba(0,0,0,0.4);
      border: 1px solid #334;
      border-radius: 50%;
      width: 32px;
      height: 32px;
      font-size: 16px;
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      transition: border-color 0.2s, background 0.2s;
      position: relative;
      color: #aabbcc;
      user-select: none;
    }
    #astro-notif-bell-btn:hover { border-color: #00ff88; background: rgba(0,255,136,0.08); }
    #astro-notif-badge {
      display: none;
      position: absolute;
      top: -4px;
      right: -4px;
      background: #ff3333;
      color: #fff;
      font-size: 9px;
      font-weight: bold;
      border-radius: 10px;
      min-width: 16px;
      height: 16px;
      line-height: 16px;
      text-align: center;
      padding: 0 3px;
      animation: notif-pulse 1.5s infinite;
      pointer-events: none;
    }
    @keyframes notif-pulse {
      0%,100% { box-shadow: 0 0 0 0 rgba(255,51,51,0.7); }
      50% { box-shadow: 0 0 0 5px rgba(255,51,51,0); }
    }
    #astro-notif-dropdown {
      display: none;
      position: absolute;
      top: 40px;
      right: 0;
      width: 320px;
      background: #070d14;
      border: 1px solid #1a2535;
      border-radius: 8px;
      box-shadow: 0 8px 32px rgba(0,0,0,0.7);
      z-index: 9998;
      font-family: 'Roboto Mono', monospace;
      font-size: 11px;
      color: #aabbcc;
      overflow: hidden;
    }
    #astro-notif-dropdown.open { display: block; }
    .notif-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 10px 14px;
      background: rgba(0,255,136,0.05);
      border-bottom: 1px solid #1a2535;
      font-size: 10px;
      letter-spacing: 1px;
      color: #00ff88;
      font-weight: bold;
    }
    .notif-section-title {
      padding: 8px 14px 4px;
      font-size: 9px;
      letter-spacing: 2px;
      color: #556677;
      text-transform: uppercase;
    }
    .notif-iss-item {
      padding: 8px 14px;
      border-bottom: 1px solid #0d1520;
    }
    .notif-iss-time { color: #00ff88; font-size: 12px; font-weight: bold; }
    .notif-iss-meta { color: #7a8fa3; font-size: 10px; margin-top: 2px; }
    .notif-iss-vis-excellent { color: #00ff88; }
    .notif-iss-vis-good { color: #ffa500; }
    .notif-iss-vis-fair { color: #556677; }
    .notif-iss-countdown { color: #00d4ff; font-size: 10px; margin-top: 3px; }
    .notif-alert-item {
      padding: 8px 14px;
      border-bottom: 1px solid #0d1520;
      border-left: 2px solid #ff9900;
    }
    .notif-alert-type { color: #ff9900; font-size: 10px; font-weight: bold; }
    .notif-alert-level { color: #ff3333; font-size: 11px; margin-left: 4px; font-weight: bold; }
    .notif-alert-msg { color: #7a8fa3; font-size: 9px; margin-top: 2px; line-height: 1.4; }
    .notif-alert-time { color: #445566; font-size: 9px; margin-top: 2px; }
    .notif-footer {
      padding: 8px 14px;
      font-size: 9px;
      color: #334455;
      text-align: center;
      border-top: 1px solid #1a2535;
    }
    .notif-empty { padding: 12px 14px; color: #334455; font-size: 10px; }
    .notif-refresh-btn {
      background: none; border: none; cursor: pointer; color: #556677; font-size: 12px; padding: 0;
    }
    .notif-refresh-btn:hover { color: #00ff88; }
  `;
  document.head.appendChild(style);

  /* ── HTML ── */
  var bell = document.createElement('div');
  bell.id = 'astro-notif-bell';
  bell.innerHTML = `
    <div id="astro-notif-bell-btn" title="Alertes ISS & météo spatiale">🔔
      <span id="astro-notif-badge"></span>
    </div>
    <div id="astro-notif-dropdown">
      <div class="notif-header">
        <span>🛰️ ALERTES TLEMCEN</span>
        <button class="notif-refresh-btn" onclick="window.__astroNotifRefresh()" title="Actualiser">↺</button>
      </div>
      <div id="notif-iss-section"></div>
      <div id="notif-alerts-section"></div>
      <div class="notif-footer" id="notif-footer">Actualisation automatique · 5 min</div>
    </div>
  `;

  /* ── Inject into navbar ── */
  function injectBell() {
    // observatoire.html: end of <nav>
    var nav = document.querySelector('nav');
    if (nav) { nav.appendChild(bell); return; }
    // portail.html: topbar-right
    var tr = document.querySelector('.topbar-right');
    if (tr) { tr.appendChild(bell); return; }
    // fallback: body top-right fixed
    bell.style.cssText = 'position:fixed;top:12px;right:16px;z-index:9997;';
    document.body.appendChild(bell);
  }

  /* ── State ── */
  var _passes = [];
  var _alerts = [];
  var _lastUpdate = 0;

  /* ── Countdown formatter ── */
  function _countdown(unix_s) {
    var diff = unix_s - Math.floor(Date.now() / 1000);
    if (diff <= 0) return 'En cours';
    var h = Math.floor(diff / 3600);
    var m = Math.floor((diff % 3600) / 60);
    var s = diff % 60;
    if (h > 0) return 'Dans ' + h + 'h ' + m + 'min';
    if (m > 0) return 'Dans ' + m + 'min ' + s + 's';
    return 'Dans ' + s + 's';
  }

  /* ── Render dropdown ── */
  function _render() {
    var issSection = document.getElementById('notif-iss-section');
    var alertsSection = document.getElementById('notif-alerts-section');
    if (!issSection || !alertsSection) return;

    // ISS passes (next 3)
    var issHtml = '<div class="notif-section-title">🛸 Passages ISS — Tlemcen</div>';
    if (_passes.length === 0) {
      issHtml += '<div class="notif-empty">Aucun passage disponible</div>';
    } else {
      _passes.slice(0, 3).forEach(function (p) {
        var visClass = 'notif-iss-vis-' + p.visibility;
        var dt = new Date(p.datetime + 'Z');
        var dateStr = dt.toLocaleDateString('fr-FR', {weekday:'short', day:'2-digit', month:'short'});
        var timeStr = dt.toLocaleTimeString('fr-FR', {hour:'2-digit', minute:'2-digit'});
        var countdown = p.timestamp_unix ? _countdown(p.timestamp_unix) : '';
        issHtml += '<div class="notif-iss-item">'
          + '<div class="notif-iss-time">' + dateStr + ' · ' + timeStr + ' UTC</div>'
          + '<div class="notif-iss-meta">'
          + 'Durée: <b>' + p.duration_min + ' min</b> · '
          + 'Élév. max: <b>' + p.max_elevation_deg + '°</b> · '
          + '<span class="' + visClass + '">' + p.visibility.toUpperCase() + '</span>'
          + ' · ' + p.direction_start + '→' + p.direction_end
          + '</div>'
          + (countdown ? '<div class="notif-iss-countdown">⏱ ' + countdown + '</div>' : '')
          + '</div>';
      });
    }
    issSection.innerHTML = issHtml;

    // Space weather alerts
    var alertsHtml = '<div class="notif-section-title">☀️ Météo Spatiale — NOAA</div>';
    if (_alerts.length === 0) {
      alertsHtml += '<div class="notif-empty">Aucune alerte active (24h)</div>';
    } else {
      _alerts.slice(0, 4).forEach(function (a) {
        alertsHtml += '<div class="notif-alert-item">'
          + '<div><span class="notif-alert-type">' + a.type + '</span>'
          + (a.level ? '<span class="notif-alert-level">' + a.level + '</span>' : '')
          + '</div>'
          + '<div class="notif-alert-msg">' + (a.message || '').substring(0, 120) + (a.message && a.message.length > 120 ? '…' : '') + '</div>'
          + '<div class="notif-alert-time">' + a.issued + '</div>'
          + '</div>';
      });
    }
    alertsSection.innerHTML = alertsHtml;

    // Badge
    var badge = document.getElementById('astro-notif-badge');
    var kpHigh = false;
    try {
      var sw = window.__spaceWeatherKp;
      if (sw && parseFloat(sw) > 4) kpHigh = true;
    } catch (e) {}
    var count = _alerts.length + (kpHigh ? 1 : 0);
    if (badge) {
      if (count > 0) {
        badge.textContent = count;
        badge.style.display = 'block';
      } else {
        badge.style.display = 'none';
      }
    }

    // Update footer
    var footer = document.getElementById('notif-footer');
    if (footer && _lastUpdate) {
      var d = new Date(_lastUpdate);
      footer.textContent = 'Mis à jour ' + d.toLocaleTimeString('fr-FR') + ' · Actualisation: 5 min';
    }
  }

  /* ── Fetch data ── */
  function _fetchData() {
    fetch('/api/iss/passes')
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (Array.isArray(d)) _passes = d;
        _render();
      })
      .catch(function () {});

    fetch('/api/space-weather/alerts')
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (Array.isArray(d)) _alerts = d;
        _lastUpdate = Date.now();
        _render();
      })
      .catch(function () {});

    // Also try to get Kp from space_weather endpoint
    fetch('/api/space-weather')
      .then(function (r) { return r.json(); })
      .then(function (d) {
        var kp = d && (d.kp_index || d.kp);
        if (kp !== undefined && kp !== null) window.__spaceWeatherKp = kp;
        _render();
      })
      .catch(function () {});
  }

  /* ── Toggle dropdown ── */
  document.addEventListener('click', function (e) {
    var btn = document.getElementById('astro-notif-bell-btn');
    var drop = document.getElementById('astro-notif-dropdown');
    if (!btn || !drop) return;
    if (btn.contains(e.target)) {
      drop.classList.toggle('open');
      if (drop.classList.contains('open')) {
        _render(); // update countdowns on open
      }
    } else if (!drop.contains(e.target)) {
      drop.classList.remove('open');
    }
  });

  /* ── Public refresh ── */
  window.__astroNotifRefresh = function () {
    // Clear cache by invalidating; just re-fetch
    _fetchData();
  };

  /* ── Countdown ticker (updates every 30s when dropdown open) ── */
  setInterval(function () {
    var drop = document.getElementById('astro-notif-dropdown');
    if (drop && drop.classList.contains('open')) _render();
  }, 30000);

  /* ── Auto-refresh every 5 min ── */
  function _startAutoRefresh() {
    _fetchData();
    setInterval(_fetchData, 300000);
  }

  /* ── Init ── */
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { injectBell(); _startAutoRefresh(); });
  } else {
    injectBell();
    _startAutoRefresh();
  }
})();
