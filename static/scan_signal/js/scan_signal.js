/* SCAN A SIGNAL — main orchestration (VESSEL TRACKER edition).
   - Tab switching (vessel default / aircraft → /flight-radar)
   - Vessel search (debounced) + recent-vessels chips
   - Live AIS state polling (5 s)
   - Leaflet map render: vessel marker (cyan, oriented by COG), antenna links
*/
(function (global) {
  "use strict";

  var REFRESH_MS = 5000;
  var SEARCH_DEBOUNCE_MS = 300;
  var STATS_REFRESH_MS = 8000;
  var RECENT_REFRESH_MS = 30000;

  var state = {
    lang: (document.documentElement.getAttribute("data-lang") || "fr"),
    activeTab: "vessel",
    currentMmsi: null,
    refreshTimer: null,
    statsTimer: null,
    recentTimer: null,
    searchTimer: null,
    map: null,
    basemap: "dark",
    basemapLayers: { dark: null, sat: null },
    vesselMarker: null,
    obsMarkers: [],
    linkLines: [],
    portMarkers: [],
    vesselTrail: null,
    lastVesselTimestamp: null,
    lastVesselLat: null,
    lastVesselLon: null,
    lastFetchAt: null,
    tracking: true,
  };

  // ──────────────────────────────────────────────────────────────────
  // Bootstrap
  // ──────────────────────────────────────────────────────────────────

  function init() {
    state.lang = document.documentElement.getAttribute("data-lang") || "fr";
    setupTabs();
    setupSearchUi();
    setupHudActions();
    setupLangButtons();
    initMap();
    loadRecent();
    startUtcClock();
    refreshStats();
    state.statsTimer = setInterval(refreshStats, STATS_REFRESH_MS);
    state.recentTimer = setInterval(loadRecent, RECENT_REFRESH_MS);
    document.body.classList.add("ss-app");

    // Default tab: vessel (the only functional tab — aircraft redirects).
    switchTab("vessel");
  }

  // ──────────────────────────────────────────────────────────────────
  // Tabs
  // ──────────────────────────────────────────────────────────────────

  function setupTabs() {
    var btns = document.querySelectorAll(".ss-tab");
    btns.forEach(function (btn) {
      btn.addEventListener("click", function () {
        var tab = btn.getAttribute("data-tab");
        if (!tab) return;
        if (tab === "aircraft") {
          window.location.href = "/flight-radar";
          return;
        }
        switchTab(tab);
      });
    });
  }

  function switchTab(tab) {
    state.activeTab = tab;
    document.querySelectorAll(".ss-tab").forEach(function (b) {
      b.classList.toggle("active", b.getAttribute("data-tab") === tab);
    });
    document.querySelectorAll(".ss-tab-panel").forEach(function (p) {
      p.classList.toggle("hidden", p.getAttribute("data-panel") !== tab);
    });
    if (tab === "vessel" && state.map) {
      setTimeout(function () { state.map.invalidateSize(); }, 50);
    }
  }

  // ──────────────────────────────────────────────────────────────────
  // Map
  // ──────────────────────────────────────────────────────────────────

  function initMap() {
    var el = document.getElementById("ss-map");
    if (!el || typeof L === "undefined") return;

    state.map = L.map(el, {
      center: [20, 0],
      zoom: 2,
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
    var satImagery = L.tileLayer(
      "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
      {
        attribution: "Tiles &copy; Esri &mdash; Source: Esri, Maxar, Earthstar Geographics",
        maxZoom: 19,
      }
    );
    var satLabels = L.tileLayer(
      "https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",
      { attribution: "", maxZoom: 19 }
    );
    state.basemapLayers.sat = L.layerGroup([satImagery, satLabels]);
    state.basemapLayers.dark.addTo(state.map);
    state.basemap = "dark";
    addBasemapToggleControl();

    var loaderEl = document.getElementById("ss-map-loader");
    var fade = function () { if (loaderEl) loaderEl.classList.add("fade"); };
    state.map.whenReady(fade);
    setTimeout(fade, 1200);

    drawObservatories();
    drawPorts();
  }

  function switchBasemap(which) {
    if (!state.map || !state.basemapLayers[which]) return;
    if (state.basemap === which) return;
    var prev = state.basemapLayers[state.basemap];
    var next = state.basemapLayers[which];
    if (prev) state.map.removeLayer(prev);
    next.addTo(state.map);
    state.basemap = which;
    var root = document.querySelector(".ss-basemap-toggle");
    if (root) {
      root.querySelectorAll(".ss-basemap-btn").forEach(function (b) {
        b.classList.toggle("active", b.getAttribute("data-basemap") === which);
      });
    }
  }

  function addBasemapToggleControl() {
    if (!state.map || typeof L === "undefined") return;
    var Ctrl = L.Control.extend({
      options: { position: "topright" },
      onAdd: function () {
        var div = L.DomUtil.create("div", "ss-basemap-toggle");
        div.innerHTML =
          '<button type="button" class="ss-basemap-btn active" data-basemap="dark">DARK</button>' +
          '<button type="button" class="ss-basemap-btn" data-basemap="sat">SAT</button>';
        L.DomEvent.disableClickPropagation(div);
        L.DomEvent.disableScrollPropagation(div);
        div.querySelectorAll(".ss-basemap-btn").forEach(function (b) {
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

  // Render major-port pulsing markers — fetched once, no refresh.
  function drawPorts() {
    fetch("/api/scan-signal/ports", { cache: "no-store" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (!d || !Array.isArray(d.ports)) return;
        d.ports.forEach(function (p) {
          if (typeof p.lat !== "number" || typeof p.lon !== "number") return;
          var icon = L.divIcon({
            className: "ss-port-marker",
            html: "<span class='ss-port-core'></span>",
            iconSize: [12, 12],
            iconAnchor: [6, 6],
          });
          var m = L.marker([p.lat, p.lon], {
            icon: icon,
            title: p.name,
            keyboard: false,
            interactive: true,
          }).addTo(state.map);
          var country = (state.lang === "en" ? p.country_en : p.country_fr) || p.country_iso || "";
          var tipHtml = "<strong>" + escapeHtml(p.name) + "</strong>"
                      + (country ? "<br>" + escapeHtml(country) : "");
          m.bindTooltip(tipHtml, {
            permanent: false,
            direction: "top",
            offset: [0, -8],
            className: "ss-port-tip",
            opacity: 1,
          });
          state.portMarkers.push(m);
        });
      })
      .catch(function () { /* ports optional — degrade gracefully */ });
  }

  function drawObservatories() {
    fetch("/api/ground-assets/network", { cache: "no-store" })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        var obs = (d && d.observatories) || [];
        obs.forEach(function (o) {
          if (typeof o.lat !== "number" || typeof o.lon !== "number") return;
          var icon = L.divIcon({
            className: "ss-obs-marker" + (o.is_home ? " home" : ""),
            html: "<span class='core'></span>",
            iconSize: [14, 14],
            iconAnchor: [7, 7],
          });
          var m = L.marker([o.lat, o.lon], { icon: icon, title: o.name }).addTo(state.map);
          m.bindTooltip(o.name, { permanent: false, direction: "top", offset: [0, -8], className: "ss-obs-tip" });
          state.obsMarkers.push({ obs: o, marker: m });
        });
      })
      .catch(function () { /* observatories optional */ });
  }

  function setVesselMarker(lat, lon, headingDeg) {
    if (!state.map) return;
    var rot = (typeof headingDeg === "number" && isFinite(headingDeg)) ? headingDeg : 0;
    // The third sonar ring + the ping-burst span need to live inside the
    // marker DOM so their CSS animations align with the marker centre.
    var html = "<span class='core' style='transform:rotate(" + rot + "deg)'>"
             +   "<svg viewBox='0 0 24 24' width='22' height='22' aria-hidden='true'>"
             +     "<path d='M12 2 L18 20 L12 16 L6 20 Z' fill='currentColor' stroke='#fff' stroke-width='1' stroke-linejoin='round'/>"
             +   "</svg>"
             + "</span>"
             + "<span class='ss-radar-ring-3' aria-hidden='true'></span>"
             + "<span class='ss-ping-burst' aria-hidden='true'></span>";
    var icon = L.divIcon({
      className: "ss-vessel-marker",
      html: html,
      iconSize: [28, 28],
      iconAnchor: [14, 14],
    });
    if (!state.vesselMarker) {
      state.vesselMarker = L.marker([lat, lon], { icon: icon, zIndexOffset: 1000 }).addTo(state.map);
    } else {
      state.vesselMarker.setLatLng([lat, lon]);
      state.vesselMarker.setIcon(icon);
    }
  }

  // ──────────────────────────────────────────────────────────────────
  // Live effects — speed glow, radar lock, AIS ping flash, vessel trail
  // ──────────────────────────────────────────────────────────────────

  function applyVesselSpeedClass(marker, sogKnots) {
    if (!marker || !marker._icon) return;
    var el = marker._icon;
    el.classList.remove(
      "ss-vessel-marker--speed-stationary",
      "ss-vessel-marker--speed-slow",
      "ss-vessel-marker--speed-cruise",
      "ss-vessel-marker--speed-fast"
    );
    var v = (typeof sogKnots === "number" && isFinite(sogKnots)) ? sogKnots : null;
    if (v == null || v < 0.1) {
      el.classList.add("ss-vessel-marker--speed-stationary");
    } else if (v < 5) {
      el.classList.add("ss-vessel-marker--speed-slow");
    } else if (v < 15) {
      el.classList.add("ss-vessel-marker--speed-cruise");
    } else {
      el.classList.add("ss-vessel-marker--speed-fast");
    }
  }

  function lockVesselMarker(marker) {
    if (marker && marker._icon) marker._icon.classList.add("ss-vessel-marker--locked");
  }

  function unlockVesselMarker(marker) {
    if (marker && marker._icon) marker._icon.classList.remove("ss-vessel-marker--locked");
  }

  function flashAisReceived(marker) {
    if (!marker || !marker._icon) return;
    var el = marker._icon;
    // restart animation: remove → reflow → add
    el.classList.remove("ss-vessel-marker--ping");
    void el.offsetWidth;
    el.classList.add("ss-vessel-marker--ping");
    setTimeout(function () {
      if (marker._icon) marker._icon.classList.remove("ss-vessel-marker--ping");
    }, 360);
  }

  function clearVesselTrail() {
    if (state.vesselTrail) {
      state.map.removeLayer(state.vesselTrail);
      state.vesselTrail = null;
    }
  }

  function drawVesselTrack(mmsi) {
    if (!mmsi || !state.map) return;
    fetch("/api/scan-signal/vessel/" + encodeURIComponent(mmsi) + "/track", { cache: "no-store" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        clearVesselTrail();
        if (!d || !Array.isArray(d.track) || d.track.length < 2) return;
        var pts = d.track
          .filter(function (p) { return typeof p.lat === "number" && typeof p.lon === "number"; })
          .map(function (p) { return [p.lat, p.lon]; });
        if (pts.length < 2) return;
        // Multi-segment polyline with linearly graduating opacity:
        // oldest segment = 0.15, newest = 0.80.
        var n = pts.length;
        var segs = [];
        for (var i = 0; i < n - 1; i++) {
          var t = (n - 1 === 0) ? 1 : (i / (n - 1));
          var opacity = 0.15 + (0.65 * t);
          var seg = L.polyline([pts[i], pts[i + 1]], {
            className: "ss-vessel-trail",
            weight: 1.5,
            opacity: opacity,
            interactive: false,
          });
          segs.push(seg);
        }
        state.vesselTrail = L.layerGroup(segs).addTo(state.map);
      })
      .catch(function () { /* trail is decorative — degrade gracefully */ });
  }

  function clearLinks() {
    state.linkLines.forEach(function (ln) { state.map.removeLayer(ln); });
    state.linkLines = [];
  }

  function drawLinks(targetLat, targetLon, antennas) {
    clearLinks();
    if (!Array.isArray(antennas)) return;
    antennas.forEach(function (a) {
      if (typeof a.antenna_lat !== "number" || typeof a.antenna_lon !== "number") return;
      var cls = "ss-link-line";
      if (a.quality === "WEAK") cls += " weak";
      if (a.quality === "MARGINAL") cls += " marginal";
      var line = L.polyline(
        [[a.antenna_lat, a.antenna_lon], [targetLat, targetLon]],
        { className: cls, weight: 1.4, opacity: 0.95, interactive: false }
      ).addTo(state.map);
      state.linkLines.push(line);
    });
  }

  function flyToTarget(lat, lon, opts) {
    if (!state.map) return;
    var z = (opts && typeof opts.zoom === "number") ? opts.zoom : 7;
    var dur = (opts && typeof opts.duration === "number") ? opts.duration : 1.2;
    state.map.flyTo([lat, lon], z, { animate: true, duration: dur });
  }

  // ──────────────────────────────────────────────────────────────────
  // Search
  // ──────────────────────────────────────────────────────────────────

  function setupSearchUi() {
    var input = document.getElementById("ss-search-input");
    var btn   = document.getElementById("ss-search-btn");
    var dd    = document.getElementById("ss-search-dropdown");
    if (!input || !btn || !dd) return;

    input.addEventListener("input", function () {
      var q = input.value.trim();
      clearTimeout(state.searchTimer);
      if (!q) { hideDropdown(); return; }
      state.searchTimer = setTimeout(function () { runSearch(q); }, SEARCH_DEBOUNCE_MS);
    });
    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter") {
        e.preventDefault();
        triggerScanFromInput();
      }
      if (e.key === "Escape") {
        hideDropdown();
      }
    });
    btn.addEventListener("click", triggerScanFromInput);

    document.addEventListener("click", function (e) {
      if (!dd.contains(e.target) && e.target !== input) hideDropdown();
    });
  }

  function runSearch(q) {
    fetch("/api/scan-signal/vessel/search?q=" + encodeURIComponent(q), { cache: "no-store" })
      .then(function (r) { return r.json(); })
      .then(function (d) { renderDropdown(d); })
      .catch(function () { hideDropdown(); });
  }

  function renderDropdown(d) {
    var dd = document.getElementById("ss-search-dropdown");
    if (!dd) return;
    if (!d || !Array.isArray(d.matches) || !d.matches.length) {
      dd.innerHTML = "<div class='ss-search-row more'>"
        + (state.lang === "en" ? "No vessels match — try a wider query or wait for AIS data." : "Aucun navire trouvé — essayez une requête plus large ou attendez les données AIS.")
        + "</div>";
      dd.classList.add("visible");
      return;
    }
    var html = "";
    d.matches.forEach(function (m) {
      html += "<div class='ss-search-row' data-mmsi='" + escapeHtml(m.mmsi) + "'>"
        + "<span>" + escapeHtml(m.name) + "</span>"
        + "<span class='ss-row-norad'>MMSI " + escapeHtml(m.mmsi) + "</span>"
      + "</div>";
    });
    var hidden = (d.total_found || 0) - (d.showing || d.matches.length);
    if (hidden > 0) {
      var lbl = (state.lang === "en")
        ? "+ " + hidden + " more matches"
        : "+ " + hidden + " résultats supplémentaires";
      html += "<div class='ss-search-row more'>" + lbl + "</div>";
    }
    dd.innerHTML = html;
    dd.classList.add("visible");
    dd.querySelectorAll(".ss-search-row[data-mmsi]").forEach(function (row) {
      row.addEventListener("click", function () {
        var m = row.getAttribute("data-mmsi");
        if (m) {
          hideDropdown();
          beginScan(m);
        }
      });
    });
  }

  function hideDropdown() {
    var dd = document.getElementById("ss-search-dropdown");
    if (dd) dd.classList.remove("visible");
  }

  function triggerScanFromInput() {
    var input = document.getElementById("ss-search-input");
    if (!input) return;
    var q = input.value.trim();
    if (!q) return;
    hideDropdown();
    if (/^\d{6,}$/.test(q)) {
      beginScan(q);
      return;
    }
    fetch("/api/scan-signal/vessel/search?q=" + encodeURIComponent(q), { cache: "no-store" })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (d && d.matches && d.matches.length) beginScan(d.matches[0].mmsi);
      })
      .catch(function () {});
  }

  // ──────────────────────────────────────────────────────────────────
  // Recent vessels (replaces "popular" grid)
  // ──────────────────────────────────────────────────────────────────

  function loadRecent() {
    fetch("/api/scan-signal/vessel/recent?limit=12", { cache: "no-store" })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        renderRecentChips((d && d.items) || []);
        var size = (d && d.cache_size) || 0;
        setText("ss-stat-cache", size);
      })
      .catch(function () {});
  }

  function renderRecentChips(items) {
    var host = document.getElementById("ss-popular-chips");
    if (!host) return;
    if (!items.length) {
      host.innerHTML = "<div class='ss-popular-empty'>"
        + (state.lang === "en"
            ? "Awaiting AIS messages — chips will appear shortly."
            : "En attente des messages AIS — les chips apparaîtront bientôt.")
        + "</div>";
      return;
    }
    var html = "";
    items.forEach(function (it) {
      var label = it.name || ("MMSI " + it.mmsi);
      html += "<button class='ss-chip' data-mmsi='" + escapeHtml(it.mmsi) + "' title='MMSI " + escapeHtml(it.mmsi) + "'>"
        + "<span class='ss-chip-icon'>🚢</span>"
        + "<span>" + escapeHtml(label) + "</span>"
      + "</button>";
    });
    host.innerHTML = html;
    host.querySelectorAll(".ss-chip").forEach(function (chip) {
      chip.addEventListener("click", function () {
        var m = chip.getAttribute("data-mmsi");
        if (m) beginScan(m);
      });
    });
  }

  // ──────────────────────────────────────────────────────────────────
  // Scan flow
  // ──────────────────────────────────────────────────────────────────

  function beginScan(mmsi) {
    var input = document.getElementById("ss-search-input");
    if (input) input.classList.add("pulsing");
    var btn = document.getElementById("ss-search-btn");
    if (btn) btn.classList.add("busy");

    var idleEl = document.getElementById("ss-side-idle");
    var hudEl  = document.getElementById("ss-hud");
    var acqEl  = document.getElementById("ss-acquire");
    if (idleEl) idleEl.style.display = "none";
    if (hudEl)  hudEl.classList.remove("visible");
    if (acqEl && global.SSCinematic) {
      global.SSCinematic.showAcquisition(acqEl, state.lang, function () {
        if (acqEl) acqEl.classList.remove("visible");
        if (hudEl) hudEl.classList.add("visible");
      });
    }

    pingActivity("vessel");

    fetch("/api/scan-signal/vessel/" + encodeURIComponent(mmsi), { cache: "no-store" })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (d) {
        if (input) input.classList.remove("pulsing");
        if (btn) btn.classList.remove("busy");
        applyVesselState(d, true);
        startRefreshLoop(d.mmsi);
      })
      .catch(function (err) {
        if (input) input.classList.remove("pulsing");
        if (btn) btn.classList.remove("busy");
        if (acqEl) acqEl.classList.remove("visible");
        if (idleEl) idleEl.style.display = "flex";
        console.warn("[scan_signal] vessel scan failed", err);
      });
  }

  function applyVesselState(d, isFirst) {
    if (!d || !d.position) return;
    state.currentMmsi = d.mmsi;
    state.lastFetchAt = Date.now();

    var lat = d.position.latitude;
    var lon = d.position.longitude;
    var hdg = (d.kinematics && (d.kinematics.true_heading_deg != null
              ? d.kinematics.true_heading_deg
              : d.kinematics.cog_deg));

    setVesselMarker(lat, lon, hdg);
    drawLinks(lat, lon, d.antenna_reception);

    // Live effects ----------------------------------------------------
    var sog = d.kinematics ? d.kinematics.sog_knots : null;
    applyVesselSpeedClass(state.vesselMarker, sog);

    if (isFirst) {
      lockVesselMarker(state.vesselMarker);
      drawVesselTrack(d.mmsi);
      // Honest zoom: closer when in a known inland waterway so the river
      // is actually visible at CARTO's zoom level (otherwise vessels look
      // like they're "on land"). Open sea → 8, inland → 10.
      var targetZoom = d.inland_waterway ? 10 : 8;
      setTimeout(function () {
        flyToTarget(lat, lon, { zoom: targetZoom, duration: 1.4 });
      }, 200);
    } else {
      // Detect a fresh AIS update: timestamp changed OR position moved.
      var positionChanged = (lat !== state.lastVesselLat || lon !== state.lastVesselLon);
      var tsChanged = (d.timestamp && d.timestamp !== state.lastVesselTimestamp);
      if (tsChanged || positionChanged) {
        flashAisReceived(state.vesselMarker);
        // Refresh the trail when there's likely a new history sample.
        drawVesselTrack(d.mmsi);
      }
    }
    state.lastVesselTimestamp = d.timestamp || state.lastVesselTimestamp;
    state.lastVesselLat = lat;
    state.lastVesselLon = lon;

    var hudEl = document.getElementById("ss-hud");
    if (hudEl && global.SSVesselRender) {
      var fresh = Math.floor((Date.now() - state.lastFetchAt) / 1000);
      global.SSVesselRender.renderHud(hudEl, d, state.lang, fresh);
    }
  }

  function startRefreshLoop(mmsi) {
    if (state.refreshTimer) clearInterval(state.refreshTimer);
    state.refreshTimer = setInterval(function () {
      fetch("/api/scan-signal/vessel/" + encodeURIComponent(mmsi), { cache: "no-store" })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (d) { if (d) applyVesselState(d, false); })
        .catch(function () {});
    }, REFRESH_MS);
  }

  function stopRefreshLoop() {
    if (state.refreshTimer) {
      clearInterval(state.refreshTimer);
      state.refreshTimer = null;
    }
  }

  function newScan() {
    stopRefreshLoop();
    state.currentMmsi = null;
    if (state.vesselMarker) {
      unlockVesselMarker(state.vesselMarker);
      state.map.removeLayer(state.vesselMarker);
      state.vesselMarker = null;
    }
    clearLinks();
    clearVesselTrail();
    state.lastVesselTimestamp = null;
    state.lastVesselLat = null;
    state.lastVesselLon = null;
    var hudEl = document.getElementById("ss-hud");
    var idleEl = document.getElementById("ss-side-idle");
    if (hudEl) hudEl.classList.remove("visible");
    if (idleEl) idleEl.style.display = "flex";
    var input = document.getElementById("ss-search-input");
    if (input) { input.value = ""; input.focus(); }
    if (state.map) state.map.flyTo([20, 0], 2, { animate: true, duration: 0.8 });
  }

  function setupHudActions() {
    document.addEventListener("click", function (e) {
      var t = e.target;
      if (!t || !t.getAttribute) return;
      // Walk up if click landed on inner button glyph
      var action = t.getAttribute("data-action");
      var node = t;
      while (!action && node && node !== document.body) {
        node = node.parentElement;
        if (node) action = node.getAttribute && node.getAttribute("data-action");
      }
      if (!action) return;
      if (action === "new-scan") newScan();
      if (action === "close") newScan();
      if (action === "track-toggle") toggleTracking();
    });
  }

  function toggleTracking() {
    var hudEl = document.getElementById("ss-hud");
    if (!hudEl) return;
    if (hudEl.dataset.tracking === "1") {
      hudEl.dataset.tracking = "0";
      stopRefreshLoop();
    } else {
      hudEl.dataset.tracking = "1";
      if (state.currentMmsi) startRefreshLoop(state.currentMmsi);
    }
    var btn = hudEl.querySelector("[data-action='track-toggle']");
    if (btn && global.SSVesselRender) {
      btn.textContent = hudEl.dataset.tracking === "1"
        ? global.SSVesselRender.t(state.lang, "track_stop")
        : global.SSVesselRender.t(state.lang, "track_continue");
    }
  }

  // ──────────────────────────────────────────────────────────────────
  // Stats / activity
  // ──────────────────────────────────────────────────────────────────

  function refreshStats() {
    Promise.all([
      fetch("/api/scan-signal/stats", { cache: "no-store" }).then(function (r) { return r.json(); }).catch(function () { return null; }),
      fetch("/api/scan-signal/health", { cache: "no-store" }).then(function (r) { return r.json(); }).catch(function () { return null; }),
    ]).then(function (res) {
      var stats = res[0], health = res[1];
      if (stats) {
        var today = (stats.today && stats.today.vessel) || 0;
        var active = (stats.active_now && stats.active_now.vessel) || 0;
        setText("ss-stat-today", today);
        setText("ss-stat-active", active);
      }
      if (health) {
        if (typeof health.vessel_cache_size === "number") {
          setText("ss-stat-cache", health.vessel_cache_size);
        }
        var ais = health.aisstream || {};
        setText("ss-stat-ais", typeof ais.messages_received === "number" ? ais.messages_received : "—");
      }
    });
  }

  function pingActivity(kind) {
    fetch("/api/scan-signal/ping", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ type: kind }),
      cache: "no-store",
    }).then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (!d) return;
        setText("ss-stat-today", d.today_count || 0);
        setText("ss-stat-active", d.active_now || 0);
      })
      .catch(function () {});
  }

  // ──────────────────────────────────────────────────────────────────
  // Helpers
  // ──────────────────────────────────────────────────────────────────

  function startUtcClock() {
    var el = document.getElementById("ss-utc");
    if (!el) return;
    var tick = function () {
      var d = new Date();
      var hh = String(d.getUTCHours()).padStart(2, "0");
      var mm = String(d.getUTCMinutes()).padStart(2, "0");
      var ss = String(d.getUTCSeconds()).padStart(2, "0");
      el.textContent = hh + ":" + mm + ":" + ss + " UTC";
    };
    tick();
    setInterval(tick, 1000);
  }

  function setupLangButtons() {
    document.querySelectorAll(".ss-lang button[data-lang]").forEach(function (b) {
      b.addEventListener("click", function () {
        var l = b.getAttribute("data-lang");
        if (!l) return;
        var u = new URL(window.location.href);
        u.searchParams.set("lang", l);
        window.location.href = u.toString();
      });
    });
  }

  function setText(id, v) {
    var el = document.getElementById(id);
    if (el) el.textContent = String(v);
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"})[c];
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  global.SSApp = {
    state: state,
    beginScan: beginScan,
    newScan: newScan,
    switchTab: switchTab,
  };
})(window);
