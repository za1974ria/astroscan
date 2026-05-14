/* ASTROSCAN SENTINEL — unified client logic.
 * Pages dispatched by body[data-page]: landing | driver | parent.
 * Driver page handles both invite and cockpit views without URL change.
 */
(function () {
  "use strict";

  // ───────────────────────────────────────────────── utils
  function $(id) { return document.getElementById(id); }
  function showError(msg) {
    var el = $("sn-error");
    if (!el) { console.warn("Sentinel:", msg); return; }
    el.textContent = msg; el.hidden = false;
  }
  function clearError() {
    var el = $("sn-error"); if (el) { el.hidden = true; el.textContent = ""; }
  }
  function pillEl() { return $("sn-state-pill") || $("sn-ttl"); }
  function setPill(text, kind) {
    var el = pillEl(); if (!el) return;
    el.textContent = text;
    el.className = "sn-pill" + (kind ? " sn-pill--" + kind : "");
  }
  function fmtCountdown(s) {
    s = Math.max(0, Math.floor(s));
    var m = Math.floor(s / 60), r = s % 60;
    return (m < 10 ? "0" + m : m) + ":" + (r < 10 ? "0" + r : r);
  }
  function fmtAge(serverTs, lastTs) {
    if (!lastTs) return "—";
    var s = Math.max(0, serverTs - lastTs);
    if (s < 60) return s + " s";
    return Math.round(s / 60) + " min";
  }
  function postJson(url, body) {
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {})
    }).then(function (r) {
      return r.json().then(function (j) { return { ok: r.ok, status: r.status, body: j }; });
    });
  }
  function getJson(url) {
    return fetch(url).then(function (r) {
      return r.json().then(function (j) { return { ok: r.ok, status: r.status, body: j }; });
    });
  }

  // ───────────────────────────────────────────────── LANDING
  function initLanding() {
    var ttl = 3600, limit = 90;
    var zoneLat = null, zoneLon = null, zoneRadius = null;

    document.querySelectorAll(".sn-chip[data-ttl]").forEach(function (c) {
      c.addEventListener("click", function () {
        document.querySelectorAll(".sn-chip[data-ttl]")
          .forEach(function (x) { x.classList.remove("sn-chip--on"); });
        c.classList.add("sn-chip--on");
        ttl = parseInt(c.getAttribute("data-ttl"), 10);
      });
    });
    document.querySelectorAll(".sn-chip[data-limit]").forEach(function (c) {
      c.addEventListener("click", function () {
        document.querySelectorAll(".sn-chip[data-limit]")
          .forEach(function (x) { x.classList.remove("sn-chip--on"); });
        c.classList.add("sn-chip--on");
        limit = parseInt(c.getAttribute("data-limit"), 10);
        $("sn-limit-custom").value = "";
      });
    });
    $("sn-limit-custom").addEventListener("input", function () {
      var v = parseInt(this.value, 10);
      if (v >= 30 && v <= 200) {
        document.querySelectorAll(".sn-chip[data-limit]")
          .forEach(function (x) { x.classList.remove("sn-chip--on"); });
        limit = v;
      }
    });

    $("sn-zone-here").addEventListener("click", function () {
      if (!navigator.geolocation) { showError("Géolocalisation indisponible"); return; }
      navigator.geolocation.getCurrentPosition(function (pos) {
        $("sn-zone-lat").value = pos.coords.latitude.toFixed(5);
        $("sn-zone-lon").value = pos.coords.longitude.toFixed(5);
      }, function (e) {
        showError("Impossible d'obtenir la position : " + (e.message || e.code));
      }, { enableHighAccuracy: true, timeout: 8000 });
    });

    $("sn-create-btn").addEventListener("click", function () {
      clearError();
      zoneLat = parseFloat($("sn-zone-lat").value);
      zoneLon = parseFloat($("sn-zone-lon").value);
      zoneRadius = parseInt($("sn-zone-radius").value, 10);
      var safe_zone = null;
      if (!isNaN(zoneLat) && !isNaN(zoneLon) && zoneRadius >= 50) {
        safe_zone = { lat: zoneLat, lon: zoneLon, radius_m: zoneRadius };
      }
      var btn = this;
      btn.disabled = true;
      btn.textContent = "Création…";
      var body = {
        ttl_seconds: ttl,
        speed_limit_kmh: limit,
        driver_label: ($("sn-driver-label").value || "").trim() || null,
        safe_zone: safe_zone
      };
      postJson("/api/sentinel/session/create", body)
        .then(function (res) {
          if (!res.ok) throw new Error(res.body.error || "create_failed");
          var b = res.body;
          $("sn-invite-url").value = b.invite_url;
          $("sn-parent-open").href = b.parent_url;
          var label = b.driver_label ? (b.driver_label + ", ") : "";
          var msg = label + "voici ton invitation à un trajet protégé : " + b.invite_url;
          $("sn-share-whatsapp").href = "https://wa.me/?text=" + encodeURIComponent(msg);
          $("sn-share-sms").href = "sms:?&body=" + encodeURIComponent(msg);
          if (navigator.share) {
            $("sn-share-native").hidden = false;
            $("sn-share-native").onclick = function () {
              navigator.share({ title: "Trajet protégé · Sentinel", text: msg })
                .catch(function () {});
            };
          }
          $("sn-result").hidden = false;
          $("sn-result").scrollIntoView({ behavior: "smooth", block: "nearest" });
        })
        .catch(function (e) { showError("Erreur : " + e.message); })
        .finally(function () {
          btn.disabled = false;
          btn.textContent = "Créer l'invitation →";
        });
    });

    document.querySelectorAll("[data-copy]").forEach(function (b) {
      b.addEventListener("click", function () {
        var t = $(b.getAttribute("data-copy"));
        if (!t) return;
        t.select();
        try { document.execCommand("copy"); } catch (e) {}
        var prev = b.textContent;
        b.textContent = "Copié ✓";
        setTimeout(function () { b.textContent = prev; }, 1400);
      });
    });
  }

  // ───────────────────────────────────────────────── DRIVER
  function initDriver() {
    var token = document.body.getAttribute("data-token");
    var limit = parseInt(document.body.getAttribute("data-limit"), 10) || 90;
    var holdMs = (parseInt(document.body.getAttribute("data-sos-hold"), 10) || 3) * 1000;
    var interval = parseInt(document.body.getAttribute("data-interval"), 10) || 5;
    var initialState = document.body.getAttribute("data-initial-state") || "PENDING_DRIVER";

    var lastFix = null;
    var lastBattery = null;
    var watchId = null;
    var pushTimer = null;
    var stateTimer = null;
    var wakeSentinel = null;
    var sosActive = false;
    var ended = false;
    var inCockpit = false;

    function requestWakeLock() {
      if ("wakeLock" in navigator) {
        navigator.wakeLock.request("screen")
          .then(function (s) { wakeSentinel = s; })
          .catch(function () {});
      }
    }
    document.addEventListener("visibilitychange", function () {
      if (!document.hidden && !ended && inCockpit) requestWakeLock();
    });

    if (navigator.getBattery) {
      navigator.getBattery().then(function (b) {
        function snap() { lastBattery = Math.round(b.level * 100); }
        snap();
        b.addEventListener("levelchange", snap);
      });
    }

    function showCockpit() {
      $("sn-invite").hidden = true;
      $("sn-cockpit").hidden = false;
      inCockpit = true;
      startGeo();
    }

    function startGeo() {
      if (!("geolocation" in navigator)) {
        showError("Géolocalisation indisponible.");
        return;
      }
      requestWakeLock();
      setPill("ACQUISITION", "warn");
      watchId = navigator.geolocation.watchPosition(function (pos) {
        var spdMs = (pos.coords.speed !== null && !isNaN(pos.coords.speed) && pos.coords.speed >= 0)
          ? pos.coords.speed : null;
        var spdKmh = spdMs !== null ? (spdMs * 3.6) : null;
        lastFix = {
          lat: pos.coords.latitude,
          lon: pos.coords.longitude,
          accuracy: pos.coords.accuracy || 0,
          speed_kmh: spdKmh,
          heading_deg: (pos.coords.heading !== null && !isNaN(pos.coords.heading))
            ? pos.coords.heading : null
        };
        renderSpeed(spdKmh);
      }, function (err) {
        showError("GPS : " + (err.message || err.code));
        setPill("GPS REFUSÉ", "danger");
      }, { enableHighAccuracy: true, maximumAge: 2000, timeout: 15000 });

      pushTimer = setInterval(pushUpdate, interval * 1000);
      stateTimer = setInterval(pullState, interval * 1000);
      pullState();
    }

    function renderSpeed(kmh) {
      var el = $("sn-speed");
      var box = document.querySelector(".sn-speedo");
      if (kmh === null || kmh === undefined || isNaN(kmh)) {
        el.textContent = "—";
        box.classList.remove("sn-speedo--over");
        $("sn-over-banner").hidden = true;
        return;
      }
      el.textContent = Math.round(kmh);
      box.classList.toggle("sn-speedo--over", kmh > limit);
    }

    function pushUpdate() {
      if (!lastFix || ended) return;
      var body = {
        token: token,
        lat: lastFix.lat,
        lon: lastFix.lon,
        accuracy: lastFix.accuracy,
        speed_kmh: lastFix.speed_kmh,
        heading_deg: lastFix.heading_deg
      };
      if (lastBattery !== null) body.battery_pct = lastBattery;
      postJson("/api/sentinel/session/update", body).then(function (res) {
        if (!res.ok && res.body.error === "session_expired") handleEnded("expired");
      }).catch(function () {});
    }

    function pullState() {
      getJson("/api/sentinel/session/" + encodeURIComponent(token) + "/state")
        .then(function (res) {
          if (!res.ok) return;
          var b = res.body;
          $("sn-ttl").textContent = fmtCountdown(b.expires_at - b.server_time);
          $("sn-over-banner").hidden = !b.over_speed_active;

          $("sn-stop-pending-driver").hidden = (b.state !== "STOP_PENDING_DRIVER");
          $("sn-stop-pending-parent").hidden = (b.state !== "STOP_PENDING_PARENT");
          $("sn-stop-request").disabled = (b.state !== "ACTIVE");

          if (b.sos_active) {
            $("sn-sos-active").hidden = false;
            $("sn-sos-ack-line").textContent = b.sos_ack_at
              ? "accusé de réception reçu" : "en attente de l'accusé de réception";
            sosActive = true;
          } else {
            $("sn-sos-active").hidden = true;
            sosActive = false;
          }

          if (b.state === "ACTIVE" || b.state === "STOP_PENDING_PARENT"
              || b.state === "STOP_PENDING_DRIVER") {
            setPill("LIVE", "live");
          }
          if (b.state === "ENDED" || b.state === "EXPIRED") {
            handleEnded(b.state.toLowerCase());
          }
        }).catch(function () { setPill("HORS-LIGNE", "warn"); });
    }

    function handleEnded(reason) {
      if (ended) return;
      ended = true;
      $("sn-ended").hidden = false;
      $("sn-stop-request").disabled = true;
      $("sn-sos-btn").disabled = true;
      setPill(reason === "expired" ? "EXPIRÉ" : "TERMINÉ", "ended");
      if (watchId !== null && navigator.geolocation) navigator.geolocation.clearWatch(watchId);
      if (pushTimer) clearInterval(pushTimer);
      if (stateTimer) clearInterval(stateTimer);
      if (wakeSentinel && wakeSentinel.release) wakeSentinel.release().catch(function () {});
    }

    // SOS hold-to-fire
    (function setupSOS() {
      var btn = $("sn-sos-btn");
      var ring = $("sn-sos-ring");
      var t0 = null, raf = null;
      function tick() {
        var dt = Date.now() - t0;
        var pct = Math.min(100, (dt / holdMs) * 100);
        ring.style.width = pct + "%";
        if (dt >= holdMs) { stop(); fire(); }
        else { raf = requestAnimationFrame(tick); }
      }
      function start() {
        if (sosActive || ended) return;
        t0 = Date.now();
        btn.classList.add("sn-sos--armed");
        raf = requestAnimationFrame(tick);
      }
      function stop() {
        if (raf) cancelAnimationFrame(raf);
        raf = null; t0 = null;
        btn.classList.remove("sn-sos--armed");
        setTimeout(function () { ring.style.width = "0%"; }, 100);
      }
      function fire() {
        postJson("/api/sentinel/session/sos", { token: token })
          .then(function () { $("sn-sos-active").hidden = false; sosActive = true; })
          .catch(function () { showError("Impossible d'envoyer le SOS."); });
      }
      btn.addEventListener("pointerdown", start);
      btn.addEventListener("pointerup", stop);
      btn.addEventListener("pointerleave", stop);
      btn.addEventListener("pointercancel", stop);
    })();

    // Accept / refuse
    $("sn-accept-btn").addEventListener("click", function () {
      var btn = this;
      btn.disabled = true; btn.textContent = "Activation…";
      postJson("/api/sentinel/session/accept", { token: token })
        .then(function (res) {
          if (!res.ok) throw new Error(res.body.error || "accept_failed");
          showCockpit();
        })
        .catch(function (e) {
          showError("Impossible d'activer : " + e.message);
          btn.disabled = false;
          btn.textContent = "✓ J'accepte le trajet protégé";
        });
    });
    $("sn-refuse-btn").addEventListener("click", function () { window.location.href = "/"; });

    // Dual-stop
    $("sn-stop-request").addEventListener("click", function () {
      if (!confirm("Demander la fin du trajet ?\nLe proche devra approuver.")) return;
      postJson("/api/sentinel/session/stop_request", { token: token })
        .then(function () { pullState(); });
    });
    $("sn-stop-approve").addEventListener("click", function () {
      postJson("/api/sentinel/session/stop_approve", { token: token })
        .then(function () { pullState(); });
    });

    // Boot into the right view
    if (initialState !== "PENDING_DRIVER") showCockpit();
  }

  // ───────────────────────────────────────────────── PARENT
  function initParent() {
    var token = document.body.getAttribute("data-token");
    var interval = parseInt(document.body.getAttribute("data-interval"), 10) || 5;

    var map = L.map("sn-map", { zoomControl: true }).setView([36.7, 2.0], 5);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: "© OpenStreetMap contributors"
    }).addTo(map);

    var marker = null, accuracyCircle = null, zoneCircle = null;
    var first = true;
    var ended = false;
    var trail = [];
    var trailLayer = L.polyline([], { color: "#00d4ff", weight: 3, opacity: 0.65 }).addTo(map);

    var labels = {
      "session_created": "Session créée",
      "driver_accepted": "Conducteur a accepté",
      "over_speed": "Vitesse élevée prolongée",
      "over_speed_cleared": "Vitesse revenue à la normale",
      "safe_zone_exit": "Hors zone rassurante",
      "safe_zone_return": "Retour en zone rassurante",
      "signal_lost": "Signal GPS perdu",
      "low_battery": "Batterie faible du conducteur",
      "sos_triggered": "SOS envoyé par le conducteur",
      "sos_acknowledged": "SOS reconnu",
      "stop_requested": "Fin de trajet demandée",
      "stop_approved": "Fin de trajet approuvée",
      "session_expired": "Session expirée"
    };
    function eventLabel(t, p) {
      var base = labels[t] || t;
      if (t === "over_speed" && p && p.speed_kmh && p.limit_kmh) {
        base += " (" + Math.round(p.speed_kmh) + " km/h, limite " + p.limit_kmh + ")";
      }
      if (t === "safe_zone_exit" && p && p.distance_m) {
        base += " (" + Math.round(p.distance_m) + " m)";
      }
      if (t === "low_battery" && p && typeof p.battery_pct === "number") {
        base += " (" + p.battery_pct + " %)";
      }
      return base;
    }
    function timeShort(ts) {
      var d = new Date(ts * 1000);
      return d.getHours().toString().padStart(2, "0") + ":" + d.getMinutes().toString().padStart(2, "0");
    }
    function stateLabel(s) {
      return ({
        "PENDING_DRIVER": "EN ATTENTE",
        "ACTIVE": "EN COURS",
        "STOP_PENDING_PARENT": "VOUS AVEZ DEMANDÉ LA FIN",
        "STOP_PENDING_DRIVER": "LE CONDUCTEUR DEMANDE LA FIN",
        "ENDED": "TERMINÉ",
        "EXPIRED": "EXPIRÉ"
      })[s] || s;
    }
    function pillKindFor(s, sosUnack) {
      if (sosUnack) return "danger";
      if (s === "ACTIVE") return "live";
      if (s === "STOP_PENDING_PARENT" || s === "STOP_PENDING_DRIVER") return "warn";
      if (s === "ENDED" || s === "EXPIRED") return "ended";
      return "";
    }
    function renderEvents(events) {
      var el = $("sn-events");
      if (!events.length) {
        el.innerHTML = "<li class='sn-events-empty'>Aucune alerte pour le moment.</li>";
        return;
      }
      el.innerHTML = events.map(function (e) {
        return "<li class='sn-ev--" + e.event_type + "'>"
          + "<span>" + eventLabel(e.event_type, e.payload) + "</span>"
          + "<span class='sn-ev-time'>" + timeShort(e.created_at) + "</span></li>";
      }).join("");
    }

    function pull() {
      getJson("/api/sentinel/session/" + encodeURIComponent(token) + "/state")
        .then(function (res) {
          if (!res.ok) { setPill(res.body.error || "erreur", "danger"); return; }
          var b = res.body;
          $("sn-driver-name").textContent =
            (b.driver_label || "Conducteur") + " · trajet protégé";

          $("sn-l-limit").textContent = b.speed_limit_kmh;
          $("sn-l-speed").textContent =
            (b.last_speed_kmh !== null && b.last_speed_kmh !== undefined)
              ? Math.round(b.last_speed_kmh) : "—";
          document.querySelector(".sn-speedo-hero")
            .classList.toggle("sn-speedo-hero--over", !!b.over_speed_active);
          $("sn-l-over-banner").hidden = !b.over_speed_active;

          $("sn-l-avg").textContent =
            (b.avg_speed_kmh ? Math.round(b.avg_speed_kmh) : 0) + " km/h";
          $("sn-l-max").textContent =
            (b.max_speed_kmh ? Math.round(b.max_speed_kmh) : 0) + " km/h";
          $("sn-l-head").textContent =
            (b.last_heading_deg !== null && b.last_heading_deg !== undefined)
              ? Math.round(b.last_heading_deg) + "°" : "—";
          $("sn-l-acc").textContent =
            (b.last_accuracy !== null && b.last_accuracy !== undefined)
              ? "± " + Math.round(b.last_accuracy) + " m" : "—";
          $("sn-l-sig").textContent = b.last_signal
            ? ({ excellent: "excellent", good: "bon", fair: "moyen", poor: "faible", unknown: "—" }[b.last_signal] || "—")
            : "—";
          $("sn-l-batt").textContent =
            (b.last_battery_pct !== null && b.last_battery_pct !== undefined)
              ? (b.last_battery_pct + " %") : "—";
          $("sn-l-age").textContent = fmtAge(b.server_time, b.last_update_at);
          $("sn-l-ttl").textContent = fmtCountdown(b.expires_at - b.server_time);

          setPill(stateLabel(b.state) + (b.sos_active ? " · SOS" : ""),
                  pillKindFor(b.state, b.sos_active && !b.sos_ack_at));

          if (b.sos_active && !b.sos_ack_at) {
            $("sn-sos-banner").hidden = false;
            $("sn-sos-by").textContent = b.driver_label || "le conducteur";
          } else {
            $("sn-sos-banner").hidden = true;
          }

          $("sn-stop-pending-parent").hidden = (b.state !== "STOP_PENDING_PARENT");
          $("sn-stop-pending-driver").hidden = (b.state !== "STOP_PENDING_DRIVER");
          $("sn-stop-request").disabled = (b.state !== "ACTIVE");

          renderEvents(b.events || []);

          // Map
          if (b.safe_zone && !zoneCircle) {
            zoneCircle = L.circle([b.safe_zone.lat, b.safe_zone.lon], {
              radius: b.safe_zone.radius_m,
              color: "#2bf0a0", weight: 1, fillOpacity: 0.06
            }).addTo(map);
          }
          if (b.last_lat !== null && b.last_lon !== null
              && b.last_lat !== undefined && b.last_lon !== undefined) {
            var p = [b.last_lat, b.last_lon];
            var acc = Math.max(5, b.last_accuracy || 50);
            if (!marker) {
              marker = L.marker(p).addTo(map);
              accuracyCircle = L.circle(p, {
                radius: acc, color: "#00d4ff", weight: 1, fillOpacity: 0.15
              }).addTo(map);
            } else {
              marker.setLatLng(p);
              accuracyCircle.setLatLng(p);
              accuracyCircle.setRadius(acc);
            }
            trail.push(p);
            if (trail.length > 600) trail.shift();
            trailLayer.setLatLngs(trail);
            if (first) { map.setView(p, 15); first = false; }
          }

          if ((b.state === "ENDED" || b.state === "EXPIRED") && !ended) {
            ended = true;
            $("sn-ended").hidden = false;
            $("sn-stop-request").disabled = true;
          }
        }).catch(function () { setPill("HORS-LIGNE", "warn"); });
    }

    $("sn-sos-ack").addEventListener("click", function () {
      postJson("/api/sentinel/session/sos_ack", { token: token }).then(pull);
    });
    $("sn-stop-request").addEventListener("click", function () {
      if (!confirm("Demander la fin du trajet ?\nLe conducteur devra approuver.")) return;
      postJson("/api/sentinel/session/stop_request", { token: token }).then(pull);
    });
    $("sn-stop-approve").addEventListener("click", function () {
      postJson("/api/sentinel/session/stop_approve", { token: token }).then(pull);
    });

    pull();
    setInterval(pull, Math.max(2, interval) * 1000);
  }

  // ───────────────────────────────────────────────── dispatch
  document.addEventListener("DOMContentLoaded", function () {
    var page = document.body.getAttribute("data-page");
    if (page === "landing") return initLanding();
    if (page === "driver")  return initDriver();
    if (page === "parent")  return initParent();
  });
})();
