var _sondesData = {};

/** Carte ISS — fond Blue Marble + grille + position (même logique qu'observatoire.html) */
function drawISSCanvasModal(canvasId, data) {
  var canvas = document.getElementById(canvasId);
  if (!canvas) return;
  var ctx = canvas.getContext('2d');
  var W = canvas.width, H = canvas.height;

  var lat = parseFloat(data.latitude||data.lat||0);
  var lon = parseFloat(data.longitude||data.lon||0);
  lat = Math.round(lat*100)/100;
  lon = Math.round(lon*100)/100;

  var img = new Image();
  img.crossOrigin = 'anonymous';
  img.onload = function() {
    ctx.drawImage(img, 0, 0, W, H);

    // Grille
    ctx.strokeStyle = 'rgba(0,255,136,0.15)';
    ctx.lineWidth = 0.5;
    for(var x=0;x<W;x+=W/12){ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,H);ctx.stroke();}
    for(var y=0;y<H;y+=H/6){ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(W,y);ctx.stroke();}

    // Équateur
    ctx.strokeStyle='rgba(0,255,136,0.4)';
    ctx.setLineDash([4,4]);
    ctx.beginPath();ctx.moveTo(0,H/2);ctx.lineTo(W,H/2);ctx.stroke();
    ctx.setLineDash([]);

    // Position ISS
    var px = ((lon+180)/360)*W;
    var py = ((90-lat)/180)*H;

    // Trajet orbital
    ctx.strokeStyle='rgba(0,255,136,0.5)';
    ctx.lineWidth=1.5;
    ctx.setLineDash([4,4]);
    ctx.beginPath();
    ctx.moveTo(px-150,py+35);
    ctx.bezierCurveTo(px-70,py-25,px+70,py+25,px+150,py-35);
    ctx.stroke();
    ctx.setLineDash([]);

    // Point ISS
    ctx.shadowColor='#00ff88';
    ctx.shadowBlur=20;
    ctx.fillStyle='#00ff88';
    ctx.beginPath();ctx.arc(px,py,7,0,Math.PI*2);ctx.fill();
    ctx.shadowBlur=0;
    ctx.font='18px Arial';
    ctx.fillText('🛸',px-10,py-12);
    ctx.fillStyle='#00ff88';
    ctx.font='bold 11px monospace';
    ctx.fillText('ISS',px+12,py+4);

    // Coords
    var elLat=document.getElementById(canvasId.replace('-canvas','-lat'));
    var elLon=document.getElementById(canvasId.replace('-canvas','-lon'));
    var elAlt=document.getElementById(canvasId.replace('-canvas','-alt'));
    if(elLat)elLat.textContent=lat.toFixed(2);
    if(elLon)elLon.textContent=lon.toFixed(2);
    if(elAlt)elAlt.textContent=parseFloat(data.altitude||data.altitude_km||408).toFixed(1);
  };
  img.onerror = function() {
    // Fallback fond sombre + continents (formes précises)
    ctx.fillStyle='#000a1a';
    ctx.fillRect(0,0,W,H);
    ctx.fillStyle='#0a2a1a';ctx.strokeStyle='#00ff8833';ctx.lineWidth=1;
    // Amérique Nord
    ctx.beginPath();
    ctx.moveTo(W*0.08,H*0.12);ctx.lineTo(W*0.22,H*0.08);
    ctx.lineTo(W*0.26,H*0.15);ctx.lineTo(W*0.24,H*0.35);
    ctx.lineTo(W*0.18,H*0.45);ctx.lineTo(W*0.08,H*0.42);
    ctx.closePath();ctx.fill();ctx.stroke();
    // Amérique Sud
    ctx.beginPath();
    ctx.moveTo(W*0.14,H*0.52);ctx.lineTo(W*0.22,H*0.50);
    ctx.lineTo(W*0.24,H*0.65);ctx.lineTo(W*0.18,H*0.85);
    ctx.lineTo(W*0.12,H*0.80);ctx.closePath();ctx.fill();ctx.stroke();
    // Europe
    ctx.beginPath();
    ctx.moveTo(W*0.43,H*0.12);ctx.lineTo(W*0.52,H*0.10);
    ctx.lineTo(W*0.54,H*0.25);ctx.lineTo(W*0.48,H*0.35);
    ctx.lineTo(W*0.43,H*0.28);ctx.closePath();ctx.fill();ctx.stroke();
    // Afrique
    ctx.beginPath();
    ctx.moveTo(W*0.44,H*0.32);ctx.lineTo(W*0.54,H*0.30);
    ctx.lineTo(W*0.56,H*0.55);ctx.lineTo(W*0.50,H*0.78);
    ctx.lineTo(W*0.44,H*0.70);ctx.closePath();ctx.fill();ctx.stroke();
    // Asie
    ctx.beginPath();
    ctx.moveTo(W*0.54,H*0.08);ctx.lineTo(W*0.82,H*0.06);
    ctx.lineTo(W*0.86,H*0.20);ctx.lineTo(W*0.78,H*0.45);
    ctx.lineTo(W*0.60,H*0.48);ctx.lineTo(W*0.54,H*0.30);
    ctx.closePath();ctx.fill();ctx.stroke();
    // Océanie
    ctx.beginPath();
    ctx.moveTo(W*0.72,H*0.55);ctx.lineTo(W*0.84,H*0.53);
    ctx.lineTo(W*0.86,H*0.70);ctx.lineTo(W*0.74,H*0.72);
    ctx.closePath();ctx.fill();ctx.stroke();
    var px=((lon+180)/360)*W;
    var py=((90-lat)/180)*H;
    ctx.fillStyle='#00ff88';
    ctx.beginPath();ctx.arc(px,py,7,0,Math.PI*2);ctx.fill();
    ctx.fillText('🛸 ISS',px+10,py);
  };
  img.src = '/static/earth_texture.jpg';
}

function closeSondeModal() {
  document.getElementById('sonde-modal').style.display = 'none';
}

function openSondeModal(k) {
  var m = document.getElementById('sonde-modal');
  m.style.display = 'flex';
  renderSondeNav(k);
  renderSondeLive(k);
}

function renderSondeNav(active) {
  var nav = document.getElementById('sonde-nav');
  var labels = {voyager1:'🛸 Voyager 1',voyager2:'🛸 Voyager 2',perseverance:'🤖 Perseverance',curiosity:'🔬 Curiosity',iss:'🛰️ ISS',jwst:'🔭 JWST',hubble:'🌌 Hubble',parker:'☀️ Parker',bepi:'🪐 BepiColombo',chang_e:"🌕 Chang'e",lro:'🌑 LRO Lune'};
  var colors = {voyager1:'#00ffe7',voyager2:'#00bfff',perseverance:'#ff6a00',curiosity:'#ff4444',iss:'#39ff14',jwst:'#c084fc',hubble:'#00bfff',parker:'#ffe600',bepi:'#ff9500',chang_e:'#ffcc00',lro:'#aaaaff'};
  var html = '';
  Object.keys(labels).forEach(function(k) {
    var c = active===k ? colors[k] : '#333';
    var tc = active===k ? colors[k] : '#667788';
    html += '<button onclick="openSondeModal(\''+k+'\')" style="background:transparent;border:1px solid '+c+';color:'+tc+';padding:4px 12px;border-radius:20px;font-family:monospace;font-size:10px;cursor:pointer;margin:2px">'+labels[k]+'</button>';
  });
  nav.innerHTML = html;
}

