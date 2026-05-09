/* SCAN A SIGNAL — telemetry HUD renderer. */
(function (global) {
  "use strict";

  var I18N = {
    fr: {
      target_locked: "CIBLE VERROUILLÉE",
      pos: "POSITION",
      lat: "LAT", lon: "LON", alt: "ALT",
      vel: "VÉLOCITÉ",
      speed: "VITESSE",
      orb: "ORBITE",
      period: "PÉRIODE", incl: "INCLIN.", ecc: "EXCEN.",
      reception: "RÉCEPTION ASTRO-SCAN",
      no_reception: "Aucune antenne en ligne directe.",
      oos_title: "CIBLE HORS LIGNE DE VISÉE",
      oos_body: "Le satellite est sous l'horizon de tous les observatoires (autre côté de la Terre).",
      oos_next: "Prochain passage Tlemcen",
      oos_no_pass: "Aucun passage prévu sous 24 h.",
      sight_label: "obs. en visée",
      next_pass: "PROCHAIN PASSAGE — TLEMCEN",
      no_pass: "Aucun passage prévu sous 24 h.",
      max_elev: "Élévation max.",
      duration: "Durée",
      source: "SOURCE",
      source_value: "Skyfield + NASA TLE",
      refreshed: "rafraîchi il y a",
      seconds_short: "s",
      track_continue: "TRACKER EN CONTINU",
      track_stop: "ARRÊTER TRACKING",
      new_scan: "NOUVEAU SCAN",
      tle_age: "TLE +",
      days: "j",
      space_station: "STATION SPATIALE",
      starlink: "STARLINK",
      oneweb: "ONEWEB",
      telescope: "TÉLESCOPE",
      weather: "MÉTÉO",
      navigation: "NAVIGATION",
      earth_observation: "OBS. TERRESTRE",
      debris: "DÉBRIS",
      military: "MILITAIRE",
      satellite: "SATELLITE",
      in: "dans",
      h: "h",
      m: "m",
      s: "s",
    },
    en: {
      target_locked: "TARGET LOCKED",
      pos: "POSITION",
      lat: "LAT", lon: "LON", alt: "ALT",
      vel: "VELOCITY",
      speed: "SPEED",
      orb: "ORBIT",
      period: "PERIOD", incl: "INCLIN.", ecc: "ECC.",
      reception: "ASTRO-SCAN RECEPTION",
      no_reception: "No antenna in direct line of sight.",
      oos_title: "ASSET CURRENTLY OUT OF SIGHT",
      oos_body: "The satellite is below the horizon of every observatory (far side of Earth).",
      oos_next: "Next pass over Tlemcen",
      oos_no_pass: "No pass within next 24 h.",
      sight_label: "obs in sight",
      next_pass: "NEXT PASS — TLEMCEN",
      no_pass: "No pass within next 24 h.",
      max_elev: "Max elevation",
      duration: "Duration",
      source: "SOURCE",
      source_value: "Skyfield + NASA TLE",
      refreshed: "refreshed",
      seconds_short: "s ago",
      track_continue: "TRACK CONTINUOUSLY",
      track_stop: "STOP TRACKING",
      new_scan: "NEW SCAN",
      tle_age: "TLE +",
      days: "d",
      space_station: "SPACE STATION",
      starlink: "STARLINK",
      oneweb: "ONEWEB",
      telescope: "TELESCOPE",
      weather: "WEATHER",
      navigation: "NAVIGATION",
      earth_observation: "EARTH OBS.",
      debris: "DEBRIS",
      military: "MILITARY",
      satellite: "SATELLITE",
      in: "in",
      h: "h",
      m: "m",
      s: "s",
    },
  };

  function t(lang, k) {
    return (I18N[lang] || I18N.fr)[k] || k;
  }

  function fmtSign(v, decimals, suffixPos, suffixNeg) {
    var n = Number(v);
    if (!isFinite(n)) return "—";
    var abs = Math.abs(n).toFixed(decimals);
    return abs + " " + (n >= 0 ? suffixPos : suffixNeg);
  }

  function fmtNumber(v, decimals) {
    var n = Number(v);
    if (!isFinite(n)) return "—";
    return n.toFixed(decimals).replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  }

  function fmtDurationSec(s) {
    s = Math.max(0, Math.floor(Number(s) || 0));
    var m = Math.floor(s / 60);
    var r = s % 60;
    return m + "m " + r + "s";
  }

  function fmtRelative(thenIso, lang) {
    if (!thenIso) return "";
    var then = new Date(thenIso).getTime();
    if (!isFinite(then)) return "";
    var now = Date.now();
    var diff = then - now;
    if (diff <= 0) return "—";
    var s = Math.floor(diff / 1000);
    var h = Math.floor(s / 3600);
    var m = Math.floor((s % 3600) / 60);
    var L = lang === "en" ? "in " : "dans ";
    if (h >= 1) return L + h + "h " + m + "m";
    if (m >= 1) return L + m + "m";
    return L + s + "s";
  }

  function categoryLabel(cat, lang) { return t(lang, cat); }

  function setVal(rowVal, newText) {
    if (rowVal.textContent !== newText) {
      rowVal.classList.remove("flash");
      // reflow to restart animation
      void rowVal.offsetWidth;
      rowVal.textContent = newText;
      rowVal.classList.add("flash");
    }
  }

  function renderHud(hudEl, state, lang, freshSec) {
    lang = lang || "fr";
    if (!state) return;

    var pos = state.position || {};
    var vel = state.velocity || {};
    var orb = state.orbit || {};
    var rec = state.antenna_reception || [];
    var pass = state.next_pass_tlemcen;

    // Build skeleton if first render
    if (!hudEl.dataset.built) {
      hudEl.innerHTML = ""
        + "<div class='ss-hud-header'>"
        +   "<span class='ss-hud-title' data-k='target_locked'></span>"
        +   "<button class='ss-hud-close' aria-label='close' data-action='close'>✕</button>"
        + "</div>"
        + "<div class='ss-hud-name-block'>"
        +   "<div class='ss-hud-name' data-bind='name'></div>"
        +   "<div class='ss-hud-sub' data-bind='sub'></div>"
        +   "<div class='ss-hud-tag' data-bind='tag'></div>"
        + "</div>"
        + "<div class='ss-hud-section ss-hud-rec-hero' data-section='rec'>"
        +   "<div class='ss-hud-section-title'>"
        +     "<span data-k='reception'></span>"
        +     "<span class='ss-sight-badge' data-bind='sight_badge'></span>"
        +   "</div>"
        +   "<div data-bind='reception'></div>"
        + "</div>"
        + "<div class='ss-hud-section' data-section='pos'>"
        +   "<div class='ss-hud-section-title' data-k='pos'></div>"
        +   "<div class='ss-hud-row'><span class='k' data-k='lat'></span><span class='v' data-bind='lat'></span></div>"
        +   "<div class='ss-hud-row'><span class='k' data-k='lon'></span><span class='v' data-bind='lon'></span></div>"
        +   "<div class='ss-hud-row'><span class='k' data-k='alt'></span><span class='v' data-bind='alt'></span></div>"
        + "</div>"
        + "<div class='ss-hud-section' data-section='vel'>"
        +   "<div class='ss-hud-section-title' data-k='vel'></div>"
        +   "<div class='ss-hud-row'><span class='k' data-k='speed'></span><span class='v' data-bind='speed'></span></div>"
        + "</div>"
        + "<div class='ss-hud-section' data-section='orb'>"
        +   "<div class='ss-hud-section-title' data-k='orb'></div>"
        +   "<div class='ss-hud-row'><span class='k' data-k='period'></span><span class='v' data-bind='period'></span></div>"
        +   "<div class='ss-hud-row'><span class='k' data-k='incl'></span><span class='v' data-bind='incl'></span></div>"
        +   "<div class='ss-hud-row'><span class='k' data-k='ecc'></span><span class='v' data-bind='ecc'></span></div>"
        + "</div>"
        + "<div class='ss-hud-section' data-section='pass'>"
        +   "<div class='ss-hud-section-title' data-k='next_pass'></div>"
        +   "<div data-bind='pass'></div>"
        + "</div>"
        + "<div class='ss-hud-source'>"
        +   "<span data-k='source'></span><span class='sep' style='margin:0 6px'>·</span>"
        +   "<span data-bind='source_val'></span>"
        +   "<span class='live-dot'></span>"
        + "</div>"
        + "<div class='ss-hud-actions'>"
        +   "<button class='ss-btn cyan' data-action='track-toggle'></button>"
        +   "<button class='ss-btn ghost' data-action='new-scan'></button>"
        + "</div>";
      hudEl.dataset.built = "1";
    }

    // Apply i18n labels (static)
    hudEl.querySelectorAll("[data-k]").forEach(function (el) {
      el.textContent = t(lang, el.getAttribute("data-k"));
    });

    // Bind dynamic values
    var name = state.name || "—";
    var noradPart = "NORAD " + (state.norad_id || "—");
    var subParts = [noradPart];
    if (typeof state.tle_age_days === "number" && isFinite(state.tle_age_days)) {
      subParts.push(t(lang, "tle_age") + state.tle_age_days.toFixed(1) + " " + t(lang, "days"));
    }

    var nameEl = hudEl.querySelector("[data-bind='name']");
    var subEl  = hudEl.querySelector("[data-bind='sub']");
    var tagEl  = hudEl.querySelector("[data-bind='tag']");
    if (nameEl.textContent !== name) nameEl.textContent = name;
    subEl.textContent = subParts.join("  ·  ");
    tagEl.textContent = categoryLabel(state.category || "satellite", lang);

    setVal(hudEl.querySelector("[data-bind='lat']"),  fmtSign(pos.latitude,  4, "°N", "°S"));
    setVal(hudEl.querySelector("[data-bind='lon']"),  fmtSign(pos.longitude, 4, "°E", "°W"));
    setVal(hudEl.querySelector("[data-bind='alt']"),  fmtNumber(pos.altitude_km, 1) + " km");
    setVal(hudEl.querySelector("[data-bind='speed']"),
      fmtNumber(vel.kms, 2) + " km/s  (" + fmtNumber(vel.kmh, 0) + " km/h)");
    setVal(hudEl.querySelector("[data-bind='period']"), fmtNumber(orb.period_minutes, 1) + " min");
    setVal(hudEl.querySelector("[data-bind='incl']"),   fmtNumber(orb.inclination_deg, 2) + "°");
    setVal(hudEl.querySelector("[data-bind='ecc']"),    fmtNumber(orb.eccentricity, 4));

    // FIX 6 — In-sight badge "X/12"
    var inSight = (typeof state.in_sight_count === "number") ? state.in_sight_count : rec.length;
    var totalObs = (typeof state.observatories_total === "number") ? state.observatories_total : 12;
    var sightBadge = hudEl.querySelector("[data-bind='sight_badge']");
    if (sightBadge) {
      sightBadge.innerHTML = "<span class='ss-sight-num'>" + inSight + "</span>"
        + "<span class='ss-sight-sep'>/</span>"
        + "<span class='ss-sight-total'>" + totalObs + "</span>"
        + "<span class='ss-sight-lbl'>" + t(lang, "sight_label") + "</span>";
      sightBadge.classList.toggle("none", inSight === 0);
    }

    // FIX 5 — Out-of-sight gracieux when no antennas in line of sight
    var recHost = hudEl.querySelector("[data-bind='reception']");
    if (!rec.length) {
      recHost.innerHTML = renderOutOfSight(pass, lang);
    } else {
      var html = "";
      rec.forEach(function (a) {
        html += "<div class='ss-hud-antenna'>"
          + "<div class='a-name'>" + escapeHtml(a.antenna_name || a.antenna_id) + "</div>"
          + "<div class='a-data'>"
          +   "<span>" + fmtNumber(a.distance_km, 0) + " km</span>"
          +   "<span>" + fmtNumber(a.elevation_deg, 1) + "°</span>"
          +   "<span>" + fmtNumber(a.rssi_dbm, 1) + " dBm</span>"
          +   "<span class='quality " + escapeHtml(a.quality || "") + "'>" + escapeHtml(a.quality || "") + "</span>"
          + "</div>"
        + "</div>";
      });
      recHost.innerHTML = html;
    }

    // Pass info
    var passHost = hudEl.querySelector("[data-bind='pass']");
    if (!pass) {
      passHost.innerHTML = "<div class='ss-hud-empty'>" + t(lang, "no_pass") + "</div>";
    } else {
      var rise = (pass.rise_time_utc || "").replace("T", " ").replace("Z", " UTC");
      passHost.innerHTML = ""
        + "<div class='ss-hud-row'><span class='k'>" + t(lang, "max_elev") + "</span>"
        +   "<span class='v'>" + fmtNumber(pass.max_elevation_deg, 1) + "°</span></div>"
        + "<div class='ss-hud-row'><span class='k'>" + t(lang, "duration") + "</span>"
        +   "<span class='v'>" + fmtDurationSec(pass.duration_seconds) + "</span></div>"
        + "<div class='ss-hud-row'><span class='k'>UTC</span>"
        +   "<span class='v'>" + escapeHtml(rise) + "<span class='sub'>" + fmtRelative(pass.rise_time_utc, lang) + "</span></span></div>";
    }

    // Source line
    var srcVal = hudEl.querySelector("[data-bind='source_val']");
    var freshTxt = (typeof freshSec === "number" ? freshSec : 0) + (lang === "en" ? "s ago" : "s");
    srcVal.textContent = t(lang, "source_value") + "  ·  " + (lang === "en" ? "refreshed " : "rafraîchi il y a ") + freshTxt;

    // Track button label
    var btn = hudEl.querySelector("[data-action='track-toggle']");
    btn.textContent = hudEl.dataset.tracking === "1"
      ? t(lang, "track_stop")
      : t(lang, "track_continue");

    var newScanBtn = hudEl.querySelector("[data-action='new-scan']");
    newScanBtn.textContent = t(lang, "new_scan");
  }

  function renderOutOfSight(pass, lang) {
    var out = "<div class='ss-out-of-sight'>"
      + "<div class='ss-oos-icon'>⚠</div>"
      + "<div class='ss-oos-title'>" + t(lang, "oos_title") + "</div>"
      + "<div class='ss-oos-body'>" + t(lang, "oos_body") + "</div>";
    if (pass && pass.rise_time_utc) {
      var rise = (pass.rise_time_utc || "").replace("T", " ").replace("Z", " UTC");
      out += "<div class='ss-oos-next'>"
        + "<strong>" + t(lang, "oos_next") + "</strong>"
        + "<span>" + escapeHtml(rise) + " <span class='sub'>" + fmtRelative(pass.rise_time_utc, lang) + "</span></span>"
        + "<span>" + (lang === "en" ? "Max elevation: " : "Élévation max. : ") + fmtNumber(pass.max_elevation_deg, 1) + "°</span>"
        + "<span>" + (lang === "en" ? "Duration: " : "Durée : ") + fmtDurationSec(pass.duration_seconds) + "</span>"
      + "</div>";
    } else {
      out += "<div class='ss-oos-next'><span class='sub'>" + t(lang, "oos_no_pass") + "</span></div>";
    }
    out += "</div>";
    return out;
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"})[c];
    });
  }

  global.SSRender = {
    renderHud: renderHud,
    t: t,
  };
})(window);
