/**
 * Orbital core — fonctions de calcul pures (Next Pass, helpers).
 * Doit être chargé AVANT orbital_map_engine.js.
 */
(function () {
  "use strict";

  if (typeof Cesium === "undefined" || typeof satellite === "undefined") {
    window.OrbitalCore = window.OrbitalCore || {};
    return;
  }
  var __debugComputeElevationCalls = 0;

  function eciToEcf(positionEci, gmst) {
    if (typeof satellite.eciToEcf === "function") {
      return satellite.eciToEcf(positionEci, gmst);
    }
    var c = Math.cos(gmst);
    var s = Math.sin(gmst);
    var p = positionEci;
    return { x: p.x * c + p.y * s, y: -p.x * s + p.y * c, z: p.z };
  }

  function lookAnglesFromObserver(observerGeodeticRad, positionEcf) {
    var lat = observerGeodeticRad.latitude;
    var lon = observerGeodeticRad.longitude;
    
    var a = 6378.137; var h = (observerGeodeticRad.height || 0) / 1000;
    var e2 = 0.00669437999014;
    var sinLat = Math.sin(lat);
    var cosLat = Math.cos(lat);
    var sinLon = Math.sin(lon);
    var cosLon = Math.cos(lon);
    var N = a / Math.sqrt(1 - e2 * sinLat * sinLat);
    var ox = (N + h) * cosLat * cosLon;
    var oy = (N + h) * cosLat * sinLon;
    var oz = (N * (1 - e2) + h) * sinLat;
    var x = positionEcf.x - ox;
    var y = positionEcf.y - oy;
    var z = positionEcf.z - oz;
    var range = Math.sqrt(x * x + y * y + z * z);
    if (!range || range < 1) return { elevation: -90, azimuth: 0 };
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

  function computeElevationAtTime(sat, observerGeodetic, when) {
    try {
      if (!sat || !sat.satrec || !when) return null;
      var pv = satellite.propagate(sat.satrec, when);
      if (!pv || !pv.position) return null;
      var gmst = satellite.gstime(when);
      var ecf = eciToEcf(pv.position, gmst);
      var look = lookAnglesFromObserver(observerGeodetic, ecf);
      if (__debugComputeElevationCalls < 3) {
        __debugComputeElevationCalls += 1;
        try {
          console.log(
            "SGP4 result:",
            JSON.stringify(pv),
            "gmst:",
            gmst,
            "ecf:",
            JSON.stringify(ecf),
            "look:",
            JSON.stringify(look)
          );
        } catch (eDbg) {}
      }
      if (!look || typeof look.elevation !== "number" || isNaN(look.elevation)) return null;
      return look.elevation;
    } catch (e) {
      return null;
    }
  }

  function findCrossingTime(sat, observerGeodetic, startTime, endTime, thresholdDeg, direction, stepSeconds) {
    try {
      if (!sat || !sat.satrec || !startTime || !endTime) return null;
      var stepMs = (stepSeconds || 10) * 1000;
      var startMs = startTime.getTime();
      var endMs = endTime.getTime();
      var prevEl = null;
      for (var t = startMs; t <= endMs; t += stepMs) {
        var when = new Date(t);
        var el = computeElevationAtTime(sat, observerGeodetic, when);
        if (el == null) continue;
        if (prevEl == null) {
          prevEl = el;
          continue;
        }
        if (direction === "rise") {
          if (prevEl <= thresholdDeg && el > thresholdDeg) {
            return when;
          }
        } else if (direction === "set") {
          if (prevEl >= thresholdDeg && el < thresholdDeg) {
            return when;
          }
        }
        prevEl = el;
      }
      return null;
    } catch (e) {
      return null;
    }
  }

  /**
   * Calcule le prochain passage au-dessus d'un observateur.
   * Stratégie en 2 phases : balayage large puis raffinement local.
   * Retourne { riseTime, endTime, durationMinutes, peakElevation, peakTime } ou null.
   */
  function _normalizeAngleToRadians(value) {
    if (typeof value !== "number" || !isFinite(value)) return NaN;
    // If already in radians, keep it; otherwise convert from degrees.
    if (Math.abs(value) <= (Math.PI * 2 + 0.01)) return value;
    return Cesium.Math.toRadians(value);
  }

  function computeNextPass(sat, observerLat, observerLon, observerHeight, windowMinutesArg, options) {
    try {
      if (!sat || !sat.satrec || isNaN(observerLat) || isNaN(observerLon)) return null;
      var now = new Date();
      var opts = options && typeof options === "object" ? options : {};
      var windowMinutes = isFinite(windowMinutesArg) ? Number(windowMinutesArg) : 240;
      if (!isFinite(windowMinutes) || windowMinutes < 15) windowMinutes = 240;
      var coarseStepSeconds = 60;
      var fineStepSeconds = 10;
      var windowMs = windowMinutes * 60 * 1000;
      var latRad = _normalizeAngleToRadians(observerLat);
      var lonRad = _normalizeAngleToRadians(observerLon);
      if (!isFinite(latRad) || !isFinite(lonRad)) return null;
      var passThresholdDeg = isFinite(opts.minElevationDeg)
        ? Number(opts.minElevationDeg)
        : (isFinite(sat.minPassElevationDeg) ? Number(sat.minPassElevationDeg) : 10);
      var obsGd = {
        latitude: latRad,
        longitude: lonRad,
        height: isFinite(observerHeight) ? Number(observerHeight) : (sat.observerHeight || 0)
      };
      var threshold = Math.max(0, Math.min(20, passThresholdDeg));

      var inPass = false;
      var riseApprox = null;
      var endApprox = null;
      var t;

      for (t = 0; t <= windowMs; t += coarseStepSeconds * 1000) {
        var when = new Date(now.getTime() + t);
        var el = computeElevationAtTime(sat, obsGd, when);
        if (el == null) continue;
        if (!inPass && el > threshold) {
          inPass = true;
          riseApprox = new Date(when.getTime());
        } else if (inPass && el < threshold) {
          endApprox = new Date(when.getTime());
          break;
        }
      }

      if (!riseApprox) return null;
      if (!endApprox) {
        endApprox = new Date(now.getTime() + windowMs);
      }

      var riseStart = new Date(riseApprox.getTime() - 120 * 1000);
      var riseEnd = new Date(riseApprox.getTime() + 120 * 1000);
      if (riseStart < now) riseStart = new Date(now.getTime());
      var refinedRise = findCrossingTime(sat, obsGd, riseStart, riseEnd, threshold, "rise", fineStepSeconds) || riseApprox;

      var endStart = new Date(endApprox.getTime() - 120 * 1000);
      var endEnd = new Date(endApprox.getTime() + 120 * 1000);
      var refinedEnd = findCrossingTime(sat, obsGd, endStart, endEnd, threshold, "set", fineStepSeconds) || endApprox;

      if (refinedEnd <= refinedRise) {
        refinedEnd = new Date(refinedRise.getTime() + 60 * 1000);
      }

      var peakElevation = -90;
      var peakTime = refinedRise;
      var startMs = refinedRise.getTime();
      var endMs = refinedEnd.getTime();
      for (t = startMs; t <= endMs; t += fineStepSeconds * 1000) {
        var whenPeak = new Date(t);
        var elPeak = computeElevationAtTime(sat, obsGd, whenPeak);
        if (elPeak == null) continue;
        if (elPeak > peakElevation) {
          peakElevation = elPeak;
          peakTime = new Date(whenPeak.getTime());
        }
      }

      if (!isFinite(peakElevation)) peakElevation = 0;
      peakElevation = Math.max(0, Math.min(90, peakElevation));
      var peakElevationRounded = Math.round(peakElevation);

      var durationMinutes = Math.max(0, (refinedEnd.getTime() - refinedRise.getTime()) / 60000);
      return {
        riseTime: refinedRise,
        endTime: refinedEnd,
        durationMinutes: durationMinutes,
        peakElevation: peakElevationRounded,
        peakTime: peakTime
      };
    } catch (e) {
      return null;
    }
  }

  /**
   * Score simple pour \"prioriser\" un satellite.
   * - +50 si visible
   * - +30 si élévation > 45°
   * - +20 si durée de prochain passage > 5 min (si fournie)
   * - +10 si proche de l'observateur (distance angulaire < ~10°)
   */
  function computeSatelliteScore(sat, observerLat, observerLon, passDurationMinutes) {
    try {
      if (!sat) return 0;
      var score = 0;
      if (sat.visible) score += 50;
      if (typeof sat.elevation === "number" && sat.elevation > 45) score += 30;
      if (typeof passDurationMinutes === "number" && passDurationMinutes > 5) score += 20;
      if (typeof sat.lat === "number" && typeof sat.lon === "number" &&
          typeof observerLat === "number" && typeof observerLon === "number") {
        var dLat = Math.abs(sat.lat - observerLat);
        var dLon = Math.abs(sat.lon - observerLon);
        var distApprox = Math.sqrt(dLat * dLat + dLon * dLon);
        if (distApprox < 10) score += 10;
      }
      if (score > 100) score = 100;
      if (score < 0) score = 0;
      return score;
    } catch (e) {
      return 0;
    }
  }

  function classifyElevationQuality(elev) {
    try {
      if (!isFinite(elev)) return "LOW";
      if (elev >= 70) return "EXCELLENT";
      if (elev >= 45) return "GOOD";
      if (elev >= 20) return "MEDIUM";
      return "LOW";
    } catch (e) {
      return "LOW";
    }
  }

  window.OrbitalCore = window.OrbitalCore || {};
  window.OrbitalCore.computeNextPass = computeNextPass;
  window.OrbitalCore.computeSatelliteScore = computeSatelliteScore;
  window.OrbitalCore.classifyElevationQuality = classifyElevationQuality;

  // future: connect to live TLE API (Celestrak / Space-Track)
  function refreshTLEData() {}
  window.OrbitalCore.refreshTLEData = refreshTLEData;
})();