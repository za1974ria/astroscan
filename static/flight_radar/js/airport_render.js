/* FLIGHT RADAR — Airport HUD renderer.
   Cyan SpaceX-clean panel with live traffic within 100 km.
*/
(function (global) {
  "use strict";

  var I18N = {
    fr: {
      airport_locked: "AÉROPORT VERROUILLÉ",
      identification: "IDENTIFICATION",
      iata: "IATA", icao: "ICAO", timezone: "FUSEAU",
      country: "PAYS",
      position: "POSITION",
      latitude: "LATITUDE", longitude: "LONGITUDE", altitude: "ALTITUDE",
      live_traffic: "TRAFIC LIVE — RAYON 100 KM",
      total: "TRAFIC TOTAL",
      arrivals: "ARRIVÉES",
      departures: "DÉPARTS",
      on_ground: "AU SOL",
      transit: "TRANSIT",
      flights_arr: "VOLS EN APPROCHE",
      flights_dep: "VOLS AU DÉPART",
      flights_gnd: "AVIONS AU SOL",
      flights_xs: "TRAFIC EN TRANSIT",
      none_in_radius: "Aucun avion détecté",
      distance: "km", source: "Source",
      source_value: "OpenSky · ADS-B",
      refreshed: "rafraîchi à l'instant",
    },
    en: {
      airport_locked: "AIRPORT LOCKED",
      identification: "IDENTIFICATION",
      iata: "IATA", icao: "ICAO", timezone: "TIMEZONE",
      country: "COUNTRY",
      position: "POSITION",
      latitude: "LATITUDE", longitude: "LONGITUDE", altitude: "ALTITUDE",
      live_traffic: "LIVE TRAFFIC — 100 KM RADIUS",
      total: "TOTAL TRAFFIC",
      arrivals: "ARRIVING",
      departures: "DEPARTING",
      on_ground: "ON GROUND",
      transit: "TRANSIT",
      flights_arr: "INBOUND FLIGHTS",
      flights_dep: "OUTBOUND FLIGHTS",
      flights_gnd: "AIRCRAFT ON GROUND",
      flights_xs: "TRANSIT TRAFFIC",
      none_in_radius: "No aircraft detected",
      distance: "km", source: "Source",
      source_value: "OpenSky · ADS-B",
      refreshed: "just refreshed",
    },
  };

  function t(lang, k) {
    return (I18N[lang] || I18N.fr)[k] || k;
  }
  function escapeHtml(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"})[c];
    });
  }
  function fmtCoord(v, suffPos, suffNeg) {
    var n = Number(v);
    if (!isFinite(n)) return "—";
    return Math.abs(n).toFixed(4) + "° " + (n >= 0 ? suffPos : suffNeg);
  }
  function fmtFlightItem(f) {
    var alt = f.alt_m ? (f.alt_m + " m") : "—";
    var spd = f.speed_kmh ? (f.speed_kmh + " km/h") : "—";
    var meta = alt;
    if (f.vario_fpm) {
      var arrow = f.vario_fpm > 0 ? "▲" : "▼";
      meta += " · " + arrow + " " + Math.abs(f.vario_fpm) + " ft/min";
    }
    meta += " · " + spd;
    return ""
      + "<div class='airport-flight-item' data-icao24='" + escapeHtml(f.icao24) + "'>"
      +   "<span class='cs'>" + escapeHtml(f.callsign) + "</span>"
      +   "<span class='meta'>" + meta + "</span>"
      +   "<span class='dist'>" + f.distance_km + " km</span>"
      + "</div>";
  }

  function flagEmoji(iso) {
    if (!iso || iso.length !== 2) return "";
    var A = 0x1F1E6, ord = function (c) { return c.charCodeAt(0) - 65; };
    return String.fromCodePoint(A + ord(iso[0])) + String.fromCodePoint(A + ord(iso[1]));
  }

  function renderAirportPanel(hudEl, payload, lang, onAircraftClick) {
    lang = lang || "fr";
    if (!hudEl || !payload || !payload.airport) return;

    var ap = payload.airport;
    var lt = payload.live_traffic || {};
    var st = payload.stats_summary || {};
    var name = lang === "en" ? (ap.name_en || ap.name_fr) : (ap.name_fr || ap.name_en);

    var html = ""
      + "<div class='airport-hud-header'>"
      +   "<span class='airport-hud-title'>" + t(lang, "airport_locked") + "</span>"
      +   "<button class='airport-hud-close' data-action='close' aria-label='close'>✕</button>"
      + "</div>"
      + "<div class='airport-hud-iata'>" + escapeHtml(ap.iata || "") + "</div>"
      + "<div class='airport-hud-name'>" + escapeHtml(name || "") + "</div>"
      + "<div class='airport-hud-country'>"
      +   (ap.country_iso ? flagEmoji(ap.country_iso) + " " + escapeHtml(ap.country_iso) : "")
      +   (ap.city ? " · " + escapeHtml(ap.city) : "")
      + "</div>"
      + "<div class='airport-section'>"
      +   "<div class='airport-section-title'>" + t(lang, "identification") + "</div>"
      +   "<div class='airport-row'><span class='k'>" + t(lang, "iata") + "</span><span class='v'>" + escapeHtml(ap.iata || "—") + "</span></div>"
      +   "<div class='airport-row'><span class='k'>" + t(lang, "icao") + "</span><span class='v'>" + escapeHtml(ap.icao || "—") + "</span></div>"
      +   (ap.timezone
            ? "<div class='airport-row'><span class='k'>" + t(lang, "timezone") + "</span><span class='v'>" + escapeHtml(ap.timezone) + "</span></div>"
            : "")
      + "</div>"
      + "<div class='airport-section'>"
      +   "<div class='airport-section-title'>" + t(lang, "position") + "</div>"
      +   "<div class='airport-row'><span class='k'>" + t(lang, "latitude") + "</span><span class='v'>" + fmtCoord(ap.lat, "N", "S") + "</span></div>"
      +   "<div class='airport-row'><span class='k'>" + t(lang, "longitude") + "</span><span class='v'>" + fmtCoord(ap.lon, "E", "W") + "</span></div>"
      +   (ap.altitude_m != null
            ? "<div class='airport-row'><span class='k'>" + t(lang, "altitude") + "</span><span class='v'>" + ap.altitude_m + " m</span></div>"
            : "")
      + "</div>"
      + "<div class='airport-section'>"
      +   "<div class='airport-section-title'>" + t(lang, "live_traffic") + "</div>"
      +   "<div class='airport-traffic-grid'>"
      +     trafficCell("approaching", "✈️↘", st.approaching_count || 0, t(lang, "arrivals"))
      +     trafficCell("departing",   "🛫↗", st.departing_count   || 0, t(lang, "departures"))
      +     trafficCell("on_ground",   "🛬",   st.on_ground_count   || 0, t(lang, "on_ground"))
      +     trafficCell("transit",     "✈️",  st.transit_count     || 0, t(lang, "transit"))
      +   "</div>"
      +   "<div class='airport-row big' style='margin-top:12px'>"
      +     "<span class='k'>" + t(lang, "total") + "</span>"
      +     "<span class='v big'>" + (st.total_within_100km || 0) + "</span>"
      +   "</div>"
      + "</div>"
      + flightsList(lt.approaching, t(lang, "flights_arr"), t(lang, "none_in_radius"))
      + flightsList(lt.departing,   t(lang, "flights_dep"), t(lang, "none_in_radius"))
      + flightsList(lt.on_ground,   t(lang, "flights_gnd"), t(lang, "none_in_radius"))
      + flightsList(lt.transit,     t(lang, "flights_xs"),  t(lang, "none_in_radius"))
      + "<div class='airport-source'>"
      +   t(lang, "source") + " · " + t(lang, "source_value")
      +   "<span class='live-dot'></span>"
      + "</div>";

    hudEl.innerHTML = html;
    hudEl.removeAttribute("hidden");

    var closeBtn = hudEl.querySelector("[data-action='close']");
    if (closeBtn) {
      closeBtn.addEventListener("click", function () {
        hudEl.dispatchEvent(new CustomEvent("airport-hud-close"));
      });
    }
    if (typeof onAircraftClick === "function") {
      hudEl.querySelectorAll(".airport-flight-item").forEach(function (item) {
        item.addEventListener("click", function () {
          var icao24 = item.getAttribute("data-icao24");
          if (icao24) onAircraftClick(icao24);
        });
      });
    }
  }

  function trafficCell(cat, icon, count, label) {
    var emptyClass = count === 0 ? " empty" : "";
    return ""
      + "<div class='airport-traffic-cell" + emptyClass + "' data-cat='" + cat + "'>"
      +   "<div class='cell-icon'>" + icon + "</div>"
      +   "<div class='cell-count'>" + count + "</div>"
      +   "<div class='cell-label'>" + escapeHtml(label) + "</div>"
      + "</div>";
  }

  function flightsList(flights, sectionTitle, emptyMsg) {
    if (!flights || !flights.length) {
      return ""
        + "<div class='airport-section'>"
        +   "<div class='airport-section-title'>" + escapeHtml(sectionTitle) + "</div>"
        +   "<div style='font-size:10px;color:rgba(0,200,232,0.5);font-style:italic;padding:6px 0'>"
        +     escapeHtml(emptyMsg)
        +   "</div>"
        + "</div>";
    }
    var html = ""
      + "<div class='airport-section'>"
      +   "<div class='airport-section-title'>" + escapeHtml(sectionTitle) + " <span style='color:rgba(0,200,232,0.6)'>(" + flights.length + ")</span></div>"
      +   "<div class='airport-flights-list'>";
    flights.forEach(function (f) { html += fmtFlightItem(f); });
    html += "</div></div>";
    return html;
  }

  global.FRAirportRender = { render: renderAirportPanel };
})(window);
