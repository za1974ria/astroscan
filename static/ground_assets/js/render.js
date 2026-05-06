/* ============================================================
   GROUND ASSETS — render helpers
   Pure rendering: detail panel, mission-control stream, recent
   activity, formatters. Consumes window.GroundAssets.state.
   ============================================================ */
(function () {
  'use strict';

  const STREAM_MAX = 50;

  function escapeHTML(s) {
    if (s === null || s === undefined) return '';
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function fmtCoords(lat, lon) {
    const ns = lat >= 0 ? 'N' : 'S';
    const ew = lon >= 0 ? 'E' : 'W';
    return Math.abs(lat).toFixed(3) + '° ' + ns + ', ' +
           Math.abs(lon).toFixed(3) + '° ' + ew;
  }

  function fmtFreq(mhz) {
    if (!mhz) return '—';
    if (mhz >= 1000) return (mhz / 1000).toFixed(3) + ' GHz';
    return mhz.toFixed(3) + ' MHz';
  }

  function fmtTime(iso) {
    try {
      const d = new Date(iso);
      return ('0' + d.getUTCHours()).slice(-2) + ':' +
             ('0' + d.getUTCMinutes()).slice(-2) + ':' +
             ('0' + d.getUTCSeconds()).slice(-2);
    } catch (e) { return '--:--:--'; }
  }

  function rssiPercent(rssi) {
    return Math.max(0, Math.min(100, ((rssi + 110) / 70) * 100));
  }

  function detailRow(k, v, cls) {
    cls = cls || '';
    return (
      '<div class="ga-detail-row">' +
        '<div class="k">' + escapeHTML(k) + '</div>' +
        '<div class="v ' + cls + '">' + escapeHTML(String(v)) + '</div>' +
      '</div>'
    );
  }

  function renderDetailHTML(asset, kind, net, t) {
    const closeBtn =
      '<button class="ga-detail-close" aria-label="close">' + t('detail_close') + '</button>';
    const typeColor = kind === 'mission' ? 'cyan' : (kind === 'balloon' ? 'white' : '');
    const typeLabel =
      kind === 'mission' ? t('type_mission')
      : (kind === 'balloon' ? t('type_balloon') : t('type_observatory'));

    let rows = '';
    rows += detailRow(t('k_coords'), fmtCoords(asset.lat, asset.lon), 'accent');

    if (kind === 'observatory') {
      rows += detailRow(t('k_elev'), asset.elevation_m + ' m');
      rows += detailRow(t('k_telescope'), asset.telescope || '—');
      rows += detailRow(t('k_freq'), fmtFreq(asset.frequency_mhz));
      rows += detailRow(t('k_status'), asset.status_label || asset.status || '—');
      rows += detailRow(
        t('k_sun'),
        (asset.sun_altitude_deg >= 0 ? '+' : '') + asset.sun_altitude_deg + '°'
      );
      rows += detailRow(t('k_dist_home'), Math.round(asset.distance_from_home_km) + ' km');
    } else if (kind === 'mission') {
      rows += detailRow(t('k_callsign'), asset.callsign, 'cyan');
      rows += detailRow(t('k_target'), asset.target);
      rows += detailRow(t('k_vehicle'), asset.vehicle);
      rows += detailRow(t('k_speed'), asset.speed_kmh.toFixed(1) + ' km/h');
      rows += detailRow(t('k_heading'), asset.heading_deg.toFixed(0) + '°');
      rows += detailRow(t('k_freq'), fmtFreq(asset.frequency_mhz));
      if (asset.current_leg) {
        rows += detailRow(
          t('k_leg'),
          asset.current_leg.from + ' → ' + asset.current_leg.to +
          ' (' + Math.round(asset.current_leg.progress * 100) + '%)',
          'muted'
        );
      }
    } else if (kind === 'balloon') {
      rows += detailRow(t('k_callsign'), asset.callsign, 'cyan');
      rows += detailRow(t('k_stage'), (asset.stage || '').toUpperCase());
      rows += detailRow(t('k_elev'), Math.round(asset.altitude_m) + ' m');
      rows += detailRow(
        t('k_vspeed'),
        (asset.vertical_speed_ms >= 0 ? '+' : '') +
        asset.vertical_speed_ms.toFixed(1) + ' m/s'
      );
      rows += detailRow(t('k_freq'), fmtFreq(asset.frequency_mhz));
    }

    rows += detailRow(
      t('k_last'),
      new Date(net.timestamp).toISOString().substr(11, 8) + ' UTC',
      'muted'
    );

    let equipBlock = '';
    const items = asset.equipment || asset.payload;
    if (items && items.length) {
      const label = kind === 'balloon' ? t('k_payload') : t('k_equip');
      equipBlock =
        '<div class="ga-focus-section">' +
        '<h3>' + label + '</h3>' +
        '<ul class="ga-equip">' +
        items.map(function (i) { return '<li>' + escapeHTML(i) + '</li>'; }).join('') +
        '</ul></div>';
    }

    let linksBlock = '';
    if (kind === 'mission' || kind === 'balloon') {
      const targetLinks = (net.antennas || []).filter(function (l) {
        return l.target_id === asset.id;
      });
      if (targetLinks.length) {
        const obsById = {};
        (net.observatories || []).forEach(function (o) { obsById[o.id] = o; });
        const rowsHTML = targetLinks.map(function (l) {
          const o = obsById[l.obs_id] || { name: l.obs_id };
          const pct = rssiPercent(l.rssi_dbm);
          return (
            '<div class="ga-rssi-row">' +
              '<div>' +
                '<div style="color:' +
                  (l.primary ? 'var(--ga-gold)' : 'var(--ga-text-dim)') +
                  ';font-size:10px;letter-spacing:1.2px">' +
                  escapeHTML(o.name) +
                '</div>' +
                '<div class="ga-rssi-bar">' +
                  '<div class="ga-rssi-fill" style="width:' + pct + '%"></div>' +
                '</div>' +
              '</div>' +
              '<div class="ga-rssi-val">' +
                l.rssi_dbm.toFixed(0) + ' dBm · ' +
                Math.round(l.distance_km) + ' km' +
              '</div>' +
            '</div>'
          );
        }).join('');
        linksBlock =
          '<div class="ga-focus-section">' +
          '<h3>' + t('k_links') + '</h3>' +
          rowsHTML +
          '</div>';
      }
    }

    return (
      '<div class="ga-detail-header">' +
        closeBtn +
        '<div class="ga-detail-type ' + typeColor + '">' + typeLabel + '</div>' +
        '<div class="ga-detail-name">' + escapeHTML(asset.name) + '</div>' +
        '<div class="ga-detail-operator">' + escapeHTML(asset.operator || '') + '</div>' +
      '</div>' +
      '<div class="ga-focus-section">' + rows + '</div>' +
      equipBlock +
      linksBlock
    );
  }

  function renderRecent(events, lang) {
    const box = document.getElementById('ga-recent-list');
    if (!box) return;
    const top = events.slice(0, 6);
    if (!top.length) { box.innerHTML = ''; return; }
    box.innerHTML = top.map(function (e) {
      const dotCls =
        e.source && /BAL|BALLOON/i.test(e.source) ? '' :
        e.source && /CAIRO|RAD|AUR/i.test(e.source) ? 'cyan' : 'gold';
      const msg = lang === 'en' ? e.message_en : e.message_fr;
      return (
        '<div class="ga-recent-row">' +
          '<div class="ga-recent-dot ' + dotCls + '"></div>' +
          '<div>' +
            '<div style="color:var(--ga-text);font-size:10.5px">' +
              escapeHTML(msg) +
            '</div>' +
            '<div style="color:var(--ga-text-mute);font-size:9.5px;letter-spacing:1.2px">' +
              escapeHTML(e.source || '') +
            '</div>' +
          '</div>' +
        '</div>'
      );
    }).join('');
  }

  // Extract a dBm reading from a free-form message. Returns null if absent.
  function extractRssiDbm(text) {
    if (!text) return null;
    const m = String(text).match(/(-\d{2,3})\s*dBm/i);
    if (!m) return null;
    const v = parseInt(m[1], 10);
    return isFinite(v) ? v : null;
  }

  // Map RSSI dBm → CSS class (premium graduated colors).
  //   > -70  excellent (green)
  //   -70 ↔ -85   good (gold)
  //   -85 ↔ -100  weak (amber)
  //   < -100 critical (red)
  function rssiClass(dbm) {
    if (dbm === null || dbm === undefined) return '';
    if (dbm > -70) return 'rssi-excellent';
    if (dbm > -85) return 'rssi-good';
    if (dbm > -100) return 'rssi-weak';
    return 'rssi-critical';
  }

  function renderStream(events, lang, dedupSet) {
    const body = document.getElementById('ga-stream-body');
    if (!body) return;
    const fresh = [];
    for (let i = 0; i < events.length; i++) {
      const e = events[i];
      const k = e.timestamp + '|' + e.source + '|' + (e.message_en || '');
      if (dedupSet.has(k)) continue;
      dedupSet.add(k);
      fresh.push(e);
    }
    if (!fresh.length) return;
    fresh.forEach(function (e) {
      const row = document.createElement('div');
      const msg = lang === 'en' ? e.message_en : e.message_fr;
      const dbm = (typeof e.rssi_dbm === 'number') ? e.rssi_dbm : extractRssiDbm(msg);
      const rcls = rssiClass(dbm);
      const cls = ['ga-stream-row'];
      if (e.level === 'warn') cls.push('warn');
      if (e.level === 'error') cls.push('error');
      if (rcls) cls.push(rcls);
      row.className = cls.join(' ');
      // Wire click-to-focus when the event names a station.
      const stationId = e.source_id || e.station_id || null;
      if (stationId) row.setAttribute('data-station', stationId);
      const srcCls =
        e.source && /BAL|BALLOON/i.test(e.source) ? 'white' :
        e.source && /CAIRO|RAD|AUR|ICE/i.test(e.source) ? 'cyan' : '';
      row.innerHTML =
        '<span class="ts">' + escapeHTML(fmtTime(e.timestamp)) + '</span>' +
        '<span class="src ' + srcCls + '">' + escapeHTML(e.source || '') + '</span>' +
        '<span class="msg">' + escapeHTML(msg || '') + '</span>';
      body.insertBefore(row, body.firstChild);
    });
    while (body.children.length > STREAM_MAX) body.removeChild(body.lastChild);
    // Auto-scroll to top (newest) if user wasn't reading older entries.
    if (body.scrollTop < 24) body.scrollTop = 0;
  }

  // Render the right-panel STATIONS DETAIL list — clickable observatory rows.
  function renderStations(net, t, onSelect) {
    const box = document.getElementById('ga-stations-detail');
    if (!box) return;
    const obs = (net && net.observatories) || [];
    if (!obs.length) {
      box.innerHTML =
        '<div style="color:var(--ga-text-mute);font-family:var(--ga-mono);' +
        'font-size:10px;padding:10px 12px">—</div>';
      return;
    }
    // Best (max) RSSI per observatory across all its links.
    const bestRssi = {};
    (net.antennas || []).forEach(function (l) {
      const v = (typeof l.rssi_dbm === 'number') ? l.rssi_dbm : null;
      if (v === null) return;
      if (bestRssi[l.obs_id] === undefined || v > bestRssi[l.obs_id]) {
        bestRssi[l.obs_id] = v;
      }
    });
    box.innerHTML = obs.map(function (o) {
      const status = (o.status || '').toLowerCase();
      let ledCls = 'online';
      if (status === 'maintenance') ledCls = 'maint';
      else if (status === 'standby') ledCls = 'standby';
      const dbm = bestRssi[o.id];
      const rssiTxt = (typeof dbm === 'number')
        ? dbm.toFixed(0) + ' dBm'
        : '—';
      const rssiCls = (typeof dbm === 'number') ? '' : 'silent';
      const meta = (o.status_label || o.status || '').toUpperCase();
      return (
        '<div class="ga-station-row" data-station-id="' + escapeHTML(o.id) + '">' +
          '<span class="ga-station-led ' + ledCls + '"></span>' +
          '<div>' +
            '<div class="ga-station-name">' + escapeHTML(o.name) + '</div>' +
            '<div class="ga-station-meta">' + escapeHTML(meta) + '</div>' +
          '</div>' +
          '<div class="ga-station-rssi ' + rssiCls + '">' + escapeHTML(rssiTxt) + '</div>' +
        '</div>'
      );
    }).join('');
    if (typeof onSelect === 'function') {
      box.querySelectorAll('.ga-station-row').forEach(function (row) {
        row.addEventListener('click', function () {
          const id = row.getAttribute('data-station-id');
          if (id) onSelect(id);
        });
      });
    }
  }

  window.GroundAssetsRender = {
    escapeHTML: escapeHTML,
    fmtCoords: fmtCoords,
    fmtFreq: fmtFreq,
    fmtTime: fmtTime,
    rssiPercent: rssiPercent,
    detailRow: detailRow,
    renderDetailHTML: renderDetailHTML,
    renderRecent: renderRecent,
    renderStream: renderStream,
    renderStations: renderStations,
    extractRssiDbm: extractRssiDbm,
    rssiClass: rssiClass,
    STREAM_MAX: STREAM_MAX,
  };
})();
