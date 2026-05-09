/* ============================================================
   GROUND ASSETS — triangulation helper
   Pure-function utilities. Loaded for completeness; the main
   ground_assets.js renders polylines directly using these
   primitives via window.GroundAssetsTri.
   ============================================================ */
(function () {
  'use strict';

  const EARTH_KM = 6371.0088;

  function toRad(d) { return d * Math.PI / 180; }
  function toDeg(r) { return r * 180 / Math.PI; }

  function greatCircleKm(lat1, lon1, lat2, lon2) {
    const p1 = toRad(lat1), p2 = toRad(lat2);
    const dl = toRad(lon2 - lon1);
    const dp = p2 - p1;
    const a = Math.sin(dp / 2) ** 2 +
              Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
    return 2 * EARTH_KM * Math.asin(Math.sqrt(a));
  }

  function rssiFromKm(distanceKm) {
    let r = -67 - distanceKm / 50;
    if (r < -110) r = -110;
    if (r > -40)  r = -40;
    return r;
  }

  // Free-space path loss check — used to flag "out of comfortable range"
  function rssiQuality(rssi) {
    if (rssi >= -75)  return 'excellent';
    if (rssi >= -90)  return 'good';
    if (rssi >= -100) return 'fair';
    return 'poor';
  }

  // Sample N points along a great-circle arc — useful for animated lines
  function arcSamples(lat1, lon1, lat2, lon2, n) {
    const points = [];
    const p1 = toRad(lat1), p2 = toRad(lat2);
    const l1 = toRad(lon1), l2 = toRad(lon2);
    const d = greatCircleKm(lat1, lon1, lat2, lon2) / EARTH_KM;
    if (d < 1e-9) return [[lat1, lon1]];
    for (let i = 0; i <= n; i++) {
      const f = i / n;
      const a = Math.sin((1 - f) * d) / Math.sin(d);
      const b = Math.sin(f * d) / Math.sin(d);
      const x = a * Math.cos(p1) * Math.cos(l1) + b * Math.cos(p2) * Math.cos(l2);
      const y = a * Math.cos(p1) * Math.sin(l1) + b * Math.cos(p2) * Math.sin(l2);
      const z = a * Math.sin(p1) + b * Math.sin(p2);
      const lat = toDeg(Math.atan2(z, Math.sqrt(x * x + y * y)));
      const lon = toDeg(Math.atan2(y, x));
      points.push([lat, lon]);
    }
    return points;
  }

  window.GroundAssetsTri = {
    greatCircleKm: greatCircleKm,
    rssiFromKm: rssiFromKm,
    rssiQuality: rssiQuality,
    arcSamples: arcSamples,
  };
})();
