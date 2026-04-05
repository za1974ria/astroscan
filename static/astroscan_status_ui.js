/**
 * Binding unique des champs UI synchronisés avec GET /status (via astroscan:status).
 * Ne modifie que les éléments présents dans le DOM ; ne lève pas d'exception.
 */
(function (global) {
  "use strict";

  function get(id) {
    try {
      return document.getElementById(id);
    } catch (e) {
      return null;
    }
  }

  function setText(id, value) {
    var el = get(id);
    if (!el) return;
    try {
      el.textContent = value == null ? "—" : String(value);
    } catch (e) {}
  }

  global.AstroScanStatusUI = {
    bind: function (status) {
      try {
        if (!status || status._networkError) return;

        var obs = status.observation_mode;
        setText("mode-status", obs != null && obs !== "" ? obs : "—");

        var si = status.system_intelligence;
        var gs =
          si && typeof si === "object" && si.global_status != null && si.global_status !== ""
            ? si.global_status
            : "—";
        setText("global-status", gs);

        var po = status.priority_object;
        var name =
          po && typeof po === "object" && po.name != null && po.name !== ""
            ? String(po.name)
            : "—";
        setText("priority-object", name);

        if (get("priority-score")) {
          if (po && typeof po === "object" && po.score != null && po.score !== "") {
            setText("priority-score", po.score);
          } else {
            setText("priority-score", "—");
          }
        }

        var perf = status.performance;
        if (get("response-time")) {
          if (perf && typeof perf === "object" && perf.response_time_ms != null) {
            setText("response-time", String(perf.response_time_ms) + " ms");
          } else {
            setText("response-time", "—");
          }
        }
      } catch (e) {}
    },

    clear: function () {
      try {
        var ids = [
          "mode-status",
          "global-status",
          "priority-object",
          "priority-score",
          "response-time",
        ];
        for (var i = 0; i < ids.length; i++) {
          var el = document.getElementById(ids[i]);
          if (el) el.textContent = "—";
        }
      } catch (e) {}
    },
  };
})(typeof window !== "undefined" ? window : globalThis);
