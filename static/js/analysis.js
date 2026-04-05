/**
 * AstroScan — analysis.js
 * Responsibilities:
 *  - scoring logic, priority selection, analysis card rendering (delegated for now)
 *
 * Scaffolding for Phase 1 / Phase 2 refactor.
 */
(function () {
  "use strict";

  window.AstroScanAnalysis = window.AstroScanAnalysis || {};

  window.AstroScanAnalysis.render = function () {
    try {
      var i = window.__AstroScanInternal || {};
      if (typeof i.updateAnalysisCard === "function") i.updateAnalysisCard();
    } catch (e) {}
  };

  /** Objet prioritaire (même logique que la carte d’analyse / moteur orbital). */
  window.AstroScanAnalysis.getPriorityObject = function () {
    try {
      var i = window.__AstroScanInternal || {};
      if (typeof i.getRenderablePriorityObject === "function") return i.getRenderablePriorityObject();
    } catch (e) {}
    return null;
  };
})();

