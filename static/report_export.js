/**
 * AstroScan — report_export.js
 * Responsibilities:
 *  - showroom report generation (delegated for now)
 */
(function () {
  "use strict";

  window.AstroScanReportExport = window.AstroScanReportExport || {};

  window.AstroScanReportExport.exportShowroom = function () {
    try {
      if (window.OrbitalMapEngine && typeof window.OrbitalMapEngine.exportShowroomReport === "function") {
        window.OrbitalMapEngine.exportShowroomReport();
      }
    } catch (e) {}
  };

  window.AstroScanReportExport.buildShowroomData = function () {
    try {
      if (window.OrbitalMapEngine && typeof window.OrbitalMapEngine.buildShowroomReportData === "function") {
        return window.OrbitalMapEngine.buildShowroomReportData();
      }
    } catch (e) {}
    return null;
  };
})();

