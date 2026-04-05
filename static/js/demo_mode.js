/**
 * AstroScan — demo_mode.js
 * Responsibilities:
 *  - demo mode state, offsets, demo visual behavior (delegated for now)
 *
 * Scaffolding module for Phase 1 refactor.
 */
(function () {
  "use strict";

  window.AstroScanDemoMode = window.AstroScanDemoMode || {};

  window.AstroScanDemoMode.simulate = function () {
    try {
      var i = window.__AstroScanInternal || {};
      if (typeof i.simulateDemoActivity === "function") i.simulateDemoActivity();
    } catch (e) {}
  };
})();

