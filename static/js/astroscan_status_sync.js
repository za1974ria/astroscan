/**
 * AstroScan — synchronisation multi-appareils
 * Source de vérité : GET /status (aucune persistance localStorage / sessionStorage).
 * Optionnel : WebSocket /ws/status (même charge utile).
 */
(function (global) {
  "use strict";

  var pollTimer = null;
  var safetyTimer = null;
  var reconnectTimer = null;
  var ws = null;
  var lastSerialized = null;
  var running = false;
  var opts = {
    intervalMs: 3500,
    backupPollMs: 5000,
    wsPath: "/ws/status",
    statusPath: "/status",
    useWebSocket: true,
    reconnectMs: 2500,
  };

  function emitError() {
    lastSerialized = null;
    global.dispatchEvent(
      new CustomEvent("astroscan:status", { detail: { _networkError: true } })
    );
  }

  function emitPayload(payload) {
    try {
      var s = JSON.stringify(payload);
      if (s === lastSerialized) return;
      lastSerialized = s;
    } catch (e) {
      return;
    }
    global.dispatchEvent(new CustomEvent("astroscan:status", { detail: payload }));
  }

  function fetchStatus() {
    var url = (opts && opts.statusPath) || "/status";
    fetch(url, { cache: "no-store", credentials: "same-origin" })
      .then(function (r) {
        if (!r.ok) throw new Error("http");
        return r.json();
      })
      .then(function (d) {
        emitPayload(d);
      })
      .catch(function () {
        emitError();
      });
  }

  function clearPoll() {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  function clearSafety() {
    if (safetyTimer) {
      clearInterval(safetyTimer);
      safetyTimer = null;
    }
  }

  function clearReconnect() {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
  }

  function closeWs() {
    if (ws) {
      try {
        ws.onopen = ws.onclose = ws.onerror = ws.onmessage = null;
        ws.close();
      } catch (e) {}
      ws = null;
    }
  }

  function startHttpPolling() {
    clearPoll();
    fetchStatus();
    var iv = Math.min(5000, Math.max(2000, opts.intervalMs || 3500));
    pollTimer = setInterval(fetchStatus, iv);
  }

  function startBackupPollingWhileWs() {
    clearSafety();
    var iv = Math.min(5000, Math.max(2000, opts.backupPollMs || 5000));
    safetyTimer = setInterval(fetchStatus, iv);
  }

  function scheduleWsReconnect() {
    if (!running || opts.useWebSocket === false) return;
    clearReconnect();
    reconnectTimer = setTimeout(connectWebSocket, opts.reconnectMs || 2500);
  }

  function connectWebSocket() {
    if (!running || opts.useWebSocket === false) return;
    closeWs();
    var proto = global.location.protocol === "https:" ? "wss:" : "ws:";
    var path = opts.wsPath || "/ws/status";
    var url = proto + "//" + global.location.host + path;
    try {
      var socket = new WebSocket(url);
      ws = socket;
      socket.onopen = function () {
        clearPoll();
        startBackupPollingWhileWs();
      };
      socket.onmessage = function (ev) {
        try {
          var d = JSON.parse(ev.data);
          emitPayload(d);
        } catch (e) {}
      };
      socket.onerror = function () {
        try {
          socket.close();
        } catch (e2) {}
      };
      socket.onclose = function () {
        ws = null;
        clearSafety();
        if (!running) return;
        startHttpPolling();
        scheduleWsReconnect();
      };
    } catch (e) {
      startHttpPolling();
      scheduleWsReconnect();
    }
  }

  global.AstroScanStatusSync = {
    start: function (options) {
      if (running) this.stop();
      running = true;
      opts = Object.assign({}, opts, options || {});
      if (global.AstroScanStatusSyncConfig) {
        opts = Object.assign({}, opts, global.AstroScanStatusSyncConfig);
      }
      lastSerialized = null;
      startHttpPolling();
      if (opts.useWebSocket !== false) connectWebSocket();
    },

    stop: function () {
      running = false;
      clearPoll();
      clearSafety();
      clearReconnect();
      closeWs();
      lastSerialized = null;
    },

    /** Dernier snapshot reçu (mémoire session uniquement — pas de stockage disque). */
    getLastSerialized: function () {
      return lastSerialized;
    },

    refresh: function () {
      fetchStatus();
    },
  };
})(typeof window !== "undefined" ? window : globalThis);
