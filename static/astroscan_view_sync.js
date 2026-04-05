/**
 * AstroScanViewSync — synchro vue multi-appareils (VIEW_STATE, HEARTBEAT, REQUEST_MASTER).
 * Indépendant de /status / AstroScanStatusSync.
 */
(function (global) {
  "use strict";

  var cfg = null;
  var ws = null;
  var reconnectTimer = null;
  var reconnectAttempt = 0;
  var flushTimer = null;
  var pendingPayload = {};
  var running = false;
  var connState = "offline";
  var heartbeatTimer = null;

  var _applyingRemote = false;

  var WS_PATH = "/ws/view-sync";
  var FLUSH_MS = 120;
  var MAX_ENVELOPE_BYTES = 60000;
  var HEARTBEAT_MS = 5000;

  var VALID_ROLES = { master: 1, viewer: 1, collaborative: 1 };

  function _debug() {
    try {
      if (global.sessionStorage && sessionStorage.getItem("astroscan_view_debug") === "1") return true;
      var q = new URLSearchParams(global.location.search || "");
      return q.get("viewDebug") === "1";
    } catch (e) {
      return false;
    }
  }

  function _log() {
    if (!_debug() || !global.console) return;
    try {
      console.log.apply(console, ["[AstroScanViewSync]"].concat([].slice.call(arguments)));
    } catch (e) {}
  }

  function _toast(msg) {
    if (!msg) return;
    try {
      if (typeof global.showToast === "function") {
        global.showToast(msg);
        return;
      }
    } catch (e) {}
    try {
      if (global.console && console.warn) console.warn("[AstroScanViewSync]", msg);
    } catch (e2) {}
  }

  function getOrCreateDeviceId() {
    try {
      var k = "astroscan_view_device_id";
      var s = null;
      try {
        s = localStorage.getItem(k);
      } catch (e0) {}
      if (!s) {
        try {
          s = sessionStorage.getItem(k);
        } catch (e1) {}
      }
      if (!s) {
        s = "dev-" + Math.random().toString(36).slice(2, 11) + "-" + Date.now().toString(36);
        try {
          localStorage.setItem(k, s);
        } catch (e2) {
          try {
            sessionStorage.setItem(k, s);
          } catch (e3) {}
        }
      }
      return s;
    } catch (e) {
      return "dev-" + String(Date.now());
    }
  }

  function parseRole(v) {
    var r = (v || "master").toString().toLowerCase().trim();
    return VALID_ROLES[r] ? r : "master";
  }

  function parseConfigFromUrl() {
    try {
      var q = new URLSearchParams(global.location.search || "");
      var sid = q.get("sessionId");
      var vr = q.get("viewRole");
      var sk = q.get("sessionKey");
      return {
        sessionId: sid && sid.trim() ? sid.trim().slice(0, 128) : null,
        role: vr ? parseRole(vr) : null,
        sessionKey: sk && sk.length ? sk : null,
      };
    } catch (e) {
      return { sessionId: null, role: null, sessionKey: null };
    }
  }

  function mergeDeep(dst, src) {
    if (!src || typeof src !== "object") return;
    Object.keys(src).forEach(function (k) {
      var v = src[k];
      if (v !== null && typeof v === "object" && Object.prototype.toString.call(v) === "[object Object]") {
        if (!dst[k] || typeof dst[k] !== "object") dst[k] = {};
        mergeDeep(dst[k], v);
      } else {
        dst[k] = v;
      }
    });
  }

  function buildWsUrl() {
    var path = (cfg && cfg.wsPath) || WS_PATH;
    var sid = (cfg && cfg.sessionId) || "orbital-chohra-main";
    var role = (cfg && cfg.role) || "master";
    var dev = (cfg && cfg.sourceDevice) || "";
    var proto = global.location.protocol === "https:" ? "wss:" : "ws:";
    var q =
      "sessionId=" +
      encodeURIComponent(sid) +
      "&viewRole=" +
      encodeURIComponent(role) +
      "&sourceDevice=" +
      encodeURIComponent(dev);
    if (cfg && cfg.sessionKey) {
      q += "&sessionKey=" + encodeURIComponent(cfg.sessionKey);
    }
    return proto + "//" + global.location.host + path + "?" + q;
  }

  function clearHeartbeat() {
    if (heartbeatTimer) {
      clearInterval(heartbeatTimer);
      heartbeatTimer = null;
    }
  }

  function startHeartbeatIfNeeded() {
    clearHeartbeat();
    if (!running || !cfg || !canEmit()) return;
    heartbeatTimer = setInterval(function () {
      if (!ws || ws.readyState !== 1 || !canEmit()) return;
      sendJson({
        type: "HEARTBEAT",
        sessionId: cfg.sessionId,
        sourceDevice: cfg.sourceDevice,
        timestamp: Date.now(),
      });
    }, HEARTBEAT_MS);
  }

  function sendJson(obj) {
    if (!ws || ws.readyState !== 1) return;
    var raw;
    try {
      raw = JSON.stringify(obj);
    } catch (e) {
      return;
    }
    if (raw.length > MAX_ENVELOPE_BYTES) return;
    try {
      ws.send(raw);
    } catch (e2) {}
  }

  function setConnState(next) {
    if (connState === next) return;
    connState = next;
    _log("ws:", next);
    try {
      global.dispatchEvent(
        new CustomEvent("astroscan:view-ws", { detail: { state: next, sessionId: cfg && cfg.sessionId } })
      );
    } catch (e) {}
    var dot = document.getElementById("asc-view-sync-ws");
    if (dot) {
      dot.textContent = next === "open" ? "ONLINE" : "OFFLINE";
      dot.setAttribute("data-state", next);
    }
  }

  function updateTakeoverBtn() {
    var btn = document.getElementById("asc-view-takeover");
    if (!btn) return;
    var show = !!(cfg && cfg.role === "viewer");
    btn.style.display = show ? "inline-block" : "none";
  }

  function refreshHud() {
    var sEl = document.getElementById("asc-view-sync-session");
    var rEl = document.getElementById("asc-view-sync-role");
    if (sEl && cfg) sEl.textContent = cfg.sessionId || "—";
    if (rEl && cfg) {
      var r = cfg.role || "master";
      rEl.setAttribute("data-role", r);
      var rr = r.toString().toUpperCase();
      rEl.textContent = rr === "COLLABORATIVE" ? "COLLAB" : rr;
      if (cfg._serverDowngraded) {
        rEl.setAttribute("title", "Serveur : mode viewer (master occupé ou timeout)");
        rEl.style.opacity = "0.9";
      } else {
        rEl.removeAttribute("title");
        rEl.style.opacity = "";
      }
    }
    updateTakeoverBtn();
  }

  function clearReconnect() {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
  }

  function clearFlush() {
    if (flushTimer) {
      clearTimeout(flushTimer);
      flushTimer = null;
    }
  }

  function closeWs() {
    clearHeartbeat();
    if (ws) {
      try {
        ws.onopen = ws.onclose = ws.onerror = ws.onmessage = null;
        ws.close();
      } catch (e) {}
      ws = null;
    }
  }

  function canEmit() {
    if (!cfg) return false;
    var r = cfg.role || "master";
    return r === "master" || r === "collaborative";
  }

  function flushSend() {
    flushTimer = null;
    if (!running || !cfg || _applyingRemote) {
      pendingPayload = {};
      return;
    }
    if (!canEmit()) {
      pendingPayload = {};
      return;
    }
    if (!ws || ws.readyState !== 1) return;
    var keys = Object.keys(pendingPayload);
    if (keys.length === 0) return;
    var payload = pendingPayload;
    pendingPayload = {};
    var envelope = {
      type: "VIEW_STATE",
      sessionId: cfg.sessionId,
      sourceDevice: cfg.sourceDevice,
      timestamp: Date.now(),
      messageKind: "update",
      clientRole: cfg.role,
      payload: payload,
    };
    var raw;
    try {
      raw = JSON.stringify(envelope);
    } catch (e) {
      return;
    }
    if (raw.length > MAX_ENVELOPE_BYTES) return;
    try {
      ws.send(raw);
    } catch (e2) {}
  }

  function scheduleFlush() {
    if (flushTimer) return;
    flushTimer = setTimeout(flushSend, FLUSH_MS);
  }

  function scheduleReconnect() {
    clearReconnect();
    if (!running || !cfg) return;
    setConnState("reconnecting");
    var base = Math.min(30000, 800 * Math.pow(2, reconnectAttempt));
    reconnectAttempt++;
    reconnectTimer = setTimeout(connect, base);
  }

  function handleRoleUpdate(obj) {
    if (!cfg) return;
    if (obj.role === "master") {
      cfg.role = "master";
      cfg._serverDowngraded = false;
      _log("ROLE_UPDATE master", obj.reason || "");
      try {
        if (global.console && console.info) {
          console.info("[AstroScanViewSync] Rôle serveur : MASTER (" + (obj.reason || "") + ")");
        }
      } catch (e) {}
      refreshHud();
      startHeartbeatIfNeeded();
      try {
        global.dispatchEvent(
          new CustomEvent("astroscan:view-role", {
            detail: { role: "master", reason: obj.reason, sessionId: obj.sessionId },
          })
        );
      } catch (e2) {}
      return;
    }
    if (obj.role === "viewer") {
      cfg.role = "viewer";
      cfg._serverDowngraded = true;
      clearHeartbeat();
      _log("ROLE_UPDATE viewer", obj.reason || "");
      try {
        if (global.console && console.info) {
          console.info("[AstroScanViewSync] Rôle serveur : VIEWER (" + (obj.reason || "?") + ")");
        }
      } catch (e) {}
      if (obj.reason === "master_active" || obj.reason === "takeover_failed") {
        _toast(
          obj.reason === "master_active"
            ? "Contrôle : un autre pilote est actif."
            : "Prise de contrôle impossible pour le moment."
        );
      }
      refreshHud();
      try {
        global.dispatchEvent(
          new CustomEvent("astroscan:view-role", {
            detail: { role: "viewer", reason: obj.reason, sessionId: obj.sessionId },
          })
        );
      } catch (e3) {}
    }
  }

  function connect() {
    clearReconnect();
    if (!running || !cfg) return;
    closeWs();
    setConnState("connecting");
    try {
      ws = new WebSocket(buildWsUrl());
    } catch (e) {
      scheduleReconnect();
      return;
    }
    ws.onopen = function () {
      reconnectAttempt = 0;
      setConnState("open");
      refreshHud();
      startHeartbeatIfNeeded();
    };
    ws.onclose = function () {
      clearHeartbeat();
      setConnState("offline");
      if (running) scheduleReconnect();
    };
    ws.onerror = function () {
      try {
        ws.close();
      } catch (e) {}
    };
    ws.onmessage = function (ev) {
      var raw = ev.data;
      if (raw == null) return;
      if (typeof raw !== "string") {
        try {
          raw = String(raw);
        } catch (e) {
          return;
        }
      }
      if (raw.length > MAX_ENVELOPE_BYTES) return;
      var obj;
      try {
        obj = JSON.parse(raw);
      } catch (e) {
        return;
      }
      if (!obj) return;

      if (obj.type === "VIEW_STATE" && obj.messageKind === "init") {
        global.AstroScanViewSync.apply(obj, {
          messageKind: "init",
          skipSourceDeviceCheck: true,
        });
        return;
      }

      if (obj.type === "ROLE_UPDATE") {
        handleRoleUpdate(obj);
        return;
      }

      if (obj.type !== "VIEW_STATE") return;
      if (obj.sourceDevice === cfg.sourceDevice) return;
      var mk = obj.messageKind || "update";
      _log("recv", mk, obj.payload && obj.payload.mode);
      global.AstroScanViewSync.apply(obj, { messageKind: mk });
    };
  }

  global.AstroScanViewSync = {
    _applyingRemote: false,

    parseConfigFromUrl: parseConfigFromUrl,

    start: function (config) {
      running = true;
      cfg = cfg || {};
      var urlOpts = parseConfigFromUrl();
      cfg.sessionId =
        (config && config.sessionId) ||
        urlOpts.sessionId ||
        cfg.sessionId ||
        "orbital-chohra-main";
      cfg.sessionId = String(cfg.sessionId).trim().slice(0, 128) || "orbital-chohra-main";
      cfg.role = parseRole(
        (config && config.role) || urlOpts.role || cfg.role || "master"
      );
      cfg.sourceDevice =
        (config && config.sourceDevice) || cfg.sourceDevice || getOrCreateDeviceId();
      cfg.wsPath = (config && config.wsPath) || cfg.wsPath || WS_PATH;
      cfg.sessionKey =
        (config && config.sessionKey != null ? config.sessionKey : null) ||
        urlOpts.sessionKey ||
        cfg.sessionKey ||
        null;
      cfg._serverDowngraded = false;
      reconnectAttempt = 0;
      _log("start", cfg.sessionId, cfg.role);
      refreshHud();
      connect();
    },

    stop: function () {
      running = false;
      clearFlush();
      clearReconnect();
      clearHeartbeat();
      pendingPayload = {};
      closeWs();
      setConnState("offline");
    },

    send: function (partialPayload) {
      if (!running || !cfg || _applyingRemote) return;
      if (!canEmit()) return;
      if (!partialPayload || typeof partialPayload !== "object") return;
      mergeDeep(pendingPayload, partialPayload);
      scheduleFlush();
    },

    requestMaster: function () {
      if (!running || !cfg) return;
      sendJson({
        type: "REQUEST_MASTER",
        sessionId: cfg.sessionId,
        sourceDevice: cfg.sourceDevice,
        timestamp: Date.now(),
      });
    },

    apply: function (envelope, options) {
      if (!envelope || envelope.type !== "VIEW_STATE") return;
      var skip =
        options && options.skipSourceDeviceCheck;
      if (!skip && cfg && envelope.sourceDevice === cfg.sourceDevice) return;
      _applyingRemote = true;
      global.AstroScanViewSync._applyingRemote = true;
      try {
        var detail = envelope;
        if (options && options.messageKind) {
          detail = Object.assign({}, envelope, { messageKind: options.messageKind });
        }
        global.dispatchEvent(new CustomEvent("astroscan:view-state", { detail: detail }));
      } catch (e) {
      } finally {
        _applyingRemote = false;
        global.AstroScanViewSync._applyingRemote = false;
      }
    },

    getSessionId: function () {
      return (cfg && cfg.sessionId) || null;
    },
    getRole: function () {
      return (cfg && cfg.role) || null;
    },
    getSourceDevice: function () {
      return (cfg && cfg.sourceDevice) || null;
    },
    isMaster: function () {
      return cfg && cfg.role === "master";
    },
    isViewer: function () {
      return cfg && cfg.role === "viewer";
    },
    canEmit: function () {
      return canEmit();
    },
    getConnectionState: function () {
      return connState;
    },
  };
})(typeof window !== "undefined" ? window : this);
