/* SCAN A SIGNAL — cinematic acquisition sequence.
   Renders boot animations, telemetry "ACQUIRING…" lines, and SIGNAL ACQUIRED lock.
*/
(function (global) {
  "use strict";

  var ACQUIRE_LINES_FR = [
    "ÉTABLISSEMENT LIAISON UPLINK...",
    "INTERROGATION BASE DE DONNÉES TLE...",
    "PROPAGATION SGP4 EN COURS...",
    "LOCALISATION DE LA CIBLE...",
    "CALCUL TRIANGULATION...",
  ];
  var ACQUIRE_LINES_EN = [
    "ESTABLISHING UPLINK...",
    "QUERYING TLE DATABASE...",
    "COMPUTING SGP4 PROPAGATION...",
    "LOCATING ASSET...",
    "COMPUTING TRIANGULATION...",
  ];
  var LOCK_FR = "SIGNAL ACQUIS.";
  var LOCK_EN = "SIGNAL ACQUIRED.";

  function clearChildren(el) { while (el.firstChild) el.removeChild(el.firstChild); }

  function showAcquisition(rootEl, lang, onComplete) {
    var lines = lang === "en" ? ACQUIRE_LINES_EN : ACQUIRE_LINES_FR;
    var lock = lang === "en" ? LOCK_EN : LOCK_FR;

    rootEl.classList.add("visible");
    clearChildren(rootEl);

    var titleEl = document.createElement("div");
    titleEl.className = "ss-acquire-title";
    titleEl.textContent = lang === "en" ? "// ACQUIRING TARGET" : "// ACQUISITION DE LA CIBLE";
    rootEl.appendChild(titleEl);

    var lineEls = lines.map(function (txt) {
      var el = document.createElement("div");
      el.className = "ss-acquire-line";
      el.textContent = "> " + txt;
      rootEl.appendChild(el);
      return el;
    });

    var lockEl = document.createElement("div");
    lockEl.className = "ss-acquire-line lock";
    lockEl.textContent = "> " + lock;
    rootEl.appendChild(lockEl);

    // Stagger each line 200ms
    lineEls.forEach(function (el, i) {
      setTimeout(function () { el.classList.add("visible"); }, 200 + i * 200);
    });

    setTimeout(function () { lockEl.classList.add("visible"); }, 200 + lines.length * 200 + 60);
    setTimeout(function () {
      if (typeof onComplete === "function") onComplete();
    }, 1500);
  }

  function hideAcquisition(rootEl) {
    rootEl.classList.remove("visible");
  }

  global.SSCinematic = {
    showAcquisition: showAcquisition,
    hideAcquisition: hideAcquisition,
  };
})(window);
