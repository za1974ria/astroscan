/* ============================================================
   GROUND ASSETS NETWORK — frontend (orchestration)
   Polls /api/ground-assets/network every 5 s and updates
   markers in place (no full re-render) for smooth motion.
   Rendering helpers live in render.js (window.GroundAssetsRender).
   ============================================================ */
(function () {
  'use strict';

  const POLL_NETWORK_MS = 5000;
  const POLL_EVENTS_MS = 8000;
  const ZOOM_DETAIL_THRESHOLD = 4;

  const state = {
    lang: (document.documentElement.dataset.lang || 'fr'),
    filter: 'all',
    selectedId: null,
    network: null,
    eventTimestamps: new Set(),
    map: null,
    svgRenderer: null,
    layers: {
      observatories: null,
      missions: null,
      balloons: null,
      links: null,
      radar: null,
      badges: null,
    },
    markers: {},
    linkLayers: {},   // keyed by obs_id|target_id
    radarLayers: {},  // keyed by asset id
    badgeLayers: {},  // keyed by obs_id|target_id (primary only)
  };

  // ── i18n ──────────────────────────────────────────────────────────
  const I18N = {
    fr: {
      title: 'RÉSEAU AU SOL',
      live: 'EN DIRECT',
      filter_all: 'TOUS',
      filter_obs: 'OBS',
      filter_msn: 'MISS',
      filter_bal: 'BALL',
      stat_obs: 'OBS',
      stat_msn: 'MISS',
      stat_bal: 'BALL',
      stat_links: 'LIENS',
      panel_overview: 'APERÇU DU RÉSEAU',
      panel_stations: 'DÉTAIL DES STATIONS',
      panel_recent: 'ACTIVITÉ RÉCENTE',
      panel_select: 'Sélectionnez un actif sur la carte',
      detail_close: '✕',
      ov_obs: 'OBSERVATOIRES',
      ov_msn: 'MISSIONS',
      ov_bal: 'BALLONS',
      ov_links: 'LIENS ACTIFS',
      type_observatory: 'OBSERVATOIRE',
      type_mission: 'MISSION DE TERRAIN',
      type_balloon: 'BALLON STRATOSPHÉRIQUE',
      k_coords: 'COORDONNÉES',
      k_elev: 'ALTITUDE',
      k_telescope: 'TÉLESCOPE',
      k_freq: 'FRÉQUENCE',
      k_status: 'STATUT',
      k_sun: 'ALTITUDE SOLAIRE',
      k_speed: 'VITESSE',
      k_heading: 'CAP',
      k_target: 'CIBLE',
      k_vehicle: 'VÉHICULE',
      k_payload: 'CHARGE UTILE',
      k_equip: 'ÉQUIPEMENT',
      k_stage: 'PHASE',
      k_vspeed: 'VITESSE VERTICALE',
      k_dist_home: 'DIST. TLEMCEN',
      k_last: 'DERNIER CONTACT',
      k_links: 'LIENS RADIO',
      k_callsign: 'INDICATIF',
      k_leg: 'TRONÇON ACTUEL',
      stream_head: 'FLUX MISSION CONTROL — DIRECT',
      legend_title: '// LEGEND',
      legend_obs: 'ANTENNA NODE',
      legend_msn: 'TRACKED VEHICLE',
      legend_bal: 'STRATO PROBE',
      legend_link: 'RADIO LINK',
      boot_l1: 'INITIALIZING GROUND ASSETS NETWORK...',
      boot_l2: 'ESTABLISHING ANTENNA SYNC...',
      boot_l3: 'TRIANGULATION ENGINE ACTIVE.',
    },
    en: {
      title: 'GROUND ASSETS NETWORK',
      live: 'LIVE',
      filter_all: 'ALL',
      filter_obs: 'OBS',
      filter_msn: 'MISS',
      filter_bal: 'BALL',
      stat_obs: 'OBS',
      stat_msn: 'MISS',
      stat_bal: 'BALL',
      stat_links: 'LINKS',
      panel_overview: 'NETWORK OVERVIEW',
      panel_stations: 'STATIONS DETAIL',
      panel_recent: 'RECENT ACTIVITY',
      panel_select: 'Select an asset on the map',
      detail_close: '✕',
      ov_obs: 'OBSERVATORIES',
      ov_msn: 'MISSIONS',
      ov_bal: 'BALLOONS',
      ov_links: 'ACTIVE LINKS',
      type_observatory: 'OBSERVATORY',
      type_mission: 'FIELD MISSION',
      type_balloon: 'STRATOSPHERIC BALLOON',
      k_coords: 'COORDINATES',
      k_elev: 'ELEVATION',
      k_telescope: 'TELESCOPE',
      k_freq: 'FREQUENCY',
      k_status: 'STATUS',
      k_sun: 'SOLAR ALTITUDE',
      k_speed: 'SPEED',
      k_heading: 'HEADING',
      k_target: 'TARGET',
      k_vehicle: 'VEHICLE',
      k_payload: 'PAYLOAD',
      k_equip: 'EQUIPMENT',
      k_stage: 'STAGE',
      k_vspeed: 'VERTICAL SPEED',
      k_dist_home: 'DIST. FROM TLEMCEN',
      k_last: 'LAST CONTACT',
      k_links: 'RADIO LINKS',
      k_callsign: 'CALLSIGN',
      k_leg: 'CURRENT LEG',
      stream_head: 'MISSION CONTROL STREAM — LIVE',
      legend_title: '// LEGEND',
      legend_obs: 'ANTENNA NODE',
      legend_msn: 'TRACKED VEHICLE',
      legend_bal: 'STRATO PROBE',
      legend_link: 'RADIO LINK',
      boot_l1: 'INITIALIZING GROUND ASSETS NETWORK...',
      boot_l2: 'ESTABLISHING ANTENNA SYNC...',
      boot_l3: 'TRIANGULATION ENGINE ACTIVE.',
    },
  };

  function t(key) {
    return (I18N[state.lang] && I18N[state.lang][key]) || I18N.fr[key] || key;
  }

  // ── SVG icon templates ────────────────────────────────────────────
  // Antenna tower with three radio waves emanating
  const SVG_ANTENNA = (
    '<svg viewBox="0 0 32 32" class="ga-icon ga-icon--antenna" aria-hidden="true">' +
      '<g class="ga-icon-waves">' +
        '<path class="ga-wave w1" d="M16 14 Q22 14 22 8" />' +
        '<path class="ga-wave w2" d="M16 14 Q26 14 26 4" />' +
        '<path class="ga-wave w3" d="M16 14 Q30 14 30 0" />' +
      '</g>' +
      '<g class="ga-icon-tower">' +
        '<path d="M11 30 L13 16 L19 16 L21 30 Z" />' +
        '<line x1="11" y1="22" x2="21" y2="22" />' +
        '<line x1="12" y1="26" x2="20" y2="26" />' +
        '<circle cx="16" cy="14" r="2.4" />' +
      '</g>' +
    '</svg>'
  );

  // Field vehicle (jeep silhouette) topped by a small parabolic dish
  const SVG_VEHICLE = (
    '<svg viewBox="0 0 32 32" class="ga-icon ga-icon--vehicle" aria-hidden="true">' +
      '<g class="ga-icon-dish">' +
        '<path d="M12 14 Q16 8 20 14" />' +
        '<line x1="16" y1="13" x2="16" y2="9" />' +
        '<circle cx="16" cy="8" r="0.9" />' +
      '</g>' +
      '<g class="ga-icon-body">' +
        '<path d="M5 23 L8 17 L24 17 L27 23 Z" />' +
        '<rect x="11" y="13" width="10" height="4" rx="0.5" />' +
        '<circle cx="11" cy="25" r="2.4" />' +
        '<circle cx="21" cy="25" r="2.4" />' +
      '</g>' +
    '</svg>'
  );

  // Stratospheric balloon: envelope + nacelle
  const SVG_BALLOON = (
    '<svg viewBox="0 0 32 32" class="ga-icon ga-icon--balloon" aria-hidden="true">' +
      '<g class="ga-icon-envelope">' +
        '<ellipse cx="16" cy="12" rx="9" ry="11" />' +
        '<line x1="16" y1="2" x2="16" y2="22" />' +
      '</g>' +
      '<g class="ga-icon-gondola">' +
        '<line x1="9" y1="20" x2="14" y2="26" />' +
        '<line x1="23" y1="20" x2="18" y2="26" />' +
        '<rect x="13" y="26" width="6" height="3" rx="0.4" />' +
      '</g>' +
    '</svg>'
  );

  // ── Map ───────────────────────────────────────────────────────────
  function initMap() {
    const map = L.map('ga-leaflet-map', {
      worldCopyJump: true,
      zoomControl: false,
      attributionControl: true,
      preferCanvas: false,
      minZoom: 2,
      maxZoom: 8,
      center: [22, 10],
      zoom: 2,
      zoomSnap: 0.5,
    });
    L.control.zoom({ position: 'topright' }).addTo(map);
    L.tileLayer(
      'https://{s}.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}{r}.png',
      {
        attribution: '© OpenStreetMap · © CARTO',
        subdomains: 'abcd',
        maxZoom: 9,
      }
    ).addTo(map);
    state.map = map;
    state.svgRenderer = L.svg({ padding: 0.5 });
    state.svgRenderer.addTo(map);

    state.layers.links         = L.layerGroup().addTo(map);
    state.layers.radar         = L.layerGroup().addTo(map);
    // Use markercluster for observatories so overlapping nodes at world
    // zoom are grouped (premium SpaceX/Eurocontrol style). Disable cluster
    // at regional zoom (>=5) so individual antenna icons reappear.
    if (typeof L.markerClusterGroup === 'function') {
      state.layers.observatories = L.markerClusterGroup({
        maxClusterRadius: 40,
        showCoverageOnHover: false,
        spiderfyOnMaxZoom: true,
        disableClusteringAtZoom: 5,
        chunkedLoading: true,
        iconCreateFunction: function (cluster) {
          var n = cluster.getChildCount();
          return L.divIcon({
            html: '<div class="ga-cluster-bubble">' + n + '</div>',
            className: 'ga-cluster-icon',
            iconSize: [36, 36],
            iconAnchor: [18, 18],
          });
        },
      }).addTo(map);
    } else {
      state.layers.observatories = L.layerGroup().addTo(map);
    }
    state.layers.balloons      = L.layerGroup().addTo(map);
    state.layers.missions      = L.layerGroup().addTo(map);
    state.layers.badges        = L.layerGroup().addTo(map);

    map.whenReady(function () {
      const loader = document.getElementById('ga-map-loader');
      if (loader) loader.classList.add('fade');
    });

    // Identify the SVG renderer pane so we can scope CSS animations
    map.getContainer().classList.add('ga-leaflet-host');

    // Track zoom level for detail-only overlays (RSSI badges)
    function applyZoomDetail() {
      document.body.classList.toggle(
        'ga-zoom-detail',
        map.getZoom() >= ZOOM_DETAIL_THRESHOLD
      );
    }
    map.on('zoomend', applyZoomDetail);
    applyZoomDetail();
  }

  // ── Markers ───────────────────────────────────────────────────────
  function kindLayer(kind) {
    if (kind === 'mission') return 'missions';
    if (kind === 'balloon') return 'balloons';
    return 'observatories';
  }

  function buildMarker(asset, kind) {
    const home = !!asset.is_home;
    let html, size;

    if (kind === 'mission') {
      html =
        '<div class="ga-marker ga-marker--msn">' +
          '<div class="ga-marker-halo"></div>' +
          SVG_VEHICLE +
        '</div>';
      size = 28;
    } else if (kind === 'balloon') {
      const stage = (asset.stage || '').toLowerCase();
      html =
        '<div class="ga-marker ga-marker--bal' +
          (stage === 'ascending' ? ' is-ascending' : '') +
          (stage === 'descending' ? ' is-descending' : '') + '">' +
          '<div class="ga-marker-halo"></div>' +
          SVG_BALLOON +
        '</div>';
      size = 26;
    } else {
      html =
        '<div class="ga-marker ga-marker--obs' + (home ? ' is-home' : '') + '">' +
          '<div class="ga-marker-halo"></div>' +
          SVG_ANTENNA +
        '</div>';
      size = 34;
    }

    const icon = L.divIcon({
      html: html,
      className: 'ga-marker-icon',
      iconSize: [size, size],
      iconAnchor: [size / 2, size / 2],
    });

    const marker = L.marker([asset.lat, asset.lon], {
      icon: icon,
      title: asset.name,
      keyboard: false,
      riseOnHover: true,
      bubblingMouseEvents: false,
    });

    // Permanent label for missions and balloons (HUD-style)
    if (kind === 'mission') {
      marker.bindTooltip(
        '<span class="ga-label-callsign">' +
          escapeText(asset.callsign || asset.name) + '</span>',
        {
          permanent: true,
          direction: 'bottom',
          offset: [0, size / 2 - 2],
          className: 'ga-label ga-label--mission',
          opacity: 1,
        }
      );
    } else if (kind === 'balloon') {
      const altTxt = asset.altitude_m
        ? Math.round(asset.altitude_m).toLocaleString('en-US').replace(/,/g, ' ') + 'm'
        : '';
      marker.bindTooltip(
        '<span class="ga-label-callsign">' +
          escapeText(asset.callsign || asset.name) + '</span>' +
          (altTxt ? '<span class="ga-label-sep">·</span>' +
                    '<span class="ga-label-alt">' + altTxt + '</span>' : ''),
        {
          permanent: true,
          direction: 'bottom',
          offset: [0, size / 2 - 2],
          className: 'ga-label ga-label--balloon',
          opacity: 1,
        }
      );
    } else {
      // Observatories: tooltip on hover only (keeps map clean at world zoom)
      marker.bindTooltip(asset.name, {
        permanent: false,
        direction: 'top',
        offset: [0, -size / 2],
        className: 'ga-label ga-label--obs-hover',
      });
    }

    marker.on('click', function () { selectAsset(asset.id); });
    marker._gaKind = kind;
    marker._gaId = asset.id;
    marker._gaSize = size;
    return marker;
  }

  function escapeText(s) {
    if (s === null || s === undefined) return '';
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function applyMarker(asset, kind) {
    const id = asset.id;
    let m = state.markers[id];
    if (!m) {
      m = buildMarker(asset, kind);
      state.layers[kindLayer(kind)].addLayer(m);
      state.markers[id] = m;
    } else {
      m.setLatLng([asset.lat, asset.lon]);
      // Refresh balloon altitude label live
      if (kind === 'balloon' && m.getTooltip()) {
        const altTxt = asset.altitude_m
          ? Math.round(asset.altitude_m).toLocaleString('en-US').replace(/,/g, ' ') + 'm'
          : '';
        m.setTooltipContent(
          '<span class="ga-label-callsign">' +
            escapeText(asset.callsign || asset.name) + '</span>' +
            (altTxt ? '<span class="ga-label-sep">·</span>' +
                      '<span class="ga-label-alt">' + altTxt + '</span>' : '')
        );
      }
    }
  }

  function applyAllMarkers(net) {
    const seen = new Set();
    (net.observatories || []).forEach(function (o) {
      seen.add(o.id);
      applyMarker(o, 'observatory');
      const m = state.markers[o.id];
      if (m) {
        const el = m.getElement && m.getElement();
        if (el) {
          const inner = el.querySelector('.ga-marker');
          if (inner) {
            inner.classList.toggle(
              'is-dim',
              o.status === 'maintenance' || o.status === 'standby'
            );
          }
        }
      }
    });
    (net.missions || []).forEach(function (m) {
      seen.add(m.id); applyMarker(m, 'mission');
    });
    (net.balloons || []).forEach(function (b) {
      seen.add(b.id); applyMarker(b, 'balloon');
    });
    Object.keys(state.markers).forEach(function (id) {
      if (!seen.has(id)) {
        const m = state.markers[id];
        state.layers[kindLayer(m._gaKind)].removeLayer(m);
        delete state.markers[id];
      }
    });
    applyFilter();
  }

  // ── Triangulation links ──────────────────────────────────────────
  function linkKey(l) { return l.obs_id + '|' + l.target_id; }

  function applyLinks(net) {
    const obsById = {};
    (net.observatories || []).forEach(function (o) { obsById[o.id] = o; });
    const seen = new Set();

    (net.antennas || []).forEach(function (l) {
      const o = obsById[l.obs_id];
      if (!o) return;
      const key = linkKey(l);
      seen.add(key);

      const coords = [[o.lat, o.lon], [l.target_lat, l.target_lon]];
      let entry = state.linkLayers[key];

      if (!entry) {
        entry = {};
        if (l.primary) {
          entry.base = L.polyline(coords, {
            color: '#D4AF37',
            weight: 2.5,
            opacity: 0.95,
            className: 'ga-link ga-link--primary',
            renderer: state.svgRenderer,
            interactive: false,
            smoothFactor: 1,
          });
          entry.flow = L.polyline(coords, {
            color: '#FFE69A',
            weight: 4.5,
            opacity: 0.9,
            className: 'ga-link ga-link--primary-flow',
            renderer: state.svgRenderer,
            interactive: false,
            smoothFactor: 1,
            lineCap: 'round',
          });
        } else {
          entry.base = L.polyline(coords, {
            color: 'rgba(212,175,55,0.6)',
            weight: 1.5,
            opacity: 1,
            className: 'ga-link ga-link--secondary',
            renderer: state.svgRenderer,
            interactive: false,
            dashArray: '8 6',
            smoothFactor: 1,
          });
        }
        state.layers.links.addLayer(entry.base);
        if (entry.flow) state.layers.links.addLayer(entry.flow);
        state.linkLayers[key] = entry;
      } else {
        entry.base.setLatLngs(coords);
        if (entry.flow) entry.flow.setLatLngs(coords);
      }

      // Primary RSSI badge at midpoint
      if (l.primary) {
        const midLat = (o.lat + l.target_lat) / 2;
        const midLon = (o.lon + l.target_lon) / 2;
        const dbm = (typeof l.rssi_dbm === 'number')
          ? l.rssi_dbm.toFixed(0) + ' dBm'
          : '—';
        let badge = state.badgeLayers[key];
        if (!badge) {
          badge = L.marker([midLat, midLon], {
            icon: L.divIcon({
              className: 'ga-rssi-badge-icon',
              html: '<div class="ga-rssi-badge">' + escapeText(dbm) + '</div>',
              iconSize: [70, 18],
              iconAnchor: [35, 9],
            }),
            interactive: false,
            keyboard: false,
          });
          state.layers.badges.addLayer(badge);
          state.badgeLayers[key] = badge;
        } else {
          badge.setLatLng([midLat, midLon]);
          const el = badge.getElement && badge.getElement();
          if (el) {
            const inner = el.querySelector('.ga-rssi-badge');
            if (inner) inner.textContent = dbm;
          }
        }
      }
    });

    // Sweep stale links
    Object.keys(state.linkLayers).forEach(function (key) {
      if (!seen.has(key)) {
        const entry = state.linkLayers[key];
        if (entry.base) state.layers.links.removeLayer(entry.base);
        if (entry.flow) state.layers.links.removeLayer(entry.flow);
        delete state.linkLayers[key];
      }
    });
    Object.keys(state.badgeLayers).forEach(function (key) {
      if (!seen.has(key)) {
        state.layers.badges.removeLayer(state.badgeLayers[key]);
        delete state.badgeLayers[key];
      }
    });
  }

  // ── Radar uncertainty circles ────────────────────────────────────
  function applyRadar(net) {
    const seen = new Set();

    function bestRssi(targetId) {
      let best = null;
      (net.antennas || []).forEach(function (l) {
        if (l.target_id !== targetId) return;
        if (typeof l.rssi_dbm !== 'number') return;
        if (best === null || l.rssi_dbm > best) best = l.rssi_dbm;
      });
      return best;
    }

    function ensureCircle(asset) {
      const rssi = bestRssi(asset.id);
      if (rssi === null) return;
      // radius_km = (110 + rssi) / 70 * 50  (range 0–50 km)
      let km = (110 + rssi) / 70 * 50;
      if (!isFinite(km) || km < 0) km = 0;
      if (km > 50) km = 50;
      // visual floor so circle is visible even with strong signal
      if (km < 4) km = 4;
      const meters = km * 1000;

      seen.add(asset.id);
      let c = state.radarLayers[asset.id];
      if (!c) {
        c = L.circle([asset.lat, asset.lon], {
          radius: meters,
          color: '#D4AF37',
          weight: 1,
          opacity: 0.55,
          fillOpacity: 0,
          dashArray: '4 8',
          className: 'ga-radar-circle',
          renderer: state.svgRenderer,
          interactive: false,
        });
        state.layers.radar.addLayer(c);
        state.radarLayers[asset.id] = c;
      } else {
        c.setLatLng([asset.lat, asset.lon]);
        c.setRadius(meters);
      }
    }

    (net.missions || []).forEach(ensureCircle);
    (net.balloons || []).forEach(ensureCircle);

    Object.keys(state.radarLayers).forEach(function (id) {
      if (!seen.has(id)) {
        state.layers.radar.removeLayer(state.radarLayers[id]);
        delete state.radarLayers[id];
      }
    });
  }

  // ── Filters ───────────────────────────────────────────────────────
  function applyFilter() {
    const f = state.filter;
    const show = {
      observatories: (f === 'all' || f === 'observatory'),
      missions:      (f === 'all' || f === 'mission'),
      balloons:      (f === 'all' || f === 'balloon'),
    };
    Object.keys(show).forEach(function (key) {
      const layer = state.layers[key];
      if (!layer) return;
      if (show[key] && !state.map.hasLayer(layer)) state.map.addLayer(layer);
      if (!show[key] && state.map.hasLayer(layer)) state.map.removeLayer(layer);
    });

    // Hide radar/badges when missions+balloons are both hidden
    const showRadar = show.missions || show.balloons;
    if (showRadar && !state.map.hasLayer(state.layers.radar)) {
      state.map.addLayer(state.layers.radar);
    } else if (!showRadar && state.map.hasLayer(state.layers.radar)) {
      state.map.removeLayer(state.layers.radar);
    }
  }

  function bindFilters() {
    document.querySelectorAll('.ga-filter-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        document.querySelectorAll('.ga-filter-btn').forEach(function (b) {
          b.classList.remove('active');
        });
        btn.classList.add('active');
        state.filter = btn.dataset.filter || 'all';
        applyFilter();
      });
    });
  }

  // Toolbar manual refresh — debounced 600ms spin + re-fetch network + events.
  function bindRefresh() {
    var btn = document.getElementById('ga-btn-refresh');
    if (!btn) return;
    btn.addEventListener('click', function () {
      if (btn.classList.contains('spinning')) return;
      btn.classList.add('spinning');
      try { fetchNetwork(); fetchEvents(); } catch (e) { /* noop */ }
      setTimeout(function () { btn.classList.remove('spinning'); }, 650);
    });
  }

  // ── Stats ─────────────────────────────────────────────────────────
  function updateStats(stats) {
    setText('ga-stat-obs',
      stats.observatories_online + ' / ' + stats.observatories_total);
    setText('ga-stat-msn', String(stats.missions_active));
    setText('ga-stat-bal', String(stats.balloons_flying));
    setText('ga-stat-links', String(stats.links_active || 0));
    setText('ga-stat-latency', stats.network_latency_ms + ' MS');
  }

  // ── Asset focus ───────────────────────────────────────────────────
  function selectAsset(id) {
    state.selectedId = id;
    if (state.network) renderDetail();
    document.getElementById('ga-focus').classList.add('open');
    const m = state.markers[id];
    if (m) {
      const target = m.getLatLng();
      state.map.flyTo(target, Math.max(state.map.getZoom(), 4),
                      { duration: 0.8, easeLinearity: 0.35 });
    }
  }

  function clearSelection() {
    state.selectedId = null;
    document.getElementById('ga-network-overview').classList.remove('hidden');
    document.getElementById('ga-detail').classList.remove('active');
    document.getElementById('ga-focus').classList.remove('open');
  }

  function renderDetail() {
    if (!state.selectedId || !state.network) return;
    const id = state.selectedId;
    const net = state.network;
    let asset = null;
    let kind = null;
    (net.observatories || []).forEach(function (o) {
      if (o.id === id) { asset = o; kind = 'observatory'; }
    });
    (net.missions || []).forEach(function (m) {
      if (m.id === id) { asset = m; kind = 'mission'; }
    });
    (net.balloons || []).forEach(function (b) {
      if (b.id === id) { asset = b; kind = 'balloon'; }
    });
    if (!asset) return;
    document.getElementById('ga-network-overview').classList.add('hidden');
    const detail = document.getElementById('ga-detail');
    detail.classList.add('active');
    detail.innerHTML = window.GroundAssetsRender.renderDetailHTML(asset, kind, net, t);
    const closeBtn = detail.querySelector('.ga-detail-close');
    if (closeBtn) closeBtn.addEventListener('click', clearSelection);
  }

  // ── Polling ───────────────────────────────────────────────────────
  function fetchNetwork() {
    fetch('/api/ground-assets/network', { cache: 'no-store' })
      .then(function (r) { return r.json(); })
      .then(function (net) {
        if (!net || net.error) return;
        state.network = net;
        if (net.stats) updateStats(net.stats);
        applyAllMarkers(net);
        applyLinks(net);
        applyRadar(net);
        window.GroundAssetsRender.renderStations(net, t, selectAsset);
        if (state.selectedId) renderDetail();
      })
      .catch(function (e) {
        console.warn('[ground_assets] network fetch failed', e);
      });
  }

  function fetchEvents() {
    fetch('/api/ground-assets/events?limit=40', { cache: 'no-store' })
      .then(function (r) { return r.json(); })
      .then(function (resp) {
        if (!resp || !resp.events) return;
        window.GroundAssetsRender.renderStream(
          resp.events, state.lang, state.eventTimestamps);
        window.GroundAssetsRender.renderRecent(resp.events, state.lang);
        if (state.eventTimestamps.size > 400) state.eventTimestamps = new Set();
      })
      .catch(function () {});
  }

  // Click handler for stream rows that name a station — focus on map.
  function bindStreamFocus() {
    const body = document.getElementById('ga-stream-body');
    if (!body) return;
    body.addEventListener('click', function (ev) {
      const row = ev.target.closest('.ga-stream-row[data-station]');
      if (!row) return;
      const id = row.getAttribute('data-station');
      if (id && state.markers[id]) selectAsset(id);
    });
  }

  function updateUTC() {
    const el = document.getElementById('ga-utc');
    if (!el) return;
    const d = new Date();
    el.textContent =
      ('0' + d.getUTCHours()).slice(-2) + ':' +
      ('0' + d.getUTCMinutes()).slice(-2) + ':' +
      ('0' + d.getUTCSeconds()).slice(-2) + ' UTC';
  }

  // ── Lang ──────────────────────────────────────────────────────────
  function bindLang() {
    document.querySelectorAll('.ga-lang button').forEach(function (b) {
      b.addEventListener('click', function () {
        const lang = b.dataset.lang;
        if (!lang || lang === state.lang) return;
        state.lang = lang;
        document.documentElement.dataset.lang = lang;
        document.querySelectorAll('.ga-lang button').forEach(function (x) {
          x.classList.toggle('active', x.dataset.lang === lang);
        });
        applyTranslations();
        state.eventTimestamps = new Set();
        const body = document.getElementById('ga-stream-body');
        if (body) body.innerHTML = '';
        fetchEvents();
        if (state.selectedId) renderDetail();
        try { fetch('/set-lang/' + lang, { credentials: 'same-origin' }); }
        catch (e) {}
      });
    });
  }

  function applyTranslations() {
    document.querySelectorAll('[data-i18n]').forEach(function (el) {
      el.textContent = t(el.dataset.i18n);
    });
  }

  function bindMobileStream() {
    const head = document.querySelector('.ga-stream-head');
    const stream = document.querySelector('.ga-stream');
    if (!head || !stream) return;
    head.addEventListener('click', function () {
      if (window.innerWidth <= 900) stream.classList.toggle('open');
    });
  }

  // ── Legend (HUD card top-left of map) ────────────────────────────
  function injectLegend() {
    const host = document.querySelector('.ga-map');
    if (!host) return;
    if (host.querySelector('.ga-legend')) return;

    const el = document.createElement('div');
    el.className = 'ga-legend';
    el.innerHTML =
      '<button class="ga-legend-title" type="button" aria-expanded="true">' +
        '<span data-i18n="legend_title">' + escapeText(t('legend_title')) + '</span>' +
        '<span class="ga-legend-chevron">▾</span>' +
      '</button>' +
      '<div class="ga-legend-body">' +
        '<div class="ga-legend-row">' +
          '<svg class="ga-legend-ic gold" viewBox="0 0 12 12">' +
            '<path d="M6 1 L11 6 L6 11 L1 6 Z" />' +
          '</svg>' +
          '<span data-i18n="legend_obs">' + escapeText(t('legend_obs')) + '</span>' +
        '</div>' +
        '<div class="ga-legend-row">' +
          '<svg class="ga-legend-ic cyan" viewBox="0 0 12 12">' +
            '<path d="M6 1 L11 11 L1 11 Z" />' +
          '</svg>' +
          '<span data-i18n="legend_msn">' + escapeText(t('legend_msn')) + '</span>' +
        '</div>' +
        '<div class="ga-legend-row">' +
          '<svg class="ga-legend-ic white" viewBox="0 0 12 12">' +
            '<circle cx="6" cy="6" r="4" />' +
          '</svg>' +
          '<span data-i18n="legend_bal">' + escapeText(t('legend_bal')) + '</span>' +
        '</div>' +
        '<div class="ga-legend-row">' +
          '<svg class="ga-legend-ic gold" viewBox="0 0 16 12">' +
            '<line x1="1" y1="6" x2="13" y2="6" stroke-width="1.4"/>' +
            '<path d="M11 3 L15 6 L11 9 Z"/>' +
          '</svg>' +
          '<span data-i18n="legend_link">' + escapeText(t('legend_link')) + '</span>' +
        '</div>' +
      '</div>';
    host.appendChild(el);

    const titleBtn = el.querySelector('.ga-legend-title');
    titleBtn.addEventListener('click', function () {
      el.classList.toggle('is-collapsed');
      titleBtn.setAttribute('aria-expanded',
        el.classList.contains('is-collapsed') ? 'false' : 'true');
    });
  }

  // ── HUD overlay (corner brackets, scan line, grid is CSS-driven) ──
  function injectHUD() {
    const host = document.querySelector('.ga-map');
    if (!host) return;
    if (host.querySelector('.ga-hud')) return;

    const el = document.createElement('div');
    el.className = 'ga-hud';
    el.setAttribute('aria-hidden', 'true');
    el.innerHTML =
      '<div class="ga-hud-grid"></div>' +
      '<svg class="ga-hud-bracket tl" viewBox="0 0 30 30">' +
        '<path d="M0 12 L0 0 L12 0" />' +
      '</svg>' +
      '<svg class="ga-hud-bracket tr" viewBox="0 0 30 30">' +
        '<path d="M18 0 L30 0 L30 12" />' +
      '</svg>' +
      '<svg class="ga-hud-bracket bl" viewBox="0 0 30 30">' +
        '<path d="M0 18 L0 30 L12 30" />' +
      '</svg>' +
      '<svg class="ga-hud-bracket br" viewBox="0 0 30 30">' +
        '<path d="M18 30 L30 30 L30 18" />' +
      '</svg>' +
      '<div class="ga-hud-scan"></div>';
    host.appendChild(el);
  }

  // ── Boot sequence ────────────────────────────────────────────────
  function runBootSequence() {
    const boot = document.getElementById('ga-boot');
    if (!boot) return;
    // Remove after sequence completes (1.2s + fade 0.3s)
    setTimeout(function () {
      boot.classList.add('is-fading');
      setTimeout(function () {
        if (boot.parentNode) boot.parentNode.removeChild(boot);
      }, 320);
    }, 1200);
  }

  function setText(id, text) {
    const el = document.getElementById(id);
    if (el && el.textContent !== text) el.textContent = text;
  }

  document.addEventListener('DOMContentLoaded', function () {
    state.lang = (document.documentElement.dataset.lang || state.lang);
    applyTranslations();
    runBootSequence();
    initMap();
    injectHUD();
    injectLegend();
    bindFilters();
    bindRefresh();
    bindLang();
    bindMobileStream();
    bindStreamFocus();

    fetchNetwork();
    fetchEvents();
    updateUTC();

    setInterval(fetchNetwork, POLL_NETWORK_MS);
    setInterval(fetchEvents, POLL_EVENTS_MS);
    setInterval(updateUTC, 1000);
  });

  window.GroundAssets = {
    select: selectAsset,
    clear: clearSelection,
    state: state,
  };
})();
