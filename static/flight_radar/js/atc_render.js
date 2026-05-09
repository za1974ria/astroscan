/* FLIGHT RADAR — ATC HUD renderer.
   Phosphor-green tower-control panel for the selected aircraft.
   Same renderHud() pattern as scan_signal/vessel_render.js.
*/
(function (global) {
  "use strict";

  var I18N = {
    fr: {
      algo7_title: "ALGO-7 · FIABILITÉ ADS-B",
      algo7_freshness: "POSITION FRAÎCHEUR",
      algo7_integrity: "INTÉGRITÉ ADS-B",
      algo7_alt_coh: "COHÉRENCE ALTITUDE",
      algo7_track_dur: "DURÉE DE TRACKING",
      algo7_dest_title: "ROUTE & DESTINATION — ALGO-7",
      algo7_dest_confidence_unit: "% confiance",
      algo7_dest_level1: "🟢 NIVEAU 1 — PLAN DE VOL DÉPOSÉ",
      algo7_dest_level2: "🟡 NIVEAU 2 — INFÉRENCE COMPAGNIE",
      algo7_dest_level3: "🟡 NIVEAU 3 — MULTI-LAYER",
      algo7_dest_level4: "🟠 NIVEAU 4 — CONVERGENCE FORTE",
      algo7_dest_level0: "⚪ NIVEAU 0 — DONNÉES INSUFFISANTES",
      algo7_layers: "ANALYSE 7 LAYERS",
      algo7_alternatives: "ALTERNATIVES",
      algo7_progress: "PROGRESSION VOL",
      algo7_sources: "Sources",
      algo7_eta: "ETA",
      algo7_no_dest: "Destination indéterminée — données partielles",
      l1_label: "Plan de vol",
      l2_label: "Compagnie",
      l3_label: "Cohérence géo",
      l4_label: "Type",
      l5_label: "Couloir",
      l6_label: "Jet stream",
      l7_label: "Projection",
      target_locked: "AVION VERROUILLÉ",
      identification: "IDENTIFICATION",
      callsign: "CALLSIGN",
      icao24: "ICAO24",
      squawk: "SQUAWK",
      flag: "PAVILLON",
      altitude: "ALTITUDE",
      baro_alt: "BARO ALT",
      geo_alt: "GEO ALT",
      flight_level: "NIVEAU",
      vario: "VARIO",
      kinematics: "CINÉMATIQUE",
      gs: "VITESSE FOND",
      track: "CAP",
      on_ground: "AU SOL",
      yes: "OUI", no: "NON",
      position: "POSITION",
      lat: "LAT", lon: "LON",
      last_contact: "DERN. CONTACT",
      tracked_for: "TRACKÉ DEPUIS",
      source: "SOURCE",
      source_value: "OpenSky · ADS-B",
      refreshed: "rafraîchi il y a",
      seconds_short: "s",
      track_continue: "TRACKER EN CONTINU",
      track_stop: "ARRÊTER TRACKING",
      new_scan: "NOUVELLE ACQUISITION",
      emergency: "EMERG",
      hijack: "HIJACK",
      radio_fail: "NO-RDO",
    },
    en: {
      algo7_title: "ALGO-7 · ADS-B RELIABILITY",
      algo7_freshness: "POSITION FRESHNESS",
      algo7_integrity: "ADS-B INTEGRITY",
      algo7_alt_coh: "ALTITUDE COHERENCE",
      algo7_track_dur: "TRACKING DURATION",
      algo7_dest_title: "ROUTE & DESTINATION — ALGO-7",
      algo7_dest_confidence_unit: "% confidence",
      algo7_dest_level1: "🟢 LEVEL 1 — FILED FLIGHT PLAN",
      algo7_dest_level2: "🟡 LEVEL 2 — CARRIER INFERENCE",
      algo7_dest_level3: "🟡 LEVEL 3 — MULTI-LAYER",
      algo7_dest_level4: "🟠 LEVEL 4 — STRONG CONVERGENCE",
      algo7_dest_level0: "⚪ LEVEL 0 — INSUFFICIENT DATA",
      algo7_layers: "7-LAYER ANALYSIS",
      algo7_alternatives: "ALTERNATIVES",
      algo7_progress: "FLIGHT PROGRESS",
      algo7_sources: "Sources",
      algo7_eta: "ETA",
      algo7_no_dest: "Destination undetermined — partial data",
      l1_label: "Flight plan",
      l2_label: "Carrier",
      l3_label: "Geo coherence",
      l4_label: "Type",
      l5_label: "Airway",
      l6_label: "Jet stream",
      l7_label: "Projection",
      target_locked: "AIRCRAFT LOCKED",
      identification: "IDENTIFICATION",
      callsign: "CALLSIGN",
      icao24: "ICAO24",
      squawk: "SQUAWK",
      flag: "FLAG STATE",
      altitude: "ALTITUDE",
      baro_alt: "BARO ALT",
      geo_alt: "GEO ALT",
      flight_level: "LEVEL",
      vario: "VARIO",
      kinematics: "KINEMATICS",
      gs: "GROUND SPEED",
      track: "TRACK",
      on_ground: "ON GROUND",
      yes: "YES", no: "NO",
      position: "POSITION",
      lat: "LAT", lon: "LON",
      last_contact: "LAST CONTACT",
      tracked_for: "TRACKED FOR",
      source: "SOURCE",
      source_value: "OpenSky · ADS-B",
      refreshed: "refreshed",
      seconds_short: "s ago",
      track_continue: "TRACK CONTINUOUSLY",
      track_stop: "STOP TRACKING",
      new_scan: "NEW ACQUISITION",
      emergency: "EMERG",
      hijack: "HIJACK",
      radio_fail: "NO-RDO",
    },
  };

  function t(lang, k) {
    return (I18N[lang] || I18N.fr)[k] || k;
  }

  function fmtNum(v, decimals) {
    var n = Number(v);
    if (!isFinite(n)) return "—";
    return n.toFixed(decimals).replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  }

  function fmtSign(v, decimals, suffixPos, suffixNeg) {
    var n = Number(v);
    if (!isFinite(n)) return "—";
    return Math.abs(n).toFixed(decimals) + " " + (n >= 0 ? suffixPos : suffixNeg);
  }

  function fmtAltitude(meters) {
    var n = Number(meters);
    if (!isFinite(n)) return "—";
    var fl = Math.round((n * 3.28084) / 100);
    return fmtNum(Math.round(n), 0) + " m / FL" + String(fl).padStart(3, "0");
  }

  function fmtVelocity(mps) {
    var n = Number(mps);
    if (!isFinite(n)) return "—";
    var kmh = n * 3.6;
    return fmtNum(n.toFixed(0), 0) + " m/s · " + fmtNum(kmh.toFixed(0), 0) + " km/h";
  }

  function fmtVario(mps) {
    var n = Number(mps);
    if (!isFinite(n)) return "—";
    var fpm = n * 196.85;
    var sign = fpm >= 0 ? "▲" : "▼";
    return sign + " " + fmtNum(Math.round(Math.abs(fpm)), 0) + " ft/min";
  }

  function fmtAngle(v) {
    var n = Number(v);
    if (!isFinite(n)) return "—";
    return n.toFixed(0).padStart(3, "0") + "°";
  }

  function fmtAge(ts) {
    if (!ts) return "—";
    var n = Math.max(0, Math.round(Date.now() / 1000 - Number(ts)));
    if (n < 60) return n + " s";
    if (n < 3600) return Math.round(n / 60) + " min";
    return Math.round(n / 3600) + " h";
  }

  function fmtDuration(firstSeen) {
    if (!firstSeen) return "—";
    var n = Math.max(0, Math.round(Date.now() / 1000 - Number(firstSeen)));
    if (n < 60) return n + " s";
    if (n < 3600) {
      var m = Math.floor(n / 60), s = n % 60;
      return m + " min " + s + "s";
    }
    var h = Math.floor(n / 3600), mm = Math.floor((n % 3600) / 60);
    return h + "h " + mm + "min";
  }

  function setVal(rowVal, newText) {
    if (rowVal && rowVal.textContent !== newText) {
      rowVal.classList.remove("flash");
      void rowVal.offsetWidth;
      rowVal.textContent = newText;
      rowVal.classList.add("flash");
    }
  }

  function squawkLabel(sq, lang) {
    if (!sq) return "—";
    if (sq === "7500") return sq + " · " + t(lang, "hijack");
    if (sq === "7600") return sq + " · " + t(lang, "radio_fail");
    if (sq === "7700") return sq + " · " + t(lang, "emergency");
    return sq;
  }

  // ALGO-7: aggregate ADS-B reliability score (0-100), computed from 4 axes.
  function clamp01(n) { return Math.max(0, Math.min(1, n)); }
  function computeAlgo7(state) {
    var nowSec = Date.now() / 1000;

    // 1) POSITION FRESHNESS — based on age of last_contact.
    //    100 if <5s, 0 if >300s, linear decay between.
    var lc = Number(state.last_contact);
    var ageSec = isFinite(lc) ? Math.max(0, nowSec - lc) : 999;
    var freshness = clamp01(1 - (ageSec - 5) / 295);

    // 2) ADS-B INTEGRITY — squawk validity + non-zero kinematics + sane lat/lon.
    var integrityHits = 0;
    var integrityMax = 4;
    if (state.squawk && /^[0-7]{4}$/.test(state.squawk)) integrityHits++;
    if (isFinite(state.velocity) && state.velocity > 0) integrityHits++;
    if (isFinite(state.true_track)) integrityHits++;
    if (isFinite(state.lat) && Math.abs(state.lat) <= 90 && isFinite(state.lon) && Math.abs(state.lon) <= 180) integrityHits++;
    var integrity = integrityHits / integrityMax;

    // 3) ALTITUDE COHERENCE — baro vs geo difference (typical <300 m).
    var baro = Number(state.baro_altitude);
    var geo = Number(state.geo_altitude);
    var altCoh;
    if (state.on_ground) {
      altCoh = 1.0;
    } else if (isFinite(baro) && isFinite(geo)) {
      var diff = Math.abs(baro - geo);
      altCoh = clamp01(1 - (diff - 50) / 600);
    } else if (isFinite(baro) || isFinite(geo)) {
      altCoh = 0.6;
    } else {
      altCoh = 0.2;
    }

    // 4) TRACKING DURATION — confidence grows with continuous tracking.
    //    0 at 0s, 1 at 600s (10 min) plateau.
    var fs = Number(state.first_seen);
    var trackDur = isFinite(fs) ? clamp01((nowSec - fs) / 600) : 0;
    var trackDurSec = isFinite(fs) ? Math.max(0, nowSec - fs) : 0;

    var weights = { freshness: 0.35, integrity: 0.30, altCoh: 0.20, trackDur: 0.15 };
    var score = (
      weights.freshness * freshness +
      weights.integrity * integrity +
      weights.altCoh * altCoh +
      weights.trackDur * trackDur
    ) * 100;

    return {
      score: Math.round(score),
      axes: [
        { key: "freshness", labelKey: "algo7_freshness",
          value: ageSec.toFixed(0) + " s", pct: freshness * 100 },
        { key: "integrity", labelKey: "algo7_integrity",
          value: integrityHits + "/" + integrityMax, pct: integrity * 100 },
        { key: "alt_coh", labelKey: "algo7_alt_coh",
          value: (state.on_ground ? "GND" :
                  (isFinite(baro) && isFinite(geo)
                    ? "Δ " + Math.abs(baro - geo).toFixed(0) + " m"
                    : "—")),
          pct: altCoh * 100 },
        { key: "track_dur", labelKey: "algo7_track_dur",
          value: (trackDurSec >= 60
                    ? Math.floor(trackDurSec / 60) + " min"
                    : trackDurSec.toFixed(0) + " s"),
          pct: trackDur * 100 },
      ],
    };
  }

  function levelClass(pct) {
    if (pct >= 75) return "high";
    if (pct < 35) return "low";
    return "";
  }

  function renderHud(hudEl, state, lang, freshSec) {
    lang = lang || "fr";
    if (!state) return;

    if (!hudEl.dataset.built) {
      hudEl.innerHTML = ""
        + "<div class='atc-hud-header'>"
        +   "<span class='atc-hud-title' data-k='target_locked'></span>"
        +   "<button class='atc-hud-close' aria-label='close' data-action='close'>✕</button>"
        + "</div>"
        + "<div class='atc-hud-name-block'>"
        +   "<div class='atc-hud-callsign' data-bind='callsign'></div>"
        +   "<div class='atc-hud-sub' data-bind='sub'></div>"
        +   "<div class='atc-hud-flag' data-bind='flag' style='display:none'></div>"
        + "</div>"
        + "<div class='atc-hud-section'>"
        +   "<div class='atc-hud-section-title' data-k='identification'></div>"
        +   "<div class='atc-hud-row'><span class='k' data-k='icao24'></span><span class='v' data-bind='icao24'></span></div>"
        +   "<div class='atc-hud-row' data-row='squawk-row'><span class='k' data-k='squawk'></span><span class='v' data-bind='squawk'></span></div>"
        + "</div>"
        + "<div class='atc-algo7' data-section='algo7'>"
        +   "<div class='atc-algo7-header'>"
        +     "<span class='atc-algo7-title' data-k='algo7_title'></span>"
        +     "<span class='atc-algo7-score' data-bind='algo7_score'><span class='val'>—</span><span class='unit'>/100</span></span>"
        +   "</div>"
        +   "<div class='atc-algo7-grid' data-bind='algo7_grid'></div>"
        + "</div>"
        + "<div class='atc-algo7-dest' data-section='algo7_dest' style='display:none'></div>"
        + "<div class='atc-hud-section'>"
        +   "<div class='atc-hud-section-title' data-k='altitude'></div>"
        +   "<div class='atc-hud-row'><span class='k' data-k='baro_alt'></span><span class='v' data-bind='baro_alt'></span></div>"
        +   "<div class='atc-hud-row'><span class='k' data-k='geo_alt'></span><span class='v' data-bind='geo_alt'></span></div>"
        +   "<div class='atc-hud-row'><span class='k' data-k='vario'></span><span class='v' data-bind='vario'></span></div>"
        + "</div>"
        + "<div class='atc-hud-section'>"
        +   "<div class='atc-hud-section-title' data-k='kinematics'></div>"
        +   "<div class='atc-hud-row'><span class='k' data-k='gs'></span><span class='v' data-bind='gs'></span></div>"
        +   "<div class='atc-hud-row'><span class='k' data-k='track'></span><span class='v' data-bind='trk'></span></div>"
        +   "<div class='atc-hud-row'><span class='k' data-k='on_ground'></span><span class='v' data-bind='gnd'></span></div>"
        + "</div>"
        + "<div class='atc-hud-section'>"
        +   "<div class='atc-hud-section-title' data-k='position'></div>"
        +   "<div class='atc-hud-row'><span class='k' data-k='lat'></span><span class='v' data-bind='lat'></span></div>"
        +   "<div class='atc-hud-row'><span class='k' data-k='lon'></span><span class='v' data-bind='lon'></span></div>"
        +   "<div class='atc-hud-row'><span class='k' data-k='last_contact'></span><span class='v' data-bind='last_contact'></span></div>"
        +   "<div class='atc-hud-row' data-row='tracked'><span class='k' data-k='tracked_for'></span><span class='v' data-bind='tracked'></span></div>"
        + "</div>"
        + "<div class='atc-hud-source'>"
        +   "<span data-k='source'></span><span style='margin:0 6px'>·</span>"
        +   "<span data-bind='source_val'></span>"
        +   "<span class='live-dot'></span>"
        + "</div>"
        + "<div class='atc-hud-actions'>"
        +   "<button class='atc-btn' data-action='track-toggle'></button>"
        +   "<button class='atc-btn ghost' data-action='new-scan'></button>"
        + "</div>";
      hudEl.dataset.built = "1";
    }

    // Static labels
    hudEl.querySelectorAll("[data-k]").forEach(function (el) {
      el.textContent = t(lang, el.getAttribute("data-k"));
    });

    var callsign = state.callsign || "—";
    var icao24 = (state.icao24 || "").toUpperCase();
    setVal(hudEl.querySelector("[data-bind='callsign']"), callsign || icao24 || "—");
    var subEl = hudEl.querySelector("[data-bind='sub']");
    if (subEl) {
      var sub = "ICAO24 " + icao24;
      if (state.origin_country) sub += " · " + state.origin_country;
      subEl.textContent = sub;
    }

    // Flag
    var flagEl = hudEl.querySelector("[data-bind='flag']");
    if (flagEl) {
      if (state.country && state.country.flag) {
        var name = lang === "en" ? (state.country.name_en || state.country.name_fr) : (state.country.name_fr || state.country.name_en);
        flagEl.innerHTML = "<span class='atc-hud-flag-emoji'>" + escapeHtml(state.country.flag) + "</span>"
          + "<span>" + escapeHtml(name || state.country.iso || "") + "</span>";
        flagEl.style.display = "";
      } else {
        flagEl.style.display = "none";
      }
    }

    // Identification
    setVal(hudEl.querySelector("[data-bind='icao24']"), icao24 || "—");
    var sqEl = hudEl.querySelector("[data-bind='squawk']");
    var sqRow = hudEl.querySelector("[data-row='squawk-row']");
    if (sqEl) {
      var sq = state.squawk || "";
      sqEl.innerHTML = squawkLabel(sq, lang) || "—";
      if (sqRow) {
        sqRow.classList.toggle("urgent", sq === "7500" || sq === "7600" || sq === "7700");
      }
    }

    // ALGO-7 reliability gauges
    renderAlgo7(hudEl, state, lang);

    // ALGO-7 destination prediction (only if backend supplied algo7 data)
    renderAlgo7Destination(hudEl, state.algo7, lang);

    // Altitude
    setVal(hudEl.querySelector("[data-bind='baro_alt']"), fmtAltitude(state.baro_altitude));
    setVal(hudEl.querySelector("[data-bind='geo_alt']"), fmtAltitude(state.geo_altitude));
    setVal(hudEl.querySelector("[data-bind='vario']"), fmtVario(state.vertical_rate));

    // Kinematics
    setVal(hudEl.querySelector("[data-bind='gs']"), fmtVelocity(state.velocity));
    setVal(hudEl.querySelector("[data-bind='trk']"), fmtAngle(state.true_track));
    setVal(hudEl.querySelector("[data-bind='gnd']"),
      state.on_ground ? t(lang, "yes") : t(lang, "no"));

    // Position
    setVal(hudEl.querySelector("[data-bind='lat']"), fmtSign(state.lat, 5, "°N", "°S"));
    setVal(hudEl.querySelector("[data-bind='lon']"), fmtSign(state.lon, 5, "°E", "°W"));
    setVal(hudEl.querySelector("[data-bind='last_contact']"), fmtAge(state.last_contact));

    // Tracked-for
    var trackedEl = hudEl.querySelector("[data-bind='tracked']");
    var trackedRow = hudEl.querySelector("[data-row='tracked']");
    if (state.first_seen) {
      if (trackedRow) trackedRow.style.display = "";
      setVal(trackedEl, fmtDuration(state.first_seen));
    } else if (trackedRow) {
      trackedRow.style.display = "none";
    }

    // Source line
    var srcVal = hudEl.querySelector("[data-bind='source_val']");
    if (srcVal) {
      var freshTxt = (typeof freshSec === "number" ? freshSec : 0) + (lang === "en" ? "s ago" : "s");
      srcVal.textContent = t(lang, "source_value") + "  ·  " + (lang === "en" ? "refreshed " : "rafraîchi il y a ") + freshTxt;
    }

    // Buttons
    var trackBtn = hudEl.querySelector("[data-action='track-toggle']");
    if (trackBtn) {
      trackBtn.textContent = hudEl.dataset.tracking === "1" ? t(lang, "track_stop") : t(lang, "track_continue");
    }
    var newBtn = hudEl.querySelector("[data-action='new-scan']");
    if (newBtn) newBtn.textContent = t(lang, "new_scan");
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"})[c];
    });
  }

  function renderAlgo7(hudEl, state, lang) {
    var sec = hudEl.querySelector("[data-section='algo7']");
    if (!sec) return;
    var algo = computeAlgo7(state);

    // Title
    var titleEl = sec.querySelector("[data-k='algo7_title']");
    if (titleEl) titleEl.textContent = t(lang, "algo7_title");

    // Score
    var scoreWrap = sec.querySelector("[data-bind='algo7_score']");
    if (scoreWrap) {
      var valEl = scoreWrap.querySelector(".val");
      if (valEl) {
        var newScore = String(algo.score);
        if (valEl.textContent !== newScore) {
          valEl.textContent = newScore;
          valEl.classList.remove("flash");
          void valEl.offsetWidth;
          valEl.classList.add("flash");
        }
      }
    }

    // Grid (build once, then update)
    var grid = sec.querySelector("[data-bind='algo7_grid']");
    if (!grid) return;
    if (!grid.dataset.built) {
      var html = "";
      algo.axes.forEach(function (ax) {
        html += ""
          + "<div class='atc-algo7-item' data-axis='" + ax.key + "'>"
          +   "<div class='atc-algo7-label' data-bind='label'></div>"
          +   "<div class='atc-algo7-value' data-bind='value'>—</div>"
          +   "<div class='atc-algo7-bar'>"
          +     "<div class='atc-algo7-bar-fill' data-bind='fill' style='--fr-algo7-pct:0%'></div>"
          +   "</div>"
          + "</div>";
      });
      grid.innerHTML = html;
      grid.dataset.built = "1";
    }
    algo.axes.forEach(function (ax) {
      var item = grid.querySelector("[data-axis='" + ax.key + "']");
      if (!item) return;
      var lab = item.querySelector("[data-bind='label']");
      var val = item.querySelector("[data-bind='value']");
      var fill = item.querySelector("[data-bind='fill']");
      if (lab) lab.textContent = t(lang, ax.labelKey);
      if (val && val.textContent !== ax.value) {
        val.textContent = ax.value;
      }
      if (fill) {
        var pct = Math.max(0, Math.min(100, ax.pct));
        fill.style.setProperty("--fr-algo7-pct", pct.toFixed(0) + "%");
        fill.classList.remove("low", "high");
        var lvl = levelClass(pct);
        if (lvl) fill.classList.add(lvl);
      }
    });
  }

  function flagEmoji(iso) {
    if (!iso || iso.length !== 2) return "";
    var A = 0x1F1E6;
    var ord = function (c) { return c.charCodeAt(0) - 65; };
    return String.fromCodePoint(A + ord(iso[0])) + String.fromCodePoint(A + ord(iso[1]));
  }

  function fmtETA(minutes) {
    if (minutes == null || !isFinite(minutes)) return "—";
    var m = Math.max(0, Math.round(minutes));
    if (m < 60) return m + " min";
    var h = Math.floor(m / 60);
    var mm = m % 60;
    return h + "h " + (mm < 10 ? "0" : "") + mm + "min";
  }

  function levelLabel(lang, level) {
    if (level === 1) return t(lang, "algo7_dest_level1");
    if (level === 2) return t(lang, "algo7_dest_level2");
    if (level === 3) return t(lang, "algo7_dest_level3");
    if (level >= 4) return t(lang, "algo7_dest_level4");
    return t(lang, "algo7_dest_level0");
  }

  function renderAlgo7Destination(hudEl, algo, lang) {
    var sec = hudEl.querySelector("[data-section='algo7_dest']");
    if (!sec) return;
    if (!algo) {
      sec.style.display = "none";
      return;
    }
    sec.style.display = "";
    var lvl = Number(algo.level_used) || 0;
    var conf = Math.round((Number(algo.confidence_global) || 0) * 100);

    var primary = algo.primary_destination;
    var primaryHtml = "";
    if (primary && primary.icao) {
      var name = lang === "en" ? (primary.name_en || primary.name_fr) : (primary.name_fr || primary.name_en);
      var flag = flagEmoji(primary.country_iso || "");
      primaryHtml = ""
        + "<div class='atc-algo7-dest-primary'>"
        +   "<div class='dest-iata'>🛬 " + escapeHtml(primary.iata || primary.icao) + "</div>"
        +   "<div class='dest-name'>" + escapeHtml(name || "") + " " + flag + "</div>"
        +   "<div class='dest-prob'>" + (lang === "en" ? "Probability: " : "Probabilité : ")
        +     Math.round((primary.prob || 0) * 100) + "%</div>"
        +   (primary.eta_minutes != null
              ? "<div class='dest-eta'>" + t(lang, "algo7_eta") + " ~" + fmtETA(primary.eta_minutes) + "</div>"
              : "")
        + "</div>";
    } else {
      primaryHtml = "<div class='atc-algo7-dest-primary'><div class='dest-name'>" + escapeHtml(t(lang, "algo7_no_dest")) + "</div></div>";
    }

    var lr = algo.layer_results || {};
    function layerLine(lkey, label, available, detail) {
      var icon = available ? "✓" : "✗";
      var cls = available ? "" : " unavailable";
      return "<div class='dest-layer" + cls + "' data-layer='" + lkey + "'>"
        + icon + " " + escapeHtml(label) + (detail ? ": " + detail : "")
        + "</div>";
    }
    var layersHtml = ""
      + "<div class='atc-algo7-dest-section'>"
      +   "<div class='atc-algo7-section-title'>" + t(lang, "algo7_layers") + "</div>"
      +   layerLine("1", t(lang, "l1_label"), !!lr.layer1 && lr.layer1.available,
                    lr.layer1 && lr.layer1.available
                      ? (lr.layer1.departure_icao || "?") + " → " + (lr.layer1.arrival_icao || "?")
                      : "")
      +   layerLine("2", t(lang, "l2_label"), !!lr.layer2 && lr.layer2.available,
                    lr.layer2 && lr.layer2.available
                      ? escapeHtml(lr.layer2.carrier_name || "—") + " " + flagEmoji(lr.layer2.carrier_country || "")
                      : "")
      +   layerLine("3", t(lang, "l3_label"), true,
                    primary && primary.layer_scores
                      ? Math.round((primary.layer_scores.l3 || 0) * 100) + "%"
                      : "")
      +   layerLine("4", t(lang, "l4_label"), !!lr.layer4 && lr.layer4.available,
                    lr.layer4 && lr.layer4.available
                      ? escapeHtml(lr.layer4.category) + " · " + lr.layer4.range_km + " km"
                      : "")
      +   layerLine("5", t(lang, "l5_label"), !!lr.layer5 && lr.layer5.available,
                    lr.layer5 && lr.layer5.available
                      ? escapeHtml(lr.layer5.corridor) + " (" + escapeHtml(lr.layer5.type) + ")"
                      : "")
      +   layerLine("6", t(lang, "l6_label"), !!lr.layer6 && lr.layer6.available,
                    lr.layer6 && lr.layer6.available
                      ? (lr.layer6.tailwind_kts >= 0 ? "+" : "") + Math.round(lr.layer6.tailwind_kts) + " kt"
                      : "")
      +   layerLine("7", t(lang, "l7_label"), !!lr.layer7 && lr.layer7.available,
                    lr.layer7 && lr.layer7.available
                      ? lr.layer7.candidates_count + " candidats"
                      : "")
      + "</div>";

    var altsHtml = "";
    if (algo.alternatives && algo.alternatives.length) {
      altsHtml = ""
        + "<div class='atc-algo7-dest-section'>"
        +   "<div class='atc-algo7-section-title'>" + t(lang, "algo7_alternatives") + "</div>";
      algo.alternatives.forEach(function (alt) {
        var iata = alt.iata || alt.icao || "—";
        var name = lang === "en" ? (alt.name_en || alt.name_fr) : (alt.name_fr || alt.name_en);
        altsHtml += "<div class='dest-alt'>"
          + "<span class='alt-icao'>🛬 " + escapeHtml(iata) + " · " + escapeHtml(name || "") + "</span>"
          + "<span class='alt-prob'>" + Math.round((alt.prob || 0) * 100) + "%</span>"
          + "</div>";
      });
      altsHtml += "</div>";
    }

    var progressHtml = "";
    if (algo.progress_pct != null && isFinite(algo.progress_pct)) {
      var pct = Math.max(0, Math.min(100, algo.progress_pct));
      progressHtml = ""
        + "<div class='atc-algo7-dest-progress'>"
        +   "<div class='progress-label'>" + t(lang, "algo7_progress") + "</div>"
        +   "<div class='progress-bar'><div class='progress-fill' style='--pct: " + pct.toFixed(1) + "%'></div></div>"
        +   "<div class='progress-meta'>" + Math.round(pct) + "%"
        +     (primary && primary.eta_minutes != null ? " · " + t(lang, "algo7_eta") + " ~" + fmtETA(primary.eta_minutes) : "")
        +   "</div>"
        + "</div>";
    }

    var sourcesHtml = "";
    if (algo.sources && algo.sources.length) {
      sourcesHtml = "<div class='atc-algo7-dest-sources'>"
        + escapeHtml(t(lang, "algo7_sources")) + " : "
        + algo.sources.map(escapeHtml).join(" · ")
        + "</div>";
    }

    sec.innerHTML = ""
      + "<div class='atc-algo7-dest-header'>"
      +   "<span class='atc-algo7-dest-title'>" + t(lang, "algo7_dest_title") + "</span>"
      +   "<span class='atc-algo7-dest-confidence'>" + conf + "<span class='unit'>" + t(lang, "algo7_dest_confidence_unit") + "</span></span>"
      + "</div>"
      + "<div class='atc-algo7-dest-level' data-level='" + lvl + "'>" + escapeHtml(levelLabel(lang, lvl)) + "</div>"
      + primaryHtml
      + layersHtml
      + altsHtml
      + progressHtml
      + sourcesHtml;
  }

  global.FRAtcRender = {
    renderHud: renderHud,
    t: t,
    computeAlgo7: computeAlgo7,
    renderAlgo7Destination: renderAlgo7Destination,
  };
})(window);