function renderSondeLive(k) {
  var el = document.getElementById('sonde-live-content');
  var colors = {voyager1:'#00ffe7',voyager2:'#00bfff',perseverance:'#ff6a00',curiosity:'#ff4444',iss:'#39ff14',jwst:'#c084fc',hubble:'#00bfff',parker:'#ffe600',bepi:'#ff9500',chang_e:'#ffcc00',lro:'#aaaaff'};
  var c = colors[k] || '#00ff88';
  el.innerHTML = '<div style="color:'+c+';font-family:monospace;font-size:11px;text-align:center;padding:40px">⟳ CONNEXION NASA/JPL...</div>';
  
  fetch('/api/sondes').then(function(r){ return r.json(); }).then(function(data) {
    _sondesData = data;
    var d = data[k] || {};
    document.getElementById('sonde-modal-inner').style.borderTopColor = c;
    
    var html = '<div style="font-family:Orbitron,monospace;font-size:13px;color:'+c+';letter-spacing:3px;margin-bottom:16px">'+(d.name||k.toUpperCase())+'</div>';
    
    if(k==='iss') {
      html += '<div style="text-align:center;font-size:40px;margin-bottom:10px">🛸</div>';
      html += '<div style="text-align:center;font-family:Orbitron,monospace;font-size:11px;color:#39ff14;letter-spacing:3px;margin-bottom:14px">STATION SPATIALE INTERNATIONALE</div>';
      html += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:14px">';
      [['LAT',(d.lat||0).toFixed(2)+'°'],['LON',(d.lon||0).toFixed(2)+'°'],['ALT',parseFloat(d.altitude_km||408).toFixed(1)+' km'],['VITESSE',parseFloat(d.speed_kms||7.66).toFixed(2)+' km/s'],['ÉQUIPAGE',(d.crew_count||d.crew&&d.crew.length||7)+' 👨‍🚀'],['ORBITE','LEO ~420 km']].forEach(function(r){
        html += '<div style="background:rgba(57,255,20,0.05);border:1px solid #39ff1433;border-radius:8px;padding:10px;text-align:center"><div style="font-size:8px;color:#4a7a8a;margin-bottom:4px">'+r[0]+'</div><div style="font-size:13px;color:#39ff14">'+r[1]+'</div></div>';
      });
      html += '</div>';
      html += '<div style="border:1px solid #39ff1433;border-radius:8px;overflow:hidden;margin-bottom:10px">';
      html += '<div style="font-size:9px;color:#39ff14;padding:8px;letter-spacing:2px">🗺️ POSITION ISS EN TEMPS RÉEL</div>';
      html += '<canvas id="iss-obs-canvas" width="900" height="400" style="width:100%;height:280px;background:#000a1a;display:block"></canvas>';
      html += '<div style="text-align:center;color:#00ff88;font-size:11px;padding:6px">LAT: <span id="iss-obs-lat">--</span>° | LON: <span id="iss-obs-lon">--</span>° | ALT: <span id="iss-obs-alt">--</span> km</div>';
      html += '</div>';
      html += '<div style="text-align:center;margin:16px 0">';
      html += '<a href="https://www.n2yo.com/space-station/" target="_blank" style="display:inline-block;background:linear-gradient(135deg,#39ff14,#00ff88);color:#000;padding:14px 32px;border-radius:10px;font-family:Orbitron,monospace;font-size:13px;text-decoration:none;font-weight:bold;letter-spacing:2px;box-shadow:0 0 20px #39ff1466">🌍 OUVRIR TRACKER ISS + CAMÉRA LIVE</a>';
      html += '<div style="color:#4a7a8a;font-size:9px;margin-top:6px;font-family:monospace">Carte Leaflet + NASA Live + Passages ISS</div>';
      html += '</div>';
      el.innerHTML = html;
      if(k==='iss'){ setTimeout(function(){ if(typeof drawISSCanvasModal==='function') drawISSCanvasModal('iss-obs-canvas',d); }, 100); }
      return;
    }
    else if(k==='voyager1'||k==='voyager2') {
      var distLight = ((d.distance_au||163)*149597870.7/299792.458/3600).toFixed(1);
      html += '<div style="text-align:center;padding:24px;background:rgba(0,255,231,0.03);border:1px solid '+c+'22;border-radius:10px;margin-bottom:16px">';
      html += '<div style="font-size:3rem;margin-bottom:8px">🛸</div>';
      html += '<div style="font-family:Orbitron,monospace;font-size:32px;color:'+c+';margin-bottom:6px">'+(d.distance_au||0)+' AU</div>';
      html += '<div style="font-family:monospace;font-size:10px;color:#4a7a8a">soit '+Number(d.distance_km||0).toLocaleString()+' km</div>';
      html += '<div style="font-family:monospace;font-size:11px;color:#ff6a00;margin-top:8px">📻 Signal radio : '+distLight+'h de trajet</div>';
      html += '<div style="margin-top:14px;height:6px;background:rgba(0,255,231,0.08);border-radius:3px;overflow:hidden">';
      html += '<div style="height:100%;width:'+Math.min(100,(d.distance_au||163)/200*100)+'%;background:linear-gradient(90deg,'+c+',#00bfff);border-radius:3px"></div></div>';
      html += '</div>';
      html += '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px">';
      [['VITESSE',(d.speed_kms||17)+' km/s'],['LANCÉE','1977'],['ÉTAT',d.status||'N/A'],['SIGNAL',distLight+'h'],['SOURCE','NASA JPL'],['DESTINATION','Étoiles']].forEach(function(row) {
        html += '<div style="background:rgba(0,20,40,0.8);border:1px solid '+c+'22;border-radius:8px;padding:10px;text-align:center"><div style="font-family:monospace;font-size:8px;color:#4a7a8a;margin-bottom:5px">'+row[0]+'</div><div style="font-family:monospace;font-size:11px;color:'+c+'">'+row[1]+'</div></div>';
      });
      html += '</div>';
      var eyesUrl = (k === 'voyager1') ? 'https://eyes.nasa.gov/apps/solar-system/#/sc_voyager_1' : 'https://eyes.nasa.gov/apps/solar-system/#/sc_voyager_2';
      html += '<div style="margin-top:16px;text-align:center">';
      html += '<a href="'+eyesUrl+'" target="_blank" rel="noopener" style="background:rgba(0,255,231,0.1);border:1px solid #00ffe7;color:#00ffe7;padding:10px 24px;border-radius:6px;font-family:monospace;font-size:11px;text-decoration:none;letter-spacing:2px">';
      html += '🌐 NASA EYES — POSITION 3D LIVE</a></div>';
    }
    else if(k==='perseverance'||k==='curiosity') {
      var roverColor = k==='perseverance' ? '#ff6a00' : '#ff4444';
      var roverName = k==='perseverance' ? 'Perseverance' : 'Curiosity';
      html += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:14px">';
      html += '<div style="background:rgba(255,106,0,0.05);border:1px solid '+roverColor+'33;border-radius:8px;padding:14px">';
      html += '<div style="font-family:monospace;font-size:9px;color:'+roverColor+';letter-spacing:2px;margin-bottom:10px">🔴 TÉLÉMÉTRIE MARS</div>';
      Object.entries(d).filter(function(e){return !['name','status','img_url','targets'].includes(e[0]);}).forEach(function(e){
        html += '<div style="display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid rgba(255,255,255,0.04);font-size:10px"><span style="color:#4a7a8a;font-family:monospace">'+e[0].toUpperCase()+'</span><span style="color:#fff;font-family:monospace">'+String(e[1]).substring(0,25)+'</span></div>';
      });
      html += '</div>';
      html += '<div style="background:rgba(255,106,0,0.05);border:1px solid '+roverColor+'33;border-radius:8px;padding:14px" id="mars-weather-box">';
      html += '<div style="font-family:monospace;font-size:9px;color:'+roverColor+';letter-spacing:2px;margin-bottom:8px">🌡️ MÉTÉO MARS (InSight)</div>';
      html += '<div style="color:#4a7a8a;font-family:monospace;font-size:9px">⟳ Chargement météo...</div>';
      html += '</div></div>';
      html += '<div id="mars-gallery" style="margin-top:4px"><div style="color:'+roverColor+';font-family:monospace;font-size:10px;padding:10px">⟳ Chargement photos Mars...</div></div>';
      el.innerHTML = html;
      fetch('/api/mars/weather').then(function(r){return r.json();}).then(function(w){
        var box = document.getElementById('mars-weather-box');
        if(!box) return;
        var keys = Object.keys(w).filter(function(key){return key!=='validity_checks'&&key!=='error';}).slice(0,1);
        if(keys.length && w[keys[0]] && typeof w[keys[0]]==='object') {
          var sol = w[keys[0]];
          box.innerHTML = '<div style="font-family:monospace;font-size:9px;color:'+roverColor+';letter-spacing:2px;margin-bottom:8px">🌡️ MÉTÉO MARS (InSight)</div>';
          if(sol.AT && sol.AT.av!=null) box.innerHTML += '<div style="font-family:monospace;font-size:10px;color:#fff;margin:4px 0">🌡 Temp moy: <span style="color:'+roverColor+'">'+Number(sol.AT.av).toFixed(1)+'°C</span></div>';
          if(sol.PRE && sol.PRE.av!=null) box.innerHTML += '<div style="font-family:monospace;font-size:10px;color:#fff;margin:4px 0">💨 Pression: <span style="color:'+roverColor+'">'+Number(sol.PRE.av).toFixed(0)+' Pa</span></div>';
          if(sol.WD && sol.WD.most_common && sol.WD.most_common.compass_point) box.innerHTML += '<div style="font-family:monospace;font-size:10px;color:#fff;margin:4px 0">🌬 Vent: <span style="color:'+roverColor+'">'+sol.WD.most_common.compass_point+'</span></div>';
        } else {
          box.innerHTML = '<div style="font-family:monospace;font-size:9px;color:'+roverColor+';margin-bottom:6px">🌡️ MÉTÉO MARS</div><div style="font-family:monospace;font-size:9px;color:#4a7a8a">Données InSight hors ligne<br>Mission terminée Nov 2022</div><div style="margin-top:8px;font-family:monospace;font-size:10px;color:#fff">Temp moyenne: <span style="color:'+roverColor+'">-60°C</span></div><div style="font-family:monospace;font-size:10px;color:#fff">Atmosphère: <span style="color:'+roverColor+'">CO₂ 95%</span></div>';
        }
      }).catch(function(){
        var box = document.getElementById('mars-weather-box');
        if(box) box.innerHTML = '<div style="font-family:monospace;font-size:9px;color:'+roverColor+';margin-bottom:6px">🌡️ MARS</div><div style="font-family:monospace;font-size:10px;color:#fff">Temp moy: <span style="color:'+roverColor+'">-60°C</span></div><div style="font-family:monospace;font-size:10px;color:#fff">Pression: <span style="color:'+roverColor+'">~700 Pa</span></div>';
      });
      fetch('https://api.nasa.gov/mars-photos/api/v1/rovers/'+k+'/latest_photos?api_key=DEMO_KEY').then(function(r){return r.json();}).then(function(pd){
        var photos = (pd.latest_photos||[]).slice(0,6);
        var gallery = document.getElementById('mars-gallery');
        if(!gallery||!photos.length) return;
        var gg = '<div style="font-family:monospace;font-size:9px;color:'+roverColor+';letter-spacing:2px;margin-bottom:10px">📷 DERNIÈRES PHOTOS — '+roverName.toUpperCase()+' SUR MARS</div>';
        gg += '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px">';
        photos.forEach(function(p){
          gg += '<div style="border:1px solid '+roverColor+'33;border-radius:6px;overflow:hidden;cursor:pointer" onclick="window.open(\''+p.img_src+'\',\'_blank\')">';
          gg += '<img src="'+p.img_src+'" style="width:100%;aspect-ratio:4/3;object-fit:cover" loading="lazy">';
          gg += '<div style="padding:4px 6px;font-family:monospace;font-size:8px;color:#4a7a8a">Sol '+p.sol+' — '+p.camera.name+'</div></div>';
        });
        gg += '</div>';
        gallery.innerHTML = gg;
      }).catch(function(){
        var gallery = document.getElementById('mars-gallery');
        if(gallery) gallery.innerHTML = '<a href="https://mars.nasa.gov/mars2020/multimedia/raw-images/" target="_blank" style="color:'+roverColor+';font-family:monospace;font-size:10px">🌐 Voir toutes les photos Mars →</a>';
      });
      return;
    }
    else if(k==='jwst') {
      html += '<div style="font-size:2.5rem;text-align:center;margin:8px 0">🔭</div>';
      html += '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:10px;margin-bottom:16px">';
      Object.entries(d).filter(function(e){return !['name','status'].includes(e[0]);}).forEach(function(e){
        html += '<div style="background:rgba(0,20,40,0.8);border:1px solid #c084fc22;border-radius:8px;padding:12px"><div style="font-family:monospace;font-size:8px;color:#4a7a8a;margin-bottom:5px">'+e[0].toUpperCase()+'</div><div style="font-family:monospace;font-size:11px;color:#c084fc">'+String(e[1])+'</div></div>';
      });
      html += '</div>';
      html += '<div id="jwst-gallery" style="margin-top:8px"><div style="color:#c084fc;font-family:monospace;font-size:10px;padding:10px">⟳ Chargement images JWST/APOD...</div></div>';
      el.innerHTML = html;
      fetch('/api/jwst/images').then(function(r){return r.json();}).then(function(imgs){
        if(imgs && imgs.error) return;
        if(!Array.isArray(imgs)) imgs = [];
        var g = '<div style="font-family:monospace;font-size:9px;color:#c084fc;letter-spacing:2px;margin-bottom:10px">🌌 DERNIÈRES IMAGES SPATIALES — NASA APOD</div>';
        g += '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px">';
        imgs.slice(0,6).forEach(function(img){
          if(!img || !img.url) return;
          var openUrl = (img.hdurl || img.url).replace(/\\/g,'\\\\').replace(/'/g,"\\'");
          g += '<div style="border:1px solid #c084fc22;border-radius:6px;overflow:hidden;cursor:pointer" onclick="window.open(\''+openUrl+'\',\'_blank\')">';
          g += '<img src="'+img.url.replace(/"/g,'%22')+'" style="width:100%;aspect-ratio:4/3;object-fit:cover" loading="lazy">';
          g += '<div style="padding:5px;font-family:monospace;font-size:8px;color:#4a7a8a;overflow:hidden;white-space:nowrap;text-overflow:ellipsis">'+(img.title||'')+'</div></div>';
        });
        g += '</div>';
        var jw = document.getElementById('jwst-gallery');
        if(jw) jw.innerHTML = g;
      }).catch(function(){
        var jw = document.getElementById('jwst-gallery');
        if(jw) jw.innerHTML = '<a href="https://webbtelescope.org/news/first-images" target="_blank" style="color:#c084fc;font-family:monospace;font-size:10px">🌐 Voir les images JWST officielles →</a>';
      });
      return;
    }
    else if(k==='hubble') {
      var iconsH = {hubble:'🌌'};
      html += '<div style="font-size:3rem;text-align:center;margin:10px 0">'+(iconsH[k]||'🌌')+'</div>';
      html += '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:10px;margin-top:14px">';
      Object.entries(d).filter(function(e){return e[0]!=='name';}).forEach(function(e) {
        var val = Array.isArray(e[1]) ? e[1].map(function(i){return typeof i==='object'?Object.values(i).join(' — '):i;}).join('<br>') : String(e[1]);
        html += '<div style="background:rgba(0,20,40,0.8);border:1px solid '+c+'22;border-radius:8px;padding:12px"><div style="font-family:monospace;font-size:8px;color:#4a7a8a;margin-bottom:5px">'+e[0].toUpperCase()+'</div><div style="font-family:monospace;font-size:11px;color:#fff;word-break:break-word">'+val+'</div></div>';
      });
      html += '</div>';
      html += '<div id="hubble-gallery-wrap" style="margin-top:18px"><div style="color:#4a7a8a;font-family:monospace;font-size:10px;padding:12px">⟳ Chargement HubbleSite…</div></div>';
      el.innerHTML = html;
      fetch('/api/hubble/images').then(function(r){ return r.json(); }).then(function(data) {
        var wrap = document.getElementById('hubble-gallery-wrap');
        if(!wrap) return;
        var items = Array.isArray(data) ? data : (data && (data.results || data.data || data.images)) || [];
        if(!Array.isArray(items)) items = [];
        var grid = '<div style="font-family:monospace;font-size:9px;color:'+c+';letter-spacing:2px;margin-bottom:10px">📷 HUBBLE — 6 DERNIÈRES (HubbleSite)</div>';
        grid += '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px">';
        var n = 0;
        for(var i=0;i<items.length && n<6;i++) {
          var it = items[i];
          var imgUrl = '';
          var title = '';
          if(typeof it==='string') imgUrl = it;
          else if(it && typeof it==='object') {
            title = (it.title || it.name || it.caption || '') + '';
            imgUrl = it.url || it.image_url || it.thumbnail || it.src || it.image || '';
            if(!imgUrl && it.image_files && it.image_files[0]) imgUrl = it.image_files[0];
            if(!imgUrl && it.imgWithRes && it.imgWithRes[0] && it.imgWithRes[0][0]) imgUrl = it.imgWithRes[0][0];
            if(!imgUrl && it.links && it.links[0]) imgUrl = it.links[0];
          }
          if(!imgUrl || imgUrl.indexOf('http')!==0) continue;
          var safeTitle = title.replace(/</g,'&lt;').replace(/"/g,'&quot;');
          var safeUrl = imgUrl.replace(/"/g,'%22');
          grid += '<div style="border:1px solid '+c+'33;border-radius:8px;overflow:hidden;cursor:pointer;background:rgba(0,20,40,0.6)" onclick="window.open(\'https://hubblesite.org\',\'_blank\')" title="Ouvrir HubbleSite">';
          grid += '<img src="'+safeUrl+'" alt="" style="width:100%;aspect-ratio:4/3;object-fit:cover;display:block" onerror="this.style.display=\'none\'">';
          if(safeTitle) grid += '<div style="padding:6px 8px;font-family:monospace;font-size:8px;color:#4a7a8a;max-height:32px;overflow:hidden">'+safeTitle.substring(0,80)+'</div>';
          grid += '</div>';
          n++;
        }
        grid += '</div>';
        if(n===0) grid = '<div style="color:#4a7a8a;font-family:monospace;font-size:10px;padding:12px">Aucune image parsée — <a href="https://hubblesite.org" target="_blank" rel="noopener" style="color:'+c+'">hubblesite.org</a></div>';
        wrap.innerHTML = grid;
      }).catch(function(){
        var wrap = document.getElementById('hubble-gallery-wrap');
        if(wrap) wrap.innerHTML = '<div style="color:#4a7a8a;font-family:monospace;font-size:10px;padding:12px">API HubbleSite indisponible (CORS ou format) — <a href="https://hubblesite.org" target="_blank" rel="noopener" style="color:'+c+'">Ouvrir hubblesite.org</a></div>';
      });
      return;
    }
    else if(k==='bepi') {
      html += '<div style="font-size:2.5rem;text-align:center;margin:8px 0">🪐</div>';
      html += '<div style="text-align:center;font-family:monospace;font-size:10px;color:#ff9500;margin-bottom:16px;letter-spacing:2px">ESA/JAXA — EN ROUTE VERS MERCURE</div>';
      html += '<div id="bepi-modal-cards" style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:16px">';
      html += '<div style="background:rgba(0,20,40,0.8);border:1px solid #ff950022;border-radius:8px;padding:12px"><div style="font-family:monospace;font-size:8px;color:#4a7a8a;margin-bottom:5px">STATUT</div><div style="font-family:monospace;font-size:11px;color:#ff9500" id="bepi-modal-status">--</div></div>';
      html += '<div style="background:rgba(0,20,40,0.8);border:1px solid #ff950022;border-radius:8px;padding:12px"><div style="font-family:monospace;font-size:8px;color:#4a7a8a;margin-bottom:5px">AGENCE</div><div style="font-family:monospace;font-size:11px;color:#ff9500" id="bepi-modal-agence">--</div></div>';
      html += '<div style="background:rgba(0,20,40,0.8);border:1px solid #ff950022;border-radius:8px;padding:12px"><div style="font-family:monospace;font-size:8px;color:#4a7a8a;margin-bottom:5px">LANCEMENT</div><div style="font-family:monospace;font-size:11px;color:#ff9500" id="bepi-modal-lancement">--</div></div>';
      html += '<div style="background:rgba(0,20,40,0.8);border:1px solid #ff950022;border-radius:8px;padding:12px"><div style="font-family:monospace;font-size:8px;color:#4a7a8a;margin-bottom:5px">ARRIVÉE MERCURE</div><div style="font-family:monospace;font-size:11px;color:#ff9500" id="bepi-modal-arrivee">--</div></div>';
      html += '<div style="background:rgba(0,20,40,0.8);border:1px solid #ff950022;border-radius:8px;padding:12px"><div style="font-family:monospace;font-size:8px;color:#4a7a8a;margin-bottom:5px">DESTINATION</div><div style="font-family:monospace;font-size:11px;color:#ff9500">Mercure</div></div>';
      html += '<div style="background:rgba(0,20,40,0.8);border:1px solid #ff950022;border-radius:8px;padding:12px"><div style="font-family:monospace;font-size:8px;color:#4a7a8a;margin-bottom:5px">MISSION</div><div style="font-family:monospace;font-size:11px;color:#ff9500">2 orbiteurs</div></div>';
      html += '</div>';
      html += '<div style="margin-top:10px;display:flex;gap:10px;flex-wrap:wrap">';
      html += '<a href="https://www.esa.int/Science_Exploration/Space_Science/BepiColombo" target="_blank" rel="noopener" style="background:rgba(255,149,0,0.1);border:1px solid #ff9500;color:#ff9500;padding:8px 16px;border-radius:6px;font-family:monospace;font-size:10px;text-decoration:none">🌐 ESA BepiColombo</a>';
      html += '<a href="https://eyes.nasa.gov/apps/solar-system/#/sc_bepicolombo" target="_blank" rel="noopener" style="background:rgba(255,149,0,0.1);border:1px solid #ff9500;color:#ff9500;padding:8px 16px;border-radius:6px;font-family:monospace;font-size:10px;text-decoration:none">🌐 NASA Eyes 3D</a>';
      html += '</div>';
      el.innerHTML = html;
      fetch('/api/bepi/telemetry').then(function(r){ return r.json(); }).then(function(api){
        var s=document.getElementById('bepi-modal-status'); if(s) s.textContent = api.status || 'EN ROUTE VERS MERCURE';
        var a=document.getElementById('bepi-modal-agence'); if(a) a.textContent = api.agence || 'ESA/JAXA';
        var l=document.getElementById('bepi-modal-lancement'); if(l) l.textContent = api.lancement || '2018';
        var ar=document.getElementById('bepi-modal-arrivee'); if(ar) ar.textContent = api.arrivee || '2025';
      }).catch(function(){
        var s=document.getElementById('bepi-modal-status'); if(s) s.textContent = 'Indisponible';
      });
      return;
    }
    else if(k==='chang_e') {
      html += '<div style="font-size:2.5rem;text-align:center;margin:8px 0">🌕</div>';
      html += '<div style="text-align:center;font-family:monospace;font-size:10px;color:#ffcc00;margin-bottom:16px;letter-spacing:2px">CNSA — MISSION LUNAIRE</div>';
      html += '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:16px">';
      [['AGENCE','CNSA (Chine)'],['MISSION','Chang\'e 6'],['OBJECTIF','Face cachée Lune'],['ÉCHANTILLONS','1.9 kg ramenés'],['RETOUR','Juin 2024'],['HISTORIQUE','1er retour face cachée']].forEach(function(row){
        html += '<div style="background:rgba(0,20,40,0.8);border:1px solid #ffcc0022;border-radius:8px;padding:12px"><div style="font-family:monospace;font-size:8px;color:#4a7a8a;margin-bottom:5px">'+row[0]+'</div><div style="font-family:monospace;font-size:11px;color:#ffcc00">'+row[1]+'</div></div>';
      });
      html += '</div>';
      html += '<div style="background:rgba(255,204,0,0.05);border:1px solid #ffcc0033;border-radius:8px;padding:14px;margin-bottom:14px">';
      html += '<div style="font-family:monospace;font-size:9px;color:#ffcc00;letter-spacing:2px;margin-bottom:8px">🏆 MISSIONS LUNAIRES CNSA</div>';
      [['Chang\'e 3','2013 — 1er alunissage chinois'],['Chang\'e 4','2019 — Face cachée (1er mondial)'],['Chang\'e 5','2020 — Échantillons ramenés'],['Chang\'e 6','2024 — Face cachée échantillons'],['Chang\'e 7','2026 — Prévu pôle sud']].forEach(function(row){
        html += '<div style="display:flex;gap:10px;padding:5px 0;border-bottom:1px solid rgba(255,255,255,0.04);font-size:10px"><span style="color:#ffcc00;font-family:monospace;min-width:80px">'+row[0]+'</span><span style="color:#fff;font-family:monospace">'+row[1]+'</span></div>';
      });
      html += '</div>';
      html += '<a href="https://www.cnsa.gov.cn/" target="_blank" rel="noopener" style="background:rgba(255,204,0,0.1);border:1px solid #ffcc00;color:#ffcc00;padding:8px 16px;border-radius:6px;font-family:monospace;font-size:10px;text-decoration:none">🌐 CNSA OFFICIEL</a>';
    }
    else if(k==='lro') {
      html += '<div style="font-size:2.5rem;text-align:center;margin:8px 0">🌑</div>';
      html += '<div style="text-align:center;font-family:monospace;font-size:10px;color:#aaaaff;margin-bottom:16px;letter-spacing:2px">NASA — EN ORBITE LUNAIRE DEPUIS 2009</div>';
      html += '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:16px">';
      [['AGENCE','NASA'],['ORBITE','Lune ~50 km'],['DEPUIS','2009'],['CAMÉRA','LROC — résolution 0.5m'],['MISSION','Cartographie totale Lune'],['DONNÉES','1 pétaoctet photos']].forEach(function(row){
        html += '<div style="background:rgba(0,20,40,0.8);border:1px solid #aaaaff22;border-radius:8px;padding:12px"><div style="font-family:monospace;font-size:8px;color:#4a7a8a;margin-bottom:5px">'+row[0]+'</div><div style="font-family:monospace;font-size:11px;color:#aaaaff">'+row[1]+'</div></div>';
      });
      html += '</div>';
      html += '<div style="background:rgba(170,170,255,0.05);border:1px solid #aaaaff22;border-radius:8px;padding:14px;margin-bottom:14px">';
      html += '<div style="font-family:monospace;font-size:9px;color:#aaaaff;letter-spacing:2px;margin-bottom:8px">🌑 SITES EXPLORÉS</div>';
      ['Pôle Sud (Artemis cible)','Mare Tranquillitatis (Apollo 11)','Cratère Shackleton','Face cachée — Von Kármán'].forEach(function(site){
        html += '<div style="padding:4px 8px;margin:3px 0;background:rgba(170,170,255,0.07);border-left:2px solid #aaaaff;font-family:monospace;font-size:10px;color:#fff;border-radius:0 4px 4px 0">🔘 '+site+'</div>';
      });
      html += '</div>';
      html += '<div style="display:flex;gap:10px;flex-wrap:wrap">';
      html += '<a href="https://lunar.gsfc.nasa.gov/" target="_blank" rel="noopener" style="background:rgba(170,170,255,0.1);border:1px solid #aaaaff;color:#aaaaff;padding:8px 16px;border-radius:6px;font-family:monospace;font-size:10px;text-decoration:none">🌐 LRO NASA OFFICIEL</a>';
      html += '<a href="https://quickmap.lroc.asu.edu/" target="_blank" rel="noopener" style="background:rgba(170,170,255,0.1);border:1px solid #aaaaff;color:#aaaaff;padding:8px 16px;border-radius:6px;font-family:monospace;font-size:10px;text-decoration:none">🗺️ CARTE LUNE INTERACTIVE</a>';
      html += '</div>';
    }
    else if(k==='parker') {
      html += '<div style="font-size:2.5rem;text-align:center;margin:8px 0">☀️</div>';
      html += '<div style="text-align:center;font-family:monospace;font-size:10px;color:#ffe600;margin-bottom:6px;letter-spacing:2px">NASA — SONDE LA PLUS RAPIDE DE L\'HISTOIRE</div>';
      html += '<div style="text-align:center;font-family:monospace;font-size:28px;color:#ffe600;margin:10px 0">'+(d.distance_au||0.05)+' AU du Soleil</div>';
      html += '<div style="text-align:center;font-family:monospace;font-size:12px;color:#ff6a00;margin-bottom:16px">⚡ Vitesse record : '+(d.speed_kms||192)+' km/s — 692 280 km/h</div>';
      html += '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:16px">';
      [['LANCEMENT','2018'],['RECORD','Objet le + rapide'],['TEMP RESSENTIE','~1400°C'],['PROTECTION','Bouclier carbone'],['MISSION','Étudier la couronne'],['SOURCE','NASA APL']].forEach(function(row){
        html += '<div style="background:rgba(0,20,40,0.8);border:1px solid #ffe60022;border-radius:8px;padding:12px"><div style="font-family:monospace;font-size:8px;color:#4a7a8a;margin-bottom:5px">'+row[0]+'</div><div style="font-family:monospace;font-size:11px;color:#ffe600">'+row[1]+'</div></div>';
      });
      html += '</div>';
      html += '<div style="display:flex;gap:10px;flex-wrap:wrap">';
      html += '<a href="https://science.nasa.gov/mission/parker-solar-probe/" target="_blank" rel="noopener" style="background:rgba(255,230,0,0.1);border:1px solid #ffe600;color:#ffe600;padding:8px 16px;border-radius:6px;font-family:monospace;font-size:10px;text-decoration:none">🌐 NASA PARKER OFFICIEL</a>';
      html += '<a href="https://eyes.nasa.gov/apps/solar-system/#/sc_parker_solar_probe" target="_blank" rel="noopener" style="background:rgba(255,230,0,0.1);border:1px solid #ffe600;color:#ffe600;padding:8px 16px;border-radius:6px;font-family:monospace;font-size:10px;text-decoration:none">☀️ NASA EYES 3D</a>';
      html += '</div>';
    }
    else {
      html += '<div style="font-size:3rem;text-align:center;margin:10px 0">🚀</div>';
      html += '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:10px;margin-top:14px">';
      Object.entries(d).filter(function(e){return e[0]!=='name';}).forEach(function(e) {
        var val = Array.isArray(e[1]) ? e[1].map(function(i){return typeof i==='object'?Object.values(i).join(' — '):i;}).join('<br>') : String(e[1]);
        html += '<div style="background:rgba(0,20,40,0.8);border:1px solid '+c+'22;border-radius:8px;padding:12px"><div style="font-family:monospace;font-size:8px;color:#4a7a8a;margin-bottom:5px">'+e[0].toUpperCase()+'</div><div style="font-family:monospace;font-size:11px;color:#fff;word-break:break-word">'+val+'</div></div>';
      });
      html += '</div>';
    }
    
    el.innerHTML = html;
  }).catch(function(e) {
    el.innerHTML = '<div style="color:#ff2d55;font-family:monospace;font-size:11px">ERREUR: '+e.message+'</div>';
  });
}

function renderSondesGrid(d, g) {
  _sondesData = d || {};
  if (!g) return;
  g.dataset.loaded = '1';
  var labels = {
    voyager1: '🛸 Voyager 1',
    voyager2: '🛸 Voyager 2',
    perseverance: '🤖 Perseverance',
    curiosity: '🔬 Curiosity',
    iss: '🛰️ ISS',
    jwst: '🔭 JWST',
    hubble: '🌌 Hubble',
    parker: '☀️ Parker',
    bepi: '🪐 BepiColombo',
    chang_e: "🌕 Chang'e",
    lro: '🌑 LRO Lune'
  };
  var colors = {
    voyager1: '#00ffe7',
    voyager2: '#00bfff',
    perseverance: '#ff6a00',
    curiosity: '#ff4444',
    iss: '#39ff14',
    jwst: '#c084fc',
    hubble: '#00bfff',
    parker: '#ffe600',
    bepi: '#ff9500',
    chang_e: '#ffcc00',
    lro: '#aaaaff'
  };
  var html = '';
  Object.keys(d || {}).forEach(function (k) {
    if (k === 'generated_at' || !d[k]) return;
    var v = d[k];
    var c = colors[k] || '#00ff88';
    var rows = '';
    Object.entries(v)
      .filter(function (e) {
        return !['name', 'status', 'crew', 'targets', 'news', 'img_url'].includes(e[0]);
      })
      .slice(0, 4)
      .forEach(function (e) {
        rows +=
          '<div style=\"display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid rgba(255,255,255,0.04);font-size:10px\"><span style=\"color:#4a7a8a;font-family:monospace\">' +
          e[0].toUpperCase() +
          '</span><span style=\"color:#fff;font-family:monospace\">' +
          String(e[1]).substring(0, 22) +
          '</span></div>';
      });
    html +=
      '<div onclick=\"openSondeModal(\'' +
      k +
      '\')\" style=\"cursor:pointer;background:rgba(0,20,40,0.85);border:1px solid ' +
      c +
      '22;border-top:2px solid ' +
      c +
      ';border-radius:8px;padding:14px;transition:all 0.2s\" onmouseover=\"this.style.transform=\'translateY(-3px)\';this.style.boxShadow=\'0 6px 24px ' +
      c +
      '22\'\" onmouseout=\"this.style.transform=\'\';this.style.boxShadow=\'\'\">';
    html += '<div style=\"display:flex;align-items:center;gap:10px;margin-bottom:10px\">';
    html +=
      '<div><div style=\"font-family:Orbitron,monospace;font-size:11px;color:#fff;letter-spacing:2px\">' +
      (labels[k] || v.name || k.toUpperCase()) +
      '</div>';
    html +=
      '<div style=\"font-size:9px;color:' +
      c +
      ';letter-spacing:1px;margin-top:2px\">' +
      (v.status || '') +
      '</div></div>';
    html +=
      '<div style=\"margin-left:auto;font-family:monospace;font-size:8px;color:' +
      c +
      ';border:1px solid ' +
      c +
      '44;padding:2px 8px;border-radius:10px\">▶ LIVE</div>';
    html += '</div>' + rows + '</div>';
  });
  var extra = [
    { k: 'bepi', name: 'BepiColombo', status: 'EN ROUTE → MERCURE', c: '#ff9500' },
    { k: 'chang_e', name: 'Chang\'e CNSA', status: 'MISSION LUNAIRE', c: '#ffcc00' },
    { k: 'lro', name: 'LRO — Orbite Lunaire', status: 'EN ORBITE', c: '#aaaaff' }
  ];
  extra.forEach(function (s) {
    html +=
      '<div onclick=\"openSondeModal(\'' +
      s.k +
      '\')\" style=\"cursor:pointer;background:rgba(0,20,40,0.85);border:1px solid ' +
      s.c +
      '22;border-top:2px solid ' +
      s.c +
      ';border-radius:8px;padding:14px;transition:all 0.2s\" onmouseover=\"this.style.transform=\'translateY(-3px)\'\" onmouseout=\"this.style.transform=\'\'\">';
    html += '<div style=\"display:flex;align-items:center;gap:10px;margin-bottom:8px\">';
    html +=
      '<div><div style=\"font-family:Orbitron,monospace;font-size:11px;color:#fff;letter-spacing:2px\">' +
      s.name +
      '</div>';
    html +=
      '<div style=\"font-size:9px;color:' +
      s.c +
      ';margin-top:2px\">' +
      s.status +
      '</div></div>';
    html +=
      '<div style=\"margin-left:auto;font-family:monospace;font-size:8px;color:' +
      s.c +
      ';border:1px solid ' +
      s.c +
      '44;padding:2px 8px;border-radius:10px\">▶ LIVE</div></div></div>';
  });
  g.innerHTML =
    html ||
    '<div style=\"color:#ff2d55;font-family:monospace;font-size:11px;padding:20px\">Aucune donnée</div>';
}

function loadSondes() {
  var g = document.getElementById('sondes-grid');
  if (!g) return;
  if (g.dataset.loaded) return;
  g.innerHTML =
    '<div style=\"color:#00ff88;font-family:monospace;font-size:11px;padding:20px\">⟳ Connexion NASA/JPL...</div>';

  fetch('/api/sondes')
    .then(function (r) {
      return r.json();
    })
    .then(function (d) {
      renderSondesGrid(d, g);
    })
    .catch(function (e) {
      g.innerHTML =
        '<div style=\"color:#ff2d55;font-family:monospace;font-size:11px;padding:20px\">ERREUR API: ' +
        e.message +
        '</div>';
    });
}

async function loadSondesData() {
  var g = document.getElementById('sondes-grid');
  if (g) {
    g.dataset.loaded = '';
    g.innerHTML =
      '<div style=\"color:#00ffcc;font-family:monospace;font-size:11px;padding:20px\">⟳ Connexion SONDES + DSN en cours...</div>';
  }
  try {
    var results = await Promise.all([
      fetch('/api/sondes').then(function (r) {
        return r.json();
      }),
      fetch('/api/bepi/telemetry')
        .then(function (r) {
          return r.json();
        })
        .catch(function () {
          return null;
        })
    ]);
    var sondes = results[0] || {};
    var bepi = results[1];
    if (g) {
      renderSondesGrid(sondes, g);
    } else {
      _sondesData = sondes;
    }

    if (bepi && !bepi.error) {
      var box = document.getElementById('bepi-telemetry-box');
      if (box) {
        var rawPreview = (bepi.raw || '').slice(0, 260);
        box.innerHTML =
          '<div style=\"border:1px solid rgba(255,149,0,0.6);background:rgba(255,149,0,0.04);border-radius:8px;padding:12px;font-family:monospace;font-size:10px;line-height:1.5;color:#ffc107;\">' +
          '<div style=\"font-size:11px;letter-spacing:2px;margin-bottom:8px;color:#ff9500;\">🪐 BEPICOLOMBO — TÉLÉMÉTRIE HORIZONS</div>' +
          '<div style=\"color:#ffaa33;margin-bottom:6px;\">Statut : <span style=\"color:#00ffcc;\">' +
          (bepi.status || 'EN ROUTE VERS MERCURE') +
          '</span></div>' +
          '<div style=\"margin-bottom:4px;\">Agence : <span style=\"color:#00ffcc;\">' +
          (bepi.agence || 'ESA/JAXA') +
          '</span></div>' +
          '<div style=\"margin-bottom:4px;\">Lancement : <span style=\"color:#00ffcc;\">' +
          (bepi.lancement || '2018') +
          '</span> → Arrivée prévue : <span style=\"color:#00ffcc;\">' +
          (bepi.arrivee || '2025') +
          '</span></div>' +
          (rawPreview
            ? '<div style=\"margin-top:8px;color:#ffaa55;opacity:0.85;max-height:140px;overflow:hidden;border-top:1px solid rgba(255,149,0,0.4);padding-top:8px;white-space:pre-wrap;\">' +
              rawPreview.replace(/</g, '&lt;') +
              '...</div>'
            : '') +
          '</div>';
      }
    }

    if (typeof loadDSN === 'function') {
      loadDSN();
    }
  } catch (e) {
    if (g) {
      g.innerHTML =
        '<div style=\"color:#ff2d55;font-family:monospace;font-size:11px;padding:20px\">ERREUR API SONDES: ' +
        e.message +
        '</div>';
    }
  }
}

/**
 * Onglet NEO — /api/neo (NASA NeoWs via station_web)
 */
function loadNEO() {
  var grid = document.getElementById('neo-grid');
  if (!grid) return;
  grid.innerHTML = '<div style="color:#4a7a8a;font-family:monospace;font-size:11px;padding:20px">⟳ Chargement NEO / NASA JPL...</div>';
  fetch('/api/neo')
    .then(function (r) {
      return r.json();
    })
    .then(function (data) {
      if (data.error) {
        grid.innerHTML = '<div style="color:#ff2d55;font-family:monospace;font-size:11px;padding:20px">ERREUR: ' + data.error + '</div>';
        return;
      }
      var list = data.asteroids || [];
      if (!list.length) {
        grid.innerHTML = '<div style="color:#4a7a8a;font-family:monospace;font-size:11px;padding:20px">Aucun astéroïde sur la fenêtre courante.</div>';
        return;
      }
      var html = '';
      list.forEach(function (a) {
        var danger = !!a.dangereux;
        var border = danger ? '#ff2d55' : '#39ff14';
        var bg = danger ? 'rgba(255,45,85,0.08)' : 'rgba(57,255,20,0.06)';
        var nom = String(a.nom || '—').replace(/</g, '&lt;');
        var date = String(a.date || '—');
        var dist = a.distance_km != null ? Number(a.distance_km).toLocaleString() + ' km' : '—';
        var vit = a.vitesse_kms != null ? a.vitesse_kms + ' km/s' : '—';
        var diam = a.diametre_max != null ? a.diametre_max + ' km' : '—';
        var url = String(a.url || '').replace(/"/g, '&quot;');
        html += '<div style="background:' + bg + ';border:1px solid ' + border + '44;border-left:4px solid ' + border + ';border-radius:8px;padding:14px;font-family:monospace;font-size:11px">';
        html += '<div style="font-size:13px;color:#fff;margin-bottom:10px;letter-spacing:1px">' + nom + '</div>';
        html += '<div style="color:#4a7a8a;font-size:9px;margin-bottom:4px">DATE</div><div style="color:#aabbcc;margin-bottom:8px">' + date + '</div>';
        html += '<div style="color:#4a7a8a;font-size:9px;margin-bottom:4px">DISTANCE</div><div style="color:#aabbcc;margin-bottom:8px">' + dist + '</div>';
        html += '<div style="color:#4a7a8a;font-size:9px;margin-bottom:4px">VITESSE</div><div style="color:#aabbcc;margin-bottom:8px">' + vit + '</div>';
        html += '<div style="color:#4a7a8a;font-size:9px;margin-bottom:4px">Ø MAX</div><div style="color:#aabbcc;margin-bottom:10px">' + diam + '</div>';
        if (danger) html += '<div style="color:#ff2d55;font-size:10px;margin-bottom:8px">⚠ POTENTIELLEMENT DANGEREUX</div>';
        if (url) html += '<a href="' + url + '" target="_blank" rel="noopener" style="color:' + border + ';font-size:10px;text-decoration:none;border:1px solid ' + border + '66;padding:6px 12px;border-radius:6px;display:inline-block">🔗 Fiche JPL NASA</a>';
        html += '</div>';
      });
      grid.innerHTML = html;
    })
    .catch(function (e) {
      grid.innerHTML = '<div style="color:#ff2d55;font-family:monospace;font-size:11px;padding:20px">ERREUR RÉSEAU: ' + e.message + '</div>';
    });
}

function loadPassages() {
  var grid = document.getElementById('passages-grid');
  var location = document.getElementById('passages-location');
  var countdown = document.getElementById('passages-countdown');
  if (window._passagesCountdownInterval) {
    clearInterval(window._passagesCountdownInterval);
    window._passagesCountdownInterval = null;
  }
  if (countdown) countdown.innerHTML = '--:--:--';
  grid.innerHTML = '<div style="color:#39ff14;text-align:center;padding:40px;font-family:monospace">📡 DÉTECTION POSITION EN COURS...</div>';

  function fetchPasses(lat, lon, cityName) {
    location.innerHTML = '📍 POSITION : ' + cityName + ' | LAT: ' + lat.toFixed(2) + '° LON: ' + lon.toFixed(2) + '°';
    fetch('/api/iss-passes?lat=' + lat + '&lon=' + lon)
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.error) {
          grid.innerHTML = '<div style="color:red;padding:20px">' + data.error + '</div>';
          return;
        }
        if (!data.passes || data.passes.length === 0) {
          grid.innerHTML = '<div style="color:#aaa;padding:20px">Aucun passage visible cette semaine.</div>';
          return;
        }

        var nextPass = data.passes[0];
        var startSec = Number(nextPass.startUTC);
        window._passagesCountdownInterval = setInterval(function () {
          var now = Math.floor(Date.now() / 1000);
          var diff = startSec - now;
          if (diff <= 0) {
            clearInterval(window._passagesCountdownInterval);
            window._passagesCountdownInterval = null;
            countdown.innerHTML = '🔴 EN COURS !';
            return;
          }
          var h = Math.floor(diff / 3600);
          var m = Math.floor((diff % 3600) / 60);
          var s = diff % 60;
          countdown.innerHTML = String(h).padStart(2, '0') + ':' + String(m).padStart(2, '0') + ':' + String(s).padStart(2, '0');
        }, 1000);

        grid.innerHTML = data.passes.map(function (p) {
          var date = new Date(Number(p.startUTC) * 1000);
          var dateStr = date.toLocaleDateString('fr-FR') + ' ' + date.toLocaleTimeString('fr-FR');
          var elColor = p.maxEl > 45 ? '#39ff14' : p.maxEl > 20 ? '#ffe600' : '#aaa';
          return '<div style="border:1px solid #39ff1444;background:rgba(57,255,20,0.05);padding:15px;border-radius:8px;font-family:monospace">' +
            '<div style="color:#39ff14;font-size:13px;margin-bottom:8px">🛸 ISS</div>' +
            '<div style="color:#fff;font-size:12px">📅 ' + dateStr + '</div>' +
            '<div style="color:#aaa;font-size:11px;margin-top:5px">🧭 Direction : <b style="color:#39ff14">' + (p.startAzCompass || '—') + '</b></div>' +
            '<div style="color:#aaa;font-size:11px">📐 Hauteur max : <b style="color:' + elColor + '">' + p.maxEl + '°</b></div>' +
            '<div style="color:#aaa;font-size:11px">⏱️ Durée : <b style="color:#ffe600">' + Math.floor(p.duration / 60) + ' min ' + (p.duration % 60) + ' sec</b></div>' +
            '<div style="color:#aaa;font-size:11px">✨ Magnitude : <b style="color:#00bfff">' + p.mag + '</b></div>' +
            '</div>';
        }).join('');
      })
      .catch(function (e) {
        grid.innerHTML = '<div style="color:red;padding:20px">Erreur: ' + e + '</div>';
      });
  }

  if (navigator.geolocation) {
    navigator.geolocation.getCurrentPosition(
      function (pos) {
        fetchPasses(pos.coords.latitude, pos.coords.longitude, 'VOTRE POSITION');
      },
      function () {
        fetchPasses(34.8, 1.3, 'TLEMCEN (par défaut)');
      }
    );
  } else {
    fetchPasses(34.8, 1.3, 'TLEMCEN (par défaut)');
  }
}

function ouvrirLive(url) {
  window.open(url, '_blank');
}

function fermerLive() {
  var iframe = document.getElementById('live-iframe');
  var modal = document.getElementById('live-modal');
  if (iframe) iframe.src = '';
  if (modal) modal.style.display = 'none';
}

/* ── Cesium globe 3D — token Ion optionnel : window.CESIUM_ION_TOKEN dans observatoire.html ── */
var cesiumViewer = null;
var issEntity = null;

async function initCesium() {
  if (typeof Cesium === 'undefined') {
    console.warn('Cesium non chargé');
    return;
  }
  if (cesiumViewer) return;

  cesiumViewer = new Cesium.Viewer('cesiumContainer', {
    baseLayerPicker: false,
    navigationHelpButton: false,
    sceneModePicker: false,
    geocoder: false,
    homeButton: false,
    animation: false,
    timeline: false,
    fullscreenButton: true,
    shouldAnimate: true
  });

  try {
    var earthLayer = await Cesium.SingleTileImageryProvider.fromUrl('/static/earth_texture.jpg', {
      rectangle: Cesium.Rectangle.fromDegrees(-180, -90, 180, 90)
    });
    cesiumViewer.imageryLayers.removeAll();
    cesiumViewer.imageryLayers.addImageryProvider(earthLayer);
  } catch (e) {
    console.warn('Cesium earth texture:', e);
    try {
      cesiumViewer.imageryLayers.removeAll();
      cesiumViewer.imageryLayers.addImageryProvider(new Cesium.SingleTileImageryProvider({
        url: '/static/earth_texture.jpg',
        rectangle: Cesium.Rectangle.fromDegrees(-180, -90, 180, 90)
      }));
    } catch (e2) { console.warn('Cesium fallback imagery:', e2); }
  }

  setTimeout(function () {
    if (cesiumViewer && cesiumViewer.resize) cesiumViewer.resize();
  }, 300);

  issEntity = cesiumViewer.entities.add({
    name: 'ISS',
    label: {
      text: '🛸 ISS',
      font: '14pt monospace',
      fillColor: Cesium.Color.fromCssColorString('#39ff14'),
      outlineColor: Cesium.Color.BLACK,
      outlineWidth: 2,
      style: Cesium.LabelStyle.FILL_AND_OUTLINE,
      pixelOffset: new Cesium.Cartesian2(0, -30)
    },
    point: {
      pixelSize: 12,
      color: Cesium.Color.fromCssColorString('#39ff14'),
      outlineColor: Cesium.Color.WHITE,
      outlineWidth: 2
    }
  });

  cesiumViewer.entities.add({
    name: 'ORBITAL-CHOHRA Observatory',
    position: Cesium.Cartesian3.fromDegrees(1.3, 34.8, 0),
    label: {
      text: '🔭 ORBITAL-CHOHRA\nTlemcen, Algérie',
      font: '11pt monospace',
      fillColor: Cesium.Color.fromCssColorString('#ffd700'),
      outlineColor: Cesium.Color.BLACK,
      outlineWidth: 2,
      style: Cesium.LabelStyle.FILL_AND_OUTLINE,
      pixelOffset: new Cesium.Cartesian2(0, -30)
    },
    point: {
      pixelSize: 10,
      color: Cesium.Color.fromCssColorString('#ffd700'),
      outlineColor: Cesium.Color.WHITE,
      outlineWidth: 2
    }
  });

  updateISSOnGlobe();
  setInterval(updateISSOnGlobe, 5000);

  fetch('/api/neo').then(function (r) { return r.json(); }).then(function (d) {
    var n = (d.asteroids && d.asteroids.length) || d.count || 0;
    var neoEl = document.getElementById('globe-neo-count');
    if (neoEl) neoEl.textContent = 'NEO: ' + n;
  }).catch(function () {});
}

async function updateISSOnGlobe() {
  try {
    var r = await fetch('/api/iss');
    var d = await r.json();
    if (d && d.ok === false) {
      var elUn = document.getElementById('globe-iss-pos');
      if (elUn) elUn.textContent = 'ISS: données temporairement indisponibles';
      return;
    }
    var lat = parseFloat(d.lat != null ? d.lat : d.latitude);
    var lon = parseFloat(d.lon != null ? d.lon : d.longitude);
    if (issEntity && !isNaN(lat) && !isNaN(lon)) {
      var altM = 408000;
      if (d.alt != null && !isNaN(parseFloat(d.alt))) {
        var altKm = parseFloat(d.alt);
        altM = altKm > 1000 ? altKm : altKm * 1000;
      }
      issEntity.position = Cesium.Cartesian3.fromDegrees(lon, lat, altM);
      var latStr = lat >= 0 ? lat.toFixed(2) + '°N' : (-lat).toFixed(2) + '°S';
      var lonStr = lon >= 0 ? lon.toFixed(2) + '°E' : (-lon).toFixed(2) + '°W';
      var el = document.getElementById('globe-iss-pos');
      if (el) el.textContent = 'ISS: ' + latStr + ' ' + lonStr;
    }
  } catch (e) {
    console.error('ISS globe:', e);
  }
}

function loadVoyager() {
  var now = new Date();
  var launch1 = new Date('1977-09-05');
  var seconds1 = (now - launch1) / 1000;
  var dist1_km = 24000000000 + (seconds1 * 17.0);
  var signal1_h = (dist1_km / 299792) / 3600;
  var days1 = Math.floor((now - launch1) / 86400000);
  var years1 = Math.floor(days1 / 365);
  var el1 = document.getElementById('v1-dist');
  if (el1) el1.textContent = formatDist(dist1_km);
  el1 = document.getElementById('v1-signal');
  if (el1) el1.textContent = signal1_h.toFixed(1) + ' heures';
  el1 = document.getElementById('v1-age');
  if (el1) el1.textContent = years1 + ' ans ' + (days1 % 365) + ' jours';

  var launch2 = new Date('1977-08-20');
  var seconds2 = (now - launch2) / 1000;
  var dist2_km = 20000000000 + (seconds2 * 15.4);
  var signal2_h = (dist2_km / 299792) / 3600;
  var days2 = Math.floor((now - launch2) / 86400000);
  var years2 = Math.floor(days2 / 365);
  var el2 = document.getElementById('v2-dist');
  if (el2) el2.textContent = formatDist(dist2_km);
  el2 = document.getElementById('v2-signal');
  if (el2) el2.textContent = signal2_h.toFixed(1) + ' heures';
  el2 = document.getElementById('v2-age');
  if (el2) el2.textContent = years2 + ' ans ' + (days2 % 365) + ' jours';

  drawVoyagerMap(dist1_km, dist2_km);
}

function formatDist(km) {
  if (km >= 1e12) return (km / 1e12).toFixed(3) + ' billions km';
  if (km >= 1e9) return (km / 1e9).toFixed(2) + ' milliards km';
  return (km / 1e6).toFixed(1) + ' millions km';
}

function drawVoyagerMap(dist1, dist2) {
  var canvas = document.getElementById('voyager-canvas');
  if (!canvas || !canvas.getContext) return;
  var ctx = canvas.getContext('2d');
  var W = canvas.width;
  var H = canvas.height;
  var cx = W / 2;
  var cy = H / 2;
  var i;
  var UA = 15;

  ctx.clearRect(0, 0, W, H);
  ctx.fillStyle = '#000';
  ctx.fillRect(0, 0, W, H);
  for (i = 0; i < 200; i++) {
    ctx.fillStyle = 'rgba(255,255,255,' + (Math.random() * 0.8) + ')';
    ctx.fillRect(Math.random() * W, Math.random() * H, 1, 1);
  }

  ctx.beginPath();
  ctx.arc(cx, cy, 120 * UA / 10, 0, Math.PI * 2);
  ctx.strokeStyle = 'rgba(0,191,255,0.2)';
  ctx.lineWidth = 1;
  ctx.setLineDash([5, 5]);
  ctx.stroke();
  ctx.setLineDash([]);
  ctx.fillStyle = 'rgba(0,191,255,0.05)';
  ctx.fill();
  ctx.fillStyle = '#00bfff';
  ctx.font = '10px monospace';
  ctx.fillText('HÉLIOSPHÈRE', cx + 125, cy - 10);

  var planets = [
    { name: 'Mercure', r: 0.39 * UA, color: '#aaa' },
    { name: 'Vénus', r: 0.72 * UA, color: '#ffa500' },
    { name: 'Terre', r: 1 * UA, color: '#4fc3f7' },
    { name: 'Mars', r: 1.52 * UA, color: '#ff4444' },
    { name: 'Jupiter', r: 5.2 * UA, color: '#ffcc80' },
    { name: 'Saturne', r: 9.58 * UA, color: '#ffe082' },
    { name: 'Uranus', r: 19.2 * UA, color: '#80deea' },
    { name: 'Neptune', r: 30 * UA, color: '#3f51b5' }
  ];

  planets.forEach(function (p) {
    ctx.beginPath();
    ctx.arc(cx, cy, p.r, 0, Math.PI * 2);
    ctx.strokeStyle = p.color + '44';
    ctx.lineWidth = 0.5;
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(cx + p.r, cy, 3, 0, Math.PI * 2);
    ctx.fillStyle = p.color;
    ctx.fill();
  });

  var sunGrad = ctx.createRadialGradient(cx, cy, 0, cx, cy, 12);
  sunGrad.addColorStop(0, '#fff');
  sunGrad.addColorStop(0.3, '#ffe082');
  sunGrad.addColorStop(1, '#ff8c00');
  ctx.beginPath();
  ctx.arc(cx, cy, 10, 0, Math.PI * 2);
  ctx.fillStyle = sunGrad;
  ctx.fill();
  ctx.fillStyle = '#ffd700';
  ctx.font = 'bold 11px monospace';
  ctx.fillText('☀️ SOLEIL', cx + 12, cy - 5);

  var maxDist = 220;
  var scale1 = Math.min(dist1 / 2.4e10 * maxDist, maxDist);
  var angle1 = -45 * Math.PI / 180;
  var v1x = cx + Math.cos(angle1) * scale1;
  var v1y = cy + Math.sin(angle1) * scale1;
  ctx.beginPath();
  ctx.moveTo(cx, cy);
  ctx.lineTo(v1x, v1y);
  ctx.strokeStyle = 'rgba(57,255,20,0.3)';
  ctx.lineWidth = 1;
  ctx.stroke();
  ctx.beginPath();
  ctx.arc(v1x, v1y, 5, 0, Math.PI * 2);
  ctx.fillStyle = '#39ff14';
  ctx.fill();
  ctx.fillStyle = '#39ff14';
  ctx.font = 'bold 11px monospace';
  ctx.fillText('🛸 V1', v1x + 8, v1y - 5);

  var scale2 = Math.min(dist2 / 2.0e10 * maxDist * 0.85, maxDist * 0.85);
  var angle2 = 220 * Math.PI / 180;
  var v2x = cx + Math.cos(angle2) * scale2;
  var v2y = cy + Math.sin(angle2) * scale2;
  ctx.beginPath();
  ctx.moveTo(cx, cy);
  ctx.lineTo(v2x, v2y);
  ctx.strokeStyle = 'rgba(0,191,255,0.3)';
  ctx.lineWidth = 1;
  ctx.stroke();
  ctx.beginPath();
  ctx.arc(v2x, v2y, 5, 0, Math.PI * 2);
  ctx.fillStyle = '#00bfff';
  ctx.fill();
  ctx.fillStyle = '#00bfff';
  ctx.font = 'bold 11px monospace';
  ctx.fillText('🛸 V2', v2x + 8, v2y + 15);

  ctx.fillStyle = '#ffd700';
  ctx.font = '10px monospace';
  ctx.fillText('⭐ Alpha Centauri →', W - 150, 20);
  ctx.fillText('(4.37 années-lumière)', W - 150, 35);
  ctx.fillText('→ 40 000 ans à cette vitesse', W - 180, 50);
  ctx.fillStyle = '#666';
  ctx.font = '10px monospace';
  ctx.fillText('1 UA = ' + UA + 'px', 10, H - 15);
}

var _dsnTimer = null;

async function loadDSN() {
  if (_dsnTimer) {
    clearTimeout(_dsnTimer);
    _dsnTimer = null;
  }
  try {
    var r = await fetch('/api/dsn');
    var data = await r.json();
    var upd = document.getElementById('dsn-update');
    if (upd) upd.textContent = new Date().toLocaleTimeString();

    var grid = document.getElementById('dsn-grid');
    if (!grid) return;
    grid.innerHTML = '';

    var stationColors = { gdscc: '#39ff14', mdscc: '#ffd700', cdscc: '#00bfff' };
    var stationFlags = { gdscc: '🇺🇸', mdscc: '🇪🇸', cdscc: '🇦🇺' };
    var stations = data.stations || [];

    stations.forEach(function (station) {
      var color = stationColors[station.name] || '#aaa';
      var flag = stationFlags[station.name] || '🌍';
      var friendly = (station.friendlyName || station.name || 'Station').toUpperCase();
      var sname = (station.name || '').toUpperCase();

      var activeDishes = (station.dishes || []).filter(function (d) {
        return (d.targets || []).some(function (t) {
          return t.name !== 'DSN' && t.name !== 'DSS' && t.uplegRange !== '-1';
        });
      });

      var dishHTML = '';
      (station.dishes || []).forEach(function (dish) {
        (dish.targets || []).forEach(function (t) {
          if (t.name === 'DSN' || t.name === 'DSS') return;
          if (t.uplegRange === '-1') return;
          var rtlt = parseFloat(t.rtlt);
          var distKm = parseFloat(t.uplegRange);
          var up = (dish.upSignals && dish.upSignals[0]) || null;
          var down = null;
          (dish.downSignals || []).forEach(function (s) {
            if (s.active === 'true') down = s;
          });

          dishHTML += '<div style="border:1px solid ' + color + '33;border-radius:6px;padding:10px;margin-bottom:8px;background:rgba(0,0,0,0.3)">';
          dishHTML += '<div style="color:' + color + ';font-size:12px;font-weight:bold;margin-bottom:5px">📡 ' + (dish.name || '') + ' → <span style="color:#fff">' + (t.name || '') + '</span></div>';
          dishHTML += '<div style="font-size:10px;color:#888;line-height:1.8">';
          if (distKm > 0 && !isNaN(distKm)) dishHTML += '📏 Distance : <span style="color:#fff">' + formatDistDSN(distKm) + '</span><br>';
          if (rtlt > 0 && !isNaN(rtlt)) dishHTML += '⏱️ Délai signal : <span style="color:#ff4444">' + formatRTLT(rtlt) + '</span><br>';
          if (up) dishHTML += '⬆️ Uplink : <span style="color:#39ff14">' + (up.band || '') + '-band ' + (up.power || '') + 'W</span><br>';
          if (down) dishHTML += '⬇️ Downlink : <span style="color:#00bfff">' + (down.band || '') + '-band ' + formatDataRate(down.dataRate) + '</span><br>';
          dishHTML += '🔧 ' + (dish.activity || 'N/A');
          dishHTML += '</div></div>';
        });
      });

      if (!dishHTML) {
        dishHTML = '<div style="color:#444;font-size:11px;font-family:monospace;padding:10px">Aucune communication active</div>';
      }

      grid.innerHTML += '<div style="border:2px solid ' + color + '44;border-radius:12px;padding:15px;background:rgba(0,0,0,0.4)">';
      grid.innerHTML += '<div style="font-family:monospace;font-size:13px;color:' + color + ';letter-spacing:2px;margin-bottom:12px;border-bottom:1px solid ' + color + '33;padding-bottom:8px">';
      grid.innerHTML += flag + ' ' + friendly + ' <span style="font-size:10px;color:#666;margin-left:10px">' + sname + '</span></div>';
      grid.innerHTML += '<div style="font-size:11px;color:#666;margin-bottom:10px">' + activeDishes.length + ' antenne(s) active(s) / ' + (station.dishes || []).length + ' total</div>';
      grid.innerHTML += dishHTML + '</div>';
    });

    if (stations.length === 0 && data.error) {
      grid.innerHTML = '<div style="color:#ff4444;font-family:monospace;grid-column:1/-1;padding:20px">' + (data.error || 'Aucune donnée') + '</div>';
    }

    drawDSNMap(stations);
    _dsnTimer = setTimeout(loadDSN, 30000);
  } catch (e) {
    var g = document.getElementById('dsn-grid');
    if (g) g.innerHTML = '<div style="color:#ff4444;font-family:monospace;grid-column:1/-1;padding:20px">Erreur: ' + (e.message || e) + '</div>';
  }
}

function formatDistDSN(km) {
  if (km >= 1e9) return (km / 1e9).toFixed(2) + ' Gkm';
  if (km >= 1e6) return (km / 1e6).toFixed(1) + ' Mkm';
  if (km >= 1000) return (km / 1000).toFixed(0) + ' 000 km';
  return km + ' km';
}

function formatRTLT(seconds) {
  if (seconds >= 3600) return (seconds / 3600).toFixed(1) + ' heures';
  if (seconds >= 60) return (seconds / 60).toFixed(1) + ' minutes';
  return seconds.toFixed(1) + ' sec';
}

function formatDataRate(bps) {
  if (!bps || bps === '0' || bps === 0) return '--';
  var n = parseInt(bps, 10);
  if (isNaN(n)) return String(bps);
  if (n >= 1e6) return (n / 1e6).toFixed(1) + ' Mbps';
  if (n >= 1000) return (n / 1000).toFixed(1) + ' kbps';
  return n + ' bps';
}

function drawDSNMap(stations) {
  var canvas = document.getElementById('dsn-canvas');
  if (!canvas || !canvas.getContext) return;
  var ctx = canvas.getContext('2d');
  var W = canvas.width;
  var H = canvas.height;
  var i;
  stations = stations || [];

  ctx.fillStyle = '#0a0a1a';
  ctx.fillRect(0, 0, W, H);
  ctx.strokeStyle = '#111';
  ctx.lineWidth = 1;
  for (i = 0; i < W; i += 80) {
    ctx.beginPath();
    ctx.moveTo(i, 0);
    ctx.lineTo(i, H);
    ctx.stroke();
  }
  for (i = 0; i < H; i += 60) {
    ctx.beginPath();
    ctx.moveTo(0, i);
    ctx.lineTo(W, i);
    ctx.stroke();
  }
  for (i = 0; i < 100; i++) {
    ctx.fillStyle = 'rgba(255,255,255,' + (Math.random() * 0.5) + ')';
    ctx.fillRect(Math.random() * W, Math.random() * H, 1, 1);
  }

  var positions = {
    gdscc: { lon: -116.9, lat: 35.4, color: '#39ff14', label: '🇺🇸 GOLDSTONE' },
    mdscc: { lon: -4.2, lat: 40.4, color: '#ffd700', label: '🇪🇸 MADRID' },
    cdscc: { lon: 148.9, lat: -35.4, color: '#00bfff', label: '🇦🇺 CANBERRA' }
  };

  var pts = [];
  Object.keys(positions).forEach(function (k) {
    var p = positions[k];
    pts.push({ x: (p.lon + 180) / 360 * W, y: (90 - p.lat) / 180 * H });
  });

  ctx.setLineDash([4, 4]);
  ctx.strokeStyle = 'rgba(255,255,255,0.1)';
  ctx.lineWidth = 1;
  for (i = 0; i < pts.length; i++) {
    var j;
    for (j = i + 1; j < pts.length; j++) {
      ctx.beginPath();
      ctx.moveTo(pts[i].x, pts[i].y);
      ctx.lineTo(pts[j].x, pts[j].y);
      ctx.stroke();
    }
  }
  ctx.setLineDash([]);

  Object.keys(positions).forEach(function (key) {
    var pos = positions[key];
    var x = (pos.lon + 180) / 360 * W;
    var y = (90 - pos.lat) / 180 * H;
    ctx.beginPath();
    ctx.arc(x, y, 20, 0, Math.PI * 2);
    ctx.fillStyle = pos.color + '22';
    ctx.fill();
    ctx.beginPath();
    ctx.arc(x, y, 8, 0, Math.PI * 2);
    ctx.fillStyle = pos.color + '66';
    ctx.fill();
    ctx.beginPath();
    ctx.arc(x, y, 4, 0, Math.PI * 2);
    ctx.fillStyle = pos.color;
    ctx.fill();
    ctx.fillStyle = pos.color;
    ctx.font = 'bold 11px monospace';
    ctx.fillText(pos.label, x + 12, y + 4);
    var station = stations.find(function (s) { return s.name === key; });
    if (station) {
      var active = (station.dishes || []).filter(function (d) {
        return (d.targets || []).some(function (t) {
          return t.name !== 'DSN' && t.name !== 'DSS' && t.uplegRange !== '-1';
        });
      }).length;
      ctx.fillStyle = '#666';
      ctx.font = '10px monospace';
      ctx.fillText(active + ' actif(s)', x + 12, y + 18);
    }
  });

  ctx.fillStyle = '#39ff14';
  ctx.font = 'bold 12px monospace';
  ctx.fillText('NASA DSN — 3 STATIONS × 120° — COUVERTURE 24h/24', 20, 25);
}

async function loadSpaceWeather() {
  try {
    var r = await fetch('/api/meteo-spatiale');
    var data = await r.json();
    var box = document.getElementById('meteo-statut');
    if (box) {
      box.innerHTML = "<strong>MÉTÉO SPATIALE NOAA :</strong> " + (data.statut_magnetosphere || "Inconnu") +
        "<br><span style='font-size:0.9em; opacity:0.8;'>" + (data.impact_orbital || "") + "</span>";
      if (data.kp_index >= 4) {
        box.style.color = "#ff4444";
      } else {
        box.style.color = "#00ffcc";
      }
    }
  } catch (e) {
    console.error('Météo spatiale:', e);
  }
}

loadSpaceWeather();
setInterval(loadSpaceWeather, 60000);

async function loadSurvol() {
  try {
    var r = await fetch('/api/survol');
    var d = await r.json();
    if (d.statut === 'ok') {
      var zoneEl = document.getElementById('survol-zone');
      var paysEl = document.getElementById('survol-pays');
      if (zoneEl) zoneEl.textContent = d.zone;
      if (paysEl) paysEl.textContent = '🌍 Pays : ' + d.pays;
    }
  } catch (e) { console.error('Survol:', e); }
}
if (typeof setInterval !== 'undefined') {
  loadSurvol();
  setInterval(loadSurvol, 30000);
}

function _ensurePassagesIssDemoStyles() {
  if (document.getElementById('passages-iss-demo-style')) return;
  var st = document.createElement('style');
  st.id = 'passages-iss-demo-style';
  st.textContent =
    '@keyframes passagesIssSpin{to{transform:rotate(360deg)}}' +
    '.passages-iss-demo{font-family:monospace;font-size:12px;color:#dce8f0;line-height:1.45;position:relative;padding-top:40px;}' +
    '.passages-iss-demo .iss-corner-wrap{position:absolute;top:0;right:0;text-align:right;z-index:2;line-height:1.35;}' +
    '.passages-iss-demo .iss-corner-status{font-size:10px;font-weight:700;letter-spacing:0.04em;white-space:nowrap;}' +
    '.passages-iss-demo .iss-corner-time{font-size:9px;color:#7a9aad;display:block;margin-top:3px;white-space:nowrap;}' +
    '.passages-iss-demo .hdr{display:flex;flex-wrap:wrap;align-items:baseline;justify-content:space-between;gap:8px 16px;margin-bottom:12px;padding-bottom:10px;border-bottom:1px solid rgba(0,255,136,0.18);}' +
    '.passages-iss-demo .status-txt{font-size:10px;letter-spacing:0.16em;font-weight:800;text-transform:uppercase;}' +
    '.passages-iss-demo .status-txt.ok{color:#5eead4;}' +
    '.passages-iss-demo .status-txt.err{color:#fca5a5;}' +
    '.passages-iss-demo .meta{font-size:10px;color:#7a9aad;}' +
    '.passages-iss-demo .sub-h{font-size:10px;color:#6b8499;margin:0 0 12px 0;line-height:1.5;}' +
    '.passages-iss-demo .iss-next-block{margin-bottom:14px;padding:14px 16px;background:rgba(5,18,28,0.92);border:1px solid rgba(0,255,136,0.32);border-radius:10px;box-shadow:0 10px 28px rgba(0,0,0,0.42),inset 0 1px 0 rgba(255,255,255,0.05);}' +
    '.passages-iss-demo .iss-next-label{font-size:10px;letter-spacing:0.22em;font-weight:800;color:#5eead4;text-transform:uppercase;margin-bottom:12px;}' +
    '.passages-iss-demo .iss-next-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px 24px;}' +
    '.passages-iss-demo .iss-next-grid .cell{display:flex;flex-direction:column;gap:4px;}' +
    '.passages-iss-demo .iss-next-grid .k{font-size:9px;letter-spacing:0.08em;color:#8aa4b8;text-transform:uppercase;}' +
    '.passages-iss-demo .iss-next-grid .v{font-size:13px;font-weight:600;color:#f0f7fc;}' +
    '.passages-iss-demo .table-wrap{margin-top:4px;}' +
    '.passages-iss-demo .table-cap{font-size:9px;letter-spacing:0.14em;text-transform:uppercase;color:#6b8aa1;margin:0 0 8px 2px;}' +
    '.passages-iss-demo table{width:100%;border-collapse:separate;border-spacing:0;}' +
    '.passages-iss-demo th{text-align:left;font-size:10px;letter-spacing:0.06em;color:#9bb0c4;font-weight:700;padding:10px 10px 8px;border-bottom:1px solid rgba(0,255,136,0.22);}' +
    '.passages-iss-demo th.num{text-align:right;}' +
    '.passages-iss-demo td{padding:10px 10px;vertical-align:middle;border-bottom:1px solid rgba(255,255,255,0.07);}' +
    '.passages-iss-demo td.num{text-align:right;color:#b8d4ea;}' +
    '.passages-iss-demo .load-row{display:flex;align-items:center;gap:12px;padding:22px 6px;color:#94a8b8;}' +
    '.passages-iss-demo .spin{width:20px;height:20px;border:2px solid rgba(0,255,136,0.2);border-top-color:#5eead4;border-radius:50%;animation:passagesIssSpin 0.75s linear infinite;flex-shrink:0;}';
  document.head.appendChild(st);
}

function _issPassFields(p) {
  var dateStr = p.date_utc || p.date || '—';
  var heureMax = p.heure_max_utc || p.heure_max || '—';
  var elev = p.elevation_max_degres != null && p.elevation_max_degres !== '' ? p.elevation_max_degres : p.elevation;
  var dureeStr = p.duree;
  if (dureeStr == null || dureeStr === '') {
    dureeStr =
      p.duree_minutes != null && isFinite(p.duree_minutes) ? String(Math.round(p.duree_minutes)) + ' min' : '—';
  }
  return {
    dateStr: String(dateStr).replace(/</g, '&lt;'),
    heureMax: String(heureMax).replace(/</g, '&lt;'),
    elev: elev != null ? elev : null,
    dureeStr: String(dureeStr).replace(/</g, '&lt;'),
  };
}

function _stopPassagesIssRelTimer() {
  if (window._passagesIssRelIv) {
    clearInterval(window._passagesIssRelIv);
    window._passagesIssRelIv = null;
  }
  window._passagesIssClientFetchTs = null;
}

function _startPassagesIssRelTimer() {
  _stopPassagesIssRelTimer();
  window._passagesIssClientFetchTs = Date.now();
  function tick() {
    var el = document.getElementById('passages-iss-updated-rel');
    if (!el || !window._passagesIssClientFetchTs) return;
    var mins = Math.floor((Date.now() - window._passagesIssClientFetchTs) / 60000);
    el.textContent = mins < 1 ? 'Updated just now' : 'Updated ' + mins + ' min ago';
  }
  tick();
  window._passagesIssRelIv = setInterval(tick, 60000);
}

function _parsePassStartUtcMs(p) {
  var s = p.date_utc || p.date;
  if (!s || typeof s !== 'string') return NaN;
  var t = s.trim().replace(' ', 'T');
  var ms = Date.parse(t + (t.indexOf('Z') === -1 && t.indexOf('+') === -1 ? 'Z' : ''));
  return ms;
}

async function loadPassagesISS() {
  var box = document.getElementById('passages-iss-container');
  if (!box) return;
  _ensurePassagesIssDemoStyles();
  _stopPassagesIssRelTimer();
  box.innerHTML =
    '<div class="passages-iss-demo"><div class="load-row"><span class="spin" aria-hidden="true"></span><span>Loading ISS data…</span></div></div>';
  try {
    var r = await fetch('/api/passages-iss');
    var data;
    try {
      data = await r.json();
    } catch (parseErr) {
      data = null;
    }
    if (!r.ok || !data) {
      box.innerHTML =
        '<div class="passages-iss-demo">' +
        '<div class="iss-corner-wrap"><span class="iss-corner-status">🔴 DATA ERROR</span></div>' +
        '<p class="sub-h">' + (document.documentElement.lang === 'fr' ? 'Synchronisation en cours · NASA API' : 'Synchronizing · NASA API') + '</p></div>';
      return;
    }
    if (data.error) {
      box.innerHTML =
        '<div class="passages-iss-demo">' +
        '<div class="iss-corner-wrap"><span class="iss-corner-status">🔴 DATA ERROR</span>' +
        '<span class="iss-corner-time">' +
        String(data.message || data.error).replace(/</g, '&lt;') +
        '</span></div>' +
        '<p class="sub-h">' + (document.documentElement.lang === 'fr' ? 'Synchronisation en cours · NASA API' : 'Synchronizing · NASA API') + '</p></div>';
      return;
    }
    var passages = data.prochains_passages || [];
    var coords = String(data.coordonnees_radar || '').replace(/</g, '&lt;');
    if (!passages.length) {
      box.innerHTML =
        '<div class="passages-iss-demo">' +
        '<div class="iss-corner-wrap"><span class="iss-corner-status">🟢 DATA OK</span>' +
        '<span id="passages-iss-updated-rel" class="iss-corner-time">Updated just now</span></div>' +
        '<p class="sub-h">' +
        (coords ? coords + ' — ' : '') +
        'No passes in the current window.</p></div>';
      _startPassagesIssRelTimer();
      return;
    }
    var firstP = passages[0];
    var nf = _issPassFields(firstP);
    var html = '<div class="passages-iss-demo">';
    html += '<div class="iss-corner-wrap"><span class="iss-corner-status">🟢 DATA OK</span>';
    html +=
      '<span id="passages-iss-updated-rel" class="iss-corner-time">Updated just now</span></div>';
    if (coords) html += '<p class="sub-h">' + coords + '</p>';
    if (data.source_tle) {
      html +=
        '<p class="sub-h" style="margin-top:-8px">TLE source · ' +
        String(data.source_tle).replace(/</g, '&lt;') +
        '</p>';
    }
    html += '<div class="iss-next-block">';
    html += '<div class="iss-next-label">Next Pass</div>';
    html += '<div class="iss-next-grid">';
    html += '<div class="cell"><span class="k">date</span><span class="v">' + nf.dateStr + '</span></div>';
    html += '<div class="cell"><span class="k">heure_max</span><span class="v">' + nf.heureMax + '</span></div>';
    html +=
      '<div class="cell"><span class="k">elevation</span><span class="v">' +
      (nf.elev != null ? nf.elev + '°' : '—') +
      '</span></div>';
    html += '<div class="cell"><span class="k">duree</span><span class="v">' + nf.dureeStr + '</span></div>';
    html += '</div></div>';
    html += '<div class="iss-passes-list">';
    html += '<div class="iss-passes-cap">All passes</div>';
    for (var i = 0; i < passages.length; i++) {
      var f = _issPassFields(passages[i]);
      html += '<div class="iss-pass-card">';
      html += '<div class="iss-pass-date">' + f.dateStr + '</div>';
      html += '<div class="iss-pass-grid">';
      html += '<div class="cell"><span class="k">culmination</span><span class="v">' + f.heureMax + '</span></div>';
      html += '<div class="cell"><span class="k">elevation</span><span class="v">' + (f.elev != null ? f.elev + '°' : '—') + '</span></div>';
      html += '<div class="cell"><span class="k">duree</span><span class="v">' + f.dureeStr + '</span></div>';
      html += '</div>';
      html += '</div>';
    }
    html += '</div></div>';
    box.innerHTML = html;
    _startPassagesIssRelTimer();
  } catch (e) {
    console.error('Passages ISS:', e);
    _stopPassagesIssRelTimer();
    box.innerHTML =
      '<div class="passages-iss-demo">' +
      '<div class="iss-corner-wrap"><span class="iss-corner-status">🔴 DATA ERROR</span></div>' +
      '<p class="sub-h">' + (document.documentElement.lang === 'fr' ? 'Synchronisation en cours · NASA API' : 'Synchronizing · NASA API') + '</p></div>';
  }
}

loadPassagesISS();
setInterval(loadPassagesISS, 3600000);

async function loadVoyagerLive() {
  try {
    var r = await fetch('/api/voyager-live');
    var data = await r.json();
    var container = document.getElementById('voyager-live-container');
    if (container && data.voyager_1) {
      var html = '<div style="display: flex; justify-content: space-around; gap: 20px; flex-wrap: wrap;">';
      [ {name: 'VOYAGER 1', d: data.voyager_1}, {name: 'VOYAGER 2', d: data.voyager_2} ].forEach(function (v) {
        html += '<div style="flex: 1; min-width: 250px; border: 1px solid var(--amber); padding: 15px; background: rgba(0,0,0,0.3);">' +
          '<div style="color: var(--amber); font-weight: bold; border-bottom: 1px solid var(--amber); margin-bottom: 10px;">' + v.name + '</div>' +
          '<div style="font-size: 1.2em; color: #00ffcc;">' + (v.d && v.d.distance_km != null ? Number(v.d.distance_km).toLocaleString('fr-FR') : '--') + ' KM</div>' +
          '<div style="font-size: 0.9em; opacity: 0.8;">Vitesse: ' + (v.d && v.d.vitesse_km_s != null ? v.d.vitesse_km_s : '--') + ' km/s</div>' +
          '<div style="font-size: 0.9em; color: #ff4444; margin-top: 5px;">Latence Signal: ' + (v.d && v.d.latence_heures != null ? v.d.latence_heures : '--') + 'h</div>' +
        '</div>';
      });
      html += '</div>';
      container.innerHTML = html;
    }
  } catch (e) { console.error('Erreur Voyager:', e); }
}
loadVoyagerLive();
setInterval(loadVoyagerLive, 60000);
