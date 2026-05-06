/* FLIGHT RADAR — main orchestration (premium NASA-grade ATC).
   - Leaflet map with DARK / SAT toggle (CARTO + Esri World Imagery)
   - 50 pulsing airport markers (cyan)
   - Aircraft markers colored by altitude band, oriented by true_track
   - Selected aircraft: radar lock halo + comet trail + ping flash
   - ATC HUD (renderer in atc_render.js) updated every 30 s
*/
(function () {
  "use strict";

  var global = window;
  var REFRESH_MS = 30000;
  var STATS_REFRESH_MS = 30000;

  var state = {
    lang: document.documentElement.getAttribute("data-lang") || "fr",
    map: null,
    basemap: "dark",
    basemapLayers: { dark: null, sat: null },
    airportLayer: null,
    aircraftLayer: null,
    trailLayer: null,
    radarLockMarker: null,
    aircraftMarkers: {},   // icao24 -> L.marker
    aircraftCache: {},     // icao24 -> last state (for diff)
    selectedIcao: null,
    selectedDetail: null,
    selectedAirportIata: null,
    airportRefreshTimer: null,
    refreshTimer: null,
    statsTimer: null,
    healthTimer: null,
    tracking: true,
    lastFetchAt: null,
    filters: { mode: "all", country: "", alt_min: null, alt_max: null },
  };

  // ──────────────────────────────────────────────────────────────────
  // Bootstrap
  // ──────────────────────────────────────────────────────────────────

  function init() {
    state.lang = document.documentElement.getAttribute("data-lang") || "fr";
    setupHeaderLang();
    setupFilterChips();
    initMap();
    setupHudActions();
    startUtcClock();
    fetchAircraft();
    fetchHealth();
    state.refreshTimer = setInterval(fetchAircraft, REFRESH_MS);
    state.statsTimer = setInterval(fetchAircraft, STATS_REFRESH_MS);
    state.healthTimer = setInterval(fetchHealth, 60000);
  }

  // ──────────────────────────────────────────────────────────────────
  // Header / clock / lang
  // ──────────────────────────────────────────────────────────────────

  function startUtcClock() {
    var el = document.getElementById("fr-utc");
    if (!el) return;
    function tick() {
      var d = new Date();
      function pad(n) { return String(n).padStart(2, "0"); }
      el.textContent = pad(d.getUTCHours()) + ":" + pad(d.getUTCMinutes()) + ":" + pad(d.getUTCSeconds()) + " UTC";
    }
    tick();
    setInterval(tick, 1000);
  }

  function setupHeaderLang() {
    document.querySelectorAll(".fr-lang button").forEach(function (b) {
      b.addEventListener("click", function () {
        var l = b.getAttribute("data-lang");
        if (!l || l === state.lang) return;
        var sp = new URLSearchParams(window.location.search);
        sp.set("lang", l);
        window.location.search = sp.toString();
      });
    });
  }

  // ──────────────────────────────────────────────────────────────────
  // Map init + basemap toggle (same pattern as scan_signal)
  // ──────────────────────────────────────────────────────────────────

  function initMap() {
    var el = document.getElementById("fr-map");
    if (!el || typeof L === "undefined") return;

    state.map = L.map(el, {
      center: [30, 10],
      zoom: 3,
      worldCopyJump: true,
      zoomControl: true,
      attributionControl: true,
      preferCanvas: true,
    });

    state.basemapLayers.dark = L.tileLayer(
      "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
      {
        attribution: "&copy; <a href='https://www.openstreetmap.org/copyright'>OSM</a> · <a href='https://carto.com/attributions'>CARTO</a>",
        subdomains: "abcd",
        maxZoom: 19,
      }
    );
    state.basemapLayers.sat = L.tileLayer(
      "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
      {
        attribution: "Tiles &copy; Esri &mdash; Maxar, Earthstar Geographics",
        maxZoom: 19,
      }
    );
    state.basemapLayers.dark.addTo(state.map);
    state.basemap = "dark";
    addBasemapToggleControl();

    state.airportLayer = L.layerGroup().addTo(state.map);
    state.aircraftLayer = L.layerGroup().addTo(state.map);
    state.trailLayer = L.layerGroup().addTo(state.map);

    var loaderEl = document.getElementById("fr-map-loader");
    var fade = function () { if (loaderEl) loaderEl.classList.add("fade"); };
    state.map.whenReady(fade);
    setTimeout(fade, 1200);

    drawAirports();
  }

  function switchBasemap(which) {
    if (!state.map || !state.basemapLayers[which]) return;
    if (state.basemap === which) return;
    var prev = state.basemapLayers[state.basemap];
    var next = state.basemapLayers[which];
    if (prev) state.map.removeLayer(prev);
    next.addTo(state.map);
    state.basemap = which;
    var root = document.querySelector(".fr-basemap-toggle");
    if (root) {
      root.querySelectorAll(".fr-basemap-btn").forEach(function (b) {
        b.classList.toggle("active", b.getAttribute("data-basemap") === which);
      });
    }
  }

  function addBasemapToggleControl() {
    if (!state.map || typeof L === "undefined") return;
    var Ctrl = L.Control.extend({
      options: { position: "topright" },
      onAdd: function () {
        var div = L.DomUtil.create("div", "fr-basemap-toggle");
        div.innerHTML =
          '<button type="button" class="fr-basemap-btn active" data-basemap="dark">DARK</button>' +
          '<button type="button" class="fr-basemap-btn" data-basemap="sat">SAT</button>';
        L.DomEvent.disableClickPropagation(div);
        L.DomEvent.disableScrollPropagation(div);
        div.querySelectorAll(".fr-basemap-btn").forEach(function (b) {
          b.addEventListener("click", function (e) {
            e.preventDefault();
            switchBasemap(b.getAttribute("data-basemap"));
          });
        });
        return div;
      },
    });
    new Ctrl().addTo(state.map);
  }

  // ──────────────────────────────────────────────────────────────────
  // Airports — pulsing cyan markers (50)
  // ──────────────────────────────────────────────────────────────────

  function drawAirports() {
    fetch("/api/flight-radar/airports", { cache: "no-store" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (!d || !Array.isArray(d.airports)) return;
        d.airports.forEach(function (a) {
          if (typeof a.lat !== "number" || typeof a.lon !== "number") return;
          var icon = L.divIcon({
            className: "fr-airport-marker",
            html: "<span class='fr-airport-core'></span>",
            iconSize: [12, 12],
            iconAnchor: [6, 6],
          });
          var name = state.lang === "en" ? a.name_en : a.name_fr;
          // BUG 3 fix: airports recede behind aircraft markers.
          var m = L.marker([a.lat, a.lon], {
            icon: icon,
            keyboard: false,
            zIndexOffset: -100,
            riseOnHover: false,
          });
          // BUG 1 fix: tooltip must close cleanly on mouseout. We make it
          // non-sticky, non-interactive, and force-close on mouseout in
          // case Leaflet missed the leave event (can happen when the
          // pulse box-shadow visually overlaps but is not part of the
          // hit area).
          m.bindTooltip(
            "<strong>" + escapeHtml(a.iata) + "</strong> · " + escapeHtml(name || ""),
            {
              className: "fr-tooltip",
              direction: "top",
              offset: [0, -8],
              permanent: false,
              sticky: false,
              interactive: false,
              opacity: 0.95,
            }
          );
          m.on("mouseout", function () { try { this.closeTooltip(); } catch (_) {} });
          // BUG 2 fix: clicking an airport must NOT touch the aircraft
          // HUD. We open a Leaflet popup with airport info instead, and
          // stop propagation so the map click handler doesn't fire.
          var country = state.lang === "en"
            ? (a.country_en || a.country_iso)
            : (a.country_fr || a.country_iso);
          var popupHtml = ""
            + "<div class='fr-airport-popup'>"
            +   "<div class='fr-ap-iata'>" + escapeHtml(a.iata || "") + "</div>"
            +   "<div class='fr-ap-name'>" + escapeHtml(name || "") + "</div>"
            +   "<div class='fr-ap-meta'>"
            +     "<span class='fr-ap-flag'>" + (a.country_iso ? ("🌍 " + escapeHtml(a.country_iso)) : "") + "</span>"
            +     (a.icao ? " · <span class='fr-ap-icao'>ICAO " + escapeHtml(a.icao) + "</span>" : "")
            +   "</div>"
            +   "<div class='fr-ap-coords'>"
            +     a.lat.toFixed(4) + "°, " + a.lon.toFixed(4) + "°"
            +   "</div>"
            + "</div>";
          // Side-panel HUD AIRPORT replaces the popup: click → open dedicated
          // panel with live traffic, identification, position. Popup kept as
          // fallback for very rapid hover actions or when JS HUD missing.
          m.bindPopup(popupHtml, {
            className: "fr-airport-popup-wrap",
            closeButton: true,
            autoPan: true,
            offset: [0, -4],
          });
          var iata = a.iata;
          m.on("click", function (e) {
            if (e && e.originalEvent) {
              L.DomEvent.stopPropagation(e.originalEvent);
            }
            // Open the rich HUD AIRPORT panel rather than the popup.
            selectAirport(iata);
          });
          m.addTo(state.airportLayer);
        });
        // Populate country select
        populateCountries(d.airports);
      })
      .catch(function () {});
  }

  // ──────────────────────────────────────────────────────────────────
  // Aircraft — fetch + render
  // ──────────────────────────────────────────────────────────────────

  function altColor(meters) {
    var n = Number(meters);
    if (!isFinite(n)) return "#FFB400";
    if (n < 3000) return "#FF8A00";   // approach / departure
    if (n < 7000) return "#FFD24D";   // mid
    if (n < 12000) return "#00C8E8";  // cruise
    return "#FFFFFF";                 // high
  }

  function altOpacity(meters) {
    var n = Number(meters);
    if (!isFinite(n)) return 0.85;
    if (n < 1000) return 1.0;
    return 0.85;
  }

  function buildAircraftIcon(state_, isSelected) {
    var alt = state_.baro_altitude || state_.geo_altitude || 0;
    var color = altColor(alt);
    var heading = Number(state_.true_track) || 0;
    var html = "<div class='fr-aircraft-tri' style='color:" + color + ";transform:rotate(" + heading + "deg);'></div>";
    return L.divIcon({
      className: "fr-aircraft-marker" + (isSelected ? " selected" : ""),
      html: html,
      iconSize: [16, 16],
      iconAnchor: [8, 8],
    });
  }

  function fetchAircraft() {
    var qs = new URLSearchParams();
    if (state.filters.mode && state.filters.mode !== "all") qs.set("mode", state.filters.mode);
    if (state.filters.country) qs.set("country", state.filters.country);
    if (state.filters.alt_min !== null) qs.set("alt_min", String(state.filters.alt_min));
    if (state.filters.alt_max !== null) qs.set("alt_max", String(state.filters.alt_max));
    qs.set("limit", "800");
    return fetch("/api/flight-radar/aircraft?" + qs.toString(), { cache: "no-store" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (!d || !Array.isArray(d.aircraft)) return;
        state.lastFetchAt = Date.now();
        renderAircraft(d.aircraft);
        updateStats(d);
        if (state.selectedIcao) {
          fetchSelectedDetail();
        }
      })
      .catch(function (e) {
        console.warn("[flight_radar] fetch failed", e);
      });
  }

  function renderAircraft(list) {
    var seen = {};
    list.forEach(function (a) {
      var id = a.icao24;
      seen[id] = true;
      var existing = state.aircraftMarkers[id];
      var prev = state.aircraftCache[id];
      state.aircraftCache[id] = a;

      var isSel = (id === state.selectedIcao);
      var icon = buildAircraftIcon(a, isSel);

      if (existing) {
        existing.setLatLng([a.lat, a.lon]);
        existing.setIcon(icon);
      } else {
        var m = L.marker([a.lat, a.lon], {
          icon: icon,
          keyboard: false,
          zIndexOffset: 1000,
          riseOnHover: true,
        });
        m.on("click", function (e) {
          if (e && e.originalEvent) {
            L.DomEvent.stopPropagation(e.originalEvent);
          }
          selectAircraft(id);
        });
        m.bindTooltip(buildAircraftTooltip(a), {
          className: "fr-tooltip", direction: "top", offset: [0, -10],
          permanent: false, sticky: false, interactive: false,
        });
        m.on("mouseout", function () { try { this.closeTooltip(); } catch (_) {} });
        m.addTo(state.aircraftLayer);
        state.aircraftMarkers[id] = m;
      }
      // Update tooltip content (callsign may change, ground/air status, alt)
      var existingTip = state.aircraftMarkers[id].getTooltip();
      if (existingTip) existingTip.setContent(buildAircraftTooltip(a));

      // Mini-flash for the selected aircraft when its position changed
      if (isSel && prev && (prev.lat !== a.lat || prev.lon !== a.lon)) {
        triggerPingFlash(a);
      }
    });
    // Remove stale markers (not in this fetch and not selected)
    Object.keys(state.aircraftMarkers).forEach(function (id) {
      if (!seen[id] && id !== state.selectedIcao) {
        state.aircraftLayer.removeLayer(state.aircraftMarkers[id]);
        delete state.aircraftMarkers[id];
        delete state.aircraftCache[id];
      }
    });
  }

  function buildAircraftTooltip(a) {
    var cs = a.callsign || a.icao24.toUpperCase();
    var alt = a.baro_altitude || a.geo_altitude;
    var altTxt = (alt != null) ? Math.round(alt) + " m" : "—";
    return "<strong>" + escapeHtml(cs) + "</strong> · " + escapeHtml(a.origin_country || "—")
         + "<br>" + altTxt + (a.on_ground ? " · SOL" : "");
  }

  // ──────────────────────────────────────────────────────────────────
  // Selection / radar lock / trail / HUD
  // ──────────────────────────────────────────────────────────────────

  function selectAircraft(icao24) {
    // Aircraft selection takes priority — close any airport HUD first.
    if (state.selectedAirportIata) {
      closeAirportHud();
    }
    state.selectedIcao = icao24;
    // Re-icon to apply 'selected' class
    Object.keys(state.aircraftMarkers).forEach(function (id) {
      var st = state.aircraftCache[id];
      if (st) state.aircraftMarkers[id].setIcon(buildAircraftIcon(st, id === icao24));
    });
    showHud();
    fetchSelectedDetail();
  }

  // ──────────────────────────────────────────────────────────────────
  // Airport HUD selection
  // ──────────────────────────────────────────────────────────────────

  function selectAirport(iata) {
    if (!iata) return;
    // Switching to airport HUD: hide aircraft HUD with fade-out, then load.
    if (state.selectedIcao) {
      deselect();
    }
    state.selectedAirportIata = iata;
    var hud = document.getElementById("fr-hud");
    var apHud = document.getElementById("fr-airport-hud");
    var idle = document.getElementById("fr-side-idle");
    if (hud) hud.setAttribute("hidden", "");
    if (idle) idle.style.display = "none";
    fetchAirportDetails(iata);
    // Refresh airport details every 15 s while open.
    if (state.airportRefreshTimer) clearInterval(state.airportRefreshTimer);
    state.airportRefreshTimer = setInterval(function () {
      if (state.selectedAirportIata) fetchAirportDetails(state.selectedAirportIata);
    }, 15000);
  }

  function fetchAirportDetails(iata) {
    fetch("/api/flight-radar/airport/" + encodeURIComponent(iata) + "/details", { cache: "no-store" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (!d || !d.ok) return;
        renderAirportHud(d);
      })
      .catch(function () {});
  }

  function renderAirportHud(payload) {
    var apHud = document.getElementById("fr-airport-hud");
    if (!apHud || !global.FRAirportRender) return;
    global.FRAirportRender.render(apHud, payload, state.lang, function (icao24) {
      // Click on a flight item inside airport HUD → switch to aircraft HUD.
      closeAirportHud();
      selectAircraft(icao24);
    });
    // Wire the close event from airport_render.js
    if (!apHud.dataset.closeBound) {
      apHud.dataset.closeBound = "1";
      apHud.addEventListener("airport-hud-close", closeAirportHud);
    }
  }

  function closeAirportHud() {
    state.selectedAirportIata = null;
    var apHud = document.getElementById("fr-airport-hud");
    if (apHud) {
      apHud.classList.add("fade-out");
      setTimeout(function () {
        apHud.classList.remove("fade-out");
        apHud.setAttribute("hidden", "");
      }, 200);
    }
    var idle = document.getElementById("fr-side-idle");
    if (idle && !state.selectedIcao) idle.style.display = "";
    if (state.airportRefreshTimer) {
      clearInterval(state.airportRefreshTimer);
      state.airportRefreshTimer = null;
    }
  }

  function fetchSelectedDetail() {
    if (!state.selectedIcao) return;
    fetch("/api/flight-radar/aircraft/" + encodeURIComponent(state.selectedIcao), { cache: "no-store" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (!d || !d.ok || !d.aircraft) return;
        state.selectedDetail = d.aircraft;
        renderHud(d.aircraft);
        renderRadarLock(d.aircraft);
        renderTrail(d.aircraft);
      })
      .catch(function () {});
  }

  function renderHud(aircraft) {
    var hud = document.getElementById("fr-hud");
    if (!hud || !global.FRAtcRender) return;
    hud.removeAttribute("hidden");
    hud.dataset.tracking = state.tracking ? "1" : "0";
    var fresh = state.lastFetchAt ? Math.round((Date.now() - state.lastFetchAt) / 1000) : 0;
    global.FRAtcRender.renderHud(hud, aircraft, state.lang, fresh);
    // wire close + actions
    hud.querySelectorAll("[data-action]").forEach(function (b) {
      if (b.dataset.bound) return;
      b.dataset.bound = "1";
      b.addEventListener("click", function () {
        var act = b.getAttribute("data-action");
        if (act === "close" || act === "new-scan") {
          deselect();
        } else if (act === "track-toggle") {
          state.tracking = !state.tracking;
          hud.dataset.tracking = state.tracking ? "1" : "0";
          renderHud(state.selectedDetail || aircraft);
        }
      });
    });
  }

  function renderRadarLock(aircraft) {
    if (state.radarLockMarker) state.map.removeLayer(state.radarLockMarker);
    if (!aircraft || !isFinite(aircraft.lat) || !isFinite(aircraft.lon)) return;
    var icon = L.divIcon({
      className: "fr-radar-lock",
      html: "<span></span>",
      iconSize: [0, 0],
      iconAnchor: [0, 0],
    });
    state.radarLockMarker = L.marker([aircraft.lat, aircraft.lon], {
      icon: icon, keyboard: false, interactive: false, zIndexOffset: -10,
    }).addTo(state.map);
  }

  function renderTrail(aircraft) {
    if (state.trailLayer) state.trailLayer.clearLayers();
    var track = (aircraft && aircraft.track) || [];
    if (track.length < 2) return;
    var pts = track
      .filter(function (p) { return isFinite(p.lat) && isFinite(p.lon); })
      .map(function (p) { return [p.lat, p.lon]; });
    if (pts.length < 2) return;
    // Most recent point first → fade backwards
    for (var i = 0; i < pts.length - 1; i++) {
      var alpha = 1 - (i / pts.length) * 0.85;
      L.polyline([pts[i], pts[i + 1]], {
        className: "fr-trail",
        color: "#00FF66",
        weight: 2.5 - (i / pts.length) * 1.5,
        opacity: Math.max(0.1, alpha),
      }).addTo(state.trailLayer);
    }
  }

  function triggerPingFlash(aircraft) {
    var pane = state.map.getPanes().overlayPane;
    if (!pane) return;
    var pt = state.map.latLngToLayerPoint([aircraft.lat, aircraft.lon]);
    var flash = document.createElement("div");
    flash.className = "fr-ping-flash";
    flash.style.position = "absolute";
    flash.style.left = pt.x + "px";
    flash.style.top = pt.y + "px";
    pane.appendChild(flash);
    setTimeout(function () { flash.remove(); }, 1200);
  }

  function showHud() {
    var idle = document.getElementById("fr-side-idle");
    if (idle) idle.style.display = "none";
  }

  function deselect() {
    state.selectedIcao = null;
    state.selectedDetail = null;
    var hud = document.getElementById("fr-hud");
    if (hud) hud.setAttribute("hidden", "");
    var idle = document.getElementById("fr-side-idle");
    if (idle) idle.style.display = "";
    if (state.radarLockMarker) {
      state.map.removeLayer(state.radarLockMarker);
      state.radarLockMarker = null;
    }
    if (state.trailLayer) state.trailLayer.clearLayers();
    // Re-icon all to remove 'selected' class
    Object.keys(state.aircraftMarkers).forEach(function (id) {
      var st = state.aircraftCache[id];
      if (st) state.aircraftMarkers[id].setIcon(buildAircraftIcon(st, false));
    });
  }

  function setupHudActions() {
    // bound lazily on first render of hud
  }

  // ──────────────────────────────────────────────────────────────────
  // Filters
  // ──────────────────────────────────────────────────────────────────

  function setupFilterChips() {
    document.querySelectorAll(".fr-fchip[data-mode]").forEach(function (b) {
      b.addEventListener("click", function () {
        document.querySelectorAll(".fr-fchip[data-mode]").forEach(function (x) {
          x.classList.remove("on");
        });
        b.classList.add("on");
        state.filters.mode = b.getAttribute("data-mode");
        fetchAircraft();
      });
    });
    var sel = document.getElementById("fr-country-select");
    if (sel) {
      sel.addEventListener("change", function () {
        state.filters.country = sel.value;
        fetchAircraft();
      });
    }
  }

  function populateCountries(airports) {
    var sel = document.getElementById("fr-country-select");
    if (!sel) return;
    var set = {};
    airports.forEach(function (a) { if (a.country_iso) set[a.country_iso] = true; });
    var keys = Object.keys(set).sort();
    keys.forEach(function (k) {
      var opt = document.createElement("option");
      opt.value = k;
      opt.textContent = k;
      sel.appendChild(opt);
    });
  }

  // ──────────────────────────────────────────────────────────────────
  // Stats / health
  // ──────────────────────────────────────────────────────────────────

  function updateStats(payload) {
    var total = payload.total || 0;
    var rendered = payload.rendered || (payload.aircraft ? payload.aircraft.length : 0);
    var inAir = 0;
    var onGround = 0;
    (payload.aircraft || []).forEach(function (a) {
      if (a.on_ground) onGround++;
      else inAir++;
    });
    setText("fr-stat-total", total);
    setText("fr-stat-rendered", rendered);
    setText("fr-stat-air", inAir);
    setText("fr-stat-ground", onGround);
  }

  function fetchHealth() {
    fetch("/api/flight-radar/health", { cache: "no-store" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (h) {
        if (!h) return;
        var el = document.getElementById("fr-stat-source");
        if (el) {
          var label = "OpenSky " + (h.auth_mode || "?").toUpperCase();
          el.textContent = label;
        }
      })
      .catch(function () {});
  }

  function setText(id, val) {
    var el = document.getElementById(id);
    if (el) el.textContent = val;
  }

  // ──────────────────────────────────────────────────────────────────
  // Utils
  // ──────────────────────────────────────────────────────────────────

  function escapeHtml(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"})[c];
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
