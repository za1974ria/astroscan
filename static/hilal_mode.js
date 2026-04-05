/**
 * Hilal Mode — assisted moon-crescent observation layer (UI-only).
 * No backend changes required. Future telescope integration via Alpaca/INDI.
 */
(function () {
  "use strict";

  // -----------------------------
  // Telescope integration layer
  // -----------------------------
  class TelescopeConnector {
    constructor(opts) {
      this.opts = opts || {};
      this.connected = false;
      this.backend = this.opts.backend || "SIM";
      this.lastError = null;
    }
    async connect() {
      try {
        this.connected = true;
        this.lastError = null;
        return { ok: true, backend: this.backend };
      } catch (e) {
        this.lastError = e;
        return { ok: false, error: String(e) };
      }
    }
    async slew_to_moon(moonAzDeg, moonAltDeg) {
      try {
        if (!this.connected) return { ok: false, error: "not connected" };
        return { ok: true, az: moonAzDeg, alt: moonAltDeg };
      } catch (e) {
        this.lastError = e;
        return { ok: false, error: String(e) };
      }
    }
    async start_tracking() {
      try {
        if (!this.connected) return { ok: false, error: "not connected" };
        return { ok: true };
      } catch (e) {
        this.lastError = e;
        return { ok: false, error: String(e) };
      }
    }
    async capture_image() {
      try {
        if (!this.connected) return { ok: false, error: "not connected" };
        // Placeholder: later this will call Alpaca/INDI capture APIs.
        return { ok: true, imageRef: "SIM-CAPTURE" };
      } catch (e) {
        this.lastError = e;
        return { ok: false, error: String(e) };
      }
    }
    async disconnect() {
      try {
        this.connected = false;
        return { ok: true };
      } catch (e) {
        this.lastError = e;
        return { ok: false, error: String(e) };
      }
    }
  }

  // -----------------------------
  // Minimal solar position helpers
  // -----------------------------
  function toRad(d) { return (d * Math.PI) / 180; }
  function toDeg(r) { return (r * 180) / Math.PI; }

  // Approx sunset calculation (NOAA-style simplified). Returns Date in local time.
  function computeSunsetLocal(date, latDeg, lonDeg) {
    try {
      if (!(date instanceof Date)) return null;
      if (!isFinite(latDeg) || !isFinite(lonDeg)) return null;

      // Use day-of-year
      var d = new Date(date.getFullYear(), date.getMonth(), date.getDate());
      var start = new Date(d.getFullYear(), 0, 0);
      var n = Math.floor((d - start) / 86400000);

      // Approx solar declination and equation of time
      var gamma = (2 * Math.PI / 365) * (n - 1 + (12 - 12) / 24);
      var eqtime = 229.18 * (0.000075 + 0.001868 * Math.cos(gamma) - 0.032077 * Math.sin(gamma) - 0.014615 * Math.cos(2 * gamma) - 0.040849 * Math.sin(2 * gamma));
      var decl = 0.006918 - 0.399912 * Math.cos(gamma) + 0.070257 * Math.sin(gamma) - 0.006758 * Math.cos(2 * gamma) + 0.000907 * Math.sin(2 * gamma) - 0.002697 * Math.cos(3 * gamma) + 0.00148 * Math.sin(3 * gamma);

      // Solar zenith for sunset (90.833°)
      var lat = toRad(latDeg);
      var zenith = toRad(90.833);
      var ha = Math.acos(Math.max(-1, Math.min(1, (Math.cos(zenith) / (Math.cos(lat) * Math.cos(decl))) - Math.tan(lat) * Math.tan(decl))));

      // Minutes from midnight UTC
      var solarNoonMin = 720 - 4 * lonDeg - eqtime;
      var sunsetMin = solarNoonMin + toDeg(ha) * 4;

      // Convert to local time by using the browser TZ offset at that date
      var utcMidnight = Date.UTC(d.getFullYear(), d.getMonth(), d.getDate(), 0, 0, 0, 0);
      var utcMillis = utcMidnight + sunsetMin * 60000;
      var local = new Date(utcMillis);
      return local;
    } catch (e) {
      return null;
    }
  }

  // -----------------------------
  // Moon position (approx) — Ecliptic lon/lat model
  // Not astrophotography-grade; intended for demo credibility.
  // -----------------------------
  function julianDate(date) {
    try {
      if (!(date instanceof Date)) return null;
      return (date.getTime() / 86400000) + 2440587.5;
    } catch (e) {
      return null;
    }
  }

  function computeMoonAltAz(date, latDeg, lonDeg) {
    try {
      if (!(date instanceof Date)) return null;
      if (!isFinite(latDeg) || !isFinite(lonDeg)) return null;
      var jd = julianDate(date);
      if (!isFinite(jd)) return null;
      var d = jd - 2451545.0; // days since J2000

      // Mean elements (degrees)
      var L = (218.316 + 13.176396 * d) % 360; // mean longitude
      var M = (134.963 + 13.064993 * d) % 360; // mean anomaly
      var F = (93.272 + 13.229350 * d) % 360;  // argument of latitude

      // Ecliptic longitude/latitude (very simplified)
      var lon = L + 6.289 * Math.sin(toRad(M));
      var lat = 5.128 * Math.sin(toRad(F));
      var distKm = 385001 - 20905 * Math.cos(toRad(M));

      // Obliquity
      var e = toRad(23.439 - 0.0000004 * d);

      // Convert to RA/Dec
      var lonR = toRad(lon);
      var latR = toRad(lat);
      var x = Math.cos(lonR) * Math.cos(latR);
      var y = Math.sin(lonR) * Math.cos(latR);
      var z = Math.sin(latR);
      var xeq = x;
      var yeq = y * Math.cos(e) - z * Math.sin(e);
      var zeq = y * Math.sin(e) + z * Math.cos(e);
      var ra = Math.atan2(yeq, xeq);
      var dec = Math.asin(zeq);

      // Local sidereal time
      var T = (jd - 2451545.0) / 36525.0;
      var GMST = (280.46061837 + 360.98564736629 * (jd - 2451545.0) + 0.000387933 * T * T - (T * T * T) / 38710000.0) % 360;
      var LST = toRad((GMST + lonDeg + 360) % 360);

      var ha = LST - ra;

      var latR2 = toRad(latDeg);
      var alt = Math.asin(Math.sin(dec) * Math.sin(latR2) + Math.cos(dec) * Math.cos(latR2) * Math.cos(ha));
      var az = Math.atan2(-Math.sin(ha), Math.tan(dec) * Math.cos(latR2) - Math.sin(latR2) * Math.cos(ha));
      var azDeg = (toDeg(az) + 360) % 360;
      var altDeg = toDeg(alt);

      return { altDeg: altDeg, azDeg: azDeg, distKm: distKm };
    } catch (e) {
      return null;
    }
  }

  // Simple heuristic probability model for crescent visibility (demo-grade).
  function computeHilalProbability(altDeg, minutesAfterSunset) {
    try {
      var a = isFinite(altDeg) ? altDeg : -90;
      var t = isFinite(minutesAfterSunset) ? minutesAfterSunset : 0;
      // Encourage higher altitude early; penalize very late.
      var altScore = Math.max(0, Math.min(1, (a - 2) / 10));        // 2°→0, 12°→1
      var timeScore = Math.max(0, Math.min(1, (90 - t) / 90));      // 0→1, 90→0
      var p = (altScore * 0.7 + timeScore * 0.3);
      return Math.round(Math.max(0, Math.min(100, p * 100)));
    } catch (e) {
      return 0;
    }
  }

  function classifyHilalStatus(prob) {
    try {
      if (!isFinite(prob)) return { label: "LOW", cls: "off" };
      if (prob >= 70) return { label: "FAVORABLE", cls: "ok" };
      if (prob >= 35) return { label: "POSSIBLE", cls: "warn" };
      return { label: "LOW", cls: "off" };
    } catch (e) {
      return { label: "LOW", cls: "off" };
    }
  }

  function fmtHM(d) {
    try {
      if (!(d instanceof Date)) return "n/a";
      return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    } catch (e) {
      return "n/a";
    }
  }

  // -----------------------------
  // Hilal Mode controller
  // -----------------------------
  var state = {
    enabled: false,
    lastRenderMs: 0,
    captures: [],
    telescope: new TelescopeConnector({ backend: "SIM" }),
    lastComputed: null
  };

  function getObserverLatLon() {
    try {
      // Prefer OrbitalMapEngine observer coords if available
      var eng = window.OrbitalMapEngine && window.OrbitalMapEngine.state;
      if (eng && window.ORBITAL_OBSERVER && isFinite(window.ORBITAL_OBSERVER.lat) && isFinite(window.ORBITAL_OBSERVER.lon)) {
        return { lat: window.ORBITAL_OBSERVER.lat, lon: window.ORBITAL_OBSERVER.lon };
      }
      // Fallback: use the hardcoded default from engine if exposed
      if (eng && eng.observerGd && isFinite(eng.observerGd.latitude) && isFinite(eng.observerGd.longitude)) {
        return { lat: toDeg(eng.observerGd.latitude), lon: toDeg(eng.observerGd.longitude) };
      }
      // Ultimate fallback: Tlemcen-ish
      return { lat: 34.888, lon: 1.315 };
    } catch (e) {
      return { lat: 34.888, lon: 1.315 };
    }
  }

  function renderPanel() {
    try {
      var panel = document.getElementById("hilal-panel");
      var metricsEl = document.getElementById("hilal-metrics");
      var statusEl = document.getElementById("hilal-status-badge");
      var capsEl = document.getElementById("hilal-captures");
      if (!panel || !metricsEl || !statusEl || !capsEl) return;
      if (!state.enabled) {
        panel.style.display = "none";
        return;
      }
      panel.style.display = "block";

      var obs = getObserverLatLon();
      var now = new Date();
      var sunset = computeSunsetLocal(now, obs.lat, obs.lon);
      var windowStart = sunset ? new Date(sunset.getTime() + 20 * 60000) : null;
      var windowEnd = sunset ? new Date(sunset.getTime() + 90 * 60000) : null;
      var mid = sunset ? new Date(sunset.getTime() + 45 * 60000) : now;

      var moon = computeMoonAltAz(mid, obs.lat, obs.lon);
      var minutesAfter = sunset ? Math.max(0, Math.round((mid.getTime() - sunset.getTime()) / 60000)) : 0;
      var prob = moon ? computeHilalProbability(moon.altDeg, minutesAfter) : 0;
      var st = classifyHilalStatus(prob);

      state.lastComputed = {
        ts: now.toISOString(),
        lat: obs.lat,
        lon: obs.lon,
        sunset: sunset ? sunset.toISOString() : null,
        windowStart: windowStart ? windowStart.toISOString() : null,
        windowEnd: windowEnd ? windowEnd.toISOString() : null,
        moonAlt: moon ? moon.altDeg : null,
        moonAz: moon ? moon.azDeg : null,
        probability: prob,
        status: st.label
      };

      statusEl.className = "asc-badge " + (st.cls || "off");
      statusEl.innerHTML = "<span class=\"asc-dot\" style=\"background:currentColor;\"></span><span>" + st.label + "</span>";

      var html = "";
      html += "<div><span style=\"color:#aaa;\">Location</span>: " + obs.lat.toFixed(3) + "°, " + obs.lon.toFixed(3) + "°</div>";
      html += "<div><span style=\"color:#aaa;\">Sunset</span>: " + (sunset ? fmtHM(sunset) : "n/a") + "</div>";
      html += "<div><span style=\"color:#aaa;\">Observation window</span>: " + (windowStart ? fmtHM(windowStart) : "n/a") + " → " + (windowEnd ? fmtHM(windowEnd) : "n/a") + "</div>";
      html += "<div style=\"margin-top:6px;\"><span style=\"color:#aaa;\">Moon altitude</span>: " + (moon ? moon.altDeg.toFixed(1) + "°" : "n/a") + "</div>";
      html += "<div><span style=\"color:#aaa;\">Moon azimuth</span>: " + (moon ? moon.azDeg.toFixed(1) + "°" : "n/a") + "</div>";
      html += "<div><span style=\"color:#aaa;\">Visibility probability</span>: <span style=\"color:#ffd166;\">" + prob + "%</span></div>";
      html += "<div style=\"margin-top:6px;color:rgba(150,175,190,.85);font-size:10px;\">Model: demo-grade (altitude + timing). Telescope integration ready.</div>";
      metricsEl.innerHTML = html;

      var caps = state.captures || [];
      if (!caps.length) {
        capsEl.innerHTML = "<span style=\"color:#888;\">No captures yet.</span>";
      } else {
        capsEl.innerHTML = "<div style=\"color:#aaa;margin-bottom:4px;\">Captures (" + caps.length + ")</div>" +
          caps.slice(-3).reverse().map(function (c) {
            return "<div>• " + (c.timeLocal || "—") + " — conf " + (c.confidence || 0) + "% — " + (c.recommendation || "—") + "</div>";
          }).join("");
      }
    } catch (e) {}
  }

  function loopTick() {
    try {
      if (!state.enabled) return;
      var now = Date.now();
      if (now - (state.lastRenderMs || 0) < 1000) return;
      state.lastRenderMs = now;
      renderPanel();
    } catch (e) {}
  }

  function ensureLoop() {
    try {
      if (window.__hilalLoop) return;
      window.__hilalLoop = setInterval(loopTick, 500);
    } catch (e) {}
  }

  // -----------------------------
  // Public API
  // -----------------------------
  window.HilalMode = {
    TelescopeConnector: TelescopeConnector,
    show: function () {
      try {
        state.enabled = true;
        ensureLoop();
        renderPanel();
      } catch (e) {}
    },
    hide: function () {
      try {
        state.enabled = false;
        renderPanel();
      } catch (e) {}
    },
    toggle: function () {
      try {
        state.enabled = !state.enabled;
        if (state.enabled) this.show();
        else this.hide();
      } catch (e) {}
    },
    connectTelescope: async function () {
      try {
        var r = await state.telescope.connect();
        if (typeof window.showToast === "function") {
          window.showToast(r.ok ? ("Telescope connected (" + (r.backend || "SIM") + ")") : ("Telescope connect failed"));
        }
        renderPanel();
      } catch (e) {}
    },
    slewToMoon: async function () {
      try {
        var lc = state.lastComputed;
        var az = lc && isFinite(lc.moonAz) ? lc.moonAz : null;
        var alt = lc && isFinite(lc.moonAlt) ? lc.moonAlt : null;
        var r = await state.telescope.slew_to_moon(az, alt);
        if (typeof window.showToast === "function") {
          window.showToast(r.ok ? "Slewing to Moon ✔" : "Slew failed");
        }
      } catch (e) {}
    },
    startTracking: async function () {
      try {
        var r = await state.telescope.start_tracking();
        if (typeof window.showToast === "function") {
          window.showToast(r.ok ? "Tracking started ✔" : "Tracking failed");
        }
      } catch (e) {}
    },
    captureImage: async function () {
      try {
        var cap = await state.telescope.capture_image();
        var lc = state.lastComputed || {};
        var now = new Date();
        var confidence = 0;
        try {
          confidence = isFinite(lc.probability) ? Math.max(0, Math.min(100, Math.round(lc.probability * 0.65))) : 0;
        } catch (e2) {}
        var recommendation = confidence >= 45 ? "Attempt visual confirmation" : "Hold / wait conditions";
        var entry = {
          ts: now.toISOString(),
          timeLocal: now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
          observer: { lat: lc.lat, lon: lc.lon },
          sunset: lc.sunset,
          windowStart: lc.windowStart,
          windowEnd: lc.windowEnd,
          moonAlt: lc.moonAlt,
          moonAz: lc.moonAz,
          modelProbability: lc.probability,
          confidence: confidence,
          recommendation: recommendation,
          operatorNote: "",
          imageRef: cap && cap.imageRef ? cap.imageRef : null
        };
        state.captures.push(entry);
        if (typeof window.showToast === "function") {
          window.showToast(cap && cap.ok ? "Capture saved ✔" : "Capture saved (offline)");
        }
        renderPanel();
      } catch (e) {}
    },
    openReport: function () {
      try {
        var lc = state.lastComputed || {};
        var caps = state.captures || [];
        var w = window.open("", "_blank");
        if (!w) return;
        var now = new Date();
        var conclusion = "Insufficient confidence — continue monitoring.";
        try {
          if (lc.status === "FAVORABLE") conclusion = "Favorable conditions — proceed with observation and confirmation.";
          else if (lc.status === "POSSIBLE") conclusion = "Possible conditions — attempt observation with experienced operator.";
        } catch (e2) {}
        var html = "";
        html += "<html><head><title>AstroScan-Chohra Hilal Report</title>";
        html += "<meta charset='utf-8'/>";
        html += "<style>body{font-family:Arial;background:#05070c;color:#e8f4fa;padding:18px}h1{color:#ffd166}h2{color:#00ffcc}table{width:100%;border-collapse:collapse;margin-top:10px}td,th{border:1px solid rgba(255,255,255,.12);padding:8px;font-size:12px}small{color:#9bb0bd}</style>";
        html += "</head><body>";
        html += "<h1>AstroScan-Chohra — Hilal Observation Report</h1>";
        html += "<small>Generated: " + now.toISOString() + "</small>";
        html += "<h2>Summary</h2>";
        html += "<div><b>Location</b>: " + (isFinite(lc.lat) ? lc.lat.toFixed(3) : "—") + "°, " + (isFinite(lc.lon) ? lc.lon.toFixed(3) : "—") + "°</div>";
        html += "<div><b>Sunset</b>: " + (lc.sunset || "—") + "</div>";
        html += "<div><b>Observation window</b>: " + (lc.windowStart || "—") + " → " + (lc.windowEnd || "—") + "</div>";
        html += "<div><b>Moon</b>: alt " + (isFinite(lc.moonAlt) ? lc.moonAlt.toFixed(1) + "°" : "—") + ", az " + (isFinite(lc.moonAz) ? lc.moonAz.toFixed(1) + "°" : "—") + "</div>";
        html += "<div><b>Visibility probability</b>: " + (isFinite(lc.probability) ? lc.probability + "%" : "—") + " — <b>Status</b>: " + (lc.status || "—") + "</div>";
        html += "<div><b>Telescope status</b>: " + (state.telescope.connected ? ("CONNECTED (" + state.telescope.backend + ")") : "DISCONNECTED") + "</div>";
        html += "<h2>Captures</h2>";
        if (!caps.length) {
          html += "<div>No captures recorded.</div>";
        } else {
          html += "<table><thead><tr><th>Timestamp</th><th>Alt</th><th>Az</th><th>Model</th><th>Confidence</th><th>Recommendation</th><th>Image ref</th></tr></thead><tbody>";
          caps.forEach(function (c) {
            html += "<tr>";
            html += "<td>" + (c.ts || "—") + "</td>";
            html += "<td>" + (isFinite(c.moonAlt) ? c.moonAlt.toFixed(1) + "°" : "—") + "</td>";
            html += "<td>" + (isFinite(c.moonAz) ? c.moonAz.toFixed(1) + "°" : "—") + "</td>";
            html += "<td>" + (isFinite(c.modelProbability) ? c.modelProbability + "%" : "—") + "</td>";
            html += "<td>" + (isFinite(c.confidence) ? c.confidence + "%" : "—") + "</td>";
            html += "<td>" + (c.recommendation || "—") + "</td>";
            html += "<td>" + (c.imageRef || "—") + "</td>";
            html += "</tr>";
          });
          html += "</tbody></table>";
        }
        html += "<h2>Conclusion</h2>";
        html += "<div>" + conclusion + "</div>";
        html += "<small style='display:block;margin-top:12px;'>Note: This phase uses a demo-grade model. Future phases will add Alpaca/INDI control and image-based crescent detection.</small>";
        html += "</body></html>";
        w.document.open();
        w.document.write(html);
        w.document.close();
      } catch (e) {}
    }
  };

  // Auto-init (safe)
  try { ensureLoop(); } catch (e) {}
})();

