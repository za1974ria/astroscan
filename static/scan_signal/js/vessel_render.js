/* SCAN A SIGNAL — vessel telemetry HUD renderer.
   Renders the vessel HUD panel from a /api/scan-signal/vessel/<mmsi>
   payload. Same visual grammar as the previous satellite renderer but
   adapted for AIS PositionReports (no orbit, no next-pass).
*/
(function (global) {
  "use strict";

  var I18N = {
    fr: {
      target_locked: "NAVIRE VERROUILLÉ",
      pos: "POSITION",
      lat: "LAT", lon: "LON",
      kin: "CINÉMATIQUE",
      sog: "VITESSE FOND",
      cog: "ROUTE FOND",
      hdg: "CAP VRAI",
      nav: "STATUT NAV.",
      reception: "RÉCEPTION ASTRO-SCAN",
      no_reception: "Aucune antenne dans la portée AIS (≤ 80 km).",
      sight_label: "ant. en portée",
      source: "SOURCE",
      source_value: "AISStream PositionReport + ShipStaticData",
      refreshed: "rafraîchi il y a",
      seconds_short: "s",
      track_continue: "TRACKER EN CONTINU",
      track_stop: "ARRÊTER TRACKING",
      new_scan: "NOUVELLE ACQUISITION",
      vessel: "NAVIRE",
      knots: "kn",
      // enrichments
      flag: "PAVILLON",
      zone: "ZONE ACTUELLE",
      sector: "SECTEUR",
      destination: "DESTINATION",
      dest_undeclared: "Non déclarée",
      provenance: "PROVENANCE",
      prov_recent: "Récemment ajouté au tracking",
      prov_ago: "Il y a",
      prov_in: "en",
      tracked_for: "TRACKÉ DEPUIS",
      eta: "ETA",
      identity: "IDENTITÉ",
      callsign: "INDICATIF",
      imo: "IMO",
      length: "LONGUEUR",
      breadth: "LARGEUR",
      draught: "TIRANT D'EAU",
      // nav status labels
      underway: "EN ROUTE (MOTEUR)",
      anchored: "AU MOUILLAGE",
      not_under_command: "NON MAÎTRISÉ",
      restricted_maneuverability: "MANOEUVRE RESTREINTE",
      constrained_draught: "TIRANT D'EAU CONTRAINT",
      moored: "À QUAI",
      aground: "ÉCHOUÉ",
      fishing: "EN PÊCHE",
      underway_sailing: "EN ROUTE (VOILE)",
      undefined: "INDÉFINI",
    },
    en: {
      target_locked: "VESSEL LOCKED",
      pos: "POSITION",
      lat: "LAT", lon: "LON",
      kin: "KINEMATICS",
      sog: "SPEED OVER GROUND",
      cog: "COURSE OVER GROUND",
      hdg: "TRUE HEADING",
      nav: "NAV STATUS",
      reception: "ASTRO-SCAN RECEPTION",
      no_reception: "No antenna within AIS range (≤ 80 km).",
      sight_label: "ant. in range",
      source: "SOURCE",
      source_value: "AISStream PositionReport + ShipStaticData",
      refreshed: "refreshed",
      seconds_short: "s ago",
      track_continue: "TRACK CONTINUOUSLY",
      track_stop: "STOP TRACKING",
      new_scan: "NEW ACQUISITION",
      vessel: "VESSEL",
      knots: "kn",
      // enrichments
      flag: "FLAG STATE",
      zone: "CURRENT ZONE",
      sector: "SECTOR",
      destination: "DESTINATION",
      dest_undeclared: "Not declared",
      provenance: "FROM",
      prov_recent: "Recently added to tracking",
      prov_ago: "ago",
      prov_in: "in",
      tracked_for: "TRACKED FOR",
      eta: "ETA",
      identity: "IDENTITY",
      callsign: "CALLSIGN",
      imo: "IMO",
      length: "LENGTH",
      breadth: "BEAM",
      draught: "DRAUGHT",
      underway: "UNDER WAY (ENGINE)",
      anchored: "AT ANCHOR",
      not_under_command: "NOT UNDER COMMAND",
      restricted_maneuverability: "RESTRICTED MANEUVER",
      constrained_draught: "CONSTRAINED BY DRAUGHT",
      moored: "MOORED",
      aground: "AGROUND",
      fishing: "FISHING",
      underway_sailing: "UNDER WAY (SAIL)",
      undefined: "UNDEFINED",
    },
  };

  function t(lang, k) {
    return (I18N[lang] || I18N.fr)[k] || k;
  }

  function fmtSign(v, decimals, suffixPos, suffixNeg) {
    var n = Number(v);
    if (!isFinite(n)) return "—";
    return Math.abs(n).toFixed(decimals) + " " + (n >= 0 ? suffixPos : suffixNeg);
  }

  function fmtNumber(v, decimals) {
    var n = Number(v);
    if (!isFinite(n)) return "—";
    return n.toFixed(decimals).replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  }

  function fmtAngle(v) {
    var n = Number(v);
    if (!isFinite(n)) return "—";
    return n.toFixed(1) + "°";
  }

  function setVal(rowVal, newText) {
    if (rowVal && rowVal.textContent !== newText) {
      rowVal.classList.remove("flash");
      void rowVal.offsetWidth;
      rowVal.textContent = newText;
      rowVal.classList.add("flash");
    }
  }

  function renderHud(hudEl, state, lang, freshSec) {
    lang = lang || "fr";
    if (!state) return;

    var pos = state.position || {};
    var kin = state.kinematics || {};
    var nav = state.nav_status || {};
    var rec = state.antenna_reception || [];

    // Build skeleton on first render
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
        + "<div class='ss-hud-section' data-section='enrich' style='display:none'>"
        +   "<div class='ss-hud-row' data-row='flag' style='display:none'>"
        +     "<span class='k' data-k='flag'></span><span class='v' data-bind='flag'></span>"
        +   "</div>"
        +   "<div class='ss-hud-row' data-row='zone' style='display:none'>"
        +     "<span class='k' data-k='zone'></span><span class='v' data-bind='zone'></span>"
        +   "</div>"
        +   "<div class='ss-hud-row' data-row='sector' style='display:none'>"
        +     "<span class='k' data-k='sector'></span><span class='v' data-bind='sector'></span>"
        +   "</div>"
        +   "<div class='ss-hud-row' data-row='destination'>"
        +     "<span class='k' data-k='destination'></span><span class='v' data-bind='destination'></span>"
        +   "</div>"
        +   "<div class='ss-hud-row' data-row='provenance' style='display:none'>"
        +     "<span class='k' data-k='provenance'></span><span class='v' data-bind='provenance'></span>"
        +   "</div>"
        +   "<div class='ss-hud-row' data-row='tracked' style='display:none'>"
        +     "<span class='k' data-k='tracked_for'></span><span class='v' data-bind='tracked'></span>"
        +   "</div>"
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
        + "</div>"
        + "<div class='ss-hud-section' data-section='kin'>"
        +   "<div class='ss-hud-section-title' data-k='kin'></div>"
        +   "<div class='ss-hud-row'><span class='k' data-k='sog'></span><span class='v' data-bind='sog'></span></div>"
        +   "<div class='ss-hud-row'><span class='k' data-k='cog'></span><span class='v' data-bind='cog'></span></div>"
        +   "<div class='ss-hud-row'><span class='k' data-k='hdg'></span><span class='v' data-bind='hdg'></span></div>"
        + "</div>"
        + "<div class='ss-hud-section' data-section='nav'>"
        +   "<div class='ss-hud-section-title' data-k='nav'></div>"
        +   "<div class='ss-hud-row'><span class='k'>STATUS</span><span class='v' data-bind='nav_label'></span></div>"
        + "</div>"
        + "<div class='ss-hud-section' data-section='identity' style='display:none'>"
        +   "<div class='ss-hud-section-title' data-k='identity'></div>"
        +   "<div class='ss-hud-row' data-row='imo' style='display:none'>"
        +     "<span class='k' data-k='imo'></span><span class='v' data-bind='imo'></span>"
        +   "</div>"
        +   "<div class='ss-hud-row' data-row='callsign' style='display:none'>"
        +     "<span class='k' data-k='callsign'></span><span class='v' data-bind='callsign'></span>"
        +   "</div>"
        +   "<div class='ss-hud-row' data-row='length' style='display:none'>"
        +     "<span class='k' data-k='length'></span><span class='v' data-bind='length'></span>"
        +   "</div>"
        +   "<div class='ss-hud-row' data-row='breadth' style='display:none'>"
        +     "<span class='k' data-k='breadth'></span><span class='v' data-bind='breadth'></span>"
        +   "</div>"
        +   "<div class='ss-hud-row' data-row='draught' style='display:none'>"
        +     "<span class='k' data-k='draught'></span><span class='v' data-bind='draught'></span>"
        +   "</div>"
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

    // Static labels
    hudEl.querySelectorAll("[data-k]").forEach(function (el) {
      el.textContent = t(lang, el.getAttribute("data-k"));
    });

    // Name + MMSI sub
    var name = state.name || "—";
    var mmsi = state.mmsi || "—";
    var nameEl = hudEl.querySelector("[data-bind='name']");
    var subEl  = hudEl.querySelector("[data-bind='sub']");
    var tagEl  = hudEl.querySelector("[data-bind='tag']");
    if (nameEl && nameEl.textContent !== name) nameEl.textContent = name;
    if (subEl)  subEl.textContent = "MMSI " + mmsi;
    if (tagEl)  tagEl.textContent = t(lang, "vessel");

    // Position
    setVal(hudEl.querySelector("[data-bind='lat']"), fmtSign(pos.latitude, 5, "°N", "°S"));
    setVal(hudEl.querySelector("[data-bind='lon']"), fmtSign(pos.longitude, 5, "°E", "°W"));

    // Kinematics
    setVal(hudEl.querySelector("[data-bind='sog']"),
      kin.sog_knots == null ? "—" : (fmtNumber(kin.sog_knots, 1) + " " + t(lang, "knots")));
    setVal(hudEl.querySelector("[data-bind='cog']"),
      kin.cog_deg == null ? "—" : fmtAngle(kin.cog_deg));
    setVal(hudEl.querySelector("[data-bind='hdg']"),
      kin.true_heading_deg == null ? "—" : fmtAngle(kin.true_heading_deg));

    // Nav status
    var navLabelKey = (nav && nav.label) || "undefined";
    setVal(hudEl.querySelector("[data-bind='nav_label']"), t(lang, navLabelKey));

    // ──────────────────────────────────────────────────────────────────
    // ENRICHMENTS — flag, zone, destination, provenance, tracking
    // ──────────────────────────────────────────────────────────────────
    var enrichSec = hudEl.querySelector("[data-section='enrich']");
    var anyEnrich = false;

    function showRow(row, visible, bindKey, htmlValue) {
      var rowEl = hudEl.querySelector("[data-row='" + row + "']");
      if (!rowEl) return;
      if (visible) {
        rowEl.style.display = "";
        var v = rowEl.querySelector("[data-bind='" + bindKey + "']");
        if (v) v.innerHTML = htmlValue;
        anyEnrich = true;
      } else {
        rowEl.style.display = "none";
      }
    }

    // PAVILLON
    if (state.flag && state.flag.flag) {
      var flagName = (lang === "fr" ? state.flag.name_fr : state.flag.name_en) || state.flag.name_en || state.flag.iso || "";
      showRow("flag", true, "flag",
        "<span class='ss-flag-emoji'>" + state.flag.flag + "</span> " + escapeHtml(flagName));
    } else {
      showRow("flag", false);
    }

    // ZONE
    if (state.sea_zone) {
      showRow("zone", true, "zone", "📍 " + escapeHtml(state.sea_zone));
    } else {
      showRow("zone", false);
    }

    // SECTEUR (inland waterway honesty disclosure)
    if (state.inland_waterway && state.inland_waterway.label) {
      showRow("sector", true, "sector",
        "🌊 " + escapeHtml(state.inland_waterway.label));
    } else {
      showRow("sector", false);
    }

    // DESTINATION (always shown — undeclared vs declared)
    var destHtml;
    if (state.destination) {
      var destText = "";
      if (state.destination.flag) destText += state.destination.flag + " ";
      destText += escapeHtml(state.destination.port || state.destination.raw || "—");
      if (state.destination.country_name) {
        destText += " <span class='ss-hud-muted'>(" + escapeHtml(state.destination.country_name) + ")</span>";
      }
      if (state.destination.eta) {
        destText += " · " + t(lang, "eta") + " " + escapeHtml(state.destination.eta);
      }
      destHtml = destText;
    } else {
      destHtml = "<span class='ss-hud-muted'>" + t(lang, "dest_undeclared") + "</span>";
    }
    showRow("destination", true, "destination", destHtml);

    // PROVENANCE
    if (state.provenance) {
      var hours = Number(state.provenance.hours_ago) || 0;
      var ago;
      if (hours >= 24) {
        ago = Math.round(hours / 24) + (lang === "fr" ? "j" : "d");
      } else if (hours >= 1) {
        ago = Math.round(hours) + "h";
      } else {
        ago = Math.max(1, Math.round(hours * 60)) + "min";
      }
      var provText;
      if (state.provenance.fresh || hours < 1) {
        provText = t(lang, "prov_recent");
      } else if (state.provenance.zone) {
        if (lang === "fr") {
          provText = t(lang, "prov_ago") + " " + ago + " " + t(lang, "prov_in") + " " + escapeHtml(state.provenance.zone);
        } else {
          provText = ago + " " + t(lang, "prov_ago") + ": " + escapeHtml(state.provenance.zone);
        }
      } else {
        if (lang === "fr") {
          provText = t(lang, "prov_ago") + " " + ago;
        } else {
          provText = ago + " " + t(lang, "prov_ago");
        }
      }
      showRow("provenance", true, "provenance", provText);
    } else {
      showRow("provenance", false);
    }

    // TRACKED FOR
    if (state.tracking_duration && state.tracking_duration.human) {
      showRow("tracked", true, "tracked", "🕐 " + escapeHtml(state.tracking_duration.human));
    } else {
      showRow("tracked", false);
    }

    if (enrichSec) enrichSec.style.display = anyEnrich ? "" : "none";

    // ──────────────────────────────────────────────────────────────────
    // STATIC IDENTITY — IMO / callsign / dimensions
    // ──────────────────────────────────────────────────────────────────
    var identitySec = hudEl.querySelector("[data-section='identity']");
    var anyIdentity = false;
    var st = state.static || {};

    function showIdentityRow(row, visible, bindKey, htmlValue) {
      var rowEl = hudEl.querySelector("[data-section='identity'] [data-row='" + row + "']");
      if (!rowEl) return;
      if (visible) {
        rowEl.style.display = "";
        var vEl = rowEl.querySelector("[data-bind='" + bindKey + "']");
        if (vEl) vEl.innerHTML = htmlValue;
        anyIdentity = true;
      } else {
        rowEl.style.display = "none";
      }
    }

    showIdentityRow("imo", !!st.imo, "imo", st.imo ? escapeHtml(String(st.imo)) : "");
    showIdentityRow("callsign", !!st.callsign, "callsign", st.callsign ? escapeHtml(st.callsign) : "");
    showIdentityRow("length", !!st.length_m, "length", st.length_m ? (st.length_m + " m") : "");
    showIdentityRow("breadth", !!st.breadth_m, "breadth", st.breadth_m ? (st.breadth_m + " m") : "");
    showIdentityRow("draught", !!st.max_static_draught_m, "draught",
      st.max_static_draught_m ? (st.max_static_draught_m + " m") : "");

    if (identitySec) identitySec.style.display = anyIdentity ? "" : "none";

    // In-sight badge X/12
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

    // Reception list
    var recHost = hudEl.querySelector("[data-bind='reception']");
    if (recHost) {
      if (!rec.length) {
        recHost.innerHTML = "<div class='ss-hud-empty'>" + t(lang, "no_reception") + "</div>";
      } else {
        var html = "";
        rec.forEach(function (a) {
          html += "<div class='ss-hud-antenna'>"
            + "<div class='a-name'>" + escapeHtml(a.antenna_name || a.antenna_id) + "</div>"
            + "<div class='a-data'>"
            +   "<span>" + fmtNumber(a.distance_km, 1) + " km</span>"
            +   "<span>" + fmtNumber(a.rssi_dbm, 1) + " dBm</span>"
            +   "<span class='quality " + escapeHtml(a.quality || "") + "'>" + escapeHtml(a.quality || "") + "</span>"
            + "</div>"
          + "</div>";
        });
        recHost.innerHTML = html;
      }
    }

    // Source line
    var srcVal = hudEl.querySelector("[data-bind='source_val']");
    if (srcVal) {
      var freshTxt = (typeof freshSec === "number" ? freshSec : 0) + (lang === "en" ? "s ago" : "s");
      srcVal.textContent = t(lang, "source_value") + "  ·  " + (lang === "en" ? "refreshed " : "rafraîchi il y a ") + freshTxt;
    }

    // Track toggle / new-scan button labels
    var btn = hudEl.querySelector("[data-action='track-toggle']");
    if (btn) {
      btn.textContent = hudEl.dataset.tracking === "1"
        ? t(lang, "track_stop")
        : t(lang, "track_continue");
    }
    var newScanBtn = hudEl.querySelector("[data-action='new-scan']");
    if (newScanBtn) newScanBtn.textContent = t(lang, "new_scan");
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"})[c];
    });
  }

  global.SSVesselRender = {
    renderHud: renderHud,
    t: t,
  };
})(window);
