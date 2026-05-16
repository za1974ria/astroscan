/* ============================================================================
 * ASTROSCAN COMMAND V2 — Mission Control client
 * Modular vanilla JS: boot sequence, Cesium globe, WebSocket telemetry,
 * Web Audio command engine, animated panels, AI rotating command feed.
 * ========================================================================== */

(() => {
  "use strict";

  /* ============================== CONFIG =================================== */

  // Replace with your own Cesium Ion token if you have one. Public assets
  // will still load using the default token bundled with CesiumJS.
  const CESIUM_ION_TOKEN = "";

  // WS_PATH dynamique : respecte le préfixe URL (ex: /command/ws si servi sous /command/)
const WS_PATH = (() => {
  const path = window.location.pathname.replace(/\/+$/, "");
  // Si on est sous /command (ou autre préfixe), on l'utilise
  // Sinon path == "" et WS_PATH == "/ws"
  return path + "/ws";
})();
  // API_BASE dynamique : préfixe pour tous les fetch() vers le backend
  // Si servi sous /command/, génère "/command". Sinon "" (racine).
  const API_BASE = window.location.pathname.replace(/\/+$/, "");
  const RECONNECT_BACKOFF_MS = [1500, 3000, 5000, 8000, 12000];
  // Live data overrides — populated by background fetchers (AirTrafficLive, etc.)
  // When non-null, the WS frame interceptor overrides synthetic metric values
  // with these live values from real public sources (OpenSky, USGS, NOAA...).
  const LIVE_OVERRIDES = {
    air_traffic_density: null,
    air_traffic_meta: null,
    seismic_activity: null,
    seismic_meta: null,
    advisor_message: null,
    advisor_severity: null,
    advisor_category: null,
    advisor_log: null,
    advisor_meta: null,
    // Space weather LIVE values (mirrored from SpaceWeather module for threat calc)
    space_kp: null,           // NOAA Kp index [0..9]
    space_xray_wm2: null,     // NOAA X-Ray flux W/m²
    space_f107: null,         // NOAA F10.7 solar flux
    // TLE freshness (computed from AMSAT TLE epoch)
    tle_age_hours: null,      // hours since TLE epoch
  };

  // ─── Compute real-source threat_index from LIVE_OVERRIDES ───
  // Returns null if no live source is available (caller will use synthetic).
  // Formula: weighted blend of 5 normalized signals (each 0..100):
  //   0.35 × Kp index        (geomagnetic storm — primary spacecraft hazard)
  //   0.20 × X-ray flux      (solar flare — radio blackout risk)
  //   0.25 × seismic score   (earth-side situational awareness)
  //   0.10 × air traffic     (operational saturation)
  //   0.10 × TLE freshness   (data confidence inverted)
  function computeLiveThreatIndex() {
    const parts = [];
    let weightSum = 0;
    let weightedSum = 0;
    // Kp [0..9] → [0..100]
    if (LIVE_OVERRIDES.space_kp !== null) {
      const v = Math.min(100, (LIVE_OVERRIDES.space_kp / 9.0) * 100);
      weightedSum += 0.35 * v; weightSum += 0.35;
      parts.push("Kp=" + LIVE_OVERRIDES.space_kp.toFixed(1) + "→" + v.toFixed(0));
    }
    // X-Ray [1e-8 .. 1e-3] log-scaled → [0..100]
    if (LIVE_OVERRIDES.space_xray_wm2 !== null && LIVE_OVERRIDES.space_xray_wm2 > 0) {
      const log = Math.log10(LIVE_OVERRIDES.space_xray_wm2);
      // -8 (A-class quiet) → 0, -3 (X-class severe) → 100
      const v = Math.min(100, Math.max(0, ((log + 8) / 5) * 100));
      weightedSum += 0.20 * v; weightSum += 0.20;
      parts.push("Xray=" + LIVE_OVERRIDES.space_xray_wm2.toExponential(1) + "→" + v.toFixed(0));
    }
    // Seismic [0..100] (already normalized by backend)
    if (LIVE_OVERRIDES.seismic_activity !== null) {
      weightedSum += 0.25 * LIVE_OVERRIDES.seismic_activity; weightSum += 0.25;
      parts.push("Seis=" + LIVE_OVERRIDES.seismic_activity.toFixed(1));
    }
    // Air traffic [0..100] (already normalized)
    if (LIVE_OVERRIDES.air_traffic_density !== null) {
      weightedSum += 0.10 * LIVE_OVERRIDES.air_traffic_density; weightSum += 0.10;
      parts.push("Air=" + LIVE_OVERRIDES.air_traffic_density.toFixed(1));
    }
    // TLE age in hours [0..48] inverted: fresh = high confidence = low threat
    if (LIVE_OVERRIDES.tle_age_hours !== null) {
      const age = Math.min(48, LIVE_OVERRIDES.tle_age_hours);
      const v = (age / 48) * 100;  // older TLE → higher threat
      weightedSum += 0.10 * v; weightSum += 0.10;
      parts.push("TLE_age=" + LIVE_OVERRIDES.tle_age_hours.toFixed(1) + "h→" + v.toFixed(0));
    }
    if (weightSum === 0) return null;
    // Normalize to full 100 if some weights missing
    const idx = Math.min(100, Math.max(0, weightedSum / weightSum * weightSum * (1.0 / weightSum)));
    // Simpler & numerically stable: just renormalize
    const score = Math.min(100, Math.max(0, (weightedSum / weightSum)));
    return { score: score, breakdown: parts.join(" | "), weight_coverage: weightSum };
  }

  /* ============================== UTILITIES ================================ */

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  const clamp = (n, lo, hi) => Math.max(lo, Math.min(hi, n));

  const fmtNum = (n, digits = 2) =>
    Number.isFinite(n) ? n.toFixed(digits) : "--";

  const fmtInt = (n) => (Number.isFinite(n) ? Math.round(n).toLocaleString("en-US") : "--");

  const fmtClock = (date, tz = "UTC") => {
    try {
      return new Intl.DateTimeFormat("en-GB", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: false,
        timeZone: tz === "UTC" ? "UTC" : undefined,
      }).format(date);
    } catch (e) {
      return date.toISOString().slice(11, 19);
    }
  };

  const easeInOutCubic = (t) =>
    t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;

  /* Animate a numeric DOM value from current to next, smoothly. */
  function animateNumber(el, from, to, opts = {}) {
    const { duration = 800, digits = 2, suffix = "" } = opts;
    const start = performance.now();
    const delta = to - from;
    function frame(now) {
      const t = clamp((now - start) / duration, 0, 1);
      const v = from + delta * easeInOutCubic(t);
      el.textContent = (Number.isFinite(v) ? v.toFixed(digits) : "--") + suffix;
      if (t < 1) requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
  }

  /* ============================== BOOT SEQUENCE ============================ */

  const BOOT_SEQUENCE = [
    { label: "ASTROSCAN COMMAND",              duration: 600,  weight: 4 },
    { label: "INITIALIZING GLOBAL SYSTEMS...", duration: 700,  weight: 8 },
    { label: "CONNECTING ORBITAL TELEMETRY...",duration: 850,  weight: 12 },
    { label: "CONNECTING AIRSPACE NETWORK...", duration: 700,  weight: 12 },
    { label: "CONNECTING MARITIME GRID...",    duration: 700,  weight: 12 },
    { label: "SOLAR WEATHER ENGINE ONLINE...", duration: 700,  weight: 14 },
    { label: "EARTH HAZARD ENGINE ONLINE...",  duration: 700,  weight: 14 },
    { label: "AI COMMAND SYSTEM READY",        duration: 700,  weight: 12 },
    { label: "MISSION CONTROL ONLINE",         duration: 600,  weight: 12 },
  ];

  function runBootSequence() {
    return new Promise((resolve) => {
      const logEl = $("#boot-log");
      const fillEl = $("#boot-progress-fill");
      const pctEl = $("#boot-progress-pct");
      const labelEl = $("#boot-progress-label");

      const totalWeight = BOOT_SEQUENCE.reduce((a, b) => a + b.weight, 0);
      let acc = 0;
      let i = 0;

      const advance = () => {
        if (i >= BOOT_SEQUENCE.length) {
          fillEl.style.width = "100%";
          pctEl.textContent = "100%";
          labelEl.textContent = "READY";
          setTimeout(resolve, 480);
          return;
        }
        const step = BOOT_SEQUENCE[i++];
        const li = document.createElement("li");
        li.innerHTML = `<span class="glyph">▸</span><span>${step.label}</span>`;
        logEl.appendChild(li);
        requestAnimationFrame(() => li.classList.add("in"));

        // Keep only the last 7 visible for clean look
        while (logEl.children.length > 7) {
          logEl.removeChild(logEl.firstElementChild);
        }

        labelEl.textContent = step.label;
        acc += step.weight;
        const pct = clamp((acc / totalWeight) * 100, 0, 100);
        fillEl.style.width = pct.toFixed(1) + "%";
        pctEl.textContent = Math.round(pct) + "%";

        setTimeout(() => {
          li.classList.add("ok");
          setTimeout(advance, 120);
        }, step.duration);
      };

      setTimeout(advance, 350);
    });
  }

  async function exitBoot() {
    const overlay = $("#boot-overlay");
    const dashboard = $("#mission-control");
    overlay.classList.add("is-hidden");
    overlay.setAttribute("aria-hidden", "true");
    dashboard.setAttribute("aria-hidden", "false");
    document.body.classList.remove("boot-locked");
    requestAnimationFrame(() => dashboard.classList.add("is-live"));
  }

  /* ============================== CESIUM GLOBE ============================= */

  const EARTH_RADIUS_M = 6_371_000;

  function initCesium(sharedCtx) {
    if (typeof window.Cesium === "undefined") {
      console.warn("[ASTROSCAN] Cesium runtime not available.");
      return null;
    }

    if (CESIUM_ION_TOKEN && CESIUM_ION_TOKEN.length > 0) {
      Cesium.Ion.defaultAccessToken = CESIUM_ION_TOKEN;
    }

    const viewer = new Cesium.Viewer("cesium-container", {
      animation: false,
      timeline: false,
      baseLayerPicker: false,
      geocoder: false,
      homeButton: false,
      navigationHelpButton: false,
      sceneModePicker: false,
      fullscreenButton: false,
      infoBox: false,
      selectionIndicator: false,
      shouldAnimate: true,
      baseLayer: false,
      skyAtmosphere: new Cesium.SkyAtmosphere(),
      contextOptions: {
        webgl: { alpha: true, antialias: true, preserveDrawingBuffer: false },
      },
    });

    // GIBS WMTS "500m" TileMatrixSet is non-doubling (2x1, 3x2, 5x3, 10x5, 20x10, 40x20,
    // 80x40, 160x80). Cesium's default doubling pyramid would request tiles past the matrix
    // edge and trigger 400s in the browser network log. This scheme reports GIBS's real
    // matrix dims so only valid tiles are requested.
    const GIBS_500M_MATRIX = [[2,1],[3,2],[5,3],[10,5],[20,10],[40,20],[80,40],[160,80]];
    const gibs500mScheme = () => {
      const s = new Cesium.GeographicTilingScheme({
        numberOfLevelZeroTilesX: GIBS_500M_MATRIX[0][0],
        numberOfLevelZeroTilesY: GIBS_500M_MATRIX[0][1],
      });
      s.getNumberOfXTilesAtLevel = (l) => (GIBS_500M_MATRIX[l] || GIBS_500M_MATRIX[GIBS_500M_MATRIX.length-1])[0];
      s.getNumberOfYTilesAtLevel = (l) => (GIBS_500M_MATRIX[l] || GIBS_500M_MATRIX[GIBS_500M_MATRIX.length-1])[1];
      return s;
    };

    // -- Premium NASA imagery (GIBS BlueMarble NG). Falls back silently. --
    try {
      const blueMarble = new Cesium.UrlTemplateImageryProvider({
        url: "https://gibs.earthdata.nasa.gov/wmts/epsg4326/best/BlueMarble_NextGeneration/default/500m/{z}/{y}/{x}.jpeg",
        tilingScheme: gibs500mScheme(),
        tileWidth: 512,
        tileHeight: 512,
        minimumLevel: 0,
        maximumLevel: GIBS_500M_MATRIX.length - 1,
        credit: new Cesium.Credit("NASA GIBS BlueMarble NG"),
      });
      blueMarble.errorEvent.addEventListener(() => {});
      const layer = viewer.imageryLayers.addImageryProvider(blueMarble);
      layer.brightness = 1.00;
      layer.contrast   = 1.06;   // preserve continental midtones
      layer.saturation = 0.96;   // restrained, less poster-saturated
      layer.gamma      = 1.03;
      layer.hue        = -0.02;  // marginally cooler oceans for "deep navy" feel
      // Day-side only — fades on the dark hemisphere so Black Marble can show through.
      layer.nightAlpha = 0.0;
      layer.dayAlpha   = 1.0;
    } catch (e) {
      console.warn("[ASTROSCAN] BlueMarble imagery unavailable", e);
    }

    // -- Night-side city lights (NASA Black Marble / VIIRS 2012). Premium WOW. --
    try {
      const blackMarble = new Cesium.UrlTemplateImageryProvider({
        url: "https://gibs.earthdata.nasa.gov/wmts/epsg4326/best/VIIRS_CityLights_2012/default/500m/{z}/{y}/{x}.jpeg",
        tilingScheme: gibs500mScheme(),
        tileWidth: 512,
        tileHeight: 512,
        minimumLevel: 0,
        maximumLevel: GIBS_500M_MATRIX.length - 1,
        credit: new Cesium.Credit("NASA Black Marble · VIIRS 2012"),
      });
      blackMarble.errorEvent.addEventListener(() => {});
      const night = viewer.imageryLayers.addImageryProvider(blackMarble);
      night.dayAlpha   = 0.0;
      night.nightAlpha = 1.0;
      night.brightness = 1.40;   // subtle but visible
      night.contrast   = 1.20;
      night.saturation = 1.10;
      night.gamma      = 1.08;
    } catch (e) {
      console.warn("[ASTROSCAN] Black Marble overlay unavailable", e);
    }

    const scene = viewer.scene;
    scene.backgroundColor = Cesium.Color.fromCssColorString("#02060b");
    scene.globe.baseColor = Cesium.Color.fromCssColorString("#040f1a");
    scene.globe.enableLighting = true;
    scene.globe.showGroundAtmosphere = true;
    const _atmBase = 5.5; // restored thin elegant atmospheric limb
    scene.globe.atmosphereLightIntensity = _atmBase;
    if (scene.globe.lambertDiffuseMultiplier !== undefined) {
      scene.globe.lambertDiffuseMultiplier = 0.92; // natural specular response, less plastic shading
    }
    // Subtle atmospheric "breathing" — restrained amplitude.
    scene.postRender.addEventListener(() => {
      const t = performance.now() / 1000;
      scene.globe.atmosphereLightIntensity = _atmBase + Math.sin(t / 2.2) * 0.3;
    });
    scene.globe.dynamicAtmosphereLighting = true;
    scene.globe.dynamicAtmosphereLightingFromSun = true;
    if (scene.globe.atmosphereHueShift !== undefined) {
      scene.globe.atmosphereHueShift = -0.02;
      scene.globe.atmosphereSaturationShift = -0.12;     // less aggressive cyan saturation
      scene.globe.atmosphereBrightnessShift = 0.00;      // neutral, no over-bright limb
    }
    scene.skyAtmosphere.hueShift = -0.02;
    scene.skyAtmosphere.saturationShift = -0.32;          // desaturated outer sky
    scene.skyAtmosphere.brightnessShift = -0.04;
    if (scene.skyAtmosphere.atmosphereLightIntensity !== undefined) {
      scene.skyAtmosphere.atmosphereLightIntensity = 4;   // tightened halo
    }
    scene.fog.enabled = true;
    scene.fog.density = 0.00006;                          // thinner haze
    scene.highDynamicRange = true;
    scene.msaaSamples = 4;

    // Subtle cinematic bloom — premium glow without arcade neon.
    try {
      const bloom = scene.postProcessStages.bloom;
      if (bloom) {
        bloom.enabled = true;
        bloom.uniforms.glowOnly = false;
        bloom.uniforms.contrast = 95;     // selective: only bright highlights bloom
        bloom.uniforms.brightness = -0.15; // less base wash
        bloom.uniforms.delta = 0.80;
        bloom.uniforms.sigma = 1.2;        // tighter blur kernel (-29 %)
        bloom.uniforms.stepSize = 0.85;
      }
    } catch (e) { /* postProcess unavailable on this device */ }

    if (scene.skyBox) scene.skyBox.show = true;
    if (scene.sun) scene.sun.show = true;
    if (scene.moon) scene.moon.show = false;

    // Earth-centred camera with inertial physics. Pre-allocated vectors
    // → zero allocations per frame. Auto-rotate while idle; drag-rotate
    // and wheel-zoom carry inertia and ease toward targets.
    const cam = {
      heading: 0,
      pitch: Cesium.Math.toRadians(20),
      targetPitch: Cesium.Math.toRadians(20),
      range: 25_000_000,
      targetRange: 25_000_000,
      velocityHeading: 0,
      velocityPitch: 0,
      minRange: 8_800_000,
      maxRange: 72_000_000,
      minPitch: Cesium.Math.toRadians(-6),
      maxPitch: Cesium.Math.toRadians(72),
      zoomEase: 0.14,
      pitchEase: 0.10,
      rotateFriction: 0.92,
      autoRotateRate: 0.025, // rad/s — mode-driven
      idleResumeMs: 5000,
      lastInteractionMs: 0,
      activeMode: "command",
    };

    // Camera mode presets — globe stays look-at-origin in every mode.
    const CAMERA_MODES = {
      command:   { pitch: Cesium.Math.toRadians(20), range: 25_000_000, autoRotateRate: 0.025 },
      orbital:   { pitch: Cesium.Math.toRadians(10), range: 20_000_000, autoRotateRate: 0.045 },
      cinematic: { pitch: Cesium.Math.toRadians(28), range: 52_000_000, autoRotateRate: 0.010 },
      tactical:  { pitch: Cesium.Math.toRadians(58), range: 28_000_000, autoRotateRate: 0.000 },
    };
    window.__setCameraMode = (name) => {
      const m = CAMERA_MODES[name];
      if (!m) return;
      cam.targetPitch    = m.pitch;
      cam.targetRange    = clamp(m.range, cam.minRange, cam.maxRange);
      cam.autoRotateRate = m.autoRotateRate;
      cam.activeMode     = name;
      document.querySelectorAll(".mode-pill").forEach((p) =>
        p.classList.toggle("is-active", p.dataset.mode === name)
      );
    };

    const _camPos = new Cesium.Cartesian3();
    const _camDir = new Cesium.Cartesian3();
    const _camUp  = new Cesium.Cartesian3();
    const _worldZ = Cesium.Cartesian3.UNIT_Z;

    const applyCamera = () => {
      const ch = Math.cos(cam.heading), sh = Math.sin(cam.heading);
      const cp = Math.cos(cam.pitch),   sp = Math.sin(cam.pitch);
      _camPos.x = cam.range * cp * ch;
      _camPos.y = cam.range * cp * sh;
      _camPos.z = cam.range * sp;
      _camDir.x = -_camPos.x; _camDir.y = -_camPos.y; _camDir.z = -_camPos.z;
      Cesium.Cartesian3.normalize(_camDir, _camDir);
      const dDotZ = Cesium.Cartesian3.dot(_worldZ, _camDir);
      _camUp.x = _worldZ.x - dDotZ * _camDir.x;
      _camUp.y = _worldZ.y - dDotZ * _camDir.y;
      _camUp.z = _worldZ.z - dDotZ * _camDir.z;
      Cesium.Cartesian3.normalize(_camUp, _camUp);
      viewer.camera.setView({
        destination: _camPos,
        orientation: { direction: _camDir, up: _camUp },
      });
    };
    applyCamera();

    const ssc = scene.screenSpaceCameraController;
    ssc.enableZoom = false;
    ssc.enableTilt = false;
    ssc.enableLook = false;
    ssc.enableTranslate = false;
    ssc.enableRotate = false;

    const canvas = viewer.canvas;
    const markInteraction = () => { cam.lastInteractionMs = performance.now(); };

    // Wheel sets a TARGET range; the render loop eases toward it.
    canvas.addEventListener("wheel", (ev) => {
      ev.preventDefault();
      const factor = ev.deltaY > 0 ? 1.12 : 1 / 1.12;
      cam.targetRange = clamp(cam.targetRange * factor, cam.minRange, cam.maxRange);
      markInteraction();
    }, { passive: false });

    // Drag-to-rotate with inertia on release.
    let dragging = false;
    let dragX = 0, dragY = 0;
    let lastDragT = 0;
    let lastDragDx = 0, lastDragDy = 0;
    canvas.addEventListener("pointerdown", (ev) => {
      if (ev.button !== 0) return;
      dragging = true;
      dragX = ev.clientX; dragY = ev.clientY;
      lastDragT = performance.now();
      lastDragDx = 0; lastDragDy = 0;
      cam.velocityHeading = 0;
      cam.velocityPitch = 0;
      try { canvas.setPointerCapture(ev.pointerId); } catch (e) {}
      canvas.style.cursor = "grabbing";
      markInteraction();
    });
    canvas.addEventListener("pointermove", (ev) => {
      if (!dragging) return;
      const dx = ev.clientX - dragX;
      const dy = ev.clientY - dragY;
      dragX = ev.clientX; dragY = ev.clientY;
      lastDragDx = dx; lastDragDy = dy;
      lastDragT = performance.now();
      // Scale rotation rate by current range so the globe feels consistent at any zoom.
      const sens = 0.0042 * Math.max(0.55, cam.range / 25_000_000);
      cam.heading -= dx * sens;
      cam.pitch    = clamp(cam.pitch + dy * sens * 0.78, cam.minPitch, cam.maxPitch);
      cam.targetPitch = cam.pitch; // sync so mode easing doesn't yank back
      markInteraction();
    });
    const endDrag = (ev) => {
      if (!dragging) return;
      dragging = false;
      try { canvas.releasePointerCapture(ev.pointerId); } catch (e) {}
      canvas.style.cursor = "";
      // Convert last pointer delta into angular velocity for inertia.
      const dtMs = Math.max(8, performance.now() - lastDragT);
      const sens = 0.0042 * Math.max(0.55, cam.range / 25_000_000);
      cam.velocityHeading = -(lastDragDx / dtMs) * sens * 16;  // rad/s
      cam.velocityPitch   =  (lastDragDy / dtMs) * sens * 12;
      markInteraction();
    };
    canvas.addEventListener("pointerup", endDrag);
    canvas.addEventListener("pointercancel", endDrag);
    canvas.addEventListener("pointerleave", endDrag);

    // Render loop: ease range, decay velocity, auto-rotate while idle.
    let lastTick = performance.now();
    scene.postRender.addEventListener(() => {
      const now = performance.now();
      const dt = (now - lastTick) / 1000;
      lastTick = now;

      let dirty = false;

      // Range easing toward target
      if (Math.abs(cam.targetRange - cam.range) > 0.5) {
        cam.range += (cam.targetRange - cam.range) * cam.zoomEase;
        dirty = true;
      }

      // Pitch easing toward target (mode transitions)
      if (Math.abs(cam.targetPitch - cam.pitch) > 0.0004) {
        cam.pitch += (cam.targetPitch - cam.pitch) * cam.pitchEase;
        cam.pitch = clamp(cam.pitch, cam.minPitch, cam.maxPitch);
        dirty = true;
      }

      // Drag-release inertia (decay every frame)
      if (Math.abs(cam.velocityHeading) > 0.0005 || Math.abs(cam.velocityPitch) > 0.0005) {
        cam.heading += cam.velocityHeading * dt;
        cam.pitch    = clamp(cam.pitch + cam.velocityPitch * dt, cam.minPitch, cam.maxPitch);
        cam.velocityHeading *= cam.rotateFriction;
        cam.velocityPitch   *= cam.rotateFriction;
        dirty = true;
      }

      // Auto-rotate after a brief idle
      const idle = !dragging
                && (now - cam.lastInteractionMs) > cam.idleResumeMs
                && Math.abs(cam.velocityHeading) < 0.001
                && Math.abs(cam.velocityPitch)   < 0.001;
      if (idle && cam.autoRotateRate > 0) {
        cam.heading -= cam.autoRotateRate * dt;
        dirty = true;
      }

      if (dirty || dragging) applyCamera();
    });

    const auxOrbits = addOrbitTrails(viewer);
    const syntheticISS = addISS(viewer, sharedCtx);

    window.__camera = cam; // for RuntimeMetrics introspection
    return { viewer, syntheticISS, auxOrbits, cam };
  }

  /* ---- Orbital math helpers ------------------------------------------- */

  function orbitPositions({ altitudeM, inclinationDeg, samples = 240, phase = 0 }) {
    const R = EARTH_RADIUS_M + altitudeM;
    const inc = Cesium.Math.toRadians(inclinationDeg);
    const pts = new Array(samples + 1);
    for (let i = 0; i <= samples; i++) {
      const u = phase + (i / samples) * Math.PI * 2;
      const x = R * Math.cos(u);
      const y = R * Math.sin(u) * Math.cos(inc);
      const z = R * Math.sin(u) * Math.sin(inc);
      pts[i] = new Cesium.Cartesian3(x, y, z);
    }
    return pts;
  }

  function orbitPosition({ altitudeM, inclinationDeg, u }) {
    const R = EARTH_RADIUS_M + altitudeM;
    const inc = Cesium.Math.toRadians(inclinationDeg);
    const x = R * Math.cos(u);
    const y = R * Math.sin(u) * Math.cos(inc);
    const z = R * Math.sin(u) * Math.sin(inc);
    return new Cesium.Cartesian3(x, y, z);
  }

  function addOrbitTrails(viewer) {
    // Auxiliary decorative orbits — OFF by default. Synthetic, not catalog.
    const orbits = [
      { altitudeM:  780_000, inclinationDeg: 86.4, alpha: 0.18, phase: 1.1 },
      { altitudeM: 1_200_000, inclinationDeg: 63.4, alpha: 0.14, phase: 2.0 },
      { altitudeM: 2_000_000, inclinationDeg: 28.0, alpha: 0.12, phase: 4.7 },
    ];
    const entities = [];
    for (const o of orbits) {
      const e = viewer.entities.add({
        polyline: {
          positions: orbitPositions({
            altitudeM: o.altitudeM,
            inclinationDeg: o.inclinationDeg,
            phase: o.phase,
            samples: 200,
          }),
          width: 0.8,
          arcType: Cesium.ArcType.NONE,
          material: Cesium.Color.fromCssColorString("#7fd1e6").withAlpha(o.alpha),
        },
      });
      e.show = false; // user must opt-in via the Aux Orbits toggle
      entities.push(e);
    }
    return entities;
  }

  function addISS(viewer, sharedCtx) {
    const created = [];
    const inclinationDeg = 51.6;
    const periodSeconds = 95; // visible orbit cadence for demo

    // ISS orbit path — cached, rebuilt only when altitude shifts > 0.5 km
    let cachedPath = orbitPositions({ altitudeM: 408_000, inclinationDeg, samples: 200 });
    let cachedAltKm = 408;
    const pathProperty = new Cesium.CallbackProperty(() => {
      const altKm = sharedCtx.issAltitudeKm || 408;
      if (Math.abs(altKm - cachedAltKm) > 0.5) {
        cachedAltKm = altKm;
        cachedPath = orbitPositions({ altitudeM: altKm * 1000, inclinationDeg, samples: 200 });
      }
      return cachedPath;
    }, false);

    created.push(viewer.entities.add({
      polyline: {
        positions: pathProperty,
        width: 1.1,
        arcType: Cesium.ArcType.NONE,
        material: Cesium.Color.fromCssColorString("#7fd1e6").withAlpha(0.42),
      },
    }));

    // ISS marker (moves along the orbit)
    created.push(viewer.entities.add({
      name: "ISS",
      position: new Cesium.CallbackProperty((time) => {
        const altM = (sharedCtx.issAltitudeKm || 408) * 1000;
        const epoch = Cesium.JulianDate.toDate(time).getTime() / 1000;
        const u = ((epoch % periodSeconds) / periodSeconds) * Math.PI * 2;
        return orbitPosition({ altitudeM: altM, inclinationDeg, u });
      }, false),
      point: {
        pixelSize: 6,
        color: Cesium.Color.fromCssColorString("#eaf3fb"),
        outlineColor: Cesium.Color.fromCssColorString("#7fd1e6").withAlpha(0.75),
        outlineWidth: 1.2,
        scaleByDistance: new Cesium.NearFarScalar(1e6, 1.2, 5e7, 0.8),
      },
      label: {
        text: "ISS",
        font: '600 11px "JetBrains Mono", monospace',
        fillColor: Cesium.Color.fromCssColorString("#7fd1e6"),
        style: Cesium.LabelStyle.FILL_AND_OUTLINE,
        outlineColor: Cesium.Color.fromCssColorString("#02060b"),
        outlineWidth: 2,
        verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
        pixelOffset: new Cesium.Cartesian2(0, -14),
        showBackground: true,
        backgroundColor: Cesium.Color.fromCssColorString("#02060b").withAlpha(0.7),
        backgroundPadding: new Cesium.Cartesian2(8, 4),
        translucencyByDistance: new Cesium.NearFarScalar(1.5e7, 1.0, 6e7, 0.4),
      },
    }));

    return {
      entities: created,
      hide() { for (const e of this.entities) e.show = false; },
    };
  }

  /* ============================== REAL ISS (SGP4) ========================== */

  // Replaces the synthetic ISS orbit with a real-world propagation from a
  // CelesTrak TLE, using satellite.js. Builds a 30-min faded trail and a
  // 90-min predicted future arc; the marker is updated by Cesium each frame
  // from a CallbackProperty. If TLE or satellite.js are unavailable, this
  // simply leaves the synthetic ISS in place.
  async function upgradeToRealISS(viewer, sharedCtx) {
    if (typeof window.satellite === "undefined") {
      console.warn("[ASTROSCAN] satellite.js not loaded; keeping synthetic ISS");
      return null;
    }

    let tle;
    try {
      const r = await fetch(`${API_BASE}/api/tle/iss`, { credentials: "same-origin" });
      if (!r.ok) throw new Error(`http ${r.status}`);
      tle = await r.json();
    } catch (e) {
      console.warn("[ASTROSCAN] TLE feed unavailable; synthetic ISS in use (" + (e.message || e) + ")");
      return null;
    }
    if (!tle || !tle.line1 || !tle.line2) return null;

    let satrec;
    try {
      satrec = satellite.twoline2satrec(tle.line1, tle.line2);
    } catch (e) {
      console.warn("[ASTROSCAN] satrec parse failed", e);
      return null;
    }

    const EARTH_RADIUS_KM = 6378.137;

    const propagate = (date) => {
      try {
        const result = satellite.propagate(satrec, date);
        if (!result || !result.position) return null;
        const gmst = satellite.gstime(date);
        const ecf  = satellite.eciToEcf(result.position, gmst);
        const v    = result.velocity;
        const cart = new Cesium.Cartesian3(ecf.x * 1000, ecf.y * 1000, ecf.z * 1000);
        const r    = Math.sqrt(ecf.x * ecf.x + ecf.y * ecf.y + ecf.z * ecf.z);
        const speed = v ? Math.sqrt(v.x * v.x + v.y * v.y + v.z * v.z) : null;
        return { cart, altitudeKm: r - EARTH_RADIUS_KM, speedKmS: speed };
      } catch {
        return null;
      }
    };

    // First propagation sanity check
    const test = propagate(new Date());
    if (!test) {
      console.warn("[ASTROSCAN] SGP4 propagation produced no position; aborting");
      return null;
    }

    // Shared per-frame propagation cache. With 3+ entities (marker, aura,
    // breathing aura) all needing the same live position, a 1-frame cache
    // collapses 3 propagate() calls and 3 Cartesian3 allocations into 1.
    let _propT = 0;
    let _propResult = test;
    const tickedPropagate = () => {
      const now = performance.now();
      if (now - _propT > 16) {
        _propResult = propagate(new Date()) || _propResult;
        _propT = now;
      }
      return _propResult;
    };
    const tickedPosition = () => tickedPropagate().cart;

    // Build past + future point sets.
    const buildTrails = () => {
      const now = new Date();
      const past = [], future = [];
      for (let s = -30 * 60; s < 0; s += 60) {
        const p = propagate(new Date(now.getTime() + s * 1000));
        if (p) past.push(p.cart);
      }
      for (let s = 0; s <= 90 * 60; s += 60) {
        const p = propagate(new Date(now.getTime() + s * 1000));
        if (p) future.push(p.cart);
      }
      return { past, future };
    };
    let trails = buildTrails();

    const pastEntity = viewer.entities.add({
      polyline: {
        positions: new Cesium.CallbackProperty(() => trails.past, false),
        width: 0.9,
        arcType: Cesium.ArcType.NONE,
        material: Cesium.Color.fromCssColorString("#7fd1e6").withAlpha(0.18),
      },
    });

    const futureEntity = viewer.entities.add({
      polyline: {
        positions: new Cesium.CallbackProperty(() => trails.future, false),
        width: 1.0,
        arcType: Cesium.ArcType.NONE,
        material: Cesium.Color.fromCssColorString("#7fd1e6").withAlpha(0.32),
      },
    });

    // Inner aura — faint cyan ring around the asset for premium beacon presence.
    const issAura = viewer.entities.add({
      position: new Cesium.CallbackProperty(tickedPosition, false),
      point: {
        pixelSize: 16,
        color: Cesium.Color.fromCssColorString("#7fd1e6").withAlpha(0.0),
        outlineColor: Cesium.Color.fromCssColorString("#7fd1e6").withAlpha(0.32),
        outlineWidth: 1.0,
        scaleByDistance: new Cesium.NearFarScalar(1e6, 1.2, 5e7, 0.55),
        translucencyByDistance: new Cesium.NearFarScalar(5e6, 0.55, 5e7, 0.10),
      },
    });

    // Outer breathing aura — restrained amplitude to match tighter atmosphere.
    const _outerOutline = Cesium.Color.fromCssColorString("#7fd1e6").withAlpha(0.10);
    const issBreathAura = viewer.entities.add({
      position: new Cesium.CallbackProperty(tickedPosition, false),
      point: {
        pixelSize: new Cesium.CallbackProperty(() => 22 + Math.sin(performance.now() / 1800) * 2.0, false),
        color: Cesium.Color.fromCssColorString("#7fd1e6").withAlpha(0.0),
        outlineColor: new Cesium.CallbackProperty(() => {
          _outerOutline.alpha = 0.10 + Math.sin(performance.now() / 1800) * 0.04;
          return _outerOutline;
        }, false),
        outlineWidth: 1.0,
        scaleByDistance: new Cesium.NearFarScalar(1e6, 1.0, 5e7, 0.45),
        translucencyByDistance: new Cesium.NearFarScalar(5e6, 0.50, 5e7, 0.06),
      },
    });

    const issEntity = viewer.entities.add({
      name: "ISS",
      position: new Cesium.CallbackProperty(tickedPosition, false),
      point: {
        pixelSize: 7,
        color: Cesium.Color.fromCssColorString("#eaf3fb"),
        outlineColor: Cesium.Color.fromCssColorString("#7fd1e6").withAlpha(0.94),
        outlineWidth: 1.6,
        scaleByDistance: new Cesium.NearFarScalar(1e6, 1.3, 5e7, 0.8),
      },
      label: {
        text: "ISS",
        font: '600 11px "JetBrains Mono", monospace',
        fillColor: Cesium.Color.fromCssColorString("#eaf3fb"),
        style: Cesium.LabelStyle.FILL_AND_OUTLINE,
        outlineColor: Cesium.Color.fromCssColorString("#02060b"),
        outlineWidth: 2,
        verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
        pixelOffset: new Cesium.Cartesian2(0, -16),
        showBackground: true,
        backgroundColor: Cesium.Color.fromCssColorString("#02060b").withAlpha(0.82),
        backgroundPadding: new Cesium.Cartesian2(10, 5),
        translucencyByDistance: new Cesium.NearFarScalar(1.5e7, 1.0, 6e7, 0.4),
      },
    });

    // Push live altitude + velocity into the shared frame for the AI advisor
    // and the telemetry meters. Runs at 1Hz — Cesium handles the visible motion.
    setInterval(() => {
      const p = propagate(new Date());
      if (!p) return;
      if (Number.isFinite(p.altitudeKm)) sharedCtx.issAltitudeKm = p.altitudeKm;
      if (Number.isFinite(p.speedKmS))   sharedCtx.realIssVelocity = p.speedKmS;
    }, 1000);

    // Rebuild trails every 5 min so they slide forward through real time.
    setInterval(() => { trails = buildTrails(); }, 5 * 60 * 1000);

    // Trust badge update
    const issTrust = document.getElementById("iss-trust");
    if (issTrust) {
      if (tle.live) {
        issTrust.textContent = "Orbit · Live · CelesTrak";
        issTrust.dataset.trust = "live";
        issTrust.title = `TLE epoch ${tle.line1.slice(18, 32)} · NORAD 25544 · refreshed hourly.`;
      } else {
        issTrust.textContent = "Orbit · Estimated · cached TLE";
        issTrust.dataset.trust = "estimated";
        issTrust.title = "CelesTrak unreachable — propagating from cached TLE.";
      }
    }

    if (window.__system) {
      window.__system.set("tle", tle.live ? "live" : "cached",
        tle.live ? "Live · CelesTrak" : "Cached · fallback");
    }
    if (window.__runtime) window.__runtime.markCacheWrite();
    if (window.__alerts) {
      window.__alerts.push({
        tag: "info", source: "TLE",
        msg: tle.live ? "Orbital refresh ok · TLE updated."
                      : "Orbital refresh fallback · cached TLE in use.",
      });
    }
    if (window.__acq) window.__acq.setTrack(!!tle.live, !tle.live);
    // M3: brief refresh glow on the orbit trust badge
    if (issTrust) {
      issTrust.classList.add("is-refreshing");
      setTimeout(() => issTrust.classList.remove("is-refreshing"), 800);
    }
    // M6: one-shot acquisition pulse the first time we lock
    if (tle.live && !window.__acqPulsed) {
      window.__acqPulsed = true;
      if (issTrust) {
        issTrust.classList.add("is-acquiring");
        setTimeout(() => issTrust.classList.remove("is-acquiring"), 2200);
      }
    }

    return { tle, entities: [pastEntity, futureEntity, issAura, issBreathAura, issEntity] };
  }

  /* ============================== ACQUISITION STATUS ======================= */

  // Derives SIGNAL / TRACK / UPLINK readouts from the existing data plane.
  // SIGNAL = NOAA SWPC connection state. TRACK = SGP4 lock from CelesTrak TLE.
  // UPLINK = WS round-trip latency band. No fake operational claims.
  class AcquisitionStatus {
    constructor() {
      this.signalPill = $("#acq-signal-pill");
      this.trackPill  = $("#acq-track-pill");
      this.uplinkPill = $("#acq-uplink-pill");
      this.signalEl = $("#acq-signal");
      this.trackEl  = $("#acq-track");
      this.uplinkEl = $("#acq-uplink");
      this.confBars = {
        signal:    $("#conf-signal-bar"),
        track:     $("#conf-track-bar"),
        integrity: $("#conf-integrity-bar"),
        uplink:    $("#conf-uplink-bar"),
      };
    }
    _setConf(key, pct) {
      const el = this.confBars[key];
      if (!el) return;
      const v = clamp(pct, 0, 100);
      el.style.width = v.toFixed(1) + "%";
      const cell = el.closest(".conf-cell");
      if (cell) {
        cell.classList.toggle("conf-cell--warn", v < 70 && v >= 40);
        cell.classList.toggle("conf-cell--crit", v < 40);
      }
    }
    setSignal(live, cached) {
      if (this.signalPill) {
        const state = live ? "locked" : (cached ? "degraded" : "lost");
        this.signalPill.dataset.state = state;
        this.signalEl.textContent = live ? "LOCKED" : (cached ? "DEGRADED" : "LOST");
      }
      this._setConf("signal", live ? 95 : cached ? 65 : 12);
    }
    setTrack(live, cached) {
      if (this.trackPill) {
        const state = live ? "locked" : (cached ? "degraded" : "lost");
        this.trackPill.dataset.state = state;
        this.trackEl.textContent = live ? "VERIFIED" : (cached ? "ESTIMATED" : "ACQUIRING");
      }
      this._setConf("track", live ? 98 : cached ? 72 : 18);
    }
    setIntegrity(pct) {
      if (Number.isFinite(pct)) this._setConf("integrity", pct);
    }
    setUplink(rttMs, status) {
      if (this.uplinkPill) {
        let state = "syncing";
        let label = "—";
        const pad = (n) => String(Math.min(n, 999)).padStart(3, "0");
        if (status === "LIVE") {
          if (rttMs > 0 && rttMs < 120)        { state = "locked";   label = `${pad(rttMs)} ms · OPTIMAL`; }
          else if (rttMs > 0 && rttMs < 250)   { state = "locked";   label = `${pad(rttMs)} ms · STABLE`; }
          else if (rttMs > 0 && rttMs < 500)   { state = "degraded"; label = `${pad(rttMs)} ms · NOMINAL`; }
          else if (rttMs >= 500)               { state = "degraded"; label = `${rttMs} ms · LAG`; }
          else                                  { state = "locked";   label = "STABLE"; }
        } else if (status === "DEGRADED") { state = "degraded"; label = "DEGRADED"; }
        else if (status === "OFFLINE")    { state = "lost"; label = "OFFLINE"; }
        this.uplinkPill.dataset.state = state;
        this.uplinkEl.textContent = label;
      }
      let pct = 0;
      if (status === "LIVE") {
        if (rttMs > 0 && rttMs < 80)         pct = 99;
        else if (rttMs > 0 && rttMs < 200)   pct = 94;
        else if (rttMs > 0 && rttMs < 500)   pct = 80;
        else if (rttMs > 0)                  pct = 55;
        else                                  pct = 86;
      } else if (status === "DEGRADED") pct = 45;
      else if (status === "OFFLINE")    pct = 10;
      this._setConf("uplink", pct);
    }
  }

  /* ============================== SPACE WEATHER ============================ */

  function kpClass(kp) {
    if (kp >= 9) return "G5 EXTREME";
    if (kp >= 8) return "G4 SEVERE";
    if (kp >= 7) return "G3 STRONG";
    if (kp >= 6) return "G2 MODERATE";
    if (kp >= 5) return "G1 MINOR";
    if (kp >= 4) return "ACTIVE";
    if (kp >= 3) return "UNSETTLED";
    return "QUIET";
  }
  function xrayClass(flux) {
    if (flux >= 1e-4) return "X" + (flux * 1e4).toFixed(1);
    if (flux >= 1e-5) return "M" + (flux * 1e5).toFixed(1);
    if (flux >= 1e-6) return "C" + (flux * 1e6).toFixed(1);
    if (flux >= 1e-7) return "B" + (flux * 1e7).toFixed(1);
    return "A" + Math.max(0.1, flux * 1e8).toFixed(1);
  }
  function xrayBand(flux) {
    if (flux >= 1e-4) return "X-CLASS";
    if (flux >= 1e-5) return "M-CLASS";
    if (flux >= 1e-6) return "C-CLASS";
    if (flux >= 1e-7) return "B-CLASS";
    return "A-CLASS";
  }

  class SpaceWeather {
    constructor() {
      this.kpEl   = $("#env-kp");
      this.kpB    = $("#env-kp-band");
      this.fluxEl = $("#env-flux");
      this.xrayEl = $("#env-xray");
      this.xrayB  = $("#env-xray-band");
      this.trust  = $("#env-trust");
    }
    async start() {
      await this.refresh();
      setInterval(() => this.refresh(), 5 * 60 * 1000);
    }
    async refresh() {
      try {
        const r = await fetch(`${API_BASE}/api/space-weather`, { credentials: "same-origin" });
        if (!r.ok) throw new Error(`http ${r.status}`);
        this._notified = false;
        const swxData = await r.json();
        // Expose space weather values to LIVE_OVERRIDES for threat_index computation
        if (swxData && swxData.live === true) {
          LIVE_OVERRIDES.space_kp = typeof swxData.kp === "number" ? swxData.kp : null;
          LIVE_OVERRIDES.space_xray_wm2 = typeof swxData.xray_long_wm2 === "number" ? swxData.xray_long_wm2 : null;
          LIVE_OVERRIDES.space_f107 = typeof swxData.f107 === "number" ? swxData.f107 : null;
        } else {
          LIVE_OVERRIDES.space_kp = null;
          LIVE_OVERRIDES.space_xray_wm2 = null;
          LIVE_OVERRIDES.space_f107 = null;
        }
        this.render(swxData);
      } catch (e) {
        if (this.trust) {
          this.trust.textContent = "Offline · fallback";
          this.trust.dataset.trust = "cached";
        }
        // Warn-once: avoid console spam if the proxy stays unreachable.
        if (!this._notified) {
          this._notified = true;
          console.warn("[ASTROSCAN] space weather unavailable; fallback active (" + (e.message || e) + ")");
        }
      }
    }
    render(d) {
      if (!this.kpEl) return;
      const kp = Number(d.kp);
      if (Number.isFinite(kp)) {
        this.kpEl.textContent = kp.toFixed(1);
        this.kpB.textContent  = kpClass(kp);
        this.kpEl.dataset.level = kp >= 7 ? "crit" : kp >= 5 ? "warn" : "ok";
      }
      const flux = Number(d.f107);
      if (Number.isFinite(flux)) this.fluxEl.textContent = flux.toFixed(0);

      const xr = Number(d.xray_long_wm2);
      if (Number.isFinite(xr)) {
        this.xrayEl.textContent = xrayClass(xr);
        this.xrayB.textContent  = xrayBand(xr);
        this.xrayEl.dataset.level = xr >= 1e-4 ? "crit" : xr >= 1e-5 ? "warn" : "ok";
      }
      if (this.trust) {
        if (d.live) {
          this.trust.textContent = "Live · NOAA SWPC";
          this.trust.dataset.trust = "live";
        } else {
          this.trust.textContent = "Cached · fallback";
          this.trust.dataset.trust = "cached";
        }
      }
      if (window.__system) {
        window.__system.set("swx", d.live ? "live" : "cached",
          d.live ? "Live · NOAA SWPC" : "Cached · fallback");
      }
      if (window.__runtime) window.__runtime.markCacheWrite();
      if (window.__alerts) {
        window.__alerts.push({
          tag: "info", source: "NOAA",
          msg: `Geomagnetic Kp updated · ${Number(d.kp).toFixed(1)} (${kpClass(Number(d.kp))}).`,
        });
      }
      if (window.__acq) window.__acq.setSignal(!!d.live, !d.live);
      if (window.__sigint && Number.isFinite(d.f107)) window.__sigint.setSolarFlux(d.f107);
      // M3: brief glow on the SPACE ENVIRONMENT section when fresh data lands
      const envHead = document.querySelector(".panel__section .section-head #env-trust")?.closest(".panel__section");
      if (envHead) {
        envHead.classList.add("is-refreshing");
        setTimeout(() => envHead.classList.remove("is-refreshing"), 800);
      }
    }
  }

  /* ============================== WEBSOCKET ================================ */

  class TelemetryClient {
    constructor(path, onFrame, onStatus) {
      this.path = path;
      this.onFrame = onFrame;
      this.onStatus = onStatus;
      this.ws = null;
      this.attempts = 0;
      this.lastFrameAt = 0;
    }

    url() {
      const proto = location.protocol === "https:" ? "wss:" : "ws:";
      return `${proto}//${location.host}${this.path}`;
    }

    connect() {
      this.onStatus("CONNECTING");
      try {
        this.ws = new WebSocket(this.url());
      } catch (e) {
        this.scheduleReconnect();
        return;
      }

      this.ws.addEventListener("open", () => {
        this.attempts = 0;
        this.onStatus("LIVE");
      });

      this.ws.addEventListener("message", (evt) => {
        const now = performance.now();
        try {
          const frame = JSON.parse(evt.data);
          this.lastFrameAt = now;
          // Override synthetic metrics with live values when available
          if (frame && frame.metrics) {
            if (LIVE_OVERRIDES.air_traffic_density !== null) {
              frame.metrics.air_traffic_density = LIVE_OVERRIDES.air_traffic_density;
              frame.metrics._air_traffic_live = true;
              frame.metrics._air_traffic_meta = LIVE_OVERRIDES.air_traffic_meta;
            }
            if (LIVE_OVERRIDES.seismic_activity !== null) {
              frame.metrics.seismic_activity = LIVE_OVERRIDES.seismic_activity;
              frame.metrics._seismic_live = true;
              frame.metrics._seismic_meta = LIVE_OVERRIDES.seismic_meta;
            }
            // Threat Index recomputed from LIVE sources (NOAA Kp/Xray + USGS + OpenSky + TLE age)
            const liveThreat = computeLiveThreatIndex();
            if (liveThreat !== null) {
              frame.threat_index = liveThreat.score;
              frame._threat_live = true;
              frame._threat_breakdown = liveThreat.breakdown;
              frame._threat_coverage = liveThreat.weight_coverage;
            }
          }
          this.onFrame(frame, now);
        } catch (e) {
          console.warn("[ASTROSCAN] invalid telemetry frame", e);
        }
      });

      this.ws.addEventListener("close", () => {
        this.onStatus("OFFLINE");
        this.scheduleReconnect();
      });

      this.ws.addEventListener("error", () => {
        this.onStatus("DEGRADED");
        try { this.ws.close(); } catch (e) {}
      });
    }

    scheduleReconnect() {
      const idx = clamp(this.attempts, 0, RECONNECT_BACKOFF_MS.length - 1);
      const delay = RECONNECT_BACKOFF_MS[idx];
      this.attempts += 1;
      setTimeout(() => this.connect(), delay);
    }
  }

  /* ============================== AUDIO ENGINE ============================= */

  class CommandAudio {
    constructor() {
      this.ctx = null;
      this.master = null;
      this.panner = null;
      this.ambienceNodes = null;
      this.enabled = true;
      this.unlocked = false;
      this.volume = 0.80;
      this.balance = 0.0;
      this.profile = "mission";
    }

    async ensure() {
      if (this.ctx) {
        if (this.ctx.state === "suspended") await this.ctx.resume();
        return;
      }
      const AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return;
      this.ctx = new AC();
      this.master = this.ctx.createGain();
      this.master.gain.value = this.enabled ? this.volume : 0.0;

      if (typeof this.ctx.createStereoPanner === "function") {
        this.panner = this.ctx.createStereoPanner();
        this.panner.pan.value = this.balance;
        this.master.connect(this.panner);
        this.panner.connect(this.ctx.destination);
      } else {
        this.master.connect(this.ctx.destination);
      }

      this._buildAmbience();
      this.unlocked = true;
      this.setProfile(this.profile);
      this.startupChime();
    }

    // One-shot cinematic chord on first audio unlock. Ascending C-E-G,
    // soft attack/release, no loops, gated behind a user gesture by design.
    startupChime() {
      if (!this.ctx || !this.enabled) return;
      const ctx = this.ctx;
      const t0 = ctx.currentTime + 0.08;
      const notes = [
        { f: 261.63, delay: 0.00 }, // C4
        { f: 329.63, delay: 0.22 }, // E4
        { f: 392.00, delay: 0.44 }, // G4
      ];
      for (const n of notes) {
        const osc = ctx.createOscillator();
        const filt = ctx.createBiquadFilter();
        const gain = ctx.createGain();
        osc.type = "sine";
        osc.frequency.value = n.f;
        filt.type = "lowpass";
        filt.frequency.value = 1400;
        filt.Q.value = 0.6;
        const start = t0 + n.delay;
        gain.gain.setValueAtTime(0.0001, start);
        gain.gain.exponentialRampToValueAtTime(0.085, start + 0.06);
        gain.gain.exponentialRampToValueAtTime(0.0001, start + 1.20);
        osc.connect(filt);
        filt.connect(gain);
        gain.connect(this.master);
        osc.start(start);
        osc.stop(start + 1.40);
      }
    }

    setEnabled(on) { this.setMuted(!on); }

    setMuted(muted) {
      this.enabled = !muted;
      if (!this.master) return;
      const t = this.ctx.currentTime;
      this.master.gain.cancelScheduledValues(t);
      this.master.gain.linearRampToValueAtTime(this.enabled ? this.volume : 0.0, t + 0.3);
    }

    setVolume(v) {
      this.volume = clamp(v, 0, 1);
      if (!this.master) return;
      if (!this.enabled) return;
      const t = this.ctx.currentTime;
      this.master.gain.cancelScheduledValues(t);
      this.master.gain.linearRampToValueAtTime(this.volume, t + 0.15);
    }

    setBalance(b) {
      this.balance = clamp(b, -1, 1);
      if (!this.panner) return;
      const t = this.ctx.currentTime;
      this.panner.pan.cancelScheduledValues(t);
      this.panner.pan.linearRampToValueAtTime(this.balance, t + 0.15);
    }

    setProfile(name) {
      this.profile = name;
      if (!this.ambienceNodes || !this.ctx) return;
      const { padGain, noiseGain, osc1, osc2 } = this.ambienceNodes;
      const t = this.ctx.currentTime;
      const ramp = (param, value, dur = 0.4) => {
        param.cancelScheduledValues(t);
        param.linearRampToValueAtTime(value, t + dur);
      };
      if (name === "silent") {
        ramp(padGain.gain, 0.0);
        ramp(noiseGain.gain, 0.0);
      } else if (name === "deep") {
        ramp(padGain.gain, 0.060);
        ramp(noiseGain.gain, 0.010);
        osc1.frequency.setTargetAtTime(70,        t, 0.3);
        osc2.frequency.setTargetAtTime(70 * 1.498, t, 0.3);
      } else if (name === "cinematic") {
        // Deep, slow, restrained spacecraft hum.
        ramp(padGain.gain, 0.072, 0.6);
        ramp(noiseGain.gain, 0.024, 0.6);
        osc1.frequency.setTargetAtTime(55,        t, 0.45);
        osc2.frequency.setTargetAtTime(55 * 1.498, t, 0.45);
      } else {
        ramp(padGain.gain, 0.045);
        ramp(noiseGain.gain, 0.018);
        osc1.frequency.setTargetAtTime(110,        t, 0.3);
        osc2.frequency.setTargetAtTime(110 * 1.498, t, 0.3);
      }
    }

    _buildAmbience() {
      const ctx = this.ctx;

      // Layer 1: very soft low pad (two slightly detuned sines)
      const padGain = ctx.createGain();
      padGain.gain.value = 0.045;

      const osc1 = ctx.createOscillator();
      const osc2 = ctx.createOscillator();
      osc1.type = "sine"; osc2.type = "sine";
      osc1.frequency.value = 110;
      osc2.frequency.value = 110 * 1.498; // perfect fifth-ish for tension

      const padFilter = ctx.createBiquadFilter();
      padFilter.type = "lowpass";
      padFilter.frequency.value = 600;
      padFilter.Q.value = 0.7;

      osc1.connect(padFilter);
      osc2.connect(padFilter);
      padFilter.connect(padGain);
      padGain.connect(this.master);

      // Layer 2: gentle filtered noise "room tone"
      const bufferSize = 2 * ctx.sampleRate;
      const noiseBuffer = ctx.createBuffer(1, bufferSize, ctx.sampleRate);
      const data = noiseBuffer.getChannelData(0);
      for (let i = 0; i < bufferSize; i++) {
        data[i] = (Math.random() * 2 - 1) * 0.6;
      }
      const noise = ctx.createBufferSource();
      noise.buffer = noiseBuffer;
      noise.loop = true;

      const noiseFilter = ctx.createBiquadFilter();
      noiseFilter.type = "bandpass";
      noiseFilter.frequency.value = 480;
      noiseFilter.Q.value = 0.6;

      const noiseGain = ctx.createGain();
      noiseGain.gain.value = 0.018;

      noise.connect(noiseFilter);
      noiseFilter.connect(noiseGain);
      noiseGain.connect(this.master);

      // Subtle LFO on the pad filter for breathing
      const lfo = ctx.createOscillator();
      const lfoGain = ctx.createGain();
      lfo.frequency.value = 0.07;
      lfoGain.gain.value = 120;
      lfo.connect(lfoGain);
      lfoGain.connect(padFilter.frequency);

      osc1.start(); osc2.start(); noise.start(); lfo.start();

      this.ambienceNodes = { osc1, osc2, noise, lfo, padGain, noiseGain };
    }

    radarPing() {
      if (!this.enabled || !this.ctx) return;
      const ctx = this.ctx;
      const t = ctx.currentTime;

      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      const filter = ctx.createBiquadFilter();

      osc.type = "sine";
      osc.frequency.setValueAtTime(1320, t);
      osc.frequency.exponentialRampToValueAtTime(720, t + 0.45);

      filter.type = "bandpass";
      filter.frequency.value = 1100;
      filter.Q.value = 6;

      gain.gain.setValueAtTime(0.0001, t);
      gain.gain.exponentialRampToValueAtTime(0.18, t + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.55);

      osc.connect(filter);
      filter.connect(gain);
      gain.connect(this.master);

      osc.start(t);
      osc.stop(t + 0.6);
    }

    alertBeep() {
      if (!this.enabled || !this.ctx) return;
      const ctx = this.ctx;
      const t = ctx.currentTime;

      const osc = ctx.createOscillator();
      const gain = ctx.createGain();

      osc.type = "triangle";
      osc.frequency.setValueAtTime(880, t);
      osc.frequency.linearRampToValueAtTime(660, t + 0.18);

      gain.gain.setValueAtTime(0.0001, t);
      gain.gain.exponentialRampToValueAtTime(0.12, t + 0.015);
      gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.25);

      osc.connect(gain);
      gain.connect(this.master);

      osc.start(t);
      osc.stop(t + 0.3);
    }
  }

  /* ============================== AI COMMAND FEED ========================== */

  class AIConsole {
    constructor(el, snapshot) {
      this.el = el;
      this.snapshot = snapshot; // () => latest frame or null
      this.timer = null;
      this.lastMsg = "";
    }

    start() {
      this._tick();
      this.timer = setInterval(() => this._tick(), 5200);
    }

    _tick() {
      const msg = this._pick(this.snapshot ? this.snapshot() : null);
      this.lastMsg = msg;
      this._typewriter(msg);
    }

    _pick(frame) {
      if (!frame) return "Establishing command channel…";

      // ─── LIVE OVERRIDE : NOAA SWPC space weather advisor ───
      // When AdvisorLive has populated LIVE_OVERRIDES.advisor_message with a
      // real NOAA alert, use it directly and bypass the synthetic pool.
      // The synthetic pool resumes automatically if NOAA goes into fallback.
      if (LIVE_OVERRIDES.advisor_message) {
        return LIVE_OVERRIDES.advisor_message;
      }

      const m = frame.metrics || {};
      const o = frame.orbital_status || {};
      const t = frame.threat_index;
      const pool = [];

      if (Number.isFinite(o.integrity)) {
        if (o.integrity >= 96) pool.push("Orbital vector nominal · telemetry coherence verified.");
        else if (o.integrity >= 90) pool.push("Orbital integrity within tolerance window.");
        else pool.push("Orbital integrity degraded · diagnostic loop engaged.");
      }
      if (Number.isFinite(o.iss_velocity_km_s)) {
        pool.push(`Tracked asset stable · ${o.iss_velocity_km_s.toFixed(3)} km·s⁻¹.`);
      }
      if (Number.isFinite(t)) {
        if (t >= 70) pool.push(`Threat vector elevated · index ${t.toFixed(1)} · posture re-evaluating.`);
        else if (t >= 50) pool.push(`Threat vector trending · index ${t.toFixed(1)}.`);
        else pool.push("Threat vector nominal · acquisition stable.");
      }
      if (Number.isFinite(m.solar_activity)) {
        if (m.solar_activity >= 70) pool.push("Solar flux trend detected · radiation envelope expanding.");
        else if (m.solar_activity >= 50) pool.push("Solar flux trending · within forecast band.");
        else pool.push("Solar flux quiet · baseline confirmed.");
      }
      if (Number.isFinite(m.maritime_density)) {
        if (m.maritime_density >= 70) pool.push("Maritime grid · anomaly cluster on principal lanes.");
        else pool.push("Geo-maritime grid synchronized.");
      }
      if (Number.isFinite(m.air_traffic_density)) {
        if (m.air_traffic_density >= 70) pool.push("Airspace density rising · corridor saturation watch.");
        else pool.push("Airspace network cross-checked · nominal cadence.");
      }
      if (Number.isFinite(m.visibility_score)) {
        if (m.visibility_score >= 85) pool.push("Atmospheric visibility optimal · acquisition margin healthy.");
        else if (m.visibility_score < 65) pool.push("Atmospheric visibility reduced · acquisition margin narrowing.");
      }
      if (Number.isFinite(m.seismic_activity) && m.seismic_activity >= 55) {
        pool.push(`Seismic activity above baseline · ${m.seismic_activity.toFixed(1)} indexed.`);
      }
      if (Number.isFinite(m.system_health)) {
        if (m.system_health >= 96) pool.push("Uplink latency within window · signal integrity above threshold.");
        else pool.push("Command lattice integrity verified.");
      }

      if (pool.length === 0) return "Global systems operational.";

      // Pick differently from last message when possible
      let pick = pool[Math.floor(Math.random() * pool.length)];
      if (pick === this.lastMsg && pool.length > 1) {
        const idx = pool.indexOf(pick);
        pick = pool[(idx + 1) % pool.length];
      }
      return pick;
    }

    _typewriter(text) {
      // Refined: short cross-fade instead of typewriter. Calmer, faster to read,
      // no per-char setTimeout churn.
      const el = this.el;
      el.style.transition = "opacity 220ms ease";
      el.style.opacity = "0";
      setTimeout(() => {
        el.textContent = text;
        el.style.opacity = "1";
      }, 220);
    }
  }

  /* ============================== COMMAND TICKER =========================== */

  class CommandTicker {
    constructor(el) {
      this.el = el;
      this.current = null;
    }
    push(text) {
      const li = document.createElement("li");
      li.textContent = text;
      this.el.appendChild(li);
      requestAnimationFrame(() => li.classList.add("in"));

      if (this.current) {
        const prev = this.current;
        prev.classList.remove("in");
        prev.classList.add("out");
        setTimeout(() => prev.remove(), 600);
      }
      this.current = li;
    }
  }

  /* ============================== SOLAR MONITOR ============================ */

  class SolarMonitor {
    constructor({ waveEl, areaEl, headEl, fluxEl, bandEl }) {
      this.waveEl = waveEl;
      this.areaEl = areaEl;
      this.headEl = headEl;
      this.fluxEl = fluxEl;
      this.bandEl = bandEl;
      this.samples = new Array(64).fill(40);
      this.target = 40;
      this.t = 0;
      this.running = false;
    }

    setTarget(v) {
      if (Number.isFinite(v)) this.target = clamp(v, 0, 100);
    }

    start() {
      if (this.running) return;
      this.running = true;
      const tick = () => {
        if (!this.running) return;
        this._step();
        requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    }

    _step() {
      // 1) Drift current head value toward target + add fast oscillation
      const head = this.samples[this.samples.length - 1];
      const ease = head + (this.target - head) * 0.06;
      const wobble =
        Math.sin(this.t * 0.18) * 4.5 +
        Math.sin(this.t * 0.47 + 1.3) * 2.2 +
        Math.sin(this.t * 1.10 + 0.6) * 1.0 +
        (Math.random() - 0.5) * 1.2;
      const next = clamp(ease + wobble, 0, 100);
      this.samples.push(next);
      this.samples.shift();
      this.t += 1;

      // 2) Render polyline / area / head
      const W = 200, H = 60, n = this.samples.length;
      let line = "";
      for (let i = 0; i < n; i++) {
        const x = (i / (n - 1)) * W;
        const y = H - (this.samples[i] / 100) * (H - 6) - 3;
        line += (i === 0 ? "" : " ") + x.toFixed(2) + "," + y.toFixed(2);
      }
      this.waveEl.setAttribute("points", line);
      this.areaEl.setAttribute("points", `0,${H} ${line} ${W},${H}`);

      const lastX = W;
      const lastY = H - (next / 100) * (H - 6) - 3;
      this.headEl.setAttribute("cx", lastX.toFixed(2));
      this.headEl.setAttribute("cy", lastY.toFixed(2));

      // 3) Derived flux + band readouts (updated less often)
      if (this.t % 8 === 0) {
        const fluxWm2 = (1e-7 + (next / 100) * 9.9e-4);
        this.fluxEl.textContent = fluxWm2.toExponential(2) + " W/m²";
        let band = "QUIET";
        if (next >= 80) band = "X-CLASS";
        else if (next >= 65) band = "M-CLASS";
        else if (next >= 45) band = "C-CLASS";
        else if (next >= 25) band = "B-CLASS";
        this.bandEl.textContent = band;
      }
    }
  }

  /* ============================== METER RENDERING ========================== */

  const _meterPrev = new Map();

  function renderMeter(key, value) {
    const valueEl = $(`#m-${key}`);
    const barEl = $(`#m-${key}-bar`);
    const meterEl = barEl ? barEl.closest(".meter") : null;
    if (!valueEl || !barEl || !meterEl) return;

    const v = clamp(value, 0, 100);
    valueEl.textContent = fmtNum(v, 1);
    barEl.style.width = v.toFixed(2) + "%";

    let level = "ok";
    if (v >= 75) level = "crit";
    else if (v >= 55) level = "warn";
    meterEl.dataset.level = level;

    // Trend arrow (delta vs previous frame)
    const prev = _meterPrev.get(key);
    const trendEl = $(`#m-${key}-trend`);
    if (trendEl) {
      if (Number.isFinite(prev)) {
        const d = v - prev;
        if (Math.abs(d) < 0.8) {
          trendEl.textContent = "·";
          trendEl.dataset.dir = "flat";
        } else if (d > 0) {
          trendEl.textContent = "▲";
          trendEl.dataset.dir = "up";
        } else {
          trendEl.textContent = "▼";
          trendEl.dataset.dir = "down";
        }
      }
    }
    // Micro tick on meaningful change — single 320ms one-shot, GPU-composited.
    if (Number.isFinite(prev) && Math.abs(v - prev) > 0.2) {
      valueEl.classList.remove("is-tick");
      void valueEl.offsetWidth; // force reflow so the animation restarts
      valueEl.classList.add("is-tick");
      setTimeout(() => valueEl.classList.remove("is-tick"), 340);
    }
    _meterPrev.set(key, v);
  }

  function renderTelemetryMeter(key, value) {
    const valueEl = $(`#t-${key}`);
    const barEl = $(`#t-${key}-bar`);
    const meterEl = barEl ? barEl.closest(".meter") : null;
    if (!valueEl || !barEl || !meterEl) return;

    const v = clamp(value, 0, 100);
    valueEl.textContent = fmtNum(v, 1);
    barEl.style.width = v.toFixed(2) + "%";

    // Inverted semantics: higher is better -> warn when LOW
    let level = "ok";
    if (v < 50) level = "crit";
    else if (v < 70) level = "warn";
    meterEl.dataset.level = level;
  }

  /* ============================== THREAT RENDER ============================ */

  let _lastThreatBand = "";

  function renderThreat(value) {
    const ringBar = $("#threat-ring-bar");
    const headline = $(".threat-headline");
    const ring = $("#threat-ring");
    const valueEl = $("#threat-value");
    const bandEl = $("#threat-band");
    const chipEl = $("#chip-threat");

    const v = clamp(value, 0, 100);
    valueEl.textContent = v.toFixed(1);
    ringBar.setAttribute("stroke-dasharray", `${v.toFixed(2)} 100`);
    if (chipEl) chipEl.textContent = v.toFixed(0);

    let band = "ok", label = "NOMINAL";
    if (v >= 70) { band = "crit"; label = "ELEVATED // CRITICAL"; }
    else if (v >= 50) { band = "warn"; label = "ELEVATED"; }
    else if (v >= 30) { band = "ok"; label = "NOMINAL"; }
    else { band = "ok"; label = "STABLE"; }

    headline.dataset.band = band;
    if (ring) ring.dataset.band = band;
    bandEl.textContent = label;

    // Threshold-crossing pulse — only fires on actual band transitions.
    if (_lastThreatBand && _lastThreatBand !== band) {
      headline.classList.add("is-band-shift");
      setTimeout(() => headline.classList.remove("is-band-shift"), 720);
    }
    _lastThreatBand = band;

    const chip = $(".status-chip[data-chip='threat']");
    if (chip) chip.dataset.state = band === "ok" ? "ok" : band;

    const postureChip = $(".status-chip[data-chip='defcon']");
    if (postureChip) {
      postureChip.querySelector(".status-chip__value").textContent =
        v >= 70 ? "ELEVATED" : v >= 50 ? "GUARDED" : "NOMINAL";
      postureChip.dataset.state = band === "ok" ? "ok" : band;
    }
  }

  /* ============================== ALERT LOGIC ============================== */

  class AlertManager {
    constructor(feedEl, ticker, audio) {
      this.feedEl = feedEl;
      this.ticker = ticker;
      this.audio = audio;
      this.maxItems = 14;
      this.lastBand = "ok";
      this.lastSpikes = {};
    }

    push(payload) { this._push(payload); }

    _push({ tag, msg, source }) {
      const li = document.createElement("li");
      li.className = `alert alert--${tag}`;
      const now = new Date();
      const ms = String(now.getUTCMilliseconds()).padStart(3, "0");
      const time = `${fmtClock(now, "UTC")}.${ms}`;
      const label = source || tag.toUpperCase();
      li.innerHTML = `
        <span class="alert__time">${time}</span>
        <span class="alert__tag alert__tag--${tag}">${label}</span>
        <span class="alert__msg">${msg}</span>
      `;
      // Replace placeholder if present
      if (this.feedEl.children.length === 1 && this.feedEl.firstElementChild.textContent.includes("Awaiting")) {
        this.feedEl.innerHTML = "";
      }
      this.feedEl.prepend(li);
      while (this.feedEl.children.length > this.maxItems) {
        this.feedEl.removeChild(this.feedEl.lastElementChild);
      }
      if (this.ticker) this.ticker.push(`[${tag.toUpperCase()}] ${msg}`);

      // Cadence pulse on the ALERTS tab — only when the tab is not currently active.
      const alertsTab = document.querySelector('.drawer-tab[data-tab="alerts"]');
      if (alertsTab && !alertsTab.classList.contains("is-active")) {
        alertsTab.classList.add("is-cadence");
        setTimeout(() => alertsTab.classList.remove("is-cadence"), 1400);
      }
    }

    process(frame) {
      const v = frame.threat_index;
      let band = "ok";
      if (v >= 70) band = "crit";
      else if (v >= 50) band = "warn";

      if (band !== this.lastBand) {
        if (band === "crit") {
          this._push({ tag: "crit", msg: `Threat index elevated to ${v.toFixed(1)} — global posture re-evaluated.` });
          this.audio.alertBeep();
        } else if (band === "warn") {
          this._push({ tag: "warn", msg: `Threat trending upward — index ${v.toFixed(1)}.` });
          this.audio.alertBeep();
        } else {
          this._push({ tag: "info", msg: `Threat index normalized at ${v.toFixed(1)}.` });
        }
        this.lastBand = band;
      }

      // Spike detection on selected domain metrics
      const watch = [
        { key: "solar_activity", label: "Solar activity spike" },
        { key: "seismic_activity", label: "Seismic event detected" },
        { key: "air_traffic_density", label: "Air traffic surge" },
      ];
      for (const w of watch) {
        const cur = frame.metrics[w.key];
        const prev = this.lastSpikes[w.key];
        if (Number.isFinite(prev) && cur - prev > 14) {
          this._push({
            tag: cur >= 70 ? "crit" : "warn",
            msg: `${w.label} — ${cur.toFixed(1)}.`,
          });
          if (cur >= 70) this.audio.alertBeep();
        }
        this.lastSpikes[w.key] = cur;
      }
    }
  }

  /* ============================== SYSTEM EVENT EMITTER ===================== */

  // Periodic synthetic mission-control system events. Every entry is clearly
  // sourced (TLM / NET / IMG / ADV / SYS) so the feed feels alive without
  // misrepresenting itself as real intercept.
  class SystemEventEmitter {
    constructor(alerts, ctx) {
      this.alerts = alerts;
      this.ctx = ctx;
      this.frameSeq = 0;
      // Real-only event templates: only events tied to actual system state.
      // Fake heartbeats removed since they did not reflect real measurements.
      this.templates = [
        { src: "TLM", msg: () => `Telemetry frame received · ${(this.ctx.frameCount ?? 0).toString().padStart(4, "0")}.` },
      ];
      this.i = 0;
      this.timer = null;
    }
    start() {
      const fire = () => {
        const t = this.templates[this.i % this.templates.length];
        this.i++;
        this.alerts.push({ tag: "info", source: t.src, msg: t.msg() });
      };
      // Frame counter heartbeat every 60s (slower to let real events dominate).
      setTimeout(fire, 10000);
      this.timer = setInterval(fire, 60000);
    }
  }

  /* ============================== RF SCANNER (SIM) ========================= */

  const RF_CHANNELS = [
    { freq: 118.100, label: "AIR BAND",     note: "TWR / APPROACH" },
    { freq: 162.550, label: "WEATHER",      note: "NOAA WX PUBLIC" },
    { freq: 144.390, label: "AMATEUR APRS", note: "PUBLIC PACKET" },
    { freq: 433.920, label: "ISM BAND",     note: "PUBLIC ISM" },
  ];

  class RFScanner {
    constructor({ line, area, cursor, freqEl, bandEl, sigEl, list, recorder }) {
      this.line = line;
      this.area = area;
      this.cursor = cursor;
      this.freqEl = freqEl;
      this.bandEl = bandEl;
      this.sigEl = sigEl;
      this.list = list;
      this.recorder = recorder;
      this.minF = 88.0;
      this.maxF = 470.0;
      this.cur = this.minF;
      this.dir = 1;
      this.samples = new Array(96).fill(15);
      this.t = 0;
      this.running = false;
      this._renderList();
    }

    _renderList() {
      this.list.innerHTML = "";
      this.itemEls = {};
      for (const ch of RF_CHANNELS) {
        const el = document.createElement("li");
        el.className = "rf-channel";
        el.innerHTML = `
          <span class="rf-channel__freq">${ch.freq.toFixed(3)} MHz</span>
          <span class="rf-channel__band">${ch.label}</span>
          <span class="rf-channel__note">${ch.note}</span>
          <span class="rf-channel__sig" data-sig>--%</span>
        `;
        this.list.appendChild(el);
        this.itemEls[ch.freq.toFixed(3)] = el;
      }
    }

    start() {
      if (this.running) return;
      this.running = true;
      let last = performance.now();
      const tick = (now) => {
        if (!this.running) return;
        const dt = (now - last) / 1000;
        last = now;
        this._step(dt);
        requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    }

    _step(dt) {
      // Sweep
      const sweep = 22; // MHz / sec
      this.cur += sweep * dt * this.dir;
      if (this.cur >= this.maxF) { this.cur = this.maxF; this.dir = -1; }
      if (this.cur <= this.minF) { this.cur = this.minF; this.dir = 1; }

      // Strength model
      let amp = 14 + Math.sin(this.t * 0.45) * 7 + (Math.random() - 0.5) * 9;
      let near = null, nearDist = Infinity;
      for (const ch of RF_CHANNELS) {
        const d = Math.abs(this.cur - ch.freq);
        if (d < nearDist) { nearDist = d; near = ch; }
        if (d < 0.8) {
          const boost = (1 - d / 0.8) * (62 + Math.random() * 16);
          amp += boost;
        }
      }
      amp = clamp(amp, 0, 100);

      this.samples.push(amp);
      this.samples.shift();
      this.t += dt * 10;

      // Render wave
      const W = 400, H = 60, n = this.samples.length;
      let pts = "";
      for (let i = 0; i < n; i++) {
        const x = (i / (n - 1)) * W;
        const y = H - (this.samples[i] / 100) * (H - 6) - 3;
        pts += (i ? " " : "") + x.toFixed(1) + "," + y.toFixed(1);
      }
      this.line.setAttribute("points", pts);
      this.area.setAttribute("points", `0,${H} ${pts} ${W},${H}`);

      const cursorX = ((this.cur - this.minF) / (this.maxF - this.minF)) * W;
      this.cursor.setAttribute("x1", cursorX.toFixed(1));
      this.cursor.setAttribute("x2", cursorX.toFixed(1));

      this.freqEl.textContent = this.cur.toFixed(3) + " MHz";
      this.bandEl.textContent = near ? near.label : "—";
      this.sigEl.textContent = amp.toFixed(0) + "%";

      // List highlight
      for (const ch of RF_CHANNELS) {
        const el = this.itemEls[ch.freq.toFixed(3)];
        const d = Math.abs(this.cur - ch.freq);
        const active = d < 1.6;
        el.classList.toggle("is-active", active);
        if (active) {
          el.querySelector("[data-sig]").textContent = amp.toFixed(0) + "%";
        }
      }

      // Recorder
      if (this.recorder) {
        if (amp > 62 && near && nearDist < 0.8) {
          this.recorder.feedSignal(amp, near, this.cur);
        } else {
          this.recorder.idle(amp);
        }
      }
    }
  }

  /* ============================== AUTO RECORDER (SIM) ====================== */

  class AutoRecorder {
    constructor({ dot, status, waveEl, line, list, exportBtn, printBtn }) {
      this.dot = dot;
      this.status = status;
      this.waveEl = waveEl;
      this.line = line;
      this.list = list;
      this.events = [];
      this.maxEvents = 64;
      this.recordingUntil = 0;
      this.lastEventAt = 0;
      this.eventCooldownMs = 5500;
      this.samples = new Array(96).fill(3);
      this._render();
      exportBtn.addEventListener("click", () => this.exportReport());
      printBtn .addEventListener("click", () => this.exportReport());
      this._tickStatus();
    }

    feedSignal(amp, channel, freq) {
      this._pushSample(amp);
      const now = performance.now();
      this.recordingUntil = now + 2800;
      if (now - this.lastEventAt > this.eventCooldownMs) {
        this._addEvent(amp, channel, freq);
        this.lastEventAt = now;
      }
    }

    idle(amp) { this._pushSample(amp * 0.45); }

    _pushSample(amp) {
      this.samples.push(clamp(amp, 0, 100));
      this.samples.shift();
      this._draw();
    }

    _draw() {
      const W = 400, H = 50, n = this.samples.length;
      let pts = "";
      for (let i = 0; i < n; i++) {
        const x = (i / (n - 1)) * W;
        const y = H - (this.samples[i] / 100) * (H - 4) - 2;
        pts += (i ? " " : "") + x.toFixed(1) + "," + y.toFixed(1);
      }
      this.line.setAttribute("points", pts);
    }

    _addEvent(amp, channel, freq) {
      const ts = new Date();
      const evt = {
        id: "ASR-" + Math.floor(1000 + Math.random() * 9000),
        timestamp: ts.toISOString(),
        time_utc: ts.toISOString().slice(11, 19),
        band: `${freq.toFixed(3)} MHz · ${channel.label}`,
        strength: amp,
      };
      this.events.unshift(evt);
      if (this.events.length > this.maxEvents) this.events.pop();
      this._render();
    }

    _render() {
      if (this.events.length === 0) {
        this.list.innerHTML = `
          <li class="rec-event">
            <span class="rec-event__time">--:--:--</span>
            <span class="rec-event__id">---</span>
            <span class="rec-event__band">Awaiting signal events</span>
            <span class="rec-event__sig">--%</span>
          </li>`;
        return;
      }
      this.list.innerHTML = this.events.slice(0, 6).map(e => `
        <li class="rec-event">
          <span class="rec-event__time">${e.time_utc}</span>
          <span class="rec-event__id">${e.id}</span>
          <span class="rec-event__band">${e.band}</span>
          <span class="rec-event__sig">${e.strength.toFixed(0)}%</span>
        </li>
      `).join("");
    }

    _tickStatus() {
      const update = () => {
        const isRec = performance.now() < this.recordingUntil;
        this.dot.classList.toggle("is-rec", isRec);
        this.waveEl.classList.toggle("is-rec", isRec);
        this.status.textContent = isRec ? "REC" : "STANDBY";
      };
      update();
      setInterval(update, 220);
    }

    exportReport() {
      const html = this._buildReportHTML();
      const w = window.open("", "_blank", "noopener,width=960,height=720");
      if (!w) {
        const blob = new Blob([html], { type: "text/html" });
        const url = URL.createObjectURL(blob);
        window.open(url, "_blank", "noopener");
        return;
      }
      w.document.open();
      w.document.write(html);
      w.document.close();
      setTimeout(() => {
        try { w.focus(); w.print(); } catch (e) {}
      }, 350);
    }

    _buildReportHTML() {
      const rows = this.events.map(e => `
        <tr>
          <td>${e.timestamp}</td>
          <td>${e.id}</td>
          <td>${e.band}</td>
          <td>${e.strength.toFixed(1)}%</td>
        </tr>
      `).join("");
      const body = rows || `<tr><td colspan="4" style="text-align:center;color:#7a96b2;padding:18pt;">No simulated events recorded yet.</td></tr>`;
      return `<!doctype html><html><head><meta charset="utf-8"><title>ASTROSCAN COMMAND // Auto-Recorder Report</title>
<style>
  :root { color-scheme: light; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue", Arial, sans-serif; color: #1b2734; padding: 28pt; background: #fff; }
  header { display: flex; justify-content: space-between; align-items: flex-end; padding-bottom: 10pt; border-bottom: 1px solid #cbd5df; }
  h1 { font-family: "Orbitron", "Inter", sans-serif; letter-spacing: 0.14em; font-size: 16pt; margin: 0 0 4pt; color: #0a2b40; }
  .sub { font-size: 9pt; color: #4e6d89; letter-spacing: 0.18em; text-transform: uppercase; }
  .badge { padding: 4pt 8pt; border: 1px solid #cbd5df; border-radius: 999px; font-size: 9pt; letter-spacing: 0.14em; color: #4e6d89; text-transform: uppercase; }
  table { width: 100%; border-collapse: collapse; font-size: 10pt; margin-top: 14pt; }
  th, td { padding: 7pt 8pt; border-bottom: 1px solid #e3e8ee; text-align: left; font-variant-numeric: tabular-nums; }
  th { background: #f2f5f8; font-weight: 600; letter-spacing: 0.10em; text-transform: uppercase; font-size: 9pt; color: #2d4761; }
  .disclaimer { margin-top: 24pt; padding: 12pt 14pt; border: 1px solid #cbd5df; background: #f7fafc; font-size: 9pt; color: #2d4761; }
  footer { margin-top: 22pt; font-size: 8pt; letter-spacing: 0.20em; text-transform: uppercase; color: #7a96b2; text-align: right; }
  @media print { body { padding: 14pt; } }
</style></head><body>
<header>
  <div>
    <h1>ASTROSCAN COMMAND // AUTO-RECORDER REPORT</h1>
    <div class="sub">Generated ${new Date().toISOString()} · Build 2.0.0</div>
  </div>
  <span class="badge">Mode · Simulation</span>
</header>
<table>
  <thead><tr><th>Timestamp (UTC)</th><th>Event ID</th><th>Detected Band</th><th>Signal Strength</th></tr></thead>
  <tbody>${body}</tbody>
</table>
<div class="disclaimer">Informational simulation only. Not valid for operational, legal, or official use.</div>
<footer>AstroScan Command V2 · Mission Control</footer>
</body></html>`;
    }
  }

  /* ============================== CLOCKS =================================== */

  function startClocks() {
    const utcEl = $("#clock-utc");
    const localEl = $("#clock-local");
    const tick = () => {
      const now = new Date();
      utcEl.textContent = fmtClock(now, "UTC");
      localEl.textContent = fmtClock(now, "LOCAL");
    };
    tick();
    setInterval(tick, 1000);
  }

  /* ============================== SIGNAL QUALITY =========================== */

  class SignalQuality {
    constructor() {
      this.cells = {
        confidence: { v: $("#sq-confidence"), b: $("#sq-confidence-bar") },
        integrity:  { v: $("#sq-integrity"),  b: $("#sq-integrity-bar") },
        coverage:   { v: $("#sq-coverage"),   b: $("#sq-coverage-bar") },
      };
      this.regions = ["nam", "atl", "eur", "asia", "arc"].map(k => ({ k, el: $(`#rg-${k}`) }));
      this._t0 = performance.now() / 1000;
    }

    update(frame) {
      if (!this.cells.confidence.v) return;
      const m = frame.metrics || {};
      const o = frame.orbital_status || {};

      const confidence = clamp(0.65 * (m.system_health ?? 96) + 0.35 * (m.visibility_score ?? 85), 0, 100);
      const integrity  = clamp(o.integrity ?? 97, 0, 100);
      // Coverage: slowly varying value derived from a low-frequency sine for realism.
      const t = performance.now() / 1000 - this._t0;
      const coverage   = clamp(89 + Math.sin(t / 27) * 4 + Math.sin(t / 11) * 1.5, 60, 100);

      this._set("confidence", confidence);
      this._set("integrity",  integrity);
      this._set("coverage",   coverage);

      // Region activity — drift the watch state based on combined load.
      const load = (frame.threat_index ?? 30) / 100;
      for (let i = 0; i < this.regions.length; i++) {
        const r = this.regions[i];
        if (!r.el) continue;
        const noise = (Math.sin(t / (4 + i)) + 1) * 0.5;
        const score = noise * 0.7 + load * 0.5;
        const state = score > 1.05 ? "hot" : score > 0.62 ? "watch" : "";
        if (state) r.el.dataset.state = state; else delete r.el.dataset.state;
      }
    }

    _set(key, v) {
      const c = this.cells[key];
      if (!c.v) return;
      c.v.textContent = v.toFixed(1) + "%";
      c.b.style.width = v.toFixed(1) + "%";
    }
  }

  /* ============================== POSTURE MONITOR ========================== */

  class PostureMonitor {
    constructor() {
      this.trendEl = $("#posture-trend");
      this.peakEl  = $("#posture-peak");
      this.watchEl = $("#posture-watch");
      this.sparkEl = $("#posture-spark-line");
      this.history = []; // {t: epochSec, v: threat}
    }

    update(frame) {
      if (!this.trendEl) return;
      const now = Date.now() / 1000;
      const v = frame.threat_index;
      this.history.push({ t: now, v });
      const horizon = 60 * 60; // 1h window
      while (this.history.length && now - this.history[0].t > horizon) {
        this.history.shift();
      }
      if (this.history.length > 90) this.history.shift();

      // Trend = current vs ~5 frames ago (~10s) for visible movement
      const ref = this.history[Math.max(0, this.history.length - 6)];
      const delta = v - ref.v;
      const sign = delta > 0.05 ? "+" : delta < -0.05 ? "−" : "·";
      this.trendEl.textContent = `${sign} ${Math.abs(delta).toFixed(1)}`;
      this.trendEl.dataset.dir = delta > 0.5 ? "up" : delta < -0.5 ? "down" : "";

      const peak = this.history.reduce((m, p) => Math.max(m, p.v), 0);
      this.peakEl.textContent = peak.toFixed(1);
      this.peakEl.dataset.dir = peak >= 70 ? "hot" : peak >= 50 ? "up" : "";

      const m = frame.metrics || {};
      let watch = 0;
      if (v >= 50) watch++;
      if ((m.solar_activity   || 0) >= 65) watch++;
      if ((m.seismic_activity || 0) >= 55) watch++;
      if ((m.air_traffic_density || 0) >= 75) watch++;
      this.watchEl.textContent = String(watch);
      this.watchEl.dataset.dir = watch >= 3 ? "hot" : watch >= 1 ? "up" : "";

      // Sparkline (last ~60 samples)
      if (this.sparkEl) {
        const slice = this.history.slice(-60);
        const W = 200, H = 28;
        let pts = "";
        for (let i = 0; i < slice.length; i++) {
          const x = (i / Math.max(1, slice.length - 1)) * W;
          const y = H - clamp(slice[i].v / 100, 0, 1) * (H - 3) - 1.5;
          pts += (i ? " " : "") + x.toFixed(1) + "," + y.toFixed(1);
        }
        this.sparkEl.setAttribute("points", pts);
      }
    }
  }

  /* ============================== TELEMETRY ROUTER ========================= */

  function bindFrame(frame, audio, alerts, ctx) {
    const m = frame.metrics || {};
    const o = frame.orbital_status || {};

    // Right panel — domain metrics
    renderMeter("air", m.air_traffic_density);
    renderMeter("maritime", m.maritime_density);
    renderMeter("solar", m.solar_activity);
    renderMeter("seismic", m.seismic_activity);

    if (ctx.solarMonitor) ctx.solarMonitor.setTarget(m.solar_activity);

    if (ctx.sharedCtx) {
      if (Number.isFinite(o.iss_altitude_km)) {
        ctx.sharedCtx.issAltitudeKm = o.iss_altitude_km;
      }
      ctx.sharedCtx.latestFrame = frame;
    }

    // Left panel — telemetry
    renderTelemetryMeter("weather", m.weather_score);
    renderTelemetryMeter("visibility", m.visibility_score);
    renderTelemetryMeter("health", m.system_health);

    // Orbital readouts
    const issVel = $("#t-iss-velocity");
    const issAlt = $("#t-iss-altitude");
    const orb = $("#t-orbital");

    const prev = ctx.prev || {};
    const realV = ctx.sharedCtx?.realIssVelocity;
    const realAlt = ctx.sharedCtx?.issAltitudeKm;
    const issVelocityTarget = Number.isFinite(realV)   ? realV   : o.iss_velocity_km_s;
    const issAltitudeTarget = Number.isFinite(realAlt) ? realAlt : o.iss_altitude_km;
    if (issVel) animateNumber(issVel, prev.iss_velocity ?? issVelocityTarget, issVelocityTarget, { digits: 3 });
    if (issAlt) animateNumber(issAlt, prev.iss_altitude ?? issAltitudeTarget, issAltitudeTarget, { digits: 2 });
    if (orb)    animateNumber(orb,    prev.orbital      ?? o.integrity,       o.integrity,       { digits: 2 });

    renderThreat(frame.threat_index);
    if (window.__acq && Number.isFinite(o.integrity)) window.__acq.setIntegrity(o.integrity);

    const linkChip = $(".status-chip[data-chip='link']");
    if (linkChip) linkChip.dataset.state = "ok";
    const linkVal = $("#chip-link");
    if (linkVal) linkVal.textContent = "LIVE";

    const stageRange = $("#stage-range");
    if (stageRange) stageRange.textContent = `${(o.iss_altitude_km || 0).toFixed(0)} KM`;

    ctx.frameCount = (ctx.frameCount || 0) + 1;
    const frameStr = ctx.frameCount.toString().padStart(4, "0");
    const metaFrame = $("#meta-frame");
    if (metaFrame) metaFrame.textContent = frameStr;
    const buildFrame = $("#build-frame");
    if (buildFrame) buildFrame.textContent = "f" + frameStr;

    // Real delivery latency: client receive time − server frame timestamp.
    // The frame carries `timestamp` (server-side ISO from datetime.now(timezone.utc)).
    // Sub-50 ms on localhost, 30-200 ms across the internet — premium range.
    // EMA smoothing prevents UI flicker; clamp to 0 protects against clock skew.
    const serverMs = frame.timestamp ? new Date(frame.timestamp).getTime() : 0;
    const rawLat   = serverMs ? Math.max(0, Date.now() - serverMs) : 0;
    ctx.smoothLatency = (ctx.smoothLatency !== undefined)
      ? Math.round(ctx.smoothLatency * 0.55 + rawLat * 0.45)
      : rawLat;
    const dt = ctx.smoothLatency;
    ctx.lastNowDt = dt;

    // Quality classification — drives color via CSS [data-quality] attribute.
    const quality = dt >= 250 ? "degraded" : dt >= 120 ? "stable" : "optimal";

    // Format: zero-padded 3-digit ms, monospace stable width.
    const dtStr = String(Math.min(dt, 999)).padStart(3, "0") + " ms";

    const metaLatency = $("#meta-latency");
    if (metaLatency) {
      metaLatency.textContent = dtStr;
      const metaItem = metaLatency.closest(".drawer__meta-item");
      if (metaItem) metaItem.dataset.quality = quality;
    }
    const buildLatency = $("#build-latency");
    if (buildLatency) {
      buildLatency.textContent = dtStr;
      buildLatency.dataset.quality = quality;
    }
    if (window.__system) window.__system.setLatency("ws", dt);
    if (window.__acq)    window.__acq.setUplink(dt, "LIVE");

    alerts.process(frame);

    ctx.prev = {
      iss_velocity: o.iss_velocity_km_s,
      iss_altitude: o.iss_altitude_km,
      orbital: o.integrity,
    };
  }

  /* ============================== SYSTEM INTEGRITY ========================= */

  // Honest, structured view of every data source the page touches.
  // Sources: 'imagery', 'night', 'tle', 'swx', 'ws'.
  // States:  'live' | 'cached' | 'loading' | 'error'.
  class SystemIntegrity {
    constructor() {
      this.toggle  = $("#system-toggle");
      this.panel   = $("#system-panel");
      this.demoBtn = $("#demo-narrative-btn");
      this.demoCb  = null;
      this.sources = {};
      const keys = ["imagery", "night", "tle", "swx", "ws"];
      for (const k of keys) {
        this.sources[k] = {
          item:  document.querySelector(`.src-item[data-key="${k}"]`),
          state: document.getElementById(`src-${k}-state`),
          age:   document.getElementById(`src-${k}-age`),
          lastSyncMs: 0,
          stateValue: "loading",
        };
      }
      // Imagery + Night Marble are bundled with the page itself.
      this.set("imagery", "live");
      this.set("night",   "live");

      this._bindPopover();
      this._tickAges();
    }

    _bindPopover() {
      const setOpen = (open) => {
        this.panel.classList.toggle("is-open", open);
        this.panel.hidden = !open;
        this.toggle.setAttribute("aria-expanded", String(open));
      };
      this.toggle.addEventListener("click", (e) => {
        e.stopPropagation();
        setOpen(!this.panel.classList.contains("is-open"));
      });
      document.addEventListener("pointerdown", (e) => {
        if (!this.panel.contains(e.target) && !this.toggle.contains(e.target)) setOpen(false);
      });
      document.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && this.panel.classList.contains("is-open")) {
          setOpen(false);
          this.toggle.focus();
        }
      });
      this.demoBtn.addEventListener("click", () => {
        setOpen(false);
        if (this.demoCb) this.demoCb();
      });
    }

    onDemoRequested(fn) { this.demoCb = fn; }

    set(key, state, label) {
      const s = this.sources[key];
      if (!s || !s.item) return;
      s.item.dataset.state = state;
      s.stateValue = state;
      if (label) s.state.textContent = label;
      else if (state === "live")    s.state.textContent = "Live";
      else if (state === "cached")  s.state.textContent = "Cached";
      else if (state === "error")   s.state.textContent = "Error";
      else                          s.state.textContent = "Loading";
      if (state === "live" || state === "cached") {
        s.lastSyncMs = Date.now();
        s.age.textContent = "just now";
      }
    }

    setLatency(key, ms) {
      const s = this.sources[key];
      if (!s || !s.age) return;
      s.lastSyncMs = Date.now();
      s.age.textContent = ms < 1000
        ? `${Math.round(ms)} ms`
        : `${(ms / 1000).toFixed(1)} s`;
    }

    _tickAges() {
      const fmt = (ms) => {
        if (!ms) return "—";
        const s = (Date.now() - ms) / 1000;
        if (s < 5)   return "just now";
        if (s < 60)  return `${Math.round(s)}s ago`;
        if (s < 3600) return `${Math.round(s / 60)}m ago`;
        return `${Math.round(s / 3600)}h ago`;
      };
      const update = () => {
        for (const k of Object.keys(this.sources)) {
          const s = this.sources[k];
          // Only refresh age for non-realtime sources; WS shows latency in ms.
          if (k === "ws") continue;
          if (s.lastSyncMs) s.age.textContent = fmt(s.lastSyncMs);
        }
      };
      update();
      setInterval(update, 1000);
    }
  }

  /* ============================== RUNTIME METRICS ========================== */

  class RuntimeMetrics {
    constructor() {
      this.fpsEl   = $("#run-fps");
      this.heapEl  = $("#run-heap");
      this.rttEl   = $("#run-rtt");
      this.cacheEl = $("#run-cache");
      this.modeEl  = $("#run-mode");
      this.cacheTsMs = 0; // freshest cache write across TLE/SWX
      this._frames = 0;
      this._lastSampleMs = performance.now();
      this._tick();
      this._sample();
    }
    _tick() {
      const loop = () => {
        this._frames++;
        requestAnimationFrame(loop);
      };
      requestAnimationFrame(loop);
    }
    _sample() {
      const update = () => {
        const now = performance.now();
        const dt = now - this._lastSampleMs;
        const fps = Math.max(0, Math.round((this._frames * 1000) / dt));
        this._frames = 0;
        this._lastSampleMs = now;
        if (this.fpsEl) this.fpsEl.textContent = String(fps);
        if (this.heapEl) {
          const pm = performance.memory;
          this.heapEl.textContent = pm
            ? `${(pm.usedJSHeapSize / 1048576).toFixed(1)} MB`
            : "n/a";
        }
        if (this.cacheEl && this.cacheTsMs) {
          const s = (Date.now() - this.cacheTsMs) / 1000;
          this.cacheEl.textContent = s < 60 ? `${Math.round(s)} s`
                                    : s < 3600 ? `${Math.round(s / 60)} m`
                                    : `${Math.round(s / 3600)} h`;
        }
        if (this.modeEl && window.__camera) {
          this.modeEl.textContent = window.__camera.activeMode || "command";
        }
      };
      update();
      setInterval(update, 1000);
    }
    setRtt(ms) { if (this.rttEl) this.rttEl.textContent = `${Math.round(ms)} ms`; }
    markCacheWrite() { this.cacheTsMs = Date.now(); }
  }

  /* ============================== SPECULATIVE MODE ========================= */

  // Optional clearly fictional layer. Body class drives a palette tint + ribbon.
  // Adds one amber dashed equatorial envelope entity labelled SPECULATIVE.
  class SpeculativeMode {
    constructor(viewer) {
      this.viewer = viewer;
      this.toggle = $("#speculative-toggle");
      this.state  = $("#speculative-state");
      this.entities = [];
      this.active = false;
      this._buildEntities();
      this.toggle.addEventListener("click", () => this._toggle());
    }
    _buildEntities() {
      // A purely speculative "projected risk envelope" ring at 1500 km.
      const positions = orbitPositions({ altitudeM: 1_500_000, inclinationDeg: 0, samples: 200 });
      const e = this.viewer.entities.add({
        polyline: {
          positions,
          width: 1.4,
          arcType: Cesium.ArcType.NONE,
          material: new Cesium.PolylineDashMaterialProperty({
            color: Cesium.Color.fromCssColorString("#f0b260").withAlpha(0.70),
            dashLength: 16,
          }),
        },
      });
      e.show = false;
      this.entities.push(e);

      const tilted = orbitPositions({ altitudeM: 1_500_000, inclinationDeg: 42, samples: 200 });
      const e2 = this.viewer.entities.add({
        polyline: {
          positions: tilted,
          width: 1.0,
          arcType: Cesium.ArcType.NONE,
          material: new Cesium.PolylineDashMaterialProperty({
            color: Cesium.Color.fromCssColorString("#f0b260").withAlpha(0.45),
            dashLength: 12,
          }),
        },
      });
      e2.show = false;
      this.entities.push(e2);
    }
    _toggle() {
      this.active = !this.active;
      document.body.classList.toggle("is-black-orbit", this.active);
      this.toggle.setAttribute("aria-pressed", String(this.active));
      this.state.textContent = this.active ? "On" : "Off";
      for (const e of this.entities) e.show = this.active;
    }
  }

  /* ============================== DEMO NARRATIVE =========================== */

  class DemoNarrative {
    constructor() {
      this.banner = $("#demo-banner");
      this.stepEl = $("#demo-banner-step");
      this.msgEl  = $("#demo-banner-msg");
      this.nextBtn = $("#demo-next");
      this.skipBtn = $("#demo-skip");
      this.steps = [
        { target: ".stage", msg: "Hero stage: NASA GIBS BlueMarble (day) + Black Marble VIIRS (night) blended by Cesium's sun-driven lighting model." },
        { target: "#iss-trust", msg: "ISS marker is propagated client-side via SGP4 from a live CelesTrak TLE (NORAD 25544). 30-min past trail + 90-min predicted arc." },
        { target: ".env-grid", msg: "Space Environment: Kp / F10.7 / X-ray flux fetched from NOAA SWPC every 5 min, with graceful fallback when unreachable." },
        { target: ".panel--right", msg: "Threat Intelligence currently runs on synthetic telemetry — every block is badged Simulation or Derived. Real ingest is on the roadmap." },
        { target: ".advisor", msg: "Mission Advisor is a rules engine, not AI. Messages are conditioned on the latest telemetry frame; the badge says so explicitly." },
        { target: "#intel-drawer", msg: "Intel drawer: alerts feed (live system events), RF Signal Simulator and Event Log clearly labelled SIM. Each tab has a SIM chip." },
      ];
      this.idx = 0;
      this.nextBtn.addEventListener("click", () => this._next());
      this.skipBtn.addEventListener("click", () => this._end());
      document.addEventListener("keydown", (e) => {
        if (!this.banner.classList.contains("is-open")) return;
        if (e.key === "Escape") this._end();
        if (e.key === "ArrowRight" || e.key === "Enter") this._next();
      });
    }
    start() {
      this.idx = 0;
      this.banner.hidden = false;
      requestAnimationFrame(() => this.banner.classList.add("is-open"));
      this._render();
    }
    _next() {
      this.idx++;
      if (this.idx >= this.steps.length) return this._end();
      this._render();
    }
    _render() {
      document.querySelectorAll(".is-demo-highlight").forEach((el) => el.classList.remove("is-demo-highlight"));
      const s = this.steps[this.idx];
      const target = document.querySelector(s.target);
      if (target) {
        target.classList.add("is-demo-highlight");
        try { target.scrollIntoView({ block: "center", behavior: "smooth" }); } catch (e) {}
      }
      this.stepEl.textContent = `${this.idx + 1} / ${this.steps.length}`;
      this.msgEl.textContent  = s.msg;
      this.nextBtn.textContent = (this.idx === this.steps.length - 1) ? "Finish" : "Next ›";
    }
    _end() {
      document.querySelectorAll(".is-demo-highlight").forEach((el) => el.classList.remove("is-demo-highlight"));
      this.banner.classList.remove("is-open");
      setTimeout(() => { this.banner.hidden = true; }, 280);
    }
  }

  /* ============================== AUDIO PANEL UI =========================== */

  function bindAudioPanel(audio) {
    const muteBtn    = $("#audio-mute");
    const moreBtn    = $("#audio-more");
    const panel      = $("#audio-panel");
    const volume     = $("#audio-volume");
    const balance    = $("#audio-balance");
    const profile    = $("#audio-profile");
    const volReadout = $("#audio-volume-readout");
    const balReadout = $("#audio-balance-readout");

    const setOpen = (open) => {
      panel.classList.toggle("is-open", open);
      panel.hidden = !open;
      moreBtn.setAttribute("aria-expanded", String(open));
    };

    const refreshMuteUI = () => {
      const muted = !audio.enabled;
      muteBtn.setAttribute("aria-pressed", String(!muted));
      const dot = muteBtn.querySelector(".ghost-btn__dot");
      if (dot) dot.style.background = muted ? "" : "var(--green)";
    };

    const labelBalance = (val) => val === 0 ? "C" : (val > 0 ? "R" : "L") + Math.abs(val);

    // One-click mute on the AUDIO button.
    muteBtn.addEventListener("click", async () => {
      await audio.ensure();
      audio.setMuted(audio.enabled);
      refreshMuteUI();
    });

    // ⋯ overflow opens the popover.
    moreBtn.addEventListener("click", async (e) => {
      e.stopPropagation();
      await audio.ensure();
      const willOpen = !panel.classList.contains("is-open");
      setOpen(willOpen);
      if (willOpen) {
        // Focus management: send keyboard focus to the volume slider.
        requestAnimationFrame(() => {
          const target = panel.querySelector("input, select, button");
          if (target) target.focus({ preventScroll: true });
        });
      }
    });
    document.addEventListener("pointerdown", (e) => {
      if (!panel.contains(e.target) && !moreBtn.contains(e.target)) setOpen(false);
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && panel.classList.contains("is-open")) {
        setOpen(false);
        moreBtn.focus();
      }
    });

    volume.addEventListener("input", async () => {
      await audio.ensure();
      const v = Number(volume.value);
      volReadout.textContent = String(v);
      audio.setVolume(v / 100);
    });
    balance.addEventListener("input", async () => {
      await audio.ensure();
      const v = Number(balance.value);
      balReadout.textContent = labelBalance(v);
      audio.setBalance(v / 100);
    });
    profile.addEventListener("change", async () => {
      await audio.ensure();
      audio.setProfile(profile.value);
    });

    volume.value = String(Math.round(audio.volume * 100));
    volReadout.textContent = volume.value;
    balance.value = String(Math.round(audio.balance * 100));
    balReadout.textContent = labelBalance(Number(balance.value));
    refreshMuteUI();
  }

  /* ============================== DEEP SPACE SIGINT (SIM) =================

     Premium scientific module: hydrogen line monitor (real 1420.405 MHz),
     solar radio weather (real F10.7 SFU from NOAA SWPC), pulsar watch
     (real PSR B0329+54 period 714 ms), FRB monitor (synthetic),
     SETI candidate (anomaly score bounded 8-15 — never claims detection),
     and a hero spectrogram of the 1400-1440 MHz H-band.

     Implementation discipline:
       - Spectrum polyline generated ONCE on construction. No re-render loop.
       - All visual life via CSS keyframes (heartbeat @ real 714ms, scan beam,
         transient flickers, dish rotation).
       - One setInterval at 4s to gently cycle the synthetic readouts.
       - Real F10.7 value injected by SpaceWeather class when NOAA data lands.
     ====================================================================== */

  class SigintModule {
    constructor() {
      this.trace   = $("#sigint-spectrum-trace");
      this.area    = $("#sigint-spectrum-area");
      this.peakEl  = $("#sigint-peak");
      this.h1Conf  = $("#sigint-h1-conf");
      this.h1Bar   = $("#sigint-h1-bar");
      this.seti    = $("#sigint-seti-score");
      this.setiBar = $("#sigint-seti-bar");
      this.frbCount  = $("#sigint-frb-count");
      this.frbStatus = $("#sigint-frb-status");
      this.frbTile   = $('.sigint-tile[data-tile="frb"]');
      this.solarFlux = $("#sigint-solar-flux");
      this._cycleN = 0;
      this._buildSpectrum();
      this._cycle();
      this._timer = setInterval(() => this._cycle(), 4000);
    }

    // Generate a static H-band spectrum: noise floor + Gaussian peak at the
    // hydrogen line (1420.405 MHz, viewBox x ≈ 204 inside 1400-1440 MHz span).
    _buildSpectrum() {
      if (!this.trace || !this.area) return;
      const W = 400, H = 100, NOISE_Y = 74, PEAK_X = 204, PEAK_SIG = 4.5, PEAK_AMP = 42;
      const points = [];
      for (let i = 0; i <= 90; i++) {
        const x = (i / 90) * W;
        const noise = (Math.random() - 0.5) * 9 + Math.sin(i * 0.65) * 2.5;
        const dx = (x - PEAK_X) / PEAK_SIG;
        const peak = PEAK_AMP * Math.exp(-(dx * dx));
        const y = clamp(NOISE_Y - peak + noise, 4, H - 4);
        points.push(`${x.toFixed(1)},${y.toFixed(1)}`);
      }
      const traceStr = points.join(" ");
      this.trace.setAttribute("points", traceStr);
      this.area.setAttribute("points", `0,${H} ${traceStr} ${W},${H}`);
    }

    // Low-frequency state cycle — believable drift without spam.
    _cycle() {
      this._cycleN += 1;

      // SETI anomaly score wanders 8-15 (background). Never crosses detection.
      const score = 8 + Math.random() * 7;
      if (this.seti)    this.seti.textContent = score.toFixed(1);
      if (this.setiBar) this.setiBar.style.width = (score * 1.6).toFixed(1) + "%";

      // Hydrogen line confidence drifts 92-98%.
      const h1 = 92 + Math.random() * 6;
      if (this.h1Conf) this.h1Conf.textContent = h1.toFixed(0) + "%";
      if (this.h1Bar)  this.h1Bar.style.width  = h1.toFixed(1) + "%";

      // Spectrum peak readout (dBm) jiggles ±0.8 dB around -72.4.
      if (this.peakEl) {
        const peak = -72.4 + (Math.random() - 0.5) * 1.6;
        this.peakEl.textContent = `${peak.toFixed(1)} dBm`;
      }

      // FRB rarely flickers to "1 / 24H · TRANSIENT CANDIDATE" for ~8s. ~3% per cycle.
      if (this.frbTile && this.frbCount && this.frbStatus) {
        const now = Date.now();
        if (this._transientUntil && now < this._transientUntil) {
          // hold transient state
        } else if (this._transientUntil && now >= this._transientUntil) {
          this.frbCount.textContent = "0 / 24H";
          this.frbStatus.textContent = "NO TRANSIENT";
          this.frbTile.dataset.state = "nominal";
          this._transientUntil = 0;
        } else if (Math.random() < 0.03) {
          this.frbCount.textContent = "1 / 24H";
          this.frbStatus.textContent = "TRANSIENT CANDIDATE";
          this.frbTile.dataset.state = "transient";
          this._transientUntil = now + 8000;
        }
      }
    }

    // Real F10.7 SFU value from NOAA SWPC proxy. Pushed by SpaceWeather class.
    setSolarFlux(sfu) {
      if (!this.solarFlux) return;
      if (Number.isFinite(sfu)) this.solarFlux.textContent = `${sfu.toFixed(0)} SFU`;
    }
  }

  /* ============================== INTEL DRAWER ============================ */

  function bindIntelDrawer() {
    const drawer = $("#intel-drawer");
    const toggle = $("#drawer-toggle");
    const tabs   = $$(".drawer-tab", drawer);
    const panels = $$(".drawer-panel", drawer);

    const setTab = (name) => {
      for (const t of tabs) {
        const active = t.dataset.tab === name;
        t.classList.toggle("is-active", active);
        t.setAttribute("aria-selected", String(active));
      }
      for (const p of panels) {
        const active = p.dataset.panel === name;
        p.classList.toggle("is-active", active);
        p.hidden = !active;
      }
      drawer.dataset.activeTab = name;
    };
    for (const t of tabs) t.addEventListener("click", () => setTab(t.dataset.tab));

    toggle.addEventListener("click", () => {
      const collapsed = drawer.classList.toggle("is-collapsed");
      toggle.setAttribute("aria-expanded", String(!collapsed));
    });
  }

  /* ============================== MAIN ===================================== */

  async function main() {
    startClocks();

    // 1. Boot animation
    await runBootSequence();
    await exitBoot();

    // 2. System Integrity + Demo Narrative — must exist before async sources resolve.
    const system = new SystemIntegrity();
    window.__system = system;
    const demo = new DemoNarrative();
    system.onDemoRequested(() => demo.start());

    // 3. Cesium (shared context for ISS altitude + latest telemetry frame)
    const sharedCtx = { issAltitudeKm: 408, latestFrame: null, realIssVelocity: null };
    const { viewer, syntheticISS, auxOrbits } = initCesium(sharedCtx);

    // Runtime observability + speculative mode (depend on Cesium being initialised).
    const runtime = new RuntimeMetrics();
    window.__runtime = runtime;
    const speculative = new SpeculativeMode(viewer);

    // Acquisition status (derived from real data plane).
    const acq = new AcquisitionStatus();
    window.__acq = acq;

    // 3a. Camera mode pills — globe stays look-at-origin in every mode.
    document.querySelectorAll(".mode-pill").forEach((p) => {
      p.addEventListener("click", () => {
        const mode = p.dataset.mode;
        if (window.__setCameraMode) window.__setCameraMode(mode);
        document.querySelectorAll(".mode-pill").forEach((q) =>
          q.setAttribute("aria-selected", String(q.dataset.mode === mode))
        );
      });
    });

    // 3b. Aux orbits toggle (default OFF).
    const auxToggle = $("#aux-orbits-toggle");
    if (auxToggle) {
      auxToggle.addEventListener("click", () => {
        const on = auxToggle.getAttribute("aria-pressed") === "true";
        auxToggle.setAttribute("aria-pressed", String(!on));
        for (const e of auxOrbits) e.show = !on;
      });
    }

    // 2b. Upgrade to real-world SGP4 propagation from CelesTrak (non-blocking).
    upgradeToRealISS(viewer, sharedCtx)
      .then((real) => { if (real) syntheticISS.hide(); })
      .catch((e) => console.warn("[ASTROSCAN] real-ISS upgrade unavailable", e));

    // 3. Audio engine — unlocked on first user gesture
    const audio = new CommandAudio();
    const unlockAudio = async () => {
      await audio.ensure();
      window.removeEventListener("pointerdown", unlockAudio);
      window.removeEventListener("keydown", unlockAudio);
    };
    window.addEventListener("pointerdown", unlockAudio, { once: true });
    window.addEventListener("keydown", unlockAudio, { once: true });

    bindAudioPanel(audio);
    bindIntelDrawer();

    // 4. Mission advisor — contextual on latest telemetry frame
    const advisor = new AIConsole($("#ai-msg"), () => sharedCtx.latestFrame);
    advisor.start();

    // 5. Alerts
    const alerts = new AlertManager($("#alert-feed"), null, audio);
    window.__alerts = alerts;

    // 6. Solar activity micro-visualization
    const solarMonitor = new SolarMonitor({
      waveEl: $("#solar-wave"),
      areaEl: $("#solar-area"),
      headEl: $("#solar-head"),
      fluxEl: $("#solar-flux"),
      bandEl: $("#solar-band"),
    });
    solarMonitor.start();

    // 7. AutoRecorder/RFScanner stubs — RF/SIGINT panels removed in v2.6 honesty cleanup.
    // Stubs prevent crashes from any remaining internal calls (scanner.feedSignal etc).
    const recorder = {
      feedSignal: () => {},
      idle: () => {},
      _render: () => {},
      _addEvent: () => {},
      exportReport: () => {},
    };
    const scanner = {
      feedTelemetry: () => {},
      tick: () => {},
      _render: () => {},
      recorder: recorder,
      start: () => {},
      stop: () => {},
    };
    scanner.start();

    // 8. WebSocket telemetry context
    // ─── AirTrafficLive : fetch /api/air-traffic every 60s, override WS synthetic value ───
    class AirTrafficLive {
      constructor() {
        this.intervalId = null;
        this.lastSource = null;
      }
      async fetchOnce() {
        try {
          const r = await fetch(`${API_BASE}/api/air-traffic`, { credentials: "same-origin" });
          if (!r.ok) throw new Error(`http ${r.status}`);
          const data = await r.json();
          if (data && typeof data.density_pct === "number" && data.live === true) {
            LIVE_OVERRIDES.air_traffic_density = data.density_pct;
            LIVE_OVERRIDES.air_traffic_meta = {
              source: data.source,
              total: data.total_aircraft,
              in_flight: data.in_flight,
              on_ground: data.on_ground,
              fetched: data.fetched,
            };
            if (this.lastSource !== "live") {
              console.log("[ASTROSCAN] Air traffic LIVE engaged · " + data.total_aircraft + " aircraft worldwide · " + data.density_pct.toFixed(1) + "%");
              this.lastSource = "live";
            }
          } else {
            // Upstream returned fallback — drop the override so synthetic resumes
            LIVE_OVERRIDES.air_traffic_density = null;
            LIVE_OVERRIDES.air_traffic_meta = null;
            if (this.lastSource !== "fallback") {
              console.warn("[ASTROSCAN] Air traffic upstream in fallback, synthetic resumed");
              this.lastSource = "fallback";
            }
          }
        } catch (e) {
          // Network error — drop override, synthetic resumes
          LIVE_OVERRIDES.air_traffic_density = null;
          LIVE_OVERRIDES.air_traffic_meta = null;
          if (this.lastSource !== "error") {
            console.warn("[ASTROSCAN] Air traffic fetch failed:", e.message);
            this.lastSource = "error";
          }
        }
      }
      start() {
        this.fetchOnce();
        this.intervalId = setInterval(() => this.fetchOnce(), 60000);
      }
      stop() {
        if (this.intervalId) { clearInterval(this.intervalId); this.intervalId = null; }
      }
    }
    const airTrafficLive = new AirTrafficLive();
    airTrafficLive.start();

    // ─── SeismicLive : fetch /api/seismic every 120s, override WS synthetic value ───
    class SeismicLive {
      constructor() {
        this.intervalId = null;
        this.lastSource = null;
        this.lastTopMag = 0;
      }
      async fetchOnce() {
        try {
          const r = await fetch(`${API_BASE}/api/seismic`, { credentials: "same-origin" });
          if (!r.ok) throw new Error(`http ${r.status}`);
          const data = await r.json();
          if (data && typeof data.score === "number" && data.live === true) {
            LIVE_OVERRIDES.seismic_activity = data.score;
            LIVE_OVERRIDES.seismic_meta = {
              source: data.source,
              total_events_24h: data.total_events_24h,
              significant_events_24h: data.significant_events_24h,
              magnitude_distribution: data.magnitude_distribution,
              tsunami_warnings: data.tsunami_warnings,
              top_events: data.top_events,
              fetched: data.fetched,
            };
            if (this.lastSource !== "live") {
              const topMag = data.top_events && data.top_events[0] ? data.top_events[0].mag : 0;
              const topPlace = data.top_events && data.top_events[0] ? data.top_events[0].place : "—";
              console.log("[ASTROSCAN] Seismic LIVE engaged · " + data.total_events_24h + " events/24h · score " + data.score.toFixed(1) + "/100 · top M" + topMag + " " + topPlace);
              this.lastSource = "live";
              this.lastTopMag = topMag;
            }
          } else {
            LIVE_OVERRIDES.seismic_activity = null;
            LIVE_OVERRIDES.seismic_meta = null;
            if (this.lastSource !== "fallback") {
              console.warn("[ASTROSCAN] Seismic upstream in fallback, synthetic resumed");
              this.lastSource = "fallback";
            }
          }
        } catch (e) {
          LIVE_OVERRIDES.seismic_activity = null;
          LIVE_OVERRIDES.seismic_meta = null;
          if (this.lastSource !== "error") {
            console.warn("[ASTROSCAN] Seismic fetch failed:", e.message);
            this.lastSource = "error";
          }
        }
      }
      start() {
        this.fetchOnce();
        this.intervalId = setInterval(() => this.fetchOnce(), 120000);
      }
      stop() {
        if (this.intervalId) { clearInterval(this.intervalId); this.intervalId = null; }
      }
    }
    const seismicLive = new SeismicLive();
    seismicLive.start();

    // ─── AdvisorLive : NOAA SWPC alerts → Mission Advisor + Event Log ───
    class AdvisorLive {
      constructor() {
        this.intervalId = null;
        this.lastSource = null;
      }
      async fetchOnce() {
        try {
          const url = API_BASE + "/api/space-alerts";
          const r = await fetch(url, { credentials: "same-origin" });
          if (!r.ok) throw new Error("http " + r.status);
          const data = await r.json();
          if (data && data.live === true) {
            LIVE_OVERRIDES.advisor_message = data.advisor;
            LIVE_OVERRIDES.advisor_severity = data.severity;
            LIVE_OVERRIDES.advisor_category = data.category;
            LIVE_OVERRIDES.advisor_log = data.log || [];
            LIVE_OVERRIDES.advisor_meta = {
              source: data.source,
              active_alerts_24h: data.active_alerts_24h,
              fetched: data.fetched,
            };
            if (this.lastSource !== "live") {
              console.log("[ASTROSCAN] Advisor LIVE engaged · " + (data.active_alerts_24h || 0) + " alerts/24h · " + data.severity + " · " + data.advisor);
              this.lastSource = "live";
            }
            // DOM override no longer needed — _pick() now uses LIVE_OVERRIDES directly
            const advisorEl = document.getElementById("ai-msg");
            if (advisorEl) {
              advisorEl.setAttribute("data-severity", data.severity);
              advisorEl.setAttribute("data-live", "true");
            }
          } else {
            LIVE_OVERRIDES.advisor_message = null;
            LIVE_OVERRIDES.advisor_severity = null;
            LIVE_OVERRIDES.advisor_category = null;
            LIVE_OVERRIDES.advisor_log = null;
            LIVE_OVERRIDES.advisor_meta = null;
            if (this.lastSource !== "fallback") {
              console.warn("[ASTROSCAN] Advisor upstream in fallback");
              this.lastSource = "fallback";
            }
          }
        } catch (e) {
          if (this.lastSource !== "error") {
            console.warn("[ASTROSCAN] Advisor fetch failed:", e.message);
            this.lastSource = "error";
          }
        }
      }
      start() {
        this.fetchOnce();
        this.intervalId = setInterval(() => this.fetchOnce(), 300000);
      }
      stop() {
        if (this.intervalId) { clearInterval(this.intervalId); this.intervalId = null; }
      }
    }
    const advisorLive = new AdvisorLive();
    advisorLive.start();

    // ─── TleAgeMonitor : fetch /api/tle/iss every 5min, computes TLE age in hours ───
    class TleAgeMonitor {
      constructor() {
        this.intervalId = null;
        this.lastAge = null;
      }
      async fetchOnce() {
        try {
          const url = API_BASE + "/api/tle/iss";
          const r = await fetch(url, { credentials: "same-origin" });
          if (!r.ok) throw new Error("http " + r.status);
          const data = await r.json();
          if (data && data.line1 && data.live === true) {
            // Parse epoch from TLE line1: chars 18-32 (year YY + day-of-year DDD.dddddd)
            const yearStr = data.line1.substring(18, 20);
            const dayStr = data.line1.substring(20, 32);
            const year = 2000 + parseInt(yearStr, 10);
            const day = parseFloat(dayStr);
            // Convert to JS Date
            const epoch = new Date(Date.UTC(year, 0, 1) + (day - 1) * 86400000);
            const ageMs = Date.now() - epoch.getTime();
            const ageHours = ageMs / 3600000;
            LIVE_OVERRIDES.tle_age_hours = ageHours;
            if (this.lastAge === null) {
              console.log("[ASTROSCAN] TLE age monitor active · epoch " + epoch.toISOString() + " · " + ageHours.toFixed(1) + "h ago");
              this.lastAge = ageHours;
            }
          } else {
            LIVE_OVERRIDES.tle_age_hours = null;
          }
        } catch (e) {
          if (this.lastAge !== null) {
            console.warn("[ASTROSCAN] TLE age monitor fetch failed:", e.message);
            this.lastAge = null;
          }
        }
      }
      start() {
        this.fetchOnce();
        this.intervalId = setInterval(() => this.fetchOnce(), 300000); // 5 min
      }
    }
    const tleAgeMonitor = new TleAgeMonitor();
    tleAgeMonitor.start();

    // ─── RealEventStream : push real USGS earthquakes + NOAA alerts into event log ───
    class RealEventStream {
      constructor() {
        this.intervalId = null;
        this.seenUsgs = new Set();
        this.seenNoaa = new Set();
        this.bootDelay = 8000;
      }
      pushEvent(source, msg, tag) {
        if (typeof window.__alerts !== "undefined" && window.__alerts.push) {
          window.__alerts.push({ tag: tag || "info", source: source, msg: msg });
        }
      }
      async fetchUsgs() {
        try {
          const meta = LIVE_OVERRIDES.seismic_meta;
          if (!meta || !meta.top_events || meta.top_events.length === 0) return;
          // Push only M5+ events not yet seen
          for (const ev of meta.top_events) {
            const key = ev.time + "_" + ev.mag;
            if (this.seenUsgs.has(key)) continue;
            if (ev.mag < 5.0) continue;
            this.seenUsgs.add(key);
            const tag = ev.tsunami ? "warn" : (ev.mag >= 6.0 ? "warn" : "info");
            const tsunamiTag = ev.tsunami ? " · TSUNAMI WATCH" : "";
            const msg = "M" + ev.mag.toFixed(1) + " earthquake · " + ev.place + tsunamiTag;
            this.pushEvent("USGS", msg, tag);
          }
        } catch (e) { /* silent */ }
      }
      async fetchNoaa() {
        try {
          const log = LIVE_OVERRIDES.advisor_log;
          if (!Array.isArray(log) || log.length === 0) return;
          for (const a of log) {
            if (!a || !a.iso) continue;
            if (this.seenNoaa.has(a.iso)) continue;
            const sev = a.severity || "info";
            const cat = a.category || "other";
            // Skip info-level noise except solar flares and radiation storms
            if (sev === "info" && cat !== "solar_flare" && cat !== "radiation_storm") continue;
            this.seenNoaa.add(a.iso);
            const tag = (sev === "severe" || sev === "strong") ? "warn" : "info";
            this.pushEvent("NOAA", a.message || ("Alert " + a.product_id), tag);
          }
        } catch (e) { /* silent */ }
      }
      async tick() {
        await this.fetchUsgs();
        await this.fetchNoaa();
      }
      start() {
        setTimeout(() => { this.tick(); }, this.bootDelay);
        this.intervalId = setInterval(() => this.tick(), 300000);
      }
    }
    const realEventStream = new RealEventStream();
    realEventStream.start();

    const ctx = { frameCount: 0, solarMonitor, sharedCtx };

    // 10. System event emitter — populates ALERTS tab with periodic notices.
    const systemEvents = new SystemEventEmitter(alerts, ctx);
    systemEvents.start();

    // 11. Space weather: live Kp / F10.7 / X-ray from NOAA SWPC (cached 5 min).
    const spaceWeather = new SpaceWeather();
    spaceWeather.start().catch((e) => console.warn("[ASTROSCAN] space-weather init failed", e));

    // 12. Deep Space SIGINT — astrophysical radio observation laboratory (SIM).
    const sigint = new SigintModule();
    window.__sigint = sigint;
    const client = new TelemetryClient(
      WS_PATH,
      (frame) => bindFrame(frame, audio, alerts, ctx),
      (status) => {
        const chip = $(".status-chip[data-chip='link']");
        const valueEl = $("#chip-link");
        const map = {
          CONNECTING: { state: "warn", label: "SYNCING",  sys: "loading", sysLabel: "Connecting" },
          LIVE:       { state: "ok",   label: "LIVE",     sys: "live",    sysLabel: "Live · WS" },
          DEGRADED:   { state: "warn", label: "DEGRADED", sys: "cached",  sysLabel: "Degraded" },
          OFFLINE:    { state: "crit", label: "OFFLINE",  sys: "error",   sysLabel: "Offline" },
        };
        const cfg = map[status] || map.CONNECTING;
        if (chip)    chip.dataset.state = cfg.state === "ok" ? "ok" : cfg.state;
        if (valueEl) valueEl.textContent = cfg.label;
        if (window.__system) window.__system.set("ws", cfg.sys, cfg.sysLabel);
        if (window.__acq)    window.__acq.setUplink(ctx.lastNowDt || 0, status);

        // Push a NET event only on transitions (not on every status callback)
        if (ctx.lastWsStatus && ctx.lastWsStatus !== status && window.__alerts) {
          const msg = (status === "LIVE")     ? "WebSocket reconnected · stream live."
                    : (status === "OFFLINE")  ? "WebSocket offline · awaiting reconnect."
                    : (status === "DEGRADED") ? "WebSocket degraded · backoff engaged."
                    : null;
          if (msg) window.__alerts.push({ tag: status === "OFFLINE" ? "warn" : "info", source: "NET", msg });
        }
        ctx.lastWsStatus = status;
      }
    );
    client.connect();
  }

  document.addEventListener("DOMContentLoaded", () => {
    main().catch((err) => console.error("[ASTROSCAN] fatal", err));
  });
})();
