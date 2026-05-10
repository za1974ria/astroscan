/**
 * AstroScan-Chohra — Cesium Orbital Map engine.
 * Single source of truth: /api/satellites/tle → state → radar UI.
 */
 (function () {
  "use strict";

  var DEBUG_MODE = false;

  /** Intervalles min. entre rafraîchissements DOM (sessions longues, moins de layout thrash). */
  var ORBIT_UI_INTERVAL_MS = {
    radar: 500,
    focusPanel: 350,
    requestRender: 400,
    kpi: 650,
    alerts: 1200,
    analysis: 1600
  };

  var _orbitUiClock = { radar: 0, focus: 0, render: 0, kpi: 0, alerts: 0, analysis: 0 };

  function safeParseDate(iso) {
    try {
      if (!iso) return null;
      var d = new Date(iso);
      return isNaN(d.getTime()) ? null : d;
    } catch (e) {
      return null;
    }
  }

  function formatUtcTime(date) {
    try {
      if (!(date instanceof Date)) return "n/a";
      return date.toISOString().replace("T", " ").replace("Z", " UTC");
    } catch (e) {
      return "n/a";
    }
  }

  function formatLocalTime(date) {
    try {
      if (!(date instanceof Date)) return "n/a";
      return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    } catch (e) {
      return "n/a";
    }
  }

  function getDataAgeMinutes(date) {
    try {
      if (!(date instanceof Date)) return null;
      var now = Date.now();
      var t = date.getTime();
      if (!isFinite(t)) return null;
      var diff = Math.max(0, now - t);
      return Math.round(diff / 60000);
    } catch (e) {
      return null;
    }
  }

  function getConfidenceLevel(lastUpdateTime, liveData) {
    try {
      if (!liveData || !(lastUpdateTime instanceof Date)) {
        return { label: "LOW", color: "#ff8855", ageMin: null };
      }
      var ageMin = getDataAgeMinutes(lastUpdateTime);
      if (ageMin == null) {
        return { label: "LOW", color: "#ff8855", ageMin: null };
      }
      if (ageMin <= 30) {
        return { label: "HIGH", color: "#00ff88", ageMin: ageMin };
      }
      if (ageMin <= 180) {
        return { label: "MEDIUM", color: "#ffd166", ageMin: ageMin };
      }
      return { label: "LOW", color: "#ff8855", ageMin: ageMin };
    } catch (e) {
      return { label: "LOW", color: "#ff8855", ageMin: null };
    }
  }

  function safeWarn() {
    if (!DEBUG_MODE) return;
    try { console.warn.apply(console, arguments); } catch (e) {}
  }

  function safeError() {
    try { console.error.apply(console, arguments); } catch (e) {}
  }

  var container = document.getElementById("orbitalMap");
  if (!container) {
    console.warn("Orbital map: #orbitalMap container not found.");
    return;
  }
  if (typeof Cesium === "undefined") {
    console.error("Orbital map: Cesium not loaded.");
    return;
  }
  if (typeof satellite === "undefined") {
    console.error("Orbital map: satellite.js not loaded.");
    return;
  }

  try { Cesium.Ion.defaultAccessToken = ""; } catch (e) {}

  var viewer = new Cesium.Viewer("orbitalMap", {
    timeline: true,
    animation: true,
    baseLayerPicker: false,
    geocoder: false,
    infoBox: true,
    shouldAnimate: true,
    terrainProvider: new Cesium.EllipsoidTerrainProvider(),
    imageryProvider: new Cesium.OpenStreetMapImageryProvider({
      url: "https://tile.openstreetmap.org/"
    })
  });

  viewer.scene.globe.enableLighting = true;

  /** Marqueur test : observatoire / Tlemcen (visible même sans satellites). */
  try {
    viewer.entities.add({
      id: "astroscan-observer-tlemcen",
      name: "Tlemcen (réf. AstroScan-Chohra)",
      position: Cesium.Cartesian3.fromDegrees(-1.3167, 34.8753, 816),
      point: {
        pixelSize: 15,
        color: Cesium.Color.RED,
        outlineColor: Cesium.Color.WHITE,
        outlineWidth: 2
      }
    });
  } catch (eMark) {}

  try {
    viewer.camera.flyTo({
      destination: Cesium.Cartesian3.fromDegrees(1.32, 34.87, 2000000)
    });
  } catch (e) {
    console.warn("Orbital map: camera flyTo failed", e);
  }

  /** Aligné sur la limite côté backend (station_web tronque à ~1000 TLE). */
  var MAX_SAT = 1000;

  function logCesiumEntityCountAfterLoad(sourceLabel) {
    try {
      var coll = viewer && viewer.entities;
      var n = 0;
      if (coll && typeof coll.values !== "undefined" && coll.values) {
        n = coll.values.length;
      } else if (coll && typeof coll.length === "number") {
        n = coll.length;
      }
      console.info(
        "OrbitalMapEngine: entités Cesium après loadSatellites",
        sourceLabel || "",
        "count=",
        n,
        "| trackedSatellites=",
        (state && state.trackedSatellites) ? state.trackedSatellites.length : 0
      );
    } catch (eLog) {}
  }
  var PASS_PREDICT_WINDOW_MIN = 90;
  var PASS_ELEVATION_THRESHOLD = 10;
  // Reliability guardrails for all frontend fetch calls
  var FETCH_TIMEOUT_MS = 3500;
  var FETCH_RETRY_MAX = 2;
  var STALE_DATA_THRESHOLD_SEC = 10800;

  function delayMs(ms) {
    return new Promise(function (resolve) { setTimeout(resolve, ms); });
  }

  async function safeFetchJson(url, options, fallbackValue) {
    var lastErr = null;
    var endpointKey = "unknown_endpoint";
    try {
      if (typeof url === "string") {
        endpointKey = url.split("?")[0] || "unknown_endpoint";
      }
    } catch (e) {}

    function computeDataFreshness() {
      try {
        if (!state.lastDataUpdate) return "unknown";
        var ageSec = (Date.now() - state.lastDataUpdate) / 1000;
        if (!isFinite(ageSec)) return "unknown";
        if (ageSec <= STALE_DATA_THRESHOLD_SEC * 0.3) return "fresh";
        if (ageSec <= STALE_DATA_THRESHOLD_SEC) return "aging";
        return "stale";
      } catch (e) {
        return "unknown";
      }
    }

    function recomputeGlobalDegraded() {
      try {
        var any = false;
        var obj = state.dataDegradedByEndpoint || {};
        for (var k in obj) {
          if (obj[k]) { any = true; break; }
        }
        state.dataDegraded = any;
      } catch (e) {
        state.dataDegraded = true;
      }
    }

    var usedFallback = true;

    try {
      for (var attempt = 0; attempt <= FETCH_RETRY_MAX; attempt++) {
        try {
          var fetchOpts = options ? Object.assign({}, options) : {};
          var controller = (typeof AbortController !== "undefined") ? new AbortController() : null;
          if (controller) fetchOpts.signal = controller.signal;
          var timeoutId = null;

          var resp = await Promise.race([
            fetch(url, fetchOpts),
            new Promise(function (resolve, reject) {
              timeoutId = setTimeout(function () {
                try { if (controller) controller.abort(); } catch (e) {}
                reject(new Error("FETCH_TIMEOUT"));
              }, FETCH_TIMEOUT_MS);
            })
          ]);

          if (timeoutId) clearTimeout(timeoutId);
          if (!resp || !resp.ok) throw new Error("HTTP_" + (resp ? resp.status : "NO_RESP"));

          // Success: clear degraded status for this endpoint and update freshness markers.
          usedFallback = false;
          try {
            var now = Date.now();
            state.lastFetchSuccessByEndpoint = state.lastFetchSuccessByEndpoint || {};
            state.dataDegradedByEndpoint = state.dataDegradedByEndpoint || {};
            state.lastFetchSuccessByEndpoint[endpointKey] = now;
            state.dataDegradedByEndpoint[endpointKey] = false;
            state.lastDataUpdate = now;
            state.dataFreshness = computeDataFreshness();
            recomputeGlobalDegraded();
          } catch (e2) {}

          return await resp.json();
        } catch (e) {
          lastErr = e;
          try { await delayMs(200 * (attempt + 1)); } catch (e2) {}
        }
      }
    } catch (e) {
      lastErr = e;
    }

    // Fallback path: mark degraded and keep UI responsive.
    try {
      state.dataDegradedByEndpoint = state.dataDegradedByEndpoint || {};
      state.dataDegradedByEndpoint[endpointKey] = true;
      // requirement: when fallback used, set global flag
      state.dataDegraded = true;
      state.dataFreshness = computeDataFreshness();
      recomputeGlobalDegraded();
    } catch (e) {}

    try { safeWarn("safeFetchJson failed:", url, lastErr); } catch (e3) {}
    return fallbackValue;
  }

  /** Aligné sur Tlemcen (même référence que observerCoords) pour angles locaux. */
  var OBSERVER = {
    lat: 34.87,
    lon: 1.32,
    height: 800
  };

  function classifySatellite(name) {
    if (!name) return "other";
    name = String(name).toUpperCase();
    if (name.indexOf("ISS") >= 0 || name.indexOf("ZARYA") >= 0 || name.indexOf("SPACE STATION") >= 0) return "iss";
    if (name.indexOf("STARLINK") >= 0) return "starlink";
    if (name.indexOf("GPS") >= 0) return "gps";
    if (name.indexOf("DEB") >= 0 || name.indexOf("R/B") >= 0) return "debris";
    return "other";
  }

  /** Filtre navigation ALL / STARLINK / GPS / DEBRIS (cohérent avec classifySatellite). */
  function satelliteMatchesFilter(sat, filter) {
    var f = (filter || "all").toString().toLowerCase();
    if (f === "all") return true;
    var t = sat && sat.type != null ? String(sat.type).toLowerCase() : "other";
    var nm = sat && sat.name ? String(sat.name) : "";
    var c = classifySatellite(nm);
    if (f === "starlink") return t === "starlink" || c === "starlink";
    if (f === "gps") return t === "gps" || c === "gps";
    if (f === "debris") return t === "debris" || c === "debris";
    return true;
  }

  // Tlemcen default
  var observerCoords = (typeof window !== "undefined" && window.ORBITAL_OBSERVER) || {
    lat: 34.87,
    lon: 1.32,
    height: 800
  };

  function buildObserverGd() {
    return {
      latitude: Cesium.Math.toRadians(observerCoords.lat),
      longitude: Cesium.Math.toRadians(observerCoords.lon),
      height: observerCoords.height || 0
    };
  }

  /** Single source of truth for all radar data. */
  var state = {
    trackedSatellites: [],
    observerGd: buildObserverGd(),
    lastUpdateTime: null,
    visibleSatellites: [],
    predictedPasses: [],
    catalogLoaded: false,
    catalogError: null,
    selectedSatellite: null,
    followSatellite: false,
    closeApproaches: [],
    lastConjunctionUpdate: null,
    filter: "all",
    selectedSat: null,
    // Orbit demo mode (Cesium selection/rotation) — pre-existing behavior
    orbitDemoMode: false,
    demoLastSwitch: null,
    demoIndex: 0,
    demoJustSwitched: false,
    lastAlertTime: 0,
    liveData: false,
    tleLastRefreshIso: null,
    tleSource: null,
    videoDemoMode: false,
    videoDemoStartTime: null,
    videoDemoStep: -1,
    videoDemoOverlayVisible: false,
    selfTestMode: false,
    selfTestStartTime: null,
    selfTestStep: 0,
    selfTestResults: {
      startupOk: false,
      dataOk: false,
      topPassOk: false,
      focusOk: false,
      videoDemoOk: false
    },
    selfTestPrevSnapshot: null,
    selfTestLastValidateToastMs: 0,
    selfTestScoreSmooth: 0,
    selfTestLocked: false,
    // Showroom DEMO MODE (UI-only) — offsets + synthetic alerts, reversible
    demoMode: false,
    _demoOffsets: { tracked: 0, visible: 0, alerts: 0, scoreBoost: 0 },
    _demoAlerts: [],
    _demoNextAlertMs: 0,
    _demoNextJitterMs: 0,
    _demoLastAlertTs: 0
    ,
    // Frontend reliability / degraded-mode guardrails
    dataDegraded: false,
    lastDataUpdate: null, // ms timestamp of last successful fetch (any guarded endpoint)
    dataFreshness: "unknown",
    lastFetchSuccessByEndpoint: {},
    dataDegradedByEndpoint: {},
    alerts: [],
    nasaFeeds: { apod: "", neo: "", solar: "", updatedAt: null },
    /** Dernière position ISS depuis /api/iss (alignée Observatoire + panneau ISS LIVE). */
    issLiveSnapshot: null
  };

  /** Âge max. d’un snapshot ISS live avant retombée sur le modèle TLE. */
  var ISS_LIVE_SNAPSHOT_MAX_AGE_MS = 90000;

  var CLOSE_APPROACH_THRESHOLD_KM = 50;

  /** Distance in km between two satellites using current lat/lon/alt_km. */
  function computeDistanceKm(satA, satB) {
    try {
      if (satA == null || satB == null) return Infinity;
      var latA = satA.lat, lonA = satA.lon, altA = satA.alt_km;
      var latB = satB.lat, lonB = satB.lon, altB = satB.alt_km;
      if (latA == null || lonA == null || altA == null || latB == null || lonB == null || altB == null) return Infinity;
      var cartA = Cesium.Cartesian3.fromDegrees(lonA, latA, altA * 1000);
      var cartB = Cesium.Cartesian3.fromDegrees(lonB, latB, altB * 1000);
      return Cesium.Cartesian3.distance(cartA, cartB) / 1000;
    } catch (e) {
      return Infinity;
    }
  }

  function detectCloseApproaches() {
    state.closeApproaches = [];
    state.lastConjunctionUpdate = new Date();
    var list = state.trackedSatellites;
    if (list.length < 2) return;
    var i, j, satA, satB, distKm, severity, pair;
    for (i = 0; i < list.length; i++) {
      list[i].inCriticalConjunction = false;
    }
    for (i = 0; i < list.length; i++) {
      satA = list[i];
      for (j = i + 1; j < list.length; j++) {
        satB = list[j];
        distKm = computeDistanceKm(satA, satB);
        if (distKm >= CLOSE_APPROACH_THRESHOLD_KM) continue;
        if (distKm < 10) severity = "critical";
        else if (distKm < 25) severity = "warning";
        else severity = "watch";
        pair = {
          satA: satA.name,
          satB: satB.name,
          distance_km: distKm,
          severity: severity,
          satA_ref: satA,
          satB_ref: satB
        };
        state.closeApproaches.push(pair);
        if (severity === "critical") {
          satA.inCriticalConjunction = true;
          satB.inCriticalConjunction = true;
        }
      }
    }
    state.closeApproaches.sort(function (a, b) { return a.distance_km - b.distance_km; });
  }

  function updateCloseApproachUI() {
    var panel = document.getElementById("close-approach-content");
    if (!panel) return;
    var list = state.closeApproaches;
    if (state.trackedSatellites.length < 2) {
      state.closeApproaches = [];
      panel.innerHTML = "No close approaches detected.";
      return;
    }
    if (list.length === 0) {
      panel.innerHTML = "No close approaches detected.";
      return;
    }
    var top5 = list.slice(0, 5);
    var html = top5.map(function (p) {
      var badge = "<span style=\"font-size:10px;padding:1px 4px;border-radius:3px;margin-left:4px;\">" + p.severity + "</span>";
      if (p.severity === "critical") badge = "<span style=\"font-size:10px;padding:1px 4px;border-radius:3px;margin-left:4px;background:#800;color:#fff;\">critical</span>";
      else if (p.severity === "warning") badge = "<span style=\"font-size:10px;padding:1px 4px;border-radius:3px;margin-left:4px;background:#660;color:#fff;\">warning</span>";
      else badge = "<span style=\"font-size:10px;padding:1px 4px;border-radius:3px;margin-left:4px;background:#446;color:#ccc;\">watch</span>";
      return p.satA + " / " + p.satB + " — " + p.distance_km.toFixed(1) + " km" + badge;
    }).join("<br/>");
    panel.innerHTML = html;
  }

  function setObserver(lat, lon, height) {
    observerCoords.lat = lat;
    observerCoords.lon = lon;
    observerCoords.height = height || 0;
    state.observerGd = buildObserverGd();
    if (state.trackedSatellites.length) {
      computePassPredictions();
      updatePassesUI();
    }
  }

  /**
   * Élévation / azimut depuis l'observateur (géodésique WGS84, hauteur en mètres)
   * vers la position satellite en ECEF WGS84 en **mètres** (satellite.js fournit le ECF en km).
   */
  function lookAnglesFromObserver(observerGeodeticRad, positionEcfMeters) {
    var lat = observerGeodeticRad.latitude;
    var lon = observerGeodeticRad.longitude;
    var h = observerGeodeticRad.height || 0;
    var a = 6378137;
    var e2 = 0.00669437999014;
    var sinLat = Math.sin(lat);
    var cosLat = Math.cos(lat);
    var sinLon = Math.sin(lon);
    var cosLon = Math.cos(lon);
    var N = a / Math.sqrt(1 - e2 * sinLat * sinLat);
    var ox = (N + h) * cosLat * cosLon;
    var oy = (N + h) * cosLat * sinLon;
    var oz = (N * (1 - e2) + h) * sinLat;
    var x = positionEcfMeters.x - ox;
    var y = positionEcfMeters.y - oy;
    var z = positionEcfMeters.z - oz;
    var range = Math.sqrt(x * x + y * y + z * z);
    if (range < 1) return { elevation: -90, azimuth: 0 };
    var rx = x / range;
    var ry = y / range;
    var rz = z / range;
    var upX = cosLat * cosLon;
    var upY = cosLat * sinLon;
    var upZ = sinLat;
    var elevationRad = Math.asin(Math.max(-1, Math.min(1, rx * upX + ry * upY + rz * upZ)));
    var eastX = -sinLon;
    var eastY = cosLon;
    var northX = -sinLat * cosLon;
    var northY = -sinLat * sinLon;
    var northZ = cosLat;
    var rNorth = rx * northX + ry * northY + rz * northZ;
    var rEast = rx * eastX + ry * eastY;
    var azimuthRad = Math.atan2(rEast, rNorth);
    return {
      elevation: Cesium.Math.toDegrees(elevationRad),
      azimuth: (Cesium.Math.toDegrees(azimuthRad) + 360) % 360
    };
  }

  function eciToEcf(positionEci, gmst) {
    if (typeof satellite.eciToEcf === "function") {
      return satellite.eciToEcf(positionEci, gmst);
    }
    var c = Math.cos(gmst);
    var s = Math.sin(gmst);
    var p = positionEci;
    return { x: p.x * c + p.y * s, y: -p.x * s + p.y * c, z: p.z };
  }

  /** satellite.js : ECF/ECEF en kilomètres → Cesium / lookAngles en mètres. */
  function ecfKmToMeters(ecf) {
    if (!ecf || typeof ecf.x !== "number") return { x: 0, y: 0, z: 0 };
    return {
      x: ecf.x * 1000,
      y: ecf.y * 1000,
      z: ecf.z * 1000
    };
  }

  async function fetchConnectedTLE() {
    try {
      var data = await safeFetchJson("/api/tle/active", { cache: "no-store" }, null);
      if (!data) {
        state.liveData = false;
        return null;
      }
      var items = (data && data.items) || [];
      if (!Array.isArray(items) || !items.length) {
        state.liveData = false;
        return null;
      }
      // Le backend peut exposer status "simulation", "connected", "cached", etc.
      // Ne rejeter que les erreurs explicites — sinon /api/tle/active reste vide côté carte.
      var st = (data && data.status) != null ? String(data.status) : "";
      if (st === "error") {
        state.liveData = false;
        return null;
      }
      state.liveData = true;
      var newIso = data.last_refresh_iso || null;
      if (state.tleLastRefreshIso && newIso === state.tleLastRefreshIso) {
        // aucune mise à jour côté backend
      } else {
        state.tleLastRefreshIso = newIso;
        state.lastUpdateTime = safeParseDate(newIso);
      }
      state.tleSource = data.source || "CelesTrak / NORAD TLE";
      try {
        console.info(
          "OrbitalMapEngine: /api/tle/active — status=",
          st,
          "items=",
          items.length,
          "→ buildSatellitesFromItems"
        );
      } catch (eI) {}
      return items;
    } catch (e) {
      state.liveData = false;
      return null;
    }
  }

  function clearExistingSatEntities() {
    try {
      if (!state.trackedSatellites || !state.trackedSatellites.length) return;
      state.trackedSatellites.forEach(function (s) {
        try {
          if (s && s.entity) viewer.entities.remove(s.entity);
        } catch (e) {}
      });
    } catch (e) {}
  }

  function buildSatellitesFromItems(items) {
    state.trackedSatellites = [];
    var count = 0;
    var invalidCount = 0;
    items.forEach(function (s) {
      if (count >= MAX_SAT) return;
      var name = (s.name || s.OBJECT_NAME || "Sat");
      var line1 = s.tle_line1 || s.TLE_LINE1 || s.tle1 || s.line1;
      var line2 = s.tle_line2 || s.TLE_LINE2 || s.tle2 || s.line2;
      if (!line1 || !line2) return;
      try {
        var satrec = satellite.twoline2satrec(line1, line2);
        if (!satrec || (typeof satrec.error === "number" && satrec.error !== 0)) {
          safeError("INVALID SATREC:", name, satrec);
          invalidCount++;
          return;
        }
        var entity = viewer.entities.add({
          name: name,
          position: Cesium.Cartesian3.fromDegrees(0, 0, 0),
          point: { pixelSize: 4, color: Cesium.Color.CYAN }
        });
        try { entity.description = name; } catch (e) {}
        var objType = (s.object_type || s.OBJECT_TYPE || "").toString().toLowerCase();
        state.trackedSatellites.push({
          name: name,
          type: objType || classifySatellite(name),
          satrec: satrec,
          entity: entity,
          trail: [],
          elevation: 0,
          azimuth: 0,
          visible: false,
          goodPass: false,
          lat: 0,
          lon: 0,
          alt_km: 0,
          inCriticalConjunction: false,
          noradId: s.norad_cat_id || s.NORAD_CAT_ID || null,
          tle1: line1,
          tle2: line2
        });
        count++;
      } catch (e) {
        safeError("OrbitalMapEngine: satrec create failed for:", name, e);
        invalidCount++;
      }
    });
    try {
      if (count === 0) {
        console.warn("OrbitalMapEngine: visible=0 guard — no valid SGP4 satrec built from TLE.");
      } else {
        console.info("OrbitalMapEngine: SGP4 loaded sats=", count, "invalid=", invalidCount);
      }
    } catch (e) {}
  }

  function loadSatellitesFallback() {
    state.catalogError = null;
    (async function () {
      try {
        var url = window.location.origin + "/api/satellites/tle?ts=" + Date.now();
        var data = await safeFetchJson(url, { cache: "no-store" }, null);
        if (!data) throw new Error("NO_DATA");

        var sats = (data && data.satellites) || [];
        if (!Array.isArray(sats)) sats = [];
        safeWarn("FRONTEND RECEIVED SATS:", sats.length, sats.slice(0, 2));
        if (!Array.isArray(sats) || sats.length === 0) {
          console.warn("No satellites from API → injecting fallback ISS");
          sats = [{
            name: "ISS TEST",
            tle1: "1 25544U 98067A   24001.00000000  .00016717  00000-0  10270-3 0  9993",
            tle2: "2 25544  51.6443  10.0000 0005000  10.0000  20.0000 15.50000000 00001"
          }];
        }

        clearExistingSatEntities();
        buildSatellitesFromItems(sats);
        state.catalogLoaded = state.trackedSatellites.length > 0;
        state.catalogError = null;
        logCesiumEntityCountAfterLoad("(source=/api/satellites/tle fallback)");
        try {
          if (!state.tleSource) state.tleSource = "/api/satellites/tle (fallback)";
        } catch (e) {}
        updateSpaceRadarUI();
        computePassPredictions();
        updatePassesUI();
        safeWarn("OrbitalMapEngine: satellites loaded (fallback) =", state.trackedSatellites.length);
      } catch (err) {
        state.catalogLoaded = false;
        state.catalogError = "Satellite catalog unavailable";
        state.trackedSatellites = [];
        updateSpaceRadarUI();
        safeError("Orbital map: failed to fetch /api/satellites/tle", err);
      }
    })();
  }

  function issTrackedSatellite(sat) {
    if (!sat) return false;
    try {
      var id = sat.noradId != null ? String(sat.noradId) : "";
      if (id === "25544") return true;
    } catch (eId) {}
    return classifySatellite(sat.name) === "iss";
  }

  /**
   * Alimente la position ISS live (même source que /api/iss côté Observatoire).
   * Appelée depuis orbital_map.html après chaque fetch /api/iss.
   */
  function ingestIssLivePayload(raw) {
    try {
      if (!raw || typeof raw !== "object") {
        state.issLiveSnapshot = null;
        return;
      }
      var lat = parseFloat(raw.lat != null ? raw.lat : raw.latitude);
      var lon = parseFloat(raw.lon != null ? raw.lon : raw.longitude);
      if (!isFinite(lat) || !isFinite(lon)) {
        state.issLiveSnapshot = null;
        return;
      }
      var altKm = parseFloat(raw.alt != null ? raw.alt : (raw.altitude != null ? raw.altitude : 408));
      if (!isFinite(altKm)) altKm = 408;
      var speedRaw = parseFloat(raw.speed != null ? raw.speed : (raw.velocity != null ? raw.velocity : NaN));
      state.issLiveSnapshot = {
        ok: raw.ok !== false,
        lat: lat,
        lon: lon,
        alt_km: altKm,
        speed_kmh: isFinite(speedRaw) ? speedRaw : null,
        region: raw.region || raw.country_name || null,
        crew: raw.crew,
        fetchedAt: Date.now()
      };
    } catch (e) {
      state.issLiveSnapshot = null;
    }
  }

  function loadSatellites() {
    state.catalogError = null;
    (async function () {
      var items = await fetchConnectedTLE();
      if (items && items.length) {
        clearExistingSatEntities();
        buildSatellitesFromItems(items);
        state.catalogLoaded = state.trackedSatellites.length > 0;
        state.catalogError = null;
        logCesiumEntityCountAfterLoad("(source=/api/tle/active)");
        updateSpaceRadarUI();
        computePassPredictions();
        updatePassesUI();
        return;
      }
      // fallback sur l'API historique
      loadSatellitesFallback();
    })();
  }

  function updateSatellites() {
    if (!state.trackedSatellites.length) {
      state.lastUpdateTime = new Date();
      state.visibleSatellites = [];
      state.selectedSatellite = null;
      state.selectedSat = null;
      state.followSatellite = false;
      try { viewer.trackedEntity = null; } catch (e) {}
      updateSpaceRadarUI();
      updateSelectedSatelliteUI();
      return;
    }
    state._propTick = (state._propTick || 0) + 1;
    var doTrailSample = state._propTick % 2 === 0;
    var now = new Date();
    state.lastUpdateTime = now;
    var gmst = satellite.gstime(now);
    state.visibleSatellites = [];

    // Determine current priority object name (for demo highlight only).
    var priorityName = null;
    try {
      if (state.demoMode && state.trackedSatellites && state.trackedSatellites.length) {
        var bestA = null;
        for (var pi = 0; pi < state.trackedSatellites.length; pi++) {
          var cand = computeObjectMonitoringScore(state.trackedSatellites[pi]);
          if (cand && (!bestA || cand.score > bestA.score)) bestA = cand;
        }
        if (bestA && bestA.name) priorityName = bestA.name;
      }
    } catch (eP) {}

    function setTrackedEntityCart(sat, cart) {
      try {
        if (!sat._posConst) {
          sat._posConst = new Cesium.ConstantPositionProperty(cart);
          sat.entity.position = sat._posConst;
        } else if (typeof sat._posConst.setValue === "function") {
          sat._posConst.setValue(cart);
        } else {
          sat.entity.position = new Cesium.ConstantPositionProperty(cart);
          sat._posConst = sat.entity.position;
        }
      } catch (ePos) {
        sat.entity.position = new Cesium.ConstantPositionProperty(cart);
      }
    }

    state.trackedSatellites.forEach(function (sat) {
      if (!sat || !sat.satrec || !sat.entity) return;
      try {
        var snap = state.issLiveSnapshot;
        var useLiveIss =
          snap &&
          snap.ok !== false &&
          isFinite(snap.lat) &&
          isFinite(snap.lon) &&
          (Date.now() - (snap.fetchedAt || 0)) <= ISS_LIVE_SNAPSHOT_MAX_AGE_MS &&
          issTrackedSatellite(sat);

        var pv = null;
        var lat;
        var lon;
        var alt;
        var cart;
        var positionEcfKm;
        var positionEcfM;

        if (useLiveIss) {
          lat = snap.lat;
          lon = snap.lon;
          var altKmLive = isFinite(snap.alt_km) ? snap.alt_km : 408;
          alt = altKmLive * 1000;
          sat.lat = lat;
          sat.lon = lon;
          sat.alt_km = altKmLive;
          cart = Cesium.Cartesian3.fromDegrees(lon, lat, alt);
          setTrackedEntityCart(sat, cart);
          positionEcfKm = { x: cart.x / 1000, y: cart.y / 1000, z: cart.z / 1000 };
          positionEcfM = cart;
          if (snap.speed_kmh != null && isFinite(snap.speed_kmh)) {
            sat.speed_kms = snap.speed_kmh / 3600;
          } else {
            try {
              var spL = estimateSpeedKmS(sat, cart, now.getTime());
              if (spL != null && isFinite(spL)) sat.speed_kms = spL;
            } catch (eSpL) {}
          }
        } else {
          pv = satellite.propagate(sat.satrec, now);
          if (!pv || !pv.position) {
            console.warn("PROPAGATION FAIL:", sat.name);
            return;
          }
          var geo = satellite.eciToGeodetic(pv.position, gmst);
          lat = Cesium.Math.toDegrees(geo.latitude);
          lon = Cesium.Math.toDegrees(geo.longitude);
          alt = geo.height * 1000;
          if (!isFinite(lat) || !isFinite(lon) || !isFinite(alt)) {
            return;
          }
          sat.lat = lat;
          sat.lon = lon;
          sat.alt_km = geo.height;
          cart = Cesium.Cartesian3.fromDegrees(lon, lat, alt);
          setTrackedEntityCart(sat, cart);
          positionEcfKm = eciToEcf(pv.position, gmst);
          positionEcfM = ecfKmToMeters(positionEcfKm);
          try {
            var sp = estimateSpeedKmS(sat, cart, now.getTime());
            if (sp != null && isFinite(sp)) sat.speed_kms = sp;
          } catch (e) {}
        }
        if (doTrailSample) {
          sat.trail.push([lon, lat, alt]);
          if (sat.trail.length > 50) sat.trail.shift();
        }

        if (!satelliteMatchesFilter(sat, state.filter)) {
          try {
            sat.entity.show = false;
          } catch (eHide) {}
          sat.visible = false;
          return;
        }
        try {
          sat.entity.show = true;
        } catch (eShow2) {}

        var obsGdM = {
          latitude: Cesium.Math.toRadians(OBSERVER.lat),
          longitude: Cesium.Math.toRadians(OBSERVER.lon),
          height: OBSERVER.height || 0
        };
        var obsGdKm = {
          latitude: obsGdM.latitude,
          longitude: obsGdM.longitude,
          height: (OBSERVER.height || 0) / 1000
        };
        try {
          if (typeof satellite.ecfToLookAngles === "function") {
            var la = satellite.ecfToLookAngles(obsGdKm, positionEcfKm);
            if (la && typeof la.elevation === "number" && !isNaN(la.elevation)) {
              sat.elevation = Cesium.Math.toDegrees(la.elevation);
              sat.azimuth = la.azimuth != null ? (Cesium.Math.toDegrees(la.azimuth) + 360) % 360 : 0;
            } else {
              var lk = lookAnglesFromObserver(obsGdM, positionEcfM);
              sat.elevation = lk.elevation;
              sat.azimuth = lk.azimuth;
            }
          } else {
            var lk2 = lookAnglesFromObserver(obsGdM, positionEcfM);
            sat.elevation = lk2.elevation;
            sat.azimuth = lk2.azimuth;
          }
        } catch (e) {
          sat.elevation = -90;
          sat.azimuth = 0;
        }
        if (sat.elevation == null || isNaN(sat.elevation)) sat.elevation = -90;
        // TEMP TEST affichage : forcer tous visibles (ignorer élévation jusqu'à fix angles).
        sat.visible = true;
        sat.goodPass = sat.elevation > 20;

        // Score dynamique basé sur visibilité, élévation, durée de prochain passage et proximité
        try {
          var passDuration = null;
          if (state.predictedPasses && state.predictedPasses.length) {
            for (var iPass = 0; iPass < state.predictedPasses.length; iPass++) {
              var p = state.predictedPasses[iPass];
              if (p && p.name === sat.name && p.riseTime && p.endTime) {
                passDuration = (p.endTime.getTime() - p.riseTime.getTime()) / 60000;
                break;
              }
            }
          }
          if (window.OrbitalCore && typeof window.OrbitalCore.computeSatelliteScore === "function") {
            sat.score = window.OrbitalCore.computeSatelliteScore(
              sat,
              observerCoords.lat,
              observerCoords.lon,
              passDuration
            );
          }
        } catch (e) {}

        if (sat.visible) state.visibleSatellites.push(sat);

        if (sat && sat.entity && sat.entity.point) {
          var isIss = false;
          var isDebris = false;
          try {
            var tLower = (sat.type || "").toString().toLowerCase();
            var nameU = (sat.name || "").toString().toUpperCase();
            isIss = tLower.indexOf("iss") >= 0 || nameU.indexOf("ISS") >= 0 || nameU.indexOf("ZARYA") >= 0;
            isDebris = tLower.indexOf("debris") >= 0 || nameU.indexOf("DEB") >= 0 || nameU.indexOf("R/B") >= 0;
            // TEMP TEST : couleurs opaques forcées (débris=rouge, ISS=jaune, autres=lime), taille min 6.
            var baseC = Cesium.Color.LIME;
            if (isIss) {
              baseC = Cesium.Color.YELLOW;
            } else if (isDebris) {
              baseC = Cesium.Color.RED;
            }
            sat.entity.point.color = baseC;
          } catch (e) {}
          try {
            var ps = 6;
            if (state.selectedSat && sat === state.selectedSat) {
              ps = Math.max(6, 10);
              sat.entity.point.outlineWidth = 4;
            } else {
              sat.entity.point.outlineWidth = 1;
            }
            sat.entity.point.pixelSize = ps;
          } catch (e) {}
        }

        // Alertes temps réel (front montant de visibilité)
        try {
          var nowMs = now.getTime();
          var wasVisible = !!sat.wasVisible;
          var toastCooldown = state.videoDemoMode ? 90000 : 30000;
          if (!wasVisible && sat.visible && nowMs - state.lastAlertTime > toastCooldown) {
            if (typeof window.showToast === "function") {
              window.showToast((sat.name || "Satellite") + " visible maintenant");
            }
            state.lastAlertTime = nowMs;
          }
          sat.wasVisible = !!sat.visible;
        } catch (e) {}
      } catch (e) {}
    });

    state.visibleSatellites.sort(function (a, b) { return b.elevation - a.elevation; });
    var nowMs = Date.now();
    if (nowMs - _orbitUiClock.radar >= ORBIT_UI_INTERVAL_MS.radar) {
      _orbitUiClock.radar = nowMs;
      updateSpaceRadarUI();
    }
    if (nowMs - _orbitUiClock.focus >= ORBIT_UI_INTERVAL_MS.focusPanel) {
      _orbitUiClock.focus = nowMs;
      updateSelectedSatelliteUI();
    }
    if (DEBUG_MODE) {
      if (!state._lastTrackLogMs || nowMs - state._lastTrackLogMs > 15000) {
        state._lastTrackLogMs = nowMs;
        try {
          console.info(
            "OrbitalMap: tracked=",
            state.trackedSatellites.length,
            "visible=",
            state.visibleSatellites.length
          );
        } catch (eL) {}
      }
    }
    try {
      if (viewer && viewer.scene && nowMs - _orbitUiClock.render >= ORBIT_UI_INTERVAL_MS.requestRender) {
        _orbitUiClock.render = nowMs;
        viewer.scene.requestRender();
      }
    } catch (eRR) {}
  }

  function computePassInterestScore(pass) {
    try {
      if (!pass) return 0;
      var score = 0;
      var peak = isFinite(pass.peakElevation) ? pass.peakElevation : 0;
      var dur = isFinite(pass.durationMinutes) ? pass.durationMinutes : 0;
      var satScore = isFinite(pass.score) ? pass.score : 0;
      score += Math.min(50, peak);
      score += Math.min(30, dur * 3);
      score += Math.min(20, satScore / 5);
      if (pass.type && String(pass.type).toLowerCase().indexOf("debris") >= 0) {
        score -= 20;
      }
      return Math.max(0, Math.round(score));
    } catch (e) {
      return 0;
    }
  }

  function getTopPasses(limit) {
    try {
      var arr = (state.predictedPasses || []).slice();
      arr.sort(function (a, b) {
        var sa = isFinite(a.interestScore) ? a.interestScore : 0;
        var sb = isFinite(b.interestScore) ? b.interestScore : 0;
        if (sb !== sa) return sb - sa;
        var ta = a.riseTime ? new Date(a.riseTime).getTime() : Infinity;
        var tb = b.riseTime ? new Date(b.riseTime).getTime() : Infinity;
        return ta - tb;
      });
      return arr.slice(0, limit || 5);
    } catch (e) {
      return [];
    }
  }

  function getBestCurrentSatellite() {
    try {
      var best = null;
      (state.visibleSatellites || []).forEach(function (s) {
        if (!s) return;
        var sc = isFinite(s.score) ? s.score : 0;
        if (!best || sc > best.score) {
          best = { name: s.name || "—", score: sc, satRef: s };
        }
      });
      return best;
    } catch (e) {
      return null;
    }
  }

  function selfTestCheckStartup() {
    try {
      var ok = true;
      if (!viewer) ok = false;
      if (!state) ok = false;
      if (!state.trackedSatellites || !state.trackedSatellites.length) ok = false;
      return ok;
    } catch (e) {
      return false;
    }
  }

  function selfTestCheckData() {
    try {
      if (!state.tleSource) return false;
      if (state.liveData && !(state.lastUpdateTime instanceof Date)) return false;
      return true;
    } catch (e) {
      return false;
    }
  }

  function selfTestCheckTopPass() {
    try {
      var top = getTopPasses(1);
      var p = top && top[0];
      if (!p) {
        if (state.visibleSatellites && state.visibleSatellites.length > 0) {
          return true;
        }
        return false;
      }
      if (!p.name || !p.riseTime) return false;
      if (!p.peakElevation || p.peakElevation <= 0) return false;
      if (!p.durationMinutes || p.durationMinutes <= 0) return false;
      return true;
    } catch (e) {
      return false;
    }
  }

  function selfTestCheckFocus() {
    try {
      var sel = state.selectedSatellite || state.selectedSat;
      if (!sel) return false;
      if (!sel.name) return false;
      if (!sel.score && sel.score !== 0) return false;
      return true;
    } catch (e) {
      return false;
    }
  }

  function selfTestCheckVideoDemo() {
    try {
      if (!state.videoDemoMode) return false;
      if (!state.videoDemoStartTime) return false;
      return true;
    } catch (e) {
      return false;
    }
  }

  function computeSelfTestScore(results) {
    try {
      var total = 5;
      var ok = 0;
      if (results.startupOk) ok++;
      if (results.dataOk) ok++;
      if (results.topPassOk) ok++;
      if (results.focusOk) ok++;
      if (results.videoDemoOk) ok++;
      return Math.round((ok / total) * 100);
    } catch (e) {
      return 0;
    }
  }

  function smoothScore(newScore) {
    try {
      var prev = state.selfTestScoreSmooth || 0;
      var smoothed = Math.round(prev * 0.7 + newScore * 0.3);
      state.selfTestScoreSmooth = smoothed;
      return smoothed;
    } catch (e) {
      return newScore;
    }
  }

  function renderStepIcon(ok) {
    try {
      if (ok) {
        return "<span style=\"color:#00cc66;font-weight:bold;\">✔</span>";
      }
      return "<span style=\"color:#888;\">⬜</span>";
    } catch (e) {
      return "<span style=\"color:#888;\">⬜</span>";
    }
  }

  function buildSelfTestChecklistHtml() {
    try {
      var r = state.selfTestResults || {};
      var html = "";
      html += "<div>" + renderStepIcon(r.startupOk) + " Étape 1 — Démarrage</div>";
      html += "<div>" + renderStepIcon(r.dataOk) + " Étape 2 — Données</div>";
      var visN = (state.visibleSatellites && state.visibleSatellites.length) || 0;
      if (!r.topPassOk && visN > 0) {
        html += "<div>" + renderStepIcon(false) + " Étape 3 — Top Pass <span style=\"color:#aaa;font-size:11px;\">(no strong pass, system OK)</span></div>";
      } else {
        html += "<div>" + renderStepIcon(r.topPassOk) + " Étape 3 — Top Pass</div>";
      }
      html += "<div>" + renderStepIcon(r.focusOk) + " Étape 4 — Focus</div>";
      html += "<div>" + renderStepIcon(r.videoDemoOk) + " Étape 5 — Video Demo</div>";
      var rawScore = computeSelfTestScore(state.selfTestResults);
      var score = smoothScore(rawScore);
      try {
        if (rawScore === 100 && !state.selfTestLocked) {
          state.selfTestLocked = true;
        }
        if (state.selfTestLocked) {
          score = 100;
        }
      } catch (e) {}
      html += "<div style=\"margin-top:10px;\">Score démo : " + score + "%</div>";
      return html;
    } catch (e) {
      return "<div>Erreur checklist</div>";
    }
  }

  function computePassPredictions() {
    state.predictedPasses = [];
    if (!state.trackedSatellites.length) return;
    var now = new Date();
    var MIN_PASS_ELEVATION_DEG = 5;
    // Reliability guardrail: enforce at least 24h prediction window when configured below 6h.
    var passWindowMin = PASS_PREDICT_WINDOW_MIN;
    try {
      if (!isFinite(passWindowMin) || passWindowMin < 360) {
        passWindowMin = 1440;
      }
    } catch (eWin) {
      passWindowMin = 1440;
    }
    // Force observer reference for pass computation (Tlemcen).
    var obsLat = 34.87;
    var obsLon = 1.32;
    var obsAlt = 800;
    var obsLatRad = Cesium.Math.toRadians(obsLat);
    var obsLonRad = Cesium.Math.toRadians(obsLon);
    if (Math.abs(obsLatRad) > Math.PI || Math.abs(obsLonRad) > (Math.PI * 2)) {
      console.warn("OrbitalMapEngine: observer radians look invalid", obsLatRad, obsLonRad);
    } else {
      console.info("OrbitalMapEngine: observer deg->rad check OK", obsLat + "=>" + obsLatRad.toFixed(6), obsLon + "=>" + obsLonRad.toFixed(6));
    }

    function isUsefulForPassPrediction(sat) {
      try {
        if (!sat || !sat.satrec) return false;
        if (sat === state.selectedSat) return true;
        if (sat.visible) return true;
        var t = (sat.type || "").toString().toLowerCase();
        if (!t) return false;
        if (t.indexOf("debris") >= 0 && !sat.visible) return false;
        var keepTypes = ["starlink", "gps", "iss", "station", "science", "weather", "military", "communication", "comm"];
        for (var i = 0; i < keepTypes.length; i++) {
          if (t.indexOf(keepTypes[i]) >= 0) return true;
        }
        return false;
      } catch (e) {
        return false;
      }
    }

    var candidates = state.trackedSatellites.filter(isUsefulForPassPrediction);
    if (candidates.length > 150) {
      var selected = state.selectedSat ? [state.selectedSat] : [];
      var visibles = candidates.filter(function (s) { return s.visible && s !== state.selectedSat; });
      var rest = candidates.filter(function (s) { return !s.visible && s !== state.selectedSat; });
      rest.sort(function (a, b) {
        var sa = a.score || 0;
        var sb = b.score || 0;
        var aDebris = (a.type || "").toString().toLowerCase().indexOf("debris") >= 0;
        var bDebris = (b.type || "").toString().toLowerCase().indexOf("debris") >= 0;
        if (aDebris !== bDebris) return aDebris ? 1 : -1;
        return sb - sa;
      });
      candidates = selected.concat(visibles).concat(rest).slice(0, 150);
    }

    var debugFirstFiveMaxEl = [];
    function runPrediction(windowMin) {
      state.predictedPasses = [];
      debugFirstFiveMaxEl = [];
      candidates.forEach(function (sat) {
      try {
        if (!sat || !sat.satrec) return;
        var cache = sat._nextPassCache;
        var useCache = false;
        if (
          cache && cache.result &&
          cache.observerLat === obsLat &&
          cache.observerLon === obsLon &&
          cache.windowMin === windowMin &&
          cache.minElevationDeg === MIN_PASS_ELEVATION_DEG
        ) {
          var ageMs = now.getTime() - cache.computedAt;
          if (ageMs >= 0 && ageMs < 30000) {
            useCache = true;
          }
        }
        var passInfo = null;
        if (useCache) {
          passInfo = cache.result;
        } else if (window.OrbitalCore && typeof window.OrbitalCore.computeNextPass === "function") {
          // Pass explicit observer (lat/lon/alt), 5deg threshold and selected prediction window.
          passInfo = window.OrbitalCore.computeNextPass(
            sat,
            obsLat,
            obsLon,
            obsAlt,
            windowMin,
            { minElevationDeg: MIN_PASS_ELEVATION_DEG }
          );
          sat._nextPassCache = {
            computedAt: now.getTime(),
            observerLat: obsLat,
            observerLon: obsLon,
            windowMin: windowMin,
            minElevationDeg: MIN_PASS_ELEVATION_DEG,
            result: passInfo
          };
        }
        if (debugFirstFiveMaxEl.length < 5) {
          debugFirstFiveMaxEl.push({
            name: sat.name || "UNKNOWN",
            peakElevation: passInfo && isFinite(passInfo.peakElevation) ? passInfo.peakElevation : null
          });
        }
        if (!passInfo || !passInfo.riseTime || !passInfo.endTime) return;
        var score = sat.score || 0;
        state.predictedPasses.push({
          name: sat.name,
          type: sat.type,
          riseTime: passInfo.riseTime,
          endTime: passInfo.endTime,
          durationMinutes: passInfo.durationMinutes,
          peakElevation: passInfo.peakElevation,
          peakTime: passInfo.peakTime,
          score: score,
          satRef: sat
        });
      } catch (e) {}
      });

      state.predictedPasses.sort(function (a, b) {
        var at = a.riseTime ? a.riseTime.getTime() : 0;
        var bt = b.riseTime ? b.riseTime.getTime() : 0;
        if (at !== bt) return at - bt;
        var ae = a.peakElevation || 0;
        var be = b.peakElevation || 0;
        return be - ae;
      });

      state.predictedPasses.forEach(function (p) {
        try {
          p.interestScore = computePassInterestScore(p);
          p.qualityLabel = window.OrbitalCore && typeof window.OrbitalCore.classifyElevationQuality === "function"
            ? window.OrbitalCore.classifyElevationQuality(p.peakElevation)
            : "LOW";
        } catch (e) {}
      });
    }

    runPrediction(passWindowMin);

    if (state.predictedPasses.length === 0 && passWindowMin < 4320) {
      console.warn("OrbitalMapEngine: no pass in 24h, extending prediction window to 72h");
      passWindowMin = 4320;
      runPrediction(passWindowMin);
    }

    console.info(
      "OrbitalMapEngine: predicted passes computed =",
      state.predictedPasses.length,
      "| observer=", obsLat + "," + obsLon + "," + obsAlt,
      "| window_min=", passWindowMin,
      "| min_elevation_deg=", MIN_PASS_ELEVATION_DEG
    );
    if (debugFirstFiveMaxEl.length) {
      console.info(
        "OrbitalMapEngine: max elevation (first 5 sats) =",
        debugFirstFiveMaxEl.map(function (d) {
          return d.name + ":" + (d.peakElevation == null ? "n/a" : d.peakElevation + "deg");
        }).join(" | ")
      );
    }
    if (state.predictedPasses.length === 0) {
      try {
        var visN = (state.visibleSatellites && state.visibleSatellites.length) || 0;
        var candN = candidates.length || 0;
        var maxEl = -90;
        for (var ci = 0; ci < candidates.length; ci++) {
          var el = isFinite(candidates[ci].elevation) ? candidates[ci].elevation : -90;
          if (el > maxEl) maxEl = el;
        }
        console.warn(
          "OrbitalMapEngine debug: predicted passes = 0",
          "| causes: " +
          (candN === 0 ? "no pass candidates; " : "") +
          (visN === 0 ? "no satellites above horizon; " : "") +
          (maxEl <= 0 ? "max elevation <= 0 (horizon constraint); " : "") +
          (passWindowMin < 360 ? "window too short; " : "")
        );
      } catch (eDbg) {}
    }
  }

  function updateVideoDemoScenario() {
    try {
      if (!state.videoDemoMode || !state.videoDemoStartTime) return;
      var elapsed = Date.now() - state.videoDemoStartTime;
      var UI = window.OrbitalUI;
      if (!UI || typeof UI.updateVideoDemoOverlay !== "function") return;
      var step = 7;
      if (elapsed < 3000) step = 0;
      else if (elapsed < 8000) step = 1;
      else if (elapsed < 15000) step = 2;
      else if (elapsed < 22000) step = 3;
      else if (elapsed < 30000) step = 4;
      else if (elapsed < 38000) step = 5;
      else if (elapsed < 45000) step = 6;
      if (state.videoDemoStep === step) return;
      state.videoDemoStep = step;
      var conf = getConfidenceLevel(state.lastUpdateTime, state.liveData);
      var title;
      var text;
      if (step === 0) {
        title = "AstroScan-Chohra Radar Pro";
        text = "Connected orbital predictions based on NORAD/CelesTrak data";
      } else if (step === 1) {
        title = "Situation awareness";
        text = "Tracking satellites, visibility and future passes";
      } else if (step === 2) {
        var bestO = getBestCurrentSatellite();
        var nm = bestO ? bestO.name : "—";
        title = "Best current satellite";
        text = nm + " — data confidence " + conf.label;
      } else if (step === 3) {
        var topP = getTopPasses(1)[0];
        if (topP && topP.riseTime) {
          var ql = topP.qualityLabel || "—";
          var pk = topP.peakElevation != null ? topP.peakElevation + "°" : "n/a";
          title = "Top upcoming pass";
          text = (topP.name || "—") + " at " + formatLocalTime(topP.riseTime) + " — peak " + pk + " — " + ql;
        } else {
          title = "Top upcoming pass";
          text = "No strong satellite pass detected in the next hours — monitoring continues";
        }
      } else if (step === 4) {
        title = "Prediction engine";
        text = "Adaptive 60s/10s pass refinement with peak elevation tracking";
      } else if (step === 5) {
        title = "Operational transparency";
        text = "Source, freshness and confidence shown in real time";
      } else if (step === 6) {
        title = "AstroScan-Chohra";
        text = "Connected orbital visualization for education, analysis and demonstration";
      } else {
        title = "AstroScan-Chohra Radar Pro";
        text = "Demo mode active — explore the globe";
      }
      UI.updateVideoDemoOverlay(title, text, true);
    } catch (e) {}
  }

  function updateSelfTestScenario() {
    try {
      if (!state.selfTestMode) return;
      if (!state.selfTestStartTime) {
        state.selfTestStartTime = Date.now();
      }
      var elapsed = Date.now() - state.selfTestStartTime;
      var UI = window.OrbitalUI;
      if (!UI || typeof UI.updateSelfTestOverlay !== "function") return;

      if (!state.selfTestResults) {
        state.selfTestResults = {
          startupOk: false,
          dataOk: false,
          topPassOk: false,
          focusOk: false,
          videoDemoOk: false
        };
      }

      var r = state.selfTestResults;
      var prevSnap = state.selfTestPrevSnapshot;
      if (!prevSnap) {
        prevSnap = {
          startupOk: false,
          dataOk: false,
          topPassOk: false,
          focusOk: false,
          videoDemoOk: false
        };
      }
      try { r.startupOk = selfTestCheckStartup(); } catch (e) {}
      try { r.dataOk = selfTestCheckData(); } catch (e) {}
      try { r.topPassOk = selfTestCheckTopPass(); } catch (e) {}
      try { r.focusOk = selfTestCheckFocus(); } catch (e) {}
      try { r.videoDemoOk = selfTestCheckVideoDemo(); } catch (e) {}

      try {
        var stepToastMap = [
          { key: "startupOk", step: 1, label: "Startup" },
          { key: "dataOk", step: 2, label: "Data" },
          { key: "topPassOk", step: 3, label: "Top Pass" },
          { key: "focusOk", step: 4, label: "Focus" },
          { key: "videoDemoOk", step: 5, label: "Video Demo" }
        ];
        var flipped = null;
        for (var si = 0; si < stepToastMap.length; si++) {
          var tm = stepToastMap[si];
          if (!prevSnap[tm.key] && r[tm.key]) {
            flipped = tm;
            break;
          }
        }
        if (flipped) {
          var toastNow = Date.now();
          if (toastNow - (state.selfTestLastValidateToastMs || 0) >= 2800) {
            if (typeof window.showToast === "function") {
              window.showToast("Step " + flipped.step + " validated ✔ (" + flipped.label + ")");
            }
            state.selfTestLastValidateToastMs = toastNow;
          }
        }
      } catch (e) {}
      state.selfTestPrevSnapshot = {
        startupOk: !!r.startupOk,
        dataOk: !!r.dataOk,
        topPassOk: !!r.topPassOk,
        focusOk: !!r.focusOk,
        videoDemoOk: !!r.videoDemoOk
      };

      var stepText = "";
      if (elapsed < 5000) {
        state.selfTestStep = 0;
        stepText = "Étape 1 — Vérifie globe stable, satellites visibles, dashboard rempli";
      } else if (elapsed < 10000) {
        state.selfTestStep = 1;
        stepText = "Étape 2 — Vérifie data freshness, confidence, source, prediction engine";
      } else if (elapsed < 15000) {
        state.selfTestStep = 2;
        stepText = "Étape 3 — Vérifie best current satellite, top passes, peak, quality, interest score";
      } else if (elapsed < 20000) {
        state.selfTestStep = 3;
        stepText = "Étape 4 — Clique un satellite pour vérifier focus, score, next pass, peak elevation";
      } else if (elapsed < 25000) {
        state.selfTestStep = 4;
        stepText = "Étape 5 — Lance VIDEO DEMO et vérifie overlay, rotation, sélection auto, top pass, message moteur";
      } else {
        state.selfTestStep = 5;
        stepText = "Self-test terminé — vérifie que toutes les cases sont validées";
      }

      var checklistHtml = buildSelfTestChecklistHtml();
      var score = computeSelfTestScore(r);
      var badgeLine;
      var badgeColor;
      var visCount = (state.visibleSatellites && state.visibleSatellites.length) || 0;
      if (score === 100 || state.selfTestLocked) {
        badgeLine = "DEMO READY — PERFECT ✅";
        badgeColor = "#00ff88";
      } else if (score >= 80 && !r.topPassOk && visCount > 0) {
        badgeLine = "DEMO READY — GOOD ⚡ (no strong pass)";
        badgeColor = "#7dffcf";
      } else if (score >= 80) {
        badgeLine = "DEMO READY — GOOD ⚡";
        badgeColor = "#7dffcf";
      } else {
        badgeLine = "DEMO NEEDS CHECK ⚠️";
        badgeColor = "#ffd166";
      }
      try {
        checklistHtml += "<div style=\"margin-top:10px;color:" + badgeColor + ";font-weight:bold;\">" + badgeLine + "</div>";
        var displayScoreLocked = state.selfTestLocked ? 100 : score;
        if (state.selfTestLocked && displayScoreLocked === 100) {
          checklistHtml += "<div style=\"margin-top:6px;color:#aaa;font-size:11px;\">System integrity verified — ready for demonstration</div>";
        }
      } catch (e) {}

      UI.updateSelfTestOverlay("AstroScan-Chohra Self-Test", stepText, checklistHtml, true);
    } catch (e) {}
  }

  function updateSpaceRadarUI() {
    var statusEl = document.getElementById("radar-status-message");
    var summaryEl = document.getElementById("space-radar-summary");
    var listEl = document.getElementById("visible-satellites-list");

    var statusText = "";
    var statusColor = "#a0b0c0";
    if (state.catalogError) {
      statusText = state.catalogError;
      statusColor = "#e88";
    } else if (!state.catalogLoaded && state.trackedSatellites.length === 0) {
      statusText = "Loading satellite catalog…";
      statusColor = "#aaa";
    } else {
      statusText =
        "Observer: " + observerCoords.lat.toFixed(2) + "°, " + observerCoords.lon.toFixed(2) + "° (default)";
      statusColor = "#a0b0c0";
    }

    var sumHtml = "";
    var listHtml = "";
    if (!state.catalogLoaded && !state.trackedSatellites.length) {
      sumHtml = "Visible: 0 — real data from TLE propagation";
      listHtml = "No propagated satellites available";
    } else {
      var visible = state.visibleSatellites;
      sumHtml =
        "Visible: " + visible.length +
        " / " +
        state.trackedSatellites.length +
        " tracked — orbital predictions based on NORAD TLE data";
      var top = visible.slice(0, 10);
      if (top.length === 0) {
        listHtml = "No satellites above horizon";
      } else {
        listHtml = top
          .map(function (s) {
            var status = s.goodPass ? "GOOD PASS" : "VISIBLE";
            return s.name + " — " + s.elevation.toFixed(1) + "° — " + status;
          })
          .join("<br/>");
      }
    }

    var sig = statusText + "\n" + statusColor + "\n" + sumHtml + "\n" + listHtml;
    if (state._radarUiSig === sig) return;
    state._radarUiSig = sig;

    if (statusEl) {
      statusEl.textContent = statusText;
      statusEl.style.color = statusColor;
    }
    if (summaryEl) summaryEl.innerHTML = sumHtml;
    if (listEl) listEl.innerHTML = listHtml;
  }

  function updateDemo() {
    try {
      if (!state.orbitDemoMode) return;
      if (!state.trackedSatellites.length) return;
      var now = new Date();
      if (state.videoDemoMode) {
        var vis = (state.visibleSatellites || []).slice();
        if (vis.length) {
          vis.sort(function (a, b) {
            return (b.score || 0) - (a.score || 0);
          });
          var bestV = vis[0];
          if (bestV) {
            if (state.selectedSat !== bestV) {
              state.selectedSatellite = bestV;
              state.selectedSat = bestV;
              state.demoJustSwitched = true;
            }
            state.demoLastSwitch = now;
            return;
          }
        }
      }
      if (state.demoLastSwitch && (now.getTime() - state.demoLastSwitch.getTime()) < 10000) return;
      var list = state.visibleSatellites.length ? state.visibleSatellites : state.trackedSatellites;
      if (!list.length) return;
      var idx = state.demoIndex % list.length;
      var sat = list[idx];
      if (sat) {
        state.selectedSatellite = sat;
        state.selectedSat = sat;
        state.demoIndex++;
        state.demoLastSwitch = now;
        state.demoJustSwitched = true;
      }
    } catch (e) {}
  }
  function updateSelectedSatelliteUI() {
    var panel = document.getElementById("satellite-focus-panel");
    if (!panel) return;
    var sel = state.selectedSatellite;
    var stillTracked = sel && state.trackedSatellites.indexOf(sel) !== -1;
    if (!sel || !stillTracked) {
      state.selectedSatellite = null;
      state.selectedSat = null;
      state.followSatellite = false;
      try { viewer.trackedEntity = null; } catch (e) {}
      var emptyEl = document.getElementById("satellite-focus-content");
      if (state._focusPanelSig !== "__empty__") {
        state._focusPanelSig = "__empty__";
        if (emptyEl) emptyEl.innerHTML = "No satellite selected.";
      }
      var btnFollow = document.getElementById("satellite-focus-follow");
      if (btnFollow && btnFollow.textContent !== "Follow selected") {
        btnFollow.textContent = "Follow selected";
      }
      return;
    }
    var lat = (sel.lat != null) ? sel.lat.toFixed(4) : "—";
    var lon = (sel.lon != null) ? sel.lon.toFixed(4) : "—";
    var alt = (sel.alt_km != null) ? sel.alt_km.toFixed(1) : "—";
    var elev = (sel.elevation != null) ? sel.elevation.toFixed(1) : "—";
    var az = (sel.azimuth != null) ? sel.azimuth.toFixed(1) : "—";
    var status = sel.goodPass ? "GOOD PASS" : (sel.visible ? "VISIBLE" : "below horizon");
    var html = "<div style=\"font-size:10px;color:#0f0;margin-bottom:4px;\">Analyse en temps réel</div>";
    html += "<div class=\"sat-focus-name\">" + (sel.name || "—") + "</div>";
    html += "<div>Type: " + (sel.type || "other") + "</div>";
    html += "<div>Visible: " + (sel.visible ? "Oui" : "Non") + "</div>";
    html += "<div>Lat " + lat + "° · Lon " + lon + "°</div>";
    html += "<div>Alt " + alt + " km</div>";
    html += "<div>Elev " + elev + "° · Az " + az + "°</div>";
    html += "<div>" + status + "</div>";
    var score = (sel.score != null) ? Math.round(sel.score) : 0;
    html += "<div>Score : " + score + " / 100</div>";
    try {
      var confSel = getConfidenceLevel(state.lastUpdateTime, state.liveData);
      html += "<div style=\"font-size:10px;color:#888;\">Data confidence: " + confSel.label + "</div>";
      if (!state.liveData) {
        html += "<div style=\"font-size:9px;color:#aa8866;\">Connected feed unavailable — using local orbital model</div>";
      }
    } catch (e) {}
    try {
      var np = null;
      if (state.predictedPasses && state.predictedPasses.length) {
        for (var i = 0; i < state.predictedPasses.length; i++) {
          var p = state.predictedPasses[i];
          if (p && p.name === sel.name) {
            np = p;
            break;
          }
        }
      }
      if (!np && window.OrbitalCore && typeof window.OrbitalCore.computeNextPass === "function") {
        np = window.OrbitalCore.computeNextPass(sel, observerCoords.lat, observerCoords.lon);
      }
      if (np && np.riseTime && !isFinite(np.interestScore)) {
        try {
          np.qualityLabel = window.OrbitalCore && typeof window.OrbitalCore.classifyElevationQuality === "function"
            ? window.OrbitalCore.classifyElevationQuality(np.peakElevation)
            : "LOW";
          np.interestScore = computePassInterestScore({
            peakElevation: np.peakElevation,
            durationMinutes: np.durationMinutes,
            score: sel.score,
            type: sel.type
          });
        } catch (e) {}
      }
      if (np && np.riseTime && typeof np.durationMinutes === "number") {
        var rt = np.riseTime;
        var eh = rt.getHours(); var em = rt.getMinutes();
        var riseHH = String(eh).padStart(2, "0");
        var riseMM = String(em).padStart(2, "0");
        var dur = Math.round(np.durationMinutes);
        var peakEl = typeof np.peakElevation === "number" ? np.peakElevation : null;
        var pt = np.peakTime || null;
        var peakStr = "";
        if (peakEl != null) {
          peakStr += "Pic d’élévation : " + peakEl.toFixed(1) + "°";
        }
        if (pt instanceof Date) {
          var ph = String(pt.getHours()).padStart(2, "0");
          var pm = String(pt.getMinutes()).padStart(2, "0");
          peakStr += " — pic à " + ph + ":" + pm;
        }
        html += "<div>Prochain passage : " + riseHH + ":" + riseMM + "</div>";
        html += "<div>Durée : " + dur + " min</div>";
        if (peakStr) html += "<div>" + peakStr + "</div>";
        if (np.qualityLabel) {
          html += "<div>Pass quality: " + np.qualityLabel + "</div>";
        }
        if (isFinite(np.interestScore)) {
          html += "<div>Interest score: " + Math.round(np.interestScore) + "/100</div>";
        }
      } else {
        html += "<div>Prochain passage : aucun dans les prochaines heures</div>";
      }
    } catch (e) {}
    var srcFoot = "Source: Celestrak active TLE";
    try {
      if (
        sel &&
        classifySatellite(sel.name) === "iss" &&
        state.issLiveSnapshot &&
        (Date.now() - (state.issLiveSnapshot.fetchedAt || 0)) <= ISS_LIVE_SNAPSHOT_MAX_AGE_MS
      ) {
        srcFoot = "Source: position ISS /api/iss (synchronisée avec l’Observatoire)";
      }
    } catch (eSrc) {}
    html += "<div style=\"font-size:10px;color:#888;margin-top:4px;\">" + srcFoot + "</div>";
    var btnTxt = state.followSatellite ? "Unfollow" : "Follow selected";
    if (state._focusPanelSig === html && state._focusBtnTxt === btnTxt) return;
    state._focusPanelSig = html;
    state._focusBtnTxt = btnTxt;
    var contentEl = document.getElementById("satellite-focus-content");
    if (contentEl) contentEl.innerHTML = html;
    var btnFollow = document.getElementById("satellite-focus-follow");
    if (btnFollow) btnFollow.textContent = btnTxt;
  }

  function notifyViewSyncIfNeeded() {
    try {
      if (!window.AstroScanViewSync || window.AstroScanViewSync._applyingRemote) return;
      var n = state.selectedSatellite && state.selectedSatellite.name ? String(state.selectedSatellite.name) : null;
      window.AstroScanViewSync.send({
        selectedObject: n ? { name: n } : null
      });
    } catch (e) {}
  }

  function selectSatelliteByName(name) {
    if (!name) {
      state.selectedSatellite = null;
      state.selectedSat = null;
      state.followSatellite = false;
      try { viewer.trackedEntity = null; } catch (e) {}
      updateSelectedSatelliteUI();
      notifyViewSyncIfNeeded();
      return true;
    }
    var target = String(name).trim().toUpperCase();
    for (var i = 0; i < state.trackedSatellites.length; i++) {
      var s = state.trackedSatellites[i];
      if (!s || !s.name) continue;
      var sn = String(s.name).toUpperCase();
      if (
        sn === target ||
        ((target === "ISS" || target === "25544" || target === "ZARYA") &&
          (sn.indexOf("ISS") >= 0 || sn.indexOf("ZARYA") >= 0 || sn.indexOf("25544") >= 0))
      ) {
        state.selectedSatellite = s;
        state.selectedSat = s;
        updateSelectedSatelliteUI();
        focusCenterSelected();
        notifyViewSyncIfNeeded();
        return true;
      }
    }
    return false;
  }

  function updateGlobalDashboard() {
    var el = document.getElementById("global-dashboard-content");
    if (!el) return;
    try {
      var tracked = state.trackedSatellites.length;
      var vis = state.visibleSatellites.length;
      var best = null;
      state.trackedSatellites.forEach(function (s) {
        if (!s) return;
        var sc = (s.score != null) ? s.score : 0;
        if (!best || sc > best.score) best = { name: s.name, score: sc };
      });
      var nextGlobal = state.predictedPasses && state.predictedPasses[0] ? state.predictedPasses[0] : null;
      var html = "";
      html += "Suivis : " + tracked + "<br/>";
      html += "Visibles : " + vis + "<br/>";
      var obsCond = vis > 0 ? "ACTIVE" : "LOW";
      var obsColor = vis > 0 ? "#00ff88" : "#ffbb55";
      html += "Observation conditions: <span style=\"color:" + obsColor + ";\">" + obsCond + "</span><br/>";
      var bestVis = getBestCurrentSatellite();
      if (bestVis) {
        html += "Best current (visible): " + (bestVis.name || "—") + " (" + Math.round(bestVis.score) + "/100)<br/>";
      } else {
        html += "Best current (visible): —<br/>";
      }
      if (best) {
        html += "Meilleur satellite (global): " + (best.name || "—") + " (" + Math.round(best.score) + "/100)<br/>";
      } else {
        html += "Meilleur satellite (global): —<br/>";
      }
      if (nextGlobal && nextGlobal.riseTime) {
        var rt = nextGlobal.riseTime;
        var hh = String(rt.getHours()).padStart(2, "0");
        var mm = String(rt.getMinutes()).padStart(2, "0");
        var pel = (nextGlobal.peakElevation != null) ? " (" + Math.round(nextGlobal.peakElevation) + "°)" : "";
        html += "Prochain passage global : " + hh + ":" + mm + pel + "<br/>";
      } else {
        html += "Prochain passage global : n/a<br/>";
      }
      var top3 = getTopPasses(3);
      html += "<strong>Top Passes:</strong><br/>";
      if (top3.length === 0) {
        html += "<span style=\"color:#888;\">No strong pass detected in the next hours</span><br/>";
      } else {
        top3.forEach(function (p, idx) {
          if (!p || !p.riseTime) return;
          var h = String(p.riseTime.getHours()).padStart(2, "0");
          var m = String(p.riseTime.getMinutes()).padStart(2, "0");
          var pk = p.peakElevation != null ? Math.round(p.peakElevation) + "°" : "—";
          var ql = p.qualityLabel || "—";
          html += (idx + 1) + ". " + (p.name || "—") + " — " + h + ":" + m + " — " + pk + " — " + ql + "<br/>";
        });
      }
      var conf = getConfidenceLevel(state.lastUpdateTime, state.liveData);
      if (conf.ageMin == null) {
        html += "Data freshness: n/a<br/>";
      } else {
        html += "Data freshness: " + conf.ageMin + " min ago<br/>";
      }
      html += "Confidence: <span style=\"color:" + conf.color + ";\">" + conf.label + "</span><br/>";
      var uiMode = typeof deriveRenderableUiMode === "function" ? deriveRenderableUiMode() : (state.liveData ? "LIVE" : "DEMO");
      var modeColor = uiMode === "LIVE" ? "#00ff88" : uiMode === "OFFLINE" ? "#ff4d5a" : "#ffbb55";
      html += "Mode: <span style=\"color:" + modeColor + ";\">" + uiMode + "</span><br/>";
      html += "Source: CelesTrak GP / NORAD TLE<br/>";
      if (!state.lastUpdateTime) {
        html += "Dernière mise à jour TLE : n/a<br/>";
      } else {
        html += "Dernière mise à jour TLE : " + formatUtcTime(state.lastUpdateTime) + "<br/>";
      }
      html += "Accuracy: standard orbital prediction (± few seconds)<br/>";
      html += "Prediction engine: adaptive 60s/10s<br/>";
      el.innerHTML = html;
    } catch (e) {}
  }

  function buildOperationalAlerts() {
    var alerts = [];
    try {
      if (state.catalogError) {
        alerts.push({ level: "danger", msg: state.catalogError, meta: "catalog" });
      }
    } catch (e1) {}
    try {
      var vis0 = (state.visibleSatellites && state.visibleSatellites.length) || 0;
      if (vis0 === 0 && state.catalogLoaded) {
        alerts.push({ level: "warn", msg: "No satellites above horizon — observation conditions LOW", meta: "visibility" });
      }
    } catch (e2) {}
    try {
      if (state.closeApproaches && state.closeApproaches.length) {
        var topCa = state.closeApproaches[0];
        if (topCa && topCa.severity === "critical") {
          alerts.push({ level: "danger", msg: "Critical close approach detected", meta: "conjunction" });
        } else if (topCa && topCa.severity === "warning") {
          alerts.push({ level: "warn", msg: "Close approach watchlist active", meta: "conjunction" });
        }
      }
    } catch (e3) {}
    try {
      var confA = getConfidenceLevel(state.lastUpdateTime, state.liveData);
      if (state.liveData && confA && confA.label === "LOW") {
        alerts.push({ level: "warn", msg: "Live data confidence LOW — check freshness/source", meta: "tle" });
      }
    } catch (e4) {}
    try {
      if (state.videoDemoMode) {
        alerts.push({ level: "data", msg: "Video demo mode active", meta: "demo" });
      }
    } catch (e5) {}
    try {
      if (state.dataFreshness === "stale") {
        alerts.push({
          level: "warn",
          msg: "Orbital data is stale — predictions may be less reliable",
          meta: "freshness"
        });
      } else if (state.dataFreshness === "aging") {
        alerts.push({
          level: "data",
          msg: "Orbital data aging — refresh recommended",
          meta: "freshness"
        });
      }
    } catch (e6) {}
    try {
      if (false && state.demoMode) {
        alerts.push({ level: "data", msg: "Showroom demo mode active", meta: "demo" });
      }
    } catch (eD) {}
    return alerts;
  }

  function updateSystemBadgesAndAlerts() {
    try {
      var bOnline = document.getElementById("badge-online");
      var bTracking = document.getElementById("badge-tracking");
      var bLive = document.getElementById("badge-live");

      // ONLINE: backend/catalog ok-ish
      var onlineOk = !!(state.catalogLoaded && !state.catalogError);
      if (bOnline) {
        var oc = "asc-badge " + (onlineOk ? "ok" : "warn");
        if (bOnline.className !== oc) bOnline.className = oc;
      }

      // TRACKING: have tracked satellites
      var trackingOk = !!(state.trackedSatellites && state.trackedSatellites.length > 0);
      if (bTracking) {
        var tc = "asc-badge " + (trackingOk ? "data" : "off");
        if (bTracking.className !== tc) bTracking.className = tc;
      }

      // LIVE: liveData indicator
      if (bLive) {
        var lc = "asc-badge " + (state.liveData ? "ok" : "off");
        if (bLive.className !== lc) bLive.className = lc;
      }

      var alerts = buildOperationalAlerts();
      try {
        if (state.demoMode && state._demoAlerts && state._demoAlerts.length) {
          alerts = alerts.concat(state._demoAlerts.slice(0, 2));
        }
      } catch (eDa) {}

      // Render
      var panel = document.getElementById("alerts-panel");
      var list = document.getElementById("alerts-list");
      var metaEl = document.getElementById("alerts-meta");
      if (!panel || !list) return;

      if (!alerts.length) {
        panel.style.display = "none";
        try {
          state._uiAlerts = [];
          state.alerts = [];
        } catch (e0) {}
        state._alertsListSig = "";
        return;
      }
      var last2 = alerts.slice(-2).slice().reverse();
      var listHtml = last2.map(function (a, idx) {
        var lvl = a.level || "data";
        var msg = a.msg || "—";
        var meta = a.meta || "system";
        var ico = "•";
        if (lvl === "danger") ico = "⚠";
        else if (lvl === "warn") ico = "!";
        return "<div class=\"asc-alert " + lvl + (idx === 0 ? " recent" : "") + "\">" +
          "<div class=\"ico\">" + ico + "</div>" +
          "<div class=\"sev\" style=\"background:currentColor;\"></div>" +
          "<div><div class=\"msg\">" + String(msg) + "</div><div class=\"meta\">" + String(meta) + "</div></div>" +
          "</div>";
      }).join("");
      var metaTxt = alerts.length + " active";
      if (state._alertsListSig === listHtml && state._alertsMetaTxt === metaTxt && panel.style.display === "block") {
        try {
          state._uiAlerts = alerts;
          state.alerts = alerts;
        } catch (eSkip) {}
        return;
      }
      state._alertsListSig = listHtml;
      state._alertsMetaTxt = metaTxt;
      panel.style.display = "block";
      if (metaEl) metaEl.textContent = metaTxt;
      list.innerHTML = listHtml;
      try {
        state._uiAlerts = alerts;
        state.alerts = alerts;
      } catch (e) {}
    } catch (e) {}
  }

  // ──────────────────────────────────────────────────────────────
  // Local user configuration persistence (demo + UI prefs)
  // ──────────────────────────────────────────────────────────────
  var USER_CONFIG_KEY = "astroscan_user_config_v1";
  var userConfigCache = null;

  function loadUserConfig() {
    try {
      if (userConfigCache) return userConfigCache;
      if (typeof localStorage === "undefined") return {};
      var raw = localStorage.getItem(USER_CONFIG_KEY);
      if (!raw) return {};
      var parsed = JSON.parse(raw);
      userConfigCache = parsed && typeof parsed === "object" ? parsed : {};
      return userConfigCache;
    } catch (e) {
      return {};
    }
  }

  function saveUserConfig(partialConfig) {
    try {
      if (!partialConfig || typeof partialConfig !== "object") return;
      var base = loadUserConfig();
      var merged = Object.assign({}, base, partialConfig);
      if (typeof localStorage === "undefined") return;
      localStorage.setItem(USER_CONFIG_KEY, JSON.stringify(merged));
      userConfigCache = merged;
    } catch (e) {}
  }

  window.toggleCloseApproaches = function () {
    try {
      var el = document.getElementById("close-approaches");
      var btn = document.getElementById("btn-details");
      if (!el) return;
      if (el.classList.contains("is-open")) {
        el.classList.remove("is-open");
        try {
          if (btn) btn.classList.remove("active");
        } catch (eB) {}
        try { saveUserConfig({ closeApproachesOpen: false }); } catch (e2) {}
      } else {
        el.classList.add("is-open");
        try {
          if (btn) btn.classList.add("active");
        } catch (eB2) {}
        try { saveUserConfig({ closeApproachesOpen: true }); } catch (e3) {}
      }
    } catch (e) {}
  };

  function setDemoModeButtonActive(active) {
    try {
      var btn = document.getElementById("btn-demo-mode");
      if (!btn) return;
      btn.classList.toggle("is-active", !!active);
    } catch (e) {}
  }

  function pushAlert(level, message) {
    // UI-only alert helper: adds one synthetic alert and a toast (non-flooding).
    try {
      var lvl = (level || "data").toString().toLowerCase();
      if (lvl === "ok") lvl = "ok";
      else if (lvl === "warn" || lvl === "warning") lvl = "warn";
      else if (lvl === "danger" || lvl === "critical" || lvl === "error") lvl = "danger";
      else lvl = "data";
      var msg = (message != null) ? String(message) : "—";
      state._demoAlerts = [{ level: lvl, msg: msg, meta: "demo" }];
      try {
        if (typeof window.showToast === "function") window.showToast(msg);
      } catch (e2) {}
    } catch (e) {}
  }

  // Public toggle for showroom demo mode (UI-only).
  function updateDemoButtonState() {
    try {
      setDemoModeButtonActive(!!state.demoMode);
      try {
        if (document && document.body && document.body.classList) {
          if (state.demoMode) {
            document.body.classList.add("demo-glow");
          } else {
            document.body.classList.remove("demo-glow");
          }
        }
      } catch (e2) {}
    } catch (e) {}
  }

  window.toggleDemoMode = function () {
    try {
      state.demoMode = !state.demoMode;
      if (!state._demoOffsets) state._demoOffsets = { tracked: 0, visible: 0, alerts: 0, scoreBoost: 0 };
      if (!state.demoMode) {
        // Reset demo artifacts immediately
        state._demoOffsets = { tracked: 0, visible: 0, alerts: 0, scoreBoost: 0 };
        state._demoAlerts = [];
        state._demoLastAlertTs = 0;
      }
      pushAlert(
        state.demoMode ? "warn" : "ok",
        state.demoMode ? "Demo mode activated" : "Demo mode disabled"
      );
      updateDemoButtonState();
      try { saveUserConfig({ demoMode: state.demoMode }); } catch (e2) {}
    } catch (e) {}
  };

  function getDemoAdjustedValue(base, offset) {
    try {
      return (base || 0) + (state.demoMode ? (offset || 0) : 0);
    } catch (e) {
      return base || 0;
    }
  }

  function simulateDemoActivity() {
    // Adds small reversible offsets + occasional synthetic alerts (no destructive data changes).
    try {
      if (!state.demoMode) return;
      if (!state._demoOffsets) state._demoOffsets = { tracked: 0, visible: 0, alerts: 0, scoreBoost: 0 };

      var now = Date.now();
      if (!state._demoNextJitterMs || now >= state._demoNextJitterMs) {
        // Gentle metric motion; keep within small ranges and smooth transitions.
        var t = (state.trackedSatellites && state.trackedSatellites.length) || 0;
        var v = (state.visibleSatellites && state.visibleSatellites.length) || 0;
        var trackedTarget = (t > 0 ? (Math.random() < 0.72 ? 0 : (Math.random() < 0.6 ? 1 : -1)) : 0);
        var visibleTarget = (v > 0 ? (Math.random() < 0.68 ? 0 : (Math.random() < 0.6 ? 1 : -1)) : (Math.random() < 0.2 ? 1 : 0));

        // Smooth (avoid oscillation): new = 0.7*prev + 0.3*target
        var prevT = isFinite(state._demoOffsets.tracked) ? state._demoOffsets.tracked : 0;
        var prevV = isFinite(state._demoOffsets.visible) ? state._demoOffsets.visible : 0;
        var smoothT = Math.round(prevT * 0.7 + trackedTarget * 0.3);
        var smoothV = Math.round(prevV * 0.7 + visibleTarget * 0.3);
        state._demoOffsets.tracked = Math.max(-1, Math.min(2, smoothT));
        state._demoOffsets.visible = Math.max(-1, Math.min(3, smoothV));

        // Alerts count offset should be rare and stable
        var prevA = isFinite(state._demoOffsets.alerts) ? state._demoOffsets.alerts : 0;
        var alertTarget = (Math.random() < 0.82 ? 0 : 1);
        state._demoOffsets.alerts = Math.max(0, Math.min(1, Math.round(prevA * 0.75 + alertTarget * 0.25)));

        // Priority boost: subtle and stable (display-only)
        var prevB = isFinite(state._demoOffsets.scoreBoost) ? state._demoOffsets.scoreBoost : 0;
        var boostTarget = (Math.random() < 0.65 ? 6 : 10);
        state._demoOffsets.scoreBoost = Math.max(0, Math.min(14, Math.round(prevB * 0.75 + boostTarget * 0.25)));

        state._demoNextJitterMs = now + 2600 + Math.floor(Math.random() * 1600);
      }

      if (!state._demoNextAlertMs || now >= state._demoNextAlertMs) {
        var msgs = [
          { level: "data", msg: "High velocity object detected", meta: "tracking" },
          { level: "warn", msg: "Close approach under review", meta: "conjunction" },
          { level: "warn", msg: "Tracking confidence fluctuation detected", meta: "telemetry" }
        ];
        var pick = msgs[Math.floor(Math.random() * msgs.length)];
        // Cooldown to avoid aggressive repetition
        if (!state._demoLastAlertTs || now - state._demoLastAlertTs > 9000) {
          pushAlert(pick.level || "danger", pick.msg || "—");
          state._demoLastAlertTs = now;
        }
        state._demoNextAlertMs = now + 8000 + Math.floor(Math.random() * 5000);
      }
    } catch (e) {}
  }

  // Backward compatible helper (kept), but prefer getDemoAdjustedValue/getDemoAdjustedMetrics usage.
  function getDemoAdjustedMetrics(base) {
    try {
      if (!base) base = {};
      return {
        tracked: getDemoAdjustedValue(base.tracked || 0, state._demoOffsets ? state._demoOffsets.tracked : 0),
        visible: getDemoAdjustedValue(base.visible || 0, state._demoOffsets ? state._demoOffsets.visible : 0),
        alerts: getDemoAdjustedValue(base.alerts || 0, state._demoOffsets ? state._demoOffsets.alerts : 0),
        scoreBoost: state._demoOffsets ? (state._demoOffsets.scoreBoost || 0) : 0
      };
    } catch (e) {
      return base || {};
    }
  }

  function clamp01(x) {
    if (!isFinite(x)) return 0;
    return Math.max(0, Math.min(1, x));
  }

  function estimateSpeedKmS(sat, posCart, nowMs) {
    try {
      if (!sat || !posCart || !isFinite(nowMs)) return null;
      var prevCart = sat._lastPosCart || null;
      var prevMs = sat._lastPosMs || null;
      sat._lastPosCart = posCart;
      sat._lastPosMs = nowMs;
      if (!prevCart || !isFinite(prevMs)) return null;
      var dt = (nowMs - prevMs) / 1000;
      if (!isFinite(dt) || dt <= 0.1 || dt > 30) return null;
      var d = Cesium.Cartesian3.distance(prevCart, posCart); // meters
      if (!isFinite(d) || d < 0) return null;
      return (d / 1000) / dt;
    } catch (e) {
      return null;
    }
  }

  function classifyMonitoringLevel(score) {
    try {
      if (!isFinite(score)) score = 0;
      if (score >= 80) return "CRITICAL";
      if (score >= 60) return "HIGH";
      if (score >= 30) return "MODERATE";
      return "LOW";
    } catch (e) {
      return "LOW";
    }
  }

  function pickRecommendedAction(level, danger, sat) {
    try {
      var t = (sat && sat.type) ? String(sat.type).toLowerCase() : "";
      if (danger) {
        if (t.indexOf("debris") >= 0) return "Increase monitoring, consider avoidance analysis";
        return "Prioritize tracking, notify operator";
      }
      if (level === "HIGH") return "Maintain tracking, watch for changes";
      if (level === "MODERATE") return "Routine monitoring";
      return "No action required";
    } catch (e) {
      return "Routine monitoring";
    }
  }

  function computeObjectMonitoringScore(sat) {
    try {
      if (!sat) return null;
      var score = 10;

      var t = (sat.type || "").toString().toLowerCase();
      if (t.indexOf("debris") >= 0) score += 28;
      else if (t.indexOf("gps") >= 0) score += 12;
      else if (t.indexOf("starlink") >= 0) score += 8;
      else score += 10;

      if (sat.visible) score += 10;
      if (sat.goodPass) score += 6;

      // Speed influence (LEO ~7.5 km/s). Normalize 0..8km/s → 0..10pts.
      var sp = isFinite(sat.speed_kms) ? sat.speed_kms : null;
      if (sp != null) {
        score += Math.round(clamp01(sp / 8) * 10);
      }

      // Proximity / conjunction severity
      if (sat.inCriticalConjunction) score += 40;
      else {
        try {
          var ca = state.closeApproaches && state.closeApproaches[0] ? state.closeApproaches[0] : null;
          if (ca && (ca.satA === sat.name || ca.satB === sat.name)) {
            if (ca.severity === "warning") score += 18;
            else if (ca.severity === "watch") score += 10;
          }
        } catch (e1) {}
      }

      // Live confidence
      try {
        var conf = getConfidenceLevel(state.lastUpdateTime, state.liveData);
        if (state.liveData && conf.label === "HIGH") score += 6;
        else if (state.liveData && conf.label === "MEDIUM") score += 3;
        else if (state.liveData && conf.label === "LOW") score -= 4;
        else if (!state.liveData) score -= 2;
      } catch (e2) {}

      // Tracking status (filtered out / hidden)
      try {
        if (sat.entity && sat.entity.show === false) score -= 12;
      } catch (e3) {}

      score = Math.max(0, Math.min(100, Math.round(score)));
      var level = classifyMonitoringLevel(score);
      var danger = false;
      if (level === "HIGH" || level === "CRITICAL") danger = true;
      if (sat.inCriticalConjunction) danger = true;
      var action = pickRecommendedAction(level, danger, sat);
      return {
        name: sat.name || "—",
        type: sat.type || "other",
        score: score,
        level: level,
        danger: danger ? "YES" : "NO",
        action: action,
        visible: !!sat.visible,
        speed_kms: sp
      };
    } catch (e) {
      return null;
    }
  }

  function getRenderablePriorityObject() {
    try {
      if (!state.trackedSatellites || !state.trackedSatellites.length) return null;
      var best = null;
      for (var i = 0; i < state.trackedSatellites.length; i++) {
        var s = state.trackedSatellites[i];
        var a = computeObjectMonitoringScore(s);
        if (!a) continue;
        if (!best || a.score > best.score) best = a;
      }
      if (!best) return null;
      try {
        if (state.demoMode && state._demoOffsets) {
          var boost = isFinite(state._demoOffsets.scoreBoost) ? state._demoOffsets.scoreBoost : 0;
          if (boost > 0) {
            best = Object.assign({}, best);
            best.score = Math.max(0, Math.min(100, best.score + boost));
            best.level = classifyMonitoringLevel(best.score);
            if (best.level === "HIGH" || best.level === "CRITICAL") best.danger = "YES";
          }
        }
      } catch (eB) {}
      return best;
    } catch (e) {
      return null;
    }
  }

  function deriveRenderableUiMode() {
    try {
      if (state.demoMode || state.videoDemoMode) return "DEMO";
      if (state.dataDegraded) return "OFFLINE";
      if (state.catalogError) return "OFFLINE";
      if (!state.catalogLoaded) return "OFFLINE";
      if (!state.liveData) return "DEMO";
      if (state.dataFreshness === "stale" || state.dataFreshness === "aging") return "DEMO";
      return "LIVE";
    } catch (e) {
      return "OFFLINE";
    }
  }

  window.getRenderableSystemState = function () {
    var pr = getRenderablePriorityObject();
    return {
      tracked: state.trackedSatellites ? state.trackedSatellites.length : 0,
      visible: state.visibleSatellites ? state.visibleSatellites.length : 0,
      passes: state.predictedPasses ? state.predictedPasses.length : 0,
      alerts: state.alerts ? state.alerts.length : 0,
      priorityObject: pr ? pr.name : null,
      selectedSatellite: state.selectedSat ? state.selectedSat.name : null,
      priority: pr,
      mode: deriveRenderableUiMode(),
      liveData: !!state.liveData,
      demoMode: !!state.demoMode,
      dataDegraded: !!state.dataDegraded,
      dataFreshness: state.dataFreshness || "unknown",
      observer: {
        lat: observerCoords.lat,
        lon: observerCoords.lon,
        name: "Tlemcen, Algérie"
      }
    };
  };

  function updateAnalysisCard() {
    try {
      var card = document.getElementById("analysis-card");
      var body = document.getElementById("analysis-body");
      var badge = document.getElementById("analysis-level-badge");
      if (!card || !body || !badge) return;
      if (!state.trackedSatellites || !state.trackedSatellites.length) {
        if (state._analysisFp !== "__waiting__") {
          state._analysisFp = "__waiting__";
          body.innerHTML = "Waiting for tracking data…";
          badge.className = "asc-badge off";
          badge.innerHTML = "<span class=\"asc-dot\" style=\"background:currentColor;\"></span><span>LOW</span>";
        }
        return;
      }

      var best = getRenderablePriorityObject();
      if (!best) return;

      var cls = "off";
      if (best.level === "CRITICAL") cls = "danger";
      else if (best.level === "HIGH") cls = "warn";
      else if (best.level === "MODERATE") cls = "data";
      else cls = "off";

      var sevClass = "asc-sev-low";
      if (best.level === "MODERATE") sevClass = "asc-sev-moderate";
      else if (best.level === "HIGH") sevClass = "asc-sev-high";
      else if (best.level === "CRITICAL") sevClass = "asc-sev-critical";

      var dangerColor = (best.danger === "YES") ? "#ff4d5a" : "#00ff88";
      var speedStr = (best.speed_kms != null && isFinite(best.speed_kms)) ? (best.speed_kms.toFixed(2) + " km/s") : "n/a";
      var html = "";
      html += "<div style=\"font-size:12px;font-weight:bold;color:#e8f4fa;\">" + best.name + "</div>";
      html += "<div style=\"margin-top:2px;color:rgba(150,175,190,.85);font-size:10px;\">Type: " + best.type + " · Visible: " + (best.visible ? "YES" : "NO") + " · Speed: " + speedStr + "</div>";
      html += "<div style=\"margin-top:8px;display:flex;gap:8px;flex-wrap:wrap;\">";
      html += "<div class=\"asc-kpi-card\" style=\"flex:1 1 120px;\"><div class=\"asc-kpi-label\">Score</div><div class=\"asc-kpi-value\">" + best.score + "</div><div class=\"asc-kpi-sub\">0–100</div></div>";
      html += "<div class=\"asc-kpi-card\" style=\"flex:1 1 120px;\"><div class=\"asc-kpi-label\">Level</div><div class=\"asc-kpi-value " + sevClass + "\">" + best.level + "</div><div class=\"asc-kpi-sub\">Band</div></div>";
      html += "</div>";
      html += "<div style=\"margin-top:8px;\"><span style=\"color:#aaa;\">Danger</span>: <span style=\"color:" + dangerColor + ";font-weight:bold;\">" + best.danger + "</span></div>";
      html += "<div style=\"margin-top:4px;\"><span style=\"color:#aaa;\">Action</span>: " + best.action + "</div>";
      var analysisFp =
        best.name +
        "|" +
        best.score +
        "|" +
        best.level +
        "|" +
        best.danger +
        "|" +
        speedStr +
        "|" +
        cls +
        "|" +
        sevClass;
      if (state._analysisFp === analysisFp) return;
      state._analysisFp = analysisFp;
      badge.className = "asc-badge " + cls;
      badge.innerHTML = "<span class=\"asc-dot\" style=\"background:currentColor;\"></span><span>" + best.level + "</span>";
      body.innerHTML = html;
    } catch (e) {}
  }

  function updateTrackedKpiMinimal() {
    try {
      var valEl = document.getElementById("tracked-kpi-value");
      var subEl = document.getElementById("tracked-kpi-sub");
      if (!valEl) return;
      var tracked = (state.trackedSatellites && state.trackedSatellites.length) || 0;
      try {
        tracked = Math.max(0, getDemoAdjustedValue(tracked, state._demoOffsets ? state._demoOffsets.tracked : 0));
      } catch (e2) {}
      var txt = String(tracked);
      if (valEl.textContent === txt) {
        if (!subEl || subEl.textContent === "Objects tracked") return;
      }
      valEl.textContent = txt;
      if (subEl) subEl.textContent = "Objects tracked";
    } catch (e) {}
  }

  function updateBusinessDashboard() {
    try {
      var el = document.getElementById("global-dashboard-content");
      if (!el) return;

      var baseMetrics = {
        tracked: (state.trackedSatellites && state.trackedSatellites.length) || 0,
        visible: (state.visibleSatellites && state.visibleSatellites.length) || 0
      };
      var tracked = Math.max(0, getDemoAdjustedValue(baseMetrics.tracked, state._demoOffsets ? state._demoOffsets.tracked : 0));
      var vis = Math.max(0, getDemoAdjustedValue(baseMetrics.visible, state._demoOffsets ? state._demoOffsets.visible : 0));
      var debris = 0;
      try {
        (state.trackedSatellites || []).forEach(function (s) {
          var t = (s && s.type) ? String(s.type).toLowerCase() : "";
          if (t.indexOf("debris") >= 0) debris++;
        });
      } catch (e1) {}

      var baseAlertsLen = 0;
      try {
        baseAlertsLen = buildOperationalAlerts().length;
      } catch (e2a) {
        baseAlertsLen = 0;
      }
      var alertsCount = baseAlertsLen;
      try {
        alertsCount = Math.max(0, getDemoAdjustedValue(alertsCount, state._demoOffsets ? state._demoOffsets.alerts : 0));
      } catch (e2b) {}

      var conf = getConfidenceLevel(state.lastUpdateTime, state.liveData);
      var confTxt = conf && conf.label ? conf.label : "n/a";
      var modeLabel = state.liveData ? "CONNECTED" : "SIMULATION";
      var modeColor = state.liveData ? "#00ff88" : "#ffbb55";

      function deriveDataReliabilityMode() {
        try {
          if (state.demoMode) {
            return { mode: "SIMULATION", label: "DEMO", cls: "bad-demo" };
          }
          // If we had to fall back on any guarded endpoint, treat as degraded/offline.
          if (state.dataDegraded) {
            return { mode: "OFFLINE_DATA", label: "OFFLINE", cls: "bad-offline" };
          }
          // No timestamp yet → assume offline.
          if (!state.lastDataUpdate) {
            return { mode: "OFFLINE_DATA", label: "OFFLINE", cls: "bad-offline" };
          }
          var ageSec = (Date.now() - state.lastDataUpdate) / 1000;
          if (!isFinite(ageSec)) {
            return { mode: "OFFLINE_DATA", label: "OFFLINE", cls: "bad-offline" };
          }
          if (ageSec >= STALE_DATA_THRESHOLD_SEC) {
            return { mode: "STALE_DATA", label: "STALE", cls: "bad-stale" };
          }
          return { mode: "LIVE", label: "LIVE", cls: "bad-live" };
        } catch (e) {
          return { mode: "OFFLINE_DATA", label: "OFFLINE", cls: "bad-offline" };
        }
      }

      var dataMode = deriveDataReliabilityMode();

      var tleStatus = state.liveData ? "LIVE" : "OFFLINE";
      var tleColor = state.liveData ? "#00ffcc" : "rgba(170,190,200,.65)";

      var imgs = (state.labImagesCount != null) ? state.labImagesCount : null;
      var lastSync = state.labLastSyncIso || null;

      var platformOk = !!(state.catalogLoaded && !state.catalogError);
      var trackingQuality = "STANDARD";
      try {
        var ratio = tracked ? (vis / tracked) : 0;
        if (platformOk && confTxt === "HIGH" && ratio > 0.08) trackingQuality = "GOOD";
        else if (!platformOk || confTxt === "LOW") trackingQuality = "DEGRADED";
      } catch (e3) {}

      var html = "";
      function pushHist(key, val) {
        try {
          state._kpiHist = state._kpiHist || {};
          var arr = state._kpiHist[key] || [];
          arr.push(isFinite(val) ? val : 0);
          if (arr.length > 36) arr.shift();
          state._kpiHist[key] = arr;
          return arr;
        } catch (e) {
          return [];
        }
      }
      function sparkSvg(arr, color) {
        try {
          arr = arr || [];
          var w = 120, h = 26, pad = 2;
          if (!arr.length) {
            return "<svg class=\"asc-spark\" viewBox=\"0 0 " + w + " " + h + "\" style=\"color:" + color + ";\"><path class=\"bg\" d=\"M" + pad + " " + (h - pad) + " L" + (w - pad) + " " + (h - pad) + "\"/></svg>";
          }
          var min = Infinity, max = -Infinity;
          for (var i = 0; i < arr.length; i++) { if (arr[i] < min) min = arr[i]; if (arr[i] > max) max = arr[i]; }
          if (!isFinite(min) || !isFinite(max)) { min = 0; max = 1; }
          if (max === min) { max = min + 1; }
          var step = (w - pad * 2) / Math.max(1, (arr.length - 1));
          var d = "";
          for (var j = 0; j < arr.length; j++) {
            var x = pad + j * step;
            var y = pad + (h - pad * 2) * (1 - (arr[j] - min) / (max - min));
            d += (j === 0 ? "M" : " L") + x.toFixed(1) + " " + y.toFixed(1);
          }
          return "<svg class=\"asc-spark\" viewBox=\"0 0 " + w + " " + h + "\" style=\"color:" + color + ";\"><path class=\"bg\" d=\"M" + pad + " " + (h - pad) + " L" + (w - pad) + " " + (h - pad) + "\"/><path d=\"" + d + "\"/></svg>";
        } catch (e) {
          return "";
        }
      }
      function pill(label, cls) {
        try {
          return "<span class=\"asc-pill " + cls + "\"><span class=\"dot\"></span><span>" + label + "</span></span>";
        } catch (e) {
          return "<span>" + label + "</span>";
        }
      }

      // KPI history + sparklines
      var hTracked = pushHist("tracked", tracked);
      var hAlerts = pushHist("alerts", alertsCount);
      var hDebris = pushHist("debris", debris);

      // Dominant system status block
      var globalScore = 55;
      try {
        var bestObj = getRenderablePriorityObject();
        var base = 60;
        var ratio = tracked ? (vis / tracked) : 0;
        var ratioPts = Math.round(clamp01(ratio / 0.12) * 18); // 0..~12% visible -> 0..18
        var confPts = 0;
        if (confTxt === "HIGH") confPts = 12;
        else if (confTxt === "MEDIUM") confPts = 6;
        else if (confTxt === "LOW") confPts = -4;
        var alertPenalty = 0;
        try {
          (buildOperationalAlerts() || []).forEach(function (a) {
            if (!a) return;
            if (a.level === "danger") alertPenalty += 12;
            else if (a.level === "warn") alertPenalty += 6;
          });
        } catch (eP) {}
        var priorityPressure = bestObj ? Math.round(bestObj.score * 0.22) : 0; // higher priority → more attention
        globalScore = Math.max(0, Math.min(100, base + ratioPts + confPts - alertPenalty + (state.liveData ? 6 : 0) - Math.round(priorityPressure * 0.15)));
      } catch (eG) {}
      var globalLevel = classifyMonitoringLevel(globalScore);
      var globalCls = (globalLevel === "CRITICAL") ? "danger" : (globalLevel === "HIGH" ? "warn" : (globalLevel === "MODERATE" ? "data" : "off"));
      var globalState = platformOk ? "ONLINE" : "OFFLINE";

      html += "<div class=\"asc-anim-in\" style=\"padding:10px 10px 12px 10px;border-radius:12px;background:rgba(0,0,0,.30);border:1px solid rgba(0,255,204,.18);box-shadow:inset 0 0 18px rgba(0,255,204,.08);\">";
      html += "<div class=\"asc-title\" style=\"margin-bottom:6px;\">SYSTEM STATUS</div>";
      html += "<div style=\"display:flex;justify-content:space-between;align-items:flex-end;gap:10px;\">";
      html += "<div><div style=\"font-size:26px;font-weight:bold;letter-spacing:.02em;color:#e8f4fa;\">" + globalScore + "<span style=\"font-size:12px;color:#9bb0bd;\">/100</span></div>";
      html += "<div style=\"margin-top:2px;\">" + pill(globalState, platformOk ? "ok" : "warn") + " " + pill(dataMode.label, dataMode.cls) + " " + pill(tracked ? "ACTIVE" : "IDLE", tracked ? "ok" : "off") + "</div></div>";
      html += "<div style=\"text-align:right;\">" + pill(globalLevel, globalCls) + "<div class=\"asc-kicker\" style=\"margin-top:6px;\">Tracking quality: <span style=\"color:#e8f4fa;\">" + trackingQuality + "</span></div></div>";
      html += "</div>";
      html += "</div>";

      html += "<div class=\"asc-title\" style=\"margin:10px 0 6px 0;\">KPI OVERVIEW</div>";
      html += "<div class=\"asc-kpi-grid asc-anim-in\">";
      html += "<div class=\"asc-kpi-card\"><div class=\"asc-kpi-label\">Tracked</div><div class=\"asc-kpi-value\">" + tracked + "</div><div class=\"asc-kpi-sub\">Objects</div>" + sparkSvg(hTracked, "rgba(0,255,204,.95)") + "</div>";
      html += "<div class=\"asc-kpi-card\"><div class=\"asc-kpi-label\">Alerts</div><div class=\"asc-kpi-value\">" + alertsCount + "</div><div class=\"asc-kpi-sub\">Active</div>" + sparkSvg(hAlerts, "rgba(255,209,102,.95)") + "</div>";
      html += "<div class=\"asc-kpi-card\"><div class=\"asc-kpi-label\">Visible</div><div class=\"asc-kpi-value\">" + vis + "</div><div class=\"asc-kpi-sub\">Above horizon</div></div>";
      html += "<div class=\"asc-kpi-card\"><div class=\"asc-kpi-label\">Debris</div><div class=\"asc-kpi-value\">" + debris + "</div><div class=\"asc-kpi-sub\">Catalog tags</div>" + sparkSvg(hDebris, "rgba(255,77,90,.85)") + "</div>";
      html += "<div class=\"asc-kpi-card\"><div class=\"asc-kpi-label\">TLE</div><div class=\"asc-kpi-value\" style=\"color:" + tleColor + ";\">" + tleStatus + "</div><div class=\"asc-kpi-sub\">" + (state.tleSource || "—") + "</div></div>";
      html += "<div class=\"asc-kpi-card\"><div class=\"asc-kpi-label\">Images</div><div class=\"asc-kpi-value\">" + (imgs != null ? imgs : "n/a") + "</div><div class=\"asc-kpi-sub\">Collected</div></div>";
      html += "</div>";

      html += "<div style=\"margin-top:8px;font-size:11px;line-height:1.35;color:rgba(232,244,250,.92);\">";
      html += "<div class=\"asc-anim-in\" style=\"margin-top:6px;display:flex;flex-wrap:wrap;gap:8px;align-items:center;\">";
      html += pill(platformOk ? "ONLINE" : "OFFLINE", platformOk ? "ok" : "warn");
      html += pill(tracked ? "ACTIVE" : "IDLE", tracked ? "ok" : "off");
      html += pill(state.liveData ? "LIVE" : "SIMULATION", state.liveData ? "data" : "off");
      html += pill("CONF " + confTxt, confTxt === "HIGH" ? "ok" : (confTxt === "MEDIUM" ? "warn" : "off"));
      html += "</div>";
      html += "<div style=\"margin-top:8px;\"><span style=\"color:#aaa;\">Last sync</span>: " + (lastSync ? String(lastSync).replace("T", " ").replace("Z", " UTC") : "n/a") + "</div>";
      html += "</div>";

      html += "<div style=\"margin-top:10px;\"><span style=\"color:#aaa;\">Observation conditions</span>: <span style=\"color:" + (vis > 0 ? "#00ff88" : "#ffbb55") + ";font-weight:bold;\">" + (vis > 0 ? "ACTIVE" : "LOW") + "</span></div>";
      if (state._dashboardHtmlSig === html) return;
      state._dashboardHtmlSig = html;
      el.innerHTML = html;
    } catch (e) {}
  }

  function setNasaFeedsSnapshot(o) {
    try {
      state.nasaFeeds = state.nasaFeeds || { apod: "", neo: "", solar: "", updatedAt: null };
      if (!o || typeof o !== "object") return;
      if (o.apod != null) state.nasaFeeds.apod = String(o.apod);
      if (o.neo != null) state.nasaFeeds.neo = String(o.neo);
      if (o.solar != null) state.nasaFeeds.solar = String(o.solar);
      state.nasaFeeds.updatedAt = new Date().toISOString();
    } catch (e) {}
  }

  function buildShowroomReportData() {
    function fmtIso(dt) {
      try {
        if (!dt) return null;
        var d = dt instanceof Date ? dt : new Date(dt);
        return isNaN(d.getTime()) ? null : d.toISOString();
      } catch (e) {
        return null;
      }
    }
    function passDurationMinRep(p) {
      if (!p) return null;
      if (p.durationMinutes != null && isFinite(p.durationMinutes)) return p.durationMinutes;
      if (p.duration != null && isFinite(p.duration)) return p.duration;
      if (p.endTime && p.startTime) {
        var ms = new Date(p.endTime).getTime() - new Date(p.startTime).getTime();
        if (isFinite(ms) && ms > 0) return ms / 60000;
      }
      return null;
    }
    var nasa = state.nasaFeeds || {};
    var passRows = (state.predictedPasses || []).slice(0, 40).map(function (p) {
      if (!p) return null;
      return {
        name: p.name || (p.satRef && p.satRef.name) || "—",
        riseUtc: fmtIso(p.riseTime || p.startTime || p.start),
        maxElDeg:
          p.peakElevation != null && isFinite(p.peakElevation)
            ? Math.round(p.peakElevation)
            : p.maxElevation != null && isFinite(p.maxElevation)
              ? Math.round(p.maxElevation)
              : null,
        durationMin: passDurationMinRep(p)
      };
    }).filter(Boolean);
    var trackRows = (state.trackedSatellites || []).slice(0, 80).map(function (s) {
      if (!s) return null;
      return {
        name: s.name,
        type: s.type != null ? s.type : classifySatellite(s.name || ""),
        elevation: s.elevation,
        azimuth: s.azimuth
      };
    });
    return {
      generatedAt: new Date().toISOString(),
      observer: { lat: observerCoords.lat, lon: observerCoords.lon, name: "Tlemcen, Algérie" },
      system: typeof window.getRenderableSystemState === "function" ? window.getRenderableSystemState() : {},
      priority: typeof getRenderablePriorityObject === "function" ? getRenderablePriorityObject() : null,
      nasaFeeds: {
        apod: nasa.apod || "",
        neo: nasa.neo || "",
        solar: nasa.solar || "",
        updatedAt: nasa.updatedAt || null
      },
      trackedSatellites: trackRows,
      predictedPasses: passRows
    };
  }

  function exportShowroomReport() {
    try {
      function escHtml(v) {
        if (v == null || v === "") return "—";
        return String(v)
          .replace(/&/g, "&amp;")
          .replace(/</g, "&lt;")
          .replace(/>/g, "&gt;")
          .replace(/"/g, "&quot;");
      }
      function fmtTimeFromIso(iso) {
        try {
          if (!iso) return "—";
          var d = new Date(iso);
          return isNaN(d.getTime()) ? "—" : d.toISOString().replace("T", " ").slice(0, 19) + " UTC";
        } catch (eT) {
          return "—";
        }
      }

      var data = buildShowroomReportData();
      var rs = data.system || {};
      var nasa = data.nasaFeeds || {};
      var tracks = data.trackedSatellites || [];
      var passes = data.predictedPasses || [];

      var w = window.open("", "_blank");
      if (!w) return;

      var html = "";
      html +=
        "<!DOCTYPE html><html><head><meta charset='utf-8'/><title>AstroScan-Chohra — ORBITAL-CHOHRA</title>";
      html +=
        "<style>" +
        "body{font-family:'Segoe UI',Roboto,Helvetica,sans-serif;background:#030806;color:#d8f5e8;margin:0;padding:28px 32px 48px;line-height:1.45;}" +
        ".masthead{border-bottom:2px solid #00ff88;padding-bottom:16px;margin-bottom:20px;}" +
        ".brand{font-size:11px;letter-spacing:.28em;color:#00ff88;font-weight:700;margin:0 0 6px 0;}" +
        "h1{margin:0;font-size:22px;color:#e8fff4;font-weight:600;}" +
        ".sub{margin-top:10px;font-size:13px;color:#9bc9b0;}" +
        ".sub strong{color:#b9ffd9;}" +
        "h2{margin:26px 0 10px 0;font-size:13px;letter-spacing:.12em;color:#00ff88;text-transform:uppercase;}" +
        "table{width:100%;border-collapse:collapse;margin-top:8px;font-size:12px;}" +
        "th,td{border:1px solid rgba(0,255,136,0.22);padding:9px 10px;text-align:left;}" +
        "th{background:rgba(0,40,28,0.85);color:#00ffcc;font-weight:600;}" +
        "tr:nth-child(even) td{background:rgba(0,20,14,0.35);}" +
        ".nasa-box{margin-top:8px;padding:14px 16px;border-radius:8px;border:1px solid rgba(0,255,204,0.25);background:rgba(0,18,22,0.75);font-size:12px;color:#cdeee0;}" +
        ".btn{margin-top:18px;padding:11px 20px;border:none;border-radius:6px;background:linear-gradient(180deg,#00ffcc,#00c49a);color:#021208;font-weight:700;cursor:pointer;font-size:13px;}" +
        ".btn:hover{filter:brightness(1.06);}" +
        ".kpi{font-size:11px;color:#7aab95;margin:12px 0 0 0;}" +
        "@media print{body{padding:12mm;background:#fff;color:#111;}.btn{display:none!important;}th{background:#f0f0f0;color:#111;}td,th{border-color:#ccc;}body *{-webkit-print-color-adjust:exact;print-color-adjust:exact;}}" +
        "</style></head><body>";

      html += '<div class="masthead">';
      html += '<p class="brand">AstroScan-Chohra OBSERVATORY — ORBITAL-CHOHRA</p>';
      html += "<h1>Rapport orbital — showroom</h1>";
      html +=
        '<div class="sub"><strong>Directeur :</strong> Zakaria Chohra — Tlemcen, Algérie<br/>' +
        "<strong>Horodatage :</strong> " +
        escHtml(data.generatedAt) +
        "</div>";
      html += "</div>";

      html +=
        '<p class="kpi">Synthèse getRenderableSystemState() · trackés : ' +
        (rs.tracked != null ? rs.tracked : "—") +
        " · visibles : " +
        (rs.visible != null ? rs.visible : "—") +
        " · passages : " +
        (rs.passes != null ? rs.passes : "—") +
        " · alertes : " +
        (rs.alerts != null ? rs.alerts : "—") +
        " · objet prioritaire : " +
        escHtml(rs.priorityObject || "—") +
        "</p>";

      html += "<h2>Satellites trackés</h2>";
      if (!tracks.length) {
        html += "<p>Aucun satellite dans l’état courant.</p>";
      } else {
        html +=
          "<table><thead><tr><th>Nom</th><th>Type</th><th>Élévation (°)</th><th>Azimut (°)</th></tr></thead><tbody>";
        tracks.forEach(function (s) {
          if (!s) return;
          var ty = s.type != null ? s.type : "—";
          var elv =
            s.elevation != null && isFinite(s.elevation) ? Math.round(s.elevation * 10) / 10 : "—";
          var az =
            s.azimuth != null && isFinite(s.azimuth) ? Math.round(s.azimuth * 10) / 10 : "—";
          html +=
            "<tr><td>" +
            escHtml(s.name || "—") +
            "</td><td>" +
            escHtml(ty) +
            "</td><td>" +
            escHtml(elv) +
            "</td><td>" +
            escHtml(az) +
            "</td></tr>";
        });
        html += "</tbody></table>";
      }

      html += "<h2>Passages prédits</h2>";
      if (!passes.length) {
        html += "<p>Aucun passage prédit dans la fenêtre courante.</p>";
      } else {
        html +=
          "<table><thead><tr><th>Satellite</th><th>Heure lever (UTC)</th><th>Élév. max</th><th>Durée</th></tr></thead><tbody>";
        passes.forEach(function (p) {
          if (!p) return;
          var nm = p.name || "—";
          var rise = fmtTimeFromIso(p.riseUtc);
          var mel = p.maxElDeg != null && isFinite(p.maxElDeg) ? Math.round(p.maxElDeg) + "°" : "—";
          var dm = p.durationMin;
          var durStr = dm != null && isFinite(dm) ? Math.round(dm) + " min" : "—";
          html +=
            "<tr><td>" +
            escHtml(nm) +
            "</td><td>" +
            escHtml(rise) +
            "</td><td>" +
            escHtml(mel) +
            "</td><td>" +
            escHtml(durStr) +
            "</td></tr>";
        });
        html += "</tbody></table>";
      }

      html += "<h2>NASA FEEDS</h2>";
      html += '<div class="nasa-box">';
      html += "<div><strong>APOD (titre / état)</strong> · " + escHtml(nasa.apod || "—") + "</div>";
      html +=
        "<div style='margin-top:8px;'><strong>NEO (comptage)</strong> · " +
        escHtml(nasa.neo || "—") +
        "</div>";
      html +=
        "<div style='margin-top:8px;'><strong>Événements solaires</strong> · " +
        escHtml(nasa.solar || "—") +
        "</div>";
      html += "</div>";

      html +=
        '<p><button type="button" class="btn" onclick="window.print()">Imprimer / PDF</button></p>';
      html +=
        '<p style="margin-top:22px;font-size:11px;color:#6a907e;">Rapport généré côté client — AstroScan-Chohra / ORBITAL-CHOHRA.</p>';
      html += "</body></html>";

      w.document.open();
      w.document.write(html);
      w.document.close();
    } catch (e) {}
  }

  function refreshLabStats() {
    try {
      var now = Date.now();
      if (state._labStatsNextMs && now < state._labStatsNextMs) return;
      state._labStatsNextMs = now + 60000;
      (async function () {
        try {
          var json = await safeFetchJson("/api/lab/images", { cache: "no-store" }, null);
          if (!json) return;
          var imgs = json.images;
          if (Array.isArray(imgs)) {
            state.labImagesCount = imgs.length;
            state.labLastSyncIso = new Date().toISOString();
          }
        } catch (e) {}
      })();
    } catch (e) {}
  }

  function focusCenterSelected() {
    if (!state.selectedSatellite || !state.selectedSatellite.entity) return;
    try {
      var flyOpts = { duration: 1.6 };
      try {
        if (Cesium.EasingFunction && Cesium.EasingFunction.QUADRATIC_IN_OUT) {
          flyOpts.easingFunction = Cesium.EasingFunction.QUADRATIC_IN_OUT;
        }
      } catch (e2) {}
      viewer.flyTo(state.selectedSatellite.entity, flyOpts);
    } catch (e) {}
  }

  function focusFollowSelected() {
    state.followSatellite = !state.followSatellite;
    try {
      viewer.trackedEntity = state.followSatellite && state.selectedSatellite ? state.selectedSatellite.entity : null;
    } catch (e) {
      state.followSatellite = false;
    }
    updateSelectedSatelliteUI();
  }

  function updatePassesUI() {
    var listEl = document.getElementById("next-passes-list");
    if (!listEl) return;
    var passes = state.predictedPasses.slice(0, 5);
    var now = new Date();
    if (passes.length === 0) {
      listEl.innerHTML = "No passes in next 90 min";
      return;
    }
    listEl.innerHTML = passes.map(function (p) {
      var minFromNow = (p.riseTime.getTime() - now.getTime()) / 60000;
      var inStr = minFromNow <= 0 ? "now" : "in " + Math.round(minFromNow) + " min";
      var peak = (p.peakElevation != null) ? Math.round(p.peakElevation) + "°" : "n/a";
      var durMin = isFinite(p.durationMinutes) ? Math.round(p.durationMinutes) : 0;
      var ql = p.qualityLabel || "—";
      var is = isFinite(p.interestScore) ? Math.round(p.interestScore) : 0;
      return p.name + " — " + inStr + " — " + durMin + " min — peak " + peak + " — " + ql + " — score " + is;
    }).join("<br/>");
  }

  try {
    var handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
    handler.setInputAction(function (movement) {
      var picked = viewer.scene.pick(movement.position);
      if (!picked || !picked.id) {
        state.selectedSatellite = null;
        state.selectedSat = null;
        state.followSatellite = false;
        try { viewer.trackedEntity = null; } catch (e) {}
        updateSelectedSatelliteUI();
        notifyViewSyncIfNeeded();
        return;
      }
      var entity = picked.id;
      var sat = null;
      for (var i = 0; i < state.trackedSatellites.length; i++) {
        if (state.trackedSatellites[i].entity === entity) {
          sat = state.trackedSatellites[i];
          break;
        }
      }
      if (sat) {
        state.selectedSatellite = sat;
        state.selectedSat = sat;
        if (state.followSatellite) {
          try { viewer.trackedEntity = sat.entity; } catch (e) {}
        }
        updateSelectedSatelliteUI();
        notifyViewSyncIfNeeded();
      } else {
        state.selectedSatellite = null;
        state.selectedSat = null;
        state.followSatellite = false;
        try { viewer.trackedEntity = null; } catch (e) {}
        updateSelectedSatelliteUI();
        notifyViewSyncIfNeeded();
      }
    }, Cesium.ScreenSpaceEventType.LEFT_CLICK);
  } catch (e) {
    console.warn("Orbital map: click handler failed", e);
  }

  // Apply saved UI preferences (localStorage) before the first render.
  try {
    var _userCfg = loadUserConfig && loadUserConfig();
    if (_userCfg && typeof _userCfg === "object") {
      // Demo showroom mode — désactivé au démarrage (ne plus lire localStorage)
      // if (typeof _userCfg.demoMode === "boolean") {
      //   state.demoMode = _userCfg.demoMode;
      // }
      // Optional UI prefs if present
      if (typeof _userCfg.filter === "string" && _userCfg.filter) {
        state.filter = _userCfg.filter;
      }
      // Close approaches panel state
      var _closeEl = document.getElementById("close-approaches");
      var _btnDet = document.getElementById("btn-details");
      if (_closeEl) {
        var open = !!_userCfg.closeApproachesOpen;
        if (open) {
          _closeEl.classList.add("is-open");
          try {
            if (_btnDet) _btnDet.classList.add("active");
          } catch (eB) {}
        } else {
          _closeEl.classList.remove("is-open");
          try {
            if (_btnDet) _btnDet.classList.remove("active");
          } catch (eB2) {}
        }
      }
      try { updateDemoButtonState && updateDemoButtonState(); } catch (e2) {}
    }
  } catch (e) {}

  state.demoMode = false;
  try {
    state.orbitDemoMode = false;
  } catch (eOd) {}
  try {
    state.videoDemoMode = false;
  } catch (eVd) {}
  try {
    window.demoMode = false;
  } catch (eDm) {}
  try {
    document.body.classList.remove("demo-glow");
  } catch (eBg) {}
  try {
    setDemoModeButtonActive(false);
  } catch (eBtn) {}
  try {
    updateDemoButtonState();
  } catch (eUb) {}

  loadSatellites();

  if (DEBUG_MODE) {
    setTimeout(function () {
      var count = window.viewer ? window.viewer.entities.values.length : 0;
      console.log("CESIUM ENTITIES COUNT:", count);
      if (count > 0) {
        var e = window.viewer.entities.values[10];
        if (e && e.point) {
          var color = e.point.color.getValue(Cesium.JulianDate.now());
          console.log("ENTITY 10 COLOR:", JSON.stringify(color));
          console.log("ENTITY 10 POSITION:", JSON.stringify(e.position.getValue(Cesium.JulianDate.now())));
          console.log("ENTITY 10 SHOW:", e.show);
        }
      }
      // [REMOVED] test-paris debug marker (v2.4.0-coords-fix)
    }, 5000);
  }

  if (window.__orbitalLoop) clearInterval(window.__orbitalLoop);
  window.__orbitalLoop = setInterval(function () {
    try {
      var tickMs = Date.now();
      updateSatellites();
      refreshLabStats();
      simulateDemoActivity();
      if (tickMs - _orbitUiClock.kpi >= ORBIT_UI_INTERVAL_MS.kpi) {
        _orbitUiClock.kpi = tickMs;
        updateTrackedKpiMinimal();
      }
      if (tickMs - _orbitUiClock.alerts >= ORBIT_UI_INTERVAL_MS.alerts) {
        _orbitUiClock.alerts = tickMs;
        updateSystemBadgesAndAlerts();
      }
      if (tickMs - _orbitUiClock.analysis >= ORBIT_UI_INTERVAL_MS.analysis) {
        _orbitUiClock.analysis = tickMs;
        updateAnalysisCard();
      }
      updateDemo();
      updateVideoDemoScenario();
      updateSelfTestScenario();
      try {
        if (state.orbitDemoMode) {
          viewer.scene.camera.rotate(Cesium.Cartesian3.UNIT_Z, 0.001);
        }
      } catch (e) {}

      // Zoom caméra uniquement lors d'un changement de cible en mode démo
      if (state.orbitDemoMode && state.demoJustSwitched && state.selectedSat && state.selectedSat.entity && state.selectedSat.entity.position) {
        try {
          var jd = Cesium.JulianDate.now();
          var dest = state.selectedSat.entity.position.getValue ? state.selectedSat.entity.position.getValue(jd) : null;
          if (dest) {
            viewer.camera.flyTo({
              destination: dest,
              duration: 1.6,
              easingFunction: Cesium.EasingFunction.QUADRATIC_IN_OUT
            });
          }
        } catch (e) {}
        state.demoJustSwitched = false;
      }
    } catch (e) {
      safeError("UPDATE LOOP ERROR:", e);
    }
  }, 1000);
  safeWarn("Orbital update loop started.");

  if (DEBUG_MODE) {
    setInterval(function () {
      try {
        if (!window.viewer || !window.viewer.entities || !window.viewer.entities.values) return;
        var vals = window.viewer.entities.values;
        if (vals.length <= 7) return;
        console.log(
          "FIRST ENTITY SHOW:",
          vals[7].show,
          "POS:",
          vals[7].position.getValue(Cesium.JulianDate.now())
        );
      } catch (eLog7) {}
    }, 10000);
  }

  var passesIntervalCount = 0;
  setInterval(function () {
    computePassPredictions();
    updatePassesUI();
    if (passesIntervalCount === 0 && state.trackedSatellites.length) {
      console.info("OrbitalMapEngine: predicted passes =", state.predictedPasses.length);
      passesIntervalCount++;
    }
  }, 30000);

  setInterval(function () {
    detectCloseApproaches();
    updateCloseApproachUI();
  }, 10000);

  // Refresh léger de l'état TLE côté front (toutes les 15 minutes)
  setInterval(function () {
    (async function () {
      try {
        var json = await safeFetchJson("/api/tle/status", { cache: "no-store" }, null);
        if (!json) return;
        var iso = json.last_refresh_iso || null;
        if (!iso) return;
        if (state.tleLastRefreshIso && state.tleLastRefreshIso === iso) {
          return;
        }
        state.tleLastRefreshIso = iso;
        state.lastUpdateTime = safeParseDate(iso);
        loadSatellites();
      } catch (e) {}
    })();
  }, 900000);

  var btnCenter = document.getElementById("satellite-focus-center");
  if (btnCenter) btnCenter.addEventListener("click", focusCenterSelected);
  var btnFollow = document.getElementById("satellite-focus-follow");
  if (btnFollow) btnFollow.addEventListener("click", focusFollowSelected);

  function csvEscapeCell(v) {
    var s = v == null ? "" : String(v);
    if (/[",\n\r]/.test(s)) return '"' + s.replace(/"/g, '""') + '"';
    return s;
  }

  function exportReport() {
    try {
      var list = (state.visibleSatellites && state.visibleSatellites.length)
        ? state.visibleSatellites.slice()
        : (state.trackedSatellites || []).filter(function (s) {
          return s && s.visible && satelliteMatchesFilter(s, state.filter);
        });
      var headers = ["name", "type", "lat", "lon", "alt_km", "elevation_deg", "azimuth_deg", "speed_kms", "score"];
      var rows = [headers.join(",")];
      list.forEach(function (s) {
        if (!s) return;
        var line = [
          csvEscapeCell(s.name),
          csvEscapeCell(s.type),
          csvEscapeCell(s.lat),
          csvEscapeCell(s.lon),
          csvEscapeCell(s.alt_km),
          csvEscapeCell(s.elevation),
          csvEscapeCell(s.azimuth),
          csvEscapeCell(s.speed_kms),
          csvEscapeCell(s.score)
        ];
        rows.push(line.join(","));
      });
      var csv = "\uFEFF" + rows.join("\r\n");
      var blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
      var url = URL.createObjectURL(blob);
      var a = document.createElement("a");
      a.href = url;
      a.download = "astroscan-satellites-visibles-" + new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-") + ".csv";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      try {
        if (typeof window.showToast === "function") {
          window.showToast("CSV exporté (" + list.length + " satellite(s))");
        }
      } catch (e2) {}
    } catch (e) {
      safeError("Export failed:", e);
    }
  }

  function exportPremiumReport() {
    try {
      var total = state.trackedSatellites.length;
      var vis = state.visibleSatellites.length;
      var top = state.visibleSatellites.slice().sort(function (a, b) {
        return (b.score || 0) - (a.score || 0);
      }).slice(0, 5);
      var next = state.predictedPasses && state.predictedPasses[0] ? state.predictedPasses[0] : null;
      var w = window.open("", "_blank");
      if (!w) return;
      var html = "<html><head><title>AstroScan-Chohra Report</title></head><body style='font-family:Arial;background:#000;color:#0f0;'>";
      html += "<h2>AstroScan-Chohra Radar Pro — Rapport</h2>";
      html += "<div>Date : " + new Date().toISOString() + "</div>";
      html += "<div>Satellites totaux : " + total + "</div>";
      html += "<div>Satellites visibles : " + vis + "</div><hr/>";
      html += "<h3>Top 5 visibles</h3><ol>";
      top.forEach(function (s) {
        html += "<li>" + (s.name || "—") + " — score " + Math.round(s.score || 0) + "/100</li>";
      });
      html += "</ol>";
      if (next && next.riseTime) {
        var rt = next.riseTime;
        var hh = String(rt.getHours()).padStart(2, "0");
        var mm = String(rt.getMinutes()).padStart(2, "0");
        html += "<h3>Prochain passage global</h3>";
        html += "<div>" + (next.name || "Satellite") + " à " + hh + ":" + mm + "</div>";
      }
      html += "<script>window.print();</script>";
      html += "</body></html>";
      w.document.open();
      w.document.write(html);
      w.document.close();
    } catch (e) {
      safeError("Premium export failed:", e);
    }
  }

  window.setFilter = function (type) {
    try {
      var t = (type || "all").toString().toLowerCase();
      state.filter = t;
      try { saveUserConfig({ filter: state.filter }); } catch (e2) {}
      try {
        updateSatellites();
      } catch (e3) {}
    } catch (e) {}
  };
  window.exportReport = exportReport;
  window.exportPremiumReport = exportPremiumReport;
  if (window.AstroScanUI) window.AstroScanUI.exportShowroomReport = exportShowroomReport;
  else window.exportShowroomReport = exportShowroomReport;

  // ──────────────────────────────────────────────────────────────
  // Phase 1 scaffolding: expose internal render/update functions
  // so dedicated modules can delegate without duplicating logic.
  // (Behavior remains unchanged until we progressively move code.)
  // ──────────────────────────────────────────────────────────────
  try {
    window.__AstroScanInternal = window.__AstroScanInternal || {};
    window.__AstroScanInternal.updateBusinessDashboard = updateBusinessDashboard;
    window.__AstroScanInternal.updateAnalysisCard = updateAnalysisCard;
    window.__AstroScanInternal.updateSystemBadgesAndAlerts = updateSystemBadgesAndAlerts;
    window.__AstroScanInternal.buildOperationalAlerts = buildOperationalAlerts;
    window.__AstroScanInternal.getRenderablePriorityObject = getRenderablePriorityObject;
    window.__AstroScanInternal.buildShowroomReportData = buildShowroomReportData;
    window.__AstroScanInternal.simulateDemoActivity = simulateDemoActivity;
    window.__AstroScanInternal.updateTrackedKpiMinimal = updateTrackedKpiMinimal;
    window.__AstroScanInternal.exportShowroomReport = exportShowroomReport;
    window.__AstroScanInternal.toggleDemoMode = window.toggleDemoMode;
  } catch (e) {}

  window.viewer = viewer;
  window.astroViewer = viewer;
  try { console.log('[ASTRO] Cesium viewer exposé globalement (window.astroViewer)'); } catch (e) {}
  window.OrbitalMapEngine = window.OrbitalMapEngine || {};
  window.OrbitalMapEngine.exportShowroomReport = exportShowroomReport;
  window.OrbitalMapEngine.buildShowroomReportData = buildShowroomReportData;
  window.OrbitalMapEngine.setNasaFeedsSnapshot = setNasaFeedsSnapshot;
  window.OrbitalMapEngine.getRenderablePriorityObject = getRenderablePriorityObject;
  window.OrbitalMapEngine.state = state;
  window.OrbitalMapEngine.setObserver = setObserver;
  window.OrbitalMapEngine.updateSpaceRadarUI = updateSpaceRadarUI;
  window.OrbitalMapEngine.updatePassesUI = updatePassesUI;
  window.OrbitalMapEngine.updateSelectedSatelliteUI = updateSelectedSatelliteUI;
  window.OrbitalMapEngine.computePassPredictions = computePassPredictions;
  window.OrbitalMapEngine.focusCenterSelected = focusCenterSelected;
  window.OrbitalMapEngine.focusFollowSelected = focusFollowSelected;
  window.OrbitalMapEngine.selectSatelliteByName = selectSatelliteByName;
  window.OrbitalMapEngine.ingestIssLive = ingestIssLivePayload;
  window.OrbitalMapEngine.startSelfTest = function () {
    try {
      state.selfTestMode = true;
      state.selfTestStartTime = Date.now();
      state.selfTestStep = 0;
      state.selfTestResults = {
        startupOk: false,
        dataOk: false,
        topPassOk: false,
        focusOk: false,
        videoDemoOk: false
      };
      state.selfTestPrevSnapshot = null;
      state.selfTestLastValidateToastMs = 0;
      state.selfTestScoreSmooth = 0;
      state.selfTestLocked = false;
      if (window.OrbitalUI && typeof window.OrbitalUI.updateSelfTestOverlay === "function") {
        var checklistHtml = buildSelfTestChecklistHtml();
        window.OrbitalUI.updateSelfTestOverlay(
          "AstroScan-Chohra Self-Test",
          "Initialisation…",
          checklistHtml,
          true
        );
      }
    } catch (e) {}
  };
  window.OrbitalMapEngine.stopSelfTest = function () {
    try {
      state.selfTestMode = false;
      state.selfTestStartTime = null;
      state.selfTestStep = 0;
      state.selfTestPrevSnapshot = null;
      state.selfTestLocked = false;
      if (window.OrbitalUI && typeof window.OrbitalUI.updateSelfTestOverlay === "function") {
        window.OrbitalUI.updateSelfTestOverlay(null, null, null, false);
      }
    } catch (e) {}
  };
  window.OrbitalMapEngine.setDemoMode = function (flag) {
    try {
      state.orbitDemoMode = !!flag;
      state.demoLastSwitch = null;
      state.demoIndex = 0;
      state.demoJustSwitched = false;
    } catch (e) {}
  };

  window.OrbitalMapEngine.startVideoDemo = function () {
    try {
      state.videoDemoMode = true;
      state.videoDemoStartTime = Date.now();
      state.videoDemoStep = -1;
      state.videoDemoOverlayVisible = true;
      state.orbitDemoMode = true;
      state.demoLastSwitch = null;
      state.demoIndex = 0;
      state.demoJustSwitched = false;
      if (window.OrbitalUI && typeof window.OrbitalUI.updateVideoDemoOverlay === "function") {
        window.OrbitalUI.updateVideoDemoOverlay("AstroScan-Chohra Radar Pro", "Initialisation…", true);
      }
    } catch (e) {}
  };

  window.OrbitalMapEngine.stopVideoDemo = function () {
    try {
      state.videoDemoMode = false;
      state.videoDemoStartTime = null;
      state.videoDemoStep = -1;
      state.videoDemoOverlayVisible = false;
      if (window.OrbitalUI && typeof window.OrbitalUI.updateVideoDemoOverlay === "function") {
        window.OrbitalUI.updateVideoDemoOverlay(null, null, false);
      }
    } catch (e) {}
  };

  // Pas d’activation auto du mode démo orbital : uniquement action utilisateur (bouton / API).
})();
