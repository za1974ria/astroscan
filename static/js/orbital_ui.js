/**
 * Orbital UI helpers — gestion des boutons Radar Pro.
 * Chargé après orbital_map_engine.js.
 */
(function () {
  "use strict";

  var _proControlsWired = false;

  window.OrbitalUI = window.OrbitalUI || {};
  window.OrbitalUI.updateVideoDemoOverlay = function (title, text, visible) {
    try {
      var box = document.getElementById("video-demo-overlay");
      var titleEl = document.getElementById("video-demo-title");
      var textEl = document.getElementById("video-demo-text");
      if (!box || !titleEl || !textEl) return;
      box.style.display = visible ? "block" : "none";
      if (title != null) titleEl.textContent = title;
      if (text != null) textEl.textContent = text;
    } catch (e) {}
  };

  window.OrbitalUI.updateSelfTestOverlay = function (title, stepText, checklistHtml, visible) {
    try {
      var box = document.getElementById("self-test-overlay");
      var titleEl = document.getElementById("self-test-title");
      var stepEl = document.getElementById("self-test-step");
      var listEl = document.getElementById("self-test-checklist");
      if (!box || !titleEl || !stepEl || !listEl) return;
      box.style.display = visible ? "block" : "none";
      if (title != null) titleEl.textContent = title;
      if (stepText != null) stepEl.textContent = stepText;
      if (checklistHtml != null) listEl.innerHTML = checklistHtml;
    } catch (e) {}
  };

  function updateFilterButtons(type) {
    try {
      var buttons = document.querySelectorAll(".pro-controls button[data-filter]");
      if (!buttons || !buttons.forEach) return;
      buttons.forEach(function (btn) {
        var f = btn.getAttribute("data-filter");
        if (!f) return;
        if (type && f === type) {
          btn.classList.add("active");
        } else if (!type && f === "all") {
          btn.classList.add("active");
        } else {
          btn.classList.remove("active");
        }
      });
    } catch (e) {}
  }

  window.showToast = function (message) {
    try {
      var host = document.getElementById("alert-toasts");
      if (!host) return;
      var div = document.createElement("div");
      div.textContent = message;
      div.style.background = "rgba(0,0,0,0.85)";
      div.style.color = "#00ff88";
      div.style.padding = "4px 8px";
      div.style.marginTop = "4px";
      div.style.border = "1px solid rgba(0,255,136,0.5)";
      div.style.borderRadius = "4px";
      host.appendChild(div);
      setTimeout(function () {
        try { host.removeChild(div); } catch (e) {}
      }, 5000);
    } catch (e) {}
  };

  if (typeof window.setFilter === "function") {
    var originalSetFilter = window.setFilter;
    window.setFilter = function (type) {
      var t = (type || "all").toString().toLowerCase();
      var label = t === "all" ? "ALL" : t.toUpperCase();
      try {
        console.log("BOUTON " + label + " clicked");
      } catch (eL) {}
      originalSetFilter(t);
      updateFilterButtons(t);
    };
    var initialFilter = "all";
    try {
      if (window.OrbitalMapEngine && OrbitalMapEngine.state && OrbitalMapEngine.state.filter) {
        initialFilter = String(OrbitalMapEngine.state.filter).toLowerCase();
      }
    } catch (e0) {}
    updateFilterButtons(initialFilter);
  }

  function wireProControls() {
    if (_proControlsWired) {
      return;
    }
    try {
      document.querySelectorAll(".pro-controls button[data-filter]").forEach(function (btn) {
        btn.addEventListener("click", function (ev) {
          ev.preventDefault();
          var f = (btn.getAttribute("data-filter") || "all").toLowerCase();
          if (typeof window.setFilter === "function") window.setFilter(f);
        });
      });

      var ex = document.getElementById("btn-export-csv");
      if (ex) {
        ex.addEventListener("click", function (ev) {
          ev.preventDefault();
          try {
            console.log("BOUTON EXPORT clicked");
          } catch (e1) {}
          if (typeof window.exportReport === "function") window.exportReport();
        });
      }

      var er = document.getElementById("btn-export-report");
      if (er) {
        er.addEventListener("click", function (ev) {
          ev.preventDefault();
          try {
            console.log("BOUTON EXPORT REPORT clicked");
          } catch (e2) {}
          if (window.OrbitalMapEngine && typeof OrbitalMapEngine.exportShowroomReport === "function") {
            OrbitalMapEngine.exportShowroomReport();
          } else if (typeof window.exportShowroomReport === "function") {
            window.exportShowroomReport();
          }
        });
      }

      var dm = document.getElementById("btn-demo-mode");
      if (dm) {
        dm.addEventListener("click", function (ev) {
          ev.preventDefault();
          try {
            console.log("BOUTON DEMO MODE clicked");
          } catch (e3) {}
          if (typeof window.toggleDemoMode === "function") window.toggleDemoMode();
        });
      }

      var det = document.getElementById("btn-details");
      if (det) {
        det.addEventListener("click", function (ev) {
          ev.preventDefault();
          try {
            console.log("BOUTON DETAILS clicked");
          } catch (e4) {}
          if (typeof window.toggleCloseApproaches === "function") window.toggleCloseApproaches();
        });
      }
    } catch (eW) {}
    _proControlsWired = true;
  }

  function forceShowroomDemoOff() {
    try {
      if (window.OrbitalMapEngine && OrbitalMapEngine.state) {
        OrbitalMapEngine.state.demoMode = false;
      }
    } catch (eF) {}
    try {
      var dm = document.getElementById("btn-demo-mode");
      if (dm) dm.classList.remove("is-active");
    } catch (eB) {}
    try {
      document.body.classList.remove("demo-glow");
    } catch (eG) {}
  }

  window.OrbitalUI.updateFilterButtons = updateFilterButtons;
  window.OrbitalUI.wireProControls = wireProControls;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function onDomReady() {
      forceShowroomDemoOff();
      wireProControls();
    });
  } else {
    forceShowroomDemoOff();
    wireProControls();
  }

  // Loading overlay (progression fake 0→100% sur 2s mini)
  window.addEventListener("load", function () {
    try {
      var overlay = document.getElementById("loading-overlay");
      var barInner = document.getElementById("loading-bar-inner");
      if (!overlay || !barInner) return;
      var start = Date.now();
      var width = 0;
      var timer = setInterval(function () {
        try {
          var elapsed = Date.now() - start;
          var target = Math.min(100, (elapsed / 2000) * 100);
          if (target > width) width = target;
          barInner.style.width = width + "%";
          if (elapsed >= 2000) {
            clearInterval(timer);
            overlay.style.display = "none";
          }
        } catch (e) {
          clearInterval(timer);
        }
      }, 150);

      // tentative fullscreen douce (peut échouer silencieusement selon le navigateur)
      try {
        var elem = document.documentElement;
        if (elem && elem.requestFullscreen) {
          elem.requestFullscreen().catch(function () {});
        }
      } catch (e) {}
    } catch (e) {}
  });
})();

